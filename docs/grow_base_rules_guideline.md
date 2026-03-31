# 基础规则增长指南

本文档记录了几何推理中的基础规则和高级规则，用于指导规则提取和验证工作。

## 规则目录

| 规则编号 | 规则名称 | 规则含义 | 分组 | 转写成证明题 |
|---------|---------|---------|------|-------------|
| 03 | cyclic_properties | 同弧所对的圆周角相等。 | 基础规则 | - |
| 04 | cyclic_of_equal_angles | 圆周角定理逆定理（如果两个相等的角对着同一条线段，且顶点在同侧，则这四个点共圆）。 | 高级规则 | 已知线段$AB$，在其同侧有两点$C$和$D$，且满足$\angle ACB = \angle ADB$。请证明点$A, B, C, D$四点共圆。 |
| 07 | thales_eqratio_of_para_with_common_point | 泰勒斯定理（平行线分线段成比例定理）：如果一组平行线与两条直线相交，则在两条直线上截得的对应线段成比例。 | 高级规则 | 已知在$\triangle ABC$中，直线$l$平行于底边$BC$，且分别交射线$AB, AC$于点$D, E$。请证明$\frac{AD}{AB} = \frac{AE}{AC}$ 且 $\frac{AD}{DB} = \frac{AE}{EC}$。 |
| 11 | triangle_bisector_of_eqratio | 三角形角平分线定理逆定理：如果三角形一边上的一点将该边分成的两段之比等于相邻两边之比，则该点与对角的连线平分该角。 | 高级规则 | 在$\triangle ABC$中，点$D$在边$BC$上，已知满足比例关系 $\frac{BD}{DC} = \frac{AB}{AC}$。请证明射线$AD$是$\angle BAC$的角平分线。 |
| 12 | triangle_bisector_of_equal_angles | 三角形角平分线定理：三角形的角平分线分对边所成的两条线段与这个角的两边对应成比例。 | 高级规则 | 在$\triangle ABC$中，$AD$是$\angle BAC$的平分线，交边$BC$于点$D$。请证明 $\frac{BD}{DC} = \frac{AB}{AC}$。 |
| 19 | hypotenuse_is_diameter | 直角三角形斜边上的中线等于斜边的一半（或：直角三角形斜边的中点即为其外接圆的圆心）。 | 高级规则 | 已知在$Rt\triangle ABC$中，$\angle C = 90^\circ$，点$M$是斜边$AB$的中点。请证明$CM = \frac{1}{2}AB$。 |
| 27 | thales_para_of_eqratio_with_common_point | 泰勒斯定理逆定理：如果一条直线截三角形的两边所得的对应线段成比例，且截点在顶点的同侧，则这条直线平行于三角形的第三边。 | 高级规则 | 已知在$\triangle ABC$中，点$D, E$分别在射线$AB, AC$上，且满足线段比例 $\frac{AD}{AB} = \frac{AE}{AC}$。请证明直线$DE \parallel BC$。 |
| 28 | coll_of_para | 平行公理推论：过同一点且互相平行的线段共线。 | 基础规则 | - |
| 82 | para_of_coll | 共线点构成的线段互相平行（斜率相等）。 | 基础规则 | - |
| 34 | similar_triangles_of_aa | 相似三角形判定（AA）：两角分别对应相等的两个三角形相似。 | 基础规则 | - |
| 35 | similar_triangles_of_aa | 相似三角形判定（AA）：两角分别对应相等的两个三角形相似。 | 基础规则 | - |
| 41 | thales_para_of_eqratio | 泰勒斯定理推论：基于线段比例相等判定直线平行。 | 高级规则 | 已知直线$m$上有三点$A, B, C$，直线$n$上有三点$D, E, F$。已知直线$BE \parallel CF$，且满足比例关系 $\frac{AB}{AC} = \frac{DE}{DF}$，且点$A, D$分别在连线$BE$的同侧。请证明直线$AD \parallel BE$。 |
| 42 | thales_eqratio_of_para | 平行线分线段成比例定理的延伸性质：平行线截割产生的多组线段比例均相等。 | 高级规则 | 已知三条互相平行的直线$l_1 \parallel l_2 \parallel l_3$分别交直线$m$于点$A, B, C$，交直线$n$于点$D, E, F$。请证明 $\frac{AB}{BC} = \frac{DE}{EF}$ 且 $\frac{AB}{AC} = \frac{DE}{DF}$。 |
| 43 | orthocenter | 垂心定理：三角形的三条高交于一点。已知两高交于一点，过此点与第三顶点的连线必垂直于第三边。 | 高级规则 | 在$\triangle ABC$中，$BE \perp AC$于点$E$，$CF \perp AB$于点$F$，$BE$与$CF$相交于点$H$。连结$AH$并延长交$BC$于点$D$。请证明$AD \perp BC$。 |
| 44 | pappus | 帕普斯定理：如果两组点分别共线，则它们的交叉连线的交点也共线。 | 高级规则 | 已知点$A, B, C$在直线$l_1$上，点$D, E, F$在直线$l_2$上。设线段$AE$与$BD$交于点$X$，线段$AF$与$CD$交于点$Y$，线段$BF$与$CE$交于点$Z$。请证明点$X, Y, Z$三点共线。 |
| 46 | incenter | 内心定理：三角形的三条角平分线交于一点。 | 高级规则 | 在$\triangle ABC$中，$\angle ABC$和$\angle ACB$的平分线相交于点$I$。连结$AI$。请证明射线$AI$平分$\angle BAC$。 |
| 49 | cong_of_circumcenter_of_cyclic | 共圆性质：圆心到圆上任意一点的距离都相等。 | 基础规则 | - |
| 50 | center_of_cyclic_of_cong_of_cong | 圆心判定定理：到两条不平行弦的端点距离分别相等的点即为该圆的圆心。 | 高级规则 | 已知点$A, B, C, D$共圆，且线段$AB$与$CD$不平行。空间中存在一点$P$，满足$PA=PB$且$PC=PD$。请证明点$P$是该外接圆的圆心（即证明$PA=PB=PC=PD$）。 |
| 51 | midpoint_ratio_dist | 中点比例性质：中点将线段平分为两半，每段长度等于总长度的一半。 | 基础规则 | - |
| 52 | similar_triangles_properties | 相似三角形性质：相似三角形对应边成比例，对应角相等。 | 基础规则 | - |
| 53 | similar_triangles_properties | 相似三角形性质：相似三角形对应边成比例，对应角相等。 | 基础规则 | - |
| 54 | midpoint_of_coll_cong | 中点定义：如果三点共线且中间点到两端点距离相等，则该点为中点。 | 基础规则 | - |
| 56 | coll_cong_of_midpoint | 中点性质：中点一定与线段两端点共线，且到两端点距离相等。 | 基础规则 | - |
| 60 | similar_triangles_of_sss | 相似三角形判定（SSS）：三边对应成比例的两个三角形相似。 | 基础规则 | - |
| 61 | similar_triangles_of_sss | 相似三角形判定（SSS）：三边对应成比例的两个三角形相似。 | 基础规则 | - |
| 62 | similar_triangles_of_sas | 相似三角形判定（SAS）：两边对应成比例且夹角相等的两个三角形相似。 | 基础规则 | - |
| 63 | similar_triangles_of_sas | 相似三角形判定（SAS）：两边对应成比例且夹角相等的两个三角形相似。 | 基础规则 | - |
| 72 | cong_of_circumcenter | 外心判定：到一个三角形三个顶点距离相等的点是该三角形的外接圆圆心。 | 基础规则 | - |
| 73 | circumcenter_of_cong | 外心性质：三角形的外接圆圆心到三个顶点的距离必然相等。 | 基础规则 | - |
| 101 | congruent_triangles_of_cong | 全等三角形判定：有一对对应边相等的相似三角形是全等三角形。 | 基础规则 | - |
| 102 | congruent_triangles_of_cong | 全等三角形判定：有一对对应边相等的相似三角形是全等三角形。 | 基础规则 | - |
| 103 | congruent_triangles_properties | 全等三角形性质：全等三角形的所有对应边相等，且互为相似三角形。 | 基础规则 | - |
| 104 | congruent_triangles_properties | 全等三角形性质：全等三角形的所有对应边相等，且互为相似三角形。 | 基础规则 | - |
| 105 | eqratio_of_coll | 共线点比例传递性：如果共线点组成的线段中存在一组对应成比例，则其他组合的线段也成比例。 | 基础规则 | - |
| 106 | definition_of_secant | 割线定义：基于点共线和等距属性的割线几何定义。 | 基础规则 | - |
| 107 | eqpoints_of_same_intersections | 唯一交点定理：两条不重合的直线最多只能有一个交点。 | 基础规则 | - |
| 108 | cong_of_eqpoints | 重合点性质：重合的两点到空间内任意第三点的距离相等。 | 基础规则 | - |

---

## 高级定理构造探索

### 探索背景与目标

**问题**: 当前从 weak10k 数据集提取的 35 条规则（max_premises=7）都是基础组合规则，未能提取出上述高级定理。

**探索目标**: 反向思考——如果希望用现有的规则提取 pipeline 获得高级定理，应该构造什么样的问题？

**核心问题**:
1. 高级定理的 DSL 格式应该是什么？
2. 如何处理辅助点（aux_point）？
3. 从 llm_input_renamed 和 aux_point 出发，如何回推构造合适的问题？

### 数据格式分析

#### llm_input_renamed 格式

这是 pipeline 的主要输入格式，语法如下：

```
a : ; b : ; c : cong a b b c [000] ; d : perp b c b d [001] ? eqangle a b c d e f g h
```

**格式说明**:
- 每个 Clause 用 `;` 分隔
- Clause 格式: `点名 : 谓词1 参数 [索引] 谓词2 参数 [索引]`
- `[NNN]` 为事实索引，用于证明引用
- `?` 后为目标谓词

**示例**（来自实际数据）:
```
a : ; b : ; c : ; d : ; e : eqangle b c c d c d c e [000] cong b c c e [001] ;
f : eqangle b c c d c d c f [002] cong b c c f [003] ;
g : eqangle b e e g e g e f [004] eqangle b f f g f g e f [005] ;
? cong b h g h
```

#### aux_points 字段

辅助点列表，如 `["m", "n"]`，对应 llm_output_renamed 中的 `<aux>` 段：

```
<aux> x00 m : midp m d f [008] ; </aux>
```

**辅助点构造格式**: `x00 点名 : 构造谓词 参数 [索引] ;`

### 探索脚本设计

为了系统地探索如何构造高级定理问题，我们创建了三个轻量级脚本，放在 `tmp/` 目录下。

#### 脚本 1: analyze_existing_problems.py

**设计目的**:
- 统计现有数据中 aux_points 的使用频率
- 分析常见的辅助点构造模式
- 为构造高级定理提供参考

**具体操作**:
1. 读取 JSONL 文件（默认前 100 个样本）
2. 统计使用辅助点的问题比例
3. 统计辅助点数量分布（1个、2个、3个等）
4. 提取并展示辅助点构造示例（从 `<aux>` 段）

**运行方式**:
```bash
cd /C20545/home/duzhengtong/GeoDiscovery
python tmp/analyze_existing_problems.py
```

**预期输出**:
- 辅助点使用统计（百分比、数量分布）
- 前 10 个辅助点构造示例

#### 脚本 2: construct_theorem_dsl.py

**设计目的**:
- 为高级定理手工构造 DSL 表示
- 识别每个定理所需的辅助点
- 提供可直接用于 pipeline 的问题格式

**具体操作**:
1. 定义高级定理字典（包含名称、描述、DSL、辅助点、备注）
2. 为每个定理编写 llm_input_renamed 格式的 DSL
3. 标注所需的辅助点类型

**运行方式**:
```bash
python tmp/construct_theorem_dsl.py
```

**已构造的定理示例**:

1. **泰勒斯定理（平行线分线段成比例）**
   - DSL: `a : ; b : ; c : ; d : coll a b d [000] ; e : coll a c e [001] ; ? para d e b c, eqratio a d d b a e e c`
   - 辅助点: 无
   - 备注: 基础形式，无需辅助点

2. **角平分线定理**
   - DSL: `a : ; b : ; c : ; d : coll b c d [000] ; ? eqangle b a b d d a d c, eqratio b d d c a b a c`
   - 辅助点: 无
   - 备注: 需要用 eqangle 表示角平分，或引入 angle_bisector 构造

3. **圆周角定理逆定理**
   - DSL: `a : ; b : ; c : ; d : eqangle a c a b d c d b [000] ; ? cyclic a b c d`
   - 辅助点: 无
   - 备注: 从角度相等推导共圆

#### 脚本 3: validate_construction.py

**设计目的**:
- 验证构造的 DSL 语法是否正确
- 提取使用的谓词列表
- 输出验证报告

**具体操作**:
1. 解析 DSL 文本，提取所有谓词
2. 检查基本格式（是否包含 `?`，是否符合语法规则）
3. 列出每个定理使用的谓词

**运行方式**:
```bash
python tmp/validate_construction.py
```

**预期输出**:
- 每个定理的验证状态（✓ 格式正确 / ⚠️ 格式可能有误）
- 使用的谓词列表

### 初步发现与建议

#### 发现 1: 高级定理的构造挑战

通过分析发现，高级定理的构造面临以下挑战：

1. **辅助点依赖**: 许多高级定理需要特殊的辅助点（如角平分线与边的交点、垂足、外心等）
2. **谓词限制**: 某些定理需要的构造谓词可能在 `defs.txt` 中未定义
3. **前提复杂度**: 高级定理往往需要更多前提条件，可能超过 max_premises=7 的限制

#### 发现 2: 可直接构造的定理

以下定理可以用现有谓词直接构造：
- **泰勒斯定理**: 使用 coll, para, eqratio
- **圆周角定理逆定理**: 使用 eqangle, cyclic
- **平行四边形性质**: 使用 cong, para, eqangle

#### 发现 3: 需要扩展的定理

以下定理需要引入新的构造谓词或辅助点机制：
- **角平分线定理**: 需要 angle_bisector 构造或更复杂的 eqangle 组合
- **垂心定理**: 需要多个垂足辅助点
- **内心定理**: 需要角平分线交点

#### 建议 1: 扩展数据集

为了提取高级定理，建议：
1. 在数据生成时，增加使用高级构造的问题（如 angle_bisector, circumcenter 等）
2. 确保生成的问题包含足够的辅助点
3. 增加问题的复杂度（更多 clauses）

#### 建议 2: 放宽 pipeline 限制

考虑：
1. 增加 max_premises 到 8-10
2. 支持更复杂的辅助点构造模式
3. 引入更多高级谓词到 VALID_PREDICATES

#### 建议 3: 手工构造验证集

建议手工构造一批高级定理问题，用于：
1. 验证 pipeline 是否能正确提取
2. 测试 DDAR 引擎对高级定理的支持
3. 作为 benchmark 评估规则提取质量

### 下一步行动

1. **运行探索脚本**: 执行三个脚本，收集实际数据
2. **构造测试问题**: 为 2-3 个高级定理手工构造完整的测试问题
3. **验证 pipeline**: 将构造的问题输入 pipeline，观察提取结果
4. **迭代优化**: 根据结果调整问题构造策略或 pipeline 参数
