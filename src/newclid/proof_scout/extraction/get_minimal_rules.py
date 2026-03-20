#!/usr/bin/env python3
"""
基于等价性的最小规则集提取脚本

通过 DirectSolver 检测规则等价性，提取最小独立规则集。

算法：
1. 加载基础规则库（rules.txt）作为初始规则库 C
2. 加载提取的规则列表 R 和对应的重建题目 P
3. 初始化独立规则集 I=[]，等价关系 E={}
4. 对于每条规则 r_i 及其对应题目 p_i：
   - 使用当前规则库 C 尝试求解 p_i
   - 若成功：r_i 可被推导，通过解析证明过程确定归属关系
   - 若失败：r_i 是独立规则，将 r_i 加入 C 和 I
5. 输出独立规则集和等价关系映射

支持并行模式：通过分治+合并策略实现多进程并行提取。
"""

import json
import logging
import time
import tempfile
import shutil
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set

# ==================== 配置参数（在此处修改） ====================

FILE_PROFIX_SHORT = "c10s200k"  # 文件前缀标识符
# 输入文件路径
EXTRACTED_RULES_FILE = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}/{FILE_PROFIX_SHORT}_rules_norm.txt"
REBUILD_PROBLEMS_FILE = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/{FILE_PROFIX_SHORT}_rules_rebuild.txt"
BASE_RULES_FILE = "/c23474/home/duzhengtong/Discovery-GenesisGeo/src/newclid/default_configs/rules.txt"

# 输出文件路径
OUTPUT_MINIMAL_RULES_FILE = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}/rules_minimal.txt"
OUTPUT_EQUIVALENCE_FILE = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}/rules_equivalence.json"

# 求解超时时间（秒）
TIMEOUT = 3600

# 日志级别
LOG_LEVEL = logging.INFO

# 并行配置
MAX_WORKERS = 20  # 并行进程数（默认8，可调整为16）
CHUNK_SIZE = 250  # 每个任务块的规则数量
PARALLEL_MODE = True  # 是否启用并行模式（False则回退到串行）

# ==================== 配置参数结束 ====================

# 配置日志
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class Problem:
    """表示一道几何题目"""
    name: str
    points: List[Tuple[str, float, float]]
    premises: List[Tuple[str, List[str]]]
    goal: Tuple[str, List[str]]


@dataclass
class RuleInfo:
    """表示一条规则"""
    name: str
    content: str


def parse_point_line(line: str) -> Tuple[str, float, float]:
    """解析点坐标行，格式: name: x,y"""
    name, coords = line.strip().split(":")
    x, y = coords.split(",")
    return (name.strip(), float(x), float(y))


def parse_predicate(line: str) -> Tuple[str, List[str]]:
    """解析谓词行，格式: predicate_name arg1 arg2 ..."""
    parts = line.strip().split()
    predicate_name = parts[0]
    args = parts[1:]
    return (predicate_name, args)


def parse_extracted_rules(filepath: str) -> List[RuleInfo]:
    """
    解析提取的规则文件（两行一组：规则名 + 规则内容）
    
    格式示例：
    0sub_0
    eqangle a b b c b d a b, midp e c d, perp a b a c => para a e b d
    """
    rules = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            name = lines[i]
            content = lines[i + 1]
            rules.append(RuleInfo(name=name, content=content))
    
    logger.info(f"从 {filepath} 解析到 {len(rules)} 条规则")
    return rules


def parse_base_rules(filepath: str) -> List[RuleInfo]:
    """
    解析基础规则文件（两行一组：规则描述 + 规则内容）
    
    格式示例：
    r52 Properties of similar triangles (Direct)
    simtri A B C P Q R => eqangle B A B C Q P Q R, eqratio B A B C Q P Q R
    """
    rules = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            # 从第一行提取规则名（第一个空格前的部分）
            name_line = lines[i]
            name = name_line.split()[0] if name_line.split() else name_line
            content = lines[i + 1]
            rules.append(RuleInfo(name=name, content=content))
    
    logger.info(f"从 {filepath} 解析到 {len(rules)} 条基础规则")
    return rules


def parse_problems_file(filepath: str) -> Dict[str, Problem]:
    """
    解析题目文件，返回以规则名为键的题目字典
    
    格式示例：
    Rule Name:
    0sub_0
    Points:
    a:0.18143748112873181,0.06471373773631531
    ...
    Premises:
    eqangle a b b c b d a b
    ...
    Goal:
    para a e b d
    """
    problems = {}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 按空行分割不同题目
    problem_blocks = content.strip().split("\n\n")
    
    current_problem = None
    current_section = None
    
    for block in problem_blocks:
        lines = block.strip().split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line == "Rule Name:":
                # 保存上一个题目
                if current_problem is not None and current_problem['goal'] is not None:
                    problems[current_problem['name']] = Problem(
                        name=current_problem['name'],
                        points=current_problem['points'],
                        premises=current_problem['premises'],
                        goal=current_problem['goal']
                    )
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
        problems[current_problem['name']] = Problem(
            name=current_problem['name'],
            points=current_problem['points'],
            premises=current_problem['premises'],
            goal=current_problem['goal']
        )
    
    logger.info(f"从 {filepath} 解析到 {len(problems)} 道题目")
    return problems


def create_temp_rules_file(base_rules: List[RuleInfo], 
                           independent_rules: List[RuleInfo],
                           temp_dir: Path) -> Path:
    """
    创建临时规则文件，包含基础规则和已发现的独立规则
    """
    temp_rules_path = temp_dir / "temp_rules.txt"
    
    with open(temp_rules_path, 'w', encoding='utf-8') as f:
        # 写入基础规则
        for rule in base_rules:
            f.write(f"{rule.name}\n")
            f.write(f"{rule.content}\n")
        
        # 写入独立规则
        for rule in independent_rules:
            f.write(f"{rule.name}\n")
            f.write(f"{rule.content}\n")
    
    return temp_rules_path


def solve_problem_and_get_proof_rules(problem: Problem, 
                                       rules_path: Path, 
                                       timeout: int = 3600) -> Tuple[bool, List[str], Optional[str]]:
    """
    求解单个题目并提取证明中使用的规则
    
    Returns:
        (solved, used_rules, error)
        - solved: 是否成功求解
        - used_rules: 证明中使用的规则名列表（筛选包含 "sub" 的）
        - error: 错误信息（如果有）
    """
    # 延迟导入，避免循环依赖
    from newclid.api import DirectSolver
    
    try:
        solver = DirectSolver(
            points=problem.points,
            premises=problem.premises,
            goal=problem.goal,
            problem_name=problem.name,
            rules_path=rules_path,
        )
        
        start_time = time.time()
        solved = solver.run(timeout=timeout)
        runtime = time.time() - start_time
        
        used_rules = []
        
        if solved:
            # 获取证明步骤并提取规则名
            try:
                goals = solver.solver.proof.goals
                checked_goals = [goal for goal in goals if goal.check()]
                
                if checked_goals:
                    (
                        points,
                        premises,
                        numercial_checked_premises,
                        trivial_premises,
                        aux_points,
                        aux,
                        numercial_checked_aux,
                        trivial_aux,
                        proof_steps,
                    ) = solver.solver.proof.dep_graph.get_proof_steps(checked_goals)
                    
                    # 从证明步骤中提取规则名
                    for step in proof_steps:
                        reason = step.reason
                        # 筛选包含 "sub" 的规则名（这些是新增的规则）
                        if "sub" in reason.lower():
                            used_rules.append(reason)
                    
                    # 去重
                    used_rules = list(set(used_rules))
            except Exception as e:
                logger.warning(f"提取证明步骤时出错: {e}")
        
        logger.debug(f"  求解用时: {runtime:.2f}s, 成功: {solved}, 使用规则: {used_rules}")
        return solved, used_rules, None
        
    except Exception as e:
        return False, [], str(e)


def split_rules_into_chunks(rules: List[RuleInfo], chunk_size: int) -> List[List[RuleInfo]]:
    """
    按固定块大小切分规则集
    
    Args:
        rules: 待切割的规则列表
        chunk_size: 每个块的规则数量
    
    Returns:
        List[List[RuleInfo]]: 多个规则子集，每个子集最多 chunk_size 条规则
    """
    if chunk_size <= 0:
        return [rules]
    
    chunks = []
    for i in range(0, len(rules), chunk_size):
        chunks.append(rules[i:i + chunk_size])
    
    return chunks


# 进度日志间隔（每处理多少条规则输出一次进度）
PROGRESS_LOG_INTERVAL = 50


def worker_extract_minimal_rules(
    worker_id: int,
    chunk_id: int,
    rules_subset: List[Tuple[str, str]],  # (name, content) 元组列表
    problems_dict: Dict[str, Tuple],  # 序列化的 problem 数据
    base_rules_list: List[Tuple[str, str]],  # (name, content) 元组列表
    timeout: int,
    output_dir: str  # 临时结果输出目录
) -> Tuple[int, List[Tuple[str, str]], Dict[str, List[str]], List[str], str]:
    """
    子进程工作函数：对分配的规则子集执行串行最小规则集提取
    
    Args:
        worker_id: 子进程 ID
        chunk_id: 任务块 ID
        rules_subset: 分配给该子进程的规则子集（序列化格式）
        problems_dict: 所有题目的字典（序列化格式）
        base_rules_list: 基础规则列表（序列化格式）
        timeout: 求解超时时间
        output_dir: 临时结果输出目录
    
    Returns:
        (chunk_id, independent_rules, equivalence_map, errors, result_file)
        - chunk_id: 任务块 ID
        - independent_rules: 独立规则列表（序列化格式）
        - equivalence_map: 等价关系映射
        - errors: 错误信息列表
        - result_file: 结果文件路径
    """
    # 配置子进程日志
    worker_logger = logging.getLogger(f"worker_{worker_id}_chunk_{chunk_id}")
    worker_logger.setLevel(LOG_LEVEL)
    
    # 反序列化数据
    rules = [RuleInfo(name=name, content=content) for name, content in rules_subset]
    base_rules = [RuleInfo(name=name, content=content) for name, content in base_rules_list]
    problems = {
        name: Problem(
            name=data['name'],
            points=[(p[0], p[1], p[2]) for p in data['points']],
            premises=[(pred[0], pred[1]) for pred in data['premises']],
            goal=(data['goal'][0], data['goal'][1])
        )
        for name, data in problems_dict.items()
    }
    
    # 创建子进程临时目录
    temp_dir = Path(tempfile.mkdtemp(prefix=f"worker_{worker_id}_chunk_{chunk_id}_"))
    
    independent_rules: List[RuleInfo] = []
    equivalence_map: Dict[str, List[str]] = {}
    errors: List[str] = []
    
    result_file = ""
    
    try:
        total_rules = len(rules)
        worker_logger.info(f"[Worker {worker_id}] 开始处理第 {chunk_id} 块，共 {total_rules} 条规则")
        
        for idx, rule in enumerate(rules):
            # 进度日志
            processed = idx + 1
            if processed % PROGRESS_LOG_INTERVAL == 0 or processed == total_rules:
                progress_pct = (processed / total_rules) * 100
                worker_logger.info(f"[Worker {worker_id}] 第 {chunk_id} 块进度: {processed}/{total_rules} ({progress_pct:.1f}%)")
            
            # 检查是否有对应的题目
            if rule.name not in problems:
                worker_logger.warning(f"[Worker {worker_id}] 未找到对应题目: {rule.name}")
                continue
            
            problem = problems[rule.name]
            
            # 创建临时规则文件
            temp_rules_path = create_temp_rules_file(base_rules, independent_rules, temp_dir)
            
            # 尝试求解
            solved, used_rules, error = solve_problem_and_get_proof_rules(
                problem, temp_rules_path, timeout
            )
            
            if error:
                errors.append(f"[Worker {worker_id}] {rule.name}: {error}")
                # 出错时保守地将规则视为独立规则
                independent_rules.append(rule)
                equivalence_map[rule.name] = []
            elif solved:
                # 规则可被推导
                equivalence_map[rule.name] = used_rules
            else:
                # 规则是独立规则
                independent_rules.append(rule)
                equivalence_map[rule.name] = []
        
        # 序列化返回结果
        serialized_independent = [(r.name, r.content) for r in independent_rules]
        
        # 将结果写入临时文件
        result_file = Path(output_dir) / f"chunk_{chunk_id}_result.json"
        result_data = {
            "worker_id": worker_id,
            "chunk_id": chunk_id,
            "independent_rules": serialized_independent,
            "equivalence_map": equivalence_map,
            "errors": errors
        }
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False)
        
        worker_logger.info(f"[Worker {worker_id}] 第 {chunk_id} 块完成，独立规则: {len(independent_rules)}/{total_rules}，结果已保存到临时文件")
        
    finally:
        # 清理子进程临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return chunk_id, serialized_independent, equivalence_map, errors, str(result_file)


def final_merge_check(
    candidate_rules: List[RuleInfo],
    all_equivalence_maps: List[Dict[str, List[str]]],
    problems: Dict[str, Problem],
    base_rules: List[RuleInfo],
    timeout: int,
    temp_dir: Path
) -> Tuple[List[RuleInfo], Dict[str, List[str]]]:
    """
    合并阶段：对所有子进程的候选独立规则进行最终验证
    
    1. 合并所有子进程的规则
    2. 对合并的规则进行一次原有的最小规则集提取
    3. 维护等价性归属
    
    Args:
        candidate_rules: 所有子进程发现的独立规则（已合并）
        all_equivalence_maps: 所有子进程的等价关系映射
        problems: 题目字典
        base_rules: 基础规则列表
        timeout: 求解超时时间
        temp_dir: 临时目录
    
    Returns:
        (final_independent_rules, final_equivalence_map)
    """
    logger.info("=" * 60)
    logger.info("合并阶段：对候选独立规则进行最终验证")
    logger.info(f"候选独立规则数量: {len(candidate_rules)}")
    logger.info("=" * 60)
    
    # 1. 合并所有子进程的等价关系映射
    merged_equivalence: Dict[str, List[str]] = {}
    for eq_map in all_equivalence_maps:
        merged_equivalence.update(eq_map)
    
    # 2. 对候选规则按原始顺序排序（按规则名中的数字部分）
    def extract_order_key(rule: RuleInfo) -> Tuple[int, int]:
        """从规则名中提取排序键，如 '5sub_3' -> (5, 3)"""
        try:
            parts = rule.name.replace('sub_', '_').split('_')
            return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except:
            return (999999, 0)
    
    sorted_candidates = sorted(candidate_rules, key=extract_order_key)
    
    # 3. 对合并的规则进行一次最小规则集提取
    final_independent_rules: List[RuleInfo] = []
    
    total_candidates = len(sorted_candidates)
    for idx, rule in enumerate(sorted_candidates):
        logger.info(f"[合并验证 {idx + 1}/{total_candidates}] 规则: {rule.name}")
        
        if rule.name not in problems:
            logger.warning(f"  ⚠️ 未找到对应题目，保守添加为独立规则")
            final_independent_rules.append(rule)
            merged_equivalence[rule.name] = []
            continue
        
        problem = problems[rule.name]
        
        # 创建临时规则文件（包含基础规则 + 已确认的独立规则）
        temp_rules_path = create_temp_rules_file(base_rules, final_independent_rules, temp_dir)
        
        # 尝试求解
        solved, used_rules, error = solve_problem_and_get_proof_rules(
            problem, temp_rules_path, timeout
        )
        
        if error:
            logger.error(f"  ❌ 求解出错: {error}")
            final_independent_rules.append(rule)
            merged_equivalence[rule.name] = []
            logger.info(f"  ➕ 添加为独立规则（因错误）")
        elif solved:
            # 规则可被其他独立规则推导，更新归属关系
            merged_equivalence[rule.name] = used_rules
            if used_rules:
                logger.info(f"  ✅ 可推导，归属于: {used_rules}")
            else:
                logger.info(f"  ✅ 可推导（仅使用基础规则）")
        else:
            # 规则是真正的独立规则
            final_independent_rules.append(rule)
            merged_equivalence[rule.name] = []
            logger.info(f"  ➕ 确认为独立规则")
    
    logger.info("=" * 60)
    logger.info(f"合并验证完成：最终独立规则 {len(final_independent_rules)} 条")
    logger.info("=" * 60)
    
    return final_independent_rules, merged_equivalence


def extract_minimal_rules_parallel():
    """
    并行版本：提取最小独立规则集
    
    三阶段处理：
    1. 分割阶段：将规则集按固定块大小切割成多个任务块
    2. 并行阶段：多进程并行处理各任务块（最多 MAX_WORKERS 个并行）
    3. 合并阶段：合并结果并进行最终验证
    """
    start_time = time.time()
    
    logger.info("=" * 60)
    logger.info("开始并行提取最小独立规则集")
    logger.info(f"最大并行进程数: {MAX_WORKERS}")
    logger.info(f"每个任务块大小: {CHUNK_SIZE}")
    logger.info("=" * 60)
    
    # ==================== 阶段 1: 加载数据 ====================
    logger.info("阶段 1: 加载数据...")
    phase1_start = time.time()
    
    base_rules = parse_base_rules(BASE_RULES_FILE)
    extracted_rules = parse_extracted_rules(EXTRACTED_RULES_FILE)
    problems = parse_problems_file(REBUILD_PROBLEMS_FILE)
    
    logger.info(f"阶段 1 完成，耗时: {time.time() - phase1_start:.2f}s")
    
    # ==================== 阶段 2: 分割规则集 ====================
    logger.info("阶段 2: 分割规则集...")
    phase2_start = time.time()
    
    # 按固定块大小切割规则集
    rule_chunks = split_rules_into_chunks(extracted_rules, CHUNK_SIZE)
    total_chunks = len(rule_chunks)
    
    # 确定实际使用的进程数
    actual_workers = min(MAX_WORKERS, total_chunks)
    
    logger.info(f"  总规则数: {len(extracted_rules)}")
    logger.info(f"  任务块数: {total_chunks}")
    logger.info(f"  实际并行进程数: {actual_workers}")
    
    for i, chunk in enumerate(rule_chunks):
        logger.info(f"  任务块 {i}: {len(chunk)} 条规则")
    
    logger.info(f"阶段 2 完成，耗时: {time.time() - phase2_start:.2f}s")
    
    # ==================== 阶段 3: 准备序列化数据 ====================
    logger.info("阶段 3: 准备并行处理数据...")
    phase3_start = time.time()
    
    # 序列化基础规则
    base_rules_serialized = [(r.name, r.content) for r in base_rules]
    
    # 序列化题目数据
    problems_serialized = {
        name: {
            'name': p.name,
            'points': [(pt[0], pt[1], pt[2]) for pt in p.points],
            'premises': [(pred[0], pred[1]) for pred in p.premises],
            'goal': (p.goal[0], p.goal[1])
        }
        for name, p in problems.items()
    }
    
    # 序列化规则子集
    rule_chunks_serialized = [
        [(r.name, r.content) for r in chunk]
        for chunk in rule_chunks
    ]
    
    # 创建临时输出目录
    output_temp_dir = Path(tempfile.mkdtemp(prefix="parallel_results_"))
    logger.info(f"临时结果目录: {output_temp_dir}")
    
    logger.info(f"阶段 3 完成，耗时: {time.time() - phase3_start:.2f}s")
    
    # ==================== 阶段 4: 并行处理 ====================
    logger.info("阶段 4: 并行处理...")
    phase4_start = time.time()
    
    all_independent_rules: List[RuleInfo] = []
    all_equivalence_maps: List[Dict[str, List[str]]] = []
    all_errors: List[str] = []
    completed_chunks = 0
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=actual_workers) as executor:
        # 提交所有任务块
        futures = {}
        for chunk_id in range(total_chunks):
            # worker_id 循环使用，chunk_id 唯一标识任务块
            worker_id = chunk_id % actual_workers
            future = executor.submit(
                worker_extract_minimal_rules,
                worker_id,
                chunk_id,
                rule_chunks_serialized[chunk_id],
                problems_serialized,
                base_rules_serialized,
                TIMEOUT,
                str(output_temp_dir)
            )
            futures[future] = chunk_id
        
        # 收集结果
        for future in concurrent.futures.as_completed(futures):
            chunk_id = futures[future]
            try:
                ret_chunk_id, independent, eq_map, errors, result_file = future.result()
                
                # 反序列化独立规则
                for name, content in independent:
                    all_independent_rules.append(RuleInfo(name=name, content=content))
                
                all_equivalence_maps.append(eq_map)
                all_errors.extend(errors)
                
                completed_chunks += 1
                logger.info(f"任务块 {ret_chunk_id} 完成 ({completed_chunks}/{total_chunks}): {len(independent)} 条独立规则")
                
            except Exception as e:
                logger.error(f"任务块 {chunk_id} 失败: {e}")
                # 失败时将该 chunk 的所有规则保守地视为独立规则
                for name, content in rule_chunks_serialized[chunk_id]:
                    all_independent_rules.append(RuleInfo(name=name, content=content))
                all_equivalence_maps.append({name: [] for name, _ in rule_chunks_serialized[chunk_id]})
                completed_chunks += 1
    
    logger.info(f"阶段 4 完成，耗时: {time.time() - phase4_start:.2f}s")
    logger.info(f"  总候选独立规则: {len(all_independent_rules)}")
    logger.info(f"  错误数量: {len(all_errors)}")
    
    # 清理临时结果目录
    shutil.rmtree(output_temp_dir, ignore_errors=True)
    
    # ==================== 阶段 5: 合并与最终验证 ====================
    logger.info("阶段 5: 合并与最终验证...")
    phase5_start = time.time()
    
    # 创建临时目录
    temp_dir = Path(tempfile.mkdtemp(prefix="final_merge_"))
    
    try:
        final_independent_rules, final_equivalence_map = final_merge_check(
            all_independent_rules,
            all_equivalence_maps,
            problems,
            base_rules,
            TIMEOUT,
            temp_dir
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    logger.info(f"阶段 5 完成，耗时: {time.time() - phase5_start:.2f}s")
    
    # ==================== 阶段 6: 输出结果 ====================
    logger.info("阶段 6: 输出结果...")
    phase6_start = time.time()
    
    # 确保输出目录存在
    Path(OUTPUT_MINIMAL_RULES_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_EQUIVALENCE_FILE).parent.mkdir(parents=True, exist_ok=True)
    
    # 写入最小独立规则集
    with open(OUTPUT_MINIMAL_RULES_FILE, 'w', encoding='utf-8') as f:
        for rule in final_independent_rules:
            f.write(f"{rule.name}\n")
            f.write(f"{rule.content}\n")
    logger.info(f"最小独立规则集已保存到: {OUTPUT_MINIMAL_RULES_FILE}")
    
    # 写入等价关系映射
    with open(OUTPUT_EQUIVALENCE_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_equivalence_map, f, indent=2, ensure_ascii=False)
    logger.info(f"等价关系映射已保存到: {OUTPUT_EQUIVALENCE_FILE}")
    
    logger.info(f"阶段 6 完成，耗时: {time.time() - phase6_start:.2f}s")
    
    # 打印统计信息
    total_time = time.time() - start_time
    logger.info("=" * 60)
    logger.info("统计信息:")
    logger.info(f"  - 提取的规则总数: {len(extracted_rules)}")
    logger.info(f"  - 最终独立规则数量: {len(final_independent_rules)}")
    logger.info(f"  - 可推导规则数量: {len(extracted_rules) - len(final_independent_rules)}")
    logger.info(f"  - 总耗时: {total_time:.2f}s ({total_time/60:.2f}min)")
    logger.info("=" * 60)


def extract_minimal_rules():
    """
    主算法：提取最小独立规则集
    """
    logger.info("=" * 60)
    logger.info("开始提取最小独立规则集")
    logger.info("=" * 60)
    
    # 1. 加载基础规则
    logger.info("步骤 1: 加载基础规则...")
    base_rules = parse_base_rules(BASE_RULES_FILE)
    
    # 2. 加载提取的规则
    logger.info("步骤 2: 加载提取的规则...")
    extracted_rules = parse_extracted_rules(EXTRACTED_RULES_FILE)
    
    # 3. 加载重建的题目
    logger.info("步骤 3: 加载重建的题目...")
    problems = parse_problems_file(REBUILD_PROBLEMS_FILE)
    
    # 4. 初始化数据结构
    independent_rules: List[RuleInfo] = []  # 独立规则集 I
    equivalence_map: Dict[str, List[str]] = {}  # 等价关系 E: 规则名 -> 归属的独立规则列表
    
    # 创建临时目录
    temp_dir = Path(tempfile.mkdtemp(prefix="minimal_rules_"))
    logger.info(f"临时目录: {temp_dir}")
    
    try:
        # 5. 遍历每条规则
        logger.info("步骤 4: 遍历每条规则，检测等价性...")
        total_rules = len(extracted_rules)
        
        for idx, rule in enumerate(extracted_rules):
            logger.info(f"[{idx + 1}/{total_rules}] 处理规则: {rule.name}")
            
            # 检查是否有对应的题目
            if rule.name not in problems:
                logger.warning(f"  ⚠️ 未找到对应的题目，跳过")
                continue
            
            problem = problems[rule.name]
            
            # 创建临时规则文件（包含基础规则 + 已发现的独立规则）
            temp_rules_path = create_temp_rules_file(base_rules, independent_rules, temp_dir)
            
            # 尝试求解
            solved, used_rules, error = solve_problem_and_get_proof_rules(
                problem, temp_rules_path, TIMEOUT
            )
            
            if error:
                logger.error(f"  ❌ 求解出错: {error}")
                # 出错时保守地将规则视为独立规则
                independent_rules.append(rule)
                equivalence_map[rule.name] = []
                logger.info(f"  ➕ 添加为独立规则（因错误）: {rule.name}")
            elif solved:
                # 规则可被推导，记录归属关系
                equivalence_map[rule.name] = used_rules
                if used_rules:
                    logger.info(f"  ✅ 可推导，归属于: {used_rules}")
                else:
                    logger.info(f"  ✅ 可推导（仅使用基础规则）")
            else:
                # 规则是独立规则
                independent_rules.append(rule)
                equivalence_map[rule.name] = []
                logger.info(f"  ➕ 添加为独立规则: {rule.name}")
        
        # 6. 输出结果
        logger.info("=" * 60)
        logger.info("步骤 5: 输出结果...")
        
        # 确保输出目录存在
        Path(OUTPUT_MINIMAL_RULES_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(OUTPUT_EQUIVALENCE_FILE).parent.mkdir(parents=True, exist_ok=True)
        
        # 写入最小独立规则集
        with open(OUTPUT_MINIMAL_RULES_FILE, 'w', encoding='utf-8') as f:
            for rule in independent_rules:
                f.write(f"{rule.name}\n")
                f.write(f"{rule.content}\n")
        logger.info(f"最小独立规则集已保存到: {OUTPUT_MINIMAL_RULES_FILE}")
        
        # 写入等价关系映射
        with open(OUTPUT_EQUIVALENCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(equivalence_map, f, indent=2, ensure_ascii=False)
        logger.info(f"等价关系映射已保存到: {OUTPUT_EQUIVALENCE_FILE}")
        
        # 打印统计信息
        logger.info("=" * 60)
        logger.info("统计信息:")
        logger.info(f"  - 提取的规则总数: {len(extracted_rules)}")
        logger.info(f"  - 独立规则数量: {len(independent_rules)}")
        logger.info(f"  - 可推导规则数量: {len(extracted_rules) - len(independent_rules)}")
        logger.info("=" * 60)
        
    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("临时目录已清理")


def main():
    """入口函数"""
    if PARALLEL_MODE:
        logger.info("使用并行模式")
        extract_minimal_rules_parallel()
    else:
        logger.info("使用串行模式")
        extract_minimal_rules()


if __name__ == "__main__":
    main()
