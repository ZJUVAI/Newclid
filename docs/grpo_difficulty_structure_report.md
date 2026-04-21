# GRPO 难度结构分析报告

最后更新：2026-04-21

## 分析对象

- 数据集：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v10_auxfix_relabel20k_calib/difficulty_labels_auxfix_20k.jsonl`
- 样本数：`20000`
- 难度指标：`pass_at_16`
- 结构字段：
  - `aux_points_total`
  - `aux_segment_count`
  - `n_premises`

本次分析由脚本：

- `scripts/grpo/analyze_difficulty_structure.py`

生成，产物位于：

- summary：`analysis/grpo_difficulty_structure_v10_auxfix_20k/summary.json`
- 图目录：`analysis/grpo_difficulty_structure_v10_auxfix_20k/plots`

主要图文件：

- `analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_vs_aux.png`
- `analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_vs_aux_segments.png`
- `analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_vs_premises.png`
- `analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_heatmap.png`
- `analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_heatmap_aux_segments.png`

## 总体结论

- 当前 `20k aux-fix` 标签池整体偏易：
  - `avg pass@16 = 0.8319`
  - `median pass@16 = 1.0`
  - `one_ratio = 0.7774`
  - `zero_ratio = 0.1288`
- `aux_points_total` 与 `pass_at_16` 呈中等偏弱负相关：
  - `Spearman rho = -0.1656`
- `aux_segment_count` 与 `pass_at_16` 也呈负相关，但比 `aux_points_total` 更弱：
  - `Spearman rho = -0.0931`
- `n_premises` 与 `pass_at_16` 的整体关系很弱：
  - `Spearman rho = 0.0390`
  - 说明在当前这批数据里，题目能否被模型解出，更多受 aux 结构复杂度影响，而不是单纯由 premises 数量线性决定

## `aux_points_total` 与难度

![`aux_points_total` 与 `pass_at_16` 的关系](../analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_vs_aux.png)

按 `aux_points_total` 分组的主要结果：

- `1` 点：`count=9731`, `avg_pass=0.8735`, `zero_ratio=0.1110`, `one_ratio=0.8567`
- `2` 点：`count=8744`, `avg_pass=0.7999`, `zero_ratio=0.1322`, `one_ratio=0.7011`
- `3` 点：`count=1186`, `avg_pass=0.7762`, `zero_ratio=0.1914`, `one_ratio=0.7260`
- `4` 点：`count=291`, `avg_pass=0.6587`, `zero_ratio=0.3333`, `one_ratio=0.6460`

解释：

- 从 `1 -> 4` 点，`avg_pass` 明显下降，`zero_ratio` 明显上升
- 这说明“需要更多 aux 点”的题，整体更难
- `5+` 点样本量很小：
  - `5` 点只有 `39`
  - `6` 点只有 `8`
  - `7` 点只有 `1`
- 因此 `5+` 点的统计只能作为方向参考，不能当主结论

结合图看：

- 蓝线 `avg pass@16` 从 `aux_points_total=1` 开始整体下滑
- 红线 `zero_ratio` 整体上升
- 这两条线同时变化，说明 `aux_points_total` 是当前数据里最稳定的难度 proxy 之一
- `4+` 点之后波动变大，主要是样本量开始明显不足

![`aux_points_total × n_premises` 的平均 `pass_at_16` 热力图](../analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_heatmap.png)

结合热力图看：

- 在大多数 `n_premises` 区间里，`aux_points_total=1` 的区域都偏亮，说明更容易
- `aux_points_total=3/4` 的区域整体更暗，说明需要更多辅助点的题更难
- 但暗度变化不是完全单调，说明 `n_premises` 会调制这种关系，而不是简单叠加

## `aux_segment_count` 与难度

![`aux_segment_count` 与 `pass_at_16` 的关系](../analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_vs_aux_segments.png)

按 `aux_segment_count` 分组的主要结果：

- `1` 段：`count=10092`, `avg_pass=0.8441`, `zero_ratio=0.1369`, `one_ratio=0.8261`
- `2` 段：`count=8462`, `avg_pass=0.8243`, `zero_ratio=0.1103`, `one_ratio=0.7244`
- `3` 段：`count=1121`, `avg_pass=0.8212`, `zero_ratio=0.1445`, `one_ratio=0.7681`
- `4` 段：`count=279`, `avg_pass=0.6871`, `zero_ratio=0.3047`, `one_ratio=0.6738`

解释：

- `aux_segment_count` 增加后，难度也有上升趋势，但没有 `aux_points_total` 那么稳定
- 一个合理解释是：
  - “点数更多”比“段数更多”更直接对应真实构造复杂度
  - 有些多 segment 样本并没有真正引入更多独立点，因此难度提升不如 `aux_points_total` 明显

结合图看：

- `1 -> 3` 段的变化比 `aux_points_total` 更平缓
- 真正明显变难的是 `4` 段附近
- 这说明 segment 数量更像是“粗粒度复杂度信号”，但区分度不如总 aux 点数

![`aux_segment_count × n_premises` 的平均 `pass_at_16` 热力图](../analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_heatmap_aux_segments.png)

结合热力图看：

- `aux_segment_count=1/2` 的主区域亮度接近
- `4` 段区域明显更暗，但覆盖面较小
- 因此这个特征适合当辅助结构约束，不太适合单独充当主 selector 信号

## `n_premises` 与难度

![`n_premises` 与 `pass_at_16` 的关系](../analysis/grpo_difficulty_structure_v10_auxfix_20k/plots/avg_pass_vs_premises.png)

整体上：

- `n_premises` 的秩相关只有 `0.039`
- 说明单看 premises 数量，几乎看不出稳定的一阶单调关系

按分组看：

- 较低的 `avg_pass` 桶包括：
  - `n_premises=2`: `count=85`, `avg_pass=0.6662`
  - `n_premises=22`: `count=134`, `avg_pass=0.7388`
  - `n_premises=23`: `count=76`, `avg_pass=0.6834`
- 较高的 `avg_pass` 桶包括：
  - `n_premises=11`: `count=1340`, `avg_pass=0.8699`
  - `n_premises=19`: `count=196`, `avg_pass=0.8661`
  - `n_premises=21`: `count=94`, `avg_pass=0.8677`

解释：

- 这里看不到“premises 越多越难”这种简单规律
- 更像是：
  - 某些特定题型在 `10~21` 个 premises 时恰好更容易被当前模型处理
  - premises 数量本身不是主因，题型和 aux 结构更关键

结合图看：

- `n_premises` 的蓝线整体起伏很明显，但没有统一方向
- 红线 `zero_ratio` 也不是稳定上升或下降
- 这说明 `n_premises` 更像一个混合了题型分布的弱特征，而不是当前模型下的一阶难度轴

## 模型分析

脚本用了两组 logit 模型：

1. `success_count / 16 ~ aux + premises + aux*premises`
2. `1(pass_at_16 > 0) ~ aux + premises + aux*premises`

### 以 `aux_points_total` 为结构变量

`binomial_pass_rate`：

- `aux_points_total` 系数：`-0.5150`
- `n_premises` 系数：`-0.0393`
- 交互项系数：`+0.0157`
- `pseudo_r2 = 0.0148`

`logit_nonzero_pass`：

- `aux_points_total` 系数：`-0.6388`
- `n_premises` 系数：`-0.0999`
- 交互项系数：`+0.0240`
- `pseudo_r2 = 0.0197`

解释：

- 在控制 `n_premises` 后，`aux_points_total` 增加仍然显著降低可解率
- 正的交互项说明：
  - 当 `n_premises` 更大时，`aux_points_total` 带来的负面影响会被部分抵消
  - 也就是说，“多 aux 点”不一定在所有 premise 区间都同样难

### 以 `aux_segment_count` 为结构变量

`binomial_pass_rate_by_aux_segments`：

- `aux_segment_count` 系数：`-0.6391`
- `n_premises` 系数：`-0.0786`
- 交互项系数：`+0.0438`
- `pseudo_r2 = 0.0052`

`logit_nonzero_pass_by_aux_segments`：

- `aux_segment_count` 系数：`-0.6339`
- `n_premises` 系数：`-0.1319`
- 交互项系数：`+0.0495`
- `pseudo_r2 = 0.0118`

解释：

- `aux_segment_count` 也是显著负向，但解释力弱于 `aux_points_total`
- 这和上面的分组统计一致：
  - segment 数量能反映一部分难度
  - 但“总 aux 点数”仍然是更好的结构 proxy

## 对数据筛选的直接含义

1. 如果目标是构造一个更有学习信号的 GRPO 训练集，不能只看 `n_premises`
- premises 数量本身太弱
- 只按 premises 扩池，容易混入大量“题面长但并不难”的样本

2. `aux_points_total` 比 `aux_segment_count` 更值得纳入 selector
- 它和 `pass_at_16` 的关系更稳定
- 更适合作为 hard / mid 样本的结构约束

补充：

- 如果需要一个主结构 proxy，优先用 `aux_points_total`
- 如果需要限制“结构过于单薄”的样本，再额外加 `aux_segment_count` 下限或分桶覆盖

3. 当前 `20k aux-fix` 池仍然整体偏易
- 即便 `aux_points_total=2/3` 的样本，`avg_pass` 依然偏高
- 这也再次说明：
  - 只在 `20k` 上微调 selector，空间有限
  - 完整 `150k full aux-fix` relabel 之后再做 selector 更合理

## 下一步建议

- 等 `remaining130k` aux-fix relabel 完成后，先对 full `150k` 新标签重复跑同一脚本
- 重点对比：
  - `aux_points_total_vs_pass_at_16`
  - `aux_segment_count_vs_pass_at_16`
  - `grouped_by_aux`
  - `grouped_by_aux_segments`
  - `heatmap` 与 `heatmap_aux_segments`
- 如果 full `150k` 上 `aux_points_total >= 2` 的中低 pass 区间供给显著增加，再进入新的 selector / smoke
