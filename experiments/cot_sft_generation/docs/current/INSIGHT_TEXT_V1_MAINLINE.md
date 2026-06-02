# Insight Text V1 Mainline

`insight_text_v1` is the text-only sibling of the default insight mainline.

It keeps the same insight-first target as `insight_image_v1`, but removes image and coordinate inputs from generation, validation, artifacts, and the final training sample.

## Contract

- planner input: formal problem text, visible facts, approved auxiliary construction, and `InsightSlots`
- writer input: text-only approved plan
- planner and writer do not receive `image_url`
- prompts do not include visible point coordinates
- final dataset omits `image_path`
- final dataset never exports visible point coordinates

## Validation

- source audits do not require a resolvable image path
- source audits do not require visible point coordinates
- relation grounding falls back to point names derived from the public formal problem text
- text-only checks reject coordinate leakage in planner or writer outputs
- planner fallback and writer fail-closed behavior match `insight_image_v1`

## Entrypoint

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --generation-style insight_text_v1
```
