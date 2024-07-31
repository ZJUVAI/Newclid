import sys

from geosolver.__main__ import main


def test_orthocenter():
    sys.argv = ["geosolver", "--problem-name", "orthocenter", "--exp", "tests-exp"]
    assert main()


def test_imo2009p2():
    sys.argv = ["geosolver", "--problem-name", "imo2009p2", "--exp", "tests-exp"]
    assert main()
