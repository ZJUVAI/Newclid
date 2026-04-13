from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from scripts.evaluation import (
    build_eval_output_stem,
    build_timestamped_output_stem,
    sanitize_problem_name,
    create_workers,
    main,
    solve_one_problem,
    solve_problems_single_problem_multi_gpu,
)

__all__ = [
    "build_eval_output_stem",
    "build_timestamped_output_stem",
    "sanitize_problem_name",
    "create_workers",
    "solve_one_problem",
    "solve_problems_single_problem_multi_gpu",
    "main",
]


if __name__ == "__main__":
    main()
