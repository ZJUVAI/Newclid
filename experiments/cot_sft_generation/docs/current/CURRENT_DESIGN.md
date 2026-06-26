# Current CoT SFT Design

当前 CoT SFT 设计已经改成四轨：

- `backtrace_text_v2`：默认主线文档标签；运行时 style id 仍是 `backtrace_text_v1`
- `insight_image_v1`：image sibling mainline
- `insight_text_v1`：text-only sibling mainline
- `dossier_v1`：legacy / benchmark / 对照路线
- `model_evidence_legacy`：更早的兼容回放路线

如果只是继续默认主线开发，先读 [BACKTRACE_TEXT_V2_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/BACKTRACE_TEXT_V2_MAINLINE.md)；如果明确要做 insight 合同，再补读 [INSIGHT_IMAGE_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_IMAGE_V1_MAINLINE.md) 或 [INSIGHT_TEXT_V1_MAINLINE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/INSIGHT_TEXT_V1_MAINLINE.md)。

## 总体目标

生成期教师侧仍可看到完整记录：

- 图片
- 公开题面
- `<aux>`
- hidden proof / proof DAG
- visible point 坐标

导出给学生的数据仍只保留当前 style 允许看到的输入：

- `backtrace_text_v2`（运行时 style id: `backtrace_text_v1`）
  - `input = public problem`
  - `thinking`
  - `aux`
  - `output = thinking + "\n" + aux`
- `insight_image_v1`
  - `input = public problem`
  - `thinking`
  - `aux`
  - `output = thinking + "\n" + aux`
  - `image_path`
- `insight_text_v1`
  - `input = public problem`
  - `thinking`
  - `aux`
  - `output = thinking + "\n" + aux`

最终质量标准仍以 [DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md) 为准；这里描述的是当前默认实现与阶段性策略。

区别在于当前默认 `thinking` 暂时不把 “aux -> full closure” 的完整收尾作为主线要求，而是优先学习：

1. 观察图和题面里已有的结构
2. 说清当前还缺哪类 bridge
3. 说清 helper 需要先制造什么效果
4. 因此提出哪个 aux

这只是阶段性主线，不改变最终质量标准。当前 insight family 默认不要求质量目标第 5 点的完整 post-aux closure，但这不排斥更丰富的 `pre-aux` reasoning。

## 三轨分工

### `insight_image_v1`

主线由三层组成：

1. `core/insight_extractor.py`
   - 从 proof DAG 提取 `InsightSlots`
   - 只提结构化 checkpoint，不生成长自然语言

2. `core/insight_pipeline.py`
   - 定义 planner / writer prompt
   - 校验 `InsightPlan`
   - planner 和 writer 都会拿到图片与 raw `[Visible Point Coordinates]`
   - planner 自行从 visible coordinates 提炼 `image_scan`
   - 提供 scripted fallback plan
   - writer 校验失败时按 fail-closed 处理

3. [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py)
   - 只负责入口分发和 stage orchestration
   - `generation_style=insight_image_v1` 时走 image contract

### `insight_text_v1`

它与 `insight_image_v1` 共享 `InsightSlots` 和 `InsightPlan` 主体，但可见性合同不同：

- planner / writer 都是 text-only
- 不发送 `image_url`
- prompt 不暴露 visible-point coordinates
- source audit 与 final export 都不再要求图片和坐标输入
- 仍保留 planner fallback 与 writer fail-closed

### `dossier_v1`

`dossier_v1` 不再是默认主产线，但仍保留三类用途：

- benchmark 对照
- legacy 路线说明与历史回放
- 显式指定 `--generation-style dossier_v1` 时的对照运行

### 公共基础设施

以下模块仍被多轨共用：

- `core/proof_dag.py`
- `core/geometry_text.py`
- `core/audits.py`
- `core/run_artifacts.py`
- `semantic_review.py`

## 当前入口状态

- CLI 默认：`--generation-style backtrace_text_v1`（对应文档标签 `backtrace_text_v2`）
- text-only sibling：`--generation-style insight_text_v1`
- legacy 主线：`--generation-style dossier_v1`
- 更早兼容路线：`--generation-style model_evidence_legacy`

`process_and_generate_sft(...)` 的当前分发顺序是：

1. 如果指定 `insight_image_v1` 或 `insight_text_v1`，先跑 insight planner / writer
2. insight family 内部允许 planner 失败后回退到 scripted insight plan
3. 若 writer 校验失败，则该样本直接失败，不再自动降级到 `dossier_v1`
4. 若显式指定 `dossier_v1`，只走 legacy dossier 路线
5. 若显式指定 `model_evidence_legacy`，走最旧的兼容链路

## 当前合同摘要

当前 insight family 合同可以压缩成五点：

- `insight_image_v1` 的 planner 输入是 public problem、visible facts、图片、raw `[Visible Point Coordinates]`、approved auxiliary construction 和 `InsightSlots`
- `insight_text_v1` 的 planner / writer 输入只保留 formal problem、approved plan 和 `InsightSlots`，不含图片与坐标
- writer 可以在 construction 之后继续解释 helper 在局部打开了什么，但当前合同不再保留旧版的硬句数上限或固定语气要求
- 当前真正保留的硬边界是 hidden-proof leakage、internal refs、visible-only boundary
- 只有 `insight_image_v1` 允许正文显式写 visible-point coordinates；`insight_text_v1` 不允许

## Artifact 约定

所有 generation style 仍共享：

- `summary.json`
- `item_records.jsonl`
- `item_audits.jsonl`
- `semantic_audits.jsonl`

但 insight family 额外保存：

- `insight_slots`
- `insight_plan_parsed`

最终导出的训练 JSONL 不新增隐藏字段，仍然只保留学生侧需要看到的内容；其中 `image_path` 只在 `insight_image_v1` 中导出。
