#!/usr/bin/env python3
"""
Generate Copilot task forms for MO-TG-225 natural language collection.

This script creates structured task forms for each MO-TG-225 problem,
including DSL text, metadata, and links, to facilitate natural language
text and solution collection via Copilot.

Usage:
    python scripts/generate_copilot_tasks.py \
        --jgex datasets/mo_tg_225/mo_tg_225_draft.txt \
        --index datasets/mo_tg_225/mo_tg_225_index.txt \
        --output outputs/mo_tg_225_copilot_tasks.json \
        --format json

    # Or output as Markdown
    python scripts/generate_copilot_tasks.py \
        --jgex datasets/mo_tg_225/mo_tg_225_draft.txt \
        --index datasets/mo_tg_225/mo_tg_225_index.txt \
        --output outputs/mo_tg_225_copilot_tasks.md \
        --format markdown
"""

import argparse
import json
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional


@dataclass
class ProblemTask:
    """Task information for a single problem."""
    case_id: str
    problem_name: str
    jgex_dsl: str
    problem_source: str
    year: str
    competition: str
    links: Dict[str, str]
    prompt: str


def parse_jgex_file(filepath: Path) -> Dict[str, str]:
    """
    Parse JGEX file and return mapping from problem name to DSL text.

    Returns:
        Dict mapping problem_name -> jgex_dsl
    """
    problems = {}

    with open(filepath, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    # Parse two lines at a time
    for i in range(0, len(lines), 2):
        if i + 1 >= len(lines):
            break

        name = lines[i]
        jgex_text = lines[i + 1]
        problems[name] = jgex_text

    return problems


def parse_index_file(filepath: Path) -> List[Dict[str, any]]:
    """
    Parse index file and extract metadata for each case.

    Returns:
        List of dicts with case metadata
    """
    cases = []
    current_case = None

    with open(filepath, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith('#') or line.startswith('=') or line.startswith('-'):
            continue

        # Check if this is a case line (starts with "case")
        if line.startswith('case'):
            # Save previous case if exists
            if current_case:
                cases.append(current_case)

            # Parse case line: "case76    | IMO 1959 P5 | 1959 | IMO | Converted"
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 5:
                current_case = {
                    'case_id': parts[0],
                    'problem_source': parts[1],
                    'year': parts[2],
                    'competition': parts[3],
                    'jgex_status': parts[4],
                    'links': {}
                }

        # Check if this is a link line
        elif current_case and ':' in line and ('http://' in line or 'https://' in line):
            # Parse link: "official: https://..."
            link_parts = line.split(':', 1)
            if len(link_parts) == 2:
                link_type = link_parts[0].strip()
                link_url = link_parts[1].strip()
                current_case['links'][link_type] = link_url

    # Don't forget the last case
    if current_case:
        cases.append(current_case)

    return cases


def generate_prompt(case: Dict[str, any], jgex_dsl: str) -> str:
    """
    Generate a prompt for Copilot to collect natural language text and solution.

    Args:
        case: Case metadata dict
        jgex_dsl: JGEX DSL text

    Returns:
        Prompt string
    """
    prompt = f"""Please help collect the natural language problem statement and solution for this geometry problem.

**Problem Information:**
- Source: {case['problem_source']}
- Year: {case['year']}
- Competition: {case['competition']}

**JGEX Formalization (DSL):**
```
{jgex_dsl}
```

**Available Resources:**
"""

    for link_type, link_url in case['links'].items():
        prompt += f"- {link_type.capitalize()}: {link_url}\n"

    prompt += """
**Task:**
1. Visit the provided links to find the original problem statement
2. Extract the natural language problem statement (in English)
3. If available, extract or summarize the official solution
4. Format the output as follows:

**Problem Statement:**
[Natural language problem statement here]

**Solution (if available):**
[Solution summary or key steps here]

**Notes:**
- If the problem statement is not in English, please translate it
- If multiple formulations exist, prefer the official IMO/competition version
- If no solution is readily available, note "Solution not found" and provide any relevant hints or approaches you can identify
"""

    return prompt


def create_tasks(jgex_file: Path, index_file: Path) -> List[ProblemTask]:
    """
    Create task list by combining JGEX and index data.

    Args:
        jgex_file: Path to JGEX file
        index_file: Path to index file

    Returns:
        List of ProblemTask objects
    """
    # Parse files
    jgex_problems = parse_jgex_file(jgex_file)
    index_cases = parse_index_file(index_file)

    # Create mapping from case_id to problem_name
    # Problem names in JGEX file follow pattern: case{N}_{description}
    case_to_jgex = {}
    for problem_name in jgex_problems.keys():
        # Extract case number from problem name
        match = re.match(r'case(\d+)', problem_name)
        if match:
            case_num = match.group(1)
            case_id = f"case{case_num}"
            case_to_jgex[case_id] = problem_name

    # Build tasks
    tasks = []
    for case in index_cases:
        case_id = case['case_id']

        # Skip if not converted to JGEX
        if case['jgex_status'] != 'Converted':
            continue

        # Find corresponding JGEX problem
        if case_id not in case_to_jgex:
            print(f"Warning: No JGEX found for {case_id}")
            continue

        problem_name = case_to_jgex[case_id]
        jgex_dsl = jgex_problems[problem_name]

        # Generate prompt
        prompt = generate_prompt(case, jgex_dsl)

        # Create task
        task = ProblemTask(
            case_id=case_id,
            problem_name=problem_name,
            jgex_dsl=jgex_dsl,
            problem_source=case['problem_source'],
            year=case['year'],
            competition=case['competition'],
            links=case['links'],
            prompt=prompt
        )
        tasks.append(task)

    return tasks


def save_as_json(tasks: List[ProblemTask], output_path: Path):
    """Save tasks as JSON file."""
    data = {
        'total_tasks': len(tasks),
        'tasks': [asdict(task) for task in tasks]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(tasks)} tasks to {output_path}")


def save_as_markdown(tasks: List[ProblemTask], output_path: Path):
    """Save tasks as Markdown file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# MO-TG-225 Natural Language Collection Tasks\n\n")
        f.write(f"Total Tasks: {len(tasks)}\n\n")
        f.write("---\n\n")

        for i, task in enumerate(tasks, 1):
            f.write(f"## Task {i}: {task.case_id} - {task.problem_source}\n\n")
            f.write(f"**Problem Name:** `{task.problem_name}`\n\n")
            f.write(f"**Competition:** {task.competition} ({task.year})\n\n")

            f.write("**Links:**\n")
            for link_type, link_url in task.links.items():
                f.write(f"- [{link_type.capitalize()}]({link_url})\n")
            f.write("\n")

            f.write("**JGEX DSL:**\n")
            f.write("```\n")
            f.write(task.jgex_dsl)
            f.write("\n```\n\n")

            f.write("**Prompt:**\n")
            f.write(task.prompt)
            f.write("\n\n")

            f.write("**Response Area:**\n")
            f.write("```\n")
            f.write("[Copilot: Please fill in the natural language problem statement and solution here]\n")
            f.write("```\n\n")

            f.write("---\n\n")

    print(f"Saved {len(tasks)} tasks to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate Copilot task forms for MO-TG-225 natural language collection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--jgex',
        type=Path,
        required=True,
        help='Path to JGEX file (mo_tg_225_draft.txt)'
    )
    parser.add_argument(
        '--index',
        type=Path,
        required=True,
        help='Path to index file (mo_tg_225_index.txt)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output file path'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'markdown'],
        default='json',
        help='Output format (default: json)'
    )

    args = parser.parse_args()

    # Validate input files
    if not args.jgex.exists():
        print(f"Error: JGEX file not found: {args.jgex}")
        return 1

    if not args.index.exists():
        print(f"Error: Index file not found: {args.index}")
        return 1

    # Create output directory
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Create tasks
    print("Parsing files...")
    tasks = create_tasks(args.jgex, args.index)

    print(f"Generated {len(tasks)} tasks")

    # Save output
    if args.format == 'json':
        save_as_json(tasks, args.output)
    else:
        save_as_markdown(tasks, args.output)

    # Print summary
    print("\nTask Summary:")
    competitions = {}
    for task in tasks:
        comp = task.competition
        competitions[comp] = competitions.get(comp, 0) + 1

    for comp, count in sorted(competitions.items()):
        print(f"  {comp}: {count} tasks")


if __name__ == '__main__':
    main()
