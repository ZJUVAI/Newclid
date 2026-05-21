# CoT SFT Experiment Log

本文件用于实时记录 `experiments/cot_sft_generation` 近期实验、证据和当前运行状态。

## 2026-05-20 dossier_v1 默认化与第一次 live 语义审读

### 本轮实现

- 默认主链切到 `dossier_v1`
  - CLI 默认：`--generation-style dossier_v1`
  - legacy fallback：`--generation-style model_evidence_legacy`
- 新增 / 调整：
  - dossier planner prompt / critic prompt / writer prompt
  - dossier plan validator / writer validator
  - critic `revised_dossier` patch merge 回原 dossier
  - `generation_style` 写入 `item_records.jsonl`、`item_audits.jsonl`、`semantic_audits.jsonl`、`summary.json`
  - dossier-specific `audit_generation_quality(...)` 分支
- 为了让 live run 更贴近 README 的最终质量目标，又补了几类 runtime 兜底：
  - `straight line` / `intersect at right angles` / `equidistant` 这类自然表述的 relation normalization
  - dossier `supports` 的 `0-based / 1-based` 混用兼容
  - `construction` 对齐 hidden `<aux>`
  - `aux_immediate_effects` 优先回收到 direct aux consequences
  - critic partial revision patch merge，而不是强迫 critic 重发完整 dossier

### 自动验证

- `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
  - 当前结果：`Ran 71 tests ... OK`
- `python experiments/cot_sft_generation/maintenance_smoke_check.py`
  - 当前结果：全部检查通过

### live run 记录

- 失败摸底：
  - `generated/dossier_v1_stratified4_20260520.jsonl`
  - `generated/dossier_v1_stratified4_20260520_artifacts_20260520_055214/summary.json`
  - 结果：`0/4`
  - 主要原因：`coordinate_checks` 被误设为必填
- 第二次摸底：
  - `generated/dossier_v1_stratified4_rerun_20260520.jsonl`
  - `generated/dossier_v1_stratified4_rerun_20260520_artifacts_20260520_055509/summary.json`
  - 结果：`0/4`
  - 主要原因：planner 仍被自然语言 relation、aux immediate consequences、support indexing 等机械摩擦卡住
- 当前有效 run：
  - `generated/dossier_v1_stratified4_rerun4_20260520.jsonl`
  - `generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/summary.json`
  - 模型：`qwen/qwen2.5-vl-72b-instruct`
  - 结果：
    - `surface_pass`: `3/4`
    - `surface_fail`: `1/4`
    - 剩余失败原因：writer length budget

### 人工 / Codex 语义审读

- 对这轮 run 的 `3` 条 `surface_pass` 样本做了人工/Codex 审读，并回填：
  - `generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/semantic_audits.jsonl`
- 汇总刷新后：
  - `semantic_pass`: `0/3`
  - `manual_critical_error`: `3/3`
- 共性问题：
  - bridge relation 仍经常不能由 cited supports 推出
  - route 表面完整，但最后几步依然是假闭环
  - 少数样本虽然 `surface_pass`，但正文还会泄露内部 dossier refs

### 当前判断

- `dossier_v1` 已经完成端到端落地，且比初始 `0/4` 明显更稳健。
- 但当前默认 `qwen` 还没有给出可以记作 `semantic_pass` 的样本。
- 因此，这轮改动的价值是：
  - 新链路已经可运行、可回归、可审计
  - `surface_pass` 不再被大量机械摩擦阻断
  - 语义质量问题第一次被明确压缩到“bridge 支撑不成立 / goal 收尾不闭环”这类真正的主问题上
  - 后续如果继续追 README 的最终目标，重点应放在 planner/critic 的真实几何支撑，而不是再继续修 schema 摩擦

## 2026-05-19 observation-first 补充快照

### 最近提交

- `ab9e26c` `Enforce observation cue reuse in writer validation and audits`
  - 目标：把“observation cue 只停在 prefix，正文重新退回 anchor-only narration”正式收进 validator 和 `generation audit`。
  - 新增内容：
    - writer body 必须复用至少一个 approved observation cue
    - 前 `3` 句必须尽早接回 observation cue
    - retry feedback 明确回灌 `observation_focus_relations` / `observation_focus_regions`
    - `generation audit` 新增：
      - `observation_cues_not_reused_in_body`
      - `early_observation_cue_missing`
  - 验证：
    - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
      - 当前结果：`Ran 93 tests ... OK`
    - `python experiments/cot_sft_generation/maintenance_smoke_check.py`
      - 当前结果：全部检查通过

- `9203395` `Observation-first writer prefix and coverage contracts`
  - 目标：把 writer 入口从 anchor-first 改成 observation-first。
  - 新增内容：
    - prefix 顺序改成：
      - observation sentence
      - figure overview sentence
      - orientation / anchor sentence
      - coordinate hint sentence
      - visible relation sentence
    - `coverage_targets` / handoff 新增：
      - `observation_focus_relations`
      - `observation_focus_regions`
      - `goal_side_relation_chain`
      - `bridge_side_relation_chain`
  - 作用：writer 不再一上来默认重新讲 anchor frame，而是先延续已批准的局部 visual cue。

- `02edce3` `Add observation-first plan skeleton support`
  - 目标：把 plan skeleton 本身改成 observation-first，而不是先定 anchor 再补外层关系。
  - 新增内容：
    - `observation_relations`
    - `build_observation_relations_for_skeleton(...)`
    - `select_anchor_points_from_observations(...)`
  - 作用：当前 skeleton 顺序变成：
    - 先 observation cues
    - 再 coordinate relations
    - 再最小 anchor frame

- `72f9fc0` `Add hybrid scripted planner for cot_sft generation`
  - 目标：把“脚本给 skeleton + 模型补 narrative”正式作为 `plan-mode hybrid` 落库。
  - 作用：后续不必再让 planner 从零开始生成整份 plan。

### 当前判断

- 这几次提交的意义，不是证明数据已经达到 `semantic_pass`，而是把之前人工审读里反复出现的一个具体失败模式收进实现：
  - prefix 里虽然写了 visual / coordinate cue
  - 但正文起手又掉回 anchor-only narration
  - 于是 cue 并没有真正进入后续 bridge 链
- 当前 observation-first 改造已经贯通到：
  - `hybrid` plan skeleton
  - writer prefix / handoff
  - validator
  - `generation audit`
- 下一步真正有价值的证据，不是再看 unittest，而是跑新的 live generation，并结合图片和原题审读 observation cue 是否真的进入了后续推理链。

## 2026-05-18 当前快照

### 最近提交

- `2ebca04` `Harden cot sft maintenance regression harness`
  - 这次改动的目标不是继续调样本 prompt，而是补齐长期维护闭环。
  - 新增内容：
    - `tests/test_cot_sft_fixture_pipeline.py`
    - `tests/test_cot_sft_audits.py`
    - `audits.py`
  - 同时完成：
    - 把 `build_visible_premise_summaries(...)` 从主脚本迁到 `audits.py`
    - 把 hidden coordinate candidate / hint / guidance helper 从主脚本迁到 `geometry_text.py`
    - 修复 `validate_plan_response(...)` 缺少 `extract_high_level_structure_markers` 导入导致的运行时 `NameError`
    - 删除未使用的 `run_stage(...)` 死代码
  - 作用：
    - 让 `planner -> writer -> artifacts` 主链第一次具备不依赖外部 API 的离线回归证明
    - 让 prompt/audit/geometry helper 的代码边界继续从主脚本剥离
  - 验证：
    - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
      - 当前结果：`Ran 34 tests ... OK`
    - `python experiments/cot_sft_generation/maintenance_smoke_check.py`
      - 当前结果：全部检查通过

- `351b6bc` `Track cot sft run metadata and schema version`
  - 这次改动的目标不是提升单轮样本质量，而是把 run 复现信息变成正式 artifacts。
  - 新增内容：
    - `run_config.json`
    - `artifact_schema_version = cot_sft_artifacts_v1`
    - `resolved_input_jsonl` / `input_jsonl_sha256` / `input_jsonl_bytes`
    - `sampled_inputs.jsonl` 的正式 schema
  - 作用：后续 Codex 会话不必再靠聊天记录猜“这轮 run 用的是哪份输入、哪份代码”。
  - 验证：
    - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
    - `python experiments/cot_sft_generation/maintenance_smoke_check.py`

- `f5c30ac` `Add cot sft stratified benchmark baseline`
  - 这次改动的目标是把分层固定回归从 `/tmp` 搬进仓库。
  - 新增内容：
    - `benchmarks/stratified_v1_12sample_input.jsonl`
    - `benchmarks/stratified_v1_12sample_manifest.json`
    - `goal_type x aux_type` 的第一版固定 subset
  - 同时更新：
    - `maintenance_smoke_check.py` 现在校验 `benchmarks/` 下所有 `*_manifest.json`
  - 验证：
    - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
    - `python experiments/cot_sft_generation/maintenance_smoke_check.py`

- `40dfb66` `Split cot sft prompt builders and semantic review protocol`
  - 这次改动的目标是把长 prompt 文本和语义审读协议从主脚本/对话记忆里拆出来。
  - 新增内容：
    - `prompt_builders.py`
    - `SEMANTIC_REVIEW_GUIDE.md`
    - `goal_type` / `aux_type` / `review_checklist_version` / `issue_codes` 这类语义审读字段
  - 作用：后续 Codex 改 prompt 或人工回填 `semantic_audits.jsonl` 时，不必继续依赖历史聊天上下文。
  - 验证：
    - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
    - `python experiments/cot_sft_generation/maintenance_smoke_check.py`

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
