# CoT SFT Status

## 当前结论

当前默认主线已经阶段性从 “默认要求 `aux -> full closure`” 收窄到 `insight -> aux`：

- 默认：`insight_image_v1`
- text-only sibling：`insight_text_v1`
- text-only backtrace：`backtrace_text_v1`
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
- `backtrace_text_v1` generation style 已作为独立 text-only writer-only mainline 落地
- proof DAG -> `InsightSlots` 的脚本抽取已落地
- proof DAG -> `BacktraceSlots` / `WriterHandoff` 的脚本抽取已落地
- `InsightPlan` planner / writer contract 已落地
- `item_records.jsonl` 已保存：
  - `insight_slots`
  - `insight_plan_parsed`
  - `backtrace_slots`
  - `writer_handoff`
  - `writer_validation_issues`
- 最终训练样本仍保持：
  - `thinking`
  - `aux`
  - `output = thinking + "\n" + aux`
- `insight_image_v1` 最终样本保留 `image_path`
- `insight_text_v1` 最终样本省略 `image_path`
- `backtrace_text_v1` 最终样本同样省略 `image_path`
- `dossier_v1` 已明确降级为：
  - legacy
  - benchmark
  - 对照路线

### 已验证

当前新增与受影响测试已覆盖并通过：

- `tests/test_cot_sft_backtrace_pipeline.py`
- `tests/test_cot_sft_insight_pipeline.py`
- `tests/test_cot_sft_writer_contracts.py`
- `tests/test_cot_sft_review_artifacts.py`
- `tests/test_cot_sft_replay_artifact_checks.py`
- `tests/test_cot_sft_audits.py`

额外运行级验证已经做过一轮 deterministic writer stub：

- `quality_review_v1` 前 `5` 条 smoke：`3/5` 通过
  - 失败类型：`writer_validation_failed: early_hidden_relation`
- 默认大库顺序前 `20` 条含 aux 样本：`16/20` 通过
  - 失败类型：`writer_validation_failed: early_hidden_relation`
- 对这 `16` 条中的前 `10` 条通过样本做离线人工抽查：
  - 结构上都遵守了 staged visible backtrace 合同：`goal -> current claim -> visible support -> remaining visible subgoal(s) -> visible boundary -> aux`
  - terminal visible boundary 和 supporting C1 都来自落盘的 `backtrace_slots`
  - 但文本明显仍偏模板化、偏保守；这证明链路和 hard checks 已工作，不代表真实 teacher writer 已经达到最终语义质量目标

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

### 4. `backtrace_text_v1` 的 hard check 还在收敛期

当前 deterministic run 的主要失败都集中在 `early_hidden_relation`。

这说明：

- 新链路已经能稳定把失败收敛到少数可读问题码
- 但 `early_hidden_relation` 的精度还需要继续用真实 teacher 输出和人工审读去校准

### 5. `backtrace_text_v1` 目前验证的是结构合同，不是最终文风质量

当前离线抽查已经确认：

- `V_core -> backtrace_stages -> terminal visible boundary -> aux` 的主结构可落盘、可回放、可检查

但同一轮抽查也确认：

- 通过 hard checks 的样本仍然可能过于模板化
- 这条路线还没有经过真实 teacher writer 的 10 条以上语义通过样本抽查

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
