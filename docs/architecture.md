# Architecture

## Project Overview

GenesisGeo is a neuro-symbolic geometric theorem prover reproducing AlphaGeometry. It combines a C++ symbolic deduction engine (DDAR) with neural language models for auxiliary point proposals. Achieves 24/30 on IMO-AG-30 benchmark.

## Core Components

**DDAR Symbolic Engine** (`src/newclid/DDAR/`) - C++ implementation:
- `solver/ddar.cpp`: Main deduction loop applying geometric rules exhaustively
- `matcher.cpp`: Matches theorems to current proof state (optimized for 120x speedup)
- `rule_parser.cpp`: Parses custom rule text into Theorem objects
- `custom_rule_matcher.cpp`: Matches custom rules against problem points
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
- `extraction/`: Rule extraction utilities (RuleExtractor, RuleConverter, RuleTester) - no ML dependencies
- `ml/`: ML pipeline (scout_pipeline, model_utils, data_processor) - requires torch
- `reduction/`: Rule reduction (GeneralityScorer, SubsumptionTester, RuleReducer)

## Data Flow

1. Problem parsed from JGEX format into `ProblemJGEX`
2. `ProofState` built with numerical coordinates and dependency graph
3. `DeductiveAgent.run()` applies rules until goal proven or timeout
4. For `LMAgent`: LLM proposes auxiliary constructions, DDAR verifies each

## Problem Format (JGEX)

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
- CSolver requires `log_enabled=True, exp_enabled=True` to work correctly
