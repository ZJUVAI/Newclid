"""Helper functions to write proofs in a natural language."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from geosolver.dependency.dependency import BY_CONSTRUCTION

if TYPE_CHECKING:
    from geosolver.proof import Proof


def write_solution(proof: "Proof", out_file: Optional[Path]) -> None:
    """Output the solution to out_file.

    Args:
      proof: Proof state.
      problem: Containing the problem definition and theorems.
      out_file: file to write to, empty string to skip writing to file.
    """
    solution = "==========================\n"
    solution += "* From problem construction:\n"
    proof_lines = proof.dep_graph.proof_lines(proof.goals)
    for line in proof_lines:
        if BY_CONSTRUCTION in line:
            solution += line + "\n"
    solution += "* Proof steps:\n"
    for line in proof_lines:
        if BY_CONSTRUCTION not in line:
            solution += line + "\n"
    solution += "\n=========================="
    logging.info(solution)
    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(solution)
        logging.info("Solution written to %s.", out_file)
