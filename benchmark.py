import logging
from pathlib import Path
from typing import Optional

import os

import geosolver.graph as gh
import geosolver.problem as pr
import geosolver.pretty as pt
from geosolver.ddar import solve, get_proof_steps

DEFINITIONS = None  # contains definitions of construction actions
RULES = None  # contains rules of deductions


def main():
    global DEFINITIONS
    global RULES

    # definitions of terms used in our domain-specific language.
    DEFINITIONS = pr.Definition.from_txt_file("defs.txt", to_dict=True)
    # load inference rules used in DD.
    RULES = pr.Theorem.from_txt_file("rules.txt", to_dict=True)

    logging.basicConfig(level=logging.INFO)

    # load problems from the problems_file,
    problems = pr.Problem.from_txt_file(
        "problems_datasets/examples.txt", to_dict=True, translate=False
    )
    out_folder_path = Path("./ddar_results/")
    out_folder_path.mkdir(exist_ok=True)
    for problem_name, problem in problems.items():
        if problem_name != "orthocenter_aux":
            continue
        if problem_name in os.listdir(out_folder_path):
            logging.info(f"Skipping already solved problem {problem_name}.")
            continue
        logging.info(f"Starting problem {problem_name} with ddar only.")
        graph, _ = gh.Graph.build_problem(problem, DEFINITIONS)
        run_ddar(graph, problem, out_folder_path / problem_name)
        return


def run_ddar(graph: gh.Graph, problem: pr.Problem, out_folder: Optional[Path]) -> bool:
    """Run DD+AR.

    Args:
      g: gh.Graph object, containing the proof state.
      p: pr.Problem object, containing the problem statement.
      out_file: path to output file if solution is found.

    Returns:
      Boolean, whether DD+AR finishes successfully.
    """
    solve(graph, RULES, problem, max_level=1000)

    goal_args = graph.names2nodes(problem.goal.args)
    if not graph.check(problem.goal.name, goal_args):
        logging.info(f"DD+AR failed to solve the problem {problem.url}.")
        return False

    outfile = (
        out_folder / f"{problem.url}_proof_steps.txt"
        if out_folder is not None
        else None
    )
    write_solution(graph, problem, outfile)

    gh.nm.draw(
        graph.type2nodes[gh.Point],
        graph.type2nodes[gh.Line],
        graph.type2nodes[gh.Circle],
        graph.type2nodes[gh.Segment],
        save_to=str(out_folder / f"{problem.url}_proof_figure.png"),
        block=False,
    )
    return True


def write_solution(g: gh.Graph, p: pr.Problem, out_file: Optional[Path]) -> None:
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
        "r32": "(SSS)",
        "r33": "(SAS)",
        "r34": "(Similar Triangles 34)",
        "r35": "(Similar Triangles 35)",
        "r36": "(ASA)",
        "r37": "(ASA)",
        "r38": "(Similar Triangles 38)",
        "r39": "(Similar Triangles 39)",
        "r40": "(Congruent Triangles)",
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


def natural_language_statement(logical_statement: pr.Dependency) -> str:
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
    proof_step: pr.Dependency, refs: dict[tuple[str, ...], int], last_step: bool
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


if __name__ == "__main__":
    main()
