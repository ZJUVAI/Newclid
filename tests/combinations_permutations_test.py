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

"""Unit tests for graph_utils.py."""


import pytest_check as check

from geosolver.combinations_permutations import (
    cross,
    comb2,
    comb3,
    comb4,
    perm2,
    perm3,
    perm4,
)


class TestCombinationsPermutations:
    def test_cross(self):
        check.equal(cross([], [1]), [])
        check.equal(cross([1], []), [])
        check.equal(cross([1], [2]), [(1, 2)])
        check.equal(cross([1], [2, 3]), [(1, 2), (1, 3)])

        e1 = [1, 2, 3]
        e2 = [4, 5]
        target = [(1, 4), (1, 5), (2, 4), (2, 5), (3, 4), (3, 5)]
        check.equal(cross(e1, e2), target)

    def test_comb2(self):
        check.equal(comb2([]), [])
        check.equal(comb2([1]), [])
        check.equal(comb2([1, 2]), [(1, 2)])
        check.equal(comb2([1, 2, 3]), [(1, 2), (1, 3), (2, 3)])

    def test_comb3(self):
        check.equal(comb3([]), [])
        check.equal(comb3([1]), [])
        check.equal(comb3([1, 2]), [])
        check.equal(comb3([1, 2, 3]), [(1, 2, 3)])
        check.equal(comb3([1, 2, 3, 4]), [(1, 2, 3), (1, 2, 4), (1, 3, 4), (2, 3, 4)])

    def test_comb4(self):
        check.equal(comb4([]), [])
        check.equal(comb4([1]), [])
        check.equal(comb4([1, 2]), [])
        check.equal(comb4([1, 2, 3]), [])
        check.equal(comb4([1, 2, 3, 4]), [(1, 2, 3, 4)])
        check.equal(
            comb4([1, 2, 3, 4, 5]),
            [(1, 2, 3, 4), (1, 2, 3, 5), (1, 2, 4, 5), (1, 3, 4, 5), (2, 3, 4, 5)],
        )

    def test_perm2(self):
        check.equal(perm2([]), [])
        check.equal(perm2([1]), [])
        check.equal(perm2([1, 2]), [(1, 2), (2, 1)])
        check.equal(perm2([1, 2, 3]), [(1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (3, 2)])

    def test_perm3(self):
        check.equal(perm3([]), [])
        check.equal(perm3([1]), [])
        check.equal(perm3([1, 2]), [])
        check.equal(
            perm3([1, 2, 3]),
            [(1, 2, 3), (1, 3, 2), (2, 1, 3), (2, 3, 1), (3, 1, 2), (3, 2, 1)],
        )
        check.equal(
            perm3([1, 2, 3, 4]),
            [
                (1, 2, 3),
                (1, 2, 4),
                (1, 3, 2),
                (1, 3, 4),
                (1, 4, 2),
                (1, 4, 3),
                (2, 1, 3),
                (2, 1, 4),
                (2, 3, 1),
                (2, 3, 4),
                (2, 4, 1),
                (2, 4, 3),
                (3, 1, 2),
                (3, 1, 4),
                (3, 2, 1),
                (3, 2, 4),
                (3, 4, 1),
                (3, 4, 2),
                (4, 1, 2),
                (4, 1, 3),
                (4, 2, 1),
                (4, 2, 3),
                (4, 3, 1),
                (4, 3, 2),
            ],
        )

    def test_perm4(self):
        check.equal(perm3([]), [])
        check.equal(perm3([1]), [])
        check.equal(perm3([1, 2]), [])
        check.equal(perm4([1, 2, 3]), [])
        check.equal(
            perm4([1, 2, 3, 4]),
            [
                (1, 2, 3, 4),
                (1, 2, 4, 3),
                (1, 3, 2, 4),
                (1, 3, 4, 2),
                (1, 4, 2, 3),
                (1, 4, 3, 2),
                (2, 1, 3, 4),
                (2, 1, 4, 3),
                (2, 3, 1, 4),
                (2, 3, 4, 1),
                (2, 4, 1, 3),
                (2, 4, 3, 1),
                (3, 1, 2, 4),
                (3, 1, 4, 2),
                (3, 2, 1, 4),
                (3, 2, 4, 1),
                (3, 4, 1, 2),
                (3, 4, 2, 1),
                (4, 1, 2, 3),
                (4, 1, 3, 2),
                (4, 2, 1, 3),
                (4, 2, 3, 1),
                (4, 3, 1, 2),
                (4, 3, 2, 1),
            ],
        )
