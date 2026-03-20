#!/usr/bin/env python3
"""
Flywheel Data Generation — Thin wrapper around GeometryGenerator.

Convenience script that defaults to engine=weak for the data flywheel pipeline.
All heavy lifting is done by src/newclid/generation/generate.py.

Usage:
    # First iteration (no custom rules):
    python scripts/flywheel_generate.py \
        --n_samples 10000 --n_clauses 5 --n_threads 20 \
        --dir outputs/flywheel/iter_00

    # Subsequent iteration with discovered rules:
    python scripts/flywheel_generate.py \
        --n_samples 10000 --n_clauses 5 --n_threads 20 \
        --dir outputs/flywheel/iter_01 \
        --custom_rules outputs/flywheel/iter_00/extracted_rules.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from newclid.generation.generate import main

if __name__ == "__main__":
    # Inject --engine weak as default if not explicitly provided
    if "--engine" not in sys.argv:
        sys.argv.extend(["--engine", "weak"])
    main()
