"""Shared test fixtures and utilities."""

from newclid.api import GeometricSolver, GeometricSolverBuilder
from newclid.numerical.distances import PointTooCloseError, PointTooFarError


def build_until_works(
    builder: GeometricSolverBuilder, max_attempts: int = 100
) -> GeometricSolver:
    """Build a solver, retrying on random point placement failures."""
    for attempt in range(1, max_attempts + 1):
        try:
            return builder.build()
        except (PointTooFarError, PointTooCloseError):
            continue
    raise RuntimeError(f"Failed to build solver after {max_attempts} attempts")
