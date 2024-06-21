from geosolver import GeometricSolverBuilder, GeometricSolver

solver_builder = GeometricSolverBuilder()
solver_builder.load_problem_from_file(
    "problems_datasets/examples.txt:concatenating_ratios"
)

# We now obtain the GeometricSolver with the build method
solver: GeometricSolver = solver_builder.build()

# And run the GeometricSolver
success = solver.run()

if success:
    print("Successfuly solved the problem!")
else:
    print("Failed to solve the problem...")

print(f"Run infos {solver.run_infos}")
