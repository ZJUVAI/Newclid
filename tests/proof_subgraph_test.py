from typing import List
from networkx import MultiDiGraph
import pytest

from geosolver.dependencies.dependency_graph import extract_sub_graph


class TestProofSubgraph:
    @pytest.fixture(autouse=True)
    def setup(self):
        pass

    def test_empty(self):
        """should raise error when goal is None."""
        with pytest.raises(ValueError):
            extract_sub_graph(MultiDiGraph(), [], None)

    def test_path_to_goal(self):
        """should give whole graph if only one path to goal.

        p1 -r0> s1 -r1> g

        """

        dependency_graph = MultiDiGraph()
        goal = "g"
        dependency_graph.add_edge("p1", "s1", "r0")
        dependency_graph.add_edge("s1", goal, "r1")

        expected = dependency_graph.copy()

        actual = extract_sub_graph(dependency_graph, premises(dependency_graph), goal)
        assert set(actual.edges) == set(expected.edges)

    def test_equivalent_path_to_goal(self):
        r"""should give whole graph if only two equivalent path to goal.

            -r0-> s1 -r1->
          /               \
        p1                  g
          \               /
            -r2-> s2 -r3->

        """

        dependency_graph = MultiDiGraph()
        goal = "g"
        dependency_graph.add_edge("p1", "s1", "r0")
        dependency_graph.add_edge("s1", goal, "r1")
        dependency_graph.add_edge("p1", "s2", "r2")
        dependency_graph.add_edge("s2", goal, "r3")

        expected = dependency_graph.copy()

        actual = extract_sub_graph(dependency_graph, premises(dependency_graph), goal)
        assert set(actual.edges) == set(expected.edges)

    def test_drop_edges_going_away_from_goal(self):
        r"""should drop edges not going closer to the goal.

            -r0-> s1 -r1->
          /        ^      \
        p1        r3       g
          \        |      X
            -r2-> s2 <-r4-

        """

        dependency_graph = MultiDiGraph()
        goal = "g"
        dependency_graph.add_edge("p1", "s1", "r0")
        dependency_graph.add_edge("s1", goal, "r1")
        dependency_graph.add_edge("p1", "s2", "r2")
        dependency_graph.add_edge("s2", "s1", "r3")
        dependency_graph.add_edge(goal, "s2", "r4")

        expected = MultiDiGraph()
        expected.add_edge("p1", "s1", "r0")
        expected.add_edge("s1", goal, "r1")
        expected.add_edge("p1", "s2", "r2")
        expected.add_edge("s2", "s1", "r3")

        actual = extract_sub_graph(dependency_graph, premises(dependency_graph), goal)
        assert set(actual.edges) == set(expected.edges)

    def test_drop_cycles(self):
        r"""should remove cycles always even if same key.

            -r0->
          /       \
        p1         s1 -r1-> s2 -r2-> s3 -r3-> s4 -r4-> g
          \       X
            <-r0-

        """

        dependency_graph = MultiDiGraph()
        goal = "g"
        dependency_graph.add_edge("p1", "s1", "r0")
        for i in range(1, 3):
            dependency_graph.add_edge(f"s{i}", f"s{i+1}", f"r{i}")
        dependency_graph.add_edge(f"s{i+1}", goal, f"r{i+1}")
        dependency_graph.add_edge("s1", "p1", "r0")

        expected = MultiDiGraph()
        expected.add_edge("p1", "s1", "r0")
        for i in range(1, 3):
            expected.add_edge(f"s{i}", f"s{i+1}", f"r{i}")
        expected.add_edge(f"s{i+1}", goal, f"r{i+1}")

        actual = extract_sub_graph(dependency_graph, premises(dependency_graph), goal)
        assert set(actual.edges) == set(expected.edges)

    def test_drop_nodes_without_edges(self):
        r"""should drop nodes without edges.

            -r0-> s1 -r1->
          /        ^      \
        p1        r3       g
                   X      X
                  s2 <-r2-
        """

        dependency_graph = MultiDiGraph()
        goal = "g"
        dependency_graph.add_node("p1", level=0)
        dependency_graph.add_node("s1", level=1)
        dependency_graph.add_edge("p1", "s1", "r0")

        dependency_graph.add_node(goal, level=2)
        dependency_graph.add_edge("s1", goal, "r1")

        dependency_graph.add_node("s2", level=3)
        dependency_graph.add_edge(goal, "s2", "r2")
        dependency_graph.add_edge("s2", "s1", "r3")

        actual = extract_sub_graph(dependency_graph, premises(dependency_graph), goal)

        expected = MultiDiGraph()
        expected.add_edge("p1", "s1", "r0")
        expected.add_edge("s1", goal, "r1")
        assert set(actual.edges) == set(expected.edges)
        assert set(actual.nodes) == set(expected.nodes)

    def test_keep_edges_with_same_key_even_if_out_of_path(self):
        r"""should keep edges out of premises path if they share a key.

        p1 -r0-> s1 -r1->
                         \
                 s2 -r1-> g

        """

        dependency_graph = MultiDiGraph()
        goal = "g"
        dependency_graph.add_edge("p1", "s1", "r0")
        dependency_graph.add_edge("s1", goal, "r1")
        dependency_graph.add_edge("s2", goal, "r1")

        expected = MultiDiGraph()
        expected.add_edge("p1", "s1", "r0")
        expected.add_edge("s1", goal, "r1")
        expected.add_edge("s2", goal, "r1")

        actual = extract_sub_graph(dependency_graph, premises(dependency_graph), goal)
        assert set(actual.edges) == set(expected.edges)


def premises(graph: MultiDiGraph) -> List[str]:
    return [node for node in graph.nodes if node.startswith("p")]
