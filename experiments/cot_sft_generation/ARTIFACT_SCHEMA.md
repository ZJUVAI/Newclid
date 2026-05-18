# CoT SFT Artifact Schema

本文档给出 `experiments/cot_sft_generation` 当前长期维护时应默认依赖的 artifacts 字段协议。它和 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/CURRENT_DESIGN.md) 的区别是：

- `CURRENT_DESIGN.md` 说明“代码现在怎么跑”
- 本文档说明“落盘文件里有哪些稳定字段，以及后续怎样读它们”

当前 schema 的实现入口主要有两个：

- [run_artifacts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/run_artifacts.py)
- [semantic_review.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/semantic_review.py)
- [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/SEMANTIC_REVIEW_GUIDE.md)

固定 benchmark 资产和其 manifest 见 [benchmarks/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/README.md)。

## 1. 版本兼容约定

1. 长期读 run 结果时，优先使用 `surface_pass`，不要再把 `success` 当主字段。
2. `success` 目前只为兼容旧脚本保留，语义上等同于 `surface_pass`。
3. 任何新增长期字段，都应先落到 `run_artifacts.py`，再同步更新本文档。

## 2. 最终数据集输出条目

最终输出 JSONL 的每条记录由 `build_dataset_output_record(...)` 生成，稳定字段如下：

| 字段 | 类型 | 含义 |
|------|------|------|
| `instruction` | `str` | 训练指令文本 |
| `input` | `str` | 学生模型可见题面 |
| `thinking` | `str` | 最终 `<thinking>...</thinking>` |
| `aux` | `str` | 原始 `<aux>...</aux>` |
| `output` | `str` | `thinking + "\n" + aux` |
| `image_path` | `str` | 图片路径 |
| `_order` | `int` | 本次 run 中的样本顺序 |

## 3. `item_records.jsonl`

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
| `write_output` | `str \| null` | writer 原始输出 |
| `thinking` | `str \| null` | 最终 thinking |
| `surface_pass` | `bool` | 是否通过脚本终检 |
| `success` | `bool` | 兼容字段，等同 `surface_pass` |
| `attempts_used` | `int \| null` | 本条样本实际重试次数 |
| `elapsed_seconds` | `float \| null` | 本条样本耗时 |
| `error` | `str \| null` | 失败原因 |

## 4. `item_audits.jsonl`

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

## 5. `semantic_audits.jsonl`

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

## 6. `summary.json`

这个文件是 run 级汇总。它同时保留兼容字段和新的 surface/semantic 双层字段。

| 字段 | 类型 | 含义 |
|------|------|------|
| `input_jsonl` | `str` | 本次输入文件 |
| `total_candidates_with_aux` | `int` | 输入中带 aux 的总候选数 |
| `sampled_items` | `int` | 本次实际抽样条数 |
| `successful_items` | `int` | 兼容字段，等同 `surface_pass_items` |
| `failed_items` | `int` | 兼容字段，等同 `surface_fail_items` |
| `surface_pass_items` | `int` | surface 通过数 |
| `surface_fail_items` | `int` | surface 失败数 |
| `surface_pass_rate` | `float \| null` | surface 通过率 |
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

## 7. 语义审读刷新流程

推荐顺序如下：

1. 先生成 run，拿到 `item_audits.jsonl` 和 `semantic_audits.jsonl` 占位文件。
2. 人工或 Codex 按样本回填 `semantic_audits.jsonl`。
   - 具体填写口径见 [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/SEMANTIC_REVIEW_GUIDE.md)
3. 运行：

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --write-summary
```

4. 用刷新后的 `summary.json` 记录：
   - `semantic_review_status`
   - `semantic_pass_rate`
   - `manual_critical_error_items`
   - `manual_critical_error_rate`

注意：

- `semantic_review.py` 当前只刷新语义审读相关汇总字段，不会重新计算 `avg_attempts_used` 这类生成期统计。

## 8. 最小验证入口

为了避免长期维护依赖额外测试框架，当前最小验证入口应保证在标准库环境里可跑：

```bash
python experiments/cot_sft_generation/maintenance_smoke_check.py
```

它会统一覆盖：

1. core files 的 `py_compile`
2. benchmark manifest 与固定输入文件的一致性
3. `generate_cot_sft.py --help`
4. `semantic_review.py --help`
5. `tests/test_cot_sft_*.py` 的 `unittest` 回归
