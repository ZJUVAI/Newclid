#!/usr/bin/env python3
"""
Convert Tong Geometry DSL format to JGEX format.

This script converts 196 case files from Tong Geometry's Python DSL format
to the JGEX format used by GenesisGeo/AlphaGeometry.

Usage:
    python scripts/convert_tong_to_jgex.py \\
        --input datasets/tong_geometry_cases \\
        --output datasets/mo_tg_225/mo_tg_225_draft.txt \\
        --index datasets/mo_tg_225/tong_geometry_cases/tong_case_196_index.txt
"""

import re
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from collections import defaultdict
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TongToJGEXConverter:
    """Converts Tong Geometry DSL to JGEX format."""

    def __init__(self):
        self.points = set()  # All points in the problem
        self.constructions = []  # List of construction steps
        self.goals = []  # List of goal predicates
        self.warnings = []  # Conversion warnings
        self.unsupported_actions = set()  # Track unsupported actions

    def reset(self):
        """Reset converter state for a new problem."""
        self.points = set()
        self.constructions = []
        self.goals = []
        self.warnings = []

    def parse_action_line(self, line: str) -> Optional[Tuple[str, str, str]]:
        """Parse an Action line.

        Returns: (action_type, arg1, arg2) or None if not an Action line
        """
        match = re.match(r'Action\((\w+),\s*"([^"]*)",\s*"([^"]*)"\)', line.strip())
        if match:
            return match.groups()
        return None

    def parse_fact_line(self, line: str) -> Optional[Tuple[str, List[str]]]:
        """Parse a Fact line.

        Returns: (fact_type, args) or None if not a Fact line
        """
        match = re.match(r'Fact\("(\w+)",\s*\[(.*)\]\)', line.strip())
        if not match:
            return None

        fact_type = match.group(1)
        args_str = match.group(2)

        # Extract point names from Segment(*"AB") or Angle(*"ABC") patterns
        points = []
        for segment_match in re.finditer(r'\*"([A-Za-z]+)"', args_str):
            points.extend(list(segment_match.group(1)))

        # Also extract from Circle("V", ["D"]) or Circle(None, [*"ABC"]) patterns
        # Circle("V", ["D"]) -> V, D
        for circle_match in re.finditer(r'Circle\("([A-Za-z])",\s*\["([A-Za-z])"\]\)', args_str):
            points.extend([circle_match.group(1), circle_match.group(2)])

        # Circle(None, [*"ABC"]) -> A, B, C (center is implicit)
        for circle_match in re.finditer(r'Circle\(None,\s*\[\*"([A-Za-z]+)"\]\)', args_str):
            points.extend(list(circle_match.group(1)))

        return (fact_type, points)

    def convert_action(self, action_type: str, arg1: str, arg2: str) -> Optional[str]:
        """Convert a single Action to JGEX construction.

        Returns: JGEX construction string or None if unsupported
        """
        arg2_lower = arg2.lower()

        # BaseAcuteTriangle("", "ABC") -> a b c = triangle a b c
        if action_type == "BaseAcuteTriangle":
            if len(arg2) == 3:
                a, b, c = arg2_lower
                self.points.update([a, b, c])
                return f"{a} {b} {c} = triangle {a} {b} {c}"

        # CircumscribedCircle("ABC", "O") -> o = circle o a b c
        elif action_type == "CircumscribedCircle":
            if len(arg1) == 3 and len(arg2) == 1:
                a, b, c = arg1.lower()
                o = arg2_lower
                self.points.update([a, b, c, o])
                return f"{o} = circle {o} {a} {b} {c}"

        # PerpendicularLine("ACB", "D") -> d = foot d a b c
        # BUT: PerpendicularLine("IDP", "a") with lowercase creates a LINE, not a point - skip it
        elif action_type == "PerpendicularLine":
            if len(arg1) == 3 and len(arg2) == 1:
                if arg2.islower():
                    # This is a line definition, not a point - skip it
                    return None
                a, c, b = arg1.lower()  # ACB means foot from A to line BC
                d = arg2_lower
                self.points.update([a, b, c, d])
                return f"{d} = foot {d} {a} {b} {c}"

        # MidPoint("AB", "M") -> m = midpoint m a b
        elif action_type == "MidPoint":
            if len(arg1) == 2 and len(arg2) == 1:
                a, b = arg1.lower()
                m = arg2_lower
                self.points.update([a, b, m])
                return f"{m} = midpoint {m} {a} {b}"

        # IntersectLineLine("ABCD", "P") -> p = on_line p a b, on_line p c d
        elif action_type == "IntersectLineLine":
            if len(arg1) == 4 and len(arg2) == 1:
                a, b, c, d = arg1.lower()
                p = arg2_lower
                self.points.update([a, b, c, d, p])
                return f"{p} = on_line {p} {a} {b}, on_line {p} {c} {d}"

        # IntersectLineCircleOn("ABC", "O", "D") or IntersectLineCircleOn("MAI", "D")
        # Format 1: IntersectLineCircleOn("MAI", "D") - D is on line MA and on circle I through A
        # Format 2: IntersectLineCircleOn("ABC", "O", "D") - D is on line AB and on circle O through C
        elif action_type == "IntersectLineCircleOn":
            if len(arg1) == 3 and len(arg2) == 1:
                # Format 1: "MAI", "D" -> d = on_line d m a, on_circle d i a
                m, a, i = arg1.lower()
                d = arg2_lower
                self.points.update([m, a, i, d])
                return f"{d} = on_line {d} {m} {a}, on_circle {d} {i} {a}"
            else:
                # Format 2 or other complex cases - mark for manual review
                self.warnings.append(f"IntersectLineCircleOn needs manual review: {arg1}, {arg2}")
                return None

        # ExtendEqual("ABC", "D") -> d = eqdistance d a b c
        # Extends AB by BC from A to get D
        elif action_type == "ExtendEqual":
            if len(arg1) == 3 and len(arg2) == 1:
                a, b, c = arg1.lower()
                d = arg2_lower
                self.points.update([a, b, c, d])
                return f"{d} = eqdistance {d} {a} {b} {c}"

        # Perpendicular("BIC", "V") - perpendicular from B to line IC
        # BUT: Perpendicular with lowercase second arg creates a LINE - skip it
        elif action_type == "Perpendicular":
            if len(arg1) == 3 and len(arg2) == 1:
                if arg2.islower():
                    # This is a line definition, not a point - skip it
                    return None
                b, i, c = arg1.lower()
                v = arg2_lower
                self.points.update([b, i, c, v])
                return f"{v} = foot {v} {b} {i} {c}"

        # InCenter("ABC", "I") -> i = incenter i a b c
        elif action_type == "InCenter":
            if len(arg1) == 3 and len(arg2) == 1:
                a, b, c = arg1.lower()
                i = arg2_lower
                self.points.update([a, b, c, i])
                return f"{i} = incenter {i} {a} {b} {c}"

        # CenterCircle("OB", "") - creates a circle with center O through B
        # This doesn't create a new point, just defines a circle
        elif action_type == "CenterCircle":
            # Skip this - it's implicit in other constructions
            return None

        # AnyPoint("AC", "M") -> m = on_line m a c
        elif action_type == "AnyPoint":
            if len(arg1) == 2 and len(arg2) == 1:
                a, c = arg1.lower()
                m = arg2_lower
                self.points.update([a, c, m])
                return f"{m} = on_line {m} {a} {c}"

        # AnyArc("BDO", "C") -> c = on_circle c o b (assuming O is center)
        elif action_type == "AnyArc":
            if len(arg1) == 3 and len(arg2) == 1:
                b, d, o = arg1.lower()
                c = arg2_lower
                self.points.update([b, d, o, c])
                return f"{c} = on_circle {c} {o} {b}"

        # Parallel("DCBE", "L") -> l = on_pline l d c b e
        # Point L such that DL || BE
        elif action_type == "Parallel":
            if len(arg1) == 4 and len(arg2) == 1:
                d, c, b, e = arg1.lower()
                l = arg2_lower
                self.points.update([d, c, b, e, l])
                return f"{l} = on_pline {l} {d} {c} {b} {e}"

        # MidArc("BCO", "S") -> s = on_circle s o b (midpoint of arc BC on circle O)
        # This is complex - mark for manual review
        elif action_type == "MidArc":
            self.warnings.append(f"MidArc needs manual review: {arg1}, {arg2}")
            return None

        # IntersectLineCircleOff - opposite intersection point
        elif action_type == "IntersectLineCircleOff":
            self.warnings.append(f"IntersectLineCircleOff needs manual review: {arg1}, {arg2}")
            return None

        # IntersectCircleCircle - intersection of two circles
        elif action_type == "IntersectCircleCircle":
            self.warnings.append(f"IntersectCircleCircle needs manual review: {arg1}, {arg2}")
            return None

        # IsogonalConjugate - advanced construction
        elif action_type == "IsogonalConjugate":
            self.warnings.append(f"IsogonalConjugate needs manual review: {arg1}, {arg2}")
            return None

        else:
            self.unsupported_actions.add(action_type)
            self.warnings.append(f"Unsupported action: {action_type}")
            return None

    def convert_fact(self, fact_type: str, points: List[str]) -> Optional[str]:
        """Convert a Fact to JGEX goal predicate.

        Returns: JGEX goal string or None if unsupported
        """
        points_lower = [p.lower() for p in points]

        # eqline: equal segments
        # Fact("eqline", [Segment(*"AB"), Segment(*"CD")]) -> ? cong a b c d
        if fact_type == "eqline":
            if len(points_lower) == 4:
                return f"? cong {' '.join(points_lower)}"

        # perp: perpendicular
        # Fact("perp", [Angle(*"ABC")]) -> ? perp a b b c
        elif fact_type == "perp":
            if len(points_lower) == 3:
                a, b, c = points_lower
                return f"? perp {a} {b} {b} {c}"

        # para: parallel
        # Fact("para", [...]) -> ? para a b c d
        elif fact_type == "para":
            if len(points_lower) == 4:
                return f"? para {' '.join(points_lower)}"

        # eqangle: equal angles
        # Fact("eqangle", [Angle(*"ABC"), Angle(*"DEF")]) -> ? eqangle a b c d e f
        elif fact_type == "eqangle":
            if len(points_lower) == 6:
                return f"? eqangle {' '.join(points_lower)}"
            elif len(points_lower) == 8:
                return f"? eqangle {' '.join(points_lower)}"

        # cong: congruent (same as eqline for segments)
        elif fact_type == "cong":
            if len(points_lower) == 4:
                return f"? cong {' '.join(points_lower)}"
            elif len(points_lower) == 6:
                # Two triangles congruent - need to check if this is supported
                self.warnings.append(f"Triangle congruence may need manual review: {points}")
                return f"? cong {' '.join(points_lower)}"

        # eqcircle: equal circles (same radius)
        # Fact("eqcircle", [Circle(*"OA"), Circle(*"PB")]) -> ? cong o a p b
        # Fact("eqcircle", [Circle(None, [*"ABC"]), Circle(None, [*"DEF"])]) -> ? cong o1 a o2 d (need circumcenters)
        elif fact_type == "eqcircle":
            if len(points_lower) == 4:
                # Two circles with explicit centers: Circle("O", ["A"]), Circle("P", ["B"])
                return f"? cong {' '.join(points_lower)}"
            elif len(points_lower) == 6:
                # Two circumcircles: Circle(None, [*"ABC"]), Circle(None, [*"DEF"])
                # This means the circumradii are equal, which is complex to express
                # We'd need to construct the circumcenters first
                self.warnings.append(f"eqcircle with circumcircles needs manual review: {points}")
                return None

        # midp: midpoint
        # Fact("midp", [Point(*"M"), Segment(*"AB")]) -> ? midp m a b
        elif fact_type == "midp":
            if len(points_lower) == 3:
                return f"? midp {' '.join(points_lower)}"

        # eqratio: equal ratios
        # Fact("eqratio", [...]) -> ? eqratio a b c d e f g h
        elif fact_type == "eqratio":
            if len(points_lower) == 8:
                return f"? eqratio {' '.join(points_lower)}"

        # simtri: similar triangles
        elif fact_type == "simtri":
            self.warnings.append(f"simtri needs manual review: {points}")
            return None

        # contri: congruent triangles
        elif fact_type == "contri":
            self.warnings.append(f"contri needs manual review: {points}")
            return None

        else:
            self.warnings.append(f"Unsupported fact type: {fact_type}")
            return None

    def convert_case_file(self, file_path: Path, case_name: str) -> Optional[str]:
        """Convert a single case file to JGEX format.

        Returns: JGEX problem string (two lines) or None if conversion failed
        """
        self.reset()

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Parse all actions and facts
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Try to parse as Action
            action_result = self.parse_action_line(line)
            if action_result:
                action_type, arg1, arg2 = action_result
                construction = self.convert_action(action_type, arg1, arg2)
                if construction:
                    self.constructions.append(construction)
                continue

            # Try to parse as Fact
            fact_result = self.parse_fact_line(line)
            if fact_result:
                fact_type, points = fact_result
                goal = self.convert_fact(fact_type, points)
                if goal:
                    self.goals.append(goal)
                continue

        # Build JGEX output
        if not self.constructions:
            self.warnings.append("No constructions generated")
            return None

        if not self.goals:
            self.warnings.append("No goals generated")
            return None

        # Line 1: problem name
        # Line 2: constructions ? goals (multiple goals separated by comma)
        construction_str = "; ".join(self.constructions)

        # Remove the "?" prefix from each goal and join with commas
        goal_predicates = [g.replace("? ", "") for g in self.goals]
        goal_str = ", ".join(goal_predicates)

        jgex = f"{case_name}\n{construction_str} ? {goal_str}"
        return jgex


def main():
    parser = argparse.ArgumentParser(description="Convert Tong Geometry DSL to JGEX format")
    parser.add_argument("--input", type=str, required=True,
                        help="Input directory containing case*.txt files")
    parser.add_argument("--output", type=str, required=True,
                        help="Output JGEX file path")
    parser.add_argument("--index", type=str, required=True,
                        help="Index file mapping case numbers to problem names")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed conversion information")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_file = Path(args.output)
    index_file = Path(args.index)

    # Read index file to get problem names
    case_names = {}
    with open(index_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.match(r'Case (\d+):\s*(.+)', line.strip())
            if match:
                case_num = int(match.group(1))
                case_name = match.group(2).strip()
                # Convert to valid identifier
                case_name = re.sub(r'[^\w\s-]', '', case_name)
                case_name = re.sub(r'\s+', '_', case_name)
                case_name = f"case{case_num}_{case_name}".lower()
                case_names[case_num] = case_name

    # Convert all case files
    converter = TongToJGEXConverter()
    results = []
    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "warnings": 0
    }

    # Get all case files
    case_files = sorted(input_dir.glob("case*.txt"), key=lambda p: int(re.search(r'case(\d+)', p.name).group(1)))

    for case_file in case_files:
        case_num = int(re.search(r'case(\d+)', case_file.name).group(1))
        case_name = case_names.get(case_num, f"case{case_num}")

        stats["total"] += 1

        if args.verbose:
            print(f"\nConverting {case_file.name} -> {case_name}")

        jgex = converter.convert_case_file(case_file, case_name)

        if jgex:
            results.append(jgex)
            stats["success"] += 1
            if converter.warnings:
                stats["warnings"] += 1
                if args.verbose:
                    print(f"  Warnings: {len(converter.warnings)}")
                    for warning in converter.warnings:
                        print(f"    - {warning}")
        else:
            stats["failed"] += 1
            if args.verbose:
                print(f"  FAILED")
                for warning in converter.warnings:
                    print(f"    - {warning}")

    # Write output file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))

    # Print summary
    print(f"\n{'='*60}")
    print(f"Conversion Summary")
    print(f"{'='*60}")
    print(f"Total cases:        {stats['total']}")
    print(f"Successfully converted: {stats['success']} ({stats['success']/stats['total']*100:.1f}%)")
    print(f"Failed:             {stats['failed']} ({stats['failed']/stats['total']*100:.1f}%)")
    print(f"With warnings:      {stats['warnings']} ({stats['warnings']/stats['total']*100:.1f}%)")
    print(f"\nOutput written to: {output_file}")

    if converter.unsupported_actions:
        print(f"\nUnsupported actions encountered:")
        for action in sorted(converter.unsupported_actions):
            print(f"  - {action}")


if __name__ == "__main__":
    main()

