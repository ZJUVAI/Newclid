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
        select_support_relations_for_step,
        split_formal_relation_chain,
        summarize_aux_clause,
    )
    from .prompt_builders import (
        build_plan_narrative_prompt as build_plan_narrative_prompt_text,
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
    from audits import (
        audit_generation_quality,
        audit_source_record,
        bridge_step_relation_realized,
        build_visible_premise_summaries,
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
        select_support_relations_for_step,
        split_formal_relation_chain,
        summarize_aux_clause,
    )
    from prompt_builders import (
        build_plan_narrative_prompt as build_plan_narrative_prompt_text,
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


def validate_thinking_response(
    output_text: str,
    point_coords,
    require_coord_tags=True,
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

    for pattern in FORBIDDEN_THINKING_PATTERNS:
        hit = pattern.search(thinking_text)
        if hit:
            return False, f"Forbidden leakage pattern detected: {hit.group(0)}"

    if require_coord_tags and point_coords:
        ok, message = validate_coord_tags(thinking_text, point_coords, max_tags=max_coord_tags)
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
    if relation_keywords & {"angle", "similar", "ratio"}:
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


def build_plan_narrative_prompt(record, aux_part, plan_skeleton):
    return build_plan_narrative_prompt_text(
        record,
        aux_part,
        plan_skeleton,
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
    attempt = 1
    allowed_retries = max_retries
    bonus_retries_used = 0

    while attempt <= allowed_retries:
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{allowed_retries}")
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


def run_plan_narrative_stage(
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


def generate_thinking(record, image_path: Path, aux_part, sanitized_rest, model_name, max_retries, verbose, plan_mode="hybrid"):
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
    plan_mode,
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
            plan_mode=plan_mode,
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
        "--plan-mode",
        type=str,
        choices=["hybrid", "llm"],
        default="hybrid",
        help="Planning mode. 'hybrid' uses a scripted skeleton plus model-written narrative fields; 'llm' uses the legacy full-model planner. Default: hybrid.",
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
        plan_mode=args.plan_mode,
        verbose=args.verbose,
        random_sample=not args.sequential,
        process_all=args.process_all,
        max_retries=args.max_retries,
        run_metadata=run_metadata,
        run_dir=run_dir,
    )
