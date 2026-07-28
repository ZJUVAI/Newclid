"""Discovery Pipeline 包入口。

从 JSONL 合成数据出发，串行执行：
  Part 1: Rule Extraction —— 图修剪 → 命题提取 → 后处理 → 题目还原 → 规范化 → 去重 → JSONL 落盘
  Part 2: Reduction       —— Seed 分组规约 → 分治合并规约 → 最终最小基底规则集

对外仅暴露包级 API（如 `run_pipeline`）；具体编排细节见 `pipeline.py`。
"""
