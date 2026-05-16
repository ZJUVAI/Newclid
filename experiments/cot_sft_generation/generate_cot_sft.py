#!/usr/bin/env python3
"""
Generate CoT SFT data for geometry auxiliary-construction tasks.

Design goal:
1. The generation-time teacher model can see the full record, including aux/proof
   and point coordinates.
2. The final exported training sample exposes only the image and problem text as
   input. Hidden references are used only to supervise the writing of a clean
   visible-only thinking trace.
"""

import argparse
import base64
import json
import logging
import mimetypes
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised in bare environments
    OpenAI = None

logger = logging.getLogger(__name__)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_INPUT_JSONL = REPO_ROOT / "datasets/20260512/geometry_clauses10_samples100k_inverted_fl_points_only.jsonl"
DEFAULT_MODEL_NAME = "qwen/qwen3.5-plus-02-15"
DEFAULT_API_TIMEOUT_SECONDS = float(os.getenv("ZJUVAI_TIMEOUT_SECONDS", "180"))
DEFAULT_API_CALL_RETRIES = int(os.getenv("ZJUVAI_API_RETRIES", "3"))
DEFAULT_API_RETRY_BACKOFF_SECONDS = float(os.getenv("ZJUVAI_API_RETRY_BACKOFF_SECONDS", "3"))
FORBIDDEN_THINKING_PATTERNS = [
    re.compile(r"<\s*/?\s*(aux|proof|numerical_check)\s*>", re.IGNORECASE),
    re.compile(r"\[\d{3}\]"),
    re.compile(r"\bAR\b"),
    re.compile(r"\ba\d{2,}\b"),
    re.compile(r"\br\d+\b"),
    re.compile(r"\bsameclock\b", re.IGNORECASE),
    re.compile(r"\bsimtri?r?\b", re.IGNORECASE),
    re.compile(r"rest of the proof", re.IGNORECASE),
    re.compile(r"hidden reference", re.IGNORECASE),
    re.compile(r"supervisor", re.IGNORECASE),
    re.compile(r"given aux", re.IGNORECASE),
    re.compile(r"\\\([A-Za-z ,]+\\\)"),
    re.compile(r"\bthe construction of point\b", re.IGNORECASE),
    re.compile(r"\bthis point is crucial\b", re.IGNORECASE),
    re.compile(r"\bnecessary relationships\b", re.IGNORECASE),
    re.compile(r"\bit becomes evident\b", re.IGNORECASE),
    re.compile(r"\bwill help us\b", re.IGNORECASE),
    re.compile(r"\bspecific angle relationships\b", re.IGNORECASE),
    re.compile(r"\bnot directly evident\b", re.IGNORECASE),
    re.compile(r"\bdesired angle equality\b", re.IGNORECASE),
    re.compile(r"\bdesired ratio\b", re.IGNORECASE),
    re.compile(r"\bclear relationship\b", re.IGNORECASE),
    re.compile(r"\bfacilitate\b", re.IGNORECASE),
    re.compile(r"\bessential for proving\b", re.IGNORECASE),
    re.compile(r"\bhelp establish\b", re.IGNORECASE),
    re.compile(r"\bcoordinates?\b", re.IGNORECASE),
    re.compile(r"\bcoordinate table\b", re.IGNORECASE),
    re.compile(r"\brotational symmetry\b", re.IGNORECASE),
    re.compile(r"\bcenter of symmetry\b", re.IGNORECASE),
    re.compile(r"\bmidpoint propert(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\$[^$]+\$"),
    re.compile(r"`[^`]+`"),
]
POINT_TAG_RE = re.compile(
    r"<point>\s*([a-z]\w*)\s*</point>\s*<coord>\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)</coord>",
    re.IGNORECASE,
)
RAW_POINT_TAG_RE = re.compile(r"<point>\s*([a-z]\w*)\s*</point>", re.IGNORECASE)
AUX_NEW_POINT_RE = re.compile(r"\bx00\s+([a-z]\w*)\b", re.IGNORECASE)
PROBLEM_BODY_RE = re.compile(r"<problem>\s*(.*?)\s*</problem>", re.DOTALL | re.IGNORECASE)
FORMAL_RELATION_STARTERS = {
    "cong",
    "perp",
    "para",
    "coll",
    "cyclic",
    "midp",
    "eqratio",
    "eqangle",
    "simtri",
    "simtrir",
    "contri",
    "contrir",
    "eqpoint",
}


def configure_logging(log_path=None):
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_path is not None:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


configure_logging()


client = None


def get_client():
    global client
    if client is not None:
        return client
    if OpenAI is None:
        raise ImportError(
            "The 'openai' package is not installed. Install it with `pip install openai` "
            "before running generation."
        )
    client = OpenAI(
        api_key=os.getenv("ZJUVAI_API_KEY"),
        base_url=os.getenv("ZJUVAI_BASE_URL", "https://api.zjuqx.cn/v1"),
        timeout=DEFAULT_API_TIMEOUT_SECONDS,
    )
    return client


def ensure_parent_dir(file_path):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)


def write_json(file_path, data):
    ensure_parent_dir(file_path)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(file_path, records):
    ensure_parent_dir(file_path)
    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_default_output_jsonl():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return SCRIPT_DIR / "generated" / timestamp / "cot_sft_dataset.jsonl"


def build_run_dir(output_jsonl):
    output_path = Path(output_jsonl)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = output_path.stem or "cot_sft"
    return output_path.parent / f"{stem}_artifacts_{timestamp}"


def build_run_manifest(args_dict, output_jsonl, run_dir, model_name):
    return {
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": os.path.abspath(__file__),
        "cwd": os.getcwd(),
        "model_name": model_name,
        "api_base_url": os.getenv("ZJUVAI_BASE_URL", "https://api.zjuqx.cn/v1"),
        "api_timeout_seconds": DEFAULT_API_TIMEOUT_SECONDS,
        "api_call_retries": DEFAULT_API_CALL_RETRIES,
        "api_retry_backoff_seconds": DEFAULT_API_RETRY_BACKOFF_SECONDS,
        "default_input_jsonl": str(DEFAULT_INPUT_JSONL),
        "output_jsonl": os.path.abspath(output_jsonl),
        "run_dir": os.path.abspath(run_dir),
        "arguments": args_dict,
    }


def _encode_image_base64(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if mime_type is None:
        mime_type = "image/png"
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def resolve_input_jsonl(input_path: str) -> Path:
    path = Path(input_path)
    if path.exists():
        return path.resolve()
    repo_relative = (REPO_ROOT / path).resolve()
    if repo_relative.exists():
        return repo_relative
    return path.resolve()


def resolve_image_path(image_path: str, input_jsonl: Path) -> Path:
    raw = Path(image_path)
    if raw.exists():
        return raw.resolve()
    repo_relative = (REPO_ROOT / image_path.lstrip("./")).resolve()
    if repo_relative.exists():
        return repo_relative
    input_relative = (input_jsonl.parent / raw).resolve()
    if input_relative.exists():
        return input_relative
    return raw.resolve()


def extract_aux_and_rest(formal_output: str):
    aux_match = re.search(r"(<aux>.*?</aux>)", formal_output, re.DOTALL)
    if not aux_match:
        return None, None
    aux_part = aux_match.group(1).strip()
    rest_of_output = formal_output.replace(aux_part, "").strip()
    sanitized_rest = re.sub(r" \[\d{3}\]", "", rest_of_output)
    sanitized_rest = re.sub(r" (r\d+|AR)\b", "", sanitized_rest)
    return aux_part, sanitized_rest


def get_point_coords(record):
    coords = record.get("grid_coord") or record.get("point_coords_grid") or {}
    normalized = {}
    for point_name, pair in coords.items():
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            normalized[str(point_name)] = (int(pair[0]), int(pair[1]))
    return normalized


def validate_coord_tags(thinking_text: str, point_coords):
    tagged_points = POINT_TAG_RE.findall(thinking_text)
    if not tagged_points:
        return False, "Missing any <point>...</point><coord>(x,y)</coord> tags"
    if len(tagged_points) > 4:
        return False, "Too many coordinate tags; keep them sparse and only for key visible points"

    seen = {}
    for point_name, x_str, y_str in tagged_points:
        point_name = point_name.lower()
        x_val = int(x_str)
        y_val = int(y_str)
        if point_name not in point_coords:
            return False, f"Tagged point '{point_name}' is not an original visible point"
        expected_x, expected_y = point_coords[point_name]
        if (x_val, y_val) != (expected_x, expected_y):
            return False, (
                f"Coordinate mismatch for point '{point_name}': "
                f"expected ({expected_x}, {expected_y}), got ({x_val}, {y_val})"
            )
        if point_name in seen and seen[point_name] != (x_val, y_val):
            return False, f"Inconsistent repeated coordinates for point '{point_name}'"
        seen[point_name] = (x_val, y_val)

    stripped = POINT_TAG_RE.sub("", thinking_text)
    raw_point_tags = RAW_POINT_TAG_RE.findall(stripped)
    if raw_point_tags:
        return False, (
            "Every <point>...</point> tag must be immediately followed by its matching "
            "<coord>(x,y)</coord>, and point tags may only be used for original visible points"
        )
    return True, "Coordinate tags valid"


def validate_thinking_response(output_text: str, point_coords, require_coord_tags=True):
    if not output_text or not output_text.strip():
        return False, "Output is empty"

    stripped = output_text.strip()
    match = re.fullmatch(r"<thinking>(.*?)</thinking>", stripped, re.DOTALL)
    if not match:
        return False, "Output must be exactly one <thinking>...</thinking> block"

    thinking_text = match.group(1).strip()
    if len(thinking_text) < 80:
        return False, f"<thinking> content too short ({len(thinking_text)} chars, minimum 80)"
    if len(thinking_text) > 2200:
        return False, f"<thinking> content too long ({len(thinking_text)} chars, maximum 2200)"

    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(thinking_text)
        if hit:
            return False, f"Forbidden leakage pattern detected: {hit.group(0)}"

    if require_coord_tags and point_coords:
        ok, message = validate_coord_tags(thinking_text, point_coords)
        if not ok:
            return False, message

    return True, "Valid thinking response"


def extract_json_object(output_text: str):
    if not output_text:
        return None
    text = output_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def build_aux_keyword_expectations(aux_part):
    expectations = []
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").lower()
    if "midp" in inner:
        expectations.append(("midpoint", ["midpoint"]))
    if "cyclic" in inner:
        expectations.append(("cyclic/circle", ["cyclic", "circle", "circumcircle", "concyclic"]))
    if "cong" in inner:
        expectations.append(
            (
                "equal-length",
                [
                    "equal",
                    "congruent",
                    "same distance",
                    "equidistant",
                    "perpendicular bisector",
                ],
            )
        )
    if "perp" in inner:
        expectations.append(("perpendicular", ["perpendicular", "right angle"]))
    if "para" in inner:
        expectations.append(("parallel", ["parallel"]))
    if "coll" in inner:
        expectations.append(("collinear/line", ["collinear", "line through", "passing through", "on line", "on the line", "intersection"]))
    return expectations


def extract_visible_point_names(point_coords):
    return sorted(point_coords.keys())


def extract_point_mentions(text, visible_points):
    mentioned = set()
    lowered = text.lower()
    for point_name in visible_points:
        if re.search(rf"\b{re.escape(point_name.lower())}\b", lowered):
            mentioned.add(point_name.lower())

    single_letter_points = {point.lower() for point in visible_points if len(point) == 1}
    compound_matches = re.findall(
        r"\b(?:segment|triangle|line|angle|side|midpoint(?:\s+of)?|points?)\s+([a-z]{2,6})\b",
        lowered,
    )
    for token in compound_matches:
        if not single_letter_points:
            break
        if all(char in single_letter_points for char in token):
            mentioned.update(token)
    if single_letter_points:
        bare_compounds = re.findall(r"\b([a-z]{2,6})\b", lowered)
        for token in bare_compounds:
            if all(char in single_letter_points for char in token):
                mentioned.update(token)
    return mentioned


def relation_keyword_present(text):
    keywords = [
        "parallel",
        "perpendicular",
        "equal",
        "congruent",
        "ratio",
        "proportion",
        "similar",
        "angle",
        "midpoint",
        "collinear",
        "isosceles",
        "equilateral",
        "circle",
        "cyclic",
        "symmetric",
        "symmetry",
        "diameter",
        "bisect",
        "aligned",
        "alignment",
        "right angle",
        "right-angled",
    ]
    lowered = text.lower()
    if any(keyword in lowered for keyword in keywords):
        return True
    if re.search(r"\b[a-z]{2}\s*=\s*[a-z]{2}\b", lowered):
        return True
    if re.search(r"\bangle\s+[a-z]{2}/[a-z]{2}\s+equals\s+angle\s+[a-z]{2}/[a-z]{2}\b", lowered):
        return True
    return False


def normalize_relation_surface(text):
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    normalized = re.sub(r"\[\d{3}\]", "", cleaned).strip(" ;")
    normalized = re.sub(r"^(?:then|thus|therefore|hence|so)\s+", "", normalized, flags=re.IGNORECASE)
    coincide_match = re.fullmatch(
        r"(?:point\s+)?([a-z]\w*)\s+coincides\s+with\s+(?:point\s+)?([a-z]\w*)\.?",
        normalized,
        flags=re.IGNORECASE,
    )
    if coincide_match:
        point_a = coincide_match.group(1).lower()
        point_b = coincide_match.group(2).lower()
        return f"{point_a} equals {point_b}"
    line_match = re.fullmatch(
        r"(?:point\s+)?([a-z]\w*)\s+lies\s+on\s+(?:the\s+)?(?:line|segment)\s+([a-z]\w*)([a-z]\w*)\.?",
        normalized,
        flags=re.IGNORECASE,
    )
    if line_match:
        point_name = line_match.group(1).lower()
        line_p1 = line_match.group(2).lower()
        line_p2 = line_match.group(3).lower()
        return f"{line_p1}, {line_p2}, {point_name} are collinear"
    ratio_match = re.fullmatch(
        r"([a-z]{2})\s*:\s*([a-z]{2})\s*=\s*([a-z]{2})\s*:\s*([a-z]{2})",
        normalized,
        flags=re.IGNORECASE,
    )
    if ratio_match:
        left_num, left_den, right_num, right_den = [group.lower() for group in ratio_match.groups()]
        return f"ratio {left_num} to {left_den} equals ratio {right_num} to {right_den}"
    equality_match = re.fullmatch(
        r"([a-z]{2})\s*=\s*([a-z]{2})\.?",
        normalized,
        flags=re.IGNORECASE,
    )
    if equality_match:
        left_seg, right_seg = [group.lower() for group in equality_match.groups()]
        return f"{left_seg} equals {right_seg}"
    triangle_binary_match = re.search(
        r"triangles?\s+([a-z]{3})\s+and\s+([a-z]{3})\s+are\s+(similar|congruent)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if triangle_binary_match:
        tri_a = triangle_binary_match.group(1).lower()
        tri_b = triangle_binary_match.group(2).lower()
        relation = triangle_binary_match.group(3).lower()
        return f"triangles {tri_a} and {tri_b} are {relation}"
    triangle_unary_match = re.search(
        r"triangle\s+([a-z]{3})\s+is\s+(similar|congruent)\s+to\s+triangle\s+([a-z]{3})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if triangle_unary_match:
        tri_a = triangle_unary_match.group(1).lower()
        relation = triangle_unary_match.group(2).lower()
        tri_b = triangle_unary_match.group(3).lower()
        return f"triangles {tri_a} and {tri_b} are {relation}"
    tokens = normalized.split()
    if tokens and tokens[0].lower() in FORMAL_RELATION_STARTERS:
        summary = summarize_aux_clause(normalized)
        if summary:
            return summary
    return cleaned


def relation_text_keywords(text):
    lowered = (text or "").lower()
    keywords = set()
    keyword_groups = {
        "parallel": ["parallel"],
        "perpendicular": ["perpendicular", "right angle", "right-angled"],
        "equal": ["equal", "equals", "congruent", "equidistant"],
        "ratio": ["ratio", "proportion"],
        "similar": ["similar"],
        "angle": ["angle"],
        "midpoint": ["midpoint"],
        "collinear": ["collinear", "aligned", "alignment"],
        "circle": ["circle", "cyclic", "concyclic"],
        "bisect": ["bisect"],
        "isosceles": ["isosceles"],
    }
    for label, variants in keyword_groups.items():
        if any(variant in lowered for variant in variants):
            keywords.add(label)
    if re.search(r"\b[a-z]{2}\s*:\s*[a-z]{2}\s*=\s*[a-z]{2}\s*:\s*[a-z]{2}\b", lowered):
        keywords.add("ratio")
    if re.search(r"\b[a-z]{2}\s*=\s*[a-z]{2}\b", lowered):
        keywords.add("equal")
    return keywords


def extract_high_level_structure_markers(text):
    lowered = (text or "").lower()
    marker_groups = {
        "triangle": ["triangle", "triangles"],
        "similar": ["similar"],
        "cyclic": ["cyclic", "concyclic", "circle"],
        "parallelogram": ["parallelogram"],
        "midpoint": ["midpoint"],
    }
    markers = set()
    for label, variants in marker_groups.items():
        if any(variant in lowered for variant in variants):
            markers.add(label)
    return markers


def relations_semantically_match(text_a, text_b, point_names):
    normalized_a = normalize_relation_surface(normalize_point_case(text_a or "", point_names)).lower()
    normalized_b = normalize_relation_surface(normalize_point_case(text_b or "", point_names)).lower()
    if not normalized_a or not normalized_b:
        return False
    if normalized_a == normalized_b:
        return True
    if normalized_a in normalized_b or normalized_b in normalized_a:
        return True
    points_a = extract_point_mentions(normalized_a, point_names)
    points_b = extract_point_mentions(normalized_b, point_names)
    keyword_a = relation_text_keywords(normalized_a)
    keyword_b = relation_text_keywords(normalized_b)
    structure_a = extract_high_level_structure_markers(normalized_a)
    structure_b = extract_high_level_structure_markers(normalized_b)
    if not (points_a and points_b and keyword_a and keyword_b):
        return False
    exclusive_modalities = [
        "angle",
        "ratio",
        "similar",
        "parallel",
        "perpendicular",
        "collinear",
        "midpoint",
        "circle",
        "isosceles",
    ]
    for label in exclusive_modalities:
        if (label in keyword_a) != (label in keyword_b):
            return False
    if ("triangle" in structure_a) != ("triangle" in structure_b):
        return False
    shared_points = points_a & points_b
    shared_keywords = keyword_a & keyword_b
    if "angle" in shared_keywords and len(shared_points) >= 4:
        return True
    if "ratio" in shared_keywords and len(shared_points) >= 4:
        return True
    if {"parallel", "perpendicular"} & shared_keywords and len(shared_points) >= 4:
        return True
    if {"collinear", "midpoint", "circle"} & shared_keywords and len(shared_points) >= 3:
        return True
    if "similar" in shared_keywords and len(shared_points) >= 4:
        return True
    if "equal" in shared_keywords and len(shared_points) >= 3 and "angle" not in keyword_a and "ratio" not in keyword_a:
        return True
    return False


def align_bridge_steps_to_hidden_route(bridge_steps, hidden_route_relations, point_names):
    matches = []
    unmatched = []
    cursor = -1
    for step in bridge_steps:
        relation_text = step.get("relation", "") if isinstance(step, dict) else ""
        matched_index = None
        for idx in range(cursor + 1, len(hidden_route_relations)):
            if relations_semantically_match(relation_text, hidden_route_relations[idx], point_names):
                matched_index = idx
                break
        if matched_index is None:
            matches.append(None)
            unmatched.append(relation_text)
            continue
        matches.append(
            {
                "index": matched_index,
                "relation": hidden_route_relations[matched_index],
            }
        )
        cursor = matched_index
    return {
        "matches": matches,
        "unmatched": unmatched,
    }


def align_dependency_to_support(dependency, available_supports, point_names):
    for support in available_supports:
        if (
            has_long_ngram_overlap(support, dependency, ngram_size=3)
            or dependency.lower() in support.lower()
            or support.lower() in dependency.lower()
            or relations_semantically_match(dependency, support, point_names)
        ):
            return support
    return None


def score_support_relation(support, relation_text, point_names, next_target_relation=""):
    support_points = extract_point_mentions(support, point_names)
    relation_points = extract_point_mentions(relation_text, point_names)
    support_keywords = relation_text_keywords(support)
    relation_keywords = relation_text_keywords(relation_text)
    score = 0
    score += 5 * len(support_points & relation_points)
    score += 3 * len(support_keywords & relation_keywords)

    if next_target_relation:
        next_points = extract_point_mentions(next_target_relation, point_names)
        next_keywords = relation_text_keywords(next_target_relation)
        score += 2 * len(support_points & next_points)
        score += 1 * len(support_keywords & next_keywords)

    if "midpoint" in support_keywords and "equal" in relation_keywords and len(support_points & relation_points) >= 2:
        score += 4
    if "collinear" in support_keywords and "collinear" in relation_keywords and len(support_points & relation_points) >= 2:
        score += 4
    if relations_semantically_match(support, relation_text, point_names):
        score += 2
    return score


def select_support_relations_for_step(relation_text, available_supports, point_names, next_target_relation="", max_supports=2):
    ranked = []
    for support in available_supports:
        if not isinstance(support, str) or not support.strip():
            continue
        score = score_support_relation(
            support,
            relation_text,
            point_names,
            next_target_relation=next_target_relation,
        )
        if score <= 0:
            continue
        ranked.append((score, support))
    ranked.sort(key=lambda item: (-item[0], len(item[1]), item[1].lower()))

    selected = []
    for _, support in ranked:
        if support not in selected:
            selected.append(support)
        if len(selected) >= max_supports:
            break
    return selected


def relation_duplicates_earlier_support(relation_text, available_supports, point_names):
    normalized_relation = normalize_relation_surface(relation_text).lower()
    relation_points = extract_point_mentions(normalized_relation, point_names)
    relation_keywords = relation_text_keywords(normalized_relation)
    for support in available_supports:
        normalized_support = normalize_relation_surface(support).lower()
        if not normalized_support:
            continue
        if normalized_relation == normalized_support:
            return True
        support_points = extract_point_mentions(normalized_support, point_names)
        support_keywords = relation_text_keywords(normalized_support)
        if relation_points == support_points and relation_keywords & support_keywords and relations_semantically_match(relation_text, support, point_names):
            return True
    return False


def build_visible_premise_summaries(record, max_items=12):
    summaries = []
    seen = set()
    for fact in extract_visible_formal_facts(record):
        summary = fact.get("summary")
        if not summary:
            continue
        normalized = summary.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        summaries.append(summary)
        if len(summaries) >= max_items:
            return summaries
    return summaries


def extract_visible_formal_facts(record):
    formal_problem = (
        record.get("llm_input_renamed")
        or record.get("public_problem")
        or record.get("input")
        or ""
    ).strip()
    body_match = PROBLEM_BODY_RE.search(formal_problem)
    body = body_match.group(1).strip() if body_match else formal_problem
    if "?" in body:
        body = body.split("?", 1)[0].strip()

    facts = []
    for clause in [part.strip() for part in body.split(";") if part.strip()]:
        if ":" not in clause:
            continue
        _, relation_text = clause.split(":", 1)
        for fact in split_formal_relation_chain(relation_text):
            tokens = fact.split()
            if not tokens:
                continue
            facts.append(
                {
                    "raw": fact.strip(),
                    "predicate": tokens[0].lower(),
                    "args": [token.lower() for token in tokens[1:]],
                    "summary": summarize_aux_clause(fact),
                }
            )
    return facts


def _canonical_line_key(p1, p2):
    a, b = sorted([p1.lower(), p2.lower()])
    return (a, b)


def visible_parallelogram_supported(record, vertex_word):
    if not isinstance(vertex_word, str) or len(vertex_word) != 4:
        return False
    a, b, c, d = [char.lower() for char in vertex_word]
    visible_facts = extract_visible_formal_facts(record)
    parallel_pairs = set()
    for fact in visible_facts:
        if fact.get("predicate") != "para":
            continue
        args = fact.get("args", [])
        if len(args) < 4:
            continue
        line_1 = _canonical_line_key(args[0], args[1])
        line_2 = _canonical_line_key(args[2], args[3])
        parallel_pairs.add(frozenset([line_1, line_2]))

    needed_pairs = [
        frozenset([
            _canonical_line_key(a, b),
            _canonical_line_key(c, d),
        ]),
        frozenset([
            _canonical_line_key(a, d),
            _canonical_line_key(b, c),
        ]),
    ]
    return all(pair in parallel_pairs for pair in needed_pairs)


def iter_supported_parallelogram_mentions(record, text):
    if not isinstance(text, str) or not text:
        return
    patterns = [
        r"\bparallelogram\s+([a-z]{4})\b",
        r"\b([a-z]{4})\s+forms?\s+(?:an?\s+)?parallelogram\b",
        r"\b([a-z]{4})\s+is\s+(?:an?\s+)?parallelogram\b",
        r"\bquadrilateral\s+([a-z]{4})\s+is\s+(?:an?\s+)?parallelogram\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            vertex_word = match.group(1).lower()
            if visible_parallelogram_supported(record, vertex_word):
                yield match.span()


def aux_constructs_parallelogram(aux_part):
    if not isinstance(aux_part, str) or not aux_part.strip():
        return False
    new_points = {point.lower() for point in extract_aux_new_points(aux_part)}
    if not new_points:
        return False
    para_counts = {point: 0 for point in new_points}
    old_point_unions = {point: set() for point in new_points}
    for clause in parse_aux_clauses(aux_part):
        for fact in split_formal_relation_chain(clause["body"]):
            tokens = fact.split()
            if not tokens or tokens[0].lower() != "para":
                continue
            args = [token.lower() for token in tokens[1:]]
            if len(args) < 4:
                continue
            arg_set = set(args[:4])
            touched_new_points = arg_set & new_points
            if not touched_new_points:
                continue
            for point in touched_new_points:
                para_counts[point] += 1
                old_point_unions[point].update(arg_set - {point})
    return any(para_counts[point] >= 2 and len(old_point_unions[point]) >= 3 for point in new_points)


def iter_aux_constructed_parallelogram_mentions(text, aux_part):
    if not isinstance(text, str) or not text or not aux_constructs_parallelogram(aux_part):
        return
    patterns = [
        r"\bcreate(?:s|d|ing)?\s+(?:an?\s+)?parallelogram\b",
        r"\bform(?:s|ed|ing)?\s+(?:an?\s+)?parallelogram\b",
        r"\bcomplete(?:s|d|ing)?\s+(?:an?\s+)?parallelogram\b",
        r"\bmake(?:s|d|ing)?\s+(?:an?\s+)?parallelogram\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            yield match.span()


def extract_midpoint_relation_signature(text):
    if not isinstance(text, str):
        return None
    lowered = text.lower().strip()
    midpoint_patterns = [
        r"(?:point\s+)?([a-z])\s+looks\s+like\s+the\s+midpoint\s+of\s+([a-z])([a-z])",
        r"(?:point\s+)?([a-z])\s+is\s+the\s+midpoint\s+of\s+([a-z])([a-z])",
        r"(?:point\s+)?([a-z])\s+appears\s+to\s+be\s+the\s+midpoint\s+of\s+([a-z])([a-z])",
    ]
    for pattern in midpoint_patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        midpoint = match.group(1).lower()
        endpoint_a = match.group(2).lower()
        endpoint_b = match.group(3).lower()
        return midpoint, tuple(sorted([endpoint_a, endpoint_b]))
    return None


def coordinate_hints_support_parallelogram(plan):
    if not isinstance(plan, dict):
        return False
    midpoint_map = {}
    for relation in plan.get("coordinate_relations", []):
        signature = extract_midpoint_relation_signature(relation)
        if not signature:
            continue
        midpoint, segment = signature
        midpoint_map.setdefault(midpoint, set()).add(segment)
    for midpoint, segments in midpoint_map.items():
        if len(segments) < 2:
            continue
        segment_points = set()
        for segment in segments:
            segment_points.update(segment)
        if len(segment_points) >= 4:
            return True
    return False


def iter_coordinate_supported_parallelogram_mentions(text, plan):
    if not isinstance(text, str) or not text or not coordinate_hints_support_parallelogram(plan):
        return
    patterns = [
        r"\bparallelogram\s+structure\b",
        r"\bsuggests?\s+(?:a|the)\s+parallelogram\b",
        r"\bsuggests?\s+(?:a|the)\s+parallelogram\s+structure\b",
        r"\bparallelogram-like\s+structure\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            yield match.span()


def _coord_line_metrics(point_coords, p1, p2):
    x1, y1 = point_coords[p1]
    x2, y2 = point_coords[p2]
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    return x1, y1, x2, y2, dx, dy, length_sq


def _visible_fact_coordinate_conflict(fact, point_coords):
    predicate = fact.get("predicate", "")
    args = fact.get("args", [])
    summary = fact.get("summary") or fact.get("raw") or ""
    if predicate == "cong" and len(args) >= 4 and all(point in point_coords for point in args[:4]):
        _, _, _, _, _, _, len1 = _coord_line_metrics(point_coords, args[0], args[1])
        _, _, _, _, _, _, len2 = _coord_line_metrics(point_coords, args[2], args[3])
        if min(len1, len2) == 0:
            return None
        rel_gap = abs(len1 - len2) / max(len1, len2)
        if rel_gap > 0.18:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "perp" and len(args) >= 4 and all(point in point_coords for point in args[:4]):
        _, _, _, _, dx1, dy1, len1 = _coord_line_metrics(point_coords, args[0], args[1])
        _, _, _, _, dx2, dy2, len2 = _coord_line_metrics(point_coords, args[2], args[3])
        if min(len1, len2) == 0:
            return None
        perp_score = abs(dx1 * dx2 + dy1 * dy2) / ((len1 * len2) ** 0.5)
        if perp_score > 0.18:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "para" and len(args) >= 4 and all(point in point_coords for point in args[:4]):
        _, _, _, _, dx1, dy1, len1 = _coord_line_metrics(point_coords, args[0], args[1])
        _, _, _, _, dx2, dy2, len2 = _coord_line_metrics(point_coords, args[2], args[3])
        if min(len1, len2) == 0:
            return None
        parallel_score = abs(dx1 * dy2 - dy1 * dx2) / ((len1 * len2) ** 0.5)
        if parallel_score > 0.14:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "coll" and len(args) >= 3 and all(point in point_coords for point in args[:3]):
        x1, y1 = point_coords[args[0]]
        x2, y2 = point_coords[args[1]]
        x3, y3 = point_coords[args[2]]
        len12 = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        len23 = ((x3 - x2) ** 2 + (y3 - y2) ** 2) ** 0.5
        len13 = ((x3 - x1) ** 2 + (y3 - y1) ** 2) ** 0.5
        longest_side = max(len12, len23, len13, 1.0)
        area_score = abs((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)) / longest_side
        if area_score > 3.0:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "midp" and len(args) >= 3 and all(point in point_coords for point in args[:3]):
        xm, ym = point_coords[args[0]]
        x1, y1 = point_coords[args[1]]
        x2, y2 = point_coords[args[2]]
        seg_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if seg_len == 0:
            return None
        area_score = abs((x2 - x1) * (ym - y1) - (y2 - y1) * (xm - x1)) / seg_len
        midpoint_gap = ((xm - (x1 + x2) / 2) ** 2 + (ym - (y1 + y2) / 2) ** 2) ** 0.5
        if area_score > 3.0 or midpoint_gap > 4.0:
            return f"visible_premise_coordinate_conflict:{summary}"
    return None


def normalize_point_case(text, point_names):
    if not isinstance(text, str) or not point_names:
        return text

    normalized = text
    point_names = [str(point).lower() for point in point_names]
    single_letter_points = {point for point in point_names if len(point) == 1}

    for point in sorted(point_names, key=len, reverse=True):
        normalized = re.sub(
            rf"\b{re.escape(point)}\b",
            point,
            normalized,
            flags=re.IGNORECASE,
        )

    def lower_compound(match):
        token = match.group(0)
        lowered = token.lower()
        if single_letter_points and all(char in single_letter_points for char in lowered):
            return lowered
        return token

    normalized = re.sub(r"\b[A-Za-z]{2,6}\b", lower_compound, normalized)
    return normalized


def parse_goal_expression(visible_goal):
    tokens = [token.strip().lower() for token in (visible_goal or "").split() if token.strip()]
    if not tokens:
        return {"predicate": "", "points": []}
    predicate = tokens[0]
    points = [token for token in tokens[1:] if re.fullmatch(r"[a-z]\w*", token)]
    return {"predicate": predicate, "points": points}


def goal_keyword_hints(visible_goal):
    predicate = parse_goal_expression(visible_goal)["predicate"]
    mapping = {
        "eqratio": ["ratio", "proportion", "similar"],
        "eqangle": ["angle", "parallel", "cyclic"],
        "cong": ["equal", "congruent"],
        "contri": ["congruent", "equal", "matching"],
        "simtri": ["similar", "ratio"],
        "simtrir": ["similar", "ratio"],
        "perp": ["perpendicular", "right angle"],
        "para": ["parallel"],
        "coll": ["collinear", "line"],
        "cyclic": ["cyclic", "circle", "concyclic"],
        "midp": ["midpoint", "equal"],
    }
    return mapping.get(predicate, ["angle", "ratio", "equal"])


def parse_aux_clauses(aux_part):
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").strip()
    clauses = []
    for raw_clause in [part.strip() for part in inner.split(";") if part.strip()]:
        point_match = re.match(r"x00\s+([a-z]\w*)\s*:\s*(.*)", raw_clause, re.IGNORECASE)
        if point_match:
            clauses.append(
                {
                    "new_point": point_match.group(1).lower(),
                    "body": point_match.group(2).strip(),
                }
            )
        else:
            clauses.append({"new_point": None, "body": raw_clause})
    return clauses


def split_formal_relation_chain(text):
    cleaned = re.sub(r"\[\d+\]", "|", text or "")
    raw_parts = [part.strip(" ;") for part in cleaned.split("|") if part.strip(" ;")]
    facts = []
    for part in raw_parts:
        starter = part.split()[0].lower() if part.split() else ""
        if starter in FORMAL_RELATION_STARTERS:
            facts.append(part)
        elif facts:
            facts[-1] = f"{facts[-1]} {part}".strip()
    return facts or ([text.strip()] if text and text.strip() else [])


def extract_aux_point_scope(aux_part):
    scope = set()
    for clause in parse_aux_clauses(aux_part):
        for fact in split_formal_relation_chain(clause["body"]):
            tokens = fact.split()
            for token in tokens[1:]:
                token = token.strip().lower()
                if re.fullmatch(r"[a-z]\w*", token):
                    scope.add(token)
        if clause["new_point"]:
            scope.add(clause["new_point"])
    return scope


def infer_relation_type_from_text(text):
    lowered = (text or "").lower()
    if "midpoint" in lowered:
        return "midpoint"
    if "concyclic" in lowered or "circumcircle" in lowered or "cyclic" in lowered or "circle" in lowered:
        return "cyclic"
    if "collinear" in lowered or " on line " in f" {lowered} " or "line through" in lowered:
        return "collinear"
    if "right angle" in lowered or "right-angled" in lowered:
        return "right_triangle"
    if "perpendicular" in lowered:
        return "perpendicular"
    if "parallel" in lowered:
        return "parallel"
    if "equilateral" in lowered:
        return "equilateral"
    if "isosceles" in lowered:
        return "isosceles"
    if "equal in length" in lowered or "same length" in lowered or "equidistant" in lowered:
        return "equal_length"
    if "congruent" in lowered or re.search(r"\b[a-z]{2}\s*=\s*[a-z]{2}\b", lowered):
        return "equal_length"
    return ""


def build_aux_direct_consequences(aux_part):
    consequences = []
    for clause in parse_aux_clauses(aux_part):
        for fact in split_formal_relation_chain(clause["body"]):
            summary = summarize_aux_clause(fact)
            if summary:
                consequences.append(summary)
    return consequences


def coerce_relation_list_field(value, max_len=3):
    if isinstance(value, list):
        return value[:max_len]
    if isinstance(value, tuple):
        return list(value)[:max_len]
    if not isinstance(value, str):
        return []
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return parsed[:max_len]
    if "\n" in stripped:
        lines = [
            re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip(" ,;")
            for line in stripped.splitlines()
        ]
        lines = [line for line in lines if line]
        if len(lines) >= 2:
            return lines[:max_len]
    if ";" in stripped:
        parts = [part.strip(" ,;") for part in stripped.split(";") if part.strip()]
        if len(parts) >= 2:
            return parts[:max_len]
    return [stripped]


def coordinate_relation_matches_candidate(relation_text, candidate):
    relation_type = infer_relation_type_from_text(relation_text)
    if not relation_type:
        return False

    candidate_type = candidate.get("relation_type", "")

    candidate_points = {str(point).lower() for point in candidate.get("points", [])}
    relation_points = extract_point_mentions(relation_text, sorted(candidate_points))

    equivalent_types = {
        ("perpendicular", "right_triangle"),
        ("equal_length", "isosceles"),
        ("equal_length", "equilateral"),
    }
    if relation_type == candidate_type:
        return candidate_points.issubset(relation_points)
    if (relation_type, candidate_type) in equivalent_types:
        return relation_points.issubset(candidate_points) and len(relation_points) >= 2
    return False


def validate_aux_step_scope(step_text, aux_part, visible_points):
    allowed_points = {point.lower() for point in extract_aux_point_scope(aux_part)}
    candidate_points = sorted(set(visible_points) | allowed_points)
    step_points = extract_point_mentions(step_text, candidate_points)
    if not (step_points & allowed_points):
        return False, "the direct auxiliary relation must mention the auxiliary-point relation explicitly"
    extra_points = step_points - allowed_points
    if extra_points:
        return False, (
            "the direct auxiliary relation should stay on the direct aux consequence and must not "
            f"introduce extra old-figure points yet: {sorted(extra_points)}"
        )
    return True, None


def find_forbidden_shape_shorthand(text):
    if not isinstance(text, str):
        return None
    patterns = [
        r"\bsquare-like\b",
        r"\bsquare\s+[a-z]{4}\b",
        r"\bcomplete(?:s|d|ing)?\s+the\s+square\b",
        r"\bform(?:s|ed|ing)?\s+the\s+square\b",
        r"\bsquare\b",
        r"\brectangle\b",
        r"\brectangular\b",
        r"\bparallelogram\b",
        r"\bsquare structures?\b",
        r"\bsquare configurations?\b",
    ]
    for pattern in patterns:
        hit = re.search(pattern, text, re.IGNORECASE)
        if hit:
            return hit.group(0)
    return None


def find_forbidden_center_shorthand(text):
    if not isinstance(text, str):
        return None
    patterns = [
        r"\bcommon center\b",
        r"\breference center\b",
        r"\bcenter of symmetry\b",
        r"\bsymmetric center\b",
        r"\brotation center\b",
        r"\brotational center\b",
        r"\bcircumcenter\b",
        r"\bserve as the (?:reference )?center\b",
    ]
    for pattern in patterns:
        hit = re.search(pattern, text, re.IGNORECASE)
        if hit:
            return hit.group(0)
    return None


def audit_source_record(record, image_path: Path, aux_part, sanitized_rest):
    issues = []
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec["points"])
    visible_points = set(extract_visible_point_names(point_coords))
    aux_scope = extract_aux_point_scope(aux_part)
    aux_direct = build_aux_direct_consequences(aux_part)
    proof_guidance = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)

    if not image_path.exists():
        issues.append("missing_image")
    if not point_coords:
        issues.append("missing_point_coords")
    if not visible_goal:
        issues.append("missing_visible_goal")
    if goal_points and not goal_points.issubset(visible_points | aux_scope):
        issues.append("goal_references_unknown_points")
    if not aux_direct:
        issues.append("aux_has_no_parseable_direct_consequences")
    if not proof_guidance["goal_finish_relations"]:
        issues.append("proof_guidance_missing_goal_finish_relations")
    relation_conflicts = detect_visible_premise_relation_conflicts(record)
    if relation_conflicts:
        issues.extend(relation_conflicts[:8])
    if point_coords:
        visible_fact_conflicts = []
        for fact in extract_visible_formal_facts(record):
            conflict = _visible_fact_coordinate_conflict(fact, point_coords)
            if conflict and conflict not in visible_fact_conflicts:
                visible_fact_conflicts.append(conflict)
            if len(visible_fact_conflicts) >= 8:
                break
        issues.extend(visible_fact_conflicts)

    return {
        "issues": issues,
        "has_issue": bool(issues),
    }


def detect_visible_premise_relation_conflicts(record):
    issues = []
    visible_facts = extract_visible_formal_facts(record)
    line_pair_predicates = {}
    midpoint_claims = {}

    for fact in visible_facts:
        predicate = fact.get("predicate", "")
        args = fact.get("args", [])
        if predicate in {"para", "perp"} and len(args) >= 4:
            line_pair = frozenset([
                _canonical_line_key(args[0], args[1]),
                _canonical_line_key(args[2], args[3]),
            ])
            line_pair_predicates.setdefault(line_pair, set()).add(predicate)
        elif predicate == "midp" and len(args) >= 3:
            segment_key = _canonical_line_key(args[1], args[2])
            midpoint_claims.setdefault(segment_key, set()).add(args[0])

    for line_pair, predicates in line_pair_predicates.items():
        if {"para", "perp"}.issubset(predicates):
            lines = sorted("".join(points) for points in line_pair)
            issues.append(
                "visible_premise_relation_conflict:"
                f"{'/'.join(lines)} both parallel and perpendicular"
            )
    for segment_key, midpoints in midpoint_claims.items():
        if len(midpoints) > 1:
            issues.append(
                "visible_premise_midpoint_conflict:"
                f"{''.join(segment_key)} has multiple midpoints {','.join(sorted(midpoints))}"
            )
    return issues


def audit_generation_quality(record, generation, aux_part):
    issues = []
    point_coords = get_point_coords(record)
    visible_points = extract_visible_point_names(point_coords)
    coordinate_candidates = build_hidden_coordinate_candidates(point_coords, max_items=64, relax_type_limits=True)
    plan = generation.get("plan_parsed") or {}
    suspicious_markers = [
        "rotational symmetry",
        "common center",
        "reference center",
        "circumcenter",
        "square-like",
        "square structure",
        "square structures",
        "square configuration",
        "square configurations",
        "parallelogram",
        "crucial center",
        "midpoint property",
        "midpoint properties",
        "similarity or angle equality",
        "specific angle conditions",
    ]
    generic_bridge_markers = [
        "midpoint property",
        "midpoint properties",
        "specific angle conditions",
        "similarity or angle equality",
    ]

    if plan:
        unmatched_relations = [
            relation
            for relation in plan.get("coordinate_relations", [])
            if not any(coordinate_relation_matches_candidate(relation, candidate) for candidate in coordinate_candidates)
        ]
        if unmatched_relations:
            issues.append(
                "coordinate_relations_unmatched:" + " | ".join(unmatched_relations)
            )
        direct_relations = plan.get("aux_direct_relations") or plan.get("verification_chain") or [""]
        ok, message = validate_aux_step_scope(direct_relations[0], aux_part, visible_points)
        if not ok:
            issues.append(message)
        bridge_relations = flatten_bridge_relations(plan)
        if not bridge_relations:
            issues.append("missing_bridge_relations")
        write_output = generation.get("write_output") or ""
        if write_output and isinstance(plan.get("bridge_steps"), list):
            sentences = split_into_sentences(write_output)
            search_start = 0
            for idx, step in enumerate(plan["bridge_steps"]):
                match_idx = None
                for sentence_idx in range(search_start, len(sentences)):
                    if bridge_step_relation_realized(sentences[sentence_idx], step):
                        match_idx = sentence_idx
                        break
                if match_idx is None:
                    issues.append(f"bridge_relation_missing_in_body:{idx}")
                    continue
                sentence = sentences[match_idx].lower()
                if any(marker in sentence for marker in generic_bridge_markers):
                    issues.append(f"generic_bridge_phrase:{idx}")
                search_start = match_idx + 1

    text_to_scan = " ".join(
        part for part in [generation.get("write_output"), generation.get("thinking")] if part
    ).lower()
    for marker in suspicious_markers:
        if marker == "parallelogram":
            supported_spans = list(iter_supported_parallelogram_mentions(record, text_to_scan))
            supported_spans.extend(iter_aux_constructed_parallelogram_mentions(text_to_scan, aux_part))
            supported_spans.extend(iter_coordinate_supported_parallelogram_mentions(text_to_scan, plan))
            marker_hits = [match.span() for match in re.finditer(r"\bparallelogram\b", text_to_scan)]
            unsupported_hits = [
                hit
                for hit in marker_hits
                if not any(supported_start <= hit[0] and hit[1] <= supported_end for supported_start, supported_end in supported_spans)
            ]
            if unsupported_hits:
                issues.append(f"suspicious_phrase:{marker}")
            continue
        if marker in text_to_scan:
            issues.append(f"suspicious_phrase:{marker}")

    return {
        "issues": issues,
        "has_issue": bool(issues),
    }


def _candidate_sort_key(candidate):
    relation_priority = {
        "midpoint": 0,
        "collinear": 1,
        "right_triangle": 2,
        "isosceles": 3,
        "equilateral": 4,
        "perpendicular": 5,
        "parallel": 6,
        "equal_length": 7,
    }
    return (
        relation_priority.get(candidate["relation_type"], 99),
        candidate["score"],
        tuple(candidate["points"]),
    )


def build_hidden_coordinate_candidates(point_coords, max_items=10, relax_type_limits=False):
    point_items = sorted(point_coords.items())
    if len(point_items) < 2:
        return []

    def add_candidate(candidates, score, relation_type, points, summary):
        candidates.append(
            {
                "score": round(float(score), 4),
                "relation_type": relation_type,
                "points": list(points),
                "summary": summary,
            }
        )

    def line_metrics(p1, p2):
        x1, y1 = point_coords[p1]
        x2, y2 = point_coords[p2]
        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx * dx + dy * dy
        return dx, dy, length_sq

    segment_names = []
    for i, (p1, _) in enumerate(point_items):
        for p2, _ in point_items[i + 1:]:
            dx, dy, length_sq = line_metrics(p1, p2)
            if length_sq == 0:
                continue
            segment_names.append((p1, p2, dx, dy, length_sq))

    candidates = []

    for i, (a, b, dx1, dy1, len1) in enumerate(segment_names):
        for c, d, dx2, dy2, len2 in segment_names[i + 1:]:
            if len1 == 0 or len2 == 0:
                continue
            dot = dx1 * dx2 + dy1 * dy2
            cross = dx1 * dy2 - dy1 * dx2
            norm = (len1 * len2) ** 0.5
            if norm == 0:
                continue
            parallel_score = abs(cross) / norm
            perp_score = abs(dot) / norm
            if parallel_score <= 0.05:
                add_candidate(
                    candidates,
                    parallel_score,
                    "parallel",
                    [a, b, c, d],
                    f"segments {a}{b} and {c}{d} look parallel",
                )
            if perp_score <= 0.08:
                add_candidate(
                    candidates,
                    perp_score,
                    "perpendicular",
                    [a, b, c, d],
                    f"segments {a}{b} and {c}{d} look perpendicular",
                )
            rel_len_gap = abs(len1 - len2) / max(len1, len2)
            if rel_len_gap <= 0.06:
                add_candidate(
                    candidates,
                    rel_len_gap,
                    "equal_length",
                    [a, b, c, d],
                    f"segments {a}{b} and {c}{d} look equal in length",
                )

    visible_points = [name for name, _ in point_items]
    for mid in visible_points:
        xm, ym = point_coords[mid]
        for i, p1 in enumerate(visible_points):
            for p2 in visible_points[i + 1:]:
                if mid in {p1, p2}:
                    continue
                x1, y1 = point_coords[p1]
                x2, y2 = point_coords[p2]
                area2 = abs((x2 - x1) * (ym - y1) - (y2 - y1) * (xm - x1))
                seg_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                if seg_len == 0:
                    continue
                midpoint_gap = ((xm - (x1 + x2) / 2) ** 2 + (ym - (y1 + y2) / 2) ** 2) ** 0.5
                if area2 / seg_len <= 2.0 and midpoint_gap <= 3.0:
                    score = area2 / seg_len + midpoint_gap
                    add_candidate(
                        candidates,
                        score,
                        "midpoint",
                        [mid, p1, p2],
                        f"point {mid} looks like the midpoint of {p1}{p2}",
                    )

    for i, p1 in enumerate(visible_points):
        x1, y1 = point_coords[p1]
        for j, p2 in enumerate(visible_points[i + 1:], start=i + 1):
            x2, y2 = point_coords[p2]
            for p3 in visible_points[j + 1:]:
                x3, y3 = point_coords[p3]
                len12 = (x2 - x1) ** 2 + (y2 - y1) ** 2
                len23 = (x3 - x2) ** 2 + (y3 - y2) ** 2
                len13 = (x3 - x1) ** 2 + (y3 - y1) ** 2
                if min(len12, len23, len13) == 0:
                    continue
                twice_area = abs((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1))
                longest_side = max(len12, len23, len13) ** 0.5
                area_score = twice_area / max(longest_side, 1.0)
                if area_score <= 2.0:
                    add_candidate(
                        candidates,
                        area_score,
                        "collinear",
                        [p1, p2, p3],
                        f"points {p1}, {p2}, and {p3} look nearly collinear",
                    )

                if len12 >= len23 and len12 >= len13:
                    vertex = p3
                    side_a, side_b, hyp = len13, len23, len12
                elif len23 >= len12 and len23 >= len13:
                    vertex = p1
                    side_a, side_b, hyp = len12, len13, len23
                else:
                    vertex = p2
                    side_a, side_b, hyp = len12, len23, len13
                right_score = abs(side_a + side_b - hyp) / max(hyp, 1.0)
                if right_score <= 0.08:
                    add_candidate(
                        candidates,
                        right_score,
                        "right_triangle",
                        [p1, p2, p3],
                        f"triangle {p1}{p2}{p3} looks right-angled at {vertex}",
                    )

                sides = sorted([len12, len23, len13])
                iso_score = abs(sides[0] - sides[1]) / max(sides[1], 1.0)
                if iso_score <= 0.08:
                    repeated = []
                    if abs(len12 - len13) / max(len12, len13) <= 0.08:
                        repeated.append(p1)
                    if abs(len12 - len23) / max(len12, len23) <= 0.08:
                        repeated.append(p2)
                    if abs(len13 - len23) / max(len13, len23) <= 0.08:
                        repeated.append(p3)
                    if repeated:
                        add_candidate(
                            candidates,
                            iso_score,
                            "isosceles",
                            [p1, p2, p3],
                            f"triangle {p1}{p2}{p3} looks isosceles with apex near {repeated[0]}",
                        )

                eq_score = max(abs(len12 - len23), abs(len23 - len13), abs(len12 - len13)) / max(len12, len23, len13)
                if eq_score <= 0.08:
                    add_candidate(
                        candidates,
                        eq_score,
                        "equilateral",
                        [p1, p2, p3],
                        f"triangle {p1}{p2}{p3} looks close to equilateral",
                    )

    unique_hints = []
    seen = set()
    type_limits = {
        "midpoint": max_items if relax_type_limits else 2,
        "collinear": max_items if relax_type_limits else 2,
        "right_triangle": max_items if relax_type_limits else 2,
        "isosceles": max_items if relax_type_limits else 2,
        "equilateral": max_items if relax_type_limits else 1,
        "perpendicular": max_items if relax_type_limits else 2,
        "parallel": max_items if relax_type_limits else 2,
        "equal_length": max_items if relax_type_limits else 2,
    }
    type_counts = {}
    for candidate in sorted(candidates, key=_candidate_sort_key):
        dedupe_key = (candidate["relation_type"], tuple(candidate["points"]))
        if dedupe_key in seen:
            continue
        relation_type = candidate["relation_type"]
        if type_counts.get(relation_type, 0) >= type_limits.get(relation_type, max_items):
            continue
        seen.add(dedupe_key)
        unique_hints.append(candidate)
        type_counts[relation_type] = type_counts.get(relation_type, 0) + 1
        if len(unique_hints) >= max_items:
            break
    return unique_hints


def build_hidden_coordinate_hints(point_coords, max_items=6):
    hints = build_hidden_coordinate_candidates(point_coords, max_items=max_items)
    if not hints:
        return "No strong coordinate-based relation stands out beyond the visible diagram."
    return "; ".join(candidate["summary"] for candidate in hints)


def build_hidden_coordinate_guidance(point_coords, max_items=8):
    hints = build_hidden_coordinate_candidates(point_coords, max_items=max_items)
    if not hints:
        return "[]"
    return json.dumps(hints, ensure_ascii=False, indent=2)


def build_canonical_coordinate_hint(coordinate_relations):
    cleaned_relations = [
        normalize_relation_surface(relation).strip().rstrip(".")
        for relation in (coordinate_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    cleaned_relations = [relation for relation in cleaned_relations if relation]
    if not cleaned_relations:
        return (
            "the clearest visual cues are the midpoint, collinear, equal-length, parallel, "
            "or perpendicular relations already identified in the figure."
        )
    if len(cleaned_relations) == 1:
        relation_text = cleaned_relations[0]
        return f"the clearest visual cue is that {relation_text}, so the auxiliary plan should keep using that relation."
    if len(cleaned_relations) == 2:
        relation_text = " and that ".join(cleaned_relations)
        return f"the clearest visual cues are that {relation_text}, so the auxiliary plan should keep using those relations."
    relation_text = "; ".join(cleaned_relations[:-1]) + f"; and {cleaned_relations[-1]}"
    return f"the clearest visual cues are that {relation_text}, so the auxiliary plan should keep using those relations."


def build_canonical_helper_idea(aux_direct_relations, goal_bottleneck=""):
    relation_text = " ".join(
        relation.lower()
        for relation in (aux_direct_relations or [])
        if isinstance(relation, str)
    )
    mechanism_parts = []
    if "midpoint" in relation_text:
        mechanism_parts.append("places a midpoint on the needed segment")
    if "perpendicular" in relation_text or "right angle" in relation_text:
        mechanism_parts.append("creates a perpendicular link")
    if "parallel" in relation_text:
        mechanism_parts.append("creates a parallel link")
    if any(token in relation_text for token in [" equal", "equals", "congruent", "="]):
        mechanism_parts.append("creates equal-length links")
    if "collinear" in relation_text:
        mechanism_parts.append("places the helper on an existing line")
    if any(token in relation_text for token in ["cyclic", "circle", "concyclic"]):
        mechanism_parts.append("places the helper on a useful circle")
    if not mechanism_parts:
        mechanism_parts.append("creates the missing geometric link")

    bottleneck_text = (goal_bottleneck or "").lower()
    goal_phrase = "so the goal-side relation can be connected"
    if "angle" in bottleneck_text:
        goal_phrase = "so the missing angle relation can be connected"
    elif any(token in bottleneck_text for token in ["ratio", "proportion"]):
        goal_phrase = "so the missing ratio relation can be connected"
    elif any(token in bottleneck_text for token in ["similar", "congruent", "triangle"]):
        goal_phrase = "so the final triangle comparison can be connected"

    if len(mechanism_parts) == 1:
        mechanism_text = mechanism_parts[0]
    elif len(mechanism_parts) == 2:
        mechanism_text = f"{mechanism_parts[0]} and {mechanism_parts[1]}"
    else:
        mechanism_text = ", ".join(mechanism_parts[:-1]) + f", and {mechanism_parts[-1]}"
    return f"we need a helper that {mechanism_text} {goal_phrase}."


def build_canonical_anchor_relation(anchor_points, visible_relations):
    clean_points = [point.lower() for point in (anchor_points or []) if isinstance(point, str) and point.strip()]
    anchor_text = join_natural_list(clean_points) if clean_points else "the main visible points"
    relation_parts = []
    anchor_set = set(clean_points)
    for relation in visible_relations or []:
        if not isinstance(relation, str) or not relation.strip():
            continue
        if len(extract_point_mentions(relation, clean_points)) < 2:
            continue
        relation_parts.append(normalize_relation_surface(relation).strip().rstrip("."))
        if len(relation_parts) >= 2:
            break
    if len(relation_parts) == 1:
        return f"points {anchor_text} form the main visible frame, with {relation_parts[0]}."
    if len(relation_parts) >= 2:
        return f"points {anchor_text} form the main visible frame, with {relation_parts[0]} and {relation_parts[1]}."
    if anchor_set:
        return f"points {anchor_text} form the main visible frame of the diagram."
    return "the named visible points form the main frame of the diagram."


def build_canonical_figure_overview(anchor_points, visible_relations, coordinate_relations, visible_points):
    anchor_set = {point.lower() for point in (anchor_points or []) if isinstance(point, str)}
    candidate_relations = []
    extra_points = []
    for relation in list(visible_relations or []) + list(coordinate_relations or []):
        if not isinstance(relation, str) or not relation.strip():
            continue
        mentioned = extract_point_mentions(relation, visible_points)
        if not (mentioned - anchor_set):
            continue
        candidate_relations.append(normalize_relation_surface(relation).strip().rstrip("."))
        for point in sorted(mentioned - anchor_set):
            if point not in extra_points:
                extra_points.append(point)
        if len(candidate_relations) >= 2 and len(extra_points) >= 2:
            break
    if not candidate_relations:
        return "the broader figure introduces additional visible points and relations beyond the anchor frame."
    overview_parts = []
    if extra_points:
        overview_parts.append(
            f"beyond the anchor points, the broader figure also involves {join_natural_list(extra_points)}"
        )
    if len(candidate_relations) == 1:
        relation_text = candidate_relations[0]
    else:
        relation_text = f"{candidate_relations[0]} and {candidate_relations[1]}"
    if overview_parts:
        return f"{overview_parts[0]}, with {relation_text}."
    return f"the broader figure also uses {relation_text}."


def build_canonical_goal_bottleneck(visible_goal):
    goal_spec = parse_goal_expression(visible_goal or "")
    goal_points = [point.lower() for point in goal_spec.get("points", []) if isinstance(point, str)]
    point_text = join_natural_list(goal_points) if goal_points else "the named target points"
    predicate = (goal_spec.get("predicate") or "").lower()
    if "ratio" in predicate:
        return f"the target ratio around {point_text} still lacks a concrete bridge between the needed segment comparisons."
    if "angle" in predicate:
        return f"the target angle comparison around {point_text} still lacks a concrete bridge between the needed directions."
    if "simtri" in predicate or "contri" in predicate:
        return f"the target triangle comparison around {point_text} still lacks enough direct side or angle correspondences."
    if "cong" in predicate or "equal" in predicate:
        return f"the target equality around {point_text} still lacks a concrete bridge from the visible relations."
    return f"the target relation around {point_text} still lacks a concrete bridge from the visible figure."


def validate_descriptive_text(value, field_name, min_chars=12, point_names=None, ignored_forbidden_patterns=None):
    if isinstance(value, str) and point_names:
        value = normalize_point_case(value, point_names)
    if not isinstance(value, str) or len(value.strip()) < min_chars:
        return False, f"{field_name} must be a non-empty descriptive string", None
    value = value.strip()
    if RAW_POINT_TAG_RE.search(value) or POINT_TAG_RE.search(value):
        return False, f"{field_name} must not contain point tags", None
    ignored_forbidden_patterns = set(ignored_forbidden_patterns or [])
    for pattern in FORBIDDEN_THINKING_PATTERNS:
        if pattern.pattern in ignored_forbidden_patterns:
            continue
        hit = pattern.search(value)
        if hit:
            return False, f"{field_name} contains forbidden pattern: {hit.group(0)}", None
    return True, None, value


def validate_relation_list(items, field_name, visible_points, min_len=2, max_len=3, min_chars=12):
    if isinstance(items, list) and len(items) > max_len:
        items = items[:max_len]
    if not isinstance(items, list) or not (min_len <= len(items) <= max_len):
        return False, f"{field_name} must be a list with {min_len} to {max_len} items", None
    cleaned = []
    for idx, item in enumerate(items):
        ok, message, cleaned_item = validate_descriptive_text(
            item,
            f"{field_name}[{idx}]",
            min_chars=min_chars,
            point_names=visible_points,
        )
        if not ok:
            return False, message, None
        cleaned_item = normalize_relation_surface(cleaned_item)
        if field_name == "coordinate_relations" and re.search(r"\bsymmetr(?:y|ic)\b|\brotation(?:al)?\b", cleaned_item, re.IGNORECASE):
            return False, (
                f"{field_name}[{idx}] should name concrete equal/parallel/perpendicular/midpoint/collinear cues, "
                "not high-level symmetry or rotation claims"
            ), None
        if not relation_keyword_present(cleaned_item):
            return False, f"{field_name}[{idx}] must mention a concrete geometric relation", None
        mentioned = extract_point_mentions(cleaned_item, visible_points)
        if len(mentioned) < 2:
            return False, f"{field_name}[{idx}] must mention at least two visible points", None
        cleaned.append(cleaned_item)
    return True, None, cleaned


def canonicalize_visible_relations(items, visible_points, fallback_summaries, min_len=2, max_len=4, min_chars=5):
    raw_items = items if isinstance(items, list) else []
    cleaned = []
    used_lower = set()
    fallback_queue = [summary for summary in (fallback_summaries or []) if isinstance(summary, str) and summary.strip()]

    def next_fallback():
        while fallback_queue:
            candidate = normalize_relation_surface(fallback_queue.pop(0).strip())
            lowered = candidate.lower()
            if lowered not in used_lower:
                return candidate
        return None

    for item in raw_items[:max_len]:
        ok, _, cleaned_item = validate_descriptive_text(
            item,
            "visible_relations_item",
            min_chars=min_chars,
            point_names=visible_points,
        )
        if ok and cleaned_item:
            cleaned_item = normalize_relation_surface(cleaned_item)
            mentioned = extract_point_mentions(cleaned_item, visible_points)
            if relation_keyword_present(cleaned_item) and len(mentioned) >= 2:
                lowered = cleaned_item.lower()
                if lowered not in used_lower:
                    cleaned.append(cleaned_item)
                    used_lower.add(lowered)
                    continue
        fallback = next_fallback()
        if fallback:
            cleaned.append(fallback)
            used_lower.add(fallback.lower())

    while len(cleaned) < min_len:
        fallback = next_fallback()
        if not fallback:
            break
        cleaned.append(fallback)
        used_lower.add(fallback.lower())

    return cleaned[:max_len]


def canonicalize_coordinate_relations(items, visible_points, coordinate_candidates, min_len=2, max_len=3):
    raw_items = items if isinstance(items, list) else []
    cleaned = []
    used_lower = set()
    candidates = coordinate_candidates or []
    fallback_queue = []
    for candidate in candidates:
        summary = candidate.get("summary") if isinstance(candidate, dict) else None
        if isinstance(summary, str) and summary.strip():
            fallback_queue.append(summary.strip())

    def next_fallback():
        while fallback_queue:
            candidate = normalize_relation_surface(fallback_queue.pop(0))
            lowered = candidate.lower()
            if lowered not in used_lower:
                return candidate
        return None

    for item in raw_items[:max_len]:
        ok, _, cleaned_item = validate_descriptive_text(
            item,
            "coordinate_relations_item",
            min_chars=12,
            point_names=visible_points,
        )
        if ok and cleaned_item:
            cleaned_item = normalize_relation_surface(cleaned_item)
            mentioned = extract_point_mentions(cleaned_item, visible_points)
            if (
                relation_keyword_present(cleaned_item)
                and len(mentioned) >= 2
                and any(coordinate_relation_matches_candidate(cleaned_item, candidate) for candidate in candidates)
            ):
                lowered = cleaned_item.lower()
                if lowered not in used_lower:
                    cleaned.append(cleaned_item)
                    used_lower.add(lowered)
                    continue
        fallback = next_fallback()
        if fallback:
            cleaned.append(fallback)
            used_lower.add(fallback.lower())

    while len(cleaned) < min_len:
        fallback = next_fallback()
        if not fallback:
            break
        cleaned.append(fallback)
        used_lower.add(fallback.lower())

    covered_points = extract_point_mentions(" ".join(cleaned), visible_points)
    while len(cleaned) < max_len and len(covered_points) < 3:
        fallback = next_fallback()
        if not fallback:
            break
        cleaned.append(fallback)
        used_lower.add(fallback.lower())
        covered_points = extract_point_mentions(" ".join(cleaned), visible_points)

    return cleaned[:max_len]


def canonicalize_aux_direct_relations(items, aux_part, visible_points, preferred_immediate, min_len=1, max_len=3):
    raw_items = coerce_relation_list_field(items, max_len=max_len)
    cleaned = []
    used_lower = set()
    fallback_queue = [
        normalize_relation_surface(relation).strip()
        for relation in (preferred_immediate or [])
        if isinstance(relation, str) and relation.strip()
    ]

    def next_fallback():
        while fallback_queue:
            candidate = fallback_queue.pop(0)
            lowered = candidate.lower()
            ok, _ = validate_aux_step_scope(candidate, aux_part, visible_points)
            if lowered not in used_lower and ok:
                return candidate
        return None

    for item in raw_items[:max_len]:
        ok, _, cleaned_item = validate_descriptive_text(
            item,
            "aux_direct_relations_item",
            min_chars=5,
            point_names=visible_points + [point.lower() for point in extract_aux_new_points(aux_part or "")],
        )
        if ok and cleaned_item:
            cleaned_item = normalize_relation_surface(cleaned_item)
            lowered = cleaned_item.lower()
            scope_ok, _ = validate_aux_step_scope(cleaned_item, aux_part, visible_points)
            if relation_keyword_present(cleaned_item) and scope_ok and lowered not in used_lower:
                cleaned.append(cleaned_item)
                used_lower.add(lowered)
                continue
        fallback = next_fallback()
        if fallback:
            cleaned.append(fallback)
            used_lower.add(fallback.lower())

    while len(cleaned) < min_len:
        fallback = next_fallback()
        if not fallback:
            break
        cleaned.append(fallback)
        used_lower.add(fallback.lower())

    return cleaned[:max_len]


def build_hidden_proof_guidance(
    sanitized_rest,
    aux_part,
    visible_goal,
    max_aux=6,
    max_aux_bridge=4,
    max_bridge=4,
    max_finish=4,
):
    proof_match = re.search(r"<proof>(.*?)</proof>", sanitized_rest or "", re.DOTALL | re.IGNORECASE)
    aux_direct = build_aux_direct_consequences(aux_part)
    aux_scope = {point.lower() for point in extract_aux_point_scope(aux_part)}
    if not proof_match:
        return {
            "immediate_aux_consequences": aux_direct[:max_aux],
            "aux_bridge_relations": [],
            "bridge_relations": [],
            "goal_finish_relations": [],
        }

    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec["points"])
    new_points = {point.lower() for point in extract_aux_new_points(aux_part)}
    raw_clauses = [part.strip() for part in proof_match.group(1).split(";") if part.strip()]
    summaries = []
    for clause in raw_clauses:
        summary = summarize_aux_clause(clause)
        if not summary:
            continue
        summary = normalize_relation_surface(summary)
        lowered = clause.lower()
        clause_points = set(re.findall(r"\b([a-z]\w*)\b", lowered))
        summaries.append(
            {
                "summary": summary,
                "points": clause_points,
                "has_new_point": bool(clause_points & new_points),
                "has_goal_point": bool(clause_points & goal_points),
            }
        )

    immediate = []
    aux_bridge = []
    bridge = []
    finish = []
    seen = set()

    for text in aux_direct:
        if text not in seen:
            seen.add(text)
            immediate.append(text)
            if len(immediate) >= max_aux:
                break

    for item in summaries:
        text = item["summary"]
        if (
            item["has_new_point"]
            and not item["has_goal_point"]
            and text not in seen
            and item["points"].issubset(aux_scope)
        ):
            seen.add(text)
            immediate.append(text)
            if len(immediate) >= max_aux:
                break

    for item in summaries:
        text = item["summary"]
        if (
            item["has_new_point"]
            and text not in seen
            and not item["points"].issubset(aux_scope)
        ):
            seen.add(text)
            aux_bridge.append(text)
            if len(aux_bridge) >= max_aux_bridge:
                break

    for item in summaries:
        text = item["summary"]
        if item["has_new_point"] and item["has_goal_point"] and text not in seen:
            seen.add(text)
            bridge.append(text)
            if len(bridge) >= max_bridge:
                break
    if not bridge:
        for item in summaries:
            text = item["summary"]
            if item["has_goal_point"] and text not in seen:
                seen.add(text)
                bridge.append(text)
                if len(bridge) >= max_bridge:
                    break

    for item in reversed(summaries):
        text = item["summary"]
        if text in finish:
            continue
        if goal_spec["predicate"] and goal_spec["predicate"] in text.lower():
            finish.append(text)
            if len(finish) >= max_finish:
                break
    if len(finish) < max_finish:
        for item in reversed(summaries):
            text = item["summary"]
            if text in finish:
                continue
            if item["has_goal_point"]:
                finish.append(text)
                if len(finish) >= max_finish:
                    break
    finish.reverse()

    return {
        "immediate_aux_consequences": immediate,
        "aux_bridge_relations": aux_bridge,
        "bridge_relations": bridge,
        "goal_finish_relations": finish,
    }


def validate_plan_response(
    output_text: str,
    point_coords,
    visible_goal="",
    aux_part=None,
    coordinate_candidates=None,
    sanitized_rest=None,
    visible_premise_summaries=None,
):
    plan = output_text if isinstance(output_text, dict) else extract_json_object(output_text)
    if not isinstance(plan, dict):
        return False, "Planner must return a single JSON object", None

    required_keys = [
        "anchor_points",
        "anchor_relation",
        "figure_overview",
        "coordinate_relations",
        "visible_relations",
        "coordinate_hints",
        "goal_bottleneck",
        "helper_idea",
        "construction",
        "aux_direct_relations",
        "bridge_steps",
        "goal_finish",
    ]
    missing = [key for key in required_keys if key not in plan]
    if missing:
        return False, f"Planner JSON missing keys: {missing}", None

    anchor_points = plan.get("anchor_points")
    max_anchor_points = min(4, max(3, len(point_coords)))
    if not isinstance(anchor_points, list) or not (3 <= len(anchor_points) <= max_anchor_points):
        return False, "anchor_points must be a list with 3 or 4 visible points", None
    normalized_points = []
    for point_name in anchor_points:
        if not isinstance(point_name, str):
            return False, "anchor_points entries must be strings", None
        point_name = point_name.strip().lower()
        if point_name not in point_coords:
            return False, f"anchor point '{point_name}' is not an original visible point", None
        normalized_points.append(point_name)
    if len(set(normalized_points)) != len(normalized_points):
        return False, "anchor_points must not contain duplicates", None

    cleaned_plan = {"anchor_points": normalized_points}
    visible_points = extract_visible_point_names(point_coords)
    aux_points = [point.lower() for point in extract_aux_new_points(aux_part or "")]
    known_points = visible_points + aux_points
    for key in ["anchor_relation", "figure_overview", "coordinate_hints", "goal_bottleneck", "helper_idea", "construction"]:
        ignored_patterns = []
        if key == "coordinate_hints":
            ignored_patterns.append(r"\bmidpoint propert(?:y|ies)\b")
        if key == "helper_idea":
            ignored_patterns.extend([
                r"\bfacilitate\b",
                r"\bhelp establish\b",
                r"\bnecessary relationships\b",
                r"\bclear relationship\b",
                r"\bessential for proving\b",
                r"\brotational symmetry\b",
                r"\bcenter of symmetry\b",
                r"\bmidpoint propert(?:y|ies)\b",
            ])
        ok, message, cleaned_value = validate_descriptive_text(
            plan.get(key),
            key,
            point_names=known_points,
            ignored_forbidden_patterns=ignored_patterns,
        )
        if not ok:
            return False, message, None
        forbidden_shape = find_forbidden_shape_shorthand(cleaned_value)
        if forbidden_shape:
            if key in {"anchor_relation", "figure_overview", "coordinate_hints", "goal_bottleneck", "helper_idea"}:
                cleaned_plan[key] = cleaned_value
                continue
            return False, (
                f"{key} must avoid vague shape shorthand like '{forbidden_shape}' and should spell out "
                "the concrete perpendicular, equal-length, midpoint, or parallel relations instead"
            ), None
        forbidden_center = find_forbidden_center_shorthand(cleaned_value)
        if forbidden_center:
            if key in {"anchor_relation", "figure_overview", "coordinate_hints", "goal_bottleneck", "helper_idea"}:
                cleaned_plan[key] = cleaned_value
                continue
            return False, (
                f"{key} must avoid unsupported center shorthand like '{forbidden_center}' and should spell out "
                "the concrete midpoint, equal-length, perpendicular, or collinear relations instead"
            ), None
        cleaned_plan[key] = cleaned_value
    if aux_points:
        for field_name in [
            "anchor_relation",
            "figure_overview",
            "coordinate_hints",
            "goal_bottleneck",
            "helper_idea",
        ]:
            cleaned_plan[field_name] = anonymize_new_point_mentions(cleaned_plan[field_name], aux_points)

    coordinate_relations_seed = canonicalize_coordinate_relations(
        plan.get("coordinate_relations"),
        visible_points,
        coordinate_candidates,
        min_len=2,
        max_len=3,
    )
    ok, message, cleaned_relations = validate_relation_list(
        coordinate_relations_seed,
        "coordinate_relations",
        visible_points,
        min_len=2,
        max_len=3,
    )
    if not ok:
        return False, message, None
    cleaned_plan["coordinate_relations"] = cleaned_relations

    visible_relations_seed = canonicalize_visible_relations(
        plan.get("visible_relations"),
        visible_points,
        visible_premise_summaries,
        min_len=2,
        max_len=4,
        min_chars=5,
    )
    ok, message, cleaned_visible_relations = validate_relation_list(
        visible_relations_seed,
        "visible_relations",
        visible_points,
        min_len=2,
        max_len=4,
        min_chars=5,
    )
    if not ok:
        return False, message, None
    cleaned_plan["visible_relations"] = cleaned_visible_relations

    if find_forbidden_shape_shorthand(cleaned_plan["anchor_relation"]) or find_forbidden_center_shorthand(cleaned_plan["anchor_relation"]):
        cleaned_plan["anchor_relation"] = build_canonical_anchor_relation(
            cleaned_plan["anchor_points"],
            cleaned_plan["visible_relations"],
        )
    if find_forbidden_shape_shorthand(cleaned_plan["figure_overview"]) or find_forbidden_center_shorthand(cleaned_plan["figure_overview"]):
        cleaned_plan["figure_overview"] = build_canonical_figure_overview(
            cleaned_plan["anchor_points"],
            cleaned_plan["visible_relations"],
            cleaned_plan["coordinate_relations"],
            visible_points,
        )
    if find_forbidden_shape_shorthand(cleaned_plan["goal_bottleneck"]) or find_forbidden_center_shorthand(cleaned_plan["goal_bottleneck"]):
        cleaned_plan["goal_bottleneck"] = build_canonical_goal_bottleneck(visible_goal)

    preferred_immediate_aux = []
    if sanitized_rest and aux_part:
        preferred_immediate_aux = build_hidden_proof_guidance(
            sanitized_rest,
            aux_part,
            visible_goal,
        ).get("immediate_aux_consequences", [])
    aux_direct_relations = canonicalize_aux_direct_relations(
        plan.get("aux_direct_relations"),
        aux_part,
        visible_points,
        preferred_immediate_aux,
        min_len=1,
        max_len=3,
    )
    if not (1 <= len(aux_direct_relations) <= 3):
        return False, "aux_direct_relations must be a list with 1 to 3 ordered direct consequences", None
    cleaned_direct = []
    for idx, step in enumerate(aux_direct_relations):
        ok, message, cleaned_step = validate_descriptive_text(
            step,
            f"aux_direct_relations[{idx}]",
            min_chars=5,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_step = normalize_relation_surface(cleaned_step)
        if not relation_keyword_present(cleaned_step):
            return False, f"aux_direct_relations[{idx}] must mention a concrete geometric relation", None
        cleaned_direct.append(cleaned_step)
    cleaned_plan["aux_direct_relations"] = cleaned_direct
    helper_idea_lower = cleaned_plan["helper_idea"].lower()
    if any(
        phrase in helper_idea_lower
        for phrase in [
            "facilitate",
            "help establish",
            "necessary relationships",
            "clear relationship",
            "essential for proving",
            "rotational symmetry",
            "center of symmetry",
            "symmetric center",
            "rotation center",
            "rotational center",
            "circumcenter",
            "parallelogram",
            "rectangle",
            "rectangular",
            "square",
            "midpoint property",
            "midpoint properties",
        ]
    ) or find_forbidden_shape_shorthand(cleaned_plan["helper_idea"]) or find_forbidden_center_shorthand(cleaned_plan["helper_idea"]):
        cleaned_plan["helper_idea"] = build_canonical_helper_idea(
            cleaned_plan["aux_direct_relations"],
            cleaned_plan.get("goal_bottleneck", ""),
        )

    bridge_steps = plan.get("bridge_steps")
    if isinstance(bridge_steps, list) and len(bridge_steps) > 4:
        bridge_steps = bridge_steps[:4]
    if not isinstance(bridge_steps, list) or not (2 <= len(bridge_steps) <= 4):
        return False, "bridge_steps must be a list with 2 to 4 ordered bridge-step objects", None
    cleaned_bridge_steps = []
    cleaned_bridge_relations = []
    for idx, step in enumerate(bridge_steps):
        if not isinstance(step, dict):
            return False, f"bridge_steps[{idx}] must be an object", None
        if any(key not in step for key in ["relation", "depends_on", "why_it_helps"]):
            return False, f"bridge_steps[{idx}] must contain relation, depends_on, and why_it_helps", None
        ok, message, cleaned_relation = validate_descriptive_text(
            step.get("relation"),
            f"bridge_steps[{idx}].relation",
            min_chars=5,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_relation = normalize_relation_surface(cleaned_relation)
        if not relation_keyword_present(cleaned_relation):
            return False, f"bridge_steps[{idx}].relation must mention a concrete geometric relation", None
        depends_on = coerce_relation_list_field(step.get("depends_on"), max_len=3)
        cleaned_dependencies = []
        for dep_idx, dependency in enumerate(depends_on):
            ok, message, cleaned_dependency = validate_descriptive_text(
                dependency,
                f"bridge_steps[{idx}].depends_on[{dep_idx}]",
                min_chars=5,
                point_names=known_points,
            )
            if not ok:
                continue
            cleaned_dependency = normalize_relation_surface(cleaned_dependency)
            if not relation_keyword_present(cleaned_dependency):
                continue
            if len(extract_point_mentions(cleaned_dependency, known_points)) < 2:
                continue
            cleaned_dependencies.append(cleaned_dependency)
        ok, message, cleaned_help = validate_descriptive_text(
            step.get("why_it_helps"),
            f"bridge_steps[{idx}].why_it_helps",
            min_chars=8,
            point_names=known_points,
            ignored_forbidden_patterns=[
                r"\bmidpoint propert(?:y|ies)\b",
            ],
        )
        if not ok:
            return False, message, None
        cleaned_bridge_steps.append(
            {
                "relation": cleaned_relation,
                "depends_on": cleaned_dependencies,
                "why_it_helps": cleaned_help,
            }
        )
        cleaned_bridge_relations.append(cleaned_relation)
    cleaned_plan["bridge_steps"] = cleaned_bridge_steps
    cleaned_plan["bridge_relations"] = cleaned_bridge_relations

    ok, message, cleaned_goal_finish = validate_descriptive_text(
        plan.get("goal_finish"),
        "goal_finish",
        min_chars=8,
        point_names=known_points,
    )
    if not ok:
        return False, message, None
    cleaned_goal_finish = normalize_relation_surface(cleaned_goal_finish)
    canonical_goal_finish = normalize_relation_surface(summarize_aux_clause(visible_goal) or "")
    if canonical_goal_finish:
        cleaned_goal_finish = canonical_goal_finish
    if not relation_keyword_present(cleaned_goal_finish):
        return False, "goal_finish must mention a concrete goal-side geometric relation", None
    cleaned_plan["goal_finish"] = cleaned_goal_finish

    relation_mentions = extract_point_mentions(" ".join(cleaned_plan["coordinate_relations"]), visible_points)
    if len(relation_mentions) < 3:
        return False, "coordinate_relations should collectively cover at least three visible points", None

    canonical_coordinate_hint = build_canonical_coordinate_hint(cleaned_plan["coordinate_relations"])
    coordinate_hint_lower = cleaned_plan["coordinate_hints"].lower()
    if (
        not relation_keyword_present(cleaned_plan["coordinate_hints"])
        or re.search(r"\bsymmetr(?:y|ic)\b|\brotat(?:e|es|ed|ing|ion|ional)\b", cleaned_plan["coordinate_hints"], re.IGNORECASE)
        or find_forbidden_shape_shorthand(cleaned_plan["coordinate_hints"])
        or find_forbidden_center_shorthand(cleaned_plan["coordinate_hints"])
        or not any(point in coordinate_hint_lower for point in relation_mentions)
    ):
        cleaned_plan["coordinate_hints"] = canonical_coordinate_hint
        coordinate_hint_lower = cleaned_plan["coordinate_hints"].lower()
    if not relation_keyword_present(cleaned_plan["coordinate_hints"]):
        return False, "coordinate_hints must mention at least one concrete geometric relation cue", None
    if re.search(r"\bsymmetr(?:y|ic)\b|\brotat(?:e|es|ed|ing|ion|ional)\b", cleaned_plan["coordinate_hints"], re.IGNORECASE):
        return False, (
            "coordinate_hints must explain concrete midpoint, collinear, equal-length, parallel, or perpendicular cues, "
            "not generic symmetry or rotation language"
        ), None
    if not any(point in coordinate_hint_lower for point in relation_mentions):
        return False, "coordinate_hints must summarize at least one concrete point-based relation from coordinate_relations", None

    figure_mentions = extract_point_mentions(
        " ".join(
            [
                cleaned_plan["figure_overview"],
                " ".join(cleaned_plan["visible_relations"]),
                " ".join(cleaned_plan["bridge_relations"]),
                cleaned_plan["goal_finish"],
            ]
        ),
        visible_points,
    )
    if len(visible_points) > len(normalized_points) and not (figure_mentions - set(normalized_points)):
        return False, "figure_overview, visible_relations, bridge_relations, or goal_finish must mention at least one visible point outside anchor_points", None

    if coordinate_candidates:
        unmatched_relations = [
            relation
            for relation in cleaned_plan["coordinate_relations"]
            if not any(coordinate_relation_matches_candidate(relation, candidate) for candidate in coordinate_candidates)
        ]
        if unmatched_relations:
            return False, (
                "coordinate_relations must stay grounded in the hidden coordinate candidates; "
                f"unmatched items: {unmatched_relations}"
            ), None
    if sanitized_rest and aux_part:
        proof_guidance = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
        hidden_route_relations = (
            proof_guidance.get("aux_bridge_relations", [])
            + proof_guidance.get("bridge_relations", [])
            + proof_guidance.get("goal_finish_relations", [])
        )
        if hidden_route_relations:
            route_alignment = align_bridge_steps_to_hidden_route(
                cleaned_plan["bridge_steps"],
                hidden_route_relations,
                known_points,
            )
            if route_alignment["unmatched"]:
                return False, (
                    "bridge_steps relations must stay close to the hidden proof guidance route and follow its order; "
                    f"unmatched items: {route_alignment['unmatched']}"
                ), None
            aligned_bridge_steps = []
            for step, match in zip(cleaned_plan["bridge_steps"], route_alignment["matches"]):
                aligned_step = dict(step)
                if match:
                    aligned_step["approved_route_relation"] = match["relation"]
                    aligned_step["approved_route_position"] = match["index"] + 1
                aligned_bridge_steps.append(aligned_step)
            cleaned_plan["bridge_steps"] = aligned_bridge_steps

    cleaned_plan = enrich_bridge_steps_with_targets(cleaned_plan)

    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec["points"])
    goal_keywords = goal_keyword_hints(visible_goal)

    if aux_part:
        construction_text = f"{cleaned_plan['helper_idea']} {cleaned_plan['construction']}".lower()
        for label, keywords in build_aux_keyword_expectations(aux_part):
            if not any(keyword in construction_text for keyword in keywords):
                canonical_construction = build_canonical_construction(aux_part)
                if canonical_construction:
                    cleaned_plan["construction"] = canonical_construction
                    construction_text = f"{cleaned_plan['helper_idea']} {cleaned_plan['construction']}".lower()
                if not any(keyword in construction_text for keyword in keywords):
                    return False, f"construction is missing an expected {label} cue", None
        new_points = [point.lower() for point in extract_aux_new_points(aux_part)]
        preconstruction_fields = [
            cleaned_plan["anchor_relation"],
            cleaned_plan["figure_overview"],
            cleaned_plan["coordinate_hints"],
            cleaned_plan["goal_bottleneck"],
            cleaned_plan["helper_idea"],
            " ".join(cleaned_plan["coordinate_relations"]),
            " ".join(cleaned_plan["visible_relations"]),
        ]
        for point_name in new_points:
            if any(re.search(rf"\b{re.escape(point_name)}\b", field.lower()) for field in preconstruction_fields):
                return False, f"new point '{point_name}' must not appear before the construction field", None
        for point_name in new_points:
            if point_name not in cleaned_plan["construction"].lower():
                return False, f"construction must mention new point '{point_name}' explicitly", None
        if len(new_points) > 1:
            stage_markers = ["first", "then", "next", "after", "together", "simultaneously"]
            combined_text = (
                f"{cleaned_plan['construction']} "
                f"{' '.join(cleaned_plan['aux_direct_relations'])} "
                f"{' '.join(cleaned_plan['bridge_relations'])}"
            ).lower()
            if not any(marker in combined_text for marker in stage_markers):
                return False, "multi-point auxiliary plans must describe a staged or combined construction strategy", None
        if new_points:
            if not any(point in " ".join(cleaned_plan["aux_direct_relations"]).lower() for point in new_points):
                return False, "aux_direct_relations must state the immediate relation unlocked by the new point", None
            for idx, step in enumerate(cleaned_plan["aux_direct_relations"]):
                ok, message = validate_aux_step_scope(step, aux_part, visible_points)
                if not ok:
                    return False, f"aux_direct_relations[{idx}] invalid: {message}", None
            if not any(point in cleaned_plan["bridge_relations"][0].lower() for point in new_points):
                return False, "bridge_steps[0].relation must still reference the auxiliary point while bridging to the old figure", None
        available_supports = cleaned_plan["visible_relations"] + cleaned_plan["aux_direct_relations"]
        for idx, step in enumerate(cleaned_plan["bridge_steps"]):
            if idx > 0:
                available_supports.append(cleaned_plan["bridge_steps"][idx - 1]["relation"])
            if relation_duplicates_earlier_support(step["relation"], available_supports, known_points):
                return False, f"bridge_steps[{idx}].relation must advance beyond earlier visible, direct, or bridge relations", None
            canonical_dependencies = []
            matched_supports = []
            for dependency in step["depends_on"]:
                matched_support = align_dependency_to_support(dependency, available_supports, known_points)
                if matched_support:
                    canonical_dependencies.append(matched_support)
                    matched_supports.append(matched_support)
                else:
                    canonical_dependencies.append(dependency)
            preferred_dependencies = select_support_relations_for_step(
                step["relation"],
                available_supports,
                known_points,
                next_target_relation=step.get("next_target_relation", ""),
                max_supports=min(2, len(available_supports)),
            )
            if not matched_supports and preferred_dependencies:
                matched_supports = preferred_dependencies[:]
                canonical_dependencies = preferred_dependencies + canonical_dependencies
            if not matched_supports:
                return False, f"bridge_steps[{idx}].depends_on must reuse an earlier visible, direct, or bridge relation", None
            deduped_dependencies = []
            for dependency in canonical_dependencies:
                if dependency not in deduped_dependencies:
                    deduped_dependencies.append(dependency)
            merged_dependencies = preferred_dependencies + [
                dependency for dependency in deduped_dependencies
                if dependency not in preferred_dependencies
            ]
            if not merged_dependencies:
                merged_dependencies = deduped_dependencies
            step["depends_on"] = merged_dependencies[:3]
            step["required_supports"] = (
                preferred_dependencies[: min(2, len(preferred_dependencies))]
                if preferred_dependencies else
                step["depends_on"][: min(2, len(step["depends_on"]))]
            )
            if idx < len(cleaned_plan["bridge_steps"]) - 1:
                next_relation = cleaned_plan["bridge_steps"][idx + 1]["relation"].lower()
                why_text = step["why_it_helps"].lower()
                if re.search(r"\bmidpoint propert(?:y|ies)\b", why_text, re.IGNORECASE):
                    step["why_it_helps"] = build_canonical_bridge_unlock(
                        step.get("next_target_relation", ""),
                        final_step=False,
                    )
                    why_text = step["why_it_helps"].lower()
                allowed_structure_markers = (
                    extract_high_level_structure_markers(step["relation"])
                    | extract_high_level_structure_markers(" ".join(step["depends_on"]))
                    | extract_high_level_structure_markers(next_relation)
                )
                new_structure_markers = extract_high_level_structure_markers(why_text) - allowed_structure_markers
                if new_structure_markers:
                    step["why_it_helps"] = build_canonical_bridge_unlock(
                        step.get("next_target_relation", ""),
                        final_step=False,
                    )
            else:
                why_text = step["why_it_helps"].lower()
                if re.search(r"\bmidpoint propert(?:y|ies)\b", why_text, re.IGNORECASE):
                    step["why_it_helps"] = build_canonical_bridge_unlock(
                        step.get("next_target_relation", ""),
                        final_step=True,
                    )
                    why_text = step["why_it_helps"].lower()
                allowed_structure_markers = (
                    extract_high_level_structure_markers(step["relation"])
                    | extract_high_level_structure_markers(" ".join(step["depends_on"]))
                    | extract_high_level_structure_markers(cleaned_goal_finish)
                )
                new_structure_markers = extract_high_level_structure_markers(why_text) - allowed_structure_markers
                if new_structure_markers:
                    step["why_it_helps"] = build_canonical_bridge_unlock(
                        step.get("next_target_relation", ""),
                        final_step=True,
                    )
    final_step = cleaned_goal_finish.lower()
    if goal_points:
        mentioned_goal_points = {point for point in goal_points if point in final_step}
        if len(mentioned_goal_points) < min(2, len(goal_points)):
            return False, "goal_finish must mention the target relation using goal-side points", None
    if not any(keyword in final_step for keyword in goal_keywords):
        return False, "goal_finish must explicitly describe the goal-side relation it is aiming for", None
    if aux_part:
        bridge_mentions = extract_point_mentions(" ".join(cleaned_plan["bridge_relations"]), known_points)
        if not (bridge_mentions - set(aux_points)):
            return False, "bridge_steps must connect the auxiliary point to existing visible points", None

    return True, "Valid planner JSON", cleaned_plan


def validate_writer_body(output_text: str, visible_goal="", injected_prefix="", plan=None):
    if not output_text or not output_text.strip():
        return False, "Writer body is empty"
    body = output_text.strip()
    if body.startswith("<thinking>") or body.endswith("</thinking>"):
        return False, "Writer body must be plain text only, without <thinking> tags"
    if RAW_POINT_TAG_RE.search(body) or POINT_TAG_RE.search(body):
        return False, "Writer body must not contain point tags; anchor tags are inserted by the script"
    if "<coord>" in body or "</coord>" in body:
        return False, "Writer body must not contain coord tags"
    if len(body) < 120:
        return False, f"Writer body too short ({len(body)} chars, minimum 120)"
    max_body_len = 1500
    if injected_prefix:
        # Reserve room for the injected prefix and a small margin so final assembly
        # does not fail only after the body itself has already been accepted.
        max_body_len = min(max_body_len, max(200, 2200 - len(injected_prefix) - 40))
    if len(body) > max_body_len:
        return False, f"Writer body too long ({len(body)} chars, maximum {max_body_len})"
    if re.search(r"\b(I|We|I'm|We'll|I've|we've)\b", body):
        return False, "Writer body must stay impersonal and should not use first-person narration"
    first_sentence_match = re.match(r"\s*(.+?[.!?])(?:\s|$)", body, re.DOTALL)
    first_sentence = first_sentence_match.group(1).strip() if first_sentence_match else body
    goal_points = parse_goal_expression(visible_goal).get("points", [])
    goal_keywords = goal_keyword_hints(visible_goal)
    if visible_goal:
        first_sentence_lower = first_sentence.lower()
        mentions_goal_point = sum(1 for point in goal_points if point in first_sentence_lower)
        mentions_goal_keyword = any(keyword in first_sentence_lower for keyword in goal_keywords)
        if mentions_goal_point < 1 and not mentions_goal_keyword:
            return False, "Writer body must start from the bottleneck or goal-side obstacle, not by re-describing the injected prefix"
    if injected_prefix and has_long_ngram_overlap(injected_prefix, body, ngram_size=9):
        return False, "Writer body overlaps too much with the injected prefix block; continue from it instead of repeating it"
    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(body)
        if hit:
            return False, f"Writer body contains forbidden pattern: {hit.group(0)}"
    if re.search(r"\bsimilarity or angle equality\b", body, re.IGNORECASE):
        return False, "Writer body must state a specific bridge relation instead of hedging with 'similarity or angle equality'"
    forbidden_shape = find_forbidden_shape_shorthand(body)
    if forbidden_shape:
        return False, (
            f"Writer body must avoid vague shape shorthand like '{forbidden_shape}' and should state the "
            "concrete perpendicular, equal-length, midpoint, or parallel relations instead"
        )
    forbidden_center = find_forbidden_center_shorthand(body)
    if forbidden_center:
        return False, (
            f"Writer body must avoid unsupported center shorthand like '{forbidden_center}' and should state the "
            "concrete midpoint, equal-length, perpendicular, or collinear relations instead"
        )
    if plan and isinstance(plan.get("bridge_steps"), list):
        sentences = split_into_sentences(body)
        search_start = 0
        generic_markers = [
            "symmetry",
            "by symmetry",
            "it follows",
            "from the setup",
            "resulting symmetry",
            "midpoint property",
            "midpoint properties",
        ]
        for idx, step in enumerate(plan["bridge_steps"]):
            match_idx = None
            for sentence_idx in range(search_start, len(sentences)):
                if bridge_step_relation_realized(sentences[sentence_idx], step):
                    match_idx = sentence_idx
                    break
            if match_idx is None:
                return False, f"Writer body must explicitly realize bridge_steps[{idx}].relation in order"
            sentence = sentences[match_idx]
            required_supports = step.get("required_supports") or step.get("depends_on", [])
            mentioned_dependencies = count_relation_mentions(sentence, required_supports)
            min_support_mentions = step.get("min_support_mentions", 1 if required_supports else 0)
            if mentioned_dependencies < min_support_mentions:
                return False, (
                    f"Writer sentence for bridge_steps[{idx}] must name at least one approved supporting relation"
                )
            if any(marker in sentence.lower() for marker in generic_markers):
                if mentioned_dependencies < min(2, len(required_supports)):
                    return False, (
                        f"Writer sentence for bridge_steps[{idx}] uses a generic shortcut without naming enough supporting relations"
                    )
            search_start = match_idx + 1
        goal_finish = plan.get("goal_finish", "")
        if goal_finish:
            finish_match_idx = None
            for sentence_idx in range(search_start, len(sentences)):
                if relation_mentioned_in_text(sentences[sentence_idx], goal_finish):
                    finish_match_idx = sentence_idx
                    break
            if finish_match_idx is None:
                return False, "Writer body must explicitly realize goal_finish after the bridge steps"
    return True, "Valid writer body"


def build_instruction_text():
    return (
        "Given the geometry image and the formal problem text, write a forward-thinking "
        "trace that motivates the auxiliary construction. Output the thinking trace and "
        "the final aux block."
    )


def enrich_bridge_steps_with_targets(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("bridge_steps"), list):
        return plan
    enriched_steps = []
    total_steps = len(plan["bridge_steps"])
    for idx, step in enumerate(plan["bridge_steps"]):
        if not isinstance(step, dict):
            enriched_steps.append(step)
            continue
        enriched = dict(step)
        if idx < total_steps - 1:
            enriched["next_target_relation"] = plan["bridge_steps"][idx + 1].get("relation", "")
        else:
            enriched["next_target_relation"] = plan.get("goal_finish", "")
        dependencies = [
            dep for dep in enriched.get("depends_on", [])
            if isinstance(dep, str) and dep.strip()
        ]
        enriched["required_supports"] = dependencies[: min(2, len(dependencies))]
        enriched["min_support_mentions"] = 1 if dependencies else 0
        enriched_steps.append(enriched)
    enriched_plan = dict(plan)
    enriched_plan["bridge_steps"] = enriched_steps
    return enriched_plan


def anonymize_new_point_mentions(text, new_points):
    if not isinstance(text, str) or not new_points:
        return text
    anonymized = text
    for point_name in sorted({point.lower() for point in new_points}, key=len, reverse=True):
        anonymized = re.sub(rf"\b{re.escape(point_name)}\b", "a point", anonymized, flags=re.IGNORECASE)
    anonymized = re.sub(r"\ba point point\b", "a point", anonymized, flags=re.IGNORECASE)
    return anonymized


def build_canonical_bridge_unlock(next_target_relation, final_step=False):
    target_text = normalize_relation_surface(next_target_relation or "").strip().rstrip(".")
    if not target_text:
        return "this prepares the next approved bridge relation."
    target_text = re.sub(r"^(then|therefore|thus)\s+", "", target_text, flags=re.IGNORECASE)
    if final_step:
        return f"this prepares the final goal-side relation {target_text}."
    return f"this is required to prove {target_text} next."


def extract_problem_goal(record):
    problem_text = build_public_problem_text(record)
    body_match = PROBLEM_BODY_RE.search(problem_text)
    body = body_match.group(1).strip() if body_match else problem_text.strip()
    if "?" in body:
        return body.split("?", 1)[1].strip()
    return ""


def extract_problem_context(record):
    problem_text = build_public_problem_text(record)
    body_match = PROBLEM_BODY_RE.search(problem_text)
    body = body_match.group(1).strip() if body_match else problem_text.strip()
    if "?" in body:
        return body.split("?", 1)[0].strip()
    return body


def extract_aux_new_points(aux_part):
    return AUX_NEW_POINT_RE.findall(aux_part)


def summarize_aux_clause(clause):
    clause = re.sub(r"\[\d{3}\]", "", clause).strip()
    ratio_clause_match = re.fullmatch(
        r"([a-z]{2})\s*:\s*([a-z]{2})\s*=\s*([a-z]{2})\s*:\s*([a-z]{2})",
        clause,
        flags=re.IGNORECASE,
    )
    if ratio_clause_match:
        left_num, left_den, right_num, right_den = [group.lower() for group in ratio_clause_match.groups()]
        return f"ratio {left_num} to {left_den} equals ratio {right_num} to {right_den}"
    tokens = clause.split()
    if not tokens:
        return None

    pred = tokens[0]
    args = tokens[1:]
    if pred == "cong" and len(args) >= 4:
        return f"{args[0]}{args[1]} equals {args[2]}{args[3]}"
    if pred == "perp" and len(args) >= 4:
        return f"line {args[0]}{args[1]} is perpendicular to line {args[2]}{args[3]}"
    if pred == "para" and len(args) >= 4:
        return f"line {args[0]}{args[1]} is parallel to line {args[2]}{args[3]}"
    if pred == "coll" and len(args) >= 3:
        return f"{args[0]}, {args[1]}, {args[2]} are collinear"
    if pred == "cyclic" and len(args) >= 4:
        return f"{args[0]}, {args[1]}, {args[2]}, {args[3]} are concyclic"
    if pred == "midp" and len(args) >= 3:
        return f"{args[0]} is the midpoint of {args[1]}{args[2]}"
    if pred == "eqpoint" and len(args) >= 2:
        return f"{args[0]} equals {args[1]}"
    if pred == "eqratio" and len(args) >= 8:
        return (
            f"ratio {args[0]}{args[1]} to {args[2]}{args[3]} "
            f"equals ratio {args[4]}{args[5]} to {args[6]}{args[7]}"
        )
    if pred == "eqangle" and len(args) >= 8:
        return f"angle {args[0]}{args[1]}/{args[2]}{args[3]} equals angle {args[4]}{args[5]}/{args[6]}{args[7]}"
    if pred in {"simtri", "simtrir"} and len(args) >= 6:
        return f"triangles {args[0]}{args[1]}{args[2]} and {args[3]}{args[4]}{args[5]} are similar"
    if pred in {"contri", "contrir"} and len(args) >= 6:
        return f"triangles {args[0]}{args[1]}{args[2]} and {args[3]}{args[4]}{args[5]} are congruent"
    return clause


def build_hidden_aux_brief(aux_part):
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").strip()
    clauses = [part.strip() for part in inner.split(";") if part.strip()]
    summaries = []
    for clause in clauses:
        summary = summarize_aux_clause(clause)
        if summary:
            summaries.append(summary)
    if not summaries:
        return inner
    return "; ".join(summaries)


def build_canonical_construction(aux_part):
    clauses = parse_aux_clauses(aux_part or "")
    if not clauses:
        return ""
    sentences = []
    for clause in clauses:
        point_name = clause.get("new_point")
        fact_summaries = []
        for fact in split_formal_relation_chain(clause.get("body", "")):
            summary = summarize_aux_clause(fact)
            if summary:
                fact_summaries.append(summary)
        if not point_name or not fact_summaries:
            continue
        if len(fact_summaries) == 1:
            fact_text = fact_summaries[0]
        elif len(fact_summaries) == 2:
            fact_text = f"{fact_summaries[0]} and {fact_summaries[1]}"
        else:
            fact_text = ", ".join(fact_summaries[:-1]) + f", and {fact_summaries[-1]}"
        lead = "construct" if not sentences else "then construct"
        sentences.append(f"{lead} point {point_name} such that {fact_text}")
    return ". ".join(sentences).strip()


def build_multi_aux_instruction(aux_part):
    new_points = extract_aux_new_points(aux_part)
    if len(new_points) <= 1:
        return ""

    point_steps = []
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").strip()
    clauses = [part.strip() for part in inner.split(";") if part.strip()]
    for clause in clauses:
        match = re.match(r"x00\s+([a-z]\w*)\s*:\s*(.*)", clause, re.IGNORECASE)
        if not match:
            continue
        point_name = match.group(1).lower()
        summary = summarize_aux_clause(match.group(2).strip()) or match.group(2).strip()
        point_steps.append(f"{point_name}: {summary}")

    steps_text = "; ".join(point_steps) if point_steps else ", ".join(new_points)
    return (
        "[Multi-Point Construction Requirement]\n"
        "This target introduces multiple new points. Your construction field must use explicit stage markers such as "
        "'first', 'then', and 'finally', or say that some points are introduced together before a later step.\n"
        f"Target point-by-point outline: {steps_text}\n\n"
    )


def format_tagged_point(point_name, point_coords):
    x_val, y_val = point_coords[point_name]
    return f"<point>{point_name}</point><coord>({x_val},{y_val})</coord>"


def join_natural_list(items):
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def build_anchor_sentence(plan, point_coords):
    tagged_points = [format_tagged_point(point_name, point_coords) for point_name in plan["anchor_points"]]
    anchor_list = join_natural_list(tagged_points)
    relation = plan["anchor_relation"].strip().rstrip(".")
    return f"From the diagram, the key visible anchors are {anchor_list}; visually, {relation}."


def build_overview_sentence(plan):
    overview = plan["figure_overview"].strip().rstrip(".")
    return f"{overview}."


def build_coordinate_hint_sentence(plan):
    hints = plan["coordinate_hints"].strip().rstrip(".")
    relation_text = "; ".join(plan.get("coordinate_relations", [])).strip().rstrip(".")
    if relation_text:
        return f"{relation_text}. {hints}."
    return f"{hints}."


def build_visible_relation_sentence(plan):
    relation_text = "; ".join(plan.get("visible_relations", [])).strip().rstrip(".")
    if not relation_text:
        return ""
    return f"The visible givens also show that {relation_text}."


def build_prefix_coverage_notes(plan):
    if not isinstance(plan, dict):
        return "[]"
    notes = []
    figure_overview = plan.get("figure_overview")
    if isinstance(figure_overview, str) and figure_overview.strip():
        notes.append(f"overview already covered: {figure_overview.strip().rstrip('.')}")
    for relation in plan.get("coordinate_relations", []) or []:
        if isinstance(relation, str) and relation.strip():
            notes.append(f"coordinate cue already covered: {relation.strip().rstrip('.')}")
    for relation in plan.get("visible_relations", []) or []:
        if isinstance(relation, str) and relation.strip():
            notes.append(f"visible relation already covered: {relation.strip().rstrip('.')}")
    return json.dumps(notes, ensure_ascii=False, indent=2) if notes else "[]"


def build_writer_sentence_duties(plan):
    if not isinstance(plan, dict):
        return ""
    lines = [
        "1. Opening sentence: state the goal-side obstacle directly, using the target relation or the target-side points.",
        "2. Helper sentence: restate the approved helper idea impersonally, but do not quote the plan wording word-for-word.",
        "3. Construction sentence: introduce the auxiliary point from the approved construction, but keep the wording natural rather than copying the plan string verbatim.",
    ]
    aux_direct_relations = plan.get("aux_direct_relations", [])
    if aux_direct_relations:
        lines.append(
            f"{len(lines) + 1}. Direct-aux sentence: explicitly realize the immediate construction consequences before any bridge step."
        )
    for idx, step in enumerate(plan.get("bridge_steps", []), start=1):
        if not isinstance(step, dict):
            continue
        approved_relation = step.get("approved_route_relation") or step.get("relation", "")
        required_supports = step.get("required_supports", [])
        min_support_mentions = step.get("min_support_mentions", 1 if required_supports else 0)
        support_clause = (
            f" explicitly mention at least {min_support_mentions} of these support relations: {json.dumps(required_supports, ensure_ascii=False)};"
            if required_supports else
            " explicitly mention at least one approved support relation;"
        )
        lines.append(
            f"{len(lines) + 1}. Bridge sentence {idx}: state the approved relation '{approved_relation}',{support_clause} prefer an aux-direct or previous-bridge support when possible, avoid summary labels like symmetry or midpoint property in place of those supports, paraphrase any visible given that already appears in the prefix, and point toward '{step.get('next_target_relation', '')}'."
        )
    lines.append(
        f"{len(lines) + 1}. Final sentence: after the last bridge sentence, explicitly land on the approved goal-side finish exactly: {plan.get('goal_finish', '')}"
    )
    return "\n".join(lines)


def build_bridge_sentence_shell(step):
    if not isinstance(step, dict):
        return ""
    supports = step.get("required_supports") or step.get("depends_on", [])
    relation = step.get("approved_route_relation") or step.get("relation", "")
    next_target = step.get("next_target_relation", "")
    if supports:
        support_text = supports[0]
        if len(supports) > 1:
            support_text = f"{supports[0]} and {supports[1]}"
        shell = f"Because {support_text}, {relation}"
    else:
        shell = f"State {relation}"
    if next_target:
        shell += f", which prepares {next_target}"
    return shell + "."


def build_writer_bridge_contracts(plan):
    if not isinstance(plan, dict):
        return []
    contracts = []
    bridge_steps = plan.get("bridge_steps", [])
    for idx, step in enumerate(bridge_steps, start=1):
        if not isinstance(step, dict):
            continue
        contracts.append(
            {
                "sentence_type": f"bridge_{idx}",
                "relation": step.get("approved_route_relation") or step.get("relation", ""),
                "required_supports": step.get("required_supports", []),
                "min_support_mentions": step.get("min_support_mentions", 1 if step.get("required_supports") else 0),
                "next_target_relation": step.get("next_target_relation", ""),
                "preferred_sentence_shell": build_bridge_sentence_shell(step),
            }
        )
    contracts.append(
        {
            "sentence_type": "goal_finish",
            "relation": plan.get("goal_finish", ""),
            "must_appear_after_bridge_count": len(bridge_steps),
            "preferred_sentence_shell": f"Therefore, {plan.get('goal_finish', '')}.",
        }
    )
    return contracts


def build_writer_sentence_blueprints(plan):
    if not isinstance(plan, dict):
        return []
    blueprints = [
        {
            "sentence_type": "opening",
            "goal_finish": plan.get("goal_finish", ""),
            "instruction": "State the obstacle directly in goal-side terms without re-describing the injected prefix.",
        },
        {
            "sentence_type": "helper",
            "instruction": "State the missing helper mechanism impersonally and concretely.",
        },
        {
            "sentence_type": "construction",
            "instruction": "Introduce the approved auxiliary construction in natural language.",
        },
    ]
    if plan.get("aux_direct_relations"):
        blueprints.append(
            {
                "sentence_type": "aux_direct",
                "relation_sequence": plan.get("aux_direct_relations", []),
                "instruction": "Realize the direct auxiliary consequences before any bridge sentence.",
            }
        )
    for idx, step in enumerate(plan.get("bridge_steps", []), start=1):
        if not isinstance(step, dict):
            continue
        support_sequence = step.get("required_supports") or step.get("depends_on", [])
        blueprints.append(
            {
                "sentence_type": f"bridge_{idx}",
                "recommended_order": [
                    "support",
                    "approved_relation",
                    "next_target",
                ],
                "support_relation": support_sequence[0] if support_sequence else "",
                "fallback_support_relations": support_sequence[1:] if len(support_sequence) > 1 else [],
                "approved_relation": step.get("approved_route_relation") or step.get("relation", ""),
                "next_target_relation": step.get("next_target_relation", ""),
                "preferred_sentence_shell": build_bridge_sentence_shell(step),
                "forbid_new_claims": True,
                "instruction": (
                    "Prefer a sentence of the form 'Because <support>, <approved relation>, which prepares <next target>'. "
                    "Do not add a fresh geometric claim outside the approved support/relation/next-target bundle."
                ),
            }
        )
    blueprints.append(
        {
            "sentence_type": "goal_finish",
            "approved_relation": plan.get("goal_finish", ""),
            "instruction": "Use one final sentence that explicitly states the approved goal_finish relation and stops there.",
        }
    )
    return blueprints


def build_prefix_sentences(plan, point_coords):
    sentences = [
        build_anchor_sentence(plan, point_coords),
        build_overview_sentence(plan),
        build_coordinate_hint_sentence(plan),
    ]
    visible_relation_sentence = build_visible_relation_sentence(plan)
    if visible_relation_sentence:
        sentences.append(visible_relation_sentence)
    return sentences


def build_injected_prefix_block(plan, point_coords):
    return " ".join(build_prefix_sentences(plan, point_coords))


def _normalize_overlap_words(text):
    lowered = re.sub(r"<[^>]+>", " ", text or "")
    lowered = re.sub(r"[^a-z0-9/ ]+", " ", lowered.lower())
    return [token for token in lowered.split() if token]


def has_long_ngram_overlap(source_text, target_text, ngram_size=7):
    source_words = _normalize_overlap_words(source_text)
    target_words = _normalize_overlap_words(target_text)
    if len(source_words) < ngram_size or len(target_words) < ngram_size:
        return False
    source_ngrams = {
        tuple(source_words[idx:idx + ngram_size])
        for idx in range(len(source_words) - ngram_size + 1)
    }
    target_ngrams = {
        tuple(target_words[idx:idx + ngram_size])
        for idx in range(len(target_words) - ngram_size + 1)
    }
    return bool(source_ngrams & target_ngrams)


def flatten_bridge_relations(plan):
    if not isinstance(plan, dict):
        return []
    if isinstance(plan.get("bridge_steps"), list):
        relations = []
        for step in plan["bridge_steps"]:
            if isinstance(step, dict):
                relation = step.get("relation")
                if isinstance(relation, str) and relation.strip():
                    relations.append(relation.strip())
        if relations:
            return relations
    relations = plan.get("bridge_relations")
    if isinstance(relations, list):
        return [relation.strip() for relation in relations if isinstance(relation, str) and relation.strip()]
    return []


def split_into_sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text or "") if part.strip()]


def relation_mentioned_in_text(text, relation):
    lowered_text = (text or "").lower()
    lowered_relation = (relation or "").lower().strip()
    if not lowered_relation:
        return False
    if lowered_relation in lowered_text:
        return True
    return has_long_ngram_overlap(lowered_relation, lowered_text, ngram_size=3)


def extract_relation_point_names(text):
    lowered = (text or "").lower()
    stopwords = {
        "a",
        "i",
        "is",
        "to",
        "of",
        "on",
        "in",
        "by",
        "at",
        "as",
        "are",
        "and",
        "the",
        "line",
        "ratio",
    }
    point_names = set(re.findall(r"\b([a-z])\b", lowered))
    for token in re.findall(r"\b[a-z]{2,4}\b", lowered):
        if token in stopwords:
            continue
        if token in {"line", "ratio"}:
            continue
        if len(token) <= 4:
            point_names.update(char for char in token if char.isalpha())
    return sorted(point_names)


def relation_semantically_mentioned_in_sentence(sentence, relation):
    lowered_sentence = (sentence or "").lower()
    relation_points = extract_relation_point_names(relation)
    if not relation_points or not all(point in lowered_sentence for point in relation_points):
        return False
    keywords = relation_text_keywords(relation)
    if "parallel" in keywords and "parallel" in lowered_sentence:
        return True
    if "perpendicular" in keywords and ("perpendicular" in lowered_sentence or "right angle" in lowered_sentence):
        return True
    if "collinear" in keywords and any(
        phrase in lowered_sentence for phrase in ["collinear", "same line", "one line", "on one line", "on the same line"]
    ):
        return True
    if "circle" in keywords and any(
        phrase in lowered_sentence for phrase in ["cyclic", "concyclic", "circle", "circumcircle"]
    ):
        return True
    if "midpoint" in keywords and (
        "midpoint" in lowered_sentence
        or "bisect" in lowered_sentence
        or "bisects" in lowered_sentence
    ):
        return True
    if "similar" in keywords and "similar" in lowered_sentence:
        return True
    if "ratio" in keywords and "ratio" in lowered_sentence:
        return True
    if "angle" in keywords and "angle" in lowered_sentence:
        return True
    if "equal" in keywords and any(
        phrase in lowered_sentence for phrase in [" equal", " equals", "congruent", "same length", "same distance", "equidistant"]
    ):
        return True
    return False


def count_relation_mentions(text, relations, point_names=None):
    mentions = 0
    for relation in relations:
        if relation_mentioned_in_text(text, relation):
            mentions += 1
            continue
        if relation_semantically_mentioned_in_sentence(text, relation):
            mentions += 1
            continue
        local_points = point_names or extract_relation_point_names(relation)
        if local_points and relations_semantically_match(text, relation, local_points):
            mentions += 1
    return mentions


def bridge_step_relation_realized(sentence, step):
    if not isinstance(step, dict):
        return False
    relation_candidates = []
    for key in ["relation", "approved_route_relation"]:
        relation = step.get(key, "")
        if isinstance(relation, str) and relation.strip() and relation not in relation_candidates:
            relation_candidates.append(relation)
    for relation in relation_candidates:
        if relation_mentioned_in_text(sentence, relation):
            return True
        local_points = extract_relation_point_names(relation)
        if local_points and relations_semantically_match(sentence, relation, local_points):
            return True
    return False


def build_public_problem_text(record):
    nl_problem = (record.get("nl_problem") or "").strip()
    formal_problem = (record.get("llm_input_renamed") or "").strip()
    if nl_problem:
        return f"<nl_problem>{nl_problem}</nl_problem>\n{formal_problem}"
    return formal_problem


def build_plan_json_example():
    return json.dumps(
        {
            "anchor_points": ["a", "b", "c"],
            "anchor_relation": "triangle abc is the main visible frame, with ab perpendicular to ac and ab equal to ac.",
            "figure_overview": "point g lies on ac while d and j extend the right side of the figure beyond the main triangle.",
            "coordinate_relations": [
                "point g looks like the midpoint of segment ac",
                "points b, d, and i look nearly collinear",
            ],
            "visible_relations": [
                "ab is perpendicular to ac",
                "ab equals ac",
                "g is the midpoint of ac",
            ],
            "coordinate_hints": "the midpoint at g and the straight-looking b-d-i alignment suggest that any new helper should connect the central structure to the right side through d.",
            "goal_bottleneck": "the goal angle at g still does not have a controlled link to the direction through bj.",
            "helper_idea": "we need a local helper that first creates a tight relation around the new point and then transfers it toward d and j.",
            "construction": "construct point k so that kb equals kc and line ck is perpendicular to line dk.",
            "aux_direct_relations": [
                "kb equals kc",
                "line ck is perpendicular to line dk",
            ],
            "bridge_steps": [
                {
                    "relation": "kc equals kd",
                    "depends_on": [
                        "kb equals kc",
                        "line ck is perpendicular to line dk",
                    ],
                    "why_it_helps": "this brings d into the same local balance around k and sets up the next relation kb equals kd.",
                },
                {
                    "relation": "kb equals kd",
                    "depends_on": [
                        "kb equals kc",
                        "kc equals kd",
                    ],
                    "why_it_helps": "this lets the k-based balance control the d-side direction and prepares the next angle relation with bj.",
                },
                {
                    "relation": "angle bk/bj equals angle dj/dk",
                    "depends_on": [
                        "kb equals kd",
                        "bj equals dj",
                    ],
                    "why_it_helps": "this prepares the goal angle by connecting bj to bg and the target angle on cg and fg.",
                },
            ],
            "goal_finish": "then the angle between bg and bj can match the target angle between cg and fg.",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_aux_specific_plan_guidance(aux_part):
    if not aux_part:
        return ""
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").lower()
    if "midp" in inner:
        return (
            "[Midpoint Aux Guidance]\n"
            "This target introduces a midpoint auxiliary point.\n"
            "- Before the construction field, do not mention the new midpoint name.\n"
            "- In aux_direct_relations, stay with midpoint-local facts only: the midpoint statement itself, the equal halves, and the resulting collinearity.\n"
            "- Do not jump from 'midpoint' directly to extra altitude, perpendicular-bisector, or circumcenter claims unless those relations already appear in the hidden proof guidance route.\n"
            "- For bridge_steps, prefer the concrete bridge_relations already hinted by the hidden proof guidance, such as equal-length transfers or congruent/angle consequences that explicitly reuse the midpoint facts.\n"
            "Midpoint-flavored example:\n"
            "{\n"
            '  "construction": "construct point h as the midpoint of segment bc.",\n'
            '  "aux_direct_relations": ["h is the midpoint of bc", "bh equals ch", "b, c, h are collinear"],\n'
            '  "bridge_steps": [\n'
            '    {\n'
            '      "relation": "ah equals ch",\n'
            '      "depends_on": ["h is the midpoint of bc", "bh equals ch"],\n'
            '      "why_it_helps": "this equality is required to prove the next congruent-triangle or angle relation involving h and f."\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
        )
    new_points = [point.lower() for point in extract_aux_new_points(aux_part)]
    cong_clauses = re.findall(r"\bcong\s+([a-z]\w*)\s+([a-z]\w*)\s+([a-z]\w*)\s+([a-z]\w*)", inner)
    if len(new_points) == 1 and len(cong_clauses) >= 2:
        point_set = set()
        point_hits = 0
        for clause in cong_clauses[:2]:
            point_set.update(clause)
            if new_points[0] in clause:
                point_hits += 1
        if len(point_set) == 3 and point_hits == 2:
            return (
                "[Equal-Length Aux Guidance]\n"
                "This target introduces one new point through two immediate equal-length facts on the same local frame.\n"
                "- Before the construction field, do not name the new point and do not say 'point h' or 'triangle adh'.\n"
                "- In helper_idea, describe the missing mechanism without the point name, for example: 'we need a point built from segment ad that gives two equal-length links and then bridges toward line ac.'\n"
                "- In construction, explicitly introduce the new point and restate both equalities from the hidden target summary in plain language.\n"
                "- In aux_direct_relations, stay with those immediate equalities only; do not jump early to collinearity, symmetry, rotation, or congruent-triangle claims.\n"
                "- In bridge_steps, prefer the approved hidden route items such as a collinearity step, an equal-length transfer like ah equals ag or dh equals de, and then the final old-figure comparison.\n"
                "- Each why_it_helps sentence should name the next concrete relation directly, such as 'this is required to prove cg equals hg next', rather than mentioning a generic triangle argument.\n"
                "Equal-length example:\n"
                "{\n"
                '  "helper_idea": "we need a point built from segment ad that gives two equal-length links and then bridges toward line ac.",\n'
                '  "construction": "construct point h such that ad equals ah and ah equals dh.",\n'
                '  "aux_direct_relations": ["ad equals ah", "ah equals dh"],\n'
                '  "bridge_steps": [\n'
                '    {\n'
                '      "relation": "a, c, h are collinear",\n'
                '      "depends_on": ["ad equals ah", "ah equals dh", "ad is parallel to bc"],\n'
                '      "why_it_helps": "this alignment is required to prove cg equals hg next."\n'
                '    },\n'
                '    {\n'
                '      "relation": "cg equals hg",\n'
                '      "depends_on": ["a, c, h are collinear", "cg equals eg"],\n'
                '      "why_it_helps": "this equality is required to prove df equals cg next."\n'
                '    }\n'
                '  ]\n'
                "}\n\n"
            )
    return ""


def build_plan_retry_feedback(validation_message, aux_part):
    targeted_hints = []
    if "depends_on" in validation_message:
        targeted_hints.append(
            "- bridge_steps must be a JSON array of objects, and each depends_on field must itself be a JSON list of 1 to 3 earlier relation strings."
        )
    if "depends_on" in validation_message and "must name at least two concrete points" in validation_message:
        targeted_hints.append(
            "- every depends_on item should be a full earlier relation string with named points, such as 'ab equals bi', 'a, d, i are collinear', or 'line ac is perpendicular to line di'; do not write shorthand like 'the equality', 'the perpendicular setup', or a single-point fragment."
        )
    if "depends_on" in validation_message and "must be a list with 1 to 3 supporting relations" in validation_message:
        targeted_hints.append(
            "- if only one support is needed, still return it inside JSON brackets, for example: \"depends_on\": [\"ab equals bi\"]."
        )
    if "depends_on" in validation_message and "must mention a concrete geometric relation" in validation_message:
        targeted_hints.append(
            "- every depends_on item should copy an earlier concrete relation almost verbatim, such as 'ah equals ch' or 'line ad is parallel to line bc'; do not replace it with abstract support labels like 'the midpoint property' or 'the equal-length setup'."
        )
    if "depends_on must reuse an earlier visible, direct, or bridge relation" in validation_message:
        targeted_hints.append(
            "- every depends_on item should be copied from visible_relations, aux_direct_relations, or an earlier bridge_steps relation with nearly the same surface form; do not invent a fresh paraphrase when an earlier approved support already exists."
        )
    if "aux_direct_relations" in validation_message and "must mention a concrete geometric relation" in validation_message:
        targeted_hints.append(
            "- every aux_direct_relations item must state the immediate construction consequence itself, such as 'ah equals dh', 'line ck is perpendicular to line dk', or 'b, c, h are collinear'; do not write vague summaries like 'the construction creates symmetry' or 'an isosceles shape appears'."
        )
        targeted_hints.append(
            "- if the direct consequence is that a point lies on a known line, write it as a concrete collinearity such as 'a, b, h are collinear' instead of 'h lies on line ab'."
        )
    if "aux_direct_relations" in validation_message and "must be a list with 1 to 3 ordered direct consequences" in validation_message:
        targeted_hints.append(
            "- aux_direct_relations must be an actual JSON list, for example: [\"a, d, i are collinear\", \"ab equals bi\", \"bd equals di\"]. Do not collapse the list into one sentence or one quoted paragraph."
        )
        targeted_hints.append(
            "- prefer copying 1 to 3 items from Hidden Proof Guidance.immediate_aux_consequences almost verbatim, starting from the most local construction consequences first."
        )
    if "bridge_steps" in validation_message and "must mention a concrete geometric relation" in validation_message:
        targeted_hints.append(
            "- every bridge_steps relation should name the exact approved equality, angle, ratio, collinearity, parallel, or perpendicular statement, not a high-level summary like 'the triangles match' or 'an isosceles configuration forms'."
        )
        targeted_hints.append(
            "- avoid point-identification wording like 'h coincides with f'; if you must express that identification, rewrite it as a concrete equality or another approved route relation."
        )
    if "coordinate_hints" in validation_message:
        targeted_hints.append(
            "- include coordinate_hints as one or two plain-language sentences summarizing which coordinate_relations matter and why."
        )
    if "coordinate_relations must stay grounded in the hidden coordinate candidates" in validation_message:
        targeted_hints.append(
            "- coordinate_relations should be chosen from the hidden structured coordinate candidates, not copied from visible premises like a given parallel or equal-length statement."
        )
        targeted_hints.append(
            "- rewrite abstract shape summaries like 'triangle adc looks isosceles' into the concrete candidate relation they imply, such as 'ad looks equal to cd', only if that exact equality appears in the hidden coordinate candidate list."
        )
    if "coordinate_relations" in validation_message and "symmetry or rotation claims" in validation_message:
        targeted_hints.append(
            "- rewrite coordinate_relations as concrete cues like midpoint, collinear, equal-length, parallel, or perpendicular observations; do not say points look symmetric or that there is a rotation."
        )
    if "coordinate_hints must explain concrete midpoint" in validation_message:
        targeted_hints.append(
            "- rewrite coordinate_hints to summarize the concrete cues themselves, such as a midpoint, collinearity, equal-length, parallel, or perpendicular observation, instead of saying the figure suggests symmetry or rotation."
        )
    if "coordinate_hints contains forbidden pattern: midpoint propert" in validation_message:
        targeted_hints.append(
            "- do not write 'midpoint property' in coordinate_hints; instead name the concrete midpoint fact itself, such as 'm is the midpoint of ab' or 'am equals bm'."
        )
    if "bridge_steps must connect the auxiliary point to existing visible points" in validation_message:
        targeted_hints.append(
            "- make the first bridge relation explicitly combine the new auxiliary point with old visible points in a concrete relation, such as 'ag equals dg', 'a, c, e, g are concyclic', or 'angle bg/bj equals angle gi/ij'; do not let the bridge route drift into pure old-figure statements."
        )
        targeted_hints.append(
            "- prefer compact point-pair surface forms like 'ag equals dg' over looser wrappers such as 'segment ag equals segment dg' when you describe an approved bridge relation."
        )
    if "must advance beyond earlier visible, direct, or bridge relations" in validation_message:
        targeted_hints.append(
            "- each bridge_steps relation must be a new checkpoint beyond the visible_relations, aux_direct_relations, and earlier bridge steps; do not repeat an aux-direct equality such as 'bj equals dj' as a separate bridge step."
        )
        targeted_hints.append(
            "- if a hidden route relation is already unlocked directly by the auxiliary construction, move to the next realistic checkpoint instead of repeating the same relation."
        )
        targeted_hints.append(
            "- do not restate an earlier bridge checkpoint later in the route. Once a relation has already appeared as visible support, aux-direct support, or a prior bridge step, the next bridge step should move to a later approved checkpoint."
        )
    if "must avoid vague shape shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; replace them with the concrete perpendicular, equal-length, midpoint, or parallel facts that are actually visible."
        )
    if "must avoid unsupported center shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'common center', 'reference center', 'center of symmetry', or 'serve as the center'; replace them with the concrete midpoint, equal-length, perpendicular, or collinear relations that justify the step."
        )
    if "visible_relations" in validation_message:
        targeted_hints.append(
            "- visible_relations should contain only old-figure relations that are already visible before the auxiliary point is introduced; do not place new-point relations there."
        )
    if "construction is missing an expected" in validation_message:
        targeted_hints.append(
            "- construction must restate the hidden auxiliary facts in natural geometry language, including the required equal/perpendicular/parallel/circle cue."
        )
    if "helper_idea contains forbidden pattern" in validation_message:
        targeted_hints.append(
            "- rewrite helper_idea as a concrete missing mechanism such as an equal-length transfer, perpendicular link, midpoint, or angle relation; do not use filler like 'facilitate' or 'help establish'."
        )
        targeted_hints.append(
            "- do not describe the helper as a center of symmetry, symmetric center, or rotation center; name the concrete midpoint, equal-length, parallel, or perpendicular mechanism instead."
        )
        targeted_hints.append(
            "- do not say 'midpoint property' inside helper_idea; say the concrete midpoint fact itself, such as 'the midpoint of ad gives equal halves', instead."
        )
    if "must not appear before the construction field" in validation_message:
        targeted_hints.append(
            "- helper_idea and every pre-construction field must avoid the new point name; say 'a point built from segment ad that creates two equal-length links' rather than 'point h forms ...'."
        )
    if "aux_direct_relations" in validation_message and "direct auxiliary relation should stay on the direct aux consequence" in validation_message:
        targeted_hints.append(
            "- aux_direct_relations must stay local to the new point and the immediately constructed line/circle/perpendicular/equal relation; do not pull old-figure points like a, b, or c into later consequences unless they are part of the construction itself."
        )
        targeted_hints.append(
            "- if a relation still uses the auxiliary point but reaches out to older figure points beyond the construction scope, move it into bridge_steps and use the Preferred Aux-Bridge Checkpoints bucket instead of aux_direct_relations."
        )
    if "bridge_steps[0].relation must still reference the auxiliary point" in validation_message:
        targeted_hints.append(
            "- the first bridge_steps relation must still contain the new auxiliary point together with at least one old visible point; do not start the bridge route with a pure old-figure angle or ratio relation."
        )
        targeted_hints.append(
            "- when a Preferred Aux-Bridge Checkpoints bucket is shown, copy the first bridge relation from that bucket or stay very close to it before moving on to older goal-side checkpoints."
        )
    if "why_it_helps" in validation_message:
        targeted_hints.append(
            "- each why_it_helps string should say what the current step unlocks next in plain geometry language, but the exact next target relation will be derived by the script for the writer."
        )
    if "must stay close to the hidden proof guidance route" in validation_message:
        targeted_hints.append(
            "- do not replace the approved bridge route with a different one; reuse bridge relations that are semantically close to the hidden proof guidance, such as equalities, angle relations, or the final parallel relation already indicated there."
        )
        targeted_hints.append(
            "- when a hidden bridge relation pool is shown, copy those route relations almost verbatim into bridge_steps.relation instead of swapping in a different structure like a new similar-triangle, cyclic, or equal-length route."
        )
        targeted_hints.append(
            "- if the approved route pool lists only equalities, angle relations, ratios, collinearities, or one specific triangle step, do not invent a fresh congruent-triangle relation such as 'triangles abc and abe are congruent' unless that same triangle relation already appears explicitly in the pool."
        )
        targeted_hints.append(
            "- follow the approved route checkpoints in order: the first bridge step should match an earlier checkpoint, and later bridge steps should progress forward rather than jumping to a later finish relation or inventing a new parallel relation."
        )
        targeted_hints.append(
            "- do not postpone an earlier approved checkpoint behind a later one. If the ordered route starts with an equality like 'ai equals eg', that equality must appear before later checkpoints like 'di equals de' or 'be equals ie', not after them."
        )
        targeted_hints.append(
            "- if the approved checkpoints are angle, ratio, equality, collinearity, or parallel relations, do not wrap them into an invented triangle-congruent or triangle-similar bridge unless that same triangle relation already appears in the approved checkpoint list."
        )
        targeted_hints.append(
            "- do not invent a point-identification step like 'h equals f' unless that same identification or an equivalent equality already appears explicitly in the approved checkpoint list."
        )
    if "unsupported high-level" in validation_message:
        targeted_hints.append(
            "- do not introduce new routes such as triangle similarity, cyclic quadrilaterals, or parallelograms inside why_it_helps unless that same structure is already stated in the approved relation chain."
        )
        targeted_hints.append(
            "- rewrite why_it_helps as a direct next-step statement like 'this is required to prove kc equals kd next' or 'this prepares the goal angle involving bg, bj, cg, and fg'."
        )
    if "Planner JSON missing keys" in validation_message:
        targeted_hints.append(
            "- return all 12 required top-level keys exactly once; do not omit coordinate_hints, bridge_steps, or goal_finish."
        )
    if aux_part and len(extract_aux_new_points(aux_part)) > 1:
        targeted_hints.append(
            "- because multiple new points are introduced, construction should use stage markers such as first, then, and finally."
        )
    targeted_hint_block = "\n".join(targeted_hints)
    if targeted_hint_block:
        targeted_hint_block += "\n"
    return (
        "Your previous JSON plan was invalid.\n"
        f"Validation error: {validation_message}\n"
        "Return a corrected JSON object that satisfies every schema and quality constraint.\n"
        "Use natural-language geometry statements rather than raw formal predicates such as 'cong b j d j'.\n"
        "Repeat earlier relations verbatim inside depends_on instead of inventing new support strings.\n"
        f"{targeted_hint_block}"
        "Schema reminder:\n"
        f"{build_plan_json_example()}"
    )


def build_writer_retry_feedback(validation_message, plan, injected_prefix=""):
    bridge_steps = plan.get("bridge_steps", []) if isinstance(plan, dict) else []
    bridge_summary = json.dumps(bridge_steps, ensure_ascii=False, indent=2) if bridge_steps else "[]"
    bridge_blueprints = (
        json.dumps(build_writer_sentence_blueprints(plan), ensure_ascii=False, indent=2)
        if isinstance(plan, dict) else "[]"
    )
    bridge_contracts = (
        json.dumps(build_writer_bridge_contracts(plan), ensure_ascii=False, indent=2)
        if isinstance(plan, dict) else "[]"
    )
    prefix_coverage_notes = build_prefix_coverage_notes(plan)
    targeted_hints = []
    if "overlaps too much with the injected prefix" in validation_message:
        targeted_hints.append(
            "- do not re-describe the anchors, figure overview, coordinate hints, or visible givens from the injected prefix; start directly from the bottleneck sentence."
        )
        targeted_hints.append(
            "- if a bridge sentence needs a visible given that already appears in the prefix, paraphrase it instead of copying the exact wording, such as 'because ad runs parallel to bc' instead of repeating 'line ad is parallel to line bc'."
        )
        targeted_hints.append(
            "- the first two body sentences should avoid every item listed under Prefix-Covered Facts; use those sentences only for the bottleneck and the missing helper."
        )
    if "first-person narration" in validation_message:
        targeted_hints.append(
            "- stay impersonal: do not use 'i', 'we', 'our', or 'let us'; write 'construct point k' instead of 'we construct point k'."
        )
        targeted_hints.append(
            "- avoid openings like 'we need' or 'we construct'; rewrite them as 'a helper is needed' and 'construct point k'."
        )
        targeted_hints.append(
            "- preferred impersonal rewrites: 'the obstacle is ...', 'a helper is needed ...', 'construct point k ...', and 'this gives ...'."
        )
    if "generic shortcut" in validation_message:
        targeted_hints.append(
            "- in each bridge sentence, name the concrete depends_on relations and also state the next approved bridge relation or goal-side relation that this sentence unlocks."
        )
        targeted_hints.append(
            "- do not summarize the support as 'symmetry', 'center of symmetry', or 'midpoint property'; explicitly restate the approved support relations such as 'h is the midpoint of bc' or 'bh equals ch'."
        )
        targeted_hints.append(
            "- when a bridge step includes internal required_supports, mention those support relations explicitly in the same sentence before landing on the new bridge relation."
        )
    if "must name at least one approved supporting relation" in validation_message:
        targeted_hints.append(
            "- every bridge sentence must name at least one concrete approved support relation from its required_supports or depends_on list; do not jump straight to the new relation with no cited support."
        )
        targeted_hints.append(
            "- preferred bridge sentence shape: support relation first, then the new approved bridge relation, then one short clause about the next target."
        )
        targeted_hints.append(
            "- if needed, follow the preferred_sentence_shell in the bridge contracts almost verbatim and only smooth the wording lightly."
        )
    if "must explicitly realize goal_finish after the bridge steps" in validation_message:
        targeted_hints.append(
            "- add one final sentence after the last bridge sentence that explicitly states the approved goal_finish relation, rather than stopping one step early."
        )
        targeted_hints.append(
            "- do not end with a vague phrase like 'this gives the claim' or 'so the target follows'; restate the exact approved goal-side ratio, angle, or congruence relation."
        )
    if "too long" in validation_message:
        targeted_hints.append(
            "- shorten the body by compressing helper or bridge prose; keep the approved relation names, but trim extra explanation and repeated restatements."
        )
        targeted_hints.append(
            "- prefer one short sentence per bridge step: one relation, one or two concrete supports, and one brief forward-looking clause."
        )
    if "contains forbidden pattern" in validation_message:
        targeted_hints.append(
            "- remove all $...$ formatting, colon-style math snippets, and proof-like shorthand; restate ratios and angles as plain English geometry relations."
        )
        targeted_hints.append(
            "- examples: write 'the ratio ab over bg' instead of '$ab:bg$', and write 'angle bk/bj equals angle dj/dk' as plain text rather than math markup."
        )
        targeted_hints.append(
            "- never wrap a point pair or line name in dollar signs: write 'line be' or 'segment bh', not '$be$' or '$bh$'."
        )
    if "midpoint propert" in validation_message:
        targeted_hints.append(
            "- do not summarize support as 'midpoint property' or 'midpoint properties'; restate the concrete midpoint facts themselves, such as 'm is the midpoint of ab' and 'am equals bm'."
        )
    if "rotational symmetry" in validation_message or "center of symmetry" in validation_message:
        targeted_hints.append(
            "- remove high-level phrases like 'rotational symmetry' or 'center of symmetry'; replace them with the concrete equalities, parallels, or midpoint facts that are actually visible in the approved plan."
        )
    if "must explicitly realize bridge_steps" in validation_message:
        targeted_hints.append(
            "- include one explicit sentence for every approved bridge_steps relation in order; do not skip the last angle or parallel relation before the goal_finish sentence."
        )
        targeted_hints.append(
            "- when a bridge relation is an angle or ratio, restate it in nearly the same point ordering and surface form as the approved relation, such as 'angle bg/bj equals angle gi/ij' or 'ac over ce equals hf over ch'."
        )
    if "must avoid vague shape shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; name the concrete perpendicular, equal-length, midpoint, or parallel relations instead."
        )
    if "must avoid unsupported center shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'common center', 'reference center', 'center of symmetry', or 'serve as the center'; name the concrete midpoint, equal-length, perpendicular, or collinear relations instead."
        )
    targeted_hint_block = "\n".join(targeted_hints)
    if targeted_hint_block:
        targeted_hint_block += "\n"
    return (
        "Your previous body text was invalid.\n"
        f"Validation error: {validation_message}\n"
        "Return a corrected plain-text body that satisfies every format and quality constraint.\n"
        "Keep one sentence for each bridge step, and explicitly name concrete supporting relations instead of using vague shortcuts.\n"
        "Prefix-Covered Facts:\n"
        f"{prefix_coverage_notes}\n\n"
        "Injected Prefix Block:\n"
        f"{injected_prefix}\n\n"
        f"{targeted_hint_block}"
        "Approved bridge steps to realize in order:\n"
        f"{bridge_summary}\n\n"
        "Bridge contracts:\n"
        f"{bridge_contracts}\n\n"
        "Sentence blueprints:\n"
        f"{bridge_blueprints}"
    )


def build_supervisor_payload(record, aux_part, sanitized_rest):
    payload = {
        key: value
        for key, value in record.items()
        if not key.startswith("_")
    }
    payload["exact_aux"] = aux_part
    payload["rest_of_output_sanitized"] = sanitized_rest
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def build_plan_prompt(record, aux_part, sanitized_rest):
    public_problem = build_public_problem_text(record)
    supervisor_payload = build_supervisor_payload(record, aux_part, sanitized_rest)
    visible_goal = extract_problem_goal(record)
    hidden_aux_brief = build_hidden_aux_brief(aux_part)
    new_points = extract_aux_new_points(aux_part)
    new_points_text = ", ".join(new_points) if new_points else "the hidden auxiliary point"
    multi_aux_instruction = build_multi_aux_instruction(aux_part)
    point_coords = get_point_coords(record)
    coord_table = json.dumps(point_coords, ensure_ascii=False, sort_keys=True)
    coordinate_hints = build_hidden_coordinate_hints(point_coords)
    coordinate_guidance = build_hidden_coordinate_guidance(point_coords)
    visible_premise_summaries = build_visible_premise_summaries(record)
    visible_premise_guidance = (
        json.dumps(visible_premise_summaries, ensure_ascii=False, indent=2)
        if visible_premise_summaries else "[]"
    )
    plan_example = build_plan_json_example()
    aux_specific_guidance = build_aux_specific_plan_guidance(aux_part)
    proof_guidance_payload = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    proof_guidance = json.dumps(
        proof_guidance_payload,
        ensure_ascii=False,
        indent=2,
    )
    immediate_aux_pool = proof_guidance_payload.get("immediate_aux_consequences", [])
    immediate_aux_block = json.dumps(immediate_aux_pool, ensure_ascii=False, indent=2) if immediate_aux_pool else "[]"
    aux_bridge_pool = proof_guidance_payload.get("aux_bridge_relations", [])
    aux_bridge_block = json.dumps(aux_bridge_pool, ensure_ascii=False, indent=2) if aux_bridge_pool else "[]"
    route_relation_pool = aux_bridge_pool + proof_guidance_payload.get("bridge_relations", []) + proof_guidance_payload.get("goal_finish_relations", [])
    route_relation_block = json.dumps(route_relation_pool, ensure_ascii=False, indent=2) if route_relation_pool else "[]"
    ordered_route_checkpoint_block = (
        "\n".join(f"{idx + 1}. {relation}" for idx, relation in enumerate(route_relation_pool))
        if route_relation_pool else "1. (no hidden route checkpoints available)"
    )
    return (
        "You are planning a geometry CoT training example.\n\n"
        "[What the future student model will see at training/eval time]\n"
        "1. The geometry image.\n"
        "2. The problem text below.\n\n"
        "[Problem Text]\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Hidden Supervisor-Only Reference]\n"
        "The JSON block below is available only while generating the dataset. It exists "
        "to keep the final answer correct, logically aligned with the true aux, and "
        "coordinate-accurate. You may use it internally, but the final thinking trace "
        "must read as if it was produced from the image and the problem text alone.\n"
        "Do not mention the hidden reference, do not mention proof IDs, do not quote "
        "the proof engine, and do not say that some fact was provided to you.\n"
        f"{supervisor_payload}\n\n"
        "[Hidden Visible-Point Coordinate Table]\n"
        f"{coord_table}\n\n"
        "[Hidden Coordinate Hints]\n"
        "These hints are computed from the visible point coordinates only. Use them to "
        "sanity-check visually plausible lines, equal lengths, midpoint structure, or "
        "parallel/perpendicular cues, but do not cite the coordinate table explicitly in the final text.\n"
        f"{coordinate_hints}\n\n"
        "[Hidden Structured Coordinate Candidates]\n"
        "Each item below is derived only from visible-point coordinates. Prefer choosing 2 or 3 of these "
        "as the concrete relation checks in your plan instead of jumping directly to high-level symmetry claims.\n"
        f"{coordinate_guidance}\n\n"
        "[Visible Premise Summaries]\n"
        "These are plain-language summaries of the visible formal premises. When you describe the existing figure, "
        "prefer reusing these concrete relations instead of inventing new high-level geometry claims.\n"
        f"{visible_premise_guidance}\n\n"
        "[Hidden Target Summary]\n"
        f"New point name(s): {new_points_text}\n"
        f"Target auxiliary facts: {hidden_aux_brief}\n\n"
        f"{multi_aux_instruction}"
        "[Hidden Proof Guidance]\n"
        "These grouped checkpoints show how the true solution moves from the aux toward the goal. "
        "Use them only to keep the verification chain realistic; do not expose proof-engine syntax.\n"
        f"{proof_guidance}\n\n"
        "[Preferred Immediate Aux Consequences]\n"
        "Choose aux_direct_relations from or very close to this bucket whenever possible. "
        "These are the local consequences that should appear immediately after the construction, before any broader bridge step.\n"
        f"{immediate_aux_block}\n\n"
        "[Preferred Aux-Bridge Checkpoints]\n"
        "If the first useful bridge relation still needs the auxiliary point, choose it from or very close to this bucket before moving on to older goal-side checkpoints.\n"
        f"{aux_bridge_block}\n\n"
        "[Approved Route Relation Pool]\n"
        "Choose bridge_steps.relation items from or very close to this relation pool, in a realistic order. "
        "Do not replace this route with a different high-level structure unless that same structure already appears below.\n"
        f"{route_relation_block}\n\n"
        "[Approved Ordered Route Checkpoints]\n"
        "Your bridge_steps should usually form an ordered subsequence of the checkpoints below. "
        "Earlier bridge steps should match earlier checkpoints, and later bridge steps should move toward the goal-side checkpoints rather than inventing a new route.\n"
        f"{ordered_route_checkpoint_block}\n\n"
        "[Task]\n"
        "Return exactly one JSON object with these keys:\n"
        "1. anchor_points: a list of 3 or 4 original visible points that are the best tagged anchors for orienting the figure.\n"
        "2. anchor_relation: one sentence describing the key visible relation or shape cue involving those anchors.\n"
        "3. figure_overview: one or two sentences surveying the broader visible figure beyond the anchors, including other relevant points or sub-structures.\n"
        "4. coordinate_relations: a list of 2 or 3 short relation checks inferred from the visible placement; each item must name the points and the relation.\n"
        "5. visible_relations: a list of 2 to 4 concrete existing-figure relations that the later reasoning should actively reuse.\n"
        "6. coordinate_hints: one or two sentences synthesizing those coordinate-backed relation checks and why they matter.\n"
        "7. goal_bottleneck: one sentence describing the main obstacle to reaching the visible goal from the current figure.\n"
        "8. helper_idea: one sentence describing what kind of helper is missing, without naming the new point yet.\n"
        "9. construction: one or two sentences that finally introduce the new point or staged point sequence in plain geometry language.\n"
        "10. aux_direct_relations: a list of 1 to 3 direct consequences that come immediately from the construction itself.\n"
        "11. bridge_steps: a list of 2 to 4 ordered objects; each object must contain relation, depends_on, and why_it_helps.\n"
        "12. goal_finish: one sentence stating the goal-side angle/ratio/congruence relation that closes the argument.\n\n"
        "[Schema Example]\n"
        "Follow this JSON shape closely. In particular, bridge_steps must be a JSON list of objects, and each depends_on value must be a JSON list of earlier relation strings.\n"
        f"{plan_example}\n\n"
        "[why_it_helps Guidance]\n"
        "Good: 'this equality is required before the next bridge relation can be justified.'\n"
        "Good: 'this prepares the final goal-side angle comparison.'\n"
        "Bad: 'this enables similar triangles involving j.'\n"
        "Bad: 'this helps form a cyclic quadrilateral and later gives a parallel line.'\n\n"
        "[helper_idea / aux_direct Guidance]\n"
        "Good helper_idea: 'we need a point that creates an equal-length transfer from k toward d while keeping a perpendicular link through c.'\n"
        "Good helper_idea: 'we need the midpoint of ad so that the equal halves can be used on the d-side.'\n"
        "Bad helper_idea: 'we need a point that will facilitate the proof.'\n"
        "Bad helper_idea: 'we need a center of symmetry' or 'we need a symmetric center' when no concrete midpoint, equal-length, parallel, or perpendicular cue has been stated.\n"
        "Bad helper_idea: 'we need the midpoint property' when the concrete midpoint fact itself has not been stated.\n"
        "Bad helper_idea: 'we need point k so that ...' because the new point name should first appear in construction.\n"
        "Good aux_direct_relations: ['kb equals kc', 'line ck is perpendicular to line dk']\n"
        "Good aux_direct_relations: ['h is the midpoint of bc', 'b, c, h are collinear']\n"
        "Good aux_direct_relations: if Hidden Proof Guidance.immediate_aux_consequences starts with ['a, d, i are collinear', 'ab equals bi', 'bd equals di'], copy 1 to 3 of those local items almost verbatim before introducing any broader equality like 'ai equals eg'.\n"
        "Bad aux_direct_relations: if a candidate relation needs old points outside the construction scope, such as a later bridge equality or a goal-side angle relation, do not place it in aux_direct_relations; use a later bridge step instead.\n"
        "Bad aux_direct_relations: ['h lies on line bc'] when the same fact should be written as 'b, c, h are collinear'.\n"
        "Bad aux_direct_relations: ['kb equals kc', 'angle akd equals ...'] when a is not part of the immediate construction.\n\n"
        "[bridge_steps Surface Guidance]\n"
        "Good bridge relation: 'ah equals bh' or 'angle ak/aj equals angle gk/gj'.\n"
        "Good bridge relation: if aux_direct_relations already give 'bj equals dj', then a later bridge step should use that equality to reach the next checkpoint, not repeat 'bj equals dj' itself.\n"
        "Good bridge ordering: if the approved ordered route checkpoints are ['ai equals eg', 'di equals de', 'be equals ie'], then the bridge steps should keep that order or take an ordered subsequence such as ['ai equals eg', 'di equals de']; do not write ['di equals de', 'be equals ie', 'ai equals eg'].\n"
        "Bad bridge relation: 'triangles abc and abe are congruent' when the approved route pool only lists equalities, angle relations, ratios, collinearities, or a different named triangle relation.\n"
        "Bad bridge relation: 'h coincides with f' when the same idea should be written as a concrete equality or another approved route relation.\n\n"
        "[coordinate_relations / visible_relations Guidance]\n"
        "Good coordinate_relations: items chosen from the hidden structured coordinate candidates, such as 'point g looks like the midpoint of ac' or 'points b, d, and i look nearly collinear'.\n"
        "Bad coordinate_relations: copying a visible premise such as 'line ad is parallel to line bc' when that relation is not one of the hidden coordinate candidates.\n"
        "Good coordinate_hints: 'the midpoint at g and the near-collinearity of b, d, and i suggest a bridge through d.'\n"
        "Bad coordinate_hints: 'the figure suggests a symmetry between e and f' or 'a rotation seems present'.\n"
        "Good visible_relations: old-figure relations like 'ab equals ac' or 'line ad is parallel to line bc'.\n"
        "Bad visible_relations: any relation involving the new auxiliary point before construction, such as 'ah equals ch'.\n\n"
        f"{aux_specific_guidance}"
        "Constraints:\n"
        "- Use only lowercase point names exactly as in the problem text.\n"
        "- Do not use <point> tags, <coord> tags, LaTeX, $...$ math formatting, backticks, <aux>, <proof>, IDs, or rule names.\n"
        "- Do not restate every premise. Focus on the visible configuration, the likely useful relations, and the bottleneck toward the visible goal.\n"
        "- Survey the whole visible figure, not just the anchor points.\n"
        "- Use the hidden coordinate table only as an internal consistency check for relations that also look plausible in the image.\n"
        "- The coordinate_relations field should stay close to the structured coordinate candidates when possible. Avoid unsupported jumps like 'there is a rotation symmetry' unless you first name the concrete equal, parallel, perpendicular, midpoint, or collinear cues behind it.\n"
        "- In coordinate_relations and coordinate_hints, do not describe points as symmetric or invoke rotation directly; spell out the concrete equal, parallel, perpendicular, midpoint, or collinear cues instead.\n"
        "- In coordinate_hints, do not use words like symmetry, symmetric, mirror, or rotation; summarize the actual midpoint, collinear, equal-length, parallel, or perpendicular cue instead.\n"
        "- Do not use vague shape shorthand or high-level shape labels such as 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; if that cue matters, spell out the concrete perpendicular, equal-length, midpoint, and parallel facts instead.\n"
        "- The visible_relations field should preferentially reuse the visible premise summaries above, plus a small number of visually obvious derived facts. It should not introduce invented centers, rotations, or unnamed transformations.\n"
        "- The coordinate_relations and visible_relations fields must stay separate: coordinate_relations are coordinate-backed visual checks, while visible_relations are existing-figure givens or obvious old-figure consequences.\n"
        "- The coordinate_hints field must be written as ordinary visual geometry language. Do not say 'the coordinates show', 'the coordinates indicate', or anything similar.\n"
        "- Do not mention the new point name before the construction field.\n"
        "- Avoid vague filler such as 'this point is crucial' or 'this will help'.\n"
        "- The helper_idea field should describe a concrete missing mechanism such as an equal-length transfer, perpendicular link, midpoint control, or goal-side angle connection. Avoid filler such as 'facilitate', 'make progress', or 'help establish'.\n"
        "- In helper_idea, do not use phrases like symmetry, symmetric center, center of symmetry, rotation center, or mirror center unless the same concrete structure is already explicitly stated in the approved visible or coordinate relations.\n"
        "- Do not describe the helper as a common center, reference center, center of symmetry, or generic center of the figure; if a midpoint or equal-distance fact matters, spell out that concrete relation directly.\n"
        "- Do not invent named centers, rotation claims, square/parallelogram claims, or similarity claims unless they are already supported by the approved coordinate checks or by the approved relation buckets.\n"
        "- The construction field must describe the same geometric facts as the hidden target summary in plain language; do not invent a different line, circle, or intersection.\n"
        "- When multiple new points are introduced, construction must explicitly describe a staged or combined strategy with markers such as 'first', 'then', 'next', or 'finally', rather than naming all points in one flat sentence.\n"
        "- Each item in aux_direct_relations must stay local to the auxiliary construction itself. Do not pull unrelated old-figure points into those direct relations.\n"
        "- aux_direct_relations should usually be copied from the Preferred Immediate Aux Consequences bucket above with only light natural-language cleanup. Do not replace those local items with later bridge equalities or broad summaries.\n"
        "- If a useful relation contains the auxiliary point but also reaches outside the construction scope, place it in bridge_steps, not aux_direct_relations. Use the Preferred Aux-Bridge Checkpoints bucket for that handoff.\n"
        "- Each bridge_steps relation should explicitly mention how the auxiliary point interacts with existing visible points or substructures, in a realistic order.\n"
        "- The first bridge_steps relation must explicitly contain the new auxiliary point together with at least one old visible point, and it should be written in a compact relation form such as 'ag equals dg' or 'angle bg/bj equals angle gi/ij'.\n"
        "- A bridge_steps relation must be a new checkpoint beyond visible_relations, aux_direct_relations, and earlier bridge_steps. If the construction already gives a relation directly, treat that relation as support and move to the next bridge checkpoint instead of repeating it.\n"
        "- Each bridge_steps relation should stay semantically close to the hidden proof guidance bridge_relations or goal_finish_relations; do not swap in a different high-level route.\n"
        "- Treat the Approved Ordered Route Checkpoints as the preferred bridge-step order. Do not jump to a later checkpoint first, and do not invent a fresh parallel/similarity/angle route when an earlier approved checkpoint is already available.\n"
        "- When the ordered route begins with a concrete equality or collinearity checkpoint, do not postpone that earlier checkpoint behind a later checkpoint. Keep the bridge steps monotone in the listed order.\n"
        "- If a candidate bridge relation is not visibly close to one of the Approved Ordered Route Checkpoints, do not use it. In particular, do not inject a fresh goal-side equality or ratio relation just because it sounds useful unless that same relation family already appears in the approved checkpoint list.\n"
        "- If the approved route checkpoints are angle, ratio, collinearity, equality, or parallel relations, do not wrap them into a new triangle-congruent or triangle-similar route unless that same triangle route already appears explicitly in the checkpoint list.\n"
        "- Do not invent a point-identification bridge such as 'h equals f' unless that same identification, or an equivalent old-figure equality using h and f, already appears in the approved route checkpoints.\n"
        "- When the approved route relation pool lists a concrete relation such as 'line bg is parallel to line cd' or 'bk = dk', prefer using that relation directly instead of inventing an alternative route like a new similar-triangle claim.\n"
        "- Each bridge_steps depends_on list should reuse concrete items from visible_relations, aux_direct_relations, or an earlier bridge_steps relation, instead of inventing unsupported leaps.\n"
        "- Each depends_on item should be a full earlier relation string with at least two named points, such as 'ab equals bi' or 'a, d, i are collinear'. Do not write shorthand like 'the equality setup' or 'the perpendicular condition'.\n"
        "- Each depends_on item must be copied as a natural-language relation string, not written as a raw formal predicate such as 'cong b j d j'.\n"
        "- Each bridge_steps why_it_helps string should explain what the current step unlocks next in plain geometry language. The script will internally attach the exact next target relation for the writer.\n"
        "- Do not use why_it_helps to smuggle in a new route such as 'similar triangles', 'cyclic quadrilateral', or 'parallelogram' unless that same structure is already explicitly present in the approved relation chain.\n"
        "- The goal_finish field must mention the actual goal-side relation, not just say that the construction is useful.\n"
        "- If multiple new points appear in the hidden target summary, describe whether they are introduced together or in stages and what each stage unlocks.\n"
        "- The wording must sound supportable from the image and visible problem text alone.\n"
    )


def build_write_prompt(record, plan, aux_part, sanitized_rest, injected_prefix_block):
    plan = enrich_bridge_steps_with_targets(plan)
    public_problem = build_public_problem_text(record)
    supervisor_payload = build_supervisor_payload(record, aux_part, sanitized_rest)
    visible_goal = extract_problem_goal(record)
    hidden_aux_brief = build_hidden_aux_brief(aux_part)
    new_points = extract_aux_new_points(aux_part)
    new_points_text = ", ".join(new_points) if new_points else "the hidden auxiliary point"
    multi_aux_instruction = build_multi_aux_instruction(aux_part)
    point_coords = get_point_coords(record)
    coord_table = json.dumps(point_coords, ensure_ascii=False, sort_keys=True)
    coordinate_hints = build_hidden_coordinate_hints(point_coords)
    coordinate_guidance = build_hidden_coordinate_guidance(point_coords)
    visible_premise_summaries = build_visible_premise_summaries(record)
    visible_premise_guidance = (
        json.dumps(visible_premise_summaries, ensure_ascii=False, indent=2)
        if visible_premise_summaries else "[]"
    )
    proof_guidance = json.dumps(
        build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal),
        ensure_ascii=False,
        indent=2,
    )
    sentence_duties = build_writer_sentence_duties(plan)
    sentence_blueprints = json.dumps(
        build_writer_sentence_blueprints(plan),
        ensure_ascii=False,
        indent=2,
    )
    bridge_contracts = json.dumps(
        build_writer_bridge_contracts(plan),
        ensure_ascii=False,
        indent=2,
    )
    prefix_coverage_notes = build_prefix_coverage_notes(plan)
    bridge_steps = plan.get("bridge_steps", []) if isinstance(plan, dict) else []
    expected_sentence_count = 4 + len(bridge_steps) + (1 if plan.get("aux_direct_relations") else 0)
    return (
        "You are polishing a geometry CoT example for SFT.\n\n"
        "[Visible Inputs]\n"
        "The final trained model will only see the image and the problem text below.\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Hidden Supervisor-Only Reference]\n"
        "Use this only to ensure factual correctness and exact point coordinates. Do not "
        "mention that it exists, and do not let any hidden proof artifact appear in the "
        "final wording.\n"
        f"{supervisor_payload}\n\n"
        "[Hidden Visible-Point Coordinate Table]\n"
        f"{coord_table}\n\n"
        "[Hidden Coordinate Hints]\n"
        f"{coordinate_hints}\n\n"
        "[Hidden Structured Coordinate Candidates]\n"
        f"{coordinate_guidance}\n\n"
        "[Visible Premise Summaries]\n"
        f"{visible_premise_guidance}\n\n"
        "[Hidden Target Summary]\n"
        f"New point name(s): {new_points_text}\n"
        f"Target auxiliary facts: {hidden_aux_brief}\n\n"
        f"{multi_aux_instruction}"
        "[Hidden Proof Guidance]\n"
        "Use these only to keep the post-aux verification path faithful to the actual solvable route. "
        "Do not quote them, and do not surface proof-engine artifacts.\n"
        f"{proof_guidance}\n\n"
        "[Approved Plan]\n"
        f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        "[Approved Milestones]\n"
        f"Existing visible relations to reuse: {json.dumps(plan.get('visible_relations', []), ensure_ascii=False)}\n"
        f"Direct aux consequences to realize in order: {json.dumps(plan.get('aux_direct_relations', []), ensure_ascii=False)}\n"
        f"Bridge steps to realize in order: {json.dumps(plan.get('bridge_steps', []), ensure_ascii=False, indent=2)}\n"
        f"Goal-side finish to reach: {plan.get('goal_finish', '')}\n\n"
        "[Sentence Duties]\n"
        "Use this outline internally to keep the body stepwise, concrete, and impersonal. Do not quote these lines verbatim, and do not repeat the injected prefix.\n"
        f"{sentence_duties}\n\n"
        "[Sentence Blueprints]\n"
        "Use these sentence-level blueprints as the preferred local writing pattern. They are stricter than the prose duties: support relation first when available, then the approved relation, then a short next-target clause, with no fresh geometric claim added in the middle.\n"
        f"{sentence_blueprints}\n\n"
        "[Bridge Sentence Contracts]\n"
        "Use these contracts as a hard checklist for the post-aux body sentences. Each listed relation should appear explicitly, the listed supports should be named inside the same sentence when required, and the goal_finish contract must be realized after the final bridge sentence.\n"
        f"{bridge_contracts}\n\n"
        "[Compression Target]\n"
        f"Aim for about {expected_sentence_count} sentences total in the body. Keep each bridge sentence compact and concrete, usually one relation plus one or two named supports, rather than a long recap of the whole chain.\n\n"
        "[Injected Prefix Block]\n"
        "The script will prepend the following block exactly before your body. Do not restate these claims; start after them.\n"
        f"{injected_prefix_block}\n\n"
        "[Prefix-Covered Facts]\n"
        "The facts below are already stated by the injected prefix. Do not repeat them in the first two body sentences, and later references should usually be paraphrased rather than copied verbatim.\n"
        f"{prefix_coverage_notes}\n\n"
        "[Write Requirements]\n"
        "Write only the body text that comes after the script-supplied prefix block: an anchor sentence with coordinate tags, a full-figure overview sentence, a coordinate-focused prefix built from the approved relation checks, and a visible-relations sentence injected from the approved plan.\n"
        "Do NOT output <thinking>, <point>, or <coord> tags; the script will add the prefix sentences and the coordinate tags itself.\n"
        "The body must satisfy all of the following:\n"
        "1. It should sound supportable from the image and visible problem text alone.\n"
        "2. It should be logically coherent and centered on discovering the auxiliary construction and then checking that the construction can genuinely advance the visible goal.\n"
        "3. Follow this order: bottleneck -> missing helper idea -> final introduction of the new point or staged points -> explicit realization of aux_direct_relations -> each bridge_steps relation in order, using its depends_on and why_it_helps -> goal_finish.\n"
        "4. Most of the reasoning should happen before the new auxiliary point is named; only introduce that point in the later part of the body.\n"
        "5. Use the plan faithfully, but rewrite it into smooth prose instead of JSON fragments.\n"
        "6. Replace vague statements like 'this point is crucial' with a concrete bottleneck, relation, or next-step verification claim.\n"
        "7. Use the original lowercase point names exactly as in the problem text; do not rewrite them as uppercase, LaTeX, $...$ math formatting, or backticks.\n"
        "8. Keep the body concise and specific, roughly 120 to 230 words.\n"
        "9. The construction and post-aux verification must stay faithful to the hidden target summary; do not invent a different construction than the approved plan.\n"
        "10. It must not contain <aux>, <proof>, <numerical_check>, [012]-style IDs, AR/r63/a01-style rule tokens, or meta-talk.\n"
        "11. It must not say that some coordinate table, hidden answer, proof, or reference was provided.\n"
        "12. It must not assign coordinates to newly introduced auxiliary points.\n"
        "13. Do not repeat the prefix sentences verbatim; continue from them.\n"
        "14. Do not mention coordinates explicitly; describe those cues as visual placement, alignment, symmetry, equal-looking lengths, or perpendicular/parallel structure.\n"
        "15. Keep the post-aux reasoning faithful to the approved visible_relations, aux_direct_relations, bridge_steps, and goal_finish; do not replace them with a different invented route.\n"
        "16. Do not introduce extra named centers, rotational symmetries, square/parallelogram claims, or triangle-similarity claims unless the approved plan already states them and the immediate aux step really supports them.\n"
        "16a. Do not use vague shape shorthand or high-level shape labels such as 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; replace them with the concrete perpendicular, equal-length, midpoint, or parallel relations that justify the step.\n"
        "16b. Do not use unsupported center shorthand such as 'common center', 'reference center', 'center of symmetry', or 'serve as the center'; replace it with the concrete midpoint, equal-length, perpendicular, or collinear relations that justify the step.\n"
        "17. Reuse the approved visible_relations when connecting the new point back to the old figure, rather than inventing fresh structural claims.\n"
        "18. Stay impersonal. Do not write in the first person.\n"
        "19. The very first sentence of your body should state the bottleneck or goal-side obstacle. Do not spend the first sentence re-describing triangle abc, the midpoint layout, or the visible givens already covered by the injected prefix block.\n"
        "19a. The second sentence should state the missing helper idea, not repeat any overview, coordinate cue, or visible relation already listed under Prefix-Covered Facts.\n"
        "20. Give each bridge_steps relation its own sentence. In that sentence, explicitly name at least one concrete depends_on relation before or while stating the new bridge relation.\n"
        "20a. When a bridge step lists internal required_supports, mention those support relations explicitly in the same sentence unless doing so would repeat the exact prefix wording; in that case paraphrase them.\n"
        "20b. When a bridge contract includes a preferred_sentence_shell, stay very close to that local order and only smooth the wording lightly.\n"
        "21. Avoid shortcuts such as 'by symmetry', 'from the setup', or 'it follows' unless the same sentence explicitly names the concrete supporting relations.\n"
        "22. Do not hedge with phrases like 'similarity or angle equality'; state the specific approved relation you are using.\n"
        "23. Each bridge_steps object includes an internal next_target_relation chosen by the script. Use it to keep the reasoning pointed toward the next approved relation instead of inventing a different route.\n"
        "24. Use impersonal sentence forms such as 'the obstacle is ...', 'a helper is needed ...', 'construct point h ...', and 'this gives ...'; avoid first-person forms like 'we need' or 'we construct'.\n"
        "25. If you need to reuse a visible given that already appears in the injected prefix, paraphrase it instead of copying the exact wording from the prefix sentence.\n"
        "26. In bridge sentences, do not replace the approved supports with summary labels such as 'symmetry', 'center of symmetry', or 'midpoint property'; name the actual equalities, collinearities, parallels, or perpendicularities instead.\n"
        "27. When an approved bridge relation is an angle or ratio relation, write it in nearly the same point ordering and surface form as the approved relation, rather than paraphrasing it into a looser sentence like 'the angle formed by ...'.\n"
        "28. Keep the bridge sentences tight: usually one approved relation, one or two concrete supports, and one short forward-looking clause. Do not spend multiple clauses re-explaining the same visible setup.\n"
        "29. Never wrap a point pair, line name, segment name, ratio, or angle label in dollar signs or LaTeX-style math. Write 'line be', 'segment bh', or 'ratio de to di' as plain text, not '$be$', '$bh$', or '$de:di$'.\n"
        "30. Within each bridge sentence, prefer this local order unless the English becomes ungrammatical: approved support relation -> approved bridge relation -> short next-target clause. Avoid inserting a fresh geometric claim between those parts.\n"
        "Output only the plain-text body.\n"
    )


def is_transient_api_error(exc):
    message = str(exc).lower()
    transient_markers = [
        "connection error",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "server disconnected",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "internal server error",
        "502",
        "503",
        "504",
    ]
    return any(marker in message for marker in transient_markers)


def call_model(messages, model_name, temperature=0.2, max_tokens=2048):
    last_exc = None
    for attempt in range(1, DEFAULT_API_CALL_RETRIES + 1):
        try:
            response = get_client().chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as exc:
            last_exc = exc
            if attempt >= DEFAULT_API_CALL_RETRIES or not is_transient_api_error(exc):
                raise
            sleep_seconds = DEFAULT_API_RETRY_BACKOFF_SECONDS * attempt + random.uniform(0.0, 1.0)
            logger.warning(
                "Transient API failure on call attempt %s/%s: %s. Retrying in %.1fs",
                attempt,
                DEFAULT_API_CALL_RETRIES,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
    raise last_exc


def run_stage(stage_name, messages, model_name, point_coords, max_retries, require_coord_tags):
    last_error = None
    last_output = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name)
            elapsed = time.time() - start
            last_output = output
            ok, message = validate_thinking_response(
                output,
                point_coords=point_coords,
                require_coord_tags=require_coord_tags,
            )
            if ok:
                logger.info(f"[{stage_name}] Valid output in {elapsed:.2f}s")
                return {
                    "success": True,
                    "output": output,
                    "attempts_used": attempt,
                    "elapsed_seconds": elapsed,
                    "error": None,
                }

            last_error = message
            logger.warning(f"[{stage_name}] Validation failed: {message}")
            if attempt < max_retries:
                feedback = (
                    "Your previous answer was invalid.\n"
                    f"Validation error: {message}\n"
                    "Return a corrected answer that satisfies every format and leakage constraint."
                )
                messages = messages + [{"role": "user", "content": feedback}]
                time.sleep(1)

        except Exception as exc:
            last_error = str(exc)
            logger.error(f"[{stage_name}] API call failed: {exc}")
            if attempt < max_retries:
                time.sleep(2)

    return {
        "success": False,
        "output": last_output,
        "attempts_used": max_retries,
        "elapsed_seconds": None,
        "error": last_error or "Unknown error",
    }


def run_plan_stage(
    stage_name,
    messages,
    model_name,
    point_coords,
    visible_goal,
    aux_part,
    coordinate_candidates,
    sanitized_rest,
    visible_premise_summaries,
    max_retries,
):
    last_error = None
    last_output = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name)
            elapsed = time.time() - start
            last_output = output
            ok, message, plan = validate_plan_response(
                output,
                point_coords,
                visible_goal=visible_goal,
                aux_part=aux_part,
                coordinate_candidates=coordinate_candidates,
                sanitized_rest=sanitized_rest,
                visible_premise_summaries=visible_premise_summaries,
            )
            if ok:
                logger.info(f"[{stage_name}] Valid output in {elapsed:.2f}s")
                return {
                    "success": True,
                    "output": output,
                    "parsed": plan,
                    "attempts_used": attempt,
                    "elapsed_seconds": elapsed,
                    "error": None,
                }

            last_error = message
            logger.warning(f"[{stage_name}] Validation failed: {message}")
            if attempt < max_retries:
                feedback = build_plan_retry_feedback(message, aux_part)
                messages = messages + [{"role": "user", "content": feedback}]
                time.sleep(1)

        except Exception as exc:
            last_error = str(exc)
            logger.error(f"[{stage_name}] API call failed: {exc}")
            if attempt < max_retries:
                time.sleep(2)

    return {
        "success": False,
        "output": last_output,
        "parsed": None,
        "attempts_used": max_retries,
        "elapsed_seconds": None,
        "error": last_error or "Unknown error",
    }


def run_writer_stage(stage_name, messages, model_name, visible_goal, injected_prefix, plan, max_retries):
    last_error = None
    last_output = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name)
            elapsed = time.time() - start
            last_output = output
            ok, message = validate_writer_body(
                output,
                visible_goal=visible_goal,
                injected_prefix=injected_prefix,
                plan=plan,
            )
            if ok:
                logger.info(f"[{stage_name}] Valid output in {elapsed:.2f}s")
                return {
                    "success": True,
                    "output": output.strip(),
                    "attempts_used": attempt,
                    "elapsed_seconds": elapsed,
                    "error": None,
                }

            last_error = message
            logger.warning(f"[{stage_name}] Validation failed: {message}")
            if attempt < max_retries:
                feedback = build_writer_retry_feedback(message, plan, injected_prefix=injected_prefix)
                messages = messages + [{"role": "user", "content": feedback}]
                time.sleep(1)

        except Exception as exc:
            last_error = str(exc)
            logger.error(f"[{stage_name}] API call failed: {exc}")
            if attempt < max_retries:
                time.sleep(2)

    return {
        "success": False,
        "output": last_output,
        "attempts_used": max_retries,
        "elapsed_seconds": None,
        "error": last_error or "Unknown error",
    }


def generate_thinking(record, image_path: Path, aux_part, sanitized_rest, model_name, max_retries, verbose):
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    coordinate_candidates = build_hidden_coordinate_candidates(point_coords, max_items=64, relax_type_limits=True)
    visible_premise_summaries = build_visible_premise_summaries(record)
    plan_prompt = build_plan_prompt(record, aux_part, sanitized_rest)
    plan_messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _encode_image_base64(image_path)}},
                {"type": "text", "text": plan_prompt},
            ],
        }
    ]
    plan_result = run_plan_stage(
        "plan",
        plan_messages,
        model_name=model_name,
        point_coords=point_coords,
        visible_goal=visible_goal,
        aux_part=aux_part,
        coordinate_candidates=coordinate_candidates,
        sanitized_rest=sanitized_rest,
        visible_premise_summaries=visible_premise_summaries,
        max_retries=max_retries,
    )
    if not plan_result["success"]:
        return {
            "success": False,
            "thinking": plan_result["output"],
            "plan_prompt": plan_prompt,
            "write_prompt": None,
            "plan_output": plan_result["output"] if verbose else None,
            "plan_parsed": None,
            "attempts_used": plan_result["attempts_used"],
            "elapsed_seconds": plan_result["elapsed_seconds"],
            "error": plan_result["error"],
        }

    write_prompt = build_write_prompt(
        record,
        plan_result["parsed"],
        aux_part=aux_part,
        sanitized_rest=sanitized_rest,
        injected_prefix_block=build_injected_prefix_block(plan_result["parsed"], point_coords),
    )
    injected_prefix = build_injected_prefix_block(plan_result["parsed"], point_coords)
    write_messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _encode_image_base64(image_path)}},
                {"type": "text", "text": write_prompt},
            ],
        }
    ]
    write_result = run_writer_stage(
        "write",
        write_messages,
        model_name=model_name,
        visible_goal=visible_goal,
        injected_prefix=injected_prefix,
        plan=plan_result["parsed"],
        max_retries=max_retries,
    )

    assembled_thinking = None
    if write_result["output"]:
        assembled_thinking = f"<thinking>{injected_prefix} {write_result['output'].strip()}</thinking>"
        is_valid, message = validate_thinking_response(
            assembled_thinking,
            point_coords=point_coords,
            require_coord_tags=True,
        )
        if not is_valid:
            return {
                "success": False,
                "thinking": assembled_thinking,
                "plan_prompt": plan_prompt if verbose else None,
                "write_prompt": write_prompt if verbose else None,
                "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
                "plan_parsed": plan_result["parsed"],
                "attempts_used": plan_result["attempts_used"] + write_result["attempts_used"],
                "elapsed_seconds": (
                    (plan_result["elapsed_seconds"] or 0.0) +
                    (write_result["elapsed_seconds"] or 0.0)
                ),
                "error": f"Final assembly validation failed: {message}",
            }

    return {
        "success": write_result["success"],
        "thinking": assembled_thinking,
        "plan_prompt": plan_prompt if verbose else None,
        "write_prompt": write_prompt if verbose else None,
        "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
        "plan_parsed": plan_result["parsed"],
        "elapsed_seconds": (
            (plan_result["elapsed_seconds"] or 0.0) +
            (write_result["elapsed_seconds"] or 0.0)
        ),
        "attempts_used": plan_result["attempts_used"] + write_result["attempts_used"],
        "error": write_result["error"],
        "write_output": write_result["output"] if verbose else None,
    }


def process_and_generate_sft(
    input_jsonl,
    output_jsonl,
    sample_size,
    num_workers,
    model_name,
    verbose,
    random_sample,
    process_all,
    max_retries,
    run_metadata=None,
    run_dir=None,
):
    input_path = resolve_input_jsonl(input_jsonl)
    if not input_path.exists():
        raise FileNotFoundError(f"Input JSONL not found: {input_path}")

    if run_dir is None:
        run_dir = build_run_dir(output_jsonl)
    run_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(run_dir / "run.log")
    logger.info(f"Using input dataset: {input_path}")
    logger.info(f"Run artifacts will be stored in {run_dir}")

    if run_metadata is not None:
        write_json(run_dir / "run_config.json", run_metadata)

    all_aux_records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            if not line.strip():
                continue
            record = json.loads(line)
            aux_part, sanitized_rest = extract_aux_and_rest(record.get("llm_output_renamed", ""))
            if aux_part is None:
                continue
            record["_source_index"] = line_idx
            record["_aux_part"] = aux_part
            record["_sanitized_rest"] = sanitized_rest
            all_aux_records.append(record)

    logger.info(f"Found {len(all_aux_records)} items containing <aux>.")
    if process_all:
        selected = all_aux_records
    elif len(all_aux_records) <= sample_size:
        selected = all_aux_records
    elif random_sample:
        selected = random.sample(all_aux_records, sample_size)
    else:
        selected = all_aux_records[:sample_size]

    sampled_inputs = []
    for idx, record in enumerate(selected):
        sampled_inputs.append(
            {
                "sample_order": idx,
                "input_index": record["_source_index"],
                "image_path": record.get("image_path", ""),
                "llm_input_renamed": record.get("llm_input_renamed", ""),
                "aux": record["_aux_part"],
                "point_coords_grid": record.get("point_coords_grid", {}),
            }
        )
    if verbose:
        write_jsonl(run_dir / "sampled_inputs.jsonl", sampled_inputs)

    start_time = time.time()

    def process_item(idx_record):
        sample_order, record = idx_record
        image_path = resolve_image_path(record.get("image_path", ""), input_path)
        source_audit = audit_source_record(
            record,
            image_path=image_path,
            aux_part=record["_aux_part"],
            sanitized_rest=record["_sanitized_rest"],
        )
        if not image_path.exists():
            return {
                "result_data": None,
                "item_record": {
                    "sample_order": sample_order,
                    "input_index": record["_source_index"],
                    "image_path": str(image_path),
                    "source_audit": source_audit,
                    "success": False,
                    "error": f"Image not found: {image_path}",
                },
            }

        generation = generate_thinking(
            record,
            image_path=image_path,
            aux_part=record["_aux_part"],
            sanitized_rest=record["_sanitized_rest"],
            model_name=model_name,
            max_retries=max_retries,
            verbose=verbose,
        )
        public_problem = build_public_problem_text(record)
        aux_part = record["_aux_part"]
        thinking = generation["thinking"]
        output = None
        result_data = None
        generation_audit = audit_generation_quality(record, generation, aux_part)

        if generation["success"] and thinking:
            output = f"{thinking}\n{aux_part}"
            result_data = {
                "instruction": build_instruction_text(),
                "input": public_problem,
                "thinking": thinking,
                "aux": aux_part,
                "output": output,
                "image_path": record.get("image_path", ""),
                "_order": sample_order,
            }

        item_record = {
            "sample_order": sample_order,
            "input_index": record["_source_index"],
            "image_path": str(image_path),
            "public_problem": public_problem,
            "aux": aux_part,
            "hidden_rest_sanitized": record["_sanitized_rest"],
            "point_coords_grid": record.get("point_coords_grid", {}),
            "source_audit": source_audit,
            "generation_audit": generation_audit,
            "plan_prompt": generation.get("plan_prompt"),
            "write_prompt": generation.get("write_prompt"),
            "plan_output": generation.get("plan_output"),
            "plan_parsed": generation.get("plan_parsed"),
            "write_output": generation.get("write_output"),
            "thinking": thinking,
            "success": generation["success"],
            "attempts_used": generation["attempts_used"],
            "elapsed_seconds": generation["elapsed_seconds"],
            "error": generation["error"],
        }
        return {"result_data": result_data, "item_record": item_record}

    sft_dataset = []
    item_records = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_item, (i, rec)): i for i, rec in enumerate(selected)}
        for future in as_completed(futures):
            result = future.result()
            item_records.append(result["item_record"])
            if result["result_data"] is not None:
                sft_dataset.append(result["result_data"])

    sft_dataset.sort(key=lambda x: x["_order"])
    for item in sft_dataset:
        item.pop("_order")
    item_records.sort(key=lambda x: x["sample_order"])

    ensure_parent_dir(output_jsonl)
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for item in sft_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    if verbose:
        write_jsonl(run_dir / "item_records.jsonl", item_records)

    source_audit_issue_items = sum(1 for item in item_records if item.get("source_audit", {}).get("has_issue"))
    generation_audit_issue_items = sum(1 for item in item_records if item.get("generation_audit", {}).get("has_issue"))
    summary = {
        "input_jsonl": str(input_path),
        "total_candidates_with_aux": len(all_aux_records),
        "sampled_items": len(selected),
        "successful_items": len(sft_dataset),
        "failed_items": len(selected) - len(sft_dataset),
        "source_audit_issue_items": source_audit_issue_items,
        "generation_audit_issue_items": generation_audit_issue_items,
        "num_workers": num_workers,
        "max_retries_per_stage": max_retries,
        "model_name": model_name,
        "output_jsonl": os.path.abspath(output_jsonl),
        "artifacts_dir": os.path.abspath(run_dir),
        "runtime_seconds": time.time() - start_time,
    }
    write_json(run_dir / "summary.json", summary)
    write_jsonl(run_dir / "item_audits.jsonl", [
        {
            "sample_order": item["sample_order"],
            "input_index": item["input_index"],
            "source_audit": item.get("source_audit", {}),
            "generation_audit": item.get("generation_audit", {}),
            "success": item.get("success", False),
        }
        for item in item_records
    ])
    logger.info("SFT dataset generation completed.")
    logger.info(f"Generated {len(sft_dataset)} records.")
    return {
        "output_jsonl": os.path.abspath(output_jsonl),
        "run_dir": os.path.abspath(run_dir),
        "summary": summary,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate geometry CoT SFT data with hidden supervision and visible-only outputs."
    )
    default_output_jsonl = build_default_output_jsonl()
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default=str(DEFAULT_INPUT_JSONL),
        help=f"Input JSONL path. Default: {DEFAULT_INPUT_JSONL}",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=str(default_output_jsonl),
        help=f"Output JSONL path. Default: {default_output_jsonl}",
    )
    parser.add_argument(
        "-n",
        "--num-samples",
        type=int,
        default=3,
        help="Number of samples to process when not using --process-all. Default: 3.",
    )
    parser.add_argument(
        "--process-all",
        action="store_true",
        help="Process every record containing <aux> instead of sampling.",
    )
    parser.add_argument(
        "-w",
        "--num-workers",
        type=int,
        default=4,
        help="Number of concurrent worker threads. Default: 4.",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help=f"Teacher model name. Default: {DEFAULT_MODEL_NAME}",
    )
    parser.add_argument(
        "-r",
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries per generation stage. Default: 3.",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Use the first N eligible samples instead of random sampling.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Write sampled inputs and item-level prompts/outputs to artifacts.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    args_dict = vars(args).copy()
    run_dir = build_run_dir(args.output)
    run_metadata = build_run_manifest(args_dict, args.output, run_dir, args.model_name)

    process_and_generate_sft(
        input_jsonl=args.input,
        output_jsonl=args.output,
        sample_size=args.num_samples,
        num_workers=args.num_workers,
        model_name=args.model_name,
        verbose=args.verbose,
        random_sample=not args.sequential,
        process_all=args.process_all,
        max_retries=args.max_retries,
        run_metadata=run_metadata,
        run_dir=run_dir,
    )
