from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import os
import re
import string
import time
from typing import TYPE_CHECKING, Any

import numpy as np
import ray

from newclid.DDAR.build import DDAR
from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.configs import load_default_ddar_runtime_config
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.formulations.clause import translate_sentence
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
from newclid.ddar_build_input import build_ddar_input
from newclid.numerical.geometries import PointNum
from newclid.predicates.collinearity import Coll
from newclid.predicates.congruence import Cong
from newclid.predicates.cyclic import Cyclic
from newclid.predicates.equal_angles import EqAngle
from newclid.predicates.equal_ratios import EqRatio
from newclid.predicates.midpoint import MidPoint
from newclid.predicates.parallelism import Para
from newclid.predicates.perpendicularity import Perp
from newclid.proof import ProofState
from newclid.statement import Statement

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


def classify_build_exception(exc: Exception) -> str:
    message = str(exc)
    if "InvalidIntersectError" in message:
        return "build_numerical_error"
    if "InvalidReduceError" in message:
        return "build_reduce_error"
    if "PointTooCloseError" in message:
        return "build_point_too_close"
    if "PointTooFarError" in message:
        return "build_point_too_far"
    if "ConstructionError" in message:
        return "build_requirement_error"
    if "ValueError" in message:
        return "build_definition_error"
    return "build_definition_error"


def get_new_point_name(problem: ProblemJGEX) -> str:
    num_points = sum(len(clause.points) for clause in problem.constructions)
    letter_part = string.ascii_lowercase[num_points % 26]
    number_part = num_points // 26
    return f"{letter_part}{number_part - 1}" if number_part else letter_part


def try_dsl_to_constructions(content: str) -> str | None:
    """
    Translate generated aux DSL into internal construction syntax.
    Supports multiple auxiliary points separated by semicolons.

    Args:
        content: DSL string, e.g., "e : coll a b e [002] ; f : perp e f a b [003]"

    Returns:
        Construction string, e.g., "e = on_line e a b; f = on_tline f e a b"
        or None if parsing fails
    """
    if not content:
        return None

    content = content.strip()
    if not content:
        return None

    # Split by semicolon to get individual auxiliary points
    segments = [s.strip() for s in content.split(";") if s.strip()]

    if not segments:
        return None

    # Process each segment
    all_constructions = []
    for segment in segments:
        construction = _try_single_dsl_to_construction(segment)
        if construction is None:
            return None
        all_constructions.append(construction)

    # Join all constructions with semicolon
    return "; ".join(all_constructions)


def _try_single_dsl_to_construction(segment: str) -> str | None:
    """
    Process a single auxiliary point segment.

    Args:
        segment: Single segment like "e : coll a b e [002]" or "x00 e : coll a b e [002]"
                 Note: In actual data, each segment has x00 prefix

    Returns:
        Construction string like "e = on_line e a b" or None if invalid
    """
    # Remove x00 prefix if present (each segment in actual data has this)
    # Pattern matches "x" followed by digits and whitespace
    segment = re.sub(r"^x\d+\s+", "", segment).strip()

    try:
        points, premises = segment.split(" : ", 1)
    except ValueError:
        return None

    point_names = points.strip().split()
    if len(point_names) != 1:
        return None
    point = point_names[0]

    premise_segments = re.split(r"\s*\[\d+\]", premises)
    premise_segments = [seg.strip() for seg in premise_segments if seg.strip()]
    if len(premise_segments) > 2:
        return None
    if not premise_segments:
        return f"{point} = free {point}"

    constructions: list[str] = []
    for premise in premise_segments:
        parts = premise.split()
        if not parts or not parts[0].isalpha():
            return None
        constructions.append(translate_dsl_to_construction(point, parts[0], parts[1:]))
    return f"{point} = {', '.join(constructions)}"


def translate_dsl_to_construction(point: str, predicate: str, args: list[str]) -> str:
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
        return EqAngle.to_constructive(
            point,
            arrange_angle_points(a, b, c, d) + arrange_angle_points(e, f, g, h),
        )
    return f"{predicate} {' '.join(args)}"


def _problem_to_dsl(
    problem: ProblemJGEX, defs: dict[str, DefinitionJGEX], *, include_empty_basics: bool
) -> str:
    dep_idx: dict[Statement, str] = {}
    dep_graph = DependencyGraph(AlgebraicManipulator())
    grouped_statements: dict[str, list[Statement]] = defaultdict(list)

    for construction in problem.constructions:
        point_groups: dict[str, tuple[str, ...]] = {}
        for constr_sentence in construction.sentences:
            cdef = defs[constr_sentence[0]]
            if len(constr_sentence) == len(cdef.declare):
                mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
            else:
                points = tuple(point.split("@")[0] for point in construction.points)
                mapping = dict(zip(cdef.declare[1:], points + constr_sentence[1:]))
            for points, basics in cdef.basics:
                resolved_points = tuple(mapping[name] for name in points)
                for resolved_point in resolved_points:
                    point_groups[resolved_point] = resolved_points
                if include_empty_basics and not basics:
                    grouped_statements[" ".join(resolved_points)] = []
                for basic in basics:
                    statement = Statement.from_tokens(
                        translate_sentence(mapping, basic), dep_graph
                    )
                    grouped_statements[" ".join(resolved_points)].append(statement)

        if not include_empty_basics:
            remaining_points = [point.split("@")[0] for point in construction.points]
            while remaining_points:
                point = remaining_points[0]
                group = point_groups[point]
                remaining_points = [
                    candidate
                    for candidate in remaining_points
                    if candidate not in group
                ]
                grouped_statements.setdefault(
                    " ".join(group), grouped_statements.get(" ".join(group), [])
                )

    problem_parts: list[str] = []
    for key, statements in grouped_statements.items():
        rendered = key + " : "
        for statement in statements:
            if statement not in dep_idx:
                dep_idx[statement] = f"{len(dep_idx):03d}"
            rendered += statement.to_str() + f" [{dep_idx[statement]}] "
        problem_parts.append(rendered.strip())

    goals = [Statement.from_tokens(goal, dep_graph).to_str() for goal in problem.goals]
    return (
        "<problem> "
        + " ; ".join(problem_parts)
        + " ? "
        + " ; ".join(goals)
        + " </problem>"
    )


def problem_to_text_dsl(problem: ProblemJGEX, defs: dict[str, DefinitionJGEX]) -> str:
    return _problem_to_dsl(problem, defs, include_empty_basics=False)


def problem_to_visual_dsl(problem: ProblemJGEX, defs: dict[str, DefinitionJGEX]) -> str:
    return _problem_to_dsl(problem, defs, include_empty_basics=True)


def extract_points(proof: ProofState) -> list[tuple[str, Any, Any]]:
    points: list[tuple[str, Any, Any]] = []
    for name, point in proof.symbols_graph.name2node.items():
        if isinstance(point.num, PointNum):
            points.append((name, point.num.x, point.num.y))
    return points


def extract_premises(proof: ProofState) -> list[tuple[str, list[str]]]:
    premises: list[tuple[str, list[str]]] = []
    for stmt in proof.dep_graph.hyper_graph:
        predicate = stmt.predicate.NAME
        args: list[str] = []
        for point in stmt.args:
            args.append(str(point) if isinstance(point, Fraction) else point.name)
        premises.append((predicate, args))
    return premises


def extract_goals(proof: ProofState) -> list[tuple[str, list[str]]]:
    goals: list[tuple[str, list[str]]] = []
    for stmt in proof.goals:
        predicate = stmt.predicate.NAME
        args: list[str] = []
        for point in stmt.args:
            args.append(str(point) if isinstance(point, Fraction) else point.name)
        goals.append((predicate, args))
    return goals


def run_ddar_on_proof(proof: ProofState) -> bool:
    ddar_config = load_default_ddar_runtime_config()
    solved, _ = DDAR.run_ddar(
        "",
        extract_points(proof),
        extract_premises(proof),
        extract_goals(proof),
        500,
        ddar_config,
    )
    return solved


class BeamQueue:
    """Keep only the top-k nodes according to their scores."""

    def __init__(self, max_size: int = 512):
        self.queue: list[tuple[float, tuple[int, ...], int, Any]] = []
        self.max_size = max_size
        self.counter = 0

    @staticmethod
    def _sort_key(
        entry: tuple[float, tuple[int, ...], int, Any],
    ) -> tuple[float, tuple[int, ...], int]:
        score, stable_key, insertion_order, _ = entry
        return (-score, stable_key, insertion_order)

    def _sorted_entries(self) -> list[tuple[float, tuple[int, ...], int, Any]]:
        return sorted(self.queue, key=self._sort_key)

    def add(self, node: object, val: float, *, stable_key: tuple[int, ...]) -> None:
        self.queue.append((val, stable_key, self.counter, node))
        self.counter += 1
        if len(self.queue) > self.max_size:
            self.queue = self._sorted_entries()[: self.max_size]

    def __iter__(self):
        for val, _, _, node in self._sorted_entries():
            yield val, node

    def iter_entries(self):
        yield from self._sorted_entries()

    def __len__(self) -> int:
        return len(self.queue)

    def map_nodes(self, func) -> None:
        self.queue = [
            (val, stable_key, insertion_order, func(node))
            for val, stable_key, insertion_order, node in self.queue
        ]


def run_ddar_c(
    proof: ProofState, rules: list["Rule"], start_time: float, timeout: int = 3600
) -> bool:
    del rules, start_time, timeout
    return run_ddar_on_proof(proof)


def build_problem_proof(problem, defs, *, max_attempts: int = 100) -> ProofState:
    return ProofState.build_problemJGEX(
        problemJGEX=problem,
        defsJGEX=defs,
        rng=np.random.default_rng(998244353),
        max_attempts=max_attempts,
        problem_path=None,
    )


@ray.remote(num_cpus=1)
def run_ddar_remote(
    problem,
    defs,
    rules: list["Rule"],
    start_time: float,
    timeout: int = 3600,
    *,
    return_proof: bool = False,
):
    # These timings describe work performed inside one remote DDAR task. They
    # are not main-thread wall-clock timings and can legitimately sum to more
    # than the end-to-end runtime when many DDAR tasks run in parallel.
    eval_start = time.time()
    ddar_worker_id = f"{ray.util.get_node_ip_address()}:{os.getpid()}"
    ddar_started_at_unix_s = eval_start
    ddar_build_work_time_s = 0.0
    try:
        build_start = time.time()
        points, premises, goals = build_ddar_input(
            problem,
            defs,
            np.random.default_rng(998244353),
            max_attempts=100,
            only_useful_points=False,
        )
        ddar_build_finished_at_unix_s = time.time()
        ddar_build_work_time_s = ddar_build_finished_at_unix_s - build_start
    except Exception as exc:
        ddar_finished_at_unix_s = time.time()
        result = {
            "status": "invalid",
            "elapsed_time": ddar_finished_at_unix_s - eval_start,
            "ddar_worker_id": ddar_worker_id,
            "ddar_started_at_unix_s": ddar_started_at_unix_s,
            "ddar_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_build_started_at_unix_s": build_start,
            "ddar_build_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_engine_started_at_unix_s": None,
            "ddar_engine_finished_at_unix_s": None,
            "ddar_build_work_time_s": ddar_finished_at_unix_s - build_start,
            "ddar_engine_work_time_s": 0.0,
            "error_type": classify_build_exception(exc),
            "error_message": str(exc),
        }
        if return_proof:
            result["proof"] = None
        return result

    try:
        ddar_start = time.time()
        del rules, start_time, timeout
        ddar_config = load_default_ddar_runtime_config()
        solved, _ = DDAR.run_ddar("", points, premises, goals, 500, ddar_config)
        ddar_engine_finished_at_unix_s = time.time()
        ddar_engine_work_time_s = ddar_engine_finished_at_unix_s - ddar_start
    except Exception as exc:
        ddar_finished_at_unix_s = time.time()
        result = {
            "status": "invalid",
            "elapsed_time": ddar_finished_at_unix_s - eval_start,
            "ddar_worker_id": ddar_worker_id,
            "ddar_started_at_unix_s": ddar_started_at_unix_s,
            "ddar_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_build_started_at_unix_s": build_start,
            "ddar_build_finished_at_unix_s": ddar_build_finished_at_unix_s,
            "ddar_engine_started_at_unix_s": ddar_start,
            "ddar_engine_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_build_work_time_s": ddar_build_work_time_s,
            "ddar_engine_work_time_s": ddar_finished_at_unix_s - ddar_start,
            "error_type": "engine_error",
            "error_message": str(exc),
        }
        if return_proof:
            result["proof"] = None
        return result

    ddar_finished_at_unix_s = time.time()
    result = {
        "status": "solved" if solved else "unsolved",
        "elapsed_time": ddar_finished_at_unix_s - eval_start,
        "ddar_worker_id": ddar_worker_id,
        "ddar_started_at_unix_s": ddar_started_at_unix_s,
        "ddar_finished_at_unix_s": ddar_finished_at_unix_s,
        "ddar_build_started_at_unix_s": build_start,
        "ddar_build_finished_at_unix_s": ddar_build_finished_at_unix_s,
        "ddar_engine_started_at_unix_s": ddar_start,
        "ddar_engine_finished_at_unix_s": ddar_engine_finished_at_unix_s,
        "ddar_build_work_time_s": ddar_build_work_time_s,
        "ddar_engine_work_time_s": ddar_engine_work_time_s,
    }
    if return_proof:
        result["proof"] = build_problem_proof(problem, defs)
    return result
