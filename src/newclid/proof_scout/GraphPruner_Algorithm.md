# GraphPruner 核心算法流程

**算法名称**: 独占子图规则提取与剥离 (Exclusive Subgraph Extraction & Pruning)

**输入**:
* `PG`: 证明图
    * $V$: 节点集合 (包含 Fact Node 和 Rule Node)
    * $E$: 有向边集合 (Fact->Rule, Rule->Fact)
    * `AuxData`: 辅助点信息 (用于判定 `HasAux(Node)`)

**输出**:
* `sub_PGs`: 提取出的包含辅助点的证明子图列表 (List of SubGraphs)

---

## 算法流程伪代码

**Function** PruneAndExtract(PG):
    Initialize `sub_PGs` as empty list
    
    // 1. 初始化待检查队列
    // 筛选所有不包含辅助点的事实节点
    // 按节点层级 (Node Levels) 或拓扑序排序，确保处理顺序的合理性
    `Alive` = [ node for node in PG.Nodes 
                if IsFact(node) and not HasAux(node) ]
    Sort `Alive` based on Node Levels

    // 2. 迭代检查每个事实节点
    **For** `F0` in `Alive`:
    
        // === Step 2.1: 寻找活着的祖先 (Ancestors Discovery) ===
        // 在当前存活的图结构中，反向搜索 F0 的所有上游节点
        `Ancestors` = BFS_or_DFS_Backwards(StartNode=`F0`, Graph=PG)
        
        // 若无祖先，说明 F0 已是入度为0的前提，跳过
        If `Ancestors` is empty:
            Continue

        // === Step 2.2: 基于辅助点信息判定提取资格 (Extraction Eligibility) ===
        // F0 必然有一个直接规则前驱 R0，以及 R0 的输入事实节点集合 F1s
        `R0` = GetUniquePredecessorRule(`F0`)
        `F1s` = GetPredecessorFacts(`R0`)
        
        `ShouldExtract` = False
        // 检查直接前驱是否引入了辅助点
        // 注意：此处仅关注直接前驱，不考虑更上游的节点
        If any node in `F1s` satisfies `HasAux`:
            `ShouldExtract` = True
        
        // === Step 2.3: 独占性检查 (Isolation Check) ===
        // 目的：确认 Ancestors + F0 是否构成一个对外封闭的子图，以决定是否可以物理删除
        `IsIsolated` = True
        
        **For** `A` in `Ancestors`:
            // 获取 A 的所有连接点 (前驱 + 后继)
            `Neighbors` = GetPredecessors(`A`) + GetSuccessors(`A`)
            
            // 检查 A 是否连接到了当前子图之外的节点
            // 关键：只关注当前还“活着”的外部节点
            **For** `N` in `Neighbors`:
                If `N` is in `Alive`:  // 忽略已删除的节点
                    // 合法的连接对象只能是：Ancestors 内部节点 OR 目标节点 F0
                    If `N` is not in `Ancestors` AND `N` != `F0`:
                        `IsIsolated` = False
                        Break
            If not `IsIsolated`:
                Break
        
        // === Step 2.4: 执行操作 ===
        
        // 操作 A: 提取规则 (只要涉及辅助点，无论是否共享，都提取)
        If `ShouldExtract` is True:
            // 将 Ancestors 和 F0 组合成一个独立的子图结构
            `SubgraphNodes` = `Ancestors` + {`F0`}
            `Subgraph` = PG.CreateGraph(`SubgraphNodes`)
            Append `Subgraph` to `sub_PGs`
        
        // 操作 B: 剥离子图 (只有完全独占不影响其他分支时，才删除， 且不修改原图结构)
        If `IsIsolated` is True:
            // 从待处理列表 Alive 中移除这些节点，因为它们可以由`F0`替代
            Remove `Ancestors` from `Alive`

    Return `sub_PGs`