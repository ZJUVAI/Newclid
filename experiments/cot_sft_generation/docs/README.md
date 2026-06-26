# CoT SFT Docs

`experiments/cot_sft_generation/docs/` 现在的作用仍然是：在新会话开始改文件之前，先把文档边界和当前主线讲清楚。

## 先读这些

- [DOC_BOUNDARIES.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/DOC_BOUNDARIES.md)
  - 这个子树的编辑边界
  - 哪些文档是 immutable
  - 哪些文档可以直接更新
- [immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
  - 这条 pipeline 的不可变数据质量目标

## 可编辑文档

### 当前状态

- [current/INSIGHT_IMAGE_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_IMAGE_V1_MAINLINE.md)
  - image sibling mainline，对应 `insight_image_v1`
- [current/INSIGHT_TEXT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_TEXT_V1_MAINLINE.md)
  - text-only sibling mainline，对应 `insight_text_v1`
- [current/BACKTRACE_TEXT_V2_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/BACKTRACE_TEXT_V2_MAINLINE.md)
  - 默认 text-only backtrace writer-only mainline，对应 `backtrace_text_v2`
- [current/DOSSIER_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/DOSSIER_V1_MAINLINE.md)
  - `dossier_v1` 的 legacy / benchmark / fallback 说明
- [current/CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)
  - 当前代码实际上怎么跑
- [current/STATUS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/STATUS.md)
  - 当前证据、当前风险、当前与目标之间的 gap

### Reference

- [reference/ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/ARTIFACT_SCHEMA.md)
  - 稳定的 run / item artifact 字段协议
- [reference/SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)
  - 语义审读 checklist 与 `issue_codes`

### Maintenance And History

- [maintenance/MAINTENANCE_PLAYBOOK.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/maintenance/MAINTENANCE_PLAYBOOK.md)
  - 代码或 review 逻辑变化时需要一起更新什么
- [history/EXPERIMENT_LOG.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/history/EXPERIMENT_LOG.md)
  - 按时间顺序记录实验

## 推荐阅读顺序

### 开新一轮主线迭代

1. [DOC_BOUNDARIES.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/DOC_BOUNDARIES.md)
2. [immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
3. [current/INSIGHT_IMAGE_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_IMAGE_V1_MAINLINE.md)
4. [current/INSIGHT_TEXT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_TEXT_V1_MAINLINE.md)
5. [current/BACKTRACE_TEXT_V2_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/BACKTRACE_TEXT_V2_MAINLINE.md)
6. [benchmarks/quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)

### 更新实现或 schema

1. [DOC_BOUNDARIES.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/DOC_BOUNDARIES.md)
2. [current/CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)
3. [reference/ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/ARTIFACT_SCHEMA.md)
4. [maintenance/MAINTENANCE_PLAYBOOK.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/maintenance/MAINTENANCE_PLAYBOOK.md)

### 跑 review-oriented regression

1. [immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
2. [benchmarks/quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)
3. [reference/SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)
