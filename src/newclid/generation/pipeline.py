import logging
import os
import shutil
import argparse
import json
import time
from datetime import timedelta
import ray
import re
from millify import millify
import uuid

from newclid.configs import default_defs_path
from newclid.formulations.definition import DefinitionJGEX
from newclid.generation.statistics import Statistics, get_first_predicate
from newclid.generation.filter import GoalFilter
from newclid.generation.worker import ProblemWorker
from newclid.generation.writer import Writer

# logging.basicConfig(level=logging.DEBUG, force=True)

MACHINE_BASE_SEED = 42


class ProblemPipeline:
    def __init__(
        self,
        n_clauses=5,
        n_threads=1,
        output_dir="dataset",
        n_samples=100,
        timeout=3600,
        max_level=500,
        img=0,
        aux_only=0,
        clear=False,
        add_auxiliary=True,
        max_auxiliary_points=2,
        prune=True,
        remove_coords=False,
        construction_config=None,
        use_cache=False,
    ):
        self.n_clauses = n_clauses
        self.n_samples = n_samples
        self.n_threads = n_threads
        self.timeout = timeout
        self.max_level = max_level
        self.max_auxiliary_points = max_auxiliary_points
        self.output_dir = output_dir
        self.path_prefix = os.path.join(
            self.output_dir, f"geometry_clauses{self.n_clauses}_samples{millify(self.n_samples)}")
        self.hashed_problems = set()
        self.filter = GoalFilter()
        self.defs = DefinitionJGEX.to_dict(
            DefinitionJGEX.parse_txt_file(default_defs_path()))
        self.img = img
        self.aux_only = aux_only
        self.clear = clear
        self.add_auxiliary = add_auxiliary
        self.prune = prune
        self.remove_coords = remove_coords
        self.construction_config = construction_config
        self.use_cache = use_cache
        self.seed_cache = {}
        self.cache_file = os.path.join(self.output_dir, "seed_cache.jsonl")

        if self.use_cache and os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        key = (entry["seed"], entry["n_clauses"])
                        self.seed_cache[key] = entry
            logging.info("Loaded %d entries from cache", len(self.seed_cache))

        # Serialize defs for Ray remote tasks
        defs_data = {k: v._asdict() for k, v in self.defs.items()}

        # Generate unique session ID
        session_id = uuid.uuid4().hex[:16]
        logging.info(f"Session ID: {session_id}")
        logging.info(
            "Construction config: %s",
            "external" if self.construction_config is not None else "default",
        )

        # Initialize writer
        self.writer = Writer(
            output_dir=self.output_dir,
            path_prefix=self.path_prefix,
            img_mode=self.img,
            defs_data=defs_data,
            session_id=session_id,
        )

    def problem_hash_filter(self, data: list, key: str) -> list[str]:
        """Check if the input has already been written to the output file."""
        filtered_data = []
        for d in data:
            key_hash = hash(d[key])
            if key_hash not in self.hashed_problems:
                self.hashed_problems.add(key_hash)
                filtered_data.append(d)
        return filtered_data

    def generate(self):
        if self.clear:
            filename = self.path_prefix + ".jsonl"
            imgs_dir = os.path.join(self.output_dir, "imgs")
            imgs_png_dir = os.path.join(self.output_dir, "imgs_png")
            if os.path.exists(filename):
                os.remove(filename)
            if os.path.exists(imgs_dir):
                shutil.rmtree(imgs_dir)
            if os.path.exists(imgs_png_dir):
                shutil.rmtree(imgs_png_dir)

        def task_generator():
            for i in range(10**9):
                seed = MACHINE_BASE_SEED + i
                fl_statement = None

                if self.use_cache:
                    cache_key = (seed, self.n_clauses)
                    if cache_key in self.seed_cache:
                        entry = self.seed_cache[cache_key]
                        if not entry.get("has_real_aux", False):
                            continue
                        fl_statement = entry.get("fl_statement")

                yield (
                    i,
                    seed,
                    self.n_clauses,
                    self.max_level,
                    self.img,
                    self.aux_only,
                    self.add_auxiliary,
                    self.max_auxiliary_points,
                    self.prune,
                    self.remove_coords,
                    self.construction_config,
                    fl_statement,
                )

        if not ray.is_initialized():
            ray.init(
                ignore_reinit_error=True,
                num_cpus=self.n_threads
            )
        task_iterator = task_generator()
        max_pending = int(self.n_threads * 1.5)
        summary_reporter = Statistics(prefix=self.path_prefix)

        start_time = time.time()
        all_data_len = self.writer.data_count
        all_data_len_raw = self.writer.data_count
        pending_tasks = {}
        last_logged_written = self.writer.written_count

        while self.writer.written_count < self.n_samples:
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

                _, seed = pending_tasks.pop(task_id)

                if task_success:
                    if self.use_cache:
                        has_real_aux = summary.get("has_real_aux", False) if summary else False
                        cache_entry = {
                            "seed": seed,
                            "n_clauses": self.n_clauses,
                            "has_real_aux": has_real_aux,
                            "fl_statement": summary.get("fl_statement") if has_real_aux else None,
                        }
                        cache_key = (seed, self.n_clauses)
                        if cache_key not in self.seed_cache:
                            self.seed_cache[cache_key] = cache_entry
                            os.makedirs(self.output_dir, exist_ok=True)
                            with open(self.cache_file, "a", encoding="utf-8") as f:
                                f.write(json.dumps(cache_entry) + "\n")

                    all_data_len_raw += len(data)
                    data = self.problem_hash_filter(data, 'llm_input_renamed')
                    if data:
                        summary['n_samples'] = len(data)
                        summary['n_filtered_samples'] = summary['n_samples_raw'] - summary['n_samples']
                        summary['goals'] = [re.search(r'\?\s*(\w+)', d['fl_problem']).group(1) for d in data]
                        summary['first_predicate'] = [get_first_predicate(d['fl_problem']) for d in data]
                        summary['n_premises'] = [d['n_premises'] for d in data]
                        summary['n_proof_steps'] = [d['n_proof_steps']
                                                    for d in data]
                        self.writer.write_data(data)
                        all_data_len += summary['n_samples']
                        summary_reporter.add(summary)

                        # Log progress when new data is written to file
                        if self.writer.written_count > last_logged_written:
                            elapsed_time = time.time() - start_time
                            pending_draw = len(self.writer.pending_draw_tasks)
                            pending_write = len(self.writer.pending_write_data)
                            logging.info(
                                f"{millify(self.writer.written_count)}/{millify(self.n_samples)} "
                                f"(+{self.writer.written_count - last_logged_written:3d}, pending: {pending_draw}+{pending_write}) "
                                f"in {elapsed_time:5.0f}s | "
                                f"Total: {summary['total_time']:3.0f}s = "
                                f"Gen: {summary['generation_time']:2.0f} + "
                                f"DDAR: {summary['runtime']:2.0f} + "
                                f"Proc: {summary['process_goal_runtime']:3.0f} | "
                                f"Speed: {self.writer.written_count/elapsed_time:3.0f} samp/s | "
                                f"ETA: {timedelta(seconds=int(self.n_samples/max(1,self.writer.written_count)*elapsed_time - elapsed_time))}"
                            )
                            last_logged_written = self.writer.written_count
            for task, (s_time, _) in list(pending_tasks.items()):
                if time.time() - s_time > self.timeout:
                    print(f"⚠️ Task {task} timeout. Canceling")
                    ray.cancel(task, force=True)
                    del pending_tasks[task]

            while len(pending_tasks) < max_pending:
                task_args = next(task_iterator)
                seed = task_args[1]
                pending_tasks[ProblemWorker.ray_process_single_problem.remote(task_args)] = (
                    time.time(),
                    seed,
                )

        # Cancel any remaining problem generation tasks
        for task in pending_tasks.keys():
            ray.cancel(task, force=True)

        # Wait for all pending draw tasks to complete before shutdown
        self.writer.write_data([], force=True)

        ray.shutdown()

        final_elapsed_time = time.time() - start_time
        summary_reporter.total_elapsed_time = final_elapsed_time
        summary_reporter.total_samples_generated = self.writer.written_count
        logging.info(
            f"Generated {self.writer.written_count} samples successfully in {final_elapsed_time:.2f}s.")
        summary_reporter.output_report()


def load_construction_config(config_path: str | None) -> dict | None:
    """Load optional construction config JSON from disk."""
    if not config_path:
        return None
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise ValueError("Construction config JSON must contain a top-level object.")
    return config


def main():
    parser = argparse.ArgumentParser(
        description="Create problem fl - nl dataset")
    # General parameters
    parser.add_argument("--log_level", required=False, default="info",
                        choices=["debug", "info", "warning", "error"],
                        help="Logging level")
    parser.add_argument("--n_clauses", required=False, type=int, default=15,
                        help="Number of clauses in generated problems")
    parser.add_argument("--n_samples", required=False, type=int, default=10000,
                        help="Number of samples to generate")
    parser.add_argument("--n_threads", required=False, type=int, default=10,
                        help="Number of parallel worker threads")
    parser.add_argument("--timeout", required=False, type=int, default=3600,
                        help="Timeout for individual tasks (seconds)")
    parser.add_argument("--max_level", required=False, type=int, default=500,
                        help="Maximum DDAR search depth")
    parser.add_argument("--construction_config", required=False, default=None,
                        help="Optional JSON file defining construction sets and sampler steps",)
    parser.add_argument("--use_cache", required=False, action="store_true", default=False,
                        help="Use seed cache to skip seeds without real auxiliary points")
    # Auxiliary point parameters
    parser.add_argument("--add_auxiliary", action=argparse.BooleanOptionalAction, default=True,
                        help="Add auxiliary points (default: enabled)")
    parser.add_argument("--max_auxiliary_points", required=False, type=int, default=2,
                        help="Maximum number of auxiliary points per problem")
    parser.add_argument("--aux_only", required=False, type=int, default=0, choices=[0, 1, 2],
                        help="Auxiliary data filter: " \
                            "0=all data, " \
                            "1=include data without aux with 0.1 probability, " \
                            "2=only data with aux")
    # Output parameters
    parser.add_argument("--dir", required=False, default="./datasets", help="Output directory")
    parser.add_argument("--img", required=False, type=int, default=0, choices=[0, 1, 2, 3],
                        help="Image generation mode: " \
                            "0=no images, " \
                            "1=with annotations only, " \
                            "2=without annotations only, " \
                            "3=both")
    parser.add_argument("--prune", action=argparse.BooleanOptionalAction, default=True,
                        help="Prune clauses to preserve only deepest clause chain (default: enabled)")
    parser.add_argument("--remove_coords", action="store_true", default=False,
                        help="Remove coordinate information from final clause output")
    parser.add_argument("--clear", action="store_true", default=False,
                        help="Clear old dataset files before generation")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()), force=True)
    construction_config = load_construction_config(args.construction_config)
    generator = ProblemPipeline(
        n_clauses=args.n_clauses,
        n_threads=args.n_threads,
        output_dir=args.dir,
        n_samples=args.n_samples,
        timeout=args.timeout,
        max_level=args.max_level,
        img=args.img,
        aux_only=args.aux_only,
        clear=args.clear,
        add_auxiliary=args.add_auxiliary,
        max_auxiliary_points=args.max_auxiliary_points,
        prune=args.prune,
        remove_coords=args.remove_coords,
        construction_config=construction_config,
        use_cache=args.use_cache,
    )
    generator.generate()


if __name__ == "__main__":
    main()
