import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "../../.."))

from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.formulations.problem import ProblemJGEX
from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder
from newclid.statement import Statement
from tests.fixtures import build_until_works

def find_essential_clauses(
    dep_graph: DependencyGraph,
    pr: ProblemJGEX,
    goals: list[Statement]
) -> str:
    statements: list[str] = []
    essential_clauses, essential_aux_clauses = dep_graph.get_essential_clauses(goals)
    for clause in pr.constructions:
        if str(clause) in essential_clauses or str(clause) in essential_aux_clauses:
            statements.append(str(clause))
    return '; '.join(statements) + ' ? ' + '; '.join([' '.join(goal) for goal in pr.goals])

if __name__ == '__main__':
    # text = 'a b c = triangle a b c; d = on_tline d b a c, on_tline d c a b; e = on_line e a c, on_line e b d ? perp a d b c'
    text = 'A B C D = trapezoid A B C D; E = on_tline E C B A, eqdistance E A C D; F G = trisegment F G A D; H I J = triangle H I J; K = on_line K B H, angle_bisector K A J I; L = on_bline L J D; M = on_bline M C B, eqangle3 M A F G K E; N = on_circle N G F, on_circle N E F; O = intersection_cc O A F K; P = on_pline P I K N, eqdistance P H F M; Q R = square F G Q R; S T U = r_triangle S T U; V = on_line V P G, on_bline V N O ? eqangle A D S U G Q S T'

    builder = GeometricSolverBuilder(seed=998244353).load_problem_from_txt(text).with_deductive_agent(DDARN())
    solver = build_until_works(builder=builder)

    success = solver.run()
    print(f"Success: {success}")

    clauses, aux_clauses = solver.proof.dep_graph.get_essential_clauses(solver.goals)
    print('[essential clauses - main] ', clauses)
    print('[essential clauses - aux] ', aux_clauses)

    print('[output] ', find_essential_clauses(solver.proof.dep_graph, builder.problemJGEX, solver.goals))