# CoT SFT Status

## 当前结论

当前默认主线已经从 `aux -> full closure` 切到 `insight -> aux`：

- 默认：`insight_v1`
- legacy：`dossier_v1`
- fallback compatibility：`model_evidence_legacy`

切换原因很直接：

1. 主任务是提升 aux proposal 能力，不是训练完整证明续写。
2. `dossier_v1` 虽然保留了 benchmark 和 fallback 价值，但它天然更接近 “完整 closure 叙述”，不再适合作为默认训练目标。
3. proof 仍然是内部监督源，但 writer 不应再看到 full hidden route。

## 当前实现状态

### 已完成

- `insight_v1` generation style 已落地并成为 CLI 默认值
- proof DAG -> `InsightSlots` 的脚本抽取已落地
- `InsightPlan` planner / writer contract 已落地
- `item_records.jsonl` 已保存：
  - `insight_slots`
  - `insight_plan_parsed`
- 最终训练样本仍保持：
  - `thinking`
  - `aux`
  - `output = thinking + "\n" + aux`
- `dossier_v1` 已明确降级为：
  - legacy
  - benchmark
  - fallback

### 已验证

当前新增与受影响测试已覆盖并通过：

- `tests/test_cot_sft_insight_pipeline.py`
- `tests/test_cot_sft_writer_contracts.py`
- `tests/test_cot_sft_review_artifacts.py`
- `tests/test_cot_sft_proof_dag.py`
- `tests/test_cot_sft_audits.py`
- `tests/test_cot_sft_fixture_pipeline.py`

## 当前风险

### 1. `InsightSlots` 仍是 heuristic extraction

proof DAG 已经是强监督源，但 `required_aux_effect`、`first_bridge_checkpoint`、`pre_goal_checkpoint` 仍然是脚本启发式选点，不是 proof engine 原生字段。

### 2. `insight_v1` writer 仍偏保守

当前 writer contract 明确限制：

- 不复述 full proof
- 不列 theorem catalog
- bonus tail 最多 1 到 2 句

这能压住 proof echo，但自然度还不是最终形态。

### 3. multi-point aux 数据格式还不够统一

当前代码已经强制 multi-point aux 提供 `stage_order`，但原始 `<aux>` 记录格式本身仍有历史不一致，后续还需要继续清理。

## Benchmark 口径

当前建议把评测拆成两层：

1. `dossier_v1`
   - 继续作为 legacy benchmark / fallback 基线

2. `insight_v1`
   - 重点看：
     - `goal_gap_specificity`
     - `aux_selection_grounded`
     - `visible_only_boundary`
     - `multi_point_staging`
     - `no_proof_echo`

结论上，`dossier_v1` 的 surface 通过率不再等价于主线质量；主线是否有效，应优先看 `insight_v1` 的 gap-specificity 和 aux-grounding。
