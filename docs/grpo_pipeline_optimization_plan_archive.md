# GRPO 历史归档文档

最后更新：2026-04-29

> **文档说明**：本文档归档 GRPO 数据集/训练迭代的完整历史（v3-v13）与关键基础设施变更。主线文档 `grpo_pipeline_optimization_plan.md` 聚焦 v14+（含当前最优 v17/v18）。两份文档合起来覆盖所有版本的完整信息。

---

## 目录

1. [背景与基础设施](#背景与基础设施)
2. [关键诊断与修复](#关键诊断与修复)
3. [版本演进详解](#版本演进详解)
4. [版本演进摘要](#版本演进摘要)

---

## 背景与基础设施

### 项目基础信息

- 基础模型：`vlm_sft44`，路径为 `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- 原始数据源（版本相关）：
  - v12 及以前：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
  - v13：`/C20545/home/wangzi/GenesisGeo/datasets/20260421_maxaux5/geometry_clauses10_samples100k.jsonl`
  - v14 及以后：`/C20545/home/wangzi/GenesisGeo/datasets/20260421_maxaux8/20260421/geometry_clauses10_samples100k.jsonl`
- 当前训练入口：`scripts/grpo/train_grpo.sh`
- 当前 selector 入口：`scripts/grpo/select_debug_set.py`
- 核心判断：主要瓶颈仍然是数据分布，而不是 GRPO 训练超参数

---

## 关键诊断与修复

### 2026-04-20 Bug Audit（影响 GRPO 语义的关键排查）

#### 问题描述

- **Commit `48d9ea5`**（Fix aux DSL processing bugs affecting GRPO training）修的是两个直接影响 GRPO 语义的 bug：
  - `extract_aux_body()` 不应删除首个 `x00`，否则训练 target 会和模型的 `response_prefix="<aux> x00"` 不一致。
  - `AuxRewardEvaluator._evaluate_uncached()` 之前只正确处理第一个辅助点，多辅助点样本会被截断评估。
- 后续 **Commit `2972827`**（Fix CI dependency and GRPO test regressions）为了修 CI / test regression，把 `extract_aux_body()` 又改回了旧行为，但保留了多辅助点评估逻辑，形成了"reward 侧半修复、dataset target 侧未修复"的不一致状态。

#### 排查结果

- 旧版 `v8/v9` selected dataset 的 `response` 均为错误格式
- `2000 / 2000` 行都缺失了首个 `x00`，同时后续辅助点前仍残留 `x00`
- `models/grpo_vlm_sft44_v8_tuned_300step_bugfix/v1-20260420-171548` 应视为"reward-side bugfix rerun"，不是 full aux-format fix rerun

#### 执行的修复

- **Commit `1789955`**（Restore aux DSL x00 format and add v9 auxfix dataset）：恢复 `src/newclid/training/aux_dsl.py` 的完整前缀语义
- **Commit `cb2fd93`**（Harden auxfix relabel against parse crashes）：补充 `tests/test_grpo_rewards.py` 回归测试，覆盖多辅助点 reward 与 dataset 导出；同时在 `src/newclid/training/grpo_rewards.py` 中将单样本解析异常降级为 `format_invalid`
- **Commit `1789955`**：新增 `scripts/grpo/rewrite_selected_aux_responses.py`，从原始 1M 数据按 `(query, fl_problem)` 回填原始 `<aux> ... </aux>`
- 保留 aux-fix 版数据集：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v9_stagebalanced_2k_auxfix`

#### 诊断结论

- full aux-format fix 已在 `v8` / `v9` 两条 selector 上完成 smoke 诊断
- 问题不是"只要修好 aux DSL 就会自然改善"，而是旧 selector 在 aux-fix 语义下需要重新适配

---

### 2026-04-20 Relabel Infrastructure（aux-fix 语义下的重标基础设施）

#### 新增/完善脚本

- **Commit `bc534f6`**（Add resumable GRPO relabel tooling and auxfix caps）：
  - `scripts/grpo/label_difficulty_vlm.py`
    - 支持 `--resume`
    - 支持 `--work-dir`
    - 支持 worker 级 `progress.json` 与 `worker.log`
    - 支持按 `flush-every-batches` 周期性落盘 shard 输出
  - `scripts/grpo/select_debug_set.py`
    - 新增 `v10_auxfix_stage_balanced`
    - 新增 easy-tail cap：`greedy_success_max_fraction`、`pass_one_max_fraction`、`high_pass_max_fraction`
- **Commit `e15b0d6`**（Add GRPO difficulty label reconciliation helpers）：
  - `scripts/grpo/report_difficulty_drift.py`
    - 用于对齐旧标签与新标签的 `pass@k / greedy_success / all_invalid` 漂移

#### 测试

```bash
pytest -q tests/test_grpo_rewards.py tests/test_grpo_data_selection.py
```

#### 20k 校准重标集（aux-fix）

**目录**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v10_auxfix_relabel20k_calib`

**产物**：
- `difficulty_labels_auxfix_20k.jsonl`
- `difficulty_labels_auxfix_20k_summary.json`
- `difficulty_drift_old_vs_auxfix_20k.json`

**旧 vs 新（matched drift）核心结论**：
- `avg pass@16: 0.6057 -> 0.8319`
- `zero_ratio: 0.3324 -> 0.1288`
- `one_ratio: 0.5515 -> 0.7774`
- `greedy_success_rate: 0.6050 -> 0.8370`

**结论**：旧语义下的难度标签明显失真，full aux-fix 语义下大量样本被重新判成易题。

#### remaining130k 扩展重标与 150k 合并池

**扩展重标目录**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v10_auxfix_relabel150k_full_remaining130k`

**合并产物**：
- `difficulty_labels_auxfix_merged_150k.jsonl`
- `difficulty_labels_auxfix_merged_150k_summary.json`

**合并后统计（150k）**：
- `total_rows = 150000`
- `avg pass@16 = 0.8642`
- `zero_ratio = 0.1238`
- `one_ratio = 0.8446`
- `all_invalid_ratio = 0.0868`
- `greedy_success_ratio = 0.8667`

---

## 版本演进详解

### v3_tiered

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v3`

**Selector 策略**：`v3_tiered`

**静态结果**：
- `selected_rows = 2000`
- `selected_zero_pass_ratio = 0.6785`
- `selected_nonzero_pass_ratio = 0.3215`
- `selected_avg_unique_aux_count = 1.873`

**主要问题**：
- 选出的样本池被 `pass@16 = 0` 的样本主导（`1357 / 2000`）
- reward 多样性很差

**Smoke 结果**：
- run：`models/grpo_vlm_sft44_v3_smoke_s1_single/v1-20260419-112703`
- `first50_avg_frac_reward_zero_std = 0.6136`
- `first50_median_reward_std = 0.0`
- `max_consecutive_full_zero_std_steps = 7`

**结论**：`v3` 明确失败；旧 hard-valid fallback 放进过多 pass-zero 样本，导致 reward variance 崩塌。

---

### v4_reward_mixed

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v4_rewardmix_800`

**Selector 策略**：`v4_reward_mixed`

**静态结果**：
- `selected_rows = 800`
- `selected_zero_pass_ratio = 0.20375`
- `selected_reward_mixed_zero_ratio = 0.20375`
- `selected_avg_proxy_reward_std = 0.3512`
- `selected_median_proxy_reward_std = 0.3248`

**主要改进**：用 `reward_mixed_zero` 替代通用 pass-zero fallback；zero-pass 占比 `67.85% -> 20.38%`。

**主要限制**：规模仅 `800`，更像 selector 概念验证。

**结论**：reward-mixed 过滤必要，但 v4 不能回答 2k 规模可否维持 reward variance。

---

### v5_rewardmix_2k

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v5_rewardmix_2k`

**标注来源**：
- 复用与 `v2_relaxed` 重叠的标签
- 对剩余 delta 重标并合并到 `100k` 行

**Selector**：`v4_reward_mixed`

**静态结果**：
- `selected_rows = 2000`
- `selected_zero_pass_ratio = 0.1685`
- `selected_reward_mixed_zero_ratio = 0.1685`
- `selected_nonzero_pass_ratio = 0.8315`
- `selected_avg_proxy_reward_std = 0.3595`
- `selected_median_proxy_reward_std = 0.3476`

**Smoke**：
- run：`models/grpo_vlm_sft44_v5_rewardmix_s1_4gpu_256/v1-20260419-195804`
- `first50_avg_frac_reward_zero_std = 0.4375`
- `first50_median_reward_std = 0.1833`
- `max_consecutive_full_zero_std_steps = 1`

**结论**：仅扩大规模仍不足，瓶颈不是 `num_generations` 或 `max_completion_length`，而是一阶数据组成问题。

---

### v6_mid_strict_zero

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v6_midpass_2k`

**Selector**：`v6_mid_strict_zero`

**设计目标**：
- 更严格的 `reward_mixed_zero` 过滤
- core window 收窄到中间 pass band
- 高 pass 但非 mastered 独立成限额 tier

**静态结果**：
- `selected_rows = 2000`
- `selected_zero_pass_ratio = 0.10`
- `selected_reward_mixed_zero_ratio = 0.10`
- `selected_nonzero_pass_ratio = 0.90`
- `selected_avg_proxy_reward_std = 0.3663`
- `selected_median_proxy_reward_std = 0.3476`
- `selected_avg_valid_ratio = 0.8333`
- `multi_point_shortage = 137`
- high-pass 尾部仍偏重：`0.8125 = 153`、`0.8750 = 118`（合计 271）

**Smoke**：
- run：`models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740`
- `first50_avg_frac_reward_zero_std = 0.4125`
- `first50_median_reward_std = 0.2054`
- `max_consecutive_full_zero_std_steps = 0`

**与 v5 对比**：
- `avg_frac_reward_zero_std: 0.4375 -> 0.4125`
- `median_reward_std: 0.1833 -> 0.2054`

**结论**：更好但仍未过 gate（`0.4125 > 0.40`）。

---

### v7_structure_strict_zero

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k`

**Prefilter 改动**：
- candidate pool 目标扩大到 `150k`
- 顶层结构预算从 `multi_aux/single_aux` 改为 `multi_point/single_point`
- 目标 `multi_point = 70%`，实际仅 `44.35%`（供给限制）

**标注来源**：fast-path 合并：
- `v5_merged_100k = 100000`
- `v2_relaxed_extra = 13350`
- 合并标签池 `113350`

**Selector**：`v7_structure_strict_zero`

**静态结果**：
- `selected_rows = 2000`
- `selected_zero_pass_ratio = 0.10`
- `selected_reward_mixed_zero_ratio = 0.10`
- `selected_nonzero_pass_ratio = 0.90`
- `selected_avg_proxy_reward_std = 0.3711`
- `selected_median_proxy_reward_std = 0.3476`
- `selected_avg_valid_ratio = 0.8267`
- `selected_avg_unique_aux_count = 2.1115`
- `multi_point_shortage = 61`
- high-pass 尾部改善：`0.8125 + 0.8750 = 200`

**Smoke**：
- run：`models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401`
- `first50_avg_frac_reward_zero_std = 0.2900`
- `first50_median_reward_std = 0.2562`
- `max_consecutive_full_zero_std_steps = 0`

**结论**：首个通过统一 50-step smoke gate 的版本；收益来自 reward-variance 稳定性。

---

### v8_structure_full150k_strict_zero（旧语义）

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v8_structure_full150k_2k`

**标注来源**：
- 复用 union labels 覆盖 `71974`
- 对剩余 `78026` 重新标注
- 合并后标签池 `150000`

**Selector**：`v7_structure_strict_zero`

**静态结果**：
- `selected_rows = 2000`
- `selected_zero_pass_ratio = 0.061`
- `selected_reward_mixed_zero_ratio = 0.061`
- `selected_nonzero_pass_ratio = 0.939`
- `selected_avg_proxy_reward_std = 0.3811`
- `selected_median_proxy_reward_std = 0.3631`
- `selected_avg_valid_ratio = 0.8429`
- `selected_avg_unique_aux_count = 2.138`

**Smoke**：
- run：`models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140`
- `first50_avg_frac_reward_zero_std = 0.2300`
- `first50_median_reward_std = 0.3472`
- `max_consecutive_full_zero_std_steps = 1`

**结论**：早期 smoke 明显优于 v7，但中段训练仍会塌缩。

---

### v9_stage_balanced（旧语义）

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v9_stagebalanced_2k`

**Selector**：`v9_stage_balanced`

**设计目标**：
- 修复 v8 的 `near_low / near_high_mid` 空桶
- 不重做 150k 标注的前提下保留边界桶
- smoke 从"只看 50 step"升级为"50 + 170"两段式

**静态结果**：
- `selected_rows = 2000`
- `selected_zero_pass_ratio = 0.15`
- `selected_nonzero_pass_ratio = 0.85`
- `selected_median_proxy_reward_std = 0.3631`
- `selected_avg_unique_aux_count = 2.1325`
- `tier_selected_rows = {core: 1322, near_low: 138, reward_mixed_zero: 300, near_high_mid: 160, near_high_high: 80}`

**tuned smoke（170-step 预期，但实际因 early rule 停止）**：
- run：`models/grpo_vlm_sft44_v9_stagebalanced_s1_4gpu_tuned/v0-20260420-154747`
- `first50_avg_frac_reward_zero_std = 0.22`
- `first50_median_reward_std = 0.3267`
- `first50_max_consecutive_full_zero_std_steps = 4`
- 因连续 full-zero 超上限，按规则停止，不进入 `170-step` gate

---

### v8/v9_auxfix_rerun（aux-format 修复后的旧 selector 复跑 - 关键诊断）

**数据集**：
- `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v8_structure_full150k_2k_auxfix`
- `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v9_stagebalanced_2k_auxfix`

**数据来源**：`scripts/grpo/rewrite_selected_aux_responses.py` 从原始 1M 数据按 `(query, fl_problem)` 回填 `<aux> ... </aux>`，恢复首个 `x00`。

**tuned smoke 配置**：`temperature=1.1, top_p=0.95, top_k=0, beta=0.02, num_generations=8, max_completion_length=256`

**结果**：

| 版本 | avg_zero_std | median_reward_std | max_consecutive_zero | 状态 |
|------|--------------|-------------------|----------------------|------|
| v9 auxfix | 0.53 | 0.0970 | 5 | 约 step 125/170 停止 |
| v8 auxfix | 0.56 | 0.0 | 6 | 完整 50 step |

**对比结论**：
- `v8` 本来就差（旧语义下 `avg_zero_std = 0.63, median_reward_std = 0.0`），auxfix 后失败不意外
- `v9` 在旧语义最好、auxfix 后明显变坏：说明旧 selector/旧 labels 不适配 full aux-fix 语义
- 抽样 512 条 fixed-relabelling 进一步确认必须重标：
  - 旧标签：`avg_pass_at_16 = 0.3370`, `median = 0.3125`, `zero_ratio = 0.1367`, `one_ratio = 0.0`
  - 重标后：`avg_pass_at_16 = 0.6969`, `median = 0.7500`, `zero_ratio = 0.0195`, `one_ratio = 0.3809`
  - `pass_up = 382 / 512`
  - 结论：旧标签显著低估 full aux-fix 语义下可解率；必须先重标

---

### v10（显式 stage-balanced selector 复跑；后来在主线被命名为 v13）

**背景**：`select_debug_set.py` 的默认窗口与文档口径不一致，因此复现 v10/v11 stage-balanced 必须显式传参。

**数据源**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux5/difficulty_labels.jsonl`

**静态结果（2k）**：
- `selected_zero_pass_ratio = 0.05`
- `selected_avg_proxy_reward_std = 0.4336`
- `selected_median_proxy_reward_std = 0.4050`
- 分桶：core=1740, near_low=100, reward_mixed_zero=100, near_high_mid=60

**50-step tuned smoke**：
- run：`models/grpo_vlm_sft44_geometry100k_v10_stagebalanced_s1_4gpu_tuned/v0-20260421-235544`
- `first50_avg_frac_reward_zero_std = 0.4364`（FAIL）
- `first50_median_reward_std = 0.2005`（PASS）
- `max_consecutive_full_zero_std_steps = 1`（PASS）

**结论**：边缘但未通过 early smoke；当时按规则不进入 170-step。

---

### v11（aux-fix 语义下的 stage-balanced 复跑）

**背景**：基于 full aux-fix 150k 重标池，继续沿用 stage-balanced selector 思路。

**数据集**：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v11_auxfix_full150k_stagebalanced_2k`

**标签池**：full aux-fix `150k` merged pool

**Selector**：`v10_auxfix_stage_balanced`（采用当前最新版配额）

**静态结果**：
- `selected_rows = 2000`
- `mastered_fallback_triggered = false`
- `selected_zero_pass_ratio = 0.005`
- `selected_nonzero_pass_ratio = 0.995`
- `selected_avg_proxy_reward_std = 0.4979`
- `selected_median_proxy_reward_std = 0.4961`
- `tier_selected_rows = {core: 1830, near_low: 100, reward_mixed_zero: 10, near_high_mid: 60}`
- 完整 `150k` 分桶：
  - `core = 2094`
  - `near_low = 141`
  - `reward_mixed_zero = 10`
  - `near_high_mid = 897`
  - `mastered = 127227`
  - `all_invalid = 13014`
  - `discarded_non_dead = 6617`

**tuned 300-step run**：
- run：`models/grpo_vlm_sft44_v11_full150k_tuned_300step/v0-20260421-125128`
- 配置：`num_generations=8, temperature=1.1, top_p=0.95, top_k=0, beta=0.02, max_completion_length=256`
- 到 `170 step` 的关键指标：
  - `first170_avg_frac_reward_zero_std = 0.5735`
  - `first170_median_reward_std = 0.0`
  - `last20_avg_frac_reward_zero_std = 0.9`
  - `last20_median_reward_std = 0.0`
  - `max_consecutive_full_zero_std_steps = 23`

**结论**：
- full `150k` 池已足够支持"不依赖 mastered 回填"地选满 `2k`
- 但 `reward_mixed_zero` 仍然极缺，`100` 的 floor 实际只能拿到 `10`
- 中段明显进入 collapse 轨迹，表现比历史 `v7` 的中段崩坏还更糟
- 说明问题仍然是一阶数据分布问题，而不是单纯训练超参问题

---

### v12（结构特征筛选实验）

**背景**：VLM 标注慢，尝试用结构特征快速筛训练集。

**数据源**：`grpo_geometry100k_vlm_label_20260421_maxaux5`

**筛选策略**：
- `aux_points_total` 分层采样（30%/40%/30%）
- 限制 easy tail（排除 aux_points=1 且 n_premises<5）
- 要求 aux_segment_count≥1
- 谓词族平衡（每个 goal_predicate ≤18%）
- 前提数覆盖（n_premises 2-25）

**数据集**：`datasets/grpo_pipeline_vlm_sft44_geometry100k_structure_v12_2k`（脚本：`scripts/grpo/quick_sample_by_structure.py`）

**50-step smoke 结果（对比 v11）**：

| 指标 | 阈值 | v11 | v12 | 结果 |
|------|------|-----|-----|------|
| avg_frac_reward_zero_std | ≤0.40 | 0.29 | 0.54 | ✗ FAIL |
| median_reward_std | ≥0.15 | 0.3574 | 0.0884 | ✗ FAIL |
| 零方差步数占比 | - | - | 46% | - |

**核心问题**：
- 46% 的步数出现零方差（23/50 步）
- reward_std 中位数仅 0.0884，不到 v11 的 1/4
- 信号质量显著下降

**失败原因分析**：
1. **结构特征筛选过于粗糙**
   - 仅基于 aux_points、n_premises、goal_predicate 平衡
   - 缺少对候选池质量的直接评估（Pass@16 分布）
   - 无法识别 reward_mixed_zero 类型样本（部分 aux 可解、部分不可解）
2. **新 100k 候选池特性**
   - 平均 Pass@16 从 79.5%（v10 auxfix）降至 57.3%
   - 候选池更难，但不代表训练分布更好
   - 需要更精细的难度分层采样
3. **结构特征解释力有限**
   - 基于 v10 auxfix 20k 的分析：pseudo R² 只有 0.015
   - 说明 98.5% 的方差无法用结构特征解释
   - 结构特征不能直接预测 proxy_reward_std

**结论**：结构特征筛选**不能替代** VLM 标注；增加数据量或 batch size 不会解决根本问题（问题在于数据分布质量，不是数量）。

#### v12 Large Batch（2026-04-21）

**动机**：验证增加 batch size 是否能改善 reward_std 分布，减少零方差步数。

**配置变更**：
- per_device_train_batch_size: 1 → 2
- gradient_accumulation_steps: 8 → 16
- 每 step 看到的 problems: 8 → 32（**4倍增加**）
- 其他参数与 v12 原始配置完全一致

**50-step 对比**：

| 指标 | 阈值 | v12 原始 (1×8) | v12 Large (2×16) | 改善 |
|------|------|----------------|------------------|------|
| avg_frac_reward_zero_std | ≤0.40 | 0.54 (✗) | 0.55 (✗) | +0.01 |
| median_reward_std | ≥0.15 | 0.0884 (✗) | **0.1581 (✓)** | +0.0697 |
| max_consecutive_zero_std | ≤3 | 3 (✓) | 1 (✓) | -2 |
| 零方差步数占比 | - | 46.0% | **6.0%** | **-40.0%** |

**关键改善**：
1. **零方差步数大幅减少**：从 23/50 步（46%）降至 3/50 步（6%）
2. **median_reward_std 通过阈值**：从 0.0884 提升至 0.1581（+79%）
3. **连续零方差步数减少**：从最多 3 步降至 1 步
4. **整个 step 坍塌问题基本解决**：94% 的 steps 有非零方差

**仍存在的问题**：
- `avg_frac_reward_zero_std` 仍未通过（0.55 > 0.40）
- 虽然很少有整个 step 完全零方差，但每个 step 内仍有 30-60% 的 samples 是零方差
- 说明增加 batch size 改善了"整个 step 坍塌"，但没有解决"数据分布质量不好"的根本问题

**结论**：
- Large batch 配置（2×16）显著优于原始配置（1×8）
- 但仍未完全通过 smoke gate（1/3 指标失败）
- 核心问题仍然是数据分布质量，不是 batch size
- 建议：等待 VLM 标注完成，用 pass@16 精确筛选数据

---

### v13（2026-04-21）：命名映射与结论

主线文档将上述"geometry100k 显式 v10 stage-balanced 复跑"统一命名为 **v13**。

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k/`

**结论**：50-step smoke 边缘失败（`avg_zero_std = 0.4364`），因此后续主线转向 `maxaux8 bucket_unified`（v14）。

---

## 版本演进摘要

### v3 → v4：引入 reward_mixed_zero 过滤

- 将通用 zero-pass fallback 改成更严格的 `reward_mixed_zero`
- `selected_zero_pass_ratio: 0.6785 -> 0.20375`
- v4 规模仅 800，属于概念验证

### v4 → v5：扩大规模到 2k

- reward-mixed 扩到 2k，标注池扩到 100k
- smoke 仍未通过：仅扩大规模不够

### v5 → v6：收窄 core 并限制高 pass 样本

- 收窄 core、限制高 pass easy 样本，继续压 zero-pass
- smoke 指标继续改善但仍未过 gate

### v6 → v7：扩大 prefilter pool 并偏向 multi_point

- prefilter pool 扩到 150k，并显式偏向 multi_point
- v7 成为首个通过统一 50-step smoke gate 的版本
- **关键发现**：池子结构和 selector 同等重要

### v7 → v8：补齐 150k 标注池

- 补齐 150k 标注池，早期稳定性优于 v7
- 但中段训练仍会塌缩

### v8 → v9：引入 stage-balanced 思路

- stage-balanced 思路引入边界桶并升级 smoke 规则
- 旧语义下 early 指标优秀，但 full aux-fix 语义下无法直接继承（需要重标）

### v9 → v10：显式 stage-balanced selector 复跑

- 在 geometry100k 新标签池上复现 v10 stage-balanced selector
- 50-step smoke 边缘失败（avg_zero_std = 0.4364）
- 按规则不进入 170-step

### v10 → v11：aux-fix 语义下的 stage-balanced 复跑

- 基于 full aux-fix 150k 重标池，继续沿用 stage-balanced selector
- 中段明显进入 collapse 轨迹，表现比历史 v7 还更糟
- 说明问题仍然是一阶数据分布问题

### v11 → v12：结构特征筛选实验

- 尝试用结构特征快速筛训练集，无需 VLM 标注
- 50-step smoke 明显失败（avg_zero_std = 0.54, median_reward_std = 0.0884）
- 结论：结构特征筛选不能替代 VLM 标注

### v12 → v13：后续主线转向

- v12 large batch 实验：改善"整步坍塌"但无法解决根因
- v13（即 v10 的命名）：50-step smoke 边缘失败
- 后续主线转向 maxaux8 bucket_unified（v14）

---

## 关键结论

1. **必须减少 pass-zero 污染**：v3 失败的直接原因就是放进了太多 `pass@16 = 0` 样本。

2. **仅仅减少 pass-zero 污染还不够**：v6 已经把 zero-pass 占比降到 10%，但仍然没通过 smoke gate。

3. **Candidate pool 的结构和 selector 策略同等重要**：v7 之所以能过，是因为扩大了 prefilter pool，并显式偏向 `multi_point` 结构。

4. **aux-fix 语义下需要重新适配**：旧 selector 在 full aux-format 修复后需要重标和重新校准，不能直接继承。

5. **数据分布质量是一阶问题**：结构特征筛选、增加 batch size 等都无法替代高质量的数据分布。
