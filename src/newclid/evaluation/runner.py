from __future__ import annotations

from typing import Any


def _evaluation_module():
    from scripts import evaluation as evaluation_module

    return evaluation_module


def create_workers(*args: Any, **kwargs: Any):
    return _evaluation_module().create_workers(*args, **kwargs)


def solve_one_problem(*args: Any, **kwargs: Any):
    return _evaluation_module().solve_one_problem(*args, **kwargs)


def solve_problems_single_problem_multi_gpu(*args: Any, **kwargs: Any):
    return _evaluation_module().solve_problems_single_problem_multi_gpu(*args, **kwargs)


def main(*args: Any, **kwargs: Any):
    return _evaluation_module().main(*args, **kwargs)


__all__ = [
    "create_workers",
    "main",
    "solve_one_problem",
    "solve_problems_single_problem_multi_gpu",
]
