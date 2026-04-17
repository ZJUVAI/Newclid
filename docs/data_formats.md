# Data Formats Reference

本文档定义项目中所有核心数据格式的标准规范，供开发时对齐参考。

---

## 1. Synthetic JSONL（合成数据）

**文件位置**: `outputs/datasets/*/geometry_clauses15_samples*.jsonl`
**用途**: Discovery Pipeline 的输入数据，每行一个 JSON 对象。

### Schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `pid` | `str` | 问题唯一标识，格式 `p{seq:06d}`（如 `p000001`） |
| `seed` | `int` | 构造种子，同一 seed 的题目来自相同 construction clauses |
| `n_premises` | `int` | 前提数量 |
| `fl_problem` | `str` | 函数式问题描述（人类可读，pipeline 不使用） |
| `nl_problem` | `str` | 自然语言描述（当前为空） |
| `n_proof_steps` | `int` | 证明步数 |
| `llm_input_renamed` | `str` | JGEX 格式问题（pipeline 主要输入） |
| `llm_output_renamed` | `str` | LLM 生成的证明（含 aux/check/proof 三段） |
| `aux_points` | `list[str]` | 辅助点名列表 |
| `point_coords` | `dict[str, [float, float]]` | 所有点的数值坐标 |

### `fl_problem` 语法

```
a = free a; b = free b; c = free c; e f = square a d e f; j = midpoint j e i ? para b k g l
```

- `;` 分隔构造步骤，`?` 后为目标
- 每步: `新点 = 构造名 参数`

### `llm_input_renamed` 语法

```
<problem> a : ; b : ; c : cong a b b c [000] ; d : perp b c b d [001] ? eqangle a b c d e f g h </problem>
```

- `<problem>...</problem>` 包裹
- `;` 分隔 Clause，每个 Clause: `点名 : 谓词1 [索引] 谓词2 [索引]`
- `[NNN]` 为事实索引，用于证明引用

### `llm_output_renamed` 内部结构

```
<aux> x00 m : midp m d f [008] ; </aux>
<numerical_check> ncoll a j m [009] ; sameside e a m e i j [010] ; </numerical_check>
<proof> coll e i j [014] r56 [004] ; perp a d a f [016] AR [003] [000] ; </proof>
```

| 段 | 说明 |
|----|------|
| `<aux>` | 辅助点构造，格式: `x00 点名 : 构造谓词 [索引] ;` |
| `<numerical_check>` | 数值验证条件（ncoll, sameside 等） |
| `<proof>` | 证明步骤，格式: `结论谓词 [新索引] 规则名 [引用索引] ;` |

---

## 2. Problem JGEX（问题定义）

**代码定义**: `src/newclid/formulations/problem.py` → `ProblemJGEX(NamedTuple)`
**文件位置**: `benchmarks/core/*.txt`（每两行一个问题：名称 + 定义）

### 数据结构

```python
class ProblemJGEX(NamedTuple):
    name: str                              # 问题标识
    constructions: tuple[Clause, ...]      # 构造步骤
    goals: tuple[tuple[str, ...], ...]     # 目标谓词
```

### 文本格式

**简洁格式**（benchmark 标准）:
```
1995USAMOp3
a b c = triangle; o = circumcenter a b c; d = on_line b c, angle_bisector b a c ? coll p c c2
```

**完整格式**（full，点名出现在构造名参数中）:
```
1995USAMOp3
a b c = triangle a b c; o = circumcenter o a b c; d = on_line d b c, angle_bisector d b a c ? coll p c c2
```

### Clause 语法

```
点名1 点名2 = 构造谓词1 参数, 构造谓词2 参数
```

- `=` 或 `:` 分隔点名与构造
- `,` 分隔同一 Clause 内的多个构造约束
- `;` 分隔不同 Clause
- `?` 分隔构造与目标

---

## 3. Rule Text（规则文本）

**代码定义**: `src/newclid/formulations/rule.py` → `Rule(NamedTuple)`
**文件位置**: 多个阶段共用同一格式（见下方"Pipeline 产物"）

### 数据结构

```python
class Rule(NamedTuple):
    descrption: str                            # 规则名/ID
    premises: tuple[tuple[str, ...], ...]      # 前提谓词列表
    conclusions: tuple[tuple[str, ...], ...]   # 结论谓词列表
```

### 文件格式（交替行）

```
r000042
cong a b b c, perp a b c d => para e f g h
r000108
coll a b c, midp d a c => cong a d d c
```

- `rid` 格式: `r` + pid 数字部分（如 pid=`p000042` → rid=`r000042`）
- 子图后缀保留: pid=`p000042_0` → rid=`r000042_0`

- 奇数行: 规则 ID（如 `r0000`）或描述文本
- 偶数行: 规则文本 `前提1, 前提2, ... => 结论1, 结论2`

### 规则语法

```
谓词名 参数1 参数2 ..., 谓词名 参数1 参数2 ... => 谓词名 参数1 参数2 ...
```

- `,` 分隔谓词，`=>` 分隔前提与结论
- 每个谓词: `谓词名 + 空格分隔的参数`（点名或常量如 `3pi/4`, `1/2`）

### 支持的谓词

完整列表见 `src/newclid/proof_scout/extraction/rule_converter.py` → `VALID_PREDICATES`

基础: `coll`, `cong`, `para`, `perp`, `cyclic`, `midp`, `circle`
角/比: `eqangle`(8参), `eqratio`(8参), `eqangle3`(6参), `eqratio3`(6参), `rconst`, `aconst`
三角形: `simtri`, `simtrir`, `contri`, `contrir`
辅助: `sameclock`, `sameside`, `ncoll`, `npara`, `nsameside`

---

## 4. Definition Text（构造定义）

**代码定义**: `src/newclid/formulations/definition.py` → `DefinitionJGEX(NamedTuple)`
**文件位置**: `src/newclid/default_configs/defs.txt`

### 格式（每个定义 6 行）

```
angle_bisector x a b c          ← Line 1: 声明（构造名 + 参数）
x : a b c x                     ← Line 2: 依赖关系
a b c = ncoll a b c             ← Line 3: 前置条件
x : eqangle b a b x b x b c    ← Line 4: 基本事实
bisect a b c                    ← Line 5: 数值约束
                                ← Line 6: 空行
```

---

## 5. Pipeline 中间产物

所有中间 JSON 遵循统一框架: **统计摘要 + 成功条目列表 + 失败/跳过条目列表**。
保存位置: 实验目录下 `intermediates/` 或 `reduction/`。

| 阶段 | 文件名 | 统计字段 | 成功条目 | 失败/跳过条目 |
|------|--------|---------|---------|--------------|
| Step 1a | `step1a_aux_filter.json` | total/kept/dropped | `kept_records` (pid, aux_points, fl_problem) | `dropped_records` |
| Step 1a+ | `step1a_plus_predicate_filter.json` | input/kept/dropped | `kept_records` | `dropped_records` + `skip_predicates` |
| Step 1c | `step1c_prune.json` | total/success/failed | pruned 图 (nodes/edges) | `failed_records` (含失败原因) |
| Step 1d | `step1d_propositions.json` | total/success/skipped | 命题列表 | `fail_multi_concl_records` |
| Step 1e | `step1e_rules_stats.json` | input_rules_raw/output_rules_deduped/skipped_rules | `entries` (rid/pid/rule) | `skipped_entries` + `dedup_groups` |
| Stage 2 | `discovered_rules.txt` | — | 验证通过的规则 (Rule Text 格式) | `discovered_rules_skipped.txt` |
| Reduction | `reduction_stats.json` | original/ddar_covered/basis/eliminated/reduction_rate/elapsed_seconds | — | — |
| Reduction | `basis_rules.txt` | — | 最终基底规则集 (Rule Text 格式) | — |

---

## 5.1 Divide-and-Conquer Reduction Output

Part 4 的 Divide-and-Conquer 规约阶段输出目录结构：

```
part4/
  divide_conquer_reduction/
    phase1_chunks/
      chunk_0000.json   # 每个初始 chunk 的规约结果
      chunk_0001.json
      ...
    phase2_merges/
      merge_0001.json   # 每次两两合并的详细统计
      merge_0002.json
      ...
    final_stats.json    # 最终统计汇总
```

### `final_stats.json` Schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `input_count` | int | 输入规则总数 |
| `basis_count` | int | 最终基底规则数 |
| `eliminated_count` | int | 被淘汰规则数 |
| `reduction_rate` | float | 淘汰率 |
| `phase1.n_chunks` | int | Phase 1 分块数 |
| `phase1.chunk_size` | int | 每块大小 |
| `phase1.elapsed_seconds` | float | Phase 1 耗时 |
| `phase2.n_merges` | int | Phase 2 合并次数 |
| `phase2.elapsed_seconds` | float | Phase 2 耗时 |
| `n_subsumption_tests` | int | 总 subsumption 测试次数 |
| `elapsed_seconds` | float | 总耗时 |

---

## 6. 冗余分析与统一建议

### 6.1 `fl_problem` vs `llm_input_renamed`

同一问题的两种文本表示:

| 字段 | 语法风格 | Pipeline 使用 | 用途 |
|------|---------|--------------|------|
| `fl_problem` | 函数式 (`a = free a; e f = square a d e f`) | ✗ | 人类阅读、调试 |
| `llm_input_renamed` | JGEX 带索引 (`a : ; e : perp a d d e [000]`) | ✓ | Pipeline 解析输入 |

**建议**: 保留两者，明确标注 `fl_problem` 仅供调试，不作为 pipeline 数据源。

### 6.2 规则文件命名

以下文件格式完全相同（Rule Text 格式），仅代表 pipeline 不同阶段:

```
*_pruned_rules.txt       → Step 1e 输出（提取+去重后）
discovered_rules.txt     → Stage 2 输出（谓词验证后）
basis_rules.txt          → Reduction 输出（规约后最终集）
```

**建议**: 无需统一，文档中定义一次 Rule Text 格式，各阶段引用。

### 6.3 点名大小写不一致

| 来源 | 点名风格 | 示例 |
|------|---------|------|
| 默认规则 `rules.txt` | 大写 | `simtri A B C P Q R => eqangle B A B C Q P Q R` |
| 发现规则 | 小写 | `cong a b b c, perp a b c d => para e f g h` |

**建议**: 长期统一为小写。短期可在 `RuleConverter` 或规则加载阶段自动转换。
