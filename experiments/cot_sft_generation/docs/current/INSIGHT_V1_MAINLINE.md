# Insight V1 Mainline

## 当前阶段性目标

`insight_v1` 这里描述的是当前默认主线的阶段性优化目标，不是最终数据质量目标本身。

最终质量标准仍以 [DATA_QUALITY_REQUIREMENTS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/immutable/DATA_QUALITY_REQUIREMENTS.md) 为准，尤其其中第 5 点“需要包含从提出 aux 到解答出 goal 的完整逻辑”仍然是长期目标。

当前 `insight_v1` 只是把默认训练重点阶段性收窄为：

1. 从图和题面判断当前缺口
2. 说清 helper 需要制造什么局部效果
3. 因此提出哪个 auxiliary construction

最终学生侧输出仍保持：

- `thinking`
- `aux`

但 `thinking` 的默认风格已经改成 insight-first，而不是把 `post-aux full-closure retelling` 作为当前默认硬要求。

这里的阶段性收窄只表示：

- 当前默认不强求把 aux 之后一路收尾到 goal 的完整逻辑全写出来
- 当前阶段性不以质量目标第 5 点作为默认 writer 合同

这不表示：

- 最终质量目标被重写
- `pre-aux` reasoning 必须被压缩到极短
- 最终 `thinking` 不应显式使用可见点坐标

只要不泄露 hidden source，并且服务于 obstacle / helper / aux 判断，前段 visible-only reasoning 仍然可以更丰富，也允许显式使用 visible-point coordinates。

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

### 2. planner 只看可见输入和 slots，不看 full proof

[core/insight_pipeline.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/insight_pipeline.py) 的 planner prompt 只给：

- public problem
- visible facts
- raw `[Visible Point Coordinates]`
- approved auxiliary construction
- `InsightSlots`

planner 不再看完整 proof，也不负责输出 full closure chain。
`image_scan` 现在由模型根据 raw visible coordinates 自己决定是否生成，不再预先塞入脚本合成的 coordinate-relation text。
`<aux>` 的 direct consequences 仍可由脚本本地临时现算，但不再作为 planner / writer 合同字段。

[generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py) 里的 `generate_insight_thinking(...)` 对 `insight_v1` 已不再构造脚本侧 coordinate-derived `image_scan_candidates`；planner 运行时就是直接拿 visible facts、visible coordinates 和 slots 自行组织 `image_scan`。

### 3. writer 看批准后的 `InsightPlan`，也看 raw visible coordinates

当前实现里，writer 默认聚焦：

- 说清 visible gap
- 说清 helper 需要制造的 effect
- 说明为什么这个 aux 合适
- 在 construction 之后，只继续补与 helper 局部 unlock 直接相关的内容，不扩写成 full hidden closure retelling

这是一条默认收窄的实现主线，不是唯一合法内容边界。

- 更丰富的 `pre-aux` visible-only reasoning 仍然允许
- writer prompt 当前会同时给 approved plan 和 raw `[Visible Point Coordinates]`
- 显式 visible-point coordinates 仍然允许，只要它们服务于可见结构判断
- coordinates 只在有帮助时内联即可，不要求每次提到 visible point 都带坐标
- auxiliary points 不得被赋予坐标

## 校验边界

当前合同已经放松了一些更早版本里的泛化措辞限制和硬性篇幅上限；真正仍然重要的硬边界是：

- `goal_gap_type` 和 goal family 冲突
- `required_aux_effect` 脱离 slots
- `required_aux_effect` 与 `<aux>` 的 direct consequence 不对齐
- `aux_selection_reason` 发明新的 hidden relation
- multi-point aux 缺少 `stage_order`
- hidden-proof leakage / proof retelling / theorem list / hidden marker leak
- internal refs，例如 `visible_facts[i]`、`image_scan[i]` 这类内部引用语法
- visible-only boundary：不能把未在正文中建立的远端 goal-side 连接直接说成已经打通
- 如果正文内联 visible-point coordinates，这些坐标必须和可见坐标表一致
- auxiliary points 不得写成带坐标的点

fail-closed 语义保持不变：

- planner 失败时仍可回退到 scripted insight plan
- 但 scripted fallback 不再伪造 coordinate-derived `image_scan`，当前可能直接保留 `image_scan=[]`
- writer 失败仍直接判该样本失败，不再启用 scripted writer fallback

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

这表示当前阶段性把“提出正确 aux 并说清其局部必要性”放在更前面，而不是表示最终质量目标已经放弃第 5 点。

如果下一会话继续主线开发，优先改这条链，而不是继续扩大 `dossier_v1` 的 full-closure 逻辑。
