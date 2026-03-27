from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Collection, Optional, Union
from adjustText import adjust_text
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from numpy.random import Generator

import numpy as np
import matplotlib.patches as patches

from newclid.numerical.geometries import (
    PointNum,
    intersect,
)
from newclid.dependencies.symbols import Point, Circle, Line
from newclid.formulations.clause import Clause, translate_sentence
from newclid.formulations.definition import DefinitionJGEX
from newclid.numerical.draw_figure import draw_point, draw_segment, draw_circle_num
from newclid.numerical.geometries import CircleNum
from newclid.statement import Statement

if TYPE_CHECKING:
    from newclid.dependencies.dependency_graph import DependencyGraph
    from newclid.proof import ProofState
    from newclid.formulations.problem import ProblemJGEX

def draw_clause_figure(
    proof: "ProofState",
    problem: "ProblemJGEX",
    save_to: Optional[Union[str, Path]],
    rng: Generator,
    draw_annotations: bool = True,
):
    """Draw clauses figure."""
    fig = deepcopy(proof.fig)
    draw_clauses(
        fig.axes[0],
        list(problem.constructions),
        proof.defs,
        Statement.from_tokens(problem.goals[0], proof.dep_graph),
        rng,
        proof.dep_graph,
        draw_annotations=draw_annotations,
    )
    if save_to is not None:
        save_path = Path(save_to)
        if save_path.suffix.lower() == ".svg":
            fig.savefig(save_to, format="svg")
        elif save_path.suffix.lower() == ".png":
            fig.savefig(save_to, format="png")
        else:
            fig.savefig(save_to)

def draw_clauses(
    ax: "Axes",
    clauses: list[Clause],
    defs: dict[str, DefinitionJGEX],
    goal: "Statement",
    rng: Generator,
    dep_graph: "DependencyGraph",
    mapping: dict[str, str] = None,
    draw_annotations: bool = True,
):
    """Draw clauses."""
    point_names = []
    segment_parent: dict[tuple[str, str], tuple[str, str]] = {}
    segment_colors: dict[tuple[str, str], int] = {}
    figure_sizes: list = []
    for clause in clauses:
        clause_wo_coords = Clause(
            points=tuple([p.split('@')[0] for p in clause.points]),
            sentences=clause.sentences,
        )
        _draw_clause(
            clause_wo_coords, ax, defs, rng, dep_graph, draw_annotations, segment_parent, segment_colors, figure_sizes
        )
        points = dep_graph.symbols_graph.names2points(clause_wo_coords.points)
        for p in points:
            if mapping is None:
                point_names.append(draw_point(ax, p))
            else:
                mapped_p = Point(name=mapping[p.name], symbols_graph=None, dep=None)
                mapped_p.num = p.num
                point_names.append(draw_point(ax, mapped_p))

    goal.draw(ax, rng, draw_annotations=False)

    adjust_text(point_names, ax=ax)


def _draw_clause(
    clause: Clause,
    ax: "Axes",
    defs: dict[str, DefinitionJGEX],
    rng: Generator,
    dep_graph: "DependencyGraph",
    draw_annotations: bool = True,
    segment_parent: dict[tuple[str, str], tuple[str, str]] = None,
    segment_colors: dict[tuple[str, str], int] = None,
    figure_sizes: list = [],
):
    for constr_sentence in clause.sentences:
        cdef = defs[constr_sentence[0]]
        if len(constr_sentence) == len(cdef.declare):
            mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
            args = [
                dep_graph.symbols_graph.name2node.get(name, name)
                for name in constr_sentence[1:]
            ]
        else:
            assert len(constr_sentence) + \
                len(clause.points) == len(cdef.declare)
            mapping = dict(
                zip(cdef.declare[1:], clause.points + constr_sentence[1:]))
            args = [
                dep_graph.symbols_graph.name2node.get(name, name)
                for name in clause.points + constr_sentence[1:]
            ]
        for _, bs in cdef.basics:
            for b in bs:
                statement = Statement.from_tokens(
                    translate_sentence(mapping, b), dep_graph)
                if statement.predicate.NAME == 'cong':
                    statement.predicate.draw(
                        ax,
                        statement.args,
                        dep_graph,
                        rng,
                        segment_parent,
                        segment_colors,
                        figure_sizes,
                        draw_annotations,
                    )
                else:
                    statement.draw(ax, rng, draw_annotations)
        
        if constr_sentence[0] == 'segment':
            draw_segment(ax, args[0], args[1])
        if 'triangle' in constr_sentence[0] or \
            'risos' in constr_sentence[0]:
            for i in range(3):
                draw_segment(ax, args[i], args[(i+1)%3])
        if constr_sentence[0] == 'orthocenter':
            for i in range(3):
                draw_segment(ax, args[i+1], args[(i+1)%3+1])
        if 'trapezoid' in constr_sentence[0] or \
            'sqaure' in constr_sentence[0] or \
            'rectangle' in constr_sentence[0] or \
            'parallelogram' in constr_sentence[0] or \
            'quadrangle' in constr_sentence[0]:
            for i in range(4):
                draw_segment(ax, args[i], args[(i+1)%4])
        if 'pentagon' in constr_sentence[0]:
            for i in range(5):
                draw_segment(ax, args[i], args[(i+1)%5])
        if constr_sentence[0] == 'circle':
            c_num = CircleNum(
                p1=args[1].num,
                p2=args[2].num,
                p3=args[3].num,
            )
            draw_circle_num(ax, c_num)
        if constr_sentence[0] == 'on_circle':
            c_num = CircleNum(
                center=args[1].num,
                p1=args[2].num,
            )
            draw_circle_num(ax, c_num)
        if constr_sentence[0] == 'tangent':
            c_num = CircleNum(
                center=args[-2].num,
                p1=args[-1].num,
            )
            draw_circle_num(ax, c_num)
        if constr_sentence[0] == 'cc_tangent':
            c_num1 = CircleNum(
                center=args[-4].num,
                p1=args[-3].num,
            )
            c_num2 = CircleNum(
                center=args[-2].num,
                p1=args[-1].num,
            )
            draw_circle_num(ax, c_num1)
            draw_circle_num(ax, c_num2)
        if constr_sentence[0] == 'lc_tangent':
            c_num = CircleNum(
                center=args[-1].num,
                p1=args[-2].num,
            )
            draw_circle_num(ax, c_num)
        if constr_sentence[0] == 'on_dia':
            c_num = CircleNum(
                p1=args[0].num,
                p2=args[1].num,
                p3=args[2].num,
            )
            draw_circle_num(ax, c_num)
            draw_segment(ax, args[1], args[2])
        if constr_sentence[0] == 'ninepoints':
            c_num = CircleNum(
                p1=args[0].num,
                p2=args[1].num,
                p3=args[2].num,
            )
            draw_circle_num(ax, c_num)
        if constr_sentence[0] == 'intersection_cc':
            c_num1 = CircleNum(
                center=args[1].num,
                p1=args[3].num,
            )
            c_num2 = CircleNum(
                center=args[2].num,
                p1=args[3].num,
            )
            draw_circle_num(ax, c_num1)
            draw_circle_num(ax, c_num2)
        if constr_sentence[0] == 'intersection_lc':
            c_num = CircleNum(
                center=args[-2].num,
                p1=args[-1].num,
            )
            draw_circle_num(ax, c_num)
