## Prompt（要求）

你是一个认真的编程专家，协助我完成本项目。请严格遵循以下要求：

1) 在每次开始任务前，先阅读并对齐项目说明与代码说明：`geometry_knowledge_discovery.md`（视为当前权威规范）。
2) 你可以阅读全部任务，了解我的整体规划，但是一次只完成本文档 task 列表中“未被勾选”的任务中的第一条；开始执行前需先给出详细计划（步骤/涉及文件/可能影响/验证方式），待我确认后再执行。
3) task 列表的复选项除在我要求时进行添加外，不得改动 task 的条目文本与顺序。
4) 仅修改与本次任务直接相关的文件，最小化改动，避免无关格式化与风格漂移。
5) 变更前对齐仓库现状，必要时写明“假设与限制”，不确定处以注释或待办标注。
6) 改动后执行基础质量闸门：能构建/能导入、关键单测可运行、关键路径小样本可跑通；如失败先自我修复至可用。
7) 输出改动要点（delta）。
8) 日志/打印保持简洁可检索；长耗时或重计算前先征询确认。
9) 结果文件与路径遵循文档约定；若实现与文档不一致，先列差异并征询是“改代码对齐文档”还是“改文档对齐实现”。
10) 不引入新外部依赖，除非得到确认；若需引入，提供最小可行列表与锁定版本。
11) 所有测试调试命令都发给我，由我决定是否需要测试并执行，如果需要我会给你反馈测试的结果。
12) 后续的所有提问，你在回答的时候只能提出修改建议，不能直接修改代码文件，所有的修改都需要在我的确认之后进行。
13) 每次任务完成后，询问我是否更新本次完成的复选项内容具体说明与 `geometry_knowledge_discovery.md` 中的内容，由我确认是否更新。
14) data的内容是作为记录使用，你不需要在意。

---

date: 0907

- [x] 检查 data_discovery 目录代码，并与 geometry_knowledge_discovery.md 逐项比对，反馈差异
- [x] 将本次任务记录到 data_discovery/copilot_task.md（持续追加后续任务）
- [x] 按已确认的更新点修改 `geometry_knowledge_discovery.md` 并回传变更摘要
- [x] 当前的sch_split.txt中缺少translate fail的原因，添加这部分输出进来，在输出文件中添加新的条目用来记录被翻译的schema原文
- [x] 将 schema 与 schema_before 的求解输出分开落盘：分别生成各自的 tests/success/fail/summary 文件（保留当前合并版输出以兼容）
- [x] 将 schema_eval.py 中的功能方法提取出来，作为一个类函数，保留在data_discovery目录中，在schema_eval.py中分别调用两次这个函数，实现对schema和schema_before的处理
- [x] 将 schema_eval.py 移至 scripts/ 目录，改为从仓库根目录直接运行（绝对导入，免相对包路径问题）
- [x] 将脚本入口精简为仅两次高层调用（process_kind(schema) / process_kind(schema_before)），其余逻辑下沉到 SchemaBatchEvaluator
- [x] 输出策略改为“一个输入对应一个输出”：基于输入 JSON 的 basename 生成结果文件 `<basename>.<kind>.results.json`，不再生成 success/fail/summary 与合并版文件
- [x] 中间文件按输入名派生，便于审计：`<basename>.<kind>.rules.txt` 与 `<basename>.<kind>.split.txt`
- [x] 废弃旧的 src/newclid/data_discovery/schema_eval.py（改为抛出异常的占位模块，提示使用 scripts/schema_eval.py）
- [x] 重新组织geometry_knowledge_discovery.md中的内容，重命名为geometry_knowledge_discovery.md。主题改为几何知识发现，从介绍背景出发，指出需要实现的目标，当前的第一步是完成r07规则的重新发现，然后介绍具体的方法，不添加额外信息的情况下重新组织结构，先制定新的大纲，我确认后开始执行。

date: 0908

- [x] 更新文档，添加第二步：基础规则集扩展的任务描述及规划
- [x] 修改 run_batch.py，将其放入 scripts 目录中，其他路径不做修改；仿照 run_gspan_branched_demo.py 的脚本逻辑，将需要设定的超参集中于脚本文件开头，命令行只需执行 python run_batch.py
- [x] 检查rules_basic.txt，确认jgex可以全build，记录题目完成率
- [x] 利用当前generate.sh脚本，修改调用的generate.py文件，改用rules_basic.txt生成一批数据(100k) -> aux: 15k

date: 0909

- [x] 统计现在与data_discovery功能有关的新代码与数据，结合git的记录，文档的内容进行整理，将代码文件的目录整理写在geometry_knowledge_discovery.md中
- [x] 在现有的schema筛选部分代码中添加一步过滤，在生成schema_before后，先过滤掉sameclock sameside这两个premises，然后以过滤后的schema作为输入进行后续的过滤

date: 0910

- [x] 将translate_rule_to_problem.py中的函数提取出来，改成一个类似于tests/test_solve.py的简单测试函数，根据branched_mining.json中的文件格式，给一个简单的测试，方便我进行调试检查我希望能够完整迁移translate_rule_to_problem.py中translate_premise整个函数以及其中调用的若干translate_*函数及辅助函数，实现输入类似eqratio(X1,X2,X3,X2,X4,X2,X5,X2) => eqratio3(X1,X3,X4,X5,X2,X2)的schema格式，输出x5 = free x5; x4 = free x4; x3 = free x3; x2 = free x2; x1 = eqratio x1 x5 x2 x4 x2 x3 x2 x2 ? eqratio3 x1 x3 x4 x5 x2 x2这样的dsl语言题目。整个测试代码文件可以复制所有需要的功能独立完成上述流程，这样我通过调试这个测试代码就可以知道translate_rule_to_problem.py中哪里存在需要修复的bug

date: 0911

- [x] 确认当前的solve部分代码，找到画图与确定题目中点的坐标部分的代码，之后更新solver_utils.py，在当前求解部分将这些点的坐标添加进来，类似于
    ```
    point a -0.40746902984670474446 -0.66665500610231753775
    point b -0.11560335689440992546 -0.59371690741631888422
    point g1 -0.44257354475251259318 -0.52618242659683756024
    point g2 -0.17244267242498786952 -0.36627136967481344065
    point m -0.40604502710432055501 -0.38607339777242094536
    ```
    的格式，作为新的一项存储在输出文件中对应的题目项下
- [x] 更新子图挖掘的代码，在输出的schema中保留一份各点的坐标信息，格式如下：
    ```
        "point_lines": [
        "point a -0.49216369270784277 0.0322773499542357",
        "point b -0.34837646691822327 0.795407168565341",
        "point c -1.104024433863752 1.044882521415065",
        "point m -0.420270079813033 0.41384225925978835",
        "point n -0.27917315628915673 0.38725709025424193",
        "point o -0.8656498763618392 0.4977597314993747"
      ],
      "points": [
        {
          "name": "a",
          "x": -0.49216369270784277,
          "y": 0.0322773499542357
        },
        {
          "name": "b",
          "x": -0.34837646691822327,
          "y": 0.795407168565341
        },
        {
          "name": "c",
          "x": -1.104024433863752,
          "y": 1.044882521415065
        },
        {
          "name": "m",
          "x": -0.420270079813033,
          "y": 0.41384225925978835
        },
        {
          "name": "n",
          "x": -0.27917315628915673,
          "y": 0.38725709025424193
        },
        {
          "name": "o",
          "x": -0.8656498763618392,
          "y": 0.4977597314993747
        }
      ],
    ```
    更详细的格式可以参考outputs/jgex_ag_231_results.json中的内容，对每个schema只需要记录一个代表的坐标值即可，将这部分信息补充在输出的json文件中
- [x] 梳理当前run_gspan_branched_demo.py及其依赖的代码文件，精简其中的实现与注释内容，并与当前文档中描述进行比对，对文档内容进行精简和更新
- [x] 在scripts目录下新创建一个脚本文件，目标是将src/newclid/data_discovery/data/branched_mining.json文件中的schema和schema_before_dependency，结合对应的点坐标信息，重新整理成若干个txt的题目，每个题目的形式与src/newclid/data_discovery/data/schema_tests/example.txt的格式相同，文件名称为schema_{id}.txt和schema_before_{id}.txt，其中id是从0000开始，按顺序到9999的编号，这批文件最终存储在src/newclid/data_discovery/data/schema_tests/目录下。该脚本文件应该不需要依赖其他库中的代码文件。
- [x] 在scripts中写一个脚本代码，可以将指定文件（如outputs/data/geometry_clauses13_samples100k.jsonl）中的fl_problem项提取出来，整理成类似src/newclid/data_discovery/data/r07_problems.txt这种格式，整理后写成一个txt文件，存放在data_discovery/data/目录下该脚本文件应该不需要依赖其他库中的代码文件。

date: 0912

- [x] 统计目前的子图挖掘部分代码是如何进行schema筛选的，然后将筛选步骤的代码移出重新整理成一个类函数，并用单独的脚本文件（写在scripts目录下）进行调用，每个阶段单独保存输出文件,类函数代码名称为schema_filter.py；脚本文件名字取filt_schemas.py，同时还要更新make_schema_tests.py的格式，使得新的输出schema和不同的审计文件都可以后续经过make_schema_tests.py管线，make_schema_tests.py的cli选项都放在代码开头部分，通过手动在文件内修改超参来实现，我希望运行脚本文件只需要在命令行中输入python make_schema_tests.py
  备注：已新增 `src/newclid/data_discovery/schema_filter.py` 与 `scripts/filt_schemas.py` 并通过实际数据验证可用；`mining_pipeline.py` 已去除筛选/审计仅保留挖掘与schema生成。`make_schema_tests.py` 的常量化改造暂未执行，后续单独处理。
- [x] 跑通yuclid的流程，目前的情况：473 success + 26 fail to solve + 160 error(ncoll + eqratio3)

date: 0915

- [x] 检查mining_pipeline.py代码，输出的结果确实是正确的，并非一开始猜测的推理结果有误。

date: 0916

- [x] 在现在的schema_filter.py中添加一个新的函数，它用来进行结果的检查及过滤，方法如下：首先确认schema中每个premise的点集的并集和conclusion的点集，如果并集是点集的真子集，存放在error_schemas中；如果并集等于点集，则存放在discarded_schemas中，余下的存放在candidate_schemas中。
- [x] 设计一个python脚本，实现schema的图可视化方案，能够根据rendered中的信息将schema进行可视化，输出格式可以为图片或图形格式的文本，你来给我提供一些可能的参考
- [x] 根据每个schema中的rely_on信息，对candidate_schemas进行第二次筛选，规则如下：首先确认schema中conclusion中点及其rely_on组成union_rely集合，与premise中的点集的并集pre_union进行比较，会得到四种结果，根据不同的结果对schema进行分类：1. pre_union等于union_rely，此时schema被分类到discarded_schemas；2. pre_union是union_rely的真子集，此时schema被分类到discarded_schemas；3. union_rely是pre_union的真子集，此时schema被分类到candidate_schemas；4. union_rely和pre_union互不包含，此时schema被分类到candidate_schemas_type2中。新的过滤环节只输入partition_by_point_coverage.json中的candidate_schemas进行处理，输出到partition_by_rely_on.json中，同样保留rendered等附带信息。

date: 0917
- [x] 将第二次筛选过的schema接入visualize_schemas.py中进行可视化，输出到schema_fig目录下
- [x] 整理目前的挖掘-筛选-可视化代码，使其整体脉络更清晰，并更新文档
- [x] 进一步优化可视化环节，包括如下几部分：1. 目前schema的内容还是会超出圆圈的范围，尝试调整布局方式，使得或者圆圈中内容在外部指代或者如何调整字体大小，给出一个可行方案；2. 在图中添加union_rely的信息；3. 为fact node添加更多中标识方法，除了现在的绿色和蓝色表示premise和conclusion外，我还希望提供更多可供操作的接口，这样后续我可以对premise根据其点集是否包含在union_rely中进行区分；4. 完成1 2 3后开始对schema图中premise进行进一步细分的颜色标识区分。
- [x] 将filt/mine/visualize_schemas.py和schema_filter/miner/visualizer.py的内容更新到文档中，并去除文档中mining_pipeline.py和run_gspan_branched_demo.py的内容

date: 0918
- [x] 更新schema_visualizer.py，使得所有fact node都添加颜色标识，判断依据还是单个premise的点集是否包含在union_rely中，包含则为绿色，不包含则为橙色，conclusion为蓝色，用在schema中的前提（入度为0）边框加粗

date: 0919
- [x] 在二次筛选后再添加一个筛选，对于candidate_schemas和candidate_schemas_type2进行筛选，规则如下：对每个schema，检查其对应的图结构中的rule node连接的fact node，如果有一个rule node连接的全部fact node都满足其点集包含在union_rely中，则该schema被分类到discarded_schemas中，否则分类到final_candidate_schemas中
- [x] 将三次筛选的结果接入可视化功能
- [x] 修改第三次筛选的代码，使其输出的json中格式与第一次/第二次筛选的输出一致，先整理第一次第二次筛选后json文件的条目，然后给出第三次筛选的json文件条目修改方案。
- [x] 将第二阶段筛选（"stage" 为 "rely_on"）中的candidate_schemas和candidate_schemas_type2两类合并成candidate_schemas输出，第三阶段筛选后的绘图也像第二阶段一样在命令行中添加进度显示消息，之后整理第三阶段筛选（"stage"为"pruning"）的规则，我来指导如何进行修改

date: 0924
- [x] 检查当前scripts/run_batch.py管线，查看如何输出辅助构造信息（Auxiliary Constructions），将该功能添加进来后可以将辅助构造信息加在输出的json中
- [x] 整理现有的proof_graph的代码，整理成一个类函数，说明现在的功能及节点中存储的信息，之后按我的要求添加更多存储信息（辅助点信息、依赖关系）

date: 0925
- [x] 将schema_visualizer.py中的可视化功能复制到新的proof_graph中，整理现有的绘制规则，在我的要求下进行修改
- [x] 整理现在的类函数代码和所有脚本文件，梳理代码，去除多余的函数，修改后我来进行测试，确认没问题之后进行下一步开发
- [x] 参考schema_miner.py和mine_schemas.py重新设计一个子图提取的管线，只处理包含辅助点的题目；给定输入proof_graph后，从结论节点出发，向上挖掘，最终得到的子图为入度为0的节点都是fact node，出度为0的节点为结论节点。这部分功能保存在一个python文件中，在scripts目录下再保留一个脚本文件用来调用这个功能，输入就是json格式的数据，存放在类似r07_expanded_problems.results.json中，输出的格式也是json格式文件和得到的子图的可视化渲染结果。
- [x] 调整绘图的细节：1. 像schema_visualizer.py中一样，在图片左上角添加一个“前提-> 结论”的标签； 2. 现在的很多结果中节点的间距，特别是层与层之间的间距太小，需要调整，可以将画布调大一些。
- [x] 现在的proof_graph_visualizer中的绘图功能中对节点的染色规则需要更新：先整理目前的绘制规则，然后按如下需求重新设定规则：对结论节点绘制成蓝色；其余所有fact node中，包含辅助点的fact node染成橙色，否则染成绿色；对前提（入度为0）的节点进行边框加粗。

date: 0926
- [x] 完全重做extract_aux_subgraph.py以及调用的类函数，类函数改成aux_extractor.py，脚本函数改成extract_aux_graph.py，这个类函数只用来判断证明过程中aux_points是否是空的，只保留非空的证明结果，然后extract_aux_graph.py输入json文件，进行筛选后输出到一个带_aux后缀的json文件中，并且完全参照plot_proof_graphs.py的使用方法对这个带aux后缀的json文件进行可视化，最终输出到proof_graphs目录下
- [x] 添加一个新的类函数代码graph_pruner.py和一个脚本代码prune_graphs.py，按如下规则进行证明图的修剪：对每个规则节点进行判断，如果指向它的fact node全部都是题目的前提（在图中对应加粗边框的fact node），且与它相连的所有fact node都是不包含辅助点的fact node（在图中对应绿色节点的前提），则删去这个规则节点及与周围fact node相连的边；将它指向的fact node改为题目的前提，并检查是否有前提节点没有与任何规则节点相连，如果有则也删去这个fact node，迭代删减直到没有符合条件的规则节点出现位置。输出结果方面，我需要输出的格式和输入的格式尽可能保持一致，仍然能通过proof_graph_visualizer进行可视化，并且包含aux_points的信息。

date: 0927
- [x] 参考schema_visualizer.py，为proof_graph_visualizer添加legend模式
- [x] 将现在的extract_aux_graph.py和prune_graphs.py两个脚本合并成一个新的脚本，可以实现对run_batch.py的输出进行筛选 + 修剪的功能。并且我希望能够添加一个开关，将每道筛选后的题目与剪枝后的结果绘制的图像放在一张大图中
- [x] 我希望能够并行处理不同的题目，为此我需要将proof_graph的运行逻辑进行修改，不再将不同的题目组成一张大的graph进行处理。为了解决这个问题，我希望可以创建一个额外的proof_graph类，叫做single_proof_graph，用来代替之前的proof_graph的功能，先用添加的方式适配extract_aux_graph.py prune_graphs.py 和filter_and_prune这几个脚本的功能，我测试后确认没问题了再开始移除proof_graph的调用，并添加多进程处理题目的功能。
- [x] 在proof_graph_visualizer中添加一个新功能，在图片的右下角标注出题目中的辅助点信息，写法类似于aux_points: m, n这样，在右上角的predicate展示中将辅助点加粗表示
- [x] 将输出的proposition中点的名称重命名，保持对应关系的情况下从a开始逐个命名，并且输出格式改成rule.txt中的格式，比如para a b c d, para m n a b, coll m a d, coll n b c, ncoll a b c => eqratio m a m d n b n c，相应在json文件中的内容也改成这个格式。

date: 1009
- [x] 创建一个脚本，名称为rename_and_deduplicate.py，用来整理前面输出的\*_aux_pruned.json文件：1. 提取其中的proposition_rule条目；2. 对提取的proposition_rule进行去重，要求对不同的字母命名但是相同的顺序的情况（如cong a b c d, coll a b e f与cong r t c d, coll r t e f）进行去重，重复结果写在duplicated_rules.txt文件中，去重后的rules写在\*_rules.txt文件中，格式为单行：r00id，双行是对应的rule
- [x] 整理现有的脚本与相应的类函数代码，与文档进行比对，列出所有的差异后按照我的要求进行文档的更新
- [x] 将rename_and_deduplicate.py更名为extract_rules.py，修改当前规则：只能对给定参数的具体文件进行rule的提取，而不是读取多个 *_aux_pruned.json，提取results[].proposition_rule。并增加一个新的功能，对于一个rule，比如para a b c d, perp a b b c, cong a b b c, sameclock a b c a c d, eqangle a b b c c d a d => simtrir a b c a d c，进行一个检测：=>右侧的premise中包含的点如果不在左侧任意一个premise中，则跳过检查这个rule.

date: 1010
- [x] 我希望拓展filter_and_prune.py的输入格式，将其它脚本生成的数据传给filter_and_prune.py进行处理，它其中一条内容的数据格式是这样的：
  {"n_clauses": 5, "fl_problem": "a b c d = r_trapezoid a b c d; e f g = triangle e f g; h i j = risos h i j; k = on_pline0 k i b f, on_dia k b h; l = on_circle l j a, on_circle l f h; m = eqdistance m j g h, on_circum m f h e; n = on_tline n e i c, angle_mirror n k g b; o = shift o h i a; p q = square d k p q; r = on_tline r b e l, on_tline r j p q; s = angle_mirror s j h d, eqangle3 s r a e f m; t = on_aline0 t a i r e b d n, eqdistance t r p g; u = on_circle u l b, angle_mirror u t g n ? simtrir d k p d q p", "nl_problem": "", "n_proof_steps": 10, "llm_input": "<problem> a : ; b : ; c : ; d : para a b c d [000] perp a b a d [001] ; e : ; f : ; g : ; h : ; i : ; k : para b f i k [002] perp b k h k [003] ; l : cong a j j l [004] cong f h f l [005] ; m : cong g h j m [006] cyclic e f h m [007] ; n : perp c i e n [008] eqangle b g g k g n b g [009] ; o : cong a i h o [010] cong a h i o [011] ; p : perp d k k p [012] cong d k k p [013] ; q : para d k p q [014] para d q k p [015] ; r : perp b r e l [016] perp j r p q [017] ; s : eqangle d h h j h s d h [018] eqangle a s e m r s e f [019] ; t : eqangle a i b d e r n t [020] cong g p r t [021] ; u : cong b l l u [022] eqangle g n g t g u g n [023] ? simtrir d k p d q p </problem>", "llm_output": "<aux> x00 j : perp h i h j [024] cong h i h j [025] ; </aux> <numerical_check> sameclock d k p d p q [026] ; sameclock d k p h j i [027] ; sameclock h i j h i j [028] ; </numerical_check> <proof> eqangle d k k p p q d q [029] a01 [014] [015] ; eqangle d k h i k p h j [030] a01 [012] [024] ; eqratio d k h i k p h j [031] a00 [013] [025] ; simtri d k p i h j [032] r62 [030] [031] [027] ; eqangle d p i j k p h j [033] r52 [032] ; eqratio h i h j i j i j [034] a00 [025] ; simtrir h i j h j i [035] r61 [034] [028] ; eqangle h i i j i j h j [036] r53 [035] ; eqangle d p k p p q d p [037] a01 [033] [036] [014] [012] [024] ; simtrir d k p d q p [038] r35 [029] [037] [026] ; </proof>", "llm_input_renamed": "<problem> a : ; b : ; c : ; d : ; e : perp a d d e [000] cong a d d e [001] ; f : para a d e f [002] para a f d e [003] ? simtrir a d e a f e </problem>", "llm_output_renamed": "<aux> x00 g : perp b c b g [004] cong b c b g [005] ; </aux> <numerical_check> sameclock a d e a e f [006] ; sameclock a d e b g c [007] ; sameclock b c g b c g [008] ; </numerical_check> <proof> eqangle a d d e e f a f [009] a01 [002] [003] ; eqangle a d b c d e b g [010] a01 [000] [004] ; eqratio a d b c d e b g [011] a00 [001] [005] ; simtri a d e c b g [012] r62 [010] [011] [007] ; eqangle a e c g d e b g [013] r52 [012] ; eqratio b c b g c g c g [014] a00 [005] ; simtrir b c g b g c [015] r61 [014] [008] ; eqangle b c c g c g b g [016] r53 [015] ; eqangle a e d e e f a e [017] a01 [013] [016] [002] [000] [004] ; simtrir a d e a f e [018] r35 [009] [017] [006] ; </proof>"}
  我希望根据取其中llm_input_renamed和llm_output_renamed的内容进行处理。你首先检查一下这件事情是否可行，这部分内容是否完全够用，如果不够用的话列出缺少的信息，我来决定后续怎么做；如果够用，制定改造filter_and_prune.py的计划

date: 1011
- [x] 将filter_and_prune.py中旧格式处理的部分代码移除，只保留处理新格式代码的功能；将filter_and_prune.py和extract_rules.py两个脚本合并成同一个，去除中间的\*_aux.json中间文件，可选保留\*_aux_prune.json文件，直接用filter_and_prune.py的结果给extract_rules.py处理。
- [x] 现在filter_and_prune.py脚本的流程是什么，我在确认流程后决定是否对现在的流程进行调整
- [x] 将filter_and_prune.py脚本的功能代码提取成类函数，存储在data_discovery目录下，脚本文件改成只用来调用类函数的接口
- [x] 在filter_and_prune_engine.py中添加一步筛选，放在“筛选含aux”和“修剪”两步行为之间，规则如下：将每个题目的问题部分（llm_input_renamed中问号之前的部分）和辅助构造部分（llm_output_renamed中<aux> </aux>之间的内容）组成字符串计算其哈希值，如果存在重复的，则跳过该条内容。
- [x] 现在filter_and_prune.py的修剪规则是什么，我会考虑修改具体的规则（已补充“兄弟规则-辅助点牵连”保护条件：若 R 的任一前驱 p 还指向另一个规则 R' 且 R' 的前驱中含辅助点，则不删除 R）

date: 1015
- [x] _normalize_input_object函数，对于000条目是类似rconst a b a c 1/2 [000]的情况，调用convert_list函数处理的结果跳过了这个条目，导致normalized_results中对应的题目从001开始，即analysis: coll a b d [001]。核实这个情况并进行检查修改。
- [x] 现在绘图的编号和生成的rule之间是否能保持统一关系？我希望生成的图片刚好和rule的编号一一对应

date: 1020
- [x] 我删除了很多不必要文件，请根据现在的目录树结构，对文档内容进行精简
- [x] 进一步去重：现在的结果中会存在这样的重复内容：
  r0007
  perp a b a c, eqangle a b a d a d a c, coll a b e, perp a b e d => cong a e e d
  r0008
  perp a b a c, eqangle a b a d a d a c, coll a c e, perp a c e d => cong a e e d
  这种内容无法去重的原因在于没有提前告知在perp中前两个点的顺序可以互换，但是如果记录每个点的映射关系实在太复杂了，所以我希望能够直接根据每个rule中包含的predicate和conclusion的名称直接进行粗去重，比如上面两个rule的名称都是perp*2+eqangle*1+coll*1+con:cong*1，所以就进行去重。请设计一个方案实现这个功能
- [x] 我希望能够获得一个shell命令，用来直接过滤掉指定文件中包含aconst、rconst的条目，包括它的编号及内容（即包括指定谓词的行和其上一行）
    awk 'NR%2==1{ id=$0; next }
     {
       if ($0 ~ /(^|[^[:alnum:]_])(a|r)const([^[:alnum:]_]|$)/) next;
       print id ORS $0
     }' outputs/geometry_clauses14_samples100k_aux_pruned_rules.txt > outputs/geometry_clauses14_samples100k_aux_pruned_rules.filter.txt
    jq '.results | map(select(.success? == true))' /c23474/home/math/dzt/Newclid/outputs/all_problems_unsolved.results.json > /c23474/home/math/dzt/Newclid/outputs/all_problems.success.results.json
- [x] 我希望能够获得一个shell命令，统计*_rule.txt(比如outputs/geometry_clauses13_samples1M_aux_aux_pruned_rules.txt)中每条rule的结论predicate的分布情况
    sed -n 's/.*=>[[:space:]]*\([[:alnum:]_][[:alnum:]_]*\).*/\1/p' outputs/geometry_clauses13_samples2M_aux_pruned_rules.filter.txt \
    | tr '[:upper:]' '[:lower:]' \
    | awk '{c[$1]++; total++} END{for (k in c) printf "%d %s %.2f%%\n", c[k], k, (c[k]*100.0)/total}' \
    | sort -k1,1nr -k2,2

date: 1024

- [x] 整理了题目集，得到了两个具体的测试集，在飞书上的对应测试也搭建好了

date: 1025

- [ ] 之前生成的所有数据在新的测试集上进行测试
- [ ] 对数据集进行规则提取

- [ ] 根据得到的rule的渲染图片分析每条rule的正确性，判断是否存在前期的错误情况/ddar中的问题

- [ ] 重构代码并重新更正文档
- [ ] 检查现在的筛选结果，看一下筛选掉的条目是否正确/剩余的条目是否是正确的命题/添加新的筛选逻辑使得剩余的条目都是正确命题/进行新一轮测试100