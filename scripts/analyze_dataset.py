#!/usr/bin/env python3
"""
Analyze geometry JSONL datasets and optionally validate aux constructions.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import signal
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import ray
from tqdm import tqdm

from newclid.generation.aux_translation import (
    extract_tag_content,
    extract_tag_segments,
    split_segments,
    translate_aux_segment,
)


STATUS_ERROR = "error"
STATUS_FAILED = "failed"
STATUS_BASE_TIMEOUT = "base_timeout"
STATUS_BASE_BUILD_FAILED = "base_build_failed"
STATUS_BASE_SOLVED = "base_solved"
STATUS_AUX_TRANSLATION_FAILED = "aux_translation_failed"
STATUS_WITH_AUX_TIMEOUT = "with_aux_timeout"
STATUS_WITH_AUX_BUILD_FAILED = "with_aux_build_failed"
STATUS_SOLVED_WITH_AUX = "solved_with_aux"
STATUS_UNSOLVED_WITH_AUX = "unsolved_with_aux"

PREDICATE_RE = re.compile(r"([a-z]+)\s+[a-z\s]+\s*\[\d+\]")


@dataclass
class AnalyzeConfig:
    input_file: str
    seed: int
    max_level: int
    sample_rate: float
    cap: int
    num_workers: int
    skip_validation: bool


@dataclass
class ValidationSample:
    line_num: int
    fl_problem: str
    llm_output: str


@dataclass
class ValidationResult:
    line_num: int
    status: str
    error_msg: str = ""
    base_built: bool = False
    base_solved: bool = False
    aux_segment_count: int = 0
    translated_segment_count: int = 0
    aux_translation_ok: bool = False
    with_aux_built: bool | None = None
    with_aux_solved: bool | None = None


@dataclass
class DatasetStats:
    total_records: int = 0
    aux_count: int = 0
    eligible_aux_count: int = 0
    parse_errors: int = 0
    processing_errors: int = 0
    point_counts: Counter[int] = field(default_factory=Counter)
    predicates_before: Counter[str] = field(default_factory=Counter)
    predicates_after: Counter[str] = field(default_factory=Counter)
    aux_predicate_combinations: Counter[tuple[str, ...]] = field(
        default_factory=Counter
    )
    aux_segment_counts: Counter[int] = field(default_factory=Counter)
    aux_points_per_segment: Counter[int] = field(default_factory=Counter)
    proof_lengths: list[int] = field(default_factory=list)


class SolverTimeout(Exception):
    """Raised when solver execution exceeds the worker timeout."""


def extract_points(problem_text: str) -> set[str]:
    points: set[str] = set()
    for segment in split_segments(problem_text):
        if ":" not in segment:
            continue
        points.update(segment.split(":", 1)[0].strip().split())
    return points


def extract_predicates(part: str) -> list[str]:
    predicates: list[str] = []
    for segment in split_segments(part):
        if ":" in segment:
            predicates.extend(PREDICATE_RE.findall(segment.split(":", 1)[1].strip()))
            continue
        head = segment.split("[", 1)[0].strip() if "[" in segment else segment
        tokens = head.split()
        if tokens:
            predicates.append(tokens[0])
    return predicates


def extract_predicates_before_after_question(
    problem_text: str,
) -> tuple[list[str], list[str]]:
    parts = problem_text.split("?")
    if len(parts) != 2:
        return [], []
    return extract_predicates(parts[0]), extract_predicates(parts[1])


def parse_aux_stats(
    aux_segments: list[str],
) -> tuple[list[tuple[str, ...]], int, list[int]]:
    if not aux_segments:
        return [], 0, []

    combinations: list[tuple[str, ...]] = []
    points_per_segment: list[int] = []
    for segment in aux_segments:
        if ":" not in segment:
            continue
        before_colon, after_colon = segment.split(":", 1)
        predicates = PREDICATE_RE.findall(after_colon.strip())
        if predicates:
            combinations.append(tuple(sorted(predicates)))
        points_per_segment.append(
            len([token for token in before_colon.strip().split() if token != "x00"])
        )
    return combinations, len(points_per_segment), points_per_segment


def count_proof_steps(llm_output: str) -> int:
    return extract_tag_content(llm_output, "proof").count(";")


def run_with_timeout(solver: object, timeout_seconds: int, max_level: int) -> bool:
    def handle_timeout(signum: int, frame: object) -> None:
        raise SolverTimeout()

    previous_handler = signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(timeout_seconds)
    try:
        return solver.run(max_level=max_level)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def solve_problem(
    problem_text: str, problem_name: str, seed: int, max_level: int
) -> tuple[bool, bool, bool, str]:
    from newclid.api import CSolver, GeometricSolverBuilder

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
        )
    except Exception as exc:
        return False, False, False, str(exc)

    try:
        return (
            True,
            bool(run_with_timeout(solver, timeout_seconds=60, max_level=max_level)),
            False,
            "",
        )
    except SolverTimeout:
        return True, False, True, ""


def validate_sample(
    sample: ValidationSample, seed: int, max_level: int
) -> ValidationResult:
    try:
        aux_segments = extract_tag_segments(
            sample.llm_output, "aux", strip_aux_prefix=True
        )
        if not aux_segments:
            return ValidationResult(
                sample.line_num, STATUS_ERROR, error_msg="empty aux segments"
            )

        base_built, base_solved, base_timeout, base_error = solve_problem(
            sample.fl_problem,
            f"line_{sample.line_num}_base",
            seed,
            max_level,
        )
        result = ValidationResult(
            line_num=sample.line_num,
            status="",
            error_msg=base_error,
            base_built=base_built,
            base_solved=base_solved,
            aux_segment_count=len(aux_segments),
        )
        if base_timeout:
            result.status = STATUS_BASE_TIMEOUT
            return result
        if not base_built:
            result.status = STATUS_BASE_BUILD_FAILED
            return result
        if base_solved:
            result.status = STATUS_BASE_SOLVED
            return result

        translated = [
            item
            for item in (translate_aux_segment(seg) for seg in aux_segments)
            if item
        ]
        result.translated_segment_count = len(translated)
        result.aux_translation_ok = len(translated) == len(aux_segments)
        if not result.aux_translation_ok:
            result.status = STATUS_AUX_TRANSLATION_FAILED
            return result

        from newclid.formulations.problem import ProblemJGEX

        problem_with_aux = str(
            ProblemJGEX.from_text(sample.fl_problem).with_more_construction(
                "; ".join(translated)
            )
        )
        aux_built, aux_solved, aux_timeout, aux_error = solve_problem(
            problem_with_aux,
            f"line_{sample.line_num}_with_aux",
            seed,
            max_level,
        )
        result.with_aux_built = aux_built
        result.with_aux_solved = aux_solved
        if aux_error:
            result.error_msg = aux_error
        if aux_timeout:
            result.status = STATUS_WITH_AUX_TIMEOUT
        elif not aux_built:
            result.status = STATUS_WITH_AUX_BUILD_FAILED
        elif aux_solved:
            result.status = STATUS_SOLVED_WITH_AUX
        else:
            result.status = STATUS_UNSOLVED_WITH_AUX
        return result
    except Exception as exc:
        return ValidationResult(sample.line_num, STATUS_FAILED, error_msg=str(exc))


@ray.remote(num_cpus=1, max_retries=0)
def validate_sample_shard(
    samples: list[ValidationSample],
    seed: int,
    max_level: int,
) -> list[ValidationResult]:
    return [validate_sample(sample, seed, max_level) for sample in samples]


def collect_stats_and_sample(
    config: AnalyzeConfig,
) -> tuple[DatasetStats, list[ValidationSample]]:
    stats = DatasetStats()
    rng = random.Random(config.seed)
    reservoir: list[ValidationSample] = []

    print(f"Analyzing {config.input_file}...")
    with open(config.input_file, "r", encoding="utf-8") as handle:
        for line_num, line in enumerate(tqdm(handle, desc="Processing"), 1):
            stats.total_records += 1
            try:
                record = json.loads(line.strip())
                llm_input = record["llm_input_renamed"]
                llm_output = record["llm_output_renamed"]
                fl_problem = record.get("fl_problem", "")

                aux_segments = extract_tag_segments(llm_output, "aux")
                if aux_segments:
                    stats.aux_count += 1
                    combinations, segment_count, points_per_segment = parse_aux_stats(
                        aux_segments
                    )
                    stats.aux_predicate_combinations.update(combinations)
                    stats.aux_segment_counts[segment_count] += 1
                    stats.aux_points_per_segment.update(points_per_segment)
                    if fl_problem:
                        stats.eligible_aux_count += 1
                        sample = ValidationSample(line_num, fl_problem, llm_output)
                        if len(reservoir) < config.cap:
                            reservoir.append(sample)
                        else:
                            chosen = rng.randint(0, stats.eligible_aux_count - 1)
                            if chosen < config.cap:
                                reservoir[chosen] = sample

                problem_text = extract_tag_content(llm_input, "problem")
                if problem_text:
                    stats.point_counts[len(extract_points(problem_text))] += 1
                    before_preds, after_preds = (
                        extract_predicates_before_after_question(problem_text)
                    )
                    stats.predicates_before.update(before_preds)
                    stats.predicates_after.update(after_preds)
                stats.proof_lengths.append(count_proof_steps(llm_output))
            except json.JSONDecodeError as exc:
                stats.parse_errors += 1
                print(f"Error parsing line {line_num}: {exc}")
            except Exception as exc:
                stats.processing_errors += 1
                print(f"Error processing line {line_num}: {exc}")

    target_size = min(int(stats.eligible_aux_count * config.sample_rate), config.cap)
    if target_size <= 0:
        return stats, []
    if len(reservoir) > target_size:
        reservoir = rng.sample(reservoir, target_size)
    return stats, reservoir


def split_evenly(
    items: list[ValidationSample], parts: int
) -> list[list[ValidationSample]]:
    if parts <= 0:
        return []
    base_size, remainder = divmod(len(items), parts)
    shards: list[list[ValidationSample]] = []
    start = 0
    for index in range(parts):
        stop = start + base_size + (1 if index < remainder else 0)
        if start < stop:
            shards.append(items[start:stop])
        start = stop
    return shards


def format_eta(seconds: float | None) -> str:
    if seconds is None:
        return "--:--:--"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def estimate_eta(started_at: float, completed: int, total: int) -> str:
    if completed <= 0 or completed >= total:
        return format_eta(None if completed <= 0 else 0)
    elapsed = time.perf_counter() - started_at
    return format_eta(elapsed * (total - completed) / completed)


def validate_samples(
    samples: list[ValidationSample], config: AnalyzeConfig
) -> list[ValidationResult]:
    if not samples:
        return []

    worker_count = min(len(samples), config.num_workers)
    shards = split_evenly(samples, worker_count)
    print(
        f"Using {worker_count} Ray workers with shard sizes {[len(shard) for shard in shards]}."
    )

    should_shutdown = False
    if not ray.is_initialized():
        ray.init(
            num_cpus=worker_count, ignore_reinit_error=True, include_dashboard=False
        )
        should_shutdown = True

    futures = [
        validate_sample_shard.remote(shard, config.seed, config.max_level)
        for shard in shards
    ]
    results: list[ValidationResult] = []
    completed = 0
    started_at = time.perf_counter()
    pending = list(futures)

    with tqdm(total=len(samples), desc="Validating aux samples") as progress:
        while pending:
            done, pending = ray.wait(pending, num_returns=1, timeout=1)
            for ref in done:
                shard_results = ray.get(ref)
                results.extend(shard_results)
                completed += len(shard_results)
                progress.update(len(shard_results))
            progress.set_postfix_str(
                f"eta={estimate_eta(started_at, completed, len(samples))}"
            )

    if should_shutdown:
        ray.shutdown()

    results.sort(key=lambda item: item.line_num)
    return results


def build_proof_length_bins(lengths: list[int]) -> list[tuple[tuple[int, int], int]]:
    bins: defaultdict[tuple[int, int], int] = defaultdict(int)
    for length in lengths:
        if length < 20:
            key = (length, length)
        elif length < 100:
            start = (length // 10) * 10
            key = (start, start + 9)
        elif length < 200:
            start = (length // 20) * 20
            key = (start, start + 19)
        else:
            start = (length // 50) * 50
            key = (start, start + 49)
        bins[key] += 1
    return sorted(bins.items())


def print_distribution(
    title: str,
    counter: Counter,
    total: int,
    label,
    *,
    ordered: bool = False,
) -> None:
    if not counter:
        return
    print(f"\n{title}")
    items = (
        ((key, counter[key]) for key in sorted(counter))
        if ordered
        else counter.most_common()
    )
    for key, count in items:
        print(f"  {label(key)}: {count:,} ({(count / total) * 100:.2f}%)")


def generate_stats_report(stats: DatasetStats) -> None:
    print("\n" + "=" * 80)
    print("GEOMETRY DATASET ANALYSIS REPORT")
    print("=" * 80)

    aux_ratio = (
        (stats.aux_count / stats.total_records) * 100 if stats.total_records else 0.0
    )
    print("\n0. AUXILIARY CONTENT ANALYSIS")
    print("-" * 40)
    print(f"Total samples analyzed: {stats.total_records:,}")
    print(f"Samples containing '<aux>': {stats.aux_count:,} ({aux_ratio:.2f}%)")
    print(
        f"Samples without '<aux>': {stats.total_records - stats.aux_count:,} ({100 - aux_ratio:.2f}%)"
    )
    if stats.parse_errors or stats.processing_errors:
        print(f"Parse errors: {stats.parse_errors:,}")
        print(f"Processing errors: {stats.processing_errors:,}")

    print_distribution(
        "Auxiliary Predicate Combination Distribution:",
        stats.aux_predicate_combinations,
        sum(stats.aux_predicate_combinations.values()),
        lambda combo: "[" + ", ".join(combo) + "]",
    )
    print_distribution(
        "Auxiliary Segment Count Distribution:",
        stats.aux_segment_counts,
        sum(stats.aux_segment_counts.values()),
        lambda count: f"{count} segments",
        ordered=True,
    )
    print_distribution(
        "Auxiliary Points Per Segment Distribution:",
        stats.aux_points_per_segment,
        sum(stats.aux_points_per_segment.values()),
        lambda count: f"{count} points",
        ordered=True,
    )

    print("\n1. POINT DISTRIBUTION ANALYSIS")
    print("-" * 40)
    for point_count in sorted(stats.point_counts):
        count = stats.point_counts[point_count]
        print(
            f"  {point_count} points: {count:,} samples ({(count / stats.total_records) * 100:.2f}%)"
        )

    print("\n2. PREDICATE DISTRIBUTION ANALYSIS")
    print("-" * 40)
    print_distribution(
        "Predicates BEFORE '?' (Given conditions):",
        stats.predicates_before,
        sum(stats.predicates_before.values()),
        str,
    )
    print_distribution(
        "Predicates AFTER '?' (Goals to prove):",
        stats.predicates_after,
        sum(stats.predicates_after.values()),
        str,
    )

    print("\n3. PROOF LENGTH ANALYSIS")
    print("-" * 40)
    if not stats.proof_lengths:
        return
    print(f"Total proofs analyzed: {len(stats.proof_lengths):,}")
    print(f"Average proof length: {statistics.mean(stats.proof_lengths):.2f} steps")
    print(f"Median proof length: {statistics.median(stats.proof_lengths):.1f} steps")
    print(f"Min proof length: {min(stats.proof_lengths)} steps")
    print(f"Max proof length: {max(stats.proof_lengths)} steps")
    print(f"Standard deviation: {statistics.pstdev(stats.proof_lengths):.2f}")

    print(
        f"\nProof length distribution (full range: {min(stats.proof_lengths)}-{max(stats.proof_lengths)}):"
    )
    for (start, end), count in build_proof_length_bins(stats.proof_lengths):
        label = f"{start} steps" if start == end else f"{start}-{end} steps"
        print(
            f"  {label}: {count:,} proofs ({(count / len(stats.proof_lengths)) * 100:.2f}%)"
        )


_TREE_BRANCH = "├── "
_TREE_LAST = "└── "
_TREE_CONTINUE = "│   "


def _format_tree_count(count: int, total: int | None = None) -> str:
    text = f"{count:,}"
    if total is not None and total > 0:
        text += f" ({count / total:.1%})"
    return text


def _print_tree_line(
    prefix: str, label: str, count: int, total: int | None = None
) -> None:
    print(f"  {prefix}{label}: {_format_tree_count(count, total)}")


def _tree_depth(node: tuple[str, int, list]) -> int:
    _, count, children = node
    if count <= 0:
        return 0
    visible_children = [child for child in children if child[1] > 0]
    if not visible_children:
        return 1
    return 1 + max(_tree_depth(child) for child in visible_children)


def _render_tree(
    children: list[tuple[str, int, list]], prefix: str, total: int | None
) -> None:
    visible_children = sorted(
        (child for child in children if child[1] > 0),
        key=_tree_depth,
    )
    for index, (label, count, sub_children) in enumerate(visible_children):
        is_last = index == len(visible_children) - 1
        connector = _TREE_LAST if is_last else _TREE_BRANCH
        _print_tree_line(prefix + connector, label, count, total)
        if sub_children:
            child_prefix = "    " if is_last else _TREE_CONTINUE
            _render_tree(sub_children, prefix + child_prefix, total)


def generate_validation_report(
    results: list[ValidationResult], total_aux_count: int
) -> None:
    print("\n" + "=" * 80)
    print("AUX VALIDATION RESULTS")
    print("=" * 80)
    if not results:
        print("\n  No samples to validate.")
        return

    total = len(results)
    status_counts = Counter(result.status for result in results)
    base_built = sum(result.base_built for result in results)
    base_solved = status_counts[STATUS_BASE_SOLVED]
    base_unsolved = sum(
        result.base_built and not result.base_solved for result in results
    )
    translation_ok = sum(
        result.base_built and not result.base_solved and result.aux_translation_ok
        for result in results
    )
    with_aux_built = sum(result.with_aux_built is True for result in results)
    solved_with_aux = status_counts[STATUS_SOLVED_WITH_AUX]
    unsolved_with_aux = status_counts[STATUS_UNSOLVED_WITH_AUX]
    base_build_failed = status_counts[STATUS_BASE_BUILD_FAILED]
    base_timeout = status_counts[STATUS_BASE_TIMEOUT]
    aux_translation_failed = status_counts[STATUS_AUX_TRANSLATION_FAILED]
    with_aux_build_failed = status_counts[STATUS_WITH_AUX_BUILD_FAILED]
    with_aux_timeout = status_counts[STATUS_WITH_AUX_TIMEOUT]
    validation_errors = status_counts[STATUS_ERROR] + status_counts[STATUS_FAILED]
    total_segments = sum(result.aux_segment_count for result in results)
    translated_segments = sum(result.translated_segment_count for result in results)

    print(f"\n  Sampled: {total:,} / {total_aux_count:,}")
    tree = [
        (
            "Base build ok",
            base_built,
            [
                ("Base solved (no aux needed)", base_solved, []),
                (
                    "Base unsolved (aux candidates)",
                    base_unsolved,
                    [
                        (
                            "Aux translation ok",
                            translation_ok,
                            [
                                (
                                    "With-aux build ok",
                                    with_aux_built,
                                    [
                                        ("Solved with aux", solved_with_aux, []),
                                        ("Unsolved with aux", unsolved_with_aux, []),
                                        ("With-aux timeout", with_aux_timeout, []),
                                    ],
                                ),
                                ("With-aux build failed", with_aux_build_failed, []),
                            ],
                        ),
                        ("Aux translation failed", aux_translation_failed, []),
                    ],
                ),
            ],
        ),
        ("Base build failed", base_build_failed, []),
        ("Base timeout", base_timeout, []),
        ("Validation errors", validation_errors, []),
    ]
    _render_tree(tree, "", total)
    if total_segments:
        print(
            f"  Segments translated: {translated_segments:,} / {total_segments:,} "
            f"({translated_segments / total_segments:.1%})"
        )


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_rate(value: str) -> float:
    parsed = float(value)
    if parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def parse_args() -> AnalyzeConfig:
    parser = argparse.ArgumentParser(
        description="Analyze geometry JSONL datasets and validate aux constructions."
    )
    parser.add_argument("input_file", help="Path to JSONL dataset file")
    parser.add_argument(
        "--seed", type=int, default=123, help="Random seed (default: 123)"
    )
    parser.add_argument(
        "--max-level",
        type=positive_int,
        default=500,
        help="CSolver max level (default: 500)",
    )
    parser.add_argument(
        "--sample-rate",
        type=non_negative_rate,
        default=0.01,
        help="Fraction of aux records to validate (default: 0.01)",
    )
    parser.add_argument(
        "--cap",
        type=positive_int,
        default=10_000,
        help="Max validation samples (default: 10000)",
    )
    parser.add_argument(
        "--num-workers",
        type=positive_int,
        default=10,
        help="Number of Ray workers for validation (default: 10)",
    )
    parser.add_argument(
        "--skip-validation", action="store_true", help="Skip aux validation, stats only"
    )
    args = parser.parse_args()
    return AnalyzeConfig(
        input_file=args.input_file,
        seed=args.seed,
        max_level=args.max_level,
        sample_rate=args.sample_rate,
        cap=args.cap,
        num_workers=args.num_workers,
        skip_validation=args.skip_validation,
    )


def main() -> None:
    config = parse_args()
    stats, sample = collect_stats_and_sample(config)
    generate_stats_report(stats)

    if config.skip_validation or config.sample_rate == 0:
        print("\n" + "=" * 80)
        print("Analysis complete!")
        print("=" * 80)
        return

    if not sample:
        print("\nNo aux candidates found for validation.")
        print("\n" + "=" * 80)
        print("Analysis complete!")
        print("=" * 80)
        return

    print(
        f"\nAux validation: {len(sample):,} samples selected from "
        f"{stats.eligible_aux_count:,} validation-eligible aux candidates "
        f"({stats.aux_count:,} total aux samples)"
    )
    results = validate_samples(sample, config)
    generate_validation_report(results, stats.aux_count)

    print("\n" + "=" * 80)
    print("Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
