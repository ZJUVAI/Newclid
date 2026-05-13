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

## 当前生成框架

脚本现在采用更受控的两阶段生成：

1. `plan`
   - 教师模型看到完整记录和图片
   - 只输出结构化 JSON，而不是直接写整段 `thinking`
   - JSON 中包含：
     - `anchor_points`
     - `anchor_relation`
     - `goal_bottleneck`
     - `helper_idea`
     - `construction`
   - 目标是先把“看图得到的关键锚点、当前证明瓶颈、需要的辅助构造类型、最终构造语句”拆干净
2. `write`
   - 再根据 `plan` 输出纯正文 body
   - 这一步不允许模型自己输出 `<point>` / `<coord>` 标签
   - 脚本会把 `plan` 中选出的锚点自动拼成带坐标的 anchor sentence，再与正文 body 合成为最终 `<thinking>`

也就是说，坐标标签和最终结构顺序现在由脚本控制，而不是完全交给模型自由生成。

## 泄露控制

最终 `thinking` 会做程序化校验，默认会拒绝以下内容：

- `<aux>` / `<proof>` / `<numerical_check>`
- `[012]` 这类步骤编号
- `AR` / `r63` / `a01` 这类证明引擎痕迹
- `sameclock` / `simtri` / `simtrir` 这类未来证明或引擎术语
- “hidden reference / supervisor / given aux / rest of the proof” 等元话术
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
- `sampled_inputs.jsonl`（仅 `-v`）
- `item_records.jsonl`（仅 `-v`）

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

## 辅助脚本

目录中的 `prepare_metadata.py` 仍然保留，用于从其他源数据准备本地抽样 metadata；它不是当前主生成流程的必要步骤。
