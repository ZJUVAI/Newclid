# Dossier V1 Mainline

这份文档只服务一个目标：

- 以后续会话把 `dossier_v1` 当成唯一主线继续迭代。

如果只是想知道当前代码做什么，读 [CURRENT_DESIGN.md](/root/GenesisGeo-cot/experiments/cot_sft_generation/docs/current/CURRENT_DESIGN.md)。
如果是准备继续做新链路迭代，先读这份文档。

## 1. 当前主线状态

- 默认链路：`--generation-style dossier_v1`
- fallback：`--generation-style model_evidence_legacy`
- 当前仓库内可复用的人审证据：
  - [summary.json](/root/GenesisGeo-cot/experiments/cot_sft_generation/generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/summary.json)
  - [semantic_audits.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/semantic_audits.jsonl)
- 该证据的结论：
  - `surface_pass = 3/4`
  - `semantic_pass = 0/3`
  - `manual_critical_error = 3/3`
- 最新严格门控证据目前还只在 `/tmp`，需视为 temporary evidence：
  - `/tmp/cot_sft_quality_review_v1_full12_20260522_postsimbridge_artifacts_20260522_125400/summary.json`
  - 对应代码：`f7b54cc`
  - 结果：
    - `successful_items = 0/12`
    - `surface_pass_items = 0/12`
    - `surface_fail_items = 12/12`
    - `semantic_review_status = not_reviewed`

这说明：

- orchestration 已经跑通。
- schema / support / critic handoff 的机械摩擦已经明显下降。
- weak bridge false positive 又被继续压下去了一层。
- 但当前主问题已经从“格式摩擦”进一步收敛成“无法稳定构造 grounded positive bridge chain”，而不是单纯再多拦几条弱 closure 就能解决。

## 2. 下个会话不要再做什么

- 不要再把主要精力放在 legacy `model_evidence_legacy`。
- 不要再优先修低价值 surface 问题，例如轻微 wording 波动。
- 不要在没有明确失败模式的情况下同时大改 prompt、validator、writer 和长度预算。
- 不要把 `surface_pass` 当成质量提升证据。

legacy 现在只保留三种用途：

- fallback 回退
- 旧 artifact 对照
- 防回归测试

## 3. 当前真正的主问题

来自 [semantic_audits.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/semantic_audits.jsonl) 的共性问题：

1. `bridge_unsupported`
   - bridge relation 虽然写出来了，但 cited supports 推不出它。

2. `goal_finish_unclosed`
   - 最后几步形式上落到 goal，实际上没有可信闭环。

3. `route_drift`
   - planner/critic 会编出“看起来顺”的中间桥接，但它和图形、题面、aux 不真正对齐。

4. `not_visible_only`
   - writer 还会泄露内部 dossier 引用，例如 `aux_immediate_effects[0]`、`bridge_chain[2]`。

5. writer 长度不稳
   - 当前 stratified4 第 4 条失败直接原因仍然是 length budget。

## 3.1 2026-05-22 最新 live 跟进

- 本轮先做了两类 runtime 收紧：
  - `07888a2`：writer / final thinking 禁止泄露内部 dossier refs，例如 `visible_facts[1]`、`bridge_chain[2]`
  - dossier validator 新增 support-grounding 检查，直接拦截把 full similarity / ratio / angle closure 建在未铺垫 supports 上的 plan
- 随后跑了两轮 live benchmark：
  - `generated/dossier_v1_quality_review6_20260522.jsonl`
  - `generated/dossier_v1_quality_review6_20260522_artifacts_20260521_164105/summary.json`
  - 结果：`0/6 surface_pass`
  - 主要失败：
    - `5/6` 是 planner 被 `unsupported angle/ratio/similar segments` 打回
    - 剩余 `1/6` 是 writer length overflow
  - 样本级最常见错误：
    - `eqratio`: `bridge_chain[0]` 直接引入 `bh/ch`
    - `simtrir`: `goal_closure[0]` 直接引入 `bd/ce/cg/de/eg`
    - `simtri`: `goal_closure[0]` 直接引入 `ag/cg/fg`
    - `contri` / `contrir`: 中后段 bridge 或 closure 直接引入整组 fresh helper segments
  - prompt-only 跟进：
    - `generated/dossier_v1_quality_review4_prompttight_20260522.jsonl`
    - `generated/dossier_v1_quality_review4_prompttight_20260522_artifacts_20260521_165216/summary.json`
    - 结果：`0/4 surface_pass`
    - 结论：仅靠 planner prompt / retry feedback 强调 support-local claim，仍不足以让默认 `qwen` 稳定改写成小步 route
- 当前结论已经更明确：
  - 新 validator 没有“误杀”语义好样本；它主要是在把原本会伪装成 `surface_pass` 的坏 route 显式打回
  - 下一轮主线不应继续只加 prompt 约束，而应优先把 smaller-claim decomposition 更前置地脚本化，例如进入 planner skeleton / bridge staging

## 3.2 2026-05-23 当前 full-12 状态

- `f7b54cc` 把 similarity 的 local-correspondence gate 从“只拦带 aux 点的 similarity bridge”扩展成“所有 similarity bridge claim 都要过门”。
- 自动验证：
  - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
    - `Ran 115 tests ... OK`
  - `python experiments/cot_sft_generation/maintenance_smoke_check.py`
    - 全部检查通过
- 随后在当前代码上完成的 full-12 run：
  - `/tmp/cot_sft_quality_review_v1_full12_20260522_postsimbridge_artifacts_20260522_125400/summary.json`
  - 结果：
    - `successful_items = 0/12`
    - `surface_pass_items = 0/12`
    - `surface_fail_items = 12/12`
- 代表性失败族：
  - `unsupported angle/ratio/similar segments before supports ground them`
  - `missing symbolic directional coverage`
  - `missing local pairwise support`
  - `missing local correspondence support`
  - `scripted dossier skeleton invalid: bridge_chain must not be empty`
- 这轮结果的意义不是“质量达标”，而是：
  - fail-closed 已经足够强，弱 similarity / ratio / angle closure 更难混成 `surface_pass`
  - 但召回已经塌到 `0/12`，说明当前真正卡住的是正例构造能力，而不是 gate 还不够严
- 因此，下一步最值钱的工作不是继续加严 similarity / ratio gate，而是恢复 grounded positive：
  - `eqratio`：先让 scripted `bridge_chain` 真正非空，并给 ratio closure 提供 local pairwise support
  - `simtri` / `simtrir`：先补 locally grounded predecessor relation，再谈 full similarity closure
  - `eqangle`：优先修 planner hygiene，避免 fresh points / invalid supports 在 closure 才第一次出现

## 4. 下个会话最应该看的样本

优先看这三个 `surface_pass` 但 `semantic_fail` 的样本：

1. `eqratio`
   - run record: [item_records.jsonl](/root/GenesisGeo-cot/experiments/cot_sft_generation/generated/dossier_v1_stratified4_rerun4_20260520_artifacts_20260520_062623/item_records.jsonl)
   - 典型问题：伪造 helper-triangle similarity，再把 ratio chain 建在这个错误桥上。

2. `eqangle`
   - 同上
   - 典型问题：writer 泄露内部 ids，且 angle chain 有明显 tautology。

3. `simtrir`
   - 同上
   - 典型问题：helper frame 到旧图主链的对应关系是硬编的。

建议下个会话先逐条拆：

- 哪个 `bridge_chain[i]` 真正不成立
- 当前 validator 为什么没拦住
- 是 planner 质量问题、critic 质量问题，还是 writer 落句问题

## 5. 推荐迭代顺序

只按这个顺序推进：

1. 先恢复一个 grounded positive family，而不是继续找新的 gate 往下压
   - 推荐优先级：
   - `eqratio`：`bridge_chain must not be empty` 与 `missing local pairwise support`
   - `simtri` / `simtrir`：`missing local correspondence support`
   - `eqangle`：fresh points / invalid supports / closure staging

2. 先改正例构造最相关的一层
   - 优先：`scripted dossier skeleton` / planner normalization / support pruning
   - 其次：critic 或 writer
   - 当前不推荐把“再加一层 stricter similarity/ratio gate”当成第一步

- 2026-05-22 的补充判断：
  - `not_visible_only` 已经通过 runtime boundary checks 明显收紧
  - 但 `bridge_unsupported` 仍然是绝对主问题，而且 prompt-only tightening 没有显著改善 live 结果
  - 因此下一轮更推荐：
    - planner skeleton / scripted bridge decomposition
    - 再考虑 critic 或 writer

- 2026-05-23 的补充判断：
  - 最新 full-12 已经是 `0/12 surface_pass`
  - 所以下一轮的成功标准不再是“再少放过几个坏样本”，而是“恢复出少量真正站得住的正例”
  - 如果只看到 gate 更严、`surface_pass` 继续维持 `0`，那不算向最终目标前进

3. 跑最小回归
   - `python -m unittest discover -s tests -p 'test_cot_sft_*.py'`
   - `python experiments/cot_sft_generation/maintenance_smoke_check.py`

4. 先跑定向小回放，再回到 full benchmark
   - 先挑 `2-3` 个代表性失败样本：
     - 一个 `bridge_chain must not be empty`
     - 一个 `missing local pairwise support`
     - 一个 `missing local correspondence support`
   - 只有恢复出至少 `1-2` 个 grounded 正例后，再回到 `quality_review_v1` 的 `quick6` 或 full-12

```bash
python experiments/cot_sft_generation/generate_cot_sft.py \
  -i experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl \
  -o experiments/cot_sft_generation/generated/dossier_v1_quality_review6_next.jsonl \
  -n 6 \
  --sequential \
  -v \
  --generation-style dossier_v1 \
  -w 1 \
  -r 3
```

5. 只审 `surface_pass` 样本

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --print-pending \
  --print-pending-payloads \
  --surface-pass-only
```

6. 回填 `semantic_audits.jsonl` 后刷新 summary

```bash
python experiments/cot_sft_generation/semantic_review.py \
  --run-dir /path/to/run_artifacts \
  --write-summary
```

## 6. 文件优先级

下个会话大概率只需要优先看这些文件：

- [generate_cot_sft.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/generate_cot_sft.py)
- [prompt_builders.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/prompt_builders.py)
- [geometry_text.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/geometry_text.py)
- [audits.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/audits.py)
- [semantic_review.py](/root/GenesisGeo-cot/experiments/cot_sft_generation/semantic_review.py)
- [tests/test_cot_sft_fixture_pipeline.py](/root/GenesisGeo-cot/tests/test_cot_sft_fixture_pipeline.py)
- [tests/test_cot_sft_prompt_builders.py](/root/GenesisGeo-cot/tests/test_cot_sft_prompt_builders.py)
- [tests/test_cot_sft_audits.py](/root/GenesisGeo-cot/tests/test_cot_sft_audits.py)
- [tests/test_cot_sft_geometry_text.py](/root/GenesisGeo-cot/tests/test_cot_sft_geometry_text.py)

## 7. 下个会话的合格完成标准

不要用“又过了 4/4 surface”当完成标准。

更合格的短期目标是：

- 至少恢复一类 grounded positive bridge chain
- 在新 run 里拿到更少的 `bridge_unsupported` / `goal_finish_unclosed`
- 或者拿到第一批真正可记作 `semantic_pass` 的样本

如果下一轮仍然是 `surface_pass` 上升、`semantic_pass` 仍然为 `0`，那说明迭代还在表层打转。
