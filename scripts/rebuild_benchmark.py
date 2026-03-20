#!/usr/bin/env python3
"""
将 benchmark 题目转换为 DirectSolver 可用的 rebuild 格式。

用法:
    python scripts/rebuild_benchmark.py
    python scripts/rebuild_benchmark.py --input <输入文件> --output <输出文件>

输入格式（两行一组）：
    examples/HAGeo-IMO/2000USATSTp2.gex
    a b c = triangle; d = on_circum a b c; ... ? perp e f m n

输出格式：
    Rule Name:
    2000USATSTp2
    Points:
    a:x1,y1
    b:x2,y2
    ...
    Premises:
    predicate1 arg1 arg2 ...
    ...
    Goal:
    predicate arg1 arg2 ...
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Tuple, Optional
from fractions import Fraction
from concurrent.futures import ProcessPoolExecutor, as_completed

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from newclid.api import GeometricSolverBuilder
from newclid.numerical.geometries import PointNum

# ==================== 默认配置（硬编码路径） ====================

DEFAULT_INPUT = "/c23474/home/duzhengtong/Discovery-GenesisGeo/benchmarks/hageo_409.txt"
DEFAULT_OUTPUT = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/hageo_409_rebuild.txt"
DEFAULT_SEED = 998244353
DEFAULT_MAX_WORKERS = 10  # 默认单线程，设置 > 1 开启并行

# ==================== 日志配置 ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_benchmark_file(filepath: str) -> List[Tuple[str, str]]:
    """
    解析 benchmark 文件，返回 (题目名, 题目文本) 列表。
    
    文件格式：两行一组
    - 第一行：source 路径（如 examples/HAGeo-IMO/2000USATSTp2.gex）
    - 第二行：problem 文本（含 ? goal）
    
    Args:
        filepath: 输入文件路径
        
    Returns:
        [(problem_name, problem_text), ...]
    """
    problems = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    if len(lines) % 2 != 0:
        logger.warning(f"文件行数 {len(lines)} 不是偶数，可能格式有误")
    
    for i in range(0, len(lines) - 1, 2):
        source_line = lines[i]
        problem_text = lines[i + 1]
        
        # 从 source 路径提取题目名
        # 例如：examples/HAGeo-IMO/2000USATSTp2.gex -> 2000USATSTp2
        problem_name = Path(source_line).stem
        
        problems.append((problem_name, problem_text))
    
    logger.info(f"从 {filepath} 解析到 {len(problems)} 道题目")
    return problems


def extract_rebuild_info(
    problem_name: str,
    problem_text: str,
    seed: int = DEFAULT_SEED
) -> Optional[dict]:
    """
    从题目文本构建 solver 并提取 rebuild 信息。
    
    Args:
        problem_name: 题目名称
        problem_text: 题目文本（含 ? goal）
        seed: 随机种子
        
    Returns:
        {
            'name': str,
            'points': [(name, x, y), ...],
            'premises': [(predicate, [args]), ...],
            'goal': (predicate, [args])
        }
        构建失败时返回 None
    """
    try:
        # 构建 solver
        solver = (
            GeometricSolverBuilder(seed)
            .load_problem_from_txt(problem_text)
            .build()
        )
        
        # 收集有用的点（出现在 premises 或 goal 中）
        useful_points: List[str] = []
        
        # 提取前提 (premises)
        premises: List[Tuple[str, List[str]]] = []
        for stmt in solver.proof.dep_graph.hyper_graph:
            predicate = stmt.predicate.NAME
            args = []
            for pt in stmt.args:
                if isinstance(pt, Fraction):
                    args.append(str(pt))
                else:
                    args.append(pt.name)
                    if pt.name not in useful_points:
                        useful_points.append(pt.name)
            premises.append((predicate, args))
        
        # 提取目标 (goal)
        # 假设只有一个目标
        goal = None
        for stmt in solver.proof.goals:
            predicate = stmt.predicate.NAME
            args = []
            for pt in stmt.args:
                if isinstance(pt, Fraction):
                    args.append(str(pt))
                else:
                    args.append(pt.name)
                    if pt.name not in useful_points:
                        useful_points.append(pt.name)
            goal = (predicate, args)
            break  # 只取第一个目标
        
        if goal is None:
            logger.warning(f"[{problem_name}] 未找到目标")
            return None
        
        # 提取点坐标（仅有用的点）
        points: List[Tuple[str, float, float]] = []
        for name, node in solver.proof.symbols_graph.name2node.items():
            if isinstance(node.num, PointNum) and name in useful_points:
                points.append((name, node.num.x, node.num.y))
        
        return {
            'name': problem_name,
            'points': points,
            'premises': premises,
            'goal': goal
        }
        
    except Exception as e:
        logger.error(f"[{problem_name}] 构建失败: {e}")
        return None


def write_rebuild_file(
    rebuild_infos: List[dict],
    output_path: str
) -> None:
    """
    将 rebuild 信息写入文件。
    
    Args:
        rebuild_infos: rebuild 信息列表
        output_path: 输出文件路径
    """
    # 确保输出目录存在
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for info in rebuild_infos:
            # Rule Name:
            f.write("Rule Name:\n")
            f.write(f"{info['name']}\n")
            
            # Points:
            f.write("Points:\n")
            for name, x, y in info['points']:
                f.write(f"{name}:{x},{y}\n")
            
            # Premises:
            f.write("Premises:\n")
            for predicate, args in info['premises']:
                f.write(f"{predicate} {' '.join(args)}\n")
            
            # Goal:
            f.write("Goal:\n")
            predicate, args = info['goal']
            f.write(f"{predicate} {' '.join(args)}\n")
            
            # 空行分隔
            f.write("\n")
    
    logger.info(f"已写入 {len(rebuild_infos)} 道题目到 {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="将 benchmark 题目转换为 DirectSolver 可用的 rebuild 格式"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=DEFAULT_INPUT,
        help=f"输入文件路径 (默认: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"输出文件路径 (默认: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=DEFAULT_SEED,
        help=f"随机种子 (默认: {DEFAULT_SEED})"
    )
    parser.add_argument(
        "--max-workers", "-w",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"并行工作进程数，设置 > 1 开启并行 (默认: {DEFAULT_MAX_WORKERS})"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("开始转换 benchmark 题目为 rebuild 格式")
    logger.info(f"输入文件: {args.input}")
    logger.info(f"输出文件: {args.output}")
    logger.info(f"并行进程数: {args.max_workers}")
    logger.info("=" * 60)
    
    # 解析输入文件
    problems = parse_benchmark_file(args.input)
    
    # 转换每道题目
    rebuild_infos = []
    success_count = 0
    fail_count = 0
    
    if args.max_workers <= 1:
        # 串行处理
        for idx, (problem_name, problem_text) in enumerate(problems):
            logger.info(f"[{idx + 1}/{len(problems)}] 处理: {problem_name}")
            
            info = extract_rebuild_info(problem_name, problem_text, args.seed)
            
            if info is not None:
                rebuild_infos.append(info)
                success_count += 1
            else:
                fail_count += 1
    else:
        # 并行处理
        logger.info(f"启用并行模式，使用 {args.max_workers} 个进程")
        
        # 用于保持原顺序的结果列表，初始化为 None
        results = [None] * len(problems)
        
        with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
            # 提交所有任务，保存 future 到索引的映射
            future_to_idx = {}
            for idx, (problem_name, problem_text) in enumerate(problems):
                future = executor.submit(
                    extract_rebuild_info, 
                    problem_name, 
                    problem_text, 
                    args.seed
                )
                future_to_idx[future] = (idx, problem_name)
            
            # 收集结果
            for future in as_completed(future_to_idx):
                idx, problem_name = future_to_idx[future]
                try:
                    info = future.result()
                    results[idx] = info
                    if info is not None:
                        success_count += 1
                        logger.info(f"[{success_count + fail_count}/{len(problems)}] 完成: {problem_name}")
                    else:
                        fail_count += 1
                        logger.warning(f"[{success_count + fail_count}/{len(problems)}] 失败: {problem_name}")
                except Exception as e:
                    fail_count += 1
                    logger.error(f"[{success_count + fail_count}/{len(problems)}] 异常: {problem_name} - {e}")
        
        # 按顺序收集成功的结果
        rebuild_infos = [r for r in results if r is not None]
    
    # 写出结果
    write_rebuild_file(rebuild_infos, args.output)
    
    # 统计
    logger.info("=" * 60)
    logger.info(f"转换完成: 成功 {success_count}, 失败 {fail_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
