# quality_review_v1

`quality_review_v1` is the current main benchmark for `experiments/cot_sft_generation`.

It is intentionally review-oriented, not score-oriented.

## What This Benchmark Is For

- keep one repo-stored benchmark pack for mainline iteration
- preserve `goal_type x aux_type` coverage
- make small prefix runs actually meaningful
- force benchmark use back onto the immutable data-quality requirements and semantic review workflow

## What This Benchmark Does Not Mean

This benchmark does not define a numeric acceptance threshold.

- `surface_pass_rate` is only a script-level screen
- `semantic_pass_rate` is only a review summary of the samples that were actually reviewed
- neither number replaces the requirements in [DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)

Any claim that a new chain is "good enough" still requires semantic review using:

- [DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md)
- [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)

## Folder Contents

- [quality_review_v1_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl)
  - self-contained 12-sample benchmark input
- [quality_review_v1_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_manifest.json)
  - coverage, ordering, and review-axis metadata

## What Was Enhanced In The Main Pack

This pack is still 12 samples. The enhancement is not sample-count growth.

The enhancement is in the review structure:

- each record now carries `route_depth_hint`
- each record now carries `figure_span_hint`
- each record now carries `coordinate_dependency_hint`
- each record now carries `must_check`
- each record now carries `review_prompts`

The goal is to make the main pack stronger as a reusable review baseline before adding a separate stress pack.

## Why This Pack Replaces The Old Default

The old `stratified_v1_12sample` pack had the right sample pool but the wrong order for quick prefix runs:

- records `0-5` were all `single_point`
- a quick `-n 4` run looked "small stratified" in name but was not balanced in reality

`quality_review_v1` keeps the same proven source pool, but reorders it so prefixes are intentional:

- first `4` items: `quick4_balanced`
- first `6` items: `quick6_goal_aux_balanced`
- full `12` items: full review pack

## Prefix Presets

### Quick4

Use this for a fast smoke pass with both `single_point` and `multi_point` cases:

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl \
  -n 4 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_quality_review_v1_quick4.jsonl \
  -v
```

### Quick6

Use this for the smallest prefix that still covers all six core goal families:

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl \
  -n 6 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_quality_review_v1_quick6.jsonl \
  -v
```

### Full12

Use this when you want the full repo-stored mainline review pack:

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl \
  -n 12 \
  -w 1 \
  --sequential \
  -o /tmp/cot_sft_quality_review_v1_full12.jsonl \
  -v
```

## Review Axes

The manifest attaches `review_axes` to each sample so targeted review can stay tied to the real quality goals instead of drifting into generic "looks good" checks.

Current review axes are:

- `visible_only_boundary`
- `whole_figure_coverage`
- `coordinate_integration`
- `aux_to_goal_closure`
- `single_point_necessity`
- `multi_point_staging`

The point is not to turn those axes into automatic pass/fail metrics. They are prompts for which parts of the immutable quality target must be checked most carefully on each sample.

## Record-Level Review Metadata

The manifest now annotates each record with a few extra hints:

- `route_depth_hint`
  - how long and failure-prone the closing chain usually is
- `figure_span_hint`
  - how much of the visible figure should realistically enter the reasoning
- `coordinate_dependency_hint`
  - how strongly the sample depends on coordinate or image-derived cues staying alive in the route
- `must_check`
  - the highest-priority axes to verify first
- `review_prompts`
  - concrete questions for human review

These fields are review guidance only. They are not automatic labels and they do not override the semantic review guide.

## New Priority Subsets

The main pack now exposes a few more targeted subsets:

- `single_point_whole_figure_coverage_priority`
  - single-point cases that still need broad visible-figure coverage
- `single_point_coordinate_integration_priority`
  - single-point cases where coordinate or image cues are especially important
- `high_closure_depth_priority`
  - cases with longer or more failure-prone back-half closure
- `mixed_mechanism_multi_point_priority`
  - multi-point cases that mix several helper mechanisms and therefore drift more easily
