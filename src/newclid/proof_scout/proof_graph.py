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

    # --- 正则表达式定义  ---
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
        if self.problem_id is None:
            self.problem_id = str(data.get("id", "unknown"))
        input_str = data.get("llm_input_renamed", "")
        output_str = data.get("llm_output_renamed", "")

        # 1. 提取各个部分的文本内容
        problem_text = self._extract_tag_content(input_str, "problem")
        num_check_text = self._extract_tag_content(output_str, "numerical_check")
        tvl_check_text = self._extract_tag_content(output_str, "trivial")
        aux_text = self._extract_tag_content(output_str, "aux")
        proof_text = self._extract_tag_content(output_str, "proof")

        # 2. 识别辅助点 (从 <aux> 标签中提取)
        self.aux_points = self._parse_aux_points(aux_text)
        if self.verbose:
            self.logger.debug(f"Aux points extracted: {self.aux_points}")

        # 3. 解析初始事实 (Premises) - Layer 0
        # 这里包括 problem 定义和 aux 定义中的事实
        self._parse_facts_batch(problem_text)
        self._parse_facts_batch(num_check_text)
        self._parse_facts_batch(tvl_check_text)
        self._parse_facts_batch(aux_text)

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
    
    # ---------------------------------------------------------
    # 新增：规则导出接口
    # ---------------------------------------------------------
    def export_to_rule_format(self) -> str:
        """
        将当前图导出为规则格式字符串。
        格式：
        第一行：problem_id
        第二行：前提1, 前提2 ... => 结论
        
        前提：所有入度为0的事实节点 (Fact)
        结论：唯一的出度为0的事实节点 (Fact)
        """
        # 确保邻接表已构建
        if not hasattr(self, "_adj_in") or not hasattr(self, "_adj_out"):
            self.build_adjacency()

        inputs = []
        conclusion = None
        
        # 遍历所有节点寻找起点（前提）和终点（结论）
        # 注意：只关心 Fact 类型的节点，Rule 节点是中间过程
        for nid, node in self.nodes.items():
            if node["type"] != "fact":
                continue
            
            if node["is_aux"] == True:
                continue
                
            # 入度为0 -> 前提
            if not self._adj_in.get(nid):
                # 过滤trivial节点
                if node["label"] == "cong":
                    args = node["args"]
                    if args[0] == args[2] and args[1] == args[3]:
                        continue
                elif node["label"] == "eqangle":
                    args = node["args"]
                    if args[0] == args[2] and args[1] == args[3] and args[4] == args[6] and args[5] == args[7]:
                        continue
                elif node["label"] == "sameclock":
                    args = node["args"]
                    if args[0] == args[3] and args[1] == args[4] and args[2] == args[5]:
                        continue
                inputs.append(node)
            
            # 出度为0 -> 结论
            if not self._adj_out.get(nid):
                # 理论上子图应该只有一个结论，如果有多个，最后一个会覆盖（或者可以加报错）
                conclusion = node

        # 格式化辅助函数
        def fmt_node(n):
            # 拼接 谓词 + 参数列表，例如: "cong a b c d"
            return f"{n['label']} {' '.join(n['args'])}"

        # 1. 构建前提字符串 (排序以保证确定性，例如按 local_id 或 label)
        # 这里按 local_id 排序可以保证相对稳定的顺序
        inputs.sort(key=lambda x: x.get('local_id', x['id']))
        inputs_str = ", ".join([fmt_node(n) for n in inputs])

        # 2. 构建结论字符串
        conclusion_str = fmt_node(conclusion) if conclusion else "null"

        # 3. 组合最终输出
        # problem_id 在 create_subgraph 时已经被修改为带 sub 后缀的形式
        result = f"{self.problem_id}\n{inputs_str} => {conclusion_str}"
        
        return result

    # ---------------------------------------------------------
    # 序列化接口 (导出为可重构的 JSON 字典) - 支持 Aux 保留
    # ---------------------------------------------------------
    def to_json_data(self) -> Dict[str, Any]:
        """
        将当前图对象序列化为符合 build_from_json 输入要求的字典。
        包含对辅助点(Aux points)的显式声明，确保重建图时能保留 is_aux 属性。
        """
        if not hasattr(self, "_adj_in"):
            self.build_adjacency()

        problem_facts = []
        proof_steps = []
        
        # 1. 收集当前子图中出现的所有点名 (Arguments)
        active_points = set()
        for node in self.nodes.values():
            if "args" in node:
                active_points.update(node["args"])

        # 2. 识别哪些是辅助点
        # 只要当前子图用到了某个辅助点，就必须在 XML header 中声明它
        active_aux_points = active_points.intersection(self.aux_points)
        
        # 构造 <aux> 声明块
        # 格式必须满足 _parse_aux_points 的正则: x00 name : ... ;
        # 我们生成一个哑元声明 (dummy declaration)，只为了注册点名
        aux_declarations = []
        for p in active_aux_points:
            aux_declarations.append(f"x00 {p} :")
        
        aux_xml = ""
        if aux_declarations:
            aux_xml = "<aux> " + " ; ".join(aux_declarations) + " ; </aux>"

        # 3. 分离事实 (Problem) 和 步骤 (Proof)
        rules = [n for n in self.nodes.values() if n["type"] == "rule"]
        # 按层级排序确保拓扑序
        rules.sort(key=lambda x: (x["layer"], x["id"]))

        derived_fact_ids = set()

        for rule in rules:
            successors = self.get_successors(rule["id"])
            if successors:
                concl_id = successors[0]
                derived_fact_ids.add(concl_id)
                concl_node = self.nodes[concl_id]
                
                premise_ids = []
                for p_id in self.get_predecessors(rule["id"]):
                    if p_id in self.nodes:
                        premise_ids.append(self.nodes[p_id]["local_id"])
                
                args_str = " ".join(concl_node["args"])
                premises_str = " ".join([f"[{pid}]" for pid in premise_ids])
                
                step_str = f"{concl_node['label']} {args_str} [{concl_node['local_id']}] {rule['label']} {premises_str}"
                proof_steps.append(step_str)

        all_facts = [n for n in self.nodes.values() if n["type"] == "fact"]
        for fact in all_facts:
            if fact["id"] not in derived_fact_ids:
                # 这是一个输入前提
                args_str = " ".join(fact["args"])
                fact_str = f"{fact['label']} {args_str} [{fact['local_id']}]"
                problem_facts.append(fact_str)

        # 4. 组装
        problem_xml = "<problem> " + " ; ".join(problem_facts) + " </problem>" if problem_facts else "<problem></problem>"
        proof_xml = "<proof> " + " ; ".join(proof_steps) + " ; </proof>" if proof_steps else "<proof></proof>"
                
        # 将 aux_xml 拼接到 output 中 (因为通常 parser 从 output 读取 aux)
        return {
            "id": self.problem_id,
            "llm_input_renamed": problem_xml,
            "llm_output_renamed": aux_xml + " " + proof_xml,
            "node_count": len(self.nodes),
            "is_subgraph": True
        }
    
    
    
    def get_rule_signature(self) -> str:
        """
        计算规则的签名用于去重。
        签名格式示例: "sorted_inputs(cong, coll) -> output(para)"
        这样可以忽略参数具体的变量名（如 a b c vs x y z），只关注逻辑结构。
        如果你需要区分参数位置（比如 coll a b c 和 coll a c b），
        目前的谓词级去重可能不够，需要加上 args 的相对位置 pattern。
        
        这里实现：基于谓词(Predicates)的去重。
        """
        self.build_adjacency()
        
        input_preds = []
        output_pred = "null"
        
        for nid, node in self.nodes.items():
            if node["type"] == "fact":
                # 入度为0 -> 输入
                if not self._adj_in.get(nid):
                    input_preds.append(node['label'])
                # 出度为0 -> 输出
                if not self._adj_out.get(nid):
                    output_pred = node['label']
        
        # 对输入谓词排序，保证顺序无关性 (例如 A,B => C 和 B,A => C 视为相同)
        input_preds.sort()
        
        signature = f"{','.join(input_preds)} -> {output_pred}"
        return signature

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