import logging
import os
import argparse
import json
import time
from datetime import timedelta

import ray
from millify import millify

from newclid.generation.configuration_worker import GeometryConfigurationWorker


class GeometryConfigurationGenerator:
    """Generator for geometry configurations (configuration + points_info)."""

    def __init__(
        self,
        n_clauses: int = 5,
        n_threads: int = 1,
        output_dir: str = "dataset",
        n_samples: int = 100,
        timeout: int = 3600,
    ):
        self.n_clauses = n_clauses
        self.n_samples = n_samples
        self.n_threads = n_threads
        self.timeout = timeout
        self.output_dir = output_dir
        self.path_prefix = os.path.join(
            self.output_dir, f"configuration_clauses{self.n_clauses}_samples{millify(self.n_samples)}"
        )
        self.write_buffer = []
        self.hashed_configurations = set()

    def configuration_hash_filter(self, data, key: str):
        filtered = []
        for d in data:
            key_hash = hash(d[key])
            if key_hash not in self.hashed_configurations:
                self.hashed_configurations.add(key_hash)
                filtered.append(d)
        return filtered

    def write_data(self, all_data, force: bool = False):
        self.write_buffer.extend(all_data)
        if len(self.write_buffer) > 10000 or force:
            filename = self.path_prefix + ".jsonl"
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, "a", encoding="utf-8") as f:
                for idx, data_item in enumerate(self.write_buffer, start=len(self.hashed_configurations) - len(self.write_buffer) + 1):
                    # config_id is assigned by write order within this file
                    data_item["config_id"] = idx
                    json.dump(data_item, f, ensure_ascii=False)
                    f.write("\n")
            self.write_buffer.clear()

    def generate(self):
        def task_generator():
            for i in range(10**9):
                seed = 42 + i
                yield i, seed, self.n_clauses

        if not ray.is_initialized():
            ray.init(
                ignore_reinit_error=True,
                num_cpus=self.n_threads,
            )

        task_iterator = task_generator()
        max_pending = int(self.n_threads * 1.5)

        start_time = time.time()
        all_data_len = 0
        pending_tasks = {}
        config_counter = 0

        while all_data_len < self.n_samples:
            done, _ = ray.wait(list(pending_tasks.keys()), num_returns=1, timeout=10)

            if done:
                task_id = done[0]
                task_success = True
                try:
                    data, summary = ray.get(task_id)
                    if "error" in summary:
                        task_success = False
                except Exception as e:
                    logging.error(f"Task failed: {e}")
                    task_success = False

                del pending_tasks[task_id]

                if task_success and data:
                    data = self.configuration_hash_filter(data, "configuration")
                    if data:
                        # update global count before truncating to remaining quota
                        remaining = self.n_samples - all_data_len
                        if len(data) > remaining:
                            data = data[:remaining]
                        all_data_len += len(data)
                        config_counter += len(data)
                        self.write_buffer.extend(data)
                        elapsed_time = time.time() - start_time
                        logging.info(
                            f"{millify(all_data_len)}/{millify(self.n_samples)} (+{len(data):3d}) in {elapsed_time:5.0f}s | "
                            f"Speed: {all_data_len/elapsed_time:3.0f} cfg/s | "
                            f"ETA: {timedelta(seconds=int(self.n_samples/all_data_len*elapsed_time - elapsed_time))}"
                        )

            # cancel timeout tasks
            for task, s_time in list(pending_tasks.items()):
                if time.time() - s_time > self.timeout:
                    print(f"⚠️ Task {task} timeout. Canceling")
                    ray.cancel(task, force=True)
                    del pending_tasks[task]

            while len(pending_tasks) < max_pending and all_data_len < self.n_samples:
                task_args = next(task_iterator)
                pending_tasks[GeometryConfigurationWorker.ray_process_single_configuration.remote(task_args)] = time.time()

        # Cancel any remaining tasks
        for task in pending_tasks.keys():
            ray.cancel(task, force=True)
        ray.shutdown()

        self.write_data([], force=True)
        final_elapsed_time = time.time() - start_time
        logging.info(
            f"Generated {all_data_len} configurations successfully in {final_elapsed_time:.2f}s."
        )


def main():
    parser = argparse.ArgumentParser(description="Create geometry configuration dataset")
    parser.add_argument("--n_clauses", required=False, type=int, default=15)
    parser.add_argument("--n_threads", required=False, type=int, default=10)
    parser.add_argument("--n_samples", required=False, type=int, default=10000)
    parser.add_argument("--dir", required=False, default="./datasets")
    parser.add_argument(
        "--log_level", required=False, default="info", choices=["debug", "info", "warning", "error"]
    )
    parser.add_argument("--timeout", required=False, type=int, default=3600)
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    generator = GeometryConfigurationGenerator(
        n_clauses=args.n_clauses,
        n_threads=args.n_threads,
        output_dir=args.dir,
        n_samples=args.n_samples,
        timeout=args.timeout,
    )

    generator.generate()


if __name__ == "__main__":
    main()
