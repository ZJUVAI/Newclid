# GenesisGeo

[Dataset](https://huggingface.co/datasets/ZJUVAI/GenesisGeo) | [Model](https://huggingface.co/ZJUVAI/GenesisGeo) | [Paper](https://arxiv.org/abs/2509.21896)

GenesisGeo is a neuro-symbolic geometry theorem proving project based on the technical report [*GenesisGeo: Technical Report*](https://arxiv.org/abs/2509.21896). Built on Newclid/DDAR, the repository contains a synthetic geometry data generation pipeline, text and vision-language training workflows, and benchmark evaluation code for Olympiad-style geometry proving.

The paper introduces GenesisGeo-1M and GenesisGeo-2B, and reports 29/30 on IMO-30, 63/95 on IMO-95, and 278/409 on HAGeo-409.

## Setup

```bash
git clone https://github.com/ZJUVAI/GenesisGeo.git
cd GenesisGeo
uv venv .venv
source .venv/bin/activate
uv pip install -e .
uv sync
```

## Data Generation

```bash
python src/newclid/generation/pipeline.py --n_clauses=10 --n_samples=1000000 --n_threads=20 --aux_only 2
```

Common options: `--aux_only 0|1|2`, `--dir ./datasets`, `--img 0|1|2|3`, `--construction_config path/to/config.json`, `--no-add_auxiliary`, `--no-prune`.

## Training

Text SFT:

```bash
bash scripts/train_eval.sh
```

VLM SFT:

```bash
bash scripts/train_vlm.sh
```

VLM pretraining + evaluation:

```bash
bash scripts/train_vlm_pt.sh
```

Qwen3.5 / alternative VLM pipeline:

```bash
bash scripts/train_eval_vlm54.sh
```

Before running, update dataset paths, checkpoints, output directories, and `CUDA_VISIBLE_DEVICES` in the scripts.

## Evaluation

Text model:

```bash
python scripts/evaluation.py --problems_path benchmarks/imo_ag_30.txt --model_path ZJUVAI/GenesisGeo --max_workers 80 --decoding_size 32 --beam_size 512 --search_depth 4
```

Text ensemble:

```bash
python scripts/evaluation.py --problems_path benchmarks/imo_ag_30.txt --model_path ZJUVAI/GenesisGeo-250915a ZJUVAI/GenesisGeo-250915b --max_workers 80 --decoding_size 32 --beam_size 512 --search_depth 4
```

Qwen3.5 text:

```bash
python scripts/evaluation.py --problems_path benchmarks/dev_imo.txt --model_path /path/to/checkpoint --agent qwen35_text --max_workers 40 --decoding_size 32 --beam_size 512 --search_depth 4
```

VLM:

```bash
python scripts/evaluation_vlm.py --problems_path benchmarks/hageo_409_full.txt --model_path /path/to/checkpoint --agent vlm --max_workers 40 --decoding_size 32 --beam_size 512 --search_depth 4 --timeout 3600
```

Qwen3.5 multimodal:

```bash
python scripts/evaluation_vlm.py --problems_path benchmarks/dev_imo.txt --model_path /path/to/checkpoint --agent qwen35 --max_workers 40 --decoding_size 32 --beam_size 512 --search_depth 4
```

Benchmarks are under `benchmarks/`, including `imo_ag_30.txt`, `imo_95.txt`, `hageo_409_full.txt`, `dev_imo.txt`, and `dev_jgex.txt`.

## Acknowledgements

- [AlphaGeometry](https://github.com/google-deepmind/alphageometry)
- [Newclid](https://arxiv.org/abs/2411.11938)
- [Qwen](https://github.com/QwenLM)
- [ms-swift](https://github.com/modelscope/ms-swift)

## Citation

```bibtex
@article{zhu2025genesisgeo,
  title={GenesisGeo: Technical Report},
  author={Zhu, Minfeng and Wang, Zi and Ji, Sizhe and Du, Zhengtong and Tai, Shengqiang and Ke, Junming and Deng, Xiao and Yin, Zanlang and Huang, Xiuqi and Wang, Heyu and Chen, Wei},
  journal={arXiv preprint arXiv:2509.21896},
  year={2025}
}
```
