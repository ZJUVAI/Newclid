# Benchmarks

Geometric theorem proving benchmark problems for GenesisGeo evaluation.

## Directory Structure

```
benchmarks/
├── core/           # 核心评估集（论文基准）
├── extended/       # 扩展题目集
├── coords/         # 带数值坐标版本（CSolver/Yuclid 使用）
└── dev/            # 开发测试用
```

## core/

论文中使用的核心基准集。

| 文件 | 题目数 | 格式 | 说明 |
|------|--------|------|------|
| `imo_ag_30.txt` | 30 | JGEX | AlphaGeometry 论文 30 道 IMO 题 |
| `hageo_409.txt` | 409 | JGEX-short | 高考/竞赛几何题（简化格式） |
| `hageo_409_full.txt` | 409 | JGEX | 高考/竞赛几何题（完整格式） |

## extended/

扩展评估集，用于更全面的测试。

| 文件 | 题目数 | 格式 | 说明 |
|------|--------|------|------|
| `imo_95.txt` | 95 | JGEX | 95 道 IMO 题（含 imo_ag_30） |
| `imo_not_ag.txt` | ~6 | JGEX | AG 无法解决的 IMO 题 |
| `jgex_ag_231.txt` | 231 | JGEX | JGEX 系统题目集 |
| `larger_imo_eval.txt` | ~170 | JGEX | 扩展 IMO 评估集 |
| `new_benchmark_50.txt` | 50 | JGEX | 新增题目 |
| `ag4masses_problems.txt` | ~20 | JGEX | AG4Masses 论文题目 |

## coords/

带数值坐标的重建版本，供 CSolver 和 Yuclid 直接使用。

| 文件 | 原文件名 | 说明 |
|------|----------|------|
| `hageo_409_coords.txt` | hageo_409_rebuild_with_coordinates.txt | HAGeo 409 带坐标 |
| `imo_30_coords.txt` | imo_30_rebuild_with_coordinates.txt | IMO 30 带坐标 |
| `imo_95_coords.txt` | imo_95_rebuild_with_coordinates.txt | IMO 95 带坐标 |

## dev/

开发和调试用的小规模题目集。

| 文件 | 说明 |
|------|------|
| `dev_imo.txt` | 开发测试用 IMO 题 |
| `dev_jgex.txt` | 开发测试用 JGEX 题 |
| `examples.txt` | 示例题目 |
| `new_problems.txt` | 新问题 |
| `testing_minimal_rules.txt` | 规则测试用题 |

## 辅助点数据

辅助点文件（~32MB）已移至 `datasets/aux_points/`，包含：
- `hageo_409_aux_coords.txt` / `hageo_409_aux_overlap_coords.txt`
- `imo_30_aux_coords.txt` / `imo_30_aux_overlap_coords.txt`
- `imo_95_aux_coords.txt` / `imo_95_aux_overlap_coords.txt`

## 文件格式

### JGEX 格式
```
problem_name
a : ; b : ; c : cong a b b c [000] ; d : perp b c b d [001] ? eqangle a b c d e f g h
```
两行一组：题目名 + 构造与目标。构造在 `?` 之前，目标在 `?` 之后。

### JGEX-short 格式
简化的 JGEX，省略部分参数标记。

### Coords 格式
```
Problem Name:
<name>
Points:
a:x1,y1
b:x2,y2
Premises:
predicate arg1 arg2 ...
Goal:
predicate arg1 arg2 ...
```

## 数据来源

- IMO 题目：International Mathematical Olympiad 历年几何题
- HAGeo：高考/竞赛几何题集
- JGEX：Java Geometry Expert 系统题库
- AG4Masses：AlphaGeometry for Masses 论文
