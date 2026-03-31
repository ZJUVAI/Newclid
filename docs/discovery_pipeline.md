# Discovery Pipeline: 从 AlphaGeometry 式合成证明中发现新规则

本文档不是一份“参数手册”，而是一份面向项目外读者的总览说明。

目标读者是假设你已经理解 AlphaGeometry 这类工作的基本范式：

- 用规则化几何引擎生成大量合成题；
- 用语言模型提出辅助点；
- 用符号推理器验证证明；
- 最终在 benchmark 上评估神经-符号系统。

如果你只知道这些，那么看完本文档后，应该能立刻明白：

1. GeoDiscovery 想额外回答什么问题。
2. 这条 discovery pipeline 和 AlphaGeometry 主线是什么关系。
3. 项目代码和实验结果是怎么组织的。
4. 每个阶段产出的文件到底表示什么。

---

## 1. 一句话说明这个项目在做什么

AlphaGeometry 假设“符号规则库”是给定的，然后研究如何借助辅助构造和搜索把难题证明出来。

GeoDiscovery 在此基础上再往前走一步，研究的是：

**如果我们已经有了 AlphaGeometry 风格的大规模合成数据和完整证明轨迹，能不能反过来从这些证明里自动挖出新的、可解释的几何规则，并把这些规则再反馈回符号求解器？**

所以，这个项目的核心不是再造一个训练脚本，而是建立一条从“合成证明语料”到“新规则发现、规约、评估”的完整知识发现链路。

---

## 2. 如果你只熟悉 AlphaGeometry，需要先抓住的差别

### AlphaGeometry 的标准视角

- 输入是几何题。
- LM 负责提出辅助点构造。
- 符号引擎用固定规则库做推理。
- 目标是证明更多 benchmark 定理。

### GeoDiscovery 的额外视角

- 输入不是单道 benchmark 题，而是**大规模合成题及其完整证明轨迹**。
- 我们把每条成功证明看成一份“潜在规则样本”。
- 目标不是直接输出一份证明，而是从大量证明中抽出**可复用的中间规则**。
- 最终再检查这些规则能否提升 solver 的 benchmark 覆盖率。

换句话说：

- AlphaGeometry 关心“给定规则，如何证明题目”。
- GeoDiscovery 关心“给定大量证明，如何反推出规则”。

---

## 3. 这个 pipeline 到底在回答什么问题

这条 pipeline 主要回答三个问题。

### 问题 A: 证明里是否包含可复用的局部推理模式？

如果一条证明中出现了辅助点，通常说明默认规则库不足以直接走到结论。这样的证明片段往往包含某种“局部高阶规律”。

GeoDiscovery 试图把这些局部规律提取成

`premises => conclusion`

这种规则形式。

### 问题 B: 这些规则能否被压缩成一个小而有效的 basis？

从百万级样本里直接抽出的候选规则会极多、极重复，也会包含很多只是变量改名或对称变形的规则。

因此我们不仅要“提取”，还要做：

- 规范化
- 去重
- subsumption 规约

最后得到一个可以真正交给 solver 使用的 basis rule set。

### 问题 C: 这些规则到底有没有用？

这不是纯模式挖掘项目。最终必须回答：

- 加回 solver 后，benchmark solved 数是否增加？
- 是否会引入 regression？
- 提取出的规则是否与我们关心的高级几何定理方向有关？

因此 pipeline 的最后一环一定是 benchmark evaluation，而不是停在“看起来很像规则”的文本产物上。

---

## 4. 整条链路的核心想法

可以把整个项目理解成下面这个闭环：

```text
AlphaGeometry 风格合成数据生成
    ↓
获得带完整证明轨迹的 synthetic problems
    ↓
只保留最有知识增量价值的证明
    ↓
把证明图裁成局部推理片段
    ↓
把片段规范化成 candidate rules
    ↓
去重 + 规约，得到小规模 basis rules
    ↓
把 basis rules 加回 solver
    ↓
在 hageo / jgex / imo 等 benchmark 上评估
    ↓
分析这些规则是否接近高级定理
    ↓
必要时用 weak engine 再生成更难数据，继续下一轮
```

这个闭环的意义是：

- 它既是一个**求解器增强流程**，也是一个**知识发现流程**。
- 它既追求 benchmark gain，也追求规则本身的可解释性。

---

## 5. 为什么重点盯着 auxiliary-point proofs

在 AlphaGeometry 体系里，困难题往往不是“纯代数变换不够”，而是“需要构造对的辅助点，才能打开证明路径”。

因此在 GeoDiscovery 里，一个很自然的判断是：

**如果某条合成证明依赖 auxiliary points，那么它更可能暴露默认规则库没有显式写出的组合规律。**

这就是为什么 discovery pipeline 的第一步通常会优先保留带 aux points 的样本。

直觉上可以把它理解成：

- 不带 aux 的题，很多只是默认规则的直接展开。
- 带 aux 的题，更可能包含“值得学出来”的中间 lemma。

这也是为什么 weak engine / flywheel 在后面会变得重要：

- 如果默认引擎太强，很多结构会被“直接秒掉”，你看不到真正稀缺的规则缺口。
- 先弱化引擎，再观察哪些题变难，常常更有利于发现新规则。

---

## 6. Pipeline 的五个主阶段

这条链路可以分成五个主阶段，外加一个可选的 weak-engine / flywheel 变体。

### Stage 0: 数据生成

**目的**: 生成大量带完整证明轨迹的 synthetic geometry problems。

**入口脚本**:

- `src/newclid/generation/generate.py`
- `scripts/flywheel_generate.py`（weak engine 包装）

**输入**:

- 几何构型生成参数，例如 `n_clauses`、`n_samples`、`aux_only`。

**输出**:

- JSONL 数据集，每条记录包含 problem、proof、aux points、生成统计等。

**这一步在项目中的角色**:

- 它是 discovery 的“语料来源”。
- 没有 Stage 0，就没有后续的规则提取样本。

### Stage 1: 规则提取

**目的**: 从单条证明中裁出局部规则候选，然后把海量候选规范化、去重。

**默认入口**:

- `scripts/discovery_pipeline.py`
- `src/newclid/proof_scout/core/filter_and_prune_engine.py`

**内部步骤**:

1. 输入过滤: 只保留有价值的题目，例如带 aux point 的样本。
2. 图修剪: 从完整证明图中删去冗余节点，只保留最小必要推理链。
3. 命题提取: 把修剪后的证明图变成 `premises -> conclusion` 形式。
4. 规范化: 统一点名、谓词对称性和规则文本表示。
5. 去重: 合并完全重复或规范化后相同的规则。
6. 落盘: 得到可读、可分析、可规约的候选规则文件。

**这一步真正做的事**:

它不是“从文本里摘句子”，而是把 proof graph 变成 rule graph，再把 rule graph 变成稳定的 DSL 规则文本。

### Stage 2: 规则规约

**目的**: 把 Stage 1 抽出的海量候选规则压缩成一个小规模 basis。

**入口**:

- `scripts/discovery_pipeline.py`
- `scripts/discovery_pipeline_c.py`
- `src/newclid/proof_scout/reduction/rule_reducer.py`

**核心机制**:

- 按 seed 做组内规约，先消灭明显同源规则。
- 再做全局规约，用 subsumption test 判断某条规则是否被更一般的规则覆盖。

**你可以把 Stage 2 理解成**:

- Stage 1 回答“出现过哪些规则候选”。
- Stage 2 回答“真正值得保留下来的最小规则集是什么”。

### Stage 3: 规则评估

**目的**: 检查发现的规则是否真的能提升 benchmark 表现。

**入口**:

- `scripts/evaluate_rules.py`
- `scripts/evaluate_rules_csolver.py`

**评估方式**:

1. 先跑 baseline: 只用默认规则库。
2. 再跑 augmented: 默认规则库 + discovery 得到的 rules。
3. 对比 `new_solved`、`regressed`、`net improvement`。

**这一步的重要性**:

如果没有 benchmark gain，那么“提取了很多规则”在研究上并不成立。

### Stage 4: 规则分析与可视化

**目的**: 让规则不只是一个求解器增益数字，而是可解释的知识对象。

**常见产物**:

- 规则渲染图
- 规则样例卡片
- 标注后的规则文本
- 与高级定理的比对文档

**入口脚本和产物**:

- `scripts/figures/...`
- `scripts/render_rule_cards.py`
- 各 experiment 目录下的 `*_annotated.txt`、`rule_comparison_analysis.md`

---

## 7. 为什么项目里同时有 Python pipeline 和 CSolver pipeline

你会在仓库里看到两条相近但不完全相同的链路：

- `scripts/discovery_pipeline.py`
- `scripts/discovery_pipeline_c.py`

区别不在 Stage 1，而主要在 Stage 2 和 evaluation：

- Stage 1 的规则提取逻辑本质一致。
- Stage 2 的 subsumption test 可以走 Python 版推理器，也可以走 C++ DDAR/CSolver。
- 大规模实验通常优先使用 CSolver 版本，因为它更快，也更接近最终 benchmark 使用的符号后端。

对项目外读者来说，可以把它简单理解成：

- Python pipeline = 逻辑更直接、开发更方便。
- CSolver pipeline = 大规模规约和评估的主力版本。

如果你只想抓住项目主线，优先看下面三个入口就够了：

- `scripts/discovery_pipeline_c.py`
- `scripts/evaluate_rules_csolver.py`
- `src/newclid/proof_scout/core/filter_and_prune_engine.py`

---

## 8. 这个项目在代码库里是怎么组织的

从 outsider 的角度，仓库可以按功能划成五块。

### A. 数据生成

- `src/newclid/generation/generate.py`
- `scripts/flywheel_generate.py`

负责生产 discovery 所需的 synthetic proof corpus。

### B. 规则提取

- `scripts/discovery_pipeline.py`
- `src/newclid/proof_scout/core/filter_and_prune_engine.py`
- `src/newclid/proof_scout/core/proof_graph.py`
- `src/newclid/proof_scout/core/graph_pruner.py`

负责从 proof traces 中抽 candidate rules。

### C. 规则规约

- `scripts/discovery_pipeline.py`
- `scripts/discovery_pipeline_c.py`
- `src/newclid/proof_scout/reduction/rule_reducer.py`
- `src/newclid/proof_scout/reduction/subsumption_tester.py`

负责把候选规则压成 basis rules。

### D. 规则评估

- `scripts/evaluate_rules.py`
- `scripts/evaluate_rules_csolver.py`

负责回答“加规则后 benchmark 是否更好”。

### E. 规则分析

- `docs/grow_base_rules_guideline.md`
- 各 experiment 目录下的 `*_annotated.txt`
- 各 experiment 目录下的 `rule_comparison_analysis.md`

负责回答“这些规则和高级定理有没有关系”。

---

## 9. 一次标准实验会产出什么文件

一个典型 experiment 目录通常长这样：

```text
outputs/experiments/<experiment_name>/
├── intermediates/
│   ├── step1_input_filter.json
│   ├── step2_graph_prune.json
│   ├── step3_propositions.json
│   ├── step4_normalized_rules.json
│   ├── step5_dedup.json
│   └── step6_rules_stats.json
├── extracted_rules_maxprem7.txt
├── eliminated_rules_maxprem7.json
├── reduction_stats_maxprem7.json
└── eval/
    └── <benchmark>_eval.json
```

对于 outsider，最值得先看的文件有四类。

### 1. `step1_input_filter.json`

告诉你：原始数据里有多少题真正进入 discovery 主线。

### 2. `step6_rules_stats.json`

告诉你：提取后真正留下了多少条“可用规则”。

### 3. `extracted_rules_maxprem7.txt`

这是最终 basis rules，本质上就是你想交给 solver 的 discovery 成果。

### 4. `eval/*.json`

这是最终研究结论的证据：

- baseline solved
- augmented solved
- new_solved
- regressed

如果只看一个文件，那就看 evaluation JSON。

---

## 10. 这条 pipeline 当前已经产出了什么结果

下面给两个代表性例子，帮助你理解这不是“规划中的想法”，而是一条已经在运行的实验链路。

### 例子 A: CSolver + 100k 规则发现

项目中已有一轮成熟结果表明：

- 从 100k 级 synthetic 数据中提取并规约后，可得到约百条 basis rules。
- 在 CSolver 上进行 benchmark 回测时，能带来稳定的 solved 增量。

代表性结果：

- `hageo_409`: baseline `106/409`，增强后 `114/409`，新增 `+8`。
- `jgex_ag_231`: baseline `204/231`，增强后 `213/231`，新增 `+9`。

这说明 discovery pipeline 不是只在做“规则可视化”，它已经能产出有 benchmark 价值的规则集。

### 例子 B: weak 1M 规则发现（2026-03-27 / 2026-03-28）

实验目录：

- `outputs/experiments/20260327_01_weak1m_rule_extraction/`

该实验对应的主结论是：

- 生成侧得到 `1,000,091` 条样本。
- 经过 aux 过滤、图修剪、规范化、去重和规约后，最终保留 `512` 条 basis rules。
- 其中用于 `jgex_ag_231` 评估的有效规则数为 `492`。
- 在 `jgex_ag_231` 上，CSolver 从 `87/231` 提升到 `144/231`，净增 `+57`，且 `0` regression。

更重要的是，这批规则已经开始出现明显的高级定理相关主题：

- 最强的是泰勒斯正向比例家族（`para -> eqratio`）。
- 其次是角平分线与比例互推家族（`eqangle -> eqratio` 和少量 `eqratio -> eqangle`）。
- 还出现了弱一些的共圆+等距、三重共线推出新共线等雏形。

但这些规则大多仍然是“通向高级定理的中间规则族”，而不是教材式 canonical theorem 形式。

这正是 GeoDiscovery 的当前研究位置：

- 不是还没发现东西。
- 也不是已经直接抽出了完整高级定理库。
- 而是已经走到“中间规则族稳定出现，并能带来 benchmark gain”的阶段。

---

## 11. 这项工作的真正组织逻辑

如果只看脚本，很容易以为仓库里有很多零碎实验。实际上它们围绕的是同一条组织逻辑。

### 第一层: 生产 discovery 语料

- 通过标准生成器生产 synthetic problems。
- 必要时通过 weak engine 放大“规则缺口”。

### 第二层: 从语料中挖规则

- proof graph 抽 candidate rules。
- 再通过 normalization + dedup + reduction 得到 basis rules。

### 第三层: 判断这些规则有没有 solver 价值

- 在 benchmark 上做 baseline / augmented 对照。

### 第四层: 判断这些规则有没有几何知识价值

- 用标注文件和高级定理比对文档解释这批规则到底在“长向哪里”。

因此，项目的最终交付并不是单一文件，而是四种互相支撑的证据：

1. 数据侧证据: 这些规则来自什么语料。
2. 压缩侧证据: 这些规则如何从海量候选缩成 basis。
3. benchmark 侧证据: 这些规则是否能提升求解器。
4. 几何语义侧证据: 这些规则是否接近我们真正关心的高级定理。

---

## 12. 一位新读者最推荐的阅读顺序

如果你刚进入这个项目，建议按下面顺序读。

1. 先读本文档，建立整体地图。
2. 再读 `README.md`，理解项目与 AlphaGeometry reproduction 的关系。
3. 再看 `scripts/discovery_pipeline_c.py`，知道主入口怎么串起来。
4. 再看 `src/newclid/proof_scout/core/filter_and_prune_engine.py`，理解规则是怎么被抽出来的。
5. 再看 `scripts/evaluate_rules_csolver.py`，理解“规则有用”是怎么被定义的。
6. 最后看某个具体实验目录，例如 `outputs/experiments/20260327_01_weak1m_rule_extraction/`。

如果你更关心“这些规则是不是接近高级定理”，就直接接着看：

- `docs/grow_base_rules_guideline.md`
- `outputs/experiments/20260327_01_weak1m_rule_extraction/rule_comparison_analysis.md`

---

## 13. 常用入口命令

下面给出 outsider 最需要知道的最短命令集。

### 生成 discovery 数据

```bash
python src/newclid/generation/generate.py \
    --n_clauses 10 \
    --aux_only 1 \
    --n_threads 30 \
    --n_samples 100000 \
    --timeout 3600 \
    --log_level info \
    --dir outputs/datasets/geometry_clauses10_samples100k
```

### 跑完整 discovery pipeline（推荐 CSolver 版本）

```bash
python scripts/discovery_pipeline_c.py \
    -i outputs/datasets/geometry_clauses10_samples100k/geometry_clauses10_samples100k.jsonl \
    -o outputs/experiments/YYYYMMDD_01_csolver_discovery \
    --save-intermediates \
    --engine full \
    --max-premises 7
```

### 先做 baseline，再评估 discovery rules

```bash
python scripts/evaluate_rules_csolver.py baseline \
    --output outputs/eval_baselines_csolver/

python scripts/evaluate_rules_csolver.py evaluate \
    --rules outputs/experiments/YYYYMMDD_01_csolver_discovery/extracted_rules_maxprem7.txt \
    --baseline-cache outputs/eval_baselines_csolver/ \
    --output outputs/experiments/YYYYMMDD_01_csolver_discovery/eval/ \
    --benchmarks hageo_409,jgex_ag_231 \
    --workers 30 \
    --timeout 600
```

### 跑 weak-engine flywheel 数据生成

```bash
python scripts/flywheel_generate.py \
    --n_samples 10000 \
    --n_clauses 5 \
    --n_threads 20 \
    --dir outputs/flywheel/iter_00
```

---

## 14. 最后用一句话再总结一次

GeoDiscovery 的 discovery pipeline，本质上是在 AlphaGeometry 的 synthetic proof universe 上再加一层“知识反演”：

**不是只问系统能不能证明题，而是问系统成功证明过的大量题目里，是否已经隐含着一批值得被显式写回 solver 的新规则。**

这条 pipeline 的组织方式，就是把这个问题拆成：

- 数据生成
- 证明裁剪
- 规则提取
- 规则规约
- benchmark 回测
- 高级定理语义分析

六个互相衔接的环节。

如果你理解了这一点，就已经理解了这个项目的主线。
