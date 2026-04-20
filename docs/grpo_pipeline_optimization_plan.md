# GRPO 迭代状态与后续计划

最后更新：2026-04-20

## 背景

- 基础模型：`vlm_sft44`，路径为 `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- 原始数据源：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
- 当前训练入口：`scripts/grpo/train_grpo.sh`
- 当前 selector 入口：`scripts/grpo/select_debug_set.py`
- 当前判断：主要瓶颈仍然是数据分布，而不是 GRPO 训练超参数

## 2026-04-20 Bug Audit

- `48d9ea5` 修的是两个直接影响 GRPO 语义的 bug：
  - `extract_aux_body()` 不应删除首个 `x00`，否则训练 target 会和模型的 `response_prefix="<aux> x00"` 不一致。
  - `AuxRewardEvaluator._evaluate_uncached()` 之前只正确处理第一个辅助点，多辅助点样本会被截断评估。
- 后续 `2972827` 为了修 CI / test regression，把 `extract_aux_body()` 又改回了旧行为，但保留了多辅助点评估逻辑，形成了“reward 侧半修复、dataset target 侧未修复”的不一致状态。
- 排查结果：
  - 旧版 `v8/v9` selected dataset 的 `response` 均为错误格式；
  - `2000 / 2000` 行都缺失了首个 `x00`，同时后续辅助点前仍残留 `x00`；
  - 因此 `models/grpo_vlm_sft44_v8_tuned_300step_bugfix/v1-20260420-171548` 应视为“reward-side bugfix rerun”，不是 full aux-format fix rerun。
- 已执行修复：
  - 恢复 `src/newclid/training/aux_dsl.py` 的完整前缀语义；
  - 补充 `tests/test_grpo_rewards.py` 回归测试，覆盖多辅助点 reward 与 dataset 导出；
  - 新增 `scripts/grpo/rewrite_selected_aux_responses.py`，从原始 1M 数据按 `(query, fl_problem)` 回填原始 `<aux> ... </aux>`；
  - 已在仓库中保留当前主实验所需的 aux-fix 版数据集：
    - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v9_stagebalanced_2k_auxfix`
  - `v8` 的 aux-fix 数据可通过同一脚本按需重建，但不再放进这次提交里；
- 当前 active 诊断结论：
  - full aux-format fix 已经在 `v8` / `v9` 两条 selector 上完成 smoke 诊断；
  - 结果表明问题不是“只要修好 aux DSL 就会自然改善”，而是旧 selector 在 aux-fix 语义下需要重新适配。

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
- 下一步应变为：
  - 先用 `label_difficulty_vlm.py` 基于 aux-fix 语义重新标注
  - 基于新标签重新统计 `150k` 标注池的桶分布
  - 重做 `v9` selector 的 bucket 配额与 zero-pass / near-low / near-high 限额
  - 先跑新的 `50-step` smoke
  - 只有 early gate 恢复到接近旧 `v9` 水平时，才重新进入 `170-step` / `300-step`
- 当前阶段的 Git 纪律：
  - 只跟踪 `docs/` 下这两个文档
  - 不要提交临时 benchmark resume 文件、monitor log 或一次性的 recovery helper
