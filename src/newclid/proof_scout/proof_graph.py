import re
import logging
from typing import Dict, List, Optional, Tuple, Any, Set

class ProofGraph:
    """
    针对特定数据结构定制的证明图构建类。
    
    功能：
    1. 解析包含 <problem>, <aux>, <proof> 等标签的字符串。
    2. 构建分层 DAG 图，区分事实(fact)和规则(rule)节点。
    3. 自动识别辅助点及包含辅助点的节点。
    4. 计算节点层级(layer)和图的总深度。
    """

    # --- 正则表达式定义 (复用自 proof_graph.py 和 filter_and_prune_engine.py) ---
    # 解析形如 [001] 的ID
    _BRACKET_ID_RE = re.compile(r"\[(\d+)\]")
    # 解析事实片段: "pred a b c [000]"
    _FACT_SEG_RE = re.compile(r"^\s*(?P<pred>\w+)\s+(?P<args>.*?)\s*\[(?P<id>\d+)\]\s*$")
    # 匹配 XML 标签
    _TAG_RE = re.compile(r"</?\w+>")

    def __init__(self, verbose: bool = False):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str]] = []
        
        # 映射: problem_id -> {local_id -> node_id}
        # 注意：虽然你的数据是单题，但保留 problem_id 结构有助于兼容性
        self.problem_id: Optional[str] = None
        self.fact_id_map: Dict[str, str] = {} 
        self.aux_points: Set[str] = set()
        
        self.verbose = verbose
        self.logger = logging.getLogger("ProofGraph")
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO if verbose else logging.WARNING)

    # ---------------------------------------------------------
    # 核心构建接口
    # ---------------------------------------------------------
    
    def build_from_json(self, data: Dict[str, Any]):
        """
        从提供的数据字典构建图。
        数据结构示例:
        {
            "problem_id": 8,
            "llm_input_renamed": "<problem>...</problem>",
            "llm_output_renamed": "<numerical_check>...</numerical_check><aux>...</aux> <proof>...</proof>"
        }
        """
        self.problem_id = str(data.get("problem_id", "unknown"))
        input_str = data.get("llm_input_renamed", "")
        output_str = data.get("llm_output_renamed", "")

        # 1. 提取各个部分的文本内容
        problem_text = self._extract_tag_content(input_str, "problem") or input_str
        num_check_text = self._extract_tag_content(output_str, "numerical_check")
        aux_text = self._extract_tag_content(output_str, "aux")
        proof_text = self._extract_tag_content(output_str, "proof")

        # 2. 识别辅助点 (从 <aux> 标签中提取)
        self.aux_points = self._parse_aux_points(aux_text)
        if self.verbose:
            self.logger.debug(f"Aux points extracted: {self.aux_points}")

        # 3. 解析初始事实 (Premises) - Layer 0
        # 这里包括 problem 定义和 aux 定义中的事实
        self._parse_facts_batch(problem_text)
        self._parse_facts_batch(aux_text)
        self._parse_facts_batch(num_check_text)

        # 4. 解析证明步骤 (Proof Steps) - Layer > 0
        self._parse_proof_steps(proof_text)
        
        self.build_adjacency()

    # ---------------------------------------------------------
    # 解析辅助逻辑
    # ---------------------------------------------------------

    def _extract_tag_content(self, text: str, tag: str) -> str:
        """提取 <tag>content</tag> 中的内容"""
        if not text:
            return ""
        pattern = re.compile(rf"<{tag}>" r"(.*?)" rf"</{tag}>", re.IGNORECASE | re.DOTALL)
        match = pattern.search(text)
        return match.group(1) if match else ""

    def _parse_aux_points(self, aux_text: str) -> Set[str]:
        """解析 <aux> x00 f : ... </aux> 中的点名"""
        points = set()
        # 查找形如 "x00 pointname :" 的模式, 类似 "x00 f : coll a b f [004]"，其中 f 是辅助点
        
        content = self._strip_tags(aux_text).replace("\n", " ")
        for part in content.split(";"):
            tokens = [tok for tok in part.strip().split() if tok]
            if len(tokens) >= 2 and tokens[0].lower().startswith("x00"):
                points.add(tokens[1])
        return points

    def _parse_facts_batch(self, text: str):
        """
        批量解析文本中的事实子句。
        使用 finditer 全局扫描，只提取符合 "pred args [id]" 格式的内容。
        """
        if not text:
            return
            
        # 1. 简单清理标签 (保留内容)
        clean_text = self._strip_tags(text)
        
        # 2. 定义扫描正则
        # (?P<pred>\w+)       : 抓取谓词 (如 coll, cong)
        # \s+                 : 必须有空格分隔
        # (?P<args>[^\[\]:;]+?) : 抓取参数 (非贪婪匹配，遇到 [ ] : ; 就停止)
        # \s*\[(?P<id>\d+)\]  : 抓取 [ID]
        pattern = re.compile(r"(?P<pred>\w+)\s+(?P<args>[^\[\]:;?]+?)\s*\[(?P<id>\d+)\]")

        # 3. 全局搜索并提取
        for m in pattern.finditer(clean_text):
            pred = m.group("pred")
            # 这里的 args 字符串可能包含多余空格，split() 会自动处理
            args = m.group("args").strip().split()
            local_id = m.group("id")
            
            # 过滤掉可能的误匹配 (例如 args 为空)
            if not args:
                continue

            self._add_fact_node(local_id, pred, args, layer=0)

    def _parse_proof_steps(self, text: str):
        """解析证明步骤"""
        if not text:
            return
        clean_text = self._strip_tags(text)
        step_idx = 1
        
        for segment in clean_text.split(";"):
            seg = segment.strip()
            if not seg:
                continue
            
            # 解析单步: concl_pred args [id] rule [premise1] [premise2]
            parsed = self._parse_single_step_str(seg)
            if parsed:
                concl_pred, concl_args, concl_id, rule_code, premise_ids = parsed
                self._add_rule_step(step_idx, rule_code, premise_ids, concl_pred, concl_args, concl_id)
                step_idx += 1

    def _parse_single_step_str(self, line: str):
        """解析单行证明字符串"""
        # 找到第一个 [NNN]
        first_bracket = self._BRACKET_ID_RE.search(line)
        if not first_bracket:
            return None
        
        concl_id = first_bracket.group(1)
        left_part = line[:first_bracket.start()].strip() # "pred args"
        right_part = line[first_bracket.end():].strip()  # "rule [id] [id]"
        
        # 解析结论部分
        tokens = left_part.split()
        if not tokens: return None
        concl_pred = tokens[0]
        concl_args = tokens[1:]
        
        # 解析规则部分
        right_tokens = right_part.split()
        if not right_tokens: return None
        rule_code = right_tokens[0]
        # 提取所有前提ID
        premise_ids = self._BRACKET_ID_RE.findall(right_part)
        
        return concl_pred, concl_args, concl_id, rule_code, premise_ids

    # ---------------------------------------------------------
    # 图构建逻辑 (节点与边)
    # ---------------------------------------------------------

    def _add_fact_node(self, local_id: str, label: str, args: List[str], layer: int) -> str:
        """添加事实节点"""
        node_id = f"F:{self.problem_id}:{local_id}"
        
        # 如果已存在，直接返回 (去重)
        if node_id in self.nodes:
            return node_id
            
        # 注册 ID 映射
        self.fact_id_map[local_id] = node_id
        
        # 判断是否包含辅助点
        is_aux = any(arg in self.aux_points for arg in args)
        
        self.nodes[node_id] = {
            "id": node_id,
            "type": "fact",
            "label": label,
            "args": args,
            "local_id": local_id,
            "layer": layer,
            "is_aux": is_aux
        }
        return node_id

    def _add_rule_step(self, step_idx: int, rule_code: str, premise_local_ids: List[str], 
                       concl_pred: str, concl_args: List[str], concl_local_id: str):
        """添加规则节点及连接边"""
        
        # 1. 查找前提节点并计算层数
        premise_node_ids = []
        max_premise_layer = 0
        has_aux_premise = False
        
        for lid in premise_local_ids:
            if lid in self.fact_id_map:
                nid = self.fact_id_map[lid]
                premise_node_ids.append(nid)
                node_data = self.nodes[nid]
                max_premise_layer = max(max_premise_layer, node_data["layer"])
                if node_data["is_aux"]:
                    has_aux_premise = True
            else:
                self.logger.warning(f"Missing premise [{lid}] for rule {rule_code}")

        # 规则节点的层数 = 前提最大层数 + 1
        rule_layer = max_premise_layer + 1
        rule_node_id = f"R:{self.problem_id}:{step_idx}:{rule_code}"
        
        # 规则节点是否辅助：如果前提有辅助点，或者生成的结论将有辅助点(下面判断)，则视为辅助逻辑的一部分
        # 这里主要看输入是否污染
        rule_is_aux = has_aux_premise

        self.nodes[rule_node_id] = {
            "id": rule_node_id,
            "type": "rule",
            "label": rule_code,
            "layer": rule_layer,
            "is_aux": rule_is_aux,
            "premises": premise_node_ids
        }

        # 添加边: Premise -> Rule
        for pid_ref in premise_node_ids:
            self.edges.append((pid_ref, rule_node_id))

        # 2. 添加/获取结论节点
        # 结论节点的层数 = 规则层数 + 1
        concl_layer = rule_layer + 1
        concl_node_id = self._add_fact_node(concl_local_id, concl_pred, concl_args, concl_layer)
        
        # 添加边: Rule -> Conclusion
        self.edges.append((rule_node_id, concl_node_id))
        
        # 更新规则的 is_aux 属性：如果输出是辅助点，规则也算辅助相关
        if self.nodes[concl_node_id]["is_aux"]:
            self.nodes[rule_node_id]["is_aux"] = True

    # ---------------------------------------------------------
    # 辅助工具
    # ---------------------------------------------------------
    
    def _strip_tags(self, text: str) -> str:
        return self._TAG_RE.sub("", text or "")

    def get_max_depth(self) -> int:
        """获取图的最大深度 (层数)"""
        if not self.nodes:
            return 0
        return max(node["layer"] for node in self.nodes.values())

    def get_stats(self) -> Dict[str, Any]:
        """返回图的统计信息"""
        fact_nodes = [n for n in self.nodes.values() if n["type"] == "fact"]
        rule_nodes = [n for n in self.nodes.values() if n["type"] == "rule"]
        aux_nodes = [n for n in self.nodes.values() if n["is_aux"]]
        
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "fact_count": len(fact_nodes),
            "rule_count": len(rule_nodes),
            "aux_node_count": len(aux_nodes),
            "max_depth": self.get_max_depth(),
            "aux_points": list(self.aux_points)
        }
        
    def build_adjacency(self):
        """
        构建邻接表以加速图遍历。
        在 build_from_json 后必须调用，或者将其放入 build_from_json 的末尾。
        """
        self._adj_in: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        self._adj_out: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        
        for u, v in self.edges:
            if u in self._adj_out and v in self._adj_in:
                self._adj_out[u].append(v)
                self._adj_in[v].append(u)

    def get_predecessors(self, node_id: str) -> List[str]:
        """获取直接前驱节点ID列表"""
        return self._adj_in.get(node_id, [])

    def get_successors(self, node_id: str) -> List[str]:
        """获取直接后继节点ID列表"""
        return self._adj_out.get(node_id, [])

    def get_ancestors(self, start_node_id: str) -> Set[str]:
        """
        获取指定节点的所有上游节点（祖先），不包含自身。
        使用 BFS/DFS 反向遍历。
        """
        ancestors = set()
        queue = [start_node_id]
        visited = {start_node_id}
        
        while queue:
            curr = queue.pop(0)
            preds = self.get_predecessors(curr)
            for p in preds:
                if p not in visited:
                    visited.add(p)
                    ancestors.add(p)
                    queue.append(p)
        
        return ancestors

    def create_subgraph(self, node_ids: Set[str]) -> 'ProofGraph':
        """
        根据节点 ID 集合构建并返回一个新的 ProofGraph 子图对象。
        子图只包含 node_ids 中的节点，以及连接这些节点的内部边。
        继承原图的元数据（如 ID 映射和辅助点信息）。
        
        Args:
            node_ids: 包含在新子图中的节点 ID 集合。
            
        Returns:
            一个新的 ProofGraph 实例，代表导出的子图。
        """
        new_pg = ProofGraph(verbose=False) # 创建新的图实例
        
        # 1. 复制元数据
        new_pg.copy_meta_data(self)
        
        # 2. 提取节点
        sub_nodes = {}
        for nid in node_ids:
            if nid in self.nodes:
                # 注意：我们复制节点数据，确保不修改原图的节点属性
                sub_nodes[nid] = self.nodes[nid].copy()
                
        new_pg.nodes = sub_nodes
        
        # 3. 提取边 (仅提取起点和终点都在集合中的内部边)
        sub_edges = []
        for u, v in self.edges:
            if u in node_ids and v in node_ids:
                sub_edges.append((u, v))
                
        new_pg.edges = sub_edges
        
        # 4. 构建邻接表 (对于子图是必需的，以备后续操作)
        new_pg.build_adjacency()
                
        return new_pg
    
    # ---------------------------------------------------------
    # 可视化/调试接口
    # ---------------------------------------------------------

    def print_graph(self):
        """
        以文本形式打印图结构，按层级显示节点信息。
        显示格式：[ID] (Aux: T/F) Label Args/Premises
        """
        if not self.nodes:
            print("Graph is empty.")
            return

        # 1. 打印头部统计信息
        stats = self.get_stats()
        pid = self.problem_id if self.problem_id else "Unknown"
        print("=" * 60)
        print(f"Proof Graph Structure (Problem ID: {pid})")
        print(f"Stats: Nodes={stats['total_nodes']}, Edges={stats['total_edges']}, "
              f"MaxDepth={stats['max_depth']}, AuxPoints={stats['aux_points']}")
        print("=" * 60)

        # 2. 按层级分组节点
        layers = {}
        for nid, node in self.nodes.items():
            lvl = node.get("layer", 0)
            if lvl not in layers:
                layers[lvl] = []
            layers[lvl].append(node)

        # 3. 按层级顺序输出
        sorted_layers = sorted(layers.keys())
        for lvl in sorted_layers:
            print(f"\n--- Layer {lvl} ---")
            # 在同一层内，先打印 Fact 再打印 Rule (通常同一层只有一种，但为了兼容混合层)
            # 或者按 ID 排序
            nodes_in_layer = sorted(layers[lvl], key=lambda x: x['id'])
            
            for node in nodes_in_layer:
                nid = node['id']
                ntype = node['type']
                is_aux = "TRUE" if node['is_aux'] else "False"
                label = node['label']
                
                if ntype == 'fact':
                    # Fact 格式: [ID] (Aux) pred arg1 arg2 ...
                    args_str = " ".join(node.get('args', []))
                    print(f"[{nid}] (Aux:{is_aux}) FACT: {label} {args_str}")
                
                elif ntype == 'rule':
                    # Rule 格式: [ID] (Aux) rule_name <- [PremiseIDs]
                    premises = node.get('premises', [])
                    # 尝试简化 premise ID 显示，只显示 local part 或者简短 hash
                    premise_str = ", ".join([p.split(":")[-1] for p in premises])
                    print(f"[{nid}] (Aux:{is_aux}) RULE: {label} <- [{premise_str}]")

        print("\n" + "=" * 60 + "\n")
        
    def copy_meta_data(self, other_pg: 'ProofGraph'):
        """
        将另一个 ProofGraph 实例的元数据（非节点/边数据）复制到当前实例。
        用于构建子图时继承原图的辅助信息。
        """
        self.fact_id_map = other_pg.fact_id_map.copy()
        self.aux_points = other_pg.aux_points.copy()

# 使用示例
if __name__ == "__main__":
    # 使用你提供的示例数据进行测试
    sample_data = {
        "problem_id": 8, 
        "llm_input_renamed": "<problem> a : ; b : ; c : ; d : coll b c d [000] cong b d c d [001] ; e : coll a c e [002] cong a e c e [003] ? simtri a b c e d c </problem>", 
        "llm_output_renamed": "<aux> x00 f : coll a b f [004] cong a f b f [005] ; </aux> <numerical_check> sameclock a b c c e d [006] ; </numerical_check> <proof> eqangle a c b c c e c d [007] AR [002] [000] ; eqratio a f a e b f c e [008] AR [005] [003] ; eqratio a b a c a f a e [009] r105 [004] [002] [008] ; eqratio a f b f b d c d [010] AR [005] [001] ; eqratio a b a f b c b d [011] r105 [004] [000] [010] ; eqratio a c b c c e c d [012] AR [003] [001] [009] [011] ; simtri a b c e d c [013] r62 [007] [012] [006] ; </proof>"
    }

    pg = ProofGraph(verbose=True)
    pg.build_from_json(sample_data)
    
    print("Graph Stats:", pg.get_stats())
    # print("Nodes:", pg.nodes)