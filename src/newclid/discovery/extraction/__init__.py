"""Part 1: 规则提取子包。

从合成数据 JSONL 出发，通过 7 个 step 提取最小、规范化、去重后的规则集，并以 JSONL
落盘供 Part 2 使用。

模块映射（伪代码 §4 / §7.2，实现已合并部分相邻 step）：
- `engine.py`            —— 整体编排（Steps 1-7）+ Ray 并行控制。
- `graph_manager.py`     —— Step 1：证明图构建 + 图修剪。
- `proposition_extractor.py` —— Step 2：从修剪图提取 premises + conclusion。
- `post_processor.py`    —— Step 3：平凡谓词简化 + eqpoint 等价点合并。
- `rule_restorer.py`     —— Step 4：规则关联回原始题目信息。
- `normalizer.py`        —— Step 5：对称性规范化 + 签名生成。
- `output_handler.py`    —— Steps 6-7：SHA256 去重 + JSONL 落盘 + 辅助文件。
"""
