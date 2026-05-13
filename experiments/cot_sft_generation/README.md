# CoT SFT Dataset Generation

生成包含思考过程（Chain of Thought）的监督微调（SFT）数据集。

## 任务背景

当前任务的核心目标是：利用大语言模型为形式化几何题自动合成高质量的 SFT 训练数据。具体做法是，给模型提供：

- 形式化几何题目描述（如 DDAR / formal language problem）
- 最终需要发现的辅助构造 `<aux>`
- 以及用于提供逻辑上下文的 `rest_of_proof`

然后要求模型输出一段纯自然语言的 `<thinking>`，这段内容必须看起来像是数学家从零开始做题时的正向推理过程，而不是对标准答案的倒叙解释。理想的 CoT 应该体现：

- 将形式化条件翻译成几何直觉
- 识别当前证明的瓶颈或缺失环节
- 自然引出所需辅助点、辅助线或辅助关系
- 在不泄露未来证明细节的前提下完成推导

## 主要挑战

这个任务最大的难点不是“让模型生成内容”，而是“阻止模型作弊”。

当我们把完整证明上下文一并提供给模型时，模型很容易出现以下污染行为：

- 直接照抄底层引擎语言，如 `simtrir`、`sameside`、`AR`
- 泄露未来证明步骤编号，如 `[015]`
- 使用“上帝视角”或提示词视角解释答案，例如直接说“根据给定的 aux”或“我需要模拟推理过程”
- 复述完整 formal proof，而不是只关注辅助构造的发现过程

这些输出虽然表面上“正确”，但会严重污染 SFT 数据，导致后续训练出的模型学会底层证明模板、prompt 元话术和格式投机，而不是学会真正的人类式几何思考。

## 当前策略

为减少上述污染，当前实验主要从两个方向控制生成质量：

### 1. Prompt 工程

- 强调只能输出 `<thinking>` + 原样 `<aux>`
- 强调必须使用正向推理，不能以后验方式解释
- 强调禁止泄露未来步骤编号和底层 formal rule 名称
- 强调不能出现 meta-talk，必须始终以数学家视角叙述
- 在需要时引入高质量 one-shot / few-shot 示例，给模型一个“黄金风格”参考

### 2. 工程层数据预处理

在调用模型前，会对 `rest_of_proof` 做物理脱敏，减少模型直接抄写 formal proof 的机会：

- 删除形如 `[012]` 的步骤编号
- 删除形如 `r63`、`AR` 的规则名

这一步不能彻底解决作弊问题，但可以显著降低模型把底层引擎轨迹原样搬运到 `<thinking>` 里的概率。

## 功能

该脚本从原始几何问题数据集生成 CoT SFT 数据集，通过调用 LLM API 为每个问题生成：
- `<thinking>` 标签：模型的思考过程
- `<aux>` 标签：辅助点预测

## 环境配置

设置 API 凭证（支持 OpenAI 兼容的 API）：

```bash
export ZJUVAI_API_KEY="sk-xxxxxx"
export ZJUVAI_BASE_URL="https://api.zjuqx.cn/v1"  # 可选，默认使用此 URL
```

模型名称通过命令行参数 `--model_name` 指定，默认值为 `qwen/qwen3.5-plus-02-15`。

## 使用方法

```bash
python generate_cot_sft.py \
  -i <input_jsonl> \
  [-o <output_jsonl>] \
  [-n <num_samples>] \
  [-w <num_workers>] \
  [-m <mode>] \
  [--model_name <model_name>] \
  [-r <max_retries>] \
  [--sequential] \
  [-v]
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-i, --input` | str | 必需 | 输入的原始几何问题 JSONL 文件路径 |
| `-o, --output` | str | `experiments/cot_sft_generation/generated/<UTC时间戳>/cot_sft_dataset.jsonl` | 输出的 SFT 数据集 JSONL 文件路径 |
| `-n, --num_samples` | int | 3 | 要处理的样本数量 |
| `-w, --num_workers` | int | 4 | 并行 API 调用的线程数 |
| `-m, --mode` | str | vision | 生成模式：`vision`（基于图像）或 `text`（仅文本） |
| `--model_name` | str | `qwen/qwen3.5-plus-02-15` | 调用 API 时使用的模型名称 |
| `-r, --max_retries` | int | 3 | 验证失败时的最大重试次数 |
| `--sequential` | flag | - | 使用顺序采样而非随机采样 |
| `-v, --verbose` | flag | - | 启用详细日志（显示完整提示词） |

## 示例

```bash
# 基础用法：处理 100 个样本
python generate_cot_sft.py \
  -i data/raw_geometry.jsonl \
  -o data/cot_sft_dataset.jsonl \
  -n 100

# 使用多线程加速
python generate_cot_sft.py \
  -i data/raw_geometry.jsonl \
  -o data/cot_sft_dataset.jsonl \
  -n 1000 \
  -w 8

# 仅文本模式，启用详细日志
python generate_cot_sft.py \
  -i data/raw_geometry.jsonl \
  -o data/cot_sft_dataset.jsonl \
  -m text \
  -v

# 指定模型
python generate_cot_sft.py \
  -i data/raw_geometry.jsonl \
  --model_name qwen/qwen3-30b-a3b-thinking-2507

# 使用默认输出路径
python generate_cot_sft.py \
  -i data/raw_geometry.jsonl
```

## 准备本地元数据样本

`prepare_metadata.py` 用于从外部数据集抽样，并在当前实验目录下生成可复用的 `metadata.jsonl` 与反色图片样本。脚本不再依赖写死的绝对路径，调用时需要显式传入源数据路径。

```bash
python prepare_metadata.py \
  --src-jsonl /path/to/output.jsonl \
  --src-img-dir /path/to/imgs_png \
  --metadata-dir experiments/cot_sft_generation/metadata \
  --output-jsonl experiments/cot_sft_generation/metadata/metadata.jsonl \
  -n 100 \
  --seed 42
```

### `prepare_metadata.py` 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--src-jsonl` | path | 必需 | 原始数据集 JSONL 路径 |
| `--src-img-dir` | path | 必需 | 原始 PNG 图片目录 |
| `--metadata-dir` | path | `experiments/cot_sft_generation/metadata` | 输出元数据目录 |
| `--output-jsonl` | path | `experiments/cot_sft_generation/metadata/metadata.jsonl` | 输出元数据 JSONL |
| `-n, --num-samples` | int | 100 | 采样数量上限 |
| `--seed` | int | 42 | 随机采样种子 |

## 输出格式

生成的 JSONL 文件中每行包含：

```json
{
  "instruction": "...",
  "input": "...",
  "output": "...",
  "image_path": "..."
}
```

其中：

- `instruction`：给 SFT 模型的任务说明
- `input`：形式化题目输入
- `output`：模型生成的 `<thinking>...</thinking><aux>...</aux>`
- `image_path`：仅 `vision` 模式下保留

## 实验记录与产物

除了你通过 `-o` 指定的最终输出文件外，脚本现在还会为每次运行自动创建一个独立的 artifacts 目录：

```text
<output_stem>_artifacts_<UTC时间戳>/
```

例如，如果没有显式传入 `-o`，脚本会自动生成类似：

```text
experiments/cot_sft_generation/generated/20260312_101530/cot_sft_dataset.jsonl
```

对应的 artifacts 目录会生成在同一层级下，例如：

```text
experiments/cot_sft_generation/generated/20260312_101530/cot_sft_dataset_artifacts_20260312_101530/
```

该目录中会保存本次实验的完整上下文，便于复现、排查失败样本和分析 prompt 效果。主要文件包括：

- `run.log`：脚本运行过程中的完整日志输出
- `run_config.json`：本次运行的参数、模型名、脚本路径、输出路径、API base URL 等
- `summary.json`：本次运行的汇总统计，包括样本数、失败数、运行模式、工作线程等基础指标，以及 `runtime_seconds`（整次脚本运行耗时）

当启用 `-v` 时，还会额外记录更细粒度的样本级调试信息：

- `sampled_inputs.jsonl`：本次被采样到的原始样本及其源索引
- `item_records.jsonl`：每条样本的详细记录，包括 prompt、脱敏后的 `rest_of_proof`、生成结果、错误信息、尝试次数和耗时

如果某条样本失败，`item_records.jsonl` 中仍会保留失败记录，方便分析是 prompt 违规、验证失败还是 API 异常。

## 验证规则

生成的 CoT 输出必须满足以下条件：

1. 包含 `<thinking>...</thinking>` 标签
2. 包含 `<aux>...</aux>` 标签
3. `<thinking>` 必须在 `<aux>` 之前
4. `<thinking>` 内容至少 50 个字符
5. `<aux>` 内容必须与预期的辅助点完全匹配
6. 不能包含 `<proof>` 标签

如果验证失败，脚本会自动重试（最多 `max_retries` 次）。

## 日志

脚本会同时将日志输出到终端和 artifacts 目录下的 `run.log`。日志内容包括：

- 处理进度
- 验证失败的原因
- API 调用统计与单条样本耗时
- 重试过程中的报错信息
- 最终生成的数据集大小

因此，后续回看实验时，不需要依赖终端历史；prompt、参数、样本、输出和日志都可以在同一个 artifacts 目录中找到。
