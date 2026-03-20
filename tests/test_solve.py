from newclid import GeometricSolverBuilder, GeometricSolver
from newclid import proof_writing
from newclid.formulations.problem import ProblemJGEX

solver_builder = GeometricSolverBuilder(123)
solver_builder.load_problem_from_txt(
    'a b c = triangle; a1 = on_line b c; b1 = on_line a c; p = on_line a a1; q = on_line b b1, on_pline p a b; p1 = on_line p b1, eqangle3 p c a b c; q1 = on_line q a1, eqangle3 c q b c a; a2 = on_line a2 a a1, on_circum a2 a b c; b2 = on_line b2 b b1, on_circum b2 a b c ? cyclic p q p1 q1'
)


# We now obtain the GeometricSolver with the build method
try:
    solver: GeometricSolver = solver_builder.build(max_attempts=100)
except Exception as e:
    print("connot build solver:", e)
    exit(1)

# And run the GeometricSolver
success = solver.run()

if success:
    print("Successfuly solved the problem!")
else:
    print("Failed to solve the problem...")

proof_writing.write_proof_steps(solver.proof)

print(f"Run infos {solver.proof}")
