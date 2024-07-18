ATOM = 1e-9


def close_enough(
    a: float, b: float, rel_tol: float = 0.001, abs_tol: float = 4 * ATOM
) -> bool:
    return abs(a - b) < abs_tol or abs(a - b) / max(abs(a), abs(b)) < rel_tol


def sign(a: float) -> int:
    return 0 if close_enough(a, 0) else (1 if a > 0 else -1)
