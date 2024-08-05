from fractions import Fraction
from typing import Any, Optional, TypeVar, Union

from geosolver.numerical import close_enough


class InfQuotientError(Exception):
    pass


# maximum denominator for a fraction.
MAX_DENOMINATOR = 1000000

T = TypeVar("T")


def notNone(x: Optional[T]) -> T:
    assert x is not None
    return x


def get_quotient(v: Any) -> Fraction:
    v = float(v)
    n = v
    d = 1
    while not close_enough(n, round(n)):
        d += 1
        n += v
        if d > MAX_DENOMINATOR:
            e = InfQuotientError(v)
            raise e

    n = int(round(n))
    return Fraction(n, d)


def atomize(s: str, split_by: Optional[str] = None) -> tuple[str, ...]:
    words = s.split(split_by)
    return tuple(word.strip() for word in words)


def str_to_fraction(s: str) -> Fraction:
    if "pi/" in s:
        ns, ds = s.split("pi/")
        n, d = int(ns), int(ds)
        if d < 0:
            n, d = -n, -d
        return Fraction(n % d, d)
    elif "o" in s:
        n = int(s[:-1])
        d = 180
        return Fraction(n % d, d)
    elif "/" in s:
        ns, ds = s.split("/")
        n, d = int(ns), int(ds)
        return Fraction(n, d)
    else:
        n = int(s)
        d = 1
        return Fraction(n, d)


def fraction_to_len(f: Fraction):
    return f"{f.numerator}/{f.denominator}"


def fraction_to_ratio(f: Fraction):
    return f"{f.numerator}/{f.denominator}"


def fraction_to_angle(f: Fraction):
    n, d = f.numerator, f.denominator
    return f"{n%d}pi/{d}"


def reshape(to_reshape: Union[list[T], tuple[T, ...]], n: int) -> list[tuple[T, ...]]:
    assert len(to_reshape) % n == 0
    columns: list[list[T]] = [[] for _ in range(n)]
    for i, x in enumerate(to_reshape):
        columns[i % n].append(x)
    return [tuple(columns[k][i] for k in range(n)) for i in range(len(columns[0]))]
