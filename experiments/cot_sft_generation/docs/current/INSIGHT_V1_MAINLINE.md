# Insight V1 Mainline

## 目标

`insight_v1` 的目标不是让学生学完整 hidden closure，而是让学生学会：

1. 从图和题面判断当前缺口
2. 说清 helper 需要制造什么局部效果
3. 因此提出哪个 auxiliary construction

最终学生侧输出仍保持：

- `thinking`
- `aux`

但 `thinking` 的默认风格已经改成 insight-first，而不是 full-closure retelling。

## 默认入口

当前 CLI 默认就是：

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --generation-style insight_v1
```

当前 `insight_v1` 已按 fail-closed 运行：

- `insight_v1` 失败时不再自动降级到 `dossier_v1`
- planner 仍保留 scripted plan fallback
- writer 不再使用 scripted body fallback；writer 校验失败即该样本失败

## 核心对象

### `InsightSlots`

由脚本直接从 proof DAG 抽取，当前持久化到 artifacts，但不会暴露给最终训练样本。

字段：

- `goal_family`
- `goal_gap_type`
- `required_aux_effect`
- `first_bridge_checkpoint`
- `pre_goal_checkpoint`
- `stage_order` 可选
- `evidence_windows`

### `InsightPlan`

由 planner 输出，再由脚本校验后交给 writer。

字段：

- `visible_facts`
- `image_scan`
- `goal_gap_type`
- `goal_gap_text`
- `required_aux_effect`
- `aux_construction`
- `aux_selection_reason`
- `stage_order` 可选
- `bonus_post_aux_tail` 可选

## 运行流程

### 1. 脚本抽取 `InsightSlots`

[core/insight_extractor.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/insight_extractor.py) 当前做的事：

- 从 goal 的祖先子图里找 aux-reachable steps
- 估计最早进入 goal 路径的 `required_aux_effect`
- 找第一次把 aux-side 接回旧图的 `first_bridge_checkpoint`
- 找 goal 前最后一个非纯 AR checkpoint 的 `pre_goal_checkpoint`
- 推断 `goal_gap_type`

### 2. planner 只看 slots，不看 full proof

[core/insight_pipeline.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/insight_pipeline.py) 的 planner prompt 只给：

- public problem
- visible facts
- visible image cues
- `InsightSlots`

planner 不再看完整 proof，也不负责输出 full closure chain。
`<aux>` 的 direct consequences 仍可由脚本本地临时现算，但不再作为 planner / writer 合同字段。

### 3. writer 只看批准后的 `InsightPlan`

writer 的职责被收窄为：

- 说清 visible gap
- 说清 helper 需要制造的 effect
- 说明为什么这个 aux 合适
- 如有必要，只补 1 到 2 句 very short post-aux tail

## 校验边界

当前 validator 会重点拦这几类退化：

- `goal_gap_type` 和 goal family 冲突
- `required_aux_effect` 脱离 slots
- `required_aux_effect` 与 `<aux>` 的 direct consequence 不对齐
- `aux_selection_reason` 发明新的 hidden relation
- multi-point aux 缺少 `stage_order`
- writer 退化成 proof retelling / theorem list / hidden marker leak

## Artifact 约定

`item_records.jsonl` 现在会额外保存：

- `insight_slots`
- `insight_plan_parsed`
- `exported_to_dataset`
- `dataset_filter_reason`

最终导出的训练样本不新增这些隐藏字段。

这里要区分两层状态：

- `surface_pass/success=true` 只表示生成链路本身成功
- `exported_to_dataset=true` 才表示该样本真的进入最终训练 jsonl

当前只有 `insight_v1` 会额外应用 generation-audit 导出门禁：

- 硬拦截：`no_proof_echo`、`visible_only_boundary`
- 只记告警不拦导出：`goal_gap_specificity`、`aux_selection_grounded`、`multi_point_staging`

## 当前评测重点

`insight_v1` 的 review 重点不是 full closure，而是：

- `goal_gap_specificity`
- `aux_selection_grounded`
- `visible_only_boundary`
- `multi_point_staging`
- `no_proof_echo`

如果下一会话继续主线开发，优先改这条链，而不是继续扩大 `dossier_v1` 的 full-closure 逻辑。
