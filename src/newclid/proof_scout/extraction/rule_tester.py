#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RuleTester - Validate discovered rules using DDAR solver.

This module provides utilities to:
- Convert rules to constructible JGEX problems
- Use DDAR solver to verify conclusions are derivable from premises
- Support parallel testing of multiple rules

No ML dependencies required.
"""
from __future__ import annotations

import random
import re
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _split_rule(rule: str) -> Tuple[List[Tuple[str, ...]], List[Tuple[str, ...]]]:
    """Split rule into premise and goal tuples.

    Example: "cong a b c d, para e f g h => coll i j k"
    Returns: ([('cong', 'a', 'b', 'c', 'd'), ('para', 'e', 'f', 'g', 'h')],
              [('coll', 'i', 'j', 'k')])
    """
    premise_part, goal_part = rule.split('=>', 1)

    premise_tuples = []
    for condition in premise_part.split(','):
        parts = re.findall(r'\w+', condition)
        if parts:
            premise_tuples.append(tuple(parts))

    goal_tuples = []
    for condition in goal_part.split(','):
        parts = re.findall(r'\w+', condition)
        if parts:
            goal_tuples.append(tuple(parts))

    return premise_tuples, goal_tuples


def _update_dep(point1: str, point2: str, deps: Dict[str, List[str]]) -> None:
    """Update dependency: point1 depends on point2."""
    if point1 == point2 or point1 in deps[point2]:
        return
    deps[point2].append(point1)
    for p, dep in deps.items():
        if point2 in dep:
            _update_dep(point1, p, deps)
    for p in deps[point1]:
        _update_dep(p, point2, deps)


def _check_count(num: int, point: str, points: List[str]) -> bool:
    """Check if point appears exactly num times in points."""
    return points.count(point) == num


def _translate_perp(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c, d = args
    if _check_count(1, d, args) and a not in deps[d] and b not in deps[d] and c not in deps[d] and state[d]:
        constructions[d].append(('on_tline', d, c, a, b))
        if len(constructions[d]) == 2:
            state[d] = False
        for p in [a, b, c]:
            _update_dep(d, p, deps)
        return True
    return False


def _translate_cong(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    if len(args) == 4:
        a, b, c, d = args
        if _check_count(1, d, args) and a not in deps[d] and b not in deps[d] and c not in deps[d] and len(constructions[d]) < 2:
            constructions[d].append(('eqdistance', d, c, a, b))
            if len(constructions[d]) == 2:
                state[d] = False
            for p in [a, b, c]:
                _update_dep(d, p, deps)
            return True
    return False


def _translate_isotri(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    if len(args) == 4:
        a, b, c, d = args
        if a == c and b not in deps[a] and d not in deps[a] and state[a]:
            constructions[a].append(('iso_triangle_vertex', a, b, d))
            if len(constructions[a]) == 2:
                state[a] = False
            for p in [b, d]:
                _update_dep(a, p, deps)
            return True
    return False


def _translate_cyclic(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    count = 0
    for point in reversed(args):
        if not state[point]:
            count += 1
            if count > 3:
                return False
            continue
        cycles = []
        for p in args:
            if p != point and p not in deps[point]:
                cycles.append(p)
                if len(cycles) == 3:
                    break
        if len(cycles) != 3:
            count += 1
            if count > 3:
                return False
            continue
        a, b, c = cycles
        constructions[point].append(('on_circum', point, a, b, c))
        if len(constructions[point]) == 2:
            state[point] = False
        for p in [a, b, c]:
            _update_dep(point, p, deps)
    return True


def _translate_eqangle(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c, d, e, f, g, h = args
    if _check_count(1, e, args) and all(p not in deps[e] for p in [a, b, c, d, f, g, h]) and state[e]:
        constructions[e].append(('on_aline0', e, c, d, a, b, g, h, f))
        if len(constructions[e]) == 2:
            state[e] = False
        for p in [a, b, c, d, f, g, h]:
            _update_dep(e, p, deps)
        return True
    return False


def _translate_eqangle6(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c, d, e, f, g, h = args
    if a == c and e == g and _check_count(1, h, args) and all(p not in deps[h] for p in [a, b, d, f, g]) and state[h]:
        constructions[h].append(('on_aline', h, e, f, d, a, b))
        if len(constructions[h]) == 2:
            state[h] = False
        for p in [a, b, d, e, f]:
            _update_dep(h, p, deps)
        return True
    elif a == c and e == g and all(p not in deps[a] for p in [b, d, f, g, h]) and state[a]:
        constructions[a].append(('eqangle3', a, b, d, e, f, h))
        if len(constructions[a]) == 2:
            state[a] = False
        for p in [b, d, e, f, h]:
            _update_dep(a, p, deps)
        return True
    return False


def _translate_eqratio(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c, d, e, f, g, h = args
    if _check_count(1, e, args) and all(p not in deps[e] for p in [a, b, c, d, f, g, h]) and state[e]:
        constructions[e].append(('eqratio', e, c, d, a, b, g, h, f))
        if len(constructions[e]) == 2:
            state[e] = False
        for p in [a, b, c, d, f, g, h]:
            _update_dep(e, p, deps)
        return True
    return False


def _translate_eqratio6(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c, d, e, f, g, h = args
    if b == d and _check_count(2, b, args) and all(p not in deps[b] for p in [a, c, e, f, g, h]) and state[b]:
        constructions[b].append(('eqratio6', b, a, c, e, f, g, h))
        if len(constructions[b]) == 2:
            state[b] = False
        for p in [a, c, e, f, g, h]:
            _update_dep(b, p, deps)
        return True
    return False


def _translate_midp(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c = args
    if b not in deps[a] and c not in deps[a] and len(constructions[a]) == 0:
        constructions[a].append(('midpoint', a, b, c))
        state[a] = False
        for p in [b, c]:
            _update_dep(a, p, deps)
        return True
    elif a not in deps[b] and c not in deps[b] and len(constructions[b]) == 0:
        constructions[b].append(('online', b, a, c))
        constructions[b].append(('eqdistance', b, a, a, c))
        state[b] = False
        for p in [a, c]:
            _update_dep(b, p, deps)
        return True
    return False


def _translate_para(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c, d = args
    if _check_count(1, d, args) and a not in deps[d] and b not in deps[d] and c not in deps[d] and state[d]:
        constructions[d].append(('on_pline', d, c, a, b))
        if len(constructions[d]) == 2:
            state[d] = False
        for p in [a, b, c]:
            _update_dep(d, p, deps)
        return True
    return False


def _translate_coll(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c = args
    if a not in deps[c] and b not in deps[c] and state[c]:
        constructions[c].append(('on_line', c, a, b))
        if len(constructions[c]) == 2:
            state[c] = False
        for p in [a, b]:
            _update_dep(c, p, deps)
        return True
    return False


def _translate_circle(args: List[str], deps: Dict, constructions: Dict, state: Dict) -> bool:
    a, b, c, d = args
    if b not in deps[a] and c not in deps[a] and d not in deps[a] and len(constructions[a]) == 0:
        constructions[a].append(('circle', a, b, c, d))
        state[a] = False
        for p in [b, c, d]:
            _update_dep(a, p, deps)
        return True
    elif a not in deps[c] and b not in deps[c] and a not in deps[d] and b not in deps[d] and state[c] and state[d]:
        constructions[c].append(('on_circle', c, a, b))
        constructions[d].append(('on_circle', d, a, b))
        if len(constructions[c]) == 2:
            state[c] = False
        if len(constructions[d]) == 2:
            state[d] = False
        for p in [a, b]:
            _update_dep(c, p, deps)
            _update_dep(d, p, deps)
        return True
    return False


def _translate_premise(premise: Tuple[str, ...], deps: Dict, constructions: Dict, state: Dict) -> bool:
    """Translate a premise into construction commands."""
    pred_type = premise[0]
    args = list(premise[1:])

    # Unsupported predicates
    if pred_type in ['simtri', 'simtrir', 'PythagoreanPremises']:
        return False

    # Predicates that don't need construction
    if pred_type in ['sameclock', 'ncoll', 'npara', 'sameside', 'nsameside']:
        return True

    if pred_type == 'perp':
        return _translate_perp(args, deps, constructions, state)
    if pred_type == 'cong':
        return _translate_cong(args, deps, constructions, state) or _translate_isotri(args, deps, constructions, state)
    if pred_type == 'cyclic':
        return _translate_cyclic(args, deps, constructions, state)
    if pred_type == "eqangle":
        return _translate_eqangle(args, deps, constructions, state) or _translate_eqangle6(args, deps, constructions, state)
    if pred_type == "eqratio":
        return _translate_eqratio(args, deps, constructions, state) or _translate_eqratio6(args, deps, constructions, state)
    if pred_type == "midp":
        return _translate_midp(args, deps, constructions, state)
    if pred_type == "para":
        return _translate_para(args, deps, constructions, state)
    if pred_type == "coll":
        return _translate_coll(args, deps, constructions, state)
    if pred_type == "circle":
        return _translate_circle(args, deps, constructions, state)

    return False


def _shuffle_premise(premise: Tuple[str, ...]) -> Tuple[str, ...]:
    """Shuffle premise arguments to try different construction orders."""
    pred_type = premise[0]
    args = list(premise[1:])

    if pred_type in ['sameclock', 'ncoll', 'npara', 'sameside', 'nsameside']:
        return premise
    elif pred_type in ['coll', 'cyclic']:
        random.shuffle(args)
        return (pred_type, *args)
    elif pred_type in ['cong', 'para', 'perp']:
        grouped_list = [args[i:i+2] for i in range(0, len(args), 2)]
        for group in grouped_list:
            random.shuffle(group)
        random.shuffle(grouped_list)
        flattened_list = [item for group in grouped_list for item in group]
        return (pred_type, *flattened_list)
    elif pred_type in ['midp', 'circle']:
        points = args[1:]
        random.shuffle(points)
        return (pred_type, args[0], *points)
    elif pred_type in ['eqangle', 'eqratio']:
        grouped_list = [args[i:i+2] for i in range(0, len(args), 2)]
        for group in grouped_list:
            random.shuffle(group)
        possible_orders = [
            [0, 1, 2, 3],
            [1, 0, 3, 2],
            [2, 3, 0, 1],
            [3, 2, 1, 0],
        ]
        selected_order = random.choice(possible_orders)
        reordered_groups = [grouped_list[i] for i in selected_order]
        flattened_list = [item for group in reordered_groups for item in group]
        return (pred_type, *flattened_list)

    return premise


def _topological_sort(elements: List[str], deps: Dict[str, List[str]]) -> Optional[List[str]]:
    """Topological sort of elements based on dependencies."""
    in_degree = defaultdict(int)
    graph = defaultdict(list)

    for elem in elements:
        if elem not in deps:
            deps[elem] = []
        for dep in deps[elem]:
            graph[dep].append(elem)
            in_degree[elem] += 1

    queue = deque([elem for elem in elements if in_degree[elem] == 0])
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) == len(elements):
        return result
    return None


def _dict2str(points: List[str], deps: Dict, constructions: Dict) -> Optional[str]:
    """Convert construction dict to JGEX problem string."""
    sorted_points = _topological_sort(points, deps)
    if not sorted_points:
        return None

    sorted_points.reverse()
    res = ""
    for p in sorted_points:
        if p in constructions:
            if len(constructions[p]) == 0:
                res += p + " = free " + p + "; "
                continue
            res += p + " = "
            for c in constructions[p]:
                res += " ".join(c) + ", "
            res = res.strip().rstrip(',')
            res += "; "

    return res.lower().strip().rstrip(';')


def _expand_special_predicates(premise_tuples: List[Tuple[str, ...]]) -> List[Tuple[str, ...]]:
    """Expand special predicates like simtri, simtrir, PythagoreanPremises."""
    tuples_new = []
    for premise_tuple in premise_tuples:
        if premise_tuple[0] == 'simtri':
            a, b, c, p, q, r = premise_tuple[1:]
            tuples_new.append(('eqangle', b, a, b, c, q, p, q, r))
            tuples_new.append(('eqangle', c, a, c, b, r, p, r, q))
        elif premise_tuple[0] == 'simtrir':
            a, b, c, p, q, r = premise_tuple[1:]
            tuples_new.append(('eqangle', b, a, b, c, q, p, q, r))
            tuples_new.append(('eqangle', c, a, c, b, r, q, r, p))
        elif premise_tuple[0] == 'PythagoreanPremises':
            a, b, c = premise_tuple[1:]
            tuples_new.append(('perp', a, b, a, c))
        else:
            tuples_new.append(premise_tuple)
    return tuples_new


class RuleTester:
    """Test discovered rules using DDAR solver."""

    # Predicates that cannot be used as goals (unsupported or parsing issues)
    UNSUPPORTED_GOAL_PREDICATES = {'contri', 'contrir', 'eqratio3', 'rconst'}

    # Patterns of (premise_predicate, conclusion_predicate) that cause inference explosion
    # These rules create feedback loops with built-in DDAR rules
    GENERATIVE_RULE_PATTERNS = {
        ('cyclic', 'eqangle'),  # cyclic => eqangle creates feedback with eqangle => cyclic
    }

    def __init__(
        self,
        max_attempts: int = 100,
        timeout: int = 60,
        seed: int = 42,
        use_csolver: bool = True,
        max_premises: int = 6,
        filter_generative: bool = True,
    ):
        """Initialize RuleTester.

        Args:
            max_attempts: Maximum attempts to find valid construction order
            timeout: Timeout in seconds for each rule test
            seed: Random seed for reproducibility
            use_csolver: Use CSolver (C++ DDAR) instead of DDARN (Python). Default True.
            max_premises: Maximum number of premises to attempt conversion (default 6).
                         Rules with more premises are skipped to avoid exponential search.
            filter_generative: Filter out generative rules that cause inference explosion.
                              Default True.
        """
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.seed = seed
        self.use_csolver = use_csolver
        self.max_premises = max_premises
        self.filter_generative = filter_generative

    def _is_generative_rule(self, rule_text: str) -> bool:
        """Check if a rule causes inference explosion.

        A rule is considered generative if it matches any pattern in GENERATIVE_RULE_PATTERNS,
        where the premise contains the first predicate and conclusion contains the second.

        Args:
            rule_text: Rule in format "premise1, premise2 => conclusion"

        Returns:
            True if the rule is generative (should be filtered out)
        """
        if '=>' not in rule_text:
            return False

        premise_part, conclusion_part = rule_text.split('=>', 1)

        # Extract predicates (first word of each condition)
        premise_preds = set()
        for condition in premise_part.split(','):
            parts = re.findall(r'\w+', condition)
            if parts:
                premise_preds.add(parts[0])

        conclusion_preds = set()
        for condition in conclusion_part.split(','):
            parts = re.findall(r'\w+', condition)
            if parts:
                conclusion_preds.add(parts[0])

        for premise_pred, conclusion_pred in self.GENERATIVE_RULE_PATTERNS:
            if premise_pred in premise_preds and conclusion_pred in conclusion_preds:
                return True

        return False

    def rule_to_problem(self, rule_text: str, max_attempts: Optional[int] = None) -> Tuple[Optional[str], Optional[str]]:
        """Convert a rule to a JGEX problem string.

        Args:
            rule_text: Rule in format "premise1, premise2 => conclusion"
            max_attempts: Override default max_attempts

        Returns:
            Tuple of (JGEX problem string, error message).
            If conversion succeeds, returns (problem, None).
            If conversion fails, returns (None, error_message).
        """
        if max_attempts is None:
            max_attempts = self.max_attempts

        random.seed(self.seed)

        try:
            premise_tuples, goal_tuples = _split_rule(rule_text)
        except Exception:
            return None, "Failed to parse rule"

        if not premise_tuples or not goal_tuples:
            return None, "Empty premises or goals"

        # Check for unsupported goal predicates
        goal_predicate = goal_tuples[0][0]
        if goal_predicate in self.UNSUPPORTED_GOAL_PREDICATES:
            return None, f"Unsupported goal predicate: {goal_predicate}"

        # Check complexity (number of premises)
        if len(premise_tuples) > self.max_premises:
            return None, f"Too many premises ({len(premise_tuples)} > {self.max_premises})"

        # Collect all points
        points = []
        for premise_tuple in premise_tuples:
            for point in premise_tuple[1:]:
                if point not in points:
                    points.append(point)
        points = sorted(list(set(points)))

        # Expand special predicates
        premise_tuples = _expand_special_predicates(premise_tuples)

        # Try multiple times with different orderings
        for _ in range(max_attempts):
            # Shuffle premises
            for j, premise in enumerate(premise_tuples):
                premise_tuples[j] = _shuffle_premise(premise)

            constructions = {point: [] for point in points}
            state = {point: True for point in points}
            deps = {point: [] for point in points}

            success = True
            random.shuffle(premise_tuples)
            for premise_tuple in premise_tuples:
                if not _translate_premise(premise_tuple, deps, constructions, state):
                    success = False
                    break

            if success:
                premise_str = _dict2str(points, deps, constructions)
                if premise_str:
                    # Build problem with first goal
                    goal = goal_tuples[0]
                    problem = premise_str + " ? " + " ".join(goal)
                    return problem.lower(), None

        return None, "Failed to find valid construction order"

    def test_rule(self, rule_text: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Test a single rule using the configured engine.

        Args:
            rule_text: Rule in format "premise1, premise2 => conclusion"
            timeout: Override default timeout

        Returns:
            Dict with test results:
                - rule: original rule text
                - problem: generated JGEX problem (or None)
                - success: whether rule was verified
                - error: error message if any
                - filtered: True if rule was filtered as generative
        """
        # Check for generative rules first
        if self.filter_generative and self._is_generative_rule(rule_text):
            return {
                "rule": rule_text,
                "problem": None,
                "success": False,
                "error": "Filtered: generative rule causes inference explosion",
                "filtered": True,
            }

        if self.use_csolver:
            return self._test_rule_csolver(rule_text, timeout)
        else:
            return self._test_rule_ddarn(rule_text, timeout)

    def _test_rule_ddarn(self, rule_text: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Test a single rule using DDARN (Python DDAR engine)."""
        if timeout is None:
            timeout = self.timeout

        result = {
            "rule": rule_text,
            "problem": None,
            "success": False,
            "error": None,
        }

        # Convert rule to problem
        problem, error = self.rule_to_problem(rule_text)
        if not problem:
            result["error"] = error or "Failed to convert rule to problem"
            return result

        result["problem"] = problem

        # Try to solve with DDAR
        try:
            from newclid.api import GeometricSolverBuilder
            from newclid.agent.ddarn import DDARN

            builder = GeometricSolverBuilder(seed=self.seed)
            builder.load_problem_from_txt(problem)
            builder.with_deductive_agent(DDARN())
            solver = builder.build(max_attempts=100)

            is_solved = solver.run(timeout=timeout)
            result["success"] = is_solved
            if not is_solved:
                result["error"] = "DDARN failed to prove the rule"

        except Exception as e:
            result["error"] = f"DDARN error: {str(e)}"

        return result

    def _test_rule_csolver(self, rule_text: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Test a single rule using CSolver (C++ DDAR engine)."""
        if timeout is None:
            timeout = self.timeout

        result = {
            "rule": rule_text,
            "problem": None,
            "success": False,
            "error": None,
        }

        # Convert rule to problem
        problem, error = self.rule_to_problem(rule_text)
        if not problem:
            result["error"] = error or "Failed to convert rule to problem"
            return result

        result["problem"] = problem

        try:
            # Build solver to get coordinates and extract problem data
            from newclid.api import GeometricSolverBuilder
            from newclid.agent.ddarn import DDARN
            from newclid.numerical.geometries import PointNum
            from fractions import Fraction

            builder = GeometricSolverBuilder(seed=self.seed)
            builder.load_problem_from_txt(problem)
            builder.with_deductive_agent(DDARN())
            solver = builder.build(max_attempts=100)

            # Extract points, premises, goals from the built solver
            points = []
            premises = []
            goals = []
            useful_points = []

            # Extract premises from dependency graph
            for stmt in solver.proof.dep_graph.hyper_graph:
                predicate = stmt.predicate.NAME
                args = []
                for pt in stmt.args:
                    if isinstance(pt, Fraction):
                        args.append(str(pt))
                    else:
                        args.append(pt.name)
                        if pt.name not in useful_points:
                            useful_points.append(pt.name)
                premises.append((predicate, args))

            # Extract goals
            for stmt in solver.proof.goals:
                predicate = stmt.predicate.NAME
                args = []
                for pt in stmt.args:
                    if isinstance(pt, Fraction):
                        args.append(str(pt))
                    else:
                        args.append(pt.name)
                        if pt.name not in useful_points:
                            useful_points.append(pt.name)
                goals.append((predicate, args))

            # Extract point coordinates (handle points with num=None)
            for name, point in solver.proof.symbols_graph.name2node.items():
                if point.num is not None and isinstance(point.num, PointNum) and name in useful_points:
                    points.append((name, point.num.x, point.num.y))

            # Check if all useful points have coordinates
            points_with_coords = {p[0] for p in points}
            missing_points = set(useful_points) - points_with_coords
            if missing_points:
                result["error"] = f"Missing coordinates for points: {', '.join(sorted(missing_points))}"
                return result

            # Call DDAR.run_ddar() directly
            # CRITICAL: log_enabled=True and exp_enabled=True are required for CSolver to work correctly!
            from newclid.DDAR.build import DDAR

            solved, dep_graph = DDAR.run_ddar(
                f"rule_test_{self.seed}",
                points,
                premises,
                goals,
                500,   # max_level
                True,  # log_enabled (CRITICAL!)
                True   # exp_enabled (CRITICAL!)
            )

            result["success"] = solved
            if not solved:
                result["error"] = "CSolver failed to prove the rule"

        except AttributeError as e:
            # Common error: Point.num is None during numerical validation
            if "'Point' object has no attribute 'num'" in str(e) or "has no attribute 'num'" in str(e):
                result["error"] = "Geometry construction failed: numerical validation error"
            else:
                result["error"] = f"CSolver error: {str(e)}"
        except Exception as e:
            result["error"] = f"CSolver error: {str(e)}"

        return result

    def batch_test(
        self,
        rules: List[Tuple[str, str]],
        max_workers: int = 1,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Test multiple rules in parallel.

        Args:
            rules: List of (rule_id, rule_text) tuples
            max_workers: Number of parallel workers
            timeout: Override default timeout

        Returns:
            Dict with batch test results:
                - total: total number of rules
                - valid: number of valid rules
                - invalid: number of invalid rules
                - failed_conversion: number of rules that failed conversion
                - filtered: number of rules filtered as generative
                - results: list of individual test results
        """
        if timeout is None:
            timeout = self.timeout

        results = {
            "total": len(rules),
            "valid": 0,
            "invalid": 0,
            "failed_conversion": 0,
            "filtered": 0,
            "results": [],
        }

        if max_workers > 1:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for rule_id, rule_text in rules:
                    future = executor.submit(self._test_rule_worker, rule_id, rule_text, timeout)
                    futures[future] = rule_id

                for future in as_completed(futures):
                    rule_id = futures[future]
                    try:
                        test_result = future.result()
                        results["results"].append(test_result)
                        if test_result.get("filtered"):
                            results["filtered"] += 1
                        elif test_result.get("problem") is None:
                            results["failed_conversion"] += 1
                        elif test_result.get("success"):
                            results["valid"] += 1
                        else:
                            results["invalid"] += 1
                    except Exception as e:
                        results["results"].append({
                            "rule_id": rule_id,
                            "success": False,
                            "error": str(e),
                        })
                        results["invalid"] += 1
        else:
            for rule_id, rule_text in rules:
                test_result = self._test_rule_worker(rule_id, rule_text, timeout)
                results["results"].append(test_result)
                if test_result.get("filtered"):
                    results["filtered"] += 1
                elif test_result.get("problem") is None:
                    results["failed_conversion"] += 1
                elif test_result.get("success"):
                    results["valid"] += 1
                else:
                    results["invalid"] += 1

        return results

    def _test_rule_worker(self, rule_id: str, rule_text: str, timeout: int) -> Dict[str, Any]:
        """Worker function for testing a single rule."""
        result = self.test_rule(rule_text, timeout=timeout)
        result["rule_id"] = rule_id
        return result


def _test_rule_standalone(rule_id: str, rule_text: str, timeout: int, seed: int, use_csolver: bool = True) -> Dict[str, Any]:
    """Standalone function for multiprocessing."""
    tester = RuleTester(timeout=timeout, seed=seed, use_csolver=use_csolver)
    result = tester.test_rule(rule_text, timeout=timeout)
    result["rule_id"] = rule_id
    return result


__all__ = ["RuleTester"]
