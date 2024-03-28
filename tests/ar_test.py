# Copyright 2023 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Unit tests for ar.py."""

import pytest
import pytest_check as check
import geosolver.algebraic.geometric_tables as geometric_tables
from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.proof import Proof
from geosolver.problem import Definition, Problem, Theorem


class TestAR:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.defs = Definition.from_txt_file("defs.txt", to_dict=True)
        self.rules = Theorem.from_txt_file("rules.txt", to_dict=True)

    def test_update_groups(self):
        """Test for update_groups."""
        groups1 = [{1, 2}, {3, 4, 5}, {6, 7}]
        groups2 = [{2, 3, 8}, {9, 10, 11}]

        _, links, history = geometric_tables.update_groups(groups1, groups2)
        check.equal(
            history,
            [
                [{1, 2, 3, 4, 5, 8}, {6, 7}],
                [{1, 2, 3, 4, 5, 8}, {6, 7}, {9, 10, 11}],
            ],
        )
        check.equal(links, [(2, 3), (3, 8), (9, 10), (10, 11)])

        groups1 = [{1, 2}, {3, 4}, {5, 6}, {7, 8}]
        groups2 = [{2, 3, 8, 9, 10}, {3, 6, 11}]

        _, links, history = geometric_tables.update_groups(groups1, groups2)
        check.equal(
            history,
            [
                [{1, 2, 3, 4, 7, 8, 9, 10}, {5, 6}],
                [{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}],
            ],
        )
        check.equal(links, [(2, 3), (3, 8), (8, 9), (9, 10), (3, 6), (6, 11)])

        groups1 = []
        groups2 = [{1, 2}, {3, 4}, {5, 6}, {2, 3}]

        _, links, history = geometric_tables.update_groups(groups1, groups2)
        check.equal(
            history,
            [
                [{1, 2}],
                [{1, 2}, {3, 4}],
                [{1, 2}, {3, 4}, {5, 6}],
                [{1, 2, 3, 4}, {5, 6}],
            ],
        )
        check.equal(links, [(1, 2), (3, 4), (5, 6), (2, 3)])

    def test_generic_table_simple(self):
        tb = geometric_tables.Table()

        # If a-b = b-c & d-a = c-d
        tb.add_eq4("a", "b", "b", "c", "fact1")
        tb.add_eq4("d", "a", "c", "d", "fact2")
        tb.add_eq4("x", "y", "z", "t", "fact3")  # distractor fact

        # Then b=d, because {fact1, fact2} but not fact3.
        result = list(tb.get_all_eqs_and_why())
        check.is_in(("b", "d", ["fact1", "fact2"]), result)

    def test_angle_table_inbisector_exbisector(self):
        """Test that AR can figure out bisector & ex-bisector are perpendicular."""
        # Load the scenario that we have cd is bisector of acb and
        # ce is the ex-bisector of acb.
        problem = Problem.from_txt(
            "a b c = triangle a b c; d = incenter d a b c; e = excenter e a b c ?"
            " perp d c c e"
        )
        proof, _ = Proof.build_problem(problem, self.defs)

        # Create an external angle table:
        tb = geometric_tables.AngleTable("pi")

        # Add bisector & ex-bisector facts into the table:
        ca, cd, cb, ce = proof.symbols_graph.names2nodes(
            ["d(ac)", "d(cd)", "d(bc)", "d(ce)"]
        )
        tb.add_eqangle(ca, cd, cd, cb, "fact1")
        tb.add_eqangle(ce, ca, cb, ce, "fact2")

        # Add a distractor fact to make sure traceback does not include this fact
        ab = proof.symbols_graph.names2nodes(["d(ab)"])[0]
        tb.add_eqangle(ab, cb, cb, ca, "fact3")

        # Check for all new equalities
        result = list(tb.get_all_eqs_and_why())

        # halfpi is represented as a tuple (1, 2)
        halfpi = (1, 2)

        # check that cd-ce == halfpi and this is because fact1 & fact2, not fact3
        check.equal(
            result,
            [
                (cd, ce, halfpi, ["fact1", "fact2"]),
                (ce, cd, halfpi, ["fact1", "fact2"]),
            ],
        )

    def test_angle_table_equilateral_triangle(self):
        """Test that AR can figure out triangles with 3 equal angles => each is pi/3."""
        # Load an equaliteral scenario
        problem = Problem.from_txt("a b c = ieq_triangle ? cong a b a c")
        proof, _ = Proof.build_problem(problem, self.defs)

        # Add two eqangles facts because ieq_triangle only add congruent sides
        a, b, c = proof.symbols_graph.names2nodes("abc")
        proof.statements_adder._add_eqangle(
            [a, b, b, c, b, c, c, a], EmptyDependency(0, None)
        )
        proof.statements_adder._add_eqangle(
            [b, c, c, a, c, a, a, b], EmptyDependency(0, None)
        )

        # Create an external angle table:
        tb = geometric_tables.AngleTable("pi")

        # Add the fact that there are three equal angles
        ab, bc, ca = proof.symbols_graph.names2nodes(["d(ab)", "d(bc)", "d(ac)"])
        tb.add_eqangle(ab, bc, bc, ca, "fact1")
        tb.add_eqangle(bc, ca, ca, ab, "fact2")

        # Now check for all new equalities
        result = list(tb.get_all_eqs_and_why())
        result = [(x.name, y.name, z, t) for x, y, z, t in result]

        # 1/3 pi is represented as a tuple angle_60
        angle_60 = (1, 3)
        angle_120 = (2, 3)

        # check that angles constants are created and figured out:
        check.equal(
            result,
            [
                ("d(bc)", "d(ac)", angle_120, ["fact1", "fact2"]),
                ("d(ab)", "d(bc)", angle_120, ["fact1", "fact2"]),
                ("d(ac)", "d(ab)", angle_120, ["fact1", "fact2"]),
                ("d(ac)", "d(bc)", angle_60, ["fact1", "fact2"]),
                ("d(bc)", "d(ab)", angle_60, ["fact1", "fact2"]),
                ("d(ab)", "d(ac)", angle_60, ["fact1", "fact2"]),
            ],
        )

    def test_incenter_excenter_touchpoints(self):
        """Test that AR can figure out incenter/excenter touchpoints are equidistant to midpoint."""

        problem = Problem.from_txt(
            "a b c = triangle a b c; d1 d2 d3 d = incenter2 a b c; e1 e2 e3 e ="
            " excenter2 a b c ? perp d c c e",
            translate=False,
        )
        proof, _ = Proof.build_problem(problem, self.defs)

        a, b, c, ab, bc, ca, d1, d2, d3, e1, e2, e3 = proof.symbols_graph.names2nodes(
            ["a", "b", "c", "ab", "bc", "ac", "d1", "d2", "d3", "e1", "e2", "e3"]
        )

        # Create an external distance table:
        tb = geometric_tables.DistanceTable()

        # DD can figure out the following facts,
        # we manually add them to AR.
        tb.add_cong(ab, ca, a, d3, a, d2, "fact1")
        tb.add_cong(ab, ca, a, e3, a, e2, "fact2")
        tb.add_cong(ca, bc, c, d2, c, d1, "fact5")
        tb.add_cong(ca, bc, c, e2, c, e1, "fact6")
        tb.add_cong(bc, ab, b, d1, b, d3, "fact3")
        tb.add_cong(bc, ab, b, e1, b, e3, "fact4")

        # Now we check whether tb has figured out that
        # distance(b, d1) == distance(e1, c)

        # linear comb exprssion of each variables:
        b = tb.v2e["bc:b"]
        c = tb.v2e["bc:c"]
        d1 = tb.v2e["bc:d1"]
        e1 = tb.v2e["bc:e1"]

        check.equal(geometric_tables.minus(d1, b), geometric_tables.minus(c, e1))
