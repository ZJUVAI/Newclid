import networkx as nx
from networkx.drawing.nx_agraph import to_agraph
import os

from proof_graph import ProofGraph 

class ProofGraphVisualizer:
    """
    专门用于渲染 ProofGraph 的可视化器，风格仿照教科书式的证明树结构。
    依赖: networkx, pygraphviz, 以及已安装的 Graphviz 软件。
    """
    
    # 定义样式常量
    STYLE_PREMISE = {'shape': 'circle', 'style': 'filled', 'fillcolor': '#C6EFCE', 'fontname': 'Helvetica', 'fontsize': 10, 'width': 0.6, 'fixedsize': 'true'} # 浅绿
    STYLE_INTERMEDIATE = {'shape': 'circle', 'style': 'filled', 'fillcolor': '#FFD9B3', 'fontname': 'Helvetica', 'fontsize': 10, 'width': 0.6, 'fixedsize': 'true'} # 浅橙
    STYLE_AUX = {'shape': 'circle', 'style': 'filled', 'fillcolor': "#F55E4A", 'fontname': 'Helvetica', 'fontsize': 10, 'width': 0.6, 'fixedsize': 'true'} # 红色
    STYLE_CONCLUSION = {'shape': 'circle', 'style': 'filled', 'fillcolor': '#99CCFF', 'fontname': 'Helvetica', 'fontsize': 10, 'width': 0.6, 'fixedsize': 'true'} # 浅蓝
    STYLE_RULE = {'shape': 'square', 'style': 'filled', 'fillcolor': '#E0E0E0', 'fontname': 'Helvetica', 'fontsize': 10, 'width': 0.5, 'height': 0.5, 'fixedsize': 'true'}   # 浅灰

    def __init__(self, pg):
        self.pg = pg
        # 确保邻接表已构建，用于判断入度/出度
        if not hasattr(self.pg, "_adj_in"):
            self.pg.build_adjacency()
            
        self.G = nx.DiGraph()
        # 映射长ID到短显示标签 (如 F1, R1)
        self.id_to_short_label = {}
        self.legend_lines = []
        self.title_text = ""

    def _generate_short_labels_and_legend(self):
        """生成短标签 (F1, R1...) 并构建图例内容"""
        f_count = 1
        r_count = 1
        
        # 对节点排序以确保每次运行生成的标签顺序一致 (可选)
        sorted_nodes = sorted(self.pg.nodes.items(), key=lambda x: x[0])
        
        fact_legend = []
        rule_legend = []

        for nid, node in sorted_nodes:
            if node['type'] == 'fact':
                short = f"F{f_count}"
                f_count += 1
                args_str = ",".join(node['args'])
                # 图例格式: F1: coll(a,b,c)
                fact_legend.append(f"{short}: {node['label']}({args_str})")
            else:
                short = f"R{r_count}"
                r_count += 1
                # 图例格式: R1: r105
                rule_legend.append(f"{short}: {node['label']}")
            
            self.id_to_short_label[nid] = short
            
        self.legend_lines = ["Legend", "--- Facts ---"] + fact_legend + ["", "--- Rules ---"] + rule_legend

    def _determine_node_style(self, nid, node):
        """根据节点类型和在图中的位置确定样式"""
        if node['type'] == 'rule':
            return self.STYLE_RULE
        else:
            # Fact 节点，判断是前提、中间还是结论
            in_degree = len(self.pg._adj_in.get(nid, []))
            out_degree = len(self.pg._adj_out.get(nid, []))
            
            if in_degree == 0:
                return self.STYLE_PREMISE
            elif out_degree == 0:
                return self.STYLE_CONCLUSION
            else:
                return self.STYLE_INTERMEDIATE

    def _build_title(self):
        """构建顶部标题，显示前提 => 结论"""

        self.title_text = f"Norm Rule: {self.pg.export_to_rule_format()}"

    def build_graphviz_structure(self):
        """构建用于 Graphviz 渲染的 NetworkX 结构"""
        self._generate_short_labels_and_legend()
        self._build_title()
        
        # 1. 添加节点
        for nid, node in self.pg.nodes.items():
            short_label = self.id_to_short_label[nid]
            style = self._determine_node_style(nid, node)
            if node['is_aux']:
                    style = self.STYLE_AUX
            # 将样式字典展开作为节点属性
            self.G.add_node(short_label, label=short_label, **style)
            
        # 2. 添加边
        for u, v in self.pg.edges:
            u_short = self.id_to_short_label[u]
            v_short = self.id_to_short_label[v]
            self.G.add_edge(u_short, v_short, color="#666666")

    def render(self, output_path: str = "proof_graph.png"):
        """执行布局并保存图像"""
        # 转换为 pygraphviz AGraph 对象
        A = to_agraph(self.G)
        
        # --- Graphviz 全局设置 ---
        A.graph_attr.update(
            rankdir='TB',       # Top to Bottom 布局
            splines='polyline', # 尽量使用直线边，看起来更整洁
            bgcolor='white',
            pad='0.5',          # 图像边缘留白
            nodesep='0.4',      # 同一层节点间的最小距离
            ranksep='0.5',      # 不同层之间的距离
            fontname='Helvetica'
        )

        # --- 添加标题节点 (作为一个独立的孤立节点放在最上面) ---
        # Graphviz 的一个小技巧：创建一个看不见的节点来承载标题文本
        title_node_name = "title_node"
        A.add_node(title_node_name, 
                   label=self.title_text, 
                   shape='box', 
                   style='filled', fillcolor='white', color='black',
                   fontname='Helvetica', fontsize=12,
                   margin="0.2,0.1")
        
        # --- 添加图例子图 (Subgraph) ---
        # 使用 'cluster' 前缀可以让 Graphviz 将其视为一个分组框
        legend_subgraph = A.add_subgraph(name="cluster_legend", label="", color="white")
        
        legend_content = "\\l".join(self.legend_lines) + "\\l" # \\l 表示左对齐换行
        
        legend_subgraph.add_node("legend_box",
                                 label=legend_content,
                                 shape='note', # 便签形状
                                 style='filled', fillcolor='#FFFFEE', color='black',
                                 fontname='Courier', fontsize=9, # 使用等宽字体对齐
                                 margin="0.1,0.1")
        
        # --- 关键布局技巧 ---
        # 为了让标题在最上，图例在右侧，需要一些 hack。
        # 一种简单方法是利用 Graphviz 的 rank 约束。
        # 将所有前提节点和标题节点放在同一个 'min' rank 中，
        # 将图例节点放在 'max' rank 或不做限制让其自然浮动。
        
        # 找到所有前提节点
        premise_nodes = [self.id_to_short_label[nid] for nid, node in self.pg.nodes.items() 
                         if node['type']=='fact' and not self.pg._adj_in.get(nid)]
        
        # 创建一个子图来强制这些节点在最顶层
        A.add_subgraph([title_node_name] + premise_nodes, rank='min')


        print(f"Rendering graph to {output_path} using Graphviz (dot engine)...")
        # 使用 'dot' 引擎进行层次化布局
        A.layout(prog='dot')
        A.draw(output_path)
        print("Render complete.")


# =====================================================================
# 测试代码 (使用你提供的示例数据)
# =====================================================================
if __name__ == "__main__":
    # 假设你已经有了 proof_graph.py，这里直接导入使用
    # 为了让代码独立运行，这里临时粘贴 ProofGraph 的简化版本或者假设它存在
    # 实际使用时，请取消下面导入的注释，并确保 proof_graph.py 在同一目录
    from proof_graph import ProofGraph 

    sample_data = {
        "problem_id": 8, 
        "llm_input_renamed": "<problem> a : ; b : ; c : ; d : coll b c d [000] cong b d c d [001] ; e : coll a c e [002] cong a e c e [003] ? simtri a b c e d c </problem>", 
        "llm_output_renamed": "<aux> x00 f : coll a b f [004] cong a f b f [005] ; </aux> <numerical_check> sameclock a b c c e d [006] ; </numerical_check> <proof> eqangle a c b c c e c d [007] AR [002] [000] ; eqratio a f a e b f c e [008] AR [005] [003] ; eqratio a b a c a f a e [009] r105 [004] [002] [008] ; eqratio a f b f b d c d [010] AR [005] [001] ; eqratio a b a f b c b d [011] r105 [004] [000] [010] ; eqratio a c b c c e c d [012] AR [003] [001] [009] [011] ; simtri a b c e d c [013] r62 [007] [012] [006] ; </proof>"
    }

    # 1. 构建 PG 对象
    pg = ProofGraph(verbose=False)
    pg.build_from_json(sample_data)
    # build_adjacency 在 visualizer 内部也会调用，这里显式调用也没问题
    pg.build_adjacency()
    
    # 2. 初始化可视化器
    visualizer = ProofGraphVisualizer(pg)
    
    # 3. 构建内部结构
    visualizer.build_graphviz_structure()
    
    # 4. 渲染输出
    output_file = "proof_graph_rendered.png"
    # 支持输出 png, pdf, svg 等格式
    visualizer.render(output_file)
    