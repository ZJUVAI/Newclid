#!/usr/bin/env python3

import argparse
import json
from collections import defaultdict
from pathlib import Path


def find_duplicate_points(jsonl_path: Path) -> int:
    duplicate_line_count = 0

    with jsonl_path.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            record = json.loads(line)
            point_coords = record.get("point_coords_grid", {})

            coord_to_points = defaultdict(list)
            for point_name, coord in point_coords.items():
                coord_to_points[tuple(coord)].append(point_name)

            duplicates = {
                coord: point_names
                for coord, point_names in coord_to_points.items()
                if len(point_names) > 1
            }
            if not duplicates:
                continue

            duplicate_line_count += 1
            image_path = record.get("image_path", "<missing image_path>")
            print(f"line {line_no}: {image_path}")
            for coord, point_names in sorted(duplicates.items()):
                points_text = ", ".join(sorted(point_names))
                print(f"  coord {coord}: {points_text}")

    if duplicate_line_count == 0:
        print("No duplicate coordinates found within any point_coords_grid.")
    else:
        print(f"Found duplicates in {duplicate_line_count} line(s).")

    return duplicate_line_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check whether any JSONL row contains duplicate coordinates in point_coords_grid."
    )
    parser.add_argument("jsonl_path", type=Path, help="Path to the JSONL file to inspect.")
    args = parser.parse_args()

    find_duplicate_points(args.jsonl_path)


if __name__ == "__main__":
    main()
