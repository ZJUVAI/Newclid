"""Proof DAG: parses DDAR `<proof>` blocks into structured form and selects milestones.

The DDAR proof is already a verified DAG: each step has a step ID, rule name, and
explicit dependency list. This module exposes that structure so downstream code can
walk back from the goal step and translate the chosen milestones into natural language,
instead of re-deriving "support" via segment-overlap heuristics.
"""

import re
from collections import deque
from dataclasses import dataclass, field

from .geometry_text import summarize_aux_clause


_PROOF_BLOCK_RE = re.compile(r"<proof>(.*?)</proof>", re.DOTALL | re.IGNORECASE)
_NUMERICAL_BLOCK_RE = re.compile(r"<numerical_check>(.*?)</numerical_check>", re.DOTALL | re.IGNORECASE)
_STEP_ID_RE = re.compile(r"\[(\d{3})\]")


@dataclass
class ProofStep:
    step_id: str
    predicate: str
    args: list
    rule_id: str
    deps: list
    raw_line: str
    natural_language: str = ""


@dataclass
class NumericalFact:
    step_id: str
    predicate: str
    args: list
    raw_line: str


@dataclass
class ProofDAG:
    steps_by_id: dict = field(default_factory=dict)
    ordered_step_ids: list = field(default_factory=list)
    goal_step_id: str = ""
    numerical_facts: dict = field(default_factory=dict)  # predicate -> [NumericalFact]
    numerical_facts_by_id: dict = field(default_factory=dict)  # step_id -> NumericalFact

    def get(self, step_id):
        return self.steps_by_id.get(step_id)


@dataclass
class Milestone:
    step: ProofStep
    kind: str  # "rule" | "ar" | "premise"
    depth: int


def _parse_step_clause(clause):
    """Parse a clause like 'eqangle a b c d e f g h [022] r03 [021]' into a ProofStep.

    Returns None on parse failure.
    """
    clause = clause.strip().rstrip(";").strip()
    if not clause:
        return None

    # Find all [NNN] tokens and the position of the first one (= the step ID).
    id_matches = list(_STEP_ID_RE.finditer(clause))
    if not id_matches:
        return None
    step_id = id_matches[0].group(1)

    # The text before the first [NNN] is the predicate + args.
    pred_args_text = clause[: id_matches[0].start()].strip()
    pred_tokens = pred_args_text.split()
    if not pred_tokens:
        return None
    predicate = pred_tokens[0]
    args = pred_tokens[1:]

    # The text between [first id] and the next [NNN] (if any) contains the rule name.
    after_first_id = clause[id_matches[0].end():]
    if len(id_matches) > 1:
        next_id_offset_in_remainder = id_matches[1].start() - id_matches[0].end()
        rule_text = after_first_id[:next_id_offset_in_remainder].strip()
    else:
        rule_text = after_first_id.strip()
    rule_tokens = rule_text.split()
    rule_id = rule_tokens[0] if rule_tokens else ""

    deps = [m.group(1) for m in id_matches[1:]]

    return ProofStep(
        step_id=step_id,
        predicate=predicate,
        args=args,
        rule_id=rule_id,
        deps=deps,
        raw_line=clause,
        natural_language=build_step_natural_language(predicate, args),
    )


def _parse_numerical_clause(clause):
    """Parse a clause like 'sameclock a b c p q r [008]' into a NumericalFact."""
    clause = clause.strip().rstrip(";").strip()
    if not clause:
        return None
    id_match = _STEP_ID_RE.search(clause)
    if not id_match:
        return None
    step_id = id_match.group(1)
    pred_args_text = clause[: id_match.start()].strip()
    tokens = pred_args_text.split()
    if not tokens:
        return None
    predicate = tokens[0].lower()
    args = tokens[1:]
    return NumericalFact(
        step_id=step_id,
        predicate=predicate,
        args=args,
        raw_line=clause,
    )


def build_step_natural_language(predicate, args):
    """Translate a predicate and args into natural language."""
    clause_text = predicate + " " + " ".join(args) if args else predicate
    summary = summarize_aux_clause(clause_text)
    if summary:
        return summary
    return clause_text


def parse_proof_dag(llm_output_renamed):
    """Parse the `<proof>` and `<numerical_check>` blocks into a ProofDAG."""
    text = llm_output_renamed or ""

    proof_match = _PROOF_BLOCK_RE.search(text)
    steps_by_id = {}
    ordered_step_ids = []
    if proof_match:
        for clause in proof_match.group(1).split(";"):
            step = _parse_step_clause(clause)
            if step is None:
                continue
            steps_by_id[step.step_id] = step
            ordered_step_ids.append(step.step_id)

    numerical_match = _NUMERICAL_BLOCK_RE.search(text)
    numerical_facts = {}
    numerical_facts_by_id = {}
    if numerical_match:
        for clause in numerical_match.group(1).split(";"):
            fact = _parse_numerical_clause(clause)
            if fact is None:
                continue
            numerical_facts.setdefault(fact.predicate, []).append(fact)
            numerical_facts_by_id[fact.step_id] = fact

    goal_step_id = ordered_step_ids[-1] if ordered_step_ids else ""

    return ProofDAG(
        steps_by_id=steps_by_id,
        ordered_step_ids=ordered_step_ids,
        goal_step_id=goal_step_id,
        numerical_facts=numerical_facts,
        numerical_facts_by_id=numerical_facts_by_id,
    )


def parse_numerical_check(llm_output_renamed):
    """Convenience wrapper returning only the numerical facts grouped by predicate."""
    return parse_proof_dag(llm_output_renamed).numerical_facts


def walk_milestones(dag, goal_step_id=None, max_steps=6, ar_max_recursion_depth=3):
    """Backward BFS from the goal: pick rule-named milestones, recurse through AR steps.

    Returns milestones in forward (premise-to-goal) order.
    """
    if not isinstance(dag, ProofDAG) or not dag.steps_by_id:
        return []

    target_id = goal_step_id or dag.goal_step_id
    if not target_id or target_id not in dag.steps_by_id:
        return []

    # Track which rule-named or fallback-AR steps we have selected.
    selected = {}  # step_id -> Milestone
    queue = deque()  # (step_id, depth, ar_depth)
    queue.append((target_id, 0, 0))

    while queue:
        step_id, depth, ar_depth = queue.popleft()
        step = dag.get(step_id)
        if step is None:
            continue
        if step_id in selected:
            # Already chosen — keep the shallowest depth.
            if selected[step_id].depth > depth:
                selected[step_id].depth = depth
            continue

        is_ar = step.rule_id.upper() == "AR"

        if is_ar:
            # Recurse into deps unless we've gone too deep, in which case emit AR as fallback.
            if ar_depth >= ar_max_recursion_depth:
                if step_id == target_id and not selected:
                    selected[step_id] = Milestone(step=step, kind="ar", depth=depth)
                continue
            for dep_id in step.deps:
                if dep_id not in dag.steps_by_id:
                    continue
                queue.append((dep_id, depth + 1, ar_depth + 1))
            continue

        # Rule-named step: select it.
        kind = "rule"
        if not step.rule_id:
            kind = "premise"
        selected[step_id] = Milestone(step=step, kind=kind, depth=depth)

        # Recurse into rule deps to surface ancestor milestones too.
        for dep_id in step.deps:
            if dep_id in dag.steps_by_id:
                queue.append((dep_id, depth + 1, 0))

    # If the goal step was AR and we never recorded it but no rule milestone exists either,
    # ensure we surface the goal step as an AR milestone so downstream code has something.
    if not selected:
        goal_step = dag.get(target_id)
        if goal_step is not None:
            kind = "ar" if goal_step.rule_id.upper() == "AR" else "rule"
            selected[target_id] = Milestone(step=goal_step, kind=kind, depth=0)
    elif target_id not in selected:
        # Always include the goal step itself even if it was AR (so the closure has a final claim).
        goal_step = dag.get(target_id)
        if goal_step is not None:
            kind = "ar" if goal_step.rule_id.upper() == "AR" else "rule"
            selected[target_id] = Milestone(step=goal_step, kind=kind, depth=0)

    # Order milestones by their step ID order in the proof (forward order),
    # then cap the count of rule milestones at max_steps. Goal milestone is always kept.
    target_milestone = selected.get(target_id)
    ordered_milestones = []
    for sid in dag.ordered_step_ids:
        m = selected.get(sid)
        if m is not None and sid != target_id:
            ordered_milestones.append(m)

    # Cap rule-emitted milestones to max_steps - 1 (reserve one slot for the goal).
    rule_milestones = [m for m in ordered_milestones if m.kind == "rule"]
    if len(rule_milestones) > max_steps - 1:
        # Keep the rule milestones closest to the goal (largest step IDs).
        keep_ids = {m.step.step_id for m in rule_milestones[-(max_steps - 1):]}
        ordered_milestones = [
            m for m in ordered_milestones if m.kind != "rule" or m.step.step_id in keep_ids
        ]

    if target_milestone is not None:
        ordered_milestones.append(target_milestone)

    return ordered_milestones


def find_step_by_predicate_args(dag, predicate, args):
    """Locate a step in the DAG whose predicate and args match (used for tracing)."""
    if not isinstance(dag, ProofDAG):
        return None
    target_args = [str(a).lower() for a in args]
    for step in dag.steps_by_id.values():
        if step.predicate != predicate:
            continue
        if [str(a).lower() for a in step.args] == target_args:
            return step
    return None
