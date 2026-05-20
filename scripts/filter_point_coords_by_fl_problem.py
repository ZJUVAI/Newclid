#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


POINT_DEF_PATTERN = re.compile(r"([A-Za-z][A-Za-z0-9_]*)@")


def extract_identifiers(fl_problem: str) -> set[str]:
    identifiers = set()

    for construction in fl_problem.split(";"):
        if "=" not in construction:
            continue

        lhs, _ = construction.split("=", 1)
        identifiers.update(POINT_DEF_PATTERN.findall(lhs))

    return identifiers


def filter_point_coords_by_fl_problem(input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_lines = 0
    changed_lines = 0

    with input_path.open("r", encoding="utf-8") as fin, output_path.open(
        "w", encoding="utf-8"
    ) as fout:
        for raw_line in fin:
            line = raw_line.strip()
            if not line:
                continue

            total_lines += 1
            record = json.loads(line)

            point_coords = record.get("point_coords_grid", {})
            fl_problem = record.get("fl_problem", "")
            identifiers = extract_identifiers(fl_problem)

            filtered_point_coords = {
                point_name: coord
                for point_name, coord in point_coords.items()
                if point_name in identifiers
            }

            if filtered_point_coords != point_coords:
                changed_lines += 1

            record["point_coords_grid"] = filtered_point_coords
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Processed {total_lines} line(s).")
    print(f"Updated {changed_lines} line(s).")
    print(f"Wrote output to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keep only points in point_coords_grid that also appear in fl_problem."
    )
    parser.add_argument("input_jsonl", type=Path, help="Input JSONL path.")
    parser.add_argument("output_jsonl", type=Path, help="Output JSONL path.")
    args = parser.parse_args()

    filter_point_coords_by_fl_problem(args.input_jsonl, args.output_jsonl)


if __name__ == "__main__":
    main()
