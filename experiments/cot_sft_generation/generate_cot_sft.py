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
    re.compile(r"\$[^$]+\$"),
]
POINT_TAG_RE = re.compile(
    r"<point>\s*([a-z]\w*)\s*</point>\s*<coord>\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)</coord>",
    re.IGNORECASE,
)
RAW_POINT_TAG_RE = re.compile(r"<point>\s*([a-z]\w*)\s*</point>", re.IGNORECASE)
AUX_NEW_POINT_RE = re.compile(r"\bx00\s+([a-z]\w*)\b", re.IGNORECASE)
PROBLEM_BODY_RE = re.compile(r"<problem>\s*(.*?)\s*</problem>", re.DOTALL | re.IGNORECASE)


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
    if len(thinking_text) > 1400:
        return False, f"<thinking> content too long ({len(thinking_text)} chars, maximum 1400)"

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
        expectations.append(("collinear/line", ["collinear", "line through", "on line"]))
    return expectations


def validate_plan_response(output_text: str, point_coords, aux_part=None):
    plan = extract_json_object(output_text)
    if not isinstance(plan, dict):
        return False, "Planner must return a single JSON object", None

    required_keys = [
        "anchor_points",
        "anchor_relation",
        "goal_bottleneck",
        "helper_idea",
        "construction",
    ]
    missing = [key for key in required_keys if key not in plan]
    if missing:
        return False, f"Planner JSON missing keys: {missing}", None

    anchor_points = plan.get("anchor_points")
    if not isinstance(anchor_points, list) or not (2 <= len(anchor_points) <= 3):
        return False, "anchor_points must be a list with 2 or 3 visible points", None
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
    for key in required_keys[1:]:
        value = plan.get(key)
        if not isinstance(value, str) or len(value.strip()) < 12:
            return False, f"{key} must be a non-empty descriptive string", None
        value = value.strip()
        if RAW_POINT_TAG_RE.search(value) or POINT_TAG_RE.search(value):
            return False, f"{key} must not contain point tags", None
        for pattern in FORBIDDEN_THINKING_PATTERNS:
            hit = pattern.search(value)
            if hit:
                return False, f"{key} contains forbidden pattern: {hit.group(0)}", None
        cleaned_plan[key] = value

    if aux_part:
        construction_text = f"{cleaned_plan['helper_idea']} {cleaned_plan['construction']}".lower()
        for label, keywords in build_aux_keyword_expectations(aux_part):
            if not any(keyword in construction_text for keyword in keywords):
                return False, f"construction is missing an expected {label} cue", None

    return True, "Valid planner JSON", cleaned_plan


def validate_writer_body(output_text: str):
    if not output_text or not output_text.strip():
        return False, "Writer body is empty"
    body = output_text.strip()
    if body.startswith("<thinking>") or body.endswith("</thinking>"):
        return False, "Writer body must be plain text only, without <thinking> tags"
    if RAW_POINT_TAG_RE.search(body) or POINT_TAG_RE.search(body):
        return False, "Writer body must not contain point tags; anchor tags are inserted by the script"
    if "<coord>" in body or "</coord>" in body:
        return False, "Writer body must not contain coord tags"
    if len(body) < 80:
        return False, f"Writer body too short ({len(body)} chars, minimum 80)"
    if len(body) > 1200:
        return False, f"Writer body too long ({len(body)} chars, maximum 1200)"
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
        "[Hidden Target Summary]\n"
        f"New point name(s): {new_points_text}\n"
        f"Target auxiliary facts: {hidden_aux_brief}\n\n"
        "[Task]\n"
        "Return exactly one JSON object with these keys:\n"
        "1. anchor_points: a list of 2 or 3 original visible points that are the best anchors for describing the figure.\n"
        "2. anchor_relation: one sentence describing the key visible relation or shape cue involving those anchors.\n"
        "3. goal_bottleneck: one sentence describing the main obstacle to reaching the visible goal from the current figure.\n"
        "4. helper_idea: one sentence describing what kind of helper is missing, without naming the new point yet.\n"
        "5. construction: one or two sentences that finally introduce the new point and the intended construction in plain geometry language.\n\n"
        "Constraints:\n"
        "- Use only lowercase point names exactly as in the problem text.\n"
        "- Do not use <point> tags, <coord> tags, LaTeX, $...$ math formatting, <aux>, <proof>, IDs, or rule names.\n"
        "- Do not restate every premise. Focus only on the visible configuration and the bottleneck toward the visible goal.\n"
        "- Do not mention the new point name before the construction field.\n"
        "- Avoid vague filler such as 'this point is crucial' or 'this will help'.\n"
        "- The construction field must describe the same geometric facts as the hidden target summary in plain language; do not invent a different line, circle, or intersection.\n"
        "- The wording must sound supportable from the image and visible problem text alone.\n"
    )


def build_write_prompt(record, plan, aux_part, sanitized_rest):
    public_problem = build_public_problem_text(record)
    supervisor_payload = build_supervisor_payload(record, aux_part, sanitized_rest)
    visible_goal = extract_problem_goal(record)
    hidden_aux_brief = build_hidden_aux_brief(aux_part)
    new_points = extract_aux_new_points(aux_part)
    new_points_text = ", ".join(new_points) if new_points else "the hidden auxiliary point"
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
        "[Hidden Target Summary]\n"
        f"New point name(s): {new_points_text}\n"
        f"Target auxiliary facts: {hidden_aux_brief}\n\n"
        "[Approved Plan]\n"
        f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        "[Write Requirements]\n"
        "Write only the body text that comes after an anchor sentence supplied by the script.\n"
        "Do NOT output <thinking>, <point>, or <coord> tags; the script will add the anchor sentence and the coordinate tags itself.\n"
        "The body must satisfy all of the following:\n"
        "1. It should sound supportable from the image and visible problem text alone.\n"
        "2. It should be logically coherent and centered on discovering the auxiliary construction for the visible goal, not on re-listing premises.\n"
        "3. Follow this order: bottleneck -> missing helper idea -> final introduction of the new point.\n"
        "4. Most of the reasoning should happen before the new auxiliary point is named; only introduce that point in the final one or two sentences.\n"
        "5. Use the plan faithfully, but rewrite it into smooth prose instead of JSON fragments.\n"
        "6. Replace vague statements like 'this point is crucial' with a concrete bottleneck or visual cue.\n"
        "7. Use the original lowercase point names exactly as in the problem text; do not rewrite them as uppercase, LaTeX, or $...$ math formatting.\n"
        "8. Keep the body concise and specific, roughly 90 to 170 words.\n"
        "9. The final one or two sentences must stay faithful to the hidden target summary; do not invent a different construction than the approved plan.\n"
        "10. It must not contain <aux>, <proof>, <numerical_check>, [012]-style IDs, AR/r63/a01-style rule tokens, or meta-talk.\n"
        "11. It must not say that some coordinate table, hidden answer, proof, or reference was provided.\n"
        "12. It must not assign coordinates to newly introduced auxiliary points.\n"
        "Output only the plain-text body.\n"
    )


def call_model(messages, model_name, temperature=0.2, max_tokens=2048):
    response = get_client().chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content


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


def run_plan_stage(stage_name, messages, model_name, point_coords, aux_part, max_retries):
    last_error = None
    last_output = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name)
            elapsed = time.time() - start
            last_output = output
            ok, message, plan = validate_plan_response(output, point_coords, aux_part=aux_part)
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


def run_writer_stage(stage_name, messages, model_name, max_retries):
    last_error = None
    last_output = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[{stage_name}] Attempt {attempt}/{max_retries}")
            start = time.time()
            output = call_model(messages, model_name)
            elapsed = time.time() - start
            last_output = output
            ok, message = validate_writer_body(output)
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
        aux_part=aux_part,
        max_retries=max_retries,
    )
    if not plan_result["success"]:
        return {
            "success": False,
            "thinking": plan_result["output"],
            "plan_prompt": plan_prompt,
            "write_prompt": None,
            "plan_output": plan_result["output"] if verbose else None,
            "attempts_used": plan_result["attempts_used"],
            "elapsed_seconds": plan_result["elapsed_seconds"],
            "error": plan_result["error"],
        }

    write_prompt = build_write_prompt(
        record,
        plan_result["parsed"],
        aux_part=aux_part,
        sanitized_rest=sanitized_rest,
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
        max_retries=max_retries,
    )

    assembled_thinking = None
    if write_result["output"]:
        anchor_sentence = build_anchor_sentence(plan_result["parsed"], point_coords)
        assembled_thinking = f"<thinking>{anchor_sentence} {write_result['output'].strip()}</thinking>"
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
        if not image_path.exists():
            return {
                "result_data": None,
                "item_record": {
                    "sample_order": sample_order,
                    "input_index": record["_source_index"],
                    "image_path": str(image_path),
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
            "plan_prompt": generation.get("plan_prompt"),
            "write_prompt": generation.get("write_prompt"),
            "plan_output": generation.get("plan_output"),
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

    summary = {
        "input_jsonl": str(input_path),
        "total_candidates_with_aux": len(all_aux_records),
        "sampled_items": len(selected),
        "successful_items": len(sft_dataset),
        "failed_items": len(selected) - len(sft_dataset),
        "num_workers": num_workers,
        "max_retries_per_stage": max_retries,
        "model_name": model_name,
        "output_jsonl": os.path.abspath(output_jsonl),
        "artifacts_dir": os.path.abspath(run_dir),
        "runtime_seconds": time.time() - start_time,
    }
    write_json(run_dir / "summary.json", summary)
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
