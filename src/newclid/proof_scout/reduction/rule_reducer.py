#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RuleReducer - Main orchestrator for rule reduction.

Implements a greedy algorithm to eliminate redundant rules:
1. Pre-filter by max_premises
2. Score rules by generality (fewer premises = more general)
3. Sort rules by generality (most general first)
4. For each rule, test if it subsumes any other rule
5. Eliminate subsumed rules
6. Return the minimal basis set
"""
from dataclasses import dataclass
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
import re
from pathlib import Path

from newclid.proof_scout.reduction.generality_scorer import GeneralityScorer
from newclid.proof_scout.reduction.subsumption_tester import SubsumptionTester


@dataclass
class RuleWithSource:
    """Rule with its source problem data."""
    rule_id: str                    # e.g., "r000042"
    rule_text: str                  # "premise1, premise2 => conclusion"
    points: List[Tuple[str, float, float]]  # [(name, x, y), ...]
    premises: List[Tuple[str, List[str]]]   # [(predicate, [args]), ...]
    goal: Tuple[str, List[str]]             # (predicate, [args])
    llm_output_renamed: str = ""    # Proof steps from original problem
    seed: Optional[int] = None      # Construction seed for group reduction

    # Parsed structure (computed lazily)
    _premises_parsed: Optional[List[Tuple[str, ...]]] = None
    conclusions: Optional[List[Tuple[str, ...]]] = None
    generality_score: Optional[Tuple[int, int]] = None  # (-n_premises, n_conclusions)

    def parse(self):
        """Parse rule text into premises and conclusions."""
        if self._premises_parsed is not None:
            return

        if '=>' not in self.rule_text:
            self._premises_parsed = []
            self.conclusions = []
            return

        premise_part, conclusion_part = self.rule_text.split('=>', 1)

        # Parse premises
        self._premises_parsed = []
        for condition in premise_part.split(','):
            parts = re.findall(r'\w+', condition)
            if parts:
                self._premises_parsed.append(tuple(parts))

        # Parse conclusions
        self.conclusions = []
        for condition in conclusion_part.split(','):
            parts = re.findall(r'\w+', condition)
            if parts:
                self.conclusions.append(tuple(parts))


class RuleReducer:
    """Main orchestrator for rule reduction."""

    def __init__(
        self,
        timeout: int = 60,
        seed: int = 42,
        verbose: bool = True,
        n_workers: int = 1,
        batch_size: int = 10,
        max_premises: Optional[int] = None,
        debug: bool = False,
        debug_output_dir: Optional[Path] = None,
    ):
        """Initialize RuleReducer.

        Args:
            timeout: Timeout in seconds for each subsumption test
            seed: Random seed for reproducibility
            verbose: Print progress messages
            n_workers: Number of parallel workers for subsumption testing
            batch_size: Progress reporting granularity (print every N rules processed)
            max_premises: Maximum number of premises allowed (default: None = no limit)
            debug: Output proof steps when a subsumption test succeeds
            debug_output_dir: Directory to write subsumption_proofs.txt; if None
                and debug=True, proof steps are printed to stdout
        """
        self.timeout = timeout
        self.seed = seed
        self.verbose = verbose
        self.n_workers = n_workers
        self.batch_size = batch_size
        self.max_premises = max_premises
        self.debug = debug
        self.debug_output_dir = Path(debug_output_dir) if debug_output_dir else None

        proof_output_file = None
        if debug and self.debug_output_dir is not None:
            proof_output_file = self.debug_output_dir / "subsumption_proofs.txt"
            self.debug_output_dir.mkdir(parents=True, exist_ok=True)
            proof_output_file.write_text("", encoding="utf-8")

        self.scorer = GeneralityScorer()
        self.tester = SubsumptionTester(
            timeout=timeout,
            seed=seed,
            proof_output_file=proof_output_file,
        )

    def reduce(self, rules: List[RuleWithSource]) -> Dict[str, Any]:
        """Reduce rules to a minimal basis set via greedy subsumption.

        Pipeline: max_premises pre-filter → generality sort → greedy elimination.

        Args:
            rules: List of RuleWithSource objects

        Returns:
            Dict with reduction results:
                - basis_rules: List of independent rules
                - eliminated_rules: List of eliminated rules with reasons
                - skipped_by_premises: List of rules skipped due to premise count
                - stats: Statistics about the reduction
        """
        if self.verbose:
            print(f"Starting rule reduction with {len(rules)} rules")

        original_count = len(rules)

        # Pre-filter: remove rules with too many premises
        skipped_by_premises = []
        if self.max_premises is not None:
            kept = []
            for rule in rules:
                if '=>' in rule.rule_text:
                    n_prem = len([c for c in rule.rule_text.split('=>')[0].split(',') if c.strip()])
                else:
                    n_prem = 0
                if n_prem <= self.max_premises:
                    kept.append(rule)
                else:
                    skipped_by_premises.append({
                        "rule_id": rule.rule_id,
                        "rule_text": rule.rule_text,
                        "n_premises": n_prem,
                        "reason": f"Exceeds max_premises={self.max_premises} (has {n_prem})",
                    })
            if self.verbose:
                print(f"  Pre-filter: {len(skipped_by_premises)} rules skipped (premises > {self.max_premises})")
                print(f"  Remaining: {len(kept)} rules")
            rules = kept

        if len(rules) == 0:
            if self.verbose:
                print("\nNo rules remaining after pre-filter!")
            return {
                "basis_rules": [],
                "eliminated_rules": [],
                "skipped_by_premises": skipped_by_premises,
                "stats": {
                    "original_count": original_count,
                    "skipped_by_premises_count": len(skipped_by_premises),
                    "basis_count": 0,
                    "eliminated_count": 0,
                    "reduction_rate": 0,
                    "n_subsumption_tests": 0,
                },
            }

        # Step 1: Compute generality scores and parse rules
        if self.verbose:
            print("Step 1: Computing generality scores...")

        for rule in rules:
            rule.generality_score = self.scorer.score(rule.rule_text)
            rule.parse()

        # Step 2: Sort by generality (most general first)
        # Score is (-n_premises, n_conclusions), so reverse=True puts fewer premises first
        sorted_rules = sorted(rules, key=lambda r: r.generality_score, reverse=True)

        if self.verbose:
            print(f"Step 2: Sorted {len(sorted_rules)} rules by generality")
            print(f"  Most general: {sorted_rules[0].rule_text[:60]}... (score: {sorted_rules[0].generality_score})")
            print(f"  Least general: {sorted_rules[-1].rule_text[:60]}... (score: {sorted_rules[-1].generality_score})")

        # Step 3: Greedy elimination
        if self.verbose:
            mode = "parallel (serial state)" if self.n_workers > 1 else "sequential"
            print(f"Step 3: Greedy elimination ({mode})...")

        active_flags = [True] * len(sorted_rules)
        eliminated_rules = []
        n_tests = 0

        # Get batch_size from instance or use default
        batch_size = getattr(self, 'batch_size', 10)

        if self.n_workers > 1:
            # Parallel execution with serial state updates to avoid race conditions
            # Each rule_i is processed sequentially so active_flags stays consistent,
            # but the subsumption tests for rule_i vs all targets run in parallel.
            from concurrent.futures import ProcessPoolExecutor

            if self.verbose:
                print(f"  Using {self.n_workers} workers (serial state updates, progress every {batch_size} rules)")

            with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
                for i, rule_i in enumerate(sorted_rules):
                    if not active_flags[i]:
                        continue

                    # Progress reporting
                    if self.verbose and (i + 1) % batch_size == 0:
                        n_active = sum(active_flags)
                        print(f"  Progress: {i+1}/{len(sorted_rules)} rules processed, {n_active} active, {n_tests} tests")

                    # Build target rules based on CURRENT active_flags (not a stale snapshot)
                    target_rules = []
                    target_indices = []
                    for j in range(len(sorted_rules)):
                        if active_flags[j] and j != i:
                            target_rules.append(sorted_rules[j])
                            target_indices.append(j)

                    if not target_rules:
                        continue

                    # Submit single rule's subsumption tests to worker pool, wait for result
                    future = executor.submit(
                        _test_subsumption_batch_worker,
                        rule_i,
                        target_rules,
                        self.timeout,
                        self.seed,
                    )

                    try:
                        eliminated_ids = future.result()
                        n_tests += len(target_indices)

                        # Immediately update active_flags before processing next rule
                        for rule_id in eliminated_ids:
                            for j, rule_j in enumerate(sorted_rules):
                                if rule_j.rule_id == rule_id and active_flags[j]:
                                    active_flags[j] = False
                                    eliminated_rules.append({
                                        "rule_id": rule_j.rule_id,
                                        "rule_text": rule_j.rule_text,
                                        "subsumed_by": rule_i.rule_id,
                                        "reason": f"Subsumed by {rule_i.rule_id}",
                                    })

                                    if self.verbose:
                                        print(f"    Eliminated {rule_j.rule_id} (subsumed by {rule_i.rule_id})")
                                    break
                    except Exception as e:
                        if self.verbose:
                            print(f"  Warning: Error processing rule {rule_i.rule_id}: {e}")

        else:
            # Sequential execution (original code)
            for i, rule_i in enumerate(sorted_rules):
                if not active_flags[i]:
                    continue

                if self.verbose and (i + 1) % 10 == 0:
                    n_active = sum(active_flags)
                    print(f"  Progress: {i+1}/{len(sorted_rules)} rules processed, {n_active} active, {n_tests} tests")

                # Test subsumption: rule_i vs all other rules
                # IMPORTANT: Check all j (not just j > i), because generality score is heuristic
                for j in range(len(sorted_rules)):
                    if i == j or not active_flags[j]:
                        continue

                    rule_j = sorted_rules[j]

                    # Test if rule_i subsumes rule_j
                    n_tests += 1
                    if self.tester.test_subsumption(rule_i, rule_j, debug=self.debug):
                        active_flags[j] = False
                        eliminated_rules.append({
                            "rule_id": rule_j.rule_id,
                            "rule_text": rule_j.rule_text,
                            "subsumed_by": rule_i.rule_id,
                            "reason": f"Subsumed by {rule_i.rule_id}",
                        })

                        if self.verbose:
                            print(f"    Eliminated {rule_j.rule_id} (subsumed by {rule_i.rule_id})")

        # Collect basis rules
        basis_rules = [r for i, r in enumerate(sorted_rules) if active_flags[i]]

        if self.verbose:
            print(f"\nReduction complete!")
            print(f"  Original rules: {original_count}")
            print(f"  Skipped (premises): {len(skipped_by_premises)}")
            print(f"  Basis rules: {len(basis_rules)}")
            print(f"  Eliminated rules: {len(eliminated_rules)}")
            rate = len(eliminated_rules) / len(rules) * 100 if rules else 0
            print(f"  Reduction rate: {rate:.1f}%")
            print(f"  Total subsumption tests: {n_tests}")

        return {
            "basis_rules": basis_rules,
            "eliminated_rules": eliminated_rules,
            "skipped_by_premises": skipped_by_premises,
            "stats": {
                "original_count": original_count,
                "skipped_by_premises_count": len(skipped_by_premises),
                "basis_count": len(basis_rules),
                "eliminated_count": len(eliminated_rules),
                "reduction_rate": len(eliminated_rules) / len(rules) if rules else 0,
                "n_subsumption_tests": n_tests,
            },
        }

    def reduce_by_seed(self, rules: List[RuleWithSource]) -> Dict[str, Any]:
        """Two-level reduction: group reduction by seed, then global reduction.

        1. Group rules by seed
        2. Within each group: max_premises pre-filter → generality sort → greedy elimination
        3. Collect survivors from all groups
        4. Global reduction on survivors (same as reduce())

        Returns:
            Dict with group_stats, global_result, and combined stats.
        """
        # Group rules by seed
        seed_groups: Dict[Any, List[RuleWithSource]] = defaultdict(list)
        no_seed_rules: List[RuleWithSource] = []
        for r in rules:
            if r.seed is not None:
                seed_groups[r.seed].append(r)
            else:
                no_seed_rules.append(r)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"[reduce_by_seed] {len(rules)} rules, "
                  f"{len(seed_groups)} seed groups, "
                  f"{len(no_seed_rules)} rules without seed")
            print(f"{'='*60}")

        # Phase 1: Group reduction
        group_survivors: List[RuleWithSource] = []
        group_stats: List[Dict[str, Any]] = []
        total_group_eliminated = 0
        total_group_skipped = 0

        for seed_val, group_rules in sorted(seed_groups.items()):
            if self.verbose:
                print(f"\n--- Seed group {seed_val}: {len(group_rules)} rules ---")

            result = self.reduce(group_rules)
            group_survivors.extend(result["basis_rules"])
            total_group_eliminated += result["stats"]["eliminated_count"]
            total_group_skipped += result["stats"]["skipped_by_premises_count"]
            group_stats.append({
                "seed": seed_val,
                "input": result["stats"]["original_count"],
                "basis": result["stats"]["basis_count"],
                "eliminated": result["stats"]["eliminated_count"],
                "skipped_premises": result["stats"]["skipped_by_premises_count"],
            })

        # Add no-seed rules directly to global pool
        group_survivors.extend(no_seed_rules)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"[reduce_by_seed] Group phase done: "
                  f"{len(rules)} → {len(group_survivors)} survivors "
                  f"(eliminated {total_group_eliminated}, "
                  f"skipped {total_group_skipped})")
            print(f"[reduce_by_seed] Starting global reduction...")
            print(f"{'='*60}")

        # Phase 2: Global reduction on survivors
        global_result = self.reduce(group_survivors)

        # Combined stats
        return {
            "basis_rules": global_result["basis_rules"],
            "eliminated_rules": global_result["eliminated_rules"],
            "skipped_by_premises": global_result["skipped_by_premises"],
            "stats": {
                "original_count": len(rules),
                "group_phase": {
                    "n_groups": len(seed_groups),
                    "n_no_seed": len(no_seed_rules),
                    "survivors": len(group_survivors),
                    "eliminated": total_group_eliminated,
                    "skipped_premises": total_group_skipped,
                    "group_details": group_stats,
                },
                "global_phase": global_result["stats"],
                "basis_count": global_result["stats"]["basis_count"],
                "total_eliminated": total_group_eliminated + global_result["stats"]["eliminated_count"],
                "total_reduction_rate": (
                    1 - global_result["stats"]["basis_count"] / len(rules)
                ) if rules else 0,
            },
        }


def _parse_llm_input(llm_input: str) -> Tuple[List[Tuple[str, List[str]]], Tuple[str, List[str]]]:
    """Parse llm_input_renamed format into premises and goal.

    Format: <problem> a : ; b : ; c : perp a b a c [000] ; ... ? goal </problem>

    Returns:
        Tuple of (premises, goal) where:
        - premises: List[(predicate, [args]), ...]
        - goal: (predicate, [args])
    """
    # Remove <problem> tags
    text = llm_input.strip()
    if text.startswith("<problem>"):
        text = text[9:].strip()
    if text.endswith("</problem>"):
        text = text[:-10].strip()

    # Split by '?' to separate premises from goal
    if '?' not in text:
        raise ValueError(f"No goal marker '?' found in llm_input: {text}")

    premise_part, goal_part = text.split('?', 1)

    # Parse goal (single predicate)
    goal_tokens = goal_part.strip().split()
    if not goal_tokens:
        raise ValueError(f"Empty goal in llm_input: {text}")
    goal_pred = goal_tokens[0]
    goal_args = goal_tokens[1:] if len(goal_tokens) > 1 else []
    goal = (goal_pred, goal_args)

    # Parse premises
    premises = []
    clauses = premise_part.split(';')

    for clause in clauses:
        clause = clause.strip()
        if not clause or ':' not in clause:
            continue

        # Split by ':' to get point declaration and predicates
        _, pred_part = clause.split(':', 1)
        pred_part = pred_part.strip()

        if not pred_part:
            continue

        # Remove [NNN] tags
        pred_part = re.sub(r'\[\d+\]', '', pred_part).strip()

        # Split by predicate names (known predicates)
        # Common predicates: cong, para, perp, coll, cyclic, eqangle, eqratio, midp, etc.
        predicate_pattern = r'\b(cong|para|perp|coll|cyclic|eqangle|eqratio|midp|eqpoint|sameside|ncoll|on_line|on_circle|on_pline|on_tline|square|rect|iso_triangle|right_triangle|equilateral|parallelogram|trapezoid)\b'

        # Find all predicates and their positions
        matches = list(re.finditer(predicate_pattern, pred_part))

        for i, match in enumerate(matches):
            pred_name = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(pred_part)
            args_str = pred_part[start:end].strip()
            args = args_str.split() if args_str else []
            premises.append((pred_name, args))

    return premises, goal


def load_rules_from_discovery_output(
    rules_file: Path,
    source_data_file: Path,
    max_rules: Optional[int] = None,
) -> Tuple[List[RuleWithSource], List[Tuple[str, str, str]]]:
    """Load rules from discovery pipeline output.

    Args:
        rules_file: Path to *_pruned_rules.txt (format: rule_id\\nrule_text\\n...)
        source_data_file: Path to step6_rules_stats.json with llm_input_renamed and point_coords
        max_rules: Maximum number of rules to load (for testing)

    Returns:
        Tuple of (rules, failures) where failures is a list of (rule_id, rule_text, error_reason)
    """
    import json

    rules = []
    failures = []

    # Load rules file
    with open(rules_file) as f:
        lines = [line.strip() for line in f if line.strip()]

    # Parse rule_id and rule_text pairs
    rule_map = {}
    for i in range(0, len(lines), 2):
        if i + 1 >= len(lines):
            break
        rule_id = lines[i]
        rule_text = lines[i + 1]
        rule_map[rule_id] = rule_text

    # Load source data file
    with open(source_data_file) as f:
        source_data = json.load(f)

    entries = source_data.get("entries", [])

    # Build rid -> entry mapping
    entry_map = {entry["rid"]: entry for entry in entries}

    # Process each rule
    for rule_id, rule_text in rule_map.items():
        try:
            # Get source data entry
            entry = entry_map.get(rule_id)
            if not entry:
                failures.append((rule_id, rule_text, "No source data entry found"))
                continue

            llm_input = entry.get("llm_input_renamed", "")
            llm_output = entry.get("llm_output_renamed", "")
            point_coords = entry.get("point_coords", {})
            seed = entry.get("seed")

            if not llm_input:
                failures.append((rule_id, rule_text, "Empty llm_input_renamed"))
                continue

            # Parse llm_input to get premises and goal
            premises, goal = _parse_llm_input(llm_input)

            # Convert point_coords to points list
            points = [(name, coords[0], coords[1]) for name, coords in point_coords.items()]

            # Create RuleWithSource
            rules.append(RuleWithSource(
                rule_id=rule_id,
                rule_text=rule_text,
                points=points,
                premises=premises,
                goal=goal,
                llm_output_renamed=llm_output,
                seed=seed,
            ))

            if max_rules and len(rules) >= max_rules:
                break

        except Exception as e:
            failures.append((rule_id, rule_text, str(e)))
            print(f"Warning: Failed to process {rule_id}: {e}")

    return rules, failures


def _test_subsumption_batch_worker(
    rule_strong: RuleWithSource,
    rules_weak: List[RuleWithSource],
    timeout: int,
    seed: int,
) -> List[str]:
    """Worker function for parallel subsumption testing.

    Tests if rule_strong subsumes any rules in rules_weak using DirectSolver.

    Args:
        rule_strong: RuleWithSource that might subsume others
        rules_weak: List of RuleWithSource to test against
        timeout: Timeout in seconds for each test
        seed: Random seed

    Returns:
        List of rule_ids that are subsumed by rule_strong
    """
    from newclid.proof_scout.reduction.subsumption_tester import SubsumptionTester

    tester = SubsumptionTester(timeout=timeout, seed=seed)
    eliminated = []

    for rule_weak in rules_weak:
        try:
            if tester.test_subsumption(rule_strong, rule_weak):
                eliminated.append(rule_weak.rule_id)
        except Exception:
            # If test fails, conservatively assume no subsumption
            pass

    return eliminated


__all__ = ["RuleReducer", "RuleWithSource", "load_rules_from_discovery_output"]
