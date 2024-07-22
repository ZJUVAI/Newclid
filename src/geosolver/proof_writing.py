"""Helper functions to write proofs in a natural language."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from geosolver.dependency.symbols import Point
from geosolver.dependency.dependency import IN_PREMISES, NUMERICAL_CHECK, Dependency
from geosolver.statement import Statement

if TYPE_CHECKING:
    from geosolver.proof import Proof


def write_solution(proof: "Proof", out_file: Optional[Path]) -> None:
    """Output the solution to out_file.

    Args:
      proof: Proof state.
      problem: Containing the problem definition and theorems.
      out_file: file to write to, empty string to skip writing to file.
    """

    id: dict[Statement, str] = {}
    goals = [goal for goal in proof.goals if goal.check()]
    for k, goal in enumerate(goals):
        id[goal] = f"g{k}"

    def rediger(dep: Dependency) -> str:
        for statement in (dep.statement,) + dep.why:
            if statement not in id:
                id[statement] = str(len(id) - len(goals))
        return f"{', '.join(premise.pretty() + ' [' + id[premise] + ']' for premise in dep.why)} ({dep.reason})=> {dep.statement.pretty()} [{id[dep.statement]}]"

    solution = "==========================\n"
    solution += "* From problem construction:\n"
    solution += f"Points : {', '.join(p.pretty_name for p in proof.symbols_graph.nodes_of_type(Point))}\n"
    proof_deps = proof.dep_graph.proof_deps(goals)
    premises: list[Dependency] = []
    numercial_checked: list[Dependency] = []
    proof_steps: list[Dependency] = []
    for line in proof_deps:
        if IN_PREMISES == line.reason:
            premises.append(line)
        elif NUMERICAL_CHECK == line.reason:
            numercial_checked.append(line)
        else:
            proof_steps.append(line)
    for line in premises:
        solution += rediger(line) + "\n"
    for line in numercial_checked:
        solution += rediger(line) + "\n"
    solution += "* Proof steps:\n"
    for k, line in enumerate(proof_steps):
        if NUMERICAL_CHECK not in line.reason and IN_PREMISES not in line:
            solution += f"{k:03d}. {rediger(line)}\n"
    solution += "\n=========================="
    logging.info(solution)
    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(solution)
        logging.info("Solution written to %s.", out_file)
