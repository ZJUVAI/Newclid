"""Part 2 规约编排。

规约策略（作用于 Part 1 的 normalized_rules.jsonl）：
  0. （可选）前提数预过滤：丢弃前提数 >= max_premises_drop 的规则。
  1. 按 seed 分组，组内贪心规约（Ray 并行，每组一任务）。       [seed_reducer]
  2. 合并前提完全一致的存活规则 p→g1, p→g2 ⇒ p→g1,g2。          [seed_reducer.merge]
  3. 全部存活规则分治规约（打乱分块并行 → 汇总 → 迭代到稳定）。  [divide_conquer_reducer]
  4. 再合并一次前提一致的规则。

规约判定原子操作（subsumption_tester）：
  CSolver(points=R坐标, premises=R前提, goals=[R结论]).run(custom_rules=其它规则) 是否 solved。
  custom_rules 可多条 → 支持"多条规则合力推出第三条"。

并行：Ray，bounded in-flight（ray.wait 完成即补），避免 worker 闲置。
"""

from __future__ import annotations

import json
import os
from typing import Any

from newclid.discovery.reduction import divide_conquer_reducer, seed_reducer
from newclid.discovery.reduction.subsumption_tester import RuleItem, load_rules


def _premise_count(rule_text: str) -> int:
    lhs = rule_text.split("=>", 1)[0].strip()
    return len([p for p in lhs.split(",") if p.strip()]) if lhs else 0


def _write(rules: list[RuleItem], output_path: str) -> None:
    txt_path = os.path.splitext(output_path)[0] + ".txt"
    with open(output_path, "w", encoding="utf-8") as f:
        for r in rules:
            f.write(json.dumps({
                "rule_id": r.rule_id,
                "seed": r.seed,
                "index_in_seed": r.index_in_seed,
                "rule_text": r.rule_text,
                "points": [{"name": n, "x": x, "y": y} for n, x, y in r.points],
            }, ensure_ascii=False) + "\n")
    with open(txt_path, "w", encoding="utf-8") as f:
        for r in rules:
            f.write(r.rule_text + "\n")


def run_part2(
    cfg: dict[str, Any],
    output_dir: str,
    input_path: str,
) -> tuple[str, dict[str, Any]]:
    """Part 2 规约完整流程。

    config: part2_reduction.{max_premises_drop, n_workers, use_ray, chunk_size, config_path}
    """
    part2_cfg = cfg.get("part2_reduction", {})
    drop_threshold = part2_cfg.get("max_premises_drop", 8)
    n_workers = part2_cfg.get("n_workers") or cfg.get("global", {}).get("n_workers", 30)
    use_ray = part2_cfg.get("use_ray", True)
    chunk_size = part2_cfg.get("chunk_size", 200)
    config_path = part2_cfg.get("csolver_config_path")

    out_dir = os.path.join(output_dir, "part2")
    os.makedirs(out_dir, exist_ok=True)
    output_path = part2_cfg.get("output") or os.path.join(out_dir, "reduced_rules.jsonl")

    # 加载
    rules = load_rules(input_path)
    stats: dict[str, Any] = {"input": len(rules)}

    # 小规模测试：只取前 N 条
    limit = part2_cfg.get("limit")
    if limit is not None:
        rules = rules[:limit]
        print(f"[part2] limit={limit}, 只处理前 {len(rules)} 条")

    # 阶段 0：前提数预过滤 + perp 前提数过滤
    max_perp_premises = part2_cfg.get("max_perp_premises")
    if drop_threshold is not None or max_perp_premises is not None:
        if drop_threshold is not None:
            rules = [r for r in rules if r.premise_count < drop_threshold]
        if max_perp_premises is not None:
            rules = [
                r for r in rules
                if sum(1 for name, _args in r.premises if name == "perp") <= max_perp_premises
            ]
        stats["after_premise_filter"] = len(rules)
        print(f"[part2] 前提数<{drop_threshold}"
              f"{' 且 perp 前提数<=' + str(max_perp_premises) if max_perp_premises is not None else ''}"
              f" 过滤后: {len(rules)} 条")
        _write(rules, os.path.join(out_dir, "premise_num_filtered.jsonl"))

    # 阶段 1：seed 分组规约
    rules = seed_reducer.reduce_by_seed(
        rules, n_workers=n_workers, use_ray=use_ray, config_path=config_path,
    )
    stats["after_seed_reduce"] = len(rules)
    _write(rules, os.path.join(out_dir, "seed_reduced.jsonl"))

    # 阶段 3：分治规约
    rules = divide_conquer_reducer.reduce(
        rules, chunk_size=chunk_size, n_workers=n_workers, use_ray=use_ray,
        config_path=config_path,
    )
    stats["after_divide_conquer"] = len(rules)
    _write(rules, os.path.join(out_dir, "divide_reduced.jsonl"))

    # 阶段 4：再合并
    rules = seed_reducer.merge_same_premise(rules)
    stats["after_merge_2"] = len(rules)

    _write(rules, output_path)
    stats["kept"] = len(rules)
    stats["output"] = output_path
    print(f"[part2] 规约完成: {stats['input']} -> {len(rules)} 条, 结果 -> {output_path}")
    return output_path, stats
