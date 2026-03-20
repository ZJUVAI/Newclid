#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discovery Pipeline - End-to-end pipeline from Generation to Evaluation.

This script orchestrates the complete discovery workflow:
1. Stage 1: FilterAndPruneEngine - Filter, deduplicate, prune, extract rules
2. Stage 2: RuleConverter - Validate predicates, convert to DDAR format
3. Stage 3: RuleTester - Verify rules using DDAR solver (with batch processing)
4. Stage 4 (optional): Evaluation - Test on benchmark problems

Features:
- Batch processing for large rule sets (configurable batch size and timeout)
- Comprehensive rule analysis (premise/conclusion distribution, complexity)
- Markdown report generation

Usage:
    python scripts/discovery_pipeline.py \
        --input datasets/geometry_clauses15_samples1M.jsonl \
        --output outputs/discovery_run \
        --benchmark benchmarks/core/imo_ag_30.txt \
        --max_workers 50
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Rule Analysis Functions
# ============================================================================

def _parse_rule_for_analysis(rule_text: str) -> Tuple[List[Tuple[str, List[str]]], List[Tuple[str, List[str]]]]:
    """Parse rule text into premises and conclusions for analysis."""
    if "=>" not in rule_text:
        return [], []

    left, right = rule_text.split("=>", 1)

    def parse_clauses(text: str) -> List[Tuple[str, List[str]]]:
        clauses = []
        for clause in text.split(","):
            parts = clause.strip().split()
            if parts:
                pred = parts[0].lower()
                args = [a.lower() for a in parts[1:]]
                clauses.append((pred, args))
        return clauses

    premises = parse_clauses(left)
    conclusions = parse_clauses(right)
    return premises, conclusions


def _collect_variables(clauses: List[Tuple[str, List[str]]]) -> set:
    """Collect all variable names from clauses."""
    variables = set()
    for _, args in clauses:
        for arg in args:
            if re.match(r"^[a-z][a-z0-9_]*$", arg):
                variables.add(arg)
    return variables


def analyze_rules(rules: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Analyze extracted rules and return comprehensive statistics.

    Args:
        rules: List of (rule_id, rule_text) tuples

    Returns:
        Dict with analysis results including distributions and statistics
    """
    analysis = {
        "total": len(rules),
        "premise_count_dist": Counter(),
        "conclusion_count_dist": Counter(),
        "conclusion_predicates": Counter(),
        "premise_predicates": Counter(),
        "complexity_dist": Counter(),
        "variable_count_dist": Counter(),
        "predicate_combinations": Counter(),
        "parse_errors": 0,
    }

    for rule_id, rule_text in rules:
        try:
            premises, conclusions = _parse_rule_for_analysis(rule_text)

            if not premises and not conclusions:
                analysis["parse_errors"] += 1
                continue

            # Premise count distribution
            n_premises = len(premises)
            analysis["premise_count_dist"][n_premises] += 1

            # Conclusion count distribution
            n_conclusions = len(conclusions)
            analysis["conclusion_count_dist"][n_conclusions] += 1

            # Conclusion predicates
            for pred, _ in conclusions:
                analysis["conclusion_predicates"][pred] += 1

            # Premise predicates
            for pred, _ in premises:
                analysis["premise_predicates"][pred] += 1

            # Complexity classification
            if n_premises <= 2:
                complexity = "simple"
            elif n_premises <= 4:
                complexity = "medium"
            else:
                complexity = "complex"
            analysis["complexity_dist"][complexity] += 1

            # Variable count
            all_vars = _collect_variables(premises + conclusions)
            n_vars = len(all_vars)
            analysis["variable_count_dist"][n_vars] += 1

            # Predicate combination (sorted premise predicates -> conclusion predicate)
            prem_preds = tuple(sorted([p for p, _ in premises]))
            conc_preds = tuple([p for p, _ in conclusions])
            combo = f"{'+'.join(prem_preds)} => {'+'.join(conc_preds)}"
            analysis["predicate_combinations"][combo] += 1

        except Exception:
            analysis["parse_errors"] += 1

    # Convert Counters to dicts for JSON serialization
    for key in analysis:
        if isinstance(analysis[key], Counter):
            analysis[key] = dict(analysis[key])

    return analysis


def analyze_test_results_by_category(
    test_results: List[Dict[str, Any]],
    rules: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """Analyze test results grouped by rule categories.

    Args:
        test_results: List of test result dicts from RuleTester
        rules: Original list of (rule_id, rule_text) tuples

    Returns:
        Dict with analysis by complexity and predicate type
    """
    # Build rule_id -> rule_text mapping
    rule_map = {rid: rtext for rid, rtext in rules}

    # Initialize analysis structure
    analysis = {
        "by_complexity": {
            "simple": {"tested": 0, "valid": 0, "invalid": 0, "failed_conv": 0},
            "medium": {"tested": 0, "valid": 0, "invalid": 0, "failed_conv": 0},
            "complex": {"tested": 0, "valid": 0, "invalid": 0, "failed_conv": 0},
        },
        "by_conclusion_predicate": {},
    }

    for result in test_results:
        rule_id = result.get("rule_id", "")
        rule_text = result.get("rule", "") or rule_map.get(rule_id, "")

        if not rule_text:
            continue

        premises, conclusions = _parse_rule_for_analysis(rule_text)
        n_premises = len(premises)

        # Determine complexity
        if n_premises <= 2:
            complexity = "simple"
        elif n_premises <= 4:
            complexity = "medium"
        else:
            complexity = "complex"

        # Update complexity stats
        analysis["by_complexity"][complexity]["tested"] += 1
        if result.get("problem") is None:
            analysis["by_complexity"][complexity]["failed_conv"] += 1
        elif result.get("success"):
            analysis["by_complexity"][complexity]["valid"] += 1
        else:
            analysis["by_complexity"][complexity]["invalid"] += 1

        # Update predicate stats
        for pred, _ in conclusions:
            if pred not in analysis["by_conclusion_predicate"]:
                analysis["by_conclusion_predicate"][pred] = {
                    "tested": 0, "valid": 0, "invalid": 0, "failed_conv": 0
                }
            analysis["by_conclusion_predicate"][pred]["tested"] += 1
            if result.get("problem") is None:
                analysis["by_conclusion_predicate"][pred]["failed_conv"] += 1
            elif result.get("success"):
                analysis["by_conclusion_predicate"][pred]["valid"] += 1
            else:
                analysis["by_conclusion_predicate"][pred]["invalid"] += 1

    return analysis


# ============================================================================
# Report Generation
# ============================================================================

def generate_markdown_report(
    pipeline_results: Dict[str, Any],
    rule_analysis: Optional[Dict[str, Any]] = None,
    test_analysis: Optional[Dict[str, Any]] = None,
    output_path: Optional[Path] = None,
) -> str:
    """Generate a comprehensive Markdown report of the pipeline run.

    Args:
        pipeline_results: Results from run_pipeline()
        rule_analysis: Results from analyze_rules()
        test_analysis: Results from analyze_test_results_by_category()
        output_path: Optional path to write the report

    Returns:
        Markdown report string
    """
    lines = []

    # Header
    lines.append("# Discovery Pipeline Test Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Input file:** `{pipeline_results.get('input_path', 'N/A')}`")
    lines.append(f"- **Output directory:** `{pipeline_results.get('output_dir', 'N/A')}`")
    lines.append(f"- **Total time:** {pipeline_results.get('total_elapsed_seconds', 0):.2f}s")
    lines.append("")

    # Stage results
    for stage in pipeline_results.get("stages", []):
        stage_name = stage.get("stage", "unknown")
        elapsed = stage.get("elapsed_seconds", 0)
        stats = stage.get("stats", {})

        lines.append(f"## Stage: {stage_name.replace('_', ' ').title()}")
        lines.append("")
        lines.append(f"**Time:** {elapsed:.2f}s")
        lines.append("")

        if stage_name == "filter_and_prune":
            lines.append(f"- Total problems: {stats.get('total', 0)}")
            lines.append(f"- Kept (with aux): {stats.get('kept', 0)}")
            lines.append(f"- Rules extracted: {stats.get('rules', 0)}")
            lines.append(f"- Skipped rules: {stats.get('skipped_rules', 0)}")

        elif stage_name == "convert_rules":
            lines.append(f"- Total rules: {stats.get('total_rules', 0)}")
            lines.append(f"- Converted: {stats.get('converted', 0)}")
            lines.append(f"- Skipped (invalid predicates): {stats.get('skipped', 0)}")

        elif stage_name == "test_rules":
            lines.append(f"- Total tested: {stats.get('total', 0)}")
            lines.append(f"- Valid (provable): {stats.get('valid', 0)}")
            lines.append(f"- Invalid: {stats.get('invalid', 0)}")
            lines.append(f"- Failed conversion: {stats.get('failed_conversion', 0)}")

        elif stage_name == "evaluation":
            lines.append(f"- Total problems: {stats.get('total_problems', 0)}")
            lines.append(f"- Solved: {stats.get('solved', 0)}")
            lines.append(f"- Accuracy: {stats.get('accuracy', 0)*100:.1f}%")

        lines.append("")

    # Rule Analysis
    if rule_analysis:
        lines.append("## Rule Analysis")
        lines.append("")

        # Premise count distribution
        lines.append("### Premise Count Distribution")
        lines.append("")
        lines.append("| Premises | Count | Percentage |")
        lines.append("|----------|-------|------------|")
        total = rule_analysis.get("total", 1)
        for n_prem in sorted(rule_analysis.get("premise_count_dist", {}).keys()):
            count = rule_analysis["premise_count_dist"][n_prem]
            pct = count / total * 100 if total > 0 else 0
            lines.append(f"| {n_prem} | {count} | {pct:.1f}% |")
        lines.append("")

        # Conclusion predicates
        lines.append("### Conclusion Predicate Distribution")
        lines.append("")
        lines.append("| Predicate | Count | Percentage |")
        lines.append("|-----------|-------|------------|")
        conc_preds = rule_analysis.get("conclusion_predicates", {})
        for pred in sorted(conc_preds.keys(), key=lambda x: -conc_preds[x]):
            count = conc_preds[pred]
            pct = count / total * 100 if total > 0 else 0
            lines.append(f"| {pred} | {count} | {pct:.1f}% |")
        lines.append("")

        # Complexity distribution
        lines.append("### Complexity Distribution")
        lines.append("")
        lines.append("| Complexity | Count | Percentage |")
        lines.append("|------------|-------|------------|")
        for complexity in ["simple", "medium", "complex"]:
            count = rule_analysis.get("complexity_dist", {}).get(complexity, 0)
            pct = count / total * 100 if total > 0 else 0
            lines.append(f"| {complexity} (1-2/3-4/5+ premises) | {count} | {pct:.1f}% |")
        lines.append("")

        # Variable count distribution
        lines.append("### Variable Count Distribution")
        lines.append("")
        lines.append("| Variables | Count | Percentage |")
        lines.append("|-----------|-------|------------|")
        var_dist = rule_analysis.get("variable_count_dist", {})
        for n_vars in sorted(var_dist.keys()):
            count = var_dist[n_vars]
            pct = count / total * 100 if total > 0 else 0
            lines.append(f"| {n_vars} | {count} | {pct:.1f}% |")
        lines.append("")

    # Test Analysis by Category
    if test_analysis:
        lines.append("## Test Results by Category")
        lines.append("")

        # By complexity
        lines.append("### By Complexity")
        lines.append("")
        lines.append("| Complexity | Tested | Valid | Invalid | Failed Conv | Valid Rate |")
        lines.append("|------------|--------|-------|---------|-------------|------------|")
        for complexity in ["simple", "medium", "complex"]:
            stats = test_analysis.get("by_complexity", {}).get(complexity, {})
            tested = stats.get("tested", 0)
            valid = stats.get("valid", 0)
            invalid = stats.get("invalid", 0)
            failed = stats.get("failed_conv", 0)
            rate = valid / tested * 100 if tested > 0 else 0
            lines.append(f"| {complexity} | {tested} | {valid} | {invalid} | {failed} | {rate:.1f}% |")
        lines.append("")

        # By conclusion predicate
        lines.append("### By Conclusion Predicate")
        lines.append("")
        lines.append("| Predicate | Tested | Valid | Invalid | Failed Conv | Valid Rate |")
        lines.append("|-----------|--------|-------|---------|-------------|------------|")
        by_pred = test_analysis.get("by_conclusion_predicate", {})
        for pred in sorted(by_pred.keys(), key=lambda x: -by_pred[x].get("tested", 0)):
            stats = by_pred[pred]
            tested = stats.get("tested", 0)
            valid = stats.get("valid", 0)
            invalid = stats.get("invalid", 0)
            failed = stats.get("failed_conv", 0)
            rate = valid / tested * 100 if tested > 0 else 0
            lines.append(f"| {pred} | {tested} | {valid} | {invalid} | {failed} | {rate:.1f}% |")
        lines.append("")

    # Issues and Recommendations
    lines.append("## Issues Found")
    lines.append("")
    if pipeline_results.get("error"):
        lines.append(f"- **Pipeline Error:** {pipeline_results['error']}")
    if rule_analysis and rule_analysis.get("parse_errors", 0) > 0:
        lines.append(f"- **Parse Errors:** {rule_analysis['parse_errors']} rules failed to parse")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    lines.append("- Review failed conversion rules for unsupported predicate patterns")
    lines.append("- Consider increasing timeout for complex rules")
    lines.append("- Analyze invalid rules to identify common failure patterns")
    lines.append("")

    report = "\n".join(lines)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")

    return report


def run_stage1_filter_and_prune(
    input_path: Path,
    output_dir: Path,
    max_workers: int = 50,
    render_images: bool = False,
) -> Dict[str, Any]:
    """Stage 1: Filter, deduplicate, prune proofs, and extract rules.

    Args:
        input_path: Path to input JSONL file from Generation
        output_dir: Output directory for results
        max_workers: Number of parallel workers
        render_images: Whether to render proof graph images

    Returns:
        Dict with stage results including paths to output files
    """
    print("\n" + "=" * 60)
    print("Stage 1: Filter and Prune")
    print("=" * 60)

    from newclid.proof_scout.core.filter_and_prune_engine import FilterAndPruneEngine

    engine = FilterAndPruneEngine(
        max_workers=max_workers,
        render_by_rule=render_images,
        keep_pid_images=False,
        print_skipped_rules=True,
        print_dedup_removed=True,
        save_pid_inputs=True,
    )

    start_time = time.time()
    result = engine.run(input_path, output_dir)
    elapsed = time.time() - start_time

    print(f"\n[Stage 1] Completed in {elapsed:.2f}s")
    print(f"  Total problems: {result.get('total', 0)}")
    print(f"  Kept (with aux): {result.get('kept', 0)}")
    print(f"  Rules extracted: {result.get('rules', 0)}")
    print(f"  Skipped rules: {result.get('skipped_rules', 0)}")
    print(f"  Output JSON: {result.get('json', '')}")

    return {
        "stage": "filter_and_prune",
        "elapsed_seconds": elapsed,
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "pruned_json": result.get("json"),
        "rules_file": str(Path(result.get("json", "")).with_name(
            Path(result.get("json", "")).stem + "_rules.txt"
        )) if result.get("json") else None,
        "stats": result,
    }


def run_stage2_convert_rules(
    rules_file: Path,
    output_dir: Path,
    strict_validation: bool = True,
) -> Dict[str, Any]:
    """Stage 2: Convert rules to DDAR format with validation.

    Args:
        rules_file: Path to rules file from Stage 1
        output_dir: Output directory for converted rules
        strict_validation: Whether to skip rules with invalid predicates

    Returns:
        Dict with stage results including paths to output files
    """
    print("\n" + "=" * 60)
    print("Stage 2: Convert Rules")
    print("=" * 60)

    from newclid.proof_scout.extraction.rule_converter import RuleConverter

    converter = RuleConverter(strict_validation=strict_validation)

    output_path = output_dir / "discovered_rules.txt"

    start_time = time.time()
    result = converter.convert_file(rules_file, output_path, skip_invalid=True)
    elapsed = time.time() - start_time

    print(f"\n[Stage 2] Completed in {elapsed:.2f}s")
    print(f"  Total rules: {result.get('total_rules', 0)}")
    print(f"  Converted: {result.get('converted', 0)}")
    print(f"  Skipped (invalid predicates): {result.get('skipped', 0)}")
    print(f"  Output: {output_path}")

    return {
        "stage": "convert_rules",
        "elapsed_seconds": elapsed,
        "input_path": str(rules_file),
        "output_path": str(output_path),
        "stats": result,
    }


def run_stage3_test_rules(
    rules_file: Path,
    output_dir: Path,
    max_workers: int = 1,
    timeout: int = 60,
    max_rules: Optional[int] = None,
    batch_size: int = 50,
    batch_timeout: int = 300,
) -> Dict[str, Any]:
    """Stage 3: Test rules using DDAR solver with batch processing.

    Args:
        rules_file: Path to converted rules file from Stage 2
        output_dir: Output directory for test results
        max_workers: Number of parallel workers
        timeout: Timeout per rule in seconds
        max_rules: Maximum number of rules to test (None for all)
        batch_size: Number of rules per batch (default: 50)
        batch_timeout: Timeout per batch in seconds (default: 300)

    Returns:
        Dict with stage results including paths to output files
    """
    print("\n" + "=" * 60)
    print("Stage 3: Test Rules (with batch processing)")
    print("=" * 60)

    from newclid.proof_scout.extraction.rule_converter import RuleConverter
    from newclid.proof_scout.extraction.rule_tester import RuleTester

    # Parse rules from file
    converter = RuleConverter()
    rules = converter.parse_scout_rules(rules_file)

    if max_rules is not None and len(rules) > max_rules:
        print(f"  Limiting to first {max_rules} rules (total: {len(rules)})")
        rules = rules[:max_rules]

    total_rules = len(rules)
    print(f"  Total rules to test: {total_rules}")
    print(f"  Batch size: {batch_size}, Batch timeout: {batch_timeout}s")

    tester = RuleTester(timeout=timeout)

    # Process in batches
    all_results = []
    valid_count = 0
    invalid_count = 0
    failed_conversion_count = 0
    batch_num = 0

    start_time = time.time()

    for i in range(0, total_rules, batch_size):
        batch_num += 1
        batch_rules = rules[i:i + batch_size]
        batch_start = time.time()

        print(f"\n  [Batch {batch_num}] Processing rules {i+1}-{min(i+batch_size, total_rules)}...")

        try:
            batch_result = tester.batch_test(
                batch_rules,
                max_workers=max_workers,
                timeout=timeout,
            )

            for test_result in batch_result.get("results", []):
                all_results.append(test_result)
                if test_result.get("problem") is None:
                    failed_conversion_count += 1
                elif test_result.get("success"):
                    valid_count += 1
                else:
                    invalid_count += 1

            batch_elapsed = time.time() - batch_start
            print(f"  [Batch {batch_num}] Completed in {batch_elapsed:.2f}s - "
                  f"Valid: {batch_result.get('valid', 0)}, "
                  f"Invalid: {batch_result.get('invalid', 0)}, "
                  f"Failed: {batch_result.get('failed_conversion', 0)}")

            # Check batch timeout
            if batch_elapsed > batch_timeout:
                print(f"  [WARNING] Batch {batch_num} exceeded timeout ({batch_timeout}s)")

            # Save checkpoint after each batch
            checkpoint_path = output_dir / f"test_checkpoint_batch{batch_num}.json"
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({
                    "batch": batch_num,
                    "processed": len(all_results),
                    "valid": valid_count,
                    "invalid": invalid_count,
                    "failed_conversion": failed_conversion_count,
                }, f)

        except Exception as e:
            print(f"  [ERROR] Batch {batch_num} failed: {e}")
            # Continue with next batch

    elapsed = time.time() - start_time

    # Compile final results
    result = {
        "total": len(all_results),
        "valid": valid_count,
        "invalid": invalid_count,
        "failed_conversion": failed_conversion_count,
        "results": all_results,
    }

    # Write valid rules
    valid_rules_path = output_dir / "valid_rules.txt"
    valid_rules: List[Tuple[str, str]] = []
    for test_result in all_results:
        if test_result.get("success"):
            rule_id = test_result.get("rule_id", "")
            rule_text = test_result.get("rule", "")
            valid_rules.append((rule_id, rule_text))

    with open(valid_rules_path, "w", encoding="utf-8") as f:
        for rule_id, rule_text in valid_rules:
            f.write(f"{rule_id}\n{rule_text}\n")

    # Write test results
    test_results_path = output_dir / "test_results.json"
    with open(test_results_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[Stage 3] Completed in {elapsed:.2f}s")
    print(f"  Total tested: {result.get('total', 0)}")
    print(f"  Valid: {result.get('valid', 0)}")
    print(f"  Invalid: {result.get('invalid', 0)}")
    print(f"  Failed conversion: {result.get('failed_conversion', 0)}")
    print(f"  Valid rules: {valid_rules_path}")
    print(f"  Test results: {test_results_path}")

    return {
        "stage": "test_rules",
        "elapsed_seconds": elapsed,
        "input_path": str(rules_file),
        "valid_rules_path": str(valid_rules_path),
        "test_results_path": str(test_results_path),
        "stats": {
            "total": result.get("total", 0),
            "valid": result.get("valid", 0),
            "invalid": result.get("invalid", 0),
            "failed_conversion": result.get("failed_conversion", 0),
        },
        "all_rules": rules,
        "all_results": all_results,
    }


def run_stage4_evaluation(
    valid_rules_path: Path,
    benchmark_path: Path,
    output_dir: Path,
    base_rules_path: Optional[Path] = None,
    max_workers: int = 8,
    timeout: int = 600,
) -> Dict[str, Any]:
    """Stage 4 (Optional): Evaluate on benchmark problems.

    Args:
        valid_rules_path: Path to valid rules from Stage 3
        benchmark_path: Path to benchmark problems file
        output_dir: Output directory for evaluation results
        base_rules_path: Path to base rules file (default: use built-in rules)
        max_workers: Number of parallel workers
        timeout: Timeout per problem in seconds

    Returns:
        Dict with stage results
    """
    print("\n" + "=" * 60)
    print("Stage 4: Evaluation")
    print("=" * 60)

    from newclid.api import GeometricSolverBuilder
    from newclid.agent.ddarn import DDARN
    from newclid.formulations.rule import Rule
    from newclid.configs import default_rules_path

    # Load base rules
    if base_rules_path is None:
        base_rules_path = default_rules_path()

    base_rules = Rule.parse_txt_file(base_rules_path)
    print(f"  Base rules: {len(base_rules)}")

    # Load discovered rules
    discovered_rules = Rule.parse_txt_file(valid_rules_path)
    print(f"  Discovered rules: {len(discovered_rules)}")

    # Combine rules
    combined_rules = base_rules + discovered_rules
    print(f"  Combined rules: {len(combined_rules)}")

    # Load benchmark problems
    if not benchmark_path.exists():
        print(f"  [ERROR] Benchmark file not found: {benchmark_path}")
        return {
            "stage": "evaluation",
            "error": f"Benchmark file not found: {benchmark_path}",
        }

    problem_names = []
    with open(benchmark_path, "r") as f:
        lines = f.readlines()
        for i in range(0, len(lines), 2):
            problem_names.append(lines[i].strip())

    print(f"  Benchmark problems: {len(problem_names)}")

    # Run evaluation
    start_time = time.time()
    results = []
    solved_count = 0

    for i, problem_name in enumerate(problem_names):
        try:
            builder = GeometricSolverBuilder()
            builder.load_problem_from_file(benchmark_path, problem_name)
            builder.with_deductive_agent(DDARN())
            builder._rules = combined_rules

            solver = builder.build(max_attempts=100)
            is_solved = solver.run(timeout=timeout)

            results.append({
                "problem_name": problem_name,
                "solved": is_solved,
                "error": None,
            })

            if is_solved:
                solved_count += 1
                print(f"  [{i+1}/{len(problem_names)}] {problem_name}: SOLVED")
            else:
                print(f"  [{i+1}/{len(problem_names)}] {problem_name}: FAILED")

        except Exception as e:
            results.append({
                "problem_name": problem_name,
                "solved": False,
                "error": str(e),
            })
            print(f"  [{i+1}/{len(problem_names)}] {problem_name}: ERROR - {e}")

    elapsed = time.time() - start_time

    # Write evaluation results
    eval_results_path = output_dir / "evaluation_results.json"
    eval_output = {
        "benchmark": str(benchmark_path),
        "base_rules": len(base_rules),
        "discovered_rules": len(discovered_rules),
        "total_problems": len(problem_names),
        "solved": solved_count,
        "accuracy": solved_count / len(problem_names) if problem_names else 0,
        "results": results,
    }

    with open(eval_results_path, "w", encoding="utf-8") as f:
        json.dump(eval_output, f, ensure_ascii=False, indent=2)

    print(f"\n[Stage 4] Completed in {elapsed:.2f}s")
    print(f"  Solved: {solved_count}/{len(problem_names)} ({100*solved_count/len(problem_names):.1f}%)")
    print(f"  Results: {eval_results_path}")

    return {
        "stage": "evaluation",
        "elapsed_seconds": elapsed,
        "benchmark_path": str(benchmark_path),
        "eval_results_path": str(eval_results_path),
        "stats": {
            "total_problems": len(problem_names),
            "solved": solved_count,
            "accuracy": solved_count / len(problem_names) if problem_names else 0,
        },
    }


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    benchmark_path: Optional[Path] = None,
    max_workers: int = 50,
    test_timeout: int = 60,
    eval_timeout: int = 600,
    skip_stage3: bool = False,
    skip_stage4: bool = False,
    max_test_rules: Optional[int] = None,
    render_images: bool = False,
    batch_size: int = 50,
    batch_timeout: int = 300,
    generate_report: bool = True,
) -> Dict[str, Any]:
    """Run the complete discovery pipeline.

    Args:
        input_path: Path to input JSONL file from Generation
        output_dir: Output directory for all results
        benchmark_path: Path to benchmark file for evaluation (optional)
        max_workers: Number of parallel workers
        test_timeout: Timeout per rule in Stage 3
        eval_timeout: Timeout per problem in Stage 4
        skip_stage3: Skip rule testing stage
        skip_stage4: Skip evaluation stage
        max_test_rules: Maximum rules to test in Stage 3
        render_images: Whether to render proof graph images
        batch_size: Number of rules per batch in Stage 3
        batch_timeout: Timeout per batch in Stage 3
        generate_report: Whether to generate Markdown report

    Returns:
        Dict with complete pipeline results
    """
    print("\n" + "#" * 60)
    print("# Discovery Pipeline")
    print("#" * 60)
    print(f"\nInput: {input_path}")
    print(f"Output: {output_dir}")
    if benchmark_path:
        print(f"Benchmark: {benchmark_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_start = time.time()
    pipeline_results = {
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "stages": [],
    }

    # Stage 1: Filter and Prune
    stage1_result = run_stage1_filter_and_prune(
        input_path, output_dir, max_workers=max_workers, render_images=render_images
    )
    pipeline_results["stages"].append(stage1_result)

    rules_file = stage1_result.get("rules_file")
    if not rules_file or not Path(rules_file).exists():
        print("\n[ERROR] Stage 1 did not produce rules file. Stopping pipeline.")
        pipeline_results["error"] = "Stage 1 failed to produce rules"
        return pipeline_results

    # Stage 2: Convert Rules
    stage2_result = run_stage2_convert_rules(
        Path(rules_file), output_dir, strict_validation=True
    )
    pipeline_results["stages"].append(stage2_result)

    converted_rules_path = stage2_result.get("output_path")
    if not converted_rules_path or not Path(converted_rules_path).exists():
        print("\n[ERROR] Stage 2 did not produce converted rules. Stopping pipeline.")
        pipeline_results["error"] = "Stage 2 failed to produce converted rules"
        return pipeline_results

    # Stage 3: Test Rules (optional)
    valid_rules_path = None
    rule_analysis = None
    test_analysis = None
    stage3_result = None

    if not skip_stage3:
        stage3_result = run_stage3_test_rules(
            Path(converted_rules_path),
            output_dir,
            max_workers=max_workers,
            timeout=test_timeout,
            max_rules=max_test_rules,
            batch_size=batch_size,
            batch_timeout=batch_timeout,
        )
        pipeline_results["stages"].append(stage3_result)
        valid_rules_path = stage3_result.get("valid_rules_path")

        # Perform rule analysis
        all_rules = stage3_result.get("all_rules", [])
        all_results = stage3_result.get("all_results", [])

        if all_rules:
            print("\n[Analysis] Analyzing rules...")
            rule_analysis = analyze_rules(all_rules)

            # Save rule analysis
            analysis_path = output_dir / "rule_analysis.json"
            with open(analysis_path, "w", encoding="utf-8") as f:
                json.dump(rule_analysis, f, ensure_ascii=False, indent=2)
            print(f"  Rule analysis saved to: {analysis_path}")

        if all_rules and all_results:
            test_analysis = analyze_test_results_by_category(all_results, all_rules)

            # Save test analysis
            test_analysis_path = output_dir / "test_analysis.json"
            with open(test_analysis_path, "w", encoding="utf-8") as f:
                json.dump(test_analysis, f, ensure_ascii=False, indent=2)
            print(f"  Test analysis saved to: {test_analysis_path}")
    else:
        print("\n[INFO] Skipping Stage 3 (rule testing)")
        valid_rules_path = converted_rules_path

    # Stage 4: Evaluation (optional)
    if not skip_stage4 and benchmark_path and valid_rules_path:
        stage4_result = run_stage4_evaluation(
            Path(valid_rules_path),
            benchmark_path,
            output_dir,
            max_workers=max_workers,
            timeout=eval_timeout,
        )
        pipeline_results["stages"].append(stage4_result)
    elif skip_stage4:
        print("\n[INFO] Skipping Stage 4 (evaluation)")
    elif not benchmark_path:
        print("\n[INFO] No benchmark specified, skipping Stage 4")

    # Write pipeline summary
    pipeline_elapsed = time.time() - pipeline_start
    pipeline_results["total_elapsed_seconds"] = pipeline_elapsed

    summary_path = output_dir / "pipeline_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(pipeline_results, f, ensure_ascii=False, indent=2)

    # Generate Markdown report
    if generate_report:
        print("\n[Report] Generating Markdown report...")
        report_path = output_dir / "report.md"
        report = generate_markdown_report(
            pipeline_results,
            rule_analysis=rule_analysis,
            test_analysis=test_analysis,
            output_path=report_path,
        )
        print(f"  Report saved to: {report_path}")

    print("\n" + "#" * 60)
    print("# Pipeline Complete")
    print("#" * 60)
    print(f"\nTotal time: {pipeline_elapsed:.2f}s")
    print(f"Summary: {summary_path}")

    return pipeline_results


def main():
    parser = argparse.ArgumentParser(
        description="Discovery Pipeline: Generation -> Proof Scout -> Evaluation"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="Path to input JSONL file from Generation"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        required=True,
        help="Output directory for all results"
    )
    parser.add_argument(
        "--benchmark", "-b",
        type=str,
        default=None,
        help="Path to benchmark file for evaluation (optional)"
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=50,
        help="Number of parallel workers (default: 50)"
    )
    parser.add_argument(
        "--test_timeout",
        type=int,
        default=60,
        help="Timeout per rule in Stage 3 (default: 60s)"
    )
    parser.add_argument(
        "--eval_timeout",
        type=int,
        default=600,
        help="Timeout per problem in Stage 4 (default: 600s)"
    )
    parser.add_argument(
        "--skip_stage3",
        action="store_true",
        help="Skip rule testing stage"
    )
    parser.add_argument(
        "--skip_stage4",
        action="store_true",
        help="Skip evaluation stage"
    )
    parser.add_argument(
        "--max_test_rules",
        type=int,
        default=None,
        help="Maximum rules to test in Stage 3 (default: all)"
    )
    parser.add_argument(
        "--render_images",
        action="store_true",
        help="Render proof graph images (slower)"
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=50,
        help="Number of rules per batch in Stage 3 (default: 50)"
    )
    parser.add_argument(
        "--batch_timeout",
        type=int,
        default=300,
        help="Timeout per batch in Stage 3 (default: 300s)"
    )
    parser.add_argument(
        "--no_report",
        action="store_true",
        help="Skip Markdown report generation"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    benchmark_path = Path(args.benchmark) if args.benchmark else None

    run_pipeline(
        input_path=input_path,
        output_dir=output_dir,
        benchmark_path=benchmark_path,
        max_workers=args.max_workers,
        test_timeout=args.test_timeout,
        eval_timeout=args.eval_timeout,
        skip_stage3=args.skip_stage3,
        skip_stage4=args.skip_stage4,
        max_test_rules=args.max_test_rules,
        render_images=args.render_images,
        batch_size=args.batch_size,
        batch_timeout=args.batch_timeout,
        generate_report=not args.no_report,
    )


if __name__ == "__main__":
    main()
