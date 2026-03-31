# GenesisGeo 项目全局记忆

## 项目简介

GenesisGeo 是 [AlphaGeometry](https://www.nature.com/articles/s41586-023-06747-5) 的复现项目，实现了一个能够证明几何定理的 AI 系统。

**核心特性：**
- 合成数据生成（生成了 2180 万道题目）
- 增强的 DDARN 引擎（120 倍加速）
- 神经符号推理器：使用 Qwen3-0.6B-Base 微调
- 在 IMO-AG-30 基准测试中证明了 30 道题目中的 24 道

---

## 常用命令

### 运行测试
```bash
pytest tests --cov=src --cov-fail-under=76
```

### 运行 CLI
```bash
newclid --problem-name <name> --env <env> --agent <agent> [options]
```

### 数据生成
```bash
python -m newclid.generation.pipeline --n_threads=30 --n_samples=5000000 --timeout=3600
```

### 模型评估
```bash
python scripts/evaluation.py --problems_path benchmarks/imo_ag_30.txt \
  --model_path ZJUVAI/GenesisGeo --max_workers 80 \
  --decoding_size 32 --beam_size 512 --search_depth 4
```

---

## 项目结构

```
GenesisGeo/
├── src/newclid/                    # 主源码
│   ├── __main__.py                 # CLI 入口
│   ├── api.py                      # GeometricSolver 接口
│   ├── proof.py                    # 证明状态管理
│   ├── agent/                      # 推理代理
│   │   ├── ddarn.py                # DDARN 符号推理
│   │   ├── lm.py                   # 语言模型代理
│   │   └── vlm.py                  # 视觉语言模型代理
│   ├── generation/                 # 数据生成（重构后）
│   ├── DDAR/                       # C++ 符号引擎
│   ├── dependencies/               # 依赖图管理
│   ├── formulations/               # 问题表示
│   ├── numerical/                  # 数值几何
│   ├── algebraic_reasoning/        # 代数推理
│   └── predicates/                 # 几何谓词
├── scripts/                        # 评估和工具脚本
├── tests/                          # 测试套件
├── benchmarks/                     # 基准测试题库
└── docs/                           # 文档
```

---

## 核心模块说明

| 模块 | 用途 | 关键类 |
|------|------|--------|
| `api.py` | 求解器接口 | `GeometricSolver`, `GeometricSolverBuilder` |
| `proof.py` | 证明状态 | `ProofState` |
| `agent/ddarn.py` | 符号推理 | `DDARNAgent` |
| `agent/lm.py` | LLM 辅助构造 | `LMAgent` |
| `generation/` | 数据生成 | `ProblemPipeline`, `ProblemSampler` |

---

## 几何问题数据格式

### 问题定义格式（fl_problem）

```
构造部分 ? 目标
```

**例子：**
```
a b c = triangle a b c; d = free d; e = on_circum e c b d, angle_bisector e a d b ? eqangle b d b e c d c e
```

### 构造部分结构

构造部分由多个**子句（clause）** 组成，用**分号 `;`** 分隔：

```
子句1; 子句2; 子句3; ...
```

每个子句的格式：
```
点名 = 构造类型 [参数]
```

- **点名**：一个或多个点，用空格分隔（如 `a b c` 或 `d`）
- **构造类型**：可以有多个，用**逗号 `,`** 分隔
- **参数**：构造所需的参数点

### 解析例子

```
a b c = triangle a b c; d = free d; e = on_circum e c b d, angle_bisector e a d b ? eqangle b d b e c d c e
```

| 子句 | 点名 | 构造类型 | 含义 |
|------|------|----------|------|
| `a b c = triangle a b c` | a, b, c | triangle | 三个点构成一个三角形 |
| `d = free d` | d | free | d 是自由点（任意位置） |
| `e = on_circum e c b d, angle_bisector e a d b` | e | on_circum, angle_bisector | e 在 cbd 外接圆上，且在角 adb 的角平分线上 |

**目标**：`eqangle b d b e c d c e` - 证明 ∠bde = ∠dce

### 谓词（Predicates）

构造语言（如 `triangle`, `on_circum`）会被翻译成谓词语言，用于推理计算。谓词既描述前提条件，也描述目标。

#### 常见谓词

| 谓词 | 参数 | 含义 |
|------|------|------|
| `coll a b c` | 3点 | a, b, c 共线 |
| `para a b c d` | 4点 | AB ∥ CD |
| `perp a b c d` | 4点 | AB ⊥ CD |
| `cong a b c d` | 4点 | AB = CD |
| `cyclic a b c d` | 4点 | a, b, c, d 共圆 |
| `eqangle a b c d e f g h` | 8点 | ∠(AB,CD) = ∠(EF,GH) |
| `eqratio a b c d e f g h` | 8点 | AB/CD = EF/GH |
| `simtri a b c d e f` | 6点 | △ABC ∼ △DEF |
| `contri a b c d e f` | 6点 | △ABC ≅ △DEF |
| `midp m a b` | 3点 | m 是 ab 的中点 |
| `circle o a b c` | 4点 | o 是 abc 外接圆圆心 |

#### 构造到谓词的翻译

构造语言在求解时会翻译成谓词：

```
构造: e = on_circum e c b d, angle_bisector e a d b
  ↓ 翻译
谓词: cyclic b c d e [000]
      eqangle a d d e d e b d [001]
```

### LLM 输入/输出格式

#### LLM 输入格式（llm_input_renamed）

```xml
<problem> 点1 : 前提条件 ; 点2 : 前提条件 ; ... ? 目标 </problem>
```

每个前提条件格式：`谓词 参数 [编号]`

**例子：**
```xml
<problem> a : ; b : ; c : ; d : ; e : cyclic b c d e [000] eqangle a d d e d e b d [001] ? eqangle b d b e c d c e </problem>
```

#### LLM 输出格式（llm_output_renamed）

```xml
<proof> 结论1 [编号] 规则 [依赖编号] ; 结论2 [编号] 规则 [依赖编号] ; ... </proof>
```

**例子：**
```xml
<proof> eqangle b d b e c d c e [002] r03 [000] ; </proof>
```

---

## generation 模块命名

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
