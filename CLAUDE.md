# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GenesisGeo is a neuro-symbolic geometric theorem prover reproducing AlphaGeometry. It combines a C++ symbolic deduction engine (DDAR) with neural language models for auxiliary point proposals. Achieves 24/30 on IMO-AG-30 benchmark.

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
python scripts/evaluation.py --problems_path benchmarks/imo_ag_30.txt \
  --model_path ZJUVAI/GenesisGeo --max_workers 80 --decoding_size 32 \
  --beam_size 512 --search_depth 4

# Train model (uses ms-swift framework)
bash scripts/train_eval.sh

# Run CLI solver
newclid --problem-name <name> --env <env_dir> --agent ddarn
```

## Architecture

### Core Components

**DDAR Symbolic Engine** (`src/newclid/DDAR/`) - C++ implementation:
- `solver/ddar.cpp`: Main deduction loop applying geometric rules exhaustively
- `matcher.cpp`: Matches theorems to current proof state (optimized for 120x speedup)
- `predicate/`: 30+ geometric predicates (cong, para, cyclic, eqangle, eqratio, etc.)
- `ar/`: Algebraic reasoning - linear systems and equation manipulation

**Python API** (`src/newclid/`):
- `api.py`: `GeometricSolverBuilder` (builder pattern) and `GeometricSolver` classes
- `proof.py`: `ProofState` manages dependency graph and numerical geometry
- `match_theorems.py`: Python-side theorem matching

**Deductive Agents** (`src/newclid/agent/`):
- `ddarn.py`: Breadth-first exhaustive symbolic deduction
- `lm.py`: `LMAgent` uses Qwen3 LLM for auxiliary point proposals with beam search
- All inherit from `DeductiveAgent` interface in `agents_interface.py`

**Data Generation** (`src/newclid/generation/`):
- `generate.py`: Ray-based distributed generation orchestrator
- `clause_generation.py`: Random geometric construction sampling
- `problem_worker.py`: Worker processes for parallel problem generation

**Proof Scout** (`src/newclid/proof_scout/`):
- `core/`: Core graph structures (ProofGraph, GraphPruner, FilterAndPruneEngine) - no ML dependencies
- `extraction/`: Rule extraction utilities (RuleExtractor) - no ML dependencies
- `ml/`: ML pipeline (scout_pipeline, model_utils, data_processor) - requires torch
- `docs/`: Documentation

### Data Flow

1. Problem parsed from JGEX format into `ProblemJGEX`
2. `ProofState` built with numerical coordinates and dependency graph
3. `DeductiveAgent.run()` applies rules until goal proven or timeout
4. For `LMAgent`: LLM proposes auxiliary constructions, DDAR verifies each

### Problem Format (JGEX)

```
problem_name
a : ; b : ; c : cong a b b c [000] ; d : perp b c b d [001] ? eqangle a b c d e f g h
```

Constructions before `?`, goals after. Predicates: `cong`, `para`, `perp`, `coll`, `cyclic`, `eqangle`, `eqratio`, `midp`, etc.

## Key Patterns

- DDAR runs in subprocess isolation to prevent memory leaks
- Ray used for parallel data generation and evaluation
- Numerical validation prevents floating-point errors in proofs
- Beam search with multiple LLM candidates for auxiliary construction proposals

## Important Notes (铁律)

**Git Workflow Rules**:
- **Push**: 只推送到 `origin` 远端仓库，除非有特殊说明
- **GenesisGeo 远端**: 仅用于拉取信息、对齐引擎开发进度，不进行推送
- 示例: `git push origin <branch>` ✓ | `git push GenesisGeo <branch>` ✗

**DDAR Code Synchronization**: When there are differences in the DDAR directory (`src/newclid/DDAR/`), always use the version from the GenesisGeo remote repository as the authoritative source, unless explicitly stated otherwise. To sync:

```bash
git fetch GenesisGeo
git checkout GenesisGeo/main -- src/newclid/DDAR/
```

---

## Done Tasks

- 2026-01-28: 配置 git 远端仓库（origin 指向 Try-GeoDiscovery-Using-CC）
- 2026-01-28: 更新 /continue 命令，加入 plan 模式流程
- 2026-01-28: 创建 /summarize 命令
- 2026-01-28: 优化 /summarize 命令（改为询问确认 compact 状态）
- 2026-01-28: 创建 Discovery conda 环境（Python 3.10 + PyTorch 2.5.1+cu121），编译所有 C++ 扩展
- 2026-01-28: 分离ML依赖与纯引擎依赖（pyproject.toml分组、api.py延迟导入、__init__.py懒加载ML agents）
- 2026-01-29: 重组 proof_scout 模块结构（core/extraction/ml 三层分离，实现懒加载避免加载 torch/pydot）
- 2026-01-29: 从 GenesisGeo/evaluation 分支同步 benchmarks（含 _with_coordinates 格式文件）

## Current Task

(No active task)

## Todolist

- [x] 将模型训练、推理的代码和引擎的依赖用合适的形式分离，我希望在进行只涉及引擎推理的时候，不需要预先加载很多类似Torch这样的包，能够更轻盈地测试与开发
- [x] 整理目前和知识发现/定理提取/proof_scout有关的所有代码，重新组织，重新放在proof_scout这个目录下
- [x] 从GenesisGeo远端仓库的Evaluation分支拿到用来测试的benchmarks，添加到当前仓库中
- [ ] 打通从数据生成（generation）到定理发现(proof_scout)再到测试评估的pipeline

## Temporary Interaction Area

当前 Git 远端配置：
- origin → git@github.com:ZhengtongDu/Try-GeoDiscovery-Using-CC.git
- GenesisGeo → git@github.com:ZJUVAI/GenesisGeo.git

Discovery 环境配置：
- 环境路径: /root/miniconda3/envs/Discovery
- Python: 3.10
- PyTorch: 2.5.1+cu121
- 所有 C++ 扩展已编译完成（matchinC, geometry, DDAR）

proof_scout 模块结构：
- core/: 核心图结构，无 ML 依赖
- extraction/: 规则提取，无 ML 依赖
- ml/: ML 流水线，需要 torch
- data_discovery/ 已废弃，保留向后兼容层

