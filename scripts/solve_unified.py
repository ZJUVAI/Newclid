#!/usr/bin/env python3
"""
统一的几何题目求解脚本

支持多种求解引擎（CSolver-Construction, CSolver-Direct, AG2）和多种输入格式（construction, rebuild）。
通过随机采样候选辅助点来增强题目，直到求解成功或达到最大尝试次数。

用法:
    python scripts/solve_like_hageo_from_constructions.py [--solve-mode csolver-construction] [--max-attempts 3]

示例:
    python scripts/solve_like_hageo_from_constructions.py --solve-mode csolver-construction --max-attempts 3
    python scripts/solve_like_hageo_from_constructions.py --solve-mode csolver-direct --max-attempts 3
    python scripts/solve_like_hageo_from_constructions.py --solve-mode ag2 --max-attempts 3
"""

import argparse
import itertools
import json
import os
import random
import re
import sys
import time
from math import comb

import ray
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from newclid.api import CSolver, DirectSolver
from newclid import GeometricSolverBuilder, GeometricSolver
from newclid.ag2.ddar import DDAR
from newclid.ag2.parse import AGProblem

# ============== 硬编码默认路径 ==============
# Construction 格式路径
# CONSTRUCTION_PROBLEMS_PATH = "/root/GenesisGeo-main/benchmarks/imo_ag_30.txt"
# CONSTRUCTION_PROBLEMS_PATH = "/root/GenesisGeo-main/benchmarks/imo_102_requires_aux.txt"
CONSTRUCTION_PROBLEMS_PATH = "/root/GenesisGeo-main/benchmarks/hageo_409.txt"
# Rebuild 格式路径
# REBUILD_PROBLEMS_PATH = "/root/GenesisGeo-main/evaluation_dataset/rebuild_problems/imo_30_rebuild.txt"
# AUX_POINTS_PATH = "/root/GenesisGeo-main/evaluation_dataset/rebuild_problems/imo_30_rebuild_aux_points.txt"
# REBUILD_PROBLEMS_PATH = "/root/GenesisGeo-main/evaluation_dataset/rebuild_problems/imo_95_rebuild.txt"
# AUX_POINTS_PATH = "/root/GenesisGeo-main/evaluation_dataset/rebuild_problems/imo_95_rebuild_aux_points_overlap.txt"
REBUILD_PROBLEMS_PATH = "/root/GenesisGeo-main/evaluation_dataset/rebuild_problems/hageo_409_rebuild.txt"
AUX_POINTS_PATH = "/root/GenesisGeo-main/evaluation_dataset/rebuild_problems/hageo_409_rebuild_aux_points_overlap.txt"
# 规则文件路径（用于 csolver-direct 模式）
DEFAULT_RULES_PATH = "/root/GenesisGeo-main/src/newclid/default_configs/rules.txt"
# 输出路径（会根据模式自动调整后缀）
DEFAULT_OUTPUT_DIR = "/root/GenesisGeo-main/datasets/solve_results"

# ============== 默认参数 ==============
DEFAULT_SOLVE_MODE = "ag2"  # 可选: "csolver-construction", "csolver-direct", "ag2"
USE_COORDINATES = True   # 是否在 construction 中包含点坐标（如 a@1.23_4.56）
DEFAULT_N_AUX = 6        # 每次采样的辅助点数量
DEFAULT_MAX_ATTEMPTS = 512 # 每道题的最大尝试次数
DEFAULT_SEED = 998244353        # 随机种子
DEFAULT_MAX_WORKERS = 50  # 并行进程数（默认1即串行）
DEFAULT_TIMEOUT = 7200    # 单题超时时间（秒），0 表示不限制
DEFAULT_MAX_SAMPLE_RETRIES = 0  # 随机采样模式下连续采样到重复组合的最大重试次数, 0 说明不限制


@dataclass
class Problem:
    """表示一道几何题目（统一格式）
    
    根据 input_format 使用不同字段：
    - construction 格式：使用 construction 和 goal_str
    - direct 格式：使用 points, premises, goal_tuple
    """
    name: str
    input_format: str  # "construction" 或 "direct"
    # construction 格式字段
    construction: Optional[str] = None  # 完整的 construction 字符串
    goal_str: Optional[str] = None      # goal 字符串
    # rebuild 格式字段
    points: Optional[List[Tuple[str, float, float]]] = None    # [(name, x, y), ...]
    premises: Optional[List[Tuple[str, List[str]]]] = None     # [(predicate, [args]), ...]
    goal_tuple: Optional[Tuple[str, List[str]]] = None         # (predicate, [args])


@dataclass
class AuxPoint:
    """表示一个候选辅助点
    
    construction 和 predicates 二选一使用
    """
    temp_name: str       # 临时名称，如 aux_int_0
    x: float
    y: float
    construction: Optional[str] = None       # construction 格式：如 "on_line a b, on_line c d"
    predicates: Optional[List[str]] = None   # rebuild 格式：如 ["coll aux_int_0 a b", ...]


@dataclass
class SolveResult:
    """求解结果"""
    problem_name: str
    solved: bool
    attempts: int = 0
    runtime: float = 0.0
    aux_points_used: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    proof_steps: Optional[List[str]] = None  # 证明步骤（按行分割）


def parse_problems_file_construction(filepath: str) -> List[Problem]:
    """解析 construction 格式的题目文件，返回题目列表
    
    格式：两行一组
    第一行：source 路径（如 examples/HAGeo-IMO/2000USATSTp2.gex）
    第二行：problem 文本（如 a b c = triangle; ... ? goal）
    """
    problems = []

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines) - 1:
        source_line = lines[i].strip()
        problem_line = lines[i + 1].strip()
        
        # 跳过空行
        if not source_line or not problem_line:
            i += 1
            continue
        
        # 从 source 路径提取题目名称
        # 例如：examples/HAGeo-IMO/2000USATSTp2.gex -> 2000USATSTp2
        name = os.path.splitext(os.path.basename(source_line))[0]
        
        # 解析 construction 和 goal
        if ' ? ' in problem_line:
            construction, goal = problem_line.rsplit(' ? ', 1)
        else:
            # 没有 goal 的情况，跳过
            i += 2
            continue
        
        problems.append(Problem(
            name=name,
            input_format="construction",
            construction=construction.strip(),
            goal_str=goal.strip()
        ))
        
        i += 2

    return problems


def parse_aux_points_file(filepath: str) -> Dict[str, List[AuxPoint]]:
    """解析辅助点文件，返回按题目名索引的辅助点字典
    
    格式：4行一组
    第1行：<aux_point_name>
    第2行：(<x>, <y>)
    第3行：<predicate1>, <predicate2>
    第4行：<aux_name> = <construction>
    
    以 # 开头的行为无效/重合的辅助点，跳过
    
    AuxPoint 同时存储 predicates 和 construction 两个字段
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
            while i < len(lines) and lines[i].strip().startswith("#"):
                i += 1
            continue

        # 解析辅助点（4行一组：名称、坐标、predicates、construction）
        if line.startswith("aux_"):
            aux_name = line
            i += 1

            # 第2行：坐标 (x, y)
            x, y = 0.0, 0.0
            if i < len(lines):
                coord_line = lines[i].strip()
                match = re.match(r'\(([^,]+),\s*([^)]+)\)', coord_line)
                if match:
                    x = float(match.group(1))
                    y = float(match.group(2))
                    i += 1
                else:
                    # 格式不对，跳过这个辅助点
                    continue
            else:
                break

            # 第3行：predicates，用 ", " 分隔
            predicates = []
            if i < len(lines):
                pred_line = lines[i].strip()
                if not pred_line.startswith("aux_") and pred_line != "Problem Name:" and not pred_line.startswith("#"):
                    predicates = [p.strip() for p in pred_line.split(", ") if p.strip()]
                    i += 1

            # 第4行：construction
            # 格式：aux_int_0 = on_line a b, on_line c d
            construction = None
            if i < len(lines):
                const_line = lines[i].strip()
                if " = " in const_line and not const_line.startswith("#"):
                    # 提取 = 后面的部分
                    construction = const_line.split(" = ", 1)[1]
                    i += 1

            # 只要有 predicates 或 construction 就保存
            if current_problem_name is not None and (predicates or construction):
                aux_point = AuxPoint(
                    temp_name=aux_name,
                    x=x,
                    y=y,
                    construction=construction,
                    predicates=predicates if predicates else None
                )
                aux_points_map[current_problem_name].append(aux_point)
        else:
            i += 1

    return aux_points_map


# ============== 坐标映射函数 ==============

def build_point_coordinates_map(rebuild_filepath: str) -> Dict[str, Dict[str, Tuple[float, float]]]:
    """从 rebuild 格式文件中构建点坐标映射表
    
    返回：{problem_name: {point_name: (x, y)}}
    """
    problems = parse_problems_file_rebuild(rebuild_filepath)
    coords_map = {}
    for problem in problems:
        point_coords = {}
        for name, x, y in problem.points:
            point_coords[name] = (x, y)
        coords_map[problem.name] = point_coords
    return coords_map


def add_coordinates_to_construction(construction: str, coords_map: Dict[str, Tuple[float, float]]) -> str:
    """将 construction 中的点名替换为带坐标形式
    
    例如：'a b c = triangle' -> 'a@1.0_2.0 b@3.0_4.0 c@5.0_6.0 = triangle'
    
    只处理 = 左边的点定义部分，不处理 = 右边的引用
    
    Args:
        construction: construction 字符串
        coords_map: {point_name: (x, y)} 坐标映射
    
    Returns:
        添加坐标后的 construction 字符串
    
    Raises:
        ValueError: 如果某个点在 coords_map 中找不到坐标
    """
    # 按 ; 分割各构造
    constructs = construction.split(';')
    new_constructs = []
    
    for construct in constructs:
        construct = construct.strip()
        if not construct:
            continue
        
        if '=' not in construct:
            new_constructs.append(construct)
            continue
        
        # 分离 = 左右两边
        left, right = construct.split('=', 1)
        left = left.strip()
        right = right.strip()
        
        # 处理左边的点名
        tokens = left.split()
        new_tokens = []
        for token in tokens:
            # 如果已经有坐标（如 a@1.23_4.56），跳过
            if '@' in token:
                new_tokens.append(token)
                continue
            
            # 查找坐标
            if token in coords_map:
                x, y = coords_map[token]
                new_tokens.append(f"{token}@{x}_{y}")
            else:
                raise ValueError(f"Point '{token}' not found in coordinates map")
        
        new_left = ' '.join(new_tokens)
        new_constructs.append(f"{new_left} = {right}")
    
    return '; '.join(new_constructs)


# ============== Rebuild 格式解析函数 ==============

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


def parse_problems_file_rebuild(filepath: str) -> List[Problem]:
    """解析 rebuild 格式的题目文件，返回题目列表
    
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
            input_format="direct",
            points=p['points'],
            premises=p['premises'],
            goal_tuple=p['goal']
        )
        for p in problems
    ]


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


def extract_point_names_from_construction(construction: str) -> List[str]:
    """从 construction 字符串中提取所有点名
    
    例如：'a b c = triangle; d = on_circum a b c' -> ['a', 'b', 'c', 'd']
    """
    point_names = set()
    
    # 按 ; 分割各构造
    constructs = construction.split(';')
    
    for construct in constructs:
        construct = construct.strip()
        if not construct:
            continue
        
        # 分离 = 左右两边
        if '=' in construct:
            left, right = construct.split('=', 1)
            
            # 左边可能有坐标（如 a@1.23_4.56），需要提取纯点名
            for token in left.strip().split():
                # 移除坐标部分
                if '@' in token:
                    token = token.split('@')[0]
                if token and token[0].isalpha():
                    point_names.add(token)
    
    return list(point_names)


def rename_construction(construction: str, old_name: str, new_name: str) -> str:
    """将 construction 中的临时点名替换为新名称
    
    例如：on_line aux_int_0 a b -> on_line x a b
    """
    # 使用单词边界替换，避免部分匹配
    pattern = r'\b' + re.escape(old_name) + r'\b'
    return re.sub(pattern, new_name, construction)


def rename_predicate(predicate: str, old_name: str, new_name: str) -> str:
    """将 predicate 中的临时点名替换为新名称
    
    例如：coll aux_int_0 a b -> coll x a b
    """
    parts = predicate.split()
    new_parts = [new_name if part == old_name else part for part in parts]
    return " ".join(new_parts)


def rename_predicate_as_tuple(predicate: str, old_name: str, new_name: str) -> Tuple[str, List[str]]:
    """将 predicate 中的临时点名替换为新名称，直接返回解析后的元组"""
    parts = predicate.split()
    new_parts = [new_name if part == old_name else part for part in parts]
    return (new_parts[0], new_parts[1:])


def augment_problem(
    problem: Problem,
    sampled_aux: List[AuxPoint],
    new_names: List[str],
    use_coordinates: bool = False
) -> Problem:
    """用采样的辅助点增强题目
    
    根据题目的 input_format 使用不同的增强方式：
    - construction 格式：辅助点的 construction 拼接到原 construction 末尾
    - rebuild 格式：添加辅助点到 points 列表，添加 predicates 到 premises 列表
    
    返回新的 Problem 对象
    """
    if problem.input_format == "construction":
        # Construction 格式增强
        new_construction = problem.construction
        
        for aux_point, new_name in zip(sampled_aux, new_names):
            # 替换 construction 中的临时点名
            aux_construction = rename_construction(aux_point.construction, aux_point.temp_name, new_name)
            
            # 构建辅助点定义
            if use_coordinates:
                # 带坐标：x@1.23_4.56 = on_line a b, on_line c d
                aux_def = f"; {new_name}@{aux_point.x}_{aux_point.y} = {aux_construction}"
            else:
                # 不带坐标：x = on_line a b, on_line c d
                aux_def = f"; {new_name} = {aux_construction}"
            
            new_construction += aux_def
        
        return Problem(
            name=problem.name,
            input_format="construction",
            construction=new_construction,
            goal_str=problem.goal_str
        )
    else:
        # Rebuild 格式增强
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
            input_format="direct",
            points=new_points,
            premises=new_premises,
            goal_tuple=problem.goal_tuple
        )


# ============== 格式转换函数 ==============

def convert_to_ag2_format(problem: Problem) -> str:
    """将 Problem 格式转换为 AG2 格式字符串
    
    AG2 格式：
    "a@x1_y1 = ; b@x2_y2 = ; ... lastpoint@xn_yn = pred1, pred2, ... ? goal"
    
    - 每个点必须有坐标 @x_y
    - 点定义之间用 "; " 分隔，每个点后面跟 "= ;"（除最后一个）
    - 所有约束 (predicates) 放在最后一个点的 "=" 后面，用 ", " 分隔
    - goal 用 " ? " 分隔
    """
    if not problem.points:
        raise ValueError(f"Problem {problem.name} has no points")
    
    # 构建点定义部分
    point_defs = []
    for i, (name, x, y) in enumerate(problem.points):
        if i < len(problem.points) - 1:
            # 非最后一个点
            point_defs.append(f"{name}@{x}_{y} = ;")
        else:
            # 最后一个点，后面跟 predicates
            predicates_str = ", ".join(
                f"{pred} {' '.join(args)}" for pred, args in problem.premises
            )
            point_defs.append(f"{name}@{x}_{y} = {predicates_str}")
    
    # 构建 goal 部分
    goal_pred, goal_args = problem.goal_tuple
    goal_str = f"{goal_pred} {' '.join(goal_args)}"
    
    # 拼接完整的 AG2 格式字符串
    ag2_string = " ".join(point_defs) + " ? " + goal_str
    
    return ag2_string

# ============== 求解函数 ==============

def solve_problem_csolver_construction(problem: Problem, seed: int) -> Tuple[bool, float, Optional[str], Optional[List[str]]]:
    """使用 GeometricSolverBuilder + CSolver 求解 construction 格式的题目
    
    返回：(是否成功, 运行时间, 错误信息, 证明步骤列表)
    """
    # 构建完整的 problem 文本
    problem_text = f"{problem.construction} ? {problem.goal_str}"
    
    try:
        # 使用 GeometricSolverBuilder 构建
        solver_builder = GeometricSolverBuilder(seed)
        solver_builder.load_problem_from_txt(problem_text)
        
        solver: GeometricSolver = solver_builder.build(max_attempts=100)
        
        # 使用 CSolver 求解
        csolver = CSolver(problem_text, seed=seed, solver=solver, using_log=True, using_exp=True)
        
        start_time = time.time()
        solved = csolver.run()
        end_time = time.time()
        
        proof_steps = None
        if solved:
            proof_steps = csolver.solver.write_proof_steps().split('\n')
        
        runtime = end_time - start_time
        return (solved, runtime, None, proof_steps)

    except Exception as e:
        return (False, 0.0, str(e), None)


def solve_problem_csolver_direct(problem: Problem, rules_path: str) -> Tuple[bool, float, Optional[str], Optional[List[str]]]:
    """使用 DirectSolver + CSolver 求解 rebuild 格式的题目
    
    返回：(是否成功, 运行时间, 错误信息, 证明步骤列表)
    """
    try:
        Dsolver = DirectSolver(
            points=problem.points,
            premises=problem.premises,
            goal=problem.goal_tuple,
            problem_name=problem.name,
            rules_path=Path(rules_path),
        )
        
        solver = CSolver(
            solver=Dsolver.solver,
            points=problem.points,
            premises=problem.premises,
            goals=[problem.goal_tuple],
            problem_name=problem.name,
        )
        
        start_time = time.time()
        solved = solver.run()
        end_time = time.time()
        
        proof_steps = None
        if solved:
            proof_steps = solver.solver.write_proof_steps().split('\n')

        runtime = solver.solver.run_infos.get('runtime', end_time - start_time)
        return (solved, runtime, None, proof_steps)

    except Exception as e:
        return (False, 0.0, str(e), None)


def solve_problem_ag2(problem: Problem) -> Tuple[bool, float, Optional[str], Optional[List[str]]]:
    """使用 AlphaGeometry2 的 DDAR 引擎求解题目
    
    返回：(是否成功, 运行时间, 错误信息, 证明步骤列表)
    
    注意：AG2 不返回证明步骤
    """
    try:
        
        # 转换为 AG2 格式
        ag2_string = convert_to_ag2_format(problem)
        
        start_time = time.time()
        
        # 解析题目
        ag_problem = AGProblem.parse(ag2_string)
        
        # 创建 DDAR 引擎
        ddar = DDAR(ag_problem.points)
        
        # 添加所有 predicates 作为假设
        for pred in ag_problem.preds:
            ddar.force_pred(pred)
        
        # 执行推导闭包
        ddar.deduction_closure()
        
        # 检查目标是否达成
        solved = ddar.check_pred(ag_problem.goal)
        
        end_time = time.time()
        runtime = end_time - start_time
        
        # AG2 不返回证明步骤
        return (solved, runtime, None, None)

    except Exception as e:
        return (False, 0.0, str(e), None)

def save_results(results: List[SolveResult], output_path: str):
    """保存求解结果到 JSON 文件"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data = []
    for r in results:
        item = {
            'problem_name': r.problem_name,
            'solved': r.solved,
            'attempts': r.attempts,
            'runtime': r.runtime,
            'aux_points_used': r.aux_points_used,
            'error': r.error
        }
        if r.solved and r.proof_steps:
            item['proof_steps'] = r.proof_steps
        data.append(item)

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
        f.write("HAGeo 式辅助点采样求解统计 (Construction 形式)\n")
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


# ============== 统一的求解调度函数 ==============

def solve_problem_unified(
    problem: Problem,
    solve_mode: str,
    seed: int,
    rules_path: str = DEFAULT_RULES_PATH
) -> Tuple[bool, float, Optional[str], Optional[List[str]]]:
    """统一的求解入口，根据 solve_mode 选择对应的求解方法
    
    Args:
        problem: 题目对象
        solve_mode: 求解模式，可选 "csolver-construction", "csolver-direct", "ag2"
        seed: 随机种子
        rules_path: 规则文件路径（仅 csolver-direct 模式使用）
    
    Returns:
        (是否成功, 运行时间, 错误信息, 证明步骤列表)
    """
    if solve_mode == "csolver-construction":
        return solve_problem_csolver_construction(problem, seed)
    elif solve_mode == "csolver-direct":
        return solve_problem_csolver_direct(problem, rules_path)
    elif solve_mode == "ag2":
        return solve_problem_ag2(problem)
    else:
        raise ValueError(f"Unknown solve mode: {solve_mode}")

def get_point_names_from_problem(problem: Problem) -> List[str]:
    """从题目中提取所有点名"""
    if problem.input_format == "construction":
        return extract_point_names_from_construction(problem.construction)
    else:
        return [name for name, x, y in problem.points]


def format_aux_points_for_result(
    sampled_aux: List[AuxPoint],
    new_names: List[str],
    solve_mode: str,
) -> List[Dict]:
    """格式化辅助点信息用于保存结果"""
    result = []
    for aux, new_name in zip(sampled_aux, new_names):
        if solve_mode == "csolver-construction":
            result.append({
                "name": new_name,
                "coords": [aux.x, aux.y],
                "construction": rename_construction(aux.construction, aux.temp_name, new_name)
            })
        else:
            result.append({
                "name": new_name,
                "coords": [aux.x, aux.y],
                "predicates": [rename_predicate(p, aux.temp_name, new_name) for p in aux.predicates]
            })
    return result

def solve_single_problem(
    problem: Problem,
    candidates: List[AuxPoint],
    args_dict: Dict,
    problem_index: int
) -> SolveResult:
    """单题求解函数，用于并行调度"""
    random.seed(args_dict['seed'] + problem_index)
    
    n_aux = args_dict['n_aux']
    max_attempts = args_dict['max_attempts']
    use_coordinates = args_dict['use_coordinates']
    solve_mode = args_dict['solve_mode']
    rules_path = args_dict.get('rules_path', DEFAULT_RULES_PATH)
    is_parallel = args_dict.get('max_workers', 1) > 1
    seed = DEFAULT_SEED
    
    # 先尝试直接求解（不加辅助点）
    solved, runtime, error, proof_steps = solve_problem_unified(problem, solve_mode, seed, rules_path)
    result = SolveResult(
        problem_name=problem.name,
        solved=solved,
        attempts=1,
        runtime=runtime,
        aux_points_used=[],
        error=error,
        proof_steps=proof_steps
    )
    
    if not is_parallel:
        status = "✓ 成功" if solved else ("✗ 错误: " + str(error) if error else "✗ 失败")
        print(f"直接求解结果: {status}")
        print(f"用时: {runtime:.2f}s")
    
    if solved or not candidates:
        return result
    
    # 获取已有点名
    existing_point_names = get_point_names_from_problem(problem)
    n_sample = min(n_aux, len(candidates))
    precomputed_new_names = generate_new_point_names(existing_point_names, n_sample)
    
    result = SolveResult(
        problem_name=problem.name,
        solved=False,
        attempts=1,
        runtime=runtime,
        aux_points_used=[],
        error=None
    )
    
    total_runtime = runtime
    solved = False
    
    # 计算组合总数，决定使用穷举还是随机采样
    n_candidates = len(candidates)
    total_combinations = comb(n_candidates, n_sample)
    use_exhaustive = (total_combinations <= max_attempts)
    
    if use_exhaustive:
        # 穷举所有组合
        all_combinations = list(itertools.combinations(range(n_candidates), n_sample))
        random.shuffle(all_combinations)  # 随机打乱顺序
        attempts_to_try = len(all_combinations)
        if not is_parallel:
            print(f"组合总数 C({n_candidates},{n_sample})={total_combinations} <= max_attempts={max_attempts}，使用穷举模式")
    else:
        # 随机采样模式
        tried_combinations = set()
        attempts_to_try = max_attempts
        if not is_parallel:
            print(f"组合总数 C({n_candidates},{n_sample})={total_combinations} > max_attempts={max_attempts}，使用随机采样模式")
    
    for attempt in range(attempts_to_try):
        result.attempts = attempt + 2  # +2 因为第一次是直接求解
        
        # 根据模式选择辅助点
        if use_exhaustive:
            indices = all_combinations[attempt]
            sampled_aux = [candidates[i] for i in indices]
        else:
            # 随机采样，避免重复
            max_sample_retries = DEFAULT_MAX_SAMPLE_RETRIES
            sample_retry_count = 0
            found_new = False
            while sample_retry_count < max_sample_retries or DEFAULT_MAX_SAMPLE_RETRIES == 0:
                indices = tuple(sorted(random.sample(range(n_candidates), n_sample)))
                if indices not in tried_combinations:
                    tried_combinations.add(indices)
                    found_new = True
                    break
                sample_retry_count += 1
                # 如果已经尝试了所有组合，退出循环
                if len(tried_combinations) >= total_combinations:
                    break
            
            # 如果没找到新组合（连续重试失败或已穷尽），退出主循环
            if not found_new:
                if not is_parallel:
                    if len(tried_combinations) >= total_combinations:
                        print(f"已穷尽所有 {total_combinations} 种组合")
                    else:
                        print(f"连续 {max_sample_retries} 次采样均为重复，已尝试 {len(tried_combinations)}/{total_combinations} 种组合")
                break
            sampled_aux = [candidates[i] for i in indices]
        
        new_names = precomputed_new_names
        
        # 构建增强后的题目
        augmented = augment_problem(problem, sampled_aux, new_names, use_coordinates)
        
        try:
            is_solved, runtime, error, proof_steps = solve_problem_unified(augmented, solve_mode, seed + attempt + 1, rules_path)
            total_runtime += runtime
            
            if is_solved:
                solved = True
                result.solved = True
                result.runtime = total_runtime
                result.proof_steps = proof_steps
                result.aux_points_used = format_aux_points_for_result(sampled_aux, new_names, solve_mode)
                if not is_parallel:
                    print(f"✓ 第 {attempt + 1} 次辅助点采样成功！用时: {total_runtime:.2f}s")
                    print(f"  使用辅助点: {new_names}")
                break
            
        except Exception as e:
            result.error = str(e)
        
        if not is_parallel and (attempt + 1) % 10 == 0:
            print(f"  已尝试 {attempt + 1}/{attempts_to_try} 次辅助点采样...")
    
    if not solved:
        result.runtime = total_runtime
        if not is_parallel:
            if use_exhaustive:
                print(f"✗ 穷举所有 {total_combinations} 种组合后仍未成功，用时: {total_runtime:.2f}s")
            else:
                print(f"✗ {max_attempts} 次辅助点采样后仍未成功，用时: {total_runtime:.2f}s")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="统一的几何题目求解脚本，支持多种求解引擎和输入格式"
    )
    parser.add_argument(
        "--solve-mode",
        type=str,
        default=DEFAULT_SOLVE_MODE,
        choices=["csolver-construction", "csolver-direct", "ag2"],
        help="求解引擎：csolver-construction (GeometricSolverBuilder), csolver-direct (DirectSolver), ag2 (AlphaGeometry2)"
    )
    parser.add_argument(
        "--problems",
        type=str,
        default=None,
        help="题目文件路径（默认根据 solve-mode 自动选择）"
    )
    parser.add_argument(
        "--aux-points",
        type=str,
        default=None,
        help="辅助点文件路径（默认根据 solve-mode 自动选择）"
    )
    parser.add_argument(
        "--rules",
        type=str,
        default=DEFAULT_RULES_PATH,
        help="规则文件路径（仅 csolver-direct 模式使用）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出结果文件路径（默认自动生成）"
    )
    parser.add_argument(
        "--summary",
        type=str,
        default=None,
        help="汇总统计文件路径（默认自动生成）"
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
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="随机种子"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="并行进程数（默认1即串行）"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="单题超时时间（秒），0 表示不限制"
    )
    parser.add_argument(
        "--use-coordinates",
        action="store_true",
        default=USE_COORDINATES,
        help="是否在 construction 中包含点坐标"
    )
    parser.add_argument(
        "--no-coordinates",
        action="store_true",
        help="不在 construction 中包含点坐标"
    )

    args = parser.parse_args()
    
    # 处理坐标开关
    use_coordinates = args.use_coordinates
    if args.no_coordinates:
        use_coordinates = False

    # 根据 solve_mode 确定输入格式和默认路径
    solve_mode = args.solve_mode
    
    if solve_mode == "csolver-construction":
        # construction 格式
        input_format = "construction"
        default_problems_path = CONSTRUCTION_PROBLEMS_PATH
    elif solve_mode in ("csolver-direct", "ag2"):
        # rebuild 格式
        input_format = "direct"
        default_problems_path = REBUILD_PROBLEMS_PATH
    else:
        raise ValueError(f"Unknown solve mode: {solve_mode}")
    
    default_aux_path = AUX_POINTS_PATH
    # 使用用户指定的路径或默认路径
    problems_path = args.problems if args.problems else default_problems_path
    aux_points_path = args.aux_points if args.aux_points else default_aux_path
    
    # 自动生成输出路径
    if args.output:
        output_path = args.output
    else:
        # 从问题文件名生成
        base_name = os.path.splitext(os.path.basename(problems_path))[0]
        output_path = os.path.join(DEFAULT_OUTPUT_DIR, f"{base_name}_results_{input_format}_{solve_mode.replace('-', '_')}_{args.max_attempts}.json")
    
    if args.summary:
        summary_path = args.summary
    else:
        summary_path = output_path.replace('.json', '_summary.txt')

    random.seed(args.seed)

    print("=" * 60)
    print("统一几何求解器 - 支持多引擎和多格式")
    print("=" * 60)
    print(f"求解模式: {solve_mode}")
    print(f"输入格式: {input_format}")
    print(f"题目文件: {problems_path}")
    print(f"辅助点文件: {aux_points_path}")
    if solve_mode == "csolver-direct":
        print(f"规则文件: {args.rules}")
    print(f"每次采样辅助点数: {args.n_aux}")
    print(f"最大尝试次数: {args.max_attempts}")
    print(f"随机种子: {args.seed}")
    print(f"并行进程数: {args.max_workers}")
    print(f"单题超时: {args.timeout}秒" if args.timeout > 0 else "单题超时: 不限制")
    print(f"使用坐标: {use_coordinates}")
    print(f"输出文件: {output_path}")
    print("=" * 60 + "\n")

    # 根据输入格式解析题目
    print("正在加载题目...")
    if input_format == "construction":
        problems = parse_problems_file_construction(problems_path)
    else:  # rebuild
        problems = parse_problems_file_rebuild(problems_path)
    print(f"已加载 {len(problems)} 道题目\n")

    # 如果是 csolver-construction 模式且使用坐标，从 rebuild 文件加载坐标
    point_coords_map: Dict[str, Dict[str, Tuple[float, float]]] = {}
    if solve_mode == "csolver-construction" and use_coordinates:
        print(f"正在从 rebuild 文件加载点坐标: {REBUILD_PROBLEMS_PATH}")
        point_coords_map = build_point_coordinates_map(REBUILD_PROBLEMS_PATH)
        print(f"已加载 {len(point_coords_map)} 道题目的点坐标\n")
        
        # 为每个题目的 construction 添加坐标
        print("正在为 construction 添加点坐标...")
        for i, problem in enumerate(problems):
            if problem.name not in point_coords_map:
                raise ValueError(f"Problem '{problem.name}' not found in coordinates file: {REBUILD_PROBLEMS_PATH}")
            
            coords = point_coords_map[problem.name]
            try:
                new_construction = add_coordinates_to_construction(problem.construction, coords)
                problems[i] = Problem(
                    name=problem.name,
                    input_format="construction",
                    construction=new_construction,
                    goal_str=problem.goal_str
                )
            except ValueError as e:
                raise ValueError(f"Error adding coordinates to problem '{problem.name}': {e}")
        print("点坐标添加完成\n")

    # 解析辅助点（统一格式，同时包含 predicates 和 construction）
    print("正在加载辅助点...")
    aux_points_map = parse_aux_points_file(aux_points_path)
    total_aux = sum(len(v) for v in aux_points_map.values())
    print(f"已加载 {len(aux_points_map)} 道题目的辅助点，共 {total_aux} 个候选辅助点\n")

    # 构建参数字典
    args_dict = {
        'n_aux': args.n_aux,
        'max_attempts': args.max_attempts,
        'seed': args.seed,
        'max_workers': args.max_workers,
        'use_coordinates': use_coordinates,
        'solve_mode': solve_mode,
        'rules_path': args.rules,
        'timeout': args.timeout,
    }

    # 准备待求解的题目列表
    problems_to_solve = []
    for idx, problem in enumerate(problems):
        candidates = aux_points_map.get(problem.name, [])
        problems_to_solve.append((idx, problem, candidates))
    
    print(f"待求解题目数: {len(problems_to_solve)}\n")

    results_dict: Dict[str, SolveResult] = {}
    total_start_time = time.time()

    if args.max_workers == 1:
        # ============== 串行模式 ==============
        for idx, problem, candidates in problems_to_solve:
            print("-" * 60)
            print(f"[{idx + 1}/{len(problems)}] {problem.name}")
            print("-" * 60)
            
            if not candidates:
                print(f"警告：没有找到辅助点候选，仅尝试直接求解")
            else:
                print(f"候选辅助点: {len(candidates)} 个")
            
            result = solve_single_problem(problem, candidates, args_dict, idx)
            results_dict[problem.name] = result
            print()
            
            # 定期保存结果
            if (idx + 1) % 10 == 0:
                results_list = [results_dict.get(p.name) for p in problems if p.name in results_dict]
                save_results(results_list, output_path)
                print(f"[自动保存] 已保存 {len(results_list)} 道题目的结果\n")
    else:
        # ============== 并行模式 (Ray) ==============
        print(f"启用 Ray 并行模式，使用 {args.max_workers} 个进程\n")
        
        if not ray.is_initialized():
            ray.init(
                num_cpus=args.max_workers,
                ignore_reinit_error=True,
                log_to_driver=False,
                include_dashboard=False,
                _metrics_export_port=None,
            )
        
        @ray.remote(max_retries=0)
        def solve_remote(problem, candidates, args_dict, problem_index):
            return solve_single_problem(problem, candidates, args_dict, problem_index)
        
        total_to_solve = len(problems_to_solve)
        timeout = args.timeout  # 超时时间（秒），0 表示不限制
        max_concurrent = args.max_workers  # 最大并发任务数
        
        # 使用队列管理待处理任务
        pending_queue = list(problems_to_solve)  # 待处理队列
        future_to_problem = {}  # future -> (idx, problem)
        future_start_time = {}  # future -> 任务开始执行时间
        pending = []  # 当前正在执行的 futures
        
        completed_count = 0
        timeout_count = 0
        
        def submit_task(task_item):
            """提交一个任务并记录开始时间"""
            idx, problem, candidates = task_item
            future = solve_remote.remote(problem, candidates, args_dict, idx)
            future_to_problem[future] = (idx, problem)
            future_start_time[future] = time.time()  # 记录实际开始执行的时间
            pending.append(future)
            return future
        
        # 初始提交：填满所有可用进程
        initial_batch_size = min(max_concurrent, len(pending_queue))
        for _ in range(initial_batch_size):
            task_item = pending_queue.pop(0)
            submit_task(task_item)
        
        print(f"初始提交 {initial_batch_size} 个任务，剩余 {len(pending_queue)} 个待处理\n")
        
        while pending:
            # 每5秒检查一次，便于及时发现超时任务
            done, pending = ray.wait(pending, num_returns=1, timeout=5.0)
            
            current_time = time.time()
            
            # 检查并取消超时任务
            if timeout > 0:
                timed_out_futures = []
                for future in pending:
                    elapsed = current_time - future_start_time[future]
                    if elapsed > timeout:
                        timed_out_futures.append(future)
                
                for future in timed_out_futures:
                    idx, problem = future_to_problem[future]
                    elapsed = current_time - future_start_time[future]
                    
                    # 强制取消任务
                    ray.cancel(future, force=True)
                    pending.remove(future)
                    
                    completed_count += 1
                    timeout_count += 1
                    
                    print(f"[{completed_count}/{total_to_solve}] ⏱ {problem.name} 超时 ({elapsed:.1f}s > {timeout}s)")
                    results_dict[problem.name] = SolveResult(
                        problem_name=problem.name,
                        solved=False,
                        attempts=0,
                        runtime=elapsed,
                        aux_points_used=[],
                        error=f"Timeout after {elapsed:.1f} seconds"
                    )
                    
                    # 提交新任务填补空位
                    if pending_queue:
                        task_item = pending_queue.pop(0)
                        submit_task(task_item)
                        print(f"    → 已提交新任务，剩余 {len(pending_queue)} 个待处理")
                    
                    if completed_count % 10 == 0:
                        results_list = [results_dict.get(p.name) for p in problems if p.name in results_dict]
                        save_results(results_list, output_path)
                        print(f"[自动保存] 已保存 {len(results_list)} 道题目的结果")
            
            # 处理已完成的任务
            for future in done:
                idx, problem = future_to_problem[future]
                completed_count += 1
                elapsed = current_time - future_start_time[future]
                
                try:
                    result = ray.get(future)
                    results_dict[problem.name] = result
                    
                    status = "✓" if result.solved else "✗"
                    attempts_info = f"({result.attempts} attempts)" if result.attempts > 1 else ""
                    print(f"[{completed_count}/{total_to_solve}] {status} {problem.name} {attempts_info} ({result.runtime:.1f}s)")
                    
                except ray.exceptions.TaskCancelledError:
                    # 任务被取消（超时取消后可能会触发）
                    print(f"[{completed_count}/{total_to_solve}] ⏱ {problem.name} 已取消")
                    if problem.name not in results_dict:
                        results_dict[problem.name] = SolveResult(
                            problem_name=problem.name,
                            solved=False,
                            attempts=0,
                            runtime=elapsed,
                            aux_points_used=[],
                            error="Task cancelled"
                        )
                except ray.exceptions.RayTaskError as e:
                    print(f"[{completed_count}/{total_to_solve}] ✗ {problem.name} 任务错误: {e}")
                    results_dict[problem.name] = SolveResult(
                        problem_name=problem.name,
                        solved=False,
                        attempts=0,
                        runtime=elapsed,
                        aux_points_used=[],
                        error=str(e)
                    )
                except ray.exceptions.WorkerCrashedError as e:
                    print(f"[{completed_count}/{total_to_solve}] ✗ {problem.name} 进程崩溃: {e}")
                    results_dict[problem.name] = SolveResult(
                        problem_name=problem.name,
                        solved=False,
                        attempts=0,
                        runtime=elapsed,
                        aux_points_used=[],
                        error=f"Worker crashed: {e}"
                    )
                except Exception as e:
                    print(f"[{completed_count}/{total_to_solve}] ✗ {problem.name} 错误: {e}")
                    results_dict[problem.name] = SolveResult(
                        problem_name=problem.name,
                        solved=False,
                        attempts=0,
                        runtime=elapsed,
                        aux_points_used=[],
                        error=str(e)
                    )
                
                # 提交新任务填补空位
                if pending_queue:
                    task_item = pending_queue.pop(0)
                    submit_task(task_item)
                
                if completed_count % 10 == 0:
                    results_list = [results_dict.get(p.name) for p in problems if p.name in results_dict]
                    save_results(results_list, output_path)
                    print(f"[自动保存] 已保存 {len(results_list)} 道题目的结果")
        
        if timeout_count > 0:
            print(f"\n[超时统计] 共 {timeout_count} 道题目超时")
        
        ray.shutdown()

    total_time = time.time() - total_start_time

    # 按原始顺序整理结果
    results: List[SolveResult] = []
    for problem in problems:
        if problem.name in results_dict:
            results.append(results_dict[problem.name])

    # 最终保存
    save_results(results, output_path)
    save_summary(results, summary_path, total_time)

    # 打印统计
    print("=" * 60)
    print("求解统计")
    print("=" * 60)
    solved_count = sum(1 for r in results if r.solved)
    print(f"总题目数: {len(results)}")
    print(f"成功求解: {solved_count} ({100*solved_count/len(results):.1f}%)")
    print(f"总用时: {total_time:.2f} 秒")
    print(f"结果已保存到: {output_path}")
    print(f"统计已保存到: {summary_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
