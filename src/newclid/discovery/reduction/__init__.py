"""Part 2: 规则规约子包。

输入 Part 1 产出的 `extracted_rules.jsonl`，输出最小基底规则集 `extracted_rules.txt`。
两阶段串行（均可独立启用）：
  Stage 1: Seed Reduction —— 按 seed 分组，组内贪心淘汰被 subsume 的规则。
  Stage 2: Divide-and-Conquer —— Phase 1 分块规约 + Phase 2 流水线合并。

模块映射（伪代码 §5 / §7.2）：
- `orchestrator.py`          —— Part 2 整体编排 + `load_rules_from_jsonl`。
- `subsumption_tester.py`    —— 基础规约方法：CSolver subsume_test。
- `seed_reducer.py`          —— Seed 分组规约。
- `divide_conquer_reducer.py`—— 分治规约。
- `generality_scorer.py`     —— 通用度评分（`-n_premises`）。
"""
