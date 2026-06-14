# CoT SFT Artifact Schema

本文档给出 `experiments/cot_sft_generation` 当前长期维护时应默认依赖的 artifacts 字段协议。它和 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md) 的区别是：

- `CURRENT_DESIGN.md` 说明“代码现在怎么跑”
- 本文档说明“落盘文件里有哪些稳定字段，以及后续怎样读它们”

当前 schema 的实现入口主要有两个：

- [run_artifacts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/run_artifacts.py)
- [semantic_review.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/semantic_review.py)
- [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)

固定 benchmark 资产和其 manifest 见 [benchmarks/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/README.md)。

## 1. 版本兼容约定

1. 长期读 run 结果时，优先使用 `surface_pass`，不要再把 `success` 当主字段。
2. `success` 目前只为兼容旧脚本保留，语义上等同于 `surface_pass`。
3. 当前 run artifacts schema 版本为 `cot_sft_artifacts_v1`。
4. 当前 live generation style 名称是：
   - `insight_image_v1`
   - `insight_text_v1`
   - `backtrace_text_v1`
   - `dossier_v1`
   - `model_evidence_legacy`
5. `insight_v1` 只应被视为历史记录名称，不应再被当作当前可选 style。
6. 任何新增长期字段，都应先落到 `run_artifacts.py`，再同步更新本文档。

## 2. `run_config.json`

这个文件在每次 run 开始时落盘，记录“这轮结果是基于哪份代码、哪份输入、哪套参数”生成的。

| 字段 | 类型 | 含义 |
|------|------|------|
| `artifact_schema_version` | `str` | 当前 artifacts schema 版本 |
| `started_at_utc` | `str` | run 开始时间 |
| `script` | `str` | 主脚本绝对路径 |
| `cwd` | `str` | 启动 run 时的工作目录 |
| `repo_root` | `str` | 仓库根目录 |
| `model_name` | `str` | 教师模型名 |
| `api_base_url` | `str` | 推理网关地址 |
| `api_timeout_seconds` | `int` | 单次 API 超时设置 |
| `api_call_retries` | `int` | 单次 API 调用内部补偿重试次数 |
| `api_retry_backoff_seconds` | `int` | 单次 API 调用重试回退秒数 |
| `default_input_jsonl` | `str` | 脚本默认输入文件 |
| `output_jsonl` | `str` | 最终输出路径 |
| `run_dir` | `str` | artifacts 目录路径 |
| `arguments` | `object` | 原始 CLI 参数字典 |
| `git_commit` | `str \| null` | 当前仓库 commit SHA |
| `git_branch` | `str \| null` | 当前分支名 |
| `git_dirty` | `bool \| null` | 当前工作树是否有未提交修改 |
| `resolved_input_jsonl` | `str` | 实际使用的输入文件绝对路径 |
| `input_jsonl_sha256` | `str` | 实际输入文件的 SHA-256 指纹 |
| `input_jsonl_bytes` | `int` | 实际输入文件大小 |

## 3. `sampled_inputs.jsonl`

这个文件只在 `-v/--verbose` 时导出。它回答“这轮抽中的到底是哪些原始样本”，方便做回放和复核。

| 字段 | 类型 | 含义 |
|------|------|------|
| `sample_order` | `int` | 本次 run 内顺序 |
| `input_index` | `int` | 输入源中的索引 |
| `image_path` | `str` | 源样本图片路径 |
| `llm_input_renamed` | `str` | 原始可见题面字段 |
| `aux` | `str` | 原始 aux |
| `point_coords_grid` | `object` | 源样本可见点坐标表 |

## 4. 最终数据集输出条目

最终输出 JSONL 的每条记录由 `build_dataset_output_record(...)` 生成，稳定字段如下：

共同字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| `instruction` | `str` | 训练指令文本 |
| `input` | `str` | 学生模型可见题面 |
| `thinking` | `str` | 最终 `<thinking>...</thinking>` |
| `aux` | `str` | 原始 `<aux>...</aux>` |
| `output` | `str` | `thinking + "\n" + aux` |
| `_order` | `int` | 本次 run 中的样本顺序 |

style 差异：

- `insight_image_v1`
  - 额外包含 `image_path`
- `insight_text_v1`
  - 不包含 `image_path`
- `backtrace_text_v1`
  - 不包含 `image_path`
- insight family 两个 variant 都不会导出 point coordinates
- `backtrace_text_v1` 也是 text-only，不会导出 point coordinates

## 5. `item_records.jsonl`

这个文件只在 `-v/--verbose` 时导出。它保留样本级完整上下文，适合回放失败样本和对照 prompt。

| 字段 | 类型 | 含义 |
|------|------|------|
| `sample_order` | `int` | 本次 run 内顺序 |
| `input_index` | `int` | 输入源中的索引 |
| `image_path` | `str` | 图片路径 |
| `public_problem` | `str` | 对学生可见的题面 |
| `aux` | `str` | 原始 aux |
| `goal_type` | `str \| null` | 可见目标类型 |
| `aux_type` | `str \| null` | 辅助构造类型 |
| `hidden_rest_sanitized` | `str` | 脱敏后的 hidden proof/rest |
| `point_coords_grid` | `object` | 可见点坐标表 |
| `source_audit` | `object` | 源样本检查结果 |
| `generation_audit` | `object` | 生成后脚本审计结果 |
| `plan_prompt` | `str \| null` | planner prompt |
| `write_prompt` | `str \| null` | writer prompt |
| `plan_output` | `str \| null` | planner 原始输出 |
| `plan_parsed` | `object \| null` | 解析后的 plan |
| `insight_slots` | `object \| null` | insight family 的 DAG 提取槽位 |
| `insight_plan_parsed` | `object \| null` | insight family 的批准 plan |
| `backtrace_slots` | `object \| null` | `backtrace_text_v1` 的 DAG backtrace 提取结果 |
| `writer_handoff` | `object \| null` | writer-only handoff；当前用于 `backtrace_text_v1` |
| `writer_validation_issues` | `list[str]` | writer hard checks 的稳定问题码列表 |
| `write_output` | `str \| null` | writer 原始输出 |
| `thinking` | `str \| null` | 最终 thinking |
| `surface_pass` | `bool` | 是否通过脚本终检 |
| `success` | `bool` | 兼容字段，等同 `surface_pass` |
| `exported_to_dataset` | `bool` | 是否最终写入训练 jsonl |
| `dataset_filter_reason` | `str \| null` | 未导出原因；当前为 `generation_failed` 或 `generation_audit_hard_issue` |
| `attempts_used` | `int \| null` | 本条样本实际重试次数 |
| `elapsed_seconds` | `float \| null` | 本条样本耗时 |
| `error` | `str \| null` | 失败原因 |

说明：

- `surface_pass=true` 不等于一定导出。
- `backtrace_text_v1` 的 artifact 可空约定是：
  - `plan_prompt = null`
  - `plan_output = null`
  - `plan_parsed = null`
  - `insight_plan_parsed = null`
  - `write_prompt` / `write_output` / `thinking` 保留
- 当前整个 insight family 都会被 generation-audit 的硬问题拦导出，硬问题范围为：
  - `no_proof_echo`
  - `visible_only_boundary`
- `goal_gap_specificity`、`aux_selection_grounded`、`multi_point_staging` 等仍只记录在 artifacts，不阻止导出。

## 6. `item_audits.jsonl`

这个文件是 run 级轻量审计索引，适合快速统计 surface 结果。

| 字段 | 类型 | 含义 |
|------|------|------|
| `sample_order` | `int` | 与 `item_records.jsonl` 对齐的顺序 |
| `input_index` | `int` | 源样本索引 |
| `goal_type` | `str \| null` | 目标类型，便于分层统计 |
| `aux_type` | `str \| null` | 辅助构造类型，便于分层统计 |
| `source_audit` | `object` | 源样本检查结果 |
| `generation_audit` | `object` | 脚本终检和质量审计结果 |
| `surface_pass` | `bool` | 是否通过脚本终检 |
| `success` | `bool` | 兼容字段，等同 `surface_pass` |

## 7. `semantic_audits.jsonl`

这个文件是 run 级语义审读落盘入口。生成阶段会先写占位 stub，后续由人工或 Codex 回填。

| 字段 | 类型 | 含义 |
|------|------|------|
| `sample_order` | `int` | 必须与 `item_audits.jsonl` 对齐 |
| `input_index` | `int` | 必须与 `item_audits.jsonl` 对齐 |
| `image_path` | `str` | 图片路径，便于人工复核 |
| `goal_type` | `str \| null` | 当前样本的目标类型，如 `eqangle` / `eqratio` |
| `aux_type` | `str \| null` | 当前样本的辅助构造形态，如 `single_point` / `multi_point` |
| `surface_pass` | `bool` | 该样本是否先过了 surface 检查 |
| `semantic_pass` | `bool \| null` | 语义审读结论；`null` 表示尚未审 |
| `manual_critical_error` | `bool \| null` | 是否存在人工确认的关键错误 |
| `review_status` | `str` | `pending` 或 `reviewed` |
| `review_checklist_version` | `str` | 当前使用的语义审读口径版本 |
| `reviewer` | `str \| null` | 审读者标识 |
| `issue_codes` | `list[str]` | 结构化语义问题代码；代码表见 `SEMANTIC_REVIEW_GUIDE.md` |
| `issues` | `list[str]` | 语义问题列表 |
| `notes` | `str` | 审读备注 |

约束：

1. 行数必须和 `item_audits.jsonl` 完全一致。
2. 每行 `(sample_order, input_index)` 必须逐行对齐。
3. 若 `semantic_pass` 非空，`review_status` 应视为 `reviewed`。
4. `review_checklist_version` 当前必须为 `cot_sft_semantic_review_v1`。
5. 若 `semantic_pass = false`，应至少填写一个 `issue_codes` 或 `issues`。

## 8. `summary.json`

这个文件是 run 级汇总。它同时保留兼容字段和新的 surface/semantic 双层字段。

| 字段 | 类型 | 含义 |
|------|------|------|
| `artifact_schema_version` | `str` | 当前 artifacts schema 版本 |
| `input_jsonl` | `str` | 本次输入文件 |
| `total_candidates_with_aux` | `int` | 输入中带 aux 的总候选数 |
| `sampled_items` | `int` | 本次实际抽样条数 |
| `successful_items` | `int` | 兼容字段，等同 `surface_pass_items` |
| `failed_items` | `int` | 兼容字段，等同 `surface_fail_items` |
| `surface_pass_items` | `int` | surface 通过数 |
| `surface_fail_items` | `int` | surface 失败数 |
| `surface_pass_rate` | `float \| null` | surface 通过率 |
| `exported_items` | `int` | 最终写入训练 jsonl 的样本数 |
| `filtered_generation_audit_items` | `int` | 因 generation-audit 硬问题被挡住导出的样本数 |
| `exported_rate` | `float \| null` | 最终导出率 |
| `semantic_reviewed_items` | `int` | 已做语义审读的样本数 |
| `semantic_pass_items` | `int` | 语义通过数 |
| `semantic_fail_items` | `int` | 语义失败数 |
| `semantic_pass_rate` | `float \| null` | 已审样本中的语义通过率 |
| `manual_critical_error_items` | `int` | 人工确认关键错误数 |
| `manual_critical_error_rate` | `float \| null` | 已审样本中的关键错误比例 |
| `semantic_review_status` | `str` | `not_reviewed` / `partially_reviewed` / `fully_reviewed` |
| `avg_attempts_used` | `float \| null` | 样本级 `attempts_used` 的 run 级平均值 |
| `source_audit_issue_items` | `int` | 源样本审计发现问题的条数 |
| `generation_audit_issue_items` | `int` | 生成审计发现问题的条数 |
| `num_workers` | `int` | worker 数 |
| `max_retries_per_stage` | `int` | 每阶段最大重试次数 |
| `model_name` | `str` | 教师模型名 |
| `output_jsonl` | `str` | 最终输出路径 |
| `artifacts_dir` | `str` | 本次 artifacts 目录 |
| `runtime_seconds` | `float` | run 总耗时 |

## 9. 语义审读刷新流程

推荐顺序如下：

1. 先生成 run，拿到 `item_audits.jsonl` 和 `semantic_audits.jsonl` 占位文件。
2. 迭代阶段可先运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --print-pending \
  --surface-pass-only \
  --max-items 20
```

   - 这会输出当前待审样本队列，默认优先给已经 `surface_pass` 的样本做 Codex 语义审读。
   - 如果只需要待审索引，`item_audits.jsonl` 就足够。
   - 如果要直接把完整审读上下文交给 Codex，可继续运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --print-pending \
  --print-pending-payloads \
  --surface-pass-only
```

   - 或导出为 JSONL：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --surface-pass-only \
  --export-pending-review-jsonl /path/to/pending_review_payloads.jsonl
```

   - 这两种 payload 模式都依赖 `item_records.jsonl`，因此要求原始 run 是带 `-v/--verbose` 生成的。
3. 人工或 Codex 按样本回填 `semantic_audits.jsonl`。
   - 具体填写口径见 [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/reference/SEMANTIC_REVIEW_GUIDE.md)
4. 运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --write-summary
```
