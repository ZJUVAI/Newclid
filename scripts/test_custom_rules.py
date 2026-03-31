from newclid.api import CSolver
import time

def main():
    problem = "a b = segment a b; c = midpoint c a b ? cong c a c b"
    problem_name = "test_custom"
    seed = 998244353

    custom_rules = [
        "r54|cong M A M B,coll M A B|midp M A B",
        "r56|midp M A B|coll M A B,cong M A M B",
    ]

    csolver = CSolver(problem=problem, problem_name=problem_name,
                      seed=seed, using_exp=True, using_log=True)

    print(f"Points: {len(csolver.points)}, Premises: {len(csolver.premises)}, Goals: {len(csolver.goals)}")

    t0 = time.time()
    solved = csolver.run(custom_rules=custom_rules)
    t_run = time.time() - t0

    print(f"Run time: {t_run:.4f}s")
    print(f"Solved: {solved}")

if __name__ == "__main__":
    main()
