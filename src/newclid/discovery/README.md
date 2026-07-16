# Discovery Pipeline 模块说明

本文档描述 `src/newclid/discovery/` 下**当前已实现并在实际流程中被调用**的代码。部分文件中存在设计中但尚未实现的占位代码（函数体为 `raise NotImplementedError`），这些不在本文档的描述范围内，会在最后单独列出。

## 1. 整体架构

入口链路：

```
python -m newclid.discovery --config <path.json>
  __main__.py -> main.py: main()
  -> pipeline.py: run_pipeline(config_path)
```

`run_pipeline` 是顶层调度器，按配置依次执行两个阶段：

1. **Part 1（提取, extraction）**：把原始的“合成几何证明”数据，转换为标准化、去重后的几何推理规则。
2. **Part 2（约简, reduction）**：在 Part 1 输出的规则集合上做冗余消除，得到一个尽量小、但仍能推出所有原始结论的规则基（rule basis）。

两个阶段都可以通过配置文件的 `part1_extract.enabled` / `part2_reduction.enabled` 独立开关；未显式给出 `part2_reduction.input` 时，Part 2 会自动以 Part 1 的输出作为输入，实现两阶段串联。

流程结束后，`run_pipeline` 会把两阶段的统计信息写入 `{output_dir}/pipeline_summary.json`。

**输入**：JSONL，每行一条合成证明记录，包含 `seed`、`fl_problem`（构造语言，见项目根 CLAUDE.md 的“几何题目数据格式”）、`llm_input_renamed`（`<problem>` 标签，含前提与目标）、`llm_output_renamed`（`<aux>`/`<numerical_check>`/`<trivial>`/`<proof>` 标签，含证明步骤）。

**输出**：`{output_dir}/part2/reduced_rules.jsonl` + `.txt`，每条是形如 `premise1, premise2, ... => conclusion` 的通用几何推理规则。

## 2. 文件总览

```
discovery/
├── __main__.py            CLI 入口（python -m newclid.discovery）
├── main.py                 解析 --config 参数，调用 pipeline.run_pipeline
├── pipeline.py              顶层调度器：Part 1 主流程 + 触发 Part 2
├── config.py                默认配置、配置加载/合并/校验、输出路径解析
├── data_models.py           各阶段间传递的数据结构（dataclass）
├── extraction/               Part 1：提取阶段
├── reduction/                 Part 2：约简阶段
└── utils/                      两阶段共用的工具函数
```

## 3. 配置与数据模型

### config.py

- `DEFAULT_CONFIG`：三个顶层分区。
  - `global`：`output_dir`、`n_workers`、`save_intermediates`。
  - `part1_extract`：`enabled`、`input`、`output`、`decompose`、`merge_eqpoints`、`normalize`、`extract_n_workers`、`normalize_n_workers`、`draw_dir` 等。
  - `part2_reduction`：`enabled`、`input`、`output`、`max_premises_drop`、`n_workers`、`use_ray`、`chunk_size`、`csolver_config_path`。
- `load_config(path)`：读取 JSON 文本 -> 过滤 `//` 注释行 -> `json.loads` -> 递归删除 `_comment*` 字段 -> 与 `DEFAULT_CONFIG` 深度合并 -> 校验 `output_dir`、（若 Part 1 启用）`part1.input`。
- `resolve_output(explicit, output_dir, sub_dir, default_filename)`：统一的输出路径解析逻辑——显式给了路径就用显式路径，否则用 `output_dir/sub_dir/default_filename`。各阶段写文件前都调用它。

### data_models.py（实际被使用的部分）

- `PredicateInstance(predicate, args)`、`Point(name, x, y)`：基础几何类型。
- `FactNode` / `RuleNode`：证明图的节点类型，由 `extraction/graph_manager.py` 构建。
- `PropositionRecord(proposition_id, seed, index_in_seed, premises, conclusion, points)`：Part 1 中“命题提取”阶段的输出。
- `NormalizedRule(rule_id, seed, index_in_seed, rule_text, rename_map, points)`：Part 1 中“标准化”阶段的输出，即 Part 1 的最终产物，也是 Part 2 的输入。
- `PipelineSummary`：贯穿全程的统计对象，`pipeline.py` 调用其 `record_part` / `to_dict` 写最终汇总。

> 注：`Proposition`、`RuleWithSource`、`ExtractionRecord`、`ExtractionResult`、`GraphNode`、`RenderedSubgraph`、`PrunedItem`、`SeedReductionStats`、`DivideConquerStats`、`ReductionResult` 等 dataclass 也定义在此文件中，但属于未落地的设计（对应 `extraction/engine.py` 等占位模块），实际执行路径中不会产生这些对象，详见第 6 节。

## 4. Part 1：提取阶段（extraction/）

由 `pipeline.py` 中的 `run_part1` 直接串联调用（不经过任何“engine”类），大致步骤：

1. **建图**：`graph_manager.build_proof_graphs` 读取/抽样输入记录（`limit`/`sample`），对每条记录调用 `parsing.py` 里的纯文本解析函数（`extract_tag_content`、`parse_fact_segments`、`parse_proof_step`、`extract_points`、`extract_goal`、`extract_aux_points`），构建出一个 `SingleProofGraph`：包含事实节点（`FactNode`）、规则节点（`RuleNode`）、边、坐标点、目标结论、辅助点等信息。
2. **单步化简**：`SingleProofGraph.simplify_single_step()` 折叠只有单个前提的“平凡推导链”。
3. **按辅助点拆分（可选，`decompose=True` 时）**：`decomposer.decompose_by_aux(graph)` 把一张证明图按辅助点拆成多张子图，只保留触达该辅助点的部分，并做一次结构闭包吸收多余前提。
4. **可视化（可选，配置了 `draw_dir` 时）**：`visualizer.draw_proof_graph(graph, out_path)` 用 matplotlib/networkx 把证明图渲染成 PNG，按节点角色着色、按 DAG 分层布局。仅用于调试，不影响主流程数据。
5. **命题提取**：`proposition_extractor.extract_propositions(graphs)` 把每张（子）图压缩为一条 `PropositionRecord`：非辅助的给定前提集合 -> 目标结论，附带点坐标。写出 `propositions.jsonl`。
6. **等量点合并（可选，默认开启，`merge_eqpoints=True`）**：`eqpoint_merge.merge_eqpoints_batch(props)` 用并查集把 `eqpoint a b` 这类前提所指代的、数值上重合的点合并为代表点，并剔除合并后退化（`_is_degenerate`）的命题。
7. **标准化 + 去重**：`normalizer.normalize_and_dedup(props)`：
   - 调用 `predicate_rewrite.rewrite_predicate` 把语义上等价但形式更复杂的谓词改写为更简单的规范形式（例如某些 `para` 情形改写为 `coll`，某些 `eqangle` 模式改写为 `cyclic`/`cong`），依据的是预先计算好的置换群对称轨道。
   - 调用 `utils/symmetry.normalize_predicate` 按每个谓词自身的对称性类别（无序、成对交换、eqangle/eqratio 置换群轨道、三角形顶点循环、首参数固定等）规范化参数顺序。
   - 把点按首次出现顺序重命名为 A、B、C……。
   - 对前提排序、按规范化后的文本去重（保留 seed/index 更小的一条）。
   - 输出 `normalized_rules.jsonl`：每行是 `NormalizedRule`（rule_id、seed、index_in_seed、rule_text、rename_map、points）。

以上 1–6 步存在并行版本：当 `extract_n_workers > 1` 时，`pipeline.run_part1` 改用 `parallel_extract.extract_propositions_parallel`，其内部 `_process_chunk` 把建图/化简/拆分/提取/等量点合并合并为一个按 chunk 并行的任务，基于 `reduction/parallel.py` 的 Ray 调度工具（`ensure_ray`、`run_bounded`）。标准化阶段自身也有独立的并行版本 `normalizer.normalize_and_dedup_parallel`（配置 `normalize_n_workers`），同样复用 `reduction/parallel.py`。

若关闭 `normalize`，Part 1 的最终产物就是 `propositions.jsonl`（未标准化）。

## 5. Part 2：约简阶段（reduction/）

由 `pipeline.py` 的 `run_part2` 委托给 `reduction/orchestrator.py` 的 `run_part2(cfg, output_dir, input_path)` 执行，输入是 Part 1 产出的 `normalized_rules.jsonl`：

1. **加载规则**：`subsumption_tester.load_rules(jsonl_path)` 把每行 JSON 解析为一个轻量的 `RuleItem`（rule_id、seed、rule_text、points、premises、goal、premise_count），解析逻辑在 `utils/rule_parser.py` 的 `parse_predicate`/`split_rule_text`。
2. **前提数预过滤（可选）**：丢弃 `premise_count >= max_premises_drop`（默认 8）的规则，减少后续约简的计算量。
3. **按 seed 分组贪心约简**：`seed_reducer.reduce_by_seed(rules, n_workers, use_ray, config_path)` 按来源 `seed` 分组，组内调用 `greedy_reduce`：
   - 按前提数从少到多排序；
   - 依次尝试把每条规则加入当前的 `basis` 列表——如果它能被 `basis` 中已有规则推出（即冗余），就丢弃，否则保留；
   - 可推导性判断由 `SubsumptionTester.is_derivable(target, sources)` 完成：用 `newclid.api.CSolver`，把 `sources` 作为 `custom_rules` 喂给求解器，检查能否推出 `target` 的目标（这是对底层 C++ DDAR 求解器的真实调用，而非近似判断）。
   - 各 seed 分组之间通过 `reduction/parallel.py` 的 Ray 调度并行执行。
4. **合并同前提规则**：`seed_reducer.merge_same_premise(rules)` 把前提集合完全相同的多条规则合并成一条多结论规则。
5. **跨 seed 分治约简**：`divide_conquer_reducer.reduce(rules, chunk_size, n_workers, use_ray, max_rounds=5, shrink_ratio=0.98, config_path, seed=42)`：反复对当前存活规则做随机打乱 -> 按固定 chunk 大小切块 -> 每块内并行跑 `greedy_reduce` -> 汇总幸存规则；直到规模收缩比例低于 `shrink_ratio` 或达到 `max_rounds` 或规则总数已能放入单个 chunk 为止。这一步用于消除按 seed 分组时无法发现的跨 seed 冗余。
6. **再次合并同前提规则**。
7. **写出结果**：`reduced_rules.jsonl`（结构化）+ `reduced_rules.txt`（仅 `rule_text` 逐行），即最终的最小规则基。中间产物（如启用 `save_intermediates`）包括 `premise_num_filtered.jsonl`、`seed_reduced.jsonl`、`divide_reduced.jsonl`。

### 关键组件

- **`subsumption_tester.py`**：`RuleItem` 数据结构 + `SubsumptionTester.is_derivable`，是整个约简阶段唯一的“规则是否冗余”判定原语，被 `seed_reducer.py` 和 `divide_conquer_reducer.py` 共用。
- **`seed_reducer.py`**：`greedy_reduce`（贪心核心算法，也被分治约简复用）+ `merge_same_premise`（同前提合并）+ `reduce_by_seed`（按 seed 分组的并行外壳）。
- **`divide_conquer_reducer.py`**：`reduce`，跨 seed 的迭代分治约简。
- **`parallel.py`**：`ensure_ray(n_workers)`、`run_bounded(remote_fn, task_args, inflight)`，通用的 Ray 并行调度工具，被 Part 1（`normalizer.py`、`parallel_extract.py`）和 Part 2（`seed_reducer.py`、`divide_conquer_reducer.py`）共用。
- **`orchestrator.py`**：`run_part2`，把以上组件串成完整的四步（过滤 -> 组内约简 -> 分治约简 -> 合并）并负责写文件，是 Part 2 的真正驱动函数。

## 6. utils/（两阶段共用工具）

- **`jsonl_io.py`**：实际被使用的只有 `write_jsonl`（`pipeline.py`、`parallel_extract.py` 用它写各阶段的 JSONL 输出）。
- **`rule_parser.py`**：`split_rule_text`、`parse_predicate`（被 `subsumption_tester.RuleItem.from_record` 使用）、`build_rule_text`（被 `normalizer.normalize_proposition` 使用）、`to_pipe_format`（被 `subsumption_tester.is_derivable` 用于构造喂给 `CSolver` 的 `custom_rules` 格式）。
- **`symmetry.py`**：`normalize_predicate(predicate)`，按谓词的对称性类别（无序参数、成对交换、eqangle/eqratio 置换群轨道、三角形顶点循环、首参数固定、sameside 特例等）规范化参数顺序，是 `normalizer.py` 规范化步骤的核心依赖。

## 7. 已定义但当前未接入实际流程的代码（供参考，不代表可用功能）

以下模块的函数体多为 `raise NotImplementedError`，或者虽已实现但没有被 `pipeline.py`/`orchestrator.py`/任何被调用模块引用，实际运行时不会执行：

- `extraction/engine.py`、`extraction/output_handler.py`、`extraction/rule_restorer.py`、`extraction/post_processor.py`：代表一套更精细的、以 `RuleExtractionEngine` 为中心的六步流水线设计（`step1_graph_prune -> step2_extract_propositions -> step3_post_process -> step4_restore_problems -> step5_normalize -> step6_7_dedup_and_dump`），但目前是未完成的占位代码，实际流程用的是 `pipeline.py` 中更直接的手写调度，不经过这套 engine。
- `reduction/generality_scorer.py`：`GeneralityScorer` 同样是占位实现；实际的“更通用（前提更少）优先保留”策略是直接内联在 `seed_reducer.greedy_reduce` 的排序键（按 `premise_count` 升序）里，没有走这个类。
- `utils/rule_parser.py` 中的 `parse_rule_text`、`collect_points_in_order`、`build_rename_map`、`rename_rule_text`、`rename_by_first_appearance`：已实现但目前只在文件自身的 `__main__` 自测里被调用，主流程未使用。`count_premises`、`extract_conclusion_predicate`、`has_missing_points` 是占位（未实现）。
- `data_models.py` 中的 `Proposition`、`RuleWithSource`、`ExtractionRecord`、`ExtractionResult`、`GraphNode`、`RenderedSubgraph`、`PrunedItem`、`SeedReductionStats`、`DivideConquerStats`、`ReductionResult`：对应上述未接入的设计，实际执行路径不会产生这些对象的实例。
</content>
</invoke>
