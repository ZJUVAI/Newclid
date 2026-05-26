# CoT SFT Status

## 文档定位

- 本文件回答三个问题：
  - 这条链路迄今为止推进到了哪里
  - 当前最好证据是什么
  - 距离可放心全量生产还有什么差距
- 当前代码流程和字段细节见 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)。
- 按时间顺序的近期实验记录见 [EXPERIMENT_LOG.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/history/EXPERIMENT_LOG.md)。
- 如果下一会话准备继续推进新链路，请先读 [DOSSIER_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/DOSSIER_V1_MAINLINE.md)。

## 当前最新阶段：Proof DAG 直接驱动（2026-05-26）

之前的 `dossier_v1` 用 segment / keyword overlap 启发式重新验证 proof 的每一步，启发式严格弱于 DDAR 的 rule application，导致 `0/12 surface_pass`。

新链路把 bridge_chain 的构造主体从启发式 verification 改成直接读 proof DAG：

- `core/proof_dag.py`：解析 `<proof>` 块成结构化 DAG，从 goal 反向 walk 选 milestone
- `core/rule_catalog.py`：把 `r03`、`r34` 等规则 ID 翻译成真实定理名（"the inscribed angle theorem"、"AA similarity"、"SAS similarity"、"Thales' theorem"）
- `build_proof_dag_skeleton`：从 milestone 直接生成 `bridge_chain` 和 `goal_closure`，每步附带 `rule`、`proof_step_id`、`numerical_check_basis` 字段
- `build_proof_dag_writer_body`：scripted writer，引用真实定理名生成自然语言叙述
- `generate_proof_dag_thinking`：纯脚本路径，零 API 调用即可生成

结果：
- **12-item benchmark surface_pass: 12/12**（先前 baseline 是 0/12）
- 0 forbidden pattern 违规
- 全部 149 个测试通过（含新增 31 个 proof_dag / rule_catalog 测试）
- 单条样本生成耗时 < 1s（无 API 调用）

剩余事项：
- semantic_pass 尚未做语义审读（需要人工 / Codex 验证生成文本的几何正确性）
- 旧 7 个 lacks_* gate 函数和相关 tail/checkpoint helper 暂保留，作为 legacy fallback；后续 PR 可清理
- 模型 planner / critic / writer 当前未启用，纯脚本生成；如需更自然的起手段叙述可后续接回模型

## 阶段性进展

### 阶段 1：从 `v83` 开始把失败模式显式化

- `v83` 到 `v88` 这段，主要是在把坏样本的共性抓出来，而不是追求表面通过率。
- 这时期暴露的核心问题是：
  - `square-like`、`parallelogram`、`common center`、`symmetry` 这类高层 shorthand
  - writer 重复 prefix
  - planner 提前泄露新点
  - `coordinate_relations` 不够 grounded

### 阶段 2：两阶段主链成型

- 到 `v89`，随机 `4` 条里已经能过 `3/4`。
  - 记录：`/tmp/cot_quality_test_run_v89_random4_artifacts_20260516_053813/summary.json`
- 到 `v92`，小样本随机回归第一次达到 `4/4`。
  - 记录：`/tmp/cot_quality_test_run_v92_random4_artifacts_20260516_065335/summary.json`
- 这说明 `plan -> write` 两阶段主链已经成型，但还不代表稳定收敛。

### 阶段 3：`v92` 之后继续迭代，不把一次 `4/4` 当成终点

- 后续又出现了：
  - `v99`：`3/4`
  - `v102`：`2/4`
- 这证明 `v92` 的 `4/4` 只是一次小样本成功，不足以说明链路已经稳定。
- 这一阶段继续加严的重点是：
  - 路线贴合 hidden proof guidance
  - 压制 `midpoint property` / `symmetry` 等偷懒表达
  - 控制 writer 长度边界
  - 防止 bridge step 被跳过或被高层总结代替

### 阶段 4：恢复随机通过率并收紧 route drift

- `v103` 把 `v102` 暴露出的两个失败样本定向修到 `2/2`。
  - 记录：`/tmp/cot_regression_v103_v102_failed_outputs_artifacts_20260516_194526/summary.json`
- `v104` 随机回归恢复到 `4/4`。
  - 记录：`/tmp/cot_quality_test_run_v104_random4_artifacts_20260517_154443/summary.json`
- `v106` 继续维持随机 `4/4`。
  - 记录：`/tmp/cot_quality_test_run_v106_random4_artifacts_20260517_162205/summary.json`
- 但这两轮都还明显依赖样本级重试，不是“一次成文就稳定过”。

### 阶段 5：当前设计收敛到 compact handoff + bridge contracts

- 新一轮实现不是简单调 prompt，而是改了 writer 输入结构：
  - `ec59ec5`：step-level `focus_points`
  - `b45126c`：`Non-Skippable Bridge Checklist`
  - `82118d6`：compact `Approved Writer Handoff`
  - `56e432b`：补回 `preferred_sentence_shell`
  - `ace2ae7`：放宽 bridge-focus fallback
- 最近 live 证据：
  - `v137`：sample0 `1/1`，`plan 1 + write 1`
  - `v139`：sample2 `1/1`，`plan 1 + write 1`
  - `v141`：sample1 `1/1`，`plan 1 + write 1`
  - `v142`：固定 `4` 条回归 `4/4`

### 阶段 6：开始把“脚本通过”和“语义通过”分开看

- 2026-05-18 对最新完整 run `v142` 做了结合原题和图片的人工/Codex 审读。
- 审读范围：
  - `v142` 固定 `4` 条回归全部样本
  - 交叉查看 `v141` 和 `v139` 的单样本输出，确认问题不是 `v142` 单轮偶发
- 当前结论：
  - `v142` 的 `4/4` 只能算 `surface_pass`
  - 如果按 README 里的数据质量目标衡量，这 `4` 条都还不能记为 `semantic_pass`
- 暴露出的新核心问题不是格式，而是语义：
  - bridge relation 被逐句写出来了，但 support 并不能真的推出它
  - 文本后半段看起来像一条 route，却和题面/图形并不真正对齐
  - 前缀里的 visual cue 被写进了 prose，但没有真正进入后续推理链
  - 最后两步经常形式上落到 goal，实际上并没有形成可信闭环
- 这说明当前 validator 更擅长控制 surface quality，还不擅长识别“看起来顺，但几何上不成立”的桥接句。

### 阶段 7：observation-first skeleton 与 observation-cue reuse 落地

- 2026-05-19 之后，当前实现又沿着“不要先锁死 anchor frame”这个方向继续推进，已经落库的关键提交包括：
  - `72f9fc0`：`Add hybrid scripted planner for cot_sft generation`
  - `02edce3`：`Add observation-first plan skeleton support`
  - `9203395`：`Observation-first writer prefix and coverage contracts`
  - `ab9e26c`：`Enforce observation cue reuse in writer validation and audits`
- 当前真实变化不是小调 prompt，而是三层同时变化：
  - `plan` 阶段支持 `hybrid`，先由脚本生成 observation-first skeleton，再让 planner 展开
  - writer prefix 改成 observation sentence -> overview -> orientation -> coordinate -> visible
  - validator / `generation audit` 新增 observation cue reuse 检查，要求正文尤其是前 `3` 句必须真的接回 approved observation cues
- 当前证据：
  - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
    - 当前结果：`Ran 93 tests ... OK`
  - `python experiments/cot_sft_generation/maintenance_smoke_check.py`
    - 当前结果：全部检查通过
- 这一步的作用不是直接证明语义质量已经够好，而是把“visual cue 只停留在 prefix、正文又退回 anchor-only narration”这个已知失败模式正式收进实现与回归基线。

### 阶段 8：`dossier_v1` 默认化并做第一次端到端 live 审读

- 2026-05-20，默认生成风格已经从旧的 `model_evidence` 切到 `dossier_v1`：
  - 默认：`--generation-style dossier_v1`
  - fallback：`--generation-style model_evidence_legacy`
- 这轮不是只改 prompt，而是同时完成了：
  - dossier prompt / schema / validator / writer 主链落地
  - legacy fallback 路由保留
  - `generation_style` 写入 run artifacts / semantic review context
  - dossier-specific generation audit 分支
  - critic `revised_dossier` patch merge 回原 dossier 的运行时处理
- 自动回归：
  - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
    - 当前结果：`Ran 71 tests ... OK`
  - `python experiments/cot_sft_generation/maintenance_smoke_check.py`
    - 当前结果：全部检查通过
- 真实 live run 证据：
  - run：`generated/dossier_v1_stratified4_rerun4_20260520.jsonl`
  - artifacts：`generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/summary.json`
  - 模型：`qwen/qwen2.5-vl-72b-instruct`
  - 结果：
    - `surface_pass`: `3/4`
    - `avg_attempts_used`: `5.25`
    - 剩余 `1` 条失败原因：writer length budget
- 真实人工/Codex 语义审读：
  - 同一 run 的 `3` 条 `surface_pass` 样本已回填到 `semantic_audits.jsonl`
  - 审读结果：
    - `semantic_pass`: `0/3`
    - `manual_critical_error`: `3/3`
  - 主要问题：
    - bridge relation 仍然常常不能由 cited supports 推出
    - 一些样本虽然 `surface_pass`，但后半段 route 仍然是伪闭环
    - 这说明 `dossier_v1` 已经把端到端 orchestration 跑通，但默认 `qwen` 还没有给出可直接批量使用的语义质量

### 阶段 9：继续收紧 weak bridge gate，但 full-12 已进入 fail-closed

- 2026-05-22 这轮继续把“看起来顺、实际支撑不足”的弱闭环显式打回，最近一串关键提交包括：
  - `923c571`：`Reject angle closures without directional coverage`
  - `cf0a871`：`Reject ratio closures without local pair support`
  - `1aa1191`：`Reject weak similarity closures without local correspondence support`
  - `f7b54cc`：`Reject weak similarity bridge steps without local correspondence support`
- 其中 `f7b54cc` 的真实变化不是再加一条 prompt 约束，而是把 similarity 的 local-correspondence gate 从“只拦 aux-point similarity bridge”扩展成“所有 similarity bridge claim 都要过门”。
- 自动验证：
  - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
    - 当前结果：`Ran 115 tests ... OK`
  - `python experiments/cot_sft_generation/maintenance_smoke_check.py`
    - 当前结果：全部检查通过
- 最新完整 live 证据目前仍是临时 `/tmp` artifact：
  - `/tmp/cot_sft_quality_review_v1_full12_20260522_postsimbridge_artifacts_20260522_125400/summary.json`
  - 结果：
    - `successful_items`: `0/12`
    - `surface_pass_items`: `0/12`
    - `surface_fail_items`: `12/12`
    - `semantic_review_status`: `not_reviewed`
- 这轮 `0/12` 不能当成质量达标，只能说明：
  - angle / ratio / similarity 这三类弱闭环更少伪装成 `surface_pass`
  - 但当前 `scripted dossier skeleton` 与 planner hygiene 还不能稳定恢复 grounded positive chain
- 最新 full-12 暴露的主错误族已经比较稳定：
  - `unsupported angle/ratio/similar segments before supports ground them`
  - `missing symbolic directional coverage`
  - `missing local pairwise support`
  - `missing local correspondence support`
  - `scripted dossier skeleton invalid: bridge_chain must not be empty`
- 当前主结论：
  - 在“不要放出表面通过但语义站不住的数据”这件事上，当前实现更安全了
  - 但主线已经进入 zero-recall 的 fail-closed 状态，离“可批量产出高质量样本”仍有明显距离
  - 下一步不应继续优先加严 gate，而应优先恢复真正站得住的正例，重点看 `eqratio` / `simtri` 这类 scripted bridge construction 与 planner support hygiene

## 当前流程概括

- 当前默认主链：`dossier_v1`
- 当前 fallback：`model_evidence_legacy`

1. 输入处理
  - 读取题面、图片、`<aux>`、proof、visible point 坐标等字段。
   - 只把图片和题面视为未来学生可见输入，其余字段只在生成期做监督。

2. `source audit`
   - 先检查图片、题面、`<aux>`、proof、坐标之间是否有明显冲突或缺失。
   - 如果发现异常，优先记录到 artifacts，不为了通过率强行编一条看似流畅的 `thinking`。

3. `plan` 生成
   - 教师模型先输出一个结构化 JSON，而不是直接写整段 CoT。
   - 当前推荐 `hybrid`：脚本先给 observation-first skeleton，再由 planner 展开。
   - 关键字段包括 `anchor_points`、`observation_relations`、`figure_overview`、`coordinate_hints`、`aux_direct_relations`、`bridge_steps`、`goal_finish`。
   - hidden 坐标和 hidden proof 只用于约束这条链要可解、贴近真实路线，不允许直接暴露到最终文本。
   - `plan` 字段说明：
   - `anchor_points`：通常选 3 到 4 个可见点，复杂题可放宽到 5 个，作为最终 `thinking` 里打标签的坐标锚点；当前不再要求它们主导起手观察。
   - `anchor_relation`：围绕这些 anchor points 的一句核心可见关系，用来给整张图定向。
   - `observation_relations`：先从图上局部区域抽出的 visual cue，例如近共线、中点感、局部平行/垂直；这些 cue 后续应真正进入正文。
   - `figure_overview`：对锚点之外的图形结构做简短概览，补充相关点和子结构。
   - `coordinate_relations`：基于 visible point 坐标提炼出的 2 到 4 个具体关系检查，如共线、垂直、中点、等长；复杂题默认应尽量覆盖至少 4 个可见点。
   - `visible_relations`：题面里已有、后续推理应主动复用的可见 formal relations。
   - `coordinate_hints`：把 `coordinate_relations` 总结成自然语言提示，说明哪些视觉关系值得继续追。
   - `goal_bottleneck`：说明当前图到 visible goal 之间最主要的缺口是什么。
   - `helper_idea`：说明缺少哪类辅助机制，如等长转移、垂线连接、中点控制，但此时还不点名新点。
   - `construction`：正式引入 aux，新点怎么构造；如果是多点 aux，要写出 staged strategy。
   - `aux_direct_relations`：构造一完成就直接成立的局部后果，必须是 aux 的 immediate consequences。
   - `bridge_steps`：从 aux 过渡回旧图并逐步靠近目标的中间桥接步骤；每步包含 `relation`、`depends_on`、`why_it_helps`。
   - `goal_finish`：最后一步要落到的 goal-side relation，用来明确收尾目标。

4. `plan` 校验与规范化
   - 脚本检查 JSON 结构是否完整，字段是否点名了具体关系，是否提前泄露 hidden 信息。
   - 同时做 canonicalization，把过于空泛、偷懒或不受支持的表达收紧成更具体的关系表述。
   - 这里重点压制 `symmetry`、`center`、`midpoint property`、空泛 shape shorthand，以及和真实 route 不一致的 bridge steps。

5. writer 生成正文
   - writer 只负责写正文 body，不允许自己写 `<point>` / `<coord>` 标签。
   - observation 句、图形概览句、orientation/anchor 句、coordinate hint 句、visible relation 句由脚本自动注入成前缀。
   - writer 要从 bottleneck 开始，按 `aux_direct_relations -> bridge_steps -> goal_finish` 往后写，避免重复前缀。
   - 当前 validator 还会额外要求：如果 plan 有 approved observation cues，正文和前 `3` 句必须真的把它们接回推理链。

6. 终组装与终检
   - 脚本把前缀和 writer body 组装成最终 `<thinking>...</thinking>`。
   - 然后做终检：检查标签、长度、泄露词、前缀重复、最后几步是否真正落到 goal-side relation。
   - 只有通过终检的样本才记为成功。

7. 导出与记录
   - 导出 `thinking + aux`。
   - 同时保存 `summary.json`、`item_records.jsonl`、`item_audits.jsonl`、`semantic_audits.jsonl`，方便后续随机回归、语义审读和失败样本回放。

8. 维护侧补强
  - 固定 benchmark 已经开始版本化进仓库，不再只靠 `/tmp`。
  - 语义审读结果现在可以通过 `semantic_review.py` 回刷到 `summary.json`。
  - artifacts 字段协议已经单独写入 `ARTIFACT_SCHEMA.md`，不再只散落在实现和聊天记录里。
  - `source audit` / `generation audit` 与句级 relation 命中 helper 已经拆到 `audits.py`。
  - visible premise summaries 已经从主脚本迁到 `audits.py`。
  - 底层几何文本解析、relation normalization，以及 hidden coordinate candidate / hint / guidance 已经从主脚本拆到 `geometry_text.py`，主脚本职责边界比之前更清楚。
  - 统一维护入口 `maintenance_smoke_check.py` 已落仓，后续 Codex 会话可以直接跑一条命令检查维护基线是否断裂。
  - 已经补上一个不依赖外部 API 的 offline fixture pipeline test，可以离线验证 planner -> writer -> artifacts 主链编排没有断。
  - writer contract / coverage target / prefix 组装这层公共协议已经拆到 `writer_contracts.py`。
  - planner / writer prompt 与 retry feedback 已经拆到 `prompt_builders.py`，主脚本进一步从 `4124` 行降到约 `2460` 行。

更细的字段格式、脚本派生字段和 writer 合同见 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)。

## 实验经验

- 只靠 prompt 不够，必须靠 validator 和真实抽样回归一起收紧。
- 最常见的问题不是源样本自相矛盾，而是生成端偷懒：用 `symmetry`、`center`、`midpoint property` 这类高层 shorthand 跳步。
- 把推理拆成 `plan -> write` 后，质量明显比直接整段生成稳定。
- writer 最容易出现两类退化：重复前缀已说过的话，或在最后几步和真实 `goal_finish` 脱节。
- 小样本回放能修具体 bug，但是否真的变好，还是要看随机抽样。
- 中间关键控制现在基本都已经脚本化了，包括 `source audit`、planner JSON 校验、route grounding、coverage target 派生、writer 终检；不是只靠人工读样本。

## 常见问题与例子

### 1. shorthand 泄露或高层偷懒表达

- `midpoint property`
  - 出问题的原句（`thinking`）：`the visual midpoint property at a for segment bf suggests the goal ab equals af is true.`
  - 问题：把具体中点/等长关系偷换成高层概括，最终组装时被判 hidden-style leakage。
  - 出处：`/tmp/cot_quality_test_run_v102_random4_artifacts_20260516_174559/item_records.jsonl:3`
  - 对应错误：`Final assembly validation failed: Forbidden leakage pattern detected: midpoint property`

- `square-like` / `square structure`
  - 出问题的原句（`thinking`）：`another square-like structure aefg is attached at a`
  - 问题：用形状标签代替具体的垂直、平行、等长关系。
  - 出处：`/tmp/cot_quality_test_run_v83_random2_artifacts_20260516_030943/item_records.jsonl:2`
  - 审计记录：`/tmp/cot_quality_test_run_v83_random2_artifacts_20260516_030943/item_audits.jsonl:2`

- `common center`
  - 出问题的原句（`thinking`）：`A helper point is needed to serve as the common center for comparing distances to a, b, and e.`
  - 问题：用模糊 center 话术跳过具体的中点、等距或垂线关系。
  - 出处：`/tmp/cot_quality_test_run_v84_random2_artifacts_20260516_032223/item_records.jsonl:2`
  - 审计记录：`/tmp/cot_quality_test_run_v84_random2_artifacts_20260516_032223/item_audits.jsonl:2`

- `parallelogram`
  - 出问题的原句（`thinking`）：`point d completes a parallelogram abcd.`
  - 问题：直接引入高层结构标签，容易让文本看起来像在复述 hidden route，而不是从可见关系出发。
  - 出处：`/tmp/cot_quality_test_run_v64_item1_artifacts_20260515_162854/item_records.jsonl:1`
  - 审计记录：`/tmp/cot_quality_test_run_v64_item1_artifacts_20260515_162854/item_audits.jsonl:1`

- `circumcenter`
  - 出问题的原句（`plan.bridge_steps[?].why_it_helps`）：`this makes h the circumcenter of abc, establishing symmetry between a and c needed for the next congruence.`
  - 问题：在 `why_it_helps` 里偷带了高层路线和 symmetry 解释，没有把支持关系落到具体点线段上。
  - 出处：`/tmp/cot_quality_test_run_v20_triple_artifacts_20260515_041331/item_records.jsonl:2`

### 2. 长度边界

- 出问题的原句（报错，不是正文句子）：`Writer body too long (1244 chars, maximum 1243)`
- 对应正文片段（`thinking` 末段来自 writer body）：
  - `Because ag equals cg and the angle between ab and ad equals the angle between ad and ac, triangles age and cge are congruent, and this supplies the equality needed next.`
  - `Because the length of ab equals the length of ac and the angle between ab and ad equals the angle between ad and ac, ac equals af, and this supplies the last equality needed for the final conclusion.`
- 问题：正文内容本身未必错误，但超出脚本为 writer 预留的长度预算，导致整条样本失败。
- 出处：`/tmp/cot_quality_test_run_v102_random4_artifacts_20260516_174559/item_records.jsonl:1`
- 这类问题说明 prefix 注入和 writer 可用长度之间仍然比较紧，轻微波动就可能失败。

### 3. bridge step 没有真正写出来

- `plan` 里要求的原句目标（`plan.bridge_steps[2].relation`）：`gf equals fi`
- 正文实际写出的原句（`thinking`）：`Because line ig is parallel to line ac and ag equals bg, if equals fg, which prepares ratio ag to fg equals ratio gh to fh.`
- 问题：虽然意思接近，但 writer 没有按脚本要求把批准的 bridge relation 以指定顺序、指定表面形式明确落地。
- 出处：`/tmp/cot_quality_test_run_v90_random4_artifacts_20260516_060955/item_records.jsonl:1`
- 对应错误：`Writer body must explicitly realize bridge_steps[2].relation in order`
- 审计记录：`/tmp/cot_quality_test_run_v90_random4_artifacts_20260516_060955/item_audits.jsonl:1`

### 4. 其他仍会反复出现的问题

- writer 重复 injected prefix
  - 高频错误：`Writer body overlaps too much with the injected prefix block; continue from it instead of repeating it`
  - 这类问题对应的是正文把前缀里已经出现过的 overview、坐标提示或 visible givens 再说一遍；具体样本可见：
    - 出处：`/tmp/cot_quality_test_run_v75_random2_artifacts_20260515_183929/item_records.jsonl`
  - 这说明即使 plan 正确，writer 仍会把前缀里已经说过的 overview 或 visible givens 又重复一遍。

- bridge 句没有点明具体 supports
  - 高频错误：`Writer sentence for bridge_steps[i] must name at least one approved supporting relation`
  - 或 `Writer sentence for bridge_steps[i] uses a generic shortcut without naming enough supporting relations`
  - 这类问题对应的坏句子通常形如：`this similarity transfers ...`、`it follows ...`、`by symmetry ...`，只说结果，不点出具体依赖关系。
  - 这类问题本质上也是“跳步”，只是发生在 writer 落句阶段。

- 新点出现过早
  - 高频错误：`new point 'h' must not appear before the construction field`
  - 对应坏句子常出现在 `figure_overview` 或 `helper_idea`，即在正式 `construction` 前先把新点名说出来。
  - 出处：`/tmp/cot_quality_test_run_v26_triple_artifacts_20260515_064044/item_records.jsonl:3`
  - 说明 planner 有时会在 `figure_overview` 或 `helper_idea` 里提前剧透 aux 点名。

- `coordinate_relations` 不够 grounded
  - 出问题的原句（`plan.coordinate_relations`）：`line ad looks parallel to line bc`
  - 说明模型会把 visible premise 或自己发明的高层关系混进坐标提示，而不是老老实实使用脚本给出的 coordinate candidates。
  - 出处：`/tmp/cot_quality_test_run_v22_triple_artifacts_20260515_044743/item_records.jsonl:3`

## 当前最好质量

- 如果按 `surface_pass` 看，当前设计分支的最强 live 结果仍然是 `v142`：
  - 固定 `4` 条回归：`4/4`
  - `source_audit_issue_items=0`
  - `generation_audit_issue_items=0`
  - 记录：`/tmp/cot_regression_v142_v104sample_shell_handoff_output_artifacts_20260518_022014/summary.json`
  - 样本级情况：
    - sample0：`plan 1 + write 1`
    - sample1：`plan 1 + write 1`
    - sample2：`plan 1 + write 1`
    - sample3：`plan 1 + write 2`
- 如果只看当前默认 `dossier_v1` 主链：
  - 最新真实证据是 `generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/summary.json`
  - `surface_pass`: `3/4`
  - 但经人工/Codex 审读后，`semantic_pass`: `0/3`
  - 因此它已经证明“新链路能跑通且 surface 改善明显”，还没有证明“默认模型输出已经达到 README 的数据质量目标”
- 如果按 `semantic_pass` 看，当前还没有一轮最新 run 能证明“这一批样本已经达到 README 的数据质量目标”：
  - 对 `v142` 的人工/Codex 审读结论是：`4/4 surface_pass`，但 `0/4 semantic_pass`
  - 其中 sample0 最接近可用，但后半段 bridge 仍有支撑错位和 route 落地不实的问题
  - sample1 到 sample3 则已经出现更明显的伪 bridge、伪等长、伪相似或 goal-side 收尾失真
- 因此，当前最佳质量应描述为：
  - 表层格式、泄露控制和 route checklist 已经显著变强
  - 小样本脚本通过率重新回到 `4/4`
  - 但真实几何语义可靠性仍未建立，不能直接视为可批量生产的数据链路

## 当前维护支撑度

- 如果问题是“这套代码和文档现在能不能支撑稳定的长期 Codex 迭代”，当前答案现在可以明确写成“能”：
  - 文档分工已经清楚区分目标、现状、实验时间线、维护约定和 artifact schema
  - 固定 benchmark 已落仓，而且已经补到 `goal_type x aux_type` 的第一版分层清单
  - 语义审读回刷 summary 的协议已可执行
  - 最小验证入口不再依赖额外安装 `pytest`
  - prompt / retry feedback 已经有独立模块和单测，不再和主流程编排硬耦合
  - `run_config.json` 和 `sampled_inputs.jsonl` 已经进入正式 schema，并带 git / 输入文件指纹
  - `source audit` / `generation audit` 已经从主脚本拆出，后续改审计规则不必再同时改编排层
  - offline fixture pipeline test 已落仓，后续 Codex 会话可以在不依赖外部 API 的情况下离线验证 planner -> writer -> artifacts 主链
- 但如果问题是“后续维护成本是否已经足够低”，答案仍然是否：
  - [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py) 仍然过大
  - benchmark 的 `aux_shape` 和长尾失败模式覆盖仍然偏窄
  - 自动 `critic` 还没有落地

## 距离目标的差距

- 当前最主要的差距已经不是 surface 约束不够，而是 semantic validator 仍然偏弱：
  - 它能检查“bridge 写没写出来”
  - 对 `collinear` / `similar` / `ratio` 这类 bridge，最近一轮已经开始通过更严格的 `required_supports` 选择、`min_support_mentions`，以及 relation-signature matcher 去拦截“support 看起来相关、其实推不出当前 bridge”的伪通过样本
  - 最新一轮又补了一个更贴近 rerun9 的硬约束：`angle` / `similar` / `ratio` bridge 不能在 `required_supports` 还没把相关 segment/ray 对象引进来的情况下，突然自己冒出多个新的 `df` / `dk` / `bd` 这类对象
  - 同时也补了两条编排层修正，避免“本来能修好，但死在流程上”：
    - `anchor_points` 如果只是把 coordinate-heavy 的外层点吸进去、导致非 anchor coverage 失真，脚本会优先自动回收到更小的 anchor frame
    - planner 对 support/object grounding、prerequisite route checkpoint、non-anchor coordinate coverage 这类可修复失败现在会自动多给 `1-2` 次 bonus retry
  - 但这仍然只覆盖了部分高频结构，尚不能视为完整 semantic proof checker
- writer 目前仍有过大的自由度：
  - 即使 planner/contract 给定了 route，writer 仍可能把 support 和 relation 拼成一条表面合法、几何上失真的句子
- benchmark 基线虽然不再只有固定 `4` 条：
  - 现在已经补到 `12` 条分层清单，并覆盖 `6` 个核心 goal type 的 `single_point / multi_point`
  - 但更细的 `aux_shape`、复杂度分桶和失败模式分桶还没有补齐
- 当前仍有一部分硬阈值更偏工程控形，不一定与真实质量一致：
  - 复杂题虽然已经开始按复杂度自适应放宽 `anchor_points` / `coordinate_relations` / `bridge_steps` / `<thinking>` 总长度 / `<point><coord>` 标签数预算，但这些预算是否足够仍要继续靠 Codex 审读验证
- 实验记录口径也需要更新：
  - 不能再把 `4/4`、`generation_audit_issue_items=0` 直接当成高质量证据
  - 后续必须同时记录 `surface_pass_rate` 和 `semantic_pass_rate`
- `source audit` 目前更多是在排除显式冲突，还没有解决“源样本没错，但生成文本语义错位”的主问题。

## 下一步修改方向

1. 先改成功标准，而不是继续只调 writer prompt
   - 所有 run 都要区分 `surface_pass` 和 `semantic_pass`
   - 没有人工/Codex 审读通过的 run，不应被写成“质量提升证据”

2. 在 `write` 之后增加独立 `critic` 阶段
   - 重点不是再查格式，而是结构化审稿：
     - support 是否真的推出当前 bridge
     - 这一步是否和图片/题面一致
     - 最后两步是否真实闭环到 goal

3. 收缩 writer 在关键桥接句上的自由度
   - 开头 obstacle / helper 句仍可自由写
   - `aux_direct_relations`、`bridge_steps`、`goal_finish` 应更接近半模板渲染
   - 目标是减少“句子流畅但 relation 不成立”的空间

4. 给 planner 的每个 bridge step 增加更强的支撑账本
   - 不只保留 `relation / depends_on / why_it_helps`
   - 还应明确：
     - support 来自 visible givens、aux 直接后果，还是前序 bridge
     - 依赖了哪些具体点
     - 为什么这些 support 足以推出当前 relation

5. 把纯黑名单式高层几何词控制改成“条件允许”
   - `symmetry`、`circumcenter`、`parallelogram` 等词本身不是错误
   - 真正要限制的是：这些词不能替代关键支撑关系
   - 后续应优先做“若出现高层词，必须同时给出具体支撑”的检查

6. 重新审视固定数量和长度阈值
   - 对复杂题，应允许更多 anchor、更多 coordinate cues、更多真实 bridge
   - 这些预算更适合改成按题复杂度自适应，而不是长期固定死

7. 按 goal type 拆 prompt 和语义审计标准
   - `eqratio`、`eqangle`、`simtri`、`contri` 的闭环方式不同
   - 后续不应继续让一套 writer 合同覆盖全部类型

8. 更积极地放弃低置信样本
   - 如果 planner、writer、critic 在后半段 bridge 上不一致，宁可过滤
   - 当前目标是高质量蒸馏样本，不是最大化表面通过率
