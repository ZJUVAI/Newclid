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

"""Unit tests for graph.py."""
import pytest
import pytest_check as check
from geosolver.api import GeometricSolverBuilder
from geosolver.numerical.check import (
    check_circle_numerical,
    check_coll_numerical,
    check_cong_numerical,
    check_cyclic_numerical,
    check_eqangle_numerical,
    check_eqratio_numerical,
    check_para_numerical,
    check_perp_numerical,
    check_midp_numerical,
)
from geosolver.predicates import Predicate


class TestProof:
    @pytest.fixture(autouse=True)
    def setup(self):
        solver = (
            GeometricSolverBuilder()
            .load_problem_from_txt(
                "a b c = triangle a b c; "
                "h = orthocenter a b c; "
                "h1 = foot a b c; "
                "h2 = foot b c a; "
                "h3 = foot c a b; "
                "g1 g2 g3 g = centroid g1 g2 g3 g a b c; "
                "o = circle a b c "
                "? coll h g o",
                translate=False,
            )
            .build()
        )
        self.proof = solver.proof_state
        self.symbols_graph = self.proof.symbols_graph
        self.checker = self.proof.statements.checker
        self.enumerator = self.proof.statements.enumerator

    def test_enumerate_colls(self):
        for a, b, c in self.enumerator.all(Predicate.COLLINEAR):
            check.is_true(self.checker.check_coll([a, b, c]))
            check.is_true(check_coll_numerical([a.num, b.num, c.num]))

    def test_enumerate_paras(self):
        for a, b, c, d in self.enumerator.all(Predicate.PARALLEL):
            check.is_true(self.checker.check_para([a, b, c, d]))
            check.is_true(check_para_numerical([a.num, b.num, c.num, d.num]))

    def test_enumerate_perps(self):
        for a, b, c, d in self.enumerator.all(Predicate.PERPENDICULAR):
            check.is_true(self.checker.check_perp([a, b, c, d]))
            check.is_true(check_perp_numerical([a.num, b.num, c.num, d.num]))

    def test_enumerate_congs(self):
        for a, b, c, d in self.enumerator.all(Predicate.CONGRUENT):
            check.is_true(self.checker.check_cong([a, b, c, d]))
            check.is_true(check_cong_numerical([a.num, b.num, c.num, d.num]))

    def test_enumerate_cyclics(self):
        for a, b, c, d, x, y, z, t in self.enumerator.all(Predicate.CYCLIC):
            check.is_true(self.checker.check_cyclic([a, b, c, d, x, y, z, t]))
            check.is_true(check_cyclic_numerical([a.num, b.num, c.num, d.num]))

    def test_enumerate_midps(self):
        for a, b, c in self.enumerator.all(Predicate.MIDPOINT):
            check.is_true(self.checker.check_midp([a, b, c]))
            check.is_true(check_midp_numerical([a.num, b.num, c.num]))

    def test_enumerate_circles(self):
        for a, b, c, d in self.enumerator.all(Predicate.CIRCLE):
            check.is_true(self.checker.check_circle([a, b, c, d]))
            check.is_true(check_circle_numerical([a.num, b.num, c.num, d.num]))

    @pytest.mark.slow
    def test_enumerate_eqangles(self):
        for a, b, c, d, x, y, z, t in self.enumerator.all(Predicate.EQANGLE):
            check.is_true(self.checker.check_eqangle([a, b, c, d, x, y, z, t]))
            check.is_true(
                check_eqangle_numerical(
                    [a.num, b.num, c.num, d.num, x.num, y.num, z.num, t.num]
                )
            )

    @pytest.mark.slow
    def test_enumerate_eqratios(self):
        for a, b, c, d, x, y, z, t in self.enumerator.all(Predicate.EQRATIO):
            check.is_true(self.checker.check_eqratio([a, b, c, d, x, y, z, t]))
            check.is_true(
                check_eqratio_numerical(
                    [a.num, b.num, c.num, d.num, x.num, y.num, z.num, t.num]
                )
            )
