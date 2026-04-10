"""Helper functions to write proofs in a natural language."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from newclid.dependencies.dependency import (
    IN_PREMISES,
    NUMERICAL_CHECK,
    TRIVIAL,
    Dependency,
)
from newclid.statement import Statement
from newclid.dependencies.symbols import Point

if TYPE_CHECKING:
    from newclid.proof import ProofState


def write_proof_steps(
    proof_state: "ProofState",
    out_file: Optional[Path] = None,
    print_output: bool = True,
) -> None:
    """Output the solution to out_file.

    Args:
      proof: Proof state.
      problem: Containing the problem definition and theorems.
      out_file: file to write to, empty string to skip writing to file.
    """

    id: dict[Statement, str] = {}
    goals = [goal for goal in proof_state.goals if goal.check()]
    for k, goal in enumerate(goals):
        id[goal] = f"g{k}"

    def rediger(dep: Dependency) -> str:
        for statement in (dep.statement,) + dep.why:
            if statement not in id:
                id[statement] = str(len(id) - len(goals))
        return f"{', '.join(premise.pretty() + ' [' + id[premise] + ']' for premise in dep.why)} ({dep.reason})=> {dep.statement.pretty()} [{id[dep.statement]}]"

    (
        points,
        premises,
        numercial_checked_premises,
        trivial_premises,
        aux_points,
        aux,
        numercial_checked_aux,
        trivial_aux,
        proof_steps,
    ) = proof_state.dep_graph.get_proof_steps(goals)
    points = sorted([p.pretty_name for p in points if isinstance(p, Point)])
    aux_points = sorted([p.pretty_name for p in aux_points])

    solution = "==========================\n"
    solution += "* From theorem premises:\n"
    solution += f"Points : {', '.join(points)}\n"
    for line in premises:
        solution += rediger(line) + "\n"
    for line in numercial_checked_premises:
        solution += rediger(line) + "\n"
    for line in trivial_premises:
        solution += rediger(line) + "\n"

    solution += "\n* Auxiliary Constructions:\n"
    solution += f"Points : {', '.join(aux_points)}\n"
    for line in aux:
        solution += rediger(line) + "\n"
    for line in numercial_checked_aux:
        solution += rediger(line) + "\n"
    for line in trivial_aux:
        solution += rediger(line) + "\n"

    solution += "\n* Proof steps:\n"
    for k, line in enumerate(proof_steps):
        if (
            NUMERICAL_CHECK not in line.reason
            and IN_PREMISES not in line
            and TRIVIAL not in line.reason
        ):
            solution += f"{k:03d}. {rediger(line)}\n"
    solution += "=========================="
    if out_file is None and print_output is True:
        print(solution)
    elif out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(solution)
        logging.info("Solution written to %s.", out_file)
    return solution
