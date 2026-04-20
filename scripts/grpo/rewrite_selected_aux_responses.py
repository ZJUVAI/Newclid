#!/usr/bin/env python3
"""Rewrite selected GRPO datasets with the original tagged aux response format."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from newclid.training.aux_dsl import extract_first_tagged_aux_block


def _row_key(row: dict) -> tuple[str, str]:
    return str(row.get("query", "")), str(row.get("fl_problem", ""))


def _load_selected_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _build_response_lookup(raw_path: Path, keys: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    lookup: dict[tuple[str, str], str] = {}
    with raw_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            key = (
                str(row.get("llm_input_renamed", "")),
                str(row.get("fl_problem", "")),
            )
            if key not in keys or key in lookup:
                continue
            response = extract_first_tagged_aux_block(row.get("llm_output_renamed", ""))
            if response is not None:
                lookup[key] = response
    return lookup


def rewrite_dataset(input_path: Path, raw_path: Path, output_path: Path) -> tuple[int, int]:
    rows = _load_selected_rows(input_path)
    lookup = _build_response_lookup(raw_path, {_row_key(row) for row in rows})

    rewritten = 0
    missing = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            key = _row_key(row)
            response = lookup.get(key)
            if response is None:
                missing += 1
                response = row.get("response", "")
            else:
                rewritten += 1
            patched = dict(row)
            patched["response"] = response
            handle.write(json.dumps(patched, ensure_ascii=False))
            handle.write("\n")
    return rewritten, missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Selected dataset JSONL to rewrite.")
    parser.add_argument("--raw", type=Path, required=True, help="Original raw JSONL with llm_output_renamed.")
    parser.add_argument("--output", type=Path, required=True, help="Destination JSONL.")
    args = parser.parse_args()

    rewritten, missing = rewrite_dataset(args.input, args.raw, args.output)
    print(f"rewritten={rewritten}")
    print(f"missing={missing}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
