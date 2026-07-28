"""Seed 分组规约 + 前提合并（规约策略阶段 1、2）。

阶段1：按 seed 把规则分组，每组内做贪心累积规约；组间用 Ray 并行（每组一个任务）。
阶段2：合并前提完全一致的规则（p→g1, p→g2 ⇒ p→g1,g2）。

贪心规约 greedy_reduce 是组内/分块共用的核心：前提少者优先，逐条测"能否被已保留集
推出"，不能才保留 —— 得到一个基（basis）。
"""

from __future__ import annotations

from collections import defaultdict

from tqdm import tqdm

from newclid.discovery.reduction.parallel import ensure_ray, run_bounded
from newclid.discovery.reduction.subsumption_tester import RuleItem, SubsumptionTester


# ---------------------------------------------------------------------------
# 贪心累积规约（核心）
# ---------------------------------------------------------------------------

def greedy_reduce(rules: list[RuleItem], tester: SubsumptionTester) -> list[RuleItem]:
    """贪心累积求基：保留"无法被已保留规则集推出"的规则。

    顺序：前提数升序（更一般优先保留），再按 rule_id。互相可推的两条只留先处理的那条。

    第一条规则在被加入 basis 时，尚无其它规则可供测试（basis 为空），因此它永远
    不会被判定为冗余，即便后续加入的规则组合起来本可以推出它（例如它本不需要
    辅助点，只是恰好排在最前面）。收尾时用最终 basis 中的其它规则反过来测一次
    第一条规则，弥补这个不对称。
    """
    ordered = sorted(rules, key=lambda r: (r.premise_count, r.rule_id))
    basis: list[RuleItem] = []
    for r in ordered:
        if tester.is_derivable(r, basis):
            continue  # 可由已保留规则推出 → 冗余
        basis.append(r)

    if len(basis) > 1 and tester.is_derivable(basis[0], basis[1:]):
        basis.pop(0)

    return basis


# ---------------------------------------------------------------------------
# 阶段 2：合并前提一致的规则
# ---------------------------------------------------------------------------

def _premise_key(r: RuleItem) -> tuple:
    """前提集合的规范键（无序）。"""
    return tuple(sorted(f"{n} {' '.join(a)}" for n, a in r.premises))


def merge_same_premise(rules: list[RuleItem]) -> list[RuleItem]:
    """把前提完全一致的规则合并为一条多结论规则（p→g1, p→g2 ⇒ p→g1,g2）。

    注意：应在规约**之后**做——若在规约前合并，会把多个结论耦合，导致无法单独
    丢弃其中可被推出的结论，削弱规约能力。
    """
    groups: dict[tuple, list[RuleItem]] = defaultdict(list)
    for r in rules:
        groups[_premise_key(r)].append(r)

    merged: list[RuleItem] = []
    for _key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        rep = min(group, key=lambda r: (r.seed or 0, r.index_in_seed, r.rule_id))
        lhs = rep.rule_text.split("=>", 1)[0].strip()
        # 收集去重后的所有结论
        concls: list[str] = []
        for r in group:
            c = r.rule_text.split("=>", 1)[1].strip()
            if c not in concls:
                concls.append(c)
        rep.rule_text = f"{lhs} => {', '.join(concls)}"
        merged.append(rep)
    return merged


# ---------------------------------------------------------------------------
# 阶段 1：按 seed 分组规约（Ray 并行）
# ---------------------------------------------------------------------------

def _reduce_group(rules: list[RuleItem], seed: int, config_path: str | None) -> list[RuleItem]:
    """单个 seed 组的规约（在 worker 内串行执行 greedy_reduce）。"""
    tester = SubsumptionTester(seed=seed, config_path=config_path)
    return greedy_reduce(rules, tester)


def reduce_by_seed(
    rules: list[RuleItem],
    *,
    n_workers: int = 30,
    use_ray: bool = True,
    config_path: str | None = None,
) -> list[RuleItem]:
    """阶段 1：按 seed 分组，组内规约；组间并行。返回所有组的幸存者。"""
    groups: dict[object, list[RuleItem]] = defaultdict(list)
    for r in rules:
        groups[r.seed].append(r)
    print(f"[seed_reduce] {len(rules)} 条规则 -> {len(groups)} 个 seed 组")

    survivors: list[RuleItem] = []
    if use_ray and len(groups) > 1:
        import ray

        ensure_ray(n_workers)
        remote = ray.remote(_reduce_group)
        args = [(g, (seed if isinstance(seed, int) else 0), config_path)
                for seed, g in groups.items()]
        for group_survivors in tqdm(
            run_bounded(remote, args, inflight=n_workers),
            total=len(groups), desc="[part2] seed 分组规约", unit="组",
        ):
            survivors.extend(group_survivors)
    else:
        for seed, g in tqdm(groups.items(), desc="[part2] seed 分组规约", unit="组"):
            survivors.extend(_reduce_group(g, seed if isinstance(seed, int) else 0, config_path))

    print(f"[seed_reduce] 组内规约后剩 {len(survivors)} 条")
    return survivors
