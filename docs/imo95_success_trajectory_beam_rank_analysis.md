# IMO-95 Success Trajectory Beam-Rank Analysis

## 分析对象

本报告分析以下评测运行中，**成功题目的正确轨迹**在搜索过程中的 beam 排位分布：

- 运行目录：
  `results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z`
- 汇总 CSV：
  `results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z.csv`

对应的明细产物：

- 逐步轨迹 CSV：
  `results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z/analysis/success_trajectory_beam_rank_steps.csv`
- 汇总 JSON：
  `results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z/analysis/success_trajectory_beam_rank_summary.json`
- 分布图：
  `./_static/imo95_success_trajectory_beam_rank_distribution.png`
- 分阶段点状图：
  `./_static/imo95_success_trajectory_beam_rank_phase_scatter.png`

## Beam 排位的定义

这里需要区分两个不同概念：

1. `candidate_rank`

- 含义：某个父节点展开时，该候选在本次生成候选列表中的序号。
- 来源：`candidate_transition` 事件中的 `candidate_rank` 字段。

2. `frontier_beam_rank`

- 含义：某个候选经过 DDAR 验证后，如果进入下一层 frontier，它在该层 beam 中的真实排序位置。
- 这不是 trace 里现成字段，而是根据代码逻辑重建出来的。

beam 的真实排序规则来自：

- [src/newclid/agent/runtime/search_runtime.py](/C20545/home/wangzi/GenesisGeo-grpo/src/newclid/agent/runtime/search_runtime.py:309)
- [src/newclid/agent/base.py](/C20545/home/wangzi/GenesisGeo-grpo/src/newclid/agent/base.py:326)

具体做法：

- 只对 `decision="queued_next_depth"` 的节点计入下一层 frontier。
- 在同一 depth 内，按 `beam_score_after` 降序排序。
- 分数并列时，用 `path_key` 的稳定顺序打破平局。
- 只保留 `beam_size=512` 的节点。

因此，本报告中的“成功轨迹在 beam 中的排位”，默认指的是 **中间成功前缀进入下一层 frontier 时的 `frontier_beam_rank`**。

最后一步通常是“从当前节点展开后直接 solved”，它不会进入下一层 frontier，所以只有 `candidate_rank`，没有 `frontier_beam_rank`。

## 方法

分析脚本：

- [scripts/analyze_success_trajectory_beam_rank.py](/C20545/home/wangzi/GenesisGeo-grpo/scripts/analyze_success_trajectory_beam_rank.py)

脚本流程：

1. 从评测 CSV 中读取成功题目列表。
2. 对每道成功题，读取对应 `problems/*.jsonl` 原始事件流。
3. 从 `problem_end.final_node_id` 回溯最终成功节点。
4. 用 `node_id -> parent_node_id` 重建正确轨迹。
5. 在每个 depth 上，对所有 `queued_next_depth` 节点按真实 beam 规则重新排序。
6. 将正确轨迹上的中间节点映射到 `frontier_beam_rank`。
7. 输出逐步 CSV、汇总 JSON 和分布图。

## 总体结论

从汇总 JSON 可得：

- 成功题总数：`65`
- 其中 base DDAR 直接解出：`1`
- 经过搜索后成功：`64`
- 成功轨迹逐步记录总数：`151`
- 可计算 `frontier_beam_rank` 的中间步骤数：`87`

唯一的 base-solved 题目是：

- `imo_sl_2009_g2`

它的 `final_node_id=0`，没有进入 beam 搜索，因此没有 beam 排位可分析。

### 中间成功前缀的 frontier beam rank 分布

- 最小值：`1`
- 25 分位：`5`
- 中位数：`11`
- 75 分位：`40`
- 最大值：`511`

这说明：

- 大量成功轨迹在搜索早期确实处于 beam 前列。
- 但也存在明显长尾，一部分最终成功轨迹在中间层一度掉到 beam 很靠后的位置。
- 极端情况下，正确轨迹曾排到第 `511` 名，几乎处于 `beam_size=512` 的边缘。

### 最后一步的 candidate rank 分布

最后一步没有下一层 beam 排位，因此使用 `candidate_rank` 描述“解出时在父节点候选中的序号”：

- 最小值：`0`
- 25 分位：`5`
- 中位数：`16.5`
- 75 分位：`23`
- 最大值：`31`

这说明最终解并不总是来自父节点的前几个候选，后段候选同样经常贡献最终成功。

## 分布图

![IMO-95 success trajectory beam rank distribution](./_static/imo95_success_trajectory_beam_rank_distribution.png)

图中只统计 **中间步骤** 的 `frontier_beam_rank`，不包含最后一步的 `candidate_rank`。

左图是直方图，右图是累计分布（ECDF）。

从图中可以看到：

- 排名 `1-16` 的区间最密集。
- 分布右尾较长，不是一个只集中在 beam 顶部的窄分布。
- 超过 `256` 的尾部样本数量不多，但确实存在，并且这些样本最终仍然能继续走到成功。

## 分阶段点状分布

![IMO-95 success trajectory beam rank phase scatter](./_static/imo95_success_trajectory_beam_rank_phase_scatter.png)

这张图按 `depth` 分组，把每个成功轨迹中间步骤的 `frontier_beam_rank` 画成散点，纵轴使用对数刻度。

可以直接读出几个现象：

- `depth=0` 的成功前缀大多集中在 beam 前部，但仍有少量点落到更后的位置。
- `depth=1` 的离散程度明显增大，已经出现很多 `100+` 甚至 `400+` 的成功前缀。
- `depth=2` 的样本数较少，但长尾最明显，存在接近 beam 下边界的样本。

结合上面的总体分布，这说明：

- 搜索越往后，成功前缀在 beam 中的位置越不稳定。
- 后续深度上的成功往往依赖于 beam 仍然保留住这些中后部候选。

## 成功深度分布

按最终成功发生的搜索深度统计：

- `depth = 0`：`6` 题
- `depth = 1`：`34` 题
- `depth = 2`：`19` 题
- `depth = 3`：`5` 题
- `base solved`：`1` 题

按成功轨迹长度统计：

- 长度 `0`：`1` 题
- 长度 `1`：`6` 题
- 长度 `2`：`34` 题
- 长度 `3`：`19` 题
- 长度 `4`：`5` 题

说明本次 run 的大部分成功发生在较浅层，主要集中在 `depth=1`。

## 代表性案例

### 1. 一路保持靠前：`imo_sl_1999_g6`

成功轨迹：

- depth 0: `candidate_rank=0`, `frontier_beam_rank=1`
- depth 1: `candidate_rank=1`, `frontier_beam_rank=4`
- depth 2: `candidate_rank=10`, `frontier_beam_rank=75`
- depth 3: `candidate_rank=30`, 直接 solved

解读：

- 前两层都非常靠前。
- 到第三层前已掉到 `frontier rank=75`，但仍然足以保留在 beam 中并最终成功。
- 最终解本身来自父节点的第 `30` 个候选，不是顶序候选。

### 2. 几乎掉出 beam 仍然成功：`imo_sl_2002_g8`

成功轨迹：

- depth 0: `candidate_rank=6`, `frontier_beam_rank=7`
- depth 1: `candidate_rank=1`, `frontier_beam_rank=39`
- depth 2: `candidate_rank=14`, `frontier_beam_rank=511`
- depth 3: `candidate_rank=0`, 直接 solved

解读：

- 这是本次 run 中最极端的案例。
- 正确轨迹在 depth 2 时只排到 `511`，几乎位于 beam 末尾。
- 如果 beam 再小一点，这条成功轨迹很可能会被截断。

### 3. 早层不算顶序，但还能稳定命中：`imo_sl_2006_g6`

成功轨迹：

- depth 0: `candidate_rank=2`, `frontier_beam_rank=3`
- depth 1: `candidate_rank=26`, 直接 solved

解读：

- 正确的第一步并不是 top-1，而是 beam 中第 `3` 名。
- 第二步的最终解来自第 `26` 个候选，说明父节点内部的候选后段也有明显价值。

## 最差中间 beam 排名的 Top 10

根据汇总 JSON：

1. `imo_sl_2002_g8`: `511`
2. `imo_sl_2015_g5_variant`: `447`
3. `imo_sl_2011_g7`: `438`
4. `imo_sl_2016_g5_variant`: `438`
5. `imo_sl_2020_g7a`: `409`
6. `imo_sl_2016_g6_variant`: `329`
7. `imo_sl_2020_g8_variant`: `328`
8. `imo_sl_2012_g5`: `311`
9. `imo_sl_2017_g4`: `267`
10. `imo_sl_2009_g6`: `251`

这些案例表明：

- 成功路径未必始终停留在 beam 顶部。
- 当前 `beam_size=512` 对于保住一部分长尾成功轨迹是有实际作用的。

## 结论与启示

1. 成功轨迹整体偏前，但并不只集中在极前部。

- 中位数 `11` 说明多数成功前缀确实在 beam 前列。
- 但最大值 `511` 说明成功轨迹存在显著长尾。

2. 较大的 beam 对保留长尾正确轨迹是有价值的。

- 至少在这次 run 中，确实存在接近 beam 下边界的成功前缀。
- 如果缩小 beam，这些题目可能会从“可成功”变成“被提前剪枝”。

3. 最终解经常不是父节点的头部候选。

- 最后一步 `candidate_rank` 中位数 `16.5`，上四分位 `23`。
- 说明只看 top-k 很小的候选会损失不少成功机会。

4. 需要区分“候选序号”和“beam 排名”。

- `candidate_rank` 反映单次生成内部顺序。
- `frontier_beam_rank` 才反映跨父节点竞争后，在全局下一层 frontier 中的位置。

## 相关文件

- 评测运行：
  [run_meta.json](/C20545/home/wangzi/GenesisGeo-grpo/results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z/run_meta.json)
- 逐步明细：
  [success_trajectory_beam_rank_steps.csv](/C20545/home/wangzi/GenesisGeo-grpo/results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z/analysis/success_trajectory_beam_rank_steps.csv)
- 汇总统计：
  [success_trajectory_beam_rank_summary.json](/C20545/home/wangzi/GenesisGeo-grpo/results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260513T073845Z/analysis/success_trajectory_beam_rank_summary.json)
