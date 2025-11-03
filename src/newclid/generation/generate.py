import logging
import os
import argparse
import json
import time
from datetime import timedelta
import ray
import re
from millify import millify
import signal
from contextlib import contextmanager

from newclid.configs import default_defs_path
from newclid.formulations.definition import DefinitionJGEX
from newclid.generation.clause_generation import CompoundClauseGen
from newclid.generation.summary import Summary, get_first_predicate
from newclid.generation.goal_filter import GeometryGoalFilter
from newclid.generation.problem_worker import GeometryProblemWorker


class TimeoutError(Exception):
    pass


@contextmanager
def time_limit(seconds):
    def handler(signum, frame):
        raise TimeoutError("Timed out")
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


class GeometryGenerator:
    def __init__(self, n_clauses=5, n_threads=1, output_dir="dataset", min_proof_steps=5, min_clauses_num=3, n_samples=100, timeout=3600, max_level=500):
        self.n_clauses = n_clauses
        self.min_proof_steps = min_proof_steps
        self.min_clauses_num = min_clauses_num
        self.n_samples = n_samples
        self.n_threads = n_threads
        self.timeout = timeout
        self.max_level = max_level
        self.output_dir = output_dir
        self.path_prefix = os.path.join(
            self.output_dir, f"geometry_clauses{self.n_clauses}_samples{millify(self.n_samples)}")
        self.write_buffer = []
        self.hashed_problems = set()
        self.filter = GeometryGoalFilter()
        self.defs = DefinitionJGEX.to_dict(
            DefinitionJGEX.parse_txt_file(default_defs_path()))
        self.clauses_generator = CompoundClauseGen(
            seed=int(time.time())+os.getpid(), defs=self.defs)

    def problem_hash_filter(self, data: list, key: str) -> list[str]:
        """Check if the input has already been written to the output file."""
        filtered_data = []
        for d in data:
            key_hash = hash(d[key])
            if key_hash not in self.hashed_problems:
                self.hashed_problems.add(key_hash)
                filtered_data.append(d)
        return filtered_data

    def write_data(self, all_data: list, force: bool = False):
        """Append a single JSON object to a .jsonl file."""
        self.write_buffer.extend(all_data)
        if len(self.write_buffer) > 10000 or force:
            filename = self.path_prefix + ".jsonl"
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'a', encoding='utf-8') as f:
                for data_item in self.write_buffer:
                    data_item['fl_problem'] = ''
                    json.dump(data_item, f, ensure_ascii=False)
                    f.write('\n')
            self.write_buffer.clear()

    def generate(self):
        def task_generator():
            for i in range(10**9):
                seed = int(time.time() * 1000) + i  # 唯一种子 = 时间戳 + 任务ID
                yield i, seed, self.n_clauses, self.max_level

        if not ray.is_initialized():
            ray.init(
                # local_mode=True,
                ignore_reinit_error=True,
                num_cpus=self.n_threads
            )
        task_iterator = task_generator()
        max_pending = int(self.n_threads * 1.5)
        summary_reporter = Summary(prefix=self.path_prefix)

        start_time = time.time()
        all_data_len = 0
        all_data_len_raw = 0
        pending_tasks = {}
        while all_data_len < self.n_samples:
            done, _ = ray.wait(list(pending_tasks.keys()),
                               num_returns=1, timeout=10)

            if done:
                task_id = done[0]
                task_success = True
                try:
                    data, summary = ray.get(task_id)

                    if 'error' in summary:
                        task_success = False
                except Exception as e:
                    logging.error(f"Task failed: {e}")
                    task_success = False

                del pending_tasks[task_id]

                if task_success:
                    all_data_len_raw += len(data)
                    data = self.problem_hash_filter(data, 'llm_input_renamed')
                    if data:
                        summary['n_samples'] = len(data)
                        summary['n_filtered_samples'] = summary['n_samples_raw'] - \
                            summary['n_samples']
                        summary['goals'] = [
                            re.search(r'\?\s*(\w+)', d['fl_problem']).group(1) for d in data]
                        summary['first_predicate'] = [
                            get_first_predicate(d['fl_problem']) for d in data]
                        summary['n_clauses'] = [d['n_clauses'] for d in data]
                        summary['n_proof_steps'] = [d['n_proof_steps']
                                                    for d in data]
                        self.write_data(data)
                        all_data_len += summary['n_samples']
                        summary_reporter.add(summary)
                        elapsed_time = time.time() - start_time
                        logging.info(
                            f"{millify(all_data_len)}/{millify(self.n_samples)} (+{len(data):3d}) in {elapsed_time:5.0f}s | "
                            f"Total: {summary['total_time']:3.0f}s = "
                            f"DDAR: {summary['runtime']:2.0f} + "
                            f"Chk: {summary['checkgoals_runtime']:2.0f} + "
                            f"Proc: {summary['process_goal_runtime']:3.0f} | "
                            f"Speed (raw): {all_data_len/elapsed_time:3.0f} ({all_data_len_raw/elapsed_time:3.0f}) samp/s | "
                            f"ETA: {timedelta(seconds=int(self.n_samples/all_data_len*elapsed_time - elapsed_time))}"
                        )
            for task, s_time in list(pending_tasks.items()):
                if time.time() - s_time > self.timeout:
                    print(f"⚠️ Task {task} timeout. Canceling")
                    ray.cancel(task, force=True)
                    del pending_tasks[task]

            while len(pending_tasks) < max_pending:
                task_args = next(task_iterator)
                pending_tasks[GeometryProblemWorker.ray_process_single_problem.remote(
                    task_args)] = time.time()

        # Cancel any remaining tasks
        for task in pending_tasks.keys():
            ray.cancel(task, force=True)
        ray.shutdown()

        self.write_data([], force=True)
        final_elapsed_time = time.time() - start_time
        summary_reporter.total_elapsed_time = final_elapsed_time
        summary_reporter.total_samples_generated = all_data_len
        logging.info(
            f"Generated {all_data_len} samples successfully in {final_elapsed_time:.2f}s.")
        summary_reporter.output_report()


def main():
    parser = argparse.ArgumentParser(
        description="Create problem fl - nl dataset")
    parser.add_argument("--n_clauses", required=False, type=int, default=15)
    parser.add_argument("--min_proof_steps",
                        required=False, type=int, default=3)
    parser.add_argument("--min_clauses_num",
                        required=False, type=int, default=2)
    parser.add_argument("--n_threads", required=False, type=int, default=10)
    parser.add_argument("--n_samples", required=False, type=int, default=10000)
    parser.add_argument("--dir", required=False, default="./datasets")
    parser.add_argument("--log_level", required=False, default="info",
                        choices=["debug", "info", "warning", "error"])
    parser.add_argument("--timeout", required=False, type=int, default=3600)
    parser.add_argument("--max_level", required=False, type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    generator = GeometryGenerator(
        n_clauses=args.n_clauses,
        n_threads=args.n_threads,
        output_dir=args.dir,
        min_proof_steps=args.min_proof_steps,
        min_clauses_num=args.min_clauses_num,
        n_samples=args.n_samples,
        timeout=args.timeout,
        max_level=args.max_level
    )

    generator.generate()


if __name__ == "__main__":
    main()
