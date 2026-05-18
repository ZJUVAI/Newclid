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
    from .run_artifacts import (
        build_input_file_metadata,
        build_dataset_output_record,
        build_item_audit_record,
        build_item_record,
        build_missing_image_item_record,
        build_run_config,
        build_run_summary,
        build_sampled_input_record,
        build_semantic_audit_stub,
    )
    from .geometry_text import (
        PROBLEM_BODY_RE,
        align_bridge_steps_to_hidden_route,
        build_aux_direct_consequences,
        build_aux_keyword_expectations,
        build_canonical_construction,
        build_hidden_aux_brief,
        build_multi_aux_instruction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_aux_point_scope,
        extract_point_mentions,
        extract_problem_goal,
        extract_visible_point_names,
        goal_keyword_hints,
        infer_relation_type_from_text,
        normalize_point_case,
        normalize_relation_surface,
        parse_aux_clauses,
        parse_goal_expression,
        prioritize_visible_relations_for_route,
        relation_duplicates_earlier_support,
        relation_keyword_present,
        relation_text_keywords,
        relations_semantically_match,
        select_support_relations_for_step,
        split_formal_relation_chain,
        summarize_aux_clause,
    )
    from .prompt_builders import (
        build_plan_prompt as build_plan_prompt_text,
        build_plan_retry_feedback,
        build_write_prompt as build_write_prompt_text,
        build_writer_retry_feedback,
    )
    from .writer_contracts import (
        anonymize_new_point_mentions,
        build_injected_prefix_block,
        build_instruction_text,
        build_plan_coverage_targets,
        build_prefix_coverage_notes,
        build_prefix_reuse_guidance,
        build_writer_bridge_contracts,
        build_writer_handoff,
        build_writer_sentence_blueprints,
        build_writer_sentence_duties,
        build_bridge_sentence_checklist,
        enrich_bridge_steps_with_coverage_targets,
        enrich_bridge_steps_with_targets,
        join_natural_list,
        build_canonical_bridge_unlock,
    )
except ImportError:  # pragma: no cover - script execution path
    from run_artifacts import (
        build_input_file_metadata,
        build_dataset_output_record,
        build_item_audit_record,
        build_item_record,
        build_missing_image_item_record,
        build_run_config,
        build_run_summary,
        build_sampled_input_record,
        build_semantic_audit_stub,
    )
    from geometry_text import (
        PROBLEM_BODY_RE,
        align_bridge_steps_to_hidden_route,
        build_aux_direct_consequences,
        build_aux_keyword_expectations,
        build_canonical_construction,
        build_hidden_aux_brief,
        build_multi_aux_instruction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_aux_point_scope,
        extract_point_mentions,
        extract_problem_goal,
        extract_visible_point_names,
        goal_keyword_hints,
        infer_relation_type_from_text,
        normalize_point_case,
        normalize_relation_surface,
        parse_aux_clauses,
        parse_goal_expression,
        prioritize_visible_relations_for_route,
        relation_duplicates_earlier_support,
        relation_keyword_present,
        relation_text_keywords,
        relations_semantically_match,
        select_support_relations_for_step,
        split_formal_relation_chain,
        summarize_aux_clause,
    )
    from prompt_builders import (
        build_plan_prompt as build_plan_prompt_text,
        build_plan_retry_feedback,
        build_write_prompt as build_write_prompt_text,
        build_writer_retry_feedback,
    )
    from writer_contracts import (
        anonymize_new_point_mentions,
        build_injected_prefix_block,
        build_instruction_text,
        build_plan_coverage_targets,
        build_prefix_coverage_notes,
        build_prefix_reuse_guidance,
        build_writer_bridge_contracts,
        build_writer_handoff,
        build_writer_sentence_blueprints,
        build_writer_sentence_duties,
        build_bridge_sentence_checklist,
        enrich_bridge_steps_with_coverage_targets,
        enrich_bridge_steps_with_targets,
        join_natural_list,
        build_canonical_bridge_unlock,
    )

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
    re.compile(r"\bcenter of similarity\b", re.IGNORECASE),
    re.compile(r"\bsimilarity center\b", re.IGNORECASE),
    re.compile(r"\bmidpoint propert(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\$[^$]+\$"),
    re.compile(r"`[^`]+`"),
]
POINT_TAG_RE = re.compile(
    r"<point>\s*([a-z]\w*)\s*</point>\s*<coord>\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)</coord>",
    re.IGNORECASE,
)
RAW_POINT_TAG_RE = re.compile(r"<point>\s*([a-z]\w*)\s*</point>", re.IGNORECASE)


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


def backoff_last_bridge_before_goal_finish(cleaned_plan, hidden_route_relations, point_names):
    bridge_steps = cleaned_plan.get("bridge_steps") or []
    goal_finish = cleaned_plan.get("goal_finish", "")
    if not bridge_steps or not goal_finish or not hidden_route_relations:
        return False

    last_step = bridge_steps[-1]
    last_relation = last_step.get("approved_route_relation") or last_step.get("relation", "")
    if not relations_semantically_match(last_relation, goal_finish, point_names):
        return False

    previous_floor = -1
    if len(bridge_steps) >= 2:
        previous_floor = (bridge_steps[-2].get("approved_route_position") or 0) - 1

    candidate_index = (last_step.get("approved_route_position") or 0) - 2
    if candidate_index < 0:
        matched_index = None
        for idx, relation in enumerate(hidden_route_relations):
            if relations_semantically_match(last_relation, relation, point_names):
                matched_index = idx
                break
        candidate_index = matched_index - 1 if matched_index is not None else -1

    available_supports = cleaned_plan.get("visible_relations", []) + cleaned_plan.get("aux_direct_relations", [])
    if len(bridge_steps) >= 2:
        available_supports.extend(
            step.get("relation", "")
            for step in bridge_steps[:-1]
            if isinstance(step, dict) and step.get("relation")
        )

    while candidate_index > previous_floor:
        candidate_relation = normalize_relation_surface(hidden_route_relations[candidate_index])
        if (
            candidate_relation
            and not relations_semantically_match(candidate_relation, goal_finish, point_names)
            and not relation_duplicates_earlier_support(candidate_relation, available_supports, point_names)
        ):
            last_step["relation"] = candidate_relation
            last_step["approved_route_relation"] = candidate_relation
            last_step["approved_route_position"] = candidate_index + 1
            last_step["why_it_helps"] = build_canonical_bridge_unlock(goal_finish, final_step=True)
            cleaned_plan["bridge_relations"] = [
                step.get("relation", "")
                for step in bridge_steps
                if isinstance(step, dict)
            ]
            return True
        candidate_index -= 1
    return False


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
        r"\bcenter of similarity\b",
        r"\bsimilarity center\b",
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


def find_forbidden_symmetry_shorthand(text):
    if not isinstance(text, str):
        return None
    patterns = [
        r"\baxis points?\b",
        r"\baxis of symmetry\b",
        r"\bsymmetry axis\b",
        r"\baxis\b",
        r"\bsymmetr(?:y|ic|ically)\b",
        r"\bmirror\b",
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
        if isinstance(plan.get("bridge_steps"), list) and plan.get("goal_finish"):
            last_step = plan["bridge_steps"][-1] if plan["bridge_steps"] else None
            if isinstance(last_step, dict):
                last_relation = last_step.get("approved_route_relation") or last_step.get("relation", "")
                if relations_semantically_match(last_relation, plan.get("goal_finish", ""), visible_points):
                    issues.append("bridge_goal_finish_duplicate")

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
        return "the clearest visual cues are the midpoint, collinear, equal-length, parallel, or perpendicular relations already visible."
    if len(cleaned_relations) == 1:
        relation_text = cleaned_relations[0]
        return f"the clearest visual cue is that {relation_text}."
    if len(cleaned_relations) == 2:
        relation_text = " and that ".join(cleaned_relations)
        return f"the clearest visual cues are that {relation_text}."
    relation_text = "; ".join(cleaned_relations[:-1]) + f"; and {cleaned_relations[-1]}"
    return f"the clearest visual cues are that {relation_text}."


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
    return f"a helper is needed that {mechanism_text} {goal_phrase}."


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
        if key == "helper_idea":
            ignored_patterns.extend([
                r"\bfacilitate\b",
                r"\bhelp establish\b",
                r"\bnecessary relationships\b",
                r"\bclear relationship\b",
                r"\bessential for proving\b",
                r"\brotational symmetry\b",
                r"\bcenter of symmetry\b",
                r"\bcenter of similarity\b",
                r"\bsimilarity center\b",
                r"\bmidpoint propert(?:y|ies)\b",
            ])
        if key == "coordinate_hints":
            ignored_patterns.extend([
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
        forbidden_symmetry = find_forbidden_symmetry_shorthand(cleaned_value)
        if forbidden_symmetry and key != "coordinate_hints":
            if key == "anchor_relation":
                cleaned_plan[key] = cleaned_value
                continue
            if key == "figure_overview":
                cleaned_plan[key] = cleaned_value
                continue
            if key == "goal_bottleneck":
                cleaned_plan[key] = cleaned_value
                continue
            if key == "helper_idea":
                cleaned_plan[key] = cleaned_value
                continue
            return False, (
                f"{key} must avoid generic symmetry shorthand like '{forbidden_symmetry}' and should spell out "
                "the concrete midpoint, equal-length, parallel, perpendicular, or collinear relations instead"
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

    if (
        find_forbidden_shape_shorthand(cleaned_plan["anchor_relation"])
        or find_forbidden_center_shorthand(cleaned_plan["anchor_relation"])
        or find_forbidden_symmetry_shorthand(cleaned_plan["anchor_relation"])
    ):
        cleaned_plan["anchor_relation"] = build_canonical_anchor_relation(
            cleaned_plan["anchor_points"],
            cleaned_plan["visible_relations"],
        )
    if (
        find_forbidden_shape_shorthand(cleaned_plan["figure_overview"])
        or find_forbidden_center_shorthand(cleaned_plan["figure_overview"])
        or find_forbidden_symmetry_shorthand(cleaned_plan["figure_overview"])
    ):
        cleaned_plan["figure_overview"] = build_canonical_figure_overview(
            cleaned_plan["anchor_points"],
            cleaned_plan["visible_relations"],
            cleaned_plan["coordinate_relations"],
            visible_points,
        )
    if (
        find_forbidden_shape_shorthand(cleaned_plan["goal_bottleneck"])
        or find_forbidden_center_shorthand(cleaned_plan["goal_bottleneck"])
        or find_forbidden_symmetry_shorthand(cleaned_plan["goal_bottleneck"])
    ):
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
            "center of similarity",
            "similarity center",
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
    ) or find_forbidden_shape_shorthand(cleaned_plan["helper_idea"]) or find_forbidden_center_shorthand(cleaned_plan["helper_idea"]) or find_forbidden_symmetry_shorthand(cleaned_plan["helper_idea"]):
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
                r"\brotational symmetry\b",
                r"\bcenter of symmetry\b",
                r"\bcenter of similarity\b",
                r"\bsimilarity center\b",
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
    cleaned_plan["visible_relations"] = prioritize_visible_relations_for_route(
        cleaned_plan["visible_relations"],
        visible_premise_summaries,
        cleaned_plan["bridge_relations"] + [cleaned_plan["goal_finish"]],
        visible_points,
        min_len=2,
        max_len=4,
    )

    relation_mentions = extract_point_mentions(" ".join(cleaned_plan["coordinate_relations"]), visible_points)
    if len(relation_mentions) < 3:
        return False, "coordinate_relations should collectively cover at least three visible points", None

    canonical_coordinate_hint = build_canonical_coordinate_hint(cleaned_plan["coordinate_relations"])
    coordinate_hint_lower = cleaned_plan["coordinate_hints"].lower()
    if (
        not relation_keyword_present(cleaned_plan["coordinate_hints"])
        or re.search(r"\bsymmetr(?:y|ic)\b|\brotat(?:e|es|ed|ing|ion|ional)\b", cleaned_plan["coordinate_hints"], re.IGNORECASE)
        or re.search(r"\bmidpoint propert(?:y|ies)\b", cleaned_plan["coordinate_hints"], re.IGNORECASE)
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
            cleaned_plan["bridge_relations"] = [
                step.get("relation", "")
                for step in cleaned_plan["bridge_steps"]
            ]
            backoff_last_bridge_before_goal_finish(
                cleaned_plan,
                hidden_route_relations,
                known_points,
            )

    if cleaned_plan["bridge_steps"]:
        last_bridge_relation = (
            cleaned_plan["bridge_steps"][-1].get("approved_route_relation")
            or cleaned_plan["bridge_steps"][-1].get("relation", "")
        )
        if relations_semantically_match(last_bridge_relation, cleaned_goal_finish, known_points):
            return False, (
                "last bridge_steps relation must stay before goal_finish instead of duplicating the final goal-side relation"
            ), None

    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec["points"])
    goal_keywords = goal_keyword_hints(visible_goal)
    cleaned_plan = enrich_bridge_steps_with_targets(cleaned_plan)
    cleaned_plan["coverage_targets"] = build_plan_coverage_targets(
        cleaned_plan,
        visible_goal=visible_goal,
        visible_points=visible_points,
    )
    cleaned_plan = enrich_bridge_steps_with_coverage_targets(
        cleaned_plan,
        visible_points=visible_points,
    )

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
                if (
                    re.search(r"\bmidpoint propert(?:y|ies)\b", why_text, re.IGNORECASE)
                    or find_forbidden_symmetry_shorthand(why_text)
                    or find_forbidden_center_shorthand(why_text)
                ):
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
                if (
                    re.search(r"\bmidpoint propert(?:y|ies)\b", why_text, re.IGNORECASE)
                    or find_forbidden_symmetry_shorthand(why_text)
                    or find_forbidden_center_shorthand(why_text)
                ):
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
        # Reserve room for the injected prefix, the joining space, and a small
        # cleanup margin without throwing away large chunks of the 2200-char budget.
        max_body_len = min(max_body_len, max(200, 2200 - len(injected_prefix) - 12))
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
    forbidden_symmetry = find_forbidden_symmetry_shorthand(body)
    if forbidden_symmetry:
        return False, (
            f"Writer body must avoid generic symmetry shorthand like '{forbidden_symmetry}' and should state the "
            "concrete midpoint, equal-length, parallel, perpendicular, or collinear relations instead"
        )
    sentences = split_into_sentences(body)
    coverage_targets = plan.get("coverage_targets", {}) if isinstance(plan, dict) else {}
    opening_focus_points = [
        point.lower()
        for point in (coverage_targets.get("opening_focus_points") or [])
        if isinstance(point, str) and point.strip()
    ]
    bridge_focus_points = [
        point.lower()
        for point in (coverage_targets.get("bridge_focus_points") or [])
        if isinstance(point, str) and point.strip()
    ]
    coverage_point_pool = []
    for point in (
        (plan.get("anchor_points") or []) if isinstance(plan, dict) else []
    ) + (coverage_targets.get("goal_points") or []) + (coverage_targets.get("non_anchor_points") or []):
        if isinstance(point, str):
            point = point.lower().strip()
            if point and point not in coverage_point_pool:
                coverage_point_pool.append(point)
    if opening_focus_points and sentences:
        sentence_points = extract_point_mentions(sentences[0], coverage_point_pool or opening_focus_points)
        if not (sentence_points & set(opening_focus_points)):
            return False, (
                "Writer opening sentence must mention at least one approved non-anchor opening focus point "
                "from Global Coverage Targets"
            )
    if bridge_focus_points and len(sentences) >= 2:
        sentence_points = extract_point_mentions(sentences[1], coverage_point_pool or bridge_focus_points)
        if not (sentence_points & set(bridge_focus_points)):
            return False, (
                "Writer helper sentence must mention at least one approved non-anchor bridge focus point "
                "from Global Coverage Targets"
            )
    if plan and isinstance(plan.get("bridge_steps"), list):
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
            focus_points = [
                point.lower()
                for point in (step.get("focus_points") or [])
                if isinstance(point, str) and point.strip()
            ]
            if focus_points:
                sentence_points = extract_point_mentions(sentence, coverage_point_pool or focus_points)
                if not (sentence_points & set(focus_points)):
                    return False, (
                        f"Writer sentence for bridge_steps[{idx}] must mention at least one approved bridge focus point "
                        "from its contract"
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


def relation_only_appears_in_preparation_clause(sentence, relation, point_names=None):
    lowered_sentence = (sentence or "").lower()
    local_points = point_names or extract_relation_point_names(relation)
    preparation_markers = [
        "which prepares",
        "this prepares",
        "which is required to prove",
        "required to prove",
        "to prove",
    ]
    for marker in preparation_markers:
        marker_idx = lowered_sentence.find(marker)
        if marker_idx < 0:
            continue
        prefix = sentence[:marker_idx]
        suffix = sentence[marker_idx:]
        if not relation_mentioned_in_text(suffix, relation):
            if not (local_points and relations_semantically_match(suffix, relation, local_points)):
                continue
        if (
            relation_mentioned_in_text(prefix, relation)
            and relation_has_sufficient_point_coverage(prefix, relation, point_names=local_points)
        ):
            return False
        if (
            local_points
            and relations_semantically_match(prefix, relation, local_points)
            and relation_has_sufficient_point_coverage(prefix, relation, point_names=local_points)
        ):
            return False
        return True
    return False


def relation_has_sufficient_point_coverage(sentence, relation, point_names=None):
    local_points = point_names or extract_relation_point_names(relation)
    if not local_points:
        return False
    mentioned_points = extract_point_mentions(sentence, local_points)
    keywords = relation_text_keywords(relation)
    if {"collinear", "midpoint", "circle"} & keywords:
        return len(mentioned_points) >= 3
    if {"parallel", "perpendicular", "angle", "ratio", "similar"} & keywords:
        return len(mentioned_points) >= 4
    if "equal" in keywords:
        return len(mentioned_points) >= 3
    return len(mentioned_points) >= min(3, len(local_points))


def bridge_step_relation_realized(sentence, step):
    if not isinstance(step, dict):
        return False
    relation_candidates = []
    for key in ["relation", "approved_route_relation"]:
        relation = step.get(key, "")
        if isinstance(relation, str) and relation.strip() and relation not in relation_candidates:
            relation_candidates.append(relation)
    for relation in relation_candidates:
        local_points = extract_relation_point_names(relation)
        if relation_mentioned_in_text(sentence, relation):
            if relation_only_appears_in_preparation_clause(sentence, relation, point_names=local_points):
                continue
            if not relation_has_sufficient_point_coverage(sentence, relation, point_names=local_points):
                continue
            return True
        if local_points and relations_semantically_match(sentence, relation, local_points):
            if relation_only_appears_in_preparation_clause(sentence, relation, point_names=local_points):
                continue
            if not relation_has_sufficient_point_coverage(sentence, relation, point_names=local_points):
                continue
            return True
    return False


def build_plan_prompt(record, aux_part, sanitized_rest):
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    proof_guidance_payload = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    return build_plan_prompt_text(
        record,
        aux_part,
        sanitized_rest,
        point_coords=point_coords,
        coordinate_hints=build_hidden_coordinate_hints(point_coords),
        coordinate_guidance=build_hidden_coordinate_guidance(point_coords),
        visible_premise_summaries=build_visible_premise_summaries(record),
        proof_guidance_payload=proof_guidance_payload,
    )


def build_write_prompt(record, plan, aux_part, sanitized_rest, injected_prefix_block):
    visible_goal = extract_problem_goal(record)
    proof_guidance_payload = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    return build_write_prompt_text(
        record,
        plan,
        aux_part,
        injected_prefix_block=injected_prefix_block,
        proof_guidance_payload=proof_guidance_payload,
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
        run_metadata = dict(run_metadata)
        run_metadata.update(build_input_file_metadata(input_path))
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
            build_sampled_input_record(
                sample_order=idx,
                input_index=record["_source_index"],
                image_path=record.get("image_path", ""),
                llm_input_renamed=record.get("llm_input_renamed", ""),
                aux_part=record["_aux_part"],
                point_coords_grid=record.get("point_coords_grid", {}),
            )
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
                "item_record": build_missing_image_item_record(
                    sample_order=sample_order,
                    input_index=record["_source_index"],
                    image_path=str(image_path),
                    source_audit=source_audit,
                    error=f"Image not found: {image_path}",
                ),
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
        visible_goal = extract_problem_goal(record)
        goal_type = parse_goal_expression(visible_goal).get("predicate") or None
        aux_new_points = extract_aux_new_points(aux_part)
        if len(aux_new_points) == 1:
            aux_type = "single_point"
        elif len(aux_new_points) > 1:
            aux_type = "multi_point"
        else:
            aux_type = None
        thinking = generation["thinking"]
        result_data = None
        generation_audit = audit_generation_quality(record, generation, aux_part)

        if generation["success"] and thinking:
            result_data = build_dataset_output_record(
                sample_order=sample_order,
                instruction=build_instruction_text(),
                public_problem=public_problem,
                thinking=thinking,
                aux_part=aux_part,
                image_path=record.get("image_path", ""),
            )

        item_record = build_item_record(
            sample_order=sample_order,
            input_index=record["_source_index"],
            image_path=str(image_path),
            public_problem=public_problem,
            aux_part=aux_part,
            goal_type=goal_type,
            aux_type=aux_type,
            hidden_rest_sanitized=record["_sanitized_rest"],
            point_coords_grid=record.get("point_coords_grid", {}),
            source_audit=source_audit,
            generation_audit=generation_audit,
            generation=generation,
        )
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
    semantic_audit_records = [build_semantic_audit_stub(item) for item in item_records]
    summary = build_run_summary(
        input_jsonl=str(input_path),
        total_candidates_with_aux=len(all_aux_records),
        sampled_items=len(selected),
        item_records=item_records,
        semantic_audit_records=semantic_audit_records,
        source_audit_issue_items=source_audit_issue_items,
        generation_audit_issue_items=generation_audit_issue_items,
        num_workers=num_workers,
        max_retries_per_stage=max_retries,
        model_name=model_name,
        output_jsonl=output_jsonl,
        artifacts_dir=run_dir,
        runtime_seconds=time.time() - start_time,
    )
    write_json(run_dir / "summary.json", summary)
    write_jsonl(
        run_dir / "item_audits.jsonl",
        [build_item_audit_record(item) for item in item_records],
    )
    write_jsonl(run_dir / "semantic_audits.jsonl", semantic_audit_records)
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
    run_metadata = build_run_config(
        args_dict=args_dict,
        output_jsonl=args.output,
        run_dir=run_dir,
        model_name=args.model_name,
        script_path=__file__,
        cwd=os.getcwd(),
        repo_root=REPO_ROOT,
        default_input_jsonl=str(DEFAULT_INPUT_JSONL),
        api_base_url=os.getenv("ZJUVAI_BASE_URL", "https://api.zjuqx.cn/v1"),
        api_timeout_seconds=DEFAULT_API_TIMEOUT_SECONDS,
        api_call_retries=DEFAULT_API_CALL_RETRIES,
        api_retry_backoff_seconds=DEFAULT_API_RETRY_BACKOFF_SECONDS,
    )

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
