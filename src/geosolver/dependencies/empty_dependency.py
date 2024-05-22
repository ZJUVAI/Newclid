from typing import TYPE_CHECKING
from geosolver.dependencies.dependency import Dependency
from geosolver.geometry import Point

if TYPE_CHECKING:
    from geosolver.proof import Proof


class EmptyDependency:
    """Empty dependency predicate ready to get filled up."""

    def __init__(self, level: int, rule_name: str):
        self.level = level
        self.rule_name = rule_name or ""
        self.empty = True
        self.why = []
        self.trace = None

    def populate(self, name: str, args: list["Point"]) -> Dependency:
        dep = Dependency(name, args, self.rule_name, self.level)
        dep.trace2 = self.trace
        dep.why = list(self.why)
        return dep

    def copy(self) -> "EmptyDependency":
        other = EmptyDependency(self.level, self.rule_name)
        other.why = list(self.why)
        return other

    def extend(
        self,
        proof: "Proof",
        name0: str,
        args0: list["Point"],
        name: str,
        args: list["Point"],
    ) -> "EmptyDependency":
        """Extend the dependency list by (name, args)."""
        dep0 = self.populate(name0, args0)
        deps = EmptyDependency(level=self.level, rule_name=None)
        dep = Dependency(name, args, None, deps.level)
        deps.why = [
            dep0,
            dep.why_me_or_cache(
                proof.symbols_graph,
                proof.statements.checker,
                proof.dependency_cache,
                None,
            ),
        ]
        return deps

    def extend_many(
        self,
        proof: "Proof",
        name0: str,
        args0: list["Point"],
        name_args: list[tuple[str, list["Point"]]],
    ) -> "EmptyDependency":
        """Extend the dependency list by many name_args."""
        if not name_args:
            return self
        dep0 = self.populate(name0, args0)
        deps = EmptyDependency(level=self.level, rule_name=None)
        deps.why = [dep0]
        for name, args in name_args:
            dep = Dependency(name, args, None, deps.level)
            deps.why += [
                dep.why_me_or_cache(
                    proof.symbols_graph,
                    proof.statements.checker,
                    proof.dependency_cache,
                    None,
                )
            ]
        return deps
