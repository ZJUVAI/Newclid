from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import re
import string
from typing import Any

from newclid.DDAR.build import DDAR
from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.formulations.clause import translate_sentence
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
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


def get_new_point_name(problem: ProblemJGEX) -> str:
    num_points = sum(len(clause.points) for clause in problem.constructions)
    letter_part = string.ascii_lowercase[num_points % 26]
    number_part = num_points // 26
    return f"{letter_part}{number_part - 1}" if number_part else letter_part


def try_dsl_to_constructions(content: str) -> str | None:
    points, premises = content.split(";")[0].split(" : ")
    point_names = points.strip().split()
    if len(point_names) != 1:
        return None
    point = point_names[0]

    premise_segments = re.split(r"\s*\[\d+\]", premises)
    premise_segments = [segment.strip() for segment in premise_segments if segment.strip()]
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
        def arrange_angle_points(a: str, b: str, c: str, d: str) -> tuple[str, str, str] | None:
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


def _problem_to_dsl(problem: ProblemJGEX, defs: dict[str, DefinitionJGEX], *, include_empty_basics: bool) -> str:
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
                for point in resolved_points:
                    point_groups[point] = resolved_points
                if include_empty_basics and not basics:
                    grouped_statements[" ".join(resolved_points)] = []
                for basic in basics:
                    statement = Statement.from_tokens(translate_sentence(mapping, basic), dep_graph)
                    grouped_statements[" ".join(resolved_points)].append(statement)

        if not include_empty_basics:
            remaining_points = [point.split("@")[0] for point in construction.points]
            while remaining_points:
                point = remaining_points[0]
                group = point_groups[point]
                remaining_points = [candidate for candidate in remaining_points if candidate not in group]
                grouped_statements.setdefault(" ".join(group), grouped_statements.get(" ".join(group), []))

    problem_parts: list[str] = []
    for key, statements in grouped_statements.items():
        rendered = key + " : "
        for statement in statements:
            if statement not in dep_idx:
                dep_idx[statement] = f"{len(dep_idx):03d}"
            rendered += statement.to_str() + f" [{dep_idx[statement]}] "
        problem_parts.append(rendered.strip())

    goals = [
        Statement.from_tokens(goal, dep_graph).to_str()
        for goal in problem.goals
    ]
    return "<problem> " + " ; ".join(problem_parts) + " ? " + " ; ".join(goals) + " </problem>"


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
    solved, _ = DDAR.run_ddar(
        "",
        extract_points(proof),
        extract_premises(proof),
        extract_goals(proof),
        500,
        True,
        True,
    )
    return solved
