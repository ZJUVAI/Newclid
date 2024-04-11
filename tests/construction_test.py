import pytest
from geosolver.problem import Definition, Problem
from geosolver.proof import DepCheckFailError, Proof


class TestConstruction:
    @pytest.fixture(autouse=True)
    def setUp(self):
        self.defs = Definition.to_dict(Definition.from_txt_file("defs.txt"))

    def test_construction_attempts_limit(self):
        """Construction should raise an error
        after failing a fixed number of attempts."""
        p = Problem.from_txt("a b c = triangle a b c ? perp a b a c")
        max_attempts = 100
        with pytest.raises(DepCheckFailError, match=f"failed {max_attempts} times"):
            Proof.build_problem(p, self.defs, max_attempts=max_attempts)
