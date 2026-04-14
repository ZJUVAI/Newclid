#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from newclid.configs import default_defs_path
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.formulations.clause import translate_sentence
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
from newclid.statement import Statement


def problem_to_dsl(
    problem: ProblemJGEX,
    defs: dict[str, DefinitionJGEX],
) -> str:
    dep_idx: dict[Statement, str] = {}
    dep_graph = DependencyGraph(AlgebraicManipulator())

    data_tmp: dict[str, list[Statement]] = defaultdict(list)
    for construction in problem.constructions:
        group: dict[str, tuple[str, ...]] = {}
        p2deps: dict[tuple[str, ...], list[Statement]] = defaultdict(list)
        for constr_sentence in construction.sentences:
            cdef = defs[constr_sentence[0]]
            if len(constr_sentence) == len(cdef.declare):
                mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
            else:
                assert len(constr_sentence) + len(construction.points) == len(cdef.declare)
                points = tuple(p.split("@")[0] for p in construction.points)
                mapping = dict(zip(cdef.declare[1:], points + constr_sentence[1:]))
            for points, basics in cdef.basics:
                points = tuple(mapping[x] for x in points)
                for point in points:
                    group[point] = points
                for basic in basics:
                    statement = Statement.from_tokens(
                        translate_sentence(mapping, basic),
                        dep_graph,
                    )
                    p2deps[points].append(statement)

        points = [point.split("@")[0] for point in construction.points]
        while points:
            point = points[0]
            current_group = group[point]
            points = [candidate for candidate in points if candidate not in current_group]
            data_tmp[" ".join(current_group)] = list(p2deps[current_group])

    data_problem = "<problem> "
    string_premise: list[str] = []
    for points, deps in data_tmp.items():
        premise = points + " : "
        for dep in deps:
            if dep not in dep_idx:
                dep_idx[dep] = f"{len(dep_idx):03d}"
            premise += dep.to_str() + f" [{dep_idx[dep]}] "
        string_premise.append(premise.strip())
    data_problem += " ; ".join(string_premise) + " ? "
    data_problem += " ; ".join(
        Statement.from_tokens(goal, dep_graph).to_str()
        for goal in problem.goals
    )
    data_problem += " </problem>"
    return data_problem


def format_model_input(query: str, model_path: str) -> str:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": query},
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    return text + "<think>\n\n</think>\n\n"


def build_records(
    problems_path: Path,
    defs_path: Path,
    rename: bool,
    model_path: str | None,
) -> list[dict[str, Any]]:
    defs = DefinitionJGEX.to_dict(DefinitionJGEX.parse_txt_file(defs_path))
    problems = ProblemJGEX.parse_txt_file(problems_path)

    records: list[dict[str, Any]] = []
    for problem_name, raw_problem in problems.items():
        problem = raw_problem.renamed() if rename else raw_problem
        query = problem_to_dsl(problem, defs)
        record: dict[str, Any] = {
            "problem_name": problem_name,
            "rename": rename,
            "original_problem": str(raw_problem),
            "query": query,
        }
        if rename:
            record["renamed_problem"] = str(problem)
        if model_path is not None:
            record["model_path"] = model_path
            record["model_input"] = format_model_input(query, model_path)
        records.append(record)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert benchmark problems into the LM text format used by "
            "src/newclid/agent/lm.py, without appending the <aux> x00 suffix."
        )
    )
    parser.add_argument(
        "--problems-path",
        type=Path,
        default=Path("benchmarks/dev_imo.txt"),
    )
    parser.add_argument(
        "--defs-path",
        type=Path,
        default=default_defs_path(),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("experiments/test_frontier_models/dev_imo_model_inputs.jsonl"),
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help=(
            "Optional tokenizer/model path. When provided, also writes the exact "
            "chat-templated text that lm.py feeds into the model before <aux> x00."
        ),
    )
    parser.add_argument(
        "--rename",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to rename points before conversion. Defaults to true.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = build_records(
        problems_path=args.problems_path,
        defs_path=args.defs_path,
        rename=args.rename,
        model_path=args.model_path,
    )

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    with args.output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} prompts to {args.output_path}")


if __name__ == "__main__":
    main()
