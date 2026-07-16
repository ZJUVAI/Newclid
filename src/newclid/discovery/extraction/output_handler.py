"""Steps 6-7: 规则去重与 JSONL 落盘（对应伪代码 §4.2 Steps 6-7）。

Step 6: SHA256 哈希去重。
Step 7: skip 过滤 → rule_id 分配 → JSONL 主输出 + 辅助文件。
"""

from __future__ import annotations

from typing import Any

from newclid.discovery.data_models import ExtractionRecord


# ---------------------------------------------------------------------------
# Step 6: 去重
# ---------------------------------------------------------------------------

def dedup_rules(
    normalized_rules: list[ExtractionRecord],
    external_seen_hashes: set[str] | None = None,
) -> tuple[list[ExtractionRecord], list[dict[str, Any]]]:
    """SHA256 哈希去重。

    Parameters
    ----------
    normalized_rules : list[ExtractionRecord]
        Step 5 输出的规范化记录。
    external_seen_hashes : set[str] | None
        外部已知的哈希集（可选，用于跨批次去重）。

    Returns
    -------
    (unique_entries, duplicates)
        unique_entries: 去重后保留的记录。
        duplicates: 去重溯源信息列表 [{
            "normalized_rule_text", "duplicate_pid", "duplicate_subgraph_id",
            "kept_pid", "kept_subgraph_id"
        }, ...]
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Step 7: 落盘
# ---------------------------------------------------------------------------

def dump_rules(
    unique_entries: list[ExtractionRecord],
    duplicates: list[dict[str, Any]],
    rule_skip_predicates: list[str],
    output_path: str,
    output_dir: str,
    save_intermediates: bool = True,
) -> tuple[str, int, int]:
    """将去重后的规则写入 JSONL 文件。

    1. 按 rule_skip_predicates 过滤结论谓词（默认跳过 aconst, rconst）。
    2. 分配 rule_id = f"r{i:08d}_{subgraph_id}"。
    3. 写入主 JSONL 文件（每行一个 JSON 对象）。
    4. 写入辅助文件：duplicated_rules.jsonl, skipped_rules.jsonl。

    Parameters
    ----------
    unique_entries : list[ExtractionRecord]
        去重后的记录。
    duplicates : list[dict]
        去重溯源记录。
    rule_skip_predicates : list[str]
        结论谓词跳过列表。
    output_path : str
        主 JSONL 输出路径。
    output_dir : str
        辅助文件输出目录。
    save_intermediates : bool
        是否写辅助文件。

    Returns
    -------
    (rules_file, kept_count, skipped_count)
        rules_file: 主输出文件路径。
        kept_count: 保留的规则数。
        skipped_count: 被跳过的规则数。
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# 编排函数（供 engine.py 调用）
# ---------------------------------------------------------------------------

def step6_7_dedup_and_dump(
    normalized_rules: list[ExtractionRecord],
    rule_skip_predicates: list[str],
    output_path: str,
    output_dir: str,
    save_intermediates: bool = True,
) -> tuple[str, int, int, list[dict[str, Any]]]:
    """Steps 6-7 的联合编排。

    Returns
    -------
    (rules_file, kept_count, skipped_count, duplicates)
    """
    raise NotImplementedError
