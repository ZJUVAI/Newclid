"""Step 3: 规则后处理（对应伪代码 §4.2 Step 3）。

3a. 平凡谓词简化
3b. eqpoint 等价点映射
"""

from __future__ import annotations

from newclid.discovery.data_models import ExtractionRecord


# ---------------------------------------------------------------------------
# 3a: 平凡谓词简化
# ---------------------------------------------------------------------------

def simplify_trivial_predicates(rule_text: str) -> str:
    """检测 eqangle/eqratio 中边对匹配的退化情况并替换。

    规则：
    - eqangle a b c d e f g h:
        - 前两对相同 (a,b)==(c,d) → 替换为 "para e f g h"
        - 后两对相同 (e,f)==(g,h) → 替换为 "para a b c d"
    - eqratio 类似

    Parameters
    ----------
    rule_text : str
        待简化的规则文本。

    Returns
    -------
    str
        简化后的规则文本。
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# 3b: eqpoint 等价点映射
# ---------------------------------------------------------------------------

def extract_eqpoint_from_rule_text(rule_text: str) -> list[tuple[str, str]]:
    """从 rule_text 的 premises 中提取所有 eqpoint 对。

    Returns
    -------
    list[tuple[str, str]]
        如 [("a", "c"), ("b", "d")]，空列表表示无 eqpoint premise。
    """
    raise NotImplementedError


def generate_merged_rule(
    rule_text: str,
    eqpoint_pairs: list[tuple[str, str]],
) -> str | None:
    """用 Union-Find 合并等价点，生成 merged_rule。

    1. 构建等价类（如 {a, c} 表示 a 和 c 是同一点）。
    2. 用 Union-Find 合并。
    3. 在规则文本中将等价类成员替换为代表元。
    4. 移除 eqpoint premise。

    Parameters
    ----------
    rule_text : str
        含 eqpoint premise 的原始规则文本。
    eqpoint_pairs : list[tuple[str, str]]
        等价点对列表。

    Returns
    -------
    str | None
        合并后的规则文本，或 None（合并后规则为空/无效时）。
    """
    raise NotImplementedError


def eqpoint_mapping(rule_text: str) -> tuple[list[tuple[str, str]] | None, str | None]:
    """eqpoint 映射的完整流程。

    仅对含 eqpoint premise 的规则处理。

    Returns
    -------
    (eqpoint_pairs, merged_rule)
        eqpoint_pairs: 等价点对列表，无 eqpoint 时为 None。
        merged_rule: 合并后的规则文本，无 eqpoint 时为 None。
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# 编排函数（供 engine.py 调用）
# ---------------------------------------------------------------------------

def step3_post_process(results: list[ExtractionRecord]) -> list[ExtractionRecord]:
    """Step 3 的顶层编排：对每条规则做平凡简化 + eqpoint 映射。

    Parameters
    ----------
    results : list[ExtractionRecord]
        Step 2 输出的中间记录。

    Returns
    -------
    list[ExtractionRecord]
        更新了 rule_text 和 eqpoint_info 字段的记录。
    """
    raise NotImplementedError
