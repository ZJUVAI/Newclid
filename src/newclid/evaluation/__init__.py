"""Compatibility exports for the evaluation entrypoints."""

from newclid.evaluation.output import (
    build_eval_output_stem,
    build_timestamped_output_stem,
    normalize_agent_type,
    sanitize_problem_name,
)

__all__ = [
    "build_eval_output_stem",
    "build_timestamped_output_stem",
    "normalize_agent_type",
    "sanitize_problem_name",
    "create_workers",
    "main",
    "solve_one_problem",
    "solve_problems_single_problem_multi_gpu",
]


def __getattr__(name: str):
    if name in {
        "create_workers",
        "main",
        "solve_one_problem",
        "solve_problems_single_problem_multi_gpu",
    }:
        from newclid.evaluation import runner as runner_module

        return getattr(runner_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
