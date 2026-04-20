# GRPO 迭代状态与后续计划

最后更新：2026-04-20

## 背景

- 基础模型：`vlm_sft44`，路径为 `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- 原始数据源：`/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
- 当前训练入口：`scripts/grpo/train_grpo.sh`
- 当前 selector 入口：`scripts/grpo/select_debug_set.py`
- 当前判断：主要瓶颈仍然是数据分布，而不是 GRPO 训练超参数

## 当前 Gate

所有新的 GRPO 数据集迭代都统一使用前 50 个 metric step 的 smoke gate：

- `first50_avg_frac_reward_zero_std <= 0.40`
- `first50_median_reward_std >= 0.20`
- `max_consecutive_full_zero_std_steps <= 3`

只有同时通过这三个 gate 的数据集，才允许继续进入 `300-step` 训练与评估。

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

## 当前主线：`v8` Promotion

### 为什么下一步是 `300-step`

历史 `v1` GRPO run 说明，只看 `50-step` 不够：

- `first50_avg_frac_reward_zero_std = 0.29`
- `first50_median_reward_std = 0.3677`
- 但到 `300-step` 左右，同一条 run 已经塌成持续性的 zero-variance 行为

因此当前的 promotion 路径是：

1. `v8` 在 `checkpoint-50` 通过 smoke
2. true resume 到 `checkpoint-300`
3. 评估 `checkpoint-300` 的 `dev_imo`
4. 只有中段轨迹仍然健康时，才继续 true resume 到 `checkpoint-500`
5. 再评估 `checkpoint-500` 的 `dev_imo`，之后再看 `imo_95`

### `v8` Promotion 规则

在 promotion 阶段固定沿用 smoke 成功时的设置：

- `CUDA_VISIBLE_DEVICES=0,1,2,3`
- `num_generations = 8`
- `temperature = 0.9`
- `top_k = 50`
- `beta = 0.04`
- `max_completion_length = 256`
- `reward_log_interval = 20`

使用 true checkpoint resume，而不是只恢复模型参数：

- `checkpoint-50 -> checkpoint-300`
- `checkpoint-300 -> checkpoint-500`

决策规则：

- 如果 `300-step` 轨迹保持稳定，且 `dev_imo` 结果可接受，则继续到 `500-step`
- 如果 `300-step` 轨迹开始向历史 `v1` 或 `v7` 的失败模式回归，则停止 promotion，回到数据迭代

### `v8` Promotion 当前状态

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

- `v8` 是目前为止最好的 GRPO 数据集迭代版本。
- `v8` 在 50-step smoke gate 上优于 `v7`。
- 但 `v8` 到 `step 147 / 300` 仍然表现出明显的中段塌缩：
  - `all_avg_frac_reward_zero_std = 0.6134`
  - `last20_avg_frac_reward_zero_std = 0.7750`
  - `last20_median_reward_std = 0.0`
- 因此，项目下一步应该从“在同一个 selector 上继续补更多标签”，转向“修改 selector / sampling 机制，显式压制 `50-150` step 窗口中的 zero-variance streak”。
- 历史说明：`v7` 无法撑过中段 promotion：
  - 它通过了 smoke
  - 但在 `step 171 / 300` 崩塌
- 当前主线应变为：
  - 最终确认 `v8` 的 promotion 结论
  - 记录这次中段失败轨迹
  - 在启动 `v9` 之前重做 selector / promotion policy 设计
- 当前阶段的 Git 纪律：
  - 只跟踪 `docs/` 下这两个文档
  - 不要提交临时 benchmark resume 文件、monitor log 或一次性的 recovery helper
