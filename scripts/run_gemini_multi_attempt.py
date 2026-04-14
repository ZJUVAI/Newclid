#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cairosvg
import numpy as np
from PIL import Image, ImageOps

try:
    from openai import OpenAI
except ImportError:

    class OpenAI:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "openai is required to run Gemini/OpenAI-compatible API calls. "
                "Install the openai package to execute this script."
            )


try:
    from rich.live import Live
    from rich.table import Table
except ImportError:

    class Table:  # type: ignore[no-redef]
        def __init__(self):
            self.columns: list[tuple[str, str | None, bool]] = []
            self.rows: list[tuple[str, ...]] = []

        def add_column(
            self, header: str, justify: str | None = None, no_wrap: bool = False
        ):
            self.columns.append((header, justify, no_wrap))

        def add_row(self, *values: str):
            self.rows.append(tuple(values))

    class Live:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self.renderable = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, renderable):
            self.renderable = renderable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_dev_imo_prompts import problem_to_dsl
from newclid.agent.runtime.search_runtime import run_ddar_c
from newclid.api import GeometricSolverBuilder
from newclid.configs import default_defs_path, default_rules_path
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.rule import Rule
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.predicates.collinearity import Coll
from newclid.predicates.congruence import Cong
from newclid.predicates.cyclic import Cyclic
from newclid.predicates.equal_angles import EqAngle
from newclid.predicates.equal_ratios import EqRatio
from newclid.predicates.midpoint import MidPoint
from newclid.predicates.parallelism import Para
from newclid.predicates.perpendicularity import Perp
from newclid.proof import ProofState


DEFAULT_BASE_URL = "https://api.zjuqx.cn/v1"
DEFAULT_MODEL = "google/gemini-3.1-pro-preview"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT = 3600
DEFAULT_MAX_ATTEMPTS = 64
SMOKE_TEST_ATTEMPTS = 3


@dataclass
class AttemptResult:
    problem_name: str
    attempt_idx: int
    model: str
    actual_model: str | None
    query: str
    image_path: str
    raw_response: str
    aux_text: str | None
    constructed_clauses: str | None
    usage: dict[str, Any] | None
    verification_status: str
    error_message: str | None
    elapsed_api_s: float
    elapsed_verify_s: float
    elapsed_total_s: float


@dataclass
class RunSummary:
    problem_name: str
    base_ddar_solved: bool
    solved: bool
    solved_attempt_idx: int | None
    total_attempts_executed: int
    elapsed_time_s: float
    output_path: str


@dataclass
class ProblemContext:
    problem_name: str
    problem: ProblemJGEX
    proof: ProofState
    defs: dict[str, DefinitionJGEX]
    rules: list[Rule]
    query: str
    image_path: Path
    system_prompt: str


class _DSLTranslator:
    @staticmethod
    def translate_dsl_to_construction(
        point: str, predicate: str, args: list[str]
    ) -> str:
        if predicate == "perp":
            return Perp.to_constructive(point, tuple(args))
        if predicate == "para":
            return Para.to_constructive(point, tuple(args))
        if predicate == "cong":
            return Cong.to_constructive(point, tuple(args))
        if predicate == "midp":
            return MidPoint.to_constructive(point, tuple(args))
        if predicate == "coll":
            return Coll.to_constructive(point, tuple(args))
        if predicate == "eqangle":
            return _DSLTranslator._translate_eqangle(point, args)
        if predicate == "cyclic":
            return Cyclic.to_constructive(point, tuple(args))
        if predicate == "eqratio":
            return EqRatio.to_constructive(point, tuple(args))
        return f"{predicate} {' '.join(args)}"

    @staticmethod
    def _arrange_angle_points(
        a: str, b: str, c: str, d: str
    ) -> tuple[str, str, str] | None:
        if a == c:
            return (b, a, d)
        if a == d:
            return (b, a, c)
        if b == c:
            return (a, b, d)
        if b == d:
            return (a, b, c)
        return None

    @staticmethod
    def _translate_eqangle(point: str, args: list[str]) -> str:
        a, b, c, d, e, f, g, h = args
        if len(set([a, b, c, d, e, f, g, h])) == 8:
            if point == h:
                return f"on_aline0 {h} {a} {b} {c} {d} {e} {f} {g}"
            if point == g:
                return f"on_aline0 {g} {a} {b} {c} {d} {e} {f} {h}"
            if point == f:
                return f"on_aline0 {f} {c} {d} {a} {b} {g} {h} {e}"
            if point == e:
                return f"on_aline0 {e} {c} {d} {a} {b} {g} {h} {f}"
            if point == d:
                return f"on_aline0 {d} {e} {f} {g} {h} {a} {b} {c}"
            if point == c:
                return f"on_aline0 {c} {e} {f} {g} {h} {a} {b} {d}"
            if point == b:
                return f"on_aline0 {b} {g} {h} {e} {f} {c} {d} {a}"
            if point == a:
                return f"on_aline0 {a} {g} {h} {e} {f} {c} {d} {b}"

        if len(set([a, b, c, d])) == 4 and len(set([a, b, e, f])) == 3:
            a, b, c, d, e, f, g, h = a, b, e, f, c, d, g, h
        first = _DSLTranslator._arrange_angle_points(a, b, c, d)
        second = _DSLTranslator._arrange_angle_points(e, f, g, h)
        if first is None or second is None:
            raise ValueError(f"Unsupported eqangle form for point '{point}'")
        return EqAngle.to_constructive(point, first + second)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a Gemini/OpenAI-compatible VLM experiment with repeated "
            "independent attempts. Each attempt may return multiple auxiliary "
            "constructions inside one <aux> block."
        )
    )
    parser.add_argument(
        "--problems-path",
        type=Path,
        default=Path("benchmarks/dev_imo.txt"),
    )
    parser.add_argument(
        "--problem-name",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--prompt-path",
        type=Path,
        default=Path("experiments/test_frontier_models/formal_prompt.md"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/test_frontier_models/results"),
    )
    parser.add_argument(
        "--render-dir",
        type=Path,
        default=Path("temp/gemini_multi_attempt_images"),
    )
    parser.add_argument(
        "--defs-path",
        type=Path,
        default=default_defs_path(),
    )
    parser.add_argument(
        "--rules-path",
        type=Path,
        default=default_rules_path(),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=998244353,
    )
    parser.add_argument(
        "--rename",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=f"Force a small-resource run with {SMOKE_TEST_ATTEMPTS} attempts.",
    )
    return parser.parse_args()


def create_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("ZJUVAI_API_KEY"),
        base_url=os.getenv("ZJUVAI_BASE_URL", DEFAULT_BASE_URL),
    )


def sanitize_filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "default"


def build_output_paths(
    *,
    output_dir: Path,
    problems_path: Path,
    model: str,
    max_attempts: int,
) -> tuple[Path, Path]:
    dataset_name = sanitize_filename_part(problems_path.stem)
    model_name = sanitize_filename_part(model)
    base_name = f"eval_{dataset_name}_{model_name}_a{max_attempts}"
    jsonl_path = output_dir / f"{base_name}.jsonl"
    csv_path = output_dir / f"{base_name}.csv"
    return jsonl_path, csv_path


def load_problem_names(problems_path: Path, problem_name: str | None) -> list[str]:
    problems = ProblemJGEX.parse_txt_file(problems_path)
    if problem_name is not None:
        if problem_name not in problems:
            raise ValueError(f"{problem_name} not found in {problems_path}")
        return [problem_name]
    return list(problems.keys())


def render_table(
    all_tasks_info: list[tuple[str, str, int | str, float]],
    start_time: float,
    reorder: bool,
) -> Table:
    total_problems = len(all_tasks_info)
    solved_count = sum(status == "Success" for _, status, _, _ in all_tasks_info)
    processed_count = sum(status != "Pending" for _, status, _, _ in all_tasks_info)

    table = Table()
    table.add_column(
        f"Problem Names ({solved_count} Solved /{processed_count} Processed /{total_problems} Total)",
        justify="left",
        no_wrap=True,
    )
    table.add_column("Status", justify="center")
    table.add_column("Attempts", justify="right")
    table.add_column(f"Time ({time.time() - start_time:.2f}s)", justify="right")
    if reorder:
        priority = {"Failed": 0, "Pending": 1, "Success": 2}
        all_tasks_info = sorted(
            all_tasks_info,
            key=lambda x: priority.get(x[1], 99),
        )
    for problem_name, status, attempts, elapsed_time in all_tasks_info:
        elapsed = "-" if status == "Pending" else f"{elapsed_time:.2f}"
        attempts_value = "-" if status == "Pending" else str(attempts)
        table.add_row(problem_name, status, attempts_value, elapsed)
    return table


def load_system_prompt(prompt_path: Path) -> str:
    text = prompt_path.read_text(encoding="utf-8")
    if "# Input" in text:
        text = text.split("# Input", 1)[0].strip()
    return text


def encode_image_base64(image_path: str | Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    mime_type = mime_type or "image/png"
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def build_user_prompt(query: str) -> str:
    return (
        "[Formal Description]:\n"
        f"{{{query}}}\n\n"
        "Output ONLY the <aux> ... </aux> string."
    )


def build_messages(
    system_prompt: str, query: str, image_path: str | Path
) -> list[dict[str, Any]]:
    image_data_uri = encode_image_base64(image_path)
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_uri}},
                {"type": "text", "text": build_user_prompt(query)},
            ],
        },
    ]


def normalize_response_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    texts.append(text_value)
            else:
                text_attr = getattr(item, "text", None)
                if isinstance(text_attr, str):
                    texts.append(text_attr)
        return "".join(texts)
    return str(content)


def normalize_usage(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    try:
        return dict(usage)
    except Exception:
        return {"raw": str(usage)}


def extract_aux_block(text: str) -> str | None:
    match = re.search(r"<aux>\s*(.*?)\s*</aux>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    aux_text = match.group(1).strip()
    return aux_text or None


def aux_block_to_constructions(aux_text: str) -> str:
    segments = [segment.strip() for segment in aux_text.split(";") if segment.strip()]
    if not segments:
        raise ValueError("No auxiliary constructions found inside <aux> block")

    constructions: list[str] = []
    for segment in segments:
        if " : " not in segment:
            raise ValueError(f"Malformed auxiliary segment: {segment}")
        point_expr, premises_expr = segment.split(" : ", 1)
        points = point_expr.strip().split()
        if len(points) != 1:
            raise ValueError(
                f"Only one constructed point per segment is supported: {segment}"
            )
        point = points[0]

        premises_tokens = premises_expr.strip().split()
        if not premises_tokens:
            constructions.append(f"{point} = free {point}")
            continue

        premises: list[list[str]] = []
        idx = 0
        while idx < len(premises_tokens):
            predicate = premises_tokens[idx]
            idx += 1
            if predicate in {"coll"}:
                arg_count = 3
            elif predicate in {"cong", "perp", "para"}:
                arg_count = 4
            elif predicate in {"midp"}:
                arg_count = 3
            elif predicate in {"cyclic"}:
                arg_count = 4
            elif predicate in {"eqangle", "eqratio"}:
                arg_count = 8
            elif predicate in {"aconst", "rconst"}:
                arg_count = 5
            else:
                raise ValueError(f"Unsupported predicate '{predicate}'")

            if idx + arg_count > len(premises_tokens):
                raise ValueError(
                    f"Incomplete predicate arguments in segment: {segment}"
                )
            premises.append([predicate, *premises_tokens[idx : idx + arg_count]])
            idx += arg_count

        if len(premises) > 2:
            raise ValueError(f"At most two premises are supported per point: {segment}")

        translated = [
            _DSLTranslator.translate_dsl_to_construction(point, premise[0], premise[1:])
            for premise in premises
        ]
        constructions.append(f"{point} = {', '.join(translated)}")

    return "; ".join(constructions)


def render_problem_image(
    proof: ProofState,
    problem: ProblemJGEX,
    *,
    render_dir: Path,
    problem_name: str,
) -> Path:
    render_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", problem_name)
    svg_path = render_dir / f"{stem}.svg"
    png_path = render_dir / f"{stem}.png"

    draw_clause_figure(proof, problem, str(svg_path), proof.rng, draw_annotations=True)
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=1024)

    with Image.open(png_path) as img:
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            rgb_img = Image.merge("RGB", (r, g, b))
            inverted_rgb = ImageOps.invert(rgb_img)
            r_inv, g_inv, b_inv = inverted_rgb.split()
            img_out = Image.merge("RGBA", (r_inv, g_inv, b_inv, a))
        elif img.mode == "LA":
            lightness, alpha = img.split()
            lightness_inv = ImageOps.invert(lightness)
            img_out = Image.merge("LA", (lightness_inv, alpha))
        else:
            img_out = ImageOps.invert(img.convert("RGB"))
        img_out.save(png_path)

    return png_path


def build_problem_context(
    *,
    problems_path: Path,
    problem_name: str,
    defs_path: Path,
    rules_path: Path,
    prompt_path: Path,
    render_dir: Path,
    rename: bool,
    seed: int,
) -> ProblemContext:
    builder = (
        GeometricSolverBuilder(seed=seed)
        .load_problem_from_file(problems_path, problem_name, rename=rename)
        .load_defs_from_file(defs_path)
        .load_rules_from_file(rules_path)
    )
    solver = builder.build()
    proof = solver.proof
    query = problem_to_dsl(builder.problemJGEX, proof.defs)
    image_path = render_problem_image(
        proof,
        builder.problemJGEX,
        render_dir=render_dir,
        problem_name=problem_name,
    )
    return ProblemContext(
        problem_name=problem_name,
        problem=builder.problemJGEX,
        proof=proof,
        defs=proof.defs,
        rules=builder.rules,
        query=query,
        image_path=image_path,
        system_prompt=load_system_prompt(prompt_path),
    )


def verify_constructions(
    *,
    problem: ProblemJGEX,
    constructions: str,
    defs: dict[str, DefinitionJGEX],
    rules: list[Rule],
    timeout: int,
) -> tuple[str, str | None]:
    try:
        new_problem = problem.with_more_construction(constructions)
        proof = ProofState.build_problemJGEX(
            problemJGEX=new_problem,
            defsJGEX=defs,
            rng=np.random.default_rng(998244353),
            max_attempts=100,
            problem_path=None,
        )
    except Exception as exc:
        return "invalid_build", str(exc)

    try:
        solved = run_ddar_c(proof, rules, time.time(), timeout)
    except Exception as exc:
        return "engine_error", str(exc)
    return ("solved" if solved else "unsolved"), None


def run_single_attempt(
    *,
    client: Any,
    context: ProblemContext,
    attempt_idx: int,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> AttemptResult:
    attempt_start = time.time()
    messages = build_messages(context.system_prompt, context.query, context.image_path)

    api_start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw_response = normalize_response_text(response.choices[0].message.content)
        actual_model = getattr(response, "model", None)
        usage = normalize_usage(getattr(response, "usage", None))
        api_elapsed = time.time() - api_start
    except Exception as exc:
        total_elapsed = time.time() - attempt_start
        return AttemptResult(
            problem_name=context.problem_name,
            attempt_idx=attempt_idx,
            model=model,
            actual_model=None,
            query=context.query,
            image_path=str(context.image_path),
            raw_response="",
            aux_text=None,
            constructed_clauses=None,
            usage=None,
            verification_status="api_error",
            error_message=str(exc),
            elapsed_api_s=time.time() - api_start,
            elapsed_verify_s=0.0,
            elapsed_total_s=total_elapsed,
        )

    aux_text = extract_aux_block(raw_response)
    if aux_text is None:
        total_elapsed = time.time() - attempt_start
        return AttemptResult(
            problem_name=context.problem_name,
            attempt_idx=attempt_idx,
            model=model,
            actual_model=actual_model,
            query=context.query,
            image_path=str(context.image_path),
            raw_response=raw_response,
            aux_text=None,
            constructed_clauses=None,
            usage=usage,
            verification_status="invalid_aux",
            error_message="No <aux>...</aux> block found in model output",
            elapsed_api_s=api_elapsed,
            elapsed_verify_s=0.0,
            elapsed_total_s=total_elapsed,
        )

    try:
        constructions = aux_block_to_constructions(aux_text)
    except Exception as exc:
        total_elapsed = time.time() - attempt_start
        return AttemptResult(
            problem_name=context.problem_name,
            attempt_idx=attempt_idx,
            model=model,
            actual_model=actual_model,
            query=context.query,
            image_path=str(context.image_path),
            raw_response=raw_response,
            aux_text=aux_text,
            constructed_clauses=None,
            usage=usage,
            verification_status="invalid_aux",
            error_message=str(exc),
            elapsed_api_s=api_elapsed,
            elapsed_verify_s=0.0,
            elapsed_total_s=total_elapsed,
        )

    verify_start = time.time()
    verification_status, error_message = verify_constructions(
        problem=context.problem,
        constructions=constructions,
        defs=context.defs,
        rules=context.rules,
        timeout=timeout,
    )
    verify_elapsed = time.time() - verify_start

    return AttemptResult(
        problem_name=context.problem_name,
        attempt_idx=attempt_idx,
        model=model,
        actual_model=actual_model,
        query=context.query,
        image_path=str(context.image_path),
        raw_response=raw_response,
        aux_text=aux_text,
        constructed_clauses=constructions,
        usage=usage,
        verification_status=verification_status,
        error_message=error_message,
        elapsed_api_s=api_elapsed,
        elapsed_verify_s=verify_elapsed,
        elapsed_total_s=time.time() - attempt_start,
    )


def append_jsonl_record(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_summary_csv(
    *,
    csv_path: Path,
    dataset_path: Path,
    all_tasks_info: list[tuple[str, str, int | str, float]],
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    solved_count = sum(1 for _, status, _, _ in all_tasks_info if status == "Success")
    total_problems = len(all_tasks_info)
    total_time = sum(
        elapsed_time
        for _, status, _, elapsed_time in all_tasks_info
        if status != "Pending"
    )
    with csv_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                f"Dataset: {dataset_path.stem}, Solved: {solved_count}/{total_problems}, Total Time: {total_time:.2f}s"
            ]
        )
        writer.writerow(["Problem Name", "Solved", "Time (s)"])
        for problem_name, status, _, elapsed_time in all_tasks_info:
            solved = "√" if status == "Success" else "x"
            writer.writerow([problem_name, solved, f"{elapsed_time:.2f}"])


def run_problem(
    *,
    client: Any,
    context: ProblemContext,
    output_path: Path,
    model: str,
    temperature: float,
    max_tokens: int,
    max_attempts: int,
    timeout: int,
) -> RunSummary:
    problem_start = time.time()
    base_ddar_solved = run_ddar_c(context.proof, context.rules, time.time(), timeout)
    if base_ddar_solved:
        summary = RunSummary(
            problem_name=context.problem_name,
            base_ddar_solved=True,
            solved=True,
            solved_attempt_idx=0,
            total_attempts_executed=0,
            elapsed_time_s=time.time() - problem_start,
            output_path=str(output_path),
        )
        append_jsonl_record(output_path, {"type": "summary", **asdict(summary)})
        return summary

    solved_attempt_idx: int | None = None
    attempts_executed = 0

    for attempt_idx in range(1, max_attempts + 1):
        result = run_single_attempt(
            client=client,
            context=context,
            attempt_idx=attempt_idx,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        attempts_executed = attempt_idx
        append_jsonl_record(output_path, {"type": "attempt", **asdict(result)})
        usage = result.usage or {}
        print(
            "attempt={attempt} status={status} requested_model={requested_model} "
            "actual_model={actual_model} total_tokens={total_tokens} cost={cost}".format(
                attempt=result.attempt_idx,
                status=result.verification_status,
                requested_model=result.model,
                actual_model=result.actual_model,
                total_tokens=usage.get("total_tokens"),
                cost=usage.get("cost"),
            )
        )
        if result.verification_status == "solved":
            solved_attempt_idx = attempt_idx
            break

    summary = RunSummary(
        problem_name=context.problem_name,
        base_ddar_solved=False,
        solved=solved_attempt_idx is not None,
        solved_attempt_idx=solved_attempt_idx,
        total_attempts_executed=attempts_executed,
        elapsed_time_s=time.time() - problem_start,
        output_path=str(output_path),
    )
    append_jsonl_record(output_path, {"type": "summary", **asdict(summary)})
    return summary


def main() -> None:
    args = parse_args()
    client = create_client()
    max_attempts = SMOKE_TEST_ATTEMPTS if args.smoke_test else args.max_attempts
    output_path, csv_path = build_output_paths(
        output_dir=args.output_dir,
        problems_path=args.problems_path,
        model=args.model,
        max_attempts=max_attempts,
    )
    problem_names = load_problem_names(args.problems_path, args.problem_name)
    run_start = time.time()
    all_tasks_info: list[tuple[str, str, int | str, float]] = [
        (problem_name, "Pending", "-", 0.0) for problem_name in problem_names
    ]

    with Live(refresh_per_second=1) as live:
        live.update(render_table(all_tasks_info, run_start, True))
        for idx, problem_name in enumerate(problem_names):
            context = build_problem_context(
                problems_path=args.problems_path,
                problem_name=problem_name,
                defs_path=args.defs_path,
                rules_path=args.rules_path,
                prompt_path=args.prompt_path,
                render_dir=args.render_dir,
                rename=args.rename,
                seed=args.seed,
            )
            summary = run_problem(
                client=client,
                context=context,
                output_path=output_path,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                max_attempts=max_attempts,
                timeout=args.timeout,
            )
            status = "Success" if summary.solved else "Failed"
            all_tasks_info[idx] = (
                summary.problem_name,
                status,
                summary.total_attempts_executed,
                summary.elapsed_time_s,
            )
            live.update(render_table(all_tasks_info, run_start, True))
        live.update(render_table(all_tasks_info, run_start, False))

    solved_count = sum(1 for _, status, _, _ in all_tasks_info if status == "Success")
    write_summary_csv(
        csv_path=csv_path,
        dataset_path=args.problems_path,
        all_tasks_info=all_tasks_info,
    )
    print(
        "dataset={dataset} solved={solved}/{total} output={output} csv={csv}".format(
            dataset=args.problems_path,
            solved=solved_count,
            total=len(all_tasks_info),
            output=output_path,
            csv=csv_path,
        )
    )


if __name__ == "__main__":
    main()
