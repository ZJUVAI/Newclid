import json
import string
import pathlib
import os
import re
from tqdm import tqdm  # 如果没有安装 tqdm，可以注释掉相关行
from typing import Set

# 引入类
from proof_graph import ProofGraph
from proof_graph_pruner import GraphPruner
from proof_graph_visualizer import ProofGraphVisualizer

# 配置路径

FILE_PROFIX = "geometry_clauses5_samples10k"  # 文件前缀标识符
FILE_PROFIX_SHORT = "c5s10k"  # 文件前缀标识符
# FILE_PROFIX_SHORT = FILE_PROFIX.replace("geometry_clauses", "c").replace("_samples", "s")

RAW_INPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/{FILE_PROFIX}.jsonl"  # 输入文件名
INTERMEDIATE = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_intermediate.jsonl"  # 中间文件名
RULE_OUTPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_rules.txt" # 输出文件名
SELECTED_SUBGRAPHS_OUTPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_selected_subgraphs.jsonl"  # 最终去重后保留的子图(用于最终渲染)
ENABLE_RULE_NORMALIZATION = True  # 是否启用规则规范化
NORM_RULE_OUTPUT = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/{FILE_PROFIX_SHORT}_rules_norm.txt" # 输出文件名
RENDER_SUBGRAPHS = True  # 是否渲染提取出的子图用于调试
RENDER_DIR = f"/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/proof_graphs/{FILE_PROFIX_SHORT}/"  # 渲染输出目录

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

    def normalize_rule_line(rule_line: str) -> str | None:
        """把单行规则 'lhs => rhs' 规范化为同格式；若被过滤则返回 None。"""
        if "=>" not in rule_line:
            return None

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
            return None

        norm_conclusion = "null"
        if parsed_conclusion:
            pred, args = parsed_conclusion
            new_args = map_vars(args)
            norm_conclusion = f"{pred} {' '.join(new_args)}"

        return f"{', '.join(norm_premises)} => {norm_conclusion}"
    
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
            if enable_rule_normalization:
                norm_line = normalize_rule_line(rule_line)
                if norm_line is None:
                    continue
                f_out.write(f"{pid_line}\n")
                f_out.write(f"{norm_line}\n")
            else:
                f_out.write(f"{pid_line}\n")
                f_out.write(f"{rule_line}\n")

            # 5. 保存最终选中的子图 JSON（与最终 rules 一一对应）
            json_data = pg.to_json_data()
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

    # Stage 4: 最终统一渲染（放在 normalize 之后；若未启用 normalize，则使用 RULE_OUTPUT）
    if RENDER_SUBGRAPHS:
        print(f"=== Stage 4: Rendering Final Graphs from {final_rules} ===")
        render_final_graphs(final_rules, SELECTED_SUBGRAPHS_OUTPUT, RAW_INPUT, RENDER_DIR)