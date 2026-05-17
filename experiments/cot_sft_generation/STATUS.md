# CoT SFT Status

## 当前流程

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

## 实验经验

- 只靠 prompt 不够，必须靠 validator 和真实抽样回归一起收紧。
- 最常见的问题不是源样本自相矛盾，而是生成端偷懒：用 `symmetry`、`center`、`midpoint property` 这类高层 shorthand 跳步。
- 把推理拆成 `plan -> write` 后，质量明显比直接整段生成稳定。
- writer 最容易出现两类退化：重复前缀已说过的话，或在最后几步和真实 `goal_finish` 脱节。
- 小样本回放能修具体 bug，但是否真的变好，还是要看随机抽样。

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

- 当前未提交补丁对应的最新随机结果是 `v104`：随机 `4/4` 成功，`source_audit_issue_items=0`，`generation_audit_issue_items=0`。
  - 记录：`/tmp/cot_quality_test_run_v104_random4_artifacts_20260517_154443/summary.json`
  - 但这 `4` 条分别用了 `2, 2, 3, 2` 次样本级尝试，说明当前链路虽然通过，但仍在依赖 planner/writer 重试兜底。
- 后续针对 route-drift 的窄提示补丁在 `v106` 随机回归中也维持了 `4/4`，`source_audit_issue_items=0`，`generation_audit_issue_items=0`。
  - 记录：`/tmp/cot_quality_test_run_v106_random4_artifacts_20260517_162205/summary.json`
  - 这 `4` 条分别用了 `2, 3, 2, 2` 次样本级尝试，说明 route-drift 有所收紧，但整体仍未摆脱重试依赖。
- 历史上证据最好的随机结果是 `v92`：随机 `4/4` 成功，`source_audit_issue_items=0`，`generation_audit_issue_items=0`。
  - 记录：`/tmp/cot_quality_test_run_v92_random4_artifacts_20260516_065335/summary.json`
- 但 `v92` 也有明显局限：
  - 样本只有 `4` 条，说明“这 4 条都过了”，不说明大规模随机分布都稳定。
  - `v92` 之后仍出现了 `v99` 的 `3/4` 和 `v102` 的 `2/4`，说明链路还有回归风险，不是已经彻底收敛。
  - `v92` 只代表当前脚本在小规模随机抽样上的最好证据，不等于最终数据已经达到可直接全量生产的质量。
- `v89` 也已达到随机 `3/4`，说明到那时主链已经基本成型。
  - 记录：`/tmp/cot_quality_test_run_v89_random4_artifacts_20260516_053813/summary.json`
- 最近一次随机回归 `v102` 降到 `2/4`，暴露出两个具体问题：正文长度卡边界、`coordinate_hints` 残留 `midpoint property`。
  - 记录：`/tmp/cot_quality_test_run_v102_random4_artifacts_20260516_174559/summary.json`
- 当前未提交补丁已把这两个失败样本在 `v103` 定向回放中修到 `2/2`，但还缺新的随机样本证据。
  - 记录：`/tmp/cot_regression_v103_v102_failed_outputs_artifacts_20260516_194526/summary.json`

## 距离目标的差距

- 虽然 `v104` 已经把随机结果恢复到 `4/4`，但样本量仍很小，而且通过过程还依赖重试，不能直接视为已经稳定超过 `v92`。
- 随机抽样规模仍偏小，现阶段只能说明局部质量较好，不能代表全量 10 万样本的真实通过率。
- 仍会偶发 planner/writer 漏出 shorthand、长度边界、最后几步桥接不自然的问题。
- 当前随机样本里已经看到 planner 一度想写出不在批准 route 里的关系，例如 `b, k, h are collinear`，只是后来被重试纠正了；这说明 route 漂移风险还在。
- `source audit` 目前在已抽样样本里基本没发现明显矛盾，但这只能说明“目前没撞到”，还不能等同于“全量源数据已经充分验证”。
