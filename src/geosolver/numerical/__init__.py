ATOM = 1e-12


def close_enough(a: float, b: float, tol: float = 1e-12) -> bool:
    return abs(a - b) < tol
