"""Implementing Algebraic Reasoning (AR)."""

import logging
from typing import TYPE_CHECKING, Any, Literal, Optional
from numpy import exp
from geosolver.tools import simplify
import numpy as np
import scipy.optimize as opt  # type: ignore

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
    from geosolver.dependency.symbols import Point

ATOM: float = 1e-9
NLOGATOM: int = 9


Angle_Chase = "alc"
Ratio_Chase = "rac"


class Coef(float):
    def __hash__(self) -> int:
        raise NotImplementedError

    def __eq__(self, other: "Coef"):  # type: ignore
        return abs(self - other) < ATOM

    def __ne__(self, other: "Coef") -> bool:  # type: ignore
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return f"{self:.2f}"

    def __add__(self, value: float) -> "Coef":
        return Coef(super().__add__(value))

    def __mul__(self, value: float) -> "Coef":
        return Coef(super().__mul__(value))

    def __sub__(self, value: float) -> "Coef":
        return Coef(super().__sub__(value))

    def __truediv__(self, value: float) -> "Coef":
        return Coef(super().__truediv__(value))

    def __neg__(self) -> "Coef":
        return Coef(super().__neg__())

    def __mod__(self, value: float) -> "Coef":
        return Coef(round(float(self), NLOGATOM) % round(float(value), NLOGATOM))


SumCV = dict[str, Coef]
EqDict = dict[str, SumCV]


class InfQuotientError(Exception):
    pass


# maximum denominator for a fraction.
MAX_DENOMINATOR = 1000000

# tolerance for fraction approximation
TOL = 1e-9


def get_quotient(v: Any) -> tuple[int, int]:
    v = float(v)
    n = v
    d = 1
    while abs(n - round(n)) > TOL:
        d += 1
        n += v
        if d > MAX_DENOMINATOR:
            e = InfQuotientError(v)
            raise e

    n = int(round(n))
    return simplify(n, d)


def hashed(e: SumCV) -> tuple[tuple[str, Coef], ...]:
    return tuple(sorted(list(e.items())))


def strip(e: SumCV) -> SumCV:
    return {v: c for v, c in e.items() if c != Coef(0)}


def plus(e1: SumCV, e2: SumCV) -> SumCV:
    e = dict(e1)
    for v, c in e2.items():
        if v in e:
            e[v] += c
        else:
            e[v] = c
    return strip(e)


def plus_all(*es: SumCV) -> SumCV:
    result = {}
    for e in es:
        result = plus(result, e)
    return result


def mult(e: SumCV, m: Coef) -> SumCV:
    return {v: m * c for v, c in e.items()}


def minus(e1: SumCV, e2: SumCV) -> SumCV:
    return plus(e1, mult(e2, Coef(-1)))


def recon(e: SumCV, const: str) -> Optional[tuple[str, SumCV]]:
    """Reconcile one variable in the expression e=0, given const."""
    e = strip(e)
    if len(e) == 0:
        return None

    v0 = None
    for v in e:
        if v != const:
            v0 = v
            break
    if v0 is None:
        return None

    c0 = e.pop(v0)
    return v0, {v: -c / c0 for v, c in e.items()}


def replace(e: SumCV, v0: str, e0: SumCV) -> SumCV:
    if v0 not in e:
        return e
    e = dict(e)
    m = e.pop(v0)
    return plus(e, mult(e0, m))


def _fix_width(s: Any, width: int, align: Literal["right", "left", "center"] = "right"):
    if align != "right":
        raise NotImplementedError
    s = str(s)
    return " " * (width - len(s)) + s


def coef2str(x: Coef):
    try:
        n, d = get_quotient(x)
        return f"{n}/{d}"
    except InfQuotientError as _:
        n, d = get_quotient(exp(x))
        return f"log{n}/{d}"


def report(eqdict: EqDict):
    table_str = ">>>>>>>>>table begins\n"
    maxlv = 0
    maxlcoef = 0
    setv_right: set[str] = set()
    setv_left: set[str] = set()
    for leftv, eq in eqdict.items():
        setv_left.add(leftv)
        maxlv = max(maxlv, len(str(leftv)))
        for rightv, coef in eq.items():
            setv_right.add(rightv)
            maxlv = max(maxlv, len(str(rightv)))
            maxlcoef = max(maxlcoef, len(coef2str(coef)))
    listv_left = sorted(setv_left)
    listv_right = sorted(setv_right)
    for leftv in listv_left:
        table_str += f"{_fix_width(leftv, maxlv)} = "
        for rightv in listv_right:
            try:
                coef = eqdict[leftv][rightv]
                if abs(coef) < ATOM:
                    raise ValueError
                table_str += f"{_fix_width(coef2str(coef), maxlcoef)} * {str(rightv)}"
                if rightv != listv_right[-1]:
                    table_str += " + "
            except (KeyError, ValueError) as _:
                table_str += f"{_fix_width('', len(str(rightv))+maxlcoef+3)}"
                if rightv != listv_right[-1]:
                    table_str += "   "
        table_str += "\n"
    table_str += "table ends<<<<<<<<<<<\n"
    logging.info(table_str)


class Table:
    """The coefficient matrix."""

    def __init__(self, const: str = "1"):
        self.const = const
        self.v2e: EqDict = {}  # the table {var: {vark : coefk}} var = sum coefk*vark
        self.add_free(const)

        # for why (linprog)
        self._c = np.zeros((0))
        self._v2i: dict[str, int] = {}  # v -> index of row in A.
        self.deps: list[Dependency] = []  # equal number of columns.
        self._mA = np.zeros((0, 0))

    def add_free(self, v: str) -> None:
        self.v2e[v] = {v: Coef(1)}

    def replace(self, v0: str, e0: SumCV) -> None:
        for v, e in list(self.v2e.items()):
            self.v2e[v] = replace(e, v0, e0)

    def modulo(self, e: SumCV) -> SumCV:
        return strip(e)

    def sumcv_from_list(self, vc: list[tuple[str, Coef]]) -> SumCV:
        return self.modulo(plus_all(*[{v: c} for v, c in vc]))

    def add_expr(self, vc: SumCV, dep: Optional["Dependency"]) -> bool:
        """
        Add a new equality (sum cv = 0), represented by the list of tuples vc=[(v, c), ..].
        If dep=None, Else return True iff the equality is not wrong inside AR
        Else return True iff the equality can already be deduced by the internal system
        """
        vc = self.modulo(vc)
        if len(vc) == 0:
            return False
        result = {}
        new_vars: list[tuple[str, Coef]] = []

        for v, c in vc.items():
            if v in self.v2e:
                result = plus(result, mult(self.v2e[v], c))
            else:
                new_vars.append((v, c))

        result = self.modulo(result)
        if dep is None:
            return len(result) == 0 and len(new_vars) == 0

        if new_vars == []:
            if len(result) == 0:
                return False
            result_recon = recon(result, self.const)
            if result_recon is None:
                if len(result) > 0:
                    raise Exception("Add conflicting results into AR")
                return False
            v, e = result_recon
            self.replace(v, e)

        else:
            dependent_v: tuple[str, Coef] = new_vars[0]
            for v, m in new_vars[1:]:
                self.add_free(v)
                result = plus(result, {v: m})

            v, m = dependent_v
            self.v2e[v] = mult(result, Coef(-1) / m)

        self._register(vc, dep)
        return True

    def _register(self, vc: SumCV, dep: "Dependency") -> None:
        """Register a new equality vc=[(v, c), ..] with traceback dependency dep."""
        vc = self.modulo(vc)
        if len(vc) == 0:
            return

        for v in vc:
            if v not in self._v2i:
                self._v2i[v] = len(self._v2i)

        (m, n), length = self._mA.shape, len(self._v2i)
        if length > m:
            self._mA = np.concatenate([self._mA, np.zeros([length - m, n])], 0)

        new_column = np.zeros((len(self._v2i), 2))  # N, 2
        for v, c in vc.items():
            new_column[self._v2i[v], 0] += c
            new_column[self._v2i[v], 1] -= c

        self._mA = np.concatenate((self._mA, new_column), 1)
        self._c = np.concatenate((self._c, np.array([1.0, -1.0])))
        self.deps += [dep]

    def why(self, e: SumCV) -> list["Dependency"]:
        """AR traceback == MILP."""
        # why expr == 0?
        # Solve min(c^Tx) s.t. A_eq * x = b_eq, x >= 0
        e = strip(e)
        if not e:
            return []

        b_eq = np.array([0] * len(self._v2i))
        for v, c in e.items():
            b_eq[self._v2i[v]] += c

        try:
            x = opt.linprog(c=self._c, A_eq=self._mA, b_eq=b_eq, method="highs")["x"]  # type: ignore
        except ValueError:
            x = opt.linprog(c=self._c, A_eq=self._mA, b_eq=b_eq)["x"]  # type: ignore

        deps: list[Dependency] = []
        for i, dep in enumerate(self.deps):
            if x[2 * i] > ATOM or x[2 * i + 1] > ATOM:
                if dep not in deps:
                    deps.append(dep)
        return deps

    def get_eq2(self, a: str, b: str) -> SumCV:
        """
        a = b
        """
        return self.sumcv_from_list([(a, Coef(1)), (b, Coef(-1))])

    def get_eq3(self, a: str, b: str, f: Any) -> SumCV:
        """
        a - b = f * constant
        """
        return self.sumcv_from_list(
            [(a, Coef(1)), (b, Coef(-1)), (self.const, -Coef(f))]
        )

    def get_eq4(self, a: str, b: str, c: str, d: str) -> SumCV:
        """
        a - b = c - d
        """
        return self.sumcv_from_list(
            [(a, Coef(1)), (b, Coef(-1)), (c, Coef(-1)), (d, Coef(1))]
        )


class RatioTable(Table):
    """Coefficient matrix A for log(distance)."""

    def __init__(self):
        super().__init__("1")
        self.one = self.const

    @classmethod
    def get_length(cls, p0: "Point", p1: "Point") -> str:
        if p0.name > p1.name:
            p0, p1 = p1, p0
        length = f"l({p0.name},{p1.name})"
        return length


class AngleTable(Table):
    """Coefficient matrix A for slope(direction)."""

    def __init__(self):
        super().__init__("pi")
        self.pi = self.const

    def modulo(self, e: SumCV) -> SumCV:
        e = strip(e)
        if self.pi in e:
            e[self.pi] = e[self.pi] % Coef(1)
        return strip(e)
