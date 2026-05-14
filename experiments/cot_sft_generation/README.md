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

## 默认数据源

默认输入文件已经切换为：

```text
datasets/20260512/geometry_clauses10_samples100k_inverted_fl_points_only.jsonl
```

如果不传 `-i/--input`，脚本会直接使用这个文件。

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

## 当前生成框架

脚本现在采用更受控的两阶段生成：

1. `plan`
   - 教师模型看到完整记录和图片
   - 只输出结构化 JSON，而不是直接写整段 `thinking`
   - JSON 中包含：
     - `anchor_points`
     - `anchor_relation`
     - `figure_overview`
     - `coordinate_relations`
     - `visible_relations`
     - `coordinate_hints`
     - `goal_bottleneck`
     - `helper_idea`
     - `construction`
     - `aux_direct_relations`
     - `bridge_relations`
     - `goal_finish`
   - 目标不再只是“提出 aux”，而是把下面几件事先拆干净：
     - 用少量 tagged anchor points 给图定向
     - 对全图做更完整的可见结构概览，而不只盯 2-3 个点
     - 利用 hidden visible-point coordinates 做内部 sanity check，先提炼 2-3 个更具体的候选关系，再决定哪些几何关系值得继续追
     - 说明当前目标的真正瓶颈是什么
     - 给出 aux 的构造语句
     - 明确拆开“加了这个 aux 之后，下一步打算怎么继续解”的关系桶：
       - `aux_direct_relations`
       - `bridge_relations`
       - `goal_finish`
   - 如果 hidden aux 含多个新点，还会额外要求 `construction` 里显式写出 staged strategy，例如 `first ... then ...`
2. `write`
   - 再根据 `plan` 输出纯正文 body
   - 这一步不允许模型自己输出 `<point>` / `<coord>` 标签
   - 脚本会自动把四类前缀句拼进最终 `thinking`：
     - 带 `<point>...</point><coord>(x,y)</coord>` 的 anchor sentence
     - `figure_overview` 句
     - `coordinate_hints` 句
     - `visible_relations` 句
   - writer 只负责后续正文，即：
     - 解释瓶颈
     - 引出 aux
     - 按 `aux_direct_relations -> bridge_relations -> goal_finish` 把 aux 之后的验证链真正推进到目标

也就是说，现在的机制是：

- 模型负责选哪些点值得被 tagged，以及如何理解全图和后续验证路径
- 脚本负责把这些点的真实坐标从源数据精确注入最终 `thinking`
- hidden structured coordinate candidates 负责把“坐标判断”先收敛成更具体的可疑关系
- hidden proof guidance 负责约束 `aux_direct_relations / bridge_relations / goal_finish` 不要停在“提出 aux”，而要尽量贴近真实可解路径

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
- `plan` 中的 `figure_overview` / `visible_relations` / `bridge_relations` 必须覆盖锚点之外的可见点或子结构
- `plan` 中的 `aux_direct_relations` 必须只写 aux 的直接后果，不能提前跳到旧图深处
- `plan` 中的 `bridge_relations` 必须明确说明该后果如何连接回原图已有结构
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
- `sampled_inputs.jsonl`（仅 `-v`）
- `item_records.jsonl`（仅 `-v`）

`summary.json` 还会额外汇总：

- `source_audit_issue_items`
- `generation_audit_issue_items`

`item_audits.jsonl` 会为每条样本分别记录：

- `source_audit`
- `generation_audit`
- `success`

`item_records.jsonl` 会保存每条样本的：

- public problem
- 原始 aux
- 脱敏后的 hidden proof 片段
- plan / write prompt
- plan 输出
- write 输出
- final thinking
- 校验失败信息

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

## 辅助脚本

目录中的 `prepare_metadata.py` 仍然保留，用于从其他源数据准备本地抽样 metadata；它不是当前主生成流程的必要步骤。
