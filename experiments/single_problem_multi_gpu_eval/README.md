# Single Problem Multi GPU Eval

This experiment directory contains an isolated evaluation workflow for:

- loading one model replica per GPU at startup
- evaluating problems sequentially
- using all available GPUs for candidate generation within a single problem
- using Ray CPU tasks for DDAR validation
- supporting `lm`, `vlm`, and `qwen35` backends through one shared single-problem multi-GPU runner

Current status:

- the architecture in this directory is unified around one shared multi-GPU search core
- GPU dispatch can batch multiple prepared requests into one worker call
- search remains depth-by-depth, but request preparation / GPU inference / DDAR now overlap within a depth
- worker-level tracing supports gantt visualization for prepare, GPU, and DDAR work
- profiling captures candidate quality and token-efficiency metrics for GPU generation
- this experiment runner does not use `problem_db`

## Files

- `evaluation_single_problem_multi_gpu.py`: experiment entrypoint
- `model_pool.py`: GPU worker pool and batched dispatcher
- `base_multi_gpu_agent.py`: shared beam-search and DDAR orchestration
- `lm_actor.py`: GPU-resident text-model worker
- `visual_actor.py`: GPU-resident vision-model worker shared by `vlm` and `qwen35`
- `lm_multi_gpu_agent.py`: LM-specific experiment agent adapter
- `visual_multi_gpu_agent.py`: VLM/Qwen3.5-vision experiment agent adapter
- `search_common.py`: shared queue and DDAR helpers
- `scripts/run_profiled_eval.sh`: profiled eval wrapper
- `scripts/run_profiled_eval_and_plot_gantt.sh`: one-click eval + gantt wrapper
- `scripts/plot_worker_gantt.py`: worker gantt renderer
- `scripts/analyze_eval_trace.py`: trace summarizer

## Architecture

The code is organized in three layers:

1. Runner layer
   - `evaluation_single_problem_multi_gpu.py`
   - CLI parsing, Ray init, worker startup, per-problem iteration, live table, CSV output

2. Shared search layer
   - `base_multi_gpu_agent.py`
   - `search_common.py`
   - common beam-search loop, candidate validation, DDAR backpressure

3. Backend-specific generation layer
   - `lm_actor.py` + `lm_multi_gpu_agent.py`
   - `visual_actor.py` + `visual_multi_gpu_agent.py`
   - backend-specific prompt construction, model loading, rendering, and candidate generation
   - worker actors expose batch generation only; for one-request debugging use `gpu_batch_size=1`

## Entrypoint

Main command:

```bash
python experiments/single_problem_multi_gpu_eval/evaluation_single_problem_multi_gpu.py ...
```

Supported arguments:

| Argument | Default | Meaning |
| --- | --- | --- |
| `--problems_path` | required | Benchmark file. The runner reads every other line as a problem name. |
| `--model_path` | required | Local checkpoint/model directory or a remote model id resolvable by `modelscope.snapshot_download`. |
| `--agent` | `lm` | Backend to run: `lm`, `vlm`, or `qwen35`. |
| `--log_dir` | `results` | Directory for the output CSV. |
| `--render_root` | `<log_dir>/_rendered` | Directory for rendered visual prompts. Used by `vlm` and `qwen35`. |
| `--enable_trace` | `False` | Write per-problem trace JSONL files under `<log_dir>/<run_id>/`. |
| `--ray_address` | `local` | Ray address. Use `local` for a fresh local runtime. |
| `--max_workers` | `8` | CPU budget for Ray, mainly affecting DDAR concurrency. |
| `--decoding_size` | `8` | Number of model candidates generated per retained state at one search depth. |
| `--beam_size` | `64` | Maximum number of candidate states kept between depths. |
| `--search_depth` | `4` | Number of iterative auxiliary-construction expansion rounds. |
| `--gpu_batch_size` | `1` | Maximum number of prepared requests grouped into one GPU generate call. |
| `--gpu_batch_timeout_ms` | `0` | Optional wait budget before dispatching a not-full GPU batch. |
| `--torch_seed` | `123` | Torch RNG seed applied once per GPU worker process. |
| `--timeout` | `7200` | Per-problem timeout in seconds. |
| `--num_gpus_for_eval` | `0` | Number of GPU workers to create. `0` means all GPUs visible to Ray. |
| `--max_pending_ddar` | `2 * max_workers` | Upper bound on in-flight DDAR tasks for the current problem. |
| `--prepare_request_workers` | `2 * num_gpus_for_eval` | Local thread count for request preparation when omitted. |
| `--prepare_prefetch_limit` | derived | Upper bound on running + ready prepared requests when omitted. |
| `--enable_profiling` | `False` | Write a sidecar profiling CSV with build/inference/DDAR timings and candidate quality metrics. |

## Parameter Relationships

- `decoding_size` controls generation breadth per retained state
- `beam_size` controls how many validated states survive
- `search_depth` controls how many rounds of expansion happen
- `num_gpus_for_eval` controls how many model replicas stay resident
- `gpu_batch_size` controls how many prepared requests are combined per GPU generate call
- `gpu_batch_timeout_ms` controls how long the dispatcher may wait before releasing a tail batch
- `max_workers` and `max_pending_ddar` control DDAR-side throughput and backpressure

If DDAR is the bottleneck, increasing GPUs alone will not help much. In that case, inspect `max_workers` and `max_pending_ddar`.

## Trace And Profiling

When `--enable_trace` is enabled, each run writes per-problem JSONL traces containing:

- prepare/GPU/DDAR worker timestamps
- attempt-level candidate and DDAR outcomes
- enough worker-level timing fields to render the gantt chart
- the analysis script derives candidate-quality summaries from `attempts/` records rather than a separate `model_response` event

When `--enable_profiling` is enabled, the sidecar CSV includes:

- wall-time breakdowns for prepare/GPU/DDAR stages
- GPU batching effectiveness
- DDAR throughput and candidate parse/build success rates

## Examples

Single-problem multi-GPU VLM run:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 LOGLEVEL=WARNING python experiments/single_problem_multi_gpu_eval/evaluation_single_problem_multi_gpu.py \
  --problems_path benchmarks/imo_95.txt \
  --model_path models/vlm_checkpoint \
  --agent vlm \
  --log_dir experiments/single_problem_multi_gpu_eval/runs/example_vlm \
  --max_workers 40 \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --gpu_batch_size 2 \
  --gpu_batch_timeout_ms 100 \
  --timeout 3600 \
  --num_gpus_for_eval 4
```

Single-GPU debug run:

```bash
CUDA_VISIBLE_DEVICES=0 LOGLEVEL=DEBUG python experiments/single_problem_multi_gpu_eval/evaluation_single_problem_multi_gpu.py \
  --problems_path benchmarks/imo_2000_p6.txt \
  --model_path models/vlm_sft50/checkpoint-19194 \
  --agent vlm \
  --log_dir experiments/single_problem_multi_gpu_eval/runs/debug_vlm_1gpu \
  --max_workers 1 \
  --decoding_size 2 \
  --beam_size 4 \
  --search_depth 1 \
  --gpu_batch_size 1 \
  --timeout 7200 \
  --num_gpus_for_eval 1
```

Profiled run with trace analysis:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 LOGLEVEL=WARNING bash experiments/single_problem_multi_gpu_eval/scripts/run_profiled_eval.sh \
  --problems_path benchmarks/imo_95.txt \
  --model_path models/vlm_checkpoint \
  --agent vlm \
  --max_workers 40 \
  --decoding_size 32 \
  --beam_size 512 \
  --search_depth 4 \
  --gpu_batch_size 2 \
  --gpu_batch_timeout_ms 100 \
  --num_gpus_for_eval 4
```

One-click profiled run plus worker gantt:

```bash
bash experiments/single_problem_multi_gpu_eval/scripts/run_profiled_eval_and_plot_gantt.sh \
  --problem 0 \
  -- --problems_path benchmarks/imo_2008_p1b.txt \
     --model_path /path/to/checkpoint \
     --agent vlm \
     --max_workers 40 \
     --decoding_size 32 \
     --beam_size 512 \
     --search_depth 4 \
     --timeout 3600 \
     --num_gpus_for_eval 4 \
     --gpu_batch_size 2 \
     --gpu_batch_timeout_ms 100 \
     --torch_seed 42
```

## Output

Each run writes a CSV named like:

```text
eval_single_problem_multi_gpu_<agent>_<dataset>_<model>_d<decoding_size>_b<beam_size>_s<search_depth>_gbs<gpu_batch_size>_gbt<gpu_batch_timeout_ms>_seed<torch_seed>_<timestamp>.csv
```

When `--enable_trace` is enabled, each run creates a trace directory named like:

```text
eval_single_problem_multi_gpu_<agent>_<dataset>_<model>_d<decoding_size>_b<beam_size>_s<search_depth>_gbs<gpu_batch_size>_gbt<gpu_batch_timeout_ms>_seed<torch_seed>_<timestamp>/
```

For visual backends, rendered prompt images are written under:

```text
<log_dir>/_rendered/
```
