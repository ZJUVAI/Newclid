from newclid.api import CSolver
import time


def main():
    problem = "a b c = triangle a b c; d = eqangle3 d a b c a b; o1 = circumcenter o1 a b d; o2 = circumcenter o2 a b c; p = on_line p a d, on_line p b c ? cyclic a b c d"
    problem_name = "test"
    seed = 998244353

    csolver = CSolver(problem=problem, problem_name=problem_name,
                           seed=seed, using_exp=True, using_log=True, engine="weak")

    t0 = time.time()
    solved = csolver.run()
    t_run = time.time() - t0
    print(f"DDAR run time: {t_run:.4f}s")
    print(f"Solved: {solved}")

    print(csolver.solver.write_proof_steps())


if __name__ == "__main__":
    main()