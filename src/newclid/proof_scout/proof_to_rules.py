import json
import os
import logging
from tqdm import tqdm  # 如果没有安装 tqdm，可以注释掉相关行

# 引入你的类
from proof_graph import ProofGraph
from proof_graph_pruner import GraphPruner

def process_jsonl_and_extract(input_path: str, output_path: str):
    """
    读取 JSONL 文件，构建图，剪枝提取子图，并导出为规则格式。
    """
    # 初始化 Pruner (verbose=False 关闭详细日志，以免刷屏)
    pruner = GraphPruner(verbose=False)
    
    # 统计计数器
    total_lines = 0
    total_subgraphs = 0
    
    # 确保输出目录存在
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # 以追加模式打开输出文件（或者 'w' 覆盖模式）
    with open(output_path, 'w', encoding='utf-8') as f_out:
        
        # 读取输入文件
        with open(input_path, 'r', encoding='utf-8') as f_in:
            # 使用 tqdm 显示进度条
            lines = f_in.readlines()
            iterator = tqdm(lines, desc="Processing")
            
            for line in iterator:
                line = line.strip()
                if not line:
                    continue
                
                total_lines += 1
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON line: {line[:50]}...")
                    continue

                # 1. 构建 ProofGraph
                pg = ProofGraph(verbose=False)
                try:
                    pg.build_from_json(data)
                    # 必须构建邻接表，pruner 和 export 都需要
                    pg.build_adjacency()
                except Exception as e:
                    print(f"Error building graph for ID {data.get('id')}: {e}")
                    continue

                # 2. 执行剪枝提取
                try:
                    subgraphs_data = pruner.prune_and_extract(pg)
                except Exception as e:
                    print(f"Error pruning graph for ID {data.get('id')}: {e}")
                    continue

                # 3. 遍历提取出的子图并输出
                for item in subgraphs_data:
                    sub_pg = item["subgraph_object"]
                    
                    # 子图在 create_subgraph 内部已经调用过 build_adjacency，
                    # 所以可以直接导出
                    rule_text = sub_pg.export_to_rule_format()
                    
                    # 写入文件
                    f_out.write(rule_text + "\n")
                    total_subgraphs += 1

    print(f"\nDone.")
    print(f"Processed {total_lines} JSON lines.")
    print(f"Extracted {total_subgraphs} rules.")
    print(f"Results saved to: {output_path}")

if __name__ == "__main__":
    # 配置路径
    INPUT_FILE = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/geometry_clauses5_samples10k.jsonl"  # 你的输入文件名
    OUTPUT_FILE = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/tmp_test.txt" # 你的输出文件名

    # # 创建一个简单的测试文件（如果是初次运行且没有文件）
    # if not os.path.exists(INPUT_FILE):
    #     print(f"Generating sample {INPUT_FILE}...")
    #     sample_line = json.dumps({
    #         "id": 1, 
    #         "n_clauses": 4, 
    #         "n_premises": 6, 
    #         "fl_problem": "...", 
    #         "nl_problem": "", 
    #         "n_proof_steps": 6, 
    #         "llm_input_renamed": "<problem> a : ; b : ; c : ; d : coll a c d [000] cong a d c d [001] ; e : coll b c e [002] cong b e c e [003] ? para a b d e </problem>", 
    #         "llm_output_renamed": "<aux> x00 f : coll a b f [004] cong a f b f [005] ; </aux> <numerical_check> ncoll a b e [006] ; sameside c a d c b e [007] ; </numerical_check> <proof> eqratio a d a f c d b f [008] AR [001] [005] ; eqratio a b a c a f a d [009] r105 [004] [000] [008] ; eqratio a f b f c e b e [010] AR [005] [003] ; eqratio a b a f b c c e [011] r105 [004] [002] [010] ; eqratio a c a d b c b e [012] AR [003] [009] [011] ; para a b d e [013] r27 [000] [002] [012] [006] [007] ; </proof>"
    #     })
    #     with open(INPUT_FILE, 'w') as f:
    #         f.write(sample_line + "\n")

    # 运行处理
    process_jsonl_and_extract(INPUT_FILE, OUTPUT_FILE)