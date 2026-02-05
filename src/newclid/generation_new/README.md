# Generation Module

A refactored and optimized geometry problem generation module with clean architecture and improved maintainability.

## Overview

This module generates synthetic geometry problems for automated theorem proving. It creates geometric constructions, finds meaningful points, filters valid goals, and produces problems with proofs.

## Features

- **Clause Generation**: Creates geometric constructions using various construction types
- **Point Enhancement**: Automatically discovers and adds meaningful auxiliary points
- **Goal Filtering**: Identifies valid and interesting theorem goals
- **Proof Validation**: Verifies problems have valid proofs
- **Parallel Processing**: Uses Ray for efficient batch generation
- **Summary Reports**: Generates detailed statistics and reports

## Directory Structure

```
generation_new/
├── __init__.py              # Module exports
├── point_enhancement/       # Point enhancement package
│   ├── __init__.py          # Package exports
│   ├── primitives.py        # Basic geometry utilities
│   ├── distance.py          # Distance checking
│   ├── line_utils.py        # Line calculations
│   ├── circle_utils.py      # Circle calculations
│   ├── intersection.py      # Intersection calculations
│   └── enhancer.py          # Point enhancement logic
├── point_generator.py       # Point name generator
├── construction_types.py    # Construction type constants
├── clause_generator.py      # Clause generation core
├── goal_filter.py           # Goal filtering
├── problem_worker.py        # Ray worker for parallel processing
├── summary.py               # Statistics and reporting
├── generate.py              # Main entry point
└── test.py                  # Test suite
```

## Quick Start

### Basic Usage

```python
from newclid.generation_new import CompoundClauseGen

# Generate geometric clauses
gen = CompoundClauseGen(seed=42)
clause_text = gen.generate(
    length=15,           # Number of construction steps
    add_auxiliary=True,  # Add auxiliary points
    prune=True,          # Prune to essential clauses
    remove_coords=False  # Keep coordinates
)

print(clause_text)
```

### Batch Generation

```python
from newclid.generation_new.generate import GeometryGenerator

# Initialize generator
generator = GeometryGenerator(
    num_samples=1000,
    num_threads=8,
    output_dir='./output',
    seed=42
)

# Generate problems
generator.generate()
```

## Module Descriptions

### Core Modules

**point_enhancement/** - Point enhancement utilities package
- `primitives.py`: Basic constants (`TOLERANCE`, `ROUND_DECIMALS`) and utilities
- `distance.py`: Point distance validation
- `line_utils.py`: Line extraction, finding, and validation
- `circle_utils.py`: Circle detection and validation
- `intersection.py`: Line-line, circle-circle, line-circle intersections
- `enhancer.py`: Midpoints, reflections, feet, and point enhancement

**clause_generator.py** - Main clause generation logic
- Creates geometric constructions
- Validates numerical constraints
- Manages point dependencies

**goal_filter.py** - Goal filtering and validation
- Filters trivial and redundant goals
- Scores goal interestingness

**problem_worker.py** - Ray worker for parallel processing
- Handles problem generation in parallel
- Manages proof validation

**summary.py** - Statistics collection and reporting
- Collects generation statistics
- Generates JSON reports
- Outputs command-line summaries

**generate.py** - Main entry point
- Orchestrates the generation pipeline
- Manages Ray workers
- Handles output and reporting

## Testing

Run the test suite:

```bash
cd /root/autodl-fs/projects/GenesisGeo/src/newclid/generation_new
python test.py
```

Expected output:
```
============================================================
GENERATION_NEW MODULE TEST SUITE
============================================================

✓ primitives: 3/3 tests passed
✓ distance: 4/4 tests passed
✓ point_generator: 6/6 tests passed
✓ line_utils: 4/4 tests passed
✓ construction_types: 1/1 test passed

Total: 18/18 tests passed ✓
```

### Test Coverage

The test suite covers:
- Primitives: coordinate rounding, direction normalization
- Distance: point proximity checks
- Point generator: name generation and tracking
- Line utilities: point extraction, collinearity detection
- Construction types: type constants validation

## API Reference

### Import Examples

```python
# Import from main module
from newclid.generation_new import (
    CompoundClauseGen,
    enhance_text_with_potential_points,
    GeometryGoalFilter,
    Summary
)

# Import from point_enhancement package
from newclid.generation_new.point_enhancement import (
    TOLERANCE,
    lines,
    circles,
    intersection_between_lines
)
```

### Key Classes

**CompoundClauseGen** - Main clause generator
```python
gen = CompoundClauseGen(seed=42, defs=None)
clauses = gen.generate(length=15, add_auxiliary=True, prune=True)
```

**GeometryGoalFilter** - Goal filter
```python
filter = GeometryGoalFilter()
valid_goals = filter.filter_goals(goals, constructions)
```

**Summary** - Statistics reporter
```python
summary = Summary(prefix='output')
summary.add(problem_stats)
summary.output_report()
```

## Configuration

### Construction Types

Defined in `construction_types.py`:
- `BASIC`: Basic shapes (triangle, square, rectangle, etc.)
- `BASIC_FREE`: Free point constructions
- `INTERSECT`: Intersection-based constructions
- `OTHER`: Special constructions (midpoint, reflection, etc.)

### Constants

Defined in `point_enhancement/primitives.py`:
- `TOLERANCE = 1e-08`: Numerical tolerance for geometric checks
- `ROUND_DECIMALS = 9`: Decimal places for coordinate rounding

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

## Performance

Typical performance on a multi-core system:
- Single problem: ~1-2 seconds
- Batch (1000 problems, 8 workers): ~5-10 minutes
- Average speed: ~2-5 samples/second

## Troubleshooting

### Import Errors

If you encounter import errors:
```bash
export PYTHONPATH=/root/autodl-fs/projects/GenesisGeo/src:$PYTHONPATH
```

### Ray Errors

If Ray fails to initialize:
```bash
ray stop  # Stop any existing Ray instances
# Then retry
```

### Memory Issues

For large batch generation:
- Reduce `num_threads`
- Lower `max_pending` in generate.py
- Process in smaller batches

## Contributing

When adding new features:
1. Follow existing code style
2. Add tests to `test.py`
3. Update this README
4. Document all public functions with docstrings

## Migration from Old Module

```python
# Old
from newclid.generation.clause_generation import CompoundClauseGen
from newclid.generation.HA import enhance_text_with_potential_points

# New
from newclid.generation_new import CompoundClauseGen, enhance_text_with_potential_points
```

## License

Part of the GenesisGeo project.
