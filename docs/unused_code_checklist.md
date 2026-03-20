# Unused Code Checklist

本文档列出了 GeoDiscovery 代码库中潜在的冗余代码，分为三个层级。用户需要review并确认删除范围。

**生成日期**: 2026-03-12
**分析范围**: `src/newclid/proof_scout/` 和 `scripts/`

---

## 分类说明

- **Tier 1 (确认未使用)**: 无任何 import 引用，且不在主 pipeline 中，可安全删除
- **Tier 2 (历史遗留)**: 曾经使用但已被新实现替代，建议归档
- **Tier 3 (实验性代码)**: 一次性实验脚本，需用户确认是否保留

---

## Tier 1: 确认未使用（建议删除）

### 1.1 ML模块 (`src/newclid/proof_scout/ml/`)

**状态**: 仅被 `scripts/scout_main.py` 使用，不在主 discovery pipeline 中

| 文件 | 行数 | 用途 | 当前引用 |
|------|------|------|----------|
| `scout_pipeline.py` | 397 | ML pipeline 管理器 | `scout_main.py` |
| `train_with_val.py` | 254 | 训练循环（带验证） | `scout_pipeline.py` |
| `data_processor.py` | 196 | 数据预处理 & 模型定义 | `scout_pipeline.py`, `eval.py` |
| `problems_filter.py` | 200 | 问题过滤（ML训练用） | `scout_pipeline.py` |
| `model_utils.py` | 154 | 模型工具 & 推理 | `scout_pipeline.py` |
| `scout_config.py` | 40 | 配置常量 | `scout_pipeline.py` |
| `eval.py` | 52 | 模型评估工具 | `scout_pipeline.py` |

**总计**: ~1,293行代码

**删除影响**:
- ✓ 不影响主 discovery pipeline（`discovery_pipeline.py`）
- ✓ 不影响规则提取（`FilterAndPruneEngine`）
- ✓ 不影响规则规约（`RuleReducer`）
- ✓ 不影响评估（`evaluate_rules.py`）
- ✗ 会导致 `scripts/scout_main.py` 无法运行（但该脚本本身也是实验性的）

**建议操作**:
- [x] 移动到 `archive/ml_experiments/proof_scout_ml/`（用户已确认）
- [x] 同时移动 `scripts/scout_main.py` 到 `archive/ml_experiments/`
- [ ] 更新 `src/newclid/proof_scout/ml/__init__.py` 删除相关导入

---

### 1.2 替代算法 (`src/newclid/proof_scout/core/`)

#### `subgraph_extractor.py` (164行)

**用途**: 旧版图修剪算法（exclusive subgraph extraction）

**当前状态**:
- 仅在 `__init__.py` 中作为 `SubgraphExtractor` 导出
- 实际引用: 0次（已被 `GraphPruner` 替代）
- 主 pipeline 使用 `GraphPruner` 进行图修剪

**删除影响**:
- ✓ 不影响主 pipeline
- ✗ 如果有外部代码使用 `from newclid.proof_scout.core import SubgraphExtractor` 会报错

**建议操作**:
- [ ] 删除 `__init__.py` 中的 `SubgraphExtractor` 导出
- [ ] 移动文件到 `archive/alternative_algorithms/`

---

### 1.3 实验性脚本 (`scripts/`)

以下脚本为一次性实验或已被新实现替代，建议归档：

| 文件 | 行数 | 用途 | 状态 |
|------|------|------|------|
| `backtrack_elimination.py` | ~150 | 实验性规约算法（回溯消除） | 实验性，未用于主pipeline |
| `reduce_rules_incremental.py` | ~200 | 增量规约实验 | 实验性，未用于主pipeline |
| `debug_r0012_subsumption.py` | ~100 | 一次性调试脚本（R0012 subsumption） | 调试完成，可归档 |
| `filter_and_prune.py` | ~150 | 旧版提取入口 | 已被 `discovery_pipeline.py` 替代 |
| `compare_step1e.py` | ~120 | 一次性对比脚本（Step 1e） | 对比完成，可归档 |
| `compare_step2.py` | ~130 | 一次性对比脚本（Step 2） | 对比完成，可归档 |
| `extract_aux_graph.py` | ~180 | 辅助图提取实验 | 实验性 |
| `plot_premise_distribution.py` | ~100 | 一次性分析脚本 | 分析完成，可归档 |
| `run_10k_extraction.py` | ~120 | 一次性运行脚本（10k数据） | 已被 `discovery_pipeline.py` 替代 |
| `run_risos_subset_extraction.py` | ~130 | RISOS子集提取 | 特定实验，可归档 |
| `run_risos_subset_reduction.py` | ~120 | RISOS子集规约 | 特定实验，可归档 |

**总计**: ~1,500行代码

**建议操作**:
- [ ] **用户需要review**: 确认哪些脚本可以归档
- [ ] 移动到 `scripts/archive/experimental/`（按类别分子目录）

---

## Tier 2: 历史遗留（建议归档）

### 2.1 旧版Benchmark脚本

| 文件 | 行数 | 用途 | 状态 |
|------|------|------|------|
| `benchmark_reduction.py` | ~200 | 旧版规约性能benchmark | 已被新版 `discovery_pipeline.py` 集成 |
| `benchmark_yuclid.py` | ~180 | Yuclid solver benchmark | Yuclid已废弃 |
| `run_batch.py` | ~150 | 旧版批处理 | 已被 `solver_utils.py` 替代 |
| `run_batch_batch.py` | ~120 | 旧版批批处理 | 已被 `solver_utils.py` 替代 |

**总计**: ~650行代码

**建议操作**:
- [ ] 移动到 `scripts/archive/legacy_benchmarks/`

---

### 2.2 数据转换脚本

| 文件 | 行数 | 用途 | 状态 |
|------|------|------|------|
| `convert_tong_to_jgex.py` | ~150 | 一次性数据格式转换 | 转换完成，可归档 |
| `parse_llm_input.py` | ~100 | LLM输入解析 | 功能已集成到引擎 |

**总计**: ~250行代码

**建议操作**:
- [ ] 移动到 `scripts/archive/data_conversion/`

---

## Tier 3: 实验性代码（需用户确认）

### 3.1 旧版可视化

| 文件 | 行数 | 用途 | 状态 |
|------|------|------|------|
| `scripts/figures/fig_rule_extraction_old.py` | ~300 | 旧版规则提取可视化 | 已被 `fig_rule_extraction.py` 替代 |

**建议操作**:
- [ ] **用户确认**: 是否有历史实验依赖此脚本？
- [ ] 如无依赖，移动到 `scripts/archive/visualization/`

---

### 3.2 工具脚本（可能复用）

以下脚本可能在未来实验中复用，建议保留或移动到 `scripts/utils/`：

| 文件 | 行数 | 用途 | 建议 |
|------|------|------|------|
| `extract_success_problem_ids.py` | ~80 | 提取成功题目ID | 保留在 `scripts/utils/` |
| `translate_rule_to_problem.py` | ~120 | 规则转问题格式 | 保留在 `scripts/utils/` |
| `translate_rules_to_problem.py` | ~150 | 批量规则转问题 | 保留在 `scripts/utils/` |
| `aux_checker.py` | ~100 | 验证辅助点提取 | 保留在 `scripts/utils/` |
| `validate_benchmark_semantics.py` | ~180 | 验证benchmark语义 | 保留在 `scripts/utils/` |
| `rebuild_benchmark.py` | ~150 | 重建benchmark数据集 | 保留在 `scripts/utils/` |

**建议操作**:
- [ ] **用户确认**: 这些工具脚本是否需要保留？
- [ ] 如保留，创建 `scripts/utils/` 目录并移动
- [ ] 如不需要，移动到 `scripts/archive/utilities/`

---

## 删除计划

### 阶段1: 安全删除（Tier 1 - 已确认）

**ML模块**:
```bash
# 创建归档目录
mkdir -p archive/ml_experiments/proof_scout_ml

# 移动ML模块
git mv src/newclid/proof_scout/ml/*.py archive/ml_experiments/proof_scout_ml/
git mv scripts/scout_main.py archive/ml_experiments/

# 更新__init__.py（删除ML相关导入）
# 编辑 src/newclid/proof_scout/ml/__init__.py
```

**预计减少**: ~1,300行代码

---

### 阶段2: 归档历史代码（Tier 2）

```bash
# 创建归档目录
mkdir -p scripts/archive/{legacy_benchmarks,data_conversion}

# 移动旧版benchmark
git mv scripts/benchmark_reduction.py scripts/archive/legacy_benchmarks/
git mv scripts/benchmark_yuclid.py scripts/archive/legacy_benchmarks/
git mv scripts/run_batch.py scripts/archive/legacy_benchmarks/
git mv scripts/run_batch_batch.py scripts/archive/legacy_benchmarks/

# 移动数据转换脚本
git mv scripts/convert_tong_to_jgex.py scripts/archive/data_conversion/
git mv scripts/parse_llm_input.py scripts/archive/data_conversion/
```

**预计减少**: ~900行代码

---

### 阶段3: 用户确认（Tier 3）

**等待用户确认**:
1. 实验性脚本（Tier 1.3）: 11个脚本，~1,500行
2. 旧版可视化（Tier 3.1）: 1个脚本，~300行
3. 工具脚本（Tier 3.2）: 6个脚本，~780行

**用户需要决定**:
- [ ] 哪些实验性脚本可以归档？
- [ ] 旧版可视化是否有历史依赖？
- [ ] 工具脚本是否需要保留？

---

## 验证清单

删除前必须验证（在小数据集上测试）:

- [ ] 运行完整 pipeline 测试
  ```bash
  python scripts/discovery_pipeline.py \
      -i datasets/test_1k.jsonl \
      -o outputs/test_cleanup \
      --save-intermediates
  ```

- [ ] 运行评估测试
  ```bash
  python scripts/evaluate_rules.py baseline \
      --output outputs/test_cleanup/eval \
      --benchmarks jgex_ag_231 \
      --workers 10
  ```

- [ ] 运行可视化测试
  ```bash
  python scripts/figures/fig_pipeline_flow.py
  python scripts/figures/fig_rule_extraction.py
  ```

- [ ] 检查所有 import 语句
  ```bash
  grep -r "from newclid.proof_scout.ml" src/ scripts/
  grep -r "SubgraphExtractor" src/ scripts/
  ```

- [ ] 运行单元测试（如有）
  ```bash
  pytest tests/ -v
  ```

---

## 总结

| 层级 | 文件数 | 代码行数 | 状态 |
|------|--------|----------|------|
| Tier 1 (确认未使用) | ~20 | ~3,000 | ML模块已确认删除，其他待用户review |
| Tier 2 (历史遗留) | ~6 | ~900 | 建议归档 |
| Tier 3 (实验性代码) | ~18 | ~2,600 | 需用户确认 |
| **总计** | **~44** | **~6,500** | |

**预期收益**:
- 代码库更清晰，减少维护负担
- `scripts/` 目录更整洁，易于导航
- 保留git历史，未来可恢复

**下一步**:
1. ✓ 用户已确认ML模块归档
2. ⏸ 用户review Tier 1.3 实验性脚本清单
3. ⏸ 用户确认Tier 3工具脚本处理方式
4. 执行归档操作
5. 运行验证测试
