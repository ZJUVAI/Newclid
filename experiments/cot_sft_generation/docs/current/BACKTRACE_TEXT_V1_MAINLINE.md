# Backtrace Text V1 Mainline

`backtrace_text_v1` is a text-only writer-only mainline.

Its design goal is narrower than the insight family: instead of asking for an insight-first helper pitch, it starts from the visible goal, backtraces only through the non-aux visible portion of the hidden proof DAG, organizes that route into ordered visible stages, stops when a visible stage already has direct aux-point dependencies, and then motivates the approved auxiliary construction.

## Definitions

- `C1`
  - `premise-only closure`
  - 一个 proof step 属于 `C1`，当且仅当：
    - 该 step 的结论本身不含 aux 点
    - 且它的所有 proof 前驱要么是 premise，要么已经在 `C1` 中
- `C2`
  - 结论表面不含 aux 点的所有 step；只看 statement，不看推导过程
- `C3`
  - `ProofDAG \ C1`
- `V`
  - `V = C2 ∩ C3`
  - 结论本身不含 aux 点，但又不是仅靠 premises 就能推出的结论
- `H`
  - `H = C3 \ C2`
  - 不属于 premise-only，且结论本身含 aux 点的结论
- `V_core`
  - 从 `goal` 出发，只沿 `dep ∈ V` 的边反向回溯所能到达的那部分 `V`
- `backtrace_stage`
  - `V_core` 中 writer 会显式叙述的一层可见 claim
  - 每层保留三类 direct 依赖：
    - 已可见支持 `visible_support = deps ∩ C1`
    - 仍需继续回溯的可见子目标 `next_v = deps ∩ V_core`
    - 已经触到 aux 路线的阻塞 `blocking_h = deps ∩ H`
- `U`
  - `U = V \ V_core`
  - `backtrace_text_v1` 第一版忽略
- `frontier_nodes`
  - 兼容字段
  - 在当前版本里等于 direct deps 已经触到 `H` 的 terminal `backtrace_stage`
- `supporting_c1_by_frontier`
  - 兼容字段
  - 每个 terminal stage 的直接 `C1` 支持；只作已有支持，不继续主回溯展开

## Flow

`backtrace_text_v1` 固定走：

`formal problem/aux/proof -> Proof DAG -> BacktraceSlots -> WriterHandoff -> writer -> hard checks -> thinking + 原始 aux`

这一支路明确不做：

- 不走 planner
- 不生成 planner prompt
- 不生成 planner validation
- 不写 planner artifacts
- 不使用 `image_scan`
- 不使用 `goal_gap_summary_seed`
- 不使用 `required_aux_effect`
- 不使用 `aux_direct_consequences`
- 不处理 `U = V \ V_core`
- 不做在线深语义裁判

## Structures

`BacktraceSlots` 至少包含：

- `C1_step_ids`
- `C2_step_ids`
- `C3_step_ids`
- `V_step_ids`
- `H_step_ids`
- `V_core_step_ids`
- `backtrace_root_step_id`
- `backtrace_stage_order_step_ids`
- `backtrace_stages`
- `terminal_stage_ids`
- `backtrace_chain_step_ids`
- `frontier_node_ids`
- `supporting_c1_by_frontier`
- `aux_construction_formal`
- `aux_construction_nl`

同一提取层还会统一生成 canonical NL 字段：

- `goal_nl`
- `backtrace_chain_nl`
- `frontier_nodes_nl`
- `supporting_c1_facts_nl`
- `aux_construction_nl`

`WriterHandoff` 的固定最小字段是：

- `goal_nl`
- `backtrace_stages`
- `terminal_claims_nl`
- `aux_construction_nl`

## Writer Contract

writer prompt 不把这些规则塞进 handoff，而是直接写死：

- 顺序：`goal -> current claim -> visible support -> remaining visible subgoal(s) -> visible boundary -> aux`
- 不提图片、不提坐标
- 不提 proof step id / rule id / hidden proof / internal schema name
- theorem / proof-style phrasing 只作软提醒，不作硬拒绝
- aux 之前不得提前说 hidden route 结论
- 不改变真实 aux 构造的几何语义
- 输出只返回 plain-text body；脚本再包 `<thinking>...</thinking>`

## Online Checks vs Offline Review

在线 hard checks 只负责高精度边界：

- `thinking` 包装格式
- proof marker / rule marker 泄露
- hidden meta language
- text-only boundary
- `aux_construction` 对齐
- 叙事顺序粗检查
- aux 之前明显 hidden relation 提前出现

在线阶段不做深语义裁判。

离线 Codex / 人工抽样负责：

- 是否真的沿 `V_core` 回溯
- 是否在 direct-`H` 的 visible boundary 停住
- 是否只把 `C1` 当支持而不继续主回溯
- aux 引入是否自然
- 是否虽过 hard checks 但仍空泛、偷渡 hidden route、逻辑断裂

## Artifacts

`backtrace_text_v1` 会新增：

- `backtrace_slots`
- `writer_handoff`
- `writer_validation_issues`

同时约定：

- `plan_prompt = null`
- `plan_output = null`
- `plan_parsed = null`
- `insight_plan_parsed = null`
- `write_prompt` / `write_output` / `thinking` 仍保留

## Entrypoint

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  --generation-style backtrace_text_v1
```
