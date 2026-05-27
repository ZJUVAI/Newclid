# Current CoT SFT Design

当前 CoT SFT 设计已经改成双轨：

- `insight_v1`：默认主线
- `dossier_v1`：legacy / benchmark / fallback
- `model_evidence_legacy`：更早的兼容回放路线

如果只是继续主线开发，先读 [INSIGHT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_V1_MAINLINE.md)。

## 总体目标

生成期教师侧仍可看到完整记录：

- 图片
- 公开题面
- `<aux>`
- hidden proof / proof DAG
- visible point 坐标

导出给学生的数据仍只保留：

- `input = public problem`
- `thinking`
- `aux`
- `output = thinking + "\n" + aux`

区别在于默认 `thinking` 不再追求 “aux -> full closure” 的完整收尾，而是优先学习：

1. 观察图和题面里已有的结构
2. 说清当前还缺哪类 bridge
3. 说清 helper 需要先制造什么效果
4. 因此提出哪个 aux

## 双轨分工

### `insight_v1`

主线由三层组成：

1. `core/insight_extractor.py`
   - 从 proof DAG 提取 `InsightSlots`
   - 只提结构化 checkpoint，不生成长自然语言

2. `core/insight_pipeline.py`
   - 定义 planner / writer prompt
   - 校验 `InsightPlan`
   - 提供 scripted fallback plan 和 scripted fallback writer

3. [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py)
   - 只负责入口分发和 stage orchestration
   - `generation_style=insight_v1` 时走新的 planner / writer contract

`InsightSlots` 只进入 artifacts，不进入最终训练样本。当前持久化字段：

- `insight_slots`
- `insight_plan_parsed`

### `dossier_v1`

`dossier_v1` 不再是默认主产线，但仍保留三类用途：

- benchmark 对照
- proof DAG scripted fallback
- 当 `insight_v1` 无法抽出 slots 或 plan/writer 失败时的降级路线

### 公共基础设施

以下模块仍被双轨共用：

- `core/proof_dag.py`
- `core/geometry_text.py`
- `core/audits.py`
- `core/run_artifacts.py`
- `semantic_review.py`

## 当前入口状态

- CLI 默认：`--generation-style insight_v1`
- legacy 主线：`--generation-style dossier_v1`
- 更早兼容路线：`--generation-style model_evidence_legacy`

`process_and_generate_sft(...)` 的实际分发顺序是：

1. 如果指定 `insight_v1`，先跑 insight planner / writer
2. 若 `insight_v1` 失败，则降级到 `dossier_v1`
3. 若显式指定 `dossier_v1`，只走 legacy dossier 路线
4. 若显式指定 `model_evidence_legacy`，走最旧的兼容链路

## Artifact 约定

所有 generation style 仍共享：

- `summary.json`
- `item_records.jsonl`
- `item_audits.jsonl`
- `semantic_audits.jsonl`

但 `insight_v1` 额外保存：

- `insight_slots`
- `insight_plan_parsed`

最终导出的训练 JSONL 不新增隐藏字段，仍然只保留学生侧需要看到的内容。
