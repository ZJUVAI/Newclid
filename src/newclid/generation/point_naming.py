"""
Point naming utilities.

Provides a class for generating unique point names in geometric constructions.
"""

import string


class PointNaming:
    """
    Generator for unique point names.

    Creates point names using lowercase letters and numbers:
    a, b, ..., z, a0, b0, ..., z0, a1, b1, ...
    """

    def __init__(self, max_points: int = 260):
        """
        Initialize the point naming.

        Args:
            max_points: Maximum number of points that can be generated.
        """
        self.max_points = max_points
        self.defined_points: list[str] = []

    def get_point_name(self, va_idx: int) -> str:
        """
        Generate a point name for the given index.

        Args:
            va_idx: The index of the point (0-based).

        Returns:
            A point name string (e.g., "a", "b", "a0", "b0").
        """
        letter_part = string.ascii_lowercase[va_idx % 26]
        number_part = va_idx // 26
        # a, b, ..., z, a0, b0, ...
        return f"{letter_part}{number_part - 1}" if number_part else letter_part

    def prefetch_points(self, n: int) -> list[str]:
        """
        Generate n new point names without defining them.

        Args:
            n: Number of point names to generate.

        Returns:
            List of new point names.

        Raises:
            ValueError: If generating n points would exceed max_points.
        """
        res = []
        for i in range(n):
            if len(self.defined_points) + i >= self.max_points:
                raise ValueError("All point names exhausted.")
            point_name = self.get_point_name(len(self.defined_points) + i)
            res.append(point_name)
        return res

    def define_points(self, points: list[str]) -> None:
        """
        Mark points as defined.

        Args:
            points: List of point names to define.

        Raises:
            ValueError: If defining points would exceed max_points.
        """
        for p in points:
            if len(self.defined_points) >= self.max_points:
                raise ValueError("All point names exhausted.")
            self.defined_points.append(p)
