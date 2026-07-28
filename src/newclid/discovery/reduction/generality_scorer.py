"""通用度评分（对应伪代码 §5.4 / §6 GeneralityScorer）。

score(rule) = -n_premises(rule)
premise 越少 → 越通用 → 越优先。
"""

from __future__ import annotations

from newclid.discovery.data_models import RuleWithSource


class GeneralityScorer:
    """规则通用度评分器。"""

    @staticmethod
    def score(rule: RuleWithSource) -> int:
        """返回规则的通用度分数。

        当前策略: -n_premises（premise 越少分数越高）。

        Parameters
        ----------
        rule : RuleWithSource
            待评分的规则。

        Returns
        -------
        int
            通用度分数。
        """
        raise NotImplementedError

    @staticmethod
    def sort_by_generality(rules: list[RuleWithSource]) -> list[RuleWithSource]:
        """按通用度降序排列规则（最通用的在前）。

        Parameters
        ----------
        rules : list[RuleWithSource]
            待排序的规则列表。

        Returns
        -------
        list[RuleWithSource]
            排序后的列表（新列表，不修改原始）。
        """
        raise NotImplementedError
