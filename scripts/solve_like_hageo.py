#!/usr/bin/env python3
"""
带辅助点随机采样的题目求解脚本

通过随机采样候选辅助点来增强题目，直到求解成功或达到最大尝试次数。

用法:
    python scripts/solve_like_hageo.py [--max-attempts 3] [--n-aux 6] [--timeout 600]

示例:
    python scripts/solve_like_hageo.py --max-attempts 3  # 小样本快速测试
    python scripts/solve_like_hageo.py                   # 完整运行
"""

import argparse
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from newclid.api import CSolver, DirectSolver

# ============== 硬编码默认路径 ==============
DEFAULT_PROBLEMS_PATH = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/hageo_224_remain_rebuild.txt"
DEFAULT_AUX_POINTS_PATH = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/hageo_224_remain_rebuild_aux_points.txt"
DEFAULT_RULES_PATH = "/c23474/home/duzhengtong/Discovery-GenesisGeo/src/newclid/default_configs/rules.txt"
DEFAULT_OUTPUT_PATH = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/solve_results/hageo_224_remain_like_hageo_solve_results.json"
DEFAULT_SUMMARY_PATH = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/solve_results/hageo_224_remain_like_hageo_summary.txt"

# ============== 默认参数 ==============
DEFAULT_N_AUX = 2        # 每次采样的辅助点数量
DEFAULT_MAX_ATTEMPTS = 15  # 每道题的最大尝试次数
DEFAULT_TIMEOUT = 600    # 单次求解超时秒数
DEFAULT_SEED = 42        # 随机种子


@dataclass
class Problem:
    """表示一道几何题目"""
    name: str
    points: List[Tuple[str, float, float]]
    premises: List[Tuple[str, List[str]]]
    goal: Tuple[str, List[str]]


@dataclass
class AuxPoint:
    """表示一个候选辅助点"""
    temp_name: str  # 临时名称，如 aux_int_0
    x: float
    y: float
    predicates: List[str]  # 如 ["coll aux_int_0 a b", "coll aux_int_0 c d"]


@dataclass
class SolveResult:
    """求解结果"""
    problem_name: str
    solved: bool
    attempts: int = 0
    runtime: float = 0.0
    aux_points_used: List[Dict] = field(default_factory=list)
    error: Optional[str] = None


def parse_point_line(line: str) -> Tuple[str, float, float]:
    """解析点坐标行，格式: name:x,y"""
    name, coords = line.strip().split(":")
    x, y = coords.split(",")
    return (name.strip(), float(x), float(y))


def parse_predicate(line: str) -> Tuple[str, List[str]]:
    """解析谓词行，格式: predicate_name arg1 arg2 ..."""
    parts = line.strip().split()
    predicate_name = parts[0]
    args = parts[1:]
    return (predicate_name, args)


def parse_problems_file(filepath: str) -> List[Problem]:
    """解析题目文件，返回题目列表
    
    格式：每个题目以 "Problem Name:" 开始，依次是 Points:, Premises:, Goal:
    """
    problems = []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 按空行分割不同题目块
    problem_blocks = content.strip().split("\n\n")

    current_problem = None
    current_section = None

    for block in problem_blocks:
        lines = block.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line == "Problem Name:":
                # 保存上一个题目
                if current_problem is not None and current_problem['goal'] is not None:
                    problems.append(current_problem)
                current_problem = {
                    'name': '',
                    'points': [],
                    'premises': [],
                    'goal': None
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


def parse_aux_points_file(filepath: str) -> Dict[str, List[AuxPoint]]:
    """解析辅助点文件，返回按题目名索引的辅助点字典
    
    格式：
    Problem Name:
    <problem_name>
    <aux_point_name>
    (<x>, <y>)
    <predicate1>, <predicate2>
    ...
    
    以 # 开头的行为无效/重合的辅助点，跳过
    """
    aux_points_map: Dict[str, List[AuxPoint]] = {}

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    current_problem_name = None

    while i < len(lines):
        line = lines[i].strip()

        # 跳过空行
        if not line:
            i += 1
            continue

        # 检测新题目
        if line == "Problem Name:":
            i += 1
            if i < len(lines):
                current_problem_name = lines[i].strip()
                if current_problem_name not in aux_points_map:
                    aux_points_map[current_problem_name] = []
            i += 1
            continue

        # 跳过以 # 开头的无效辅助点（整块跳过）
        if line.startswith("#"):
            i += 1
            # 跳过后续可能的注释行（坐标和predicate）
            while i < len(lines) and lines[i].strip().startswith("#"):
                i += 1
            continue

        # 解析辅助点
        # 第一行：辅助点名称
        if line.startswith("aux_"):
            aux_name = line
            i += 1

            # 第二行：坐标 (x, y)
            if i < len(lines):
                coord_line = lines[i].strip()
                # 解析 (x, y) 格式
                match = re.match(r'\(([^,]+),\s*([^)]+)\)', coord_line)
                if match:
                    x = float(match.group(1))
                    y = float(match.group(2))
                else:
                    # 格式不对，跳过
                    i += 1
                    continue
            else:
                break
            i += 1

            # 第三行：predicates，用 ", " 分隔
            if i < len(lines):
                pred_line = lines[i].strip()
                # 可能是下一个辅助点或题目，需要检查
                if pred_line.startswith("aux_") or pred_line == "Problem Name:" or pred_line.startswith("#"):
                    # 没有 predicate 行，这种情况不应该发生
                    predicates = []
                else:
                    predicates = [p.strip() for p in pred_line.split(", ") if p.strip()]
                    i += 1
            else:
                predicates = []

            if current_problem_name is not None:
                aux_point = AuxPoint(
                    temp_name=aux_name,
                    x=x,
                    y=y,
                    predicates=predicates
                )
                aux_points_map[current_problem_name].append(aux_point)
        else:
            i += 1

    return aux_points_map


def generate_new_point_names(existing_names: List[str], count: int) -> List[str]:
    """生成新的点名，避免与已有点名冲突
    
    策略：优先使用未用的单字母 (a-z)，用尽后使用 a1, b1, ..., z1, a2, ...
    """
    existing_set = set(existing_names)
    new_names = []

    # 首先尝试单字母
    for c in 'abcdefghijklmnopqrstuvwxyz':
        if c not in existing_set:
            new_names.append(c)
            existing_set.add(c)
            if len(new_names) >= count:
                return new_names

    # 然后尝试带数字的名称
    suffix = 1
    while len(new_names) < count:
        for c in 'abcdefghijklmnopqrstuvwxyz':
            name = f"{c}{suffix}"
            if name not in existing_set:
                new_names.append(name)
                existing_set.add(name)
                if len(new_names) >= count:
                    return new_names
        suffix += 1

    return new_names


def rename_predicate(predicate: str, old_name: str, new_name: str) -> str:
    """将 predicate 中的临时点名替换为新名称
    
    例如：coll aux_int_0 a b -> coll x a b (当 old_name=aux_int_0, new_name=x)
    """
    parts = predicate.split()
    new_parts = [new_name if part == old_name else part for part in parts]
    return " ".join(new_parts)


def rename_predicate_as_tuple(predicate: str, old_name: str, new_name: str) -> Tuple[str, List[str]]:
    """将 predicate 中的临时点名替换为新名称，直接返回解析后的元组
    
    例如：coll aux_int_0 a b -> ("coll", ["x", "a", "b"]) (当 old_name=aux_int_0, new_name=x)
    避免了先拼接成字符串再解析的开销
    """
    parts = predicate.split()
    new_parts = [new_name if part == old_name else part for part in parts]
    return (new_parts[0], new_parts[1:])


def augment_problem(
    problem: Problem,
    sampled_aux: List[AuxPoint],
    new_names: List[str]
) -> Problem:
    """用采样的辅助点增强题目
    
    返回一个新的 Problem 对象，包含原始题目的所有信息加上辅助点
    """
    # 复制原始数据
    new_points = list(problem.points)
    new_premises = list(problem.premises)

    for aux_point, new_name in zip(sampled_aux, new_names):
        # 添加点坐标
        new_points.append((new_name, aux_point.x, aux_point.y))

        # 添加 predicates，替换临时名称，直接获得解析后的元组
        for pred in aux_point.predicates:
            new_premises.append(rename_predicate_as_tuple(pred, aux_point.temp_name, new_name))

    return Problem(
        name=problem.name,
        points=new_points,
        premises=new_premises,
        goal=problem.goal
    )


def solve_problem(problem: Problem, rules_path: str, timeout: int) -> Tuple[bool, float, Optional[str]]:
    """使用 DirectSolver 求解题目
    
    返回：(是否成功, 运行时间, 错误信息)
    """

    try:
        Dsolver = DirectSolver(
            points=problem.points,
            premises=problem.premises,
            goal=problem.goal,
            problem_name=problem.name,
            rules_path=Path(rules_path),
        )
        
        solver = CSolver(
            solver=Dsolver.solver,
            points=problem.points,
            premises=problem.premises,
            goals=[problem.goal],
            problem_name=problem.name,
        )
        
        start_time = time.time()
        solved = solver.run()
        end_time = time.time()

        runtime = solver.solver.run_infos.get('runtime', end_time - start_time)
        return (solved, runtime, None)

    except Exception as e:
        return (False, 0.0, str(e))


def load_existing_results(output_path: str) -> Dict[str, SolveResult]:
    """加载已有的求解结果，用于断点续跑"""
    results = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    if item.get('solved', False):
                        # 只加载已成功求解的题目
                        result = SolveResult(
                            problem_name=item['problem_name'],
                            solved=item['solved'],
                            attempts=item.get('attempts', 0),
                            runtime=item.get('runtime', 0.0),
                            aux_points_used=item.get('aux_points_used', []),
                            error=item.get('error')
                        )
                        results[item['problem_name']] = result
        except Exception as e:
            print(f"[警告] 无法加载已有结果文件: {e}")
    return results


def save_results(results: List[SolveResult], output_path: str):
    """保存求解结果到 JSON 文件"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data = []
    for r in results:
        data.append({
            'problem_name': r.problem_name,
            'solved': r.solved,
            'attempts': r.attempts,
            'runtime': r.runtime,
            'aux_points_used': r.aux_points_used,
            'error': r.error
        })

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_summary(results: List[SolveResult], summary_path: str, total_time: float):
    """保存汇总统计到文本文件"""
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    solved_count = sum(1 for r in results if r.solved)
    failed_count = sum(1 for r in results if not r.solved and r.error is None)
    error_count = sum(1 for r in results if r.error is not None)
    total_count = len(results)

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("HAGeo 式辅助点采样求解统计\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"总题目数: {total_count}\n")
        f.write(f"成功求解: {solved_count} ({100*solved_count/total_count:.1f}%)\n")
        f.write(f"求解失败: {failed_count} ({100*failed_count/total_count:.1f}%)\n")
        f.write(f"发生错误: {error_count} ({100*error_count/total_count:.1f}%)\n")
        f.write(f"总用时: {total_time:.2f} 秒\n")
        f.write(f"平均用时: {total_time/total_count:.2f} 秒/题\n\n")

        f.write("-" * 60 + "\n")
        f.write("详细结果\n")
        f.write("-" * 60 + "\n\n")

        for r in results:
            status = "✓" if r.solved else ("✗ ERROR" if r.error else "✗")
            f.write(f"[{status}] {r.problem_name}\n")
            f.write(f"    尝试次数: {r.attempts}\n")
            f.write(f"    运行时间: {r.runtime:.2f}s\n")
            if r.solved and r.aux_points_used:
                f.write(f"    使用辅助点: {len(r.aux_points_used)} 个\n")
            if r.error:
                f.write(f"    错误: {r.error}\n")
            f.write("\n")


def main():
    parser = argparse.ArgumentParser(
        description="带辅助点随机采样的题目求解脚本"
    )
    parser.add_argument(
        "--problems",
        type=str,
        default=DEFAULT_PROBLEMS_PATH,
        help="题目文件路径"
    )
    parser.add_argument(
        "--aux-points",
        type=str,
        default=DEFAULT_AUX_POINTS_PATH,
        help="辅助点文件路径"
    )
    parser.add_argument(
        "--rules",
        type=str,
        default=DEFAULT_RULES_PATH,
        help="规则文件路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_PATH,
        help="输出结果文件路径"
    )
    parser.add_argument(
        "--summary",
        type=str,
        default=DEFAULT_SUMMARY_PATH,
        help="汇总统计文件路径"
    )
    parser.add_argument(
        "--n-aux",
        type=int,
        default=DEFAULT_N_AUX,
        help="每次采样的辅助点数量"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help="每道题的最大尝试次数"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="单次求解超时秒数"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="随机种子"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从已有结果断点续跑"
    )

    args = parser.parse_args()

    # 设置随机种子
    random.seed(args.seed)

    print("=" * 60)
    print("HAGeo 式辅助点采样求解器")
    print("=" * 60)
    print(f"题目文件: {args.problems}")
    print(f"辅助点文件: {args.aux_points}")
    print(f"规则文件: {args.rules}")
    print(f"每次采样辅助点数: {args.n_aux}")
    print(f"最大尝试次数: {args.max_attempts}")
    print(f"单次超时: {args.timeout}s")
    print(f"随机种子: {args.seed}")
    print("=" * 60 + "\n")

    # 解析题目
    print("正在加载题目...")
    problems = parse_problems_file(args.problems)
    print(f"已加载 {len(problems)} 道题目\n")

    # 解析辅助点
    print("正在加载辅助点...")
    aux_points_map = parse_aux_points_file(args.aux_points)
    total_aux = sum(len(v) for v in aux_points_map.values())
    print(f"已加载 {len(aux_points_map)} 道题目的辅助点，共 {total_aux} 个候选辅助点\n")

    # 加载已有结果（断点续跑）
    existing_results = {}
    if args.resume:
        existing_results = load_existing_results(args.output)
        print(f"断点续跑：已有 {len(existing_results)} 道题目成功求解，将跳过\n")

    # 求解
    results: List[SolveResult] = []
    total_start_time = time.time()

    for idx, problem in enumerate(problems, 1):
        print("-" * 60)
        print(f"[{idx}/{len(problems)}] {problem.name}")
        print("-" * 60)

        # 检查是否已成功求解
        if problem.name in existing_results:
            print("已成功求解，跳过\n")
            results.append(existing_results[problem.name])
            continue

        # 获取该题目的候选辅助点
        candidates = aux_points_map.get(problem.name, [])
        if not candidates:
            print(f"警告：没有找到辅助点候选，尝试直接求解\n")
            # 尝试直接求解（无辅助点）
            solved, runtime, error = solve_problem(problem, args.rules, args.timeout)
            result = SolveResult(
                problem_name=problem.name,
                solved=solved,
                attempts=1,
                runtime=runtime,
                aux_points_used=[],
                error=error
            )
            results.append(result)
            status = "✓ 成功" if solved else ("✗ 错误: " + str(error) if error else "✗ 失败")
            print(f"结果: {status}")
            print(f"用时: {runtime:.2f}s\n")
            continue

        print(f"候选辅助点: {len(candidates)} 个")

        # 获取已有点名，预生成足够的新点名（只需计算一次）
        existing_point_names = [p[0] for p in problem.points]
        n_sample = min(args.n_aux, len(candidates))
        precomputed_new_names = generate_new_point_names(existing_point_names, n_sample)

        result = SolveResult(
            problem_name=problem.name,
            solved=False,
            attempts=0,
            runtime=0.0,
            aux_points_used=[],
            error=None
        )

        total_runtime = 0.0
        solved = False

        for attempt in range(args.max_attempts):
            result.attempts = attempt + 1

            # 随机采样辅助点
            sampled_aux = random.sample(candidates, n_sample)

            # 使用预生成的点名
            new_names = precomputed_new_names

            # 构建增强后的题目
            augmented = augment_problem(problem, sampled_aux, new_names)

            # 求解
            try:
                is_solved, runtime, error = solve_problem(augmented, args.rules, args.timeout)
                total_runtime += runtime

                if is_solved:
                    solved = True
                    result.solved = True
                    result.runtime = total_runtime
                    result.aux_points_used = [
                        {
                            "name": new_name,
                            "coords": [aux.x, aux.y],
                            "predicates": [rename_predicate(p, aux.temp_name, new_name) for p in aux.predicates]
                        }
                        for aux, new_name in zip(sampled_aux, new_names)
                    ]
                    print(f"✓ 第 {attempt + 1} 次尝试成功！用时: {total_runtime:.2f}s")
                    print(f"  使用辅助点: {new_names}")
                    break

                if error:
                    # 记录错误但继续尝试
                    pass

            except Exception as e:
                result.error = str(e)

            # 每 10 次打印进度
            if (attempt + 1) % 10 == 0:
                print(f"  已尝试 {attempt + 1}/{args.max_attempts} 次...")

        if not solved:
            result.runtime = total_runtime
            print(f"✗ {args.max_attempts} 次尝试后仍未成功，用时: {total_runtime:.2f}s")

        results.append(result)
        print()

        # 定期保存结果
        if idx % 10 == 0:
            save_results(results, args.output)
            print(f"[自动保存] 已保存 {len(results)} 道题目的结果\n")

    total_time = time.time() - total_start_time

    # 最终保存
    save_results(results, args.output)
    save_summary(results, args.summary, total_time)

    # 打印统计
    print("=" * 60)
    print("求解统计")
    print("=" * 60)
    solved_count = sum(1 for r in results if r.solved)
    print(f"总题目数: {len(results)}")
    print(f"成功求解: {solved_count} ({100*solved_count/len(results):.1f}%)")
    print(f"总用时: {total_time:.2f} 秒")
    print(f"结果已保存到: {args.output}")
    print(f"统计已保存到: {args.summary}")
    print("=" * 60)


if __name__ == "__main__":
    main()
