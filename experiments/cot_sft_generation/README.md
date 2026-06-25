# CoT SFT Generation

这个实验目录现在用于生成“带 CoT 的辅助构造数据”。核心约束是两层分离：

1. 生成数据时，教师模型可以看到数据中的完整信息，包括：
   - 图片
   - `llm_input_renamed`
   - `llm_output_renamed` 中的 `<aux>` 与后续证明
   - `point_coords_grid` / `grid_coord`
   - 其他源字段
2. 最终导出的训练样本只保留学生模型在训练和评估时应当看到的输入：
   - `backtrace_text_v1`：题目文本，writer-only backtrace 合同
   - `insight_image_v1`：图片 + 题目文本
   - `insight_text_v1`：题目文本

因此，这个脚本做的是“full-information teacher -> visible-only student target”的数据蒸馏，而不是把完整证明直接暴露给训练模型。

## 文档导航

- [docs/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/README.md)：新的文档总入口，先按用途看文档，不要直接在平铺文件里找。
- [docs/DOC_BOUNDARIES.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/DOC_BOUNDARIES.md)：先看这个，分清楚 agent 能改什么、不能改什么。
- [docs/immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)：不可改的数据质量要求镜像。
- [docs/current/BACKTRACE_TEXT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/BACKTRACE_TEXT_V1_MAINLINE.md)：默认主线，先看这份。
- [docs/current/INSIGHT_IMAGE_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_IMAGE_V1_MAINLINE.md)：image sibling mainline。
- [docs/current/INSIGHT_TEXT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_TEXT_V1_MAINLINE.md)：text-only sibling mainline。
- [docs/current/DOSSIER_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/DOSSIER_V1_MAINLINE.md)：legacy / benchmark 路线说明。
- [benchmarks/quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)：当前主线默认使用的 review-oriented benchmark。

## 目录结构

当前目录按四层来理解：

- `README.md`
  - 入口说明，只回答“这个实验要做什么、当前默认链路是什么、从哪里开始看”。
- `docs/`
  - 文档总入口；内部再分成 `immutable`、`current`、`reference`、`maintenance`、`history`。
- `benchmarks/`
  - 固定 benchmark 输入、manifest，以及当前主线 benchmark 包。
- `generated/`
  - 已落盘的真实 run 输出和 artifacts。
- `core/`
  - 通用实现模块；根目录同名 `.py` 文件现在只保留兼容入口，方便旧 `import` 路径和脚本继续工作。

根目录代码文件现在只保留入口与兼容层，按职责划分：

- `generate_cot_sft.py`
  - 主入口和编排。
- `audits.py`
  - `core/audits.py` 的兼容 re-export；source/generation audit 与句级关系检查的真实实现放在 `core/`。
- `geometry_text.py`
  - `core/geometry_text.py` 的兼容 re-export；几何文本归一化、relation parsing、aux helper 的真实实现放在 `core/`。
- `prompt_builders.py`
  - `core/prompt_builders.py` 的兼容 re-export；planner / critic / writer prompt 与 retry feedback 的真实实现放在 `core/`。
- `run_artifacts.py`
  - `core/run_artifacts.py` 的兼容 re-export；run 级和 item 级 artifacts 组装的真实实现放在 `core/`。
- `semantic_review.py`
  - 语义审读队列、汇总与 summary 刷新。
- `writer_contracts.py`
  - `core/writer_contracts.py` 的兼容 re-export；writer handoff、坐标片段和正文合同的真实实现放在 `core/`。
- `maintenance_smoke_check.py` / `prepare_metadata.py` / `replay_artifact_checks.py`
  - 维护、输入准备和 artifact 回放工具。

## 默认数据源

默认输入文件已经切换为：

```text
datasets/20260512/geometry_clauses10_samples100k_inverted_fl_points_only.jsonl
```

如果不传 `-i/--input`，脚本会直接使用这个文件。

## 固定基线

长期迭代时，不应只依赖 `/tmp` 里的临时回归文件。当前已经落仓的固定基线见 [benchmarks/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/README.md)。

当前主线 benchmark 是：

- [benchmarks/quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)
- [benchmarks/quality_review_v1/quality_review_v1_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl)
- [benchmarks/quality_review_v1/quality_review_v1_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_manifest.json)

保留的 legacy support packs 是：

- [benchmarks/fixed_v104sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl)
- [benchmarks/fixed_v104sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json)
- [benchmarks/stratified_v1_12sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_input.jsonl)
- [benchmarks/stratified_v1_12sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_manifest.json)

它用于：

- 提供当前主线的 review-oriented 固定回归入口
- 保留历史最小集和 lineage set，方便回放旧证据
- 把 benchmark 使用重新绑定到数据质量要求的人审，而不是只看脚本通过率

## 生成目标

每条输出样本包含两部分：

- `thinking`：模型写出的 `<thinking>...</thinking>`，内容必须看起来只能依赖当前 style 允许的可见输入得到，不能泄露 `<problem>...</problem>` 之后的信息
- `aux`：直接保留源数据中的原始 `<aux>...</aux>`

此外还会保留一个兼容字段：

- `output`：`thinking + "\n" + aux`

## 数据质量目标

当前这条生成链路的目标，不是只产出“看起来像 CoT”的文本，而是产出真正可用于训练辅助构造模型的高质量样本。具体要求如下：

1. 可见输入边界必须严格
   - 最终训练样本暴露给学生模型的只有当前 style 对应的可见输入。
   - `insight_image_v1` 暴露图片和题目文本。
   - `insight_text_v1` 只暴露题目文本。
   - `backtrace_text_v1` 只暴露题目文本。
   - `thinking` 不得泄露 `<problem>...</problem>` 之后的 hidden proof、proof IDs、规则名、数值检查字段、坐标表来源等生成期信息。

2. `thinking` 必须像是从图和题面观察得到的
   - 文本应当从可见图形结构出发，而不是像在复述 formal proof。
   - 允许生成期教师模型使用完整记录做监督，但最终导出的 `thinking` 必须读起来像“观察当前可见输入后得到的构造与验证思路”。

3. 不能只盯 2-3 个点，要对整张图有完整认识
   - 少量 tagged anchor points 只负责给图定向。
   - `thinking` 还必须覆盖与目标有关的其他可见点、子结构、平行线、圆、等腰/等边/中点/共线等更广义的可见配置。
   - 如果正文只围绕开头 2-3 个点打转，而忽略后续真正参与目标的点或子图，这类样本不算高质量。

4. 坐标应当服务于几何关系判断，而不是只做标签
   - 生成期可以使用 `point_coords_grid` / `grid_coord` 做内部 sanity check。
   - 坐标的作用应当是帮助教师模型确认哪些平行、垂直、等长、中点、共线等关系值得进一步追踪，而且这些判断不应只围着少数点打转。
   - 当前实现允许 `insight_image_v1` 的最终 `thinking` 显式写出可见点坐标、向量/长度/面积残差这类 plain-text 计算，但这些计算必须服务于后续 bridge 或 goal，而不是装饰性堆算式。
   - `insight_text_v1` 的 planner、writer、validation 和最终训练样本都不应出现图片或点坐标输入，也不应在正文里泄露坐标。
   - `backtrace_text_v1` 同样是 text-only；writer prompt、validation、artifacts 和最终训练样本都不应出现图片或点坐标输入。
   - 文本里必须区分：
     - 题面直接给出的 visible text facts
     - 从图片和可见点坐标中观察或计算出的 image / coordinate facts（仅 `insight_image_v1`）

5. 需要包含从提出 aux 到解答出 goal 的完整逻辑
   - 高质量样本不能只说明“为什么要加这个点”，还要继续写清楚加点之后的关键关系如何逐步推进到最终结论。
   - 文本应明确说明：
     - aux 的直接后果是什么
     - 这些后果如何接回原图已有结构
     - 最后如何落到 goal 对应的 angle / ratio / congruence / similarity / contradiction
   - 对 `eqratio` 目标，应明确写出相关线段之间的比例链如何闭环到目标。
   - 对 `eqangle` 目标，应明确写出角关系如何一步步转化到目标角。
   - 对 `simtri` / `contri` 目标，应明确写出建立了哪些边角对应，并如何由此得到最终的相似或全等。
   - 生成期可参考 hidden proof milestones，但最终文本不能照抄 proof engine 语句；高质量样本应尽量在后半段对齐真实 proof 的关键中间关系，尤其是接近 goal 的最后 2-4 步桥接逻辑。
   - 如果文本只说“这样会有帮助”或“这样就可以做相似”，没有继续写出中间桥接步骤，或者和真实 proof 的收尾完全脱节，那样本仍然不合格。

6. 单点 aux 与多点 aux 都要真正可解
   - 对单点 aux，文本应解释这个点为什么是必要桥梁，以及它引出的第一组关键关系。
   - 对多点 aux，文本必须显式说明 staged strategy，例如 `first ... then ... finally ...`，并解释每一步解锁的几何关系。
   - 多点构造不能只是把所有新点一次性报出来，而不说明每个点为什么存在。

## 迭代与审计要求

下面这些要求更偏向生成流程与审计流程，用来保证上面的数据质量目标能够被持续验证。

1. 发现源样本异常时应优先标记，而不是硬写
   - 如果 visible problem、aux、proof、point coordinates 之间出现明显冲突，应优先在审计中记录或过滤。
   - 不要为了提高通过率，强行生成一条看似流畅但实际上与源样本不一致的 `thinking`。
   - 当前脚本默认会对每条输入做 source audit，并把发现的问题记录到 artifacts；除非是缺图这类致命错误，否则会先记录，不会直接假设源样本一定有问题并强行过滤。

2. 验收要靠真实抽样，而不是只靠 prompt 设计
   - 每次修改 prompt、schema、validator 或拼接策略后，都应做真实随机抽样审计。
   - 审计时不仅看通过率，还要人工检查：
     - 坐标标签是否正确
     - 文本是否真的覆盖全图
     - aux 后是否有有效验证链
     - 末段是否真正 bridge 到 goal
     - 多点 aux 是否写出了 staged strategy

## 迭代规范流程

为了避免把“脚本没报错”误当成“数据已经可用”，后续所有迭代都应区分两类通过：

1. `surface_pass`
   - 含义：样本通过脚本检查。
   - 作用：说明格式、泄露控制、坐标标签、route 顺序、prefix 重复等表层约束暂时成立。
   - 非作用：不能单独证明这条 `thinking` 的几何语义已经可靠，更不能单独证明这轮改动提升了数据质量。

2. `semantic_pass`
   - 含义：结合原题、图片、`aux` 和最终 `thinking` 做人工或 Codex 审读后，确认文本确实满足上面的数据质量目标。
   - 最低检查项：
     - 文本是否真的像从图和题面观察得到
     - 坐标/视觉 cue 是否真正进入推理链
     - 文本是否真的从 aux 的直接后果一路 bridge 到 goal-side finish
     - 每个 bridge relation 是否真的由前文 support 推出
     - 最后 2 到 4 步是否真实落到目标

后续每轮迭代都应按下面的顺序执行，而不是只看一次脚本回归：

1. 明确本轮改动想修什么
   - 例如：修 route drift、修最后两步脱节、修 ratio 链闭环、修多点 aux staged strategy。
   - 不要在没有明确失败模式的情况下同时大改 prompt、validator、writer handoff 和长度预算。

2. 固定失败样本脚本回归
   - 先在已知失败样本或固定基准样本上跑脚本回归。
   - 目标：确认没有引入明显格式回退、泄露回退、prefix 重复回退或 route 顺序回退。

3. 小规模随机脚本回归
   - 再跑一小批真实随机样本。
   - 目标：确认改动不是只修了固定回放样本，而是没有立刻在其他样本上回归。

4. 定向 Codex 人审
   - 对 5 到 10 条与本轮改动强相关的样本做人工/Codex 审读。
   - 目标：直接回答“这次改动想修的问题，在真实文本里是不是真的被修了”。

5. 随机 Codex 人审
   - 再对 15 到 20 条随机样本做审读，最好覆盖不同 goal type 和 aux type。
   - 目标：确认没有新的高频语义错误被 prompt 或 validator 掩盖。

6. 分开记录两类结果
   - `surface_pass_rate`
   - `semantic_pass_rate`
   - `manual_critical_error_rate`
   - `avg_attempts_used`
   - 任何实验记录都不应只写 `4/4`、`generation_audit_issue_items=0`，而不说明是否做过语义审读。

7. 只有双重通过，才算本轮改动有效
   - 脚本回归稳定，只说明“表层约束没有明显坏掉”。
   - 只有脚本回归稳定且 Codex 人审明确改善，才能把这轮改动记为“数据质量提升证据”。

补充要求：

- 固定回归优先使用仓库内 benchmark，而不是重新在 `/tmp` 手工挑样本。
- 迭代阶段建议先运行 `semantic_review.py --print-pending --surface-pass-only`，只把已经 `surface_pass` 的样本送去 Codex 审读；完成人工/Codex 审读后，再回填 `semantic_audits.jsonl` 并运行 `semantic_review.py --write-summary` 刷新 `summary.json`。
- `semantic_audits.jsonl` 的字段填写和 `issue_codes` 口径以 [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md) 为准。
- schema 细节和字段解释以 [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/ARTIFACT_SCHEMA.md) 为准。

## 脚本检测与 Codex 人审的分工

两者都需要，不能互相替代。

- 脚本检测适合做：
  - 格式、长度、标签、泄露、prefix 重复、route 顺序、source audit、运行级统计
  - 大规模预筛和批量回归

- Codex 人审适合做：
  - 结合图片和题面判断文本是否自然可信
  - 判断某个 support 是否真的推出某个 bridge relation
  - 判断最后几步是否真实落到 goal
  - 判断“覆盖全图”是否只是提到了点，还是确实进入了推理链

因此，日常内环迭代可以先靠脚本筛选，但任何声称“质量提升”或“可以批量生产”的结论，都必须经过 Codex 人审确认。

## 当前生成框架

如果你接下来明确要以新链路为主线继续做迭代，请先读 [INSIGHT_IMAGE_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_IMAGE_V1_MAINLINE.md)；如果你明确要做 text-only 合同，再补读 [INSIGHT_TEXT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_TEXT_V1_MAINLINE.md)。下面这节描述的是当前实现本身，而不是“下个会话最该先做什么”。

先区分两层文档角色：

- `docs/immutable/` 代表最终质量标准，不随当前实验主线收窄而改变。
- `docs/current/` 代表当前默认实现与阶段性策略，其中 `backtrace_text_v1` 是默认 text-only writer-only backtrace mainline，`insight_image_v1` 是 image sibling mainline，`insight_text_v1` 是 text-only sibling mainline，`dossier_v1` 是 legacy / benchmark 路线。

当前默认主链已经切到 `backtrace_text_v1`，并保留显式 sibling 变体：

- 默认：`--generation-style backtrace_text_v1`
- image sibling：`--generation-style insight_image_v1`
- text-only sibling：`--generation-style insight_text_v1`
- legacy / benchmark：`--generation-style dossier_v1`
- 兼容 fallback：`--generation-style model_evidence_legacy`

`backtrace_text_v1` 的核心思想是：阶段性把默认主线收窄到 staged visible backtrace，而不是默认要求完整 closure。这里的“收窄”只针对当前主线，不重写最终质量目标；[DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md) 中第 5 点仍然是长期标准。

`backtrace_text_v1` 不走 planner，只做 `Proof DAG -> BacktraceSlots -> WriterHandoff -> writer -> hard checks`，要求正文按 staged visible backtrace 的顺序写出：从 goal 开始，逐层说明当前 claim、已有 visible support、仍需的 visible subgoal，直到 visible route 触到 aux boundary，再引入 aux。

同时要避免两个误读：

- 这不是要求压缩所有前段 reasoning。只要不泄露 hidden source，`pre-aux` 的 visible-only reasoning 仍然可以更丰富。
- 这也不是在两个 variant 上都允许显式使用 visible-point coordinates。当前 `insight_image_v1` 允许并且在需要时可以鼓励把可见点坐标用于前段 visible-only reasoning；`insight_text_v1` 和 `backtrace_text_v1` 则要求 generation、validation、artifacts 和最终训练样本都避免图片与点坐标输入。

1. `source audit`
   - 先检查图片、题面、`<aux>`、proof、坐标字段是否缺失或明显冲突。
   - 对 `insight_image_v1`，图片路径和 visible coordinates 仍是常规 source audit 输入。
   - 对 `insight_text_v1`，不会再把缺图或缺 visible coordinates 当作 source-audit 硬问题。
   - 对 `backtrace_text_v1`，同样不会再把缺图或缺 visible coordinates 当作 source-audit 硬问题。
   - 发现异常先记录，不为了通过率强行硬写。

2. `insight slots + plan`
   - 脚本先从 proof DAG 提取 `InsightSlots`，再让 planner 产出结构化 `InsightPlan`。
   - 当前默认 plan 只围绕 visible facts、image scan、goal gap、required helper effect、aux construction、aux selection reason，以及可选的 `stage_order` / `bonus_post_aux_tail`。
   - planner 不负责输出 full closure chain；`post-aux` 的完整收尾也不是当前默认合同。
   - `insight_image_v1` 的 planner 仍会看到图片和 raw visible coordinates。
   - `insight_text_v1` 的 planner 改为 text-only，不接收 `image_url`，也不接收 raw visible coordinates。

3. 脚本兜底与规范化
   - 对 `image_scan` / `required_aux_effect` 等字段做自然语言归一化。
   - 当 validator 需要检查 `<aux>` 的直接后果时，脚本会本地临时现算，但不把这些内容扩展成当前默认 writer 合同。
   - 如果 planner 失败，当前 insight family 仍允许回退到 scripted insight plan；如果 writer 校验失败，则该样本直接失败，不再自动降级到 `dossier_v1`。
   - `insight_slots` 和 `insight_plan_parsed` 会保存到 artifacts，方便 replay 与审计。

4. `write`
   - writer 从批准后的 `InsightPlan` 写出完整 `thinking`。
   - 当前默认重点是 visible gap、helper effect、aux selection reason，以及非常短的 post-aux local tail。
   - richer `pre-aux` visible-only reasoning 仍然允许。
   - `insight_image_v1` 允许显式坐标，但只应服务于可见结构判断，且不能泄露 hidden 坐标来源。
   - `insight_text_v1` 的 writer prompt 和最终正文都不应出现图片或坐标输入。

5. 终检、artifact 与语义审读
   - writer 正文通过脚本终检后，才会组装成最终 `<thinking>...</thinking>`。
   - 终检会检查：
     - 长度和格式
     - shorthand / 泄露
     - inline visible-point coordinates 是否与源数据一致（仅 `insight_image_v1`）
     - 当前 `InsightPlan` 是否与正文一致
     - multi-point aux 的 staged strategy 是否在需要时被保留
   - run artifacts 里会显式记录：
     - `generation_style`
     - `surface_pass`
     - `semantic_audits.jsonl`
     - `summary.json` 里的 `semantic_review_status` / `semantic_pass_rate`

## 最新实测（2026-05-20）

下面这组数字是 `dossier_v1` legacy benchmark 的历史记录，不应当被误读为当前默认 insight family 合同本身：

- 默认模型 `qwen/qwen2.5-vl-72b-instruct`
- 基准：`benchmarks/stratified_v1_12sample_input.jsonl` 中分层抽样 `4` 条
- 真实 run：
  - `generated/dossier_v1_stratified4_rerun4_20260520.jsonl`
  - `generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/summary.json`
- 结果：
  - `surface_pass`: `3/4`
  - 对这 `3` 条 `surface_pass` 样本做了人工/Codex 审读后：
    - `semantic_pass`: `0/3`
    - `manual_critical_error`: `3/3`
- 当前结论：
  - `dossier_v1` 端到端已经跑通，且比最初的 `0/4` 有明显 surface 改善。
  - 但以 README 的数据质量目标衡量，默认 `qwen` 这轮输出仍然不能直接用于批量生产，主要问题还是 bridge 语义不成立、goal 尾段未真实闭环。

更细的字段说明和脚本过程见 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)。

## 泄露控制

最终 `thinking` 会做程序化校验，默认会拒绝以下内容：

- `<aux>` / `<proof>` / `<numerical_check>`
- `[012]` 这类步骤编号
- `AR` / `r63` / `a01` 这类证明引擎痕迹
- `sameclock` / `simtri` / `simtrir` 这类未来证明或引擎术语
- “hidden reference / supervisor / given aux / rest of the proof” 等元话术
- `coordinate table` 这类直接暴露 hidden 坐标来源的表述
- LaTeX / `$...$` 数学包裹
- `this point is crucial` / `necessary relationships` / `help establish` 这类低信息密度套话

同时会校验：

- 输出必须是且仅是一个 `<thinking>...</thinking>` 块
- `thinking` 长度足够；复杂题的总长度预算会按 plan 复杂度适度放宽
- 如果正文显式写了 `a=(x,y)` 这类可见点坐标，脚本会校验这些坐标必须与源数据中的 `point_coords_grid` / `grid_coord` 完全一致
- `plan` 中的构造语义必须与 hidden aux 对齐，例如：
  - `midp` 必须明确 midpoint
  - `cyclic` 必须明确 circle / circumcircle / cyclic
  - `cong` 必须明确 equal / congruent / equidistant
- 当前 `insight_image_v1` 允许显式使用 visible-point coordinates，但这些坐标句必须服务于 visible-only reasoning，而不是装饰性标签或 hidden route 的替代品
- 当前 `insight_text_v1` 不允许 planner、writer 或最终 `thinking` 泄露图片和 visible-point coordinates 输入
- 当前 insight family 会检查 `goal_gap_text` / `required_aux_effect` / `aux_selection_reason` 是否保持 insight-first 且与批准后的 `InsightPlan` 对齐
- 当前 insight family 鼓励覆盖 anchor 之外的更多可见点与子结构，但不会把 README 写成 `dossier_v1` 那套字段级合同
- 多点 aux 的 `construction` 必须显式写出 staged / combined strategy，否则会被拒绝

如果需要 `dossier_v1` 的字段级校验口径，例如 `bridge_chain`、`goal_closure` 或更细的 coordinate contract，请直接看 [DOSSIER_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/DOSSIER_V1_MAINLINE.md)，不要把它当成当前默认 insight family 合同。

## 导出格式

`insight_image_v1` 输出 JSONL 每行形如：

```json
{
  "instruction": "Given the geometry image and the formal problem text, write a forward-thinking trace that motivates the auxiliary construction. Output the thinking trace and the final aux block.",
  "input": "<problem> ... </problem>",
  "thinking": "<thinking>...</thinking>",
  "aux": "<aux> ... </aux>",
  "output": "<thinking>...</thinking>\n<aux> ... </aux>",
  "image_path": "./datasets/20260512/imgs_png_inverted/xxx.png"
}
```

`insight_text_v1` 的最终数据集记录与上面相同，但不包含 `image_path`。

`backtrace_text_v1` 的最终数据集记录同样不包含 `image_path`。

这里的 `input` 就是最终训练/评估时应暴露给学生模型的文本输入；隐藏证明和坐标索引不会写进训练输入。

## 使用方法

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -n 100 \
  -w 8 \
  --generation-style insight_image_v1 \
  --model-name qwen/qwen3.5-plus-02-15 \
  -o experiments/cot_sft_generation/generated/run.jsonl \
  -v
```

text-only 版本：

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -n 100 \
  -w 8 \
  --generation-style insight_text_v1 \
  --model-name qwen/qwen3.5-plus-02-15 \
  -o experiments/cot_sft_generation/generated/run_text.jsonl \
  -v
```

text-only writer-only backtrace 版本：

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -n 100 \
  -w 8 \
  --generation-style backtrace_text_v1 \
  --model-name qwen/qwen3.5-plus-02-15 \
  -o experiments/cot_sft_generation/generated/run_backtrace.jsonl \
  -v
```

处理全量数据：

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --process-all \
  -w 16 \
  --generation-style insight_image_v1 \
  --model-name qwen/qwen3.5-plus-02-15 \
  -o experiments/cot_sft_generation/generated/full.jsonl
```

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-i, --input` | `datasets/20260512/geometry_clauses10_samples100k_inverted_fl_points_only.jsonl` | 输入数据 |
| `-o, --output` | 时间戳输出路径 | 输出 JSONL |
| `-n, --num-samples` | `3` | 非全量模式下处理多少条 |
| `--process-all` | 关闭 | 处理全部含 `<aux>` 的样本 |
| `-w, --num-workers` | `4` | 并发 worker 数 |
| `--model-name` | `qwen/qwen3.5-plus-02-15` | 教师模型 |
| `--generation-style` | `insight_image_v1` | 当前 generation style；也可显式指定 `insight_text_v1` / `backtrace_text_v1` / `dossier_v1` / `model_evidence_legacy` |
| `-r, --max-retries` | `3` | 每个阶段的最大重试次数 |
| `--sequential` | 关闭 | 顺序取前 N 条，而不是随机抽样 |
| `-v, --verbose` | 关闭 | 记录样本级 prompt / plan / body / final thinking |

## 运行产物

除最终 `output_jsonl` 外，还会生成一个 artifacts 目录，里面包含：

- `run.log`
- `run_config.json`
- `summary.json`
- `item_audits.jsonl`
- `semantic_audits.jsonl`
- `sampled_inputs.jsonl`（仅 `-v`）
- `item_records.jsonl`（仅 `-v`）

其中：

- `run_config.json` 用于记录当前 run 的代码版本、输入文件指纹、参数和 git 状态
- `sampled_inputs.jsonl` 用于记录本轮实际抽中的源样本
- 这两个文件的正式字段协议见 [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/ARTIFACT_SCHEMA.md)

`summary.json` 还会额外汇总：

- `surface_pass_items`
- `surface_fail_items`
- `surface_pass_rate`
- `semantic_reviewed_items`
- `semantic_pass_items`
- `semantic_fail_items`
- `semantic_pass_rate`
- `manual_critical_error_items`
- `manual_critical_error_rate`
- `avg_attempts_used`
- `semantic_review_status`
- `source_audit_issue_items`
- `generation_audit_issue_items`

如果已经补完 `semantic_audits.jsonl`，应再运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --write-summary
```

这样 `summary.json` 里的 `semantic_review_status`、`semantic_pass_rate`、`manual_critical_error_items` 和 `manual_critical_error_rate` 才会与最新语义审读结果一致。

如果是在迭代阶段准备给 Codex 做语义审读，建议先运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --print-pending \
  --surface-pass-only \
  --max-items 20
```

这样会先列出当前最值得审的待审样本队列，并附上 `source_audit` / `generation_audit` 的问题提示，避免把还没过 surface 的样本和真正值得看语义的样本混在一起。

如果想直接把完整审读上下文交给 Codex，而不是再手工翻 `item_records.jsonl`，可以在 `-v/--verbose` 生成的 run 上继续运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --print-pending \
  --print-pending-payloads \
  --surface-pass-only \
  --max-items 10
```

或者导出成独立 JSONL：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --surface-pass-only \
  --export-pending-review-jsonl /path/to/pending_review_payloads.jsonl
```

注意：payload 模式依赖 `item_records.jsonl`，因此必须来自带 `-v/--verbose` 的 run。

`item_audits.jsonl` 会为每条样本分别记录：

- `goal_type`
- `aux_type`
- `source_audit`
- `generation_audit`
- `surface_pass`
- `success`

`semantic_audits.jsonl` 会为每条样本预先写出语义审读占位记录：

- `goal_type`
- `aux_type`
- `surface_pass`
- `semantic_pass`
- `manual_critical_error`
- `review_status`
- `review_checklist_version`
- `issue_codes`
- `issues`
- `notes`

`item_records.jsonl` 会保存每条样本的：

- public problem
- 原始 aux
- `goal_type`
- `aux_type`
- 脱敏后的 hidden proof 片段
- plan / write prompt
- plan 输出
- write 输出
- final thinking
- `surface_pass`
- 校验失败信息

更细的字段表见 [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/ARTIFACT_SCHEMA.md)。

## 依赖

脚本运行生成时需要：

```bash
pip install openai
```

并设置：

```bash
export ZJUVAI_API_KEY="sk-xxxxxx"
export ZJUVAI_BASE_URL="https://api.zjuqx.cn/v1"
```

如果网关偶尔抖动，还可以额外设置：

```bash
export ZJUVAI_TIMEOUT_SECONDS="180"
export ZJUVAI_API_RETRIES="3"
export ZJUVAI_API_RETRY_BACKOFF_SECONDS="3"
```

这里的 `ZJUVAI_API_RETRIES` 是单次 API 调用内部对瞬时 `Connection error` / `timeout` / `502/503/504` 的补偿重试，不会替代脚本本身的 stage 级内容校验重试。

注意：planner stage 现在对少数明显可修复的失败类型会额外给 `1-2` 次 bonus retry，主要覆盖：

- 高阶 `angle` / `similar` / `ratio` bridge 的 support/object grounding 还不完整
- 跳过 prerequisite checkpoint
- 非 anchor coordinate coverage 仍然太窄

维护相关的最小本地检查：

```bash
python experiments/cot_sft_generation/maintenance_smoke_check.py
```

它会统一执行：

- core files 的 `py_compile`
- 固定 benchmark manifest 和输入文件的一致性检查
- `generate_cot_sft.py --help`
- `semantic_review.py --help`
- `tests/test_cot_sft_*.py` 的 `unittest` 回归

## 辅助脚本

目录中的 `prepare_metadata.py` 仍然保留，用于从其他源数据准备本地抽样 metadata；它不是当前主生成流程的必要步骤。
