# Build & Commands

## Build & Setup

```bash
# Install package
pip install -e .

# Compile C++ Python extensions (required)
cd src/newclid
c++ -O3 -Wall -shared -std=c++14 -march=native -funroll-loops -flto \
  `python3 -m pybind11 --includes` matchinC.cpp \
  -o matchinC`python3-config --extension-suffix` -fPIC

cd dependencies
c++ -O3 -Wall -shared -std=c++14 -march=native -funroll-loops -flto \
  `python3 -m pybind11 --includes` geometry.cpp \
  -o geometry`python3-config --extension-suffix` -fPIC

# Build DDAR C++ components
cd src/newclid/DDAR && bash build.sh
```

## Test Commands

```bash
# Run all tests with coverage (76% minimum required)
pytest tests --cov=src --cov-fail-under=76

# Run specific test file
pytest tests/test_direct_solver.py
```

## Lint Commands

```bash
ruff check src/newclid --fix
ruff format src/newclid
```

## Key Commands

```bash
# Generate synthetic data (5M samples, 30 threads)
python src/newclid/generation/generate.py --n_threads=30 --n_samples=5000000 --log_level=info --timeout=3600

# Evaluate on benchmark
python scripts/evaluation.py --problems_path benchmarks/core/imo_ag_30.txt \
  --model_path ZJUVAI/GenesisGeo --max_workers 80 --decoding_size 32 \
  --beam_size 512 --search_depth 4

# Train model (uses ms-swift framework)
bash scripts/train_eval.sh

# Run CLI solver
newclid --problem-name <name> --env <env_dir> --agent ddarn
```

## Discovery Pipeline Commands

```bash
# Run pipeline (Stage 1-2, save intermediates)
python scripts/discovery_pipeline.py \
    --input <input.jsonl> \
    --output outputs/experiments/YYYYMMDD_experiment_name \
    --skip_stage3 --skip_stage4 \
    --max_workers 30 --save_intermediates

# Run rule reduction (Stage R0-R3)
python scripts/reduce_rules.py \
    --rules outputs/experiments/.../discovered_rules.txt \
    --source-data outputs/experiments/.../intermediates/step1e_rules_stats.json \
    --output outputs/experiments/.../reduction \
    --max-premises 10 --timeout 60 --n-workers 50 --seed 42

# Generate filtering report
python scripts/analyze_filtering.py \
    --experiment outputs/experiments/YYYYMMDD_experiment_name
```

更多命令历史参见 `memory/command_history.md`。
