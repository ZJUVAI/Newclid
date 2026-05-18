# CoT SFT Status

## 文档定位

- 本文件回答三个问题：
  - 这条链路迄今为止推进到了哪里
  - 当前最好证据是什么
  - 距离可放心全量生产还有什么差距
- 当前代码流程和字段细节见 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/CURRENT_DESIGN.md)。
- 按时间顺序的近期实验记录见 [EXPERIMENT_LOG.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/EXPERIMENT_LOG.md)。

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

## 当前流程概括

1. 输入处理
   - 读取题面、图片、`<aux>`、proof、visible point 坐标等字段。
   - 只把图片和题面视为未来学生可见输入，其余字段只在生成期做监督。

2. `source audit`
   - 先检查图片、题面、`<aux>`、proof、坐标之间是否有明显冲突或缺失。
   - 如果发现异常，优先记录到 artifacts，不为了通过率强行编一条看似流畅的 `thinking`。

3. `plan` 生成
   - 教师模型先输出一个结构化 JSON，而不是直接写整段 CoT。
   - 关键字段包括 `anchor_points`、`figure_overview`、`coordinate_hints`、`aux_direct_relations`、`bridge_steps`、`goal_finish`。
   - hidden 坐标和 hidden proof 只用于约束这条链要可解、贴近真实路线，不允许直接暴露到最终文本。
   - `plan` 字段说明：
   - `anchor_points`：选 3 到 4 个可见点，作为最终 `thinking` 里打标签的坐标锚点。
   - `anchor_relation`：围绕这些 anchor points 的一句核心可见关系，用来给整张图定向。
   - `figure_overview`：对锚点之外的图形结构做简短概览，补充相关点和子结构。
   - `coordinate_relations`：基于 visible point 坐标提炼出的 2 到 3 个具体关系检查，如共线、垂直、中点、等长。
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
   - anchor 坐标句、图形概览句、coordinate hint 句、visible relation 句由脚本自动注入成前缀。
   - writer 要从 bottleneck 开始，按 `aux_direct_relations -> bridge_steps -> goal_finish` 往后写，避免重复前缀。

6. 终组装与终检
   - 脚本把前缀和 writer body 组装成最终 `<thinking>...</thinking>`。
   - 然后做终检：检查标签、长度、泄露词、前缀重复、最后几步是否真正落到 goal-side relation。
   - 只有通过终检的样本才记为成功。

7. 导出与记录
   - 导出 `thinking + aux`。
   - 同时保存 `summary.json`、`item_records.jsonl`、`item_audits.jsonl`，方便后续随机回归和失败样本回放。

更细的字段格式、脚本派生字段和 writer 合同见 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/CURRENT_DESIGN.md)。

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

- 如果按“当前设计分支的最新 live 证据”看，最强结果是 `v142`：
  - 固定 `4` 条回归：`4/4`
  - `source_audit_issue_items=0`
  - `generation_audit_issue_items=0`
  - 记录：`/tmp/cot_regression_v142_v104sample_shell_handoff_output_artifacts_20260518_022014/summary.json`
  - 样本级情况：
    - sample0：`plan 1 + write 1`
    - sample1：`plan 1 + write 1`
    - sample2：`plan 1 + write 1`
    - sample3：`plan 1 + write 2`
- 如果按“历史上最近的小样本随机回归”看，`v104` 和 `v106` 都达到过随机 `4/4`：
  - `v104`：`/tmp/cot_quality_test_run_v104_random4_artifacts_20260517_154443/summary.json`
  - `v106`：`/tmp/cot_quality_test_run_v106_random4_artifacts_20260517_162205/summary.json`
- 但无论是 `v92`、`v104`、`v106` 还是 `v142`，都只有很小的样本规模，不能直接当成全量真实通过率。
- 当前最佳质量可以概括为：
  - 结构上，planner/writer 的主要偷懒路径已经大幅被脚本约束住
  - 小样本上，最新设计已经重新拿到 `4/4`
  - 稳定性上，sample3 一类 bridge-focus 样本还没被证明已经完全摆脱 writer retry

## 距离目标的差距

- 虽然当前设计在 `v142` 已经重新拿到 `4/4`，但样本量仍很小，而且 sample3 还依赖一次 writer retry。
- 随机抽样规模仍偏小，现阶段只能说明局部质量较好，不能代表全量 10 万样本的真实通过率。
- 仍会偶发 planner/writer 漏出 shorthand、长度边界、最后几步桥接不自然的问题。
- 当前随机样本里已经看到 planner 一度想写出不在批准 route 里的关系，例如 `b, k, h are collinear`，只是后来被重试纠正了；这说明 route 漂移风险还在。
- `source audit` 目前在已抽样样本里基本没发现明显矛盾，但这只能说明“目前没撞到”，还不能等同于“全量源数据已经充分验证”。
- `ace2ae7` 针对 sample3 的 bridge-focus fallback 已经落代码，但还缺新的完整 live 结论来证明它是否把 `write 2` 压回 `write 1`。
