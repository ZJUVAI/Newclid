# Dossier V1 Mainline

这份文档只服务一个目标：

- 以后续会话把 `dossier_v1` 当成唯一主线继续迭代。

如果只是想知道当前代码做什么，读 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)。
如果是准备继续做新链路迭代，先读这份文档。

## 1. 当前主线状态（2026-05-26 更新）

- 默认链路：`--generation-style dossier_v1`
- 主路径：`generate_proof_dag_thinking` — 直接从 proof DAG 生成 bridge_chain，零 API 调用
- fallback：`generate_dossier_thinking`（旧启发式路径，仅在 proof 不可解析时触发）
- 当前 benchmark 证据：
  - **12-item full benchmark: `surface_pass = 12/12`**
  - forbidden pattern violations: 0
  - 181 tests pass（含新增 32 个 proof_dag / rule_catalog 测试）
  - 单条生成耗时 < 1s

### 架构转变

旧路线（Phase 1-3，已废弃为 fallback）：
- 用 segment / keyword overlap 启发式重新验证 proof 每一步
- 启发式严格弱于 DDAR rule application → 拦掉合法步骤 → 0/12 surface_pass
- Phase 3 的几十个 commits 都在打补丁让启发式逼近 rule，但永远到不了 rule 的精度

新路线（Proof DAG 直接驱动）：
- 信任 proof DAG 是 ground truth，脚本只做翻译/压缩/边界处理
- `core/proof_dag.py`：解析 `<proof>` 块成结构化 DAG，从 goal 反向 BFS 选 milestone
- `core/rule_catalog.py`：把 rule ID 翻译成真实定理名（inscribed angle theorem、AA similarity、Thales' theorem 等）
- `build_proof_dag_skeleton`：从 milestone 直接生成 bridge_chain / goal_closure
- `build_proof_dag_writer_body`：scripted writer，引用真实定理名

## 2. 下个会话不要再做什么

- 不要再给旧 7 个 lacks_* gate 打补丁 — 它们已经被绕过
- 不要再用 segment overlap 启发式验证 proof 步骤 — proof DAG 已经验证过了
- 不要把 `surface_pass` 当成唯一质量证据 — 需要 semantic_pass 确认几何正确性
- 不要在没有 semantic review 的情况下宣布”质量达标”

## 3. 当前真正的主问题

`surface_pass = 12/12` 已经解决了”正例构造能力”问题。当前主问题转移到：

### 3.1 Semantic 正确性（未验证）

生成的 thinking 文本引用了真实定理名和 proof DAG 的结论，但：
- 定理应用的前提条件是否在叙述中被充分铺垫？
- “by algebraic combination” 的 AR 步骤是否对读者来说跳跃过大？
- 自然语言翻译是否准确反映了 predicate 的几何含义？

### 3.2 叙述自然度

当前 scripted body 的句式比较机械：
- “Then, by X, Y. Next, by X, Y. Then, by X, Y. Finally, by X, Y.”
- 起手段（goal_obstacle + construction）是模板化的
- 没有”为什么选这个 aux”的动机叙述

### 3.3 模型 Writer 未启用

当前路径完全 scripted，不调用模型。如果需要更自然的叙述风格：
- 可以把 DAG skeleton 作为 dossier 传给 model writer
- writer prompt 已经更新支持引用定理名
- `build_writer_visible_dossier` 已经正确剥离私有字段

## 4. 推荐迭代顺序

### 短期（下 1-2 个会话）

1. **做 semantic review** — 人工审读 12 条生成样本，标注几何正确性
   ```bash
   python experiments/cot_sft_generation/semantic_review.py \
     --run-dir <new_artifact_dir> \
     --print-pending --print-pending-payloads --surface-pass-only
   ```

2. **改善 AR 步骤叙述** — 当前 AR 步骤只说 “by algebraic combination”，可以：
   - 识别常见 AR 模式（角减法、比例传递、等式代入）
   - 给出更具体的描述（”subtracting the two angle equalities”）

3. **改善起手段** — 当前 `build_canonical_goal_bottleneck` 是模板化的，可以：
   - 从 proof DAG 的第一步反推”为什么需要这个 aux”
   - 让模型 planner 只负责写 1-2 句 aux motivation

### 中期

4. **接回模型 writer** — 把 DAG skeleton 作为 dossier 传给 writer，让它用更自然的语言重述
5. **扩大 benchmark** — 从 12 条扩展到 50-100 条，验证 proof DAG 路径的泛化性
6. **清理旧代码** — 删除 7 个 lacks_* gate、~10 个匹配 helper、~8 个 tail/checkpoint helper

## 5. 文件优先级

下个会话大概率只需要看这些文件：

- [core/proof_dag.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/proof_dag.py) — DAG 解析和 milestone 选取
- [core/rule_catalog.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/rule_catalog.py) — 规则名翻译
- [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py) — `build_proof_dag_skeleton`、`build_proof_dag_writer_body`、`generate_proof_dag_thinking`
- [core/prompt_builders.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/core/prompt_builders.py) — writer prompt（如果要接回模型）
- [semantic_review.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/semantic_review.py) — 语义审读工具
- [tests/test_cot_sft_proof_dag.py](/root/GenesisGeo-cot/tests/test_cot_sft_proof_dag.py)
- [tests/test_cot_sft_rule_catalog.py](/root/GenesisGeo-cot/tests/test_cot_sft_rule_catalog.py)

## 6. 下个会话的合格完成标准

- 至少完成 12 条样本的 semantic review，标注 `semantic_pass` / `semantic_fail`
- 如果 `semantic_pass >= 6/12`：proof DAG 路线确认可行，进入扩量阶段
- 如果 `semantic_pass < 3/12`：需要分析失败模式，可能是 AR 步骤叙述不足或定理应用前提缺失
- 不论结果如何，都要回填 `semantic_audits.jsonl` 并刷新 summary

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --write-summary
```

## 7. 历史记录（已过时，仅供参考）

以下是旧启发式路径的历史记录，保留供对照：

- Phase 1-2（v83-v92）：两阶段主链成型，小样本 4/4
- Phase 3（v92 之后）：加严 gate，full-12 降到 0/12
- 根因：启发式 verification 严格弱于 DDAR rule application
- 解决方案：直接信任 proof DAG，不再重新发明 reasoning verification

