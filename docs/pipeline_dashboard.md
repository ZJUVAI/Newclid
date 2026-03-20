# Discovery Pipeline 数据看板

本文档记录 Discovery Pipeline 每一步的数据过滤逻辑、对应代码位置、伪代码说明和运行结果。
每次运行 pipeline 时使用 `--save-intermediates` 参数，中间结果保存在实验目录的 `intermediates/` 下。

---

## Pipeline 总览

```
JSONL 合成数据
  │
  ├─ Stage 1: FilterAndPruneEngine (filter_and_prune_engine.py)
  │   ├─ Step 1. 输入过滤 (aux + skip_predicates)  ─→ intermediates/step1_input_filter.json
  │   ├─ Step 2. 图修剪                             ─→ intermediates/step2_graph_prune.json
  │   ├─ Step 3. 命题提取                           ─→ intermediates/step3_propositions.json
  │   ├─ Step 4. 规范化 (missing_points + 对称性)    ─→ intermediates/step4_*.json
  │   ├─ Step 5. 去重 (SHA256 hash)                 ─→ intermediates/step5_dedup.json
  │   └─ Step 6. 规则落盘 (rule_skip_predicates)    ─→ intermediates/step6_rules_stats.json
  │                                                     + *_pruned_rules.txt
  │
  └─ Stage 2: RuleReducer (rule_reducer.py)
      ├─ Phase 1: 小组规约 (reduce_by_seed)
      │   ├─ 按 seed 分组
      │   └─ 组内: max_premises → 泛化度排序 → 贪心淘汰
      └─ Phase 2: 全局规约
          ├─ Pre-filter: max_premises 过滤
          ├─ Step 1: 泛化度评分
          ├─ Step 2: 泛化度排序
          └─ Step 3: 贪心淘汰 (subsumption)             ─→ extracted_rules.txt
```

---

## Stage 1: FilterAndPruneEngine

入口: `scripts/discovery_pipeline.py` → `run_stage1_extraction()`
核心: `src/newclid/proof_scout/core/filter_and_prune_engine.py`

### Step 1: 输入过滤

**目的**: 合并两个过滤条件 — (1) 只保留含辅助点的题目；(2) 跳过包含 `skip_predicates` 中谓词的题目

**参数**:
- `skip_predicates`: 默认 `{eqpoint, constline}`

**伪代码**:
```
for record in all_records:
    if record.aux_points is empty:
        dropped (no aux)
    elif record contains any skip_predicate:
        dropped (skip predicate)
    else:
        kept
```

**中间结果**: `intermediates/step1_input_filter.json`
- `total`, `kept`, `dropped_no_aux`, `dropped_skip_predicates`
- `kept_records`: 每条保留记录的 problem_id, aux_points
- `dropped_records`: 被丢弃记录

---

### Step 2: 图修剪

**目的**: 对每个题目构建证明图（SingleProofGraph），用 GraphPruner 修剪冗余节点，只保留从前提到结论的最小证明路径

**代码**: `_worker_prune()`

**伪代码**:
```
for record in kept_records:  # 并行
    proof_graph = SingleProofGraph.build_from_result_record(record)
    pruned = GraphPruner().prune_proof_graph(proof_graph)
    if pruned is not None:
        pruned_map[record.pid] = pruned
```

**中间结果**: `intermediates/step2_graph_prune.json`
- `total_input`, `pruned_success`, `pruned_failed`
- 每条记录的 nodes/edges 统计

---

### Step 3: 命题提取

**目的**: 从修剪后的证明图中提取命题（premises → conclusion 形式）

**代码**: `_extract_propositions()`

**伪代码**:
```
for pid, pruned_graph in pruned_map.items():
    propositions = extract_from_graph(pruned_graph)
    for prop in propositions:
        all_propositions.append({
            pid, premises, conclusion, point_coords, ...
        })
```

**中间结果**: `intermediates/step3_propositions.json`
- `total_propositions`, `by_conclusion_predicate` 分布

---

### Step 4: 规范化

**目的**: (1) 检查 missing_points；(2) 对谓词参数应用对称性规范化；(3) 生成 signature

**对称性规范化**: 19 个几何谓词各有对称性规则（如 `cong(a,b,c,d)` → 排序使 `(a,b) ≤ (c,d)`）

**伪代码**:
```
for rule in raw_rules:
    if has_missing_points(rule):
        skipped (missing points)
    else:
        normalized = canonicalize_predicates(rule)
        signature = compute_signature(normalized)
        normalized_rules.append((normalized, signature))
```

**中间结果**:
- `intermediates/step4_normalized_rules.json` — 规范化后的规则列表
- `intermediates/step4_signature_distribution.json` — signature 分布
- `intermediates/step4_predicate_normalization_samples.json` — 规范化样例

---

### Step 5: 去重

**目的**: 按 signature 排序，使用 SHA256 hash 去重

**伪代码**:
```
rules_sorted = sort_by_signature(normalized_rules)
seen_hashes = set()
for rule in rules_sorted:
    h = sha256(rule.text)
    if h not in seen_hashes:
        seen_hashes.add(h)
        deduped.append(rule)
```

**中间结果**: `intermediates/step5_dedup.json`
- `before_dedup`, `after_dedup`, `duplicates_removed`
- 去重组统计

---

### Step 6: 规则落盘

**目的**: 过滤掉包含 `rule_skip_predicates` 中谓词的规则，写入最终规则文件

**参数**:
- `rule_skip_predicates`: 默认 `{aconst, rconst}`

**伪代码**:
```
for rule in deduped_rules:
    if rule contains any rule_skip_predicate:
        skipped
    else:
        write to output file
```

**输出**:
- `*_pruned_rules.txt` — 最终规则文件（rule_id + rule_text 交替行）
- `intermediates/step6_rules_stats.json` — 规则统计 + 每条规则的元数据

---

## Stage 2: RuleReducer

入口: `scripts/discovery_pipeline.py` → `run_stage2_reduction()`
核心: `src/newclid/proof_scout/reduction/rule_reducer.py`

### Phase 1: 小组规约（reduce_by_seed）

**目的**: 按 seed 分组，先在组内规约。同一 seed 生成的规则高度相似，组内规约效率极高。

**流程**:
1. 按 `seed` 字段将规则分组
2. 对每组执行完整的 `reduce()` 流程（max_premises 过滤 → 泛化度排序 → 贪心淘汰）
3. 收集各组的 basis_rules 作为全局规约的输入
4. 无 seed 的规则直接进入全局规约

**可选**: 使用 `--no-group-reduction` 跳过此阶段

### Phase 2: 全局规约

### Pre-filter: max_premises

**目的**: 过滤前提数超过阈值的规则

### Step 1-2: 泛化度评分 + 排序

**目的**: 计算每条规则的泛化度分数 `(-n_premises, n_conclusions)`，按泛化度排序（最通用的在前）

### Step 3: 贪心淘汰

**目的**: 对排序后的规则，逐条测试是否被更通用的规则包含（subsumption test）

**伪代码**:
```
active = [True] * len(sorted_rules)
for i, rule_i in enumerate(sorted_rules):
    if not active[i]: continue
    for j in range(len(sorted_rules)):
        if i == j or not active[j]: continue
        if subsumption_test(rule_i, rule_j):
            active[j] = False  # rule_j 被 rule_i 包含
basis = [r for i, r in enumerate(sorted_rules) if active[i]]
```

**输出**:
- `extracted_rules.txt` — 最终基底规则集
- `eliminated_rules.json` — 被淘汰的规则及原因
- `reduction_stats.json` — 统计信息（含 group_phase 和 global_phase 详情）

---

## 数据生成标准参数（铁律）

**脚本**: `src/newclid/generation/generate.py`

必须使用以下标准参数，除非用户明确指定其他值：

| 参数 | 标准值 | 说明 |
|------|--------|------|
| `--n_clauses` | `15` | 每题构造子句数 |
| `--aux_only` | `1` | 只保留含辅助点的题目（pipeline 必须） |
| `--n_threads` | `30` | 并行 worker 数（生产环境） |
| `--n_samples` | 由用户指定 | 目标样本数 |
| `--dir` | 由用户指定 | 输出目录 |

**标准生成命令**:
```bash
source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery
python src/newclid/generation/generate.py \
    --n_clauses 15 --aux_only 1 \
    --n_threads 30 --n_samples <N> \
    --dir outputs/datasets/<dataset_name> \
    --log_level info --timeout 3600
```

验证/测试场景可减少 `--n_threads`（如 10），但 `--aux_only 1` 和 `--n_clauses 15` 不得省略。

---

## CLI 使用

### 完整 pipeline（提取 + 规约）
```bash
python scripts/discovery_pipeline.py \
    -i datasets/synthetic_10k.jsonl \
    -o outputs/experiments/YYYYMMDD_XX_experiment_name \
    --save-intermediates
```

### 仅提取
```bash
python scripts/discovery_pipeline.py \
    -i datasets/synthetic_10k.jsonl \
    -o outputs/experiments/YYYYMMDD_XX_experiment_name \
    --skip-reduction --save-intermediates
```

### 仅规约（从已有提取结果）
```bash
python scripts/discovery_pipeline.py \
    -o outputs/experiments/YYYYMMDD_XX_experiment_name \
    --skip-extraction \
    --rules <path/to/pruned_rules.txt> \
    --source-data <path/to/step6_rules_stats.json>
```

---

## 相关文件

- Pipeline 入口: `scripts/discovery_pipeline.py`
- 核心引擎: `src/newclid/proof_scout/core/filter_and_prune_engine.py`
- 规则规约: `src/newclid/proof_scout/reduction/rule_reducer.py`
- 数据格式参考: `docs/data_formats.md`

---

## Evaluation Pipeline

评估提取规则对 benchmark 求解性能的影响。

### 脚本: `scripts/evaluate_rules.py`

**两个子命令**:
1. `baseline` — 预计算 baseline（默认规则）并缓存结果
2. `evaluate` — 对比 baseline vs 增强规则（默认规则 + 提取规则）

**三个 benchmark**:
- `jgex_ag_231` — JGEX AG 231 problems (202/231 solved by baseline)
- `imo_95` — IMO 95 problems (1/95 solved by baseline)
- `hageo_409` — HAGeo 409 problems (100/405 solved by baseline, 4 problems skipped due to engine incompatibility)

### 使用方法

#### 1. 计算 baseline（首次运行或更新 baseline）

```bash
# 计算所有 benchmark 的 baseline
python scripts/evaluate_rules.py baseline \
    --output outputs/eval_baselines/ \
    --workers 30 \
    --timeout 3600

# 计算单个 benchmark 的 baseline
python scripts/evaluate_rules.py baseline \
    --output outputs/eval_baselines/ \
    --benchmarks hageo_409 \
    --workers 30 \
    --timeout 3600

# 跳过已知失败的题目（HAGeo 409 专用）
python scripts/evaluate_rules.py baseline \
    --output outputs/eval_baselines/ \
    --benchmarks hageo_409 \
    --workers 30 \
    --timeout 3600 \
    --skip outputs/experiments/20260311_01_hageo409_oom_diagnosis/failed_problems.txt
```

**输出**: `outputs/eval_baselines/{benchmark_name}_baseline.json`

#### 2. 评估提取规则

```bash
# 评估提取规则对所有 benchmark 的影响
python scripts/evaluate_rules.py evaluate \
    --rules outputs/experiments/20260310_01_10k_normalized_extraction_reduction/extracted_rules.txt \
    --baseline-cache outputs/eval_baselines/ \
    --output outputs/eval_results/20260312_01_extracted_rules_eval \
    --workers 30 \
    --timeout 3600

# 评估单个 benchmark
python scripts/evaluate_rules.py evaluate \
    --rules outputs/experiments/20260310_01_10k_normalized_extraction_reduction/extracted_rules.txt \
    --baseline-cache outputs/eval_baselines/ \
    --output outputs/eval_results/20260312_01_extracted_rules_eval \
    --benchmarks jgex_ag_231 \
    --workers 30 \
    --timeout 3600

# 跳过已知失败的题目（HAGeo 409 专用）
python scripts/evaluate_rules.py evaluate \
    --rules outputs/experiments/20260310_01_10k_normalized_extraction_reduction/extracted_rules.txt \
    --baseline-cache outputs/eval_baselines/ \
    --output outputs/eval_results/20260312_01_extracted_rules_eval \
    --benchmarks hageo_409 \
    --workers 30 \
    --timeout 3600 \
    --skip outputs/experiments/20260311_01_hageo409_oom_diagnosis/failed_problems.txt
```

**输出**:
- `{benchmark_name}_baseline.json` — baseline 结果（如果 baseline-cache 中不存在）
- `{benchmark_name}_augmented.json` — 增强规则结果
- `{benchmark_name}_comparison.json` — 对比报告（new_solved, regressed, 详细列表）
- 终端输出对比表

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workers` | 并行 worker 数量 | 30 |
| `--timeout` | 单题超时时间（秒） | 3600 |
| `--skip` | 跳过列表文件（每行一个 problem ID） | None |
| `--benchmarks` | 逗号分隔的 benchmark 名称 | 全部 |
| `--baseline-cache` | baseline 缓存目录（evaluate 专用） | None |

### 已知问题

**HAGeo 409 的 4 个失败题目**（引擎不兼容，需跳过）:
- `2011CTSTp10` — `PointTooCloseError()`
- `2019KoMaLA736` — `AttributeError: 'Point' has no attribute 'num'`
- `ShuZhiMiGeo209` — `PointTooCloseError()`
- `XinXingV35p1` — `PointTooCloseError()`

跳过列表文件: `outputs/experiments/20260311_01_hageo409_oom_diagnosis/failed_problems.txt`

### 当前 Baseline 结果

| Benchmark | Total | Solved | Solve Rate |
|-----------|-------|--------|------------|
| jgex_ag_231 | 231 | 202 | 87.4% |
| imo_95 | 95 | 1 | 1.05% |
| hageo_409 | 405* | 100 | 24.69% |

*注: HAGeo 409 原有 409 题，跳过 4 题后剩余 405 题

