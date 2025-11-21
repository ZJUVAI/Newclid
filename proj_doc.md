# 项目主题: 基于知识发现的 GenesisGeo 性能增强
# (Project Context: GenesisGeo Performance Enhancement via Knowledge Discovery)

---

## 1. 项目概览 (Project Overview)

* **核心目标 (Goal):** 实现几何高质量定理的发现，并由此构建一个迭代增强几何解题的模型GenesisGeo框架，实现模型性能的提升。
* **最终交付物 (Deliverable):** 1. 一个多模态几何定理质量评估器； 2. 一个性能增强的 GenesisGeo V2 模型。
* **关键术语 (Glossary):**
    * `GenesisGeo`: 我们的基础几何求解器 (V1)。
    * `ddar`: 我们的一个核心依赖库/方法。
    * `DAG`: 定理的图结构表示 (有向无环图)。
    * `Tool 1`: 启发式规则过滤器。
    * `Tool 2`: 多模态几何定理质量 (LLM+GNN+Features) 评估器。
    * `V2`: 经过新创建的框架迭代，获得高质量定理知识后训练的 GenesisGeo V2。
    * `IMO-AG-30/50`: 我们的最终评估基准 (Benchmark)。

---

## 2. 项目背景与痛点 (Background & Critical Gaps)

### 2.1. 盘点资产

#### 2.1.1 核心数据 (Data)
-   **数据来源 (Source):** 利用 ddar 引擎，以现有定义和规则从头随机合成的定理数据。
-   **数据规模 (Scale):** 所有定理均带有证明，总量约 10^6；其中包含辅助点的数据约占 10%；对定理进行去重后约 1%（约 10^4 条）。
-   **数据格式 (Format):**
    * 定理描述 (Premise + Conclusion)，例如 `llm_input_renamed` 字段：
        ```xml
        <problem> a : ; b : ; c : cong a b b c [000] cong a c b c [001] ; d : perp b c b d [002] cong b c b d [003] ? aconst a b c d 7pi/12 </problem>
        ```
    * 证明步骤 (Proof)，以 JSON 记录，例如：
        ```json
        {
            "n_clauses": 2,
            "fl_problem": "a@-0.9708300138587499_-1.208111825600701 b@-1.3896240262758974_0.6475103291955953 c@0.4267889058114889_0.0823855055035124 = ieq_triangle a b c; d@0.6276198675704225_-0.8074705357947214 = angle_mirror d a c b; e@-0.2337473231378291_-0.18619078671027625 = on_tline e a b d, on_line e d b; f@-1.9547488499679802_-1.168902602891791 g@-0.13833591788059407_-1.734027426583874 = square c b f g; h@0.7837084790509459_-0.725459732931095 = intersection_pp h d c f b a g; i@-1.007888301622236_-1.0342480886648988 = eqangle3 i d c b f a, on_bline i c h; j@2.4621877233262666_-1.1901663293483296 = eqratio j g d c a h i e, angle_mirror j h d f; k@-0.9101610458856924_-1.0386391918199047 = on_circum k j c e, on_line k i j; l@1.0707139952591982_-0.6606856670427174 = s_angle b h l 45o, angle_bisector l h c j ? aconst a b c f 7pi/12",
            "nl_problem": "",
            "n_proof_steps": 22,
            "llm_input_renamed": "<problem> a : ; b : ; c : cong a b b c [000] cong a c b c [001] ; d : perp b c b d [002] cong b c b d [003] ? aconst a b c d 7pi/12 </problem>",
            "llm_output_renamed": "<aux> x00 e : para b c d e [004] para b d c e [005] ; </aux> <numerical_check> sameclock a b c a b c [006] ; sameclock b c d b c d [007] ; ncoll b c d e [008] ; sameclock b c d c e d [009] ; sameclock a b d a e c [010] ; </numerical_check> <proof> eqratio a b a c b c a b [011] a00 [000] [001] ; eqratio a b b c b c a c [012] a00 [000] [001] ; simtri a b c b c a [013] r60 [011] [012] [006] ; eqangle a b a c b c a b [014] r52 [013] ; eqangle a b b c b c a c [015] r52 [013] ; eqangle b c b d c e d e [016] a01 [004] [005] [002] ; cyclic b c d e [017] r04 [016] [008] ; eqangle b c b e c d d e [018] r03 [017] ; eqangle b d b e c d c e [019] r03 [017] ; eqangle a b b d c e a c [020] a01 [015] [018] [019] [004] ; eqangle b c c d d e c d [021] a01 [004] ; eqangle b d c d c e c d [022] a01 [005] ; simtri b c d e d c [023] r34 [021] [022] [009] ; eqratio b d c d c e c d [024] r52 [023] ; eqratio a b a c b d c e [025] a00 [000] [001] [024] ; simtrir a b d a c e [026] r63 [020] [025] [010] ; eqangle a b a d a e a c [027] r53 [026] ; eqangle a d b d c e a e [028] r53 [026] ; eqratio b c b d c d c d [029] a00 [003] ; simtrir b c d b d c [030] r61 [029] [007] ; eqangle b c c d c d b d [031] r53 [030] ; aconst a b c d 7pi/12 [032] a01 [014] [027] [015] [028] [031] [005] ; </proof>"
        }
        ```
-   **“黄金数据” (Golden Set):** 现有规则集 + 前期实验中人工筛选出的有意义定理，共 41 条。其中“定义 → 性质”类定理 16 条，其余 25 条是真正高质量的定理（不能由其他定理直接推导，通常需要额外辅助构造才能证明）。

#### 2.1.2 现有工具 (Tools / Pipeline)
-   **生成器 (Generator):** 基于 dd（deductive database）+ ar（algebraic reasoning）的前向推演系统。
    * **算法 (Algorithm):** 通过若干次随机组合构造语句，得到不同的几何配置（geometry configuration），借助解析绘图得到可能成立的 goals，使用现有规则进行前向推导验证，并通过反向回溯确定其中的辅助构造。
    * **优点 (Pros):** 可以在 CPU 上快速得到结果，且找到的结果在逻辑上都是正确的，无需额外的正确性检查。
    * **问题 (Cons):** 能找到的结果过多且相近；生成过程不区分难易度，有时证明过程会“绕远路”。理想情况下该引擎的生成结果应高度有用，但当前 ar 环节存在问题（非本课题重点），因此需要在“正确性”维度额外做检查与过滤。
-   **当前“命中率” (Current Hit Rate):** 这是一个关键指标。前期两轮实验中，在约 5k 条去重后的“带辅助构造”命题中人工可选出 2–3 个优质定理；随后的实验中该比例进一步下降，黄金定理命中率约为 **~0.05%**。

### 2.2. 几何定理评估的痛点 (Critical Gaps — 评估与筛选乏力)

-   **缺失的标签 (Missing Labels)** — 如果为数据打上如下标签，将更有助于筛出有价值的定理：
    * **难度 (Difficulty):** 这个证明有多难？
    * **有趣性 (Interestingness):** 这个结论有多“出人意料”？
    * **新颖性 (Novelty):** 这个定理是否已为人所知？
    * **对称性 (Symmetry):** 这个定理的表述在几何上是否简洁优美？
-   **“有价值”的直觉定义 (What is Valuable?):**
    * **标准 1:** 形式非常简洁，可以通过简单构造洞见核心性质。
    * **标准 2:** 借助该定理可以解决原本难以解决的问题。
-   **“无价值”的直觉定义 (What is Junk?):**
    * **标准 1:** 在命题部分涉及或引入与最终结论无关的点（即“垃圾点”）。

---

## 3. 核心方案：V3 评估器智能体 (Core Solution: The V3 Evaluator Agent)

本节整合“评估器智能体 (Evaluator Agent)”与“科研飞轮”落地的可执行说明。

### 3.1. 核心需求：多阶段评估系统
面向极低命中率（~0.05%）场景的多阶段、混合智能“定理质量评估系统”。目标是构建一个由评估智能体 (Evaluator Agent) 驱动的自动化“科研飞轮”，实现“数据生成 → 智能筛选 → 人类反馈 → 模型迭代”的闭环。

系统由以下三个核心组件构成：

### 3.2. 组件一：(工具) 启发式预筛选器 (Heuristic Pre-Filter)

-   **资产:** 正在开发的“基于人类规则的打分工具”。
-   **角色:** “第一道防线”，作为基础层和预筛选器，快速剔除显而易见的低价值样本。
-   **工作流:**
    1.  **输入:** ddar 引擎生成的 ~10^6 条“原始”定理数据。
    2.  **处理:** 执行快速的、基于规则的检查（例如：是否引入无关点，是否为简单同义替换）。
    3.  **输出:** ~10^4 条“可能有趣”的候选数据，并为每条数据附加一个“启发式得分” (H-Score)。
-   **优势:** 计算成本低、可解释性强，可显著减少后续昂贵 AI 模型的计算负担。

### 3.3. 组件二：(AI) 语义评估器 (LLM-based Semantic Scorer)

-   **资产:** (16+9)=25 条“黄金定理”的文本表示（`llm_input_renamed` 字段）。
-   **角色:** 评估定理的“语义质量”，包括“简洁性、优美性、出人意料性”等维度。
-   **AI 方案:** 少样本提示 (Few-shot Prompting)。
-   **工作流:**
    1.  **输入:** `problem` 字符串（即定理的文本表示）。
    2.  **处理:** 将 25 条黄金样本和 N 条“垃圾样本”作为 In-Context-Learning 示例，提示一个强大的 LLM（如 GPT-4、Claude 3）对输入定理的语义质量进行打分。
    3.  **输出:** 语义得分 S-Score，范围 [0.0, 1.0]。
-   **优势:** 无需训练，直接利用大模型的“人类语感”来刻画 GNN 难以捕捉的“美感”。

### 3.4. 组件三：(AI) 结构评估器 (GNN-based Structural Scorer)

-   **资产:**
    * 9 条“黄金定理”的证明图 (P_dag)。
    * N 条“垃圾定理”的证明图 (N_dag)。
    * ~10^4 条“未标注”的证明图 (U_dag)。
-   **角色:** 评估定理的“结构质量”，包括“证明的巧妙性、难度、非平凡性”等维度。
-   **AI 方案:** 自监督预训练 (Self-Supervised Pre-training) + 监督微调 (Finetuning)。
-   **工作流:**
    1.  **预训练:** 利用 ~10^4 条 U_dag 数据，对 GNN 进行自监督预训练（如预测 `n_proof_steps`、掩码节点预测等任务），让模型先学习几何证明图的一般结构模式。
    2.  **微调:** 使用 9 条 P_dag（标记为 Y=1）和 N 条 N_dag（标记为 Y=0）对预训练好的 GNN 进行监督微调，教会模型区分“黄金”与“垃圾”的结构差异。
    3.  **输出:** 结构得分 G-Score，范围 [0.0, 1.0]。
-   **优势:** 在仅有 9 个正样本的严苛条件下，仍能通过自监督 + 微调的方式学习到深层的逻辑结构模式。

### 3.5. 最终系统：「评估智能体」与「科研飞轮」

-   **1. 评估 (Evaluate):**
    * 最终得分定义为
        $$\text{Final\_Score} = w_1 \cdot H\text{-Score} + w_2 \cdot S\text{-Score} + w_3 \cdot G\text{-Score},$$
        其中 $w_1, w_2, w_3$ 为可调权重，代表我们对三种评估方式的信任度。
-   **2. 学习 (Learn — Active Learning):**
    * 评估智能体批量处理所有候选定理，找出“最值得人类一看”的样本，例如 Top-K 高分样本，或 G-Score 与 S-Score 差异最大的“有分歧”样本。
-   **3. 反馈 (Human-in-the-Loop):**
    * 人类专家审核这 K 条候选，沉淀出其中真正高质量的新的黄金定理。
-   **4. 迭代 (Iterate):**
    * 将新增的 K 条黄金样本同时加入 GNN 微调集与 LLM 提示集，循环迭代，持续提升评估器能力。

### 3.6. 最终指标

-   **贡献:** 通过下游几何解题性能证明“人机协同科研飞轮”的有效性。
-   **评估:** 以求解器的解题能力为主指标。
-   **实验设计:** 比较两种配置的性能差异：
    * [求解器 + V4 飞轮筛选得到的 Top-N 新定理]；
    * [求解器 + 原始 41 条规则]。

---

## 4. 实验 Pipeline 大纲 (Experiment Pipeline Outline)

### 4.1. 阶段一：数据准备 (Phase 1: Data Preparation)
* **1.1 海量数据生成 (Massive Generation):** 使用GenesisGeo V1求解器随机生成 ~10^6 条定理数据。
* **1.2 显式特征提取 (Wide Features):** 提取定理文本特征 (e.g.定理文本长度, 涉及点/线的数量, 证明树深度, 是否含辅助点, 共圆/共线等几何属性计数)
* **1.3 正/负样本标注 (Labeling Strategy):**
    * *Positive Samples:* 人工筛选的 41 条已知高质量定理, 或能用于解决 IMO 难题的定理
    * *Negative Samples:* 包含无效点, 结论平凡/冗余, 或纯粹的同义词替换
* **1.4 黄金测试集 (Gold Test Set):** 人工精选 100 条正样本和 400 条负样本, 确保标签准确

### 4.2. 阶段二：评估器构建 (Phase 2: Scorer Construction)
* **2.1 [Tool 1] 规则过滤器:** 过滤掉证明步数 < 3 或 > 50 的定理, 剔除引入“垃圾点”的定理
* **2.2 [Tool 2] 多模态评估器架构（暂定）:**
    * *Text Branch (LLM):* (e.g., 选用 DeBERTa-base 作为文本编码器, 提取 [CLS] token 向量)
    * *Graph Branch (GNN):* (e.g., 选用 5 层 GIN, 对证明的 DAG 进行图级别表征)
    * *Wide Branch (Features):* (e.g., 1.2 中的显式特征, 归一化后通过一个 2 层 MLP)
    * *Fusion Strategy:* (e.g., 采用 Concat + 3层 MLP 融合三个分支的向量, 最终输出一个 sigmoid 质量分)
* **2.3 [Tool 2] 训练与评估:** (e.g., 使用 Binary Cross-Entropy 损失, 监控验证集上的 AUC 和 F1 Score)

### 4.3. 阶段三：模型迭代与评估 (Phase 3: Model Iteration & Evaluation)
* **3.1 知识发现 (Knowledge Distillation):** (e.g., 使用 Tool 2 对 10^6 条原始数据打分, 筛选出 Top 1% (即 10k) 作为高质量集)
* **3.2 [GenesisGeo V2] 训练:** (e.g., 将 High-Quality Set 作为 SFT (监督微调) 数据, 在 V1 模型基础上进行训练)
* **3.3 最终基准测试 (Benchmarking):**
    * *Metrics:* (e.g., Pass@1, Pass@10, 以及平均解题步数)
    * *Baselines:* (e.g., GenesisGeo V1, AlphaGeometry (AG-0), IMO-Tool)
    * *Ours:* GenesisGeo V2
    * *Ablation Study:* (e.g., V2 (Full) vs V2 (w/o GNN) vs V2 (w/o LLM) vs V1 (Baseline))

## 5 ICML 2026 冲刺：周度作战大纲 (Weekly Master Plan)

* **4.1 核心故事线 (Core Narrative):** (e.g., 强调“AI 评估器驱动的知识发现”闭环, 以及人机协同的科研飞轮模式)
* **4.2 关键图表 (Key Figures):**
    * *Fig 1:* (e.g., 评估器 (Tool 2) 的多模态架构图)
    * *Fig 2:* (e.g., Tool 2 评估器的 AUC/ROC 曲线和 F1 分数表格)
    * *Fig 3:* (e.g., V2 vs V1 及其他 Baselines 在 IMO-AG-30 上的 Pass@K 对比柱状图)

---

### 5.1. 9 周冲刺日程 (9-Week Sprint Plan)

**第 1 周：数据奠基 (Foundation)**
* 时间: 11.14 (Fri) - 11.20 (Thu)
* 核心目标: 搞定数据 pipeline，确保有一份高质量的测试集。
* 技术任务:
    * 启动 GenesisGeo/AG 随机生成脚本，确保后台稳定产出。
    * 编写 Python 脚本提取显式特征（Wide Features）。
    * 完成自动标注脚本（Pos/Neg），并人工校验 500 条测试集（这是本周最重要的事）。
* 写作任务:
    * 建立 Overleaf 项目。
    * 完成 Method: 3.1 (Preliminaries) 和 3.2 (Data Construction) 的草稿。
* 本周交付物: dataset_v1 (含清洗后的 Train/Val/Test) + 论文数据章节草稿。

**第 2 周：组件准备 (Components)**
* 时间: 11.21 (Fri) - 11.27 (Thu)
* 核心目标: 跑通所有模块的“单体测试”，准备好模型输入。
* 技术任务:
    * 打包数据 (.pt/.jsonl)，写好 PyTorch Dataloader。
    * 跑通 Baseline (Tool 1 规则过滤器) 的指标。
    * 跑通 LLM (Text Encoder) 和 GNN (Graph Encoder) 的 Embedding 提取代码。
* 写作任务:
    * 撰写 Method: 3.3 (Rule Filter) 和 3.4 (Multi-modal Input)。
    * 通读一遍 Method 章节，确保逻辑通顺。
* 本周交付物: 可运行的 Dataloader + Tool 1 实验数据。

**第 3 周：评估器构建 (The Scorer)**
* 时间: 11.28 (Fri) - 12.04 (Thu)
* 核心目标: 训练出那个“火眼金睛”的 Tool 2 模型。
* 技术任务:
    * 搭建 Fusion Layer (拼接 Text+Graph+Features)，跑通训练循环。
    * 训练 Tool 2，调整超参，确保 F1 Score 达标。
    * 选定 Best Checkpoint。
* 写作任务:
    * 绘制核心架构图 (Model Figure) 并插入论文。
    * 撰写 Exp: 4.1 (Scorer Performance)，填入 Tool 2 的评估表格。
* 本周交付物: 训练好的评估器模型文件 (tool2_best.pt) + 架构图。

**第 4 周：飞轮启动 (Ignition)**
* 时间: 12.05 (Fri) - 12.11 (Thu)
* 核心目标: 利用评估器“淘金”，并启动最终模型 V2 的训练。
* 技术任务:
    * 使用 Tool 2 清洗海量未标注数据，筛选出“高质量数据集”。
    * 配置 GenesisGeo V2 的训练环境。
    * 正式启动 V2 的微调/训练 (这通常很耗时)。
* 写作任务:
    * 转向开头，构思并撰写 Introduction (三段式逻辑)。
    * 写出 Contribution Summary (贡献点列表)。
* 本周交付物: distilled_high_quality_data.jsonl + Intro 初稿。

**第 5 周：验证与刷榜 (Verification)**
* 时间: 12.12 (Fri) - 12.18 (Thu)
* 核心目标: 拿到 GenesisGeo V2 的最终成绩单。
* 技术任务:
    * 监控 V2 训练，防止过拟合，训练完成并保存权重。
    * 核心实验: 在 IMO-AG-30 上运行 V2，记录 Pass Rate。
    * 如果效果好，设计消融实验 (Ablation Study)。
* 写作任务:
    * 撰写 Exp: 4.2 (Main Results)，描述 V2 的表现。
    * 撰写 Exp: 4.3 (Case Study)，找几个 V2 解出但 V1 没解出的例子。
* 本周交付物: 核心结果对比表 (Table/Chart)。

**第 6 周：可视化与补漏 (Visualization)**
* 时间: 12.19 (Fri) - 12.25 (Thu)
* 核心目标: 让数据变成漂亮的图表，补全实验短板。
* 技术任务:
    * 根据初步结果，补充缺失的 Baseline 对比。
    * 用 Matplotlib/Python 精修所有实验图表 (Bar charts, Curves)。
    * 整理代码库，准备开源/提交。
* 写作任务:
    * 撰写 Abstract (重中之重)。
    * 撰写 Conclusion 和 Related Work。
    * 全文通读第一次。
* 本周交付物: 所有精修图表 + Abstract 初稿。

**第 7 周：拼装与初修 (Assembly)**
* 时间: 12.26 (Fri) - 01.01 (Thu)
* 核心目标: 完成论文的 90%，准备给小老板看。
* 技术任务:
    * (此时应无重大代码任务，主要是查漏补缺)。
* 写作任务:
    * 排版调整 (压缩篇幅到 8-9 页)。
    * 检查参考文献 (BibTex)。
    * 对照 ICML Review Form 进行自我模拟评审 (Self-Rebuttal)。
* 本周交付物: 论文 Draft V0.8 (结构完整，待润色)。

**第 8 周：精修与附录 (Polishing)**
* 时间: 01.02 (Fri) - 01.08 (Thu)
* 核心目标: 将 Draft 打磨到可以投稿的水平。
* 写作任务:
    * 使用工具 (GPT-4/Grammarly) 深度润色 Intro 和 Abstract。
    * 整理 Appendix (附录)，将冗余证明和图表移过去。
    * 匿名化处理 (Anonymization)。
* 本周交付物: 论文 Draft V0.9 (语言流畅，无明显错误)。

**第 9 周：交付 (Delivery)**
* 时间: 01.09 (Fri) - 01.12 (Mon) 短周
* 核心目标: 最后的检查，发送给导师。
* 写作任务:
    * 打印纸质版，进行最后一次人工校对。
    * 修正所有发现的小错误 (Typos)。
    * 1月12日：发送邮件给小老板。
* 本周交付物: Draft V1.0 (Ready for Review)。

