# Current CoT SFT Design

本文档描述当前代码头部实现，也就是 [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py)、[audits.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/audits.py)、[geometry_text.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/geometry_text.py)、[prompt_builders.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/prompt_builders.py)、[writer_contracts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/writer_contracts.py)、[run_artifacts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/run_artifacts.py) 与 [semantic_review.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/semantic_review.py) 现在真正执行的流程；历史迭代和实验结论见 [STATUS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/STATUS.md) 与 [EXPERIMENT_LOG.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/EXPERIMENT_LOG.md)。字段表见 [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/ARTIFACT_SCHEMA.md)。

## 1. 总体目标

这条链路要做的是：

1. 生成期让教师模型看到完整记录，包括图片、题面、`<aux>`、proof、visible point 坐标等。
2. 导出时只保留学生未来能看到的输入，也就是图片和题面。
3. 最终 `thinking` 必须像是“看图后形成的辅助构造思路”，不能泄露 hidden proof 或坐标表来源。

## 2. 实际流水线

### 2.1 输入读取

每条样本会读取：

- 图片路径
- 公开题面
- 原始 `<aux>`
- hidden proof / hidden rest
- `point_coords_grid` / `grid_coord`
- visible formal premises

脚本随后把样本拆成两层：

- public input：图片 + 题面
- hidden supervisor context：`<aux>`、proof、坐标、visible premise summaries 等

### 2.2 `source audit`

这一步是脚本做的，不是靠人工肉眼。

用途：

- 检查图片、题面、`<aux>`、proof、坐标字段是否缺失或明显异常
- 发现问题时优先记到 artifacts，而不是为了通过率强行生成

当前抽样证据里，`source audit` 基本没有发现明确自相矛盾的源样本，但这只能说明“目前抽到的样本没撞到明显问题”，不能外推到全量。

### 2.3 `plan` 阶段

这一步调用 planner 模型，先产出结构化 JSON，而不是直接写整段 `thinking`。

`plan` 的原始必填字段如下：

1. `anchor_points`
   - 格式：`list[str]`
   - 长度：`3` 或 `4`
   - 含义：最终会被脚本打上 `<point>...<coord>...</coord>` 标签的可见锚点。

2. `anchor_relation`
   - 格式：`str`
   - 含义：围绕 `anchor_points` 的一句可见关系，用于开场定向。

3. `figure_overview`
   - 格式：`str`
   - 含义：锚点之外的整图概览，必须把注意力扩展到和目标相关的其他可见点或子结构。

4. `coordinate_relations`
   - 格式：`list[str]`
   - 长度：`2` 到 `3`
   - 含义：由 visible-point 坐标支持的具体关系检查。
   - 要求：必须 grounded 在脚本内部算出的 coordinate candidates 上，不能随意发明。

5. `visible_relations`
   - 格式：`list[str]`
   - 长度：`2` 到 `4`
   - 含义：题面里已有、后续桥接应该主动复用的可见 formal relations。

6. `coordinate_hints`
   - 格式：`str`
   - 含义：把 `coordinate_relations` 转成自然语言提示。
   - 要求：不能说 `coordinate table`，也不能用 `symmetry`、`midpoint property` 这种偷懒话术。

7. `goal_bottleneck`
   - 格式：`str`
   - 含义：当前图到 visible goal 之间真正缺的那一步。

8. `helper_idea`
   - 格式：`str`
   - 含义：需要什么辅助机制，例如等长转移、角对齐、比例桥接。
   - 要求：还不能提前说出新点名字。

9. `construction`
   - 格式：`str`
   - 含义：正式引入 aux。
   - 多点 aux 时：必须写出 staged strategy，例如 `first ... then ...`。

10. `aux_direct_relations`
    - 格式：`list[str]`
    - 长度：`1` 到 `3`
    - 含义：构造一完成就直接成立的局部后果。
    - 要求：必须是 immediate consequences，不能跳进旧图深处。

11. `bridge_steps`
    - 格式：`list[object]`
    - 长度：`2` 到 `4`
    - 每个对象至少包含：
      - `relation: str`
      - `depends_on: list[str]`
      - `why_it_helps: str`
    - 含义：把 aux 的直接后果重新接回旧图，并逐步推到目标前一跳。

12. `goal_finish`
    - 格式：`str`
    - 含义：最后必须明确落到的 goal-side relation。

### 2.4 `plan` 校验、规范化和脚本补全

这一步也是脚本做的。

主要事情有：

1. 基础 schema 校验
   - 字段是否齐全
   - `anchor_points` 数量是否为 `3/4`
   - `coordinate_relations` 是否为 `2/3`
   - `bridge_steps` 是否为 `2` 到 `4`

2. 文本约束
   - 禁止 proof-engine 痕迹
   - 禁止新点在 `construction` 之前泄露
   - 禁止 `square-like`、`parallelogram`、`common center`、`symmetry`、`midpoint property` 等 shorthand

3. route grounding
   - `coordinate_relations` 必须贴合 hidden coordinate candidates
   - `bridge_steps` 必须尽量贴合 hidden proof guidance 给出的真实 bridge / finish 路线

4. 脚本自动补充的派生字段
   - `bridge_relations`
   - `coverage_targets`
   - 每个 `bridge_steps[*]` 上的：
     - `next_target_relation`
     - `next_target_purpose`
     - `required_supports`
     - `min_support_mentions`
     - `focus_points`
     - `focus_hint`

### 2.5 `coverage_targets` 是什么

这是脚本根据 `figure_overview`、`visible_relations`、`bridge_steps`、`goal_finish` 自动派生出来的全图覆盖目标。

主要字段有：

1. `goal_points`
   - 从 visible goal 里抽出的目标点。

2. `goal_points_outside_anchors`
   - goal 中那些不属于 anchor 的点。

3. `non_anchor_points`
   - 在全图中更值得正文继续跟踪的非锚点。

4. `opening_focus_points`
   - writer 第一正文句应该优先点到的非锚点区域。

5. `bridge_focus_points`
   - writer 第二正文句应该优先接回的更大可见区域。

6. `focus_relations`
   - 对应这些点的关键关系摘要。

7. `opening_sentence_hint`
   - 第一正文句的局部落点提示。

8. `helper_sentence_hint`
   - 第二正文句的局部落点提示。

9. `reminder`
   - 给 writer 的简短提醒，要求不要只围着 anchor frame 打转。

注意：现在仍然只给 `3-4` 个 `anchor_points` 打标签，不等于只看 `3-4` 个点。全图覆盖要求主要由 `figure_overview`、`visible_relations`、`coverage_targets`、`bridge_steps[*].focus_points` 来补。

### 2.6 `bridge_steps[*].focus_points` 是什么

这是脚本在 bridge 级别再加的一层局部 coverage contract。

来源：

- 当前 step 的 `relation`
- 下一跳 `next_target_relation`
- 当前 step 的 `required_supports`
- 当前 step 的 `depends_on`
- 全局 `goal_points` 和 `non_anchor_points`

用途：

- writer 在写该 bridge 句时，必须显式提到这些点里的至少一个
- 避免 bridge 句只用 anchor 语言空转

最新补丁 `ace2ae7` 进一步放宽了这里的 fallback：

- 如果非 anchor 的 `focus_points` 太窄，脚本会回退到 support-side points，并允许把 anchor 侧支持点补进来
- 目的：修复 sample3 首条 bridge 句因为 contract 过窄而掉到 `write 2`

### 2.7 writer 阶段

这一步也是模型调用，但已经不再把整份大 plan 原样塞给 writer。

当前 writer 看到的是：

1. `Injected Prefix Block`
   - 由脚本自动拼接，包含：
     - anchor sentence
     - figure overview sentence
     - coordinate hint sentence
     - visible relation sentence

2. `Approved Writer Handoff`
   - 这是当前紧凑版 plan-to-write payload
   - 只保留真正需要 writer 消化的字段：
     - `goal_bottleneck`
     - `helper_idea`
     - `construction`
     - `aux_direct_relations`
     - 精简版 `bridge_steps`
     - `goal_finish`
     - `opening_focus_points`
     - `bridge_focus_points`
     - `opening_sentence_hint`
     - `helper_sentence_hint`

3. `Non-Skippable Bridge Checklist`
   - 脚本把每个 bridge step 重新列成一句一句的硬约束
   - 每条通常会要求：
     - 本 step 单独成句
     - 点出至少一个 `required_supports`
     - 点出至少一个 `focus_points`
     - 说明这句解锁什么 `unlock_purpose`

4. `preferred_sentence_shell`
   - 脚本会为每个 bridge step 生成一句推荐壳子
   - 典型形式：
     - `Because <support>, <approved relation>, and <unlock purpose>.`
   - writer 可以自然化，但不能偏离太远

### 2.8 writer 输出后脚本终检

writer 只输出 body 纯文本，不允许自己输出 `<thinking>`、`<point>`、`<coord>` 标签。

脚本会检查：

1. 格式
   - 是否只有正文
   - 长度是否在预算内
   - 是否出现第一人称

2. 与 prefix 的关系
   - 不能大面积重复 injected prefix
   - 第一正文句必须落到 `opening_focus_points`
   - 第二正文句必须落到 `bridge_focus_points`

3. bridge 合同是否逐句落实
   - 每个 `bridge_steps[i].relation` 必须按顺序出现
   - 对应句子必须提到足够的 `required_supports`
   - 对应句子必须提到至少一个 `focus_points`
   - 最后必须显式写出 `goal_finish`

4. 泄露与偷懒表达
   - 禁止 hidden proof 痕迹
   - 禁止 `symmetry`、`midpoint property`、`common center`、`square-like` 等 shorthand

### 2.9 终组装

writer body 通过后，脚本才会：

1. 把 prefix 和 body 拼成最终 `<thinking>...</thinking>`
2. 把原始 `<aux>` 原样带出
3. 导出：
   - `thinking`
   - `aux`
   - `output = thinking + "\\n" + aux`

### 2.10 run artifacts 层

当前 artifacts/schema 相关逻辑已经从主流程里抽出一层，放到 [run_artifacts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/run_artifacts.py) 与 [semantic_review.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/semantic_review.py)。另外，`source audit` / `generation audit`、visible premise summaries 与句级 relation 命中这层公共 helper 现在放到 [audits.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/audits.py)，几何文本解析、关系归一化、goal/aux 拆解以及 hidden coordinate candidate / hint / guidance 这层公共 helper 现在放到 [geometry_text.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/geometry_text.py)，planner / writer prompt 与 retry feedback 这层长文本协议现在放到 [prompt_builders.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/prompt_builders.py)，而 writer 合同、coverage target、prefix 组装这层公共 helper 现在放到 [writer_contracts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/writer_contracts.py)。

它负责的不是几何推理，而是 run 级数据结构：

1. 数据集输出条目
   - `instruction`
   - `input`
   - `thinking`
   - `aux`
   - `output`
   - `image_path`

2. `run_config.json`
   - 每次 run 开始时先落：
     - `artifact_schema_version`
     - `git_commit` / `git_branch` / `git_dirty`
     - `resolved_input_jsonl`
     - `input_jsonl_sha256`
     - CLI 参数和 API 配置
   - 目的：
     - 让后续 Codex 会话能直接知道某个 artifacts 目录是基于哪份代码和哪份输入生成的

3. `sampled_inputs.jsonl`
   - 仅 `-v` 时导出
   - 记录本轮实际抽中的：
     - `sample_order`
     - `input_index`
     - `image_path`
     - 原始可见题面
     - 原始 aux
     - `point_coords_grid`
   - 目的：
     - 让回放样本和复现抽样不再依赖聊天记录或 `/tmp` 临时笔记

4. `item_record`
   - 样本级完整记录
   - 包括：
     - public problem
     - aux
     - `goal_type`
     - `aux_type`
     - hidden rest
     - source audit
     - generation audit
     - plan / write prompt
     - plan / write 输出
     - final thinking
     - `surface_pass`

5. `item_audits.jsonl`
   - 当前每条样本都会导出：
     - `sample_order`
     - `input_index`
     - `goal_type`
     - `aux_type`
     - `source_audit`
     - `generation_audit`
     - `surface_pass`
   - 为了兼容旧分析脚本，仍保留 `success` 字段，但长期应优先读 `surface_pass`

6. `semantic_audits.jsonl`
   - 当前生成阶段不会自动给出 `semantic_pass`
   - 但脚本已经会为每条样本写出一条语义审读占位记录，包含：
     - `goal_type`
     - `aux_type`
     - `surface_pass`
     - `semantic_pass: null`
     - `manual_critical_error: null`
     - `review_status: "pending"`
     - `review_checklist_version`
     - `issue_codes`
     - `issues`
     - `notes`
   - 这一步的目的，是把“语义审读还没做”也显式落盘，而不是只留在对话记忆里

7. `summary.json`
   - 当前仍保留旧的兼容字段：
     - `successful_items`
     - `failed_items`
   - 同时新增更明确的分层字段：
     - `artifact_schema_version`
     - `surface_pass_items`
     - `surface_fail_items`
     - `surface_pass_rate`
     - `avg_attempts_used`
     - `semantic_reviewed_items`
     - `semantic_pass_items`
     - `semantic_fail_items`
     - `semantic_pass_rate`
     - `manual_critical_error_items`
     - `manual_critical_error_rate`
     - `semantic_review_status`
   - 因为当前 run 结束时默认还没做人工/Codex 审读，所以大多数 run 的 `semantic_review_status` 会是 `not_reviewed`

8. `semantic_review.py`
   - 用途不是重新生成数据，而是对已落盘的语义审读结果做一致性校验和汇总刷新。
   - 它会：
     - 校验 `semantic_audits.jsonl` 与 `item_audits.jsonl` 行数和 `(sample_order, input_index)` 是否对齐
     - 规范化 `semantic_pass` / `review_status` / `issue_codes` / `issues`
     - 刷新 `summary.json` 中的 `semantic_review_status`、`semantic_pass_rate`、`manual_critical_error_items`、`manual_critical_error_rate`
   - 推荐在人工/Codex 回填完 `semantic_audits.jsonl` 后运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --write-summary
```

9. 固定 benchmark
   - 当前仓库内已经有一组固定回归基线：
     - [benchmarks/fixed_v104sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl)
     - [benchmarks/fixed_v104sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json)
     - [benchmarks/stratified_v1_12sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_input.jsonl)
     - [benchmarks/stratified_v1_12sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_manifest.json)
   - 其用途是给长期回归和语义复核提供一个不会因 `/tmp` 被清空而消失的稳定入口。
   - 更细说明见 [benchmarks/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/README.md)。

10. `audits.py`
   - 负责：
     - `source audit`
     - `generation audit`
     - visible formal fact parsing
     - bridge sentence relation matching
   - 目的：
     - 把样本审计和句级 relation 命中逻辑从主流程编排层剥离出来
     - 让后续单独改 audit 规则的人，不必再同时触碰 planner / writer 调用编排

11. `geometry_text.py`
   - 负责：
     - visible goal / public problem 文本拆解
     - aux 子句解析
     - formal relation 到自然语言 relation 的归一化
     - relation keyword / point mention / semantic match 这些跨阶段公用 helper
   - 目的：
     - 避免 `generate_cot_sft.py` 同时承担“主流程编排”和“底层文本规则库”两类职责
     - 为 `prompt_builders.py`、`writer_contracts.py` 和后续 validator 拆分提供稳定底层

12. `writer_contracts.py`
   - 负责：
     - `coverage_targets`
     - bridge step `focus_points`
     - writer handoff / bridge checklist / sentence blueprint
     - injected prefix 组装
   - 目的：
     - 把“writer 约束协议”从主脚本编排层剥离出来
     - 让后续只改 writer 合同的人，不必再同时触碰主流程和 validator 大块逻辑

13. `prompt_builders.py`
   - 负责：
     - planner prompt
     - writer prompt
     - planner / writer retry feedback
     - hidden supervisor payload 组装
   - 目的：
     - 把超长 prompt 文本和重试提示从主脚本编排层剥离出来
     - 让 prompt 调整和 validator / audit 调整可以分别维护、分别测试

## 3. 中间哪些步骤是通过脚本做的

是的，中间大部分关键控制都已经转成脚本，不只是 prompt。

脚本负责：

- `source audit`
- planner JSON 校验
- route canonicalization
- hidden coordinate candidate grounding
- hidden proof route grounding
- `coverage_targets` 派生
- bridge-step `focus_points` / `required_supports` / `preferred_sentence_shell` 派生
- injected prefix 注入
- writer body 终检
- final `<thinking>` 组装
- run artifacts schema 构造
- `surface_pass` / `semantic_audits` 占位落盘
- `semantic_review.py` 对语义审读结果的对齐检查和 summary 刷新

模型主要负责两件事：

- 先给出结构化 `plan`
- 再在批准约束下写出正文 body

## 4. `3/4`、`2/4`、`4/4` 是什么意思

这是实验记录里的样本级通过数，不是某个字段格式。

例如：

- `4/4`：本次测试抽了 4 条，4 条都通过终检
- `3/4`：抽了 4 条，通过 3 条
- `2/4`：抽了 4 条，通过 2 条

这类数字只说明该次小样本回归的结果，不能直接当成全量真实通过率。

## 5. 当前设计相对旧版本的关键变化

1. 从“直接整段写 `thinking`”转成了 `plan -> write` 两阶段。
2. 从“只管 anchor 定向”扩展到 `coverage_targets` 和 step-level `focus_points`。
3. 从“大而重复的 writer prompt”压缩成 `Approved Writer Handoff`。
4. 给 writer 加了 `Non-Skippable Bridge Checklist` 和 `preferred_sentence_shell`。
5. 把很多历史上反复出问题的 shorthand、route drift、prefix 重复、bridge 跳步都收进脚本校验。

## 6. 当前还没彻底解决的问题

1. 虽然当前头部设计已经在固定回归上拿到新的 `4/4`，但样本数仍然小。
2. sample3 一类样本之前仍会掉到 `write 2`，最新 `ace2ae7` 是针对这个点的补丁，但还缺新的完整 live 结论。
3. 全量 10 万样本的真实通过率、重试成本和长尾失败分布还没有被充分测过。
4. 虽然代码已经开始显式落 `semantic_audits.jsonl` 和 `surface_pass_rate`，并支持通过 `semantic_review.py` 刷新 run 级汇总，但真正的 `semantic_pass` 仍然要靠后续人工/Codex 审读回填；当前还没有自动 `critic` 阶段。
5. 当前固定 benchmark 已经补到一组最小 `4` 条回放集和一组 `12` 条 `goal_type x aux_type` 分层集，但不同 `aux_shape` 和更长尾失败模式仍然覆盖不足。
