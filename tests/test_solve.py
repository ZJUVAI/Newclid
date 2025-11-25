from newclid import GeometricSolverBuilder, GeometricSolver
from newclid import proof_writing
from newclid.formulations.problem import ProblemJGEX

solver_builder = GeometricSolverBuilder(123)
solver_builder.load_problem_from_txt(
    # 'a b c = triangle a b c; d = on_circum d a b c ? eqangle a c a d b c b d'
    'a b c = triangle a b c; d = foot d a b c; e = free e; f = foot f e b c; g = midpoint g a e; h = midpoint h d f ? cong g d g f'
)

problem = ProblemJGEX.from_text('a b c = triangle a b c; d = foot d a b c; e = free e; f = foot f e b c; g = midpoint g a e; h = midpoint h d f ? cong g d g f')

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
