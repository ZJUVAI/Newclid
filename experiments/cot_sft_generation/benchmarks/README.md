# CoT SFT Benchmarks

这个目录用于保存 `experiments/cot_sft_generation` 长期迭代时必须稳定复用的基线资产，避免把关键回归输入和审读样本长期留在 `/tmp`。

## 当前包含的资产

### 1. 最小固定回归输入

- [fixed_v104sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl)
  - 来源：`/tmp/cot_regression_v114_v104sample_rebuilt_input.jsonl`
  - 条数：`4`
  - 用途：
    - 固定 surface regression
    - 固定 semantic review baseline
    - 复现 `v142` 这组最新完整回归输入

### 2. 最小固定回归 manifest

- [fixed_v104sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json)
  - 记录：
    - benchmark 名称
    - 输入文件路径
    - 每条样本的 goal type / aux type / review focus
    - 可复用的子集定义

### 3. 分层固定回归输入

- [stratified_v1_12sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_input.jsonl)
  - 来源：`datasets/20260512/geometry_clauses10_samples100k_inverted_fl_points_only.jsonl`
  - 条数：`12`
  - 用途：
    - 长期固定分层回归
    - `goal_type x aux_type` 的定向语义审读
    - 覆盖 `eqratio` / `eqangle` / `simtri` / `simtrir` / `contri` / `contrir`
    - 每类同时覆盖 `single_point` 与 `multi_point`

### 4. 分层固定回归 manifest

- [stratified_v1_12sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_manifest.json)
  - 记录：
    - `sample_order`
    - `source_index`
    - `goal_type`
    - `goal_text`
    - `aux_type`
    - `aux_shape`
    - `image_path`
    - `focus_tags`
    - `notes`
    - 可复用的子集定义

## 使用方式

### 跑最小固定回归

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl \
  -n 4 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_fixed_regression_output.jsonl \
  -v
```

### 跑分层固定回归

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_input.jsonl \
  -n 12 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_stratified_regression_output.jsonl \
  -v
```

### 固定回归后的语义审读汇总

生成结束后，可以运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /tmp/cot_sft_fixed_regression_output_artifacts_xxx \
  --write-summary
```

它会：

- 校验 `semantic_audits.jsonl` 与 `item_audits.jsonl` 是否对齐
- 按当前语义审读记录刷新 `summary.json`
- 输出新的 `semantic_pass_rate`、`manual_critical_error_items` 等字段

## 维护要求

1. 新的固定回归集进入长期使用前，应先落仓，不应只停留在 `/tmp`
2. manifest 至少要说明：
   - benchmark 名称
   - 输入文件
   - 样本数
   - 子集定义
   - 样本的 goal / aux 类型
   - 该回归集想监控的失败模式
   - 分层 benchmark 还应优先补 `source_index`、`focus_tags` 和 `notes`
3. 如果某个历史固定回归集不再使用，应在 manifest 或文档中标明废弃，而不是直接静默删除
4. 当前 `fixed_v104sample` 仍是最小稳定基线；`stratified_v1_12sample` 则是当前默认的分层长期基线
5. `python experiments/cot_sft_generation/maintenance_smoke_check.py` 现在会校验本目录下所有 `*_manifest.json`，不是只看单个固定文件
