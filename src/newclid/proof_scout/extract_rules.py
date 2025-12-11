import json
import string
import os
import hashlib
import logging
from tqdm import tqdm  # 如果没有安装 tqdm，可以注释掉相关行
from typing import Set, Dict, List

# 引入类
from proof_graph import ProofGraph
from proof_graph_pruner import GraphPruner

# 配置路径
RAW_INPUT = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/geometry_clauses5_samples100.jsonl"  # 输入文件名
INTERMEDIATE = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/c5s10k_intermediate.jsonl"  # 中间文件名
RULE_OUTPUT = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/c5s10k_rules.txt" # 输出文件名
ENABLE_RULE_NORMALIZATION = True
NORM_RULE_OUTPUT = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/extracted_rules/c5s10k_rules_norm.txt" # 输出文件名

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

def stage_deduplicate_and_export(intermediate_file: str, rules_output_file: str):
    unique_signatures: Set[str] = set()
    dedup_count = 0
    total_read = 0
    
    with open(intermediate_file, 'r', encoding='utf-8') as f_in, \
         open(rules_output_file, 'w', encoding='utf-8') as f_out:
        
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
            
            # 3. 渲染 (这里调用 print_graph 模拟渲染，你可以替换为 draw_graph 等实际渲染函数)
            # print(f"Rendering unique rule: {sig}")
            # pg.print_graph()  # 或者 pg.render_to_file(...)
            
            # 4. 导出规则文本
            # 复用之前写的 export_to_rule_format
            rule_text = pg.export_to_rule_format()
            f_out.write(rule_text + "\n")

def normalize_rules_file(input_path: str, output_path: str):
    """
    读取规则文件，对每一条规则进行规范化处理：
    1. 按照谓词字母序对前提(Premises)进行排序。
    2. 按顺序重新映射变量名为 a, b, c...
    3. 写入输出文件。
    
    Args:
        input_path: 原始 rules.txt 路径
        output_path: 处理后的 rules_norm.txt 路径
    """
    
    # 准备变量名生成器 (a-z, 然后 a1-z1...)
    alphabet = string.ascii_lowercase
    def get_canonical_name(index):
        if index < 26:
            return alphabet[index]
        else:
            return f"{alphabet[index % 26]}{index // 26}"

    print(f"Normalizing rules from {input_path} to {output_path}...")
    
    with open(input_path, 'r', encoding='utf-8') as f_in, \
         open(output_path, 'w', encoding='utf-8') as f_out:
        
        lines = f_in.readlines()
        
        # 规则文件格式是两行一组：
        # Line 1: problem_id
        # Line 2: premise => conclusion
        for i in range(0, len(lines), 2):
            if i + 1 >= len(lines):
                break
                
            pid_line = lines[i].strip()
            rule_line = lines[i+1].strip()
            
            if "=>" not in rule_line:
                continue
                
            # 1. 解析规则字符串
            lhs_str, rhs_str = rule_line.split("=>")
            
            # 提取前提 (Premises)
            # 格式: "pred1 a b, pred2 c d" -> [("pred1", ["a", "b"]), ("pred2", ["c", "d"])]
            premises_raw = [p.strip() for p in lhs_str.split(",") if p.strip()]
            parsed_premises = []
            for p_str in premises_raw:
                parts = p_str.split()
                if parts:
                    parsed_premises.append((parts[0], parts[1:]))
            
            # 提取结论 (Conclusion)
            conclusion_raw = rhs_str.strip()
            parsed_conclusion = None
            if conclusion_raw and conclusion_raw != "null":
                parts = conclusion_raw.split()
                if parts:
                    parsed_conclusion = (parts[0], parts[1:])

            # 2. 对前提进行排序
            # 排序是为了去重的一致性：确保 "A, B => C" 和 "B, A => C" 被处理成相同的规范形式
            # 排序键：谓词名称 -> 参数数量 -> 原始参数字符串
            parsed_premises.sort(key=lambda x: (x[0], len(x[1]), " ".join(x[1])))
            
            # 3. 变量重命名 (Renaming)
            rename_map = {}
            next_var_idx = 0
            
            def map_vars(args):
                nonlocal next_var_idx
                new_args = []
                for arg in args:
                    if arg not in rename_map:
                        rename_map[arg] = get_canonical_name(next_var_idx)
                        next_var_idx += 1
                    new_args.append(rename_map[arg])
                return new_args

            # 重构前提字符串
            norm_premises = []
            for pred, args in parsed_premises:
                new_args = map_vars(args)
                norm_premises.append(f"{pred} {' '.join(new_args)}")
            
            # 重构结论字符串
            norm_conclusion = "null"
            if parsed_conclusion:
                pred, args = parsed_conclusion
                new_args = map_vars(args) # 继续使用同一个 map，保证输入输出变量对应
                norm_conclusion = f"{pred} {' '.join(new_args)}"
            
            # 4. 写入文件
            f_out.write(f"{pid_line}\n")
            f_out.write(f"{', '.join(norm_premises)} => {norm_conclusion}\n")

    print("Normalization complete.")

if __name__ == "__main__":
    # 运行处理
    print(f"=== Stage 1: Extracting Subgraphs to {INTERMEDIATE} ===")
    stage_extract_subgraphs(RAW_INPUT, INTERMEDIATE)
    print(f"=== Stage 2: Deduplicating and Exporting to {RULE_OUTPUT} ===")
    stage_deduplicate_and_export(INTERMEDIATE, RULE_OUTPUT)
    if ENABLE_RULE_NORMALIZATION:
        print(f"=== Stage 3: Normalizing Rules to {NORM_RULE_OUTPUT} ===")
        normalize_rules_file(RULE_OUTPUT, NORM_RULE_OUTPUT)