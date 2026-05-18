# CoT SFT Generation

这个实验目录现在用于生成“带 CoT 的辅助构造数据”。核心约束是两层分离：

1. 生成数据时，教师模型可以看到数据中的完整信息，包括：
   - 图片
   - `llm_input_renamed`
   - `llm_output_renamed` 中的 `<aux>` 与后续证明
   - `point_coords_grid` / `grid_coord`
   - 其他源字段
2. 最终导出的训练样本只保留学生模型在训练和评估时应当看到的输入：
   - 图片
   - 题目文本

因此，这个脚本做的是“full-information teacher -> visible-only student target”的数据蒸馏，而不是把完整证明直接暴露给训练模型。

## 文档导航

- [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/CURRENT_DESIGN.md)：当前代码真正执行的流程、`plan` 字段、脚本派生字段、writer 约束。
- [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/ARTIFACT_SCHEMA.md)：`summary.json`、`item_records.jsonl`、`item_audits.jsonl`、`semantic_audits.jsonl` 的正式字段协议。
- [MAINTENANCE_PLAYBOOK.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/MAINTENANCE_PLAYBOOK.md)：长期 Codex 迭代时的文件分工、变更地图、回归资产要求和维护检查清单。
- [benchmarks/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/README.md)：仓库内固定 benchmark、manifest 和复用方式。
- [STATUS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/STATUS.md)：阶段性进展、当前最好证据、已知问题、距离目标的差距。
- [EXPERIMENT_LOG.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/EXPERIMENT_LOG.md)：按时间记录的近期实验日志和提交对应关系。

## 默认数据源

默认输入文件已经切换为：

```text
datasets/20260512/geometry_clauses10_samples100k_inverted_fl_points_only.jsonl
```

如果不传 `-i/--input`，脚本会直接使用这个文件。

## 固定基线

长期迭代时，不应只依赖 `/tmp` 里的临时回归文件。当前已经落仓的固定基线见 [benchmarks/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/README.md)。

当前最重要的固定集是：

- [benchmarks/fixed_v104sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl)
- [benchmarks/fixed_v104sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json)

它用于：

- 固定 surface regression
- 固定 semantic review baseline
- 复现 `v142` 这组当前最常引用的 `4` 条回归样本

## 生成目标

每条输出样本包含两部分：

- `thinking`：模型写出的 `<thinking>...</thinking>`，内容必须看起来只能依赖图片和题目得到，不能泄露 `<problem>...</problem>` 之后的信息
- `aux`：直接保留源数据中的原始 `<aux>...</aux>`

此外还会保留一个兼容字段：

- `output`：`thinking + "\n" + aux`

## 数据质量目标

当前这条生成链路的目标，不是只产出“看起来像 CoT”的文本，而是产出真正可用于训练辅助构造模型的高质量样本。具体要求如下：

1. 可见输入边界必须严格
   - 最终训练样本暴露给学生模型的只有图片和题目文本。
   - `thinking` 不得泄露 `<problem>...</problem>` 之后的 hidden proof、proof IDs、规则名、数值检查字段、坐标表来源等生成期信息。

2. `thinking` 必须像是从图和题面观察得到的
   - 文本应当从可见图形结构出发，而不是像在复述 formal proof。
   - 允许生成期教师模型使用完整记录做监督，但最终导出的 `thinking` 必须读起来像“观察图片后得到的构造与验证思路”。

3. 不能只盯 2-3 个点，要对整张图有完整认识
   - 少量 tagged anchor points 只负责给图定向。
   - `thinking` 还必须覆盖与目标有关的其他可见点、子结构、平行线、圆、等腰/等边/中点/共线等更广义的可见配置。
   - 如果正文只围绕开头 2-3 个点打转，而忽略后续真正参与目标的点或子图，这类样本不算高质量。

4. 坐标应当服务于几何关系判断，而不是只做标签
   - 生成期可以使用 `point_coords_grid` / `grid_coord` 做内部 sanity check。
   - 坐标的作用应当是帮助教师模型确认哪些平行、垂直、等长、中点、共线、对称、圆结构值得进一步追踪。
   - 最终 `thinking` 中的坐标标签只是一层可见锚定；高质量样本还应当体现这些坐标支持的几何关系确实进入了推理链。

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
     - `aux_direct_relations -> bridge_steps -> goal_finish` 是否形成有效闭环
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
- 完成人工/Codex 审读后，要回填 `semantic_audits.jsonl`，再运行 `semantic_review.py --write-summary` 刷新 `summary.json`。
- schema 细节和字段解释以 [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/ARTIFACT_SCHEMA.md) 为准。

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

当前代码是“脚本强约束 + 两阶段模型生成”：

1. `source audit`
   - 先检查图片、题面、`<aux>`、proof、坐标字段是否缺失或明显冲突。
   - 发现异常先记录，不为了通过率强行硬写。

2. `plan`
   - planner 只输出结构化 JSON，不直接写整段 `thinking`。
   - 关键字段包括：
     - `anchor_points`
     - `figure_overview`
     - `coordinate_relations`
     - `visible_relations`
     - `goal_bottleneck`
     - `construction`
     - `aux_direct_relations`
     - `bridge_steps`
     - `goal_finish`
   - 脚本会把 planner 输出继续规范化，并自动补齐 route / coverage 相关派生字段。

3. 脚本补全中间约束
   - 自动派生 `coverage_targets`，把 goal-side 非锚点区域显式交给 writer。
   - 为每个 `bridge_steps[*]` 自动补：
     - `next_target_relation`
     - `next_target_purpose`
     - `required_supports`
     - `focus_points`
     - `preferred_sentence_shell`
   - 这些字段的目的，是强制 writer 不要只围着 anchor frame 打转，也不要跳过 bridge。

4. `write`
   - writer 只写 body 纯文本，不允许自己写 `<point>` / `<coord>`。
   - 脚本会先注入 prefix：
     - anchor sentence
     - figure overview sentence
     - coordinate hint sentence
     - visible relation sentence
   - writer 实际吃到的是紧凑版 `Approved Writer Handoff`，而不是整份冗长 plan。
   - prompt 中还会附带：
     - `Global Coverage Targets`
     - `Non-Skippable Bridge Checklist`
     - 每个 bridge step 的 `preferred_sentence_shell`

5. 终检与导出
   - writer body 通过脚本终检后，才会组装成最终 `<thinking>...</thinking>`。
   - 终检会检查：
     - 长度和格式
     - prefix 重复
     - shorthand / 泄露
     - bridge relation 是否逐句按顺序落实
     - `goal_finish` 是否真的落地

更细的字段说明和脚本过程见 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/CURRENT_DESIGN.md)。

## 泄露控制

最终 `thinking` 会做程序化校验，默认会拒绝以下内容：

- `<aux>` / `<proof>` / `<numerical_check>`
- `[012]` 这类步骤编号
- `AR` / `r63` / `a01` 这类证明引擎痕迹
- `sameclock` / `simtri` / `simtrir` 这类未来证明或引擎术语
- “hidden reference / supervisor / given aux / rest of the proof” 等元话术
- `coordinate` / `coordinates` / `coordinate table` 这类直接暴露 hidden 坐标来源的表述
- LaTeX / `$...$` 数学包裹
- `this point is crucial` / `necessary relationships` / `help establish` 这类低信息密度套话

同时会校验：

- 输出必须是且仅是一个 `<thinking>...</thinking>` 块
- `thinking` 长度足够
- `<point>...</point><coord>(x,y)</coord>` 标签数量不能过多
- 至少出现一个 `<point>...</point><coord>(x,y)</coord>` 标签
- 这些坐标必须与源数据中的 `point_coords_grid` / `grid_coord` 完全一致
- `<point>` 标签不能单独出现，必须紧跟匹配坐标
- `plan` 中的构造语义必须与 hidden aux 对齐，例如：
  - `midp` 必须明确 midpoint
  - `cyclic` 必须明确 circle / circumcircle / cyclic
  - `cong` 必须明确 equal / congruent / equidistant
- `plan` 中的 `coordinate_relations` 必须列出 2-3 个具体关系检查，并明确点名对应 visible points
- `plan` 中的 `visible_relations` 必须优先复用 visible formal premises 中已有的具体关系，而不是凭空发明高层结构
- `plan` 中的 `coordinate_hints` 必须说出具体几何关系，不允许空泛描述
- `plan` 中的 `figure_overview` / `visible_relations` / `bridge_steps` 必须覆盖锚点之外的可见点或子结构
- `plan` 中的 `aux_direct_relations` 必须只写 aux 的直接后果，不能提前跳到旧图深处
- `plan` 中的 `bridge_steps` 必须是结构化桥接步骤，每步至少说明：
  - 这一步得到什么 `relation`
  - 它依赖哪些已有关系 `depends_on`
  - 它为下一跳或收尾解锁什么 `why_it_helps`
  - `why_it_helps` 不能只写抽象作用，例如 “enabling angle transfers”；它应说明这一步为下一跳或收尾解锁了什么，但“下一跳的精确 relation”现在由脚本内部补成 `next_target_relation` 传给 writer
  - `why_it_helps` 也不应偷偷引入未在 relation/depends_on/下一跳中出现的新高层路线，例如凭空说相似三角形、圆、平行四边形等
- `plan` 中的 `bridge_steps.relation` 还应尽量贴近 hidden proof guidance 给出的真实 bridge / finish 关系，不能任意换成另一条高层路线
- `plan` 中的 `goal_finish` 必须明确最后要落到哪个 goal-side angle / ratio / congruence 关系
- 多点 aux 的 `construction` 必须显式写出 staged / combined strategy，否则会被拒绝

## 导出格式

输出 JSONL 每行形如：

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

这里的 `input` 就是最终训练/评估时应暴露给学生模型的文本输入；隐藏证明和坐标索引不会写进训练输入。

## 使用方法

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -n 100 \
  -w 8 \
  --model-name qwen/qwen3.5-plus-02-15 \
  -o experiments/cot_sft_generation/generated/run.jsonl \
  -v
```

处理全量数据：

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --process-all \
  -w 16 \
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

`summary.json` 还会额外汇总：

- `surface_pass_items`
- `surface_fail_items`
- `surface_pass_rate`
- `semantic_reviewed_items`
- `semantic_pass_items`
- `semantic_fail_items`
- `semantic_pass_rate`
- `manual_critical_error_items`
- `semantic_review_status`
- `source_audit_issue_items`
- `generation_audit_issue_items`

如果已经补完 `semantic_audits.jsonl`，应再运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --write-summary
```

这样 `summary.json` 里的 `semantic_review_status`、`semantic_pass_rate` 和 `manual_critical_error_items` 才会与最新语义审读结果一致。

`item_audits.jsonl` 会为每条样本分别记录：

- `source_audit`
- `generation_audit`
- `surface_pass`
- `success`

`semantic_audits.jsonl` 会为每条样本预先写出语义审读占位记录：

- `surface_pass`
- `semantic_pass`
- `manual_critical_error`
- `review_status`
- `issues`
- `notes`

`item_records.jsonl` 会保存每条样本的：

- public problem
- 原始 aux
- 脱敏后的 hidden proof 片段
- plan / write prompt
- plan 输出
- write 输出
- final thinking
- `surface_pass`
- 校验失败信息

更细的字段表见 [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/ARTIFACT_SCHEMA.md)。

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

维护相关的最小本地检查：

```bash
python experiments/cot_sft_generation/maintenance_smoke_check.py
```

它会统一执行：

- core files 的 `py_compile`
- 固定 benchmark manifest 和输入文件的一致性检查
- `semantic_review.py --help`
- `tests/test_cot_sft_*.py` 的 `unittest` 回归

## 辅助脚本

目录中的 `prepare_metadata.py` 仍然保留，用于从其他源数据准备本地抽样 metadata；它不是当前主生成流程的必要步骤。
