ATOM = 1e-12
NLOGATOM = 12


def close_enough(
    a: float, b: float, rel_tol: float = 0.001, abs_tol: float = 3 * ATOM
) -> bool:
    return abs(a - b) / abs(a) < rel_tol or abs(a - b) < abs_tol
