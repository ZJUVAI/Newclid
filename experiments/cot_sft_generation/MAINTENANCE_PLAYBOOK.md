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

- [ARTIFACT_SCHEMA.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/ARTIFACT_SCHEMA.md)
  - 回答：
    - `summary.json`
    - `item_records.jsonl`
    - `item_audits.jsonl`
    - `semantic_audits.jsonl`
    - 最终输出 JSONL
    - 这些文件里有哪些稳定字段
  - 适合更新的场景：
    - schema 变更
    - 新增/废弃兼容字段
    - 语义审读刷新协议变化

- [SEMANTIC_REVIEW_GUIDE.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/SEMANTIC_REVIEW_GUIDE.md)
  - 回答：
    - `semantic_pass` 的统一判定口径
    - `manual_critical_error` 的使用边界
    - `issue_codes` 的固定代码表
  - 适合更新的场景：
    - 人审 checklist 变化
    - 新增 / 废弃 issue code
    - 不同 Codex 会话之间需要统一语义审读口径

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

- [benchmarks/README.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/README.md)
  - 回答：
    - 当前有哪些固定 benchmark
    - 这些 benchmark 的来源和用途
    - manifest 至少应记录哪些信息
  - 适合更新的场景：
    - 新 benchmark 落仓
    - 历史 benchmark 废弃或换代

### 1.2 代码文件

- [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py)
  - 当前主入口，负责：
    - planner / writer 调用
    - validator
    - 主流程编排
  - 任何对主流程阶段、validator、artifact schema、run summary 的修改，都必须同步更新 `CURRENT_DESIGN.md`。

- [audits.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/audits.py)
  - 负责：
    - `source audit`
    - `generation audit`
    - visible formal fact parsing
    - bridge sentence relation matching
  - 如果改的是 source/generation 审计规则、句级 relation 命中规则或可见 formal fact 解析，这里应优先作为落点，而不是继续把这些逻辑塞回主脚本。

- [run_artifacts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/run_artifacts.py)
  - 当前 artifacts/schema 层，负责：
    - `run_config.json`
    - `sampled_inputs.jsonl`
    - 数据集输出条目 schema
    - `item_record`
    - `item_audits.jsonl`
    - `semantic_audits.jsonl`
    - `summary.json`
  - 如果改动的是 run summary、surface/semantic pass 字段、人工审读占位 schema，这里应优先作为落点，而不是继续把 schema 拼装逻辑塞回主脚本。

- [prepare_metadata.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/prepare_metadata.py)
  - 独立的前处理脚本，负责抽样和反转图片。
  - 如果这里只改采样元数据，不需要更新主链设计文档；只有当输入协议变化时，才要更新 `README.md` 或 `CURRENT_DESIGN.md`。

- [geometry_text.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/geometry_text.py)
  - 负责：
    - goal / aux / visible relation 文本拆解
    - relation 归一化和 semantic match
    - hidden coordinate candidate / hint / guidance 生成
    - 跨 planner、validator、writer 共用的底层几何文本 helper
  - 如果改了 point mention、relation keyword、aux clause parsing、goal parsing、surface normalization，这里应优先作为落点，而不是继续把底层文本规则塞回主脚本。

- [writer_contracts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/writer_contracts.py)
  - 负责：
    - writer contract / bridge checklist
    - coverage target 计算
    - injected prefix 拼装
    - plan 到 writer handoff 的公共转换
  - 如果改了 focus points、sentence shell、prefix 结构、writer handoff 字段或 coverage target 逻辑，这里应优先作为落点，而不是继续把 writer 协议细节塞回主脚本。

- [prompt_builders.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/prompt_builders.py)
  - 负责：
    - planner / writer prompt 正文
    - planner / writer retry feedback
    - hidden supervisor payload 组装
  - 如果改的是 prompt 正文、retry guidance、prompt 中暴露的 hidden context、或 prompt 级约束口径，这里应优先作为落点，而不是继续把长 prompt 文本塞回主脚本。

- [maintenance_smoke_check.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/maintenance_smoke_check.py)
  - 负责：
    - core files `py_compile`
    - benchmark manifest 一致性检查
    - `generate_cot_sft.py --help`
    - `semantic_review.py --help`
    - `tests/test_cot_sft_*.py` 的统一回归入口
  - 如果新增长期维护必跑检查，应优先把它接到这里，而不是只补一条文档命令。

- [semantic_review.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/semantic_review.py)
  - 负责：
    - 校验 `semantic_audits.jsonl` 与 `item_audits.jsonl` 是否逐行对齐
    - 刷新 `summary.json` 的 run 级 semantic 指标
    - 按 `surface_pass` 优先级导出待审样本队列
    - 在 `item_records.jsonl` 可用时导出完整的 Codex 审读 payload
  - 如果改了语义审读字段、review status 规则、issue code 规则或 summary 汇总逻辑，这里必须和 `ARTIFACT_SCHEMA.md`、`SEMANTIC_REVIEW_GUIDE.md` 同步更新。

- [tests/test_cot_sft_review_artifacts.py](/root/GenesisGeo-cot/tests/test_cot_sft_review_artifacts.py)
  - 负责：
    - `run_artifacts.py`
    - `semantic_review.py`
    - summary 刷新协议
    的最小回归验证
  - 当前刻意写成 `unittest` 入口，避免长期维护依赖额外安装 `pytest`。

- [tests/test_cot_sft_audits.py](/root/GenesisGeo-cot/tests/test_cot_sft_audits.py)
  - 负责：
    - `audits.py`
    - `source audit`
    - bridge relation 句级命中规则
    - visible formal fact 抽取
    的最小回归验证
  - 如果改了 `audits.py` 的核心规则，这个测试文件应视为必跑最小回归。

- [tests/test_cot_sft_geometry_text.py](/root/GenesisGeo-cot/tests/test_cot_sft_geometry_text.py)
  - 负责：
    - `geometry_text.py`
    - relation normalization / semantic match
    - aux / goal / public problem 拆解
    的最小回归验证
  - 如果改了 relation surface、formal-text 解析或 hidden-route 对齐规则，这个测试文件应视为必跑最小回归。

- [tests/test_cot_sft_prompt_builders.py](/root/GenesisGeo-cot/tests/test_cot_sft_prompt_builders.py)
  - 负责：
    - `prompt_builders.py`
    - planner / writer prompt 关键段落存在性
  - 目的不是验证 prompt 语义好坏，而是避免重构后出现缺段、断引用或隐式依赖缺失。

- [tests/test_cot_sft_writer_contracts.py](/root/GenesisGeo-cot/tests/test_cot_sft_writer_contracts.py)
  - 负责：
    - `writer_contracts.py`
    - coverage target 派生
    - bridge target enrichment
    - writer handoff / injected prefix 结构
  - 如果改了 writer contract、focus point、prefix 或 handoff schema，这个测试文件应视为必跑最小回归。

- [tests/test_cot_sft_maintenance_smoke.py](/root/GenesisGeo-cot/tests/test_cot_sft_maintenance_smoke.py)
  - 负责：
    - `maintenance_smoke_check.py`
    - benchmark manifest 的结构约束
    - 仓库内 benchmark 资产的最小完整性验证
  - 如果新增 benchmark manifest 字段、subset 规则或 smoke check 行为，这个测试文件应视为必跑最小回归。

- [tests/test_cot_sft_fixture_pipeline.py](/root/GenesisGeo-cot/tests/test_cot_sft_fixture_pipeline.py)
  - 负责：
    - `process_and_generate_sft(...)`
    - `generate_thinking(...)`
    - planner -> writer -> artifacts 主链编排
    - 在不依赖外部 API 的情况下验证离线 fixture run
  - 如果改了主流程编排、stage 接口、item/run artifact 落盘或 validator 接线，这个测试文件应视为必跑最小回归。

## 2. 变更类型与必查文件

### 2.1 改 prompt 或 writer handoff

至少检查：

- `prompt_builders.py` 里的 `build_plan_prompt(...)` / `build_write_prompt(...)`
- 如果 prompt 依赖的上下文字段也变了，还要检查 `generate_cot_sft.py` 里的 wrapper / context 预计算
- `CURRENT_DESIGN.md`
- `STATUS.md` 的“下一步修改方向”是否还准确

如果 prompt 的目标或验收口径也变了，还要检查：

- `README.md`

### 2.2 改 validator 或 audit 规则

至少检查：

- `generate_cot_sft.py` 里的相关 validator 函数
- `audits.py` 里的 source / generation audit 或 relation matching 规则
- `tests/test_cot_sft_audits.py`
- `CURRENT_DESIGN.md`
- `README.md` 里的长期验收口径是否仍匹配
- `STATUS.md` 里的“距离目标的差距”是否要重写

### 2.3 改 artifacts schema 或 run summary

至少检查：

- `generate_cot_sft.py` 的落盘逻辑
- `run_artifacts.py`
- `semantic_review.py`
- `CURRENT_DESIGN.md` 的 artifacts 说明
- `ARTIFACT_SCHEMA.md`
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

### 2.5 改 benchmark manifest 或定向审读子集

至少检查：

- `benchmarks/README.md`
- 对应的 `*_manifest.json`
- `maintenance_smoke_check.py`
- `tests/test_cot_sft_maintenance_smoke.py`

如果变更会影响“某类修改该先审哪组样本”的默认协议，还要检查：

- `README.md`
- `STATUS.md`

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
- run 级 `avg_attempts_used`

当前已经落仓的最小基线是：

- [benchmarks/fixed_v104sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl)
- [benchmarks/fixed_v104sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json)
- [benchmarks/stratified_v1_12sample_input.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_input.jsonl)
- [benchmarks/stratified_v1_12sample_manifest.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/benchmarks/stratified_v1_12sample_manifest.json)

- `fixed_v104sample` 负责最小稳定回放。
- `stratified_v1_12sample` 负责当前默认的 `goal_type x aux_type` 分层回归。
- 但这仍不代表长期分层 benchmark 已经彻底补齐，例如不同 `aux_shape` 和更长尾失败模式还需要继续补。

## 4. 当前代码最需要避免的维护风险

### 4.1 单文件过大

当前主脚本体量已经较大；截至 2026-05-18，在把审计 helper 拆到 [audits.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/audits.py)、把几何文本 helper 拆到 [geometry_text.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/geometry_text.py)、把 prompt 组装拆到 [prompt_builders.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/prompt_builders.py)、把 writer 合同 helper 拆到 [writer_contracts.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/writer_contracts.py) 后，[generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py) 仍约 `2460` 行。后续若继续增长，会让以下几类修改更容易互相干扰：

- prompt 调整
- validator 调整
- artifacts schema 调整
- 审计指标调整

因此，后续重构时应优先把“纯 schema / artifacts 逻辑”和“模型推理逻辑”拆开，而不是继续把所有辅助函数堆回主文件。

推荐的下一轮拆分边界是：

1. `planner/plan normalization`
2. `validators`
3. `run orchestration`

如果以后继续做大改，但没有沿这些边界拆模块，那么“文档清楚”也不足以抵消主文件互相干扰的风险。

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
  - `ARTIFACT_SCHEMA.md`
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

5. 最小验证入口是否还能在当前环境运行
   - `python experiments/cot_sft_generation/maintenance_smoke_check.py`

## 6. 当前仍需补齐的说明

截至当前版本，下面几项已经补齐：

1. 固定 benchmark 的落仓目录和 manifest 说明
2. `run_config.json` / `sampled_inputs.jsonl` 的正式 schema
3. 语义审读 artifacts 的正式 schema
4. `summary.json` 字段表
5. `item_records.jsonl` / `item_audits.jsonl` 字段表
6. `semantic_review.py` 的刷新协议
7. 最小验证入口的标准库运行方式

当前仍建议继续补齐的是：

1. 按 `aux_shape` 和失败模式继续扩充的 benchmark 清单
2. 主脚本后续模块拆分后的落点文档
3. 如果将来引入自动 `critic`，其输出 schema 和与 `semantic_audits.jsonl` 的关系
4. 更细粒度的 validator / planner normalization 模块拆分计划

## 7. 当前支撑程度判断

按当前代码与文档状态，这套链路已经可以支撑“稳定交接的长期 Codex 迭代”，但还不能算“长期低成本维护”。

### 7.1 已经具备的条件

- 目标说明、当前实现、状态判断、时间线记录已经分层
- 运行产物不再只有脚本通过/失败，也开始显式落：
  - `surface_pass`
  - `semantic_audits.jsonl` 占位记录
  - run 级 `surface_pass_rate`
- artifacts/schema 层已经单独拆出，不必继续所有字段都塞回主脚本
- 固定 benchmark 已经开始版本化进仓库，而不是只留在 `/tmp`
- 按 `goal_type x aux_type` 分层的仓库内 benchmark 已经有第一版固定清单
- `semantic_review.py` 已经把“语义审读回填后如何刷新 summary”变成可执行协议
- schema 细节和最小验证入口已经写成文档，不再依赖会话记忆
- 已经补上一个不依赖外部 API 的 offline fixture pipeline test，可离线验证 planner -> writer -> artifacts 主链编排没有断

### 7.2 仍然限制维护成本的点

- 分层 benchmark 虽然已有第一版，但不同 `aux_shape`、失败模式和更长尾复杂题仍然覆盖不足
- `semantic_pass` 仍需人工/Codex 回填，当前还没有自动 `critic` 阶段
- prompt / validator / audit 逻辑仍高度集中在主脚本里，后续还需要继续拆分

### 7.3 当前推荐结论

- 如果目标是让不同 Codex 会话、不同人或不同机器按同一协议继续维护，这一版已经够用，而且已经具备稳定交接所需的最小闭环
- 如果目标是让后续维护成本继续下降，优先级最高的补充仍然是：
  - 分层 benchmark 扩充
  - 自动 `critic` 或更强语义审读协议
  - 更细的代码拆分
