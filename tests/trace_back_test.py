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

from geosolver.configs import default_defs_path, default_rules_path
from geosolver.ddar import solve
import geosolver.graph as gh
import geosolver.problem as pr
import geosolver.trace_back as tb


class TestTraceback:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.defs = pr.Definition.from_txt_file(default_defs_path(), to_dict=True)
        self.rules = pr.Theorem.from_txt_file(default_rules_path(), to_dict=True)

    def test_orthocenter_dependency_difference(self):
        txt = "a b c = triangle a b c; d = on_tline d b a c, on_tline d c a b; e = on_line e a c, on_line e b d ? perp a d b c"
        p = pr.Problem.from_txt(txt)
        graph, _ = gh.Graph.build_problem(p, self.defs)

        solve(graph, self.rules, p)

        goal_args = graph.names2nodes(p.goal.args)
        query = pr.Dependency(p.goal.name, goal_args, None, None)

        setup, aux, _, _ = tb.get_logs(query, graph, merge_trivials=False)

        # Convert each predicates to its hash string:
        setup = [p.hashed() for p in setup]
        aux = [p.hashed() for p in aux]

        check.equal(
            set(setup), {("perp", "a", "c", "b", "d"), ("perp", "a", "b", "c", "d")}
        )

        check.equal(set(aux), {("coll", "a", "c", "e"), ("coll", "b", "d", "e")})
