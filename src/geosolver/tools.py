from typing import Optional, TypeVar


def _gcd(x: int, y: int) -> int:
    while y:
        x, y = y, x % y
    return x


def simplify(n: int, d: int) -> tuple[int, int]:
    g = _gcd(n, d)
    n //= g
    d //= g
    if d < 0:
        n, d = -n, -d
    return n, d


def atomize(s: str, split_by: Optional[str] = None) -> tuple[str, ...]:
    words = s.split(split_by)
    return tuple(word.strip() for word in words)


def str_to_nd(s: str) -> tuple[int, int]:
    if "pi/" in s:
        ns, ds = s.split("pi/")
        n, d = simplify(int(ns), int(ds))
        return n % d, d
    elif "o" in s:
        n = int(s[:-1])
        d = 180
        n, d = simplify(n, d)
        return n % d, d
    elif "/" in s:
        ns, ds = s.split("/")
        n, d = simplify(int(ns), int(ds))
        return n, d
    else:
        n = int(s)
        d = 1
        return simplify(n, d)


def nd_to_len(n: int, d: int):
    n, d = simplify(n, d)
    return f"{n}/{d}"


def nd_to_ratio(n: int, d: int):
    n, d = simplify(n, d)
    return f"{n}/{d}"


def nd_to_angle(n: int, d: int):
    n, d = simplify(n, d)
    return f"{n%d}pi/{d}"


def parse_len(s: str):
    return nd_to_len(*str_to_nd(s))


def parse_ratio(s: str):
    return nd_to_ratio(*str_to_nd(s))


def parse_angle(s: str):
    return nd_to_angle(*str_to_nd(s))


T = TypeVar("T")


def reshape(to_reshape: list[T] | tuple[T, ...], n: int) -> list[tuple[T, ...]]:
    assert len(to_reshape) % n == 0
    columns: list[list[T]] = [[] for _ in range(n)]
    for i, x in enumerate(to_reshape):
        columns[i % n].append(x)
    return [tuple(columns[k][i] for k in range(n)) for i in range(len(columns[0]))]
