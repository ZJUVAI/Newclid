# 几何知识发现

## 0. 目录速览


- 1. 概述与背景 — 当前几何自动证明的瓶颈与从带辅助点的证明中归纳新命题/规则的思路。
- 2. 目标与阶段里程碑 — 基于 r07 验证等阶段目标与规则集评估情况。
- 3. 数据与证明图构建 — 将证明文本解析为“fact-rule”分层有向二分图，节点/边与一致性策略。
- 4. 现行方法（Filter-and-Prune 管线）— 题目筛选（含辅助点）→ 去重 → 建图 → 修剪 → 可视化 → 规则提取与规范化。
- 5. 代码结构与运行入口 — 当前脚本与模块清单，运行方法与输出说明。
- 6. 剩余目标及日程规划 — 实验/论文待办，时间表与阶段产出。

## 1. 概述与背景

- 当前存在的问题 / 待解决目标
  1. AlphaGeometry中的LLM主要充当辅助构造的向导，而非新几何原理的发现者。
  2. 包括AG在内的几何定理证明系统依赖于静态数据集或预设知识（defs & rules）。
  3. 人类直观的非形式化证明与机器可验证的形式化证明之间的鸿沟是一个主要瓶颈。
- 几何发现思路：分析带辅助点的生成数据，发掘其中利用辅助点、经常出现、有新颖性与非平凡性质的证明过程构成新定理；如果把题目的证明过程看成是DAG，那么找到经常出现的子过程就是发掘依赖图中的频繁子图
  ```
  "analysis": "<analysis> coll c d k [000] ; coll c g l [001] ; cong c k d k [002] ; cong c l g l [003] ; coll g k n [004] ; coll d l n [005] ; </analysis>",  
  "numerical_check": "<numerical_check> ncoll g k l [006] ; sameside k c d l c g [007] ; sameclock d g n k n l [008] ; sameclock d g l g z l [009] ; sameclock g k z k l n [010] ; </numerical_check>",  
  "proof": "<proof> eqratio c k c l d k g l [011] a00 [002] [003] ; para d g k l [012] r27 [000] [001] [011] [006] [007] ; eqangle d g g l l z g l [013] a01 [014] [012] ; eqangle d l g l g z g l [015] a01 [016] ; simtri d g l z l g [017] r34 [013] [015] [009] ; eqratio d l g l g z g l [018] r52 [017] ; eqangle d g g n k l k n [019] a01 [004] [012] ; eqangle d n g n l n k n [020] a01 [005] [004] ; simtri d g n l k n [021] r34 [019] [020] [008] ; eqratio d n g n l n k n [022] r52 [021] ; eqangle g k k n k z k l [023] a01 [004] [014] ; eqangle g z k z l n k l [024] a01 [005] [014] [016] ; simtri g k z n k l [025] r34 [023] [024] [010] ; eqratio g k k n k z k l [026] r52 [025] ; eqratio g z k z l n k l [027] r52 [025] ; eqratio d l d n g k g n [028] a00 [018] [022] [026] [027] ; </proof>"  
  ```
- 预期贡献
  1. 自主几何引理发现与泛化：系统应能够超越辅助构造的简单建议，自主识别、泛化和存储可应用于未来问题的创新性几何引理。
      1. 更高效率：相比每次通过AG进行辅助构造的猜测，直接从库中提取新发现定理可以更高效地解决问题
  2. 弥合几何形式化与非形式化证明之间的鸿沟：通过整合人类非形式化证明作为指导，使系统能够将人类的直观思维转化为严谨的几何形式化步骤。
      1. 可以为下一阶段的自动形式化积累数据集（或者直接生成非形式化-形式化文本对的数据集）
  3. 构建自我持续的几何学课程：设计一个反馈循环，使证明尝试的成功或失败能够指导进化器优先泛化哪些类型的引理和解决哪些请求，从而创建一个自我强化的几何学习过程。

## 2. 目标与阶段里程碑

### 2.1 方案可行性验证 I

验证思路：目前的ddar规则集中，r07（Thales Theorem I）的结论可以通过添加辅助点来证明，包含r07的题目如果添加相应的辅助点，就可以不依赖r07求解。如果对一批这样的求解结果利用频繁子图搜索算法重新找出r07，就可以验证这个思路是可行的

  ```
  r07 Thales Theorem I
  para A B C D, coll O A C, ncoll O A B, coll O B D => eqratio3 A B C D O O
  ```

### 2.2 方案可行性验证 II

将通过“选择小规则集 → 评估小规则集解题能力 → 生成数据 → 定理挖掘 → 更新规则集并重新评估”的流程，验证方案的实际效果。为此，先对现有规则集进行整理：在当前 31 条规则中，可按“基础规则/派生定理”进行如下划分。

#### 基础规则：公理与定义(16条)

基础规则是系统的逻辑基石，定义了最核心的几何概念与关系，本身无需证明。

```
r28 Overlapping parallels
para A B A C => coll A B C
r34 AA Similarity of triangles (Direct)
eqangle B A B C Q P Q R, eqangle C A C B R P R Q, sameclock A B C P Q R => simtri A B C P Q R
r35 AA Similarity of triangles (Reverse)
eqangle B A B C Q R Q P, eqangle C A C B R Q R P, sameclock A B C P R Q => simtrir A B C P Q R
r49 Recognize center of cyclic (circle)
circle O A B C, cyclic A B C D => cong O A O D
r50 Recognize center of cyclic (cong)
cong O A O B, cong O C O D, cyclic A B C D, npara A B C D => cong O A O C
r51 Midpoint splits in two
midp M A B => rconst M A A B 1/2
r52 Properties of similar triangles (Direct)
simtri A B C P Q R => eqangle B A B C Q P Q R, eqratio B A B C Q P Q R
r53 Properties of similar triangles (Reverse)
simtrir A B C P Q R => eqangle B A B C Q R Q P, eqratio B A B C Q P Q R
r54 Definition of midpoint
cong M A M B, coll M A B => midp M A B
r56 Properties of midpoint (coll)
midp M A B => coll M A B
r60 SSS Similarity of triangles (Direct)
eqratio B A B C Q P Q R, eqratio C A C B R P R Q, sameclock A B C P Q R => simtri A B C P Q R
r61 SSS Similarity of triangles (Reverse)
eqratio B A B C Q P Q R, eqratio C A C B R P R Q, sameclock A B C P R Q => simtrir A B C P Q R
r62 SAS Similarity of triangles (Direct)
eqratio B A B C Q P Q R, eqangle B A B C Q P Q R, sameclock A B C P Q R => simtri A B C P Q R
r63 SAS Similarity of triangles (Reverse)
eqratio B A B C Q P Q R, eqangle B A B C Q R Q P, sameclock A B C P R Q => simtrir A B C P Q R
r101 Similarity to Congruence (Direct)
simtri A B C P Q R, cong A B P Q => contri A B C P Q R
r102 Similarity to Congruence (Reverse)
simtrir A B C P Q R, cong A B P Q => contrir A B C P Q R
```

- 定义性规则：定义几何概念的内涵与外延。
  - 中点定义（r51, r54, r56）：完整给出“何为中点”（r54）及其共线（r56）与二等分（r51）性质。
  - 相似性的性质（r52, r53）：定义 simtri（相似三角形）这一谓词的含义，一旦确立相似关系，可推出对应角相等与对应边成比例。
  - 相似到全等（r101, r102）：可视作 congtri 的定义途径之一：若两三角形相似且有一对对应边相等，则它们全等。
  - 圆心定义（r49, r50）：基于“圆上各点到圆心距离相等”的定义，用于识别与使用圆心。
- 公理化规则：源于欧几里得几何的基本公理。
  - 重叠平行线（r28）：平行公理的直接逻辑推论（过直线外一点仅有一条与已知直线平行的直线）。

#### 核心判定规则：建立等价关系的基石

此类规则虽在严格意义上可证，但在几何推理系统中承担着判定三角形相似的核心职责，是运用比例与角度关系的关键工具。

- AA 相似（r34, r35）：角-角相似准则。
- SSS 相似（r60, r61）：边-边-边相似准则。
- SAS 相似（r62, r63）：边-角-边相似准则。

将这些判定准则视作基础层级是合理的，因为它们是多数复杂定理证明的起点。

#### 派生定理：由基础规则构建的几何知识

派生定理在系统中数量最多，代表欧几里得几何中那些著名且需多步证明的定理。在 DDARN 引擎中将其固化为单步规则，能显著提升推理效率，避免每次从零展开冗长推导。

- 泰勒斯定理（r07, r27, r41, r42）：泰勒斯定理（平行线分线段成比例）及其逆定理，均可通过构造相似三角形（利用 AA 相似）证明。
- 圆几何定理（r03, r04, r19, r58, r59）：包括圆周角定理及其逆、等弦对等角、直角三角形斜边是外接圆直径等，可通过添加圆心、连接半径构造等腰三角形并利用基础角关系来证明。
- 著名三角形定理：
  - 角平分线定理（r11, r12）：可通过添加辅助平行线构造相似三角形来证明。
  - 勾股定理（r57）：经典做法是过直角顶点向斜边作高，利用产生的三个相似三角形（AA 相似）进行边长比例推导。
  - 垂心定理（r43）与内心定理（r46）：关于“四心”的更高级结论，证明常需综合运用多种规则，例如通过证明四点共圆获得新的角度关系。
- 高等几何定理：
  - 帕普斯定理（r44）：更高等的定理，射影几何框架下更简洁；在欧氏框架下证明也依赖反复应用相似与泰勒斯定理。

接下来，我们将检查提取到的基础规则集，记录对 benchmark jgex-231 的题目求解率；利用当前数据生成功能，基于基础规则集生成一批数据，提取其中包含辅助点的数据，并调用子图挖掘管线进行求解。

- 基础规则集的求解完成率：158/231
- 完全规则集的求解完成率：202/231

## 3. 数据与证明图构建

- 图模型
  - 分层有向二分图：奇数层为 fact 节点，偶数层为 rule 节点。
  - 边不区分类型；仅存储有向边 (src, dst)。
- 数据来源与解析
  - 从 JSON 的 `results[*].proof.analysis`、`results[*].proof.numerical_check`、`results[*].proof.proof` 构建图。
  - `analysis` 与 `numerical_check` 中的子句统一解析为 fact：形如 `pred args [NNN]`。
  - `proof` 中每一步统一解析：`concl_pred args [NEW_ID] RULE [PID] [PID] ...`。
- 一致性与约束
  - 不做去重（同一个 [NNN] 多次出现时如一致则记录为重复，否则冲突并告警）。
  - 去重作用域与 [NNN] 局部 ID：
    - [NNN] 的作用域仅在单个 problem_id 内；同一题目内，analysis / numerical_check / proof 出现的相同 [NNN] 被视为指向同一“本题的局部实体”。
    - 同题同 [NNN] 若 predicate/args 完全一致，则允许重复登记；若不一致，保留首次登记并输出冲突告警（不抹平差异、不全局改写）。
    - 不进行跨题合并：不同 problem_id 即便标签、args 完全相同，也不会在合并图 G* 中被折叠或连边；仅保留其各自的节点与本题边。
    - 规则步索引/局部 ID 均为题内局部概念；缺失前提仅在本题内创建占位 fact（不会跨题借用任何节点）。
    - 支持度统计口径：以覆盖到的去重后的 problem_id 计数（每题最多计 1 次）；而 occurrence/embeddings 可在同一题内包含多处出现，用于举例展示但不影响支持度。
  - FSM 阶段仅使用 fact 的标签（predicate）与 rule 的 code；fact 的 args 暂不参与 FSM（仅在可读化输出时使用）。
  - 任意“无法解析/跳过/占位/冲突”必须通过 logger 和/或 print 发出提示，不允许静默忽略。

### 3.1 解析规则
- 去标签：`<analysis>...</analysis>`、`<proof>...</proof>` 等用正则剥离，仅保留内容。
- fact 子句正则：`^\s*(?P<pred>\w+)\s+(?P<args>.*?)\s*\[(?P<id>\d+)\]\s*$`。
- proof 步骤：通过首个 `[NNN]` 锚定结论 ID；左侧拆出 `pred args`，右侧第一个 token 为 `rule_code`，其后找到全部 `[PID]`。
- 缺失前提：创建占位 fact（`label=unknown, args=[], layer=1`），并告警。
- 结论冲突：若同一局部 ID 先前已登记且内容不一致，保持原记录并告警忽略新值。

## 4. 现行方法（Filter-and-Prune 管线）

本仓库当前以“基于证明图的筛选-修剪-可视化-规则提取”作为主线，围绕带辅助点的题目抽取与归纳有效命题/规则。

- 输入来源：`scripts/run_batch.py` 生成的 results（或等价 JSON/JSONL 对象），使用其中的 `llm_input_renamed`（题目，问号前为前提）与 `llm_output_renamed` 的 `<aux>...</aux>`（辅助构造）。
- 目标：筛选出含辅助点的题目，构建单题证明图，按规则对图进行迭代修剪，生成可视化与可读命题（proposition_rule），并统一命名与输出。

### 4.1 流程步骤

1) 含辅助点筛选（AuxExtractor）
   - 仅保留 `aux_points` 非空的题目；新增一步哈希去重：对“问题部分（问号前）+ 辅助构造段（<aux>...</aux>）”计算哈希，重复的样本跳过。

2) 单题证明图构建（SingleProofGraph / ProofGraph）
   - 将 `<problem>`、`<proof>` 等片段解析为 fact-rule 二分图；保证题内局部 ID 自洽，不跨题合并。

3) 图修剪（GraphPruner）
   - 规则：若某规则 R 的所有前驱 fact 都是题目的前提，且这些前驱均不包含辅助点（绿色节点），则删除 R 及其关联边；将其结论转为前提，迭代直至不再满足条件。
   - 保护条件（兄弟规则-辅助点牵连）：若 R 的任一前驱还指向另一个规则 R' 且 R' 的前驱中含辅助点，则不删除 R。

4) 可视化（ProofGraphVisualizer）
   - 配色与标注：
     - 结论节点为蓝色；前提 fact：包含辅助点为橙色，否则为绿色；前提（入度=0）节点边框加粗。
     - 左上角标注“前提 -> 结论”；右下角标注 `aux_points: ...`；支持 legend 模式以外移长标签。

5) 规则提取与规范化（RuleExtractor / translate_rules_to_problem）
   - 从修剪后的图提取 `proposition_rule` 文本，统一从 a 开始重命名点，保持与图片编号一致；输出 rule.txt 风格（如单行 id + 双行规则体）。
   - 过滤：若结论中包含的点不在任何一个前提中，则跳过该条规则。

产物（详见第 5 节）：可选 `_aux_pruned.json`、可视化图片、规则文本输出等。

### 4.2 绘图样式与接口要点

- 节点形状：规则为方形，fact 为圆形；唯一结论 fact 使用蓝色描边。
- 分色策略：前提且含辅助点（橙色），前提且不含辅助点（绿色），结论（蓝色）。
- 标签：`label_mode` 支持 `legend`（推荐，右侧显示完整映射）、`short`、`full`。
- 题目编号与文件名一致，便于对照规则输出与图片。

### 4.3 命题文本与命名规范

- 命名：统一从 a 开始依次命名，保持与原图点的对应关系；
- 文本格式：遵循 rule.txt 风格，例如：
  - `para a b c d, para m n a b, coll m a d, coll n b c, ncoll a b c => eqratio m a m d n b n c`
- 规则校验：若 `=>` 右侧使用了左侧未出现的点，则跳过此规则（避免错误命题）。

## 5. 实现与代码结构

（完整的 data_discovery 代码与数据清单见文末“附录A”。）

### 5.1 近期更新速览（与脚本/输出对齐）
- 新增“规则仅挖掘”模式（rules-only）：在合并图上仅以规则节点建图与扩展，最终再基于嵌入回溯重建 schema；显著减小搜索图规模，同时保留可读化输出。
- 分叉挖掘（branched）鲁棒性修复：
  - 若模式中所有规则均已完整，先行“预 finalize”产出结果，避免在后续扩展中因限额而丢失可输出模式。
  - A 阶段（补齐规则）若没有实际进展，则不会提前 return，而是继续进入 FRF/attach 流程，减少“0 结果”情况。
  - 变量闭包检查改为“逐嵌入过滤”，更新支持度后再判定，避免一刀切误杀。
- 输出落盘统一（仅分叉/规则仅）：
  - 分叉挖掘（fact_rule）：`data_discovery/data/branched_mining.json`
  - 规则仅挖掘（rule_only）：`data_discovery/data/rules_only_mining.json`
  - 统一包含：`created_at/proof_graph/merged_graph/params/timing_sec/patterns_summary_topN/patterns` 等结构化字段（不再写入 input.json 相关信息）。
- SchemaMiner 后处理总线（取代早期 MiningPipeline）：将 schema 生成、多步过滤、去重、最终“同结论按前提集合最小化”与审计写入聚合为统一流程；由脚本集中管理超参与调用。
- aconst/rconst 语义修正：其最后一个参数是数值常量（非点/变量），不计入依赖/变量闭包；在 schema 渲染时保留字面量、不参与变量重命名。
- 日志改进：在总节点/边统计后，追加 per-problem 平均节点/边数，便于设置 `max_nodes`。

- 求解输出增强：在 `scripts/run_batch.py` 生成的结果中，每题对象新增两项以便审计与后续绘图/重放：
  - `point_lines`: 形如 `point a x y` 的行列表（按点名排序）；
  - `points`: 结构化数组 `[{"name": str, "x": float, "y": float}]`。

- 证明图一键筛选+修剪合并：新增 `scripts/filter_and_prune.py`，支持对 results.json 先筛选出 `aux_points` 非空题目，再进行图修剪，并将“筛选前/修剪后”两张图合成为一张对比图输出；同时写出 `*_aux.json` 与 `*_aux_pruned.json` 以便后续处理与可视化。

- 规则提炼与去重：新增 `scripts/rename_and_deduplicate.py`，从 `*_aux_pruned.json` 中提取 `proposition_rule`，对同构（重命名等价）规则进行去重；去重后写出 `*_rules.txt`，重复项写入 `duplicated_rules.txt`。

- 单题图与修剪器：新增 `src/newclid/data_discovery/single_proof_graph.py`（单题粒度的证明图构建）与 `graph_pruner.py`（基于前提与是否包含辅助点的规则级修剪），配合 `proof_graph_visualizer.py` 完成单题可视化与合图能力。

并行与脚本更新（多进程 seeds_mproc）
- 新增“种子级并行挖掘”通道：
  - 子进程仅负责搜索（按 seed 扩展并通过 emit 推送原始模式对象），不做 schema/过滤。
  - 主进程集中完成 schema 转换、两层去重（结构签名 + 规范化 schema）、过滤（可选丢弃 unknown、变量闭包兜底与依赖过滤）与写入（流式或批量）。
- 脚本参数（`Newclid/scripts/mine_schemas.py`）：支持常见命令行参数，推荐编辑脚本顶部的 CONFIG 常量以控制引擎/阈值/剪枝/时间预算等。
- 全局扩展预算（重要变化）：
  - seeds_mproc 下，`debug_limit_expansions` 作为“全体子进程共享”的严格上限实现，使用 `multiprocessing.Semaphore` 作为跨进程预算；每次可导致结构增长的扩展尝试前均会尝试消耗 1 个配额，耗尽后所有 worker 将不再产生新扩展。
  - `single` 与 `seeds` 引擎下则为“当前一次运行/当前种子内”的本地上限。
- 死锁修复与可靠退出：
  - 工作队列采用 `JoinableQueue` + 阻塞式 `get()`；在启动前预投递与 worker 数相同的哨兵 `None`，worker 消费到哨兵后 `task_done()` 并退出。
  - 主进程对每次 `put` 调用都有匹配的 `task_done()`；`jobs.join()` 不再挂起。
  - 结果通道使用 `qout`；每个 worker 结束时会向 `qout` 发送一次 `None` 作为完成信号，主进程据此统计 worker 退出并收尾。
  - 加入 `maxsize` 以防止输出洪泛，emit 端采用带超时的 `put` 避免阻塞。
- 日志顺序：不再调用整体 `run_*`，而是在主进程汇总后统一记录耗时。
推荐入口脚本：
- `Newclid/scripts/mine_schemas.py`：挖掘（分叉/规则仅），写出结构化 patterns 与载荷
- `Newclid/scripts/filt_schemas.py`：读取挖掘结果进行筛选与审计，生成终态 JSON 与 NDJSON 审计
- `Newclid/scripts/visualize_schemas.py`：将已筛选或原始挖掘结果进行可视化渲染
- `Newclid/scripts/filter_and_prune.py`：对 run_batch 结果一键筛选（含辅助点）并修剪，输出 `_aux.json/_aux_pruned.json` 与合图
- `Newclid/scripts/rename_and_deduplicate.py`：从 `_aux_pruned.json` 提取命题规则、去重与落盘

### 5.2 数据模型与主要类
- ProofGraph
  - 存储节点与边、问题内局部 ID 映射、规则步映射等。
  - 公有字段：
    - `nodes: Dict[node_id, {type, label/code, args, problem_id, layer, ...}]`
    - `edges: List[(src_id, dst_id)]`
    - `fact_id_map: {problem_id: {id_local: fact_node_id}}`
    - `rule_step_map: {problem_id: {step_index: rule_node_id}}`
  - 关键方法：
    - `parse_facts_from_text(problem_id, text)`：解析 fact 子句并登记 fact 节点（layer=1）。
    - `parse_proof_step(line)`：解析单条 proof 步骤（结论 + 规则 + 前提 IDs）。
    - `add_rule_step(...)`：创建 rule 节点、连接前提→规则、规则→结论，缺失前提创建占位 fact。
    - `from_single_result(result_obj)` / `from_results_json(path)` / `from_results_obj(obj)`：构建整图入口。
- MergedGraph
  - 将所有题目的子图合并为一张大图 G*，节点标签规范化为 `F:{predicate}` 与 `R:{code}`；保留 `orig_node_id` 与 `problem_id`，不跨题连边。
- GSpanMiner
  - 构造合并图，并提供两种挖掘入口：
    - `run()`：路径挖掘变体（仅简单路径）。
  - `run_branched(...)`：分叉子图挖掘（规则完整性 + FRF 原子扩展 + 可选生产者接入），含鲁棒性修复。
  - `run_rules_only(...)`：规则仅挖掘；内部构建规则邻接 r1→r2（若存在 r1→F 且 F→r2，且同题），在仅含规则的图上扩展；输出阶段用 `pattern_to_schema_rules_only(...)` 还原前提与唯一结论。
  - 支持度阈值 `min_support` 可为绝对值（int）或比例（float 0~1）。

### 5.3 运行方法（命令）
```sh
/usr/bin/env python3 Newclid/scripts/mine_schemas.py
/usr/bin/env python3 Newclid/scripts/filt_schemas.py
/usr/bin/env python3 Newclid/scripts/visualize_schemas.py
# 证明图（筛选+修剪+合图，对 run_batch 输出进行处理）
/usr/bin/env python3 Newclid/scripts/filter_and_prune.py
# 从 *_aux_pruned.json 中提取并去重规则
/usr/bin/env python3 Newclid/scripts/rename_and_deduplicate.py
```
超参与模式从脚本内 `CONFIG` 修改。

默认数据集：
- 路径挖掘默认 `r07_expanded_problems_results_lil.json`；
- 分叉/规则仅默认 `r07_expanded_problems_results.json`。

### 5.4 输出与落盘
- 统一落盘目录：`data_discovery/data/`
- 文件名：
  - 分叉挖掘（fact_rule）：`branched_mining.json`
  - 规则仅挖掘（rule_only）：`rules_only_mining.json`
- 文件结构（示例字段）：
  - `created_at`: 生成时间（ISO 格式）
  - `proof_graph`: 原图统计（每题与合并图）
  - `merged_graph`: 合并图统计与标签覆盖度
  - `params`: 运行参数快照（来自脚本内 CONFIG）
  - `timing_sec`: 各阶段耗时
  - `pattern_count`: 模式总数
  - `patterns_summary_topN`: 概览（前 N 条）
  - `patterns`: 完整列表（含 `labels/nodes/edges/support/pids/embeddings/schema/rendered` 等）
- 说明：
  - 路径挖掘 demo 不写入文件，仅打印到 stdout；
  ## 5. 代码结构与运行入口

  （完整的 data_discovery 代码与数据清单见文末“附录A”。以下仅保留当前有效组件与脚本。）

  ### 5.1 关键组件（src/newclid/data_discovery）

  - `filter_and_prune_engine.py`：一键处理引擎，串联“含 aux 筛选 → 去重 → 建图 → 修剪 → 可视化 → 规则提取”。
  - `single_proof_graph.py`：单题证明图构建（fact-rule 二分图）。
  - `proof_graph.py`：通用证明图结构与解析工具。
  - `graph_pruner.py`：基于前提/是否含辅助点的规则级修剪器（含兄弟规则保护条件）。
  - `proof_graph_visualizer.py`：证明图可视化（legend/配色/布局/标签、角标注）。
  - `aux_extractor.py`：辅助点信息抽取与判断。
  - `rule_extractor.py`：从修剪后图中提取 `proposition_rule` 并规范化重命名。
  - `solver_utils.py`：与求解器/数值检查相关的辅助工具。

  ### 5.2 脚本（scripts）

  - `run_batch.py`：集中参数生成/收集 results 的入口（推荐先运行）。
  - `filter_and_prune.py`：对 results 进行筛选（含 aux）与修剪，可视化与规则提取为主；可选写出 `*_aux_pruned.json`。
  - `plot_proof_graphs.py`：对指定 JSON 结果批量绘图（与可视化器对齐）。
  - `translate_rule_to_problem.py`、`translate_rules_to_problem.py`：规则到题目的转写辅助。

  ### 5.3 运行方法（命令）

  ```sh
  # 1) 生成或获取题目结果（示例）
  /usr/bin/env python3 Newclid/scripts/run_batch.py

  # 2) 筛选+修剪+可视化+规则提取（可选写出 *_aux_pruned.json）
  /usr/bin/env python3 Newclid/scripts/filter_and_prune.py

  # 3) 可视化（如对特定结果重复绘制）
  /usr/bin/env python3 Newclid/scripts/plot_proof_graphs.py
  ```
  超参与模式一般在脚本顶部/CONFIG 常量中修改；本仓库不再提供基于 gSpan 的挖掘脚本入口。

  ### 5.4 输出与落盘

  - 统一目录：`src/newclid/data_discovery/data/`
  - 典型产物：
    - 可选中间结果：`*_aux_pruned.json`（筛选含 aux + 修剪后的题目对象，仍含 `aux_points` 信息）。
    - 可视化：输出到配置的图片目录（如 `proof_graphs/`），支持合并对比图（筛选前/修剪后）。
    - 规则文本：去重/规范化后的 `*_rules.txt` 与重复项 `duplicated_rules.txt`（若启用规则导出）。

  ### 5.5 兼容性与历史说明

  早期文档与脚本中涉及的 gSpan 挖掘器（路径/分叉/规则仅）、schema 生成与筛选（schema_miner/schema_filter）、schema 可视化与批评估（schema_eval.py）等，已从当前仓库实现中移除。若后续需要恢复该线，可在“历史版本/分支”或“未来规划”中另行说明。
- 数据与样例（输入/参考）
  - `src/newclid/data_discovery/r07_expanded_problems_results_lil.json`：r07 扩展结果（轻量版）
  - 其他（用于开发/统计）
    - `src/newclid/data_discovery/discovery_aux_data.jsonl`
    - `src/newclid/data_discovery/lil_data.jsonl`
    - `src/newclid/data_discovery/rules_with_discovery.txt`

- 其他工具
  - `scripts/translate_rule_to_problem.py`：规则到题目转写工具

- 包装与入口
  - `src/newclid/data_discovery/__init__.py`：模块导出
  - `src/newclid/data_discovery/summary_and_todo.md`：阶段记录（文档）

#### A.2 生成数据产物（结果与审计）

统一落盘目录：`src/newclid/data_discovery/data/`（审计为 NDJSON）。

### 附录A：data_discovery 代码与数据目录清单

基于当前分支目录扫描，仅列出现行有效的脚本与模块；若后续有增删，将在附录处持续更新。

#### A.1 代码（按功能分类，列至文件级）

- 图构建与解析
  - `src/newclid/data_discovery/proof_graph.py`
  - `src/newclid/data_discovery/single_proof_graph.py`
  - `src/newclid/data_discovery/solver_utils.py`

- 筛选/修剪/可视化/抽取
  - `src/newclid/data_discovery/filter_and_prune_engine.py`
  - `src/newclid/data_discovery/graph_pruner.py`
  - `src/newclid/data_discovery/aux_extractor.py`
  - `src/newclid/data_discovery/proof_graph_visualizer.py`
  - `src/newclid/data_discovery/rule_extractor.py`

- 脚本与入口
  - `scripts/run_batch.py`
  - `scripts/filter_and_prune.py`
  - `scripts/plot_proof_graphs.py`
  - `scripts/translate_rule_to_problem.py`
  - `scripts/translate_rules_to_problem.py`

- 数据与样例（输入/参考）
  - `src/newclid/data_discovery/r07_expanded_problems_results_lil.json`
  - `src/newclid/data_discovery/data/`（统一输出目录）

#### A.2 生成数据产物（结果与审计）

统一落盘目录：`src/newclid/data_discovery/data/`

| 文件/目录 | 角色 | 生成脚本/来源 | 说明 |
|---|---|---|---|
| `*_aux_pruned.json` | 筛选含 aux + 修剪后的题目对象 | `scripts/filter_and_prune.py` | 可选中间产物，含 `aux_points` |
| `proof_graphs/` 或配置目录 | 证明图像 | `scripts/filter_and_prune.py` / `scripts/plot_proof_graphs.py` | 支持合成对比图与 legend 模式 |
| `*_rules.txt` | 规则文本输出 | `scripts/filter_and_prune.py`（启用规则导出时） | 统一重命名，rule.txt 风格 |
| `duplicated_rules.txt` | 重复项清单 | `scripts/filter_and_prune.py`（启用时） | 记录同构/重命名等价的重复项 |
- `label_mode="legend"` 时，节点上使用短名（F1/F2/R1/C），右上角 Legend 显示短名与完整标签映射，避免节点内文字拥挤；
