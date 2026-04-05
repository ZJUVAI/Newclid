#!/usr/bin/env python3
"""
Unified profiling script for generation pipeline.
Compares Python vs C++ implementations and profiles the full pipeline with multi-threading.

Usage:
    # Compare Python vs C++ auxiliary implementations
    uv run python scripts/profile_generation_unified.py --mode=auxiliary --iterations=100

    # Profile full generation pipeline with 500 seeds, 10 threads
    uv run python scripts/profile_generation_unified.py --mode=pipeline --n_seeds=500 --n_threads=10

    # Profile both
    uv run python scripts/profile_generation_unified.py --mode=both --iterations=100 --n_seeds=500 --n_threads=10
"""

import argparse
import os
import sys
import time
from pathlib import Path
from collections import defaultdict
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Module-level function for multiprocessing (must be picklable)
def _process_seed_worker(seed_idx, n_clauses, aux_only):
    """Worker function for processing a single seed"""
    try:
        from newclid.generation.worker import ProblemWorker

        worker_args = (
            seed_idx,
            42 + seed_idx,  # seed
            n_clauses,
            500,  # max_level
            0,
            aux_only,
            True,
            2,  # max_auxiliary_points
            True,
            False,
            None,
        )
        data, summary = ProblemWorker._process_single_problem(worker_args)
        return seed_idx, data, summary
    except Exception as e:
        print(f"Seed {seed_idx} failed: {e}")
        return seed_idx, None, None


class AuxiliaryProfiler:
    """Profile auxiliary point finding (C++ implementation)"""

    def __init__(self, iterations=100):
        self.iterations = iterations
        self.min_time_threshold = 0.001  # Only report if avg time > 1ms

    def profile_auxiliary(self):
        """Profile C++ auxiliary implementation"""

        # Generate test data
        np.random.seed(42)
        num_points = 12
        point_names = [chr(ord('a') + i) for i in range(num_points)]
        coords = {
            name: (np.random.uniform(0, 10), np.random.uniform(0, 10))
            for name in point_names
        }

        print(f"\nTest Configuration:")
        print(f"  Points: {num_points}")
        print(f"  Iterations: {self.iterations}")
        print()

        # Test C++ version
        print("Testing C++ implementation...")
        try:
            from newclid.generation.auxiliary import (
                add_potential_points as add_potential_points_cpp,
            )

            t0 = time.time()
            for i in range(self.iterations):
                result_cpp = add_potential_points_cpp(point_names, coords, 2)
                if i == 0:
                    print(f"  First run: found {len(result_cpp)} potential points")

            cpp_time = (time.time() - t0) / self.iterations
            print(f"  Average time: {cpp_time * 1000:.3f}ms")
        except Exception as e:
            print(f"  Error: {e}")

        return


class PipelineProfiler:
    """Profile full generation pipeline (multi-threaded)"""

    def __init__(self, n_seeds=500, n_threads=10, n_clauses=10, aux_only=0):
        self.n_seeds = n_seeds
        self.n_threads = n_threads
        self.n_clauses = n_clauses
        self.aux_only = aux_only

    def profile_pipeline(self):
        """Profile full generation pipeline (multi-threaded)"""
        print("\n" + "=" * 80)
        print("GENERATION PIPELINE PROFILING (Multi-threaded)")
        print("=" * 80)

        from newclid.generation.worker import ProblemWorker
        from concurrent.futures import ProcessPoolExecutor, as_completed

        print(f"\nConfiguration:")
        print(f"  Seeds: {self.n_seeds}")
        print(f"  Threads: {self.n_threads}")
        print(f"  Clauses: {self.n_clauses}")
        print(f"  Aux-only filter: {self.aux_only}")
        print(f"  Implementation: C++")
        print()

        all_timings = []
        all_procgoal_timings = []

        print("Submitting tasks...\n")
        start_time = time.time()

        completed = 0
        with ProcessPoolExecutor(max_workers=self.n_threads) as executor:
            futures = {
                executor.submit(
                    _process_seed_worker, i, self.n_clauses, self.aux_only
                ): i
                for i in range(self.n_seeds)
            }

            for future in as_completed(futures):
                seed_idx, data, summary = future.result()

                if summary:
                    all_timings.append(summary)
                    if data:
                        # Collect timings from ALL samples, but deduplicate by group
                        # Each group of goals shares the same find_aux_time, etc.
                        seen_group_keys = set()
                        for sample in data:
                            if "_timings" in sample:
                                t = sample["_timings"]
                                # Use a combination of times and counts to identify a unique group call
                                group_id = (t.get("build_predicates_time"), t.get("build_solver_time"), t.get("run_solver_time"))
                                if group_id not in seen_group_keys:
                                    all_procgoal_timings.append(t)
                                    seen_group_keys.add(group_id)

                completed += 1
                if completed % max(1, self.n_seeds // 20) == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed
                    eta = (self.n_seeds - completed) / rate if rate > 0 else 0
                    print(
                        f"Progress: {completed}/{self.n_seeds} "
                        f"({completed / self.n_seeds * 100:.1f}%) "
                        f"- {rate:.1f} seeds/s - ETA: {eta:.0f}s"
                    )

        total_time = time.time() - start_time

        print()
        print(f"{'=' * 80}")
        print(f"Completed {len(all_timings)} seeds in {total_time:.2f}s")
        print(f"Throughput: {len(all_timings) / total_time:.2f} seeds/s")
        print(f"{'=' * 80}")

        # Print significant timings only
        self._print_significant_timings(all_timings, all_procgoal_timings)

        return all_timings, all_procgoal_timings

    def _print_significant_timings(self, all_timings, all_procgoal_timings):
        """Print total accumulated times with a hierarchical tree structure"""
        if not all_timings:
            return

        print()
        print(f"{'=' * 80}")
        print(f"HIERARCHICAL PERFORMANCE ANALYSIS ({len(all_timings)} seeds)")
        print(f"{'=' * 80}")

        # Main stages
        main_keys = [
            ("generation_time", "Problem Sampling"),
            ("build_solver_time", "Solver Building"),
            ("ddar_time", "DDAR Execution"),
            ("group_runtime", "Goal Grouping"),
            ("process_goal_runtime", "Goal Processing"),
        ]

        # Goal Processing sub-components (from _timings in samples)
        procgoal_keys = [
            ("run_solver_time", "Run Solver (DDAR)"),
            ("build_solver_time", "Build Solver"),
            ("build_predicates_time", "Build Predicates"),
        ]

        # Problem Sampling sub-components
        sampling_keys = [
            ("sampling", "Initial Clause Sampling"),
            ("prune", "Prune Chains"),
            ("add_auxiliary", "Add Auxiliary Points"),
            ("to_problem", "Convert to Problem"),
        ]

        def _filter_items(totals_dict, keys_list, grand_total):
            """Filter and sort items by total time, removing items < MIN_PCT."""
            result = []
            for key, label in keys_list:
                val = totals_dict.get(key, 0)
                pct = (val / grand_total * 100) if grand_total > 0 else 0
                result.append((key, label, val, pct))
            result.sort(key=lambda x: x[2], reverse=True)
            return result

        # Compute totals for main stages
        main_totals = {}
        for key, label in main_keys:
            main_totals[key] = sum(t.get(key, 0) for t in all_timings)

        # Compute totals for sub-components
        sub_totals = {}
        for key, label in procgoal_keys:
            sub_totals[key] = sum(t.get(key, 0) for t in all_procgoal_timings)

        # Compute totals for sampling sub-components
        sampling_totals = {}
        for key, label in sampling_keys:
            sampling_totals[key] = sum(
                t.get('sampling_timings', {}).get(key, 0) for t in all_timings
            )

        # Grand total
        total_time_values = [t["total_time"] for t in all_timings if "total_time" in t]
        grand_total = sum(total_time_values) if total_time_values else sum(main_totals.values())

        print(f"\nTotal Pipeline Wall-clock Time: {grand_total:.2f}s")
        print("\nTree Structure (Total Time & % of Grand Total):")
        print(f"Total ({grand_total:.2f}s)")

        # Filter and sort main stages
        main_items = _filter_items(main_totals, main_keys, grand_total)
        for i, (key, label, total, pct) in enumerate(main_items):
            is_last = (i == len(main_items) - 1)
            connector = "└──" if is_last else "├──"
            print(f"{connector} {label:25s}: {total:8.2f}s  ({pct:5.1f}%)")

            # Prefix for children: "│   " if parent has siblings after, "    " if last
            child_prefix = "    " if is_last else "│   "

            # Goal Processing children
            if key == "process_goal_runtime":
                sub_items = _filter_items(sub_totals, procgoal_keys, grand_total)
                for j, (sk, sl, sv, sp) in enumerate(sub_items):
                    sj_last = (j == len(sub_items) - 1)
                    sc = child_prefix + ("└──" if sj_last else "├──")
                    pp = (sv / total * 100) if total > 0 else 0
                    print(f"{sc} {sl:21s}: {sv:8.2f}s  ({sp:5.1f}% of total, {pp:4.1f}% of parent)")

            # Problem Sampling children
            elif key == "generation_time":
                samp_items = _filter_items(sampling_totals, sampling_keys, grand_total)
                for j, (sk, sl, sv, sp) in enumerate(samp_items):
                    sj_last = (j == len(samp_items) - 1)
                    sc = child_prefix + ("└──" if sj_last else "├──")
                    pp = (sv / total * 100) if total > 0 else 0
                    print(f"{sc} {sl:29s}: {sv:8.2f}s  ({sp:5.1f}% of total, {pp:4.1f}% of parent)")


        # Seed and sample statistics
        print()
        print(f"{'=' * 80}")
        print("SEED & SAMPLE STATISTICS")
        print(f"{'=' * 80}")
        n_samples_raw_list = [t.get("n_samples_raw", 0) for t in all_timings]
        total_samples_generated = sum(n_samples_raw_list)
        seeds_with_data = sum(1 for n in n_samples_raw_list if n > 0)
        print(f"Total seeds processed: {len(all_timings)}")
        print(
            f"Seeds with generated samples: {seeds_with_data} "
            f"({seeds_with_data / len(all_timings) * 100:.1f}%)"
        )
        print(f"Total samples generated: {total_samples_generated}")
        if len(all_timings) > 0:
            print(f"Avg samples per seed: {total_samples_generated / len(all_timings):.2f}")
        if seeds_with_data > 0:
            print(
                f"Avg samples per seed (with data): {total_samples_generated / seeds_with_data:.2f}"
            )




def main():
    parser = argparse.ArgumentParser(
        description="Unified profiling for GenesisGeo generation pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["auxiliary", "pipeline", "both"],
        default="both",
        help="Profiling mode",
    )
    parser.add_argument(
        "--iterations", type=int, default=100, help="Iterations for auxiliary profiling"
    )
    parser.add_argument(
        "--n_seeds", type=int, default=500, help="Number of seeds for pipeline profiling"
    )
    parser.add_argument(
        "--n_threads", type=int, default=10, help="Number of threads for pipeline profiling"
    )
    parser.add_argument(
        "--n_clauses", type=int, default=10, help="Number of clauses per problem"
    )
    parser.add_argument(
        "--aux_only", type=int, default=0, help="Auxiliary filter mode (0, 1, or 2)"
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("GenesisGeo Generation Pipeline Profiler")
    print("=" * 80)

    if args.mode in ["auxiliary", "both"]:
        aux_profiler = AuxiliaryProfiler(iterations=args.iterations)
        aux_profiler.profile_auxiliary()

    if args.mode in ["pipeline", "both"]:
        pipeline_profiler = PipelineProfiler(
            n_seeds=args.n_seeds,
            n_threads=args.n_threads,
            n_clauses=args.n_clauses,
            aux_only=args.aux_only,
        )
        pipeline_profiler.profile_pipeline()

    print("\n" + "=" * 80)
    print("Profiling Complete")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
