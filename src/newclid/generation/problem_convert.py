# src/newclid/generation/problem_convert.py

import argparse
import json
import os
from typing import Iterable, List, Optional


def strip_coordinates(configuration: str) -> str:
    """
    去掉 configuration 字符串中所有点的坐标，只保留点名与构造关系。

    输入示例：
        "a@0.1_0.2 b@0.3_0.4 = eq_quadrangle a b c d; e@0.5_0.6 = on_circle e b c"

    输出示例：
        "a b = eq_quadrangle a b c d; e = on_circle e b c"

    规则：
    - 按 ';' 切分成若干段，每段形如 "<lhs> = <rhs>" 或其它特殊片段；
    - 对于含 '=' 的片段：
        - lhs 按空格切成 token；
        - 每个 token 如 "a@x_y"，保留 '@' 之前的部分作为点名；
        - 没有 '@' 的 token 原样保留；
        - 再拼成 "lhs' = rhs"；
    - 不含 '=' 的片段原样保留；
    - 最终各段用 '; ' 拼接。
    """
    if not configuration:
        return ""

    segments = [seg.strip() for seg in configuration.split(";") if seg.strip()]
    new_segments: List[str] = []

    for seg in segments:
        if "=" not in seg:
            # 无法识别的片段保持原样，保证鲁棒性
            new_segments.append(seg)
            continue

        lhs, rhs = seg.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()

        # lhs 可能包含多个点
        tokens = [tok for tok in lhs.split() if tok]
        new_points: List[str] = []
        for tok in tokens:
            if "@" in tok:
                # 形如 "a@x_y" 或 "a@x_y,"，去掉坐标部分和尾随标点
                name = tok.split("@", 1)[0]
                name = name.strip()
                if name:
                    new_points.append(name)
            else:
                # 已经是纯点名，直接保留
                new_points.append(tok)

        new_lhs = " ".join(new_points)
        if new_lhs:
            new_segments.append(f"{new_lhs} = {rhs}")
        else:
            # 极端情况：lhs 全部被清空时，保守起见保留原 seg
            new_segments.append(seg)

    return "; ".join(new_segments)


def iter_jsonl_lines(path: str) -> Iterable[str]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            # 保留原始行以便 json 解析
            if line.strip():
                yield line


def convert_file(
    input_path: str,
    output_path: str,
    skip_empty: bool = True,
) -> None:
    """
    将 configuration_clauses*.jsonl 转换为 txt 题目文件。

    - input_path: 源 jsonl，每行一个 JSON 对象，包含至少:
        - "configuration": str
        - "unsolved_goals": list[{"goal_str": str, "predicate": str}] (可能为空/缺失)
    - output_path: 输出 txt，每题两行：id 行 + problem 行。
    - skip_empty: 当 unsolved_goals 为空/缺失时是否跳过该行。
    """
    total_lines = 0
    used_lines = 0
    total_problems = 0

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fout:
        for line_idx, line in enumerate(iter_jsonl_lines(input_path), start=1):
            total_lines += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # 无法解析的行直接跳过
                continue

            configuration = obj.get("configuration", "")
            if not configuration:
                # 没有 configuration 就没有意义，跳过
                continue

            unsolved_goals = obj.get("unsolved_goals")
            if not isinstance(unsolved_goals, list) or not unsolved_goals:
                if skip_empty:
                    continue

            config_no_coord = strip_coordinates(configuration)
            if not config_no_coord:
                # 极端情况：去坐标后为空，跳过
                continue

            goals_written_for_line = 0
            for goal_idx, goal in enumerate(unsolved_goals or []):
                if not isinstance(goal, dict):
                    continue
                goal_str = goal.get("goal_str")
                if not goal_str or not isinstance(goal_str, str):
                    continue

                problem_str = f"{config_no_coord} ? {goal_str}"
                problem_id = f"{line_idx}_{goal_idx}"

                # 写入两行：id 行 + problem 行
                fout.write(problem_id + "\n")
                fout.write(problem_str.strip() + "\n")

                total_problems += 1
                goals_written_for_line += 1

            if goals_written_for_line > 0:
                used_lines += 1

    # 简要统计信息，便于在命令行查看
    print(
        f"[problem_convert] input_lines={total_lines}, "
        f"lines_with_goals={used_lines}, problems_written={total_problems}"
    )
    print(f"[problem_convert] output saved to: {output_path}")


def _default_output_path(input_path: str) -> str:
    """
    根据输入路径生成默认输出路径：
    xxx/configuration_clauses{n}_samples{N}.jsonl
    -> xxx/problems/configuration_clauses{n}_samples{N}_problems.txt
    """
    base_dir = os.path.dirname(input_path)
    base_name = os.path.basename(input_path)

    name_without_ext = base_name
    if name_without_ext.endswith(".jsonl"):
        name_without_ext = name_without_ext[: -len(".jsonl")]
    elif name_without_ext.endswith(".json"):
        name_without_ext = name_without_ext[: -len(".json")]

    problems_dir = os.path.join(base_dir, "problems")
    os.makedirs(problems_dir, exist_ok=True)

    out_name = f"{name_without_ext}_problems.txt"
    return os.path.join(problems_dir, out_name)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert configuration_clauses*.jsonl into txt problems:\n"
            "each unsolved goal becomes one problem (two lines: id + problem)."
        )
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to configuration_clauses{n}_samples{N}.jsonl",
    )
    parser.add_argument(
        "--output",
        "-o",
        help=(
            "Output txt path; if omitted, generated as "
            "datasets/problems/configuration_clauses{n}_samples{N}_problems.txt"
        ),
    )
    parser.add_argument(
        "--no-skip-empty",
        action="store_true",
        help="Do not skip lines with empty or missing unsolved_goals.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    input_path = args.input
    output_path = args.output

    if output_path is None:
        output_path = _default_output_path(input_path)

    skip_empty = not args.no_skip_empty
    convert_file(input_path=input_path, output_path=output_path, skip_empty=skip_empty)


if __name__ == "__main__":
    main()