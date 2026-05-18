# CoT SFT Experiment Log

本文件用于实时记录 `experiments/cot_sft_generation` 近期实验、证据和当前运行状态。

## 2026-05-18 当前快照

### 最近提交

- `56e432b` `Add bridge sentence shells to writer handoff`
  - 在 compact writer handoff 里给每个 `bridge_steps` 补回 `preferred_sentence_shell` 和 `min_support_mentions`。
  - 目的：压掉 compact handoff 后 sample1 首轮 `generic shortcut` 的 writer 失败。

- `82118d6` `Compress writer handoff payload`
  - 把 writer prompt 从整份 plan + 多套重复说明，压成更小的 `Approved Writer Handoff`。
  - 保留的核心字段：
    - `goal_bottleneck`
    - `helper_idea`
    - `construction`
    - `aux_direct_relations`
    - 精简版 `bridge_steps`
    - `goal_finish`
    - opening/helper 句相关的 focus hints

- `b45126c` `Add non-skippable bridge sentence checklist`
  - 给 writer prompt 和 retry feedback 增加 ordered checklist。
  - 目的：强制每个 bridge step 各自成句，不允许跳过中间桥接关系。

- `ec59ec5` `Add step-level bridge focus targets`
  - 给每个 `bridge_steps` 派生 `focus_points` / `focus_hint`。
  - writer validator 现在要求对应桥接句至少点到该 step 的非锚点局部区域。

### 近期证据

- 静态重验：
  - 历史 `v117` 四条成功样本在当前 validator 下仍然 `4/4` 通过。

- prompt 体量变化：
  - 早期 writer prompt 约 `132720` 字符。
  - compact handoff 后约 `20139` 字符。
  - 加回 shell 后当前约 `21245` 字符。

- `v137` 单样本成功：
  - 路径：`/tmp/cot_regression_v137_single_sample0_compact_writer_handoff_output_artifacts_20260518_014501/summary.json`
  - 结果：`1/1`
  - `source_audit_issue_items=0`
  - `generation_audit_issue_items=0`
  - `plan 1 + write 1`

- `v139` 单样本成功：
  - 路径：`/tmp/cot_regression_v139_single_sample2_compact_writer_handoff_output_artifacts_20260518_015601/summary.json`
  - 结果：`1/1`
  - `source_audit_issue_items=0`
  - `generation_audit_issue_items=0`
  - `plan 1 + write 1`
  - 相比旧 `v133`，样本级尝试数从 `3` 降到 `2`

- `v141` 单样本成功：
  - 路径：`/tmp/cot_regression_v141_single_sample1_shell_handoff_output_artifacts_20260518_021517/summary.json`
  - 结果：`1/1`
  - `source_audit_issue_items=0`
  - `generation_audit_issue_items=0`
  - `plan 1 + write 1`
  - 这条样本对应前一轮 fixed-4 回归里唯一掉到 `write 2` 的 sample1，说明 `preferred_sentence_shell` 回补是有效的

### 当前正在跑的回归

- `v142`
  - 任务：固定 `4` 条回归
  - 输入：`/tmp/cot_regression_v114_v104sample_rebuilt_input.jsonl`
  - artifacts：`/tmp/cot_regression_v142_v104sample_shell_handoff_output_artifacts_20260518_022014`

- 截止当前日志状态：
  - sample0：`plan 1 + write 1` 成功
  - sample1：`plan 1 + write 1` 成功
  - sample2：`plan 1 + write 1` 成功
  - sample3：`plan 1` 已开始，尚未返回
  - 当前日志摘录：
    - `2026-05-18 10:22:43 [INFO] [plan] Valid output in 149.55s`
    - `2026-05-18 10:23:17 [INFO] [write] Valid output in 33.57s`
    - `2026-05-18 10:28:48 [INFO] [plan] Valid output in 331.30s`
    - `2026-05-18 10:30:15 [INFO] [write] Valid output in 87.30s`
    - `2026-05-18 10:33:05 [INFO] [plan] Valid output in 169.08s`
    - `2026-05-18 10:34:06 [INFO] [write] Valid output in 61.10s`
    - `2026-05-18 10:34:06 [INFO] [plan] Attempt 1/3`

### 最新判断补充

- `56e432b` 之后，当前最强的 live 证据是：
  - sample0 单样本：`plan 1 + write 1`
  - sample1 单样本：`plan 1 + write 1`
  - sample2 单样本：`plan 1 + write 1`
- 固定 `4` 条回归 `v142` 目前已经证明前三条样本也都是 `plan 1 + write 1`，但整轮结果还未落盘。

### 当前判断

- 最近几轮改动方向已经比较明确：
  - 先给 writer 更明确的局部 bridge 约束
  - 再压缩 plan-to-write handoff，去掉重复的大块上下文
  - 最后只把最必要的局部句壳加回去

- 现阶段最关键的验证项仍然是：
  - 固定 `4` 条回归能否形成一轮新的完整 `4/4`
  - sample1/sample2 是否能稳定保持 `write 1`
