"""命题提取（Part 1）。

把一张（经拆解 / 约简后的）证明图变成一个命题：
- 前提：图中所有**不含辅助点**的给定前提（produced_by 为 None 的 fact）。
- 结论：图的最终结论（goal）。
- 保留命题涉及点的坐标，以及来源序号（seed / index_in_seed / problem_id），便于后续处理。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tqdm import tqdm

from newclid.discovery.data_models import Point, PredicateInstance, PropositionRecord

if TYPE_CHECKING:
    from newclid.discovery.extraction.graph_manager import SingleProofGraph


def extract_proposition(graph: "SingleProofGraph") -> PropositionRecord | None:
    """从一张证明图提取命题。

    Returns
    -------
    PropositionRecord | None
        无法确定结论时返回 None。
    """
    conclusion = graph.goal
    if conclusion is None:
        gid = graph.find_goal_fact_id()
        if gid is None:
            return None
        gf = graph.facts[gid]
        conclusion = PredicateInstance(predicate=gf.predicate, args=gf.args)

    aux_set = set(graph.aux_points)

    # 前提：不含辅助点的给定 fact（produced_by 为 None），按 (谓词, 参数) 去重
    premises: list[PredicateInstance] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for f in graph.facts.values():
        if f.produced_by is not None:
            continue
        if set(f.args) & aux_set:
            continue
        key = (f.predicate, tuple(f.args))
        if key in seen:
            continue
        seen.add(key)
        premises.append(PredicateInstance(predicate=f.predicate, args=tuple(f.args)))

    # 命题涉及的点（前提 + 结论中出现的点），保留坐标
    coord = {p.name: p for p in graph.points}
    used_points: list = []
    seen_pt: set[str] = set()
    for pi in [*premises, conclusion]:
        for a in pi.args:
            if a in coord and a not in seen_pt:
                seen_pt.add(a)
                used_points.append(coord[a])

    return PropositionRecord(
        proposition_id=graph.problem_id,
        seed=graph.seed,
        index_in_seed=graph.index_in_seed,
        premises=tuple(premises),
        conclusion=conclusion,
        points=tuple(used_points),
    )


def extract_propositions(graphs: list["SingleProofGraph"]) -> list[PropositionRecord]:
    """对一批证明图逐个提取命题，跳过无法提取者。"""
    out: list[PropositionRecord] = []
    for g in tqdm(graphs, desc="[part1] 命题提取", unit="图"):
        prop = extract_proposition(g)
        if prop is not None:
            out.append(prop)
    return out


def _fmt_predicate(pi: PredicateInstance) -> str:
    return pi.predicate + (" " + " ".join(pi.args) if pi.args else "")


def proposition_to_text(prop: PropositionRecord) -> str:
    """命题的原始文本（保留原始点名，不做重命名）：``prem1, prem2 => concl``。"""
    prem = ", ".join(_fmt_predicate(p) for p in prop.premises)
    concl = _fmt_predicate(prop.conclusion)
    return f"{prem} => {concl}" if prem else f"=> {concl}"


def proposition_to_output(prop: PropositionRecord) -> dict:
    """命题的落盘结构：规则文本 + 点坐标 + 来源序号。"""
    return {
        "proposition_id": prop.proposition_id,
        "seed": prop.seed,
        "index_in_seed": prop.index_in_seed,
        "rule_text": proposition_to_text(prop),
        "points": [{"name": p.name, "x": p.x, "y": p.y} for p in prop.points],
    }


def _parse_predicate_text(text: str) -> PredicateInstance:
    parts = text.strip().split()
    return PredicateInstance(predicate=parts[0], args=tuple(parts[1:]))


def output_to_proposition(record: dict) -> PropositionRecord:
    """把 proposition_to_output 落盘的一条记录还原为 PropositionRecord。

    与 proposition_to_output 互为逆操作，用于从 propositions.jsonl 直接
    恢复内存对象，跳过重新读原始数据集 + 重新构图/拆解/提取命题的开销。
    """
    lhs, rhs = record["rule_text"].split("=>", 1)
    premises = tuple(
        _parse_predicate_text(p) for p in lhs.split(",") if p.strip()
    )
    conclusion = _parse_predicate_text(rhs)
    points = tuple(
        Point(name=p["name"], x=p["x"], y=p["y"]) for p in record["points"]
    )
    return PropositionRecord(
        proposition_id=record["proposition_id"],
        seed=record.get("seed"),
        index_in_seed=record.get("index_in_seed", 0),
        premises=premises,
        conclusion=conclusion,
        points=points,
    )


def load_propositions(jsonl_path: str) -> list[PropositionRecord]:
    """读取 propositions.jsonl，还原为 PropositionRecord 列表。"""
    props: list[PropositionRecord] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="[part1] 加载命题", unit="行"):
            line = line.strip()
            if line:
                props.append(output_to_proposition(json.loads(line)))
    return props
