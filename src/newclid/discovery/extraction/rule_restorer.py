"""Step 4: 规则关联回原始题目信息（对应伪代码 §4.2 Step 4）。

从原始 record 还原 points / premises / goal / llm_output_renamed，
构建带题目的完整规则。不修改 rule_text，仅"补全题目"。
"""

from __future__ import annotations

import re
from typing import Any

from newclid.discovery.data_models import (
    ExtractionRecord,
    Point,
    PredicateInstance,
)


# ---------------------------------------------------------------------------
# 题目解析
# ---------------------------------------------------------------------------

def parse_llm_input(llm_input_renamed: str) -> tuple[list[PredicateInstance], PredicateInstance]:
    """解析 llm_input_renamed 获取 premises 和 goal。

    Parameters
    ----------
    llm_input_renamed : str
        如 "<problem> a : ; b : ; c : ; ... ? eqangle b d b e c d c e </problem>"

    Returns
    -------
    (premises, goal)
        premises: [PredicateInstance, ...]
        goal: PredicateInstance
    """
    text = llm_input_renamed.strip()
    wrapper = re.fullmatch(r"<problem>\s*(.*?)\s*</problem>", text, re.DOTALL)
    if wrapper:
        text = wrapper.group(1)

    premises_text, sep, goal_text = text.rpartition("?")
    if not sep:
        premises_text, goal_text = "", text

    goal_tokens = goal_text.split()
    goal = PredicateInstance(predicate=goal_tokens[0], args=tuple(goal_tokens[1:]))

    premises: list[PredicateInstance] = []
    last_end = 0
    for marker in re.finditer(r"\[\d+\]", premises_text):
        colon_idx = premises_text.rfind(":", last_end, marker.start())
        start = colon_idx + 1 if colon_idx != -1 else last_end
        phrase = premises_text[start:marker.start()].strip()
        if phrase:
            tokens = phrase.split()
            premises.append(
                PredicateInstance(predicate=tokens[0], args=tuple(tokens[1:]))
            )
        last_end = marker.end()

    return premises, goal


def extract_points(point_coords: Any) -> tuple[Point, ...]:
    """从 record 的 point_coords 字段提取点坐标。

    Parameters
    ----------
    point_coords : Any
        record 中的坐标数据（格式取决于上游，可能是 dict 或 list）。

    Returns
    -------
    tuple[Point, ...]
        (Point(name, x, y), ...)
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# 编排函数（供 engine.py 调用）
# ---------------------------------------------------------------------------

def step4_restore_problems(
    processed_results: list[ExtractionRecord],
    records: list[dict[str, Any]],
) -> list[ExtractionRecord]:
    """Step 4 的顶层编排：为每条规则还原原始题目信息。

    对每个 result：
    1. 通过 pid 找到对应 record。
    2. 解析 llm_input_renamed 得到 premises、goal。
    3. 提取 point_coords 为 Points。
    4. 填充 problem_statement, points, premises, goal, seed, llm_output_renamed。

    Parameters
    ----------
    processed_results : list[ExtractionRecord]
        Step 3 输出。
    records : list[dict]
        原始 records（按 pid 索引）。

    Returns
    -------
    list[ExtractionRecord]
        已填充题目信息的记录。
    """
    raise NotImplementedError


if __name__ == "__main__":
    sample = (
        "<problem> a : ; b : ; c : ; d : cong a d b d [000] cong b d c d [001] ; e : perp a e b c [002] perp a c b e [003] ; f : coll a d f [004] coll b e f [005] ; g : coll a d g [006] coll c e g [007] ; h : cong f h g h [008] cong e h g h [009] ; i : midp i b c [010] ; j : coll a h j [011] cyclic a b f j [012] ? eqangle a b a i b i b j </problem>"
    )
    premises, goal = parse_llm_input(sample)
    print("Premises:")
    for p in premises:
        print(" ", p)
    print("Goal:")
    print(" ", goal)
