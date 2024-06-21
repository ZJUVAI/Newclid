def pretty_angle(a: str, b: str, c: str, d: str) -> str:
    if b in (c, d):
        a, b = b, a
    if a == d:
        c, d = d, c

    if a == c:
        return f"\u2220{b}{a}{d}"
    return f"\u2220({a}{b}-{c}{d})"
