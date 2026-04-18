"""CSolver benchmark regression tests.

Ensures the solver can solve at least as many problems as the baseline count.
Marked as @pytest.mark.slow — excluded from normal test runs.

Run with: python -m pytest tests/test_csolver_benchmarks.py -v
"""

from pathlib import Path

import pytest

from newclid.api import CSolver

BENCHMARKS_DIR = Path(__file__).resolve().parents[1] / "benchmarks"

# Baseline solve counts (current performance, must not regress)
BASELINES = {
    "imo_ag_30.txt": 15,
    "imo_95.txt": 0,
    "jgex_ag_231.txt": 203,
    "hageo_409.txt": 103,
}


def _load_problems(path: Path) -> list[tuple[str, str]]:
    """Load (name, problem) pairs from a benchmark file."""
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    problems = []
    for i in range(0, len(lines), 2):
        name = lines[i].strip()
        stmt = lines[i + 1].strip()
        problems.append((name, stmt))
    return problems


@pytest.mark.slow
@pytest.mark.parametrize(
    "filename,min_solved", list(BASELINES.items()), ids=list(BASELINES.keys())
)
def test_benchmark_regression(filename: str, min_solved: int):
    path = BENCHMARKS_DIR / filename
    if not path.exists():
        pytest.skip(f"Benchmark file not found: {path}")

    problems = _load_problems(path)
    solved = 0

    for name, stmt in problems:
        try:
            solver = CSolver(problem=stmt, problem_name=name, seed=123, using_log=True)
            if solver.run(max_level=500):
                solved += 1
        except Exception:
            pass

    assert solved >= min_solved, (
        f"{filename}: solved {solved}/{len(problems)}, expected >= {min_solved}"
    )
