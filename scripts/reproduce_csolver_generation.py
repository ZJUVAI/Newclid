#!/usr/bin/env python3
"""
Reproduce CSolver Generation with Missing IDs

This script takes a problem's FL statement (with auxiliary constructions),
runs CSolver to generate proof traces, and reproduces the missing ID error
from the data generation phase.

Usage:
    # Use a JGEX verified problem (with aux constructions)
    python scripts/reproduce_csolver_generation.py --jgex-problem 0

    # Use a custom FL statement (must include aux constructions)
    python scripts/reproduce_csolver_generation.py --fl-statement "a b c = triangle a b c; h = midpoint h d f ? cong d g f g"
"""

import json
import sys
from pathlib import Path
from typing import Optional
import argparse
import re

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import the actual generation function
sys.path.insert(0, str(Path(__file__).parent))
from generate_from_jgex_problems_no_ray import process_jgex_problem

JGEX_VERIFIED = Path("outputs/experiments/20260314_01_jgex231_aux_verified/success_proofs_aux_constructions.jsonl")


def load_jgex_problem(index: int) -> dict:
    """Load a JGEX verified problem by index."""
    with open(JGEX_VERIFIED) as f:
        for i, line in enumerate(f):
            if i == index:
                return json.loads(line)
    raise IndexError(f"Problem index {index} out of range")


def list_jgex_problems():
    """List all available JGEX verified problems."""
    with open(JGEX_VERIFIED) as f:
        for i, line in enumerate(f):
            rec = json.loads(line)
            name = rec.get("problem_name", "")
            aux = rec.get("auxiliary_constructions_renamed", "")
            fl = rec.get("full_problem_with_aux_renamed", "")
            print(f"  [{i:2d}] {name}")
            print(f"       aux: {aux}")
            print(f"       fl:  {fl[:100]}...")
            print()


def reproduce_csolver_generation(fl_statement: str, seed: Optional[int] = None, verbose: bool = True):
    """Run CSolver on FL statement and analyze the generated proof."""
    if seed is None:
        seed = abs(hash(fl_statement)) % (2**31)

    if verbose:
        print(f"\n{'='*80}")
        print("CSolver Generation")
        print(f"{'='*80}")
        print(f"FL Statement: {fl_statement}")
        print(f"Seed: {seed}")
        print()

    # Use the actual generation function
    args = ("test_problem", fl_statement, seed, 500, None)
    try:
        generated_data, summary = process_jgex_problem(args)
    except Exception as e:
        if verbose:
            print(f"✗ Generation failed: {e}")
            import traceback
            traceback.print_exc()
        return {"success": False, "error": str(e)}

    if not generated_data:
        if verbose:
            print("✗ No proof traces generated")
        return {"success": False, "error": "No proof traces generated"}

    if verbose:
        print(f"✓ Generated {len(generated_data)} proof traces")
        print()

    # Analyze generated proofs for missing IDs
    if verbose:
        print(f"{'='*80}")
        print("Proof Analysis")
        print(f"{'='*80}")

    def extract_tag_content(text: str, tag: str) -> str:
        pattern = f"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def extract_ids(text: str) -> set:
        return set(re.findall(r'\[(\d+)\]', text))

    results = []
    for i, item in enumerate(generated_data):
        llm_input = item.get("llm_input_renamed", "")
        llm_output = item.get("llm_output_renamed", "")
        aux_points = item.get("aux_points", [])

        problem_section = extract_tag_content(llm_input, "problem") or llm_input
        aux_section = extract_tag_content(llm_output, "aux")
        numerical_section = extract_tag_content(llm_output, "numerical_check")
        trivial_section = extract_tag_content(llm_output, "trivial")
        proof_section = extract_tag_content(llm_output, "proof")

        defined_ids = extract_ids(problem_section) | extract_ids(aux_section) | extract_ids(numerical_section)
        trivial_ids = extract_ids(trivial_section)

        # Also count IDs defined by proof conclusions
        proof_conclusion_ids = set()
        proof_premise_ids = set()
        proof_steps = [s.strip() for s in proof_section.split(';') if s.strip()]
        for step in proof_steps:
            ids_in_step = re.findall(r'\[(\d+)\]', step)
            if ids_in_step:
                proof_conclusion_ids.add(ids_in_step[0])
                for pid in ids_in_step[1:]:
                    if pid.isdigit():
                        proof_premise_ids.add(pid)

        all_defined = defined_ids | proof_conclusion_ids
        missing_ids = proof_premise_ids - all_defined
        missing_ids_with_trivial = proof_premise_ids - (all_defined | trivial_ids)

        has_aux = bool(aux_points)
        results.append({
            "index": i,
            "aux_points": aux_points,
            "has_aux": has_aux,
            "defined_ids_count": len(defined_ids),
            "trivial_ids_count": len(trivial_ids),
            "proof_steps": len(proof_steps),
            "missing_ids_count": len(missing_ids),
            "missing_ids": sorted(missing_ids),
            "missing_from_trivial": sorted(missing_ids - missing_ids_with_trivial),
            "has_missing_ids": len(missing_ids) > 0,
        })

        if verbose and has_aux:
            status = "✗" if missing_ids else "✓"
            trivial_note = f" (all from <trivial>)" if missing_ids and not missing_ids_with_trivial else ""
            print(f"  {status} Proof {i}: aux={aux_points}, "
                  f"defined={len(defined_ids)}, trivial={len(trivial_ids)}, steps={len(proof_steps)}, "
                  f"missing={len(missing_ids)}{trivial_note}")
            if missing_ids:
                print(f"      Missing IDs: {sorted(missing_ids)[:10]}{'...' if len(missing_ids) > 10 else ''}")
                if trivial_section:
                    print(f"      <trivial> content: {trivial_section[:100]}")

    # Summary
    aux_results = [r for r in results if r["has_aux"]]
    non_aux_results = [r for r in results if not r["has_aux"]]
    aux_with_missing = [r for r in aux_results if r["has_missing_ids"]]
    trivial_only_missing = [r for r in aux_with_missing if not (set(r["missing_ids"]) - set(r["missing_from_trivial"]))]

    if verbose:
        print(f"\n{'='*80}")
        print("Summary")
        print(f"{'='*80}")
        print(f"Total proof traces: {len(generated_data)}")
        print(f"  With aux construction: {len(aux_results)}")
        print(f"  Without aux construction: {len(non_aux_results)}")
        if aux_results:
            print(f"Aux proofs with missing IDs: {len(aux_with_missing)}/{len(aux_results)} "
                  f"({100*len(aux_with_missing)/len(aux_results):.1f}%)")
            if trivial_only_missing:
                print(f"  Of which ALL missing IDs are from <trivial>: {len(trivial_only_missing)}/{len(aux_with_missing)}")

    return {
        "success": True,
        "total_proofs": len(generated_data),
        "aux_proofs": len(aux_results),
        "non_aux_proofs": len(non_aux_results),
        "aux_with_missing_ids": len(aux_with_missing),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce CSolver generation with missing IDs"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--jgex-problem", type=int, metavar="INDEX",
                       help="Load JGEX verified problem by index (0-24)")
    group.add_argument("--fl-statement", type=str,
                       help="Direct FL statement input (must include aux constructions)")
    group.add_argument("--list", action="store_true",
                       help="List all available JGEX verified problems")
    parser.add_argument("--seed", type=int, help="Random seed for CSolver")
    args = parser.parse_args()

    if args.list:
        print("Available JGEX verified problems:")
        print()
        list_jgex_problems()
        return

    # Determine FL statement source
    fl_statement = None
    if args.jgex_problem is not None:
        try:
            rec = load_jgex_problem(args.jgex_problem)
            fl_statement = rec.get("full_problem_with_aux_renamed", "")
            aux = rec.get("auxiliary_constructions_renamed", "")
            name = rec.get("problem_name", "")
            print(f"Loaded JGEX problem [{args.jgex_problem}]: {name}")
            print(f"  Auxiliary constructions: {aux}")
        except IndexError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    elif args.fl_statement:
        fl_statement = args.fl_statement
        print(f"Using provided FL statement")

    result = reproduce_csolver_generation(fl_statement, seed=args.seed, verbose=True)

    if not result["success"]:
        print(f"\n✗ FAILED: {result['error']}")
        sys.exit(1)
    else:
        print(f"\n✓ Done: {result['total_proofs']} proofs generated, "
              f"{result['aux_with_missing_ids']}/{result['aux_proofs']} aux proofs have missing IDs")


if __name__ == "__main__":
    main()
