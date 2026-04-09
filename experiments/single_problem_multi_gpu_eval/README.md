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
- this experiment runner does not use `problem_db`
- the top-level `scripts/evaluation_vlm.py` remains the original per-problem Ray workflow and is separate from this experiment runner

## Files

- `evaluation_single_problem_multi_gpu.py`: experiment entrypoint
- `model_pool.py`: GPU worker pool and batched dispatcher
- `base_multi_gpu_agent.py`: shared beam-search and DDAR orchestration
- `lm_actor.py`: GPU-resident text-model worker
- `visual_actor.py`: GPU-resident vision-model worker shared by `vlm` and `qwen35`
- `lm_multi_gpu_agent.py`: LM-specific experiment agent adapter
- `visual_multi_gpu_agent.py`: VLM/Qwen3.5-vision experiment agent adapter
- `search_common.py`: shared queue and DDAR helpers
- `scripts/eval_qwen3_17b_text_single_problem_multi_gpu.sh`: reference script for text runs
- `scripts/compare_dev_imo_sft34.sh`: comparison script for original vs experiment LM evaluation

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

More concretely:

- `base_multi_gpu_agent.py` is the shared search chassis. It owns the frontier loop, GPU dispatch coordination, DDAR future scheduling, and success/failure payload construction.
- `lm_multi_gpu_agent.py` adapts the shared chassis to text-only search state `ProblemJGEX`.
- `visual_multi_gpu_agent.py` adapts the shared chassis to visual search state `(problem, proof)` so each expansion can render a fresh image.
- `model_pool.py` manages the resident GPU workers and dispatches one request batch at a time to each worker.
- request batching is controlled by `gpu_batch_size`; `gpu_batch_size=1` preserves the historical single-request behavior

## Execution Flow

At a high level:

1. `evaluation_single_problem_multi_gpu.py` starts Ray and creates one GPU worker per GPU for the selected backend.
2. Problems are processed one by one.
3. Inside one problem, the agent expands the beam layer by layer.
4. Requests for the current depth are prepared on demand instead of rendering the whole layer up front.
5. Candidate generation requests are grouped into batches and dispatched across the GPU workers.
6. Each surviving candidate is checked by DDAR through Ray CPU tasks.
7. Valid unsolved candidates enter the next beam layer after the current depth drains.

Important implications:

- `num_gpus_for_eval` reduces latency within one problem, not across multiple problems
- `max_workers` mainly controls DDAR-side CPU concurrency
- GPU workers always process one actor call at a time, but each call may contain multiple requests
- `max_pending_ddar` is the main backpressure knob between generation and validation
- depth boundaries are still strict; requests from different search depths never mix

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
| `--max_workers` | `8` | CPU budget for Ray, mainly affecting DDAR concurrency. |
| `--decoding_size` | `8` | Number of model candidates generated per retained state at one search depth. |
| `--beam_size` | `64` | Maximum number of candidate states kept between depths. |
| `--search_depth` | `4` | Number of iterative auxiliary-construction expansion rounds. |
| `--gpu_batch_size` | `1` | Maximum number of prepared requests grouped into one GPU generate call. |
| `--gpu_batch_timeout_ms` | `0` | Optional wait budget before dispatching a not-full GPU batch. |
| `--timeout` | `7200` | Per-problem timeout in seconds. |
| `--num_gpus_for_eval` | `0` | Number of GPU workers to create. `0` means all GPUs visible to Ray. |
| `--max_pending_ddar` | `2 * max_workers` | Upper bound on in-flight DDAR tasks for the current problem. |

## Parameter Relationships

- `decoding_size` controls generation breadth per retained state
- `beam_size` controls how many validated states survive
- `search_depth` controls how many rounds of expansion happen

Resource knobs:

- `num_gpus_for_eval` controls how many model replicas stay resident
- `gpu_batch_size` controls how many prepared requests are combined per GPU generate call
- `gpu_batch_timeout_ms` controls how long the dispatcher may wait before releasing a tail batch
- `model_pool.py` is a tunable batch dispatcher
- `max_workers` and `max_pending_ddar` control DDAR-side throughput and backpressure

If DDAR is the bottleneck, increasing GPUs alone will not help much. In that case, inspect `max_workers` and `max_pending_ddar`.

## `max_pending_ddar`

`max_pending_ddar` limits how many candidate validations can be in flight at once.

It does not change:

- how many candidates the model proposes
- beam width
- number of GPU workers

It changes:

- how far GPU generation is allowed to get ahead of DDAR validation
- when new requests stop being prepared or dispatched because DDAR backlog is too high

Typical symptoms:

- too small: DDAR becomes a hard bottleneck and GPU workers go idle more often
- too large: CPU and memory pressure rise because too many DDAR tasks accumulate

## Logging

The runner uses standard Python logging with:

```text
%(asctime)s %(levelname)s %(name)s: %(message)s
```

Set:

```bash
LOGLEVEL=DEBUG
```

to see detailed progress from:

- runner startup and problem loop boundaries
- worker warmup
- request dispatch and completion
- search-depth transitions
- vision worker request start/end

Ray may prepend actor/pid information to some worker logs.

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

## Output

Each run writes a CSV named like:

```text
eval_single_problem_multi_gpu_<agent>_<dataset>_<model>_d<decoding_size>_b<beam_size>_s<search_depth>.csv
```

For visual backends, rendered prompt images are written under:

```text
<log_dir>/_rendered/
```
