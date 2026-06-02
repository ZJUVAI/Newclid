# CoT SFT Status

## 当前结论

当前默认主线已经阶段性从 “默认要求 `aux -> full closure`” 收窄到 `insight -> aux`：

- 默认：`insight_image_v1`
- text-only sibling：`insight_text_v1`
- legacy：`dossier_v1`
- fallback compatibility：`model_evidence_legacy`

切换原因很直接：

1. 当前阶段性训练重点是提升 aux proposal 能力，而不是默认先优化完整证明续写。
2. `dossier_v1` 虽然保留了 benchmark 和 legacy 对照价值，但它天然更接近 “完整 closure 叙述”，不再适合作为当前默认主线。
3. proof 仍然是内部监督源，但 writer 不应再看到 full hidden route。

这不是最终目标收缩。最终质量标准仍以 [DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md) 为准，尤其第 5 点仍然存在；当前主线只是阶段性降低它在默认 writer 合同中的优先级。

## 当前实现状态

### 已完成

- `insight_image_v1` generation style 已落地并成为 CLI 默认值
- `insight_text_v1` generation style 已作为 sibling mainline 落地
- proof DAG -> `InsightSlots` 的脚本抽取已落地
- `InsightPlan` planner / writer contract 已落地
- `item_records.jsonl` 已保存：
  - `insight_slots`
  - `insight_plan_parsed`
- 最终训练样本仍保持：
  - `thinking`
  - `aux`
  - `output = thinking + "\n" + aux`
- `insight_image_v1` 最终样本保留 `image_path`
- `insight_text_v1` 最终样本省略 `image_path`
- `dossier_v1` 已明确降级为：
  - legacy
  - benchmark
  - 对照路线

### 已验证

当前新增与受影响测试已覆盖并通过：

- `tests/test_cot_sft_insight_pipeline.py`
- `tests/test_cot_sft_writer_contracts.py`
- `tests/test_cot_sft_review_artifacts.py`
- `tests/test_cot_sft_replay_artifact_checks.py`
- `tests/test_cot_sft_audits.py`

## 当前风险

### 1. `InsightSlots` 仍是 heuristic extraction

proof DAG 已经是强监督源，但 `required_aux_effect`、`first_bridge_checkpoint`、`pre_goal_checkpoint` 仍然是脚本启发式选点，不是 proof engine 原生字段。

### 2. insight-family writer 仍偏保守

当前 writer contract 明确限制：

- 不复述 full proof
- 不列 theorem catalog
- bonus tail 最多 1 到 2 句

这能压住 proof echo，但自然度还不是最终形态；同时它也意味着当前默认主线与最终质量目标之间存在已知 gap，尤其是第 5 点的完整 post-aux closure 被阶段性降权，而不是被删除。

### 3. multi-point aux 数据格式还不够统一

当前代码已经强制 multi-point aux 提供 `stage_order`，但原始 `<aux>` 记录格式本身仍有历史不一致，后续还需要继续清理。

## Benchmark 口径

当前建议把评测拆成三层：

1. `dossier_v1`
   - 继续作为 legacy benchmark / 对照基线

2. `insight_image_v1`
   - 重点看：
     - `goal_gap_specificity`
     - `aux_selection_grounded`
     - `visible_only_boundary`
     - `multi_point_staging`
     - `no_proof_echo`

3. `insight_text_v1`
   - 除了上面这些，还要额外看：
     - 是否真的不依赖图片
     - 是否真的不泄露 visible-point coordinates

结论上，`dossier_v1` 的 surface 通过率不再等价于主线质量；主线是否有效，应优先看 insight family 的 gap-specificity 和 aux-grounding。
