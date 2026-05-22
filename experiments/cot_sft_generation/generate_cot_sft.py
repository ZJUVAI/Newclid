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
    from .audits import (
        audit_generation_quality,
        audit_source_record,
        bridge_step_relation_realized,
        build_visible_premise_summaries,
        select_visible_formal_facts,
        count_support_relation_mentions,
        coordinate_relation_matches_candidate,
        count_relation_mentions,
        extract_relation_point_names,
        flatten_bridge_relations,
        get_point_coords,
        has_long_ngram_overlap,
        relation_has_sufficient_point_coverage,
        relation_only_appears_in_preparation_clause,
        relation_semantically_mentioned_in_sentence,
        relation_mentioned_in_text,
        split_into_sentences,
        validate_aux_step_scope,
    )
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
        build_canonical_coordinate_hint,
        build_hidden_aux_brief,
        build_hidden_coordinate_candidates,
        build_hidden_coordinate_guidance,
        build_hidden_coordinate_hints,
        build_multi_aux_instruction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_aux_point_scope,
        extract_high_level_structure_markers,
        extract_point_mentions,
        extract_relation_segment_tokens,
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
        score_support_relation,
        select_support_relations_for_step,
        split_formal_relation_chain,
        summarize_aux_clause,
    )
    from .prompt_builders import (
        build_dossier_critic_prompt as build_dossier_critic_prompt_text,
        build_dossier_plan_prompt as build_dossier_plan_prompt_text,
        build_dossier_plan_retry_feedback,
        build_dossier_write_prompt as build_dossier_write_prompt_text,
        build_dossier_writer_retry_feedback,
        build_plan_prompt as build_plan_prompt_text,
        build_plan_critic_prompt as build_plan_critic_prompt_text,
        build_plan_retry_feedback,
        build_raw_plan_retry_feedback,
        build_raw_record_plan_prompt,
        build_write_prompt as build_write_prompt_text,
        build_writer_retry_feedback,
    )
    from .writer_contracts import (
        build_coordinate_derivation_block,
        build_instruction_text,
        build_writer_handoff,
        join_natural_list,
        render_coordinate_derivation_snippet,
    )
except ImportError:  # pragma: no cover - script execution path
    from audits import (
        audit_generation_quality,
        audit_source_record,
        bridge_step_relation_realized,
        build_visible_premise_summaries,
        select_visible_formal_facts,
        count_support_relation_mentions,
        coordinate_relation_matches_candidate,
        count_relation_mentions,
        extract_relation_point_names,
        flatten_bridge_relations,
        get_point_coords,
        has_long_ngram_overlap,
        relation_has_sufficient_point_coverage,
        relation_only_appears_in_preparation_clause,
        relation_semantically_mentioned_in_sentence,
        relation_mentioned_in_text,
        split_into_sentences,
        validate_aux_step_scope,
    )
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
        build_canonical_coordinate_hint,
        build_hidden_aux_brief,
        build_hidden_coordinate_candidates,
        build_hidden_coordinate_guidance,
        build_hidden_coordinate_hints,
        build_multi_aux_instruction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_aux_point_scope,
        extract_high_level_structure_markers,
        extract_point_mentions,
        extract_relation_segment_tokens,
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
        score_support_relation,
        select_support_relations_for_step,
        split_formal_relation_chain,
        summarize_aux_clause,
    )
    from prompt_builders import (
        build_dossier_critic_prompt as build_dossier_critic_prompt_text,
        build_dossier_plan_prompt as build_dossier_plan_prompt_text,
        build_dossier_plan_retry_feedback,
        build_dossier_write_prompt as build_dossier_write_prompt_text,
        build_dossier_writer_retry_feedback,
        build_plan_prompt as build_plan_prompt_text,
        build_plan_critic_prompt as build_plan_critic_prompt_text,
        build_plan_retry_feedback,
        build_raw_plan_retry_feedback,
        build_raw_record_plan_prompt,
        build_write_prompt as build_write_prompt_text,
        build_writer_retry_feedback,
    )
    from writer_contracts import (
        build_coordinate_derivation_block,
        build_instruction_text,
        build_writer_handoff,
        join_natural_list,
        render_coordinate_derivation_snippet,
    )

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised in bare environments
    OpenAI = None

logger = logging.getLogger(__name__)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_INPUT_JSONL = REPO_ROOT / "datasets/20260512/geometry_clauses10_samples100k_inverted_fl_points_only.jsonl"
DEFAULT_MODEL_NAME = os.getenv("ZJUVAI_MODEL_NAME", "qwen/qwen2.5-vl-72b-instruct")
DEFAULT_FALLBACK_MODELS = [
    model_name
    for model_name in (
        os.getenv("ZJUVAI_FALLBACK_MODELS", "gpt-4.1-mini,gpt-4o-mini").split(",")
    )
    if model_name.strip()
]
DEFAULT_API_TIMEOUT_SECONDS = float(os.getenv("ZJUVAI_TIMEOUT_SECONDS", "120"))
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
    re.compile(r"\bcoordinate table\b", re.IGNORECASE),
    re.compile(r"\brotational symmetry\b", re.IGNORECASE),
    re.compile(r"\bcenter of symmetry\b", re.IGNORECASE),
    re.compile(r"\bcenter of similarity\b", re.IGNORECASE),
    re.compile(r"\bsimilarity center\b", re.IGNORECASE),
    re.compile(r"\bmidpoint propert(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\$[^$]+\$"),
    re.compile(r"`[^`]+`"),
]
DOSSIER_WRITER_SEMANTIC_PENALTY_PATTERNS = [
    re.compile(r"\bmoving us closer to the goal\b", re.IGNORECASE),
    re.compile(r"\bthis construction allows\b", re.IGNORECASE),
    re.compile(r"\bfacilitates?\b", re.IGNORECASE),
    re.compile(r"\bbridging the necessary\b", re.IGNORECASE),
    re.compile(r"\bprovides? the necessary bridge\b", re.IGNORECASE),
    re.compile(r"\bachieving the target relation\b", re.IGNORECASE),
    re.compile(r"\bthis completes the route to the visible goal\b", re.IGNORECASE),
]
INTERNAL_REASONING_REF_RE = re.compile(
    r"\b(?:visible_facts|image_scan|coordinate_checks|aux_immediate_effects|bridge_chain|goal_closure|"
    r"bridge_steps|selected_text_fact_ids|selected_coordinate_candidate_ids|coordinate_derivations|"
    r"text_facts_used)\[\d+\]",
    re.IGNORECASE,
)


def find_internal_reasoning_ref(text: str):
    if not isinstance(text, str) or not text.strip():
        return None
    return INTERNAL_REASONING_REF_RE.search(text)
POINT_TAG_RE = re.compile(
    r"<point>\s*([a-z]\w*)\s*</point>\s*<coord>\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)</coord>",
    re.IGNORECASE,
)
RAW_POINT_TAG_RE = re.compile(r"<point>\s*([a-z]\w*)\s*</point>", re.IGNORECASE)
INLINE_POINT_COORD_RE = re.compile(
    r"\b([a-z]\w*)\s*=\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)",
    re.IGNORECASE,
)
RAW_PLAN_SUPPORT_REF_RE = re.compile(
    r"^(text_facts_used|image_observations|coordinate_derivations|bridge_steps)\[(\d+)\]$",
    re.IGNORECASE,
)
DOSSIER_SUPPORT_REF_RE = re.compile(
    r"^(visible_facts|image_scan|coordinate_checks|aux_immediate_effects|bridge_chain)\[(\d+)\]$",
    re.IGNORECASE,
)


def configure_logging(log_path=None):
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
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
CLIENT_BASE_URL = os.getenv("ZJUVAI_BASE_URL", "https://api.zjuqx.cn/v1")
CLIENT_TIMEOUT_SECONDS = DEFAULT_API_TIMEOUT_SECONDS


def configure_client(base_url=None, timeout_seconds=None):
    global client, CLIENT_BASE_URL, CLIENT_TIMEOUT_SECONDS
    if base_url is not None:
        CLIENT_BASE_URL = base_url
    if timeout_seconds is not None:
        CLIENT_TIMEOUT_SECONDS = timeout_seconds
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
        base_url=CLIENT_BASE_URL,
        timeout=CLIENT_TIMEOUT_SECONDS,
    )
    return client


def normalize_model_name_list(raw_models):
    if raw_models is None:
        return []
    if isinstance(raw_models, str):
        raw_items = raw_models.split(",")
    else:
        raw_items = raw_models
    normalized = []
    seen = set()
    for item in raw_items:
        if not isinstance(item, str):
            continue
        model_name = item.strip()
        if not model_name or model_name in seen:
            continue
        normalized.append(model_name)
        seen.add(model_name)
    return normalized


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


def validate_coord_tags(thinking_text: str, point_coords, max_tags=4):
    tagged_points = POINT_TAG_RE.findall(thinking_text)
    if not tagged_points:
        return False, "Missing any <point>...</point><coord>(x,y)</coord> tags"
    if len(tagged_points) > max_tags:
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


def validate_inline_point_coordinates(thinking_text: str, point_coords):
    seen = {}
    for point_name, x_str, y_str in INLINE_POINT_COORD_RE.findall(thinking_text):
        point_name = point_name.lower()
        x_val = int(x_str)
        y_val = int(y_str)
        if point_name not in point_coords:
            return False, f"Inline coordinate uses non-visible point '{point_name}'"
        expected_x, expected_y = point_coords[point_name]
        if (x_val, y_val) != (expected_x, expected_y):
            return False, (
                f"Inline coordinate mismatch for point '{point_name}': "
                f"expected ({expected_x}, {expected_y}), got ({x_val}, {y_val})"
            )
        if point_name in seen and seen[point_name] != (x_val, y_val):
            return False, f"Inconsistent repeated inline coordinates for point '{point_name}'"
        seen[point_name] = (x_val, y_val)
    return True, "Inline coordinates valid"


def validate_thinking_response(
    output_text: str,
    point_coords,
    require_coord_tags=False,
    max_total_len=2200,
    max_coord_tags=4,
):
    if not output_text or not output_text.strip():
        return False, "Output is empty"

    stripped = output_text.strip()
    match = re.fullmatch(r"<thinking>(.*?)</thinking>", stripped, re.DOTALL)
    if not match:
        return False, "Output must be exactly one <thinking>...</thinking> block"

    thinking_text = match.group(1).strip()
    if len(thinking_text) < 80:
        return False, f"<thinking> content too short ({len(thinking_text)} chars, minimum 80)"
    if len(thinking_text) > max_total_len:
        return False, f"<thinking> content too long ({len(thinking_text)} chars, maximum {max_total_len})"

    internal_ref_hit = find_internal_reasoning_ref(thinking_text)
    if internal_ref_hit:
        return False, f"Internal planning reference detected: {internal_ref_hit.group(0)}"

    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(thinking_text)
        if hit:
            return False, f"Forbidden leakage pattern detected: {hit.group(0)}"

    if require_coord_tags and point_coords:
        ok, message = validate_coord_tags(thinking_text, point_coords, max_tags=max_coord_tags)
        if not ok:
            return False, message

    if point_coords:
        ok, message = validate_inline_point_coordinates(thinking_text, point_coords)
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


def build_visible_text_facts(record, max_items=12):
    point_coords = get_point_coords(record)
    visible_points = extract_visible_point_names(point_coords)
    facts = []
    for fact in select_visible_formal_facts(record, max_items=max_items):
        relation = normalize_relation_surface((fact.get("summary") or "").strip())
        if not relation:
            continue
        facts.append(
            {
                "id": f"T{len(facts) + 1}",
                "relation": relation,
                "predicate": fact.get("predicate", ""),
                "points": sorted(extract_point_mentions(relation, visible_points)),
                "source": "public_problem_text",
            }
        )
    return facts


def build_coordinate_candidate_witness(candidate, point_coords):
    if not isinstance(candidate, dict):
        return {}
    relation_type = candidate.get("relation_type")
    points = [point for point in candidate.get("points", []) if point in point_coords]
    if relation_type in {"parallel", "perpendicular", "equal_length"} and len(points) >= 4:
        a, b, c, d = points[:4]
        x1, y1 = point_coords[a]
        x2, y2 = point_coords[b]
        x3, y3 = point_coords[c]
        x4, y4 = point_coords[d]
        v1 = [x2 - x1, y2 - y1]
        v2 = [x4 - x3, y4 - y3]
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        len_sq_1 = v1[0] * v1[0] + v1[1] * v1[1]
        len_sq_2 = v2[0] * v2[0] + v2[1] * v2[1]
        return {
            "vector_1": v1,
            "vector_2": v2,
            "cross": cross,
            "dot": dot,
            "length_sq_1": len_sq_1,
            "length_sq_2": len_sq_2,
        }
    if relation_type == "midpoint" and len(points) >= 3:
        mid, p1, p2 = points[:3]
        xm, ym = point_coords[mid]
        x1, y1 = point_coords[p1]
        x2, y2 = point_coords[p2]
        midpoint = [(x1 + x2) / 2, (y1 + y2) / 2]
        midpoint_gap = ((xm - midpoint[0]) ** 2 + (ym - midpoint[1]) ** 2) ** 0.5
        area2 = abs((x2 - x1) * (ym - y1) - (y2 - y1) * (xm - x1))
        seg_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1.0
        return {
            "midpoint_of_endpoints": midpoint,
            "midpoint_gap": round(midpoint_gap, 4),
            "line_residual": round(area2 / seg_len, 4),
        }
    if relation_type == "collinear" and len(points) >= 3:
        p1, p2, p3 = points[:3]
        x1, y1 = point_coords[p1]
        x2, y2 = point_coords[p2]
        x3, y3 = point_coords[p3]
        area2 = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
        return {
            "area_residual": round(area2, 4),
        }
    return {}


def build_canonical_coordinate_relation(candidate):
    if not isinstance(candidate, dict):
        return ""
    relation_type = str(candidate.get("relation_type") or "").strip().lower()
    points = [
        str(point).lower()
        for point in (candidate.get("points") or [])
        if isinstance(point, str) and point.strip()
    ]
    if relation_type == "parallel" and len(points) >= 4:
        return f"line {points[0]}{points[1]} is parallel to line {points[2]}{points[3]}"
    if relation_type == "perpendicular" and len(points) >= 4:
        return f"line {points[0]}{points[1]} is perpendicular to line {points[2]}{points[3]}"
    if relation_type == "equal_length" and len(points) >= 4:
        return f"{points[0]}{points[1]} equals {points[2]}{points[3]}"
    if relation_type == "midpoint" and len(points) >= 3:
        return f"{points[0]} is the midpoint of {points[1]}{points[2]}"
    if relation_type == "collinear" and len(points) >= 3:
        return f"{points[0]}, {points[1]}, and {points[2]} are collinear"
    return normalize_relation_surface((candidate.get("summary") or "").strip())


def build_image_coordinate_candidates(point_coords, visible_text_facts, max_items=10):
    raw_candidates = build_hidden_coordinate_candidates(
        point_coords,
        max_items=max_items * 4,
        relax_type_limits=True,
    )
    visible_points = extract_visible_point_names(point_coords)
    allowed_types = {"parallel", "perpendicular", "equal_length", "midpoint", "collinear"}
    items = []
    for raw_candidate in raw_candidates:
        relation_type = raw_candidate.get("relation_type")
        if relation_type not in allowed_types:
            continue
        relation = normalize_relation_surface((raw_candidate.get("summary") or "").strip())
        if not relation:
            continue
        overlaps_text = any(
            relations_semantically_match(relation, fact.get("relation", ""), visible_points)
            for fact in visible_text_facts
        )
        items.append(
            {
                "id": f"C{len(items) + 1}",
                "relation": relation,
                "relation_type": relation_type,
                "points": [point for point in raw_candidate.get("points", []) if point in point_coords],
                "score": raw_candidate.get("score"),
                "overlaps_text": overlaps_text,
                "witness": build_coordinate_candidate_witness(raw_candidate, point_coords),
            }
        )
        if len(items) >= max_items:
            break
    return items


def relation_matches_hint_bucket(relation_text, bucket_relations, point_names):
    if not isinstance(relation_text, str) or not relation_text.strip():
        return False
    for bucket_relation in bucket_relations or []:
        if relations_semantically_match(relation_text, bucket_relation, point_names):
            return True
        shared_points = extract_point_mentions(relation_text, point_names) & extract_point_mentions(bucket_relation, point_names)
        shared_keywords = relation_text_keywords(relation_text) & relation_text_keywords(bucket_relation)
        if len(shared_points) >= 2 and shared_keywords:
            return True
    return False


def resolve_support_refs(step, fact_lookup, candidate_lookup, prior_bridge_lookup):
    dependencies = []
    for ref in step.get("support_refs", []) or []:
        if ref in fact_lookup:
            dependencies.append(fact_lookup[ref]["relation"])
        elif ref in candidate_lookup:
            dependencies.append(candidate_lookup[ref]["relation"])
        elif ref in prior_bridge_lookup:
            dependencies.append(prior_bridge_lookup[ref])
    return dependencies


def render_plan_coordinate_derivations(plan, point_coords):
    rendered = []
    for derivation in plan.get("coordinate_derivations", []) if isinstance(plan, dict) else []:
        if not isinstance(derivation, dict):
            continue
        snippet = render_coordinate_derivation_snippet(derivation, point_coords)
        item = dict(derivation)
        item["rendered_text"] = snippet
        rendered.append(item)
    return rendered


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


def build_canonical_bridge_unlock(next_target_relation, final_step=False):
    normalized_next = normalize_relation_surface(next_target_relation or "").strip()
    lowered = normalized_next.lower()
    if final_step:
        if "ratio" in lowered:
            return "this puts the needed segment comparison in place right before the final ratio closes."
        if "angle" in lowered:
            return "this puts the needed direction comparison in place right before the final angle closes."
        if "similar" in lowered:
            return "this supplies the last correspondence needed before the final similarity closes."
        if "congruent" in lowered:
            return "this supplies the last correspondence needed before the final congruence closes."
        if any(token in lowered for token in [" equals ", "equal"]):
            return "this puts the needed equality in place right before the final goal closes."
        return "this sets up the last direct bridge before the final goal relation closes."

    if "ratio" in lowered:
        return "this creates one intermediate segment comparison that the next ratio step can reuse."
    if "angle" in lowered:
        return "this creates one intermediate direction comparison that the next angle step can reuse."
    if "similar" in lowered:
        return "this adds one correspondence that can be reused in the next triangle-comparison step."
    if "congruent" in lowered:
        return "this adds one correspondence that can be reused in the next congruence step."
    if any(token in lowered for token in [" equals ", "equal"]):
        return "this creates one intermediate equality that the next step can reuse."
    return "this prepares one smaller bridge that the next step can reuse."


def relation_contains_forbidden_thinking_pattern(text):
    normalized_text = normalize_relation_surface(text or "").strip()
    if not normalized_text:
        return True
    return any(pattern.search(normalized_text) for pattern in FORBIDDEN_THINKING_PATTERNS)


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
        surface_item = cleaned_item.strip()
        normalized_item = normalize_relation_surface(surface_item)
        if field_name == "coordinate_relations" and re.search(r"\bsymmetr(?:y|ic)\b|\brotation(?:al)?\b", normalized_item, re.IGNORECASE):
            return False, (
                f"{field_name}[{idx}] should name concrete equal/parallel/perpendicular/midpoint/collinear cues, "
                "not high-level symmetry or rotation claims"
            ), None
        if not relation_keyword_present(normalized_item):
            return False, f"{field_name}[{idx}] must mention a concrete geometric relation", None
        mentioned = extract_point_mentions(normalized_item, visible_points)
        if len(mentioned) < 2:
            return False, f"{field_name}[{idx}] must mention at least two visible points", None
        cleaned.append(surface_item if field_name == "coordinate_relations" else normalized_item)
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
            candidate = fallback_queue.pop(0).strip()
            lowered = normalize_relation_surface(candidate).lower()
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
            surface_item = cleaned_item.strip()
            normalized_item = normalize_relation_surface(surface_item)
            mentioned = extract_point_mentions(normalized_item, visible_points)
            if (
                relation_keyword_present(normalized_item)
                and len(mentioned) >= 2
                and any(coordinate_relation_matches_candidate(normalized_item, candidate) for candidate in candidates)
            ):
                lowered = normalized_item.lower()
                if lowered not in used_lower:
                    cleaned.append(surface_item)
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


def canonicalize_observation_relations(items, visible_points, coordinate_candidates, max_len=4):
    if not isinstance(items, list):
        items = []
    cleaned = []
    candidate_map = {}
    for candidate in coordinate_candidates or []:
        if not isinstance(candidate, dict):
            continue
        summary = normalize_relation_surface((candidate.get("summary") or "")).strip()
        if not summary:
            continue
        candidate_map[summary.lower()] = candidate

    for raw_item in items[:max_len]:
        if not isinstance(raw_item, dict):
            continue
        relation = normalize_relation_surface((raw_item.get("relation") or raw_item.get("visual_surface") or "")).strip()
        if not relation:
            continue
        candidate = candidate_map.get(relation.lower())
        if not candidate:
            continue
        points = [
            point.lower()
            for point in (raw_item.get("points") or candidate.get("points") or [])
            if isinstance(point, str) and point.strip() and point.lower() in visible_points
        ]
        if len(points) < 2:
            points = sorted(extract_point_mentions(relation, visible_points))
        if len(points) < 2:
            continue
        evidence_mode = (raw_item.get("evidence_mode") or "hybrid").strip().lower()
        if evidence_mode not in {"visual_only", "coordinate_only", "hybrid"}:
            evidence_mode = "hybrid"
        verification_role = (raw_item.get("verification_role") or "seed").strip().lower()
        if verification_role not in {"seed", "verify", "derive"}:
            verification_role = "seed"
        priority_region = (raw_item.get("priority_region") or "mixed").strip().lower()
        if priority_region not in {"goal_side", "bridge_side", "anchor_side", "mixed"}:
            priority_region = "mixed"
        cleaned.append(
            {
                "id": raw_item.get("id") or f"obs_{len(cleaned) + 1}",
                "relation": relation,
                "relation_type": raw_item.get("relation_type") or candidate.get("relation_type") or infer_relation_type_from_text(relation),
                "points": points,
                "evidence_mode": evidence_mode,
                "visual_surface": (raw_item.get("visual_surface") or relation).strip(),
                "coordinate_surface": (raw_item.get("coordinate_surface") or candidate.get("summary") or relation).strip(),
                "verification_role": verification_role,
                "priority_region": priority_region,
            }
        )
    return cleaned[:max_len]


def derive_observation_relations_from_coordinate_relations(coordinate_relations, visible_points, coordinate_candidates, max_len=4):
    derived = []
    candidate_map = {}
    for candidate in coordinate_candidates or []:
        if not isinstance(candidate, dict):
            continue
        summary = normalize_relation_surface((candidate.get("summary") or "")).strip()
        if summary:
            candidate_map[summary.lower()] = candidate
    for relation in coordinate_relations[:max_len]:
        normalized_relation = normalize_relation_surface(relation).strip()
        if not normalized_relation:
            continue
        candidate = candidate_map.get(normalized_relation.lower(), {})
        points = [
            point.lower()
            for point in (candidate.get("points") or [])
            if isinstance(point, str) and point.strip() and point.lower() in visible_points
        ]
        if len(points) < 2:
            points = sorted(extract_point_mentions(normalized_relation, visible_points))
        if len(points) < 2:
            continue
        derived.append(
            {
                "id": f"obs_{len(derived) + 1}",
                "relation": normalized_relation,
                "relation_type": candidate.get("relation_type") or infer_relation_type_from_text(normalized_relation),
                "points": points,
                "evidence_mode": "hybrid",
                "visual_surface": normalized_relation,
                "coordinate_surface": candidate.get("summary") or normalized_relation,
                "verification_role": "seed",
                "priority_region": "mixed",
            }
        )
    return derived[:max_len]


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
    goal_spec = parse_goal_expression(visible_goal)
    effective_max_finish = max_finish
    if (goal_spec.get("predicate") or "").lower() in {"contri", "contrir"}:
        effective_max_finish = max(max_finish, 6)
    if not proof_match:
        return {
            "immediate_aux_consequences": aux_direct[:max_aux],
            "aux_bridge_relations": [],
            "bridge_relations": [],
            "goal_finish_relations": [],
        }

    goal_points = set(goal_spec["points"])
    new_points = {point.lower() for point in extract_aux_new_points(aux_part)}
    raw_clauses = [part.strip() for part in proof_match.group(1).split(";") if part.strip()]
    summaries = []
    for clause_index, clause in enumerate(raw_clauses):
        summary = summarize_aux_clause(clause)
        if not summary:
            continue
        summary = normalize_relation_surface(summary)
        lowered = clause.lower()
        clause_points = set(re.findall(r"\b([a-z]\w*)\b", lowered))
        summaries.append(
            {
                "index": clause_index,
                "summary": summary,
                "points": clause_points,
                "has_new_point": bool(clause_points & new_points),
                "has_goal_point": bool(clause_points & goal_points),
                "keywords": relation_text_keywords(summary),
                "segments": extract_relation_segment_tokens(summary),
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
            if len(finish) >= effective_max_finish:
                break
    if len(finish) < effective_max_finish:
        for item in reversed(summaries):
            text = item["summary"]
            if text in finish:
                continue
            if item["has_goal_point"]:
                finish.append(text)
                if len(finish) >= effective_max_finish:
                    break
    finish.reverse()

    ordered_route_relations = build_ordered_hidden_route_relations(
        summaries,
        immediate_relations=immediate,
        route_relations=aux_bridge + bridge + finish,
    )

    return {
        "immediate_aux_consequences": immediate,
        "aux_bridge_relations": aux_bridge,
        "bridge_relations": bridge,
        "goal_finish_relations": finish,
        "ordered_route_relations": ordered_route_relations,
    }


def build_ordered_hidden_route_relations(summaries, immediate_relations, route_relations, max_extra=4):
    ordered_core = []
    seen_core = set()
    for relation in route_relations or []:
        if not isinstance(relation, str) or not relation.strip():
            continue
        lowered = relation.lower().strip()
        if lowered in seen_core:
            continue
        seen_core.add(lowered)
        ordered_core.append(relation)
    if not ordered_core:
        return []

    immediate_order = []
    seen_immediate = set()
    for relation in immediate_relations or []:
        if not isinstance(relation, str) or not relation.strip():
            continue
        lowered = relation.lower().strip()
        if lowered in seen_immediate:
            continue
        seen_immediate.add(lowered)
        immediate_order.append(relation)

    summary_by_relation = {}
    for item in summaries or []:
        text = item.get("summary", "")
        lowered = text.lower().strip()
        summary_by_relation.setdefault(lowered, item)

    expanded_route = []
    used_relations = set()
    added_extra = 0
    last_route_index = -1

    for relation in ordered_core:
        lowered_relation = relation.lower().strip()
        current_item = summary_by_relation.get(lowered_relation)
        current_index = current_item.get("index", len(summaries) + len(expanded_route)) if current_item else len(summaries) + len(expanded_route)
        if current_index <= last_route_index:
            current_index = last_route_index + 1

        current_keywords = relation_text_keywords(relation)
        current_segments = extract_relation_segment_tokens(relation)
        grounded_segments = set()
        for support in immediate_order + expanded_route:
            grounded_segments.update(extract_relation_segment_tokens(support))

        if current_keywords & {"angle", "ratio", "similar"} and current_segments:
            missing_segments = current_segments - grounded_segments
            while missing_segments and added_extra < max_extra:
                best_item = None
                best_key = None
                for item in summaries or []:
                    candidate_text = item.get("summary", "")
                    candidate_lower = candidate_text.lower().strip()
                    if (
                        not candidate_text
                        or candidate_lower in used_relations
                        or candidate_lower == lowered_relation
                    ):
                        continue
                    candidate_index = item.get("index", -1)
                    if candidate_index >= current_index:
                        continue
                    candidate_segments = item.get("segments") or set()
                    if not candidate_segments or not (candidate_segments & missing_segments):
                        continue
                    candidate_keywords = item.get("keywords") or set()
                    if candidate_keywords & {"ratio", "similar"}:
                        continue
                    if not candidate_keywords & {"collinear", "equal", "parallel", "perpendicular", "angle", "circle"}:
                        continue
                    covered_missing = len(candidate_segments & missing_segments)
                    covered_current = len(candidate_segments & current_segments)
                    distance = current_index - candidate_index
                    key = (
                        covered_missing,
                        covered_current,
                        -distance,
                        -len(candidate_text),
                        candidate_lower,
                    )
                    if best_key is None or key > best_key:
                        best_key = key
                        best_item = item
                if best_item is None:
                    break
                candidate_text = best_item["summary"]
                candidate_lower = candidate_text.lower().strip()
                expanded_route.append(candidate_text)
                used_relations.add(candidate_lower)
                grounded_segments.update(best_item.get("segments") or set())
                missing_segments = current_segments - grounded_segments
                last_route_index = max(last_route_index, best_item.get("index", last_route_index))
                added_extra += 1

        if lowered_relation not in used_relations:
            expanded_route.append(relation)
            used_relations.add(lowered_relation)
        if current_item:
            last_route_index = max(last_route_index, current_item.get("index", last_route_index))

    return expanded_route


def compute_plan_complexity_limits(point_coords, visible_goal="", aux_part=None):
    visible_points = extract_visible_point_names(point_coords or {})
    aux_points = [point.lower() for point in extract_aux_new_points(aux_part or "")]
    goal_spec = parse_goal_expression(visible_goal or "")
    complexity_score = 0
    if len(visible_points) >= 5:
        complexity_score += 1
    if len(aux_points) > 1:
        complexity_score += 1
    if goal_spec.get("predicate") in {"eqratio", "simtri", "contri"}:
        complexity_score += 1

    extended_budget = complexity_score >= 1
    richer_route_budget = complexity_score >= 2 or len(aux_points) > 1
    anchor_min = 3 if len(visible_points) >= 3 else len(visible_points)
    anchor_max = min(5, len(visible_points)) if visible_points else 0
    if not extended_budget:
        anchor_max = min(anchor_max, 4)
    coordinate_coverage_min = 4 if extended_budget and len(visible_points) >= 4 else min(3, len(visible_points))
    return {
        "extended_budget": extended_budget,
        "anchor_min": anchor_min,
        "anchor_max": anchor_max,
        "coordinate_relations_min": 2,
        "coordinate_relations_max": 4 if extended_budget else 3,
        "visible_relations_min": 2,
        "visible_relations_max": 5 if extended_budget else 4,
        "aux_direct_relations_min": 1,
        "aux_direct_relations_max": 4 if richer_route_budget else 3,
        "bridge_steps_min": 2,
        "bridge_steps_max": 5 if richer_route_budget else 4,
        "depends_on_max": 4 if richer_route_budget else 3,
        "coordinate_coverage_min": coordinate_coverage_min,
    }


def compute_writer_body_budget(plan=None, injected_prefix=""):
    anchor_count = len(plan.get("anchor_points") or []) if isinstance(plan, dict) else 0
    coordinate_count = len(plan.get("coordinate_relations") or []) if isinstance(plan, dict) else 0
    aux_direct_count = len(plan.get("aux_direct_relations") or []) if isinstance(plan, dict) else 0
    bridge_count = len(plan.get("bridge_steps") or []) if isinstance(plan, dict) else 0

    total_budget = compute_thinking_total_budget(plan)

    body_budget = 1500
    body_budget += max(0, bridge_count - 4) * 130
    body_budget += max(0, anchor_count - 4) * 70
    body_budget += max(0, coordinate_count - 3) * 60
    body_budget += max(0, aux_direct_count - 3) * 50
    body_budget = min(body_budget, 1900)

    if injected_prefix:
        body_budget = min(body_budget, max(240, total_budget - len(injected_prefix) - 12))
    return body_budget


def normalize_coordinate_render_mode(render_mode, calc_type):
    normalized = str(render_mode or "").strip().lower()
    if normalized == "coordinate":
        return {
            "parallel": "vector",
            "perpendicular": "vector",
            "equal_length": "distance",
            "midpoint": "midpoint",
            "collinear": "area",
        }.get(str(calc_type or "").strip().lower(), normalized)
    return normalized


def compute_thinking_total_budget(plan=None):
    anchor_count = len(plan.get("anchor_points") or []) if isinstance(plan, dict) else 0
    coordinate_count = len(plan.get("coordinate_relations") or []) if isinstance(plan, dict) else 0
    aux_direct_count = len(plan.get("aux_direct_relations") or []) if isinstance(plan, dict) else 0
    bridge_count = len(plan.get("bridge_steps") or []) if isinstance(plan, dict) else 0

    total_budget = 2200
    total_budget += max(0, bridge_count - 4) * 160
    total_budget += max(0, anchor_count - 4) * 90
    total_budget += max(0, coordinate_count - 3) * 80
    total_budget += max(0, aux_direct_count - 3) * 70
    return min(total_budget, 2700)


def choose_required_supports_for_bridge_step(step, point_names, max_supports=2):
    if not isinstance(step, dict):
        return []
    relation_text = step.get("approved_route_relation") or step.get("relation", "")
    if not isinstance(relation_text, str) or not relation_text.strip() or max_supports <= 0:
        return []
    dependencies = [
        dependency
        for dependency in (step.get("depends_on") or [])
        if isinstance(dependency, str) and dependency.strip()
    ]
    if not dependencies:
        return []
    relation_keywords = relation_text_keywords(relation_text)
    relation_points = extract_point_mentions(relation_text, point_names)
    next_target_relation = step.get("next_target_relation", "")

    low_level_relation_families = {"collinear", "midpoint", "equal", "parallel", "perpendicular"}
    exact_semantic_matches = [
        dependency
        for dependency in dependencies
        if relations_semantically_match(dependency, relation_text, point_names)
    ]
    if relation_keywords & low_level_relation_families and exact_semantic_matches:
        exact_semantic_matches = sorted(
            exact_semantic_matches,
            key=lambda dependency: (
                0 if re.search(r"\b(?:look|looks|appear|appears|seem|seems|nearly|midpoint)\b", dependency, re.IGNORECASE) else 1,
                len(dependency),
                dependency.lower(),
            ),
        )
        return exact_semantic_matches[:1]

    selected = []

    def append_supports(items):
        for item in items:
            if item not in selected:
                selected.append(item)
            if len(selected) >= max_supports:
                break

    if "collinear" in relation_keywords:
        collinear_dependencies = [
            dependency
            for dependency in dependencies
            if (
                "collinear" in relation_text_keywords(dependency)
                and len(extract_point_mentions(dependency, point_names) & relation_points) >= 2
            )
        ]
        append_supports(
            sorted(
                collinear_dependencies,
                key=lambda dependency: (
                    -len(extract_point_mentions(dependency, point_names) & relation_points),
                    len(dependency),
                    dependency.lower(),
                ),
            )
        )

    ranked_dependencies = select_support_relations_for_step(
        relation_text,
        dependencies,
        point_names,
        next_target_relation=next_target_relation,
        max_supports=max(len(dependencies), max_supports),
    )
    append_supports(ranked_dependencies)
    append_supports(dependencies)
    return selected[:max_supports]


def compute_bridge_step_min_support_mentions(step):
    if not isinstance(step, dict):
        return 0
    required_supports = [
        dependency
        for dependency in (step.get("required_supports") or [])
        if isinstance(dependency, str) and dependency.strip()
    ]
    if not required_supports:
        return 0
    relation_text = step.get("approved_route_relation") or step.get("relation", "")
    relation_keywords = relation_text_keywords(relation_text)
    if relation_keywords & {"collinear", "similar", "ratio"}:
        return min(2, len(required_supports))
    return 1


def compute_bridge_step_required_support_cap(step):
    if not isinstance(step, dict):
        return 2
    relation_text = step.get("approved_route_relation") or step.get("relation", "")
    relation_keywords = relation_text_keywords(relation_text)
    if relation_keywords & {"similar", "ratio"}:
        return 4 if len(extract_relation_segment_tokens(relation_text)) >= 4 else 3
    if relation_keywords & {"angle"}:
        return 3
    return 2


def rebalance_anchor_points_for_coordinate_coverage(
    anchor_points,
    coordinate_relations,
    visible_points,
    min_anchor_count,
    required_non_anchor_coverage,
):
    normalized_anchor_points = [
        point.lower()
        for point in (anchor_points or [])
        if isinstance(point, str) and point.strip()
    ]
    if required_non_anchor_coverage <= 0 or len(normalized_anchor_points) <= min_anchor_count:
        return normalized_anchor_points

    relation_mentions = [
        extract_point_mentions(relation, visible_points)
        for relation in (coordinate_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    if not relation_mentions:
        return normalized_anchor_points

    all_coordinate_points = set().union(*relation_mentions)

    def compute_non_anchor_mentions(candidate_anchor_points):
        candidate_anchor_set = set(candidate_anchor_points)
        mentions = set()
        for mentioned_points in relation_mentions:
            mentions.update(
                point
                for point in mentioned_points
                if point not in candidate_anchor_set
            )
        return mentions

    best_anchor_points = normalized_anchor_points[:]
    best_non_anchor_mentions = compute_non_anchor_mentions(best_anchor_points)
    while (
        len(best_anchor_points) > min_anchor_count
        and len(best_non_anchor_mentions) < required_non_anchor_coverage
    ):
        best_trial = None
        best_trial_mentions = best_non_anchor_mentions
        best_trial_key = None
        for idx, anchor_point in enumerate(best_anchor_points):
            trial_anchor_points = (
                best_anchor_points[:idx] + best_anchor_points[idx + 1:]
            )
            trial_non_anchor_mentions = compute_non_anchor_mentions(trial_anchor_points)
            trial_key = (
                len(trial_non_anchor_mentions),
                1 if anchor_point in all_coordinate_points else 0,
                idx,
            )
            if best_trial_key is None or trial_key > best_trial_key:
                best_trial_key = trial_key
                best_trial = trial_anchor_points
                best_trial_mentions = trial_non_anchor_mentions
        if best_trial is None or len(best_trial_mentions) <= len(best_non_anchor_mentions):
            break
        best_anchor_points = best_trial
        best_non_anchor_mentions = best_trial_mentions
    return best_anchor_points


def find_unsupported_bridge_relation_segments(step, support_relations):
    if not isinstance(step, dict):
        return []
    relation_text = step.get("approved_route_relation") or step.get("relation", "")
    relation_keywords = relation_text_keywords(relation_text)
    if not relation_keywords & {"angle", "ratio", "similar"}:
        return []
    relation_segments = extract_relation_segment_tokens(relation_text)
    if not relation_segments:
        return []
    grounded_segments = set()
    for support in support_relations or []:
        if isinstance(support, str) and support.strip():
            grounded_segments.update(extract_relation_segment_tokens(support))
    return sorted(relation_segments - grounded_segments)


def find_skipped_prerequisite_route_checkpoint(
    step,
    previous_route_position,
    hidden_route_relations,
    point_names,
    previous_bridge_relation="",
):
    if not isinstance(step, dict):
        return ""
    current_route_position = step.get("approved_route_position")
    if not isinstance(current_route_position, int) or current_route_position <= previous_route_position + 1:
        return ""
    current_relation = step.get("approved_route_relation") or step.get("relation", "")
    current_keywords = relation_text_keywords(current_relation)
    if not current_keywords & {"similar", "ratio"}:
        return ""
    current_points = extract_point_mentions(current_relation, point_names)
    dependency_pool = [
        dependency
        for dependency in (step.get("depends_on") or [])
        if isinstance(dependency, str) and dependency.strip()
    ]
    if previous_bridge_relation:
        dependency_pool.append(previous_bridge_relation)
    skipped_relations = hidden_route_relations[previous_route_position: current_route_position - 1]
    best_candidate = ("", -1, -1)
    for skipped_relation in skipped_relations:
        skipped_keywords = relation_text_keywords(skipped_relation)
        if not skipped_keywords & {"angle", "ratio", "parallel", "perpendicular", "equal", "collinear"}:
            continue
        skipped_points = extract_point_mentions(skipped_relation, point_names)
        shared_points = current_points & skipped_points
        if len(shared_points) < 3:
            continue
        if any(relations_semantically_match(dependency, skipped_relation, point_names) for dependency in dependency_pool):
            continue
        score = (len(shared_points), len(current_keywords & skipped_keywords))
        if score > best_candidate[1:]:
            best_candidate = (skipped_relation, score[0], score[1])
    return best_candidate[0]


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
    limits = compute_plan_complexity_limits(point_coords, visible_goal=visible_goal, aux_part=aux_part)

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
    if not isinstance(anchor_points, list) or not (
        limits["anchor_min"] <= len(anchor_points) <= limits["anchor_max"]
    ):
        return False, (
            f"anchor_points must be a list with {limits['anchor_min']} to {limits['anchor_max']} visible points"
        ), None
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
        min_len=limits["coordinate_relations_min"],
        max_len=limits["coordinate_relations_max"],
    )
    ok, message, cleaned_relations = validate_relation_list(
        coordinate_relations_seed,
        "coordinate_relations",
        visible_points,
        min_len=limits["coordinate_relations_min"],
        max_len=limits["coordinate_relations_max"],
    )
    if not ok:
        return False, message, None
    cleaned_plan["coordinate_relations"] = cleaned_relations
    observation_relations = canonicalize_observation_relations(
        plan.get("observation_relations"),
        visible_points,
        coordinate_candidates,
        max_len=limits["coordinate_relations_max"],
    )
    if not observation_relations:
        observation_relations = derive_observation_relations_from_coordinate_relations(
            cleaned_plan["coordinate_relations"],
            visible_points,
            coordinate_candidates,
            max_len=limits["coordinate_relations_max"],
        )
    cleaned_plan["observation_relations"] = observation_relations

    visible_relations_seed = canonicalize_visible_relations(
        plan.get("visible_relations"),
        visible_points,
        visible_premise_summaries,
        min_len=limits["visible_relations_min"],
        max_len=limits["visible_relations_max"],
        min_chars=5,
    )
    ok, message, cleaned_visible_relations = validate_relation_list(
        visible_relations_seed,
        "visible_relations",
        visible_points,
        min_len=limits["visible_relations_min"],
        max_len=limits["visible_relations_max"],
        min_chars=5,
    )
    if not ok:
        return False, message, None
    cleaned_plan["visible_relations"] = cleaned_visible_relations

    non_anchor_coordinate_coverage_min = min(
        3 if limits["extended_budget"] else 2,
        max(0, len(visible_points) - limits["anchor_min"]),
    )
    rebalanced_anchor_points = rebalance_anchor_points_for_coordinate_coverage(
        normalized_points,
        cleaned_plan["coordinate_relations"],
        visible_points,
        limits["anchor_min"],
        non_anchor_coordinate_coverage_min,
    )
    if rebalanced_anchor_points != normalized_points:
        normalized_points = rebalanced_anchor_points
        cleaned_plan["anchor_points"] = normalized_points
        cleaned_plan["anchor_relation"] = build_canonical_anchor_relation(
            cleaned_plan["anchor_points"],
            cleaned_plan["visible_relations"],
        )
        cleaned_plan["figure_overview"] = build_canonical_figure_overview(
            cleaned_plan["anchor_points"],
            cleaned_plan["visible_relations"],
            cleaned_plan["coordinate_relations"],
            visible_points,
        )

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
        min_len=limits["aux_direct_relations_min"],
        max_len=limits["aux_direct_relations_max"],
    )
    if not (
        limits["aux_direct_relations_min"]
        <= len(aux_direct_relations)
        <= limits["aux_direct_relations_max"]
    ):
        return False, (
            "aux_direct_relations must be a list with "
            f"{limits['aux_direct_relations_min']} to {limits['aux_direct_relations_max']} ordered direct consequences"
        ), None
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
    if isinstance(bridge_steps, list) and len(bridge_steps) > limits["bridge_steps_max"]:
        bridge_steps = bridge_steps[: limits["bridge_steps_max"]]
    if not isinstance(bridge_steps, list) or not (
        limits["bridge_steps_min"] <= len(bridge_steps) <= limits["bridge_steps_max"]
    ):
        return False, (
            "bridge_steps must be a list with "
            f"{limits['bridge_steps_min']} to {limits['bridge_steps_max']} ordered bridge-step objects"
        ), None
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
        depends_on = coerce_relation_list_field(step.get("depends_on"), max_len=limits["depends_on_max"])
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
        min_len=limits["visible_relations_min"],
        max_len=limits["visible_relations_max"],
    )

    relation_mentions = extract_point_mentions(" ".join(cleaned_plan["coordinate_relations"]), visible_points)
    if len(relation_mentions) < limits["coordinate_coverage_min"]:
        return False, (
            "coordinate_relations should collectively cover at least "
            f"{limits['coordinate_coverage_min']} visible points"
        ), None
    non_anchor_visible_points = [
        point for point in visible_points
        if point not in set(normalized_points)
    ]
    non_anchor_visible_point_set = set(non_anchor_visible_points)
    non_anchor_coordinate_mentions = set()
    for relation in cleaned_plan["coordinate_relations"]:
        non_anchor_coordinate_mentions.update(
            point
            for point in extract_point_mentions(relation, visible_points)
            if point in non_anchor_visible_point_set
        )
    non_anchor_coordinate_coverage_min = min(
        3 if limits["extended_budget"] else 2,
        len(non_anchor_visible_points),
    )
    if non_anchor_coordinate_coverage_min and len(non_anchor_coordinate_mentions) < non_anchor_coordinate_coverage_min:
        return False, (
            "coordinate_relations should cover at least "
            f"{non_anchor_coordinate_coverage_min} visible non-anchor points so the route does not stay trapped on the anchor frame"
        ), None

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
        hidden_route_relations = proof_guidance.get("ordered_route_relations") or (
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
                    aligned_step["relation"] = match["relation"]
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
        novelty_supports = cleaned_plan["visible_relations"] + cleaned_plan["aux_direct_relations"]
        available_supports = (
            cleaned_plan["coordinate_relations"]
            + cleaned_plan["visible_relations"]
            + cleaned_plan["aux_direct_relations"]
        )
        for idx, step in enumerate(cleaned_plan["bridge_steps"]):
            if idx > 0:
                previous_relation = cleaned_plan["bridge_steps"][idx - 1]["relation"]
                available_supports.append(previous_relation)
                novelty_supports.append(previous_relation)
            if relation_duplicates_earlier_support(step["relation"], novelty_supports, known_points):
                return False, f"bridge_steps[{idx}].relation must advance beyond earlier visible, direct, or bridge relations", None
            support_cap = min(
                compute_bridge_step_required_support_cap(step),
                limits["depends_on_max"],
            )
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
                max_supports=min(support_cap, len(available_supports)),
            )
            if not matched_supports and preferred_dependencies:
                matched_supports = preferred_dependencies[:]
                canonical_dependencies = preferred_dependencies + canonical_dependencies
            if not matched_supports:
                return False, f"bridge_steps[{idx}].depends_on must reuse an earlier visible, coordinate, direct, or bridge relation", None
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
            step["depends_on"] = merged_dependencies[: limits["depends_on_max"]]
            step["required_supports"] = choose_required_supports_for_bridge_step(
                step,
                known_points,
                max_supports=min(support_cap, len(step["depends_on"])),
            )
            if not step["required_supports"]:
                step["required_supports"] = step["depends_on"][: min(support_cap, len(step["depends_on"]))]
            step["min_support_mentions"] = compute_bridge_step_min_support_mentions(step)
            unsupported_required_segments = find_unsupported_bridge_relation_segments(
                step,
                step["required_supports"],
            )
            if len(unsupported_required_segments) > 1:
                return False, (
                    f"bridge_steps[{idx}].relation still introduces unsupported angle/ratio/similar segments "
                    "before they are grounded by required_supports: "
                    f"{unsupported_required_segments}"
                ), None
            previous_route_position = 0
            previous_bridge_relation = ""
            if idx > 0:
                previous_route_position = int(cleaned_plan["bridge_steps"][idx - 1].get("approved_route_position") or 0)
                previous_bridge_relation = cleaned_plan["bridge_steps"][idx - 1].get("approved_route_relation") or cleaned_plan["bridge_steps"][idx - 1].get("relation", "")
            skipped_prerequisite = find_skipped_prerequisite_route_checkpoint(
                step,
                previous_route_position,
                hidden_route_relations,
                known_points,
                previous_bridge_relation=previous_bridge_relation,
            )
            if skipped_prerequisite:
                return False, (
                    "bridge_steps should not skip prerequisite hidden-route checkpoints before higher-order similarity or ratio steps; "
                    f"missing prerequisite: {skipped_prerequisite}"
                ), None
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
    max_body_len = compute_writer_body_budget(plan=plan, injected_prefix=injected_prefix)
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
    coordinate_focus_points = [
        point.lower()
        for point in (coverage_targets.get("coordinate_focus_points") or [])
        if isinstance(point, str) and point.strip()
    ]
    coordinate_focus_relations = [
        relation
        for relation in (coverage_targets.get("coordinate_focus_relations") or [])
        if isinstance(relation, str) and relation.strip()
    ]
    observation_focus_relations = [
        relation
        for relation in (coverage_targets.get("observation_focus_relations") or [])
        if isinstance(relation, str) and relation.strip()
    ]
    if not observation_focus_relations and isinstance(plan, dict):
        for observation in plan.get("observation_relations", []) or []:
            if not isinstance(observation, dict):
                continue
            relation = normalize_relation_surface(observation.get("relation") or "").strip()
            if relation and relation not in observation_focus_relations:
                observation_focus_relations.append(relation)
    coordinate_reuse_min = int(coverage_targets.get("coordinate_reuse_min") or 0)
    early_coordinate_reuse_min = int(coverage_targets.get("early_coordinate_reuse_min") or 0)
    coverage_point_pool = []
    for point in (
        (plan.get("anchor_points") or []) if isinstance(plan, dict) else []
    ) + (coverage_targets.get("goal_points") or []) + (coverage_targets.get("non_anchor_points") or []):
        if isinstance(point, str):
            point = point.lower().strip()
            if point and point not in coverage_point_pool:
                coverage_point_pool.append(point)
    if observation_focus_relations:
        observation_relation_mentions = count_relation_mentions(
            body,
            observation_focus_relations,
            point_names=coverage_point_pool or None,
        )
        if observation_relation_mentions < 1:
            return False, "Writer body must explicitly reuse at least one approved observation cue after the prefix"
        early_body = " ".join(sentences[: min(3, len(sentences))])
        early_observation_mentions = count_relation_mentions(
            early_body,
            observation_focus_relations,
            point_names=coverage_point_pool or None,
        )
        if early_observation_mentions < 1:
            return False, (
                "Writer early body must continue from at least one approved observation cue "
                "instead of restarting from the anchor frame"
            )
    if plan and isinstance(plan.get("coordinate_relations"), list):
        coordinate_relations = [
            relation
            for relation in plan.get("coordinate_relations", [])
            if isinstance(relation, str) and relation.strip()
        ]
        required_coordinate_mentions = coordinate_reuse_min or (1 if coordinate_relations else 0)
        coordinate_relation_mentions = (
            count_relation_mentions(body, coordinate_relations, point_names=coverage_point_pool or None)
            if coordinate_relations else 0
        )
        if coordinate_relations and coordinate_relation_mentions < required_coordinate_mentions:
            if required_coordinate_mentions <= 1:
                return False, "Writer body must explicitly reuse at least one approved coordinate relation cue after the prefix"
            return False, (
                "Writer body must explicitly reuse at least "
                f"{required_coordinate_mentions} approved coordinate relation cues after the prefix"
            )
    if coordinate_focus_relations and early_coordinate_reuse_min:
        early_body = " ".join(sentences[: min(3, len(sentences))])
        early_coordinate_mentions = count_relation_mentions(
            early_body,
            coordinate_focus_relations,
            point_names=coverage_point_pool or coordinate_focus_points or None,
        )
        if early_coordinate_mentions < early_coordinate_reuse_min:
            return False, (
                "Writer early body must connect the bottleneck/helper to at least one approved non-anchor coordinate cue"
            )
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
            mentioned_dependencies = count_support_relation_mentions(
                sentence,
                required_supports,
                point_names=coverage_point_pool or None,
                target_relation=step.get("approved_route_relation") or step.get("relation", ""),
            )
            min_support_mentions = step.get("min_support_mentions", 1 if required_supports else 0)
            if mentioned_dependencies < min_support_mentions:
                support_phrase = (
                    "at least one approved supporting relation"
                    if min_support_mentions <= 1 else
                    f"at least {min_support_mentions} approved supporting relations"
                )
                return False, (
                    f"Writer sentence for bridge_steps[{idx}] must name {support_phrase}"
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


def build_plan_prompt(record, aux_part, sanitized_rest, planner_style="default"):
    if planner_style == "raw_record_v1":
        return build_raw_record_plan_prompt(record)
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    proof_guidance_payload = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    visible_text_facts = build_visible_text_facts(record)
    image_coordinate_candidates = build_image_coordinate_candidates(point_coords, visible_text_facts)
    return build_plan_prompt_text(
        record,
        aux_part,
        visible_text_facts=visible_text_facts,
        image_coordinate_candidates=image_coordinate_candidates,
        hidden_route_hints=proof_guidance_payload,
    )


def build_plan_critic_prompt(record, plan, sanitized_rest, aux_part):
    visible_goal = extract_problem_goal(record)
    proof_guidance_payload = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    return build_plan_critic_prompt_text(
        record,
        plan,
        hidden_route_hints=proof_guidance_payload,
    )


def build_canonical_goal_finish_relation(visible_goal, proof_guidance_payload=None):
    proof_guidance_payload = proof_guidance_payload or {}
    goal_finish_relations = proof_guidance_payload.get("goal_finish_relations") or []
    if goal_finish_relations:
        return normalize_relation_surface(goal_finish_relations[-1]).strip()
    ordered_route = proof_guidance_payload.get("ordered_route_relations") or []
    if ordered_route:
        return normalize_relation_surface(ordered_route[-1]).strip()

    goal_spec = parse_goal_expression(visible_goal or "")
    predicate = (goal_spec.get("predicate") or "").lower()
    points = [point.lower() for point in goal_spec.get("points", []) if isinstance(point, str)]
    if predicate == "eqratio" and len(points) >= 8:
        return f"ratio {points[0]}{points[1]} to {points[2]}{points[3]} equals ratio {points[4]}{points[5]} to {points[6]}{points[7]}"
    if predicate == "eqangle" and len(points) >= 8:
        return f"angle {points[0]}{points[1]}/{points[2]}{points[3]} equals angle {points[4]}{points[5]}/{points[6]}{points[7]}"
    if predicate in {"cong", "equal"} and len(points) >= 4:
        return f"{points[0]}{points[1]} equals {points[2]}{points[3]}"
    if predicate in {"simtri", "simtrir"} and len(points) >= 6:
        return f"triangles {points[0]}{points[1]}{points[2]} and {points[3]}{points[4]}{points[5]} are similar"
    if predicate in {"contri", "contrir"} and len(points) >= 6:
        return f"triangles {points[0]}{points[1]}{points[2]} and {points[3]}{points[4]}{points[5]} are congruent"
    if predicate == "para" and len(points) >= 4:
        return f"line {points[0]}{points[1]} is parallel to line {points[2]}{points[3]}"
    if predicate == "perp" and len(points) >= 4:
        return f"line {points[0]}{points[1]} is perpendicular to line {points[2]}{points[3]}"
    if predicate == "coll" and len(points) >= 3:
        return f"{points[0]}, {points[1]}, and {points[2]} are collinear"
    return build_canonical_goal_bottleneck(visible_goal)


def select_coordinate_relations_for_skeleton(
    coordinate_candidates,
    route_relations,
    anchor_points,
    visible_points,
    min_len=2,
    max_len=4,
):
    route_relations = [
        relation.strip()
        for relation in (route_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    if not coordinate_candidates:
        return []

    anchor_set = {point.lower() for point in (anchor_points or []) if isinstance(point, str)}
    route_text = " ".join(route_relations)
    route_points = extract_point_mentions(route_text, visible_points)
    route_keywords = relation_text_keywords(route_text)
    selected = []
    selected_lower = set()
    covered_points = set()

    ranked_candidates = []
    for idx, candidate in enumerate(coordinate_candidates):
        summary = normalize_relation_surface((candidate or {}).get("summary", "")).strip()
        if not summary:
            continue
        points = extract_point_mentions(summary, visible_points)
        if len(points) < 2:
            continue
        keywords = relation_text_keywords(summary)
        non_anchor_points = points - anchor_set
        key = (
            len(non_anchor_points & route_points),
            len(points & route_points),
            len(keywords & route_keywords),
            1 if any(keyword in keywords for keyword in {"midpoint", "collinear", "equal", "parallel", "perpendicular"}) else 0,
            -float(candidate.get("score", 9999.0)),
            -idx,
        )
        ranked_candidates.append((key, summary, points))
    ranked_candidates.sort(key=lambda item: item[0], reverse=True)

    while ranked_candidates and len(selected) < max_len:
        best_idx = None
        best_key = None
        for idx, (base_key, summary, points) in enumerate(ranked_candidates):
            lowered = summary.lower()
            if lowered in selected_lower:
                continue
            new_non_anchor = len((points - anchor_set) - covered_points)
            new_points = len(points - covered_points)
            key = (
                new_non_anchor,
                new_points,
                *base_key,
                -len(summary),
                summary.lower(),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_idx = idx
        if best_idx is None:
            break
        _, summary, points = ranked_candidates.pop(best_idx)
        selected.append(summary)
        selected_lower.add(summary.lower())
        covered_points.update(points)

    for _, summary, _ in ranked_candidates:
        if len(selected) >= max_len:
            break
        lowered = summary.lower()
        if lowered in selected_lower:
            continue
        selected.append(summary)
        selected_lower.add(lowered)

    return selected[: max(min_len, min(max_len, len(selected)))] if selected else []


def classify_observation_priority_region(points, goal_points, bridge_route_points):
    point_set = {point.lower() for point in (points or []) if isinstance(point, str)}
    goal_set = {point.lower() for point in (goal_points or []) if isinstance(point, str)}
    bridge_set = {point.lower() for point in (bridge_route_points or []) if isinstance(point, str)}
    if point_set & goal_set:
        return "goal_side"
    if point_set & bridge_set:
        return "bridge_side"
    return "mixed"


def build_observation_relations_for_skeleton(
    coordinate_candidates,
    route_relations,
    visible_points,
    goal_points,
    max_items=4,
):
    if not coordinate_candidates:
        return []
    route_text = " ".join(
        relation.strip()
        for relation in (route_relations or [])
        if isinstance(relation, str) and relation.strip()
    )
    route_points = extract_point_mentions(route_text, visible_points)
    goal_point_set = {point.lower() for point in (goal_points or []) if isinstance(point, str)}
    observations = []
    seen_relations = set()
    ranked = []
    for idx, candidate in enumerate(coordinate_candidates):
        if not isinstance(candidate, dict):
            continue
        relation = normalize_relation_surface((candidate.get("summary") or "")).strip()
        if not relation:
            continue
        points = [
            point.lower()
            for point in (candidate.get("points") or [])
            if isinstance(point, str) and point.strip() and point.lower() in visible_points
        ]
        if len(points) < 2:
            points = sorted(extract_point_mentions(relation, visible_points))
        if len(points) < 2:
            continue
        relation_type = candidate.get("relation_type") or infer_relation_type_from_text(relation)
        relation_points = set(points)
        bridge_overlap = len(relation_points & route_points)
        goal_overlap = len(relation_points & goal_point_set)
        quality_bonus = 1 if relation_type in {"midpoint", "collinear", "equal_length", "parallel", "perpendicular"} else 0
        score = (
            goal_overlap,
            bridge_overlap,
            quality_bonus,
            -float(candidate.get("score", 9999.0)),
            -idx,
        )
        ranked.append((score, relation, points, relation_type, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)

    covered_points = set()
    while ranked and len(observations) < max_items:
        best_idx = None
        best_key = None
        for idx, (score, relation, points, relation_type, candidate) in enumerate(ranked):
            lowered = relation.lower()
            if lowered in seen_relations:
                continue
            new_points = len(set(points) - covered_points)
            goal_overlap = len(set(points) & goal_point_set)
            key = (
                new_points,
                goal_overlap,
                *score,
                -len(relation),
                relation.lower(),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_idx = idx
        if best_idx is None:
            break
        _, relation, points, relation_type, candidate = ranked.pop(best_idx)
        seen_relations.add(relation.lower())
        covered_points.update(points)
        observations.append(
            {
                "id": f"obs_{len(observations) + 1}",
                "relation": relation,
                "relation_type": relation_type,
                "points": points,
                "evidence_mode": "hybrid",
                "visual_surface": relation,
                "coordinate_surface": candidate.get("summary") or relation,
                "verification_role": "seed",
                "priority_region": classify_observation_priority_region(points, goal_points, route_points),
            }
        )
    return observations


def select_anchor_points_from_observations(
    visible_points,
    observation_relations,
    goal_points,
    min_anchor_count,
    max_anchor_count,
):
    visible_points = [point.lower() for point in (visible_points or []) if isinstance(point, str) and point.strip()]
    goal_set = {point.lower() for point in (goal_points or []) if isinstance(point, str)}
    observation_points = []
    observation_point_set = set()
    point_scores = {}
    for observation in observation_relations or []:
        for point in observation.get("points", []) or []:
            point = point.lower()
            if point not in visible_points:
                continue
            observation_points.append(point)
            observation_point_set.add(point)
            point_scores[point] = point_scores.get(point, 0) + 1

    ranked = sorted(
        visible_points,
        key=lambda point: (
            point in goal_set,
            point in observation_point_set,
            -point_scores.get(point, 0),
            visible_points.index(point),
            point,
        ),
    )
    anchors = []
    reserved_non_anchor = set(observation_points[: min(3, len(observation_points))])
    for point in ranked:
        if point in reserved_non_anchor and len(visible_points) - len(anchors) > min_anchor_count:
            continue
        anchors.append(point)
        if len(anchors) >= max_anchor_count:
            break
    if len(anchors) < min_anchor_count:
        for point in visible_points:
            if point not in anchors:
                anchors.append(point)
            if len(anchors) >= min_anchor_count:
                break
    return anchors[:max_anchor_count]


def build_scripted_plan_skeleton(
    record,
    aux_part,
    sanitized_rest,
    point_coords,
    coordinate_candidates,
    visible_premise_summaries,
    visible_goal,
):
    proof_guidance_payload = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    limits = compute_plan_complexity_limits(point_coords, visible_goal=visible_goal, aux_part=aux_part)
    visible_points = extract_visible_point_names(point_coords)
    known_points = visible_points + [point.lower() for point in extract_aux_new_points(aux_part or "")]
    goal_points = parse_goal_expression(visible_goal or "").get("points", [])
    goal_finish = build_canonical_goal_finish_relation(
        visible_goal,
        proof_guidance_payload=proof_guidance_payload,
    )

    route_relations = proof_guidance_payload.get("ordered_route_relations") or (
        proof_guidance_payload.get("aux_bridge_relations", [])
        + proof_guidance_payload.get("bridge_relations", [])
        + proof_guidance_payload.get("goal_finish_relations", [])
    )
    observation_relations = build_observation_relations_for_skeleton(
        coordinate_candidates,
        route_relations,
        visible_points,
        goal_points,
        max_items=limits["coordinate_relations_max"],
    )
    target_anchor_count = min(
        limits["anchor_max"],
        max(limits["anchor_min"], 4 if len(visible_points) >= 4 else len(visible_points)),
    )
    anchor_points = select_anchor_points_from_observations(
        visible_points,
        observation_relations,
        goal_points,
        min_anchor_count=limits["anchor_min"],
        max_anchor_count=target_anchor_count,
    )
    coordinate_relations = [
        observation.get("relation", "")
        for observation in observation_relations
        if isinstance(observation, dict) and observation.get("relation")
    ]
    if len(coordinate_relations) < limits["coordinate_relations_min"]:
        coordinate_relations = select_coordinate_relations_for_skeleton(
            coordinate_candidates,
            route_relations,
            anchor_points,
            visible_points,
            min_len=limits["coordinate_relations_min"],
            max_len=limits["coordinate_relations_max"],
        )
        if not observation_relations:
            observation_relations = build_observation_relations_for_skeleton(
                coordinate_candidates,
                route_relations,
                visible_points,
                goal_points,
                max_items=limits["coordinate_relations_max"],
            )
    anchor_points = rebalance_anchor_points_for_coordinate_coverage(
        anchor_points,
        coordinate_relations,
        visible_points,
        min_anchor_count=limits["anchor_min"],
        required_non_anchor_coverage=min(
            limits["coordinate_coverage_min"],
            max(0, len(visible_points) - limits["anchor_min"]),
        ),
    )

    aux_direct_relations = [
        normalize_relation_surface(relation).strip()
        for relation in (
            proof_guidance_payload.get("immediate_aux_consequences")
            or build_aux_direct_consequences(aux_part)
        )
        if isinstance(relation, str) and relation.strip()
    ][: limits["aux_direct_relations_max"]]
    visible_relations = prioritize_visible_relations_for_route(
        existing_relations=[],
        fallback_summaries=visible_premise_summaries,
        route_relations=route_relations,
        visible_points=visible_points,
        min_len=limits["visible_relations_min"],
        max_len=limits["visible_relations_max"],
    )
    visible_relations = canonicalize_visible_relations(
        visible_relations,
        visible_points,
        visible_premise_summaries,
        min_len=limits["visible_relations_min"],
        max_len=limits["visible_relations_max"],
        min_chars=5,
    )

    bridge_steps = []
    available_supports = coordinate_relations + visible_relations + aux_direct_relations
    novelty_supports = visible_relations + aux_direct_relations
    hidden_route_relations = route_relations[:]
    normalized_goal_finish = normalize_relation_surface(goal_finish).strip()

    for route_index, relation in enumerate(hidden_route_relations):
        if len(bridge_steps) >= limits["bridge_steps_max"]:
            break
        if not isinstance(relation, str) or not relation.strip():
            continue
        relation = normalize_relation_surface(relation).strip()
        if relations_semantically_match(relation, normalized_goal_finish, known_points):
            continue
        if not bridge_steps and known_points[len(visible_points):]:
            aux_points = known_points[len(visible_points):]
            if not any(point in relation.lower() for point in aux_points):
                continue
        if relation_duplicates_earlier_support(relation, novelty_supports, known_points):
            continue

        previous_route_position = 0
        previous_bridge_relation = ""
        if bridge_steps:
            previous_route_position = int(bridge_steps[-1].get("approved_route_position") or 0)
            previous_bridge_relation = (
                bridge_steps[-1].get("approved_route_relation")
                or bridge_steps[-1].get("relation", "")
            )
        support_cap = min(compute_bridge_step_required_support_cap({"relation": relation}), limits["depends_on_max"])
        next_target_relation = ""
        for later_relation in hidden_route_relations[route_index + 1:]:
            if not isinstance(later_relation, str) or not later_relation.strip():
                continue
            later_relation = normalize_relation_surface(later_relation).strip()
            if relations_semantically_match(later_relation, normalized_goal_finish, known_points):
                next_target_relation = normalized_goal_finish
                break
            if later_relation not in {step.get("relation", "") for step in bridge_steps}:
                next_target_relation = later_relation
                break
        if not next_target_relation:
            next_target_relation = normalized_goal_finish

        preferred_dependencies = select_support_relations_for_step(
            relation,
            available_supports,
            known_points,
            next_target_relation=next_target_relation,
            max_supports=min(support_cap, len(available_supports)),
        )
        if not preferred_dependencies:
            continue
        step = {
            "relation": relation,
            "approved_route_relation": relation,
            "approved_route_position": route_index + 1,
            "depends_on": preferred_dependencies[: limits["depends_on_max"]],
        }
        step["required_supports"] = choose_required_supports_for_bridge_step(
            step,
            known_points,
            max_supports=min(support_cap, len(step["depends_on"])),
        )
        if not step["required_supports"]:
            step["required_supports"] = step["depends_on"][: min(support_cap, len(step["depends_on"]))]
        if len(find_unsupported_bridge_relation_segments(step, step["required_supports"])) > 1:
            continue
        skipped_prerequisite = find_skipped_prerequisite_route_checkpoint(
            step,
            previous_route_position,
            hidden_route_relations,
            known_points,
            previous_bridge_relation=previous_bridge_relation,
        )
        if skipped_prerequisite:
            continue
        bridge_steps.append(step)
        available_supports.append(relation)
        novelty_supports.append(relation)

    if len(bridge_steps) < limits["bridge_steps_min"]:
        fallback_relations = []
        for relation in hidden_route_relations:
            normalized_relation = normalize_relation_surface(relation).strip()
            if relations_semantically_match(normalized_relation, normalized_goal_finish, known_points):
                continue
            if normalized_relation not in fallback_relations:
                fallback_relations.append(normalized_relation)
            if len(fallback_relations) >= limits["bridge_steps_min"]:
                break
        bridge_steps = []
        available_supports = coordinate_relations + visible_relations + aux_direct_relations
        novelty_supports = visible_relations + aux_direct_relations
        for route_index, relation in enumerate(fallback_relations):
            support_cap = min(compute_bridge_step_required_support_cap({"relation": relation}), limits["depends_on_max"])
            preferred_dependencies = select_support_relations_for_step(
                relation,
                available_supports,
                known_points,
                next_target_relation=normalized_goal_finish,
                max_supports=min(support_cap, len(available_supports)),
            )
            if not preferred_dependencies:
                continue
            step = {
                "relation": relation,
                "approved_route_relation": relation,
                "approved_route_position": route_index + 1,
                "depends_on": preferred_dependencies[: limits["depends_on_max"]],
            }
            bridge_steps.append(step)
            available_supports.append(relation)
            novelty_supports.append(relation)

    bridge_plan = {"bridge_steps": bridge_steps, "goal_finish": normalized_goal_finish}
    bridge_plan = enrich_bridge_steps_with_targets(bridge_plan)
    enriched_steps = []
    total_steps = len(bridge_plan.get("bridge_steps", []))
    for idx, step in enumerate(bridge_plan.get("bridge_steps", [])):
        enriched = dict(step)
        enriched["required_supports"] = choose_required_supports_for_bridge_step(
            enriched,
            known_points,
            max_supports=min(
                compute_bridge_step_required_support_cap(enriched),
                len(enriched.get("depends_on", [])),
                limits["depends_on_max"],
            ),
        ) or enriched.get("depends_on", [])[: min(limits["depends_on_max"], len(enriched.get("depends_on", [])))]
        enriched["min_support_mentions"] = compute_bridge_step_min_support_mentions(enriched)
        enriched["why_it_helps"] = build_canonical_bridge_unlock(
            enriched.get("next_target_relation", normalized_goal_finish),
            final_step=(idx == total_steps - 1),
        )
        enriched_steps.append(enriched)

    return {
        "anchor_points": anchor_points,
        "anchor_relation": build_canonical_anchor_relation(anchor_points, visible_relations),
        "figure_overview": build_canonical_figure_overview(anchor_points, visible_relations, coordinate_relations, visible_points),
        "observation_relations": observation_relations,
        "coordinate_relations": coordinate_relations,
        "visible_relations": visible_relations,
        "coordinate_hints": build_canonical_coordinate_hint(coordinate_relations),
        "goal_bottleneck": build_canonical_goal_bottleneck(visible_goal),
        "helper_idea": build_canonical_helper_idea(aux_direct_relations, build_canonical_goal_bottleneck(visible_goal)),
        "construction": build_canonical_construction(aux_part),
        "aux_direct_relations": aux_direct_relations,
        "bridge_steps": enriched_steps,
        "goal_finish": normalized_goal_finish,
    }


def enrich_bridge_steps_with_targets(plan):
    if not isinstance(plan, dict):
        return plan
    bridge_steps = plan.get("bridge_steps")
    if not isinstance(bridge_steps, list):
        return plan
    goal_finish = normalize_relation_surface(plan.get("goal_finish", "") or "").strip()
    for idx, raw_step in enumerate(bridge_steps):
        if not isinstance(raw_step, dict):
            continue
        step = raw_step
        if idx + 1 < len(bridge_steps):
            next_relation = (
                bridge_steps[idx + 1].get("approved_route_relation")
                or bridge_steps[idx + 1].get("relation", "")
            )
            next_purpose = "bridge"
        else:
            next_relation = goal_finish
            next_purpose = "goal_finish"
        step["next_target_relation"] = normalize_relation_surface(next_relation or goal_finish).strip()
        step["next_target_purpose"] = next_purpose
        if not step.get("approved_route_relation"):
            step["approved_route_relation"] = step.get("relation", "")
        if not step.get("proof_alignment"):
            step["proof_alignment"] = "bridge"
    plan["bridge_steps"] = bridge_steps
    return plan


def merge_plan_skeleton_and_narrative(plan_skeleton, narrative_fields):
    merged = json.loads(json.dumps(plan_skeleton))
    if not isinstance(narrative_fields, dict):
        return merged
    for key in [
        "anchor_relation",
        "figure_overview",
        "coordinate_hints",
        "goal_bottleneck",
        "helper_idea",
        "construction",
    ]:
        value = narrative_fields.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    unlocks = narrative_fields.get("bridge_step_unlocks")
    if isinstance(unlocks, list):
        for idx, unlock in enumerate(unlocks):
            if idx >= len(merged.get("bridge_steps", [])):
                break
            if isinstance(unlock, str) and unlock.strip():
                merged["bridge_steps"][idx]["why_it_helps"] = unlock.strip()
    return merged


def build_write_prompt(record, plan, aux_part, point_coords):
    return build_write_prompt_text(
        record,
        plan,
        aux_part,
        coordinate_derivation_block=build_coordinate_derivation_block(plan, point_coords),
    )


def build_dossier_hidden_milestone_summary(
    sanitized_rest,
    aux_part,
    visible_goal,
    source_audit=None,
):
    proof_guidance = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    return {
        "immediate_aux_milestones": list(proof_guidance.get("immediate_aux_consequences") or [])[:4],
        "plausible_bridge_milestones": (
            list(proof_guidance.get("aux_bridge_relations") or [])
            + list(proof_guidance.get("bridge_relations") or [])
        )[:6],
        "plausible_goal_closures": list(proof_guidance.get("goal_finish_relations") or [])[:4],
        "source_audit_flags": list((source_audit or {}).get("issues") or [])[:6],
    }


def build_safe_dossier_aux_motivation(aux_part: str, visible_goal: str):
    goal_family = "goal relation"
    visible_goal_lower = (visible_goal or "").lower()
    if visible_goal_lower.startswith("eqratio"):
        goal_family = "ratio relation"
    elif visible_goal_lower.startswith("eqangle"):
        goal_family = "angle relation"
    elif visible_goal_lower.startswith("simtri") or visible_goal_lower.startswith("simtrir"):
        goal_family = "similarity relation"
    elif visible_goal_lower.startswith("contri") or visible_goal_lower.startswith("contrir"):
        goal_family = "congruence relation"
    aux_labels = [label for label, _ in build_aux_keyword_expectations(aux_part or "")]
    aux_cue = aux_labels[0] if aux_labels else "local helper"
    stage_phrase = "in stages and then reconnect those stages" if len(extract_aux_new_points(aux_part or "")) > 1 else "first and then reconnect that relation"
    return (
        f"the helper should create one local {aux_cue} relation {stage_phrase} "
        f"to the visible figure before the target {goal_family} closes."
    )


def build_dossier_relation_ref_catalog(
    visible_facts,
    image_scan,
    coordinate_checks,
    aux_immediate_effects,
    bridge_claims,
):
    catalog = []
    for idx, relation in enumerate(visible_facts or [], start=1):
        if isinstance(relation, str) and relation.strip():
            catalog.append({"ref": f"visible_facts[{idx}]", "relation": normalize_relation_surface(relation)})
    for idx, relation in enumerate(image_scan or [], start=1):
        if isinstance(relation, str) and relation.strip():
            catalog.append({"ref": f"image_scan[{idx}]", "relation": normalize_relation_surface(relation)})
    for idx, item in enumerate(coordinate_checks or [], start=1):
        relation = item.get("relation") if isinstance(item, dict) else ""
        if isinstance(relation, str) and relation.strip():
            catalog.append({"ref": f"coordinate_checks[{idx}]", "relation": normalize_relation_surface(relation)})
    for idx, relation in enumerate(aux_immediate_effects or [], start=1):
        if isinstance(relation, str) and relation.strip():
            catalog.append({"ref": f"aux_immediate_effects[{idx}]", "relation": normalize_relation_surface(relation)})
    for idx, relation in enumerate(bridge_claims or [], start=1):
        if isinstance(relation, str) and relation.strip():
            catalog.append({"ref": f"bridge_chain[{idx}]", "relation": normalize_relation_surface(relation)})
    return catalog


def map_support_relations_to_dossier_refs(
    support_relations,
    support_catalog,
    point_names,
    max_supports=2,
):
    refs = []
    used_refs = set()
    for support_relation in support_relations or []:
        if not isinstance(support_relation, str) or not support_relation.strip():
            continue
        normalized_support = normalize_relation_surface(support_relation)
        matched_ref = None
        for item in support_catalog or []:
            relation = item.get("relation", "")
            ref = item.get("ref", "")
            if ref in used_refs:
                continue
            if normalized_support.lower() == str(relation).lower():
                matched_ref = ref
                break
            if relations_semantically_match(normalized_support, relation, point_names):
                matched_ref = ref
                break
        if matched_ref:
            refs.append(matched_ref)
            used_refs.add(matched_ref)
        if len(refs) >= max_supports:
            break
    return refs


def select_low_level_relay_support_refs(
    relation_text,
    support_catalog,
    point_names,
    max_supports=2,
):
    relation_keywords = relation_text_keywords(relation_text)
    if max_supports < 2 or not (relation_keywords & {"parallel", "perpendicular"}):
        return []

    relation_segments = extract_relation_segment_tokens(relation_text)
    relation_points = extract_point_mentions(relation_text, point_names)
    if len(relation_segments) < 2:
        return []

    def ref_source_priority(ref):
        lowered = str(ref or "").lower()
        if lowered.startswith("image_scan["):
            return 3
        if lowered.startswith("coordinate_checks["):
            return 2
        if lowered.startswith("visible_facts["):
            return 1
        return 0

    candidates = []
    for item in support_catalog or []:
        relation = item.get("relation", "")
        ref = item.get("ref", "")
        if not relation or not ref:
            continue
        lowered_ref = ref.lower()
        if lowered_ref.startswith("bridge_chain[") or lowered_ref.startswith("aux_immediate_effects["):
            continue
        support_keywords = relation_text_keywords(relation)
        if not support_keywords & {"parallel", "perpendicular", "collinear"}:
            continue
        support_segments = extract_relation_segment_tokens(relation)
        if not support_segments:
            continue
        candidates.append(
            {
                "ref": ref,
                "relation": relation,
                "keywords": support_keywords,
                "segments": support_segments,
                "points": extract_point_mentions(relation, point_names),
                "source_priority": ref_source_priority(ref),
            }
        )

    best_pair = []
    best_key = None
    for left_idx, left in enumerate(candidates):
        for right in candidates[left_idx + 1:]:
            combined_segments = left["segments"] | right["segments"]
            covered_claim_segments = len(combined_segments & relation_segments)
            if covered_claim_segments < len(relation_segments):
                continue
            shared_relay_segments = (left["segments"] & right["segments"]) - relation_segments
            shared_relay_points = (left["points"] & right["points"]) - relation_points
            if not shared_relay_segments and not shared_relay_points:
                continue
            pair = [left, right]
            pair.sort(
                key=lambda candidate: (
                    len(candidate["segments"] & relation_segments),
                    candidate["source_priority"],
                    score_support_relation(candidate["relation"], relation_text, point_names),
                    -len(candidate["relation"]),
                    candidate["relation"].lower(),
                ),
                reverse=True,
            )
            key = (
                covered_claim_segments,
                len(shared_relay_segments),
                len(shared_relay_points),
                sum(candidate["source_priority"] for candidate in pair),
                sum(
                    score_support_relation(candidate["relation"], relation_text, point_names)
                    for candidate in pair
                ),
                -sum(len(candidate["relation"]) for candidate in pair),
                tuple(candidate["relation"].lower() for candidate in pair),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_pair = pair

    return [candidate["ref"] for candidate in best_pair[:max_supports]]


def select_dossier_support_refs_for_relation(
    relation_text,
    support_catalog,
    point_names,
    preferred_supports=None,
    next_target_relation="",
    max_supports=2,
):
    support_catalog = support_catalog or []
    preferred_refs = map_support_relations_to_dossier_refs(
        preferred_supports or [],
        support_catalog,
        point_names,
        max_supports=max_supports,
    )
    if len(preferred_refs) >= max_supports:
        return preferred_refs[:max_supports]

    relay_refs = select_low_level_relay_support_refs(
        relation_text,
        support_catalog,
        point_names,
        max_supports=max_supports,
    )
    ranked_supports = select_support_relations_for_step(
        relation_text,
        [item.get("relation", "") for item in support_catalog],
        point_names,
        next_target_relation=next_target_relation,
        max_supports=max(max_supports, len(preferred_refs) + 1),
    )
    ranked_refs = map_support_relations_to_dossier_refs(
        ranked_supports,
        support_catalog,
        point_names,
        max_supports=max_supports,
    )
    combined = []
    for ref in preferred_refs + relay_refs + ranked_refs:
        if ref not in combined:
            combined.append(ref)
        if len(combined) >= max_supports:
            break
    relation_segments = extract_relation_segment_tokens(relation_text)
    if relation_segments and len(combined) < max_supports:
        grounded_segments = set()
        for item in support_catalog:
            if item.get("ref") in combined:
                grounded_segments.update(extract_relation_segment_tokens(item.get("relation", "")))
        missing_segments = relation_segments - grounded_segments
        while missing_segments and len(combined) < max_supports:
            best_item = None
            best_key = None
            for item in support_catalog:
                ref = item.get("ref", "")
                relation = item.get("relation", "")
                if ref in combined:
                    continue
                candidate_segments = extract_relation_segment_tokens(relation)
                if not candidate_segments or not (candidate_segments & missing_segments):
                    continue
                candidate_keywords = relation_text_keywords(relation)
                if candidate_keywords & {"ratio", "similar"}:
                    continue
                key = (
                    len(candidate_segments & missing_segments),
                    len(candidate_segments & relation_segments),
                    1 if ref.lower().startswith("coordinate_checks[") else 0,
                    1 if candidate_keywords & {"collinear", "equal", "parallel", "perpendicular", "angle", "circle"} else 0,
                    -len(str(relation)),
                    ref.lower(),
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best_item = item
            if best_item is None:
                break
            combined.append(best_item.get("ref", ""))
            grounded_segments.update(extract_relation_segment_tokens(best_item.get("relation", "")))
            missing_segments = relation_segments - grounded_segments
    return combined


def build_scripted_dossier_coordinate_checks(
    coordinate_candidates,
    point_coords,
    visible_relations,
    image_scan,
    target_relations,
    max_items=4,
):
    allowed_types = {"parallel", "perpendicular", "equal_length", "midpoint", "collinear"}
    visible_points = extract_visible_point_names(point_coords)
    target_relations = [
        relation
        for relation in (target_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    target_points = extract_point_mentions(" ".join(target_relations), visible_points)
    target_segments = set()
    for relation in target_relations:
        target_segments.update(extract_relation_segment_tokens(relation))

    existing_relations = [
        relation
        for relation in list(visible_relations or []) + list(image_scan or [])
        if isinstance(relation, str) and relation.strip()
    ]
    existing_lower = {
        normalize_relation_surface(relation).strip().lower()
        for relation in existing_relations
    }

    ranked_candidates = []
    for idx, raw_candidate in enumerate(coordinate_candidates or []):
        if not isinstance(raw_candidate, dict):
            continue
        relation_type = str(raw_candidate.get("relation_type") or "").strip().lower()
        if relation_type not in allowed_types:
            continue
        relation = build_canonical_coordinate_relation(raw_candidate)
        if not relation:
            continue
        relation = normalize_relation_surface(relation).strip()
        lowered_relation = relation.lower()
        if lowered_relation in existing_lower:
            continue
        if any(
            relations_semantically_match(relation, existing_relation, visible_points)
            for existing_relation in existing_relations
        ):
            continue
        points = [
            point.lower()
            for point in (raw_candidate.get("points") or [])
            if isinstance(point, str) and point.lower() in point_coords
        ]
        if len(points) < 2:
            continue
        candidate_segments = extract_relation_segment_tokens(relation)
        ranked_candidates.append(
            {
                "relation": relation,
                "points": points,
                "calc_type": relation_type,
                "score": float(raw_candidate.get("score", 9999.0)),
                "segments": candidate_segments,
                "point_overlap": len(set(points) & target_points),
                "segment_overlap": len(candidate_segments & target_segments),
                "index": idx,
            }
        )

    selected = []
    selected_lower = set()
    covered_segments = set()
    route_keywords = relation_text_keywords(" ".join(target_relations))
    while ranked_candidates and len(selected) < max_items:
        best_idx = None
        best_key = None
        for idx, candidate in enumerate(ranked_candidates):
            lowered = candidate["relation"].lower()
            if lowered in selected_lower:
                continue
            new_segment_overlap = len((candidate["segments"] & target_segments) - covered_segments)
            key = (
                new_segment_overlap,
                candidate["segment_overlap"],
                candidate["point_overlap"],
                1 if candidate["calc_type"] in {"midpoint", "collinear", "equal_length", "parallel", "perpendicular"} else 0,
                -candidate["score"],
                -len(candidate["relation"]),
                -candidate["index"],
            )
            if best_key is None or key > best_key:
                best_key = key
                best_idx = idx
        if best_idx is None:
            break
        candidate = ranked_candidates.pop(best_idx)
        if best_key[0] <= 0 and selected:
            break
        why_it_matters = "this gives one concrete coordinate-backed cue that the later route can reuse."
        if route_keywords & {"ratio"}:
            why_it_matters = "this gives one concrete segment cue that the later ratio route can reuse."
        elif route_keywords & {"similar"}:
            why_it_matters = "this gives one concrete triangle-side cue that the later similarity route can reuse."
        elif route_keywords & {"angle"}:
            why_it_matters = "this gives one concrete direction cue that the later angle route can reuse."
        selected.append(
            {
                "relation": candidate["relation"],
                "points": candidate["points"],
                "calc_type": candidate["calc_type"],
                "why_it_matters": why_it_matters,
            }
        )
        selected_lower.add(candidate["relation"].lower())
        covered_segments.update(candidate["segments"])

    return selected


def _extract_bridge_chain_ref_index(ref_text, bridge_chain_len):
    match = DOSSIER_SUPPORT_REF_RE.fullmatch(str(ref_text or "").strip())
    if not match or match.group(1).lower() != "bridge_chain":
        return None
    index, index_error = _resolve_dossier_support_index(int(match.group(2)), bridge_chain_len)
    if index_error:
        return None
    return index


def prune_unreferenced_dossier_bridge_chain(bridge_chain, goal_support_refs, aux_points=None):
    if not isinstance(bridge_chain, list) or not bridge_chain:
        return bridge_chain, goal_support_refs or []

    aux_points = [
        str(point).lower()
        for point in (aux_points or [])
        if isinstance(point, str) and point.strip()
    ]
    keep_indices = set()
    bridge_chain_len = len(bridge_chain)

    for ref in goal_support_refs or []:
        index = _extract_bridge_chain_ref_index(ref, bridge_chain_len)
        if index is not None:
            keep_indices.add(index)
    for idx, step in enumerate(bridge_chain):
        if step.get("_script_source") == "tail":
            keep_indices.add(idx)
    if not keep_indices:
        keep_indices.add(bridge_chain_len - 1)

    def step_reconnects_aux(step):
        claim_text = str((step or {}).get("claim", "")).lower()
        if any(point in claim_text for point in aux_points):
            return True
        for ref in step.get("supports", []) or []:
            match = DOSSIER_SUPPORT_REF_RE.fullmatch(str(ref or "").strip())
            if match and match.group(1).lower() == "aux_immediate_effects":
                return True
        return False

    changed = True
    while changed:
        changed = False
        for step_index in list(keep_indices):
            step = bridge_chain[step_index]
            for ref in step.get("supports", []) or []:
                dependency_index = _extract_bridge_chain_ref_index(ref, bridge_chain_len)
                if dependency_index is None or dependency_index in keep_indices:
                    continue
                keep_indices.add(dependency_index)
                changed = True

    if aux_points and not any(step_reconnects_aux(bridge_chain[idx]) for idx in keep_indices):
        for idx, step in enumerate(bridge_chain):
            if step_reconnects_aux(step):
                keep_indices.add(idx)
                changed = True
                break
        while changed:
            changed = False
            for step_index in list(keep_indices):
                step = bridge_chain[step_index]
                for ref in step.get("supports", []) or []:
                    dependency_index = _extract_bridge_chain_ref_index(ref, bridge_chain_len)
                    if dependency_index is None or dependency_index in keep_indices:
                        continue
                    keep_indices.add(dependency_index)
                    changed = True

    if aux_points and keep_indices:
        earliest_kept_index = min(keep_indices)
        if not step_reconnects_aux(bridge_chain[earliest_kept_index]):
            for idx, step in enumerate(bridge_chain):
                if not step_reconnects_aux(step):
                    continue
                keep_indices.add(idx)
                changed = True
                break
            while changed:
                changed = False
                for step_index in list(keep_indices):
                    step = bridge_chain[step_index]
                    for ref in step.get("supports", []) or []:
                        dependency_index = _extract_bridge_chain_ref_index(ref, bridge_chain_len)
                        if dependency_index is None or dependency_index in keep_indices:
                            continue
                        keep_indices.add(dependency_index)
                        changed = True

    sorted_keep_indices = sorted(keep_indices)
    old_to_new_index = {
        old_index: new_index
        for new_index, old_index in enumerate(sorted_keep_indices)
    }

    def rewrite_support_refs(refs):
        rewritten = []
        for ref in refs or []:
            dependency_index = _extract_bridge_chain_ref_index(ref, bridge_chain_len)
            if dependency_index is None:
                rewritten.append(ref)
                continue
            if dependency_index in old_to_new_index:
                rewritten.append(f"bridge_chain[{old_to_new_index[dependency_index] + 1}]")
        return rewritten

    pruned_bridge_chain = []
    for old_index in sorted_keep_indices:
        original_step = bridge_chain[old_index]
        cleaned_step = {
            key: value
            for key, value in original_step.items()
            if not str(key).startswith("_")
        }
        pruned_bridge_chain.append(
            {
                **cleaned_step,
                "supports": rewrite_support_refs(original_step.get("supports", [])),
            }
        )

    rewritten_goal_support_refs = rewrite_support_refs(goal_support_refs or [])
    return pruned_bridge_chain, rewritten_goal_support_refs


def prune_unreferenced_dossier_coordinate_checks(coordinate_checks, bridge_chain, goal_support_refs):
    if not isinstance(coordinate_checks, list) or not coordinate_checks:
        return coordinate_checks, bridge_chain, goal_support_refs or []

    keep_indices = set()
    coordinate_check_len = len(coordinate_checks)

    def collect_ref(ref_text):
        match = DOSSIER_SUPPORT_REF_RE.fullmatch(str(ref_text or "").strip())
        if not match or match.group(1).lower() != "coordinate_checks":
            return None
        index, index_error = _resolve_dossier_support_index(int(match.group(2)), coordinate_check_len)
        if index_error:
            return None
        return index

    for step in bridge_chain or []:
        for ref in step.get("supports", []) or []:
            index = collect_ref(ref)
            if index is not None:
                keep_indices.add(index)
    for ref in goal_support_refs or []:
        index = collect_ref(ref)
        if index is not None:
            keep_indices.add(index)

    if not keep_indices:
        return [], bridge_chain, goal_support_refs or []

    sorted_keep_indices = sorted(keep_indices)
    old_to_new_index = {
        old_index: new_index
        for new_index, old_index in enumerate(sorted_keep_indices)
    }

    def rewrite_refs(refs):
        rewritten = []
        for ref in refs or []:
            index = collect_ref(ref)
            if index is None:
                rewritten.append(ref)
                continue
            if index in old_to_new_index:
                rewritten.append(f"coordinate_checks[{old_to_new_index[index] + 1}]")
        return rewritten

    pruned_bridge_chain = []
    for step in bridge_chain or []:
        pruned_bridge_chain.append(
            {
                **step,
                "supports": rewrite_refs(step.get("supports", [])),
            }
        )
    pruned_goal_support_refs = rewrite_refs(goal_support_refs or [])
    pruned_coordinate_checks = [coordinate_checks[index] for index in sorted_keep_indices]
    return pruned_coordinate_checks, pruned_bridge_chain, pruned_goal_support_refs


def build_aux_goal_bridge_tail_relations(
    proof_guidance,
    goal_finish,
    aux_points,
    known_points,
    max_items=3,
):
    normalized_goal_finish = normalize_relation_surface(goal_finish or "").strip()
    aux_point_set = {
        point.lower()
        for point in (aux_points or [])
        if isinstance(point, str) and point.strip()
    }
    if not normalized_goal_finish or not aux_point_set:
        return []

    ordered_route_relations = [
        normalize_relation_surface(relation).strip()
        for relation in (proof_guidance or {}).get("ordered_route_relations", [])
        if isinstance(relation, str) and relation.strip()
    ]
    if not ordered_route_relations:
        return []

    target_segments = set(extract_relation_segment_tokens(normalized_goal_finish))
    target_points = extract_point_mentions(normalized_goal_finish, known_points)
    selected = []
    seen_relations = {normalized_goal_finish.lower()}

    for relation in reversed(ordered_route_relations):
        lowered_relation = relation.lower()
        if lowered_relation in seen_relations:
            continue
        if relation_contains_forbidden_thinking_pattern(relation):
            continue
        relation_points = extract_point_mentions(relation, known_points)
        relation_segments = extract_relation_segment_tokens(relation)
        if not (relation_points & aux_point_set):
            continue
        if not ((relation_segments & target_segments) or (relation_points & target_points)):
            continue
        selected.append(relation)
        seen_relations.add(lowered_relation)
        target_segments.update(relation_segments)
        target_points.update(relation_points)
        if len(selected) >= max_items:
            break

    return list(reversed(selected))


def relation_has_tautological_ratio_side(relation):
    match = re.search(
        r"\bratio\s+([a-z0-9]+)\s+to\s+([a-z0-9]+)\s+equals\s+ratio\s+([a-z0-9]+)\s+to\s+([a-z0-9]+)\b",
        normalize_relation_surface(relation or ""),
        re.IGNORECASE,
    )
    if not match:
        return False
    left_num, left_den, right_num, right_den = [
        item.lower()
        for item in match.groups()
    ]
    return left_num == left_den or right_num == right_den


def build_dossier_goal_tail_relations(
    proof_guidance,
    goal_finish,
    known_points,
):
    normalized_goal_finish = normalize_relation_surface(goal_finish or "").strip()
    goal_tail_relations = []
    for relation in (proof_guidance or {}).get("goal_finish_relations", []) or []:
        if not isinstance(relation, str) or not relation.strip():
            continue
        normalized_relation = normalize_relation_surface(relation)
        if relation_contains_forbidden_thinking_pattern(normalized_relation):
            continue
        if relations_semantically_match(normalized_relation, normalized_goal_finish, known_points):
            continue
        if normalized_relation.lower() not in {item.lower() for item in goal_tail_relations}:
            goal_tail_relations.append(normalized_relation)

    if (
        goal_tail_relations
        and "ratio" in relation_text_keywords(goal_tail_relations[0])
        and relation_has_tautological_ratio_side(goal_tail_relations[0])
    ):
        ordered_route_relations = [
            normalize_relation_surface(relation).strip()
            for relation in (proof_guidance or {}).get("ordered_route_relations", [])
            if isinstance(relation, str) and relation.strip()
        ]
        for route_index, route_relation in enumerate(ordered_route_relations):
            if not relations_semantically_match(route_relation, goal_tail_relations[0], known_points):
                continue
            target_segments = extract_relation_segment_tokens(goal_tail_relations[0])
            for prerequisite_relation in reversed(ordered_route_relations[:route_index]):
                if "similar" not in relation_text_keywords(prerequisite_relation):
                    continue
                if len(extract_relation_segment_tokens(prerequisite_relation) & target_segments) < 2:
                    continue
                goal_tail_relations = [prerequisite_relation] + goal_tail_relations[1:]
                break
            break
    return goal_tail_relations


def count_ordered_relation_matches(candidate_relations, target_relations, point_names):
    search_start = 0
    matches = 0
    for target_relation in target_relations or []:
        for idx in range(search_start, len(candidate_relations or [])):
            candidate_relation = candidate_relations[idx]
            if relations_semantically_match(target_relation, candidate_relation, point_names):
                matches += 1
                search_start = idx + 1
                break
    return matches


def count_tail_suffix_relation_matches(candidate_relations, target_relations, point_names):
    suffix_matches = 0
    candidate_tail = list(candidate_relations or [])
    target_tail = list(target_relations or [])
    while candidate_tail and target_tail:
        if not relations_semantically_match(candidate_tail[-1], target_tail[-1], point_names):
            break
        suffix_matches += 1
        candidate_tail.pop()
        target_tail.pop()
    return suffix_matches


def score_dossier_plan_goal_tail_route(plan, proof_guidance, visible_goal, known_points):
    if not isinstance(plan, dict):
        return (-1, -1, -1, -1, -1)

    goal_finish = normalize_relation_surface(
        plan.get("goal_finish")
        or summarize_aux_clause(visible_goal)
        or ""
    ).strip()
    route_relations = [
        normalize_relation_surface(step.get("claim", "")).strip()
        for step in (plan.get("bridge_chain") or [])
        if isinstance(step, dict) and step.get("claim")
    ]
    route_relations.extend(
        normalize_relation_surface(step.get("claim", "")).strip()
        for step in (plan.get("goal_closure") or [])
        if (
            isinstance(step, dict)
            and step.get("claim")
            and not relations_semantically_match(step.get("claim", ""), goal_finish, known_points)
        )
    )
    goal_tail_relations = build_dossier_goal_tail_relations(
        proof_guidance,
        goal_finish,
        known_points,
    )
    if not goal_tail_relations:
        return (0, 0, 0, 0, -len(route_relations))

    ordered_matches = count_ordered_relation_matches(
        route_relations,
        goal_tail_relations,
        known_points,
    )
    suffix_matches = count_tail_suffix_relation_matches(
        route_relations,
        goal_tail_relations,
        known_points,
    )
    exact_matches = sum(
        1
        for target_relation in goal_tail_relations
        if any(
            relations_semantically_match(target_relation, candidate_relation, known_points)
            for candidate_relation in route_relations
        )
    )
    extra_route_steps = max(0, len(route_relations) - len(goal_tail_relations))
    return (
        ordered_matches,
        suffix_matches,
        exact_matches,
        -extra_route_steps,
        -len(route_relations),
    )


def compose_aux_goal_tail_relations(aux_tail_relations, goal_tail_relations, visible_goal):
    aux_tail_relations = [
        relation
        for relation in (aux_tail_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    goal_tail_relations = [
        relation
        for relation in (goal_tail_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    if not aux_tail_relations:
        return goal_tail_relations, goal_tail_relations
    if not goal_tail_relations:
        return aux_tail_relations, []

    appended_goal_tail_relations = list(goal_tail_relations)
    goal_predicate = parse_goal_expression(visible_goal or "").get("predicate")
    if (
        goal_predicate == "eqratio"
        and len(appended_goal_tail_relations) >= 2
        and "collinear" in relation_text_keywords(appended_goal_tail_relations[0])
    ):
        appended_goal_tail_relations = appended_goal_tail_relations[-2:]

    combined_tail_relations = list(aux_tail_relations)
    combined_lower = {relation.lower() for relation in combined_tail_relations}
    for relation in appended_goal_tail_relations:
        if relation.lower() not in combined_lower:
            combined_tail_relations.append(relation)
            combined_lower.add(relation.lower())
    return combined_tail_relations, appended_goal_tail_relations


def merge_dossier_visible_relations(primary_relations, fallback_relations, max_items=12):
    merged_relations = []
    seen = set()
    for relation in list(primary_relations or []) + list(fallback_relations or []):
        if not isinstance(relation, str) or not relation.strip():
            continue
        normalized_relation = normalize_relation_surface(relation).strip()
        lowered_relation = normalized_relation.lower()
        if not normalized_relation or lowered_relation in seen:
            continue
        seen.add(lowered_relation)
        merged_relations.append(normalized_relation)
        if len(merged_relations) >= max_items:
            break
    return merged_relations


def tail_route_can_start_without_prefix(
    tail_relations,
    goal_finish,
    visible_facts,
    image_scan,
    coordinate_candidates,
    point_coords,
    aux_immediate_effects,
    known_points,
):
    candidate_tail_relations = [
        normalize_relation_surface(relation).strip()
        for relation in (tail_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    if not candidate_tail_relations:
        return False

    coordinate_check_targets = [normalize_relation_surface(goal_finish or "").strip()]
    if candidate_tail_relations[-1]:
        coordinate_check_targets.insert(0, candidate_tail_relations[-1])
    provisional_coordinate_checks = build_scripted_dossier_coordinate_checks(
        coordinate_candidates,
        point_coords,
        visible_facts,
        image_scan,
        coordinate_check_targets,
        max_items=4,
    )
    support_catalog = build_dossier_relation_ref_catalog(
        visible_facts,
        image_scan,
        provisional_coordinate_checks,
        aux_immediate_effects,
        [],
    )
    if not support_catalog:
        return False

    first_relation = candidate_tail_relations[0]
    next_relation = (
        candidate_tail_relations[1]
        if len(candidate_tail_relations) > 1
        else normalize_relation_surface(goal_finish or "").strip()
    )
    max_supports = min(
        compute_bridge_step_required_support_cap({"relation": first_relation}),
        max(1, len(support_catalog)),
    )
    support_refs = select_dossier_support_refs_for_relation(
        first_relation,
        support_catalog,
        known_points,
        preferred_supports=[],
        next_target_relation=next_relation,
        max_supports=max_supports,
    )
    resolved_support_relations = [
        item.get("relation", "")
        for item in support_catalog
        if item.get("ref") in set(support_refs)
    ]
    unsupported_segments = find_unsupported_bridge_relation_segments(
        {
            "relation": first_relation,
            "approved_route_relation": first_relation,
        },
        resolved_support_relations,
    )
    return len(unsupported_segments) <= 1


def maybe_choose_scripted_dossier_plan(
    record,
    aux_part,
    sanitized_rest,
    point_coords,
    visible_goal,
    visible_text_facts,
    visible_premise_summaries,
    live_plan,
    logger,
):
    if not isinstance(live_plan, dict):
        return live_plan, None

    skeleton_ok, skeleton_message, scripted_dossier = build_scripted_dossier_skeleton(
        record,
        aux_part,
        sanitized_rest,
        point_coords,
        visible_goal,
        visible_text_facts=visible_text_facts,
        visible_premise_summaries=visible_premise_summaries,
    )
    if not skeleton_ok:
        logger.warning(
            "[plan] Scripted dossier candidate unavailable for live-plan comparison: %s",
            skeleton_message,
        )
        return live_plan, None

    known_points = extract_visible_point_names(point_coords) + [
        point.lower()
        for point in extract_aux_new_points(aux_part or "")
    ]
    proof_guidance = build_hidden_proof_guidance(
        sanitized_rest,
        aux_part,
        visible_goal,
    )
    goal_tail_relations = build_dossier_goal_tail_relations(
        proof_guidance,
        scripted_dossier.get("goal_finish", ""),
        known_points,
    )
    if not goal_tail_relations:
        return live_plan, None

    live_score = score_dossier_plan_goal_tail_route(
        live_plan,
        proof_guidance,
        visible_goal,
        known_points,
    )
    scripted_score = score_dossier_plan_goal_tail_route(
        scripted_dossier,
        proof_guidance,
        visible_goal,
        known_points,
    )
    if scripted_score > live_score and scripted_score[0] == len(goal_tail_relations):
        logger.warning(
            "[plan] Replacing live validated dossier with scripted skeleton based on stronger goal-tail route (%s -> %s)",
            live_score,
            scripted_score,
        )
        return scripted_dossier, "scripted_preferred"

    return live_plan, None


def build_scripted_dossier_skeleton(
    record,
    aux_part,
    sanitized_rest,
    point_coords,
    visible_goal,
    visible_text_facts=None,
    visible_premise_summaries=None,
):
    visible_text_facts = visible_text_facts or build_visible_text_facts(record)
    visible_premise_summaries = visible_premise_summaries or [
        fact.get("relation", "")
        for fact in visible_text_facts
        if isinstance(fact, dict) and fact.get("relation")
    ]
    coordinate_candidates = build_hidden_coordinate_candidates(
        point_coords,
        max_items=64,
        relax_type_limits=True,
    )
    scripted_plan = build_scripted_plan_skeleton(
        record,
        aux_part,
        sanitized_rest,
        point_coords,
        coordinate_candidates,
        visible_premise_summaries,
        visible_goal,
    )
    proof_guidance = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    visible_facts = merge_dossier_visible_relations(
        scripted_plan.get("visible_relations", []),
        visible_premise_summaries,
        max_items=12,
    )
    image_scan = [
        observation.get("relation", "")
        for observation in scripted_plan.get("observation_relations", [])
        if isinstance(observation, dict) and observation.get("relation")
    ]
    if not image_scan:
        image_scan = [
            relation
            for relation in scripted_plan.get("coordinate_relations", [])
            if isinstance(relation, str) and relation.strip()
        ]
    aux_immediate_effects = [
        relation
        for relation in scripted_plan.get("aux_direct_relations", [])
        if isinstance(relation, str) and relation.strip()
    ]
    aux_points = [
        point.lower()
        for point in extract_aux_new_points(aux_part or "")
    ]
    known_points = extract_visible_point_names(point_coords) + aux_points
    normalized_goal_finish = normalize_relation_surface(scripted_plan.get("goal_finish", ""))
    goal_tail_relations = build_dossier_goal_tail_relations(
        proof_guidance,
        normalized_goal_finish,
        known_points,
    )
    goal_tail_mentions_aux = any(
        any(point in relation.lower() for point in aux_points)
        for relation in goal_tail_relations
    )
    tail_relations_for_chain = goal_tail_relations
    aux_goal_bridge_tail_relations = []
    appended_goal_tail_relations = goal_tail_relations
    if aux_points and goal_tail_relations and not goal_tail_mentions_aux:
        aux_goal_bridge_tail_relations = build_aux_goal_bridge_tail_relations(
            proof_guidance,
            normalized_goal_finish,
            aux_points,
            known_points,
            max_items=3,
        )
        if aux_goal_bridge_tail_relations:
            tail_relations_for_chain, appended_goal_tail_relations = compose_aux_goal_tail_relations(
                aux_goal_bridge_tail_relations,
                goal_tail_relations,
                visible_goal,
            )
    tail_only_viable = tail_route_can_start_without_prefix(
        tail_relations_for_chain,
        normalized_goal_finish,
        visible_facts,
        image_scan,
        coordinate_candidates,
        point_coords,
        aux_immediate_effects,
        known_points,
    )

    base_bridge_steps = [
        step
        for step in scripted_plan.get("bridge_steps", [])
        if isinstance(step, dict) and step.get("relation")
    ]
    max_bridge_steps = 6
    keep_prefix_count = max_bridge_steps - len(tail_relations_for_chain)
    min_prefix_count = 1 if base_bridge_steps and extract_aux_new_points(aux_part or "") else 0
    keep_prefix_count = max(min_prefix_count, keep_prefix_count)
    keep_prefix_count = min(len(base_bridge_steps), keep_prefix_count)
    merged_aux_goal_tail = bool(
        aux_goal_bridge_tail_relations
        and len(tail_relations_for_chain) > len(aux_goal_bridge_tail_relations)
    )
    tail_chain_starts_from_aux = bool(
        tail_relations_for_chain
        and any(point in tail_relations_for_chain[0].lower() for point in aux_points)
    )
    if (
        merged_aux_goal_tail
        and tail_chain_starts_from_aux
        and appended_goal_tail_relations
        and tail_only_viable
        and count_ordered_relation_matches(
            tail_relations_for_chain,
            appended_goal_tail_relations,
            known_points,
        ) == len(appended_goal_tail_relations)
    ):
        keep_prefix_count = 0
    if (
        goal_tail_mentions_aux
        and tail_relations_for_chain == goal_tail_relations
        and len(tail_relations_for_chain) >= 3
        and tail_only_viable
        and "similar" in relation_text_keywords(tail_relations_for_chain[0])
    ):
        keep_prefix_count = 0
    selected_bridge_specs = [
        {
            "relation": step.get("relation", ""),
            "preferred_supports": step.get("required_supports") or step.get("depends_on") or [],
            "why_next": step.get("why_it_helps", ""),
            "source": "base",
        }
        for step in base_bridge_steps[:keep_prefix_count]
    ]
    remaining_slots = max(0, max_bridge_steps - len(selected_bridge_specs))
    tail_relations_to_add = tail_relations_for_chain[-remaining_slots:] if remaining_slots else []
    for idx, relation in enumerate(tail_relations_to_add):
        if any(
            relations_semantically_match(
                relation,
                candidate.get("relation", ""),
                known_points,
            )
            for candidate in selected_bridge_specs
        ):
            continue
        next_relation = (
            tail_relations_to_add[idx + 1]
            if idx + 1 < len(tail_relations_to_add)
            else normalized_goal_finish
        )
        selected_bridge_specs.append(
            {
                "relation": relation,
                "preferred_supports": [],
                "why_next": build_canonical_bridge_unlock(
                    next_relation,
                    final_step=(idx == len(tail_relations_to_add) - 1),
                ),
                "source": "tail",
            }
        )

    coordinate_check_targets = [normalized_goal_finish]
    if merged_aux_goal_tail and aux_goal_bridge_tail_relations:
        coordinate_check_targets.insert(0, aux_goal_bridge_tail_relations[-1])
    elif tail_relations_for_chain:
        coordinate_check_targets.insert(0, tail_relations_for_chain[-1])
    elif selected_bridge_specs:
        coordinate_check_targets.insert(0, selected_bridge_specs[-1].get("relation", ""))

    coordinate_checks = build_scripted_dossier_coordinate_checks(
        coordinate_candidates,
        point_coords,
        visible_facts,
        image_scan,
        coordinate_check_targets,
        max_items=4,
    )

    raw_bridge_chain = []
    prior_bridge_claims = []
    for step_idx, step in enumerate(selected_bridge_specs):
        if not isinstance(step, dict):
            continue
        support_catalog = build_dossier_relation_ref_catalog(
            visible_facts,
            image_scan,
            coordinate_checks,
            aux_immediate_effects,
            prior_bridge_claims,
        )
        next_relation = (
            selected_bridge_specs[step_idx + 1]["relation"]
            if step_idx + 1 < len(selected_bridge_specs)
            else normalized_goal_finish
        )
        max_supports = min(
            compute_bridge_step_required_support_cap({"relation": step.get("relation", "")}),
            max(1, len(support_catalog)),
        )
        support_refs = select_dossier_support_refs_for_relation(
            step.get("relation", ""),
            support_catalog,
            known_points,
            preferred_supports=step.get("preferred_supports"),
            next_target_relation=next_relation,
            max_supports=max_supports,
        )
        if not support_refs and support_catalog:
            support_refs = [support_catalog[0]["ref"]]
        resolved_support_relations = [
            item.get("relation", "")
            for item in support_catalog
            if item.get("ref") in set(support_refs)
        ]
        unsupported_segments = find_unsupported_bridge_relation_segments(
            {
                "relation": step.get("relation", ""),
                "approved_route_relation": step.get("relation", ""),
            },
            resolved_support_relations,
        )
        if step.get("source") == "tail" and len(unsupported_segments) > 1:
            continue
        raw_bridge_chain.append(
            {
                "claim": step.get("relation", ""),
                "supports": support_refs,
                "why_next": step.get("why_it_helps", "this moves the route one step closer to the visible goal."),
                "_script_source": step.get("source", "base"),
            }
        )
        prior_bridge_claims.append(step.get("relation", ""))
    goal_support_catalog = build_dossier_relation_ref_catalog(
        visible_facts,
        image_scan,
        coordinate_checks,
        aux_immediate_effects,
        prior_bridge_claims,
    )
    goal_support_refs = select_dossier_support_refs_for_relation(
        normalized_goal_finish,
        goal_support_catalog,
        known_points,
        preferred_supports=[],
        max_supports=min(4, max(1, len(goal_support_catalog))),
    )
    if not goal_support_refs and goal_support_catalog:
        goal_support_refs = [goal_support_catalog[-1]["ref"]]
    raw_bridge_chain, goal_support_refs = prune_unreferenced_dossier_bridge_chain(
        raw_bridge_chain,
        goal_support_refs,
        aux_points=extract_aux_new_points(aux_part or ""),
    )
    coordinate_checks, raw_bridge_chain, goal_support_refs = prune_unreferenced_dossier_coordinate_checks(
        coordinate_checks,
        raw_bridge_chain,
        goal_support_refs,
    )

    raw_dossier = {
        "visible_facts": visible_facts,
        "image_scan": image_scan,
        "coordinate_checks": coordinate_checks,
        "goal_obstacle": scripted_plan.get("goal_bottleneck") or build_canonical_goal_bottleneck(visible_goal),
        "aux_motivation": scripted_plan.get("helper_idea") or build_safe_dossier_aux_motivation(aux_part or "", visible_goal),
        "construction": scripted_plan.get("construction") or build_canonical_construction(aux_part or ""),
        "aux_immediate_effects": aux_immediate_effects,
        "bridge_chain": raw_bridge_chain,
        "goal_closure": [
            {
                "claim": normalized_goal_finish,
                "supports": goal_support_refs,
                "why_next": "this is the target relation.",
            }
        ],
    }
    ok, message, cleaned_dossier = validate_dossier_plan_response(
        raw_dossier,
        point_coords,
        visible_goal=visible_goal,
        aux_part=aux_part,
        visible_text_facts=visible_text_facts,
    )
    if not ok:
        return False, f"scripted dossier skeleton invalid: {message}", None
    return True, "Valid scripted dossier skeleton", cleaned_dossier


def build_scripted_dossier_writer_body(plan):
    if not isinstance(plan, dict):
        return ""

    def clean_text(value):
        if not isinstance(value, str):
            return ""
        return value.strip().rstrip(".")

    coordinate_relations = [
        clean_text(relation)
        for relation in (plan.get("coordinate_relations") or [])
        if clean_text(relation)
    ]

    def relation_matches_coordinate(relation, point_names):
        cleaned_relation = clean_text(relation)
        if not cleaned_relation:
            return False
        for coordinate_relation in coordinate_relations:
            if cleaned_relation.lower() == coordinate_relation.lower():
                return True
            if relations_semantically_match(cleaned_relation, coordinate_relation, point_names):
                return True
        return False

    def choose_support_texts(step, max_items=3, force_coordinate=False, goal_step=False):
        claim = clean_text(step.get("claim"))
        required = [
            clean_text(relation)
            for relation in (step.get("required_supports") or step.get("resolved_supports") or [])
            if clean_text(relation)
        ]
        resolved_supports = [
            clean_text(relation)
            for relation in (step.get("resolved_supports") or [])
            if clean_text(relation)
        ]
        support_refs = [
            str(ref).strip()
            for ref in (step.get("supports") or [])
            if str(ref).strip()
        ]
        if not claim or not (required or resolved_supports):
            return []

        def ref_priority(ref):
            lowered = str(ref or "").lower()
            if lowered.startswith("bridge_chain["):
                return 3
            if lowered.startswith("aux_immediate_effects["):
                return 2
            if lowered.startswith("visible_facts["):
                return 1
            if lowered.startswith("image_scan["):
                return 0
            if lowered.startswith("coordinate_checks["):
                return -2
            return 0

        candidate_map = {}
        source_pairs = (
            list(zip(support_refs, resolved_supports))
            if resolved_supports
            else [("", relation) for relation in required]
        )
        for ref, relation in source_pairs:
            lowered_relation = relation.lower()
            candidate = {
                "ref": ref,
                "relation": relation,
                "segments": extract_relation_segment_tokens(relation),
            }
            candidate_key = (
                ref_priority(ref),
                -len(relation),
                relation.lower(),
            )
            if (
                lowered_relation not in candidate_map
                or candidate_key > candidate_map[lowered_relation][0]
            ):
                candidate_map[lowered_relation] = (candidate_key, candidate)
        candidates = [candidate for _, candidate in candidate_map.values()]
        if not candidates:
            return []

        point_names = extract_relation_point_names(
            " ".join(
                [claim]
                + required
                + [candidate.get("relation", "") for candidate in candidates]
            )
        )
        non_tautological_candidates = [
            candidate
            for candidate in candidates
            if not relations_semantically_match(
                candidate.get("relation", ""),
                claim,
                point_names,
            )
        ]
        fallback_candidates = candidates
        candidates = non_tautological_candidates or candidates
        claim_segments = extract_relation_segment_tokens(claim)
        claim_keywords = relation_text_keywords(claim)
        complex_claim = bool(claim_keywords & {"angle", "ratio", "similar"})
        min_mentions = int(step.get("min_support_mentions") or 1)
        base_target = max(
            min_mentions,
            2 if complex_claim and len(candidates) >= 2 else 1,
        )
        if goal_step and claim_keywords & {"angle", "similar"} and len(candidates) >= 3:
            base_target = max(base_target, 3)
        if claim_keywords & {"parallel", "perpendicular"} and len(candidates) >= 2:
            base_target = max(base_target, 2)
        target_cap = min(len(candidates), max_items)

        def select_next_candidate(remaining, covered_segments):
            best_candidate = None
            best_key = None
            for candidate in remaining:
                relation = candidate.get("relation", "")
                relation_segments = candidate.get("segments") or set()
                new_segments = len((relation_segments & claim_segments) - covered_segments)
                required_match = 0
                for required_relation in required:
                    if relation.lower() == required_relation.lower():
                        required_match = 1
                        break
                    if relations_semantically_match(relation, required_relation, point_names):
                        required_match = 1
                        break
                key = (
                    new_segments,
                    required_match,
                    ref_priority(candidate.get("ref", "")),
                    score_support_relation(relation, claim, point_names),
                    -len(relation),
                    relation.lower(),
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best_candidate = candidate
            return best_candidate

        selected_relations = []
        covered_segments = set()
        remaining = candidates[:]

        initial_target = min(base_target, target_cap)
        while remaining and len(selected_relations) < initial_target:
            best_candidate = select_next_candidate(remaining, covered_segments)
            if best_candidate is None:
                break
            selected_relations.append(best_candidate.get("relation", ""))
            covered_segments.update((best_candidate.get("segments") or set()) & claim_segments)
            remaining = [
                candidate
                for candidate in remaining
                if candidate.get("relation", "").lower() != best_candidate.get("relation", "").lower()
            ]

        min_segment_coverage = 0
        if complex_claim and claim_segments:
            min_segment_coverage = 3 if len(claim_segments) >= 4 else min(2, len(claim_segments))
        while (
            remaining
            and len(selected_relations) < target_cap
            and len(covered_segments) < min_segment_coverage
        ):
            best_candidate = select_next_candidate(remaining, covered_segments)
            if best_candidate is None:
                break
            selected_relations.append(best_candidate.get("relation", ""))
            covered_segments.update((best_candidate.get("segments") or set()) & claim_segments)
            remaining = [
                candidate
                for candidate in remaining
                if candidate.get("relation", "").lower() != best_candidate.get("relation", "").lower()
            ]

        if (
            force_coordinate
            and coordinate_relations
            and not any(relation_matches_coordinate(relation, point_names) for relation in selected_relations)
        ):
            coordinate_candidates = [
                candidate
                for candidate in candidates
                if relation_matches_coordinate(candidate.get("relation", ""), point_names)
                and (
                    extract_relation_segment_tokens(candidate.get("relation", "")) & claim_segments
                )
                and candidate.get("relation", "") not in selected_relations
            ]
            if coordinate_candidates:
                coordinate_candidates.sort(
                    key=lambda candidate: (
                        score_support_relation(candidate.get("relation", ""), claim, point_names),
                        len((candidate.get("segments") or set()) & claim_segments),
                        ref_priority(candidate.get("ref", "")),
                        -len(candidate.get("relation", "")),
                        candidate.get("relation", "").lower(),
                    ),
                    reverse=True,
                )
                if len(selected_relations) < target_cap:
                    selected_relations.append(coordinate_candidates[0].get("relation", ""))
                else:
                    replace_idx = None
                    for idx, relation in enumerate(selected_relations):
                        if not relation_matches_coordinate(relation, point_names):
                            replace_idx = idx
                            break
                    if replace_idx is not None:
                        selected_relations[replace_idx] = coordinate_candidates[0].get("relation", "")

        if not selected_relations and fallback_candidates:
            selected_relations.append(fallback_candidates[0].get("relation", ""))

        return selected_relations

    def make_support_clause(relations):
        cleaned_relations = [clean_text(relation) for relation in relations if clean_text(relation)]
        if not cleaned_relations:
            return ""
        if len(cleaned_relations) == 1:
            return cleaned_relations[0]
        return join_natural_list(cleaned_relations)

    sentences = []
    obstacle = clean_text(plan.get("goal_obstacle") or plan.get("goal_bottleneck"))
    observation_cues = [
        clean_text(relation)
        for relation in (plan.get("image_scan") or [])
        if clean_text(relation)
    ]
    if obstacle:
        if observation_cues:
            sentences.append(f"{obstacle}, and the figure also shows {observation_cues[0]}.")
        else:
            sentences.append(f"{obstacle}.")

    construction = clean_text(plan.get("construction"))
    if construction:
        sentences.append(f"{construction.capitalize()}.")

    aux_effects = [
        clean_text(relation)
        for relation in (plan.get("aux_immediate_effects") or [])
        if clean_text(relation)
    ]
    if aux_effects:
        if len(aux_effects) == 1:
            sentences.append(f"This immediately gives {aux_effects[0]}.")
        else:
            sentences.append(f"This immediately gives {make_support_clause(aux_effects[:2])}.")

    coordinate_reused = False
    bridge_steps = plan.get("bridge_chain", []) if isinstance(plan.get("bridge_chain"), list) else []
    for step_idx, step in enumerate(bridge_steps):
        claim = clean_text(step.get("claim"))
        if not claim:
            continue
        step_has_coordinate_support = any(
            str(ref).strip().lower().startswith("coordinate_checks[")
            for ref in (step.get("supports") or [])
        )
        force_coordinate = (
            bool(coordinate_relations)
            and step_has_coordinate_support
        )
        selected_supports = choose_support_texts(
            step,
            force_coordinate=force_coordinate,
        )
        if any(
            relation_matches_coordinate(
                relation,
                extract_relation_point_names(" ".join([claim] + selected_supports)),
            )
            for relation in selected_supports
        ):
            coordinate_reused = True
        support_clause = make_support_clause(selected_supports)
        if support_clause:
            sentences.append(f"Because {support_clause}, {claim}.")
        else:
            sentences.append(f"{claim.capitalize()}.")

    goal_steps = plan.get("goal_closure", []) if isinstance(plan.get("goal_closure"), list) else []
    for idx, step in enumerate(goal_steps):
        claim = clean_text(step.get("claim"))
        if not claim:
            continue
        step_has_coordinate_support = any(
            str(ref).strip().lower().startswith("coordinate_checks[")
            for ref in (step.get("supports") or [])
        )
        force_coordinate = (
            bool(coordinate_relations)
            and step_has_coordinate_support
        )
        selected_supports = choose_support_texts(
            step,
            max_items=4,
            force_coordinate=force_coordinate,
            goal_step=True,
        )
        if any(
            relation_matches_coordinate(
                relation,
                extract_relation_point_names(" ".join([claim] + selected_supports)),
            )
            for relation in selected_supports
        ):
            coordinate_reused = True
        support_clause = make_support_clause(selected_supports)
        prefix = "Finally" if idx == len(goal_steps) - 1 else "Next"
        if support_clause:
            sentences.append(f"{prefix}, because {support_clause}, {claim}.")
        else:
            sentences.append(f"{prefix}, {claim}.")

    return " ".join(sentence.strip() for sentence in sentences if sentence.strip())


def score_dossier_writer_body_plan_faithfulness(plan, body):
    if not isinstance(plan, dict) or not isinstance(body, str) or not body.strip():
        return (-1, -1, -1, -1, -1, -1, -1, -1, 0)

    sentences = split_into_sentences(body)
    search_start = 0
    bridge_quota_satisfied = 0
    bridge_support_mentions = 0
    bridge_realized = 0

    for step in plan.get("bridge_chain", []) if isinstance(plan.get("bridge_chain"), list) else []:
        claim = step.get("claim", "")
        required_supports = step.get("required_supports") or step.get("resolved_supports") or []
        min_support_mentions = int(step.get("min_support_mentions") or (1 if required_supports else 0))
        match_idx = None
        for sentence_idx in range(search_start, len(sentences)):
            if relation_mentioned_in_text(sentences[sentence_idx], claim):
                match_idx = sentence_idx
                break
        if match_idx is None:
            continue
        bridge_realized += 1
        grounded_supports = count_support_relation_mentions(
            sentences[match_idx],
            required_supports,
            target_relation=claim,
        )
        bridge_support_mentions += grounded_supports
        if grounded_supports >= min_support_mentions:
            bridge_quota_satisfied += 1
        search_start = match_idx + 1

    goal_quota_satisfied = 0
    goal_support_mentions = 0
    goal_realized = 0
    for step in plan.get("goal_closure", []) if isinstance(plan.get("goal_closure"), list) else []:
        claim = step.get("claim", "")
        required_supports = step.get("required_supports") or step.get("resolved_supports") or []
        min_support_mentions = int(step.get("min_support_mentions") or (1 if required_supports else 0))
        match_idx = None
        for sentence_idx in range(search_start, len(sentences)):
            if relation_mentioned_in_text(sentences[sentence_idx], claim):
                match_idx = sentence_idx
                break
        if match_idx is None:
            continue
        goal_realized += 1
        grounded_supports = count_support_relation_mentions(
            sentences[match_idx],
            required_supports,
            target_relation=claim,
        )
        goal_support_mentions += grounded_supports
        if grounded_supports >= min_support_mentions:
            goal_quota_satisfied += 1
        search_start = match_idx + 1

    aux_mentions = count_relation_mentions(body, plan.get("aux_immediate_effects") or [])
    observation_mentions = count_relation_mentions(body, plan.get("image_scan") or [])
    coordinate_mentions = count_relation_mentions(body, plan.get("coordinate_relations") or [])
    generic_penalty_count = sum(
        1
        for pattern in DOSSIER_WRITER_SEMANTIC_PENALTY_PATTERNS
        if pattern.search(body)
    )

    return (
        goal_quota_satisfied,
        bridge_quota_satisfied,
        goal_support_mentions,
        bridge_support_mentions,
        goal_realized,
        bridge_realized,
        aux_mentions + observation_mentions + coordinate_mentions,
        -generic_penalty_count,
        -len(body),
    )


def maybe_choose_scripted_dossier_writer_body(record, aux_part, visible_goal, plan, write_result, logger):
    if not isinstance(plan, dict):
        return write_result

    scripted_body = build_scripted_dossier_writer_body(plan)
    scripted_ok, scripted_message = validate_dossier_writer_body(
        scripted_body,
        visible_goal=visible_goal,
        plan=plan,
    )
    if not scripted_ok:
        logger.warning("[write] Scripted dossier writer fallback invalid: %s", scripted_message)
        return write_result

    if not write_result["success"]:
        logger.warning(
            "[write] Falling back to scripted dossier writer after writer failure: %s",
            write_result["error"],
        )
        return {
            "success": True,
            "output": scripted_body,
            "attempts_used": write_result["attempts_used"],
            "elapsed_seconds": write_result["elapsed_seconds"],
            "error": None,
        }

    coordinate_candidates = build_hidden_coordinate_candidates(
        get_point_coords(record),
        max_items=64,
        relax_type_limits=True,
    )
    live_audit = audit_generation_quality(
        record,
        {"plan_parsed": plan, "write_output": write_result.get("output") or ""},
        aux_part,
        coordinate_candidates=coordinate_candidates,
    )
    scripted_audit = audit_generation_quality(
        record,
        {"plan_parsed": plan, "write_output": scripted_body},
        aux_part,
        coordinate_candidates=coordinate_candidates,
    )
    live_issue_count = len(live_audit.get("issues") or [])
    scripted_issue_count = len(scripted_audit.get("issues") or [])
    if scripted_issue_count < live_issue_count:
        logger.warning(
            "[write] Replacing live dossier writer body with scripted fallback body (%d audit issues -> %d)",
            live_issue_count,
            scripted_issue_count,
        )
        updated_result = dict(write_result)
        updated_result["output"] = scripted_body
        updated_result["error"] = None
        return updated_result

    live_score = score_dossier_writer_body_plan_faithfulness(plan, write_result.get("output") or "")
    scripted_score = score_dossier_writer_body_plan_faithfulness(plan, scripted_body)
    if scripted_score > live_score:
        logger.warning(
            "[write] Replacing live dossier writer body with scripted fallback body based on stronger plan grounding (%s -> %s)",
            live_score,
            scripted_score,
        )
        updated_result = dict(write_result)
        updated_result["output"] = scripted_body
        updated_result["error"] = None
        return updated_result
    return write_result


def canonicalize_dossier_image_scan(items, visible_points, min_len=1, max_len=4):
    raw_items = items if isinstance(items, list) else []
    cleaned = []
    used_lower = set()
    for idx, item in enumerate(raw_items[:max_len]):
        ok, _, cleaned_item = validate_descriptive_text(
            item,
            f"image_scan[{idx}]",
            min_chars=5,
            point_names=visible_points,
        )
        if not ok:
            continue
        normalized_item = normalize_relation_surface(cleaned_item)
        if not relation_keyword_present(normalized_item):
            continue
        mentioned = extract_point_mentions(normalized_item, visible_points)
        if len(mentioned) < 2:
            continue
        lowered = normalized_item.lower()
        if lowered in used_lower:
            continue
        cleaned.append(normalized_item)
        used_lower.add(lowered)
    if len(cleaned) < min_len:
        return False, "image_scan must include at least one concrete geometric relation cue", None
    return True, None, cleaned


def _resolve_dossier_support_index(raw_index: int, bucket_len: int):
    if raw_index < 0:
        return None, "support indices must be non-negative"
    if raw_index == 0:
        if bucket_len <= 0:
            return None, "supports references an unavailable earlier item"
        return 0, None
    normalized_index = raw_index - 1
    if normalized_index >= bucket_len:
        return None, "supports references an unknown item"
    return normalized_index, None


def _resolve_dossier_support_ref(
    ref_text,
    cleaned_visible_facts,
    cleaned_image_scan,
    cleaned_coordinate_checks,
    cleaned_aux_effects,
    cleaned_bridge_chain,
):
    match = DOSSIER_SUPPORT_REF_RE.fullmatch(str(ref_text or "").strip())
    if not match:
        return None, (
            "supports must use only visible_facts[i], image_scan[i], coordinate_checks[i], "
            "aux_immediate_effects[i], or earlier bridge_chain[i]"
        )
    bucket_name = match.group(1).lower()
    raw_index = int(match.group(2))
    if bucket_name == "visible_facts":
        index, index_error = _resolve_dossier_support_index(raw_index, len(cleaned_visible_facts))
        if index_error:
            return None, "supports references unknown visible_facts item"
        return cleaned_visible_facts[index], None
    if bucket_name == "image_scan":
        index, index_error = _resolve_dossier_support_index(raw_index, len(cleaned_image_scan))
        if index_error:
            return None, "supports references unknown image_scan item"
        return cleaned_image_scan[index], None
    if bucket_name == "coordinate_checks":
        index, index_error = _resolve_dossier_support_index(raw_index, len(cleaned_coordinate_checks))
        if index_error:
            return None, "supports references unknown coordinate_checks item"
        return cleaned_coordinate_checks[index]["relation"], None
    if bucket_name == "aux_immediate_effects":
        index, index_error = _resolve_dossier_support_index(raw_index, len(cleaned_aux_effects))
        if index_error:
            return None, "supports references unknown aux_immediate_effects item"
        return cleaned_aux_effects[index], None
    if bucket_name == "bridge_chain":
        index, index_error = _resolve_dossier_support_index(raw_index, len(cleaned_bridge_chain))
        if index_error:
            return None, "supports may reference only earlier bridge_chain items"
        return cleaned_bridge_chain[index]["claim"], None
    return None, "unsupported support reference bucket"


def validate_dossier_plan_response(
    output_text: str,
    point_coords,
    visible_goal="",
    aux_part=None,
    coordinate_candidates=None,
    sanitized_rest=None,
    visible_premise_summaries=None,
    visible_text_facts=None,
):
    del coordinate_candidates, sanitized_rest, visible_premise_summaries
    dossier = output_text if isinstance(output_text, dict) else extract_json_object(output_text)
    if not isinstance(dossier, dict):
        return False, "Planner must return a single JSON object", None

    visible_points = extract_visible_point_names(point_coords)
    aux_points = [point.lower() for point in extract_aux_new_points(aux_part or "")]
    known_points = visible_points + aux_points
    limits = compute_plan_complexity_limits(point_coords, visible_goal=visible_goal, aux_part=aux_part)
    max_bridge_steps = max(6, limits["bridge_steps_max"])
    required_keys = [
        "visible_facts",
        "image_scan",
        "goal_obstacle",
        "aux_motivation",
        "construction",
        "aux_immediate_effects",
        "bridge_chain",
        "goal_closure",
    ]
    missing = [key for key in required_keys if key not in dossier]
    if missing:
        return False, f"Dossier JSON missing keys: {missing}", None

    max_visible_facts = min(12, max(6, len(dossier.get("visible_facts") or []), limits["visible_relations_max"]))
    ok, message, cleaned_visible_facts = validate_relation_list(
        dossier.get("visible_facts"),
        "visible_facts",
        visible_points,
        min_len=1,
        max_len=max_visible_facts,
        min_chars=5,
    )
    if not ok:
        return False, message, None
    if visible_text_facts:
        unmatched_visible_facts = [
            relation
            for relation in cleaned_visible_facts
            if not any(
                relations_semantically_match(
                    relation,
                    item.get("relation", ""),
                    visible_points,
                )
                for item in visible_text_facts
                if isinstance(item, dict) and item.get("relation")
            )
        ]
        if unmatched_visible_facts:
            return False, "visible_facts must stay grounded in public problem facts", None

    max_image_scan = min(6, max(3, len(dossier.get("image_scan") or []), limits["coordinate_relations_max"] + 1))
    ok, message, cleaned_image_scan = canonicalize_dossier_image_scan(
        dossier.get("image_scan"),
        visible_points,
        min_len=1,
        max_len=max_image_scan,
    )
    if not ok:
        return False, message, None

    cleaned_plan = {
        "generation_style": "dossier_v1",
        "dossier_version": "dossier_v1",
        "visible_facts": cleaned_visible_facts,
        "visible_relations": cleaned_visible_facts[:],
        "image_scan": cleaned_image_scan,
        "image_observations": cleaned_image_scan[:],
        "observation_relations": [
            {
                "id": f"obs_{idx + 1}",
                "relation": relation,
                "points": sorted(extract_point_mentions(relation, visible_points)),
            }
            for idx, relation in enumerate(cleaned_image_scan)
        ],
        "anchor_points": [],
        "anchor_relation": "",
    }

    for key in ["goal_obstacle", "aux_motivation", "construction"]:
        raw_value = dossier.get(key)
        if key == "aux_motivation":
            raw_value = raw_value or build_safe_dossier_aux_motivation(aux_part or "", visible_goal)
        ok, message, cleaned_value = validate_descriptive_text(
            raw_value,
            key,
            point_names=known_points,
        )
        if not ok and key == "aux_motivation":
            ok, message, cleaned_value = validate_descriptive_text(
                build_safe_dossier_aux_motivation(aux_part or "", visible_goal),
                key,
                point_names=known_points,
            )
        if not ok:
            return False, message, None
        cleaned_plan[key] = cleaned_value
    canonical_construction = build_canonical_construction(aux_part or "")
    if canonical_construction:
        cleaned_plan["construction"] = canonical_construction

    coordinate_checks = dossier.get("coordinate_checks") or []
    if not isinstance(coordinate_checks, list):
        return False, "coordinate_checks must be a list", None
    allowed_calc_types = {"parallel", "perpendicular", "equal_length", "midpoint", "collinear"}
    cleaned_checks = []
    for idx, check in enumerate(coordinate_checks[: limits["coordinate_relations_max"]]):
        if not isinstance(check, dict):
            return False, f"coordinate_checks[{idx}] must be an object", None
        calc_type = str(check.get("calc_type") or "").strip().lower()
        if calc_type not in allowed_calc_types:
            return False, f"coordinate_checks[{idx}].calc_type is unsupported", None
        ok, message, cleaned_relation = validate_descriptive_text(
            check.get("relation"),
            f"coordinate_checks[{idx}].relation",
            min_chars=5,
            point_names=visible_points,
        )
        if not ok:
            return False, message, None
        cleaned_relation = normalize_relation_surface(cleaned_relation)
        if not relation_keyword_present(cleaned_relation):
            return False, f"coordinate_checks[{idx}].relation must mention a concrete geometric relation", None
        points = [
            point.lower()
            for point in (check.get("points") or [])
            if isinstance(point, str) and point.lower() in point_coords
        ]
        min_point_count = 4 if calc_type in {"parallel", "perpendicular", "equal_length"} else 3
        if len(points) < min_point_count:
            return False, (
                f"coordinate_checks[{idx}].points must name at least {min_point_count} visible points"
            ), None
        if any(point in aux_points for point in points):
            return False, f"coordinate_checks[{idx}] must not assign coordinates to auxiliary points", None
        ok, message, why_it_matters = validate_descriptive_text(
            check.get("why_it_matters"),
            f"coordinate_checks[{idx}].why_it_matters",
            min_chars=8,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_item = {
            "relation": cleaned_relation,
            "points": points,
            "calc_type": calc_type,
            "render_mode": normalize_coordinate_render_mode("coordinate", calc_type),
            "why_it_matters": why_it_matters,
            "witness": build_coordinate_candidate_witness(
                {"relation_type": calc_type, "points": points},
                point_coords,
            ),
        }
        cleaned_item["rendered_text"] = render_coordinate_derivation_snippet(cleaned_item, point_coords)
        cleaned_checks.append(cleaned_item)
    cleaned_plan["coordinate_checks"] = cleaned_checks
    cleaned_plan["coordinate_derivations"] = cleaned_checks[:]
    cleaned_plan["coordinate_relations"] = [item["relation"] for item in cleaned_checks]

    aux_immediate_effects = canonicalize_aux_direct_relations(
        dossier.get("aux_immediate_effects"),
        aux_part or "",
        visible_points,
        preferred_immediate=build_aux_direct_consequences(aux_part or ""),
        min_len=limits["aux_direct_relations_min"],
        max_len=limits["aux_direct_relations_max"],
    )
    if not (
        limits["aux_direct_relations_min"] <= len(aux_immediate_effects) <= limits["aux_direct_relations_max"]
    ):
        return False, (
            "aux_immediate_effects must be a list with "
            f"{limits['aux_direct_relations_min']} to {limits['aux_direct_relations_max']} ordered direct consequences"
        ), None
    cleaned_aux_effects = []
    for idx, relation in enumerate(aux_immediate_effects):
        ok, message, cleaned_relation = validate_descriptive_text(
            relation,
            f"aux_immediate_effects[{idx}]",
            min_chars=5,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_relation = normalize_relation_surface(cleaned_relation)
        if not relation_keyword_present(cleaned_relation):
            return False, f"aux_immediate_effects[{idx}] must mention a concrete geometric relation", None
        ok, message = validate_aux_step_scope(cleaned_relation, aux_part or "", visible_points)
        if not ok:
            return False, f"aux_immediate_effects[{idx}] invalid: {message}", None
        cleaned_aux_effects.append(cleaned_relation)
    cleaned_plan["aux_immediate_effects"] = cleaned_aux_effects
    cleaned_plan["aux_direct_relations"] = cleaned_aux_effects[:]

    def clean_claim_steps(step_items, field_name, max_len, allow_empty=False, available_bridge_chain=None):
        if not isinstance(step_items, list):
            return False, f"{field_name} must be a list", None
        if not allow_empty and not step_items:
            return False, f"{field_name} must not be empty", None
        if len(step_items) > max_len:
            return False, f"{field_name} must contain at most {max_len} steps", None
        available_bridge_chain = available_bridge_chain or []
        cleaned_steps = []
        for idx, step in enumerate(step_items):
            if not isinstance(step, dict):
                return False, f"{field_name}[{idx}] must be an object", None
            if any(key not in step for key in ["claim", "supports", "why_next"]):
                return False, f"{field_name}[{idx}] must contain claim, supports, and why_next", None
            ok, message, cleaned_claim = validate_descriptive_text(
                step.get("claim"),
                f"{field_name}[{idx}].claim",
                min_chars=5,
                point_names=known_points,
            )
            if not ok:
                return False, message, None
            cleaned_claim = normalize_relation_surface(cleaned_claim)
            if not relation_keyword_present(cleaned_claim):
                return False, f"{field_name}[{idx}].claim must mention a concrete geometric relation", None
            supports = [str(ref).strip() for ref in (step.get("supports") or []) if str(ref).strip()]
            if not supports:
                return False, f"{field_name}[{idx}].supports must not be empty", None
            resolved_supports = []
            for ref in supports:
                resolved, support_error = _resolve_dossier_support_ref(
                    ref,
                    cleaned_visible_facts,
                    cleaned_image_scan,
                    cleaned_checks,
                    cleaned_aux_effects,
                    cleaned_steps if field_name == "bridge_chain" else available_bridge_chain,
                )
                if support_error:
                    return False, f"{field_name}[{idx}].supports invalid: {support_error}", None
                resolved_supports.append(resolved)
            step_contract = {
                "relation": cleaned_claim,
                "approved_route_relation": cleaned_claim,
                "depends_on": resolved_supports[:],
            }
            support_cap = min(
                compute_bridge_step_required_support_cap(step_contract),
                max(1, len(resolved_supports)),
            )
            required_supports = choose_required_supports_for_bridge_step(
                step_contract,
                known_points,
                max_supports=support_cap,
            ) or resolved_supports[:support_cap]
            unsupported_segments = find_unsupported_bridge_relation_segments(
                step_contract,
                required_supports,
            )
            if len(unsupported_segments) > 1:
                return False, (
                    f"{field_name}[{idx}].claim introduces unsupported angle/ratio/similar segments "
                    f"before its cited supports ground them: {unsupported_segments}"
                ), None
            min_support_mentions = compute_bridge_step_min_support_mentions(
                {
                    **step_contract,
                    "required_supports": required_supports,
                }
            )
            ok, message, cleaned_why_next = validate_descriptive_text(
                step.get("why_next"),
                f"{field_name}[{idx}].why_next",
                min_chars=8,
                point_names=known_points,
            )
            if not ok:
                return False, message, None
            cleaned_steps.append(
                {
                    "id": f"{field_name[0].upper()}{idx + 1}",
                    "claim": cleaned_claim,
                    "supports": supports,
                    "resolved_supports": resolved_supports,
                    "required_supports": required_supports,
                    "min_support_mentions": min_support_mentions,
                    "why_next": cleaned_why_next,
                }
            )
        return True, "ok", cleaned_steps

    ok, message, cleaned_bridge_chain = clean_claim_steps(
        dossier.get("bridge_chain"),
        "bridge_chain",
        max_len=max_bridge_steps,
    )
    if not ok:
        return False, message, None

    ok, message, cleaned_goal_closure = clean_claim_steps(
        dossier.get("goal_closure"),
        "goal_closure",
        max_len=3,
        available_bridge_chain=cleaned_bridge_chain,
    )
    if not ok:
        return False, message, None

    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec.get("points") or [])
    goal_keywords = goal_keyword_hints(visible_goal)
    final_goal_claim = cleaned_goal_closure[-1]["claim"]
    if goal_points:
        mentioned_goal_points = {point for point in goal_points if point in final_goal_claim.lower()}
        if len(mentioned_goal_points) < min(2, len(goal_points)):
            return False, "goal_closure must finish with goal-side points", None
    if goal_keywords and not any(keyword in final_goal_claim.lower() for keyword in goal_keywords):
        return False, "goal_closure must finish on the correct goal relation family", None

    if aux_points:
        construction_text = f"{cleaned_plan['aux_motivation']} {cleaned_plan['construction']}".lower()
        for label, keywords in build_aux_keyword_expectations(aux_part or ""):
            if not any(keyword in construction_text for keyword in keywords):
                return False, f"construction is missing an expected {label} cue", None
        preconstruction_texts = (
            cleaned_visible_facts
            + cleaned_image_scan
        )
        for point_name in aux_points:
            if any(re.search(rf"\b{re.escape(point_name)}\b", text.lower()) for text in preconstruction_texts):
                return False, f"new point '{point_name}' must not appear before the construction field", None
            if point_name not in cleaned_plan["construction"].lower():
                return False, f"construction must mention new point '{point_name}' explicitly", None
        if len(aux_points) > 1:
            stage_markers = ["first", "then", "next", "after", "finally", "together", "simultaneously"]
            combined_text = (
                f"{cleaned_plan['construction']} "
                f"{' '.join(cleaned_aux_effects)} "
                f"{' '.join(step['claim'] for step in cleaned_bridge_chain)}"
            ).lower()
            if not any(marker in combined_text for marker in stage_markers):
                return False, "multi-point auxiliary dossiers must describe a staged strategy", None

    referenced_coordinate_checks = set()
    referenced_aux_effects = set()
    for step in cleaned_bridge_chain + cleaned_goal_closure:
        for ref in step["supports"]:
            lowered = ref.lower()
            if lowered.startswith("coordinate_checks["):
                referenced_coordinate_checks.add(lowered)
            if lowered.startswith("aux_immediate_effects["):
                referenced_aux_effects.add(lowered)
    for idx, _ in enumerate(cleaned_checks, start=1):
        if f"coordinate_checks[{idx}]".lower() not in referenced_coordinate_checks:
            return False, f"coordinate_checks[{idx - 1}] must support a later bridge or closure step", None
    if cleaned_aux_effects and not referenced_aux_effects and aux_points:
        first_bridge_claim = cleaned_bridge_chain[0]["claim"].lower() if cleaned_bridge_chain else ""
        if not any(point in first_bridge_claim for point in aux_points):
            return False, "bridge_chain must reconnect the auxiliary consequences to the old figure", None

    cleaned_plan["bridge_chain"] = cleaned_bridge_chain
    cleaned_plan["goal_closure"] = cleaned_goal_closure
    cleaned_plan["goal_obstacle"] = cleaned_plan["goal_obstacle"]
    cleaned_plan["goal_bottleneck"] = cleaned_plan["goal_obstacle"]
    cleaned_plan["aux_motivation"] = cleaned_plan["aux_motivation"]
    cleaned_plan["helper_idea"] = cleaned_plan["aux_motivation"]
    cleaned_plan["figure_overview"] = " ".join(cleaned_image_scan[:2])
    cleaned_plan["coordinate_hints"] = build_canonical_coordinate_hint(cleaned_plan["coordinate_relations"])
    cleaned_plan["coverage_targets"] = {
        "coordinate_focus_relations": cleaned_plan["coordinate_relations"][:3],
        "observation_focus_relations": cleaned_image_scan[:3],
        "coordinate_reuse_min": 1 if cleaned_checks else 0,
        "goal_points": list(goal_points),
    }
    cleaned_plan["bridge_steps"] = [
        {
            "id": f"B{idx + 1}",
            "relation": step["claim"],
            "support_refs": step["supports"],
            "depends_on": step["resolved_supports"],
            "required_supports": step.get(
                "required_supports",
                step["resolved_supports"][: min(2, len(step["resolved_supports"]))],
            ),
            "min_support_mentions": step.get("min_support_mentions", 1),
            "why_it_helps": step["why_next"],
            "proof_alignment": "bridge",
            "focus_points": sorted(extract_point_mentions(step["claim"], known_points)),
            "approved_route_relation": step["claim"],
        }
        for idx, step in enumerate(cleaned_bridge_chain)
    ]
    cleaned_plan["bridge_relations"] = [step["claim"] for step in cleaned_bridge_chain]
    cleaned_plan["goal_finish"] = final_goal_claim
    return True, "Valid dossier", cleaned_plan


def validate_dossier_writer_body(output_text: str, visible_goal="", injected_prefix="", plan=None):
    del injected_prefix
    if not output_text or not output_text.strip():
        return False, "Writer body is empty"
    body = output_text.strip()
    if body.startswith("<thinking>") or body.endswith("</thinking>"):
        return False, "Writer body must be plain text only, without <thinking> tags"
    if RAW_POINT_TAG_RE.search(body) or POINT_TAG_RE.search(body) or "<coord>" in body:
        return False, "Writer body must not contain point/coord tags"
    internal_ref_hit = find_internal_reasoning_ref(body)
    if internal_ref_hit:
        return False, f"Internal planning reference detected: {internal_ref_hit.group(0)}"
    if len(body) < 120:
        return False, f"Writer body too short ({len(body)} chars, minimum 120)"
    if len(body) > compute_writer_body_budget(plan=plan):
        return False, f"Writer body too long ({len(body)} chars, maximum {compute_writer_body_budget(plan=plan)})"
    if re.search(r"\b(I|We|I'm|We'll|I've|we've)\b", body):
        return False, "Writer body must stay impersonal and should not use first-person narration"
    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(body)
        if hit:
            return False, f"Writer body contains forbidden pattern: {hit.group(0)}"
    if re.search(r"\bsimilarity or angle equality\b", body, re.IGNORECASE):
        return False, "Writer body must state concrete relations instead of vague high-level shortcuts"

    plan = plan or {}
    new_points = [point.lower() for point in extract_aux_new_points(plan.get("construction", ""))]
    if not new_points and plan.get("construction"):
        new_points = [
            point.lower()
            for point in re.findall(r"\b([a-z]\w*)\b", plan.get("construction", "").lower())
            if len(point) == 1
        ]
    if new_points and not any(re.search(rf"\b{re.escape(point)}\b", body.lower()) for point in new_points):
        return False, "Writer body must mention the auxiliary construction itself"

    coordinate_derivations = [
        item for item in (plan.get("coordinate_derivations") or [])
        if isinstance(item, dict) and item.get("rendered_text")
    ]
    if INLINE_POINT_COORD_RE.search(body):
        if not coordinate_derivations:
            return False, "Writer body uses coordinates without any approved coordinate snippet"
        if not any(item["rendered_text"] in body for item in coordinate_derivations):
            return False, "Writer body must reuse one approved coordinate snippet verbatim"

    sentences = split_into_sentences(body)
    if plan.get("aux_immediate_effects"):
        if not any(
            relation_mentioned_in_text(body, relation)
            for relation in plan.get("aux_immediate_effects", [])
            if isinstance(relation, str) and relation.strip()
        ):
            return False, "Writer body must state at least one approved aux_immediate_effect"

    search_start = 0
    for idx, step in enumerate(plan.get("bridge_chain", []) if isinstance(plan, dict) else []):
        match_idx = None
        claim = step.get("claim", "")
        for sentence_idx in range(search_start, len(sentences)):
            if relation_mentioned_in_text(sentences[sentence_idx], claim):
                match_idx = sentence_idx
                break
        if match_idx is None:
            return False, f"Writer body must explicitly realize bridge_chain[{idx}]"
        search_start = match_idx + 1

    for idx, step in enumerate(plan.get("goal_closure", []) if isinstance(plan, dict) else []):
        match_idx = None
        claim = step.get("claim", "")
        for sentence_idx in range(search_start, len(sentences)):
            if relation_mentioned_in_text(sentences[sentence_idx], claim):
                match_idx = sentence_idx
                break
        if match_idx is None:
            return False, f"Writer body must explicitly realize goal_closure[{idx}]"
        search_start = match_idx + 1

    goal_points = parse_goal_expression(visible_goal).get("points", [])
    goal_keywords = goal_keyword_hints(visible_goal)
    suffix = " ".join(sentences[max(0, len(sentences) - 2):]).lower()
    if goal_points and not any(point in suffix for point in goal_points):
        return False, "Writer body must close near the goal-side points"
    if goal_keywords and not any(keyword in suffix for keyword in goal_keywords):
        return False, "Writer body must close on the correct goal relation family"
    return True, "Valid dossier writer body"


def _resolve_raw_plan_support_ref(
    ref_text,
    cleaned_text_facts,
    cleaned_observations,
    cleaned_derivations,
    cleaned_bridge_steps,
):
    match = RAW_PLAN_SUPPORT_REF_RE.fullmatch(str(ref_text or "").strip())
    if not match:
        return None, "supports must use only text_facts_used[i], image_observations[i], coordinate_derivations[i], or earlier bridge_steps[i]"
    bucket_name = match.group(1).lower()
    index = int(match.group(2))
    if index <= 0:
        return None, "support indices must be 1-based positive integers"
    if bucket_name == "text_facts_used":
        if index > len(cleaned_text_facts):
            return None, "supports references unknown text_facts_used item"
        return cleaned_text_facts[index - 1], None
    if bucket_name == "image_observations":
        if index > len(cleaned_observations):
            return None, "supports references unknown image_observations item"
        return cleaned_observations[index - 1], None
    if bucket_name == "coordinate_derivations":
        if index > len(cleaned_derivations):
            return None, "supports references unknown coordinate_derivations item"
        return cleaned_derivations[index - 1]["relation"], None
    if bucket_name == "bridge_steps":
        if index > len(cleaned_bridge_steps):
            return None, "supports may reference only earlier bridge_steps items"
        return cleaned_bridge_steps[index - 1]["relation"], None
    return None, "unsupported support reference bucket"


def validate_raw_plan_response(
    output_text: str,
    point_coords,
    visible_goal="",
    aux_part=None,
    coordinate_candidates=None,
    sanitized_rest=None,
    visible_premise_summaries=None,
    visible_text_facts=None,
):
    del coordinate_candidates, sanitized_rest, visible_premise_summaries, visible_text_facts
    plan = output_text if isinstance(output_text, dict) else extract_json_object(output_text)
    if not isinstance(plan, dict):
        return False, "Planner must return a single JSON object", None

    visible_points = extract_visible_point_names(point_coords)
    aux_points = [point.lower() for point in extract_aux_new_points(aux_part or "")]
    known_points = visible_points + aux_points
    limits = compute_plan_complexity_limits(point_coords, visible_goal=visible_goal, aux_part=aux_part)
    required_keys = [
        "text_facts_used",
        "image_observations",
        "coordinate_derivations",
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

    ok, message, cleaned_text_facts = validate_relation_list(
        plan.get("text_facts_used"),
        "text_facts_used",
        visible_points,
        min_len=1,
        max_len=limits["visible_relations_max"],
        min_chars=5,
    )
    if not ok:
        return False, message, None
    ok, message, cleaned_observations = validate_relation_list(
        plan.get("image_observations"),
        "image_observations",
        visible_points,
        min_len=1,
        max_len=limits["coordinate_relations_max"],
        min_chars=5,
    )
    if not ok:
        return False, message, None

    cleaned_plan = {
        "text_facts_used": cleaned_text_facts,
        "visible_relations": cleaned_text_facts[:],
        "image_observations": cleaned_observations,
        "observation_relations": [
            {
                "id": f"obs_{idx + 1}",
                "relation": relation,
                "points": sorted(extract_point_mentions(relation, visible_points)),
            }
            for idx, relation in enumerate(cleaned_observations)
        ],
        "anchor_points": [],
        "anchor_relation": "",
    }

    for key in ["goal_bottleneck", "helper_idea", "construction"]:
        ok, message, cleaned_value = validate_descriptive_text(
            plan.get(key),
            key,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_plan[key] = cleaned_value

    aux_direct_relations = plan.get("aux_direct_relations") or []
    if not isinstance(aux_direct_relations, list) or not (
        limits["aux_direct_relations_min"] <= len(aux_direct_relations) <= limits["aux_direct_relations_max"]
    ):
        return False, (
            "aux_direct_relations must be a list with "
            f"{limits['aux_direct_relations_min']} to {limits['aux_direct_relations_max']} ordered direct consequences"
        ), None
    cleaned_direct = []
    for idx, relation in enumerate(aux_direct_relations):
        ok, message, cleaned_relation = validate_descriptive_text(
            relation,
            f"aux_direct_relations[{idx}]",
            min_chars=5,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_relation = normalize_relation_surface(cleaned_relation)
        if not relation_keyword_present(cleaned_relation):
            return False, f"aux_direct_relations[{idx}] must mention a concrete geometric relation", None
        cleaned_direct.append(cleaned_relation)
    cleaned_plan["aux_direct_relations"] = cleaned_direct

    coordinate_derivations = plan.get("coordinate_derivations") or []
    if not isinstance(coordinate_derivations, list) or not coordinate_derivations:
        return False, "coordinate_derivations must contain at least one explicit coordinate computation", None
    allowed_calc_types = {"parallel", "perpendicular", "equal_length", "midpoint", "collinear"}
    allowed_render_modes = {"vector", "distance", "midpoint", "area"}
    cleaned_derivations = []
    for idx, derivation in enumerate(coordinate_derivations[: limits["coordinate_relations_max"]]):
        if not isinstance(derivation, dict):
            return False, f"coordinate_derivations[{idx}] must be an object", None
        calc_type = str(derivation.get("calc_type") or "").strip().lower()
        render_mode = normalize_coordinate_render_mode(derivation.get("render_mode"), calc_type)
        if calc_type not in allowed_calc_types:
            return False, f"coordinate_derivations[{idx}].calc_type is unsupported", None
        if render_mode not in allowed_render_modes:
            return False, f"coordinate_derivations[{idx}].render_mode is unsupported", None
        ok, message, cleaned_relation = validate_descriptive_text(
            derivation.get("relation"),
            f"coordinate_derivations[{idx}].relation",
            min_chars=5,
            point_names=visible_points,
        )
        if not ok:
            return False, message, None
        cleaned_relation = normalize_relation_surface(cleaned_relation)
        if not relation_keyword_present(cleaned_relation):
            return False, f"coordinate_derivations[{idx}].relation must mention a concrete geometric relation", None
        points = [
            point.lower()
            for point in (derivation.get("points") or [])
            if isinstance(point, str) and point.lower() in point_coords
        ]
        min_point_count = 4 if calc_type in {"parallel", "perpendicular", "equal_length"} else 3
        if len(points) < min_point_count:
            return False, f"coordinate_derivations[{idx}].points must name at least {min_point_count} visible points", None
        if any(point in aux_points for point in points):
            return False, f"coordinate_derivations[{idx}] must not assign coordinates to auxiliary points", None
        ok, message, why_it_matters = validate_descriptive_text(
            derivation.get("why_it_matters"),
            f"coordinate_derivations[{idx}].why_it_matters",
            min_chars=8,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        witness = build_coordinate_candidate_witness(
            {
                "relation_type": calc_type,
                "points": points,
            },
            point_coords,
        )
        cleaned_item = {
            "relation": cleaned_relation,
            "points": points,
            "calc_type": calc_type,
            "render_mode": render_mode,
            "why_it_matters": why_it_matters,
            "witness": witness,
        }
        cleaned_item["rendered_text"] = render_coordinate_derivation_snippet(cleaned_item, point_coords)
        cleaned_derivations.append(cleaned_item)
    cleaned_plan["coordinate_derivations"] = cleaned_derivations
    cleaned_plan["coordinate_relations"] = [item["relation"] for item in cleaned_derivations]

    bridge_steps = plan.get("bridge_steps") or []
    if not isinstance(bridge_steps, list) or not (
        limits["bridge_steps_min"] <= len(bridge_steps) <= limits["bridge_steps_max"]
    ):
        return False, (
            "bridge_steps must be a list with "
            f"{limits['bridge_steps_min']} to {limits['bridge_steps_max']} ordered bridge-step objects"
        ), None
    cleaned_bridge_steps = []
    for idx, step in enumerate(bridge_steps):
        if not isinstance(step, dict):
            return False, f"bridge_steps[{idx}] must be an object", None
        if any(key not in step for key in ["relation", "supports", "why_it_helps", "focus_points"]):
            return False, f"bridge_steps[{idx}] must contain relation, supports, why_it_helps, and focus_points", None
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
        supports = [
            str(ref).strip()
            for ref in (step.get("supports") or [])
            if str(ref).strip()
        ]
        if not supports:
            return False, f"bridge_steps[{idx}].supports must not be empty", None
        resolved_supports = []
        for ref in supports:
            resolved, support_error = _resolve_raw_plan_support_ref(
                ref,
                cleaned_text_facts,
                cleaned_observations,
                cleaned_derivations,
                cleaned_bridge_steps,
            )
            if support_error:
                return False, f"bridge_steps[{idx}].supports invalid: {support_error}", None
            resolved_supports.append(resolved)
        ok, message, cleaned_help = validate_descriptive_text(
            step.get("why_it_helps"),
            f"bridge_steps[{idx}].why_it_helps",
            min_chars=8,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        focus_points = [
            point.lower()
            for point in (step.get("focus_points") or [])
            if isinstance(point, str) and point.lower() in known_points
        ]
        if len(focus_points) < 2:
            return False, f"bridge_steps[{idx}].focus_points must mention at least two known points", None
        cleaned_bridge_steps.append(
            {
                "id": f"B{idx + 1}",
                "relation": cleaned_relation,
                "support_refs": supports,
                "depends_on": resolved_supports,
                "required_supports": resolved_supports[: min(2, len(resolved_supports))],
                "min_support_mentions": 1,
                "why_it_helps": cleaned_help,
                "proof_alignment": "bridge",
                "focus_points": focus_points,
                "approved_route_relation": cleaned_relation,
            }
        )
    cleaned_plan["bridge_steps"] = cleaned_bridge_steps
    cleaned_plan["bridge_relations"] = [step["relation"] for step in cleaned_bridge_steps]

    ok, message, cleaned_goal_finish = validate_descriptive_text(
        plan.get("goal_finish"),
        "goal_finish",
        min_chars=8,
        point_names=known_points,
    )
    if not ok:
        return False, message, None
    cleaned_goal_finish = normalize_relation_surface(cleaned_goal_finish)
    if not relation_keyword_present(cleaned_goal_finish):
        return False, "goal_finish must mention a concrete goal-side geometric relation", None
    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec.get("points") or [])
    goal_keywords = goal_keyword_hints(visible_goal)
    if goal_points:
        mentioned_goal_points = {point for point in goal_points if point in cleaned_goal_finish.lower()}
        if len(mentioned_goal_points) < min(2, len(goal_points)):
            return False, "goal_finish must mention the target relation using goal-side points", None
    if not any(keyword in cleaned_goal_finish.lower() for keyword in goal_keywords):
        return False, "goal_finish must explicitly describe the goal-side relation it is aiming for", None
    cleaned_plan["goal_finish"] = cleaned_goal_finish

    relation_mentions = extract_point_mentions(" ".join(cleaned_plan["coordinate_relations"]), visible_points)
    if relation_mentions and len(relation_mentions) < min(3, len(visible_points)):
        return False, "coordinate_derivations should collectively cover at least three visible points", None

    if aux_part:
        new_points = [point.lower() for point in extract_aux_new_points(aux_part)]
        preconstruction_fields = [
            " ".join(cleaned_text_facts),
            " ".join(cleaned_observations),
            cleaned_plan["goal_bottleneck"],
            cleaned_plan["helper_idea"],
        ]
        for point_name in new_points:
            if any(re.search(rf"\b{re.escape(point_name)}\b", field.lower()) for field in preconstruction_fields):
                return False, f"new point '{point_name}' must not appear before the construction field", None
            if point_name not in cleaned_plan["construction"].lower():
                return False, f"construction must mention new point '{point_name}' explicitly", None
        if len(new_points) > 1:
            stage_markers = ["first", "then", "next", "after", "finally", "together", "simultaneously"]
            combined_text = (
                f"{cleaned_plan['construction']} "
                f"{' '.join(cleaned_plan['aux_direct_relations'])} "
                f"{' '.join(cleaned_plan['bridge_relations'])}"
            ).lower()
            if not any(marker in combined_text for marker in stage_markers):
                return False, "multi-point auxiliary plans must describe a staged or combined construction strategy", None

    cleaned_plan["figure_overview"] = " ".join(cleaned_observations[:2])
    cleaned_plan["coordinate_hints"] = build_canonical_coordinate_hint(cleaned_plan["coordinate_relations"])
    cleaned_plan["coverage_targets"] = {
        "coordinate_focus_relations": cleaned_plan["coordinate_relations"][:3],
        "observation_focus_relations": cleaned_observations[:3],
        "coordinate_reuse_min": 1 if cleaned_derivations else 0,
        "goal_points": list(goal_points),
    }
    return True, "Valid raw-record plan", cleaned_plan


def validate_plan_response(
    output_text: str,
    point_coords,
    visible_goal="",
    aux_part=None,
    coordinate_candidates=None,
    sanitized_rest=None,
    visible_premise_summaries=None,
    visible_text_facts=None,
):
    plan = output_text if isinstance(output_text, dict) else extract_json_object(output_text)
    if not isinstance(plan, dict):
        return False, "Planner must return a single JSON object", None

    visible_points = extract_visible_point_names(point_coords)
    aux_points = [point.lower() for point in extract_aux_new_points(aux_part or "")]
    known_points = visible_points + aux_points
    limits = compute_plan_complexity_limits(point_coords, visible_goal=visible_goal, aux_part=aux_part)
    hidden_route_hints = (
        build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
        if sanitized_rest and aux_part else {}
    )

    required_keys = [
        "selected_text_fact_ids",
        "selected_coordinate_candidate_ids",
        "image_observations",
        "coordinate_derivations",
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

    visible_text_facts = visible_text_facts or [
        {"id": f"T{idx + 1}", "relation": relation}
        for idx, relation in enumerate(visible_premise_summaries or [])
    ]
    coordinate_candidates = coordinate_candidates or []
    fact_lookup = {
        item["id"]: item
        for item in visible_text_facts
        if isinstance(item, dict) and item.get("id") and item.get("relation")
    }
    candidate_lookup = {
        item["id"]: item
        for item in coordinate_candidates
        if isinstance(item, dict) and item.get("id") and item.get("relation")
    }

    selected_text_fact_ids = [
        str(item).strip() for item in (plan.get("selected_text_fact_ids") or [])
        if str(item).strip()
    ]
    selected_coordinate_candidate_ids = [
        str(item).strip() for item in (plan.get("selected_coordinate_candidate_ids") or [])
        if str(item).strip()
    ]
    if not selected_text_fact_ids:
        return False, "selected_text_fact_ids must contain at least one T* item", None
    if not selected_coordinate_candidate_ids:
        return False, "selected_coordinate_candidate_ids must contain at least one C* item", None
    if any(item not in fact_lookup for item in selected_text_fact_ids):
        return False, "selected_text_fact_ids contains unknown T* item", None
    if any(item not in candidate_lookup for item in selected_coordinate_candidate_ids):
        return False, "selected_coordinate_candidate_ids contains unknown C* item", None

    cleaned_plan = {
        "selected_text_fact_ids": selected_text_fact_ids,
        "selected_coordinate_candidate_ids": selected_coordinate_candidate_ids,
        "visible_relations": [fact_lookup[item]["relation"] for item in selected_text_fact_ids],
        "coordinate_relations": [candidate_lookup[item]["relation"] for item in selected_coordinate_candidate_ids],
        "anchor_points": [],
        "anchor_relation": "",
    }

    cleaned_plan["image_observations"] = []
    cleaned_plan["observation_relations"] = []
    image_observations = plan.get("image_observations") or cleaned_plan["coordinate_relations"]
    if not isinstance(image_observations, list) or not image_observations:
        return False, "image_observations must be a non-empty list", None
    for idx, observation in enumerate(image_observations[: max(2, limits["coordinate_relations_max"])]):
        ok, message, cleaned_observation = validate_descriptive_text(
            observation,
            f"image_observations[{idx}]",
            min_chars=5,
            point_names=visible_points,
        )
        if not ok:
            return False, message, None
        cleaned_observation = normalize_relation_surface(cleaned_observation)
        cleaned_plan["image_observations"].append(cleaned_observation)
        cleaned_plan["observation_relations"].append(
            {
                "id": f"obs_{idx + 1}",
                "relation": cleaned_observation,
                "points": sorted(extract_point_mentions(cleaned_observation, visible_points)),
            }
        )

    for key in ["goal_bottleneck", "helper_idea", "construction"]:
        ok, message, cleaned_value = validate_descriptive_text(
            plan.get(key),
            key,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_plan[key] = cleaned_value

    aux_direct_relations = plan.get("aux_direct_relations") or []
    if not isinstance(aux_direct_relations, list) or not (
        limits["aux_direct_relations_min"] <= len(aux_direct_relations) <= limits["aux_direct_relations_max"]
    ):
        return False, (
            "aux_direct_relations must be a list with "
            f"{limits['aux_direct_relations_min']} to {limits['aux_direct_relations_max']} ordered direct consequences"
        ), None
    cleaned_direct = []
    for idx, relation in enumerate(aux_direct_relations):
        ok, message, cleaned_relation = validate_descriptive_text(
            relation,
            f"aux_direct_relations[{idx}]",
            min_chars=5,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_relation = normalize_relation_surface(cleaned_relation)
        if not relation_keyword_present(cleaned_relation):
            return False, f"aux_direct_relations[{idx}] must mention a concrete geometric relation", None
        cleaned_direct.append(cleaned_relation)
    immediate_hints = hidden_route_hints.get("immediate_aux_consequences", [])
    if immediate_hints and not any(
        relation_matches_hint_bucket(relation, immediate_hints, known_points)
        for relation in cleaned_direct
    ):
        return False, "aux_direct_relations must stay close to the immediate aux consequences", None
    cleaned_plan["aux_direct_relations"] = cleaned_direct

    coordinate_derivations = plan.get("coordinate_derivations") or []
    if not isinstance(coordinate_derivations, list) or not coordinate_derivations:
        return False, "coordinate_derivations must contain at least one explicit coordinate computation", None
    cleaned_derivations = []
    allowed_calc_types = {"parallel", "perpendicular", "equal_length", "midpoint", "collinear"}
    allowed_render_modes = {"vector", "distance", "midpoint", "area"}
    for idx, derivation in enumerate(coordinate_derivations[: limits["coordinate_relations_max"]]):
        if not isinstance(derivation, dict):
            return False, f"coordinate_derivations[{idx}] must be an object", None
        candidate_id = str(derivation.get("candidate_id") or "").strip()
        if candidate_id not in candidate_lookup or candidate_id not in selected_coordinate_candidate_ids:
            return False, f"coordinate_derivations[{idx}].candidate_id must reference a selected C* item", None
        calc_type = str(derivation.get("calc_type") or "").strip()
        render_mode = normalize_coordinate_render_mode(
            derivation.get("render_mode"),
            calc_type,
        )
        if calc_type not in allowed_calc_types:
            return False, f"coordinate_derivations[{idx}].calc_type is unsupported", None
        if render_mode not in allowed_render_modes:
            return False, f"coordinate_derivations[{idx}].render_mode is unsupported", None
        ok, message, cleaned_relation = validate_descriptive_text(
            derivation.get("relation"),
            f"coordinate_derivations[{idx}].relation",
            min_chars=5,
            point_names=visible_points,
        )
        if not ok:
            return False, message, None
        candidate_relation = candidate_lookup[candidate_id]["relation"]
        if not relations_semantically_match(cleaned_relation, candidate_relation, visible_points):
            return False, f"coordinate_derivations[{idx}].relation must match its selected coordinate candidate", None
        points = [
            point.lower()
            for point in (derivation.get("points") or candidate_lookup[candidate_id].get("points") or [])
            if isinstance(point, str) and point.lower() in point_coords
        ]
        if any(point in aux_points for point in points):
            return False, f"coordinate_derivations[{idx}] must not assign coordinates to auxiliary points", None
        ok, message, why_it_matters = validate_descriptive_text(
            derivation.get("why_it_matters"),
            f"coordinate_derivations[{idx}].why_it_matters",
            min_chars=8,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        cleaned_item = {
            "candidate_id": candidate_id,
            "relation": candidate_relation,
            "points": points,
            "calc_type": calc_type,
            "render_mode": render_mode,
            "why_it_matters": why_it_matters,
            "witness": candidate_lookup[candidate_id].get("witness", {}),
        }
        cleaned_item["rendered_text"] = render_coordinate_derivation_snippet(cleaned_item, point_coords)
        cleaned_derivations.append(cleaned_item)
    cleaned_plan["coordinate_derivations"] = cleaned_derivations

    bridge_steps = plan.get("bridge_steps") or []
    if not isinstance(bridge_steps, list) or not (
        limits["bridge_steps_min"] <= len(bridge_steps) <= limits["bridge_steps_max"]
    ):
        return False, (
            "bridge_steps must be a list with "
            f"{limits['bridge_steps_min']} to {limits['bridge_steps_max']} ordered bridge-step objects"
        ), None
    cleaned_bridge_steps = []
    prior_bridge_lookup = {}
    for idx, step in enumerate(bridge_steps):
        if not isinstance(step, dict):
            return False, f"bridge_steps[{idx}] must be an object", None
        if any(key not in step for key in ["relation", "support_refs", "why_it_helps", "proof_alignment", "focus_points"]):
            return False, f"bridge_steps[{idx}] must contain relation, support_refs, why_it_helps, proof_alignment, and focus_points", None
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
        support_refs = [
            str(ref).strip()
            for ref in (step.get("support_refs") or [])
            if str(ref).strip()
        ]
        if not support_refs:
            return False, f"bridge_steps[{idx}].support_refs must not be empty", None
        for ref in support_refs:
            if ref[0] not in {"T", "C", "B"}:
                return False, f"bridge_steps[{idx}].support_refs must use only T*, C*, or B* references", None
            if ref.startswith("T") and ref not in fact_lookup:
                return False, f"bridge_steps[{idx}].support_refs references unknown text fact", None
            if ref.startswith("C") and ref not in candidate_lookup:
                return False, f"bridge_steps[{idx}].support_refs references unknown coordinate candidate", None
            if ref.startswith("B") and ref not in prior_bridge_lookup:
                return False, f"bridge_steps[{idx}].support_refs may only reference earlier bridge steps", None
        ok, message, cleaned_help = validate_descriptive_text(
            step.get("why_it_helps"),
            f"bridge_steps[{idx}].why_it_helps",
            min_chars=8,
            point_names=known_points,
        )
        if not ok:
            return False, message, None
        proof_alignment = str(step.get("proof_alignment") or "").strip()
        if proof_alignment not in {"immediate_aux", "bridge", "goal_finish"}:
            return False, f"bridge_steps[{idx}].proof_alignment must be immediate_aux, bridge, or goal_finish", None
        focus_points = [
            point.lower()
            for point in (step.get("focus_points") or [])
            if isinstance(point, str) and point.lower() in known_points
        ]
        dependencies = resolve_support_refs(step, fact_lookup, candidate_lookup, prior_bridge_lookup)
        if not dependencies:
            return False, f"bridge_steps[{idx}] could not resolve any support_refs into earlier evidence", None
        bridge_id = f"B{idx + 1}"
        cleaned_step = {
            "id": bridge_id,
            "relation": cleaned_relation,
            "support_refs": support_refs,
            "depends_on": dependencies,
            "required_supports": dependencies[: min(2, len(dependencies))],
            "min_support_mentions": 1,
            "why_it_helps": cleaned_help,
            "proof_alignment": proof_alignment,
            "focus_points": focus_points,
            "approved_route_relation": cleaned_relation,
        }
        cleaned_bridge_steps.append(cleaned_step)
        prior_bridge_lookup[bridge_id] = cleaned_relation
    cleaned_plan["bridge_steps"] = cleaned_bridge_steps
    cleaned_plan["bridge_relations"] = [step["relation"] for step in cleaned_bridge_steps]

    ok, message, cleaned_goal_finish = validate_descriptive_text(
        plan.get("goal_finish"),
        "goal_finish",
        min_chars=8,
        point_names=known_points,
    )
    if not ok:
        return False, message, None
    cleaned_goal_finish = normalize_relation_surface(cleaned_goal_finish)
    if not relation_keyword_present(cleaned_goal_finish):
        return False, "goal_finish must mention a concrete goal-side geometric relation", None
    cleaned_plan["goal_finish"] = cleaned_goal_finish

    for idx, step in enumerate(cleaned_bridge_steps):
        bucket_name = "bridge_relations"
        if step["proof_alignment"] == "immediate_aux":
            bucket_name = "immediate_aux_consequences"
        elif step["proof_alignment"] == "goal_finish":
            bucket_name = "goal_finish_relations"
        bucket = hidden_route_hints.get(bucket_name, [])
        if bucket and not relation_matches_hint_bucket(step["relation"], bucket, known_points):
            return False, (
                f"bridge_steps[{idx}] does not stay close to its hidden {step['proof_alignment']} hint bucket"
            ), None
    finish_bucket = hidden_route_hints.get("goal_finish_relations", [])
    if finish_bucket and not relation_matches_hint_bucket(cleaned_goal_finish, finish_bucket, known_points):
        return False, "goal_finish must stay close to the hidden goal_finish hint bucket", None

    cleaned_plan["figure_overview"] = " ".join(cleaned_plan["image_observations"][:2])
    cleaned_plan["coordinate_hints"] = build_canonical_coordinate_hint(cleaned_plan["coordinate_relations"])
    cleaned_plan["coverage_targets"] = {
        "coordinate_focus_relations": cleaned_plan["coordinate_relations"][:3],
        "observation_focus_relations": cleaned_plan["image_observations"][:3],
        "coordinate_reuse_min": 1 if cleaned_derivations else 0,
        "goal_points": parse_goal_expression(visible_goal).get("points", []),
    }
    return True, "Valid plan", cleaned_plan


def validate_writer_body(output_text: str, visible_goal="", injected_prefix="", plan=None):
    del injected_prefix
    if not output_text or not output_text.strip():
        return False, "Writer body is empty"
    body = output_text.strip()
    if body.startswith("<thinking>") or body.endswith("</thinking>"):
        return False, "Writer body must be plain text only, without <thinking> tags"
    if RAW_POINT_TAG_RE.search(body) or POINT_TAG_RE.search(body) or "<coord>" in body:
        return False, "Writer body must not contain point/coord tags"
    internal_ref_hit = find_internal_reasoning_ref(body)
    if internal_ref_hit:
        return False, f"Internal planning reference detected: {internal_ref_hit.group(0)}"
    if len(body) < 160:
        return False, f"Writer body too short ({len(body)} chars, minimum 160)"
    if len(body) > compute_writer_body_budget(plan=plan):
        return False, f"Writer body too long ({len(body)} chars, maximum {compute_writer_body_budget(plan=plan)})"
    if re.search(r"\b(I|We|I'm|We'll|I've|we've)\b", body):
        return False, "Writer body must stay impersonal and should not use first-person narration"
    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(body)
        if hit:
            return False, f"Writer body contains forbidden pattern: {hit.group(0)}"
    if plan and plan.get("coordinate_derivations"):
        if not INLINE_POINT_COORD_RE.search(body):
            return False, "Writer body must include at least one explicit coordinate computation"
        rendered_snippets = [
            derivation.get("rendered_text", "")
            for derivation in plan.get("coordinate_derivations", [])
            if isinstance(derivation, dict)
        ]
        if rendered_snippets and not any(snippet and snippet.split(";")[-1].strip(". ")[:20].lower() in body.lower() for snippet in rendered_snippets):
            return False, "Writer body must reuse at least one approved coordinate computation"
    sentences = split_into_sentences(body)
    search_start = 0
    for idx, step in enumerate((plan or {}).get("bridge_steps", [])):
        match_idx = None
        for sentence_idx in range(search_start, len(sentences)):
            if relation_mentioned_in_text(sentences[sentence_idx], step.get("relation", "")):
                match_idx = sentence_idx
                break
        if match_idx is None:
            return False, f"Writer body must explicitly realize bridge_steps[{idx}]"
        sentence = sentences[match_idx]
        support_mentions = count_support_relation_mentions(
            sentence,
            step.get("required_supports") or step.get("depends_on") or [],
            point_names=extract_problem_goal({"llm_input_renamed": visible_goal}) if False else None,
            target_relation=step.get("relation", ""),
        )
        if step.get("required_supports") and support_mentions < step.get("min_support_mentions", 1):
            return False, f"Writer sentence for bridge_steps[{idx}] must name at least one approved supporting relation"
        search_start = match_idx + 1
    goal_finish = (plan or {}).get("goal_finish", "")
    if goal_finish and not any(relation_mentioned_in_text(sentence, goal_finish) for sentence in sentences[search_start:]):
        return False, "Writer body must explicitly realize goal_finish after the bridge steps"
    return True, "Valid writer body"


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
    fallback_model_names=None,
    visible_text_facts=None,
    validator_fn=None,
    retry_feedback_builder=None,
):
    validator_fn = validator_fn or validate_plan_response
    retry_feedback_builder = retry_feedback_builder or build_plan_retry_feedback
    last_error = None
    last_output = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name, fallback_model_names=fallback_model_names)
            elapsed = time.time() - start
            last_output = output
            ok, message, plan = validator_fn(
                output,
                point_coords,
                visible_goal=visible_goal,
                aux_part=aux_part,
                coordinate_candidates=coordinate_candidates,
                sanitized_rest=sanitized_rest,
                visible_premise_summaries=visible_premise_summaries,
                visible_text_facts=visible_text_facts,
            )
            if ok:
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
                messages = messages + [{"role": "user", "content": retry_feedback_builder(message, aux_part)}]
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


def run_plan_critic_stage(
    stage_name,
    messages,
    model_name,
    max_retries,
    fallback_model_names=None,
    allow_revised_plan=False,
):
    last_error = None
    last_output = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name, fallback_model_names=fallback_model_names)
            elapsed = time.time() - start
            last_output = output
            parsed = extract_json_object(output)
            if isinstance(parsed, dict) and isinstance(parsed.get("approved"), bool):
                if parsed["approved"] or (
                    allow_revised_plan and isinstance(parsed.get("revised_dossier"), dict)
                ):
                    return {
                        "success": True,
                        "output": output,
                        "parsed": parsed,
                        "attempts_used": attempt,
                        "elapsed_seconds": elapsed,
                        "error": None,
                    }
                last_error = "; ".join(parsed.get("issues") or []) or "critic_rejected_plan"
            else:
                last_error = "plan critic must return JSON with boolean approved"
            logger.warning(f"[{stage_name}] Validation failed: {last_error}")
            if attempt < max_retries:
                messages = messages + [{"role": "user", "content": "Return exactly one JSON object with approved, issues, and summary."}]
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


def run_writer_stage(
    stage_name,
    messages,
    model_name,
    visible_goal,
    injected_prefix,
    plan,
    max_retries,
    fallback_model_names=None,
    validator_fn=None,
    retry_feedback_builder=None,
    failure_recovery_fn=None,
):
    del injected_prefix
    validator_fn = validator_fn or validate_writer_body
    retry_feedback_builder = retry_feedback_builder or build_writer_retry_feedback
    last_error = None
    last_output = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name, fallback_model_names=fallback_model_names)
            elapsed = time.time() - start
            last_output = output
            ok, message = validator_fn(
                output,
                visible_goal=visible_goal,
                plan=plan,
            )
            if ok:
                return {
                    "success": True,
                    "output": output.strip(),
                    "attempts_used": attempt,
                    "elapsed_seconds": elapsed,
                    "error": None,
                }
            last_error = message
            logger.warning(f"[{stage_name}] Validation failed: {message}")
            if failure_recovery_fn is not None:
                recovered_result = failure_recovery_fn(
                    {
                        "success": False,
                        "output": output.strip() if isinstance(output, str) else output,
                        "attempts_used": attempt,
                        "elapsed_seconds": elapsed,
                        "error": message,
                    }
                )
                if recovered_result is not None and recovered_result.get("success"):
                    return recovered_result
            if attempt < max_retries:
                feedback = retry_feedback_builder(message, plan)
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


def generate_dossier_thinking(
    record,
    image_path: Path,
    aux_part,
    sanitized_rest,
    model_name,
    max_retries,
    verbose,
    plan_mode=None,
    fallback_model_names=None,
    source_audit=None,
):
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    visible_text_facts = build_visible_text_facts(record)
    hidden_milestone_summary = build_dossier_hidden_milestone_summary(
        sanitized_rest,
        aux_part,
        visible_goal,
        source_audit=source_audit,
    )
    visible_fact_relations = [fact.get("relation", "") for fact in visible_text_facts if fact.get("relation")]
    plan_prompt = build_dossier_plan_prompt_text(
        record,
        aux_part,
        visible_text_facts=visible_fact_relations,
        point_coords=point_coords,
        hidden_milestone_summary=hidden_milestone_summary,
    )
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
        fallback_model_names=fallback_model_names,
        point_coords=point_coords,
        visible_goal=visible_goal,
        aux_part=aux_part,
        coordinate_candidates=None,
        sanitized_rest=sanitized_rest,
        visible_premise_summaries=[fact["relation"] for fact in visible_text_facts],
        visible_text_facts=visible_text_facts,
        max_retries=max_retries,
        validator_fn=validate_dossier_plan_response,
        retry_feedback_builder=build_dossier_plan_retry_feedback,
    )
    plan_source = "llm"
    if not plan_result["success"]:
        skeleton_ok, skeleton_message, scripted_dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            point_coords,
            visible_goal,
            visible_text_facts=visible_text_facts,
            visible_premise_summaries=[fact["relation"] for fact in visible_text_facts],
        )
        if skeleton_ok:
            logger.warning(
                "[plan] Falling back to scripted dossier skeleton after planner failure: %s",
                plan_result["error"],
            )
            plan_result = {
                "success": True,
                "output": json.dumps(scripted_dossier, ensure_ascii=False, indent=2),
                "parsed": scripted_dossier,
                "attempts_used": plan_result["attempts_used"],
                "elapsed_seconds": plan_result["elapsed_seconds"],
                "error": None,
            }
            plan_source = "scripted_fallback"
        else:
            return {
                "success": False,
                "thinking": plan_result["output"],
                "plan_prompt": plan_prompt if verbose else None,
                "write_prompt": None,
                "plan_output": plan_result["output"] if verbose else None,
                "plan_parsed": None,
                "attempts_used": plan_result["attempts_used"],
                "elapsed_seconds": plan_result["elapsed_seconds"],
                "error": f"{plan_result['error']}; {skeleton_message}",
                "write_output": None,
                "generation_style": "dossier_v1",
            }

    if plan_mode == "plan_only":
        return {
            "success": True,
            "thinking": None,
            "plan_prompt": plan_prompt if verbose else None,
            "write_prompt": None,
            "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
            "plan_parsed": plan_result["parsed"],
            "attempts_used": plan_result["attempts_used"],
            "elapsed_seconds": plan_result["elapsed_seconds"],
            "error": None,
            "write_output": None,
            "generation_style": "dossier_v1",
        }

    critic_result = {
        "success": True,
        "output": None,
        "parsed": {"approved": True, "issues": [], "summary": "critic skipped"},
        "attempts_used": 0,
        "elapsed_seconds": 0.0,
        "error": None,
    }
    if plan_source == "scripted_fallback":
        logger.info("[plan_critic] Skipping critic for validator-clean scripted fallback dossier")
    else:
        critic_prompt = build_dossier_critic_prompt_text(
            record,
            plan_result["parsed"],
            hidden_milestone_summary=hidden_milestone_summary,
        )
        critic_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _encode_image_base64(image_path)}},
                    {"type": "text", "text": critic_prompt},
                ],
            }
        ]
        critic_result = run_plan_critic_stage(
            "plan_critic",
            critic_messages,
            model_name=model_name,
            fallback_model_names=fallback_model_names,
            max_retries=max_retries,
            allow_revised_plan=True,
        )
        if not critic_result["success"]:
            skeleton_ok, skeleton_message, scripted_dossier = build_scripted_dossier_skeleton(
                record,
                aux_part,
                sanitized_rest,
                point_coords,
                visible_goal,
                visible_text_facts=visible_text_facts,
                visible_premise_summaries=[fact["relation"] for fact in visible_text_facts],
            )
            if skeleton_ok:
                logger.warning(
                    "[plan_critic] Falling back to scripted dossier skeleton after critic failure: %s",
                    critic_result["error"],
                )
                plan_result["parsed"] = scripted_dossier
                plan_source = "scripted_fallback"
                critic_result = {
                    "success": True,
                    "output": critic_result["output"],
                    "parsed": {"approved": True, "issues": [], "summary": "critic fallback to scripted skeleton"},
                    "attempts_used": critic_result["attempts_used"],
                    "elapsed_seconds": critic_result["elapsed_seconds"] or 0.0,
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "thinking": plan_result["output"],
                    "plan_prompt": plan_prompt if verbose else None,
                    "write_prompt": None,
                    "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
                    "plan_parsed": plan_result["parsed"],
                    "attempts_used": plan_result["attempts_used"] + critic_result["attempts_used"],
                    "elapsed_seconds": (plan_result["elapsed_seconds"] or 0.0) + (critic_result["elapsed_seconds"] or 0.0),
                    "error": f"{critic_result['error']}; {skeleton_message}",
                    "write_output": None,
                    "generation_style": "dossier_v1",
                }

        if not critic_result["parsed"].get("approved") and isinstance(critic_result["parsed"].get("revised_dossier"), dict):
            merged_revised_dossier = dict(plan_result["parsed"])
            merged_revised_dossier.update(critic_result["parsed"]["revised_dossier"])
            ok, message, cleaned_plan = validate_dossier_plan_response(
                merged_revised_dossier,
                point_coords,
                visible_goal=visible_goal,
                aux_part=aux_part,
                visible_text_facts=visible_text_facts,
            )
            if not ok:
                logger.warning(
                    "[plan_critic] Ignoring invalid revised_dossier patch and keeping original validated dossier: %s",
                    message,
                )
            else:
                plan_result["parsed"] = cleaned_plan

    if plan_source != "scripted_fallback":
        preferred_plan, replacement_source = maybe_choose_scripted_dossier_plan(
            record=record,
            aux_part=aux_part,
            sanitized_rest=sanitized_rest,
            point_coords=point_coords,
            visible_goal=visible_goal,
            visible_text_facts=visible_text_facts,
            visible_premise_summaries=[fact["relation"] for fact in visible_text_facts],
            live_plan=plan_result["parsed"],
            logger=logger,
        )
        if replacement_source:
            plan_result["parsed"] = preferred_plan
            plan_source = replacement_source

    write_prompt = build_dossier_write_prompt_text(
        record,
        plan_result["parsed"],
        aux_part=aux_part,
        coordinate_derivation_block=build_coordinate_derivation_block(plan_result["parsed"], point_coords),
    )
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
        fallback_model_names=fallback_model_names,
        visible_goal=visible_goal,
        injected_prefix="",
        plan=plan_result["parsed"],
        max_retries=max_retries,
        validator_fn=validate_dossier_writer_body,
        retry_feedback_builder=build_dossier_writer_retry_feedback,
        failure_recovery_fn=lambda failed_write_result: maybe_choose_scripted_dossier_writer_body(
            record=record,
            aux_part=aux_part,
            visible_goal=visible_goal,
            plan=plan_result["parsed"],
            write_result=failed_write_result,
            logger=logger,
        ),
    )
    if plan_source in {"scripted_fallback", "scripted_preferred"}:
        write_result = maybe_choose_scripted_dossier_writer_body(
            record=record,
            aux_part=aux_part,
            visible_goal=visible_goal,
            plan=plan_result["parsed"],
            write_result=write_result,
            logger=logger,
        )
    assembled_thinking = None
    if write_result["output"]:
        assembled_thinking = f"<thinking>{write_result['output'].strip()}</thinking>"
        is_valid, message = validate_thinking_response(
            assembled_thinking,
            point_coords=point_coords,
            require_coord_tags=False,
            max_total_len=compute_thinking_total_budget(plan_result["parsed"]),
        )
        if not is_valid:
            return {
                "success": False,
                "thinking": assembled_thinking,
                "plan_prompt": plan_prompt if verbose else None,
                "write_prompt": write_prompt if verbose else None,
                "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
                "plan_parsed": plan_result["parsed"],
                "attempts_used": plan_result["attempts_used"] + critic_result["attempts_used"] + write_result["attempts_used"],
                "elapsed_seconds": (
                    (plan_result["elapsed_seconds"] or 0.0) +
                    (critic_result["elapsed_seconds"] or 0.0) +
                    (write_result["elapsed_seconds"] or 0.0)
                ),
                "error": f"Final assembly validation failed: {message}",
                "write_output": write_result["output"],
                "generation_style": "dossier_v1",
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
            (critic_result["elapsed_seconds"] or 0.0) +
            (write_result["elapsed_seconds"] or 0.0)
        ),
        "attempts_used": plan_result["attempts_used"] + critic_result["attempts_used"] + write_result["attempts_used"],
        "error": write_result["error"],
        "write_output": write_result["output"],
        "generation_style": "dossier_v1",
    }


def generate_thinking(
    record,
    image_path: Path,
    aux_part,
    sanitized_rest,
    model_name,
    max_retries,
    verbose,
    plan_mode=None,
    planner_style="default",
    fallback_model_names=None,
):
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    visible_text_facts = build_visible_text_facts(record)
    coordinate_candidates = build_image_coordinate_candidates(point_coords, visible_text_facts, max_items=8)
    visible_premise_summaries = [fact["relation"] for fact in visible_text_facts]
    plan_prompt = build_plan_prompt(record, aux_part, sanitized_rest, planner_style=planner_style)
    plan_messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _encode_image_base64(image_path)}},
                {"type": "text", "text": plan_prompt},
            ],
        }
    ]
    plan_validator = validate_plan_response
    retry_feedback_builder = build_plan_retry_feedback
    if planner_style == "raw_record_v1":
        plan_validator = validate_raw_plan_response
        retry_feedback_builder = build_raw_plan_retry_feedback
    plan_result = run_plan_stage(
        "plan",
        plan_messages,
        model_name=model_name,
        fallback_model_names=fallback_model_names,
        point_coords=point_coords,
        visible_goal=visible_goal,
        aux_part=aux_part,
        coordinate_candidates=coordinate_candidates,
        sanitized_rest=sanitized_rest,
        visible_premise_summaries=visible_premise_summaries,
        visible_text_facts=visible_text_facts,
        max_retries=max_retries,
        validator_fn=plan_validator,
        retry_feedback_builder=retry_feedback_builder,
    )
    if not plan_result["success"]:
        return {
            "success": False,
            "thinking": plan_result["output"],
            "plan_prompt": plan_prompt if verbose else None,
            "write_prompt": None,
            "plan_output": plan_result["output"] if verbose else None,
            "plan_parsed": None,
            "attempts_used": plan_result["attempts_used"],
            "elapsed_seconds": plan_result["elapsed_seconds"],
            "error": plan_result["error"],
            "write_output": None,
        }

    if plan_mode == "plan_only":
        plan_result["parsed"]["coordinate_derivations"] = render_plan_coordinate_derivations(
            plan_result["parsed"],
            point_coords,
        )
        return {
            "success": True,
            "thinking": None,
            "plan_prompt": plan_prompt if verbose else None,
            "write_prompt": None,
            "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
            "plan_parsed": plan_result["parsed"],
            "attempts_used": plan_result["attempts_used"],
            "elapsed_seconds": plan_result["elapsed_seconds"],
            "error": None,
            "write_output": None,
        }

    critic_prompt = build_plan_critic_prompt(record, plan_result["parsed"], sanitized_rest, aux_part)
    critic_messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _encode_image_base64(image_path)}},
                {"type": "text", "text": critic_prompt},
            ],
        }
    ]
    critic_result = run_plan_critic_stage(
        "plan_critic",
        critic_messages,
        model_name=model_name,
        fallback_model_names=fallback_model_names,
        max_retries=max_retries,
    )
    if not critic_result["success"]:
        return {
            "success": False,
            "thinking": plan_result["output"],
            "plan_prompt": plan_prompt if verbose else None,
            "write_prompt": None,
            "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
            "plan_parsed": plan_result["parsed"],
            "attempts_used": plan_result["attempts_used"] + critic_result["attempts_used"],
            "elapsed_seconds": (plan_result["elapsed_seconds"] or 0.0) + (critic_result["elapsed_seconds"] or 0.0),
            "error": critic_result["error"],
            "write_output": None,
        }

    plan_result["parsed"]["coordinate_derivations"] = render_plan_coordinate_derivations(
        plan_result["parsed"],
        point_coords,
    )
    write_prompt = build_write_prompt(
        record,
        plan_result["parsed"],
        aux_part=aux_part,
        point_coords=point_coords,
    )
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
        fallback_model_names=fallback_model_names,
        visible_goal=visible_goal,
        injected_prefix="",
        plan=plan_result["parsed"],
        max_retries=max_retries,
    )
    assembled_thinking = None
    if write_result["output"]:
        assembled_thinking = f"<thinking>{write_result['output'].strip()}</thinking>"
        is_valid, message = validate_thinking_response(
            assembled_thinking,
            point_coords=point_coords,
            require_coord_tags=False,
            max_total_len=compute_thinking_total_budget(plan_result["parsed"]),
        )
        if not is_valid:
            return {
                "success": False,
                "thinking": assembled_thinking,
                "plan_prompt": plan_prompt if verbose else None,
                "write_prompt": write_prompt if verbose else None,
                "plan_output": json.dumps(plan_result["parsed"], ensure_ascii=False, indent=2) if verbose else None,
                "plan_parsed": plan_result["parsed"],
                "attempts_used": plan_result["attempts_used"] + critic_result["attempts_used"] + write_result["attempts_used"],
                "elapsed_seconds": (
                    (plan_result["elapsed_seconds"] or 0.0) +
                    (critic_result["elapsed_seconds"] or 0.0) +
                    (write_result["elapsed_seconds"] or 0.0)
                ),
                "error": f"Final assembly validation failed: {message}",
                "write_output": write_result["output"],
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
            (critic_result["elapsed_seconds"] or 0.0) +
            (write_result["elapsed_seconds"] or 0.0)
        ),
        "attempts_used": plan_result["attempts_used"] + critic_result["attempts_used"] + write_result["attempts_used"],
        "error": write_result["error"],
        "write_output": write_result["output"],
    }


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


def is_timeout_api_error(exc):
    message = str(exc).lower()
    return "timed out" in message or "timeout" in message


def should_extend_plan_retry_budget(validation_message, used_bonus_retries, max_bonus_retries=2):
    if not isinstance(validation_message, str) or not validation_message.strip():
        return False
    if used_bonus_retries >= max_bonus_retries:
        return False
    extension_markers = [
        "introduces unsupported angle/ratio/similar segments",
        "should not skip prerequisite hidden-route checkpoints",
        "coordinate_relations should cover at least",
    ]
    return any(marker in validation_message for marker in extension_markers)


def call_model(messages, model_name, fallback_model_names=None, temperature=0.2, max_tokens=2048):
    last_exc = None
    model_sequence = normalize_model_name_list([model_name] + list(fallback_model_names or []))
    for model_index, active_model_name in enumerate(model_sequence, start=1):
        for attempt in range(1, DEFAULT_API_CALL_RETRIES + 1):
            try:
                response = get_client().chat.completions.create(
                    model=active_model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if active_model_name != model_name:
                    logger.info(
                        "Model fallback succeeded with %s (primary %s timed out or failed earlier).",
                        active_model_name,
                        model_name,
                    )
                return response.choices[0].message.content
            except Exception as exc:
                last_exc = exc
                is_last_attempt = attempt >= DEFAULT_API_CALL_RETRIES
                transient = is_transient_api_error(exc)
                timed_out = is_timeout_api_error(exc)
                has_next_model = model_index < len(model_sequence)
                if not transient and not has_next_model:
                    raise
                if not transient and has_next_model:
                    logger.warning(
                        "Model %s failed with a non-transient error on attempt %s/%s: %s. Trying fallback model %s.",
                        active_model_name,
                        attempt,
                        DEFAULT_API_CALL_RETRIES,
                        exc,
                        model_sequence[model_index],
                    )
                    break
                if timed_out and has_next_model:
                    logger.warning(
                        "Model %s timed out on attempt %s/%s: %s. Switching immediately to fallback model %s.",
                        active_model_name,
                        attempt,
                        DEFAULT_API_CALL_RETRIES,
                        exc,
                        model_sequence[model_index],
                    )
                    break
                if is_last_attempt and has_next_model:
                    logger.warning(
                        "Model %s exhausted %s transient retries: %s. Trying fallback model %s.",
                        active_model_name,
                        DEFAULT_API_CALL_RETRIES,
                        exc,
                        model_sequence[model_index],
                    )
                    break
                if is_last_attempt:
                    raise
                sleep_seconds = DEFAULT_API_RETRY_BACKOFF_SECONDS * attempt + random.uniform(0.0, 1.0)
                logger.warning(
                    "Transient API failure on model %s call attempt %s/%s: %s. Retrying in %.1fs",
                    active_model_name,
                    attempt,
                    DEFAULT_API_CALL_RETRIES,
                    exc,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)
    raise last_exc


def legacy_run_plan_stage_old(
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
    fallback_model_names=None,
):
    raise RuntimeError("Legacy planner path has been removed; use the model_evidence pipeline.")
    last_error = None
    last_output = None
    attempt = 1
    allowed_retries = max_retries
    bonus_retries_used = 0

    while attempt <= allowed_retries:
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{allowed_retries}")
            start = time.time()
            output = call_model(messages, model_name, fallback_model_names=fallback_model_names)
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
            if should_extend_plan_retry_budget(message, bonus_retries_used):
                allowed_retries += 1
                bonus_retries_used += 1
            if attempt < allowed_retries:
                feedback = build_plan_retry_feedback(message, aux_part)
                messages = messages + [{"role": "user", "content": feedback}]
                time.sleep(1)

        except Exception as exc:
            last_error = str(exc)
            logger.error(f"[{stage_name}] API call failed: {exc}")
            if attempt < allowed_retries:
                time.sleep(2)
        attempt += 1

    return {
        "success": False,
        "output": last_output,
        "parsed": None,
        "attempts_used": attempt - 1,
        "elapsed_seconds": None,
        "error": last_error or "Unknown error",
    }


def legacy_run_plan_narrative_stage(
    stage_name,
    messages,
    model_name,
    plan_skeleton,
    point_coords,
    visible_goal,
    aux_part,
    coordinate_candidates,
    sanitized_rest,
    visible_premise_summaries,
    max_retries,
    fallback_model_names=None,
):
    raise RuntimeError("Legacy plan narrative stage has been removed; use the model_evidence pipeline.")
    last_error = None
    last_output = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name, fallback_model_names=fallback_model_names)
            elapsed = time.time() - start
            last_output = output
            narrative_fields = extract_json_object(output)
            if not isinstance(narrative_fields, dict):
                last_error = "Plan narrative stage must return a single JSON object"
                logger.warning(f"[{stage_name}] Validation failed: {last_error}")
                if attempt < max_retries:
                    messages = messages + [{
                        "role": "user",
                        "content": "Return exactly one JSON object with only the requested narrative fields. Do not change the locked plan skeleton."
                    }]
                    time.sleep(1)
                continue
            merged_plan = merge_plan_skeleton_and_narrative(plan_skeleton, narrative_fields)
            ok, message, cleaned_plan = validate_plan_response(
                merged_plan,
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
                    "output": output.strip(),
                    "parsed": cleaned_plan,
                    "attempts_used": attempt,
                    "elapsed_seconds": elapsed,
                    "error": None,
                }

            last_error = message
            logger.warning(f"[{stage_name}] Validation failed: {message}")
            if attempt < max_retries:
                feedback = (
                    "Keep the locked route structure exactly as given. "
                    "Only rewrite the narrative text fields and the per-step unlock lines.\n"
                    f"{build_plan_retry_feedback(message, aux_part)}"
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


def legacy_run_writer_stage(stage_name, messages, model_name, visible_goal, injected_prefix, plan, max_retries, fallback_model_names=None):
    raise RuntimeError("Legacy writer prefix stage has been removed; use the model_evidence pipeline.")
    last_error = None
    last_output = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name, fallback_model_names=fallback_model_names)
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


def legacy_generate_thinking(
    record,
    image_path: Path,
    aux_part,
    sanitized_rest,
    model_name,
    max_retries,
    verbose,
    plan_mode="hybrid",
    fallback_model_names=None,
):
    raise RuntimeError("Legacy hybrid/llm generation path has been removed; use the model_evidence pipeline.")
    point_coords = get_point_coords(record)
    visible_goal = extract_problem_goal(record)
    coordinate_candidates = build_hidden_coordinate_candidates(point_coords, max_items=64, relax_type_limits=True)
    visible_premise_summaries = build_visible_premise_summaries(record)
    plan_prompt = None
    plan_result = None

    if plan_mode == "llm":
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
            fallback_model_names=fallback_model_names,
            point_coords=point_coords,
            visible_goal=visible_goal,
            aux_part=aux_part,
            coordinate_candidates=coordinate_candidates,
            sanitized_rest=sanitized_rest,
            visible_premise_summaries=visible_premise_summaries,
            max_retries=max_retries,
        )
    else:
        skeleton_plan = build_scripted_plan_skeleton(
            record,
            aux_part,
            sanitized_rest,
            point_coords,
            coordinate_candidates,
            visible_premise_summaries,
            visible_goal,
        )
        skeleton_ok, skeleton_message, cleaned_skeleton = validate_plan_response(
            skeleton_plan,
            point_coords,
            visible_goal=visible_goal,
            aux_part=aux_part,
            coordinate_candidates=coordinate_candidates,
            sanitized_rest=sanitized_rest,
            visible_premise_summaries=visible_premise_summaries,
        )
        if not skeleton_ok:
            return {
                "success": False,
                "thinking": json.dumps(skeleton_plan, ensure_ascii=False, indent=2),
                "plan_prompt": None,
                "write_prompt": None,
                "plan_output": json.dumps(skeleton_plan, ensure_ascii=False, indent=2) if verbose else None,
                "plan_parsed": None,
                "attempts_used": 0,
                "elapsed_seconds": None,
                "error": f"Scripted plan skeleton invalid: {skeleton_message}",
            }
        plan_prompt = build_plan_narrative_prompt(record, aux_part, cleaned_skeleton)
        plan_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _encode_image_base64(image_path)}},
                    {"type": "text", "text": plan_prompt},
                ],
            }
        ]
        narrative_result = run_plan_narrative_stage(
            "plan_narrative",
            plan_messages,
            model_name=model_name,
            fallback_model_names=fallback_model_names,
            plan_skeleton=cleaned_skeleton,
            point_coords=point_coords,
            visible_goal=visible_goal,
            aux_part=aux_part,
            coordinate_candidates=coordinate_candidates,
            sanitized_rest=sanitized_rest,
            visible_premise_summaries=visible_premise_summaries,
            max_retries=max_retries,
        )
        if narrative_result["success"]:
            plan_result = narrative_result
        else:
            logger.warning(f"[plan_narrative] Falling back to scripted plan skeleton: {narrative_result['error']}")
            plan_result = {
                "success": True,
                "output": json.dumps(cleaned_skeleton, ensure_ascii=False, indent=2),
                "parsed": cleaned_skeleton,
                "attempts_used": narrative_result["attempts_used"],
                "elapsed_seconds": narrative_result["elapsed_seconds"],
                "error": None,
            }

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
        fallback_model_names=fallback_model_names,
        visible_goal=visible_goal,
        injected_prefix=injected_prefix,
        plan=plan_result["parsed"],
        max_retries=max_retries,
    )

    assembled_thinking = None
    if write_result["output"]:
        assembled_thinking = f"<thinking>{injected_prefix} {write_result['output'].strip()}</thinking>"
        max_coord_tags = min(5, max(1, len(plan_result["parsed"].get("anchor_points") or [])))
        is_valid, message = validate_thinking_response(
            assembled_thinking,
            point_coords=point_coords,
            require_coord_tags=True,
            max_total_len=compute_thinking_total_budget(plan_result["parsed"]),
            max_coord_tags=max_coord_tags,
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
    plan_mode=None,
    generation_style="dossier_v1",
    planner_style="default",
    run_metadata=None,
    run_dir=None,
    fallback_model_names=None,
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
        visible_goal = extract_problem_goal(record)
        proof_guidance = build_hidden_proof_guidance(
            record["_sanitized_rest"],
            record["_aux_part"],
            visible_goal,
        )
        source_audit = audit_source_record(
            record,
            image_path=image_path,
            aux_part=record["_aux_part"],
            visible_goal=visible_goal,
            proof_guidance=proof_guidance,
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
                    generation_style=generation_style,
                ),
            }

        if generation_style == "dossier_v1":
            generation = generate_dossier_thinking(
                record,
                image_path=image_path,
                aux_part=record["_aux_part"],
                sanitized_rest=record["_sanitized_rest"],
                model_name=model_name,
                fallback_model_names=fallback_model_names,
                max_retries=max_retries,
                verbose=verbose,
                plan_mode=plan_mode,
                source_audit=source_audit,
            )
        else:
            generation = generate_thinking(
                record,
                image_path=image_path,
                aux_part=record["_aux_part"],
                sanitized_rest=record["_sanitized_rest"],
                model_name=model_name,
                fallback_model_names=fallback_model_names,
                max_retries=max_retries,
                verbose=verbose,
                plan_mode=plan_mode,
                planner_style=planner_style,
            )
        public_problem = build_public_problem_text(record)
        aux_part = record["_aux_part"]
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
        coordinate_candidates = build_hidden_coordinate_candidates(
            get_point_coords(record),
            max_items=64,
            relax_type_limits=True,
        )
        generation_audit = audit_generation_quality(
            record,
            generation,
            aux_part,
            coordinate_candidates=coordinate_candidates,
        )

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
            generation_style=generation_style,
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
        generation_style=generation_style,
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
        "--fallback-models",
        type=str,
        default=",".join(DEFAULT_FALLBACK_MODELS),
        help=(
            "Comma-separated fallback model names used when the primary model times out or fails. "
            f"Default: {','.join(DEFAULT_FALLBACK_MODELS)}"
        ),
    )
    parser.add_argument(
        "--api-timeout-seconds",
        type=float,
        default=DEFAULT_API_TIMEOUT_SECONDS,
        help=f"Per-request API timeout in seconds. Default: {DEFAULT_API_TIMEOUT_SECONDS}",
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
    parser.add_argument(
        "--generation-style",
        type=str,
        default="dossier_v1",
        choices=["dossier_v1", "model_evidence_legacy"],
        help="Generation pipeline style. Default: dossier_v1.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Run only the planner stage and stop after plan validation/artifact export.",
    )
    parser.add_argument(
        "--planner-style",
        type=str,
        default="default",
        choices=["default", "raw_record_v1"],
        help="Planner prompt style. Default: default.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.generation_style != "model_evidence_legacy" and args.planner_style != "default":
        raise SystemExit("--planner-style is supported only with --generation-style model_evidence_legacy")
    if args.planner_style != "default" and not args.plan_only:
        raise SystemExit("--planner-style raw_record_v1 is currently supported only together with --plan-only")
    fallback_model_names = normalize_model_name_list(args.fallback_models)
    configure_client(timeout_seconds=args.api_timeout_seconds)
    args_dict = vars(args).copy()
    run_dir = build_run_dir(args.output)
    run_metadata = build_run_config(
        args_dict=args_dict,
        output_jsonl=args.output,
        run_dir=run_dir,
        model_name=args.model_name,
        fallback_model_names=fallback_model_names,
        script_path=__file__,
        cwd=os.getcwd(),
        repo_root=REPO_ROOT,
        default_input_jsonl=str(DEFAULT_INPUT_JSONL),
        api_base_url=CLIENT_BASE_URL,
        api_timeout_seconds=args.api_timeout_seconds,
        api_call_retries=DEFAULT_API_CALL_RETRIES,
        api_retry_backoff_seconds=DEFAULT_API_RETRY_BACKOFF_SECONDS,
    )

    process_and_generate_sft(
        input_jsonl=args.input,
        output_jsonl=args.output,
        sample_size=args.num_samples,
        num_workers=args.num_workers,
        model_name=args.model_name,
        fallback_model_names=fallback_model_names,
        plan_mode="plan_only" if args.plan_only else None,
        generation_style=args.generation_style,
        planner_style=args.planner_style,
        verbose=args.verbose,
        random_sample=not args.sequential,
        process_all=args.process_all,
        max_retries=args.max_retries,
        run_metadata=run_metadata,
        run_dir=run_dir,
    )
