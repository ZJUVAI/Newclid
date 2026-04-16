#!/usr/bin/env python3
"""
Analysis + aux validation script for geometry JSONL datasets.

In a single pass over the file:
  1. Computes distribution statistics (points, predicates, proof length, aux content)
  2. Reservoir-samples aux-eligible records (1% by default, capped at 10k)

After the pass, sampled records are dispatched to Ray workers. Each worker
processes a batch of problems with CSolver to reduce per-problem scheduling
overhead.
"""

import argparse
import json
import random
import re
import signal
import statistics
import time
from collections import Counter, defaultdict
from itertools import islice
from typing import Iterable

import ray
from tqdm import tqdm


# ============================================================================
# SHARED TAG HELPERS
# ============================================================================


def extract_tag_content(text: str, tag: str) -> str:
    """Extract the inner content of a simple XML-like tag."""
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


# ============================================================================
# STATS EXTRACTION FUNCTIONS
# ============================================================================


def extract_points(problem_text: str) -> set[str]:
    """Extract point names from the problem text."""
    points = set()
    for segment in problem_text.split(";"):
        segment = segment.strip()
        if ":" not in segment:
            continue
        before_colon = segment.split(":", 1)[0].strip()
        points.update(token for token in before_colon.split() if token)
    return points


def extract_predicates_before_after_question(
    problem_text: str,
) -> tuple[list[str], list[str]]:
    """Extract predicates before and after the ? mark."""
    parts = problem_text.split("?")
    if len(parts) != 2:
        return [], []

    def extract_predicates_from_part(part: str) -> list[str]:
        predicates = []
        for segment in part.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            if ":" in segment:
                after_colon = segment.split(":", 1)[1].strip()
                predicates.extend(
                    re.findall(r"([a-z]+)\s+[a-z\s]+\s*\[\d+\]", after_colon)
                )
                continue
            before_bracket = (
                segment.split("[", 1)[0].strip() if "[" in segment else segment
            )
            tokens = before_bracket.split()
            if tokens:
                predicates.append(tokens[0])
        return predicates

    return extract_predicates_from_part(parts[0]), extract_predicates_from_part(
        parts[1]
    )


def parse_aux_stats(llm_output: str) -> tuple[list[tuple[str, ...]], int, list[int]]:
    """Extract aux predicate combinations and per-segment point counts in one pass."""
    aux_content = extract_tag_content(llm_output, "aux")
    if not aux_content:
        return [], 0, []

    combinations: list[tuple[str, ...]] = []
    points_per_segment: list[int] = []

    for segment in aux_content.split(";"):
        segment = segment.strip()
        if not segment or ":" not in segment:
            continue

        before_colon, after_colon = segment.split(":", 1)
        predicates = re.findall(r"([a-z]+)\s+[a-z\s]+\s*\[\d+\]", after_colon.strip())
        if predicates:
            combinations.append(tuple(sorted(predicates)))

        points = [p for p in before_colon.strip().split() if p and p != "x00"]
        points_per_segment.append(len(points))

    return combinations, len(points_per_segment), points_per_segment


def count_proof_semicolons(llm_output: str) -> int:
    """Count semicolons in <proof> section."""
    return extract_tag_content(llm_output, "proof").count(";")


# ============================================================================
# AUX PREPROCESSING HELPERS
# ============================================================================


def extract_aux_points(llm_output: str) -> set[str]:
    """Extract new point names from <aux> tags."""
    aux_content = extract_tag_content(llm_output, "aux")
    if not aux_content:
        return set()

    points = set()
    for segment in aux_content.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        match = re.match(r"x\d+\s+(.*?)\s*:\s*.*", segment)
        if match:
            points.update(match.group(1).strip().split())
    return points


def extract_aux_segments(llm_output: str) -> list[str]:
    """Extract individual aux DSL segments without xNN prefixes."""
    aux_content = extract_tag_content(llm_output, "aux")
    if not aux_content:
        return []

    segments = []
    for segment in aux_content.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        segment = re.sub(r"^x\d+\s+", "", segment).strip()
        if segment:
            segments.append(segment)
    return segments


# ============================================================================
# VALIDATION
# ============================================================================


class SolverTimeout(Exception):
    """Raised when solver execution exceeds the worker timeout."""


def run_with_timeout(solver, timeout_seconds: int, max_level: int) -> bool:
    """Run CSolver with a hard timeout inside the worker process."""

    def _handle_timeout(signum, frame):
        raise SolverTimeout()

    previous_handler = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(timeout_seconds)
    try:
        return solver.run(max_level=max_level)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def translate_dsl_to_construction(
    point: str, predicate: str, args: list[str]
) -> str | None:
    """Translate one aux DSL predicate into a constructive clause."""
    from newclid.predicates.collinearity import Coll
    from newclid.predicates.congruence import Cong
    from newclid.predicates.cyclic import Cyclic
    from newclid.predicates.equal_angles import EqAngle
    from newclid.predicates.equal_ratios import EqRatio
    from newclid.predicates.midpoint import MidPoint
    from newclid.predicates.parallelism import Para
    from newclid.predicates.perpendicularity import Perp

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
    if predicate == "cyclic":
        return Cyclic.to_constructive(point, tuple(args))
    if predicate == "eqratio":
        return EqRatio.to_constructive(point, tuple(args))
    if predicate == "eqangle":

        def arrange_angle_points(
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

        if len(args) != 8:
            return None
        a, b, c, d, e, f, g, h = args
        if len({a, b, c, d, e, f, g, h}) == 8:
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
            return None

        if len({a, b, c, d}) == 4 and len({a, b, e, f}) == 3:
            a, b, c, d, e, f, g, h = a, b, e, f, c, d, g, h
        left = arrange_angle_points(a, b, c, d)
        right = arrange_angle_points(e, f, g, h)
        if left is None or right is None:
            return None
        return EqAngle.to_constructive(point, left + right)

    return f"{predicate} {' '.join(args)}"


def try_dsl_to_constructions(content: str) -> str | None:
    """Translate one aux DSL segment into a construction assignment."""
    if ":" not in content:
        return None

    points_part, premises_part = re.split(r"\s*:\s*", content, maxsplit=1)
    points = [token for token in points_part.strip().split() if token]
    if len(points) != 1:
        return None
    point = points[0]

    premises = re.split(r"\s*\[\d+\]", premises_part)
    premises = [segment.strip() for segment in premises if segment.strip()]
    if len(premises) > 2:
        return None
    if not premises:
        return f"{point} = free {point}"

    constructions = []
    for premise in premises:
        parts = premise.split()
        if not parts or not parts[0].isalpha():
            return None
        construction = translate_dsl_to_construction(point, parts[0], parts[1:])
        if construction is None:
            return None
        constructions.append(construction)
    return point + " = " + ", ".join(constructions)


def solve_problem(
    problem_text: str, problem_name: str, seed: int, max_level: int
) -> dict:
    """Build and solve a problem with CSolver, separating build and run failures."""
    import_start = time.perf_counter()
    from newclid.api import CSolver, GeometricSolverBuilder

    import_seconds = time.perf_counter() - import_start

    build_start = time.perf_counter()
    try:
        geometric_solver = (
            GeometricSolverBuilder(seed)
            .load_problem_from_txt(problem_text)
            .build(max_attempts=1000)
        )
        solver = CSolver(
            problem=problem_text,
            problem_name=problem_name,
            seed=seed,
            solver=geometric_solver,
            using_log=True,
        )
    except Exception as e:
        build_seconds = time.perf_counter() - build_start
        return {
            "built": False,
            "solved": False,
            "timeout": False,
            "error_msg": str(e),
            "import_seconds": import_seconds,
            "build_seconds": build_seconds,
            "run_seconds": 0.0,
            "total_seconds": import_seconds + build_seconds,
        }

    build_seconds = time.perf_counter() - build_start
    run_start = time.perf_counter()
    try:
        solved = run_with_timeout(solver, timeout_seconds=60, max_level=max_level)
        run_seconds = time.perf_counter() - run_start
        return {
            "built": True,
            "solved": bool(solved),
            "timeout": False,
            "error_msg": "",
            "import_seconds": import_seconds,
            "build_seconds": build_seconds,
            "run_seconds": run_seconds,
            "total_seconds": import_seconds + build_seconds + run_seconds,
        }
    except SolverTimeout:
        run_seconds = time.perf_counter() - run_start
        return {
            "built": True,
            "solved": False,
            "timeout": True,
            "error_msg": "",
            "import_seconds": import_seconds,
            "build_seconds": build_seconds,
            "run_seconds": run_seconds,
            "total_seconds": import_seconds + build_seconds + run_seconds,
        }


def validate_one_sample(record: dict, seed: int, max_level: int) -> dict:
    """Validate one aux sample with base-build/base-solve/aux-translation/with-aux-solve."""
    total_start = time.perf_counter()
    problem_import_start = time.perf_counter()
    from newclid.formulations.problem import ProblemJGEX

    problem_import_seconds = time.perf_counter() - problem_import_start

    line_num = record["line_num"]
    fl_problem = record["fl_problem"]
    llm_output_renamed = record["llm_output_renamed"]

    try:
        aux_parse_start = time.perf_counter()
        aux_segments = extract_aux_segments(llm_output_renamed)
        aux_parse_seconds = time.perf_counter() - aux_parse_start
        if not aux_segments:
            return {
                "line_num": line_num,
                "status": "error",
                "error_msg": "empty aux segments",
                "base_built": False,
                "base_solved": False,
                "aux_segment_count": 0,
                "translated_segment_count": 0,
                "aux_translation_ok": False,
                "with_aux_built": None,
                "with_aux_solved": None,
                "aux_parse_seconds": aux_parse_seconds,
                "aux_translation_seconds": 0.0,
                "base_build_seconds": 0.0,
                "base_run_seconds": 0.0,
                "with_aux_build_seconds": 0.0,
                "with_aux_run_seconds": 0.0,
                "base_import_seconds": 0.0,
                "with_aux_import_seconds": 0.0,
                "problem_import_seconds": problem_import_seconds,
                "total_seconds": time.perf_counter() - total_start,
            }

        base_result = solve_problem(
            fl_problem, f"line_{line_num}_base", seed, max_level
        )
        result = {
            "line_num": line_num,
            "status": "",
            "error_msg": base_result["error_msg"],
            "base_built": base_result["built"],
            "base_solved": base_result["solved"],
            "aux_segment_count": len(aux_segments),
            "translated_segment_count": 0,
            "aux_translation_ok": False,
            "with_aux_built": None,
            "with_aux_solved": None,
            "aux_parse_seconds": aux_parse_seconds,
            "aux_translation_seconds": 0.0,
            "base_build_seconds": base_result["build_seconds"],
            "base_run_seconds": base_result["run_seconds"],
            "base_import_seconds": base_result["import_seconds"],
            "with_aux_build_seconds": 0.0,
            "with_aux_run_seconds": 0.0,
            "with_aux_import_seconds": 0.0,
            "problem_import_seconds": problem_import_seconds,
            "total_seconds": 0.0,
        }

        if base_result["timeout"]:
            result["status"] = "base_timeout"
            result["total_seconds"] = time.perf_counter() - total_start
            return result
        if not base_result["built"]:
            result["status"] = "base_build_failed"
            result["total_seconds"] = time.perf_counter() - total_start
            return result

        translation_start = time.perf_counter()
        translated = []
        for segment in aux_segments:
            construction = try_dsl_to_constructions(segment)
            if construction is not None:
                translated.append(construction)
        result["aux_translation_seconds"] = time.perf_counter() - translation_start

        result["translated_segment_count"] = len(translated)
        result["aux_translation_ok"] = len(translated) == len(aux_segments)

        if base_result["solved"]:
            result["status"] = "base_solved"
            result["total_seconds"] = time.perf_counter() - total_start
            return result

        if not result["aux_translation_ok"]:
            result["status"] = "aux_translation_failed"
            result["total_seconds"] = time.perf_counter() - total_start
            return result

        augment_start = time.perf_counter()
        problem_with_aux = ProblemJGEX.from_text(fl_problem).with_more_construction(
            "; ".join(translated)
        )
        result["augment_problem_seconds"] = time.perf_counter() - augment_start
        with_aux_result = solve_problem(
            str(problem_with_aux),
            f"line_{line_num}_with_aux",
            seed,
            max_level,
        )
        result["with_aux_built"] = with_aux_result["built"]
        result["with_aux_solved"] = with_aux_result["solved"]
        result["with_aux_import_seconds"] = with_aux_result["import_seconds"]
        result["with_aux_build_seconds"] = with_aux_result["build_seconds"]
        result["with_aux_run_seconds"] = with_aux_result["run_seconds"]
        if with_aux_result["error_msg"]:
            result["error_msg"] = with_aux_result["error_msg"]

        if with_aux_result["timeout"]:
            result["status"] = "with_aux_timeout"
        elif not with_aux_result["built"]:
            result["status"] = "with_aux_build_failed"
        elif with_aux_result["solved"]:
            result["status"] = "solved_with_aux"
        else:
            result["status"] = "unsolved_with_aux"
        result["total_seconds"] = time.perf_counter() - total_start
        return result
    except Exception as e:
        return {
            "line_num": line_num,
            "status": "failed",
            "error_msg": str(e),
            "base_built": False,
            "base_solved": False,
            "aux_segment_count": 0,
            "translated_segment_count": 0,
            "aux_translation_ok": False,
            "with_aux_built": None,
            "with_aux_solved": None,
            "aux_parse_seconds": 0.0,
            "aux_translation_seconds": 0.0,
            "base_build_seconds": 0.0,
            "base_run_seconds": 0.0,
            "with_aux_build_seconds": 0.0,
            "with_aux_run_seconds": 0.0,
            "base_import_seconds": 0.0,
            "with_aux_import_seconds": 0.0,
            "problem_import_seconds": 0.0,
            "total_seconds": time.perf_counter() - total_start,
        }


@ray.remote(num_cpus=1, max_retries=0)
def validate_sample_batch(records: list[dict], seed: int, max_level: int) -> list[dict]:
    """Validate a batch of aux samples in one Ray task to reduce scheduling overhead."""
    return [validate_one_sample(record, seed, max_level) for record in records]


def chunked(items: list[dict], chunk_size: int) -> Iterable[list[dict]]:
    """Yield fixed-size chunks from a list."""
    iterator = iter(items)
    while True:
        chunk = list(islice(iterator, chunk_size))
        if not chunk:
            return
        yield chunk


def choose_batch_size(num_samples: int, num_workers: int) -> int:
    """Choose a batch size large enough to amortize Ray scheduling overhead."""
    if num_samples <= 0:
        return 1
    target_batches = max(num_workers * 2, 1)
    batch_size = (num_samples + target_batches - 1) // target_batches
    return max(8, min(128, batch_size))


# ============================================================================
# COMBINED SINGLE-PASS WITH RESERVOIR SAMPLING
# ============================================================================


def collect_stats_and_sample(file_path: str, sample_rate: float, cap: int, seed: int):
    """
    Single pass over the JSONL file:
    - Accumulates all distribution statistics
    - Reservoir-samples validation-eligible aux records (O(cap) memory)

    Returns (stats_tuple, sampled_candidates, total_aux_count, eligible_aux_count)
    """
    rng = random.Random(seed)

    total_records = 0
    point_counts = Counter()
    predicates_before = Counter()
    predicates_after = Counter()
    aux_predicate_combinations = Counter()
    aux_segment_counts = Counter()
    aux_points_per_segment = Counter()
    proof_lengths = []
    aux_count = 0
    eligible_aux_count = 0
    parse_errors = 0
    processing_errors = 0

    reservoir = []

    print(f"Analyzing {file_path}...")
    with open(file_path, "r") as f:
        for i, line in enumerate(tqdm(f, desc="Processing"), 1):
            try:
                total_records += 1
                data = json.loads(line.strip())
                llm_input = data["llm_input_renamed"]
                llm_output = data["llm_output_renamed"]
                fl_problem = data.get("fl_problem", "")

                if "<aux>" in llm_output:
                    aux_count += 1
                    combinations, seg_count, pts_per_seg = parse_aux_stats(llm_output)
                    for combo in combinations:
                        aux_predicate_combinations[combo] += 1
                    aux_segment_counts[seg_count] += 1
                    for pts in pts_per_seg:
                        aux_points_per_segment[pts] += 1

                    if fl_problem:
                        eligible_aux_count += 1
                        record = {
                            "line_num": i,
                            "fl_problem": fl_problem,
                            "llm_output_renamed": llm_output,
                        }
                        if len(reservoir) < cap:
                            reservoir.append(record)
                        else:
                            j = rng.randint(0, eligible_aux_count - 1)
                            if j < cap:
                                reservoir[j] = record

                problem_text = extract_tag_content(llm_input, "problem")
                if problem_text:
                    points = extract_points(problem_text)
                    point_counts[len(points)] += 1
                    before_preds, after_preds = (
                        extract_predicates_before_after_question(problem_text)
                    )
                    predicates_before.update(before_preds)
                    predicates_after.update(after_preds)

                proof_lengths.append(count_proof_semicolons(llm_output))

            except json.JSONDecodeError as e:
                parse_errors += 1
                print(f"Error parsing line {i}: {e}")
            except Exception as e:
                processing_errors += 1
                print(f"Error processing line {i}: {e}")

    target = min(int(eligible_aux_count * sample_rate), cap)
    if len(reservoir) > target:
        reservoir = rng.sample(reservoir, target)

    stats_tuple = (
        total_records,
        point_counts,
        predicates_before,
        predicates_after,
        aux_predicate_combinations,
        proof_lengths,
        aux_count,
        aux_segment_counts,
        aux_points_per_segment,
        parse_errors,
        processing_errors,
    )
    return stats_tuple, reservoir, aux_count, eligible_aux_count


# ============================================================================
# REPORTING
# ============================================================================


def generate_report(
    total_records,
    point_counts,
    predicates_before,
    predicates_after,
    aux_predicate_combinations,
    proof_lengths,
    aux_count,
    aux_segment_counts,
    aux_points_per_segment,
    parse_errors,
    processing_errors,
):
    print("\n" + "=" * 80)
    print("GEOMETRY DATASET ANALYSIS REPORT")
    print("=" * 80)

    print("\n0. AUXILIARY CONTENT ANALYSIS")
    print("-" * 40)
    aux_ratio = (aux_count / total_records) * 100 if total_records > 0 else 0
    print(f"Total samples analyzed: {total_records:,}")
    print(f"Samples containing '<aux>': {aux_count:,} ({aux_ratio:.2f}%)")
    print(
        f"Samples without '<aux>': {total_records - aux_count:,} ({100 - aux_ratio:.2f}%)"
    )
    if parse_errors or processing_errors:
        print(f"Parse errors: {parse_errors:,}")
        print(f"Processing errors: {processing_errors:,}")

    if aux_predicate_combinations:
        print("\nAuxiliary Predicate Combination Distribution:")
        total_aux_combinations = sum(aux_predicate_combinations.values())
        for combo, count in aux_predicate_combinations.most_common():
            percentage = (count / total_aux_combinations) * 100
            combo_str = "[" + ", ".join(combo) + "]"
            print(f"  {combo_str}: {count:,} ({percentage:.2f}%)")

    if aux_segment_counts:
        print("\nAuxiliary Segment Count Distribution:")
        total_aux_samples = sum(aux_segment_counts.values())
        for num_segments in sorted(aux_segment_counts.keys()):
            count = aux_segment_counts[num_segments]
            percentage = (count / total_aux_samples) * 100
            print(f"  {num_segments} segments: {count:,} samples ({percentage:.2f}%)")

    if aux_points_per_segment:
        print("\nAuxiliary Points Per Segment Distribution:")
        total_segments = sum(aux_points_per_segment.values())
        for num_points in sorted(aux_points_per_segment.keys()):
            count = aux_points_per_segment[num_points]
            percentage = (count / total_segments) * 100
            print(f"  {num_points} points: {count:,} segments ({percentage:.2f}%)")

    print("\n1. POINT DISTRIBUTION ANALYSIS")
    print("-" * 40)
    for num_points in sorted(point_counts.keys()):
        count = point_counts[num_points]
        percentage = (count / total_records) * 100 if total_records > 0 else 0
        print(f"  {num_points} points: {count:,} samples ({percentage:.2f}%)")

    print("\n2. PREDICATE DISTRIBUTION ANALYSIS")
    print("-" * 40)
    print("\nPredicates BEFORE '?' (Given conditions):")
    total_before = sum(predicates_before.values())
    for pred, count in predicates_before.most_common():
        percentage = (count / total_before) * 100 if total_before > 0 else 0
        print(f"  {pred}: {count:,} ({percentage:.2f}%)")

    print("\nPredicates AFTER '?' (Goals to prove):")
    total_after = sum(predicates_after.values())
    for pred, count in predicates_after.most_common():
        percentage = (count / total_after) * 100 if total_after > 0 else 0
        print(f"  {pred}: {count:,} ({percentage:.2f}%)")

    print("\n3. PROOF LENGTH ANALYSIS")
    print("-" * 40)
    if proof_lengths:
        print(f"Total proofs analyzed: {len(proof_lengths):,}")
        print(f"Average proof length: {statistics.mean(proof_lengths):.2f} steps")
        print(f"Median proof length: {statistics.median(proof_lengths):.1f} steps")
        print(f"Min proof length: {min(proof_lengths)} steps")
        print(f"Max proof length: {max(proof_lengths)} steps")
        print(f"Standard deviation: {statistics.pstdev(proof_lengths):.2f}")

        proof_length_dist = Counter(proof_lengths)
        bin_counts = defaultdict(int)
        for length, count in proof_length_dist.items():
            if length < 20:
                bin_counts[(length, length)] += count
            elif length < 100:
                bin_start = (length // 10) * 10
                bin_counts[(bin_start, bin_start + 9)] += count
            elif length < 200:
                bin_start = (length // 20) * 20
                bin_counts[(bin_start, bin_start + 19)] += count
            else:
                bin_start = (length // 50) * 50
                bin_counts[(bin_start, bin_start + 49)] += count

        min_length = min(proof_length_dist.keys())
        max_length = max(proof_length_dist.keys())
        print(f"\nProof length distribution (full range: {min_length}-{max_length}):")
        for (start, end), count in sorted(bin_counts.items()):
            percentage = (count / len(proof_lengths)) * 100
            if start == end:
                print(f"  {start} steps: {count:,} proofs ({percentage:.2f}%)")
            else:
                print(f"  {start}-{end} steps: {count:,} proofs ({percentage:.2f}%)")


def summarize_seconds(results: list[dict], field: str) -> str:
    """Summarize timing values for a validation phase."""
    values = [r.get(field, 0.0) for r in results if r.get(field, 0.0) > 0]
    if not values:
        return "n=0"
    values = sorted(values)
    p95_index = min(len(values) - 1, int(len(values) * 0.95))
    return (
        f"n={len(values):,}, mean={statistics.mean(values):.3f}s, "
        f"median={statistics.median(values):.3f}s, "
        f"p95={values[p95_index]:.3f}s, max={values[-1]:.3f}s"
    )


_T = "\u251c\u2500\u2500 "  # ├──
_L = "\u2514\u2500\u2500 "  # └──
_I = "\u2502   "  # │


def _fmt(count: int, parent: int | None = None) -> str:
    """Format count with percentage relative to parent."""
    s = f"{count:,}"
    if parent is not None and parent > 0:
        s += f"  ({count / parent:.1%})"
    return s


def _line(prefix: str, label: str, count: int, parent: int | None = None) -> None:
    """Print a single tree line with indent, prefix, label and count."""
    print(f"  {prefix}{label}: {_fmt(count, parent)}")


def _render_tree(
    children: list[tuple[str, int, list]],
    prefix: str,
    parent: int | None,
) -> None:
    """Recursively render a tree branch.

    Each child is (label, count, sub_children).
    Automatically picks ├── vs └── and manages │ continuations.
    """
    for i, (label, count, sub) in enumerate(sorted(children, key=lambda c: c[1])):
        is_last = i == len(children) - 1
        connector = _L if is_last else _T
        _line(prefix + connector, label, count, parent)
        if sub:
            continuation = _I if not is_last else "    "
            _render_tree(sub, prefix + continuation, parent)


def generate_validation_report(results: list[dict], total_aux_count: int):
    total = len(results)
    base_built = sum(1 for r in results if r.get("base_built"))
    base_solved = sum(1 for r in results if r.get("base_solved"))
    base_unsolved = sum(
        1 for r in results if r.get("base_built") and not r.get("base_solved")
    )
    total_aux_segments = sum(r.get("aux_segment_count", 0) for r in results)
    translated_aux_segments = sum(r.get("translated_segment_count", 0) for r in results)
    aux_translation_ok = sum(1 for r in results if r.get("aux_translation_ok"))
    solved_with_aux = sum(1 for r in results if r.get("status") == "solved_with_aux")
    with_aux_build_failed = sum(
        1 for r in results if r.get("status") == "with_aux_build_failed"
    )
    with_aux_timeout = sum(1 for r in results if r.get("status") == "with_aux_timeout")
    base_build_failed = sum(
        1 for r in results if r.get("status") == "base_build_failed"
    )
    base_timeout = sum(1 for r in results if r.get("status") == "base_timeout")
    translation_failed = sum(
        1 for r in results if r.get("status") == "aux_translation_failed"
    )
    unsolved_with_aux = sum(
        1 for r in results if r.get("status") == "unsolved_with_aux"
    )
    errors = sum(1 for r in results if r.get("status") in {"error", "failed"})
    eligible_with_aux = sum(
        1
        for r in results
        if r.get("base_built")
        and not r.get("base_solved")
        and r.get("aux_translation_ok")
    )

    print("\n" + "=" * 80)
    print("AUX VALIDATION RESULTS")
    print("=" * 80)

    if total == 0:
        print("\n  No samples to validate.")
        return

    # Build the tree structure bottom-up
    with_aux_children = [("Solved with aux", solved_with_aux, [])]
    if unsolved_with_aux > 0:
        with_aux_children.append(("Unsolved with aux", unsolved_with_aux, []))
    if with_aux_timeout > 0:
        with_aux_children.append(("Timeout with aux", with_aux_timeout, []))

    translation_ok_children = [
        ("With-aux build ok", eligible_with_aux, with_aux_children)
    ]
    if with_aux_build_failed > 0:
        translation_ok_children.append(
            ("Build failed with aux", with_aux_build_failed, [])
        )

    base_unsolved_children = [
        ("Full translation ok", aux_translation_ok, translation_ok_children)
    ]
    if translation_failed > 0:
        base_unsolved_children.append(("Translation failed", translation_failed, []))

    base_build_ok_children = [
        ("Base solved (no aux needed)", base_solved, []),
        ("Base unsolved (aux candidates)", base_unsolved, base_unsolved_children),
    ]

    root_children = [("Base build ok", base_built, base_build_ok_children)]
    base_build_err = base_build_failed + base_timeout
    if base_build_err > 0:
        root_children.append(("Build failed / timeout", base_build_err, []))
    if errors > 0:
        root_children.append(("Errors", errors, []))

    # Render tree
    print(f"\n  Sampled: {total:,} / {total_aux_count:,}")
    _render_tree(root_children, "", total)

    if total_aux_segments > 0:
        seg_pct = translated_aux_segments / total_aux_segments
        print(
            f"  (segments translated: {translated_aux_segments:,} / {total_aux_segments:,} = {seg_pct:.1%})"
        )

    # -- Timing --
    print("\n  Timing:")
    print(f"    Total/sample:        {summarize_seconds(results, 'total_seconds')}")
    print(
        f"    Problem import:      {summarize_seconds(results, 'problem_import_seconds')}"
    )
    print(f"    Aux parse:           {summarize_seconds(results, 'aux_parse_seconds')}")
    print(
        f"    Base CSolver import: {summarize_seconds(results, 'base_import_seconds')}"
    )
    print(
        f"    Base build:          {summarize_seconds(results, 'base_build_seconds')}"
    )
    print(f"    Base run:            {summarize_seconds(results, 'base_run_seconds')}")
    print(
        f"    Aux translation:     {summarize_seconds(results, 'aux_translation_seconds')}"
    )
    print(
        f"    Augment problem:     {summarize_seconds(results, 'augment_problem_seconds')}"
    )
    print(
        f"    With-aux import:     {summarize_seconds(results, 'with_aux_import_seconds')}"
    )
    print(
        f"    With-aux build:      {summarize_seconds(results, 'with_aux_build_seconds')}"
    )
    print(
        f"    With-aux run:        {summarize_seconds(results, 'with_aux_run_seconds')}"
    )


# ============================================================================
# MAIN
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Analyze geometry JSONL dataset and validate aux constructions."
    )
    parser.add_argument("input_file", help="Path to JSONL dataset file")
    parser.add_argument(
        "--seed", type=int, default=123, help="Random seed (default: 123)"
    )
    parser.add_argument(
        "--max-level", type=int, default=500, help="CSolver max level (default: 500)"
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=0.01,
        help="Fraction of aux records to validate (default: 0.01)",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=10_000,
        help="Max validation samples (default: 10000)",
    )
    parser.add_argument(
        "--num-workers", type=int, default=10, help="Ray CPU workers (default: 10)"
    )
    parser.add_argument(
        "--skip-validation", action="store_true", help="Skip aux validation, stats only"
    )
    args = parser.parse_args()

    stats_tuple, sample, total_aux_count, eligible_aux_count = collect_stats_and_sample(
        args.input_file, args.sample_rate, args.cap, args.seed
    )

    generate_report(*stats_tuple)

    print("\n" + "=" * 80)
    print("Analysis complete!")
    print("=" * 80)

    if args.skip_validation or args.sample_rate == 0:
        return

    if not sample:
        print("\nNo aux candidates found for validation.")
        return

    print(
        f"\nAux validation: {len(sample):,} samples selected from "
        f"{eligible_aux_count:,} validation-eligible aux candidates "
        f"({total_aux_count:,} total aux samples)"
    )

    batch_size = choose_batch_size(len(sample), args.num_workers)
    batches = list(chunked(sample, batch_size))
    results: list[dict] = []

    if args.num_workers <= 1:
        print(f"Using single-thread validation with batch size {batch_size}.")
        with tqdm(total=len(sample), desc="Validating aux samples") as pbar:
            for batch in batches:
                batch_results = validate_sample_batch._function(
                    batch, args.seed, args.max_level
                )
                results.extend(batch_results)
                pbar.update(len(batch_results))
    else:
        ray.init(
            num_cpus=args.num_workers,
            ignore_reinit_error=True,
            dashboard_host="0.0.0.0",
            runtime_env={"working_dir": None},
        )

        print(f"Using {len(batches):,} Ray tasks with batch size {batch_size}.")
        futures = [
            validate_sample_batch.remote(batch, args.seed, args.max_level)
            for batch in batches
        ]

        pending = list(futures)
        with tqdm(total=len(sample), desc="Validating aux samples") as pbar:
            while pending:
                done, pending = ray.wait(pending, num_returns=1, timeout=10)
                for ref in done:
                    batch_results = ray.get(ref)
                    results.extend(batch_results)
                    pbar.update(len(batch_results))

    generate_validation_report(results, total_aux_count)


if __name__ == "__main__":
    main()
