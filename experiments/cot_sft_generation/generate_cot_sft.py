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
        expectations.append(("equal-length", ["equal", "congruent", "same distance", "equidistant"]))
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


def build_visible_premise_summaries(record, max_items=12):
    formal_problem = (record.get("llm_input_renamed") or "").strip()
    body_match = PROBLEM_BODY_RE.search(formal_problem)
    body = body_match.group(1).strip() if body_match else formal_problem
    if "?" in body:
        body = body.split("?", 1)[0].strip()

    summaries = []
    seen = set()
    for clause in [part.strip() for part in body.split(";") if part.strip()]:
        if ":" not in clause:
            continue
        _, relation_text = clause.split(":", 1)
        for fact in split_formal_relation_chain(relation_text):
            summary = summarize_aux_clause(fact)
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

    return {
        "issues": issues,
        "has_issue": bool(issues),
    }


def audit_generation_quality(record, generation, aux_part):
    issues = []
    point_coords = get_point_coords(record)
    visible_points = extract_visible_point_names(point_coords)
    coordinate_candidates = build_hidden_coordinate_candidates(point_coords, max_items=64, relax_type_limits=True)
    plan = generation.get("plan_parsed") or {}
    suspicious_markers = [
        "rotational symmetry",
        "common center",
        "circumcenter",
        "square-like",
        "parallelogram",
        "crucial center",
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

    text_to_scan = " ".join(
        part for part in [generation.get("write_output"), generation.get("thinking")] if part
    ).lower()
    for marker in suspicious_markers:
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


def validate_descriptive_text(value, field_name, min_chars=12, point_names=None):
    if isinstance(value, str) and point_names:
        value = normalize_point_case(value, point_names)
    if not isinstance(value, str) or len(value.strip()) < min_chars:
        return False, f"{field_name} must be a non-empty descriptive string", None
    value = value.strip()
    if RAW_POINT_TAG_RE.search(value) or POINT_TAG_RE.search(value):
        return False, f"{field_name} must not contain point tags", None
    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(value)
        if hit:
            return False, f"{field_name} contains forbidden pattern: {hit.group(0)}", None
    return True, None, value


def validate_relation_list(items, field_name, visible_points, min_len=2, max_len=3, min_chars=12):
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
        if not relation_keyword_present(cleaned_item):
            return False, f"{field_name}[{idx}] must mention a concrete geometric relation", None
        mentioned = extract_point_mentions(cleaned_item, visible_points)
        if len(mentioned) < 2:
            return False, f"{field_name}[{idx}] must mention at least two visible points", None
        cleaned.append(cleaned_item)
    return True, None, cleaned


def build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal, max_aux=6, max_bridge=4, max_finish=4):
    proof_match = re.search(r"<proof>(.*?)</proof>", sanitized_rest or "", re.DOTALL | re.IGNORECASE)
    aux_direct = build_aux_direct_consequences(aux_part)
    if not proof_match:
        return {
            "immediate_aux_consequences": aux_direct[:max_aux],
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
        if item["has_new_point"] and not item["has_goal_point"] and text not in seen:
            seen.add(text)
            immediate.append(text)
            if len(immediate) >= max_aux:
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
        "bridge_relations": bridge,
        "goal_finish_relations": finish,
    }


def validate_plan_response(output_text: str, point_coords, visible_goal="", aux_part=None, coordinate_candidates=None):
    plan = extract_json_object(output_text)
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
        "bridge_relations",
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
        ok, message, cleaned_value = validate_descriptive_text(plan.get(key), key, point_names=known_points)
        if not ok:
            return False, message, None
        cleaned_plan[key] = cleaned_value

    ok, message, cleaned_relations = validate_relation_list(
        plan.get("coordinate_relations"),
        "coordinate_relations",
        visible_points,
        min_len=2,
        max_len=3,
    )
    if not ok:
        return False, message, None
    cleaned_plan["coordinate_relations"] = cleaned_relations

    ok, message, cleaned_visible_relations = validate_relation_list(
        plan.get("visible_relations"),
        "visible_relations",
        visible_points,
        min_len=2,
        max_len=4,
        min_chars=5,
    )
    if not ok:
        return False, message, None
    cleaned_plan["visible_relations"] = cleaned_visible_relations

    aux_direct_relations = plan.get("aux_direct_relations")
    if not isinstance(aux_direct_relations, list) or not (1 <= len(aux_direct_relations) <= 3):
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
        if not relation_keyword_present(cleaned_step):
            return False, f"aux_direct_relations[{idx}] must mention a concrete geometric relation", None
        cleaned_direct.append(cleaned_step)
    cleaned_plan["aux_direct_relations"] = cleaned_direct

    bridge_relations = plan.get("bridge_relations")
    if not isinstance(bridge_relations, list) or not (2 <= len(bridge_relations) <= 4):
        return False, "bridge_relations must be a list with 2 to 4 ordered bridge steps", None
    cleaned_bridge = []
    for idx, step in enumerate(bridge_relations):
        ok, message, cleaned_step = validate_descriptive_text(
            step,
            f"bridge_relations[{idx}]",
            min_chars=5,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        if not relation_keyword_present(cleaned_step):
            return False, f"bridge_relations[{idx}] must mention a concrete geometric relation", None
        cleaned_bridge.append(cleaned_step)
    cleaned_plan["bridge_relations"] = cleaned_bridge

    ok, message, cleaned_goal_finish = validate_descriptive_text(
        plan.get("goal_finish"),
        "goal_finish",
        min_chars=8,
        point_names=known_points,
    )
    if not ok:
        return False, message, None
    if not relation_keyword_present(cleaned_goal_finish):
        return False, "goal_finish must mention a concrete goal-side geometric relation", None
    cleaned_plan["goal_finish"] = cleaned_goal_finish

    if not relation_keyword_present(cleaned_plan["coordinate_hints"]):
        return False, "coordinate_hints must mention at least one concrete geometric relation cue", None

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

    relation_mentions = extract_point_mentions(" ".join(cleaned_plan["coordinate_relations"]), visible_points)
    if len(relation_mentions) < 3:
        return False, "coordinate_relations should collectively cover at least three visible points", None

    if not any(point in cleaned_plan["coordinate_hints"].lower() for point in relation_mentions):
        return False, "coordinate_hints must summarize at least one concrete point-based relation from coordinate_relations", None

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

    if aux_part:
        construction_text = f"{cleaned_plan['helper_idea']} {cleaned_plan['construction']}".lower()
        for label, keywords in build_aux_keyword_expectations(aux_part):
            if not any(keyword in construction_text for keyword in keywords):
                return False, f"construction is missing an expected {label} cue", None
        new_points = [point.lower() for point in extract_aux_new_points(aux_part)]
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
                return False, "bridge_relations[0] must still reference the auxiliary point while bridging to the old figure", None
    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec["points"])
    goal_keywords = goal_keyword_hints(visible_goal)
    final_step = cleaned_goal_finish.lower()
    if goal_points:
        mentioned_goal_points = {point for point in goal_points if point in final_step}
        if len(mentioned_goal_points) < min(2, len(goal_points)):
            return False, "goal_finish must mention the target relation using goal-side points", None
    if not any(keyword in final_step for keyword in goal_keywords):
        return False, "goal_finish must explicitly describe the goal-side relation it is aiming for", None
    if aux_part:
        bridge_mentions = extract_point_mentions(" ".join(cleaned_plan["bridge_relations"]), visible_points)
        if not (bridge_mentions - set(extract_aux_new_points(aux_part))):
            return False, "bridge_relations must connect the auxiliary point to existing visible points", None

    return True, "Valid planner JSON", cleaned_plan


def validate_writer_body(output_text: str, visible_goal="", injected_prefix=""):
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
    if len(body) > 1500:
        return False, f"Writer body too long ({len(body)} chars, maximum 1500)"
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
    if injected_prefix and has_long_ngram_overlap(injected_prefix, body, ngram_size=7):
        return False, "Writer body overlaps too much with the injected prefix block; continue from it instead of repeating it"
    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(body)
        if hit:
            return False, f"Writer body contains forbidden pattern: {hit.group(0)}"
    return True, "Valid writer body"


def build_instruction_text():
    return (
        "Given the geometry image and the formal problem text, write a forward-thinking "
        "trace that motivates the auxiliary construction. Output the thinking trace and "
        "the final aux block."
    )


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
    tokens = clause.split()
    if not tokens:
        return None

    pred = tokens[0]
    args = tokens[1:]
    if pred == "cong" and len(args) >= 4:
        return f"{args[0]}{args[1]} = {args[2]}{args[3]}"
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
    if pred == "eqratio" and len(args) >= 8:
        return f"{args[0]}{args[1]}:{args[2]}{args[3]} = {args[4]}{args[5]}:{args[6]}{args[7]}"
    if pred == "eqangle" and len(args) >= 8:
        return f"angle {args[0]}{args[1]}/{args[2]}{args[3]} equals angle {args[4]}{args[5]}/{args[6]}{args[7]}"
    if pred in {"simtri", "simtrir"} and len(args) >= 6:
        return f"triangles {args[0]}{args[1]}{args[2]} and {args[3]}{args[4]}{args[5]} are similar"
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


def build_public_problem_text(record):
    nl_problem = (record.get("nl_problem") or "").strip()
    formal_problem = (record.get("llm_input_renamed") or "").strip()
    if nl_problem:
        return f"<nl_problem>{nl_problem}</nl_problem>\n{formal_problem}"
    return formal_problem


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
    proof_guidance = json.dumps(
        build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal),
        ensure_ascii=False,
        indent=2,
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
        "11. bridge_relations: a list of 2 to 4 ordered bridge relations showing how the new point reconnects to the old figure.\n"
        "12. goal_finish: one sentence stating the goal-side angle/ratio/congruence relation that closes the argument.\n\n"
        "Constraints:\n"
        "- Use only lowercase point names exactly as in the problem text.\n"
        "- Do not use <point> tags, <coord> tags, LaTeX, $...$ math formatting, backticks, <aux>, <proof>, IDs, or rule names.\n"
        "- Do not restate every premise. Focus on the visible configuration, the likely useful relations, and the bottleneck toward the visible goal.\n"
        "- Survey the whole visible figure, not just the anchor points.\n"
        "- Use the hidden coordinate table only as an internal consistency check for relations that also look plausible in the image.\n"
        "- The coordinate_relations field should stay close to the structured coordinate candidates when possible. Avoid unsupported jumps like 'there is a rotation symmetry' unless you first name the concrete equal, parallel, perpendicular, midpoint, or collinear cues behind it.\n"
        "- The visible_relations field should preferentially reuse the visible premise summaries above, plus a small number of visually obvious derived facts. It should not introduce invented centers, rotations, or unnamed transformations.\n"
        "- The coordinate_hints field must be written as ordinary visual geometry language. Do not say 'the coordinates show', 'the coordinates indicate', or anything similar.\n"
        "- Do not mention the new point name before the construction field.\n"
        "- Avoid vague filler such as 'this point is crucial' or 'this will help'.\n"
        "- Do not invent named centers, rotation claims, square/parallelogram claims, or similarity claims unless they are already supported by the approved coordinate checks or by the approved relation buckets.\n"
        "- The construction field must describe the same geometric facts as the hidden target summary in plain language; do not invent a different line, circle, or intersection.\n"
        "- Each item in aux_direct_relations must stay local to the auxiliary construction itself. Do not pull unrelated old-figure points into those direct relations.\n"
        "- The bridge_relations field should explicitly mention how the auxiliary point interacts with existing visible points or substructures, in a realistic order.\n"
        "- The goal_finish field must mention the actual goal-side relation, not just say that the construction is useful.\n"
        "- If multiple new points appear in the hidden target summary, describe whether they are introduced together or in stages and what each stage unlocks.\n"
        "- The wording must sound supportable from the image and visible problem text alone.\n"
    )


def build_write_prompt(record, plan, aux_part, sanitized_rest, injected_prefix_block):
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
        f"Bridge relations to realize in order: {json.dumps(plan.get('bridge_relations', []), ensure_ascii=False)}\n"
        f"Goal-side finish to reach: {plan.get('goal_finish', '')}\n\n"
        "[Injected Prefix Block]\n"
        "The script will prepend the following block exactly before your body. Do not restate these claims; start after them.\n"
        f"{injected_prefix_block}\n\n"
        "[Write Requirements]\n"
        "Write only the body text that comes after the script-supplied prefix block: an anchor sentence with coordinate tags, a full-figure overview sentence, a coordinate-focused prefix built from the approved relation checks, and a visible-relations sentence injected from the approved plan.\n"
        "Do NOT output <thinking>, <point>, or <coord> tags; the script will add the prefix sentences and the coordinate tags itself.\n"
        "The body must satisfy all of the following:\n"
        "1. It should sound supportable from the image and visible problem text alone.\n"
        "2. It should be logically coherent and centered on discovering the auxiliary construction and then checking that the construction can genuinely advance the visible goal.\n"
        "3. Follow this order: bottleneck -> missing helper idea -> final introduction of the new point or staged points -> explicit realization of aux_direct_relations -> bridge_relations -> goal_finish.\n"
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
        "15. Keep the post-aux reasoning faithful to the approved visible_relations, aux_direct_relations, bridge_relations, and goal_finish; do not replace them with a different invented route.\n"
        "16. Do not introduce extra named centers, rotational symmetries, square/parallelogram claims, or triangle-similarity claims unless the approved plan already states them and the immediate aux step really supports them.\n"
        "17. Reuse the approved visible_relations when connecting the new point back to the old figure, rather than inventing fresh structural claims.\n"
        "18. Stay impersonal. Do not write in the first person.\n"
        "19. The very first sentence of your body should state the bottleneck or goal-side obstacle. Do not spend the first sentence re-describing triangle abc, the midpoint layout, or the visible givens already covered by the injected prefix block.\n"
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


def run_plan_stage(stage_name, messages, model_name, point_coords, visible_goal, aux_part, coordinate_candidates, max_retries):
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
                feedback = (
                    "Your previous JSON plan was invalid.\n"
                    f"Validation error: {message}\n"
                    "Return a corrected JSON object that satisfies every schema and quality constraint."
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
        "parsed": None,
        "attempts_used": max_retries,
        "elapsed_seconds": None,
        "error": last_error or "Unknown error",
    }


def run_writer_stage(stage_name, messages, model_name, visible_goal, injected_prefix, max_retries):
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
                feedback = (
                    "Your previous body text was invalid.\n"
                    f"Validation error: {message}\n"
                    "Return a corrected plain-text body that satisfies every format and quality constraint."
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


def generate_thinking(record, image_path: Path, aux_part, sanitized_rest, model_name, max_retries, verbose):
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    coordinate_candidates = build_hidden_coordinate_candidates(point_coords, max_items=64, relax_type_limits=True)
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
