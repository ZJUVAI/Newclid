#!/usr/bin/env python3
"""
Test script for CSolver custom rule support.
"""

import sys
sys.path.insert(0, '/root/GenesisGeo/src')

from newclid.DDAR.build import DDAR

def test_run_ddar_with_rules_basic():
    """Test that run_ddar_with_rules function exists and can be called."""
    # Simple triangle problem
    points = [
        ("a", 0.0, 0.0),
        ("b", 1.0, 0.0),
        ("c", 0.5, 0.866),
        ("d", 0.5, 0.0),  # midpoint of a, b
    ]

    premises = [
        ("midp", ["d", "a", "b"]),  # d is midpoint of a, b
    ]

    goals = [
        ("coll", ["a", "d", "b"]),  # a, d, b are collinear
    ]

    # Test without custom rules
    solved, dep_graph = DDAR.run_ddar(
        "test_problem", points, premises, goals, 100, True, True
    )
    print(f"Without custom rules: solved={solved}")

    # Test with empty custom rules
    solved2, dep_graph2 = DDAR.run_ddar_with_rules(
        "test_problem", points, premises, goals, [], 100, True, True
    )
    print(f"With empty custom rules: solved={solved2}")

    # Test with a simple custom rule (should not affect this problem)
    custom_rules = [
        "cong a b c d, para a b c d => cyclic a b c d"
    ]
    solved3, dep_graph3 = DDAR.run_ddar_with_rules(
        "test_problem", points, premises, goals, custom_rules, 100, True, True
    )
    print(f"With custom rule: solved={solved3}")

    return solved and solved2 and solved3


def test_custom_rule_matching():
    """Test that custom rules are actually matched and applied."""
    # Create a problem where a custom rule would help
    # Square with vertices a, b, c, d
    points = [
        ("a", 0.0, 0.0),
        ("b", 1.0, 0.0),
        ("c", 1.0, 1.0),
        ("d", 0.0, 1.0),
    ]

    # Premises: ab parallel to cd, ad parallel to bc
    premises = [
        ("para", ["a", "b", "c", "d"]),
        ("para", ["a", "d", "b", "c"]),
        ("cong", ["a", "b", "c", "d"]),
        ("cong", ["a", "d", "b", "c"]),
    ]

    # Goal: prove ab is congruent to cd (should be trivially true from premises)
    goals = [
        ("cong", ["a", "b", "c", "d"]),
    ]

    # Test with custom rules
    custom_rules = [
        "para a b c d => para c d a b",  # symmetry rule
    ]

    solved, dep_graph = DDAR.run_ddar_with_rules(
        "square_test", points, premises, goals, custom_rules, 100, True, True
    )
    print(f"Square test with custom rules: solved={solved}")

    return solved


def test_csolver_api():
    """Test CSolver Python API with custom rules using direct point/premise/goal input."""
    from newclid.api import CSolver, GeometricSolverBuilder

    # Use a simple problem with coordinates
    problem_txt = "orthocenter\na b c = triangle; h = on_tline h b a c, on_tline h c a b ? perp a h b c"

    # Build solver first to get coordinates
    builder = GeometricSolverBuilder(seed=123)
    builder.load_problem_from_txt(problem_txt)
    solver = builder.build()

    # Extract points, premises, goals from the solver
    points = []
    premises = []
    goals = []

    # Get points with coordinates
    from newclid.numerical.geometries import PointNum
    from fractions import Fraction

    useful_points = []
    for stmt in solver.proof.dep_graph.hyper_graph:
        predicate = stmt.predicate.NAME
        args = []
        for pt in stmt.args:
            if isinstance(pt, Fraction):
                args.append(str(pt))
            else:
                args.append(pt.name)
                if pt.name not in useful_points:
                    useful_points.append(pt.name)
        premises.append((predicate, args))

    for stmt in solver.proof.goals:
        predicate = stmt.predicate.NAME
        args = []
        for pt in stmt.args:
            if isinstance(pt, Fraction):
                args.append(str(pt))
            else:
                args.append(pt.name)
                if pt.name not in useful_points:
                    useful_points.append(pt.name)
        goals.append((predicate, args))

    for name, point in solver.proof.symbols_graph.name2node.items():
        if isinstance(point.num, PointNum) and name in useful_points:
            points.append((name, point.num.x, point.num.y))

    print(f"Points: {len(points)}, Premises: {len(premises)}, Goals: {len(goals)}")

    # Test CSolver with direct input (no custom rules)
    csolver1 = CSolver(
        problem=None,
        problem_name="test1",
        solver=solver,
        using_log=True,
        using_exp=True,
        points=points,
        premises=premises,
        goals=goals
    )
    result1 = csolver1.run(max_level=100)
    print(f"CSolver without custom rules: solved={result1}")

    # Test CSolver with custom rules
    custom_rules = ["perp a b c d => perp c d a b"]  # perpendicular symmetry
    csolver2 = CSolver(
        problem=None,
        problem_name="test2",
        solver=solver,
        using_log=True,
        using_exp=True,
        points=points,
        premises=premises,
        goals=goals,
        custom_rules=custom_rules
    )
    result2 = csolver2.run(max_level=100)
    print(f"CSolver with custom rules: solved={result2}")

    return result1 and result2


if __name__ == "__main__":
    print("=" * 60)
    print("Testing CSolver Custom Rule Support")
    print("=" * 60)

    print("\n1. Testing run_ddar_with_rules basic functionality...")
    try:
        test1_passed = test_run_ddar_with_rules_basic()
        print(f"   Result: {'PASSED' if test1_passed else 'FAILED'}")
    except Exception as e:
        print(f"   Result: FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        test1_passed = False

    print("\n2. Testing custom rule matching...")
    try:
        test2_passed = test_custom_rule_matching()
        print(f"   Result: {'PASSED' if test2_passed else 'FAILED'}")
    except Exception as e:
        print(f"   Result: FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        test2_passed = False

    print("\n3. Testing CSolver Python API...")
    try:
        test3_passed = test_csolver_api()
        print(f"   Result: {'PASSED' if test3_passed else 'FAILED'}")
    except Exception as e:
        print(f"   Result: FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        test3_passed = False

    print("\n" + "=" * 60)
    all_passed = test1_passed and test2_passed and test3_passed
    print(f"Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)
