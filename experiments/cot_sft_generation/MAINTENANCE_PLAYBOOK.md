# CoT SFT Maintenance Playbook

本文档描述 `experiments/cot_sft_generation` 这条链路在长期 Codex 迭代时的维护约定。它不替代 [README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/README.md) 的目标说明，也不替代 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/CURRENT_DESIGN.md) 的当前实现说明；它回答的是：

- 这套代码和文档现在如何分工
- 改某一类逻辑时，必须同步检查哪些文件
- 哪些实验资产必须持久化到仓库，不能只留在 `/tmp`
- 后续 Codex 迭代时，怎样避免“代码变了，文档和证据口径没跟上”

## 1. 文件分工

### 1.1 顶层说明文档

- [README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/README.md)
  - 回答：
    - 这条链路要产出什么数据
    - 数据质量目标是什么
    - 迭代规范流程是什么
    - 脚本检测与 Codex 人审如何分工
  - 适合更新的场景：
    - 目标口径变化
    - 验收协议变化
    - 长期适用的流程变化

- [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/CURRENT_DESIGN.md)
  - 回答：
    - 当前代码实际跑了哪些阶段
    - `plan`、`coverage_targets`、writer contract 等字段现在是什么意思
    - artifacts 当前如何落盘
  - 适合更新的场景：
    - 代码实现变化
    - 新增/删除字段
    - 新增/删除阶段
    - summary 或 audit schema 变化

- [STATUS.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/STATUS.md)
  - 回答：
    - 当前最好证据是什么
    - 离目标还有什么差距
    - 下一步要改什么
  - 适合更新的场景：
    - 对“当前质量”的判断发生变化
    - 新的人审结论推翻了旧结论
    - 下一轮修改方向改变

- [EXPERIMENT_LOG.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/EXPERIMENT_LOG.md)
  - 回答：
    - 某一天具体跑了什么
    - 某个提交对应哪次回归
    - 当时看到的 live evidence 是什么
  - 适合更新的场景：
    - 新 run 落盘
    - 新 commit 对应的实验结果确认
    - 新的人审结论需要追加到时间线

### 1.2 代码文件

- [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py)
  - 当前主入口，负责：
    - source audit
    - planner / writer 调用
    - validator
    - generation audit
    - 主流程编排
  - 任何对 prompt、validator、artifact schema、run summary 的修改，都必须同步更新 `CURRENT_DESIGN.md`。

- [run_artifacts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/run_artifacts.py)
  - 当前 artifacts/schema 层，负责：
    - 数据集输出条目 schema
    - `item_record`
    - `item_audits.jsonl`
    - `semantic_audits.jsonl`
    - `summary.json`
  - 如果改动的是 run summary、surface/semantic pass 字段、人工审读占位 schema，这里应优先作为落点，而不是继续把 schema 拼装逻辑塞回主脚本。

- [prepare_metadata.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/prepare_metadata.py)
  - 独立的前处理脚本，负责抽样和反转图片。
  - 如果这里只改采样元数据，不需要更新主链设计文档；只有当输入协议变化时，才要更新 `README.md` 或 `CURRENT_DESIGN.md`。

## 2. 变更类型与必查文件

### 2.1 改 prompt 或 writer handoff

至少检查：

- `generate_cot_sft.py` 里的 `build_plan_prompt(...)` / `build_write_prompt(...)`
- `CURRENT_DESIGN.md`
- `STATUS.md` 的“下一步修改方向”是否还准确

如果 prompt 的目标或验收口径也变了，还要检查：

- `README.md`

### 2.2 改 validator 或 audit 规则

至少检查：

- `generate_cot_sft.py` 里的相关 validator / audit 函数
- `CURRENT_DESIGN.md`
- `README.md` 里的长期验收口径是否仍匹配
- `STATUS.md` 里的“距离目标的差距”是否要重写

### 2.3 改 artifacts schema 或 run summary

至少检查：

- `generate_cot_sft.py` 的落盘逻辑
- `CURRENT_DESIGN.md` 的 artifacts 说明
- `README.md` 的“迭代规范流程”是否还要求了当前代码没有落盘的字段
- 历史实验记录里是否存在旧字段口径，需要补说明

### 2.4 改质量判断口径

至少检查：

- `README.md`
- `STATUS.md`
- `EXPERIMENT_LOG.md`

如果新口径需要代码承接，还要检查：

- `generate_cot_sft.py`
- 对应 run artifacts schema

## 3. 长期回归资产要求

当前最大的长期维护风险，不是单个 prompt 细节，而是核心证据大量停留在 `/tmp`。长期 Codex 迭代必须逐步把下面这些资产持久化到仓库内的稳定位置。

### 3.1 必须持久化的基线

至少应有：

- 固定失败样本清单
- 固定回归样本清单
- 按 `goal_type` 分层的审读样本清单
- 按 `aux_type` 分层的审读样本清单

这些清单不应只在 `/tmp/*.jsonl` 中存在。否则换机器、清空 `/tmp`、或换容器后，Codex 无法稳定复用同一批基线。

### 3.2 人工/Codex 语义审读结果

对任何被拿来支持“质量提升”的 run，都应有可落盘的语义审读记录，而不是只保留在聊天记录或临时笔记里。

建议长期维持：

- 样本级 `semantic_audits.jsonl`
- run 级 `surface_pass_rate`
- run 级 `semantic_pass_rate`
- run 级 `manual_critical_error_rate`

## 4. 当前代码最需要避免的维护风险

### 4.1 单文件过大

当前主脚本体量已经较大，后续若继续增长，会让以下几类修改更容易互相干扰：

- prompt 调整
- validator 调整
- artifacts schema 调整
- 审计指标调整

因此，后续重构时应优先把“纯 schema / artifacts 逻辑”和“模型推理逻辑”拆开，而不是继续把所有辅助函数堆回主文件。

### 4.2 文档先行、代码不跟

如果文档里已经要求：

- `surface_pass`
- `semantic_pass`
- `manual_critical_error_rate`

但代码 artifacts 还没有落盘这些字段，那么这类要求仍然只是“流程口径”，还不是“可执行协议”。每次新增长期规则时，都要尽快让代码 artifacts 至少能承接最基本的字段。

### 4.3 过度依赖对话记忆

Codex 可以基于对话上下文推进，但长期维护不能依赖“之前在某次对话里讨论过”。凡是会影响后续判断的结论，都应最终回写到：

- `README.md`
- `CURRENT_DESIGN.md`
- `STATUS.md`
- `EXPERIMENT_LOG.md`

至少其中之一。

## 5. 每次关键修改后的最小检查清单

在提交前，至少确认：

1. 改动影响的是哪一类东西
   - prompt
   - validator
   - audit
   - artifact schema
   - run orchestration
   - 文档口径

2. 对应文档是否同步了
   - `README.md`
   - `CURRENT_DESIGN.md`
   - `STATUS.md`
   - `EXPERIMENT_LOG.md`

3. 当前 run artifacts 是否还能回答下面这些问题
   - 哪些样本 `surface_pass`
   - 哪些样本脚本失败
   - 失败原因是什么
   - 是否做过语义审读
   - 如果做过，人审结论是什么

4. 这轮结论是否仍然依赖 `/tmp` 中不可复现的临时文件
   - 如果是，要在文档里明确标注它只是“临时证据”，不能当长期基线

## 6. 当前仍需补齐的说明

截至当前版本，仍建议后续补齐：

1. 固定 benchmark 清单落仓规则
2. 语义审读 artifacts 的正式 schema
3. `summary.json` 字段表
4. `item_records.jsonl` / `item_audits.jsonl` 字段表
5. “改某个 goal type 的 prompt 时，应抽哪些样本做定向审读”的具体说明

这些内容一旦落地，应优先更新到 `CURRENT_DESIGN.md` 或新增专门 schema 文档，而不是只停留在聊天记录里。

## 7. 当前支撑程度判断

按当前代码与文档状态，这套链路已经可以支撑“有纪律的持续 Codex 迭代”，但还不能算“完全稳定的长期维护形态”。

### 7.1 已经具备的条件

- 目标说明、当前实现、状态判断、时间线记录已经分层
- 运行产物不再只有脚本通过/失败，也开始显式落：
  - `surface_pass`
  - `semantic_audits.jsonl` 占位记录
  - run 级 `surface_pass_rate`
- artifacts/schema 层已经单独拆出，不必继续所有字段都塞回主脚本

### 7.2 仍然限制长期稳定性的点

- 固定回归集和分层抽样集还没有真正版本化进仓库
- `semantic_pass` 仍需人工/Codex 回填，当前还没有自动 `critic` 阶段
- prompt / validator / audit 逻辑仍高度集中在主脚本里，后续还需要继续拆分

### 7.3 当前推荐结论

- 如果目标是下一轮继续按同一协议推进实验，当前结构已经够用
- 如果目标是把这条链路长期交给不同 Codex 会话、不同人或不同机器持续接手，仍建议优先补齐：
  - benchmark 持久化
  - 语义审读落盘协议
  - 更细的代码拆分
