# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GenesisGeo — 神经-符号几何定理证明器，复现 AlphaGeometry，结合 C++ 符号推理引擎 (DDAR) 与神经语言模型。

## Current Focus: 知识发现 (Knowledge Discovery)

当前主线任务是**从合成数据中提取几何推理规则**，核心 pipeline 流程：

```
合成数据 (JSONL)
  → Stage 1: FilterAndPruneEngine (输入过滤/图修剪/命题提取/规范化/去重/落盘)
  → Stage 2: RuleReducer (max_premises过滤 → 泛化度排序 → 贪心淘汰)
  → 输出: extracted_rules.txt (最小基底规则集)
```
```

关键代码:
- Pipeline 核心: `src/newclid/proof_scout/core/filter_and_prune_engine.py`
- 规则规约: `src/newclid/proof_scout/reduction/rule_reducer.py`
- Pipeline 入口脚本: `scripts/discovery_pipeline.py`

详细 pipeline 数据看板: `docs/pipeline_dashboard.md`

| 模块 | 用途 | 关键类 |
|------|------|--------|
| `api.py` | 求解器接口 | `GeometricSolver`, `GeometricSolverBuilder` |
| `proof.py` | 证明状态 | `ProofState` |
| `agent/ddarn.py` | 符号推理 | `DDARNAgent` |
| `agent/lm.py` | LLM 辅助构造 | `LMAgent` |
| `generation/` | 数据生成 | `ProblemPipeline`, `ProblemSampler` |

---

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

**Planning Mode Language Rules**:
- 所有 plan 文件必须使用中文编写，确保用户能够直接理解计划内容
- Plan 文件中的所有章节（背景、实施步骤、验证方式等）都必须用中文表达
- 唯一例外：文件路径、代码片段、技术术语可以保持英文

**AI Tool Workflow Rules**:
- 所有 AI 编程工具在开始处理仓库任务前，必须先阅读 `CLAUDE.md`
- 在执行具体任务前，必须根据任务范围按需索引并阅读相关文档与 memory 文件，至少包括对应模块文档和 `memory/MEMORY.md`
- 完成任务后，必须按 `Memory Update Rules` 将本次任务摘要整理到 `memory/` 目录下对应文件
- 完成 memory 更新后，必须执行 git 提交，并直接推送到 `origin` 当前分支，无需再次征求用户确认

**Experiment Directory Rules** (实验目录铁律):
1. 每次实验必须在 `outputs/experiments/` 下创建子目录
2. 子目录命名格式: `YYYYMMDD_{id}_实验名称` 其中的id用两位数表示（如 01, 02, ..., 10, 11, ...），用来作为一天中任务的顺序标识
3. 子目录中必须包含 `info.md` 文件，说明：
   - 实验目的
   - 使用的命令
   - 关键参数
   - 结果摘要
4. Claude 在执行实验过程中需要同步编写 info.md

**Environment and Script Execution Rules** (CRITICAL - 每次执行脚本前必须检查):

1. **Conda Environment Activation**:
   - 环境名称: `Discovery` (注意大写D)
   - 激活命令: `source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery`
   - **所有Python脚本执行前必须先激活此环境**

2. **PYTHONPATH Configuration**:
   - 项目根目录: `/C20545/home/duzhengtong/GeoDiscovery`
   - src目录: `/C20545/home/duzhengtong/GeoDiscovery/src`
   - **如果脚本导入newclid模块失败，需要设置**: `PYTHONPATH=/C20545/home/duzhengtong/GeoDiscovery/src:$PYTHONPATH`
   - **注意**: 使用conda环境激活后通常不需要手动设置PYTHONPATH，因为项目已通过`pip install -e .`安装

3. **Script Execution Checklist** (执行脚本前的检查清单):
   ```bash
   # Step 1: 激活conda环境
   source /C20545/home/duzhengtong/miniconda3/bin/activate Discovery

   # Step 2: 验证环境
   which python  # 应该显示 /C20545/home/duzhengtong/miniconda3/envs/Discovery/bin/python

   # Step 3: 执行脚本
   python scripts/your_script.py [args]
   ```

4. **Background Task Execution**:
   - 长时间运行的任务应使用`run_in_background=true`
   - 使用conda环境时，必须在命令中包含环境激活: `source ... && python ...`

5. **CSolver 必须开启 using_log 和 using_exp** (CRITICAL):
   - 所有 CSolver 实例化必须设置 `using_log=True, using_exp=True`
   - 不开启这两个参数会导致 C++ DDAR 引擎缺少关键推理功能（对数推理、指数推理），结果不完整
   - 示例: `CSolver(problem=..., using_log=True, using_exp=True)`
   - **唯一例外**: 明确需要测试关闭这些功能的对比实验

**Memory Update Rules** (Memory 更新铁律):
- 每次任务完成后，必须更新 `memory/` 目录下对应的文件
- 每次任务摘要必须写入至少一个对应的 memory 文件；涉及全局流程、约束或工作流变更时，同时更新 `memory/MEMORY.md` 和 `memory/design_docs.md`
- 新实验完成 → 更新 `memory/completed_tasks.md` 和 `memory/test_results.md`
- 性能相关实验 → 更新 `memory/csolver_performance.md`
- 新命令/脚本使用 → 更新 `memory/command_history.md`
- 新设计决策 → 更新 `memory/design_docs.md`
- `memory/MEMORY.md` 保持为主索引，关键事实有变化时同步更新

**Task Completion Git Rules**:
- 完成代码与 memory 更新后，必须检查变更、执行 git commit，并推送到 `origin`
- 默认流程: `git add ...` → `git commit -m "..."` → `git push origin <current-branch>`
- 除非用户明确禁止，否则不要只停留在本地未推送状态

**Code-Documentation Sync Rules** (代码文档同步铁律):
- 修改 pipeline 代码（如 `filter_and_prune_engine.py`）时，必须同步更新 `docs/pipeline_dashboard.md`
- 修改 pipeline 步骤（增删改）时，dashboard 的总览图、详细说明、漏斗模板都要同步调整
- 代码中的 dashboard 对齐注释（`# Step 1a/1c/1d/1e`）必须与文档保持一致

**Data Format Reference Rules** (数据格式参考铁律):
- 处理数据文件或修改 pipeline 数据流时，必须先查阅 `docs/data_formats.md`
- 新增数据格式时，必须同步更新 `docs/data_formats.md`
- 修改现有数据格式时，必须检查是否影响下游消费者并更新文档

**Planning Mode Rigor Rules** (Planning 模式严格审问铁律):
- 在写任何代码之前，在 Planning 模式下无尽地审问我的想法
- 不要假设任何问题，问问题直到没有假设剩下
- 必须充分理解需求、现有代码结构、潜在影响后才能开始实现

**Experiment Error Tracking Rules** (实验错误追踪铁律):
- 在进行任何实验时，对于细小的错误或者数据有误都需要严格检查
- 所有错误必须详细记录在 `docs/tiny_error_records.md` 文档中
- 每条记录必须包含：
  - 日期 (YYYY-MM-DD)
  - 实验名称
  - 具体命令
  - 预期输出（可选）
  - 实际输出
  - 是否解决 (✓/✗)
- 即使是微小的数据不一致也要记录，这有助于追踪系统性问题

---

## Documentation Index (文档索引)

### docs/ — 技术文档 (按需查看)

| 文档 | 内容 | 何时需要查看 |
|------|------|-------------|
| `docs/architecture.md` | 系统架构、核心组件、数据流、问题格式 | 需要理解代码结构或修改核心模块时 |
| `docs/build_and_commands.md` | 构建、测试、lint、常用命令 | 需要构建项目、运行测试或执行命令时 |
| `docs/directory_structure.md` | 目录结构、环境配置 | 需要查找文件或了解项目组织时 |
| `docs/data_formats.md` | 数据格式参考（JSONL/Rule/Problem/中间产物） | 处理数据文件、修改 pipeline 代码、新增数据格式时 **必读** |
| `docs/pipeline_dashboard.md` | Discovery Pipeline 数据看板（每步逻辑+伪代码+漏斗数据） | 修改 pipeline 代码或分析 pipeline 数据时 **必读** |
| `docs/ddar_engine.md` | DDAR C++ 引擎技术文档（架构、谓词、定理、AR、Python API） | 修改 DDAR 引擎代码、调试 CSolver、理解符号推理流程时 **必读** |
| `docs/tiny_error_records.md` | 实验错误追踪记录（日期、命令、预期/实际输出、解决状态） | 遇到实验错误或数据异常时记录；排查历史问题时查看 |
| `docs/manual/` | Sphinx 用户手册（问题格式、规则定义等） | 需要了解 JGEX 格式或规则语法细节时 |

### memory/ — 任务记忆 (按需查看)

| 文档 | 内容 | 何时需要查看 |
|------|------|-------------|
| `memory/MEMORY.md` | **主索引** — 最近更新、关键事实、目录结构 | **每次任务开始时必读** |
| `memory/completed_tasks.md` | 已完成任务历史 | 需要了解历史上做过什么时 |
| `memory/design_docs.md` | 设计文档（Rule Reduction 算法、验证问题等） | 涉及设计决策或算法修改时 |
| `memory/test_results.md` | 测试结果归档 | 需要对比历史测试数据时 |
| `memory/csolver_performance.md` | CSolver 性能分析与优化记录 | 涉及 CSolver 性能调优时 |
| `memory/command_history.md` | 重要命令历史记录 | 需要查找之前运行过的命令时 |

### generation 模块命名

| 文件 | 类 | 用途 |
|------|-----|------|
| `sampler.py` | `ProblemSampler` | 采样几何构造 |
| `point_naming.py` | `PointNaming` | 点命名管理 |
| `filter.py` | `GoalFilter` | 目标过滤 |
| `worker.py` | `ProblemWorker` | 问题处理 |
| `pipeline.py` | `ProblemPipeline` | 生成流水线 |
| `writer.py` | `Writer` | 数据写入和图像生成 |
| `constructions.py` | - | 构造类型常量 |
| `statistics.py` | `Statistics` | 统计信息 |
| `auxiliary/` | - | 辅助点查找子包 |
