import pytest
from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.dependency.dependency import Dependency
from geosolver.dependency.dependency_graph import DependencyGraph
from geosolver.predicates.equal_angles import EqAngle
from geosolver.reasoning_engines.algebraic_reasoning.algebraic_manipulator import (
    AlgebraicManipulator,
)
from geosolver.api import GeometricSolverBuilder
from geosolver.statement import Statement
from tests.fixtures import build_until_works


def test_ar_module():
    ar = AlgebraicManipulator()
    dep_graph = DependencyGraph(ar)
    deps = [
        Dependency(
            Statement(
                EqAngle,
                ("x", "b", "b", "c", "x", "p", "p", "c", "x", "a", "a", "c"),
                dep_graph,
            )
        ),
        Dependency(
            Statement(
                EqAngle,
                ("x", "c", "c", "b", "x", "p", "p", "b", "x", "a", "a", "b"),
                dep_graph,
            )
        ),
        Dependency(
            Statement(
                EqAngle, ("c", "p", "p", "p_b", "p", "p_b", "p_b", "c"), dep_graph
            )
        ),
        Dependency(
            Statement(
                EqAngle, ("a", "p", "p", "p_b", "p", "p_b", "p_b", "a"), dep_graph
            )
        ),
        Dependency(
            Statement(
                EqAngle, ("b", "q_a", "q_a", "q", "q_a", "q", "q", "b"), dep_graph
            )
        ),
        Dependency(
            Statement(
                EqAngle, ("b", "q_c", "q_c", "q", "q_c", "q", "q", "b"), dep_graph
            )
        ),
        Dependency(
            Statement(EqAngle, ("p_a", "b", "b", "c", "c", "b", "b", "p"), dep_graph)
        ),
        Dependency(
            Statement(EqAngle, ("q_a", "b", "b", "c", "c", "b", "b", "q"), dep_graph)
        ),
        Dependency(
            Statement(EqAngle, ("q_c", "b", "b", "a", "a", "b", "b", "q"), dep_graph)
        ),
        Dependency(
            Statement(
                EqAngle, ("h", "p_b", "q", "q_a", "p_b", "c", "c", "a"), dep_graph
            )
        ),
        Dependency(
            Statement(
                EqAngle, ("h", "p_a", "q", "q_c", "p_a", "b", "b", "c"), dep_graph
            )
        ),
    ]
    for dep in deps:
        ar.ingest(dep)
    goal = Statement(EqAngle, ("c", "p", "h", "p_a", "a", "p", "h", "p_b"), dep_graph)
    assert not ar.check(goal.predicate, goal.args)


def test_ar_world_hardest_problem_vertex():
    solver = build_until_works(
        GeometricSolverBuilder()
        .load_problem_from_txt(
            "a b = segment a b; "
            "o = s_angle b a o 70o, s_angle a b o 120o; "
            "c = s_angle o a c 10o, s_angle o b c 160o; "
            "d = on_line d o b, on_line d c a; "
            "e = on_line e o a, on_line e c b; "
            "f = on_pline f d a b, on_line f b c; "
            "g = on_line g f a, on_line g d b "
            "? aconst c a c b 1pi/9"
        )
        .with_deductive_agent(BFSDDAR)
    )

    success = solver.run()
    assert success


@pytest.mark.xfail
def test_ar_ratio_hallucination():
    solver = build_until_works(
        GeometricSolverBuilder()
        .load_problem_from_txt(
            "a b e = triangle12 a b e; c = midpoint c a e ? cong a c a b"
        )
        .with_deductive_agent(BFSDDAR)
    )

    success = solver.run()
    assert success
