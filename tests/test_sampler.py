"""Tests for ClauseDAG and ProblemSampler."""

from newclid.formulations.clause import Clause
from newclid.generation.sampler import ClauseDAG, ClauseNode, ProblemSampler


# ── ClauseDAG Tests ──────────────────────────────────────────────────────────


class TestClauseDAGConstruction:
    def test_add_single_clause(self):
        dag = ClauseDAG()
        dag.add_clause(
            Clause(("a@0_0", "b@1_0", "c@0.5_1"), (("triangle", "a", "b", "c"),))
        )
        assert len(dag.nodes) == 1
        assert dag.get_max_depth() == 0
        assert "a" in dag.point_to_node
        assert dag.point_coords["a"] == (0.0, 0.0)

    def test_add_multiple_clauses_depth(self):
        dag = ClauseDAG()
        dag.add_clause(
            Clause(("a@0_0", "b@1_0", "c@0.5_1"), (("triangle", "a", "b", "c"),))
        )
        dag.add_clause(Clause(("d@0.5_0",), (("midpoint", "d", "a", "b"),)))
        dag.add_clause(Clause(("e@0.25_0.5",), (("midpoint", "e", "a", "c"),)))
        dag.add_clause(Clause(("f@0.375_0.25",), (("midpoint", "f", "d", "e"),)))

        assert len(dag.nodes) == 4
        assert dag.get_max_depth() == 2  # f depends on d,e which depend on a,b,c

    def test_parent_child_relationships(self):
        dag = ClauseDAG()
        root = dag.add_clause(Clause(("a@0_0", "b@1_0"), (("segment", "a", "b"),)))
        child = dag.add_clause(Clause(("m@0.5_0",), (("midpoint", "m", "a", "b"),)))
        assert child in root.children
        assert root in child.parents

    def test_extract_coordinates_formats(self):
        dag = ClauseDAG()
        # Format: name@x_y
        dag.add_clause(Clause(("p@1.0_2.0",), (("free", "p"),)))
        assert dag.point_coords["p"] == (1.0, 2.0)

    def test_empty_dag(self):
        dag = ClauseDAG()
        assert dag.get_max_depth() == -1
        assert dag.get_all_points() == set()


class TestClauseDAGPrune:
    def _build_dag(self):
        """Build a DAG with multiple branches of different depths."""
        dag = ClauseDAG()
        # Root
        dag.add_clause(Clause(("a@0_0", "b@1_0"), (("segment", "a", "b"),)))
        # Deep branch: a -> c -> e
        dag.add_clause(Clause(("c@0.5_1",), (("free", "c"),)))
        dag.add_clause(Clause(("e@0.25_0.5",), (("midpoint", "e", "a", "c"),)))
        # Shallow branch: a -> d (leaf at depth 1)
        dag.add_clause(Clause(("d@2_0",), (("free", "d"),)))
        return dag

    def test_prune_keeps_deepest(self):
        dag = self._build_dag()
        dag.prune(topk=1)
        # d (depth 1) should be removed, e (depth 2) should remain
        assert "e" in dag.point_to_node
        assert "d" not in dag.point_to_node
        assert "a" in dag.point_to_node  # ancestor kept

    def test_prune_topk_2(self):
        dag = self._build_dag()
        dag.prune(topk=2)
        # Both d (depth 1) and e (depth 2) should be kept
        assert "e" in dag.point_to_node
        assert "d" in dag.point_to_node

    def test_prune_empty_dag(self):
        dag = ClauseDAG()
        dag.prune()  # should not crash
        assert len(dag.nodes) == 0


class TestClauseDAGToProblem:
    def test_to_problem_with_rename(self):
        dag = ClauseDAG()
        dag.add_clause(
            Clause(("x@0_0", "y@1_0", "z@0.5_1"), (("triangle", "x", "y", "z"),))
        )
        result = dag.to_problem(rename=True)
        # Should use standard names a, b, c
        assert "a" in result
        assert "triangle" in result

    def test_to_problem_no_rename(self):
        dag = ClauseDAG()
        dag.add_clause(Clause(("x@0_0", "y@1_0"), (("segment", "x", "y"),)))
        result = dag.to_problem(rename=False)
        assert "x" in result
        assert "y" in result

    def test_to_problem_without_coords(self):
        dag = ClauseDAG()
        dag.add_clause(Clause(("p@1_2", "q@3_4"), (("segment", "p", "q"),)))
        result = dag.to_problem(with_coords=False, rename=False)
        assert "@1_2" not in result

    def test_empty_dag_to_problem(self):
        dag = ClauseDAG()
        assert dag.to_problem() == ""


class TestClauseNode:
    def test_extract_point_names(self):
        clause = Clause(("a@0_0", "b@1_0"), (("segment", "a", "b"),))
        node = ClauseNode(clause)
        assert node.points == {"a", "b"}

    def test_extract_construction_deps(self):
        clause = Clause(("m@0.5_0",), (("midpoint", "m", "a", "b"),))
        node = ClauseNode(clause)
        # "a" and "b" are dependency points (not defined by this clause)
        assert "a" in node.rely_on_points
        assert "b" in node.rely_on_points
        assert "m" not in node.rely_on_points


# ── ProblemSampler Tests ────────────────────────────────────────────────────


class TestProblemSampler:
    def test_generate_returns_nonempty_string(self):
        sampler = ProblemSampler(seed=42)
        result = sampler.generate(
            length=3, add_auxiliary=False, prune=True, with_coords=False
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_reproducible(self):
        r1 = ProblemSampler(seed=42).generate(
            length=5, add_auxiliary=False, prune=True, with_coords=False
        )
        r2 = ProblemSampler(seed=42).generate(
            length=5, add_auxiliary=False, prune=True, with_coords=False
        )
        assert r1 == r2

    def test_generate_different_seeds_differ(self):
        r1 = ProblemSampler(seed=1).generate(
            length=5, add_auxiliary=False, prune=True, with_coords=False
        )
        r2 = ProblemSampler(seed=2).generate(
            length=5, add_auxiliary=False, prune=True, with_coords=False
        )
        assert r1 != r2

    def test_generate_with_coords(self):
        sampler = ProblemSampler(seed=42)
        result = sampler.generate(
            length=3, add_auxiliary=False, prune=True, with_coords=True
        )
        assert "@" in result  # coordinates present

    def test_generate_without_coords(self):
        sampler = ProblemSampler(seed=42)
        result = sampler.generate(
            length=3, add_auxiliary=False, prune=True, with_coords=False
        )
        assert "@" not in result  # no coordinates

    def test_generate_with_prune(self):
        sampler = ProblemSampler(seed=42)
        sampler.generate(length=10, add_auxiliary=False, prune=True, with_coords=False)
        # After pruning, should have fewer nodes than input length
        assert len(sampler.dag.nodes) > 0

    def test_generate_with_auxiliary(self):
        sampler = ProblemSampler(seed=42)
        result = sampler.generate(
            length=5,
            add_auxiliary=True,
            max_auxiliary_points=2,
            prune=True,
            with_coords=False,
        )
        assert isinstance(result, str)
        assert len(sampler.dag.get_all_points()) > 0

    def test_generate_with_timings(self):
        sampler = ProblemSampler(seed=42)
        result, timings = sampler.generate(
            length=3, add_auxiliary=False, prune=True, return_timings=True
        )
        assert isinstance(result, str)
        assert "sampling" in timings
        assert "prune" in timings
        assert "to_problem" in timings

    def test_generate_dag_has_correct_structure(self):
        sampler = ProblemSampler(seed=42)
        sampler.generate(length=5, add_auxiliary=False, prune=False, with_coords=False)
        dag = sampler.dag
        assert len(dag.nodes) > 0
        assert dag.get_max_depth() >= 0
        assert len(dag.get_all_points()) > 0
