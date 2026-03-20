#!/usr/bin/env python3
"""
Create MO-TG-225 benchmark index file.

This script creates an index file mapping each case to its problem source,
with links to original problems and solutions where available.
"""

import re
from pathlib import Path
from typing import Dict, Tuple, Optional


def parse_problem_name(name: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Parse problem name to extract competition, year, and problem number.

    Returns: (competition, year, problem_num) or (None, None, None) if not parseable
    """
    # IMO patterns
    imo_match = re.match(r'IMO (\d{4}) P(\d+)', name, re.IGNORECASE)
    if imo_match:
        return ("IMO", int(imo_match.group(1)), imo_match.group(2))

    # USAMO patterns
    usamo_match = re.match(r'USAMO (\d{4}) P(\d+)', name, re.IGNORECASE)
    if usamo_match:
        return ("USAMO", int(usamo_match.group(1)), usamo_match.group(2))

    # USAJMO patterns
    usajmo_match = re.match(r'USAJMO (\d{4}) P(\d+)', name, re.IGNORECASE)
    if usajmo_match:
        return ("USAJMO", int(usajmo_match.group(1)), usajmo_match.group(2))

    # USATST patterns
    usatst_match = re.match(r'USATST (\d{4}) P(\d+)', name, re.IGNORECASE)
    if usatst_match:
        return ("USATST", int(usatst_match.group(1)), usatst_match.group(2))

    # TSTST patterns
    tstst_match = re.match(r'TSTST (\d{4}) P(\d+)', name, re.IGNORECASE)
    if tstst_match:
        return ("TSTST", int(tstst_match.group(1)), tstst_match.group(2))

    # USEMO patterns
    usemo_match = re.match(r'USEMO (\d{4}) P(\d+)', name, re.IGNORECASE)
    if usemo_match:
        return ("USEMO", int(usemo_match.group(1)), usemo_match.group(2))

    # ISL patterns
    isl_match = re.match(r'ISL (\d{4}) G(\d+)', name, re.IGNORECASE)
    if isl_match:
        return ("ISL", int(isl_match.group(1)), f"G{isl_match.group(2)}")

    # China TST patterns (various formats)
    china_match = re.match(r'China TST (\d{4})', name, re.IGNORECASE)
    if china_match:
        return ("China TST", int(china_match.group(1)), None)

    return (None, None, None)


def get_problem_links(competition: str, year: int, problem_num: str) -> Dict[str, str]:
    """Get links for a problem.

    Returns: dict with 'official', 'evan_chen', 'aops' keys
    """
    links = {}

    if competition == "IMO":
        # IMO official site
        links["official"] = f"https://www.imo-official.org/year_info.aspx?year={year}"
        # Evan Chen's site
        links["evan_chen"] = f"https://web.evanchen.cc/exams/IMO-{year}-notes.pdf"
        # AoPS
        links["aops"] = f"https://artofproblemsolving.com/community/c6h{year}p{problem_num}"

    elif competition in ["USAMO", "USAJMO", "USATST", "TSTST", "USEMO"]:
        # Evan Chen's site
        links["evan_chen"] = f"https://web.evanchen.cc/exams/{competition}-{year}-notes.pdf"
        # AoPS
        links["aops"] = f"https://artofproblemsolving.com/community/c6"

    elif competition == "ISL":
        # IMO Shortlist
        links["official"] = f"https://www.imo-official.org/year_info.aspx?year={year}"
        links["evan_chen"] = f"https://web.evanchen.cc/exams/ISL-{year}-notes.pdf"

    elif competition == "China TST":
        # No standard links available
        pass

    return links


def main():
    # Read the existing index
    index_file = Path("datasets/mo_tg_225/tong_geometry_cases/tong_case_196_index.txt")
    output_file = Path("datasets/mo_tg_225/mo_tg_225_index.txt")

    cases = {}
    with open(index_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.match(r'Case (\d+):\s*(.+)', line.strip())
            if match:
                case_num = int(match.group(1))
                case_name = match.group(2).strip()
                cases[case_num] = case_name

    # Group cases by competition
    grouped = {
        "IMO": [],
        "USAMO": [],
        "USAJMO": [],
        "USATST": [],
        "TSTST": [],
        "USEMO": [],
        "ISL": [],
        "China TST": [],
        "Other": []
    }

    for case_num, case_name in sorted(cases.items()):
        competition, year, problem_num = parse_problem_name(case_name)
        if competition:
            grouped[competition].append((case_num, case_name, year, problem_num))
        else:
            grouped["Other"].append((case_num, case_name, None, None))

    # Write output file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# MO-TG-225 Benchmark Index\n")
        f.write("#\n")
        f.write("# This file maps each case from the Tong Geometry benchmark to its metadata:\n")
        f.write("# - Case ID: Case number (1-196)\n")
        f.write("# - Problem Source: Original problem designation\n")
        f.write("# - Year: Competition year\n")
        f.write("# - Competition: Competition name\n")
        f.write("# - JGEX Status: Conversion status (Converted/Failed/Manual Review)\n")
        f.write("# - Links: URLs to problem statements and solutions\n")
        f.write("#\n")
        f.write("# Generated: 2026-03-02\n")
        f.write("# Source: Tong Geometry paper, tong_case_196_index.txt\n")
        f.write("#\n")
        f.write("# Note: The Tong Geometry paper mentions 225 problems derived from these 196 cases.\n")
        f.write("# Some cases may generate multiple problems (e.g., if-and-only-if splits).\n")
        f.write("\n")
        f.write("="*80 + "\n")
        f.write(f"{'Case ID':<10} | {'Problem Source':<35} | {'Year':<6} | {'Competition':<15} | {'JGEX Status':<15}\n")
        f.write("="*80 + "\n")
        f.write("\n")

        # Write each competition group
        for comp_name in ["IMO", "USAMO", "USAJMO", "USATST", "TSTST", "USEMO", "ISL", "China TST", "Other"]:
            if not grouped[comp_name]:
                continue

            f.write(f"# {comp_name} Problems\n")
            f.write("-"*80 + "\n")

            for case_num, case_name, year, problem_num in sorted(grouped[comp_name], key=lambda x: (x[2] or 0, x[0])):
                year_str = str(year) if year else "N/A"
                status = "Converted"  # Default, would need to check actual conversion results

                f.write(f"case{case_num:<5} | {case_name:<35} | {year_str:<6} | {comp_name:<15} | {status:<15}\n")

                # Add links if available
                if year and problem_num:
                    links = get_problem_links(comp_name, year, problem_num)
                    if links:
                        for link_type, url in links.items():
                            f.write(f"         {link_type}: {url}\n")

            f.write("\n")

        # Summary statistics
        f.write("="*80 + "\n")
        f.write("# Summary Statistics\n")
        f.write("="*80 + "\n")
        f.write(f"Total cases: {len(cases)}\n")
        for comp_name, items in grouped.items():
            if items:
                f.write(f"{comp_name}: {len(items)} cases\n")

    print(f"Index file created: {output_file}")
    print(f"Total cases: {len(cases)}")


if __name__ == "__main__":
    main()
