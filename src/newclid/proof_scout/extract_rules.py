import json
import string
import pathlib
import os
import re
from tqdm import tqdm  # 如果没有安装 tqdm，可以注释掉相关行
from typing import Set, Dict, List, Tuple, Optional

# 引入类
from proof_graph import ProofGraph
from proof_graph_pruner import GraphPruner
from proof_graph_visualizer import ProofGraphVisualizer

# 配置路径

FILE_PROFIX = "geometry_clauses10_samples50"  # 文件前缀标识符
FILE_PROFIX_SHORT = "c10s50"  # 文件前缀标识符
# FILE_PROFIX_SHORT = FILE_PROFIX.replace("geometry_clauses", "c").replace("_samples", "s")

RAW_INPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/generated_data/{FILE_PROFIX}.jsonl"  # 输入文件名
INTERMEDIATE = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_intermediate.jsonl"  # 中间文件名
RULE_OUTPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_rules.txt" # 输出文件名
SELECTED_SUBGRAPHS_OUTPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_selected_subgraphs.jsonl"  # 最终去重后保留的子图(用于最终渲染)
ENABLE_RULE_NORMALIZATION = True  # 是否启用规则规范化
NORM_RULE_OUTPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_rules_norm.txt" # 输出文件名
RENDER_SUBGRAPHS = False  # 是否渲染提取出的子图用于调试
RENDER_DIR = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/proof_graphs/{FILE_PROFIX_SHORT}/"  # 渲染输出目录
ENABLE_REBUILD_PROBLEMS = True  # 是否重建题目
REBUILD_OUTPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/{FILE_PROFIX_SHORT}_rules_rebuild.txt"  # 重建题目输出文件

def stage_extract_subgraphs(input_file: str, intermediate_file: str):
    pruner = GraphPruner(verbose=False)
    count = 0
    input_idx = 0
    
    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(intermediate_file, 'w', encoding='utf-8') as f_out:
        
        lines = f_in.readlines()
        for line in tqdm(lines, desc="Extracting"):
            line = line.strip()
            if not line: continue
            
            try:
                data = json.loads(line)
                pg = ProofGraph(verbose=False)
                pg.problem_id = str(input_idx)
                input_idx += 1
                pg.build_from_json(data)
                
                # 剪枝提取
                sub_entries = pruner.prune_and_extract(pg)
                
                for entry in sub_entries:
                    sub_pg = entry["subgraph_object"]
                    # 序列化为 JSON 结构
                    json_data = sub_pg.to_json_data()
                    
                    # 写入中间文件
                    f_out.write(json.dumps(json_data) + "\n")
                    count += 1
                    
            except Exception as e:
                print(f"Error processing line: {e}")

def stage_deduplicate_and_export(
    intermediate_file: str,
    rules_output_file: str,
    selected_subgraphs_output_file: str,
    enable_rule_normalization: bool = True,
):
    unique_signatures: Set[str] = set()
    dedup_count = 0
    total_read = 0
    kept_final = 0

    alphabet = string.ascii_lowercase

    def get_canonical_name(index: int) -> str:
        if index < 26:
            return alphabet[index]
        return f"{alphabet[index % 26]}{index // 26}"

    def is_constant_token(tok: str) -> bool:
        if "/" in tok:
            return True
        try:
            float(tok)
            return True
        except ValueError:
            return False

    def normalize_rule_line(rule_line: str) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
        """把单行规则 'lhs => rhs' 规范化为同格式；若被过滤则返回 (None, None)。
        返回: (规范化后的规则字符串, 规范化映射表 {原变量名 -> 新变量名})
        """
        if "=>" not in rule_line:
            return None, None

        lhs_str, rhs_str = rule_line.split("=>", 1)
        premises_raw = [p.strip() for p in lhs_str.split(",") if p.strip()]

        parsed_premises: list[tuple[str, list[str]]] = []
        for p_str in premises_raw:
            parts = p_str.split()
            if parts:
                parsed_premises.append((parts[0], parts[1:]))

        conclusion_raw = rhs_str.strip()
        parsed_conclusion: tuple[str, list[str]] | None = None
        if conclusion_raw and conclusion_raw != "null":
            parts = conclusion_raw.split()
            if parts:
                parsed_conclusion = (parts[0], parts[1:])

        # 1) 前提按谓词名排序，保证一致性
        parsed_premises.sort(key=lambda x: (x[0]))

        # 2) 变量重命名
        rename_map: dict[str, str] = {}
        next_var_idx = 0

        def map_vars(args: list[str]) -> list[str]:
            nonlocal next_var_idx
            new_args: list[str] = []
            for arg in args:
                if is_constant_token(arg):
                    new_args.append(arg)
                    continue
                if arg not in rename_map:
                    rename_map[arg] = get_canonical_name(next_var_idx)
                    next_var_idx += 1
                new_args.append(rename_map[arg])
            return new_args

        contain_con_sim = False
        norm_premises: list[str] = []
        for pred, args in parsed_premises:
            new_args = map_vars(args)
            norm_premises.append(f"{pred} {' '.join(new_args)}")
            if pred in ["contri", "simtri", "contrir", "simtrir"]:
                contain_con_sim = True
        if contain_con_sim:
            return None, None

        norm_conclusion = "null"
        if parsed_conclusion:
            pred, args = parsed_conclusion
            new_args = map_vars(args)
            norm_conclusion = f"{pred} {' '.join(new_args)}"

        return f"{', '.join(norm_premises)} => {norm_conclusion}", rename_map
    
    with open(intermediate_file, 'r', encoding='utf-8') as f_in, \
         open(rules_output_file, 'w', encoding='utf-8') as f_out, \
         open(selected_subgraphs_output_file, 'w', encoding='utf-8') as f_sel:
        
        lines = f_in.readlines()
        for line in tqdm(lines, desc="Processing"):
            line = line.strip()
            if not line: continue
            
            total_read += 1
            data = json.loads(line)
            
            # 1. 重建 ProofGraph 对象
            pg = ProofGraph(verbose=False)
            try:
                pg.build_from_json(data)
            except Exception as e:
                print(f"Rebuild error: {e}")
                continue
            
            # 2. 计算签名并去重
            # 这里的签名仅包含谓词，如果你需要包含变量关系的去重(结构同构)，需要更复杂的算法
            sig = pg.get_rule_signature()
            
            if sig in unique_signatures:
                continue
            
            unique_signatures.add(sig)
            dedup_count += 1

            # 3. 导出规则文本（两行）
            rule_text = pg.export_to_rule_format()
            rule_lines = [ln.strip() for ln in rule_text.splitlines() if ln.strip()]
            if len(rule_lines) < 2:
                continue
            pid_line = rule_lines[0]
            rule_line = rule_lines[1]

            # 4. 规范化（可选）并过滤；只写入最终保留下来的部分
            norm_rename_map = None  # 规范化时产生的变量映射
            if enable_rule_normalization:
                norm_line, norm_rename_map = normalize_rule_line(rule_line)
                if norm_line is None:
                    continue
                f_out.write(f"{pid_line}\n")
                f_out.write(f"{norm_line}\n")
            else:
                f_out.write(f"{pid_line}\n")
                f_out.write(f"{rule_line}\n")

            # 5. 保存最终选中的子图 JSON（与最终 rules 一一对应）
            json_data = pg.to_json_data()
            # 保存规范化映射（如果启用了规范化）
            if norm_rename_map is not None:
                json_data["norm_rename_map"] = norm_rename_map
            f_sel.write(json.dumps(json_data) + "\n")
            kept_final += 1

    print(
        f"Stage2 done: read={total_read}, unique_dedup={dedup_count}, kept_final={kept_final}, "
        f"rules_out={rules_output_file}, selected_subgraphs_out={selected_subgraphs_output_file}"
    )


def render_final_graphs(final_rules_file: str, selected_subgraphs_file: str, raw_input_file: str, render_dir: str):
    """在 normalize_rules_file 之后统一渲染：
    - sub_graph: 由去重后保留的子图 JSON 重建
    - full_graph: 通过 pid 解析出原题号，在 RAW_INPUT 中重建完整图
    命名规则（pid等）不修改，仅将渲染移动到最后。
    """

    # 1) 读取最终保留的子图（去重后）: pid -> json
    selected_subgraphs = {}
    with open(selected_subgraphs_file, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            pid = str(obj.get("id", ""))
            if pid:
                selected_subgraphs[pid] = obj

    # 2) 读取 RAW_INPUT 所有行，便于按 index 随机访问
    with open(raw_input_file, 'r', encoding='utf-8') as f_raw:
        raw_lines = [ln for ln in f_raw.read().splitlines() if ln.strip()]

    # 3) 解析最终 rules 文件（两行一组）并渲染
    pathlib.Path(render_dir).mkdir(parents=True, exist_ok=True)
    with open(final_rules_file, 'r', encoding='utf-8') as f_rules:
        lines = [ln.strip() for ln in f_rules.readlines()]

    for i in tqdm(range(0, len(lines), 2), desc="Rendering"):
        if i + 1 >= len(lines):
            break

        pid = lines[i].strip()
        if not pid:
            continue

        sub_obj = selected_subgraphs.get(pid)
        if sub_obj is None:
            print(f"[render] skip pid={pid}: subgraph json not found in {selected_subgraphs_file}")
            continue

        # --- sub_graph 渲染（文件名保持旧逻辑不变）---
        try:
            sub_pg = ProofGraph(verbose=False)
            sub_pg.build_from_json(sub_obj)
            sub_render_path = os.path.join(render_dir, f"rule_norm_{pid}.png")
            sub_vis = ProofGraphVisualizer(sub_pg)
            sub_vis.build_graphviz_structure()
            sub_vis.render(sub_render_path)
        except Exception as e:
            print(f"[render] sub_graph failed pid={pid}: {e}")

        # --- full_graph 渲染 ---
        try:
            m = re.match(r"^(\d+)", pid)
            if not m:
                print(f"[render] skip full_graph pid={pid}: cannot parse source problem index")
                continue

            full_idx = int(m.group(1))
            if full_idx < 0 or full_idx >= len(raw_lines):
                print(f"[render] skip full_graph pid={pid}: source index out of range ({full_idx})")
                continue

            full_data = json.loads(raw_lines[full_idx])
            full_pg = ProofGraph(verbose=False)
            # RAW_INPUT 不含 id/problem_id，必须手动赋值以保证一致
            full_pg.problem_id = str(full_idx)
            full_pg.build_from_json(full_data)

            full_render_path = os.path.join(render_dir, f"rule_norm_{full_idx}.png")
            full_vis = ProofGraphVisualizer(full_pg)
            full_vis.build_graphviz_structure()
            full_vis.render(full_render_path)
        except Exception as e:
            print(f"[render] full_graph failed pid={pid}: {e}")


def stage_rebuild_problems(
    rules_file: str,
    selected_subgraphs_file: str,
    raw_input_file: str,
    output_file: str,
):
    """
    Stage 3: 根据提取的规则和子图重建题目
    
    重建问题的核心在于正确处理两层映射：
    1. 原始数据中的 rename_map: 原始点名 -> llm_input_renamed 中的点名
    2. 规范化时的 norm_rename_map: llm_input_renamed 中的点名 -> 规范化后的点名 (a, b, c...)
    
    坐标链: fl_problem 中的原始坐标 -> rename_map -> norm_rename_map -> 最终规则中的点名
    """
    
    def parse_fl_problem(fl_problem: str) -> Dict[str, Tuple[str, str]]:
        """解析 fl_problem，提取点名和坐标"""
        points_coords = {}
        pattern = r'(\w+)@(-?[\d.]+)_(-?[\d.]+)'
        matches = re.findall(pattern, fl_problem)
        for match in matches:
            point_name = match[0]
            x = match[1]
            y = match[2]
            points_coords[point_name] = (x, y)
        return points_coords
    
    def parse_rule(rule_text: str) -> Tuple[List[str], str]:
        """解析规则文本，提取前提和目标"""
        parts = rule_text.split('=>')
        if len(parts) != 2:
            raise ValueError(f"规则格式错误，应包含 '=>': {rule_text}")
        premises_str = parts[0].strip()
        goal_str = parts[1].strip()
        premises = [p.strip() for p in premises_str.split(',')]
        return premises, goal_str
    
    def extract_points_from_predicates(predicates: List[str]) -> Set[str]:
        """从谓词列表中提取所有点名"""
        points = set()
        for pred in predicates:
            tokens = pred.split()
            for token in tokens[1:]:  # 跳过谓词名
                if token.isalpha() or (len(token) <= 3 and token[0].isalpha()):
                    points.add(token)
        return points
    
    def parse_rule_name(rule_name: str) -> Tuple[Optional[int], Optional[int]]:
        """解析规则名称，提取ID: {id}sub_{sub_id}"""
        match = re.match(r'(\d+)sub_(\d+)', rule_name)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None, None
    
    # 1) 加载原始数据（用于获取 fl_problem 和 rename_map）
    print(f"  Loading raw data from: {raw_input_file}")
    raw_data = []
    with open(raw_input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                raw_data.append(json.loads(line))
    print(f"    Loaded {len(raw_data)} raw entries")
    
    # 2) 加载选中的子图（用于获取 norm_rename_map）
    print(f"  Loading selected subgraphs from: {selected_subgraphs_file}")
    subgraph_data = {}  # pid -> subgraph_json
    with open(selected_subgraphs_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                obj = json.loads(line)
                pid = str(obj.get("id", ""))
                if pid:
                    subgraph_data[pid] = obj
    print(f"    Loaded {len(subgraph_data)} subgraphs")
    
    # 3) 加载规则文件（两行一组）
    print(f"  Loading rules from: {rules_file}")
    rules = []
    with open(rules_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        rule_name = lines[i].strip()
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        rule_text = lines[i].strip()
        i += 1
        rules.append((rule_name, rule_text))
    print(f"    Loaded {len(rules)} rules")
    
    # 4) 重建每条规则对应的题目
    results = []
    errors = []
    
    for rule_name, rule_text in tqdm(rules, desc="Rebuilding"):
        rule_id, sub_id = parse_rule_name(rule_name)
        
        if rule_id is None:
            errors.append(f"无法解析规则名称: {rule_name}")
            continue
        
        if rule_id < 0 or rule_id >= len(raw_data):
            errors.append(f"规则 {rule_name}: 原始数据索引 {rule_id} 超出范围")
            continue
        
        raw_entry = raw_data[rule_id]
        subgraph_entry = subgraph_data.get(rule_name)
        
        if subgraph_entry is None:
            errors.append(f"规则 {rule_name}: 未找到对应的子图数据")
            continue
        
        try:
            # 解析规则
            premises, goal = parse_rule(rule_text)
            all_predicates = premises + [goal]
            used_points = extract_points_from_predicates(all_predicates)
            
            # 获取原始坐标
            fl_problem = raw_entry.get('fl_problem', '')
            original_coords = parse_fl_problem(fl_problem)
            
            # 获取两层映射
            # rename_map: 原始点名 -> llm_input 中的点名
            rename_map = raw_entry.get('rename_map', {})
            # norm_rename_map: llm_input 中的点名 -> 规范化后的点名
            norm_rename_map = subgraph_entry.get('norm_rename_map', {})
            
            # 构建反向映射: 规范化后的点名 -> llm_input 中的点名
            norm_to_llm = {v: k for k, v in norm_rename_map.items()} if norm_rename_map else {}
            # 构建反向映射: llm_input 中的点名 -> 原始点名
            llm_to_original = {v: k for k, v in rename_map.items()}
            
            # 整理点和坐标
            points_output = {}
            missing_points = []
            
            for point in sorted(used_points):
                # 规范化后的点名 -> llm_input 中的点名
                llm_name = norm_to_llm.get(point, point)
                # llm_input 中的点名 -> 原始点名
                original_name = llm_to_original.get(llm_name, llm_name)
                
                if original_name in original_coords:
                    coords = original_coords[original_name]
                    points_output[point] = coords
                else:
                    missing_points.append(f"{point} (llm:{llm_name}, orig:{original_name})")
            
            # 格式化输出
            result_lines = []
            result_lines.append("Rule Name:")
            result_lines.append(f"{rule_name}")
            result_lines.append("Points:")
            for point in sorted(points_output.keys()):
                x, y = points_output[point]
                result_lines.append(f"{point}:{x},{y}")
            result_lines.append("Premises:")
            for premise in premises:
                result_lines.append(premise)
            result_lines.append("Goal:")
            result_lines.append(goal)
            
            results.append((rule_name, '\n'.join(result_lines), missing_points))
            
        except Exception as e:
            errors.append(f"规则 {rule_name} 处理出错: {str(e)}")
    
    # 5) 写入输出文件
    pathlib.Path(os.path.dirname(output_file)).mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for rule_name, problem, missing in results:
            f.write(problem)
            if missing:
                f.write(f"\n# 警告: 缺失点坐标: {', '.join(missing)}")
            f.write("\n\n")
    
    print(f"  Rebuild done: success={len(results)}, errors={len(errors)}")
    print(f"  Output: {output_file}")
    
    if errors:
        print(f"  Errors (first 10):")
        for err in errors[:10]:
            print(f"    - {err}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")
    
    return results, errors


if __name__ == "__main__":
    # 运行处理
    print(f"=== Stage 1: Extracting Subgraphs to {INTERMEDIATE} ===")
    stage_extract_subgraphs(RAW_INPUT, INTERMEDIATE)
    final_rules = NORM_RULE_OUTPUT if ENABLE_RULE_NORMALIZATION else RULE_OUTPUT
    print(f"=== Stage 2: Deduplicating+Normalizing Exporting to {final_rules} ===")
    stage_deduplicate_and_export(
        INTERMEDIATE,
        final_rules,
        SELECTED_SUBGRAPHS_OUTPUT,
        enable_rule_normalization=ENABLE_RULE_NORMALIZATION,
    )

    # Stage 3: 重建题目
    if ENABLE_REBUILD_PROBLEMS:
        print(f"=== Stage 3: Rebuilding Problems to {REBUILD_OUTPUT} ===")
        stage_rebuild_problems(
            final_rules,
            SELECTED_SUBGRAPHS_OUTPUT,
            RAW_INPUT,
            REBUILD_OUTPUT,
        )

    # Stage 4: 最终统一渲染（放在 normalize 之后；若未启用 normalize，则使用 RULE_OUTPUT）
    if RENDER_SUBGRAPHS:
        print(f"=== Stage 4: Rendering Final Graphs from {final_rules} ===")
        render_final_graphs(final_rules, SELECTED_SUBGRAPHS_OUTPUT, RAW_INPUT, RENDER_DIR)