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
import signal
from contextlib import contextmanager
import cairosvg
import numpy as np
import uuid

from newclid.configs import default_defs_path
from newclid.formulations.definition import DefinitionJGEX
from newclid.generation.clause_generation import CompoundClauseGen
from newclid.generation.summary import Summary, get_first_predicate
from newclid.generation.goal_filter import GeometryGoalFilter
from newclid.generation.problem_worker import GeometryProblemWorker

MACHINE_BASE_SEED = 42

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


def convert_svg_to_png(svg_path, png_path, width=1024):
    # Ensure the output directory exists
    output_dir = os.path.dirname(png_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    try:
        cairosvg.svg2png(
            url=svg_path,
            write_to=png_path,
            output_width=width
        )
    except Exception as e:
        # Catch the exception, add context (filename), and re-raise it
        raise RuntimeError(
            f"Failed to convert '{svg_path}' to PNG. Error: {str(e)}") from e


@ray.remote(num_cpus=0.5)
def draw_figure_task(draw_data: dict, defs_data: dict, imgs_dir: str, imgs_png_dir: str, file_idx: int, session_id: str, img_mode: int):
    """
    Ray remote task for drawing figures.
    This runs in a separate Ray worker to avoid blocking the main process.
    img_mode: 0=no images, 1=with annotations only, 2=without annotations only, 3=both
    """
    try:
        from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
        from newclid.dependencies.dependency_graph import DependencyGraph
        from newclid.dependencies.symbols import Point
        from newclid.numerical.geometries import PointNum
        from newclid.numerical.draw_figure import init_figure
        from newclid.numerical.draw_clause_figure import draw_clauses
        from newclid.statement import Statement
        from newclid.formulations.clause import Clause
        from newclid.formulations.definition import DefinitionJGEX
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        
        # Rebuild defs from serialized data
        defs = {k: DefinitionJGEX(**v) for k, v in defs_data.items()}
        
        # Rebuild Point objects with coordinates
        dep_graph = DependencyGraph(AlgebraicManipulator())
        for name, (x, y) in draw_data["point_coords"].items():
            point = Point(name=name, symbols_graph=dep_graph.symbols_graph, dep=None)
            point.num = PointNum(x, y)
            dep_graph.symbols_graph.name2node[name] = point

        # Rebuild Clause objects from (points, sentences) tuples
        clauses = [Clause(points=tuple(c[0]), sentences=tuple(tuple(s) for s in c[1])) 
                   for c in draw_data["clauses"]]

        # Rebuild goal Statement
        goal = Statement.from_tokens(tuple(draw_data["goal_tokens"]), dep_graph)

        paths_update = {}
        
        # Determine which images to generate based on img_mode
        # 1: with annotations only, 2: without annotations only, 3: both
        draw_configs = []
        if img_mode == 1:
            draw_configs = [('', True)]
        elif img_mode == 2:
            draw_configs = [('_no_annotations', False)]
        elif img_mode == 3:
            draw_configs = [('', True), ('_no_annotations', False)]
        
        for suffix, annotations in draw_configs:
            # Use session_id + file_idx to ensure uniqueness across multiple runs
            file_name = f"{session_id}_{file_idx}{suffix}"
            svg_path = os.path.join(imgs_dir, f"{file_name}.svg")
            png_path = os.path.join(imgs_png_dir, f"{file_name}.png")

            # Draw figure
            fig = init_figure()
            draw_clauses(
                fig.axes[0],
                clauses,
                defs,
                goal,
                np.random.default_rng(draw_data["seed"]),
                dep_graph,
                draw_data["mapping"],
                annotations,
            )
            fig.savefig(svg_path, format='svg')
            plt.close(fig)
            convert_svg_to_png(svg_path, png_path)

            paths_update[f'image_path{suffix}'] = png_path

        return file_idx, paths_update, None
    except Exception as e:
        import traceback
        return file_idx, {}, traceback.format_exc()


class GeometryGenerator:
    def __init__(
        self,
        n_clauses=5,
        n_threads=1,
        output_dir="dataset",
        min_proof_steps=5,
        min_clauses_num=3,
        n_samples=100,
        timeout=3600,
        max_level=500,
        img=0,
        aux_only=0,
        clear=False,
        add_auxiliary=True,
        prune=True,
        remove_coords=False,
    ):
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
        self.img = img
        self.aux_only = aux_only
        self.clear = clear
        self.add_auxiliary = add_auxiliary
        self.prune = prune
        self.remove_coords = remove_coords
        self.data_count = 0
        self.written_count = 0  # Track actually written data count
        # Serialize defs for Ray remote tasks
        self.defs_data = {k: v._asdict() for k, v in self.defs.items()}
        # Pending draw tasks and their associated data
        self.pending_draw_tasks = {}  # task_id -> (file_idx, data_item)
        self.completed_data = {}  # file_idx -> result_data
        # Generate a unique session ID using UUID4 (globally unique, collision-proof)
        # Use first 16 chars for shorter filenames while maintaining uniqueness
        self.session_id = uuid.uuid4().hex[:16]
        logging.info(f"Session ID: {self.session_id}")

    def problem_hash_filter(self, data: list, key: str) -> list[str]:
        """Check if the input has already been written to the output file."""
        filtered_data = []
        for d in data:
            key_hash = hash(d[key])
            if key_hash not in self.hashed_problems:
                self.hashed_problems.add(key_hash)
                filtered_data.append(d)
        return filtered_data

    def _process_completed_draw_tasks(self, wait_all: bool = False):
        """Process completed draw tasks and write results to file."""
        if not self.pending_draw_tasks:
            return
        
        # Get tasks to process: all tasks if wait_all, otherwise only completed ones
        if wait_all:
            done_tasks = list(self.pending_draw_tasks.keys())
        else:
            done_tasks, _ = ray.wait(
                list(self.pending_draw_tasks.keys()), 
                num_returns=len(self.pending_draw_tasks), 
                timeout=0
            )
        
        # Process each completed task
        for task_id in done_tasks:
            try:
                file_idx, paths_update, error = ray.get(task_id)
                if error:
                    logging.warning(f"Draw task {file_idx} failed: {error}")
                else:
                    data_item = self.pending_draw_tasks[task_id][1]
                    self.completed_data[file_idx] = {**paths_update, **data_item}
            except Exception as e:
                logging.error(f"Failed to get draw task result: {e}")
            del self.pending_draw_tasks[task_id]

    def _flush_completed_data(self, filename: str) -> int:
        """Write completed data to file in order. Returns number of items written."""
        if not self.completed_data:
            return 0
        
        # Sort by file_idx and write in order
        sorted_indices = sorted(self.completed_data.keys())
        with open(filename, 'a', encoding='utf-8') as f:
            for idx in sorted_indices:
                result_data = self.completed_data[idx]
                json.dump(result_data, f, ensure_ascii=False)
                f.write('\n')
        written = len(self.completed_data)
        self.written_count += written
        self.completed_data.clear()
        return written

    def write_data(self, all_data: list, force: bool = False):
        """Append data to buffer and submit draw tasks if needed."""
        filename = self.path_prefix + ".jsonl"
        imgs_dir = os.path.join(self.output_dir, "imgs")
        imgs_png_dir = os.path.join(self.output_dir, "imgs_png")
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        os.makedirs(imgs_dir, exist_ok=True)
        os.makedirs(imgs_png_dir, exist_ok=True)
        
        for data_item in all_data:
            self.data_count += 1
            if self.img > 0 and "draw_data" in data_item:
                draw_data = data_item.pop("draw_data")
                # Submit draw task to Ray with session_id for unique filenames
                task_id = draw_figure_task.remote(
                    draw_data, 
                    self.defs_data, 
                    imgs_dir, 
                    imgs_png_dir, 
                    self.data_count,
                    self.session_id,
                    self.img
                )
                self.pending_draw_tasks[task_id] = (self.data_count, data_item)
            else:
                # No image needed, write directly
                data_item.pop("draw_data", None)
                self.completed_data[self.data_count] = data_item
        
        # Process any completed draw tasks
        self._process_completed_draw_tasks(wait_all=False)
        
        # Flush completed data to file periodically or when forced
        # Also flush when too many draw tasks are pending to avoid memory buildup
        should_flush = (
            len(self.completed_data) > 100 or 
            len(self.pending_draw_tasks) > 200 or
            force
        )
        if should_flush:
            # If many draw tasks pending, wait for some to complete first
            if len(self.pending_draw_tasks) > 200:
                self._process_completed_draw_tasks(wait_all=True)
            self._flush_completed_data(filename)
        
        # If force, wait for all pending draw tasks
        if force and self.pending_draw_tasks:
            self._process_completed_draw_tasks(wait_all=True)
            self._flush_completed_data(filename)

    @staticmethod
    def _inject_pids(jsonl_path: str):
        """Post-process JSONL file to inject sequential pid into each record."""
        if not os.path.exists(jsonl_path):
            return
        tmp_path = jsonl_path + ".tmp"
        with open(jsonl_path, 'r', encoding='utf-8') as fin, \
             open(tmp_path, 'w', encoding='utf-8') as fout:
            for i, line in enumerate(fin, start=1):
                record = json.loads(line)
                record["pid"] = f"p{i:06d}"
                json.dump(record, fout, ensure_ascii=False)
                fout.write('\n')
        os.replace(tmp_path, jsonl_path)
        logging.info(f"Injected pid into {i} records in {jsonl_path}")

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
        # else:
        #     filename = self.path_prefix + ".jsonl"
        #     if os.path.exists(filename):
        #         with open(filename, 'r', encoding='utf-8') as f:
        #             self.data_count = sum(1 for line in f if line.strip())

        def task_generator():
            for i in range(10**9):
                # seed = 42 + i  # 唯一种子 = 42 + 任务ID
                seed = MACHINE_BASE_SEED + i
                yield i, seed, self.n_clauses, self.max_level, self.img, self.aux_only, self.add_auxiliary, self.prune, self.remove_coords

        if not ray.is_initialized():
            ray.init(
                # local_mode=True,
                ignore_reinit_error=True,
                num_cpus=self.n_threads,
                _system_config={
                    "raylet_start_wait_time_s": 120,
                    "gcs_rpc_server_reconnect_timeout_s": 120,
                }
            )
        task_iterator = task_generator()
        max_pending = int(self.n_threads * 1.5)
        summary_reporter = Summary(prefix=self.path_prefix)

        start_time = time.time()
        all_data_len = self.data_count  # Total generated (including pending draw)
        all_data_len_raw = self.data_count
        pending_tasks = {}
        last_logged_written = self.written_count
        
        while self.written_count < self.n_samples:
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
                        summary['n_premises'] = [d['n_premises'] for d in data]
                        summary['n_proof_steps'] = [d['n_proof_steps']
                                                    for d in data]
                        self.write_data(data)
                        all_data_len += summary['n_samples']
                        summary_reporter.add(summary)
                        
                        # Log progress when new data is written to file
                        if self.written_count > last_logged_written:
                            elapsed_time = time.time() - start_time
                            pending_draw = len(self.pending_draw_tasks)
                            pending_completed = len(self.completed_data)
                            logging.info(
                                f"{millify(self.written_count)}/{millify(self.n_samples)} "
                                f"(+{self.written_count - last_logged_written:3d}, pending: {pending_draw}+{pending_completed}) "
                                f"in {elapsed_time:5.0f}s | "
                                f"Total: {summary['total_time']:3.0f}s = "
                                f"Enh: {summary['enhance_runtime']:2.0f} + "
                                f"DDAR: {summary['runtime']:2.0f} + "
                                f"Chk: {summary['checkgoals_runtime']:2.0f} + "
                                f"Group: {summary['group_runtime']:2.0f} + "
                                f"Proc: {summary['process_goal_runtime']:3.0f} | "
                                f"Speed: {self.written_count/elapsed_time:3.0f} samp/s | "
                                f"ETA: {timedelta(seconds=int(self.n_samples/max(1,self.written_count)*elapsed_time - elapsed_time))}"
                            )
                            last_logged_written = self.written_count
            for task, s_time in list(pending_tasks.items()):
                if time.time() - s_time > self.timeout:
                    print(f"⚠️ Task {task} timeout. Canceling")
                    ray.cancel(task, force=True)
                    del pending_tasks[task]

            while len(pending_tasks) < max_pending:
                task_args = next(task_iterator)
                pending_tasks[GeometryProblemWorker.ray_process_single_problem.remote(
                    task_args)] = time.time()

        # Cancel any remaining problem generation tasks
        for task in pending_tasks.keys():
            ray.cancel(task, force=True)

        # Wait for all pending draw tasks to complete before shutdown
        self.write_data([], force=True)
        
        ray.shutdown()

        # Post-process: inject sequential pid into each JSONL record
        jsonl_path = self.path_prefix + ".jsonl"
        self._inject_pids(jsonl_path)

        final_elapsed_time = time.time() - start_time
        summary_reporter.total_elapsed_time = final_elapsed_time
        summary_reporter.total_samples_generated = self.written_count
        logging.info(
            f"Generated {self.written_count} samples successfully in {final_elapsed_time:.2f}s.")
        summary_reporter.output_report()


def str_to_bool(value):
    """Convert string to boolean value."""
    if isinstance(value, bool):
        return value
    if value.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif value.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


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
    parser.add_argument("--img", required=False, type=int, default=0, choices=[0, 1, 2, 3],
                        help="Image generation mode: " \
                            "0=no images, " \
                            "1=with annotations only, " \
                            "2=without annotations only, " \
                            "3=both.")
    parser.add_argument("--aux_only", required=False, type=int, default=0, choices=[0, 1, 2],
                        help="Auxiliary data filter: " \
                            "0=all data, " \
                            "1=include data without aux with 0.1 probability, " \
                            "2=only data with aux.")
    parser.add_argument("--clear", required=False, type=str_to_bool, default=False,
                        help="Whether to clear old dataset files.")
    parser.add_argument("--add_auxiliary", required=False, type=str_to_bool, default=True,
                        help="Whether to add auxiliary points (e.g., midpoint, orthocenter) for triangles.")
    parser.add_argument("--prune", required=False, type=str_to_bool, default=True,
                        help="Whether to prune clauses to preserve only the deepest clause chain.")
    parser.add_argument("--remove_coords", required=False, type=str_to_bool, default=False,
                        help="Whether to remove coordinate information from the final clause output.")
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
        max_level=args.max_level,
        img=args.img,
        aux_only=args.aux_only,
        clear=args.clear,
        add_auxiliary=args.add_auxiliary,
        prune=args.prune,
        remove_coords=args.remove_coords,
    )

    generator.generate()


if __name__ == "__main__":
    main()
