# CoT SFT Experiment Log

本文件用于实时记录 `experiments/cot_sft_generation` 近期实验、证据和当前运行状态。

## 2026-05-18 当前快照

### 最近提交

- `ace2ae7` `Relax bridge focus fallback for anchor-side steps`
  - 这已经不是未提交补丁，已经入库。
  - 改动点：放宽 `build_bridge_step_focus_points(...)` 的 fallback。
  - 目的：如果某个 bridge step 的非锚点 `focus_points` 过窄，就回退到 support-side points，并允许把 anchor-side support 也补进来。
  - 直接动机：`v142` sample3 的首条 bridge 句第一次失败，报错是：
    - `Writer sentence for bridge_steps[0] must mention at least one approved bridge focus point from its contract`
  - 当时 sample3 的相关 route 是：
    - `ag equals eg`
    - `cg equals eg`
    - `triangles afg and cfg are similar`
    - `dg equals fg`
  - 补丁前，step1 的 `focus_points` 太窄，writer 很容易自然地先谈 support-side 的 `d/e/g`，却因为 contract 只收得很窄而被拒。

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

### 2026-05-18 人工语义审读补充

- 在 `v142` 完整落盘后，对这 `4` 条样本做了结合原题和图片的人工/Codex 审读，不使用脚本做“是否成立”的替代判断。
- 审读结论：
  - `v142` 的 `4/4` 只能算 `surface_pass`
  - 如果按 README 的数据质量目标衡量，这 `4` 条都还不能记为 `semantic_pass`
- 共同问题不是格式，而是后半段桥接语义：
  - bridge relation 表面上逐句出现了，但 support 与 relation 经常错位
  - 文本后半段像是在复述一条 route，而不是从图和题面上真实推出
  - visual cue / coordinate cue 常常只停留在前缀，没有真正进入后续推理链
  - 最后两步经常形式上落到 goal，但没有真实闭环
- 样本级简记：
  - sample0：最接近可用，但 `c, g, k are collinear` 与后续相似三角形的支撑仍不扎实
  - sample1：存在明显支撑错位，例如把长度条件拿去支撑共线或新的等长
  - sample2：存在更明显的伪 bridge，例如把“同垂于一线”直接写成等长
  - sample3：存在更明显的伪等长、伪相似和 goal-side 收尾失真
- 交叉查看：
  - `v141` 和 `v139` 的对应单样本输出也出现了同类问题
  - 这说明问题不是 `v142` 单轮偶发，而是当前 validator 主要控制 surface quality，尚不足以担保 semantic quality

### 当前正在跑的回归

- `v142`
  - 任务：固定 `4` 条回归
  - 输入：`/tmp/cot_regression_v114_v104sample_rebuilt_input.jsonl`
  - artifacts：`/tmp/cot_regression_v142_v104sample_shell_handoff_output_artifacts_20260518_022014`

- 截止当前日志状态：
  - 最终结果：`4/4`
  - `source_audit_issue_items=0`
  - `generation_audit_issue_items=0`
  - sample0：`plan 1 + write 1`
  - sample1：`plan 1 + write 1`
  - sample2：`plan 1 + write 1`
  - sample3：`plan 1 + write 2`
  - 当前日志摘录：
    - `2026-05-18 10:22:43 [INFO] [plan] Valid output in 149.55s`
    - `2026-05-18 10:23:17 [INFO] [write] Valid output in 33.57s`
    - `2026-05-18 10:28:48 [INFO] [plan] Valid output in 331.30s`
    - `2026-05-18 10:30:15 [INFO] [write] Valid output in 87.30s`
    - `2026-05-18 10:33:05 [INFO] [plan] Valid output in 169.08s`
    - `2026-05-18 10:34:06 [INFO] [write] Valid output in 61.10s`
    - `2026-05-18 10:37:02 [INFO] [plan] Valid output in 176.58s`
    - `2026-05-18 10:39:17 [WARNING] [write] Validation failed: Writer sentence for bridge_steps[0] must mention at least one approved bridge focus point from its contract`
    - `2026-05-18 10:39:55 [INFO] [write] Valid output in 36.72s`

- `v143`
  - 任务：sample3 targeted 回放，验证 bridge focus fallback
  - 输入：`/tmp/cot_regression_v143_single_sample3_focus_fallback_input.jsonl`
  - artifacts：`/tmp/cot_regression_v143_single_sample3_focus_fallback_output_artifacts_20260518_024413`
  - 当前状态：
    - 这轮没有产出 `summary.json`，因此没有形成可用于判断质量的正式结论。
    - `run.log` 只记录到：
      - `2026-05-18 10:49:45 [INFO] [plan] Valid output in 332.14s`
      - `2026-05-18 10:49:45 [INFO] [write] Attempt 1/3`
    - 之后未完成落盘，当前也没有活跃进程；因此这轮只能记为未完成，不应拿来证明 `ace2ae7` 已经生效。

### 最新判断补充

- `56e432b` 之后，当前最强的 live 证据是：
  - sample0 单样本：`plan 1 + write 1`
  - sample1 单样本：`plan 1 + write 1`
  - sample2 单样本：`plan 1 + write 1`
- 固定 `4` 条回归 `v142` 已经给出新的完整 `4/4` 证据，但 sample3 仍依赖一次 writer retry。
- `ace2ae7` 已经把 sample3 暴露出的 contract 过窄问题补到代码里，但还缺新的 live 成功样本来确认它是否把 sample3 从 `write 2` 压回 `write 1`。
- 更重要的是，`v142` 这轮人工语义审读已经说明：
  - `4/4` 不等于这 `4` 条样本已经满足 README 的数据质量目标
  - 后续实验记录必须把 `surface_pass` 和 `semantic_pass` 分开写，不再只记录脚本通过率

### 当前判断

- 最近几轮改动方向已经比较明确：
  - 先给 writer 更明确的局部 bridge 约束
  - 再压缩 plan-to-write handoff，去掉重复的大块上下文
  - 最后只把最必要的局部句壳加回去
- 但从 `v142` 的人工审读看，下一阶段不能继续只沿着“writer 合同更紧”这条路推进：
  - 当前真正缺的是后半段 bridge 的语义审稿能力
  - 下一步应优先补 `critic` 阶段、收缩 writer 在关键桥接句上的自由度，并把 run 级验收切换成“脚本回归 + Codex 人审”的双通道

- 现阶段最关键的验证项仍然是：
  - 在 `ace2ae7` 之后，sample3 是否能稳定保持 `write 1`
  - 当前 compact handoff 路线在更大随机样本上是否还能维持 `surface_pass`
  - 在此基础上，是否能通过新的人工/Codex 抽样审读拿到第一批可信的 `semantic_pass` 证据
