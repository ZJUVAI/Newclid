# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GenesisGeo is a neuro-symbolic geometric theorem prover reproducing AlphaGeometry. It combines a C++ symbolic deduction engine (DDAR) with neural language models for auxiliary point proposals. Achieves 24/30 on IMO-AG-30 benchmark.

## Build & Setup

```bash
# Install package
pip install -e .

# Compile C++ Python extensions (required)
cd src/newclid
c++ -O3 -Wall -shared -std=c++14 -march=native -funroll-loops -flto \
  `python3 -m pybind11 --includes` matchinC.cpp \
  -o matchinC`python3-config --extension-suffix` -fPIC

cd dependencies
c++ -O3 -Wall -shared -std=c++14 -march=native -funroll-loops -flto \
  `python3 -m pybind11 --includes` geometry.cpp \
  -o geometry`python3-config --extension-suffix` -fPIC

# Build DDAR C++ components
cd src/newclid/DDAR && bash build.sh
```

## Test Commands

```bash
# Run all tests with coverage (76% minimum required)
pytest tests --cov=src --cov-fail-under=76

# Run specific test file
pytest tests/test_direct_solver.py
```

## Lint Commands

```bash
ruff check src/newclid --fix
ruff format src/newclid
```

## Key Commands

```bash
# Generate synthetic data (5M samples, 30 threads)
python src/newclid/generation/generate.py --n_threads=30 --n_samples=5000000 --log_level=info --timeout=3600

# Evaluate on benchmark
python scripts/evaluation.py --problems_path benchmarks/core/imo_ag_30.txt \
  --model_path ZJUVAI/GenesisGeo --max_workers 80 --decoding_size 32 \
  --beam_size 512 --search_depth 4

# Train model (uses ms-swift framework)
bash scripts/train_eval.sh

# Run CLI solver
newclid --problem-name <name> --env <env_dir> --agent ddarn
```

## Architecture

### Core Components

**DDAR Symbolic Engine** (`src/newclid/DDAR/`) - C++ implementation:
- `solver/ddar.cpp`: Main deduction loop applying geometric rules exhaustively
- `matcher.cpp`: Matches theorems to current proof state (optimized for 120x speedup)
- `rule_parser.cpp`: Parses custom rule text into Theorem objects
- `custom_rule_matcher.cpp`: Matches custom rules against problem points
- `predicate/`: 30+ geometric predicates (cong, para, cyclic, eqangle, eqratio, etc.)
- `ar/`: Algebraic reasoning - linear systems and equation manipulation

**Python API** (`src/newclid/`):
- `api.py`: `GeometricSolverBuilder` (builder pattern) and `GeometricSolver` classes
- `proof.py`: `ProofState` manages dependency graph and numerical geometry
- `match_theorems.py`: Python-side theorem matching

**Deductive Agents** (`src/newclid/agent/`):
- `ddarn.py`: Breadth-first exhaustive symbolic deduction
- `lm.py`: `LMAgent` uses Qwen3 LLM for auxiliary point proposals with beam search
- All inherit from `DeductiveAgent` interface in `agents_interface.py`

**Data Generation** (`src/newclid/generation/`):
- `generate.py`: Ray-based distributed generation orchestrator
- `clause_generation.py`: Random geometric construction sampling
- `problem_worker.py`: Worker processes for parallel problem generation

**Proof Scout** (`src/newclid/proof_scout/`):
- `core/`: Core graph structures (ProofGraph, GraphPruner, FilterAndPruneEngine) - no ML dependencies
- `extraction/`: Rule extraction utilities (RuleExtractor, RuleConverter, RuleTester) - no ML dependencies
  - `RuleTester`: Validates rules using DDAR, includes generative rule filtering
- `ml/`: ML pipeline (scout_pipeline, model_utils, data_processor) - requires torch
- `docs/`: Documentation

### Data Flow

1. Problem parsed from JGEX format into `ProblemJGEX`
2. `ProofState` built with numerical coordinates and dependency graph
3. `DeductiveAgent.run()` applies rules until goal proven or timeout
4. For `LMAgent`: LLM proposes auxiliary constructions, DDAR verifies each

### Problem Format (JGEX)

```
problem_name
a : ; b : ; c : cong a b b c [000] ; d : perp b c b d [001] ? eqangle a b c d e f g h
```

Constructions before `?`, goals after. Predicates: `cong`, `para`, `perp`, `coll`, `cyclic`, `eqangle`, `eqratio`, `midp`, etc.

## Key Patterns

- DDAR runs in subprocess isolation to prevent memory leaks
- Ray used for parallel data generation and evaluation
- Numerical validation prevents floating-point errors in proofs
- Beam search with multiple LLM candidates for auxiliary construction proposals

## Important Notes (铁律)

**Git Workflow Rules**:
- **Push**: 只推送到 `origin` 远端仓库，除非有特殊说明
- **GenesisGeo 远端**: 仅用于拉取信息、对齐引擎开发进度，不进行推送
- 示例: `git push origin <branch>` ✓ | `git push GenesisGeo <branch>` ✗

**DDAR Code Synchronization**: When there are differences in the DDAR directory (`src/newclid/DDAR/`), always use the version from the GenesisGeo remote repository as the authoritative source, unless explicitly stated otherwise. To sync:

```bash
git fetch GenesisGeo
git checkout GenesisGeo/main -- src/newclid/DDAR/
```

**Language Usage Rules**:
- **Communication with User**: 与用户交流时尽量使用中文（特有名词可以用英语表达）
- **Task Execution**: 执行任务时（如工具调用的 description、代码注释、commit message 等）使用英语
- **Example**:
  - ✓ 用户交流: "我现在开始运行 benchmark 测试"
  - ✓ Tool description: "Run benchmark on HAGeo 409 dataset"
  - ✓ Commit message: "Add language usage rules to CLAUDE.md"

---

## Done Tasks

- 2026-01-28: 配置 git 远端仓库（origin 指向 Try-GeoDiscovery-Using-CC）
- 2026-01-28: 更新 /continue 命令，加入 plan 模式流程
- 2026-01-28: 创建 /summarize 命令
- 2026-01-28: 优化 /summarize 命令（改为询问确认 compact 状态）
- 2026-01-28: 创建 Discovery conda 环境（Python 3.10 + PyTorch 2.5.1+cu121），编译所有 C++ 扩展
- 2026-01-28: 分离ML依赖与纯引擎依赖（pyproject.toml分组、api.py延迟导入、__init__.py懒加载ML agents）
- 2026-01-29: 重组 proof_scout 模块结构（core/extraction/ml 三层分离，实现懒加载避免加载 torch/pydot）
- 2026-01-29: 从 GenesisGeo/evaluation 分支同步 benchmarks（含 _with_coordinates 格式文件）
- 2026-01-29: 打通 Generation → Proof Scout → Evaluation pipeline（创建 RuleConverter、RuleTester、discovery_pipeline.py）
- 2026-01-29: 完成 CSolver 性能分析 Phase 1（创建 benchmark_csolver.py，运行 HAGeo 409 基准测试）
- 2026-01-30: 设置 Yuclid 环境并完成 HAGeo 409 基准测试（创建 benchmark_yuclid.py）
- 2026-01-31: CSolver 性能优化（两指针合并、惰性排序、早期终止），平均提速 11%，中位数提速 18%
- 2026-02-01: CSolver 性能优化 Phase 2（TermArg比较优化、冗余normalize移除、reduce缓存），平均提速 40%，中位数提速 44%
- 2026-02-01: CSolver 支持自定义规则匹配（新增 rule_parser.cpp, custom_rule_matcher.cpp, run_ddar_with_rules API）
- 2026-02-01: Discovery pipeline 引擎改用 CSolver（RuleTester 新增 use_csolver 参数，默认使用 C++ DDAR 引擎）
- 2026-02-01: Discovery Pipeline 端到端测试完成（创建 generate_synthetic_discovery_data.py，增强 discovery_pipeline.py 支持批处理和报告生成）
- 2026-02-01: 规则验证问题分析文档（创建 docs/rule_validation_issues.md，详细分析转换失败/无效原因，给出修改方案）
- 2026-02-01: RuleTester 短期修复（添加 max_premises 参数、UNSUPPORTED_GOAL_PREDICATES 过滤、改进错误消息）
- 2026-02-02: 自定义规则影响测试（创建 benchmark_csolver_with_rules.py，发现规则导致堵塞问题）
- 2026-02-09: 修复自定义规则堵塞问题（添加生成性规则过滤，过滤 cyclic=>eqangle 规则后恢复基线性能）
- 2026-02-16: Benchmark 清洗工作 Phase 1（盘点现状、备份数据、收集 IMO 自然语言题目、整理 tong-geometry 数据）
- 2026-02-16: Benchmark 清洗工作 Phase 2（目录重组为 core/extended/coords/dev，辅助点移至 datasets/aux_points/，更新所有脚本路径引用，创建 README.md）
- 2026-02-22: IMO-AG-50 自然语言收集与整理（提取49题自然语言版本到 datasets/imo_ag_50/problems_natural_language.txt，下载19份官方shortlist PDF到 datasets/imo_shortlists/，创建 imo_ag_50_index.txt 索引文件含shortlist ID映射）
- 2026-02-22: IMO-AG-50 JGEX 形式化草稿（分析18条缺失条目，完成10条Category A草稿、4条Category B分析、4条Category C不可形式化说明，输出 datasets/imo_ag_50/jgex_formalization_drafts.md）
- 2026-03-02: MO-TG-225 Benchmark 构建完成（创建 convert_tong_to_jgex.py 转换工具，生成 mo_tg_225_draft.txt 含156题JGEX格式，创建 mo_tg_225_index.txt 索引文件含问题来源和链接，转换成功率79.6%，所有转换题目通过JGEX语法验证）
- 2026-03-04: 生成 100k 合成数据用于知识发现（修复 CSolver 调用参数 using_log=True & using_exp=True，修复点提取顺序问题，配置 Ray 超时参数，成功生成 100,134 样本，耗时 208s，平均速度 480 samples/s）

## Current Task

### MO-TG-225 Benchmark 构建完成

已完成的工作：
1. **转换工具**: 创建 `scripts/convert_tong_to_jgex.py`，支持15+种Action类型和10+种Fact类型
2. **JGEX文件**: 生成 `datasets/mo_tg_225/mo_tg_225_draft.txt`，包含156题（79.6%转换成功率）
3. **索引文件**: 创建 `datasets/mo_tg_225/mo_tg_225_index.txt`，含问题来源、年份、竞赛类型、官方链接
4. **验证**: 所有156题通过ProblemJGEX语法验证（100%有效）
5. **报告**: 生成 `datasets/mo_tg_225/CONVERSION_REPORT.md` 详细转换报告

### 转换统计

| 指标 | 数量 | 百分比 |
|------|------|--------|
| 总案例数 | 196 | 100% |
| 成功转换 | 156 | 79.6% |
| 转换失败 | 40 | 20.4% |
| JGEX语法有效 | 156 | 100% |

### 问题分布

- IMO: 42题（35转换，7失败）
- USAMO: 16题（14转换，2失败）
- ISL: 45题（35转换，10失败）
- China TST: 44题（36转换，8失败）
- 其他: 49题（36转换，13失败）

### 下一步工作

- [ ] 对转换后的题目进行DDAR引擎测试，验证语义正确性
- [ ] 手动审查40个失败案例，识别可重新形式化的题目
- [ ] 调查196案例如何生成225题（可能涉及if-and-only-if拆分）
- [ ] 将benchmark集成到benchmarks/extended/目录

### IMO-AG-50 JGEX 形式化草稿完成

已完成的工作：
1. **JGEX 形式化草稿**: 分析全部 18 条缺失条目，输出 `datasets/imo_ag_50/jgex_formalization_drafts.md`
2. **分类结果**:
   - Category A（可形式化）: 10 条，含 2 条高置信度（= 已有 AG-30）、3 条中置信度、5 条低置信度
   - Category B（部分形式化）: 4 条（不等式/求值目标，无法有意义地形式化）
   - Category C（不可形式化）: 4 条（非综合几何：n 对象、面积、组合）

### JGEX 形式化状态更新

| 状态 | 数量 | 说明 |
|------|------|------|
| 已有 JGEX (AG-30) | 29 | core/imo_ag_30.txt |
| 已有 JGEX (extended) | 4 | 2005-1, 2007-2, 2013-3, 2024-4 |
| 已有 JGEX (用户提供) | 1 | 2008-6 |
| 可复用 AG-30（拆分重命名） | 2 | 2003-4a, 2004-5a |
| 草稿待测试 | 3 | 2009-4a/b, 2023-2 |
| 草稿需深入分析 | 5 | 2003-4b, 2004-5b, 2014-3, 2018-6, 2023-6 |
| 不可形式化 | 8 | 2001-1/5, 2002-6, 2003-3, 2006-1/6, 2020-6, 2021-4 |
| **AG-50 总条目** | **50** | |

### 目录结构更新

```
datasets/
├── imo_ag_50/                    # IMO-AG-50 数据
│   ├── problems_natural_language.txt  # 49题自然语言版本
│   ├── imo_ag_50_index.txt            # 索引文件
│   └── jgex_formalization_drafts.md   # JGEX 形式化草稿 (新增)
├── imo_shortlists/               # 官方 Shortlist PDF
│   ├── IMO2006SL.pdf ~ IMO2024SL.pdf  # 19份
├── imo_natural_language/         # Evan Chen LaTeX 笔记
│   └── IMO-{YEAR}-notes.tex           # 25份 (2000-2024)
└── ...
```

## Custom Rules Impact Test (2026-02-02)

### 测试目标

验证从 discovery pipeline 提取的 13 条有效规则是否能在 HAGeo 409 基准测试中提升求解能力，或者是否会导致"堵塞"（solver 陷入无效推理循环）。

### 基线数据

| 配置 | 解决数 | 超时数 | 平均时间 |
|------|--------|--------|----------|
| CSolver (无规则) | 101/404 (25.0%) | 3 | 0.79s |
| Yuclid | 104/404 (25.7%) | 0 | 0.095s |

### 测试结果

#### 测试 1: 全部 13 条有效规则

| 指标 | 基线 | 带规则 | 变化 |
|------|------|--------|------|
| 解决数 | 101 | 100 | **-1** |
| 超时数 | 3 | 12 | **+9** |
| 平均时间 | 0.79s | 2.61s | **+230%** |

**新增超时问题 (10个)**:
- 2011G3, 2016USATSTSTp6, 2017EuropeanMCupSp3, 2023SAGFp8
- ShuZhiMi2024SpFp19, ShuZhiMiGeo180, ShuZhiMiGeo209, ShuZhiMiGeo256, ShuZhiMiGeo635, XinXingV28p2

**不再能解决的问题**:
- 2017EuropeanMCupSp3 (基线 3.7s 解决，带规则超时)

#### 测试 2: 过滤后的 6 条规则

原始 13 条规则中，7 条包含 CSolver 不支持的谓词（ncoll, sameclock, sameside），被自动跳过。

**实际可用规则 (6条)**:
1. `cyclic a b c d => eqangle c a c b d a d b`
2. `cong a b a c, coll a b c => midp a b c`
3. `midp a b c, perp b d d c => cong b a d a`
4. `midp a b c => coll a b c`
5. `perp a b c d, perp a c b d => perp a d b c`
6. `circle a b c d, cyclic b c d e => cong a b a e`

| 指标 | 基线 | 6条规则 | 变化 |
|------|------|---------|------|
| 解决数 | 101 | 100 | **-1** |
| 超时数 | 3 | 16 | **+13** |
| 平均时间 | 0.79s | 2.31s | **+192%** |

### 分析

1. **规则导致堵塞**: 添加规则后解决的问题数减少，超时数显著增加
2. **推理路径爆炸**: 规则（特别是 `cyclic => eqangle`）产生大量新的推理分支
3. **性能开销**: 即使规则被跳过（因变量不匹配），仍有显著的时间开销

### 根本原因

规则 `cyclic a b c d => eqangle c a c b d a d b` 是一个"生成性"规则：
- 对于每个 cyclic 谓词，它可以生成多个 eqangle 谓词
- 这些新的 eqangle 又可以触发其他规则
- 导致推理状态空间指数级增长

### 结论

**当前的规则集不适合直接用于 CSolver**。需要：
1. 更严格的规则筛选（避免生成性规则）
2. 规则应用的限制机制（如最大应用次数）
3. 或者改用不同的规则发现策略

### 修复方案 (2026-02-09)

实现了 Python 层面的生成性规则过滤：

**修改的文件**:
- `scripts/benchmark_csolver_with_rules.py`: 添加 `filter_generative_rules()` 函数和 `--no-filter` 参数
- `src/newclid/proof_scout/extraction/rule_tester.py`: 添加 `GENERATIVE_RULE_PATTERNS` 和 `_is_generative_rule()` 方法

**过滤规则**:
```python
GENERATIVE_RULE_PATTERNS = {
    ('cyclic', 'eqangle'),  # cyclic => eqangle 与内置 eqangle => cyclic 形成反馈循环
}
```

**测试结果 (过滤后 12 条规则)**:

| 指标 | 基线 | 未过滤 (13规则) | 过滤后 (12规则) |
|------|------|-----------------|-----------------|
| 解决数 | 101 | 100 | **101** |
| 超时数 | 3 | 12 | **2** |
| 平均时间 | 0.79s | 2.61s | **0.65s** |

**结论**: 过滤生成性规则后，性能恢复到基线水平，甚至略有提升。

### 输出文件

- 基线结果: `outputs/benchmark_baseline.json`
- 全规则结果: `outputs/benchmark_with_rules.json`
- 过滤规则结果: `outputs/benchmark_filtered_v2.json`
- 过滤规则文件: `outputs/discovery_direct_test/valid_rules_filtered.txt`

### 新增脚本

`scripts/benchmark_csolver_with_rules.py`:
- 支持 `--rules` 参数加载自定义规则
- 支持 `--compare` 模式对比两个结果文件
- 支持 `--no-filter` 禁用生成性规则过滤（默认启用过滤）
- 自动解析规则文件格式（每两行一条规则）
- 自动过滤会导致推理爆炸的生成性规则

## Todolist

- [x] 将模型训练、推理的代码和引擎的依赖用合适的形式分离，我希望在进行只涉及引擎推理的时候，不需要预先加载很多类似Torch这样的包，能够更轻盈地测试与开发
- [x] 整理目前和知识发现/定理提取/proof_scout有关的所有代码，重新组织，重新放在proof_scout这个目录下
- [x] 从GenesisGeo远端仓库的Evaluation分支拿到用来测试的benchmarks，添加到当前仓库中
- [x] 打通从数据生成（generation）到定理发现(proof_scout)再到测试评估的pipeline
- [x] 换一个新的conda环境，跑通yuclid，并且检测一下它在hageo 409基准下的测试结果
- [x] 与https://github.com/Newclid/Newclid中的yuclid比对，分析yuclid比Csolver快的原因，加速CSolver的求解速度（Phase 2完成，提速 40-44%，与Yuclid差距从10x缩小到5-6x）
- [x] 因为知识发现需要引入新的规则，Python的引擎又太慢了，需要CSolver支持对提取的规则进行匹配
- [x] discovery_pipeline的引擎改用CSolver
- [x] 用新的pipeline跑一轮结果，从数据生成到规则提取到测试评估的全流程，进行一次报告
- [x] 上一次的端到端测试中，存在很多规则转换失败或者无效的情况，我需要一个文档来说明为什么会出现这些情况，并给出修改方案，是设计如何跳过无效/错误规则还是进行CSolver引擎的改进
- [x] 上一次的端到端测试只是说明了转换成功，但是是否可以用在CSolver中，需要通过对benchmarks进行测试才行，如果添加了规则，HAGeo 409能做出的题目反而少于101或者104，那么就说明还是出现了堵塞的情况，需要调整
- [x] 彻底清洗并重构 Benchmark 文件夹：按用途分类到 core/extended/coords/dev 子目录，辅助点数据移至 datasets/aux_points/，更新所有脚本路径引用
- [ ] 下一步：对 JGEX 草稿中置信度为 Medium 的条目（2009-4a/b, 2023-2）进行 DDAR 引擎测试验证
- [ ] 上述两个问题解决后，还需要进行一个稍微大一些规模的测试，生成10k的数据，提取规则后对HAGeo 409进行测试，我需要说明这个方法是比baseline有效的

## Discovery Pipeline Test Results (2026-02-01)

### 测试概要

使用 `datasets/candidate_rules/tmp_rules.txt` 中的 50 条规则进行端到端测试。

### 结果统计

| 阶段 | 指标 | 数值 |
|------|------|------|
| Stage 2 (转换) | 总规则 | 50 |
| | 成功转换 | 49 |
| | 跳过 | 1 |
| Stage 3 (测试) | 有效 | 13 (26.5%) |
| | 无效 | 25 (51.0%) |
| | 转换失败 | 11 (22.4%) |

### 有效率按复杂度

| 复杂度 | 测试数 | 有效 | 有效率 |
|--------|--------|------|--------|
| 简单 (1-2前提) | 15 | 7 | 46.7% |
| 中等 (3-4前提) | 20 | 3 | 15.0% |
| 复杂 (5+前提) | 14 | 3 | 21.4% |

### 主要发现

1. **Pipeline 功能正常:** 从规则转换到测试验证的完整流程可以正常运行
2. **简单规则更可靠:** 1-2 个前提的规则有效率显著高于复杂规则
3. **CSolver 性能良好:** 批处理机制有效，平均每规则测试耗时约 0.15s
4. **合成数据需改进:** 当前的合成数据生成器无法产生符合 FilterAndPruneEngine 期望格式的数据

### 输出文件

- 详细报告: `outputs/discovery_pipeline_report.md`
- 有效规则: `outputs/discovery_direct_test/valid_rules.txt`
- 测试结果: `outputs/discovery_direct_test/test_results.json`
- 规则分析: `outputs/discovery_direct_test/rule_analysis.json`

## CSolver Performance Analysis (2026-01-29)

### Benchmark Results (HAGeo 409)

**Summary**:
- Total problems: 404
- Solved: 39 (9.7%)
- Failed: 364 (90.1%)
- Timeout (>30s): 1

**Time Statistics**:
| Metric | Value |
|--------|-------|
| Mean | 0.516s |
| Median | 0.189s |
| P90 | 1.275s |
| P95 | 1.813s |
| P99 | 4.561s |
| Max | 15.596s |

**Slowest Problems**:
1. ShuZhiMiGeo309: 15.6s (FAILED)
2. XinXingV28p2: 6.1s (FAILED)
3. ShuZhiMiGeo180: 5.8s (FAILED)
4. 2014CTSTp13: 4.6s (SOLVED)

**Problem Complexity**:
- Average points: 11.8
- Average premises: 17.3

### Comparison with Yuclid

**重要发现**: CSolver 需要启用 `log_enabled=True` 和 `exp_enabled=True` 才能正常工作！

**Yuclid Benchmark Results (HAGeo 409, 2026-01-30)**:
- Total problems: 404
- Solved: 104 (25.7%)
- Failed: 300 (74.3%)
- Timeouts: 0

**CSolver (log_enabled=True) Benchmark Results**:
- Total problems: 404
- Solved: 100 (24.8%)
- Failed: 298 (73.8%)
- Timeouts: 1
- Errors: 5 (non-reduced equation)

| Metric | CSolver | Yuclid | Yuclid Speedup |
|--------|---------|--------|----------------|
| Solved | 100 (24.8%) | 104 (25.7%) | +4 problems |
| Mean | 1.02s | 0.095s | 10.7x |
| Median | 0.38s | 0.038s | 10.0x |
| Max | 19.9s | 2.15s | 9.2x |

**Key Findings**:
- 解题能力相近：CSolver 100题 vs Yuclid 104题（差4题，均为CSolver报错）
- Yuclid 速度优势明显：**平均快 10-12x**
- 100个问题两者都能解决，4个问题仅 Yuclid 解决（CSolver 报 "non-reduced equation" 错误）

**CSolver Errors (5个问题)**:
- 2007CMOp4, 2011CHNWesternMOp7, 2012CHNSouthEastMOp2, 2021GOWACAp6, 2023G7
- 错误信息: "Trying to insert a non-reduced equation"

**Yuclid Environment**:
```bash
conda activate yuclid  # Python 3.11
# py-yuclid 3.0.0 + newclid 3.0.1 installed
```

**Benchmark Scripts**:
```bash
# Yuclid benchmark
python scripts/benchmark_yuclid.py \
    --problems benchmarks/coords/hageo_409_coords.txt \
    --output outputs/benchmark_yuclid_hageo409.json \
    --timeout 30 --verbose

# CSolver benchmark (已修改为 log_enabled=True, exp_enabled=True)
python scripts/benchmark_csolver.py \
    --problems benchmarks/coords/hageo_409_coords.txt \
    --output outputs/benchmark_csolver_fixed.json \
    --timeout 30
```

### Identified Bottlenecks (from code analysis)

| Component | Issue | Priority | Status |
|-----------|-------|----------|--------|
| `LinearCombination::operator+=` | O(n²) linear search for term merging | High | ✅ Fixed (two-pointer merge) |
| `DDARSolver::run_level()` | No early termination after goal proven | Medium | ✅ Fixed |
| `normalize()` | Redundant sorting | Medium | ✅ Fixed (lazy sorting) |
| `ReducedEquation::reduce()` | No caching | Low | Tested, overhead > benefit |

### CSolver Optimization Results (2026-01-31)

**Optimizations Applied**:
1. Two-pointer merge for LinearCombination (O(n) instead of O(n²))
2. Lazy sorting with `_is_sorted` flag
3. Early termination in DDARSolver when goals are proved

**Benchmark Results (HAGeo 409)**:

| Metric | Original | Optimized | Improvement |
|--------|----------|-----------|-------------|
| Solved | 100 (24.8%) | 100 (24.8%) | Same |
| Mean | 1.02s | 0.91s | **11% faster** |
| Median | 0.38s | 0.31s | **18% faster** |
| Max | 19.9s | 15.7s | **21% faster** |
| Errors | 5 | 5 | Same |

**Comparison with Yuclid**:

| Metric | Optimized CSolver | Yuclid | Gap |
|--------|-------------------|--------|-----|
| Solved | 100 (24.8%) | 104 (25.7%) | -4 problems |
| Mean | 0.91s | 0.095s | 9.6x slower |
| Median | 0.31s | 0.038s | 8.2x slower |

**Note**: The gap with Yuclid has been reduced from ~10x to ~8-9x. Further optimization would require deeper architectural changes.

### CSolver Optimization Results Phase 2 (2026-02-01)

**Optimizations Applied**:
1. TermArg::operator< - Direct field comparison instead of string allocation (preserving string ordering semantics)
2. Equation::operator+/- - Removed redundant normalize() calls
3. ReducedEquation::reduce() - Conservative caching for fully solved equations

**Benchmark Results (HAGeo 409)**:

| Metric | Phase 1 | Phase 2 | Improvement |
|--------|---------|---------|-------------|
| Solved | 100 (24.8%) | 101 (25.0%) | **+1 problem** |
| Errors | 5 | 4 | **-1 error** |
| Mean | 1.02s | 0.61s | **40% faster** |
| Median | 0.38s | 0.21s | **44% faster** |
| Max | 19.9s | 10.8s | **46% faster** |

**Comparison with Yuclid (after Phase 2)**:

| Metric | Phase 2 CSolver | Yuclid | Gap |
|--------|-----------------|--------|-----|
| Solved | 101 (25.0%) | 104 (25.7%) | -3 problems |
| Mean | 0.61s | 0.095s | 6.4x slower |
| Median | 0.21s | 0.038s | 5.5x slower |

**Progress**: Gap with Yuclid reduced from ~10x (original) → ~8-9x (Phase 1) → **~5-6x (Phase 2)**

### Benchmark Scripts

```bash
# Run CSolver benchmark (log_enabled=True, exp_enabled=True)
python scripts/benchmark_csolver.py \
    --problems benchmarks/coords/hageo_409_coords.txt \
    --output outputs/benchmark_csolver_fixed.json \
    --timeout 30
```

Results saved to: `outputs/benchmark_csolver_fixed.json`

### CSolver Custom Rules Support (2026-02-01)

CSolver now supports dynamic loading and matching of custom rules, enabling the discovery pipeline to use the fast C++ engine.

**New Files**:
- `src/newclid/DDAR/rule_parser.hpp/cpp`: Parses rule text into Theorem objects
- `src/newclid/DDAR/custom_rule_matcher.hpp/cpp`: Matches custom rules against problem points

**Rule Format**:
```
premise1, premise2 => conclusion1, conclusion2
```

Examples:
```
cong a b c d => cong c d a b
cong a b c d, para a b c d => cyclic a b c d
eqangle a b c d e f g h => eqangle e f g h a b c d
```

**Python API**:
```python
from newclid.DDAR.build import DDAR

# Direct DDAR API with custom rules
custom_rules = ["cong a b c d => cong c d a b"]
solved, dep_graph = DDAR.run_ddar_with_rules(
    name, points, premises, goals, custom_rules,
    max_level=500, log_enabled=True, exp_enabled=True
)

# CSolver API with custom rules
from newclid.api import CSolver
solver = CSolver(
    problem=problem_txt,
    custom_rules=["cong a b c d => cong c d a b"]
)
solved = solver.run()

# RuleTester API (validates rules with generative filtering)
from newclid.proof_scout.extraction.rule_tester import RuleTester
tester = RuleTester(use_csolver=True, filter_generative=True)
result = tester.test_rule("cong a b c d => cong c d a b")
# result: {"rule": ..., "success": True/False, "filtered": True/False, ...}
```

**Limitations**:
- Maximum 8 variables per rule (to prevent combinatorial explosion)
- Rule variables must match actual point names in the problem
- Invalid rules are skipped with a warning
- Generative rules (e.g., `cyclic => eqangle`) are filtered by default to prevent inference explosion

## Generative Rule Filtering

Rules that create feedback loops with built-in DDAR rules are automatically filtered:

```python
# In RuleTester and benchmark_csolver_with_rules.py
GENERATIVE_RULE_PATTERNS = {
    ('cyclic', 'eqangle'),  # cyclic => eqangle creates feedback with eqangle => cyclic
}
```

To disable filtering, use `--no-filter` flag or set `filter_generative=False` in RuleTester.

## Temporary Interaction Area

当前 Git 远端配置：
- origin → git@github.com:ZhengtongDu/Try-GeoDiscovery-Using-CC.git
- GenesisGeo → git@github.com:ZJUVAI/GenesisGeo.git

Discovery 环境配置：
- 环境路径: /root/miniconda3/envs/Discovery
- Python: 3.10
- PyTorch: 2.5.1+cu121
- 所有 C++ 扩展已编译完成（matchinC, geometry, DDAR）

Discovery Pipeline 使用方法：
```bash
# 完整流水线（Generation → Proof Scout → Evaluation）
python scripts/discovery_pipeline.py \
    --input datasets/geometry_clauses15_samples1M.jsonl \
    --output outputs/discovery_run \
    --benchmark benchmarks/core/imo_ag_30.txt \
    --max_workers 50

# 跳过规则测试和评估（仅提取规则）
python scripts/discovery_pipeline.py \
    --input datasets/data.jsonl \
    --output outputs/run \
    --skip_stage3 --skip_stage4

# 带自定义规则的基准测试（自动过滤生成性规则）
python scripts/benchmark_csolver_with_rules.py \
    --problems benchmarks/coords/hageo_409_coords.txt \
    --rules outputs/discovery_direct_test/valid_rules.txt \
    --output outputs/benchmark_with_rules.json \
    --timeout 30

# 禁用生成性规则过滤
python scripts/benchmark_csolver_with_rules.py \
    --problems benchmarks/coords/hageo_409_coords.txt \
    --rules outputs/discovery_direct_test/valid_rules.txt \
    --output outputs/benchmark_no_filter.json \
    --timeout 30 --no-filter
```


