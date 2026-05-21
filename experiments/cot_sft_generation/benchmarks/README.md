# CoT SFT Benchmarks

这个目录用于保存 `experiments/cot_sft_generation` 长期迭代时必须稳定复用的基线资产，避免把关键回归输入和审读样本长期留在 `/tmp`。

## 使用边界

benchmark 只负责三件事：

- 固定样本覆盖
- 固定回归入口
- 固定人审抽样入口

benchmark 不负责替代数据质量判断本身。

- `surface_pass_rate` 不是质量结论
- `semantic_pass_rate` 也不是自动 acceptance rule
- 最终判断仍要回到 [DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md) 与 [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)

## 当前目录结构

### 当前主 benchmark

- [quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)
  - 当前主线默认使用的 review-oriented benchmark
- [quality_review_v1/quality_review_v1_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl)
  - 当前主 benchmark 输入
- [quality_review_v1/quality_review_v1_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_manifest.json)
  - 当前主 benchmark manifest

### Legacy Support Packs

- [fixed_v104sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl)
  - 历史最小稳定回放集
- [fixed_v104sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json)
  - `fixed_v104sample` manifest
- [stratified_v1_12sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_input.jsonl)
  - `quality_review_v1` 的 lineage source pack
- [stratified_v1_12sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_manifest.json)
  - 原始 12-sample stratified manifest

## Which Pack To Use

- 新主线迭代：用 [quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)
- 回放历史 `v142` 最小集：用 `fixed_v104sample`
- 对照旧的 12-sample 分层顺序：用 `stratified_v1_12sample`

## 推荐运行方式

### quick4 smoke

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl \
  -n 4 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_quality_review_v1_quick4.jsonl \
  -v
```

### quick6 balanced

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl \
  -n 6 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_quality_review_v1_quick6.jsonl \
  -v
```

### full12 review

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl \
  -n 12 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_quality_review_v1_full12.jsonl \
  -v
```

### fixed historical replay

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl \
  -n 4 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_fixed_regression_output.jsonl \
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
   - review-oriented benchmark 还应优先补 `source_index`、`focus_tags`、`review_axes`、`must_check`、`review_prompts` 和 `notes`
3. 如果某个历史固定回归集不再使用，应在 manifest 或文档中标明废弃，而不是直接静默删除
4. 当前 `quality_review_v1` 是默认主 benchmark；`fixed_v104sample` 和 `stratified_v1_12sample` 保留为 legacy support packs
5. `python experiments/cot_sft_generation/maintenance_smoke_check.py` 现在会递归校验本目录下所有 `*_manifest.json`

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
- 想看坐标 cue 是否真正进入推理链：优先审 `coordinate_integration_priority`
- 想看是否真的覆盖整图：优先审 `whole_figure_coverage_priority`
- 想看单点样本是否也会退化成“只看局部”：优先审 `single_point_whole_figure_coverage_priority`
- 想看单点样本里坐标 cue 是否真的扛起桥接：优先审 `single_point_coordinate_integration_priority`
- 想看后半段收尾是否容易伪闭环：优先审 `high_closure_depth_priority`
- 想看 visible-only 边界是否退化：优先审 `visible_only_boundary_priority`
- 想看多机制多点构造是否容易 route drift：优先审 `mixed_mechanism_multi_point_priority`

### 按回归目的改动

- 快速回放最近固定失败/成功样本：先跑 `fixed_v104sample`
- 改的是全局 bridge 语义、goal finish 收尾、或 generation audit 这类跨 goal 规则：优先跑 `quality_review_v1` 的 `quick6_goal_aux_balanced` 或 `all`
- 改的是语义审读口径或需要人工/Codex 重点复核的规则：优先看 `semantic_review_priority`

### 当前仍未覆盖到 subset 级的维度

- `aux_shape` 目前已经写在 manifest `records[*].aux_shape` 里，但还没有全部拆成稳定 subset
- 如果改动强依赖某个 `aux_shape` 或某类失败模式，应先用 `focus_tags` / `notes` 手工选样，再考虑把该维度升级成新的固定 subset
