<div align="center">

# GenesisGeo

**Neuro-Symbolic Geometry Theorem Proving at Olympiad Level**

[![Paper](https://img.shields.io/badge/arXiv-2509.21896-b31b1b.svg)](https://arxiv.org/abs/2509.21896) [![Dataset](https://img.shields.io/badge/🤗_Dataset-GenesisGeo-blue.svg)](https://huggingface.co/datasets/ZJUVAI/GenesisGeo) [![Model](https://img.shields.io/badge/🤗_Model-GenesisGeo-blue.svg)](https://huggingface.co/ZJUVAI/GenesisGeo) [![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)

</div>

## Overview

GenesisGeo is a neuro-symbolic system that proves geometry theorems by combining a symbolic deduction engine (DDARN) with a neural language model. It is a full-stack reproduction and extension of [AlphaGeometry](https://www.nature.com/articles/s41586-023-06747-5), built on top of [Newclid/DDAR](https://arxiv.org/abs/2411.11938).

**Highlights:**

- Synthetic data generation pipeline producing **3 million** unique geometry problems with proof traces
- Enhanced DDARN engine with **120x** speedup over the original implementation
- Neuro-symbolic prover fine-tuned from **Qwen3-VL-2B**

## CoT SFT Mainline

The auxiliary-construction CoT pipeline now defaults to `insight_image_v1`.

- Mainline default: `insight_image_v1`
- Sibling text-only mainline: `insight_text_v1`
- Legacy / benchmark / fallback: `dossier_v1`
- Older compatibility route: `model_evidence_legacy`

Both insight variants target `insight -> aux`, not `aux -> full closure`.
Entry docs:

- [CURRENT_DESIGN.md](experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)
- [INSIGHT_IMAGE_V1_MAINLINE.md](experiments/cot_sft_generation/docs/current/INSIGHT_IMAGE_V1_MAINLINE.md)
- [INSIGHT_TEXT_V1_MAINLINE.md](experiments/cot_sft_generation/docs/current/INSIGHT_TEXT_V1_MAINLINE.md)
- [DOSSIER_V1_MAINLINE.md](experiments/cot_sft_generation/docs/current/DOSSIER_V1_MAINLINE.md)

## Results (GenesisGeo-2B)

| Benchmark | Score |
|-----------|:-----:|
| IMO-AG-30 | **29/30** |
| IMO-95 | **63/95** |
| HAGeo-409 | **278/409** |


## Setup

```bash
git clone https://github.com/ZJUVAI/GenesisGeo.git
cd GenesisGeo
uv venv
source .venv/bin/activate
uv sync --extra full
```

## Data Generation

Generate synthetic geometry problems with proof traces:

```bash
python src/newclid/generation/pipeline.py \
  --n_clauses 10 \
  --n_samples 1000000 \
  --n_threads 20 \
  --aux_only 2 \
  --seed_cache
```

### General Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--n_clauses` | `15` | Max number of construction clauses per problem |
| `--n_samples` | `10000` | Total number of problems to generate |
| `--n_threads` | `10` | Number of parallel Ray workers |
| `--timeout` | `3600` | Per-task timeout in seconds |
| `--max_level` | `500` | Maximum DDAR search depth |
| `--base_seed` | `42` | Base random seed for generation |
| `--log_level` | `info` | Logging level (`debug`, `info`, `warning`, `error`) |
| `--construction_config` | `None` | Path to JSON config for construction sets and sampler steps |
| `--seed_cache` | `off` | Enable seed cache to skip seeds without real auxiliary points |

### Auxiliary Point Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--add_auxiliary` / `--no-add_auxiliary` | `enabled` | Whether to add auxiliary points during generation |
| `--max_auxiliary_points` | `2` | Maximum auxiliary points per problem |
| `--aux_only` | `0` | Data filter: `0` = all, `1` = include non-aux at 0.1 prob, `2` = aux-only |

### Output Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--dir` | `./datasets` | Output directory |
| `--img` | `0` | Image mode: `0` = none, `1` = annotated only, `2` = plain only, `3` = both |
| `--direct_png` / `--no-direct_png` | `enabled` | Save PNG directly or keep the legacy `svg -> png` pipeline |
| `--img_pixels` | `512` | Output image width in pixels |
| `--prune` / `--no-prune` | `enabled` | Prune clauses to keep only the deepest clause chain |
| `--remove_coords` | `off` | Remove coordinate information from output |
| `--clear` | `off` | Clear old dataset files before generation |

## Training

### Text SFT

```bash
bash scripts/train_eval.sh
```

### VLM SFT

```bash
bash scripts/train_vlm.sh
```

### VLM Pretraining + Evaluation

```bash
bash scripts/train_vlm_pt.sh
```

### Qwen3.5 / Alternative VLM Pipeline

```bash
bash scripts/train_eval_vlm54.sh
```

> **Note:** Update dataset paths, checkpoint directories, output paths, and `CUDA_VISIBLE_DEVICES` in the scripts before running.

## Evaluation

### Text Model

```bash
python scripts/evaluation.py \
  --problems_path benchmarks/imo_ag_30.txt \
  --model_path ZJUVAI/GenesisGeo \
  --max_workers 40 \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4
```

### Text Ensemble

```bash
python scripts/evaluation.py \
  --problems_path benchmarks/imo_ag_30.txt \
  --model_path ZJUVAI/GenesisGeo-250915a ZJUVAI/GenesisGeo-250915b \
  --max_workers 80 \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4
```

### Qwen3.5 Text

```bash
python scripts/evaluation.py \
  --problems_path benchmarks/dev_imo.txt \
  --model_path /path/to/checkpoint \
  --agent qwen35_text \
  --max_workers 40 \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4
```

### VLM

```bash
python scripts/evaluation.py \
  --problems_path benchmarks/hageo_409.txt \
  --model_path /path/to/checkpoint \
  --agent vlm \
  --max_workers 40 \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --timeout 3600
```

### Qwen3.5 Multimodal

```bash
python scripts/evaluation.py \
  --problems_path benchmarks/dev_imo.txt \
  --model_path /path/to/checkpoint \
  --agent qwen35_vl \
  --max_workers 40 \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4
```

### Benchmarks

| File | Description |
|------|-------------|
| `benchmarks/imo_ag_30.txt` | IMO-AG-30 (30 problems) |
| `benchmarks/imo_95.txt` | IMO-95 (95 problems) |
| `benchmarks/hageo_409.txt` | HAGeo-409 (409 problems) |
| `benchmarks/jgex_ag_231.txt` | JGEX-AG-231 (231 problems) |
| `benchmarks/dev_imo.txt` | Small IMO development subset |
| `benchmarks/dev_jgex.txt` | Small JGEX development subset |
| `benchmarks/examples.txt` | Mixed example and debugging problems |
| `benchmarks/larger_imo_eval.txt` | Extended IMO-style evaluation set |
| `benchmarks/testing_minimal_rules.txt` | Minimal regression checks for individual rules |

## Project Structure

```
GenesisGeo/
├── src/newclid/                    # Main source code
│   ├── __main__.py                 # CLI entry point
│   ├── api.py                      # GeometricSolver interface
│   ├── proof.py                    # Proof state management
│   ├── agent/                      # Reasoning agents
│   │   ├── ddarn.py                # DDARN symbolic engine
│   │   ├── lm.py                   # Language model agent
│   │   └── vlm.py                  # Vision-language model agent
│   ├── generation/                 # Data generation pipeline
│   │   ├── pipeline.py             # ProblemPipeline orchestrator
│   │   ├── sampler.py              # Geometry construction sampling
│   │   ├── worker.py               # Per-problem processing
│   │   ├── writer.py               # Data writing & image rendering
│   │   ├── filter.py               # Goal filtering
│   │   ├── point_naming.py         # Point naming management
│   │   ├── constructions.py        # Construction type constants
│   │   ├── statistics.py           # Generation statistics
│   │   └── auxiliary/              # Auxiliary point discovery
│   ├── DDAR/                       # C++ symbolic engine
│   ├── dependencies/               # Dependency graph management
│   ├── formulations/               # Problem representations
│   ├── numerical/                  # Numerical geometry
│   ├── algebraic_reasoning/        # Algebraic reasoning
│   └── predicates/                 # Geometry predicates
├── scripts/                        # Training & evaluation scripts
├── tests/                          # Test suite
├── benchmarks/                     # Benchmark problem sets
└── docs/                           # Documentation
```

## Acknowledgements

- [AlphaGeometry](https://github.com/google-deepmind/alphageometry) — the original neuro-symbolic geometry prover
- [Newclid](https://arxiv.org/abs/2411.11938) — the DDAR symbolic engine
- [Qwen](https://github.com/QwenLM) — base language models
- [ms-swift](https://github.com/modelscope/ms-swift) — training framework

## Citation

```bibtex
@article{zhu2025genesisgeo,
  title={GenesisGeo: Technical Report},
  author={Zhu, Minfeng and Wang, Zi and Ji, Sizhe and Du, Zhengtong and Tai, Shengqiang and Ke, Junming and Deng, Xiao and Yin, Zanlang and Huang, Xiuqi and Wang, Heyu and Chen, Wei},
  journal={arXiv preprint arXiv:2509.21896},
  year={2025}
}
```
