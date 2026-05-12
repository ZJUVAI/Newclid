# Generation Module

Geometry problem generation module with clean architecture and parallel processing.

## Overview

Generates synthetic geometry problems for automated theorem proving. Samples geometric constructions, adds auxiliary points, filters valid goals, and produces problems with proofs.

## Features

- **Clause Generation**: Configurable geometric constructions
- **Auxiliary Points**: Automatic discovery of meaningful auxiliary points
- **Goal Filtering**: Identifies valid and interesting theorem goals
- **Proof Validation**: Verifies problems have valid proofs
- **Parallel Processing**: Ray-based batch generation
- **External Configs**: JSON-based construction profiles

## Directory Structure

```
generation/
├── __init__.py              # Public API exports
├── auxiliary/               # Auxiliary point utilities
│   ├── utils.py            # Constants and basic utilities
│   ├── line_utils.py       # Line operations
│   ├── circle_utils.py     # Circle operations
│   ├── intersection.py     # Geometric constructions
│   └── find_points.py      # Main entry point
├── constructions.py         # Construction config loading
├── constructions.json       # Default construction sets
├── filter.py                # Goal filtering
├── pipeline.py              # Batch generation and CLI
├── point_naming.py          # Point name generator
├── sampler.py               # Clause sampling
├── statistics.py            # Statistics and reporting
├── worker.py                # Ray worker
└── writer.py                # Data writing and image generation
```

## Public API

```python
from newclid.generation import (
    ProblemSampler,      # Sample geometric constructions
    ProblemWorker,       # Process single problems
    ProblemPipeline,     # Batch generation pipeline
    GoalFilter,          # Filter valid goals
    Statistics,          # Statistics collection
    get_first_predicate, # Extract first predicate
)
```

### Advanced Usage

Internal modules (may change without notice):

```python
# Construction utilities
from newclid.generation.constructions import (
    resolve_construction_config,
    load_default_construction_config,
)

# Auxiliary geometry
from newclid.generation.auxiliary import add_potential_points
```

## Quick Start

### Basic Usage

```python
from newclid.generation import ProblemSampler

sampler = ProblemSampler(seed=42)
problem = sampler.generate(
    length=15,
    add_auxiliary=True,
    max_auxiliary_points=2,
    prune=True,
)
print(problem)
```

### Batch Generation

```python
from newclid.generation import ProblemPipeline

pipeline = ProblemPipeline(
    n_clauses=15,
    n_threads=8,
    n_samples=1000,
    output_dir="./datasets",
    using_log=True,
    using_exp=False,
)
pipeline.generate()
```

### CLI Usage

```bash
# Basic generation
python -m newclid.generation.pipeline \
  --n_clauses 15 \
  --n_samples 1000 \
  --n_threads 8 \
  --dir ./datasets

# With external construction config
python -m newclid.generation.pipeline \
  --construction_config ./experiments/profiles.json \
  --n_samples 1000

# Disable auxiliary points
python -m newclid.generation.pipeline \
  --no-add_auxiliary \
  --n_samples 1000

# Override CSolver equation settings
python -m newclid.generation.pipeline \
  --no-using_log \
  --using_exp \
  --n_samples 1000

# Generate with images
python -m newclid.generation.pipeline \
  --img 3 \
  --n_samples 100
```

### CLI Parameters

**General:**
- `--log_level`: Logging level (debug/info/warning/error)
- `--dir`: Output directory (default: ./datasets)

**Core:**
- `--n_clauses`: Number of clauses (default: 15)
- `--n_samples`: Number of samples (default: 10000)
- `--n_threads`: Parallel workers (default: 10)
- `--timeout`: Task timeout in seconds (default: 3600)
- `--max_level`: DDAR search depth (default: 500)
- `--using_log` / `--no-using_log`: Toggle CSolver log equations (default: enabled)
- `--using_exp` / `--no-using_exp`: Toggle CSolver exponential equations (default: disabled)
- `--construction_config`: External JSON config path

**Auxiliary Points:**
- `--add_auxiliary` / `--no-add_auxiliary`: Enable/disable auxiliary points (default: enabled)
- `--max_auxiliary_points`: Max auxiliary points per problem (default: 2)
- `--aux_only`: Filter mode (0=all, 1=mixed, 2=aux only)

**Output:**
- `--img`: Image mode (0=none, 1=annotated, 2=plain, 3=both)
- `--prune` / `--no-prune`: Enable/disable clause pruning (default: enabled)
- `--remove_coords`: Remove coordinates from output
- `--clear`: Clear old dataset files

## External Construction Config

Example `profiles.json`:

```json
{
  "construction_sets": {
    "basic_small": ["triangle", "rectangle"],
    "intersect_light": ["on_line", "on_circle"],
    "single_light": ["midpoint", "foot"]
  },
  "step1_sets": ["basic_small"],
  "step2_intersect_sets": ["intersect_light"],
  "step3_single_sets": ["single_light"]
}
```

## Module Descriptions

**auxiliary/** - Auxiliary point discovery
- `utils.py`: Constants and coordinate utilities
- `line_utils.py`: Line extraction and collinearity checks
- `circle_utils.py`: Circle detection and validation
- `intersection.py`: All geometric constructions (intersections, midpoints, reflections, feet)
- `find_points.py`: Main entry point for finding auxiliary points

**sampler.py** - Clause generation
- Three-stage sampling (basic → intersect → single)
- Numerical validation
- Dependency management via ClauseDAG
- Pruning and auxiliary point insertion

**worker.py** - Ray worker
- Per-problem generation
- Solver building and proof validation
- Applies construction profiles

**pipeline.py** - Main orchestrator
- Ray worker management
- JSONL output
- Optional image generation

**writer.py** - Data writing
- Asynchronous figure drawing with Ray
- Ordered data writing
- Manages pending draw tasks and write buffers

**filter.py** - Goal filtering
- Filters trivial/redundant goals
- Scores goal interestingness

**statistics.py** - Statistics
- Collects generation metrics
- Generates JSON reports

## Performance

Typical performance (multi-core):
- Single problem: ~1-2 seconds
- Batch (1000 problems, 8 workers): ~5-10 minutes
- Average: ~2-5 samples/second

## Troubleshooting

**Import errors:**
```bash
export PYTHONPATH=./src:$PYTHONPATH
```

**Ray errors:**
```bash
ray stop
```

**Memory issues:**
- Reduce `--n_threads`
- Process in smaller batches

## Recent Changes

### Pipeline Refactoring (2026-03)
- Extracted writer logic to `writer.py`
- Removed unused parameters (`min_proof_steps`, `min_clauses_num`)
- Simplified boolean arguments with `BooleanOptionalAction`
- Reorganized CLI parameters by category
- Reduced pipeline.py from 511 to 309 lines (40% reduction)

### Auxiliary Module Cleanup (2026-03)
- Merged `primitives.py` + `distance.py` → `utils.py`
- Renamed `finder.py` → `find_points.py`
- Moved geometric constructions to `intersection.py`
- Reduced public API from 18 to 1 export

### Construction Config Externalization (2026-03)
- Moved default config to `constructions.json`
- Added `--construction_config` for external profiles
- Enabled construction-set experiments

## License

Part of the GenesisGeo project.
