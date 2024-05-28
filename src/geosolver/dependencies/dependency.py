from __future__ import annotations


from geosolver.dependencies.caching import hashed
from geosolver.geometry import Point
from geosolver.problem import Construction


class Dependency(Construction):
    """Dependency is a predicate that other predicates depend on."""

    def __init__(self, name: str, args: list["Point"], rule_name: str, level: int):
        super().__init__(name, args)
        self.rule_name = rule_name or ""
        self.level = level
        self.why: list[Dependency] = []

        self._stat = None
        self.trace = None

    def _find(self, dep_hashed: tuple[str, ...]) -> "Dependency":
        for w in self.why:
            f = w._find(dep_hashed)
            if f:
                return f
            if w.hashed() == dep_hashed:
                return w

    def remove_loop(self) -> "Dependency":
        f = self._find(self.hashed())
        if f:
            return f
        return self

    def copy(self) -> "Dependency":
        dep = Dependency(self.name, self.args, self.rule_name, self.level)
        dep.trace = self.trace
        dep.why = list(self.why)
        return dep

    def hashed(self, rename: bool = False) -> tuple[str, ...]:
        return hashed(self.name, self.args, rename=rename)
