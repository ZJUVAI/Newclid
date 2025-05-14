"""Helper functions to write proofs in a natural language."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from newclid.dependencies.dependency import IN_PREMISES, NUMERICAL_CHECK, Dependency
from newclid.statement import Statement
from newclid.dependencies.symbols import Point

if TYPE_CHECKING:
    from newclid.proof import ProofState

def get_structured_proof(proof_state: "ProofState") -> list[Dependency]:
    id: dict[Statement, str] = {}
    goals = [goal for goal in proof_state.goals if goal.check()]
    def rediger(dep: Dependency) -> str:
        for statement in (dep.statement,) + dep.why:
            if statement not in id:
                id[statement] = f"{len(id):03d}"
        return f"{', '.join(premise.to_str() + ' [' + id[premise] + ']' for premise in dep.why)} ({dep.reason})=> {dep.statement.to_str()} [{id[dep.statement]}]"
    (
        points,
        premises,
        numercial_checked_premises,
        aux_points,
        aux,
        numercial_checked_aux,
        proof_steps,
    ) = proof_state.dep_graph.get_proof_steps(goals)
    points = sorted([p.pretty_name for p in points])
    aux_points = sorted([p.pretty_name for p in aux_points])

    solution = "<premises>\n"
    for line in premises:
        solution += rediger(line) + "\n"
    for line in numercial_checked_premises:
        solution += rediger(line) + "\n"

    for line in aux:
        solution += rediger(line) + "\n"
    for line in numercial_checked_aux:
        solution += rediger(line) + "\n"
    solution += "</premises>\n"

    solution += "<proof>\n"
    for k, line in enumerate(proof_steps):
        if NUMERICAL_CHECK not in line.reason and IN_PREMISES not in line:
            solution += f"{rediger(line)}\n"
    solution += "</proof>\n"

    return solution


def return_proof_steps(proof_state: "ProofState") -> list[Dependency]:
    id: dict[Statement, str] = {}
    goals = [goal for goal in proof_state.goals if goal.check()]
    for k, goal in enumerate(goals):
        id[goal] = f"g{k}"

    def rediger(dep: Dependency) -> str:
        for statement in (dep.statement,) + dep.why:
            if statement not in id:
                id[statement] = str(len(id) - len(goals))
        return f"{', '.join(premise.pretty() + ' [' + id[premise] + ']' for premise in dep.why)} ({dep.reason})=> {dep.statement.pretty()} [{id[dep.statement]}]"

    # solution = "==========================\n"
    # solution += "* From problem construction:\n"
    # solution += f"Points : {', '.join(p.pretty_name for p in proof_state.symbols_graph.nodes_of_type(Point))}\n"
    # proof_deps = proof_state.dep_graph.proof_deps(goals)
    # premises: list[Dependency] = []
    # numercial_checked: list[Dependency] = []
    # proof_steps: list[Dependency] = []
    # for line in proof_deps:
    #     if IN_PREMISES == line.reason:
    #         premises.append(line)
    #     elif NUMERICAL_CHECK == line.reason:
    #         numercial_checked.append(line)
    #     else:
    #         proof_steps.append(line)
    # for line in premises:
    #     solution += rediger(line) + "\n"
    # for line in numercial_checked:
    #     solution += rediger(line) + "\n"

    (
        points,
        premises,
        numercial_checked_premises,
        aux_points,
        aux,
        numercial_checked_aux,
        proof_steps,
    ) = proof_state.dep_graph.get_proof_steps(goals)
    points = sorted([p.pretty_name for p in points])
    aux_points = sorted([p.pretty_name for p in aux_points])

    solution = "==========================\n"
    solution += "* From theorem premises:\n"
    solution += f"Points : {', '.join(points)}\n"
    for line in premises:
        solution += rediger(line) + "\n"
    for line in numercial_checked_premises:
        solution += rediger(line) + "\n"

    solution += "\n* Auxiliary Constructions:\n"
    solution += f"Points : {', '.join(aux_points)}\n"
    for line in aux:
        solution += rediger(line) + "\n"
    for line in numercial_checked_aux:
        solution += rediger(line) + "\n"

    solution += "\n* Proof steps:\n"
    for k, line in enumerate(proof_steps):
        if NUMERICAL_CHECK not in line.reason and IN_PREMISES not in line:
            solution += f"{k:03d}. {rediger(line)}\n"
    solution += "=========================="

    return solution


def write_proof_steps(proof_state: "ProofState", out_file: Optional[Path]) -> None:
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

    # solution = "==========================\n"
    # solution += "* From problem construction:\n"
    # solution += f"Points : {', '.join(p.pretty_name for p in proof_state.symbols_graph.nodes_of_type(Point))}\n"
    # proof_deps = proof_state.dep_graph.proof_deps(goals)
    # premises: list[Dependency] = []
    # numercial_checked: list[Dependency] = []
    # proof_steps: list[Dependency] = []
    # for line in proof_deps:
    #     if IN_PREMISES == line.reason:
    #         premises.append(line)
    #     elif NUMERICAL_CHECK == line.reason:
    #         numercial_checked.append(line)
    #     else:
    #         proof_steps.append(line)
    # for line in premises:
    #     solution += rediger(line) + "\n"
    # for line in numercial_checked:
    #     solution += rediger(line) + "\n"

    (
        points,
        premises,
        numercial_checked_premises,
        aux_points,
        aux,
        numercial_checked_aux,
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

    solution += "\n* Auxiliary Constructions:\n"
    solution += f"Points : {', '.join(aux_points)}\n"
    for line in aux:
        solution += rediger(line) + "\n"
    for line in numercial_checked_aux:
        solution += rediger(line) + "\n"

    solution += "\n* Proof steps:\n"
    for k, line in enumerate(proof_steps):
        if NUMERICAL_CHECK not in line.reason and IN_PREMISES not in line:
            solution += f"{k:03d}. {rediger(line)}\n"
    solution += "=========================="
    if out_file is None:
        print(solution)
    else:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(solution)
        logging.info("Solution written to %s.", out_file)
    return solution
