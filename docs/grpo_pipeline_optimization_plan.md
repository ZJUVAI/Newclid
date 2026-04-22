# GRPO 迭代状态与后续计划

最后更新：2026-04-22

## 背景

- 基础模型：`vlm_sft44`，路径为 `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- 原始数据源：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
- 当前训练入口：`scripts/grpo/train_grpo.sh`
- 当前 selector 入口：`scripts/grpo/select_debug_set.py`
- 核心判断：主要瓶颈仍然是数据分布，而不是 GRPO 训练超参数

---

## 当前主线状态

### v14 (2026-04-22) - 当前主线

**数据集**：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`

**模型训练目录**：`models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned`

**训练进度**：
- ✅ 50-step smoke gate：**通过** (`avg_zero_std = 0.2659`)
- ⚠️ 170-step mid gate：**部分通过** (`last50_avg_zero_std = 0.36`，略超阈值 0.35)
- ✅ 300-step 训练：**已完成**
- ✅ 500-step 训练：**已完成**
- ⚠️ dev_imo 评估：**12/16**（低于 SFT 的 14/16 和历史 GRPO505 的 13/16）

**当前状态**：
- v14 是 geometry100k 上首个通过 50-step smoke gate 的版本
- 500-step 完整跑通，但后半程（301-500）零方差占比升至 0.57
- checkpoint-500 在 dev_imo 上出现回退，proposal 分布已偏移

**下一步**：
- 分析 checkpoint-300 的 dev_imo 表现，判断是否在 300-step 前性能更好
- 考虑调整数据策略或 selector，增加高质量 hard 样本供给

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

**版本说明**：
- **v13**：原称"v10 复跑"，使用 v10_auxfix_stage_balanced selector 在 geometry100k maxaux5 数据源上的实验，50-step smoke 边缘失败（avg_zero_std = 0.4364）
- **v14**：原称"maxaux8"，使用 bucket_unified selector 在 geometry100k maxaux8 数据源上的实验，**首次通过 50-step smoke gate**（avg_zero_std = 0.2659），当前主线

## 版本回顾

### `v3_tiered`

- 数据集：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v3`
- Selector 策略：`v3_tiered`
- 静态结果：
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.6785`
  - `selected_nonzero_pass_ratio = 0.3215`
  - `selected_avg_unique_aux_count = 1.873`
- 主要问题：
  - 选出的样本池被 `pass@16 = 0` 的样本主导（`1357 / 2000`）
  - 这使得数据集虽然在规模上够大，但 reward 多样性很差
- Smoke 结果：
  - run：`models/grpo_vlm_sft44_v3_smoke_s1_single/v1-20260419-112703`
  - `first50_avg_frac_reward_zero_std = 0.6136`
  - `first50_median_reward_std = 0.0`
  - `max_consecutive_full_zero_std_steps = 7`
- 结论：
  - `v3` 明确失败
  - 旧的 hard-valid fallback 放进了过多 pass-zero 样本，直接导致 GRPO reward variance 崩塌

### `v4_reward_mixed`

- 数据集：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v4_rewardmix_800`
- Selector 策略：`v4_reward_mixed`
- 静态结果：
  - `selected_rows = 800`
  - `selected_zero_pass_ratio = 0.20375`
  - `selected_reward_mixed_zero_ratio = 0.20375`
  - `selected_avg_proxy_reward_std = 0.3512`
  - `selected_median_proxy_reward_std = 0.3248`
- 主要改进：
  - 用 `reward_mixed_zero` 替代通用的 pass-zero fallback 是正确方向
  - zero-pass 占比从 `67.85%` 降到了 `20.38%`
- 主要限制：
  - 数据集规模只有 `800` 条，仍然太小
  - 这个版本更像是 selector 的概念验证，而不是最终的 2k 训练集
- 结论：
  - reward-mixed 过滤是必要的
  - 但 `v4` 还不能回答“在 2k 规模下是否还能维持足够好的 reward variance”

### `v5_rewardmix_2k`

- 数据集：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v5_rewardmix_2k`
- 标注来源：
  - 复用了与 `v2_relaxed` 重叠的标签
  - 对剩余 delta 重新标注，并合并到 `100k` 行
- Selector 策略：`v4_reward_mixed`
- 静态结果：
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.1685`
  - `selected_reward_mixed_zero_ratio = 0.1685`
  - `selected_nonzero_pass_ratio = 0.8315`
  - `selected_avg_proxy_reward_std = 0.3595`
  - `selected_median_proxy_reward_std = 0.3476`
  - selector report 中不再有结构性 shortage
- Smoke 结果：
  - 主 run：`models/grpo_vlm_sft44_v5_rewardmix_s1_4gpu_256/v1-20260419-195804`
  - `first50_avg_frac_reward_zero_std = 0.4375`
  - `first50_median_reward_std = 0.1833`
  - `max_consecutive_full_zero_std_steps = 1`
- Fallback 检查：
  - `ng4` run 比主 smoke 更差
  - `max_len=192` 也没能把 gate 拉回来
- 结论：
  - 从 `v4` 到 `v5` 证明了“仅仅扩大规模”是不够的
  - 失败模式说明瓶颈并不主要在 `num_generations` 或 `max_completion_length`
  - 数据组成仍然是一阶问题

### `v6_mid_strict_zero`

- 数据集：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v6_midpass_2k`
- Selector 策略：`v6_mid_strict_zero`
- 设计目标：
  - 保留更严格的 `reward_mixed_zero` 过滤
  - 将 core window 收窄到中间 pass band
  - 将较高 pass、但尚未 mastered 的样本拆成独立限额 tier
- 静态结果：
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.10`
  - `selected_reward_mixed_zero_ratio = 0.10`
  - `selected_nonzero_pass_ratio = 0.90`
  - `selected_avg_proxy_reward_std = 0.3663`
  - `selected_median_proxy_reward_std = 0.3476`
  - `selected_avg_valid_ratio = 0.8333`
  - `multi_point_shortage = 137`
  - high-pass 尾部仍然偏重：
    - `0.8125 = 153`
    - `0.8750 = 118`
    - 合计 `0.8125 + 0.8750 = 271`
- Smoke 结果：
  - run：`models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740`
  - smoke gate 文件：`models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740/smoke_gate_first50.json`
  - `first50_avg_frac_reward_zero_std = 0.4125`
  - `first50_median_reward_std = 0.2054`
  - `max_consecutive_full_zero_std_steps = 0`
- 相比 `v5` 主 smoke：
  - `avg_frac_reward_zero_std`：`0.4375 -> 0.4125`
  - `median_reward_std`：`0.1833 -> 0.2054`
  - `avg_reward`：`0.6164 -> 0.6626`
  - `mean_length`：`50.88 -> 48.44`
- 结论：
  - `v6` 比 `v5` 更好
  - 但仍然没过 smoke gate，因为 `0.4125 > 0.40`
  - 单纯 selector 调整有帮助，但还不够

### `v7_structure_strict_zero`

- 数据集：`datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k`
- Prefilter 改动：
  - candidate pool 目标扩大到 `150k`
  - 顶层结构预算从 `multi_aux/single_aux` 改成 `multi_point/single_point`
  - 目标 `multi_point = 70%`，但实际 prefilter 结果受供给限制，只做到 `44.35%`
- 标注来源：
  - 通过 fast-path 合并已有标签：
    - `v5_merged_100k = 100000`
    - `v2_relaxed_extra = 13350`
  - 合并后的标签池规模为 `113350`
  - 标注模型仍为 `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- Selector 策略：`v7_structure_strict_zero`
- 静态结果：
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.10`
  - `selected_reward_mixed_zero_ratio = 0.10`
  - `selected_nonzero_pass_ratio = 0.90`
  - `selected_avg_proxy_reward_std = 0.3711`
  - `selected_median_proxy_reward_std = 0.3476`
  - `selected_avg_valid_ratio = 0.8267`
  - `selected_avg_unique_aux_count = 2.1115`
  - `multi_point_shortage = 61`
  - high-pass 尾部得到改善：
    - `0.8125 + 0.8750 = 200`
- Smoke 结果：
  - run：`models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401`
  - smoke gate 文件：`models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/smoke_gate_first50.json`
  - 对比文件：`models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/compare_vs_v6_v5_first50.json`
  - `first50_avg_frac_reward_zero_std = 0.2900`
  - `first50_median_reward_std = 0.2562`
  - `max_consecutive_full_zero_std_steps = 0`
- 相比 `v6` smoke：
  - `avg_frac_reward_zero_std`：`0.4125 -> 0.2900`
  - `median_reward_std`：`0.2054 -> 0.2562`
  - `avg_reward`：`0.6626 -> 0.6162`
  - `mean_length`：`48.44 -> 46.46`
- 结论：
  - `v7` 是第一个通过统一 50-step smoke gate 的数据集版本
  - 主要收益来自 reward-variance 稳定性，而不是更高的平均 reward
  - 下一阶段应在相同数据和超参数下推进到 `300-step`

## 当前诊断

`v3 -> v7` 的证据目前支持四个结论：

1. 必须减少 pass-zero 污染。  
   `v3` 失败的直接原因就是放进了太多 `pass@16 = 0` 样本。

2. 仅仅减少 pass-zero 污染还不够。  
   `v6` 已经把 zero-pass 占比降到 `10%`，但仍然没通过 smoke gate。

3. Candidate pool 的结构和 selector 策略同等重要。  
   `v7` 之所以能过，是因为扩大了 prefilter pool，并显式偏向 `multi_point` 结构。

4. 当前主问题已经从数据构建转移到了训练稳定性验证。  
   `v7` 已经通过了 50-step gate，接下来真正的问题是这个信号能不能撑到中段训练。

## 版本演进摘要

- `v3 -> v4`
  - 主要提升：将通用的 zero-pass fallback 改成更严格的 `reward_mixed_zero`
  - 直接效果：`selected_zero_pass_ratio` 从 `0.6785` 降到 `0.20375`
  - 局限：`v4` 只有 `800` 条，更像 selector 概念验证

- `v4 -> v5`
  - 主要提升：将 reward-mixed 方案扩到 `2k`，并把标注池扩到 `100k`
  - 直接效果：`selected_zero_pass_ratio` 进一步降到 `0.1685`，`selected_avg/median_proxy_reward_std` 上升
  - 局限：smoke 仍未通过，说明仅扩大规模不够

- `v5 -> v6`
  - 主要提升：selector 切换为 `v6_mid_strict_zero`，收紧 `core`，限制高 pass easy 样本，并继续压 zero-pass
  - 直接效果：`selected_zero_pass_ratio` 降到 `0.10`，smoke 指标继续改善
  - 局限：仍未过统一 gate，说明只改 selector 还不够

- `v6 -> v7`
  - 主要提升：candidate pool 结构升级到 `150k` prefilter，并显式偏向 `multi_point`
  - 直接效果：`selected_avg_unique_aux_count` 提升，high-pass 尾部减轻，`v7` 成为首个通过统一 50-step smoke gate 的版本
  - 结论：池子结构和 selector 同等重要

- `v7 -> v8`
  - 主要提升：在相同 `v7_structure_strict_zero` selector 下，把标注池补齐到完整 `150k`，新增补标 `78026` 条
  - 直接效果：`selected_zero_pass_ratio` 从 `0.10` 降到 `0.061`，`selected_avg_proxy_reward_std`、`selected_median_proxy_reward_std`、`selected_avg_valid_ratio` 继续提升，`50-step smoke` 明显优于 `v7`
  - 局限：主要改善的是早期稳定性，中段训练仍会塌缩

### `v8_structure_full150k_strict_zero`

- 数据集：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v8_structure_full150k_2k`
- 标注来源：
  - 复用已有 union labels 覆盖 `71974` 行
  - 对 full `150k` prefilter pool 中剩余 `78026` 行重新标注
  - 合并后标签池规模为 `150000`
  - 标注模型仍为 `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- Selector 策略：
  - `v7_structure_strict_zero`
- 静态结果：
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.061`
  - `selected_reward_mixed_zero_ratio = 0.061`
  - `selected_nonzero_pass_ratio = 0.939`
  - `selected_avg_proxy_reward_std = 0.3811`
  - `selected_median_proxy_reward_std = 0.3631`
  - `selected_avg_valid_ratio = 0.8429`
  - `selected_avg_unique_aux_count = 2.138`
  - 选出的 tier 主要集中在 `core`，只有少量 `reward_mixed_zero` 补位
- Smoke 结果：
  - run：`models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140`
  - smoke gate 文件：`models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140/smoke_gate_first50.json`
  - 对比文件：`models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140/compare_vs_v7_v6_v5_first50.json`
  - `first50_avg_frac_reward_zero_std = 0.2300`
  - `first50_median_reward_std = 0.3472`
  - `max_consecutive_full_zero_std_steps = 1`
- 相比 `v7` smoke：
  - `avg_frac_reward_zero_std`：`0.2900 -> 0.2300`
  - `median_reward_std`：`0.2562 -> 0.3472`
  - `avg_reward`：`0.6162 -> 0.6084`
  - `mean_length`：`46.46 -> 46.07`
- 结论：
  - `v8` 在统一 smoke gate 指标上优于 `v7`
  - 主要提升是更低的 zero-variance 污染，以及更高的 reward variance
  - `v8` 成为当前进入 `300-step` true resume 的主候选

### `v9_stage_balanced`

- 数据集：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v9_stagebalanced_2k`
- Selector 策略：
  - `v9_stage_balanced`
- 设计目标：
  - 修复 `v8` 中 `near_low` / `near_high_mid` 实际为空桶的问题
  - 在不重做 `150k` 标注的前提下，显式保留低通过率和高通过率边界桶
  - 将 smoke 从“只看前 50 step”升级为“50 + 170”两段式
- 静态结果：
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.15`
  - `selected_nonzero_pass_ratio = 0.85`
  - `selected_median_proxy_reward_std = 0.3631`
  - `selected_avg_unique_aux_count = 2.1325`
  - `tier_selected_rows = {core: 1322, near_low: 138, reward_mixed_zero: 300, near_high_mid: 160, near_high_high: 80}`
  - `grpo_train_report_2000_gate_check.json` 全部通过
- 当前状态：
  - 已完成 selector / report / dataset 产物
  - `170-step` tuned smoke run：`models/grpo_vlm_sft44_v9_stagebalanced_s1_4gpu_tuned/v0-20260420-154747`
  - early smoke 结果：
    - `first50_avg_frac_reward_zero_std = 0.22`
    - `first50_median_reward_std = 0.3267`
    - `first50_max_consecutive_full_zero_std_steps = 4`
  - 结论：
    - 两个均值类指标优于 gate
    - 但因连续 `full-zero` 步数超过上限，按规则停止，不进入 `170-step` gate
    - stop-summary：`models/grpo_vlm_sft44_v9_stagebalanced_s1_4gpu_tuned/v0-20260420-154747/smoke_stop_114_summary.json`

### `v8/v9_auxfix_rerun`

- 数据集：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v8_structure_full150k_2k_auxfix`
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v9_stagebalanced_2k_auxfix`
- 数据来源：
  - 使用 `scripts/grpo/rewrite_selected_aux_responses.py`
  - 依据 `(query, fl_problem)` 从原始 1M 数据
    `/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
    回填原始 `<aux> ... </aux>`，恢复首个 `x00`
- 训练配置：
  - 统一使用 tuned smoke 配置：`temperature=1.1, top_p=0.95, top_k=0, beta=0.02, num_generations=8, max_completion_length=256`
- 运行结果：
  - `v9 auxfix`：`models/grpo_vlm_sft44_v9_stagebalanced_s1_4gpu_tuned_auxfix/v0-20260420-184805`
    - `first50_avg_frac_reward_zero_std = 0.53`
    - `first50_median_reward_std = 0.0970`
    - `first50_max_consecutive_full_zero_std_steps = 5`
    - 在约 `step 125 / 170` 手动停止，因为后段持续出现 `reward_std = 0`
  - `v8 auxfix`：`models/grpo_vlm_sft44_v8_tuned_auxfix_smoke/v0-20260420-191921`
    - `first50_avg_frac_reward_zero_std = 0.56`
    - `first50_median_reward_std = 0.0`
    - `first50_max_consecutive_full_zero_std_steps = 6`
    - 完整跑到 `50 step`，不进入后续 promotion
- 对比结论：
  - `v8` 本来就差：
    - `v8_tuned_300step_bugfix/v1-20260420-171548` 的 `first50` 已经是
      `avg_zero_std = 0.63`, `median_reward_std = 0.0`
    - 因此 `v8 auxfix` 虽仍失败，但不是新的退化源头
  - `v9` 是关键异常：
    - 旧 `v9` 的 `first50` 是 `avg_zero_std = 0.22`, `median_reward_std = 0.3267`
    - `v9 auxfix` 变成 `0.53 / 0.0970`
    - 说明 `v9_stage_balanced` 的旧 selector 只适配了旧 reward / target 语义，不适配 full aux-fix 语义
  - 进一步的 fixed-relabelling 诊断已经确认必须重标：
    - 用 `scripts/grpo/label_difficulty_vlm.py` 对 `v9 auxfix` 当前 `2k` 选集随机抽样 `512` 条重新打标
    - 旧标签下这 `512` 条的统计为：
      - `avg_pass_at_16 = 0.3370`
      - `median_pass_at_16 = 0.3125`
      - `zero_ratio = 0.1367`
      - `greedy_success_rate = 0.2852`
      - `one_ratio = 0.0`
    - fixed evaluator 下重标后变为：
      - `avg_pass_at_16 = 0.6969`
      - `median_pass_at_16 = 0.7500`
      - `zero_ratio = 0.0195`
      - `greedy_success_rate = 0.6875`
      - `one_ratio = 0.3809`
    - 分布漂移量级：
      - `pass_up = 382 / 512`
      - `delta_avg = +0.3599`
      - `delta_median = +0.3125`
    - 结论：
      - 当前旧标签显著低估了这些样本在 full aux-fix 语义下的可解率
      - 只改 selector 配额不够，必须先重标
- 当前判断：
  - 下一步主线不再是继续放大 `v8` 或直接重跑 `v9`
  - 应该先基于 aux-fix 语义重标，再重做 `v9` 的 selector / bucket 配额 / gate

## 当前主线：`v9 auxfix` Selector 重做

### 为什么下一步不是继续 promotion

历史 `v1` GRPO run 说明，只看 `50-step` 不够：

- `first50_avg_frac_reward_zero_std = 0.29`
- `first50_median_reward_std = 0.3677`
- 但到 `150-170 step` 区间，同类 run 已经开始明显向 zero-variance 崩坏靠拢

截至 2026-04-20 晚上的 full aux-fix 诊断，原先这条 promotion 路径已经失效：

1. `v8` 在旧语义下的 smoke / promotion 结论只可作历史参考
2. `v8 auxfix` 与 `v9 auxfix` 都没有通过新的 early smoke 诊断
3. 尤其 `v9` 在旧语义下最好、在 aux-fix 语义下明显变坏，说明当前最需要修的是 selector，而不是继续延长训练
4. 因此当前不再推进 `checkpoint-300` / `checkpoint-500` / `dev_imo`
5. 下一步先产出适配 aux-fix 语义的新 selector 版本，再重新走 `50 + 170` 两段式 smoke

### `170-step mid smoke` 规则

在 mid smoke 阶段固定沿用 tuned smoke 成功时的设置：

- `CUDA_VISIBLE_DEVICES=0,1,2,3`
- `num_generations = 8`
- `temperature = 0.9`
- `top_k = 50`
- `beta = 0.04`
- `max_completion_length = 256`
- `reward_log_interval = 20`

使用 true checkpoint resume，而不是只恢复模型参数：

- 同一条 run 直接从 `step 1 -> 170`

决策规则：

- 如果 `170-step` 轨迹保持稳定，则进入 `300-step` promotion
- 如果 `170-step` 轨迹开始向历史 `v7/v8` 失败模式回归，则停止，回到数据迭代

### 旧 `v8` Promotion 状态

#### 原始配置 Promotion（已失败）

- Run：`models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140/v0-20260420-090218`
- 配置：`temperature=0.9, top_k=50, beta=0.04`
- 在 `step 147 / 300` 的中段状态：
  - `all_avg_frac_reward_zero_std = 0.6134`
  - `last20_avg_frac_reward_zero_std = 0.7750`
  - `max_consecutive_full_zero_std_steps = 5`
- 结论：中段塌缩，与 v7 类似

#### 调参配置 Smoke（已通过）

- Run：`models/grpo_vlm_sft44_v8_structure_full150k_s2_4gpu_tuned/v3-20260420-115549`
- 配置：`temperature=1.1, top_p=0.95, top_k=0, beta=0.02`
- 50-step smoke 结果：
  - `first50_avg_frac_reward_zero_std = 0.182`（gate ≤0.40 ✓，优于原始 0.23）
  - `first50_median_reward_std = 0.368`（gate ≥0.20 ✓）
  - `max_consecutive_full_zero_std_steps = 1`（gate ≤3 ✓）
- 改进：
  - 新增 plugin 状态分布监控（solved/unsolved/build_invalid/format_invalid + aux_unique_ratio）
  - 补充 TOP_P 参数支持
  - 提高探索强度（temperature 0.9→1.1，降低 KL 惩罚 beta 0.04→0.02）
- 结论：三项 gate 全过，准备进入 300-step promotion

### 历史 `v7` Promotion 结果

- Run：
  - `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401`
- 结果：
  - 在 `step 171 / 300` 提前停止
  - stop-summary 产物：
    - `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/promotion_stop_171_summary.json`
- 停止时关键指标：
  - `first171_avg_frac_reward_zero_std = 0.6272`
  - `first171_median_reward_std = 0.1089`
  - `last50_avg_frac_reward_zero_std = 0.8775`
  - `last50_median_reward_std = 0.0331`
  - `max_consecutive_full_zero_std_steps = 4`
- 与历史 `v1` 在相同前缀长度下对比：
  - `v7 first171 avg_zero = 0.6272`
  - `v1 first171 avg_zero = 0.5965`
  - `v7 last50 median_std = 0.0331`
  - `v1 last50 median_std = 0.0`
- 决策：
  - 将 `v7` 视为 smoke-pass 但 mid-training-fail 的数据集
  - 跳过这条分支上的 `checkpoint-300` eval、`checkpoint-500`、`dev_imo` 和 `imo_95`
  - 回到 full `150k` prefilter pool 的数据迭代

## 当前有效产物

- 主评估报告：
  - `docs/grpo_imo95_evaluation_report.md`
- `v5` 数据集报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v5_rewardmix_2k/grpo_train_report_2000.json`
- `v6` 数据集报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v6_midpass_2k/grpo_train_report_2000.json`
- `v7` prefilter 报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k/candidate_pool_prefilter_report_150k.json`
- `v7` merged-label 报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k/difficulty_labels_union_v2_v5_113k_report.json`
- `v7` 数据集报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k/grpo_train_report_2000.json`
- `v8` merged-label 报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v8_structure_full150k_2k/difficulty_labels_merged_150k_report.json`
- `v8` 数据集报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v8_structure_full150k_2k/grpo_train_report_2000.json`
- `v10` full aux-fix merged `150k`：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v10_auxfix_relabel150k_full_remaining130k/difficulty_labels_auxfix_merged_150k.jsonl`
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v10_auxfix_relabel150k_full_remaining130k/difficulty_labels_auxfix_merged_150k_summary.json`
- `v11` 数据集报告：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v11_auxfix_full150k_stagebalanced_2k/grpo_train_report_2000.json`
- `v11` 选集结构 summary：
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v11_auxfix_full150k_stagebalanced_2k/grpo_train_selected_2000_summary.json`
- `v11` tuned 300-step run：
  - `models/grpo_vlm_sft44_v11_full150k_tuned_300step/v0-20260421-125128`
- `v6` smoke gate：
  - `models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740/smoke_gate_first50.json`
- `v7` smoke gate：
  - `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/smoke_gate_first50.json`
- `v7` 对 `v6/v5` 的 smoke 对比：
  - `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/compare_vs_v6_v5_first50.json`
- `v8` smoke gate：
  - `models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140/smoke_gate_first50.json`
- `v8` 对 `v7/v6/v5` 的 smoke 对比：
  - `models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140/compare_vs_v7_v6_v5_first50.json`
- `v8` resumed promotion run：
  - `models/grpo_vlm_sft44_v8_structure_full150k_s1_4gpu_256/v9-20260420-083140/v0-20260420-090218`
- 历史长程 GRPO baseline：
  - `models/grpo_vlm_sft44_505_run1/v1-20260417-084328`

## 最近结论

- 历史上最好的旧语义 early smoke 仍然是 `v9_stage_balanced`：
  - `first50_avg_frac_reward_zero_std = 0.22`
  - `first50_median_reward_std = 0.3267`
- 但 full aux-fix 诊断表明，旧 selector 不能直接继承到新语义：
  - `v9 auxfix` 变成 `0.53 / 0.0970`
  - `v8 auxfix` 也仍然失败，`0.56 / 0.0`
- 因此当前的关键结论是：
  - `auxfix` 不是单独的充分改进
  - 旧 `v8/v9` selector 在 full aux-format 语义下都需要重新校准
  - 更准确地说，旧 `difficulty_labels` 本身已经过时，最值得保留的是 `v9` 的 stage-balanced 思路，而不是它当前的标签和精确配额
- `v11` 进一步说明：
  - 只靠 full `150k` relabel + 现有 stage-balanced selector，虽然已经能选满 `2k`
  - 但因为 `reward_mixed_zero` 和真正高信号 hard bucket 供给依旧过少，训练在 `170 step` 前后仍会坍塌
  - `selected_zero_pass_ratio = 0.005` 并不意味着训练更稳定；这里暴露出的核心问题是”零通过脏样本减少了，但高方差 hard 样本没有补上”
- 下一步应变为：
  - 继续拆解 `discarded_non_dead` 的组成，确认 `(0.75, 0.9)` easy tail 与 low-signal zero-pass 各占多少
  - 对 full `150k` 池做更强的 hard-signal 挖掘，而不是继续压缩 easy tail
  - 结合 `aux_points_total / aux_segment_count / n_premises` 重新设计 hard bucket 或新的 selector
  - 新 selector 仍先跑 `50-step` smoke，再决定是否进入 `170-step` / `300-step`
- 当前阶段的 Git 纪律：
  - 只跟踪 `docs/` 下这两个文档
  - 不要提交临时 benchmark resume 文件、monitor log 或一次性的 recovery helper

## 2026-04-21 V12 Structure-Based Selector 实验

**背景：** VLM 标注速度慢（100k 数据需要数小时），尝试基于结构特征（无需 VLM label）快速构建 GRPO 训练集。

**数据源：** 新的 100k geometry 候选池（`grpo_geometry100k_vlm_label_20260421_maxaux5`）

**筛选策略：**
- 基于 `aux_points_total` 分层采样（保守配置：30%/40%/30%）
- 限制 easy tail（排除 aux_points=1 且 n_premises<5）
- 要求 aux_segment_count≥1
- 谓词族平衡（每个 goal_predicate ≤18%）
- 前提数覆盖（n_premises 2-25）

**生成数据集：**
- 路径：`datasets/grpo_pipeline_vlm_sft44_geometry100k_structure_v12_2k`
- 规模：2,000 条
- 脚本：`scripts/grpo/quick_sample_by_structure.py`

**Smoke Test 结果（50 steps）：**

| 指标 | 阈值 | V11 | V12 | 结果 |
|------|------|-----|-----|------|
| avg_frac_reward_zero_std | ≤ 0.40 | 0.29 | **0.54** | ✗ FAIL (+0.25) |
| median_reward_std | ≥ 0.15 | 0.3574 | **0.0884** | ✗ FAIL (-0.27) |
| max_consecutive_zero_std | ≤ 3 | N/A | 3 | ✓ PASS |

**核心问题：**
- 46% 的步数出现零方差（23/50 步）
- reward_std 中位数仅 0.0884，不到 v11 的 1/4
- 信号质量显著下降

**失败原因分析：**
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

**结论：**
- 结构特征筛选**不能替代** VLM 标注
- 增加数据量或 batch size 不会解决根本问题（问题在于数据分布质量，不是数量）
- 建议等待 VLM 标注完成（当前 9.7%），用 pass@16 精确筛选

**训练配置：**
- 模型：`models/grpo_vlm_sft44_v12_structure_geometry100k_s1_4gpu_tuned/v0-20260421-162833`
- 参数：与 v11 一致（num_generations=8, temperature=1.1, beta=0.02）
- Batch size：per_device_train_batch_size=1, gradient_accumulation_steps=8（每 step 8 个 problems）
- 状态：未通过 50-step smoke gate，不进入后续训练

### V12 Large Batch 实验（2026-04-21）

**动机：** 验证增加 batch size 是否能改善 reward_std 分布，减少零方差步数。

**配置变更：**
- per_device_train_batch_size: 1 → 2
- gradient_accumulation_steps: 8 → 16
- 每 step 看到的 problems: 8 → 32（**4倍增加**）
- 其他参数与 v12 原始配置完全一致

**Smoke Test 结果对比（50 steps）：**

| 指标 | 阈值 | V12 原始 (1×8) | V12 Large (2×16) | 改善 |
|------|------|----------------|------------------|------|
| avg_frac_reward_zero_std | ≤ 0.40 | 0.54 (✗) | 0.55 (✗) | +0.01 |
| median_reward_std | ≥ 0.15 | 0.0884 (✗) | **0.1581 (✓)** | +0.0697 |
| max_consecutive_zero_std | ≤ 3 | 3 (✓) | 1 (✓) | -2 |
| 零方差步数占比 | - | 46.0% | **6.0%** | **-40.0%** |

**关键改善：**
1. **零方差步数大幅减少**：从 23/50 步（46%）降至 3/50 步（6%）
2. **median_reward_std 通过阈值**：从 0.0884 提升至 0.1581（+79%）
3. **连续零方差步数减少**：从最多 3 步降至 1 步
4. **整个 step 坍塌问题基本解决**：94% 的 steps 有非零方差

**仍存在的问题：**
- `avg_frac_reward_zero_std` 仍未通过（0.55 > 0.40）
- 虽然很少有整个 step 完全零方差，但每个 step 内仍有 30-60% 的 samples 是零方差
- 说明增加 batch size 改善了"整个 step 坍塌"，但没有解决"数据分布质量不好"的根本问题

**结论：**
- Large batch 配置（2×16）显著优于原始配置（1×8）
- 但仍未完全通过 smoke gate（1/3 指标失败）
- 核心问题仍然是数据分布质量，不是 batch size
- 建议：等待 VLM 标注完成，用 pass@16 精确筛选数据

**训练配置：**
- 模型：`models/grpo_vlm_sft44_v12_structure_geometry100k_s1_4gpu_tuned_largerbatch/v1-20260421-170742`
- 状态：部分通过 smoke gate（median_reward_std 通过），但 avg_frac_reward_zero_std 仍失败

## 2026-04-21 Geometry100k 显式 `v10` Selector 复跑

**背景：**

- 当前 `select_debug_set.py` 的函数 / CLI 默认值仍是旧窗口：
  - `core_pass_min = 0.0625`
  - `core_pass_max = 0.75`
  - `mastered_max_fraction = 0.05`
- 这与 `v10_auxfix_stage_balanced` 在文档里实际采用的主线口径不一致。
- 因此从这一轮开始，凡是复现 `v10` / `v11` stage-balanced selector，都**必须显式传参**，不能只写 `--selection-policy v10_auxfix_stage_balanced`。

**数据源：**

- `datasets/grpo_geometry100k_vlm_label_20260421_maxaux5/difficulty_labels.jsonl`

**固定命令：**

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux5/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k/grpo_train_selected_2000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k/grpo_train_report_2000.json \
  --selection-policy v10_auxfix_stage_balanced \
  --target-size 2000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --near-high-mid-max-pass 0.75 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --reward-mixed-zero-max-fraction 0.20 \
  --near-high-mid-min-fraction 0.03 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0
```

**为什么不能只写 policy：**

- 如果只传 `--selection-policy v10_auxfix_stage_balanced`，当前代码仍会落到旧默认窗口：
  - `stage_available_rows = {core: 26662, near_low: 0, reward_mixed_zero: 8373, near_high_mid: 0, mastered: 31569}`
  - `stage_selected_rows = {core: 1900, reward_mixed_zero: 100}`
- 显式传入 `core=[0.125, 0.625]` 和 `mastered_max_fraction=0.0` 后，才会恢复到当前主线想要的边界桶结构：
  - `stage_available_rows = {core: 17934, near_low: 5243, reward_mixed_zero: 8373, near_high_mid: 3485, mastered: 31569}`
  - `stage_selected_rows = {core: 1740, near_low: 100, reward_mixed_zero: 100, near_high_mid: 60}`

**静态结果：**

- 输出目录：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_v10_stagebalanced_2k`
- 选集报告：`grpo_train_report_2000.json`
- 结构 summary：`grpo_train_selected_2000_summary.json`
- 关键验收：
  - `selected_rows = 2000`
  - `mastered_fallback_triggered = false`
  - `tier_floor_shortages = {near_low: 0, reward_mixed_zero: 0, near_high_mid: 0}`
  - `selected_zero_pass_ratio = 0.05`
  - `selected_avg_proxy_reward_std = 0.4336`
  - `selected_median_proxy_reward_std = 0.4050`
- 最终分桶：
  - `core = 1740`
  - `near_low = 100`
  - `reward_mixed_zero = 100`
  - `near_high_mid = 60`
- 最终 `pass@16` 直方图：
  - `0.0000: 100`
  - `0.0625: 100`
  - `0.1250~0.6250: 1740`
  - `0.6875: 29`
  - `0.7500: 31`

**结构 summary：**

- `aux_points_total_distribution = {2: 1624, 3: 278, 4: 98}`
- `aux_segment_count_distribution = {2: 1624, 3: 278, 4: 98}`
- `goal_predicate` top buckets：
  - `eqangle = 360`
  - `eqratio = 360`
  - `cong = 222`
  - `simtrir = 196`
  - `simtri = 184`
  - `perp = 181`

**决策：**

- geometry100k 新标签池上的 `v10` 显式 selector 已通过静态验收。
- 下一步先用这版数据进入 `1x8 tuned` 的 `50-step early smoke`。
- 只有当 `v10` 未通过 `50-step` 或 `170-step` smoke 时，才切换到 `bucket_unified`。

### `v10` 50-step early smoke（2026-04-21 / 2026-04-22）

**训练配置：**

- 模型：`/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- 输出目录：`models/grpo_vlm_sft44_geometry100k_v10_stagebalanced_s1_4gpu_tuned/v0-20260421-235544`
- 参数：
  - `per_device_train_batch_size = 1`
  - `gradient_accumulation_steps = 8`
  - `num_generations = 8`
  - `temperature = 1.1`
  - `top_p = 0.95`
  - `top_k = 0`
  - `beta = 0.02`
  - `max_completion_length = 256`
  - `reward_log_interval = 20`

**结果：**

- 产物：
  - `logging.jsonl`
  - `checkpoint-50`
  - `smoke_gate_first50.json`
- gate summary：
  - `first50_avg_frac_reward_zero_std = 0.4364`
  - `first50_median_reward_std = 0.2005`
  - `max_consecutive_full_zero_std_steps = 1`
- gate 判定：
  - `avg_frac_reward_zero_std <= 0.40`：`FAIL`
  - `median_reward_std >= 0.20`：`PASS`
  - `max_consecutive_full_zero_std_steps <= 3`：`PASS`

**尾部轨迹：**

- `step 25`: `reward_std = 0.1354`, `frac_reward_zero_std = 0.7`
- `step 30`: `reward_std = 0.0736`, `frac_reward_zero_std = 0.8`
- `step 35`: `reward_std = 0.1599`, `frac_reward_zero_std = 0.6`
- `step 40`: `reward_std = 0.2929`, `frac_reward_zero_std = 0.2`
- `step 45`: `reward_std = 0.2005`, `frac_reward_zero_std = 0.7`
- `step 50`: `reward_std = 0.0`, `frac_reward_zero_std = 1.0`

**结论：**

- 这条 `v10` 显式 selector run 属于“边缘但未通过”的 early smoke：
  - `reward_std` 中位数刚好过线
  - 但后半段 `zero_std` 占比偏高，最终把 `avg_frac_reward_zero_std` 顶到 `0.4364`
- 按当前规则，不进入 `170-step`，直接切到 `bucket_unified` fallback。

## 2026-04-22 Geometry100k `bucket_unified` Fallback 静态结果

**触发原因：**

- `v10` 显式 selector 的 `50-step` early smoke 未通过：
  - `first50_avg_frac_reward_zero_std = 0.4364 > 0.40`
- 因此按当前 fallback 规则，切换到 `bucket_unified`，并重新从 base checkpoint 开新分支，而不是继续沿用 `v10` 的 checkpoint-50。

**固定命令：**

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux5/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_bucket_unified_2k/grpo_train_selected_2000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_bucket_unified_2k/grpo_train_report_2000.json \
  --selection-policy bucket_unified \
  --target-size 2000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --near-high-mid-max-pass 0.75 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --reward-mixed-zero-max-fraction 0.20 \
  --near-high-mid-min-fraction 0.03 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0
```

**静态结果：**

- 输出目录：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux5_bucket_unified_2k`
- 选集报告：`grpo_train_report_2000.json`
- 结构 summary：`grpo_train_selected_2000_summary.json`
- 关键验收：
  - `selected_rows = 2000`
  - `fallback_triggered = false`
  - `bucket_floor_shortages = {near_low: 0, reward_mixed_zero: 0, near_high_mid: 0}`
  - `selected_zero_pass_ratio = 0.05`
  - `selected_avg_proxy_reward_std = 0.4336`
  - `selected_median_proxy_reward_std = 0.4050`

**bucket 分配：**

- `core = 1740`
- `near_low = 100`
- `reward_mixed_zero = 100`
- `near_high_mid = 60`
- 其余 bucket 全为 `0`：
  - `easy_tail_nonzero = 0`
  - `high_pass_non_greedy = 0`
  - `zero_valid_low = 0`
  - `zero_valid_high = 0`
  - `zero_reward_std_low = 0`
  - `zero_unique_aux_low = 0`
  - `mastered = 0`

**结论：**

- 在这份 geometry100k 标签池上，`bucket_unified` 与显式 `v10` 的最终 `2k` 选集完全一致。
- 差异不在静态分布，而在于后续训练分支与记录口径：
  - `v10` 使用 stage/tier report
  - `bucket_unified` 使用 bucket report

### `bucket_unified` smoke 终止（2026-04-22）

**执行情况：**

- 训练目录：`models/grpo_vlm_sft44_geometry100k_bucket_unified_s1_4gpu_tuned/v0-20260422-001800`
- 同样使用：
  - `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
  - `1x8 tuned`
  - `num_generations = 8`
  - `temperature = 1.1`
  - `top_p = 0.95`
  - `top_k = 0`
  - `beta = 0.02`

**提前停止原因：**

- `bucket_unified` 选出的训练集与显式 `v10` 训练集字节级完全一致：
  - `sha256 = 6b44b467ffd6ecaa9767555cc9327de2ae864ee6beb48fa838e3b646f41da0b4`
  - `same_bytes = true`
- `bucket_unified` run 的第 `1` 步日志也与 `v10` 完全一致：
  - `reward_std = 0.13258252`
  - `frac_reward_zero_std = 0.5`
  - `reward = 0.296875`

**决策：**

- 在当前这批 geometry100k 标签池上，`bucket_unified` fallback 没有形成新的数据分支，而是退化成与显式 `v10` 完全相同的训练输入。
- 因此继续跑满 `50-step` 只会重复 `v10` 的实验，不再提供新的判别信息。
- 这条 run 在 `step 2` 前后人工终止，不作为新的 smoke 结论。

**当前结论：**

- 本轮有效结论仍然只有一条：
  - geometry100k 新标签池上的显式 `v10` selector 静态通过
  - 但 `50-step early smoke` 因 `avg_frac_reward_zero_std = 0.4364` 未通过
- 由于 `bucket_unified` 与 `v10` 选集完全相同，当前不再把它视为有效 fallback。
- 如果要继续迭代，必须先改变 selector 的实际输出数据，而不是只切换 report / bucket 命名。

## 2026-04-22 Geometry100k `v14` `bucket_unified` 静态结果

**数据源：**

- `datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl`

**固定命令：**

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8/difficulty_labels.jsonl \
  datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/grpo_train_selected_2000.jsonl \
  --report-output datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k/grpo_train_report_2000.json \
  --selection-policy bucket_unified \
  --target-size 2000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --near-high-mid-max-pass 0.75 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-unique-aux-min 2 \
  --near-low-min-fraction 0.05 \
  --near-low-max-fraction 0.20 \
  --reward-mixed-zero-min-fraction 0.05 \
  --reward-mixed-zero-max-fraction 0.20 \
  --near-high-mid-min-fraction 0.03 \
  --near-high-mid-max-fraction 0.08 \
  --mastered-max-fraction 0.0
```

**静态结果：**

- 输出目录：`datasets/grpo_geometry100k_vlm_label_20260421_maxaux8_bucket_unified_2k`
- 选集报告：`grpo_train_report_2000.json`
- 结构 summary：`grpo_train_selected_2000_summary.json`
- 关键验收：
  - `selected_rows = 2000`
  - `fallback_triggered = false`
  - `bucket_floor_shortages = {near_low: 0, reward_mixed_zero: 0, near_high_mid: 0}`
  - `selected_zero_pass_ratio = 0.05`
  - `selected_avg_proxy_reward_std = 0.4043`
  - `selected_median_proxy_reward_std = 0.3721`

**bucket 分配：**

- `core = 1729`
- `near_low = 111`
- `reward_mixed_zero = 100`
- `near_high_mid = 60`
- 其余 bucket 全为 `0`：
  - `easy_tail_nonzero = 0`
  - `high_pass_non_greedy = 0`
  - `zero_valid_low = 0`
  - `zero_valid_high = 0`
  - `zero_reward_std_low = 0`
  - `zero_unique_aux_low = 0`
  - `mastered = 0`

**与上一批 `maxaux5` 的区别：**

- 新的 `v14` 选集不再与旧的 `maxaux5 bucket_unified` 结果相同：
  - `v14` 选集 `sha256 = 492dbfa99fcf5b1aa2adf2f80b0c803a17a80695144d108c587da129c0b64bff`
  - `maxaux5` 选集 `sha256 = 6b44b467ffd6ecaa9767555cc9327de2ae864ee6beb48fa838e3b646f41da0b4`
- 因此这次 smoke 是新的数据分支，不是对前一轮 geometry100k run 的重复执行。

## 2026-04-22 Geometry100k `v14` `bucket_unified` `50-step` Smoke

**训练设置：**

- 训练目录：`models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/v0-20260422-094125`
- 模型：`/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- 配置：
  - `per_device_train_batch_size = 1`
  - `gradient_accumulation_steps = 8`
  - `num_generations = 8`
  - `temperature = 1.1`
  - `top_p = 0.95`
  - `top_k = 0`
  - `max_completion_length = 256`
  - `beta = 0.02`
  - `max_steps = 50`

**主要产物：**

- `args.json`
- `logging.jsonl`
- `checkpoint-50`
- `smoke_gate_first50.json`

**first50 gate：**

- `first50_avg_frac_reward_zero_std = 0.2659`
- `first50_median_reward_std = 0.2913`
- `max_consecutive_full_zero_std_steps = 0`

**结论：**

- 这条 `v14` run 通过了当前 `50-step` smoke gate：
  - `avg_frac_reward_zero_std <= 0.40`：通过
  - `median_reward_std >= 0.20`：通过
  - `max_consecutive_full_zero_std_steps <= 3`：通过
- 相比上一批 `maxaux5` 的 `v10` 失败 run：
  - `first50_avg_frac_reward_zero_std` 从 `0.4364` 降到 `0.2659`
  - `first50_median_reward_std` 从 `0.2005` 提高到 `0.2913`
- 当前可以把这条 `v14` 分支视为 geometry100k 上首条通过 early smoke 的新数据分支。

## 2026-04-22 Geometry100k `v14` `bucket_unified` `170-step` Smoke

**续跑方式：**

- 从 `50-step` run 的 `checkpoint-50` 做 true checkpoint resume：
  - `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/v0-20260422-094125/checkpoint-50`
- 续跑产物目录：
  - `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/v0-20260422-094125/v0-20260422-101003`
- `swift` 在 resume 时仍自动新建了一个子目录，但训练 global step 从 `51/170` 开始，确认为同一条 run 的续跑而非从头重训。

**训练配置：**

- 与通过 `50-step` 的 tuned smoke 配置保持一致：
  - `per_device_train_batch_size = 1`
  - `gradient_accumulation_steps = 8`
  - `num_generations = 8`
  - `temperature = 1.1`
  - `top_p = 0.95`
  - `top_k = 0`
  - `max_completion_length = 256`
  - `beta = 0.02`
  - `max_steps = 170`

**主要产物：**

- `logging.jsonl`
- `checkpoint-170`
- `smoke_gate_first170.json`

**mid gate：**

- `first170_avg_frac_reward_zero_std = 0.3179`
- `first170_median_reward_std = 0.2405`
- `last50_avg_frac_reward_zero_std = 0.3600`
- `last50_median_reward_std = 0.2168`
- `121_170_avg_frac_reward_zero_std = 0.3600`
- `121_170_median_reward_std = 0.2168`
- `max_consecutive_full_zero_std_steps = 0`

**结论：**

- 这条 `170-step` run 不是历史 `v7/v8` 那种中段坍塌：
  - 没有出现连续 `full-zero` step
  - `first170_median_reward_std` 和 `121_170_median_reward_std` 都明显高于 gate 下限
  - `step 170` 收尾仍保持 `reward_std = 0.3395`、`frac_reward_zero_std = 0`
- 但它仍然**未完全通过**当前 `170-step` mid gate：
  - `first170_avg_frac_reward_zero_std <= 0.40`：通过
  - `first170_median_reward_std >= 0.15`：通过
  - `last50_avg_frac_reward_zero_std <= 0.35`：失败，实际 `0.36`
  - `last50_median_reward_std >= 0.15`：通过
  - `121_170_avg_frac_reward_zero_std <= 0.35`：失败，实际 `0.36`
  - `121_170_median_reward_std >= 0.15`：通过
  - `max_consecutive_full_zero_std_steps <= 3`：通过
- 当前判断：
  - 这条分支已经显著优于之前的 geometry100k `maxaux5/v10` 失败 run
  - 但后段 `zero_std` 占比仍略高于当前 promotion 线
  - 按现规则，先不进入 `300-step`，仍归类为“边缘但未过 mid gate”的数据分支

## 2026-04-22 Geometry100k `v14` `bucket_unified` `300-step` Promotion

**续跑方式：**

- 从 `170-step` run 的 `checkpoint-170` 继续 true checkpoint resume：
  - `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/v0-20260422-094125/v0-20260422-101003/checkpoint-170`
- 续跑产物目录：
  - `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/v0-20260422-094125/v0-20260422-101003/v0-20260422-110958`

**训练配置：**

- 仍沿用 `v14` tuned smoke 的同一组配置：
  - `per_device_train_batch_size = 1`
  - `gradient_accumulation_steps = 8`
  - `num_generations = 8`
  - `temperature = 1.1`
  - `top_p = 0.95`
  - `top_k = 0`
  - `max_completion_length = 256`
  - `beta = 0.02`
  - `max_steps = 300`

**主要产物：**

- `logging.jsonl`
- `checkpoint-300`

**运行观察：**

- `300-step` 完整跑通，没有出现历史 `v7/v8/v11` 那种连续 collapse：
  - `step 250`: `reward_std = 0.0776`, `frac_reward_zero_std = 0.8`
  - `step 265`: `reward_std = 0.2973`, `frac_reward_zero_std = 0.3`
  - `step 290`: `reward_std = 0.0890`, `frac_reward_zero_std = 0.7`
  - `step 300`: `reward_std = 0.2765`, `frac_reward_zero_std = 0.4`
- 结论：
  - 后段波动明显增大
  - 但没有进入不可逆的 full-zero 连续坍塌
  - 因此继续推进到 `500-step` 做更长区间诊断

## 2026-04-22 Geometry100k `v14` `bucket_unified` `500-step` Promotion

**续跑方式：**

- 从 `300-step` run 的 `checkpoint-300` 继续 true checkpoint resume：
  - `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/v0-20260422-094125/v0-20260422-101003/v0-20260422-110958/checkpoint-300`
- 续跑产物目录：
  - `models/grpo_vlm_sft44_geometry100k_maxaux8_bucket_unified_s1_4gpu_tuned/v0-20260422-094125/v0-20260422-101003/v0-20260422-110958/v0-20260422-114039`

**训练配置：**

- 继续沿用同一套 tuned 配置：
  - `per_device_train_batch_size = 1`
  - `gradient_accumulation_steps = 8`
  - `num_generations = 8`
  - `temperature = 1.1`
  - `top_p = 0.95`
  - `top_k = 0`
  - `max_completion_length = 256`
  - `beta = 0.02`
  - `max_steps = 500`
- 额外尝试：
  - 显式传入 `save_steps = 50`，希望在 `350/400/450/500` 落中途 checkpoint
  - 但 resume 时 `swift` 明确提示与 checkpoint 内 `trainer_state.json` 的 `save_steps = 500` 不一致
  - 实际运行中也只在 `step 500` 保存了 `checkpoint-500`

**主要产物：**

- `logging.jsonl`
- `checkpoint-500`

**关键统计：**

- `301_500_avg_frac_reward_zero_std = 0.5725`
- `301_500_median_reward_std = 0.1498`
- `421_500_avg_frac_reward_zero_std = 0.5375`
- `421_500_median_reward_std = 0.1692`
- `max_consecutive_full_zero_std_steps = 1`

**代表性坏点：**

- `step 305`: `reward_std = 0.0830`, `frac_reward_zero_std = 0.8`
- `step 315`: `reward_std = 0.0`, `frac_reward_zero_std = 1.0`
- `step 345`: `reward_std = 0.0`, `frac_reward_zero_std = 1.0`

**收尾状态：**

- `step 500`: `reward = 0.5031`
- `step 500`: `reward_std = 0.2373`
- `step 500`: `frac_reward_zero_std = 0.2`

**结论：**

- `500-step` 完整跑通，并最终保存出 `checkpoint-500`
- 但从 `301-500` 整段统计看，后半程已经明显进入高零方差占比区间：
  - `avg_frac_reward_zero_std` 已经升到 `0.57`
  - `median_reward_std` 仅在 `0.15` 附近边缘徘徊
- 这条分支比历史完全 collapse 的 run 仍然更稳：
  - `max_consecutive_full_zero_std_steps = 1`
  - 最后 `step 500` 没有贴零
- 但它也不再属于“稳定 promotion”轨迹，而是“能跑完，但后半程明显劣化”的长程边缘分支

## 2026-04-22 Geometry100k `v14` `bucket_unified` `checkpoint-500` `dev_imo` 回归分析

**评估结果：**

- 评估 CSV：
  - `results/devimo_grpo_compare/v14_checkpoint-500_sv1_eval/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260422-114039_checkpoint-500_sv1_d32_b512_s4_gbs4_gbt100_seed123_20260422T044912Z.csv`
- headline：
  - `Solved: 12/16`
- 对照基线：
  - pre-GRPO SFT：
    - `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T052620Z.csv`
    - `Solved: 14/16`
  - 历史 GRPO `checkpoint-505 sv1`：
    - `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T035755Z.csv`
    - `Solved: 13/16`

**直接结论：**

- `v14 checkpoint-500` 明确低于 pre-GRPO SFT，也低于历史 `GRPO505 sv1`
- 相比 SFT 的回退题有两道：
  - `translated_imo_2008_p1b`
  - `translated_imo_2012_p5`
- 相比历史 `GRPO505 sv1` 的新增回退题只有一道：
  - `translated_imo_2012_p5`
- 没有出现对 SFT 或历史 `GRPO505 sv1` 的新增提升题

**核心判断：**

- 退化主因不是 evaluator 或 search driver 出错，而是 `checkpoint-500` 的 proposal 分布已经偏移，导致 beam 预算在前几层被大量同质构造占满
- 也就是说问题不是“搜得不够深”，而是“前几层已经被带偏”，后续深搜只是把错误分支继续展开

### `translated_imo_2012_p5`

- trace：
  - 当前 `v14 checkpoint-500`：
    - `results/devimo_grpo_compare/v14_checkpoint-500_sv1_eval/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260422-114039_checkpoint-500_sv1_d32_b512_s4_gbs4_gbt100_seed123_20260422T044912Z/problems/0008_translated_imo_2012_p5.jsonl`
  - pre-GRPO SFT：
    - `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T052620Z/problems/0008_translated_imo_2012_p5.jsonl`
  - 历史 `GRPO505 sv1`：
    - `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T035755Z/problems/0008_translated_imo_2012_p5.jsonl`
- SFT 在 `depth = 1` 即命中，`7.39s` 结束
- 历史 `GRPO505 sv1` 更早，在 `depth = 0` 就命中，`3.88s` 结束
- 当前 `v14 checkpoint-500` 则一路跑到 `depth = 3`，消耗完整预算后仍未解出，`276.14s` 结束
- 历史 `GRPO505 sv1` 的命中构造为：
  - `i = on_circum i c d f, on_line i a d`
- 在当前 `v14 checkpoint-500` 的完整 trace 中，这条构造出现次数为 `0`
- 当前 `v14 checkpoint-500` 的候选分布明显偏向 `on_line + on_circle / on_bline / eqdistance`：
  - `depth 0`：`on_circle = 66.1%`
  - `depth 1`：`on_circle = 78.0%`
  - `depth 2`：`on_circle = 86.0%`
- 说明这条 run 已经显著降低了 `on_circum` 类关键辅助构造的概率质量，beam 宽度虽然还在，但被错误家族大量占用

### `translated_imo_2008_p1b`

- trace：
  - 当前 `v14 checkpoint-500`：
    - `results/devimo_grpo_compare/v14_checkpoint-500_sv1_eval/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v0-20260422-114039_checkpoint-500_sv1_d32_b512_s4_gbs4_gbt100_seed123_20260422T044912Z/problems/0003_translated_imo_2008_p1b.jsonl`
  - pre-GRPO SFT：
    - `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T052620Z/problems/0003_translated_imo_2008_p1b.jsonl`
  - 历史 `GRPO505 sv1`：
    - `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T035755Z/problems/0003_translated_imo_2008_p1b.jsonl`
- SFT 在 `depth = 2` 命中，`117.92s` 结束
- 当前 `v14 checkpoint-500` 与历史 `GRPO505 sv1` 都一路跑到 `depth = 3` 后耗尽预算：
  - 当前 `v14 checkpoint-500`：`379.55s`
  - 历史 `GRPO505 sv1`：`385.36s`
- 当前 `v14 checkpoint-500` 在前几层明显偏 `on_circle / on_bline`：
  - `depth 1`：`on_circle = 62.9%`
  - `depth 2`：`on_circle = 50.2%`
- 对照历史 `GRPO505 sv1`，同题的失败形态则更偏 `on_circum`：
  - `depth 2`：`on_circum = 72.6%`
- 因此这道题不是简单复制旧 run 的失败模式，而是换成了另一种同样无效的 proposal 偏置

**与训练统计的对应关系：**

- 这次 `500-step` 长跑在训练后半段已经出现明显退化信号：
  - `301_500_avg_frac_reward_zero_std = 0.5725`
  - `301_500_median_reward_std = 0.1498`
  - `421_500_avg_frac_reward_zero_std = 0.5375`
  - `421_500_median_reward_std = 0.1692`
- 这些统计与 `dev_imo` trace 的现象是对齐的：
  - 模型没有完全 collapse
  - 但 proposal 明显变窄、重复模板增多、关键构造家族覆盖率下降
- 因而 `checkpoint-500` 应视为“可运行但已出现策略分布偏移”的长程边缘点，不适合作为优于 pre-GRPO 的正向证据
