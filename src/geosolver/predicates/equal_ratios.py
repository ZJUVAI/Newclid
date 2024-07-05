from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import Predicate
from geosolver.tools import reshape


if TYPE_CHECKING:
    from geosolver.statement import Statement
    from geosolver.dependency.dependency_graph import DependencyGraph


class EqRatio(Predicate):
    """eqratio AB CD EF GH -

    Represent that AB/CD=EF/GH, as ratios between lengths of segments.
    """

    NAME = "eqratio"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        groups: list[tuple[str, str, str, str]] = []
        groups1: list[tuple[str, str, str, str]] = []
        for a, b, c, d in reshape(args, 4):
            a, b = sorted((a, b))
            c, d = sorted((c, d))
            groups.append((a, b, c, d))
            groups1.append((c, d, a, b))
        return tuple(
            dep_graph.symbols_graph.names2points(sum(sorted(min(groups, groups1)), ()))
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        ratio = None
        for a, b, c, d in reshape(list(statement.args), 4):
            a: Point
            b: Point
            c: Point
            d: Point
            _ratio = a.num.distance(b.num) / c.num.distance(d.num)
            if ratio is not None and not close_enough(ratio, _ratio):
                return False
            ratio = _ratio
        return True

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)


class EqRatio6(EqRatio):
    """eqratio AB CD EF -"""

    NAME = "eqratio6"


class EqRatio3(Predicate):
    """eqratio AB CD MN -

    Represent three eqratios through a list of 6 points (due to parallel lines).
    It can be viewed as in an instance of Thales theorem which has AB // MN // CD.

    It thus represent the corresponding eqratios:
    MA / MC = NB / ND and AM / AC = BN / BD and MC / AC = ND / BD

    ::

          a -- b
         m ---- n
        c ------ d


    """

    NAME = "eqratio3"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, d, e, f = args
        groups = ((a, b), (c, d), (e, f))
        groups1 = ((b, a), (d, c), (f, e))
        return tuple(
            dep_graph.symbols_graph.names2points(sum(sorted(min(groups, groups1)), ()))
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        a, b, c, d, m, n = statement.args
        eqr1 = statement.with_new(EqRatio, (m, a, m, c, n, b, n, d))
        eqr2 = statement.with_new(EqRatio, (m, a, a, c, b, n, b, d))
        eqr3 = statement.with_new(EqRatio, (m, c, a, c, n, d, b, d))
        return (
            eqr1.check_numerical() and eqr2.check_numerical() and eqr3.check_numerical()
        )

    @classmethod
    def check(cls, statement: Statement) -> bool:
        a, b, c, d, m, n = statement.args
        eqr1 = statement.with_new(EqRatio, (m, a, m, c, n, b, n, d))
        eqr2 = statement.with_new(EqRatio, (m, a, a, c, b, n, b, d))
        eqr3 = statement.with_new(EqRatio, (m, c, a, c, n, d, b, d))
        return eqr1.check() and eqr2.check() and eqr3.check()

    # @classmethod
    # def add(cls, dep: Dependency):
    #     statement = dep.statement
    #     a, b, c, d, m, n = statement.args
    #     eqr1 = statement.with_new(EqRatio, (m, a, m, c, n, b, n, d))
    #     eqr2 = statement.with_new(EqRatio, (m, a, a, c, b, n, b, d))
    #     eqr3 = statement.with_new(EqRatio, (m, c, a, c, n, d, b, d))
    #     return eqr1.check() and eqr2.check() and eqr3.check()
