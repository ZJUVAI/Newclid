from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable


import geosolver.predicates as preds
from geosolver.predicates import Predicate

from geosolver.reasoning_engines.algebraic_reasoning.tables import (
    AngleTable,
    RatioTable,
    SumCV,
    report,
)
from geosolver.reasoning_engines.engines_interface import ReasoningEngine

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency

config: dict[Any, Any] = dict()


class AlgebraicRules(Enum):
    Angle_Chase = "alc"
    Ratio_Chase = "rac"


class AlgebraicManipulator(ReasoningEngine):
    def __init__(self) -> None:
        self.atable = AngleTable()
        self.rtable = RatioTable()
        self.verbose = config.get("verbose", "")

        self.PREDICATE_TO_GETTER: dict[
            type[Predicate], tuple[Callable[..., list[SumCV]], AngleTable | RatioTable]
        ] = {
            preds.Para: (self.atable.get_para, self.atable),
            preds.EqAngle: (self.atable.get_eqangles, self.atable),
            preds.EqAngle6: (self.atable.get_eqangles, self.atable),
            preds.ConstantAngle: (self.atable.get_const_angle, self.atable),
            preds.EqRatio: (self.rtable.get_eqratios, self.rtable),
            preds.EqRatio6: (self.rtable.get_eqratios, self.rtable),
            preds.Cong: (self.rtable.get_eqlengths, self.rtable),
            preds.ConstantRatio: (self.rtable.get_const_ratio, self.rtable),
            preds.ConstantLength: (self.rtable.get_const_length, self.rtable),
        }

    def add(self, predicate: type[Predicate], args: tuple[Any, ...], dep: "Dependency"):
        got = self.PREDICATE_TO_GETTER.get(predicate)
        if got is not None:
            getter, table = got
            exprs = getter(args)
            for e in exprs:
                table.add_expr(e, dep)

    def ingest(self, dep: "Dependency"):
        """Add new algebraic predicates."""
        got = self.PREDICATE_TO_GETTER.get(dep.statement.predicate)
        if got is not None:
            getter, table = got
            exprs = getter(dep.statement.args)
            for e in exprs:
                table.add_expr(e, dep)

    def resolve(self, **kwargs: Any) -> list[Dependency]:
        """Derive new algebraic predicates."""
        if "a" in self.verbose:
            report(self.atable.v2e)
        if "r" in self.verbose:
            report(self.rtable.v2e)
        return []

    def check(self, predicate: type[Predicate], args: tuple[Any, ...]) -> bool:
        got = self.PREDICATE_TO_GETTER.get(predicate)
        if got is not None:
            getter, table = got
            exprs = getter(args)
            return all(table.add_expr(e, None) for e in exprs)
        return False

    def why(
        self, predicate: type[Predicate], args: tuple[Any, ...]
    ) -> list[Dependency]:
        got = self.PREDICATE_TO_GETTER.get(predicate)
        if got is not None:
            getter, table = got
            exprs = getter(args)
            empty: list[Dependency] = []
            return sum((table.why(e) for e in exprs), empty)
        raise ValueError(f"{predicate} should not be asked why in AR")
