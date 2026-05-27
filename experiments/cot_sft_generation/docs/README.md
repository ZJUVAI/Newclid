# CoT SFT Docs

`experiments/cot_sft_generation/docs/` now has one job: make the document boundary explicit before any new session starts editing files.

## Read This First

- [DOC_BOUNDARIES.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/DOC_BOUNDARIES.md)
  - the edit boundary for this subtree
  - which documents are immutable
  - which documents an agent may update without asking
- [immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
  - the immutable data-quality target for this pipeline

## Editable Docs

### Current State

- [current/INSIGHT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_V1_MAINLINE.md)
  - the default mainline for `insight_v1`
- [current/DOSSIER_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/DOSSIER_V1_MAINLINE.md)
  - the legacy / benchmark / fallback track for `dossier_v1`
- [current/CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)
  - what the code actually does today
- [current/STATUS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/STATUS.md)
  - current evidence, current risks, current gap to target

### Reference

- [reference/ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/ARTIFACT_SCHEMA.md)
  - stable run and item artifact fields
- [reference/SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)
  - semantic review checklist and `issue_codes`

### Maintenance And History

- [maintenance/MAINTENANCE_PLAYBOOK.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/maintenance/MAINTENANCE_PLAYBOOK.md)
  - what to update together when code or review logic changes
- [history/EXPERIMENT_LOG.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/history/EXPERIMENT_LOG.md)
  - chronological experiment record

## Recommended Reading Orders

### Starting A New Iteration Session

1. [DOC_BOUNDARIES.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/DOC_BOUNDARIES.md)
2. [immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
3. [current/INSIGHT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_V1_MAINLINE.md)
4. [benchmarks/quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)

### Updating Implementation Or Schema

1. [DOC_BOUNDARIES.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/DOC_BOUNDARIES.md)
2. [current/CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)
3. [reference/ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/ARTIFACT_SCHEMA.md)
4. [maintenance/MAINTENANCE_PLAYBOOK.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/maintenance/MAINTENANCE_PLAYBOOK.md)

### Running Review-Oriented Regression

1. [immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
2. [benchmarks/quality_review_v1/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/README.md)
3. [reference/SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)
