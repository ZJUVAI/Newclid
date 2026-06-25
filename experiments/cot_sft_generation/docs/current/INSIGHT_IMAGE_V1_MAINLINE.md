# Insight Image V1 Mainline

`insight_image_v1` is now the image sibling CoT SFT mainline.

It keeps the current insight-first target:

1. identify the visible gap
2. state the helper effect the auxiliary construction must create
3. choose the auxiliary construction

This remains a stage-focused mainline, not the long-term full-closure target from [DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md).

## Contract

- planner input: image, formal problem text, visible facts, visible point coordinates, approved auxiliary construction, and `InsightSlots`
- writer input: image-aware approved plan plus visible point coordinates
- final dataset: includes `image_path`
- final dataset: never exports visible point coordinates

## Validation

- coordinate-aware prompt and thinking checks remain enabled
- planner may fall back to a scripted insight plan
- writer remains fail-closed
- hard export gating still blocks `no_proof_echo` and `visible_only_boundary`

## Entrypoint

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --generation-style insight_image_v1
```
