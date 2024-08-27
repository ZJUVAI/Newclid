import sys

from geosolver.__main__ import main


def test_orthocenter():
    sys.argv = [
        "geosolver",
        "--problem-name",
        "orthocenter",
        "--env",
        "tests-exp",
        "--quiet",
    ]
    assert main()


def test_imo2009p2():
    sys.argv = [
        "geosolver",
        "--problem-name",
        "imo2009p2",
        "--env",
        "tests-exp",
    ]
    assert main()
