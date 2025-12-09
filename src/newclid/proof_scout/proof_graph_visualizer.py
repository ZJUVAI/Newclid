#!/usr/bin/env python3
import logging
import re
from pathlib import Path
from typing import Any, Optional, Set, Dict, List
import matplotlib.pyplot as plt
import networkx as nx
from newclid.proof_scout.proof_graph import ProofGraph

# --- 样式常量配置 (源自旧版代码) ---
FIG_BASE_SIZE = (12, 14)  # 稍微调整基础尺寸
FIG_DPI = 200

# 颜色定义
COLOR_CONCLUSION = "#e0f2ff"       # 结论填充
COLOR_CONCLUSION_BORDER = "#007bff" # 结论边框
COLOR_FACT_AUX = "#ffe6cc"         # 含辅助点的 Fact 填充 (橙色系)
COLOR_FACT_NORMAL = "#e0ffe0"      # 普通 Fact 填充 (绿色系)
COLOR_RULE = "#f0f0f0"             # 规则填充 (灰色)
COLOR_BORDER = "#333333"           # 普通边框

# 布局参数
LAYOUT_RANKDIR = 'TB'
LAYOUT_RANKSEP = '0.8'
LAYOUT_NODESEP = '0.5'

class ProofGraphVisualizer:
    """
    结合了新版架构与旧版渲染逻辑的可视化器。
    输入：ProofGraph 对象
    输出：精美的 Matplotlib 渲染图
    """
    def __init__(self):
        self.logger = logging.getLogger("Visualizer")
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            import matplotlib
            matplotlib.use("Agg")  # 非交互模式
            import pydot
        except ImportError as e:
            self.logger.warning(f"缺少可选依赖 (pydot): {e}. 布局可能降级为 spring_layout。")

    def _bold_aux_in_predicate_text(self, text: str, aux_points: Set[str]) -> str:
        """
        旧版核心辅助函数：将文本参数中的辅助点加粗 (LaTeX 格式)。
        例如: cong(a,b,c,d) -> cong(a, $\bf{x}$, c, d)
        """
        if not text or not aux_points:
            return text
        try:
            l = text.find("(")
            r = text.rfind(")")
            if l == -1 or r == -1 or r <= l:
                return text
            
            head, args, tail = text[:l+1], text[l+1:r], text[r:]
            safe_tokens = [re.escape(str(t)) for t in aux_points if str(t)]
            if not safe_tokens:
                return text
            
            # 使用正则匹配完整单词
            pattern = re.compile(rf"(?<!\w)({'|'.join(safe_tokens)})(?!\w)")
            def repl(m):
                val = m.group(0)
                return f"$\\bf{{{val}}}$"
            
            new_args = pattern.sub(repl, args)
            return head + new_args + tail
        except Exception:
            return text

    def _pg_to_networkx(self, pg: Any) -> nx.DiGraph:
        """
        将 ProofGraph 转换为带有丰富样式的 NetworkX 对象。
        """
        G = nx.DiGraph()
        
        # 1. 提取辅助点
        # 兼容不同版本的 ProofGraph，优先取 set，若无则设为空
        pg_aux = getattr(pg, 'aux_points', set())
        if isinstance(pg_aux, dict): 
            # 兼容旧版可能是 dict 结构的情况
            aux_points = set() 
            for v in pg_aux.values():
                if isinstance(v, (list, set)): aux_points.update(v)
        else:
            aux_points = set(pg_aux)
            
        G.graph['aux_points'] = aux_points
        
        # 设置 Graphviz 布局参数
        G.graph['graph'] = {
            'rankdir': LAYOUT_RANKDIR, 
            'ranksep': LAYOUT_RANKSEP, 
            'nodesep': LAYOUT_NODESEP
        }

        # 2. 添加节点与属性计算
        for nid, attrs in pg.nodes.items():
            ntype = attrs.get('type', 'fact')
            # 原始标签处理
            pred = str(attrs.get('label', '?'))
            args = attrs.get('args', [])
            
            if ntype == 'fact':
                args_str = [str(a) for a in args]
                raw_label = f"{pred}({','.join(args_str)})"
                # 判断是否包含辅助点 (旧版逻辑)
                contains_aux = any(str(a) in aux_points for a in args_str)
                # 兼容 attrs 中显式标记的情况
                if attrs.get('is_aux'): contains_aux = True
            else:
                raw_label = str(attrs.get('label', 'Rule'))
                contains_aux = False

            # 显示用的简短标签 (去掉参数，防止圆圈内文字过长)
            if ntype == 'fact':
                display_label = pred 
            else:
                display_label = raw_label

            G.add_node(
                nid, 
                label=display_label, 
                raw_label=raw_label,
                ntype=ntype,
                contains_aux=contains_aux
            )

        # 3. 添加边
        for u, v in pg.edges:
            if u in G.nodes and v in G.nodes:
                G.add_edge(u, v)

        return G

    def _draw_single_ax(self, G: nx.DiGraph, ax: plt.Axes, title: str):
        """
        使用旧版渲染逻辑在给定的 ax 上绘图
        """
        if len(G) == 0:
            ax.text(0.5, 0.5, "Empty Graph", ha='center', va='center')
            ax.axis('off')
            return

        # --- 1. 布局计算 ---
        try:
            pos = nx.drawing.nx_pydot.graphviz_layout(G, prog='dot')
        except Exception:
            pos = nx.spring_layout(G, seed=42, k=1.2)

        # --- 2. 节点分类与样式准备 ---
        indeg = dict(G.in_degree())
        outdeg = dict(G.out_degree())
        
        # 寻找结论节点：出度为0且是Fact
        fact_sinks = [n for n, d in G.nodes(data=True) if d.get("ntype") == "fact" and outdeg.get(n, 0) == 0]
        unique_concl = fact_sinks[0] if len(fact_sinks) == 1 else None

        node_colors = {}
        node_edge_colors = {}
        node_linewidths = {}
        node_sizes = {}
        node_shapes = {}
        labels = {}

        aux_points = G.graph.get('aux_points', set())

        for n, d in G.nodes(data=True):
            ntype = d.get("ntype")
            raw_label = d.get("raw_label", "")
            
            # -- 规则节点 --
            if ntype == 'rule':
                node_shapes[n] = 's' # Square
                node_sizes[n] = 1300
                node_colors[n] = COLOR_RULE
                node_edge_colors[n] = COLOR_BORDER
                node_linewidths[n] = 1.0
                labels[n] = d.get('label') # Rule名称通常较短
            
            # -- Fact 节点 --
            else:
                node_shapes[n] = 'o' # Circle
                node_sizes[n] = 1800 # 稍微大一点以便显示谓词
                
                # 判定颜色逻辑 (旧版核心逻辑)
                if unique_concl is not None and n == unique_concl:
                    # 结论节点：蓝色背景 + 蓝色深边框
                    node_colors[n] = COLOR_CONCLUSION
                    node_edge_colors[n] = COLOR_CONCLUSION_BORDER
                    node_linewidths[n] = 2.5 # 加粗
                else:
                    # 普通 Fact
                    contains_aux = d.get('contains_aux', False)
                    node_colors[n] = COLOR_FACT_AUX if contains_aux else COLOR_FACT_NORMAL
                    node_edge_colors[n] = COLOR_BORDER
                    # 如果是前提 (入度为0)，边框稍微加粗
                    node_linewidths[n] = 2.0 if indeg.get(n, 0) == 0 else 1.0

                # 标签处理：对 Fact 只显示谓词名，参数在图中通过连线隐含或角注显示
                # 如果你想在节点里也显示加粗参数，可以使用 raw_label 并用 _bold_aux 处理
                # 这里为了整洁，沿用旧版逻辑：节点内显示简短内容
                labels[n] = d.get('label')

        # --- 3. 批量绘制 ---
        
        # 3.1 绘制边
        nx.draw_networkx_edges(
            G, pos, ax=ax, 
            arrowstyle='-|>', arrowsize=15, 
            edge_color='#666666', width=1.2
        )

        # 3.2 按形状分组绘制节点
        # Matplotlib 的 scatter 不支持混合形状，需分开画
        shape_groups = {}
        for n, s in node_shapes.items():
            shape_groups.setdefault(s, []).append(n)

        for shape, nodes in shape_groups.items():
            nx.draw_networkx_nodes(
                G, pos, nodelist=nodes, ax=ax,
                node_shape=shape,
                node_color=[node_colors[n] for n in nodes],
                edgecolors=[node_edge_colors[n] for n in nodes],
                linewidths=[node_linewidths[n] for n in nodes],
                node_size=[node_sizes[n] for n in nodes]
            )

        # 3.3 绘制标签
        nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=9)

        # --- 4. 添加旧版风格的信息标注 (Corner Text) ---
        
        # 4.1 左上角：Premises -> Conclusion 路径
        premise_nodes = [n for n in G.nodes if G.nodes[n].get('ntype') == 'fact' and indeg.get(n, 0) == 0]
        if premise_nodes and unique_concl:
            prem_texts = []
            for pn in premise_nodes:
                raw = G.nodes[pn].get('raw_label', '?')
                prem_texts.append(self._bold_aux_in_predicate_text(raw, aux_points))
            
            concl_raw = G.nodes[unique_concl].get('raw_label', '?')
            concl_text = self._bold_aux_in_predicate_text(concl_raw, aux_points)
            
            # 拼接文本
            # text_content = ", ".join(prem_texts) + " -> " + concl_text
            # 为了防止太长，只取最多3个前提
            if len(prem_texts) > 3:
                short_prems = ", ".join(prem_texts[:3]) + "..."
            else:
                short_prems = ", ".join(prem_texts)
            
            path_text = f"Flow: {short_prems} \n-> {concl_text}"
            
            ax.text(0.01, 0.99, path_text, transform=ax.transAxes, 
                    ha='left', va='top', fontsize=9,
                    bbox=dict(boxstyle='round', fc='white', ec='#999999', alpha=0.85))

        # 4.2 右下角：辅助点列表
        if aux_points:
            # 同样使用 LaTeX 加粗显示辅助点
            aux_list = ", ".join([f"$\\bf{{{p}}}$" for p in sorted(aux_points)])
            ax.text(0.99, 0.01, f"Aux Points: {aux_list}", transform=ax.transAxes,
                    ha='right', va='bottom', fontsize=10,
                    bbox=dict(boxstyle='round', fc='white', ec='#999999', alpha=0.85))

        ax.set_title(title, fontsize=14, pad=10)
        ax.axis('off')

    def render(self, pg: Any, output_path: str, title: str = "Proof Graph"):
        """渲染单个 ProofGraph"""
        G = self._pg_to_networkx(pg)
        
        fig, ax = plt.subplots(figsize=FIG_BASE_SIZE)
        self._draw_single_ax(G, ax, title)
        
        self._save(fig, output_path)

    def render_comparison(self, pg_left: Any, pg_right: Any, output_path: str, 
                          titles: tuple = ("Original", "Pruned")):
        """渲染对比图"""
        G1 = self._pg_to_networkx(pg_left)
        G2 = self._pg_to_networkx(pg_right)
        
        # 宽度加倍
        figsize = (FIG_BASE_SIZE[0] * 2, FIG_BASE_SIZE[1])
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
        
        self._draw_single_ax(G1, ax1, titles[0])
        self._draw_single_ax(G2, ax2, titles[1])
        
        self._save(fig, output_path)

    def _save(self, fig, path):
        out_p = Path(path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(out_p, dpi=FIG_DPI)
        plt.close(fig)
        print(f"Graph saved to: {out_p}")

if __name__ == "__main__":

    sample_data = {
        "problem_id": 8, 
        "llm_input_renamed": "<problem> a : ; b : ; c : ; d : coll b c d [000] cong b d c d [001] ; e : coll a c e [002] cong a e c e [003] ? simtri a b c e d c </problem>", 
        "llm_output_renamed": "<aux> x00 f : coll a b f [004] cong a f b f [005] ; </aux> <numerical_check> sameclock a b c c e d [006] ; </numerical_check> <proof> eqangle a c b c c e c d [007] AR [002] [000] ; eqratio a f a e b f c e [008] AR [005] [003] ; eqratio a b a c a f a e [009] r105 [004] [002] [008] ; eqratio a f b f b d c d [010] AR [005] [001] ; eqratio a b a f b c b d [011] r105 [004] [000] [010] ; eqratio a c b c c e c d [012] AR [003] [001] [009] [011] ; simtri a b c e d c [013] r62 [007] [012] [006] ; </proof>"
    }

    pg = ProofGraph(verbose=True)
    pg.build_from_json(sample_data)

    # 4. 执行测试
    viz = ProofGraphVisualizer()
    
    print("Test 1: Rendering single graph...")
    viz.render(pg, "datasets/output_viz/test_single.png", title="Full Proof Graph")
    
    print("Test 2: Rendering comparison...")
    viz.render_comparison(pg, pg, "datasets/output_viz/test_compare.png")