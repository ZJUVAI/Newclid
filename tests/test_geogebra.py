import sys

from newclid.__main__ import main


def test_orthocenter():
    sys.argv = [
        "newclid",
        "--problem-name",
        "orthocenter",
        "--env",
        "tests-exp",
        "--quiet",
    ]
    assert main()


def test_imo2009p2():
    sys.argv = [
        "newclid",
        "--problem-name",
        "imo2009p2",
        "--env",
        "tests-exp",
    ]
    assert main()
