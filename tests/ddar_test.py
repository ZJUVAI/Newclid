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

"""Unit tests for geosolver.py."""
import pytest
import pytest_check as check

from geosolver.ddar import ddar_solve
from geosolver.deductive.breadth_first_search import BFSDeductor
from geosolver.proof import Proof
from geosolver.problem import Definition, Problem, Theorem


class TestDDAR:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.defs = Definition.to_dict(Definition.from_txt_file("defs.txt"))
        self.rules = Theorem.from_txt_file("rules.txt")

    def test_orthocenter_should_fail(self):
        problem = Problem.from_txt(
            "a b c = triangle a b c; "
            "d = on_tline d b a c, "
            "on_tline d c a b "
            "? perp a d b c"
        )
        deductive_agent = BFSDeductor(problem)

        proof, _ = Proof.build_problem(problem, self.defs)

        ddar_solve(deductive_agent, proof, self.rules, problem, max_steps=1000)
        goal_args = proof.symbols_graph.names2nodes(problem.goal.args)
        check.is_false(proof.check(problem.goal.name, goal_args))

    def test_orthocenter_aux_should_succeed(self):
        problem = Problem.from_txt(
            "a b c = triangle a b c; "
            "d = on_tline d b a c, "
            "on_tline d c a b; "
            "e = on_line e a c, "
            "on_line e b d "
            "? perp a d b c"
        )
        deductive_agent = BFSDeductor(problem)

        proof, _ = Proof.build_problem(problem, self.defs)

        ddar_solve(deductive_agent, proof, self.rules, problem, max_steps=1000)
        goal_args = proof.symbols_graph.names2nodes(problem.goal.args)
        check.is_true(proof.check(problem.goal.name, goal_args))

    def test_incenter_excenter_should_succeed(self):
        # Note that this same problem should fail in dd_test.py
        problem = Problem.from_txt(
            "a b c = triangle a b c; "
            "d = incenter d a b c; "
            "e = excenter e a b c "
            "? perp d c c e"
        )
        deductive_agent = BFSDeductor(problem)

        proof, _ = Proof.build_problem(problem, self.defs)

        ddar_solve(deductive_agent, proof, self.rules, problem, max_steps=1000)
        goal_args = proof.symbols_graph.names2nodes(problem.goal.args)
        check.is_true(proof.check(problem.goal.name, goal_args))
