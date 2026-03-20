#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze Filtering - Generate comprehensive filtering report from experiment results.

Usage:
    python scripts/analyze_filtering.py \\
        --experiment outputs/experiments/20260307_discovery_10k_aux_only

This script reads intermediate files from a discovery experiment and generates
a detailed Markdown report showing:
- Filtering funnel with counts at each step
- Detailed breakdown of filtered data
- Deduplication mappings
- R0 conversion failures
"""
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List
from collections import Counter


def load_json_safe(path: Path) -> Dict[str, Any]:
    """Load JSON file safely, return empty dict if not found."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def generate_ascii_funnel(steps: List[Dict[str, Any]]) -> str:
    """Generate ASCII art funnel diagram."""
    lines = []
    lines.append("```")
    lines.append("Pipeline Filtering Funnel")
    lines.append("=" * 60)

    for step in steps:
        name = step["name"]
        input_count = step["input"]
        output_count = step["output"]
        filtered = input_count - output_count

        # Calculate bar width (max 40 chars)
        max_count = max(s["input"] for s in steps)
        bar_width = int((input_count / max_count) * 40) if max_count > 0 else 0
        bar = "█" * bar_width

        lines.append(f"\n{name}")
        lines.append(f"  Input:    {input_count:6d} {bar}")
        lines.append(f"  Output:   {output_count:6d}")
        lines.append(f"  Filtered: {filtered:6d} ({filtered/input_count*100:.1f}%)" if input_count > 0 else "  Filtered: 0")

    lines.append("=" * 60)
    lines.append("```")
    return "\n".join(lines)


def analyze_step1a(data: Dict[str, Any]) -> str:
    """Analyze Step 1a: Aux filter."""
    lines = []
    lines.append("## Step 1a: Aux Filter")
    lines.append("")
    lines.append(f"- Total input: {data.get('total', 0)}")
    lines.append(f"- Kept (with aux points): {data.get('kept', 0)}")
    lines.append(f"- Dropped (no aux points): {data.get('dropped', 0)}")
    lines.append("")

    dropped_records = data.get("dropped_records", [])
    if dropped_records:
        lines.append(f"### Dropped Records ({len(dropped_records)} total)")
        lines.append("")
        lines.append("Sample of dropped problems (first 10):")
        lines.append("")
        for i, rec in enumerate(dropped_records[:10]):
            pid = rec.get("problem_id", "unknown")
            fl_problem = rec.get("fl_problem", "")[:100]
            lines.append(f"{i+1}. PID: {pid}")
            lines.append(f"   Problem: {fl_problem}...")
            lines.append("")

    return "\n".join(lines)


def analyze_step1c(data: Dict[str, Any]) -> str:
    """Analyze Step 1c: Graph prune."""
    lines = []
    lines.append("## Step 1c: Graph Prune")
    lines.append("")
    lines.append(f"- Input: {data.get('input', 0)}")
    lines.append(f"- Pruned successfully: {data.get('pruned', 0)}")
    lines.append(f"- Failed: {data.get('failed', 0)}")
    lines.append("")

    failed_records = data.get("failed_records", [])
    if failed_records:
        lines.append(f"### Failed Records ({len(failed_records)} total)")
        lines.append("")
        lines.append("Sample of failed problems (first 10):")
        lines.append("")
        for i, rec in enumerate(failed_records[:10]):
            pid = rec.get("problem_id", "unknown")
            reason = rec.get("reason", "Unknown")
            fl_problem = rec.get("fl_problem", "")[:100]
            lines.append(f"{i+1}. PID: {pid}")
            lines.append(f"   Reason: {reason}")
            lines.append(f"   Problem: {fl_problem}...")
            lines.append("")

    return "\n".join(lines)


def analyze_step1d(data: Dict[str, Any]) -> str:
    """Analyze Step 1d: Proposition extraction."""
    lines = []
    lines.append("## Step 1d: Proposition Extraction")
    lines.append("")
    lines.append(f"- Input: {data.get('input', 0)}")
    lines.append(f"- Has proposition: {data.get('has_proposition', 0)}")
    lines.append(f"- Has rule: {data.get('has_rule', 0)}")
    lines.append(f"- Failed (no fact nodes): {data.get('fail_no_fact_nodes', 0)}")
    lines.append(f"- Failed (multi conclusion): {data.get('fail_multi_conclusion', 0)}")
    lines.append("")

    fail_no_fact = data.get("fail_no_fact_records", [])
    if fail_no_fact:
        lines.append(f"### Failed: No Fact Nodes ({len(fail_no_fact)} total)")
        lines.append("")
        lines.append("Sample (first 10):")
        lines.append("")
        for i, rec in enumerate(fail_no_fact[:10]):
            pid = rec.get("problem_id", "unknown")
            n_nodes = rec.get("n_nodes", 0)
            thm_labels = rec.get("theorem_labels", [])
            lines.append(f"{i+1}. PID: {pid}, Nodes: {n_nodes}, Theorems: {thm_labels}")
        lines.append("")

    fail_multi_concl = data.get("fail_multi_concl_records", [])
    if fail_multi_concl:
        lines.append(f"### Failed: Multiple Conclusions ({len(fail_multi_concl)} total)")
        lines.append("")
        lines.append("Sample (first 10):")
        lines.append("")
        for i, rec in enumerate(fail_multi_concl[:10]):
            pid = rec.get("problem_id", "unknown")
            n_concl = rec.get("n_conclusions", 0)
            concl_labels = rec.get("conclusion_labels", [])
            lines.append(f"{i+1}. PID: {pid}, Conclusions: {n_concl}, Labels: {concl_labels}")
        lines.append("")

    return "\n".join(lines)


def analyze_step1e(data: Dict[str, Any]) -> str:
    """Analyze Step 1e: Rule deduplication."""
    lines = []
    lines.append("## Step 1e: Rule Deduplication")
    lines.append("")
    lines.append(f"- Input rules (raw): {data.get('input_rules_raw', 0)}")
    lines.append(f"- Output rules (deduped): {data.get('output_rules_deduped', 0)}")
    lines.append(f"- Skipped rules (missing points): {data.get('skipped_rules', 0)}")
    lines.append("")

    # Coarse dedup groups
    coarse_groups = data.get("coarse_dedup_groups", [])
    if coarse_groups:
        total_coarse_dup = sum(g["count"] - 1 for g in coarse_groups)
        lines.append(f"### Coarse Deduplication (Signature-based)")
        lines.append("")
        lines.append(f"- Total duplicate groups: {len(coarse_groups)}")
        lines.append(f"- Total duplicates removed: {total_coarse_dup}")
        lines.append("")
        lines.append("Top 5 duplicate groups:")
        lines.append("")
        sorted_groups = sorted(coarse_groups, key=lambda g: g["count"], reverse=True)
        for i, group in enumerate(sorted_groups[:5]):
            sig = group["signature"]
            count = group["count"]
            lines.append(f"{i+1}. Signature: `{sig}` (count: {count})")
        lines.append("")

    # Fine dedup groups
    fine_groups = data.get("fine_dedup_groups", [])
    if fine_groups:
        total_fine_dup = sum(g["count"] - 1 for g in fine_groups)
        lines.append(f"### Fine Deduplication (Normalization-based)")
        lines.append("")
        lines.append(f"- Total duplicate groups: {len(fine_groups)}")
        lines.append(f"- Total duplicates removed: {total_fine_dup}")
        lines.append("")
        lines.append("Top 5 duplicate groups:")
        lines.append("")
        sorted_groups = sorted(fine_groups, key=lambda g: g["count"], reverse=True)
        for i, group in enumerate(sorted_groups[:5]):
            norm = group["normalized_form"]
            count = group["count"]
            lines.append(f"{i+1}. Normalized form: `{norm}` (count: {count})")
            # Show sample rules
            for j, rule_info in enumerate(group["rules"][:3]):
                pid = rule_info["pid"]
                rule = rule_info["rule"]
                lines.append(f"   - PID {pid}: `{rule}`")
        lines.append("")

    # Skipped entries
    skipped_entries = data.get("skipped_entries", [])
    if skipped_entries:
        lines.append(f"### Skipped Rules (Missing Points)")
        lines.append("")
        lines.append(f"Total: {len(skipped_entries)}")
        lines.append("")
        # Count by missing points
        missing_counter = Counter()
        for entry in skipped_entries:
            missing = tuple(sorted(entry.get("missing_points", [])))
            missing_counter[missing] += 1
        lines.append("Missing points distribution:")
        lines.append("")
        for missing, count in missing_counter.most_common(10):
            lines.append(f"- {missing}: {count} rules")
        lines.append("")

    return "\n".join(lines)


def analyze_r0_failures(data: Dict[str, Any]) -> str:
    """Analyze R0 conversion failures."""
    lines = []
    lines.append("## R0: Rule-to-Problem Conversion")
    lines.append("")

    if not data:
        lines.append("No R0 conversion failures file found.")
        return "\n".join(lines)

    total = data.get("total_failures", 0)
    lines.append(f"- Total conversion failures: {total}")
    lines.append("")

    categories = data.get("categories", {})
    if categories:
        lines.append("### Failure Categories")
        lines.append("")
        for reason, info in sorted(categories.items(), key=lambda x: x[1]["count"], reverse=True):
            count = info["count"]
            lines.append(f"#### {reason} ({count} rules)")
            lines.append("")
            # Show sample rules
            for i, rule_info in enumerate(info["rules"][:5]):
                rule_id = rule_info["rule_id"]
                rule_text = rule_info["rule_text"]
                lines.append(f"{i+1}. {rule_id}: `{rule_text}`")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate comprehensive filtering report from experiment results"
    )
    parser.add_argument(
        "--experiment",
        type=Path,
        required=True,
        help="Path to experiment directory (e.g., outputs/experiments/20260307_discovery_10k_aux_only)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for report (default: <experiment>/filtering_report.md)",
    )

    args = parser.parse_args()

    if not args.experiment.exists():
        print(f"Error: Experiment directory not found: {args.experiment}")
        return

    # Set default output path
    if args.output is None:
        args.output = args.experiment / "filtering_report.md"

    # Load intermediate files
    intermediates_dir = args.experiment / "intermediates"
    if not intermediates_dir.exists():
        print(f"Error: Intermediates directory not found: {intermediates_dir}")
        return

    step1a_data = load_json_safe(intermediates_dir / "step1a_aux_filter.json")
    step1c_data = load_json_safe(intermediates_dir / "step1c_prune.json")
    step1d_data = load_json_safe(intermediates_dir / "step1d_propositions.json")
    step1e_data = load_json_safe(intermediates_dir / "step1e_rules_stats.json")

    # Load R0 failures if available
    reduction_dir = args.experiment / "reduction"
    r0_failures_data = load_json_safe(reduction_dir / "r0_conversion_failures.json")

    # Build funnel steps
    funnel_steps = [
        {
            "name": "Step 1a: Aux Filter",
            "input": step1a_data.get("total", 0),
            "output": step1a_data.get("kept", 0),
        },
        {
            "name": "Step 1c: Graph Prune",
            "input": step1c_data.get("input", 0),
            "output": step1c_data.get("pruned", 0),
        },
        {
            "name": "Step 1d: Proposition Extraction",
            "input": step1d_data.get("input", 0),
            "output": step1d_data.get("has_rule", 0),
        },
        {
            "name": "Step 1e: Rule Deduplication",
            "input": step1e_data.get("input_rules_raw", 0),
            "output": step1e_data.get("output_rules_deduped", 0),
        },
    ]

    # Generate report
    report_lines = []
    report_lines.append("# Pipeline Filtering Report")
    report_lines.append("")
    report_lines.append(f"Experiment: `{args.experiment.name}`")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # Funnel diagram
    report_lines.append("# Overview")
    report_lines.append("")
    report_lines.append(generate_ascii_funnel(funnel_steps))
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # Detailed analysis
    report_lines.append("# Detailed Analysis")
    report_lines.append("")
    report_lines.append(analyze_step1a(step1a_data))
    report_lines.append("---")
    report_lines.append("")
    report_lines.append(analyze_step1c(step1c_data))
    report_lines.append("---")
    report_lines.append("")
    report_lines.append(analyze_step1d(step1d_data))
    report_lines.append("---")
    report_lines.append("")
    report_lines.append(analyze_step1e(step1e_data))
    report_lines.append("---")
    report_lines.append("")
    report_lines.append(analyze_r0_failures(r0_failures_data))

    # Write report
    report_content = "\n".join(report_lines)
    with open(args.output, 'w') as f:
        f.write(report_content)

    print(f"Filtering report generated: {args.output}")
    print(f"Total lines: {len(report_lines)}")


if __name__ == "__main__":
    main()
