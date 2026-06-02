# Dossier V1 Mainline

`dossier_v1` is the legacy / benchmark route.

It is no longer the default mainline. For current insight-family work, read:

- [INSIGHT_IMAGE_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_IMAGE_V1_MAINLINE.md)
- [INSIGHT_TEXT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_TEXT_V1_MAINLINE.md)

## What It Is Still For

- benchmark comparisons against the older fuller-closure contract
- replaying historical artifact runs
- proof-DAG-oriented debugging and scripted regression

## What It Is Not

- the default training mainline
- the text-only insight path
- the place to add new mainline contracts

## Entrypoint

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --generation-style dossier_v1
```
