#!/usr/bin/env python3
"""Generate fl_statement for debugging (前半部分数据生成)"""
import sys
import signal
from contextlib import contextmanager

sys.path.insert(0, '/root/dubhe/GenesisDiscovery/src')

from newclid.generation.clause_generation import CompoundClauseGen
from newclid.generation.HA import enhance_text_with_potential_points


class TimeoutError(Exception):
    pass


@contextmanager
def time_limit(seconds):
    def handler(signum, frame):
        raise TimeoutError("Timed out")
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


def generate_fl_statement(seed=42, n_clauses=6, add_auxiliary=True, prune=True, remove_coords=False):
    """Generate a single fl_statement"""
    clauses_generator = CompoundClauseGen(seed=seed)

    try:
        with time_limit(10):
            fl_statement = clauses_generator.generate(
                length=n_clauses,
                add_auxiliary=add_auxiliary,
                prune=prune,
                remove_coords=remove_coords,
            )
    except TimeoutError:
        print("Generation timed out")
        return None

    # Enhance with potential points
    fl_statement = enhance_text_with_potential_points(
        fl_statement, clauses_generator.point_generator, allow_coincident_points = False
    )

    return fl_statement


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate fl_statement for debugging")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n_clauses", type=int, default=6)
    parser.add_argument("--n_samples", type=int, default=500, help="Number of samples to generate")
    args = parser.parse_args()

    print(f"Generating {args.n_samples} fl_statements with seed={args.seed}, n_clauses={args.n_clauses}\n")

    import re

    TOLERANCE = 1e-6

    for i in range(args.n_samples):
        seed = args.seed + i
        fl_statement = generate_fl_statement(seed=seed, n_clauses=args.n_clauses)

        if not fl_statement:
            continue

        # 提取所有 name@x_y 坐标段
        # 格式示例: a@1.517530938298561_0.27084057038014986
        matches = re.findall(r'(\w+)@(-?[\d.]+)_(-?[\d.]+)', fl_statement)
        if not matches:
            continue

        # 检查是否有重复坐标（在一定误差下）
        points = [(name, float(x), float(y)) for name, x, y in matches]
        duplicate_found = False
        for j in range(len(points)):
            for k in range(j + 1, len(points)):
                n1, x1, y1 = points[j]
                n2, x2, y2 = points[k]
                if abs(x1 - x2) < TOLERANCE and abs(y1 - y2) < TOLERANCE:
                    print(f"[Seed={seed}] 发现重复坐标: {n1}=({x1}, {y1}) == {n2}=({x2}, {y2})")
                    print(fl_statement)
                    duplicate_found = True
                    break
            if duplicate_found:
                break

        if duplicate_found:
            break
    else:
        print(f"在 {args.n_samples} 个样本中未发现重复坐标")
