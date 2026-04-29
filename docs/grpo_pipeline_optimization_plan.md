# GRPO 迭代状态与后续计划

最后更新：2026-04-29 | 当前 commit: `da70fd477dc18c4859c1c96b8014e5c954b08254`

## 背景

- 基础模型：`vlm_sft44`，路径为 `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- 原始数据源（版本相关）：
  - v12 及以前：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
  - v13：`/C20545/home/wangzi/GenesisGeo/datasets/20260421_maxaux5/geometry_clauses10_samples100k.jsonl`
  - v14 及以后：`/C20545/home/wangzi/GenesisGeo/datasets/maxaux8/20260421/geometry_clauses10_samples100k.jsonl`
- 当前训练入口：`scripts/grpo/train_grpo.sh`
- 当前 selector 入口：`scripts/grpo/select_debug_set.py`
- 核心判断：主要瓶颈仍然是数据分布，而不是 GRPO 训练超参数

---

## 版本历史（主线 + 归档）

### v18 (2026-04-27~29) - 已归档（未优于 v17）

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_10k_v18`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v18_s1_4gpu_lr5e6`

**核心变更**：在 v17 基础上将训练集从 5k 扩大到 10k，500 步覆盖约 1.6 epoch（v17 为 3.2 epoch）

**数据集静态指标**：
- `selected_rows = 10000`，`zero_pass_ratio = 0.1299`（优于 5k 的 0.1736）
- `multi_point_shortage = 4000`（core 供给在 10k 规模下明显不足）

**Selector 参数说明**：v18 使用当前代码库的 `scripts/grpo/select_debug_set.py`（`bucket_unified`）生成数据集。参考 commit: `da70fd477dc18c4859c1c96b8014e5c954b08254`

**生成 v18 数据集的完整命令**：

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_10k_v18/grpo_train_selected_10000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_10k_v18/grpo_train_report_10000.json \
  --selection-policy bucket_unified \
  --target-size 10000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --mastered-pass-min 0.90 \
  --near-high-mid-max-pass 0.75 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0 \
  --mastered-fallback-min-fill-fraction 0.90 \
  --multi-segment-min-fraction 0.45 \
  --multi-point-min-fraction 0.40 \
  --family-min-fraction 0.10 \
  --goal-max-fraction 0.18 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --reward-mixed-zero-max-fraction 0.15 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --near-high-mid-min-fraction 0.03 \
  --greedy-success-max-fraction 1.0 \
  --pass-one-max-fraction 1.0 \
  --high-pass-min 0.75 \
  --high-pass-max-fraction 1.0 \
  --pass-one-value 1.0
```

**验证**：按上述命令生成的数据集与现有 v18 数据集完全一致（集合和顺序都相同）。

**关键差异（v17 → v18）**：
- `--target-size 5000` → `10000`
- `--reward-mixed-zero-max-fraction 0.20` → `0.15`

**训练配置**：与 v17 完全一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`

**评估结果**：
- ✅ dev_imo：**14/16**（与 v17 持平）
- ✅ imo_95：**55/95**（低于 v17 的 59/95，-4 题）
- 评估产物：`results/v18_lr5e6_checkpoint500/`
  - dev_imo CSV：`eval_single_problem_multi_gpu_vlm_dev_imo_*_checkpoint-500_*.csv`
  - imo_95 合并 CSV：`imo_95_v18_checkpoint500_merged.csv`

**对比基线**：

| 版本 | dev_imo | imo_95 | 备注 |
|------|---------|--------|------|
| SFT baseline | 14/16 | - | pre-GRPO |
| v16 checkpoint-500 | 14/16 | 55/95 | lr=5e-6，2k 数据集，8 epoch |
| **v17 checkpoint-500** | **14/16** | **59/95** | lr=5e-6，5k 数据集，3.2 epoch，**当前最佳** |
| v18 checkpoint-500 | 14/16 | 55/95 | lr=5e-6，10k 数据集，1.6 epoch |

**imo_95 逐题对比（v17 → v18）**：
- v18 回退（-4）：`imo_sl_2002_g7_variant`、`imo_sl_2009_g8`、`imo_sl_2013_g2`、`imo_sl_2020_g6`
- v18 新增（+0）：无
- 净变化：-4 题

**失败原因分析（基于 imo_sl_2020_g6 单题 trace 对比）**：
- v18 在 depth0 未生成 v17 解题路径的关键第一步构造（`l = on_line l a b, on_line l c d`）
- v18 在 depth2 每节点 unique 候选数显著更多（31.9 vs 17.5），重复率从 45% 降至 0.2%
- v18 搜索更"发散"但关键构造的概率质量下降，导致解题路径断裂
- 根本原因：10k 数据集（1.6 epoch）相比 5k（3.2 epoch）重复率更低，但模型对关键构造的集中度也随之下降

**结论**：
- 扩大数据集到 10k 并不带来进一步提升，反而因 epoch 数减少（3.2 → 1.6）导致模型对关键构造的学习不充分
- v17（5k，3.2 epoch）仍是当前最优配置
- 下一步应探索：在保持 3.2 epoch 的前提下扩大数据集，或改善 10k 数据集的质量（降低 multi_point_shortage）

---

### v17 (2026-04-23) - **当前最优**

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6`

**核心变更**：在 v16 基础上将训练集从 2k 扩大到 5k，effective batch size 不变（32 problems/step），500 步覆盖约 3.2 epoch（v16 为 8 epoch）

**数据集静态指标**：
- `selected_rows = 5000`，`fallback_triggered = false`
- `selected_zero_pass_ratio = 0.1736`（v16: 0.05，因 reward_mixed_zero 配额按比例扩大）
- `selected_avg_proxy_reward_std = 0.3607`，`selected_median_proxy_reward_std = 0.3476`
- `multi_point_shortage = 573`（core 供给在 5k 规模下接近上限）

**Selector 参数说明**：v17 使用当前代码库的 `scripts/grpo/select_debug_set.py`（`bucket_unified`）生成数据集。参考 commit: `da70fd477dc18c4859c1c96b8014e5c954b08254`

**生成 v17 数据集的完整命令**：

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_selected_5000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/grpo_train_report_5000.json \
  --selection-policy bucket_unified \
  --target-size 5000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --mastered-pass-min 0.90 \
  --near-high-mid-max-pass 0.75 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0 \
  --mastered-fallback-min-fill-fraction 0.90 \
  --multi-segment-min-fraction 0.45 \
  --multi-point-min-fraction 0.40 \
  --family-min-fraction 0.10 \
  --goal-max-fraction 0.18 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --reward-mixed-zero-max-fraction 0.20 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --near-high-mid-min-fraction 0.03 \
  --greedy-success-max-fraction 1.0 \
  --pass-one-max-fraction 1.0 \
  --high-pass-min 0.75 \
  --high-pass-max-fraction 1.0 \
  --pass-one-value 1.0
```

**验证**：按上述命令生成的数据集与现有 v17 数据集完全一致（集合和顺序都相同）。

**训练配置**：与 v16 完全一致
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `NPROC_PER_NODE = 4`，`temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`
- `max_steps = 500`，`save_steps = 50`

**训练进度**：
- ✅ 500-step 训练：**已完成**（2026-04-23）
- 全程 `avg_zero_std = 0.1248`，`median_reward_std = 0.3415`，`max_consecutive_zero = 0`
- 前 50 步：`avg_zero_std = 0.0778`，`median_reward_std = 0.3569`（smoke gate 全部通过）
- 优于 v16 全程指标（avg_zero_std: 0.1670 → 0.1248，降低 25%）

**评估结果**：
- ✅ dev_imo：**14/16**（与 v16 和 SFT baseline 持平）
- ✅ imo_95：**59/95**（94 题完成，1 题未完成，优于 v16 的 55/95）
- ✅ checkpoint-300 验证：dev_imo **13/16**（低于 checkpoint-500，确认 500 步是最优点）
- 评估产物：`results/v17_lr5e6_checkpoint500/`
  - dev_imo CSV：`eval_single_problem_multi_gpu_vlm_dev_imo_*_checkpoint-500_*.csv`
  - imo_95 合并 CSV：`imo_95_v17_checkpoint500_merged.csv`

**对比基线**：

| 版本 | dev_imo | imo_95 | 备注 |
|------|---------|--------|------|
| SFT baseline | 14/16 | - | pre-GRPO |
| GRPO505 sv1 | 13/16 | - | 历史最佳 GRPO |
| v14 checkpoint-500 | 12/16 | - | lr=1e-4，后期退化 |
| v16 checkpoint-500 | 14/16 | 55/95 | lr=5e-6，2k 数据集，8 epoch |
| **v17 checkpoint-500** | **14/16** | **59/95** | lr=5e-6，5k 数据集，3.2 epoch，**当前最佳** |

**结论**：
- v17 是首个在 5k 数据集（3.2 epoch）上保持稳定的 GRPO 版本
- 训练指标优于 v16（avg_zero_std: 0.1670 → 0.1248，降低 25%）
- dev_imo 持平 SFT baseline，imo_95 提升 4 题（55 → 59），验证了 5k 数据集的有效性
- 扩大数据集、降低重复率（8 epoch → 3.2 epoch）对 GRPO 训练和评估都有益

**v17 深度分析（2026-04-27）**：

*训练稳定性对比（v16 vs v17）*：

| 区间 | v16 avg_zero_std | v17 avg_zero_std | 改善 |
|------|------------------|------------------|------|
| 1-50 | 0.0875 | 0.0778 | -11.1% |
| 1-170 | 0.1004 | 0.0909 | -9.5% |
| 171-300 | 0.1865 | 0.1231 | -34.0% |
| 301-500 | 0.2073 | 0.1518 | -26.8% |
| **全程 (1-500)** | **0.1653** | **0.1236** | **-25.2%** |

- v17 在所有训练阶段都优于 v16，尤其是后期（171-500）改善显著
- 两个版本都无 `max_consecutive_full_zero` 步数，训练全程稳定

*评估结果详细对比*：

| 版本 | dev_imo | imo_95 | 与 SFT baseline 对比 | 与 GRPO505 sv1 对比 |
|------|---------|--------|---------------------|-------------------|
| SFT baseline | 14/16 | - | - | +1 题 |
| GRPO505 sv1 | 13/16 | - | -1 题 | - |
| v16 | 14/16 | 55/95 | 持平 | +1 题 |
| **v17** | **14/16** | **59/95** | **持平** | **+1 题** |

*imo_95 新增解题（v16 → v17）*：
- ✅ `imo_sl_2002_g7_variant`
- ✅ `imo_sl_2009_g8`
- ✅ `imo_sl_2013_g2`
- ✅ `imo_sl_2020_g6`
- 无回退题

*Proposal 分布分析（dev_imo 14 题）*：

| 指标 | GRPO505 sv1 | v16 | v17 | v17 vs v16 |
|------|-------------|-----|-----|-----------|
| mean_unique_ratio | 0.3209 | 0.3739 | 0.3860 | +3.2% |
| mean_top1_share | 0.0216 | 0.0258 | 0.0306 | +18.6% |
| mean_effective_ratio | 0.2621 | 0.3174 | 0.3238 | +2.0% |

构造家族分布：

| 家族 | GRPO505 sv1 | v16 | v17 | v17 vs v16 |
|------|-------------|-----|-----|-----------|
| on_circum | 58.13% | 32.11% | 33.56% | +1.45% |
| on_circle | 26.20% | 22.93% | 22.61% | -0.32% |
| on_line | 10.37% | 21.18% | 21.06% | -0.12% |
| on_tline | 0.37% | 13.44% | 12.58% | -0.86% |
| on_bline | 2.91% | 6.19% | 5.37% | -0.82% |

**关键发现**：
1. **训练稳定性显著提升**：v17 的 avg_zero_std 全程降低 25%，后期（301-500）降低 27%
2. **评估性能稳步提升**：dev_imo 持平 SFT baseline，imo_95 净增 4 题无回退
3. **Proposal 分布健康**：
   - v17 相比 v16 略有改善（unique_ratio +3.2%）
   - 构造家族分布与 v16 基本一致，无明显 proposal shift
   - 相比 GRPO505 sv1 的严重 on_circum 偏移（58%），v16/v17 的分布更加平衡（~33%）
4. **数据集规模效应验证**：5k 数据集（3.2 epoch）优于 2k 数据集（8 epoch），降低重复率对训练和评估都有益

**下一步**：
- ✅ 已验证 checkpoint-300（13/16）低于 checkpoint-500（14/16），确认 500 步是最优点
- ✅ 已完成 v18（10k）训练与评估，结论见上节（未优于 v17）

---

### v16 (2026-04-22~23) - 已归档

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`（与 v14/v15 相同）

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_maxaux8_v16_s1_4gpu_lr5e6`

**核心变更**：在 v15 基础上切换为 4 卡 DDP（`NPROC_PER_NODE=4`），effective batch size 从 8 扩大到 32 problems/step

**训练配置**：
- `learning_rate = 5e-6`，`warmup_steps = 10`，`lr_scheduler_type = cosine`
- `per_device_train_batch_size = 1`，`gradient_accumulation_steps = 8`，`num_generations = 8`
- `temperature = 1.1`，`top_p = 0.95`，`top_k = 0`，`beta = 0.02`，`max_completion_length = 256`
- `max_steps = 500`，`save_steps = 50`

**训练进度**：
- ✅ 500-step 训练：**已完成**
- 全程 `avg_zero_std = 0.1670`，`median_reward_std = 0.3480`，`max_consecutive_zero = 0`
- 前 50 步：`avg_zero_std = 0.1202`，`median_reward_std = 0.3759`（smoke gate 全部通过）
- 无后期崩溃，完全避免了 v14 的 301-500 退化（v14 同阶段 `avg_zero_std = 0.57`）

**评估结果**：
- ✅ dev_imo：**14/16**（与 SFT baseline 持平，优于 v14 的 12/16）
- ✅ imo_95：**55/95**（94 题完成，1 题因 Ray 崩溃未完成）
- 评估产物：`results/v16_lr5e6_checkpoint500/`
  - dev_imo CSV：`eval_single_problem_multi_gpu_vlm_dev_imo_v0-20260422-154539_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260422T134636Z.csv`
  - imo_95 合并 CSV：`imo_95_v16_checkpoint500_merged.csv`

**对比基线**：

| 版本 | dev_imo | imo_95 | 备注 |
|------|---------|--------|------|
| SFT baseline | 14/16 | - | pre-GRPO |
| GRPO505 sv1 | 13/16 | - | 历史最佳 GRPO |
| v14 checkpoint-500 | 12/16 | - | lr=1e-4，后期退化 |
| **v16 checkpoint-500** | **14/16** | **55/95** | lr=5e-6，4卡，当前主线 |

**结论**：
- v16 是首个在 500-step 全程保持稳定且 dev_imo 不低于 SFT baseline 的 GRPO 版本
- 学习率从 1e-4 降至 5e-6 是关键改进，4 卡 DDP 进一步稳定了 reward variance

---

### v15 (2026-04-22) - 已归档

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`（与 v14 相同）

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_lr5e6`

**核心变更**：学习率从 `1e-4` 降至 `5e-6`，添加 `warmup_steps=10`，单卡

**训练进度**：
- ✅ 50-step smoke gate：**通过** (`avg_zero_std = 0.0682`, `median_reward_std = 0.3730`)
- 仅跑 50 步，作为 lr 调参验证，后续由 v16（4 卡）接替

---

### v14 (2026-04-22) - 已归档

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned`

**训练进度**：
- ✅ 50-step smoke gate：**通过** (`avg_zero_std = 0.2659`)
- ⚠️ 170-step mid gate：**部分通过** (`last50_avg_zero_std = 0.36`，略超阈值 0.35)
- ✅ 300-step 训练：**已完成**
- ✅ 500-step 训练：**已完成**
- ⚠️ dev_imo 评估：**12/16**（低于 SFT 的 14/16 和历史 GRPO505 的 13/16）

**结论**：
- 500-step 后半程（301-500）零方差占比升至 0.57，checkpoint-500 在 dev_imo 出现回退
- 根本原因：学习率 1e-4 相对 SFT 的 1e-5 偏高，导致后期策略分布偏移

---

### v13 及更早版本 - 历史归档

以下版本为早期探索，**详细记录见归档文件** `grpo_pipeline_optimization_plan_archive.md`。

#### v13 (2026-04-21)
- 数据集：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k/`
- 50-step smoke 边缘失败（avg_zero_std = 0.4364）
- 详见归档文档的"v13（2026-04-21）：命名映射与结论"部分

#### v3-v12 早期版本
- **v3_tiered**：pass-zero 污染严重（67.85%），smoke 失败
- **v4_reward_mixed**：引入 reward_mixed_zero 过滤，规模仅 800 条
- **v5_rewardmix_2k**：扩大到 2k，但 smoke 仍未通过（avg_zero_std = 0.4375）
- **v6_mid_strict_zero**：收紧 core window，略有改善但仍未过 gate
- **v7_structure_strict_zero**：首个通过 50-step smoke gate 的版本（avg_zero_std = 0.2900）
- **v8_structure_full150k_strict_zero**：补齐 150k 标注池，早期稳定性优于 v7
- **v9_stage_balanced**：引入 stage-balanced 策略
- **v10-v12**：geometry100k 数据源上的各种 selector 实验

**详细历史演进、静态指标、smoke 结果、关键 bug audit 与 aux-fix 基础设施见归档文件** `grpo_pipeline_optimization_plan_archive_v13_and_earlier.md`。

---

## 当前 Gate

所有新的 GRPO 数据集迭代都统一采用两段式 smoke：

- 第一段：前 `50` 个 metric step 的 early gate
- 第二段：同一条 run 继续到 `170 step` 的 mid gate，用于覆盖 `v7/v8` 历史崩坏区间

early gate 固定检查：

- `first50_avg_frac_reward_zero_std <= 0.40`
- `first50_median_reward_std >= 0.20`
- `max_consecutive_full_zero_std_steps <= 3`

mid gate 固定检查：

- `first170_avg_frac_reward_zero_std <= 0.40`
- `first170_median_reward_std >= 0.15`
- `last50_avg_frac_reward_zero_std <= 0.35`
- `last50_median_reward_std >= 0.15`
- `121_170_avg_frac_reward_zero_std <= 0.35`
- `121_170_median_reward_std >= 0.15`
- `max_consecutive_full_zero_std_steps <= 3`

只有同时通过 early gate 和 mid gate 的数据集，才允许继续进入 `300-step` 训练与评估。

## 版本与文件系统路径映射

**注意**：部分版本在文档中使用新的版本号（v13、v14），但文件系统中的目录名保持不变。

| 版本 | 数据集路径 | 模型训练路径 |
|------|-----------|-------------|
| v13 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k/` | `models/grpo_vlm_sft44_geometry100k_v10_stagebalanced_s1_4gpu_tuned/` |
| v14 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/` | `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/` |
| v15 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/` | `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_lr5e6/` |
| v16 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/` | `models/grpo_vlm_sft44_geometry100k_maxaux8_v16_s1_4gpu_lr5e6/` |
| v17 | `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_5k_v17/` | `models/grpo_vlm_sft44_geometry100k_v17_s1_4gpu_lr5e6/` |

**版本说明**：
- **v13**：原称"v10 复跑"，使用 v10_auxfix_stage_balanced selector 在 geometry100k maxaux5 数据源上的实验，50-step smoke 边缘失败（avg_zero_std = 0.4364）
- **v14**：原称"maxaux8"，使用 bucket_unified selector 在 geometry100k maxaux8 数据源上的实验，首次通过 50-step smoke gate（avg_zero_std = 0.2659），但 500-step 后期退化，dev_imo 回退至 12/16
- **v15**：与 v14 相同数据集，将学习率从 1e-4 降至 5e-6 并添加 warmup，50-step smoke gate 大幅改善（avg_zero_std = 0.0682），仅跑 50 步作为调参验证
- **v16**：与 v15 相同配置，切换为 4 卡 DDP，500-step 全程稳定，dev_imo 14/16，imo_95 55/95
- **v17**：与 v16 相同配置，训练集从 2k 扩大到 5k（约 3.2 epoch），前 50 步 avg_zero_std = 0.0778（优于 v16），**当前主线**
