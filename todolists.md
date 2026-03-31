## Prompt（要求）

你是一个认真的编程专家，协助我完成本项目。请严格遵循以下要求：

1) 在每次开始任务前，先阅读并对齐项目说明与代码说明：`proj_doc.md`（视为当前权威规范）。
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
13) 每次任务完成后，询问我是否更新本次完成的复选项内容具体说明与 `proj_doc.md` 中的内容，由我确认是否更新。
14) data的内容是作为记录使用，你不需要在意。
15) 新建脚本文件时，输入输出路径等配置应通过在脚本中硬编码路径参数传递，同时保留命令行参数（如argparse）传递的可选项，便于直接在终端执行。

---

date: 1114

- [x] 检查generate.py代码，整理它实现生成的逻辑，理解后按我的后续要求，对clause生成部分进行截断，改成准备随机生成geometry configuration，将configuration保存下来，然后生成所有可能的goal

date: 1119
- [x] 我需要把前面的到的结果：类似这种：
    {"configuration": "a@0.23491053908945692_-0.27329364388431454 b@0.6726591206246719_0.6516514629948335 c@0.783913031903306_1.2848644157683071 d@-0.33890925011265494_0.016649326120028785 = eq_quadrangle a b c d; e@1.31378786523219_0.6995055032932629 = on_circle e b c; f@1.0511144976541837_0.9942344074963948 = angle_bisector f c b e; g@1.4314028055255188_-0.18654154090878744 = lc_tangent g b f; h@0.8233736216828985_-0.05450371794279779 = on_dia h g f", "unsolved_goals": [{"goal_str": "cyclic a c d f", "predicate": "cyclic"}, {"goal_str": "eqangle a c f a d f", "predicate": "eqangle"}, {"goal_str": "eqangle c a f c d f", "predicate": "eqangle"}, {"goal_str": "eqangle d a f d c f", "predicate": "eqangle"}], "config_id": 4}
    转化成这样的题目：
    a b = segment a b; g1 = on_tline g1 a a b; g2 = on_tline g2 b b a; m = on_circle m g1 a, on_circle m g2 b; n = on_circle n g1 a, on_circle n g2 b; c = on_pline c m a b, on_circle c g1 a; d = on_pline d m a b, on_circle d g2 b; e = on_line e a c, on_line e b d; p = on_line p a n, on_line p c d; q = on_line q b n, on_line q c d ? cong e p e q
    也就是说：1. 提取出configuration中去掉坐标的部分；2. 将每个unsolved_goals中的goal_str拼接到configuration后面，形成一个新的题目字符串，注意有一些configuration后面的unsolved_goals可能是空的，这种需要跳过，转化好的题目整理到一个文件中，按第一行是编号，第二行是题目的形式组织，编号按输入的configuration_clauses{n}_samples{N}.jsonl文件中对应的行号，与goal_str的顺序组成，比如1_0, 1_1, 2_0等，文件名为configuration_clauses{n}_samples{N}_problems.jsonl，保存在datasets/problems的目录下。在src/newclid/generation目录下创建一个新的python文件problem_convert.py实现这个功能。
    - [x] 我希望为evaluation过程中添加结果的保存功能，目前的猜想是对lm.py文件中添加证明结果的输出过程，将解题的结果写入指定内容，这部分内容我之前在run_batch.py这个脚本中实现过，我希望你参考两个文件的内容，帮我指定合适的计划

date: 1124
- [x] 我现在需要对datasets/success_proofs目录下的结果与configuration进行组合，得到若干条完整的题目-结果的证明轨迹，为此我需要你帮我设计一个python脚本文件prooftrace_combine.py，他会输入一个proof_info文件和一个configuration_info文件，proof_info是一个json文件，它的单个条目是如下格式：
    [
    "16_0",
    {
      "problem": "a b c d = iso_trapezoid a b c d; e = on_tline e b d c, on_pline e c d a; f = on_dia f c b; g = angle_bisector g f a d, on_tline g c f e; h = s_angle c d h 165o, on_tline h b c e ? cong a c b d",
      "augmented_problem": "a b c d = iso_trapezoid a b c d; e = on_tline e b d c, on_pline e c d a; f = on_dia f c b; g = angle_bisector g f a d, on_tline g c f e; h = s_angle c d h 165o, on_tline h b c e; i = eqdistance i b c d, eqdistance i d b c ? cong a c b d",
      "llm_renamed_input": "<problem> a : ; b : ; c : ; d : para a b c d [000] cong a d b c [001] ? cong a c b d </problem>",
      "llm_renamed_output": "<aux> x00 e : cong b e c d [002] cong b c d e [003] ; </aux> <numerical_check> sameclock a c d b c d [004] ; sameclock b c e c d e [005] ; sameclock a d e a d e [006] ; </numerical_check> <proof> eqratio b c c e d e c e [007] a00 [003] ; eqratio b e c d c e c e [008] a00 [002] ; simtri b c e d e c [009] r60 [007] [008] [005] ; eqangle b e c d c e c e [010] r52 [009] ; para a b b e [011] a01 [010] [000] ; coll a b e [012] r28 [011] ; eqratio a d a e d e a e [013] a00 [001] [003] ; simtrir a d e e d a [014] r61 [013] [006] ; eqangle a d a e a e d e [015] r53 [014] ; eqangle b c c e d e c e [016] r52 [009] ; eqangle a d c d c d b c [017] a01 [012] [015] [016] [000] ; eqratio a d b c c d c d [018] a00 [001] ; simtrir a c d b d c [019] r63 [017] [018] [004] ; eqratio a c b d c d c d [020] r53 [019] ; cong a c b d [021] a00 [020] ; </proof>"
    }
    ],
    configuration_info是一个jsonl文件，它的每行记录了一个条目，格式如下：
    {"configuration": "a@-0.2942234483090008_0.9099849333753868 b@-0.7729909653321325_-0.16758609636567573 c@0.122517945825804_-1.1211627675752218 d@1.0136753891376666_0.8845820035442021 = iso_trapezoid a b c d; e@1.43041678327247_-1.1465656974064062 = on_tline e b d c, on_pline e c d a; f@0.16892559725752898_-0.21587124475436736 = on_dia f c b; g@0.978627672688719_0.039234043238260866 = angle_bisector g f a d, on_tline g c f e; h@-0.7960295521971309_-1.3537540375200543 = s_angle c d h 165o, on_tline h b c e", "unsolved_goals": [{"goal_str": "cong a c b d", "predicate": "cong"}], "config_id": 16}
    我需要根据proof_info中每个条目的id（如上面的例子中id就是16_0），找出configuration中对应行的数据，合成出一个包含configuration和proof的轨迹，保存在制定的输出目录下的jsonl文件中，每一条数据包括如下信息：
    1. problem: proof_info中的problem字段
    2. points_coordinates: configuration中的各点的坐标信息
    3. aux_construction: proof_info中augmented_problem与problem的差异部分(即新增的辅助构造)
    4. llm_renamed_proof: proof_info中的llm_renamed_input字段和llm_renamed_output字段合成的proof
    5. raw_rule: proof_info中llm_renamed_input字段中，每个[0id]前面的predicate（比如"para a b c d", "cong a d b c"）用", "连接，与" ? " 后面的结论predicate组成的结构，用" => "连接，比如上面的例子中，得到的raw_rule就应该是"para a b c d, cong a d b c => cong a c b d"

date: 1127  
  - [x] 我希望对proof_trace的结果进行去重，规则是先根据predicate的名称排序，格式化raw_rule部分的内容后进行去重，我希望通过更新proof_combine.py的代码来实现这个功能，在extract_raw_rule这个函数中进行修改

date: 0105
- [x] 实现基于等价性的最小规则集提取脚本 `src/newclid/proof_scout/get_minimal_rules.py`
  - **目标**：通过DirectSolver检测规则等价性，提取最小独立规则集
  - **算法**：
    1. 加载基础规则库（rules.txt，31条）作为初始规则库C
    2. 加载提取的规则列表R和对应的重建题目P
    3. 初始化独立规则集I=[]，等价关系E={}
    4. 对于每条规则r_i及其对应题目p_i：
       - 使用当前规则库C尝试求解p_i
       - 若成功：r_i可被推导，通过解析证明过程确定归属关系
         - 调用write_proof_steps()或获取证明步骤
         - 检查证明中用到的规则名称，筛选包含"sub"的规则名
         - 将r_i归属到证明中用到的独立规则（如有多个则记录所有相关规则）
       - 若失败：r_i是独立规则，将r_i加入C和I，初始化E[r_i]=[]
    5. 输出独立规则集和等价关系映射
  - **输入文件**：
    - `datasets/extracted_rules/c10s50/c10s50_rules_norm.txt` - 提取的规则（两行一组：规则名+规则内容）
    - `datasets/rebuild_problems/c10s50_rules_rebuild.txt` - 重建的题目
    - `src/newclid/default_configs/rules.txt` - 基础规则
  - **输出文件**：
    - `datasets/extracted_rules/c10s50/rules_minimal.txt` - 最小独立规则集
    - `datasets/extracted_rules/c10s50/rules_equivalence.json` - 等价关系映射
  - **实现要点**：
    - 复用DirectSolver API和test_direct_solver.py中的解析逻辑
    - 动态更新临时规则文件（每次添加新独立规则后更新）
    - 通过证明步骤中的规则名（含"sub"）确定等价归属
    - 超时设置：3600秒/题
    - 详细日志记录（进度、求解结果、归属关系）

date: 0106
- [x] 实现并行版本的最小规则集提取脚本（改造 `get_minimal_rules.py`）
  - **目标**：通过分治+合并策略实现多进程并行提取，提升处理效率
  - **算法设计（三阶段）**：
    1. **分割阶段（主进程）**：
       - 加载待过滤规则集R（共N条）
       - 按规则数量均匀切割成 max_workers 个互不包含的子规则集 R_1, R_2, ..., R_k
       - 为每个子进程创建独立的临时工作目录
    2. **并行处理阶段（子进程）**：
       - 每个子进程独立加载基础规则库C
       - 对分配的子规则集 R_i 执行串行最小规则集提取（复用现有逻辑）
       - 输出子进程的独立规则集 I_i 和等价关系 E_i 到临时目录
    3. **合并阶段（主进程）**：
       - 收集所有子进程的独立规则集 I_1, I_2, ..., I_k
       - 合并为候选规则集 I_all = I_1 ∪ I_2 ∪ ... ∪ I_k
       - 对 I_all 再执行一次串行最小规则集检查，滤掉跨进程可互相推导的规则
       - 合并所有子进程的等价关系映射，更新归属到最终的独立规则
       - 输出最终的最小规则集和等价关系映射
       - 清理所有中间临时文件和目录
  - **新增配置参数**：
    - `MAX_WORKERS = 8` - 并行进程数（默认8，可调整为16）
    - `PARALLEL_MODE = True` - 是否启用并行模式（False则回退到串行）
  - **输入输出文件**：与串行版本保持一致
  - **实现要点**：
    - 使用 `concurrent.futures.ProcessPoolExecutor` 进行并行
    - 每个子进程有独立的临时规则文件，避免竞争
    - 子进程结果通过临时JSON文件传递，避免进程间通信开销
    - 主进程合并阶段需重新构建规则库并验证
    - 详细日志记录各阶段进度和耗时
    - 异常处理：子进程失败时记录错误但不中断整体流程

- [x] 实现规则折叠脚本 `src/newclid/proof_scout/fold_rules.py`
  - **目标**：将具有相同前提的多条规则折叠为一条规则，合并其结论
  - **算法**：
    1. 加载规则文件（两行一组：规则名+规则内容）
    2. 解析每条规则，提取前提部分和结论部分（以 ` => ` 分隔）
    3. 对前提部分进行标准化处理（按字母顺序排序各谓词），作为分组键
    4. 将具有相同标准化前提的规则分组
    5. 对于每组规则：
       - 保留第一条规则的规则名
       - 将所有规则的结论用 `, ` 连接合并
       - 生成折叠后的规则：`{原前提} => {结论1}, {结论2}, ...`
    6. 输出折叠后的规则文件
  - **命令行参数**：
    - `--input` - 输入规则文件路径（如 `datasets/extracted_rules/c10s200k/rules_minimal.txt`）
    - `--output` - 输出折叠后规则文件路径（如 `datasets/extracted_rules/c10s200k/rules_folded.txt`）
  - **实现要点**：
    - 使用argparse解析命令行参数
    - 前提标准化：对前提中的各谓词按字典序排序，确保相同前提的规则能正确匹配
    - 保持规则内各参数的原始顺序，仅对谓词排序
    - 结论合并时去重（避免重复结论）
    - 日志记录：统计原始规则数、折叠后规则数、合并比例
    - 输出格式与输入格式一致（两行一组）
  - **示例**：
    - 输入规则：
      ```
      39sub_0
      cong a b c b, midp d e f, para a e f c, perp a e a c => eqangle a b a d c d c b
      40sub_0
      cong a b c b, midp d e f, para a e f c, perp a e a c => para a e b d
      42sub_0
      cong a b c b, midp d e f, para a e f c, perp a e a c => perp a c b d
      ```
    - 输出规则：
      ```
      39sub_0
      cong a b c b, midp d e f, para a e f c, perp a e a c => eqangle a b a d c d c b, para a e b d, perp a c b d
      ```
date: 0107
    - [ ] 辅助构造的选取/生成数据应该如何优化
    - [ ] 匹配规则应该如何进一步优化，使得效率得到提升