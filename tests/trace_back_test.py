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

"""Unit testing for the trace_back code."""


import pytest
import pytest_check as check

from geosolver.concepts import ConceptName
from geosolver.ddar import ddar_solve
from geosolver.deductive.breadth_first_search import BFSDeductor
from geosolver.dependencies.dependency import Dependency
from geosolver.proof import Proof
from geosolver.problem import Definition, Problem, Theorem
from geosolver.trace_back import get_logs


class TestTraceback:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.defs = Definition.from_txt_file("defs.txt", to_dict=True)
        self.rules = Theorem.from_txt_file("rules.txt", to_dict=True)

    def test_orthocenter_dependency_difference(self):
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

        ddar_solve(deductive_agent, proof, self.rules, problem)

        goal_args = proof.symbols_graph.names2nodes(problem.goal.args)
        query = Dependency(problem.goal.name, goal_args, None, None)

        setup, aux, _, _ = get_logs(query, proof, merge_trivials=False)

        # Convert each predicates to its hash string:
        setup = [p.hashed() for p in setup]
        aux = [p.hashed() for p in aux]

        check.equal(
            set(setup),
            {
                (ConceptName.PERPENDICULAR.value, "a", "c", "b", "d"),
                ("perp", "a", "b", "c", "d"),
            },
        )

        check.equal(
            set(aux),
            {
                (ConceptName.COLLINEAR.value, "a", "c", "e"),
                (ConceptName.COLLINEAR.value, "b", "d", "e"),
            },
        )
