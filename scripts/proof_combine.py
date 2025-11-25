"""
Combine proof_info and configuration_info into proof traces.

Inputs:
  - proof_info: JSON file, list of [id_str, info_dict]
  - configuration_info: JSONL file, each line a dict with `config_id`, `configuration`, `unsolved_goals`, ...

Output:
  - JSONL file, each line:
    {
      "id": str,
      "problem": str,
      "points_coordinates": {point: [x, y], ...},
      "aux_construction": str,
      "llm_renamed_proof": str,
      "raw_rule": str
    }
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Dict, Any


POINT_COORD_RE = re.compile(
    r'\b([a-zA-Z]\w*)@([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)_([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
)

PREM_WITH_IDX_RE = re.compile(
    r'([a-zA-Z]\w*(?:\s+[a-zA-Z0-9_]+){1,10})\s*\[\d+\]'
)


def load_configuration_map(path: str) -> Dict[int, Dict[str, Any]]:
    """Load configuration_info.jsonl as a mapping: config_id -> record."""
    config_map: Dict[int, Dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            cid = obj.get("config_id")
            if cid is None:
                continue
            # later lines override earlier ones if duplicated
            config_map[int(cid)] = obj
    return config_map


def parse_points_coordinates(configuration_str: str) -> Dict[str, list[float]]:
    """Extract point coordinates from configuration string."""
    coords: Dict[str, list[float]] = {}
    for m in POINT_COORD_RE.finditer(configuration_str):
        name, xs, ys = m.group(1), m.group(2), m.group(3)
        try:
            x = float(xs)
            y = float(ys)
        except ValueError:
            continue
        coords[name] = [x, y]
    return coords


def split_constructions(left_part: str) -> list[str]:
    """Split the left part (before '?') into construction segments."""
    # e.g. "a b c d = iso_trapezoid ...; e = ...; f = ..."
    segs = [seg.strip() for seg in left_part.split(";")]
    return [s for s in segs if s]


def extract_aux_construction(problem: str, augmented_problem: str) -> str:
    """Get the difference (aux constructions) between augmented_problem and problem.

    Assumption: augmented_problem = problem + newly appended constructions.
    """
    if problem == augmented_problem:
        return ""

    try:
        base_left = problem.split(" ? ", 1)[0]
        aug_left = augmented_problem.split(" ? ", 1)[0]
    except Exception:
        # unexpected format, fallback: no aux
        return ""

    base_list = split_constructions(base_left)
    aug_list = split_constructions(aug_left)

    if len(aug_list) <= len(base_list):
        return ""

    added = aug_list[len(base_list):]
    return "; ".join(added)


def extract_llm_renamed_proof(info: Dict[str, Any]) -> str:
    """Concatenate llm_renamed_input and llm_renamed_output."""
    inp = (info.get("llm_renamed_input") or "").strip()
    out = (info.get("llm_renamed_output") or "").strip()
    if not inp and not out:
        return ""
    if not out:
        return inp
    if not inp:
        return out
    return inp + " " + out


def extract_raw_rule(llm_input: str) -> str:
    """Extract raw_rule from llm_renamed_input.

    raw_rule = 'prem1, prem2, ... => conclusion'
    """
    if not llm_input:
        return ""

    # Extract content inside <problem> ... </problem>
    start_tag = "<problem>"
    end_tag = "</problem>"
    start_idx = llm_input.find(start_tag)
    end_idx = llm_input.rfind(end_tag)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        inner = llm_input
    else:
        inner = llm_input[start_idx + len(start_tag): end_idx]

    if "?" not in inner:
        return ""

    left, right = inner.split("?", 1)
    left = left.strip()
    right = right.strip()

    # 1) premises: all 'predicate ... [id]' on the left
    prem_predicates: list[str] = []
    for m in PREM_WITH_IDX_RE.finditer(left):
        expr = m.group(1).strip()
        if expr:
            prem_predicates.append(expr)

    # 2) conclusion: first segment before '[' (single-goal assumption)
    idx_bracket = right.find("[")
    if idx_bracket != -1:
        conclusion_raw = right[:idx_bracket].strip()
    else:
        conclusion_raw = right.strip()

    # strip trailing separators like ';'
    conclusion_raw = conclusion_raw.rstrip(" ;")

    if not prem_predicates or not conclusion_raw:
        return ""

    return ", ".join(prem_predicates) + " => " + conclusion_raw


def default_output_path(proof_info_path: str) -> str:
    """Build a default output path based on proof_info filename."""
    base = os.path.basename(proof_info_path)
    root, _ext = os.path.splitext(base)
    fname = root + "_prooftraces.jsonl"
    # default dir: datasets/proof_traces
    return os.path.join("datasets", "proof_traces", fname)


def combine(proof_info_path: str, config_info_path: str, output_path: str | None = None) -> None:
    # resolve output path
    if output_path is None:
        output_path = default_output_path(proof_info_path)

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # load configuration map
    config_map = load_configuration_map(config_info_path)

    # load proof info list
    with open(proof_info_path, "r", encoding="utf-8") as f:
        proof_entries = json.load(f)

    num_total = 0
    num_written = 0

    with open(output_path, "w", encoding="utf-8") as out_f:
        for entry in proof_entries:
            num_total += 1
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            pid, info = entry
            if not isinstance(info, dict):
                continue

            # parse config_id from pid like "16_0"
            try:
                cid_str, _goal_idx_str = str(pid).split("_", 1)
                cid = int(cid_str)
            except Exception:
                continue

            config = config_map.get(cid)
            if config is None:
                continue

            configuration_str = config.get("configuration", "")
            points_coordinates = parse_points_coordinates(configuration_str)

            problem = info.get("problem", "")
            augmented_problem = info.get("augmented_problem", problem)
            aux_construction = extract_aux_construction(problem, augmented_problem)

            llm_renamed_input = info.get("llm_renamed_input", "")
            llm_renamed_proof = extract_llm_renamed_proof(info)
            raw_rule = extract_raw_rule(llm_renamed_input)

            out_obj = {
                "id": pid,
                "problem": problem,
                "points_coordinates": points_coordinates,
                "aux_construction": aux_construction,
                "llm_renamed_proof": llm_renamed_proof,
                "raw_rule": raw_rule,
                "rename_map": info.get("rename_map", {}),
            }
            out_f.write(json.dumps(out_obj, ensure_ascii=False))
            out_f.write("\n")
            num_written += 1

    print(f"[prooftrace_combine] total entries: {num_total}, written: {num_written}")
    print(f"[prooftrace_combine] output: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine proof and configuration into proof traces.")
    parser.add_argument(
        "--proof",
        type=str,
        required=True,
        help="Path to proof_info JSON file."
    )
    parser.add_argument(
        "--configuration",
        type=str,
        required=True,
        help="Path to configuration_info JSONL file."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSONL path (if omitted, auto-generate under datasets/proof_traces).",
    )
    args = parser.parse_args()
    combine(args.proof, args.configuration, args.output)


if __name__ == "__main__":
    main()