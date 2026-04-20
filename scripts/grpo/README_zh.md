# GRPO 辅助点奖励

English version: [README.md](/C20545/home/wangzi/GenesisGeo-grpo/scripts/grpo/README.md)

本目录包含基于 GRPO 的辅助点生成所需的数据筛选、奖励计算和训练启动辅助脚本。

## 脚本列表

- `plugin.py`：为 SWIFT 注册 `aux_reward`。
- `../analyze_dataset.py`：为 JSONL 数据添加辅助结构、目标谓词、谓词族标签以及轻量复杂度字段。
- `analyze_selected_dataset.py`：在 `select_debug_set.py` 之后分析最终选出的 GRPO 训练 JSONL。
- `build_candidate_pool.py`：仅保留真正包含辅助目标的样本，并输出候选池摘要。
- `prefilter_candidate_pool.py`：在模型难度标注前，对大规模候选池做廉价的流式预筛选。
- `label_difficulty.py`：基于文本模型的难度标注，采用离线生成加奖励评估。
- `label_difficulty_vlm.py`：兼容 VLM 的难度标注，支持 batch 推理和多 GPU。
- `select_grpo_dataset.sh`：一键运行完整数据筛选流水线。
- `select_debug_set.py`：过滤已掌握和无效样本，并构建最终 GRPO 子集。
- `prepare_grpo_aux_dataset.py`：将已有 JSONL 转成仅用于 aux GRPO 的 `query/fl_problem/response` 格式，并丢弃没有 `<aux>...</aux>` 的样本。
- `train_grpo.sh`：基于 `swift rlhf` 的 GRPO 启动模板。
- `src/newclid/training/grpo_rewards.py`：组合式奖励评估器。

## 所需数据字段

完整的 GRPO 流水线从包含以下原始字段的 JSONL 数据开始：

- `llm_input_renamed`：模型提示词 / query
- `llm_output_renamed`：模型回复
- `fl_problem`：原始可构造几何题目

SWIFT 使用的最终训练数据集必须包含：

- `query`
- `fl_problem`
- `response`

`response` 应该是仅包含辅助点目标的字符串，例如 `<aux> x00 i : ... ; </aux>`。

## 端到端数据流水线

推荐的完整流程：

```text
raw JSONL
-> analyze_dataset.py
-> build_candidate_pool.py
-> prefilter_candidate_pool.py
-> label_difficulty.py / label_difficulty_vlm.py
-> select_debug_set.py
-> analyze_selected_dataset.py
-> train_grpo.sh
```

### 1. 标注原始数据集

这一步会提取：

- 每一行是否包含有效的 aux 块
- aux 段数和 aux 点数量
- 目标谓词和谓词族标签
- `n_premises`、`problem_predicate_count` 和 `problem_clause_count`

```bash
python scripts/analyze_dataset.py \
  datasets/raw.jsonl \
  --annotations-output datasets/grpo/annotated.jsonl \
  --summary-output datasets/grpo/annotated_summary.json
```

### 2. 构建候选池

这一步只保留真正包含辅助目标的样本，并在保留平衡元数据的同时重写为 `query / fl_problem / response` 格式。

```bash
python scripts/grpo/build_candidate_pool.py \
  datasets/grpo/annotated.jsonl \
  datasets/grpo/candidate_pool.jsonl \
  --summary-output datasets/grpo/candidate_pool_summary.json
```

### 3. 对大候选池做预筛选

这一阶段用于在模型标注前缩小大候选池。目标不是直接得到最终训练集，而是以较低成本构造一个更小、更多样的候选池，供昂贵的难度标注步骤使用。

当前实现做了四件事：

1. 精确 query 去重。
   在构建候选池统计时，同一个 `query` 只计第一次出现，避免重复提示词占满采样预算。

2. 将每条样本分到一个三维桶中。
   每个样本按以下维度分桶：
   - aux 形态
     当 `aux_segment_count >= 2` 或 `aux_points_total >= 2` 时归为 `multi_aux`，否则归为 `single_aux`
   - 前提复杂度
     当 `n_premises >= 8` 时归为 `p8_plus`，当 `n_premises >= 5` 时归为 `p5_7`，否则归为 `p0_4`
     如果缺少 `n_premises`，脚本会回退到 `problem_clause_count`
   - 主谓词族
     优先从 `goal_predicate` 推断，其次取 `predicate_family_tags` 的第一项，否则归为 `other_family`

3. 先为每个桶分配配额，再进行采样。
   脚本先按 aux 形态拆分全局 `target_size`：
   - `60%` 分配给 `multi_aux`
   - `40%` 分配给 `single_aux`

   然后在每个 aux 桶内继续按前提复杂度分配：
   - `60%` 给 `p8_plus`
   - `30%` 给 `p5_7`
   - `10%` 给 `p0_4`

   对每个 `(aux_shape, premise_bucket)` 切片，配额会尽可能均匀地分到该切片内所有可用谓词族上。

4. 用蓄水池采样抽样，并在不足时补齐。
   对于样本足够的桶，脚本使用 reservoir sampling，因此在固定 `--seed` 下结果可复现，同时仍适合流式处理大数据集。
   如果某些桶不足以满足配额，脚本会从剩余样本中回填，直到达到 `target_size`。

回填阶段还会施加一个按目标谓词的上限：

- `goal_cap = 20% * target_size`

这个上限作用在 `goal_predicate` 上，避免某一种目标类型主导最终的预筛选候选池。

输出报告会记录：

- 采样前的不同 query 数量
- 被移除的精确重复条目数
- 每个桶的目标配额
- 采样后每个桶的实际数量
- 每个桶的缺口
- 选中样本的目标谓词分布
- 因 `goal_cap` 被跳过的回填样本数

```bash
python scripts/grpo/prefilter_candidate_pool.py \
  datasets/grpo/candidate_pool.jsonl \
  datasets/grpo/candidate_pool_prefiltered.jsonl \
  --report-output datasets/grpo/candidate_pool_prefilter_report.json \
  --target-size 50000
```

### 4. 用当前模型标注难度

这一步会运行离线生成，并用 GRPO reward 对生成的 aux 完成进行打分，生成如下字段：

- `greedy_success`
- `pass_at_16`
- `ddar_valid_count`
- `ddar_solved_count`
- `all_invalid`

文本模型版本：

```bash
python scripts/grpo/label_difficulty.py \
  datasets/grpo/candidate_pool_prefiltered.jsonl \
  datasets/grpo/difficulty_labels.jsonl \
  --model-path /path/to/text-checkpoint
```

VLM 版本：

```bash
python scripts/grpo/label_difficulty_vlm.py \
  datasets/grpo/candidate_pool_prefiltered.jsonl \
  datasets/grpo/difficulty_labels.jsonl \
  --model-path /path/to/vlm-checkpoint
```

### 5. 选择最终 GRPO 子集

筛选器支持三种策略。

`v3_tiered` 保留较早的分层策略：

- `core`：未掌握、通过率非平凡但仍可学习的样本
- `near`：刚好落在核心窗口外的样本，可能稍难或稍易
- `hard_valid_high`：`pass_at_* = 0`，但看起来仍可学习，因为无效率低且 aux 多样性尚可
- `hard_valid_mid`：`pass_at_* = 0`，有效但多样性较低
- `mastered`：高通过率样本，仅在筛选器无法补足数量时作为少量回退

`v4_reward_mixed` 对 `pass_at_* = 0` 的样本更加严格。
它保留相同的 `core` 和 `near` 层，但只有在离线标注显示奖励结果确实混合时，才会把零通过样本放入
`reward_mixed_zero`，而不是接纳那种退化的 `valid_at_* ~= 1, pass_at_* = 0` 模式，因为这种模式在训练中往往会产生 `reward_std = 0`。

`v6_mid_strict_zero` 是只改选择器的细化版本，它收窄了可学习核心区间，并把较容易的高通过率尾部分成两个带上限的层：

- `core`：`0.125 <= pass_at_* <= 0.625`
- `near_low`：略低于核心窗口的低通过率样本
- `reward_mixed_zero`：奖励结果混合的、更严格的零通过样本
- `near_high_mid`：高于核心且不超过配置上限的中高通过率样本
- `near_high_high`：更高通过率但仍未掌握的样本，比例上限更严格
- `mastered`：仅在筛选器仍无法填满时作为回退

`v3_tiered` 会先把样本分到：

- `core`
- `near`
- `hard_valid_high`
- `hard_valid_mid`
- `mastered`

它总是移除：

- 已掌握样本：`greedy_success == true` 且 `pass_at_16` 很高
- 无效样本：`all_invalid == true`

随后它构建一个真正用于 GRPO 训练的平衡子集，并强制满足：

- 最低多段和多点覆盖率
- 最低谓词族覆盖率
- 每个目标谓词的上限，避免某一目标类型垄断
- 对 `hard_valid_high`、`hard_valid_mid` 和 mastered 回退样本的显式比例上限

JSON 报告会记录各层可用数、各层选中数、选中样本的通过率直方图、零通过与非零通过占比、mastered 占比，以及 `unique_aux_count`、`duplicate_aux_ratio` 等多样性统计。

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo/difficulty_labels.jsonl \
  datasets/grpo/grpo_train_selected.jsonl \
  --report-output datasets/grpo/grpo_train_report.json \
  --target-size 2000
```

更严格的零通过过滤示例：

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo/difficulty_labels.jsonl \
  datasets/grpo/grpo_train_selected.jsonl \
  --report-output datasets/grpo/grpo_train_report.json \
  --selection-policy v4_reward_mixed \
  --target-size 800 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-max-fraction 0.25
```

聚焦中间通过率区间的筛选器示例：

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo/difficulty_labels.jsonl \
  datasets/grpo/grpo_train_selected.jsonl \
  --report-output datasets/grpo/grpo_train_report.json \
  --selection-policy v6_mid_strict_zero \
  --target-size 2000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --near-high-mid-max-pass 0.75 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.75 \
  --zero-pass-reward-std-min 0.20 \
  --reward-mixed-zero-max-fraction 0.10 \
  --near-high-mid-max-fraction 0.15 \
  --near-high-high-max-fraction 0.14
```

输出数据行严格包含：

- `query`
- `fl_problem`
- `response`

你可以在不重新引入筛选元数据的情况下分析选中数据集：

```bash
python scripts/grpo/analyze_selected_dataset.py \
  datasets/grpo/grpo_train_selected.jsonl \
  --annotations-output datasets/grpo/grpo_train_selected_annotated.jsonl \
  --summary-output datasets/grpo/grpo_train_selected_summary.json
```

这个脚本会直接基于 `query`、`fl_problem` 和 `response` 重新计算相同的几何统计量，包括：

- 目标谓词分布
- 谓词族分布
- aux 段数 / aux 点数分布
- 题目谓词数分布
- 题目子句数分布

### 一键数据筛选

如果你希望一条命令跑完整个筛选链路，可以使用：

```bash
INPUT_PATH=datasets/raw.jsonl \
MODEL_PATH=/path/to/checkpoint \
OUTPUT_DIR=datasets/grpo_pipeline \
LABELER=text \
bash scripts/grpo/select_grpo_dataset.sh
```

这个包装脚本会运行：

```text
analyze_dataset.py
-> build_candidate_pool.py
-> prefilter_candidate_pool.py
-> label_difficulty.py / label_difficulty_vlm.py
-> select_debug_set.py
-> analyze_selected_dataset.py
```

常用环境变量：

- `INPUT_PATH`：源 JSONL，需包含 `llm_input_renamed`、`llm_output_renamed` 和 `fl_problem`
- `MODEL_PATH`：用于离线难度标注的 checkpoint
- `OUTPUT_DIR`：所有中间和最终产物的输出目录
- `LABELER`：`text` 或 `vlm`
- `PREFILTER_TARGET_SIZE`：默认为 `50000`
- `FINAL_TARGET_SIZE`：默认为 `2000`
- `SEED`：默认为 `998244353`
- `LABEL_NUM_SAMPLES`：默认为 `16`
- `LABEL_TEMPERATURE`：默认为 `0.8`
- `LABEL_TOP_P`：默认为 `0.95`

主要输出：

- `grpo_train_selected.jsonl`：最终训练数据集
- `grpo_train_report.json`：`select_debug_set.py` 生成的筛选报告
- `grpo_train_selected_summary.json`：对最终数据集重新统计后的摘要

### 当前 `vlm_sft44` 来源说明

对于本仓库当前的 `vlm_sft44` GRPO 实验：

- 原始源 JSONL：
  `/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
- VLM 难度标注 checkpoint：
  `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`

现有的 `grpo_pipeline_vlm_sft44_1m_textonly_20k*` 产物就是基于上述原始数据，通过
`build_candidate_pool.py -> prefilter_candidate_pool.py -> label_difficulty_vlm.py` 生成的。

## 从现有 SFT 数据快速开始

如果你已经有清洗好的 SFT 风格数据集，只需要构造一个仅 aux 的 GRPO 数据集，可以跳过完整筛选流水线，直接提取第一个有效 aux 块：

```bash
python scripts/grpo/prepare_grpo_aux_dataset.py \
  datasets/sft_data.jsonl \
  datasets/grpo_aux.jsonl
```

它只保留 `llm_output_renamed` 中包含首个有效 `<aux> ... </aux>` 块的样本。

## 奖励语义

`src/newclid/training/grpo_rewards.py` 只会基于生成出的 aux 块和 `fl_problem` 进行评估，而不是评估完整求解轨迹。

奖励值含义：

- `1.0`：aux 有效，且 DDAR 成功解题
- `0.25`：aux 在几何上有效，但 DDAR 未解出题目
- `-0.25`：aux 可以解析，但无法构造到题目中
- `-1.0`：aux 格式无效
- `0.0`：DDAR 引擎错误

奖励接口需要：

- `completions`
- `fl_problem`

其中 `fl_problem` 是必需字段。

## 实际运行 GRPO

训练入口是 `train_grpo.sh`，它封装了：

```bash
swift rlhf \
  --rlhf_type grpo \
  --dataset "$DATASET_PATH" \
  --external_plugins scripts/grpo/plugin.py \
  --reward_funcs aux_reward
```

最小运行示例：

```bash
MODEL_PATH=/path/to/base-or-sft-checkpoint \
DATASET_PATH=datasets/grpo/grpo_train_selected.jsonl \
OUTPUT_DIR=models/grpo_aux \
bash scripts/grpo/train_grpo.sh
```

你也可以通过脚本透传额外的 SWIFT 参数，例如：

```bash
MODEL_PATH=/path/to/checkpoint \
DATASET_PATH=datasets/grpo/grpo_train_selected.jsonl \
OUTPUT_DIR=models/grpo_aux_run1 \
bash scripts/grpo/train_grpo.sh \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 16 \
  --num_generations 8 \
  --num_train_epochs 3 \
  --learning_rate 1e-6
```

## 性能基准（`label_difficulty_vlm.py`）

在一个 Qwen3-VL checkpoint 上，以 5 条样本测试得到：

| 配置 | 每条样本耗时 | 加速比 |
|------|--------------|--------|
| 基线（num_samples=16，串行） | 3.32s | 1.0x |
| 优化后（num_samples=8，batch_size=8，1 GPU） | 1.70s | 1.95x |
| 优化后（num_samples=8，batch_size=8，2 GPUs） | 0.85s | 3.9x |
| 优化后（num_samples=8，batch_size=8，4 GPUs） | 0.43s | 7.7x |

针对 100 万行数据集中生成 3k 条 goldilocks 样本的时间估算：

| 配置 | 保守估计（10% goldilocks） | 乐观估计（20% goldilocks） |
|------|----------------------------|-----------------------------|
| 基线（1 GPU, n=16） | 27.8h | 14.0h |
| 优化后（1 GPU, n=8, batch） | 14.3h | 7.2h |
| 优化后（2 GPUs, n=8, batch） | 7.2h | 3.7h |
| 优化后（4 GPUs, n=8, batch） | 3.7h | 1.9h |

关键优化点：在 `TransformersEngine` 中显式设置 `max_batch_size`，避免 batch 推理悄悄退回到串行生成。
