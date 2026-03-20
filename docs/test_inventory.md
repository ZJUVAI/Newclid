# 测试清单 (Test Inventory)

> 更新日期: 2026-03-10
> 整理完成，以下为当前 `tests/` 目录最终状态

---

## `tests/` 目录 — 当前测试文件

| # | 文件 | 测试内容 | 测试数 | 框架 | 来源 |
|---|------|---------|--------|------|------|
| 1 | `tests/test_problem.py` | Problem 解析构建（orthocenter/goal_free/multiple_build） | 3 | pytest | 原有 |
| 2 | `tests/test_individual_rules.py` | 52 条规则逐条验证（r00-r50 + Pythagorean），参数化 | 52 | pytest | 原有 |
| 3 | `tests/test_rule_necessity.py` | 规则必要性检查（需修复路径后可用） | 自定义 | 脚本 | 原有 |
| 4 | `tests/test_xconst_predicates.py` | 常量谓词 aconst/lconst/rconst/acompute/lcompute/rcompute | 15+ | pytest | 原有 |
| 5 | `tests/test_rule_extraction_figure.py` | 规则提取可视化逻辑（conclusion resolve/figure data） | 4 | pytest | 原有 |
| 6 | `tests/deductive_agents/test_breadth_first_search.py` | DDAR BFS（incenter/orthocenter exhaust/orthocenter aux） | 3 | pytest | 原有 |
| 7 | `tests/deductive_agents/test_human_agent.py` | 交互式 Human Agent（graphics/add_construction） | 2 | pytest | 原有 |
| 8 | `tests/reasoning_engines/test_algebraic_reasoning.py` | 代数推理（world hardest problem + ratio hallucination xfail） | 2 | pytest | 原有 |
| 9 | `tests/test_problems_perf.py` | 复杂 IMO 题（2016P10/2009P2/2011P6 skip/2000P1）+ CLI | 5 | pytest | 迁移自 `tests_perfs/` |
| 10 | `tests/test_all_benchmark.py` | 全数据集 benchmark（HAGeo/IMO，并行执行+可视化） | 自定义 | 脚本 | 迁移自 `scripts/` |
| 11 | `tests/test_csolver_basic.py` | CSolver 基础功能（IMO 2000 P1） | 1 | 脚本 | 迁移自 `scripts/test_DDAR.py` |
| 12 | `tests/test_csolver_synthetic.py` | CSolver 合成数据测试（argparse，依赖 JSONL） | 自定义 | 脚本 | 迁移自 `scripts/` |
| 13 | `tests/test_reduction.py` | 规约组件（GeneralityScorer/SubsumptionTester/RuleReducer） | 3 | 脚本 | 迁移自 `scripts/` |
| 14 | `tests/test_premises_loading.py` | Premises 加载（build_premises/extract/DirectSolver/JGEX） | 4 | 脚本 | 迁移自 `scripts/` |

辅助文件:
- `tests/fixtures.py` — `build_until_works()` 辅助函数
- `tests/candidate_rule.json` — 52 条规则测试数据

---

## 本次整理操作记录

### 删除的文件（16 个）

| 文件 | 删除原因 |
|------|---------|
| `tests/test_solve.py` | 非 pytest 格式，与 test_direct_solver 重叠 |
| `tests/test_direct_solver.py` | 硬编码 `/root/GenesisGeo/` 路径失效，非 pytest |
| `tests/test_step1e_normalization.py` | 用户决定删除 |
| `tests/test_cli.py` | 全部注释，空壳 |
| `tests/test_geogebra.py` | 空文件 |
| `tests/test_pyvis.py` | 唯一测试被 skip |
| `scripts/test_custom_rules.py` | 硬编码 `/root/GenesisGeo/` 路径失效 |
| `scripts/test_custom_rules_benchmark.py` | 硬编码 `/root/GenesisGeo/` 路径失效 |
| `scripts/test_direct_solver_synthetic.py` | 用户决定删除 |
| `scripts/comprehensive_direct_solver_test.py` | 用户决定删除 |
| `scripts/dual_group_direct_solver_test.py` | 用户决定删除 |
| `scripts/test_point_coords_comprehensive.py` | 依赖特定输出目录 |
| `scripts/test_load_rules.py` | 依赖特定实验输出 |
| `scripts/test_parse_llm_input.py` | 单函数临时测试 |
| `scripts/generate_test_rules.py` | 辅助生成脚本，不再需要 |
| `scripts/generate_test_coords.py` | 辅助生成脚本，不再需要 |

### 迁移的文件（6 个）

| 原路径 | 新路径 |
|--------|--------|
| `tests_perfs/test_problems.py` | `tests/test_problems_perf.py` |
| `scripts/test_all.py` | `tests/test_all_benchmark.py` |
| `scripts/test_DDAR.py` | `tests/test_csolver_basic.py` |
| `scripts/test_csolver_synthetic.py` | `tests/test_csolver_synthetic.py` |
| `scripts/test_reduction.py` | `tests/test_reduction.py` |
| `scripts/test_premises_loading.py` | `tests/test_premises_loading.py` |

### 删除的目录

- `tests_perfs/` — 内容已迁移，目录已删除
