# CoT SFT Document Boundaries

This file is the edit contract for `experiments/cot_sft_generation`.

## Hard Scope Boundary

- Do not modify anything outside `experiments/cot_sft_generation/` when working on this pipeline.
- In particular, [AGENTS.md](/root/GenesisGeo-cot/AGENTS.md) is outside this subtree and is not editable from here.

## Immutable Docs

These are the documents an agent must not rewrite on its own:

- [AGENTS.md](/root/GenesisGeo-cot/AGENTS.md)
  - external repo-level operating contract
- [immutable/DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
  - immutable data-quality target for this pipeline
- the mirrored `## 数据质量目标` section in [README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/README.md)
  - keep it aligned with the immutable copy above

If a requested change would alter the meaning of those requirements, stop and ask the user instead of editing them.

## Agent-Editable Docs

Everything else inside `experiments/cot_sft_generation/` is agent-editable by default, including:

- [README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/README.md)
  - except the mirrored immutable data-quality section
- [docs/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/README.md)
- [docs/current/](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current)
- [docs/reference/](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference)
- [docs/maintenance/](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/maintenance)
- [docs/history/](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/history)
- [benchmarks/](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks)
- [generated/](/root/GenesisGeo-cot/experiments/cot_sft_generation/generated)
  - generated evidence may be added, reviewed, or superseded

## Practical Rule

Before editing a document, classify it first:

1. Is it outside `experiments/cot_sft_generation/`?
2. Is it one of the immutable items above?
3. If neither, it is editable and should be updated when code, benchmark usage, or review protocol changes.
