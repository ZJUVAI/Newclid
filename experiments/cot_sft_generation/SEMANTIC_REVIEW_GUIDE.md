# CoT SFT Semantic Review Guide

本文档给 `semantic_audits.jsonl` 的人工 / Codex 审读提供统一口径。它回答的是：

- `semantic_pass` 应该在什么条件下打 `true`
- `manual_critical_error` 什么时候应打 `true`
- `issue_codes` 应该如何填写
- 不同 Codex 会话如何避免对同一类问题给出漂移的审读结论

当前 checklist 版本：

- `cot_sft_semantic_review_v1`

## 1. 审读必看材料

每条样本至少同时看：

- 原题文本
- 图片
- 最终 `thinking`
- 原始 `aux`

如果 run artifacts 可用，建议同时看：

- `plan_parsed`
- `generation_audit`
- `source_audit`

## 2. `semantic_pass` 判定规则

只有下面几项同时成立，才应标 `semantic_pass = true`：

- 文本整体读起来像是从图片和题面观察得到，而不是在复述 hidden proof
- 坐标 / 视觉 cue 不是只被点名，而是真正进入了推理链
- `aux_direct_relations -> bridge_steps -> goal_finish` 形成了真实闭环
- 每个关键 bridge relation 都能由前文 support 推出
- 最后 2 到 4 步确实落到目标，而不是表面相似的替代结论

只要上述任一项明显不成立，就不应标 `semantic_pass = true`。

## 3. `manual_critical_error` 判定规则

下面任一情况出现，通常应标 `manual_critical_error = true`：

- 关键 bridge relation 明显不成立
- 末段闭环到错的 goal relation 或错的 goal modality
- `thinking` 明显依赖 hidden proof 口吻或不可见信息
- 多点 aux 的 staged strategy 严重缺失，导致正文基本不可用

`manual_critical_error = true` 时，不应再标 `semantic_pass = true`。

## 4. `issue_codes` 填写规则

`issue_codes` 应尽量使用下面的固定代码，而不是每次发明新标签：

- `not_visible_only`
  - 文本像在复述 hidden proof，不像 visible-only reasoning
- `full_figure_coverage_missing`
  - 只围着少量 anchor 打转，没有覆盖真正相关的可见子结构
- `coordinate_cue_unused`
  - 坐标 / 视觉 cue 被提到，但没有进入后续推理链
- `aux_direct_not_grounded`
  - `aux_direct_relations` 不是直接构造后果，或写错了直接后果
- `bridge_unsupported`
  - bridge relation 不能由同句或前文 support 推出
- `route_drift`
  - 路线偏离可信的 goal-side chain，出现伪 bridge 或高层跳跃
- `goal_finish_unclosed`
  - 最后 2 到 4 步没有真实落到目标
- `goal_type_mismatch`
  - 结尾落到错误的 goal type / relation family
- `staged_strategy_missing`
  - 多点 aux 没有写出 staged strategy
- `high_level_shorthand_without_support`
  - 用 `symmetry`、`center`、`midpoint property` 等高层词替代具体支撑
- `other`
  - 当前 taxonomy 覆盖不到的其他问题

填写原则：

- `semantic_pass = false` 时，至少填写一个 `issue_codes` 或 `issues`
- 优先填结构化 `issue_codes`
- `issues` 留给样本级自由文本说明，不代替 `issue_codes`

## 5. 推荐审读顺序

建议按下面顺序检查：

1. 先看目标是什么，确定这是 angle / ratio / similarity / congruence 哪一类闭环。
2. 再看 `aux` 的直接后果是否被正文正确承接。
3. 再看 bridge 是否逐步回接到旧图，而不是中途发明新路线。
4. 最后只盯末段 2 到 4 步，确认是否真的闭到目标。

## 6. 审读记录示例

```json
{
  "sample_order": 3,
  "input_index": 104,
  "goal_type": "eqratio",
  "aux_type": "single_point",
  "surface_pass": true,
  "semantic_pass": false,
  "manual_critical_error": true,
  "review_status": "reviewed",
  "review_checklist_version": "cot_sft_semantic_review_v1",
  "reviewer": "codex",
  "issue_codes": ["bridge_unsupported", "goal_finish_unclosed"],
  "issues": ["the last ratio step is not implied by the cited support"],
  "notes": "sample looks fluent but the closing ratio substitution is not justified"
}
```
