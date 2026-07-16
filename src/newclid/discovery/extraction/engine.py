"""Part 1 规则提取引擎：Steps 1-7 的整体编排（对应伪代码 §4.2）。

RuleExtractionEngine.run_part1_extract(input_path, output_path) 是 Part 1 的入口。
并行化基于 Ray，使用 bounded in-flight 控制内存。
"""

from __future__ import annotations

from typing import Any

from newclid.discovery.data_models import ExtractionResult


class RuleExtractionEngine:
    """Part 1 规则提取引擎。"""

    def __init__(
        self,
        max_workers: int = 30,
        rule_skip_predicates: list[str] | None = None,
        save_intermediates: bool = True,
    ) -> None:
        """
        Parameters
        ----------
        max_workers : int
            Ray 并行 worker 数。
        rule_skip_predicates : list[str] | None
            结论谓词跳过列表，默认 ["aconst", "rconst"]。
        save_intermediates : bool
            是否保存中间结果文件。
        """
        self.max_workers = max_workers
        self.rule_skip_predicates = rule_skip_predicates or ["aconst", "rconst"]
        self.save_intermediates = save_intermediates

    def run_part1_extract(
        self,
        input_path: str,
        output_path: str,
    ) -> ExtractionResult:
        """Part 1 的完整执行流程 (Steps 1-7)。

        流程：
        1. 读入 JSONL records。
        2. Step 1: graph_manager.step1_graph_prune → pruned_list + failed_records。
        3. Step 2: proposition_extractor.step2_extract_propositions → extraction_records。
        4. Step 3: post_processor.step3_post_process → post_processed_records。
        5. Step 4: rule_restorer.step4_restore_problems → records_with_problems。
        6. Step 5: normalizer.step5_normalize → normalized_records。
        7. Steps 6-7: output_handler.step6_7_dedup_and_dump → rules_file。

        Parameters
        ----------
        input_path : str
            输入 JSONL 文件路径（合成数据）。
        output_path : str
            输出 JSONL 文件路径。

        Returns
        -------
        ExtractionResult
            包含 rules_file 路径和各种统计信息。
        """
        raise NotImplementedError
