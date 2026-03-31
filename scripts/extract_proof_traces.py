#!/usr/bin/env python3
"""
Extract proof traces for successful problems from step6_rules_stats.json.

This script reads the rule statistics and input filter data to extract
complete proof traces (auxiliary constructions + proof steps) for problems
that were successfully solved.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_jsonl(path: Path) -> List[dict]:
    """Load JSONL file."""
    data = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def build_pid_to_name_mapping(
    synthetic_data_path: Path,
    problems_jsonl_path: Path
) -> Dict[str, str]:
    """
    Build mapping from problem ID (pid) to problem name.

    Strategy: In synthetic data, samples from the same problem share the same seed.
    Problems are processed in order, so the i-th unique seed corresponds to the i-th problem.
    Each sample has a sequential pid (p000000, p000001, ...).
    """
    # Load original problems (ordered)
    problems = []
    with open(problems_jsonl_path, encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            name = data["problem_name"]
            # Use short name (filename only)
            if "/" in name:
                name = name.split("/")[-1]
            problems.append(name)

    # Load synthetic data and find seed → problem index mapping
    seed_to_problem_idx = {}
    seen_seeds = []
    with open(synthetic_data_path, encoding='utf-8') as f:
        for line in f:
            sample = json.loads(line)
            seed = sample["seed"]
            if seed not in seed_to_problem_idx:
                seed_to_problem_idx[seed] = len(seen_seeds)
                seen_seeds.append(seed)

    # Build pid → seed mapping, then pid → problem_name
    pid_to_name = {}
    with open(synthetic_data_path, encoding='utf-8') as f:
        for i, line in enumerate(f):
            sample = json.loads(line)
            pid = sample["pid"]
            seed = sample["seed"]
            problem_idx = seed_to_problem_idx[seed]
            if problem_idx < len(problems):
                pid_to_name[pid] = problems[problem_idx]

    return pid_to_name


def extract_proof_traces(
    stats_data: dict,
    pid_to_name: Dict[str, str],
    successful_problems: Set[str]
) -> List[dict]:
    """
    Extract proof traces for successful problems.

    Returns list of proof dictionaries containing:
    - problem_name
    - rule_id
    - seed
    - rule
    - aux_constructions
    - proof_steps
    """
    proofs = []

    for entry in stats_data["entries"]:
        pid = entry["pid"]
        problem_name = pid_to_name.get(pid)

        if problem_name and problem_name in successful_problems:
            llm_output = entry.get("llm_output_renamed", "")

            # Extract <aux> tag content
            aux_match = re.search(r'<aux>(.*?)</aux>', llm_output, re.DOTALL)
            aux_constructions = aux_match.group(1).strip() if aux_match else ""

            # Extract <proof> tag content
            proof_match = re.search(r'<proof>(.*?)</proof>', llm_output, re.DOTALL)
            proof_steps_raw = proof_match.group(1).strip() if proof_match else ""

            # Split proof steps by semicolon
            proof_steps = [step.strip() for step in proof_steps_raw.split(';') if step.strip()]

            proofs.append({
                "problem_name": problem_name,
                "rule_id": entry["rid"],
                "seed": entry["seed"],
                "rule": entry["rule"],
                "aux_constructions": aux_constructions,
                "proof_steps": proof_steps
            })

    return proofs


def generate_markdown_report(proofs: List[dict], output_path: Path):
    """Generate Markdown report with proof traces."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Successful Problem Proofs\n\n")
        f.write(f"Total successful problems with extracted proofs: {len(proofs)}\n\n")
        f.write("---\n\n")

        for i, proof in enumerate(proofs, 1):
            f.write(f"## {i}. {proof['problem_name']}\n\n")
            f.write(f"**Rule ID**: `{proof['rule_id']}`  \n")
            f.write(f"**Seed**: `{proof['seed']}`  \n\n")
            f.write(f"**Extracted Rule**:\n")
            f.write(f"```\n{proof['rule']}\n```\n\n")

            if proof['aux_constructions']:
                f.write(f"**Auxiliary Constructions**:\n")
                f.write(f"```\n{proof['aux_constructions']}\n```\n\n")
            else:
                f.write(f"**Auxiliary Constructions**: None\n\n")

            f.write(f"**Proof Steps** ({len(proof['proof_steps'])} steps):\n")
            if proof['proof_steps']:
                for j, step in enumerate(proof['proof_steps'], 1):
                    f.write(f"{j}. `{step}`\n")
            else:
                f.write("No proof steps found.\n")

            f.write("\n---\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="Extract proof traces for successful problems"
    )
    parser.add_argument(
        "--stats",
        type=Path,
        required=True,
        help="Path to step6_rules_stats.json"
    )
    parser.add_argument(
        "--synthetic-data",
        type=Path,
        required=True,
        help="Path to synthetic_data.jsonl (for pid-to-problem mapping)"
    )
    parser.add_argument(
        "--problems",
        type=Path,
        required=True,
        help="Path to success_proofs_aux_constructions.jsonl"
    )
    parser.add_argument(
        "--successful-list",
        type=Path,
        required=True,
        help="Path to file containing list of successful problem names (one per line)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for Markdown report"
    )

    args = parser.parse_args()

    # Load data
    print(f"Loading stats from {args.stats}...")
    stats_data = load_json(args.stats)

    print(f"Loading successful problems list from {args.successful_list}...")
    with open(args.successful_list, encoding='utf-8') as f:
        successful_problems = set(line.strip() for line in f if line.strip())

    print(f"Found {len(successful_problems)} successful problems")

    # Build pid → problem_name mapping via synthetic data
    print("Building pid to problem name mapping...")
    pid_to_name = build_pid_to_name_mapping(args.synthetic_data, args.problems)

    # Extract proof traces
    print("Extracting proof traces...")
    proofs = extract_proof_traces(stats_data, pid_to_name, successful_problems)

    print(f"Extracted {len(proofs)} proof traces")

    # Generate report
    print(f"Generating Markdown report to {args.output}...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    generate_markdown_report(proofs, args.output)

    print("Done!")


if __name__ == "__main__":
    main()
