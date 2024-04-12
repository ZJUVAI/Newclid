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

"""Unit tests for problem.py."""

import pytest
from geosolver.configs import default_defs_path
import geosolver.problem as pr


class TestProblem:
    @pytest.fixture(autouse=True)
    def setUp(self):
        self.defs = pr.Definition.from_txt_file(default_defs_path(), to_dict=True)

    def test_orthocenter_no_translate(self):
        txt = "a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c"

        # read the txt into pr.Problem object, do not change the name of points:
        p = pr.Problem.from_txt(txt, translate=False)

        # This is fed into the LM, translating from constructive to constrained:
        setup_str = p.setup_str_from_problem(self.defs)

        assert (
            setup_str
            == "{S} a : ; b : ; c : ; h : T a b c h 00 T a c b h 01 ? T a h b c"
        )

    def test_orthocenter_translate(self):
        txt = "a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c"

        # Read the txt into pr.Problem object, change h -> d to match
        # training data distribution.
        p = pr.Problem.from_txt(txt, translate=True)

        # This is fed into the LM, translating from constructive to constrained:
        setup_str = p.setup_str_from_problem(self.defs)

        assert (
            setup_str
            == "{S} a : ; b : ; c : ; d : T a b c d 00 T a c b d 01 ? T a d b c"
        )
