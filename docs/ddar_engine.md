# DDAR 引擎技术文档

> DDAR（Deductive Database with Algebraic Reasoning）— C++ 符号几何推理引擎

## 1. 概述

DDAR 是 GenesisGeo 项目的核心符号推理引擎，负责对几何问题进行自动定理证明。引擎采用 C++ 实现（~8,000 行），通过 pybind11 暴露 Python 接口，供上层 CSolver / DirectSolver 调用。

### C++ DDAR vs Python DDARN

| 特性 | C++ DDAR (CSolver) | Python DDARN (DirectSolver) |
|------|--------------------|-----------------------------|
| 实现语言 | C++ (pybind11) | Python |
| 求解策略 | 逐层推理 + 代数推理 | 广度优先穷举 |
| 自定义规则 | 支持（pipe format） | 支持（JGEX text format） |
| 性能 | 快（编译优化 -O3） | 较慢 |
| HAGeo 409 基线 | 106/409 (25.9%) | 100/405 (24.7%) |
| 适用场景 | 批量求解、pipeline 评估 | 需要完整 ProofState 的场景 |

### 在项目中的角色

- **Discovery Pipeline**: CSolver 用于 subsumption testing（规则归约阶段）
- **评估脚本**: CSolver 用于 HAGeo/JGEX benchmark 评估
- **Agent 系统**: LMAgent/VLMAgent 使用 DDARN 进行推理

---

## 2. 目录结构

```
src/newclid/DDAR/
├── CMakeLists.txt          # pybind11 构建配置
├── bindings.cpp            # Python 绑定入口（3 个导出函数）
├── matcher.cpp/hpp         # 定理匹配引擎（自动匹配 + 自定义规则匹配）
├── problem.cpp/hpp         # 问题表示（点、前提、目标）
├── theorem.cpp/hpp         # 定理定义（内置 30+ 条定理）
├── typedef.hpp             # statement_arg 联合类型定义
├── numerical.cpp/hpp       # 数值验证工具
├── build/                  # 编译产物（.so 文件）
├── type/                   # 几何基元类型
│   ├── point.hpp           #   Point — 二维点
│   ├── rational.hpp        #   Rational — 精确有理数
│   ├── dist.hpp            #   Dist — 两点距离
│   ├── angle.hpp           #   Angle — 两斜率夹角
│   ├── slope.hpp           #   Slope — 直线斜率
│   ├── dist_log.hpp        #   DistLog — 距离对数
│   ├── triangle.hpp        #   Triangle — 三角形
│   ├── point_num.hpp       #   PointNum — 数值点
│   └── object.hpp          #   Object — 等价类对象
├── predicate/              # 24 个几何谓词
│   ├── statement.hpp       #   Statement 抽象基类
│   ├── coll.hpp            #   Coll — 共线
│   ├── cong.hpp            #   Cong — 全等（等距）
│   ├── para.hpp            #   Para — 平行
│   ├── perp.hpp            #   Perp — 垂直
│   ├── cyclic.hpp          #   Cyclic — 四点共圆
│   ├── eqangle.hpp         #   EqAngle — 等角
│   ├── eqratio.hpp         #   EqRatio — 等比
│   ├── midpoint.hpp        #   Midp — 中点
│   ├── ... (共 24 个)
│   └── sameclock.hpp       #   SameClock — 同向
├── ar/                     # 代数推理系统
│   ├── term.hpp            #   Term — 代数项（系数 × 变量）
│   ├── term_arg.hpp        #   TermArg — 项参数（距离/斜率/角度）
│   ├── equation.hpp        #   Equation — 线性方程
│   ├── equation_index.hpp  #   EquationIndex — 方程索引
│   ├── linear_combination.hpp  # LinearCombination — 项的线性组合
│   ├── linear_system.hpp   #   LinearSystem — 线性方程组（高斯消元）
│   └── reduced_equation.hpp #  ReducedEquation — 化简后的方程
└── solver/                 # 求解器核心
    ├── ddar.hpp            #   DDARSolver — 主求解器
    ├── proof.hpp           #   Proof — 证明状态追踪
    ├── application.hpp     #   Application — 定理应用实例
    └── object_table.hpp    #   ObjectTable — 符号表（等价类管理）
```

---

## 3. 架构与数据流

### 核心组件关系

```
Python 层                    C++ 层
─────────                    ──────
CSolver ──pybind11──→ bindings.cpp
                              │
                              ▼
                          Problem        ← 加载点、前提、目标
                              │
                              ▼
                          Matcher        ← 枚举几何配置，生成 Theorem 实例
                              │
                              ▼
                        DDARSolver       ← 逐层推理主循环
                         ├── Application ← 每条定理的应用实例
                         ├── Proof       ← 每条命题的证明状态
                         ├── LinearSystem × 3 (slope/dist/distlog)
                         └── ObjectTable ← 等价类管理
```

### 求解流程

1. **Problem 加载**: 从 Python 传入 `(points, premises, goals)`，构建 `Problem` 对象
2. **Matcher 匹配**: 遍历所有点的组合，按几何配置（三角形、圆、共线等）生成 `Theorem` 实例，每条 Theorem 包含假设和结论
3. **DDARSolver 逐层推理**:
   - 将所有 Theorem 封装为 `Application`，初始状态为 `PENDING`
   - 每层（level）遍历所有 Application，尝试推进证明
   - 当 Application 的所有假设被证明后，其结论被建立（establish）
   - 新建立的命题会触发代数推理（AR），将几何关系转化为方程加入 LinearSystem
   - LinearSystem 通过高斯消元发现新的等式关系
   - 重复直到目标被证明或达到 `max_level`
4. **结果返回**: 返回 `(solved, dep_graph)` — 是否求解成功 + 依赖图

---

## 4. Type System（`type/`）

7 种几何基元类型，用于构建谓词和方程：

| 类型 | 文件 | 说明 | 示例 |
|------|------|------|------|
| `Point` | `point.hpp` | 二维点，含名称和坐标 | `Point("A", 0.0, 1.0)` |
| `Rational` | `rational.hpp` | 精确有理数（分子/分母） | `Rational(3, 4)` = 3/4 |
| `Dist` | `dist.hpp` | 两点间距离 | `Dist(A, B)` |
| `Angle` | `angle.hpp` | 两条斜率的夹角 | `Angle(Slope(A,B), Slope(C,D))` |
| `Slope` | `slope.hpp` | 直线斜率 | `Slope(A, B)` |
| `DistLog` | `dist_log.hpp` | 距离的对数（用于 log 推理） | `DistLog(Dist(A,B))` |
| `Triangle` | `triangle.hpp` | 三角形（三个点） | `Triangle(A, B, C)` |

### statement_arg 联合类型

`typedef.hpp` 定义了 `statement_arg`，是一个 tagged union，用于统一表示谓词参数：

```cpp
struct statement_arg {
    enum class Type { PointType, BoolType, TriangleType, RationalType, DistType, AngleType, SlopeType };
    // union { Point, bool, Triangle, Rational, Dist, Angle, Slope }
};
```

支持 `==` 和 `<` 比较，用于谓词的规范化和去重。

---

## 5. Predicate System（`predicate/`）

24 个几何谓词，全部继承自 `Statement` 抽象基类。

### Statement 基类接口

```cpp
class Statement {
    virtual string name() const = 0;              // 谓词名称（如 "cong"）
    virtual vector<Point> points() const = 0;     // 涉及的点
    virtual unique_ptr<Statement> normalize() const = 0;  // 规范化（参数排序）
    virtual bool check_nondegen() const = 0;      // 非退化检查
    virtual bool check_equations() const = 0;     // 数值验证
    virtual unique_ptr<Statement> clone() const = 0;
    virtual string to_string() const;             // 字符串表示
    virtual vector<string> to_tokens() const;     // token 化

    // 转化为代数方程（供 AR 系统使用）
    virtual vector<unique_ptr<Equation>> as_equation_slope(bool exp) const;
    virtual vector<unique_ptr<Equation>> as_equation_dist(bool exp) const;
    virtual vector<unique_ptr<Equation>> as_equation_distlog(bool exp) const;
};
```

### 谓词分类表

#### 共线性与平行

| 谓词 | 参数 | 含义 |
|------|------|------|
| `coll` | A B C | A, B, C 三点共线 |
| `ncoll` | A B C | A, B, C 三点不共线 |
| `para` | A B C D | AB ∥ CD |
| `npara` | A B C D | AB 不平行 CD |
| `perp` | A B C D | AB ⊥ CD |

#### 全等与等量

| 谓词 | 参数 | 含义 |
|------|------|------|
| `cong` | A B C D | AB = CD（等距） |
| `eqangle` | A B C D E F G H | ∠(AB,CD) = ∠(EF,GH) |
| `eqratio` | A B C D E F G H | AB/CD = EF/GH |
| `eqpoint` | A B | A 与 B 是同一点 |

#### 圆与共圆

| 谓词 | 参数 | 含义 |
|------|------|------|
| `cyclic` | A B C D | A, B, C, D 四点共圆 |
| `circumcenter` | O A B C | O 是 △ABC 的外心 |
| `thales` | A B C D E | Thales 配置 |
| `secant` | A B C D E | 割线配置 |

#### 特殊配置

| 谓词 | 参数 | 含义 |
|------|------|------|
| `midp` | M A B | M 是 AB 的中点 |
| `orthocenter` | H A B C | H 是 △ABC 的垂心 |
| `pappus` | A B C D E F | Pappus 定理配置 |
| `simtri` | A B C D E F | △ABC ∼ △DEF（相似） |
| `contri` | A B C D E F | △ABC ≅ △DEF（全等） |

#### 常量与方向

| 谓词 | 参数 | 含义 |
|------|------|------|
| `aconst` | A B C D v | ∠(AB,CD) = v（角度常量） |
| `rconst` | A B C D v | AB/CD = v（比值常量） |
| `constline` | A B v | 直线 AB 的斜率为常量 v |
| `sameside` | A B C D | A, B 在直线 CD 同侧 |
| `nsameside` | A B C D | A, B 在直线 CD 异侧 |
| `sameclock` | A B C D E F | △ABC 与 △DEF 同向 |

---

## 6. Theorem System（`theorem.hpp`）

### 内置定理

Theorem 类表示一条推理规则，包含假设（hypotheses）和结论（conclusions）。内置定理由 Matcher 根据几何配置自动实例化：

| 编号 | 静态方法 | 几何含义 |
|------|----------|----------|
| r03 | `cyclic_properties` | 四点共圆 → 等角关系 |
| r04 | `cyclic_of_equal_angles` | 等角 → 四点共圆 |
| r07 | `thales_eqratio_of_para_with_common_point` | 平行 + 共点 → 等比（Thales） |
| r11 | `triangle_bisector_of_eqratio` | 等比 → 角平分线 |
| r12 | `triangle_bisector_of_equal_angles` | 等角 → 角平分线 |
| r19 | `hypotenuse_is_diameter` | 中点 + 直角 → 斜边为直径 |
| r27 | `thales_para_of_eqratio_with_common_point` | 等比 + 共点 → 平行 |
| r28 | `coll_of_para` | 平行 + 共点 → 共线 |
| r34/r35 | `similar_triangles_of_aa` | AA 相似判定 |
| r41 | `thales_para_of_eqratio` | Thales: 等比 → 平行 |
| r42 | `thales_eqratio_of_para` | Thales: 平行 → 等比 |
| r43 | `orthocenter` | 垂心性质 |
| r44 | `pappus` | Pappus 定理 |
| r46 | `incenter` | 内心性质 |
| r49 | `cong_of_circumcenter_of_cyclic` | 外心 + 共圆 → 等距 |
| r50 | `center_of_cyclic_of_cong_of_cong` | 等距 → 共圆圆心 |
| r51 | `midpoint_ratio_dist` | 中点 → 距离比 |
| r52/r53 | `similar_triangles_properties` | 相似三角形性质（等角 + 等比） |
| r54 | `midpoint_of_coll_cong` | 共线 + 等距 → 中点 |
| r56 | `coll_cong_of_midpoint` | 中点 → 共线 + 等距 |
| r60/r61 | `similar_triangles_of_sss` | SSS 相似判定 |
| r62/r63 | `similar_triangles_of_sas` | SAS 相似判定 |
| r72 | `cong_of_circumcenter` | 外心 → 等距 |
| r73 | `circumcenter_of_cong` | 等距 → 外心 |
| r82 | `para_of_coll` | 共线 → 平行 |
| r101/r102 | `congruent_triangles_of_cong` | 等距 → 全等三角形 |
| r103/r104 | `congruent_triangles_properties` | 全等三角形性质 |
| r105 | `eqratio_of_coll` | 共线 → 等比 |
| r106 | `definition_of_secant` | 割线定义 |
| r107 | `eqpoints_of_same_intersections` | 同交点 → 等点 |
| r108 | `cong_of_eqpoints` | 等点 → 等距 |

### 自定义定理（Custom Rules）

通过 pipe format 传入自定义规则，由 `bindings.cpp` 中的 `parse_custom_theorems()` 解析：

```
格式: rule_name|premise1 arg1 arg2...,premise2 arg1 arg2...|conclusion1 arg1 arg2...,conclusion2 arg1 arg2...
示例: r54|cong M A M B,coll M A B|midp M A B
```

约束：
- 变量名为单个小写字母（a-h），最多 8 个变量
- 谓词名必须是已注册的 24 个谓词之一
- 通过 `Problem::create_statement()` 将字符串转为 Statement 对象

---

## 7. Algebraic Reasoning（`ar/`）

代数推理（AR）是 DDAR 的核心创新之一，将几何关系转化为代数方程，通过线性系统求解发现隐含关系。

### 层次结构

```
TermArg          — 原子变量（距离/斜率/角度标识符）
  ↓
Term             — 代数项 = 系数 × 变量的乘积（如 2·d(A,B)·s(C,D)）
  ↓
LinearCombination — 项的线性组合（如 d(A,B) - d(C,D)）
  ↓
Equation         — 线性方程（LinearCombination = 0）
  ↓
ReducedEquation  — 经 LinearSystem 化简后的方程
  ↓
LinearSystem     — 线性方程组（增量式高斯消元）
```

### 三套线性系统

DDARSolver 维护三套独立的 LinearSystem：

| 系统 | 变量类型 | 用途 | 启用条件 |
|------|----------|------|----------|
| `_system_slope` | Slope | 角度/平行/垂直关系推理 | 始终启用 |
| `_system_dist` | Dist | 距离/全等/等比关系推理 | 始终启用 |
| `_system_distlog` | DistLog | 距离对数推理（用于乘除关系） | `log_enabled=True` |

### 工作流程

1. **方程生成**: 当一条 Statement 被证明时，调用 `as_equation_slope()` / `as_equation_dist()` / `as_equation_distlog()` 生成对应方程
2. **方程化简**: `ReducedEquation` 对方程进行化简，消去已知变量
3. **系统更新**: 化简后的方程加入 `LinearSystem`，触发增量式高斯消元
4. **新发现**: 如果消元过程中某个方程被完全化简（remainder 为空），说明发现了新的等式关系，对应的 Proof 被标记为已证明

### Proof 证明状态

```cpp
enum class ProofState {
    NOT_PROVED,            // 未证明
    PROVED_BY_ASSUMPTION,  // 前提假设
    PROVED_NUMERICALLY,    // 数值验证通过
    PROVED_TRIVIAL,        // 平凡命题
    PROVED_AR_DIST,        // 由距离代数推理证明
    PROVED_AR_SLOPE,       // 由斜率代数推理证明
    PROVED_AR_DISTLOG,     // 由距离对数代数推理证明
    PROVED_BY_THEOREM,     // 由定理推导证明
    PROVED_BY_DOUBLEPOINT, // 由等点替换证明
};
```

---

## 8. Solver 核心算法（`solver/`）

### DDARSolver 主循环

```
DDARSolver::run(max_levels):
    for level in 0..max_levels:
        changed = run_level(max_point_at_level)
        if solved: return true
        if not changed: return false   // 不动点，无法继续推理
    return false
```

```
DDARSolver::run_level(max_pt):
    for each application in _applications:
        if application.max_point <= max_pt:
            advance_theorem(application)
            // 尝试推进该定理的证明
```

```
advance_theorem(application):
    for each hypothesis in application.hypotheses:
        if not hypothesis.is_proved():
            return  // 假设未满足，跳过
    // 所有假设已满足 → 建立结论
    for each conclusion in application.conclusions:
        establish_statement(conclusion, theorem_id)
        add_established_equations(conclusion)  // 触发 AR
```

### Application 生命周期

```
PENDING → (所有假设被证明) → PROVED
PENDING → (数值检查失败)   → DISCARDED
```

每个 Application 封装一条 Theorem 的具体实例化（变量已绑定到具体的点）。

### ObjectTable（等价类管理）

`ObjectTable` 维护符号对象的等价类。当 `eqpoint A B` 被证明时，A 和 B 被合并到同一等价类，后续推理中 A 和 B 可互换使用。

### log_enabled / exp_enabled 的作用

- `log_enabled=True`: 启用 `_system_distlog`（距离对数线性系统），使引擎能推理涉及距离乘除的关系（如 `eqratio`）。不开启时，部分 eqratio 关系无法通过 AR 发现。
- `exp_enabled=True`: 在 `as_equation_dist()` / `as_equation_distlog()` 中启用指数展开，允许从对数域回到距离域推理。

**铁律**: 除非明确需要对比实验，否则必须同时开启 `using_log=True, using_exp=True`。

---

## 9. Matcher（`matcher.hpp/cpp`）

Matcher 在构造时完成所有定理匹配，结果存放在 `_theorems` 中。

### 匹配策略

Matcher 按几何配置分类，枚举所有可能的点组合：

| 方法 | 枚举对象 | 生成的定理 |
|------|----------|-----------|
| `match_similar_triangles()` | 所有三角形对 | r34/r35, r52/r53, r60-r63, r101-r104 |
| `match_circles()` | 所有共圆四元组 | r03, r04, r49, r50 |
| `match_between()` | 所有共线三元组 | r07, r27, r28, r54, r56, r82, r105 |
| `match_equal_angles()` | 所有角度对 | r11, r12, r46 |
| `match_orthocenters()` | 所有三角形 | r43 |
| `match_perps_paras()` | 所有线段对 | r19, r41, r42 |

每个 `match_*` 方法内部调用对应的 `on_*` 回调，生成具体的 Theorem 实例并进行数值验证（`check_numerically()`），只有数值验证通过的定理才会被保留。

### 自定义规则匹配

自定义规则通过 `DDARSolver::add_custom_theorems()` 添加，不经过 Matcher，直接作为 Application 插入求解器。匹配过程在 `advance_theorem` 中完成。

---

## 10. Python API

### CSolver（C++ DDAR 封装）

位于 `src/newclid/api.py`，是 C++ DDAR 引擎的 Python 封装。

#### 构造方式

**方式 1: 从 JGEX 问题文本构造**
```python
solver = CSolver(
    problem="a b c = triangle a b c; d = midpoint d b c ? cong a d b d",
    problem_name="example",
    seed=42,
    using_log=True,
    using_exp=True
)
```

**方式 2: 从 GeometricSolver 构造**
```python
builder = GeometricSolverBuilder(seed=42)
builder.load_problem_from_txt(problem_txt)
geo_solver = builder.build()
solver = CSolver(solver=geo_solver, using_log=True, using_exp=True)
```

**方式 3: 从结构化数据直接构造**（不需要 GeometricSolver）
```python
solver = CSolver(
    points=[("a", 0.0, 0.0), ("b", 1.0, 0.0), ("c", 0.5, 1.0)],
    premises=[("cong", ["a", "b", "b", "c"])],
    goals=[("para", ["a", "b", "c", "d"])],
    problem_name="example",
    using_log=True,
    using_exp=True
)
```

#### 核心方法

```python
# 求解
solved: bool = solver.run(
    max_level=500,           # 最大推理层数
    save_path=None,          # 可选：保存依赖图到文件
    custom_rules=["r54|cong M A M B,coll M A B|midp M A B"]  # 可选：额外自定义规则
)

# 获取所有可推导的目标
goals: List[str] = solver.possible_goals()

# 打印问题信息
solver.print_info()
```

#### 数据格式

- `points`: `List[Tuple[str, float, float]]` — (名称, x, y)
- `premises` / `goals`: `List[Tuple[str, List[str]]]` — (谓词名, [参数列表])
- `custom_rules`: `List[str]` — pipe format 字符串列表

### DirectSolver（Python DDARN 封装）

位于 `src/newclid/api.py`，封装 Python 实现的 DDARN 广度优先求解器。

```python
solver = DirectSolver(
    points=[("a", 0.0, 0.0), ...],
    premises=[("cong", ["a", "b", "b", "c"]), ...],
    goal=("para", ["a", "b", "c", "d"]),
    problem_name="example",
    seed=42,
    custom_rules=["rule text..."]  # 可选
)
solved: bool = solver.run(timeout=3600)
solver.write_proof_steps(out_file=Path("proof.txt"))
```

### pybind11 绑定接口

`bindings.cpp` 导出 3 个函数：

```python
from newclid.DDAR.build import DDAR

# 标准求解
result = DDAR.run_ddar(
    problem_name: str,
    points: List[Tuple[str, float, float]],
    premises: List[Tuple[str, List[str]]],
    goals: List[Tuple[str, List[str]]],
    max_level: int,
    using_log: bool,
    using_exp: bool
)
# 返回: Tuple[bool, DepGraph]
#   bool — 是否求解成功
#   DepGraph — List[Tuple[statement_tokens, List[dep_tokens], rule_name]]

# 带自定义规则求解
result = DDAR.run_ddar_with_custom_theorems(
    problem_name, points, premises, goals,
    custom_rules: List[str],  # pipe format
    max_level, using_log, using_exp
)

# 获取所有可推导目标
goals = DDAR.get_possible_goals(
    problem_name: str,
    points: List[Tuple[str, float, float]],
    premises: List[Tuple[str, List[str]]]
)
# 返回: List[str] — 去重排序后的目标字符串列表
```

---

## 11. 构建指南

### 依赖

- C++20 编译器（GCC 10+ / Clang 12+）
- pybind11（通过 `pip install pybind11` 或系统包管理器）
- CMake 3.14+

### 编译

```bash
cd src/newclid/DDAR
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

编译产物：`build/DDAR.cpython-310-x86_64-linux-gnu.so`

### CMake 配置要点

- C++20 标准（`CMAKE_CXX_STANDARD 20`）
- Release 模式默认开启 `-O3 -march=native -flto`
- 通过 `pybind11_add_module` 构建 Python 扩展模块

---

## 12. 注意事项

### 必须开启 log/exp

所有 CSolver 实例化必须设置 `using_log=True, using_exp=True`，否则 C++ 引擎缺少距离对数推理和指数推理能力，求解率会显著下降。唯一例外是明确需要对比实验。

### DDAR 代码同步规则

`src/newclid/DDAR/` 的权威来源是 GenesisGeo 远端仓库。当本地与远端存在差异时：

```bash
git fetch GenesisGeo
git checkout GenesisGeo/main -- src/newclid/DDAR/
```

### 自定义规则注意事项

- Generative rules（如 `cyclic => eqangle`）可能导致推理爆炸，需要在 pipeline 中过滤
- 变量数量上限为 8 个（a-h）
- 规则中的谓词名必须与 `predicate/` 中的 24 个谓词完全匹配
