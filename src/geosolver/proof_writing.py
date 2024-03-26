"""Helper functions to write proofs in a natural language."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import geosolver.pretty as pt
import geosolver.trace_back as trace_back

from geosolver.problem import Clause, Dependency, Problem

if TYPE_CHECKING:
    from geosolver.proof_graph import ProofGraph


def get_proof_steps(
    g: "ProofGraph", goal: Clause, merge_trivials: bool = False
) -> tuple[
    list[Dependency],
    list[Dependency],
    list[tuple[list[Dependency], list[Dependency]]],
    dict[tuple[str, ...], int],
]:
    """Extract proof steps from the built DAG."""
    goal_args = g.symbols_graph.names2nodes(goal.args)
    query = Dependency(goal.name, goal_args, None, None)

    setup, aux, log, setup_points = trace_back.get_logs(
        query, g, merge_trivials=merge_trivials
    )

    refs = {}
    setup = trace_back.point_log(setup, refs, set())
    aux = trace_back.point_log(aux, refs, setup_points)

    setup = [(prems, [tuple(p)]) for p, prems in setup]
    aux = [(prems, [tuple(p)]) for p, prems in aux]

    return setup, aux, log, refs


def natural_language_statement(logical_statement: Dependency) -> str:
    """Convert logical_statement to natural language.

    Args:
      logical_statement: pr.Dependency with .name and .args

    Returns:
      a string of (pseudo) natural language of the predicate for human reader.
    """
    names = [a.name.upper() for a in logical_statement.args]
    names = [(n[0] + "_" + n[1:]) if len(n) > 1 else n for n in names]
    return pt.pretty_nl(logical_statement.name, names)


def proof_step_string(
    proof_step: Dependency, refs: dict[tuple[str, ...], int], last_step: bool
) -> str:
    """Translate proof to natural language.

    Args:
      proof_step: pr.Dependency with .name and .args
      refs: dict(hash: int) to keep track of derived predicates
      last_step: boolean to keep track whether this is the last step.

    Returns:
      a string of (pseudo) natural language of the proof step for human reader.
    """
    premises, [conclusion] = proof_step

    premises_nl = " & ".join(
        [
            natural_language_statement(p) + " [{:02}]".format(refs[p.hashed()])
            for p in premises
        ]
    )

    if not premises:
        premises_nl = "similarly"

    refs[conclusion.hashed()] = len(refs)

    conclusion_nl = natural_language_statement(conclusion)
    if not last_step:
        conclusion_nl += " [{:02}]".format(refs[conclusion.hashed()])

    return f"{premises_nl} \u21d2 {conclusion_nl}"


def write_solution(g: "ProofGraph", p: Problem, out_file: Optional[Path]) -> None:
    """Output the solution to out_file.

    Args:
      g: gh.Graph object, containing the proof state.
      p: pr.Problem object, containing the theorem.
      out_file: file to write to, empty string to skip writing to file.
    """
    setup, aux, proof_steps, refs = get_proof_steps(g, p.goal, merge_trivials=False)

    solution = "\n=========================="
    solution += "\n * From theorem premises:\n"
    premises_nl = []
    for premises, [points] in setup:
        solution += " ".join([p.name.upper() for p in points]) + " "
        if not premises:
            continue
        premises_nl += [
            natural_language_statement(p) + " [{:02}]".format(refs[p.hashed()])
            for p in premises
        ]
    solution += ": Points\n" + "\n".join(premises_nl)

    solution += "\n\n * Auxiliary Constructions:\n"
    aux_premises_nl = []
    for premises, [points] in aux:
        solution += " ".join([p.name.upper() for p in points]) + " "
        aux_premises_nl += [
            natural_language_statement(p) + " [{:02}]".format(refs[p.hashed()])
            for p in premises
        ]
    solution += ": Points\n" + "\n".join(aux_premises_nl)

    # some special case where the deduction rule has a well known name.
    r2name = {
        "r32": "(SSS 32)",
        "r33": "(SAS 33)",
        "r34": "(Similar Triangles 34)",
        "r35": "(Similar Triangles 35)",
        "r36": "(ASA 36)",
        "r37": "(ASA 37)",
        "r38": "(Similar Triangles 38)",
        "r39": "(Similar Triangles 39)",
        "r40": "(Congruent Triangles 40)",
        "a00": "(Distance chase)",
        "a01": "(Ratio chase)",
        "a02": "(Angle chase)",
    }

    solution += "\n\n * Proof steps:\n"
    for i, step in enumerate(proof_steps):
        _, [con] = step
        nl = proof_step_string(step, refs, last_step=i == len(proof_steps) - 1)
        rule_name = r2name.get(con.rule_name, f"({con.rule_name})")
        nl = nl.replace("\u21d2", f"{rule_name}\u21d2 ")
        solution += "{:03}. ".format(i + 1) + nl + "\n"

    solution += "==========================\n"
    logging.info(solution)
    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(solution)
        logging.info("Solution written to %s.", out_file)
