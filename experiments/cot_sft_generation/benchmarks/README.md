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

## 定向抽查建议

当改动不是“全链大改”，而是某一类 prompt / validator / audit 规则的局部调整时，默认先审下面这些 subset，而不是每次都盲抽。

### 按 goal type 改动

- `eqratio` 相关改动：优先审 `eqratio_goals`
- `eqangle` 相关改动：优先审 `eqangle_goals`
- `simtri` 相关改动：优先审 `simtri_goals`
- `simtrir` 相关改动：优先审 `simtrir_goals`
- `contri` 相关改动：优先审 `contri_goals`
- `contrir` 相关改动：优先审 `contrir_goals`

### 按 aux type 或 staged strategy 改动

- 单点构造相关改动：优先审 `single_point`
- 多点构造相关改动：优先审 `multi_point`
- 多点构造的 staged strategy、step ordering、bridge unfolding 相关改动：至少审 `multi_point_staging_priority`

### 按回归目的改动

- 快速回放最近固定失败/成功样本：先跑 `fixed_v104sample`
- 改的是全局 bridge 语义、goal finish 收尾、或 generation audit 这类跨 goal 规则：优先跑 `stratified_v1_12sample` 的 `all`
- 改的是语义审读口径或需要人工/Codex 重点复核的规则：优先看 `semantic_review_priority`

### 当前仍未覆盖到 subset 级的维度

- `aux_shape` 目前已经写在 manifest `records[*].aux_shape` 里，但还没有全部拆成稳定 subset
- 如果改动强依赖某个 `aux_shape` 或某类失败模式，应先用 `focus_tags` / `notes` 手工选样，再考虑把该维度升级成新的固定 subset
