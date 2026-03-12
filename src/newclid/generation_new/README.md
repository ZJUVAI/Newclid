# Generation Module

A refactored and optimized geometry problem generation module with clean architecture and improved maintainability.

## Overview

This module generates synthetic geometry problems for automated theorem proving. It samples geometric constructions, optionally adds auxiliary points, filters valid goals, and produces problems with proofs.

The current implementation uses:
- `sampler.py` for clause sampling and DAG pruning
- `worker.py` for single-problem generation and proof validation
- `pipeline.py` for batch generation and CLI execution
- `constructions.py` plus `constructions.json` for construction-set and profile resolution
- `constructions_notes.md` for preserved comments and disabled-entry notes from the old inline construction lists

## Features

- **Clause Generation**: Creates geometric constructions using configurable construction configs
- **Point Enhancement**: Automatically discovers and adds meaningful auxiliary points
- **Goal Filtering**: Identifies valid and interesting theorem goals
- **Proof Validation**: Verifies problems have valid proofs
- **Parallel Processing**: Uses Ray for efficient batch generation
- **Profile-Driven Sampling**: Supports external JSON configs for construction-set experiments

## Directory Structure

```text
generation_new/
├── __init__.py                 # Module exports
├── auxiliary/                  # Auxiliary geometry utilities
│   ├── __init__.py
│   ├── primitives.py
│   ├── distance.py
│   ├── line_utils.py
│   ├── circle_utils.py
│   ├── intersection.py
│   └── finder.py
├── constructions.py            # Construction config loading and profile resolution
├── constructions.json          # Default construction sets and sampler step config
├── constructions_notes.md      # Preserved notes for construction groups and disabled entries
├── filter.py                   # Goal filtering
├── pipeline.py                 # Batch generation pipeline and CLI
├── point_naming.py             # Point name generator
├── sampler.py                  # Clause sampling and DAG management
├── statistics.py               # Statistics and reporting
├── worker.py                   # Ray worker for per-problem generation
└── test.py                     # Test suite
```

## Quick Start

### Basic Usage

```python
from newclid.generation_new import ProblemSampler

sampler = ProblemSampler(seed=42)
problem_text = sampler.generate(
    length=15,
    add_auxiliary=True,
    max_auxiliary_points=2,
    prune=True,
    with_coords=False,
)

print(problem_text)
```

### Batch Generation

```python
from newclid.generation_new import ProblemPipeline

pipeline = ProblemPipeline(
    n_clauses=15,
    n_threads=8,
    n_samples=1000,
    output_dir="./datasets",
)

pipeline.generate()
```

### External Construction Config

```bash
python -m newclid.generation_new.pipeline \
  --construction_config ./experiments/construction_library_reduction/profiles.json
```

Example external JSON:

```json
{
  "construction_sets": {
    "basic_small": ["triangle", "rectangle", "quadrangle"],
    "intersect_light": ["on_line", "on_circle"],
    "single_light": ["midpoint", "foot", "free"]
  },
  "step1_sets": ["basic_small"],
  "step2_intersect_sets": ["intersect_light"],
  "step3_single_sets": ["single_light", "intersect_light"]
}
```

## Module Descriptions

### Core Modules

**auxiliary/** - Auxiliary point utilities package
- `primitives.py`: basic constants and coordinate helpers
- `distance.py`: point-distance validation
- `line_utils.py`: line extraction and checks
- `circle_utils.py`: circle detection and validation
- `intersection.py`: line-line, circle-circle, and line-circle intersections
- `finder.py`: candidate derived-point discovery

**constructions.py** - Construction config resolver
- Loads the default construction config from `constructions.json`
- Uses an external JSON config as a full replacement when provided
- Expands config steps into concrete candidate pools

**constructions_notes.md** - Human-readable construction notes
- Preserves the old inline comments that JSON cannot store
- Lists entries that were previously commented out in Python
- Records the intent of the construction groups

**sampler.py** - Main clause generation logic
- Samples clauses in three stages
- Validates numerical constraints
- Manages point dependencies through `ClauseDAG`
- Handles pruning and auxiliary point insertion

**filter.py** - Goal filtering and validation
- Filters trivial and redundant goals
- Scores goal interestingness

**worker.py** - Ray worker for parallel processing
- Handles per-problem generation
- Builds solvers and validates proofs
- Applies the selected construction profile inside worker execution

**pipeline.py** - Main entry point
- Orchestrates the generation pipeline
- Manages Ray workers
- Handles JSONL output and optional image generation
- Exposes CLI flags for construction profile and external config

**statistics.py** - Statistics collection and reporting
- Collects generation statistics
- Generates summary reports
- Outputs command-line summaries

## Sampling Flow

`ProblemSampler.generate()` currently uses three fixed steps:

1. The first clause set samples from the step-1 pool.
2. Later steps choose with probability `0.5` to sample two constructions from the step-2 pool.
3. Otherwise, later steps sample one construction from the step-3 pool.

Profiles only change which construction sets feed these three pools. They do not change the branch probability or the rest of the sampling logic.

## Testing

Run the test suite:

```bash
cd src/newclid/generation_new
python test.py
```

Expected summary:

```text
GENERATION_NEW MODULE TEST SUITE
...
✓ primitives: 3/3 tests passed
✓ distance: 4/4 tests passed
✓ point_naming: 6/6 tests passed
✓ line_utils: 4/4 tests passed
✓ construction_types: 1/1 test passed
✓ construction_config: 6/6 tests passed

Total: 24/24 tests passed ✓
```

### Test Coverage

The test suite covers:
- primitives: coordinate rounding and direction normalization
- distance: point proximity checks
- point naming: name generation and tracking
- line utilities: point extraction and collinearity detection
- construction config: default JSON loading and built-in construction sets
- config resolution: external config replacement and validation

## API Reference

### Import Examples

```python
from newclid.generation_new import (
    BASIC,
    BASIC_FREE,
    INTERSECT,
    OTHER,
    CONSTRUCTION_SETS,
    load_default_construction_config,
    resolve_construction_config,
    ProblemSampler,
    ProblemPipeline,
    GoalFilter,
    Statistics,
)
```

### Key Classes

**ProblemSampler** - Main clause sampler
```python
sampler = ProblemSampler(seed=42, construction_config=None)
problem = sampler.generate(length=15, add_auxiliary=True, prune=True)
```

**ProblemPipeline** - Batch generation pipeline
```python
pipeline = ProblemPipeline(n_samples=1000, n_threads=8)
pipeline.generate()
```

## Configuration

### Construction Sets And Profiles

Default construction data lives in `constructions.json`:
- `construction_sets`: named reusable construction lists
- `step1_sets`, `step2_intersect_sets`, `step3_single_sets`: the three sampler stages using set names

Additional experimental configs can be stored outside the module, for example in `experiments/construction_library_reduction/profiles.json`.

### CLI Flags

Available in `pipeline.py`:
- `--construction_config`: path to an external JSON file that fully defines the construction config for this run
- Existing generation flags such as `--n_clauses`, `--n_samples`, `--add_auxiliary`, `--prune`, and `--remove_coords` remain unchanged

### Constants

Defined in `auxiliary/primitives.py`:
- `TOLERANCE = 1e-08`: numerical tolerance for geometric checks
- `ROUND_DECIMALS = 9`: decimal places for coordinate rounding

## Recent Changes

### Point Enhancement Refactoring (2026-01)
- Organized point enhancement utilities into `point_enhancement/` package
- Moved 6 modules: primitives, distance, line_utils, circle_utils, intersection, enhancer
- Updated all imports to use relative imports within package
- Reduced code complexity and improved maintainability

### Summary Module Simplification (2026-01)
- Removed all plotting functions (matplotlib dependency removed)
- Simplified `output_report()` to only generate JSON reports and CLI output
- Reduced code from 425 lines to 146 lines (65.6% reduction)
- Maintained all core statistics and reporting functionality

### Construction Config Externalization (2026-03)
- Moved the default construction config into `constructions.json`
- Kept `constructions.py` focused on cached loading and config resolution
- Added support for external JSON configs via `--construction_config`
- Preserved default behavior through the bundled default config

### Profile-Driven Sampling (2026-03)
- Added three-step config expansion for sampler stage control
- Enabled experiments to swap construction pools without modifying sampler logic
- Passed external construction config through pipeline and Ray worker execution
- Added validation for missing sets, missing step keys, and invalid construction names

## Performance

Typical performance on a multi-core system:
- Single problem: ~1-2 seconds
- Batch (1000 problems, 8 workers): ~5-10 minutes
- Average speed: ~2-5 samples/second

Notes:
- Loading the default construction JSON is cached once per process
- The JSON-backed config path is negligible compared with generation, solver build, and proof search time

## Troubleshooting

### Import Errors

If you encounter import errors:
```bash
export PYTHONPATH=./src:$PYTHONPATH
```

### Ray Errors

If Ray fails to initialize:
```bash
ray stop
# Then retry
```

### Memory Issues

For large batch generation:
- Reduce `n_threads`
- Lower the number of concurrent pending tasks in `pipeline.py`
- Process in smaller batches

## Contributing

When adding new features:
1. Follow existing code style
2. Add tests to `test.py`
3. Update this README
4. Document public interfaces and config formats clearly

## Migration from Old Module

```python
# Old
from newclid.generation.clause_generation import CompoundClauseGen
from newclid.generation.HA import enhance_text_with_potential_points

# New
from newclid.generation_new import ProblemSampler, ProblemPipeline
```

Current public entry points are:

```python
from newclid.generation_new import ProblemSampler, ProblemPipeline
```

## License

Part of the GenesisGeo project.

## Notes

- The default construction config is loaded once per process and cached, so moving it into JSON does not materially affect generation speed.
- The README keeps the original section-oriented structure, but old names such as `CompoundClauseGen`, `GeometryGenerator`, `construction_types.py`, and `clause_generator.py` are no longer used by the current codebase.
