# Discovery Plotting Pipelines

This document describes the plotting scripts and visualization utilities for the discovery pipeline (rule extraction and reduction).

## Overview

Discovery plotting serves two main purposes:

1. **Explanatory single figures**: High-quality diagrams for papers, presentations, and documentation
   - Pipeline flow diagrams
   - Example rule extraction illustrations
   - Statistical distributions
2. **Batch rendering**: Large-scale visualization of intermediate results for debugging and analysis
   - Parallel rendering of all rule extractions
   - Subset-based batch visualization

## Script Inventory

### Core Explanatory Scripts

#### `scripts/figures/fig_pipeline_flow.py`

**Purpose**: Generate the discovery pipeline flow diagram showing data funnel from raw samples to final basis rules.

**Input**: Hardcoded funnel data from 10k experiment
- Stage 1 (FilterAndPruneEngine): Steps 1-6
- Stage 2 (RuleReducer): Phases 1-2

**Output**:
- `outputs/figures/discovery/pipeline_diagrams/fig1_pipeline_flow.pdf`
- `outputs/figures/discovery/pipeline_diagrams/fig1_pipeline_flow.png`

**Usage**:
```bash
python scripts/figures/fig_pipeline_flow.py
```

**Notes**:
- Aligned with current pipeline structure in `docs/pipeline_dashboard.md`
- Uses a two-stage horizontal flow with stage backgrounds
- Stage 1 shows step-level funnel counts and retention rates
- Stage 2 shows phase structure only, without hardcoding unstable intermediate reduction counts

---

#### `scripts/figures/fig_rule_extraction.py`

**Purpose**: Generate a three-panel illustration of rule extraction:
(a) full proof graph → (b) pruned graph → (c) extracted rule

**Input**:
- JSONL dataset: `outputs/datasets/synthetic_10k_aux_only/geometry_clauses15_samples10k.jsonl`
- Pruned results: `outputs/datasets/synthetic_10k_aux_only/geometry_clauses15_samples10k_pruned.json`
- Default example: auto-select the first available `problem_id` from the pruned JSON

**Output**:
- `outputs/figures/discovery/rule_extractions/fig2_rule_extraction.pdf`
- `outputs/figures/discovery/rule_extractions/fig2_rule_extraction.png`

**Usage**:
```bash
python scripts/figures/fig_rule_extraction.py
```

**Notes**:
- Uses real pipeline outputs, not synthetic examples
- Reuses graph construction and pruning logic from discovery core modules
- Suitable for paper figures and explanations

---

### Batch Rendering Scripts

#### `scripts/figures/render_rule_extractions_parallel.py`

**Purpose**: Batch render many rule extraction figures in parallel.

**Input**:
- JSONL dataset
- Pruned JSON results
- Usually a list of problem IDs or a subset selection

**Output**:
- Large batches of PNG/PDF figures
- Typically written to experiment-specific directories

**Typical Usage**:
```bash
python scripts/figures/render_rule_extractions_parallel.py [args]
```

**Placement**:
- Keep outputs in experiment directories when generating large batches
- Do not force migration to `outputs/figures/discovery/` for batch experiment outputs

---

#### `scripts/figures/render_risos_subset.py`

**Purpose**: Render a preset subset of RISOS or similar records.

**Status**: Legacy preset / subset wrapper

**Input**:
- Delegates to the same underlying rendering pipeline as batch rule extraction scripts

**Output**:
- Subset-specific rendered figures, usually experiment-bound

**Typical Usage**:
```bash
python scripts/figures/render_risos_subset.py
```

**Maintenance Note**:
- Retained for now as a convenient wrapper
- Not aggressively consolidated in this cleanup

---

### Related Discovery Plotting Scripts

#### `scripts/plot_premise_distribution.py`

**Purpose**: Plot premise-count distributions for extracted rules or intermediate rule sets.

**Input**:
- Rule files or stats JSON produced by discovery pipeline

**Output**:
- Distribution plots for premise counts
- Recommended destination: `outputs/figures/discovery/distributions/` for reusable summary plots
- Experiment directories are still appropriate for run-specific outputs

**Typical Usage**:
```bash
python scripts/plot_premise_distribution.py [args]
```

---

#### `scripts/plot_proof_graphs.py`

**Purpose**: Plot proof graphs related to discovery analysis.

**Input**:
- Discovery proof graph data / pipeline records

**Output**:
- Proof graph visualizations
- Recommended destination: `outputs/figures/discovery/proof_graphs/` for reusable summary plots
- Experiment directories remain appropriate for batch or run-specific outputs

**Typical Usage**:
```bash
python scripts/plot_proof_graphs.py [args]
```

## Core Reused Utilities

### `src/newclid/proof_scout/core/proof_graph_visualizer.py`

Core rendering utility for proof graph visualization.

**Role**:
- Shared proof graph rendering backend
- Should remain the primary reusable implementation rather than duplicating graph drawing logic elsewhere

### Reusable functions in `scripts/figures/fig_rule_extraction.py`

The following functions are explicitly reusable for future discovery plotting work:

#### `build_full_graph_from_record()`
Build full proof graph data from one raw JSONL record using `SingleProofGraph`.

#### `build_pruned_render_from_record()`
Rebuild the pruned rendered graph from one raw JSONL record using `GraphPruner`.

#### `create_three_panel_figure_from_data()`
Create the final three-panel explanatory figure from already loaded graph data.

These functions should be preferred over rewriting the same graph preparation logic in new scripts.

## Input / Output Summary

### Pipeline flow figure
- **Script**: `scripts/figures/fig_pipeline_flow.py`
- **Input**: Current pipeline funnel counts / hardcoded stage data
- **Output**: `outputs/figures/discovery/pipeline_diagrams/`
- **Use case**: Documentation, presentations, paper figure

### Rule extraction example figure
- **Script**: `scripts/figures/fig_rule_extraction.py`
- **Input**: JSONL dataset + pruned JSON
- **Output**: `outputs/figures/discovery/rule_extractions/`
- **Use case**: Explanatory example of extraction from proof graph to rule

### Batch rule extraction rendering
- **Script**: `scripts/figures/render_rule_extractions_parallel.py`
- **Input**: Large record sets from pipeline outputs
- **Output**: Experiment directories
- **Use case**: Large-scale inspection and debugging

### Subset wrapper rendering
- **Script**: `scripts/figures/render_risos_subset.py`
- **Input**: Preset subset configuration
- **Output**: Experiment directories
- **Use case**: Convenient subset inspection

### Premise distributions
- **Script**: `scripts/plot_premise_distribution.py`
- **Input**: Rule stats / rule files
- **Output**: `outputs/figures/discovery/distributions/` for reusable outputs, or experiment directories for run-specific plots
- **Use case**: Statistical characterization of extracted rules

### Proof graph plots
- **Script**: `scripts/plot_proof_graphs.py`
- **Input**: Discovery proof graph data
- **Output**: `outputs/figures/discovery/proof_graphs/` for reusable outputs, or experiment directories for run-specific plots
- **Use case**: Visual inspection of proof structures

## Output Convention

A new unified output convention is established for reusable discovery figures:

```text
outputs/figures/discovery/
├── pipeline_diagrams/
├── rule_extractions/
├── proof_graphs/
└── distributions/
```

### What goes into the unified directory

Use `outputs/figures/discovery/` for **general, reusable, explanatory figures**, such as:
- Pipeline flow diagrams
- Canonical example rule extraction figures
- Reusable summary distributions
- Reusable proof graph illustrations

### What stays in experiment directories

Keep outputs in experiment directories for **experiment-bound or large-scale generated figures**, such as:
- Large batches from `render_rule_extractions_parallel.py`
- Subset experiment figures from `render_risos_subset.py`
- Run-specific debugging plots
- Any visualization tightly coupled to a single experiment run

### Compatibility policy

- Historical files are **not migrated** in this cleanup
- Existing experiment directories remain unchanged
- The new convention applies only to future reusable or regenerated discovery figures

## Data Flow

Typical discovery plotting data flow:

```text
JSONL / step6_rules_stats.json / pruned json / results json
    -> plotting scripts
    -> figure outputs
```

More concretely:

```text
Synthetic JSONL
  -> FilterAndPruneEngine intermediates
     -> step1_input_filter.json
     -> step2_graph_prune.json
     -> step3_propositions.json
     -> step4_*.json
     -> step5_dedup.json
     -> step6_rules_stats.json
     -> *_pruned_rules.txt
  -> RuleReducer outputs
     -> extracted_rules.txt
  -> Plotting scripts
     -> pipeline diagrams / rule extraction figures / proof graphs / distributions
```

## Maintenance Notes

- `scripts/figures/fig_rule_extraction_old.py` is retained as a legacy script and is **not removed** in this cleanup.
- `scripts/figures/render_risos_subset.py` is retained as a legacy preset / wrapper and is **not aggressively consolidated**.
- `docs/pipeline_dashboard.md` remains the authoritative reference for discovery pipeline naming and stage structure.
- When pipeline stage names or step boundaries change, `scripts/figures/fig_pipeline_flow.py` must be updated accordingly.
- This document only covers **discovery-related plotting**, not all visualization modules in the repository.
