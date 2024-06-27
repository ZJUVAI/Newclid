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
