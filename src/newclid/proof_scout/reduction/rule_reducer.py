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
import threading
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
        solver_type: str = "python",
        engine: str = "full",
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
            solver_type: "python" for DirectSolver (DDARN), "csolver" for CSolver (C++ DDAR)
            engine: DDAR engine variant ("full" or "weak"), only used when solver_type="csolver"
        """
        self.timeout = timeout
        self.seed = seed
        self.verbose = verbose
        self.n_workers = n_workers
        self.batch_size = batch_size
        self.max_premises = max_premises
        self.debug = debug
        self.debug_output_dir = Path(debug_output_dir) if debug_output_dir else None
        self.solver_type = solver_type
        self.engine = engine

        proof_output_file = None
        if debug and self.debug_output_dir is not None:
            proof_output_file = self.debug_output_dir / "subsumption_proofs.txt"
            self.debug_output_dir.mkdir(parents=True, exist_ok=True)
            proof_output_file.write_text("", encoding="utf-8")

        self.scorer = GeneralityScorer()
        if solver_type == "csolver":
            from newclid.proof_scout.reduction.subsumption_tester import SubsumptionTesterCSolver
            self.tester = SubsumptionTesterCSolver(
                timeout=timeout,
                seed=seed,
                proof_output_file=proof_output_file,
                engine=engine,
            )
        else:
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
                        self.solver_type,
                        self.engine,
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

    # Load source data file (supports both JSON and JSONL)
    entries = []
    target_rids = set(rule_map.keys())
    try:
        with open(source_data_file) as f:
            # More robust detection: read the first line
            first_line = f.readline()
            if not first_line:
                return [], failures

            f.seek(0)
            is_jsonl = False
            try:
                data = json.loads(first_line)
                # If first line is a valid JSON object AND it's not the whole file
                # (or if it doesn't have the "entries" key which is our JSON convention)
                if isinstance(data, dict) and "entries" not in data:
                    is_jsonl = True
            except json.JSONDecodeError:
                # If first line is not valid JSON, it might be a multi-line JSON or something else
                # Fallback to standard json.load which will handle multi-line formatted JSON
                is_jsonl = False

            if not is_jsonl:
                # Standard JSON
                try:
                    source_data = json.load(f)
                    entries = source_data.get("entries", [])
                except json.JSONDecodeError as e:
                    if "Extra data" in str(e):
                        # Fallback to JSONL if we see extra data
                        f.seek(0)
                        is_jsonl = True
                    else:
                        raise e

            if is_jsonl:
                # Assume JSONL (one JSON object per line)
                # To save memory, only load entries that match rule_map keys
                f.seek(0)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        rid = entry.get("rid") or entry.get("pid")
                        if rid in target_rids:
                            if "rid" not in entry and "pid" in entry:
                                entry["rid"] = entry["pid"]
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"Error loading source data: {e}")
        return [], failures

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
    solver_type: str = "python",
    engine: str = "full",
) -> List[str]:
    """Worker function for parallel subsumption testing.

    Tests if rule_strong subsumes any rules in rules_weak.

    Args:
        rule_strong: RuleWithSource that might subsume others
        rules_weak: List of RuleWithSource to test against
        timeout: Timeout in seconds for each test
        seed: Random seed
        solver_type: "python" for DirectSolver, "csolver" for CSolver
        engine: DDAR engine variant ("full" or "weak")

    Returns:
        List of rule_ids that are subsumed by rule_strong
    """
    if solver_type == "csolver":
        from newclid.proof_scout.reduction.subsumption_tester import SubsumptionTesterCSolver
        tester = SubsumptionTesterCSolver(timeout=timeout, seed=seed, engine=engine)
    else:
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


class IncrementalReducer:
    """Background reducer that processes seed groups as they arrive from Stage 1.

    Usage:
        queue = Queue()
        reducer = IncrementalReducer(rule_reducer, queue)
        reducer.start()
        # ... Stage 1 pushes ("seed_done", seed, rules) and ("all_done", no_seed_rules) ...
        result = reducer.join()  # blocks until done
    """

    def __init__(self, reducer: RuleReducer, queue, *, verbose: bool = True):
        self.reducer = reducer
        self.queue = queue
        self.verbose = verbose
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[Dict[str, Any]] = None
        self._group_survivors: List[RuleWithSource] = []
        self._group_stats: List[Dict[str, Any]] = []
        self._total_group_eliminated = 0
        self._total_group_skipped = 0

    def start(self):
        import threading
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """Consume queue messages and reduce seed groups incrementally."""
        while True:
            msg = self.queue.get()
            if msg[0] == "seed_done":
                _, seed_val, rule_entries = msg
                self._process_seed_group(seed_val, rule_entries)
            elif msg[0] == "all_done":
                _, no_seed_rules = msg
                self._finalize(no_seed_rules)
                break

    def _process_seed_group(self, seed_val, rule_entries: list):
        """Reduce a single seed group."""
        if not rule_entries:
            return

        # Convert entries to RuleWithSource
        rules = _entries_to_rules_with_source(rule_entries)
        if not rules:
            return

        if self.verbose:
            print(f"\n[IncrementalReducer] Seed group {seed_val}: {len(rules)} rules")

        result = self.reducer.reduce(rules)
        survivors = result.get("basis_rules", [])
        self._group_survivors.extend(survivors)
        self._total_group_eliminated += result["stats"]["eliminated_count"]
        self._total_group_skipped += result["stats"]["skipped_by_premises_count"]
        self._group_stats.append({
            "seed": seed_val,
            "input": result["stats"]["original_count"],
            "basis": result["stats"]["basis_count"],
            "eliminated": result["stats"]["eliminated_count"],
        })

    def _finalize(self, no_seed_entries: list):
        """Run global reduction on all group survivors + no-seed rules."""
        no_seed_rules = _entries_to_rules_with_source(no_seed_entries)
        all_survivors = self._group_survivors + no_seed_rules

        if self.verbose:
            print(f"\n[IncrementalReducer] Global phase: {len(all_survivors)} survivors")

        if all_survivors:
            global_result = self.reducer.reduce(all_survivors)
        else:
            global_result = {
                "basis_rules": [],
                "eliminated_rules": [],
                "skipped_by_premises": [],
                "stats": {"original_count": 0, "basis_count": 0,
                          "eliminated_count": 0, "skipped_by_premises_count": 0,
                          "reduction_rate": 0, "n_subsumption_tests": 0},
            }

        self._result = {
            "basis_rules": global_result["basis_rules"],
            "eliminated_rules": global_result["eliminated_rules"],
            "skipped_by_premises": global_result["skipped_by_premises"],
            "stats": {
                "original_count": sum(s["input"] for s in self._group_stats) + len(no_seed_rules),
                "group_phase": {
                    "n_groups": len(self._group_stats),
                    "n_no_seed": len(no_seed_rules),
                    "survivors": len(all_survivors),
                    "eliminated": self._total_group_eliminated,
                    "group_details": self._group_stats,
                },
                "global_phase": global_result["stats"],
                "basis_count": global_result["stats"]["basis_count"],
                "total_eliminated": self._total_group_eliminated + global_result["stats"]["eliminated_count"],
            },
        }

    def join(self, timeout=None) -> Optional[Dict[str, Any]]:
        """Wait for the reducer thread to finish and return results."""
        if self._thread:
            self._thread.join(timeout=timeout)
        return self._result


def _entries_to_rules_with_source(entries: list) -> List[RuleWithSource]:
    """Convert rule entry dicts (from Stage 1 output) to RuleWithSource objects."""
    rules = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        rule_text = e.get("norm_rule") or e.get("rule", "")
        rule_id = e.get("rid", "")
        llm_input = e.get("llm_input_renamed", "")
        llm_output = e.get("llm_output_renamed", "")
        point_coords = e.get("point_coords", {})
        seed = e.get("seed")

        if not rule_text or not llm_input:
            continue

        try:
            premises, goal = _parse_llm_input(llm_input)
            points = [(name, coords[0], coords[1]) for name, coords in point_coords.items()]
            rules.append(RuleWithSource(
                rule_id=rule_id,
                rule_text=rule_text,
                points=points,
                premises=premises,
                goal=goal,
                llm_output_renamed=llm_output,
                seed=seed,
            ))
        except Exception:
            continue
    return rules


def load_rules_by_ids(
    rule_ids: List[str],
    source_data_file: Path,
) -> Tuple[List[RuleWithSource], List[Tuple[str, str]]]:
    """Load RuleWithSource objects for specific rule IDs from source data.

    Used for checkpoint resume: read rule_id list from survivors.txt,
    then restore full RuleWithSource objects from the original source data.

    Args:
        rule_ids: List of rule IDs to load (e.g., ["r000042", "r000123"])
        source_data_file: Path to step6_rules_stats.json or JSONL file

    Returns:
        Tuple of (rules, failures) where failures is [(rule_id, reason), ...]
    """
    import json

    # Load source data file (supports both JSON and JSONL)
    entries = []
    target_rids = set(rule_ids)
    try:
        with open(source_data_file) as f:
            # More robust detection: read the first line
            first_line = f.readline()
            if not first_line:
                return [], [(rid, "Empty source data file") for rid in rule_ids]

            f.seek(0)
            is_jsonl = False
            try:
                data = json.loads(first_line)
                # If first line is a valid JSON object AND it doesn't have "entries" key
                if isinstance(data, dict) and "entries" not in data:
                    is_jsonl = True
            except json.JSONDecodeError:
                is_jsonl = False

            if not is_jsonl:
                # Standard JSON
                try:
                    source_data = json.load(f)
                    entries = source_data.get("entries", [])
                except json.JSONDecodeError as e:
                    if "Extra data" in str(e):
                        # Fallback to JSONL if we see extra data
                        f.seek(0)
                        is_jsonl = True
                    else:
                        raise e

            if is_jsonl:
                # Assume JSONL (one JSON object per line)
                # Only load entries that match target rule IDs
                f.seek(0)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        rid = entry.get("rid") or entry.get("pid")
                        if rid in target_rids:
                            if "rid" not in entry and "pid" in entry:
                                entry["rid"] = entry["pid"]
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"Error loading source data: {e}")
        return [], [(rid, str(e)) for rid in rule_ids]

    entry_map = {entry["rid"]: entry for entry in entries}

    rules = []
    failures = []

    for rule_id in rule_ids:
        entry = entry_map.get(rule_id)
        if not entry:
            failures.append((rule_id, "No source data entry found"))
            continue

        llm_input = entry.get("llm_input_renamed", "")
        llm_output = entry.get("llm_output_renamed", "")
        point_coords = entry.get("point_coords", {})
        seed = entry.get("seed")
        rule_text = entry.get("norm_rule") or entry.get("rule", "")

        if not llm_input or not rule_text:
            failures.append((rule_id, "Empty llm_input_renamed or rule_text"))
            continue

        try:
            premises, goal = _parse_llm_input(llm_input)
            points = [(name, coords[0], coords[1]) for name, coords in point_coords.items()]
            rules.append(RuleWithSource(
                rule_id=rule_id,
                rule_text=rule_text,
                points=points,
                premises=premises,
                goal=goal,
                llm_output_renamed=llm_output,
                seed=seed,
            ))
        except Exception as e:
            failures.append((rule_id, str(e)))

    return rules, failures


def _reduce_chunk_worker(
    chunk_rules: List[RuleWithSource],
    timeout: int,
    seed: int,
    max_premises: Optional[int],
    batch_size: int,
    solver_type: str,
    engine: str,
) -> Dict[str, Any]:
    """Worker function for parallel chunk reduction.

    Creates its own RuleReducer instance and reduces a chunk independently.
    """
    reducer = RuleReducer(
        timeout=timeout,
        seed=seed,
        max_premises=None,  # premises already filtered
        n_workers=1,  # no nested parallelism
        batch_size=batch_size,
        verbose=True,
        solver_type=solver_type,
        engine=engine,
    )
    return reducer.reduce(chunk_rules)


class ChunkedIterativeReducer:
    """Chunked iterative rule reduction for large rule sets.

    Splits N rules into groups of group_size, reduces each group independently,
    then merges survivors for the next round. Reduces O(n^2) to ~O(n*G*k).
    """

    def __init__(
        self,
        timeout: int = 60,
        seed: int = 42,
        batch_size: int = 10,
        solver_type: str = "csolver",
        engine: str = "full",
        verbose: bool = True,
    ):
        self.timeout = timeout
        self.seed = seed
        self.batch_size = batch_size
        self.solver_type = solver_type
        self.engine = engine
        self.verbose = verbose

    @staticmethod
    def filter_by_premises(
        rules: List[RuleWithSource],
        max_premises: int,
    ) -> Tuple[List[RuleWithSource], List[Dict[str, Any]]]:
        """Filter rules exceeding max_premises.

        Returns:
            (kept, skipped) where skipped is a list of dicts with rule info.
        """
        kept = []
        skipped = []
        for rule in rules:
            if '=>' in rule.rule_text:
                n_prem = len([c for c in rule.rule_text.split('=>')[0].split(',') if c.strip()])
            else:
                n_prem = 0
            if n_prem <= max_premises:
                kept.append(rule)
            else:
                skipped.append({
                    "rule_id": rule.rule_id,
                    "rule_text": rule.rule_text,
                    "n_premises": n_prem,
                    "reason": f"Exceeds max_premises={max_premises} (has {n_prem})",
                })
        return kept, skipped

    def reduce_one_round(
        self,
        rules: List[RuleWithSource],
        group_size: int,
        chunk_workers: int = 4,
    ) -> Tuple[List[RuleWithSource], Dict[str, Any]]:
        """One round of chunked reduction.

        Splits rules into chunks, reduces each independently (parallel),
        and merges survivors.

        Returns:
            (survivors, round_stats)
        """
        import math
        import time as _time
        from concurrent.futures import ProcessPoolExecutor, as_completed

        n_chunks = math.ceil(len(rules) / group_size)
        chunks = [rules[i * group_size:(i + 1) * group_size] for i in range(n_chunks)]

        if self.verbose:
            print(f"  Splitting {len(rules)} rules into {n_chunks} chunks (group_size={group_size})")

        round_start = _time.time()
        survivors = []
        chunk_stats = []

        if chunk_workers <= 1 or n_chunks == 1:
            # Sequential
            for ci, chunk in enumerate(chunks):
                if self.verbose:
                    print(f"\n  --- Chunk {ci}/{n_chunks}: {len(chunk)} rules ---")
                result = _reduce_chunk_worker(
                    chunk, self.timeout, self.seed, None,
                    self.batch_size, self.solver_type, self.engine,
                )
                basis = result.get("basis_rules", [])
                survivors.extend(basis)
                chunk_stats.append({
                    "chunk_id": ci,
                    "input": len(chunk),
                    "survivors": len(basis),
                    "eliminated": result["stats"]["eliminated_count"],
                    "n_tests": result["stats"]["n_subsumption_tests"],
                })
        else:
            # Parallel
            with ProcessPoolExecutor(max_workers=chunk_workers) as executor:
                future_to_ci = {}
                for ci, chunk in enumerate(chunks):
                    if self.verbose:
                        print(f"  Submitting chunk {ci}/{n_chunks}: {len(chunk)} rules")
                    future = executor.submit(
                        _reduce_chunk_worker,
                        chunk, self.timeout, self.seed, None,
                        self.batch_size, self.solver_type, self.engine,
                    )
                    future_to_ci[future] = ci

                for future in as_completed(future_to_ci):
                    ci = future_to_ci[future]
                    try:
                        result = future.result()
                        basis = result.get("basis_rules", [])
                        survivors.extend(basis)
                        chunk_stats.append({
                            "chunk_id": ci,
                            "input": len(chunks[ci]),
                            "survivors": len(basis),
                            "eliminated": result["stats"]["eliminated_count"],
                            "n_tests": result["stats"]["n_subsumption_tests"],
                        })
                        if self.verbose:
                            print(f"  Chunk {ci} done: {len(chunks[ci])} → {len(basis)} survivors")
                    except Exception as e:
                        print(f"  ERROR: Chunk {ci} failed: {e}")
                        # On failure, keep all rules from this chunk
                        survivors.extend(chunks[ci])
                        chunk_stats.append({
                            "chunk_id": ci,
                            "input": len(chunks[ci]),
                            "survivors": len(chunks[ci]),
                            "eliminated": 0,
                            "n_tests": 0,
                            "error": str(e),
                        })

        # Sort chunk_stats by chunk_id
        chunk_stats.sort(key=lambda x: x["chunk_id"])

        elapsed = _time.time() - round_start
        total_eliminated = sum(cs["eliminated"] for cs in chunk_stats)
        total_tests = sum(cs["n_tests"] for cs in chunk_stats)

        round_stats = {
            "input_count": len(rules),
            "survivors_count": len(survivors),
            "eliminated_count": total_eliminated,
            "n_chunks": n_chunks,
            "group_size": group_size,
            "chunk_workers": chunk_workers,
            "n_subsumption_tests": total_tests,
            "elapsed_seconds": elapsed,
            "chunk_details": chunk_stats,
        }

        if self.verbose:
            print(f"\n  Round result: {len(rules)} → {len(survivors)} survivors "
                  f"(eliminated {total_eliminated}, {elapsed:.1f}s)")

        return survivors, round_stats

    def reduce_iterative(
        self,
        rules: List[RuleWithSource],
        group_size: int,
        iterations: int = 1,
        chunk_workers: int = 4,
        output_dir: Optional[Path] = None,
        resume: bool = True,
    ) -> Tuple[List[RuleWithSource], Dict[str, Any]]:
        """Multi-round iterative chunked reduction.

        Args:
            rules: Input rules
            group_size: Rules per chunk
            iterations: Max number of rounds
            chunk_workers: Parallel workers for chunk reduction
            output_dir: Directory to save per-round results (enables resume)
            resume: If True, check for completed rounds and resume

        Returns:
            (final_survivors, overall_stats)
        """
        import json as _json
        import time as _time

        overall_start = _time.time()
        current_rules = rules
        start_round = 1
        all_round_stats = []

        # Checkpoint resume
        if resume and output_dir is not None:
            last_completed = 0
            for r in range(1, iterations + 1):
                round_dir = output_dir / f"round_{r:03d}"
                survivors_path = round_dir / "survivors.txt"
                if survivors_path.exists() and survivors_path.stat().st_size > 0:
                    last_completed = r
                else:
                    break

            if last_completed > 0:
                # Load survivors from last completed round
                round_dir = output_dir / f"round_{last_completed:03d}"
                survivors_path = round_dir / "survivors.txt"
                with open(survivors_path) as f:
                    lines = [line.strip() for line in f if line.strip()]

                # survivors.txt format: rule_id\nrule_text\n...
                survivor_ids = [lines[i] for i in range(0, len(lines), 2) if i + 1 < len(lines)]

                # Rebuild RuleWithSource from original rules
                rule_map = {r.rule_id: r for r in rules}
                current_rules = [rule_map[rid] for rid in survivor_ids if rid in rule_map]

                # Load accumulated stats
                for r in range(1, last_completed + 1):
                    stats_path = output_dir / f"round_{r:03d}" / "stats.json"
                    if stats_path.exists():
                        with open(stats_path) as f:
                            all_round_stats.append(_json.load(f))

                start_round = last_completed + 1
                if self.verbose:
                    print(f"[Resume] Found {last_completed} completed round(s), "
                          f"loaded {len(current_rules)} survivors from round_{last_completed:03d}")

        for round_num in range(start_round, iterations + 1):
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"Round {round_num}/{iterations}: {len(current_rules)} rules")
                print(f"{'='*60}")

            # If rules fit in one chunk, this is the final round
            if len(current_rules) <= group_size:
                if self.verbose:
                    print(f"  Rules ({len(current_rules)}) <= group_size ({group_size}), "
                          f"running final single-chunk reduction")

            survivors, round_stats = self.reduce_one_round(
                current_rules, group_size, chunk_workers,
            )
            round_stats["round"] = round_num
            all_round_stats.append(round_stats)

            # Save round results
            if output_dir is not None:
                round_dir = output_dir / f"round_{round_num:03d}"
                round_dir.mkdir(parents=True, exist_ok=True)

                # Save survivors
                survivors_path = round_dir / "survivors.txt"
                with open(survivors_path, "w", encoding="utf-8") as f:
                    for rule in survivors:
                        f.write(f"{rule.rule_id}\n{rule.rule_text}\n")

                # Save stats
                stats_path = round_dir / "stats.json"
                with open(stats_path, "w", encoding="utf-8") as f:
                    _json.dump(round_stats, f, ensure_ascii=False, indent=2)

            # Early termination: no rules eliminated this round
            if len(survivors) == len(current_rules):
                if self.verbose:
                    print(f"\n  No rules eliminated in round {round_num}, stopping early")
                break

            # Early termination: fits in one chunk
            if len(survivors) <= group_size:
                if self.verbose:
                    print(f"\n  Survivors ({len(survivors)}) <= group_size ({group_size}), done")
                break

            current_rules = survivors

        # Save final result
        if output_dir is not None:
            final_path = output_dir / "final_basis_rules.txt"
            with open(final_path, "w", encoding="utf-8") as f:
                for rule in survivors:
                    f.write(f"{rule.rule_id}\n{rule.rule_text}\n")
            if self.verbose:
                print(f"\nFinal basis rules saved to {final_path}")

        overall_elapsed = _time.time() - overall_start
        overall_stats = {
            "input_count": len(rules),
            "final_survivors_count": len(survivors),
            "total_eliminated": len(rules) - len(survivors),
            "total_rounds": len(all_round_stats),
            "group_size": group_size,
            "chunk_workers": chunk_workers,
            "elapsed_seconds": overall_elapsed,
            "round_stats": all_round_stats,
        }

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Iterative reduction complete: {len(rules)} → {len(survivors)} rules "
                  f"in {len(all_round_stats)} round(s), {overall_elapsed:.1f}s")
            print(f"{'='*60}")

        return survivors, overall_stats


__all__ = ["RuleReducer", "RuleWithSource", "IncrementalReducer",
           "load_rules_from_discovery_output", "ChunkedIterativeReducer",
           "load_rules_by_ids"]
