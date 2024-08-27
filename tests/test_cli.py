import sys
from geosolver.__main__ import main


def test_exhaust():
    sys.argv = [
        "geosolver",
        "--problem-name",
        "imo2009p2",
        "--env",
        "tests-exp",
        "--exhaust",
    ]
    assert not main()


def test_run_problems_file():
    sys.argv = [
        "geosolver",
        "--problem-name",
        "orthocenter_aux",
        "--problems-file",
        r"problems_datasets/examples.txt",
        "--quiet",
    ]
    assert main()
