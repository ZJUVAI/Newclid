#!/usr/bin/env python3
"""Prepare an aux-only GRPO dataset from existing JSONL data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from newclid.training.aux_dsl import extract_first_tagged_aux_block


def convert_dataset(input_path: Path, output_path: Path) -> tuple[int, int]:
    """Keep only samples that contain a valid first <aux> block."""
    kept = 0
    skipped = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as src, output_path.open(
        "w", encoding="utf-8"
    ) as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue

            record = json.loads(line)
            query = record.get("llm_input_renamed", "")
            fl_problem = record.get("fl_problem", "")
            response = extract_first_tagged_aux_block(record.get("llm_output_renamed", ""))
            if not query or not fl_problem or response is None:
                skipped += 1
                continue

            payload = {
                "query": query,
                "fl_problem": fl_problem,
                "response": response,
            }
            dst.write(json.dumps(payload, ensure_ascii=False))
            dst.write("\n")
            kept += 1

    return kept, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source JSONL with llm_input_renamed/llm_output_renamed")
    parser.add_argument("output", type=Path, help="Output JSONL for GRPO training")
    args = parser.parse_args()

    kept, skipped = convert_dataset(args.input, args.output)
    print(f"wrote {kept} samples to {args.output}")
    print(f"skipped {skipped} samples without valid aux blocks")


if __name__ == "__main__":
    main()
