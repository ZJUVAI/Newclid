#!/usr/bin/env python3
"""
自动化几何题目求解脚本

用法: 
    python solve_problems.py --problems <题目文件路径> --rules <规则文件路径> [--timeout <超时秒数>] [--output <输出文件路径>]

示例:
    python solve_problems.py --problems problems.txt --rules rules.txt --timeout 3600 --output results.txt
"""

import time
from dataclasses import dataclass
from typing import List, Tuple, Optional
from newclid.api import DirectSolver

PROBLEMS_FILE_PATH="/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/c10s50_rules_rebuild.txt"
RULES_FILE_PATH="/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/candidate_rules/tmp_rules.txt"
OUTPUT_FILE_PATH="/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/tmp.txt"
TIMEOUT=3600

@dataclass
class Problem:
    """表示一道几何题目"""
    name:  str
    points: List[Tuple[str, float, float]]
    premises: List[Tuple[str, List[str]]]
    goal:  Tuple[str, List[str]]


def parse_point_line(line: str) -> Tuple[str, float, float]:
    """解析点坐标行，格式:  name: x,y"""
    name, coords = line.strip().split(":")
    x, y = coords.split(",")
    return (name. strip(), float(x), float(y))


def parse_predicate(line: str) -> Tuple[str, List[str]]: 
    """解析谓词行，格式: predicate_name arg1 arg2 .. ."""
    parts = line.strip().split()
    predicate_name = parts[0]
    args = parts[1:]
    return (predicate_name, args)


def parse_problems_file(filepath: str) -> List[Problem]:
    """解析题目文件，返回题目列表"""
    problems = []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 按空行分割不同题目
    problem_blocks = content.strip().split("\n\n")

    current_problem = None
    current_section = None

    for block in problem_blocks:
        lines = block.strip().split("\n")

        for line in lines: 
            line = line. strip()
            if not line:
                continue

            if line == "Rule Name:":
                # 保存上一个题目
                if current_problem is not None:
                    problems.append(current_problem)
                current_problem = {
                    'name': '',
                    'points': [],
                    'premises': [],
                    'goal':  None
                }
                current_section = 'name'
            elif line == "Points:":
                current_section = 'points'
            elif line == "Premises:": 
                current_section = 'premises'
            elif line == "Goal:": 
                current_section = 'goal'
            elif current_problem is not None: 
                if current_section == 'name':
                    current_problem['name'] = line
                elif current_section == 'points': 
                    current_problem['points'].append(parse_point_line(line))
                elif current_section == 'premises': 
                    current_problem['premises'].append(parse_predicate(line))
                elif current_section == 'goal': 
                    current_problem['goal'] = parse_predicate(line)

    # 保存最后一个题目
    if current_problem is not None and current_problem['goal'] is not None: 
        problems.append(current_problem)

    # 转换为 Problem 对象
    return [
        Problem(
            name=p['name'],
            points=p['points'],
            premises=p['premises'],
            goal=p['goal']
        )
        for p in problems
    ]


def solve_problem(problem: Problem, rules_path: str, timeout:  int = 3600) -> dict:
    """求解单个题目，返回结果字典"""
    result = {
        'name': problem.name,
        'solved': False,
        'runtime': 0.0,
        'error': None
    }

    try:
        solver = DirectSolver(
            points=problem.points,
            premises=problem.premises,
            goal=problem.goal,
            problem_name=problem. name,
            rules_path=rules_path,
        )

        start_time = time.time()
        solved = solver.run(timeout=timeout)
        end_time = time. time()

        result['solved'] = solved
        result['runtime'] = solver.run_infos. get('runtime', end_time - start_time)

        if solved:
            solver.write_proof_steps()

    except Exception as e:
        result['error'] = str(e)

    return result


def main():
    # 解析题目文件
    print("=" * 60)
    print("正在解析题目文件...")
    print("=" * 60)

    problems = parse_problems_file(PROBLEMS_FILE_PATH)
    print(f"共解析到 {len(problems)} 道题目\n")

    # 逐题求解
    results = []
    solved_count = 0
    failed_count = 0
    error_count = 0
    total_time = 0.0

    for i, problem in enumerate(problems, 1):
        print("-" * 60)
        print(f"[{i}/{len(problems)}] 正在求解: {problem.name}")
        print("-" * 60)

        result = solve_problem(problem, RULES_FILE_PATH, TIMEOUT)
        results.append(result)

        total_time += result['runtime']

        if result['error']:
            error_count += 1
            status = f"❌ 错误: {result['error']}"
        elif result['solved']: 
            solved_count += 1
            status = "✅ 成功"
        else:
            failed_count += 1
            status = "❌ 失败"

        print(f"结果: {status}")
        print(f"用时: {result['runtime']:.4f} 秒\n")

    # 打印统计结果
    print("=" * 60)
    print("求解统计")
    print("=" * 60)
    print(f"总题目数: {len(problems)}")
    print(f"成功求解:  {solved_count} ({100*solved_count/len(problems):.1f}%)")
    print(f"求解失败: {failed_count} ({100*failed_count/len(problems):.1f}%)")
    print(f"发生错误: {error_count} ({100*error_count/len(problems):.1f}%)")
    print(f"总用时:  {total_time:.4f} 秒")
    print(f"平均用时: {total_time/len(problems):.4f} 秒/题")
    print("=" * 60)

    # 输出到文件（如果指定）
    with open(OUTPUT_FILE_PATH, 'w', encoding='utf-8') as f:
        f.write("求解结果报告\n")
        f.write("=" * 60 + "\n\n")

        for result in results: 
            if result['error']:
                status = f"错误: {result['error']}"
            elif result['solved']: 
                status = "成功"
            else:
                status = "失败"

            f.write(f"题目: {result['name']}\n")
            f.write(f"结果: {status}\n")
            f.write(f"用时: {result['runtime']:.4f} 秒\n")
            f.write("-" * 40 + "\n")

        f.write("\n统计\n")
        f.write("=" * 60 + "\n")
        f.write(f"总题目数: {len(problems)}\n")
        f.write(f"成功求解:  {solved_count} ({100*solved_count/len(problems):.1f}%)\n")
        f.write(f"求解失败:  {failed_count} ({100*failed_count/len(problems):.1f}%)\n")
        f.write(f"发生错误: {error_count} ({100*error_count/len(problems):.1f}%)\n")
        f.write(f"总用时: {total_time:.4f} 秒\n")
        f.write(f"平均用时:  {total_time/len(problems):.4f} 秒/题\n")

        print(f"\n结果已保存到: {OUTPUT_FILE_PATH}")


if __name__ == "__main__":
    main()