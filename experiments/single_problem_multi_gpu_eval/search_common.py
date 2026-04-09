from __future__ import annotations

import heapq
from pathlib import Path
import time
from fractions import Fraction
from typing import TYPE_CHECKING, Any

import cairosvg
import numpy as np
from PIL import Image, ImageOps
import ray

from newclid.DDAR.build import DDAR
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.numerical.geometries import PointNum
from newclid.problem_db import classify_build_exception
from newclid.proof import ProofState
from newclid.search_trace import proof_to_ddar_input

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


class BeamQueue:
    """Keep only the top-k nodes according to their scores."""

    def __init__(self, max_size: int = 512):
        self.queue: list[list[Any]] = []
        self.max_size = max_size
        self.counter = 0
        self.entry_finder: dict[object, list[Any]] = {}
        self.REMOVED = object()

    def add(self, node: object, val: float) -> None:
        if len(self.queue) < self.max_size:
            entry = [val, self.counter, node]
            self.counter += 1
            heapq.heappush(self.queue, entry)
            self.entry_finder[node] = entry
            return

        min_val, _, min_node = self.queue[0]
        if val > min_val:
            self.remove(min_node)
            entry = [val, self.counter, node]
            self.counter += 1
            heapq.heappush(self.queue, entry)
            self.entry_finder[node] = entry

    def remove(self, node: object) -> None:
        entry = self.entry_finder.pop(node, None)
        if entry:
            entry[-1] = self.REMOVED
        self._rebuild_heap()

    def _rebuild_heap(self) -> None:
        self.queue = [entry for entry in self.queue if entry[-1] is not self.REMOVED]
        heapq.heapify(self.queue)

    def __iter__(self):
        for val, _, node in self.queue:
            if node is not self.REMOVED:
                yield val, node

    def __len__(self) -> int:
        return len(self.queue)


def extract_points(proof: ProofState) -> list[tuple[str, Any, Any]]:
    points: list[tuple[str, Any, Any]] = []
    for name, point in proof.symbols_graph.name2node.items():
        if isinstance(point.num, PointNum):
            points.append((name, point.num.x, point.num.y))
    return points


def extract_premises(proof: ProofState) -> list[tuple[str, list[str]]]:
    premises: list[tuple[str, list[str]]] = []
    for stmt in proof.dep_graph.hyper_graph:
        predicate = stmt.predicate.NAME
        args: list[str] = []
        for pt in stmt.args:
            if isinstance(pt, Fraction):
                args.append(str(pt))
            else:
                args.append(pt.name)
        premises.append((predicate, args))
    return premises


def extract_goals(proof: ProofState) -> list[tuple[str, list[str]]]:
    goals: list[tuple[str, list[str]]] = []
    for stmt in proof.goals:
        predicate = stmt.predicate.NAME
        args: list[str] = []
        for pt in stmt.args:
            if isinstance(pt, Fraction):
                args.append(str(pt))
            else:
                args.append(pt.name)
        goals.append((predicate, args))
    return goals


def run_ddar_c(proof: ProofState, rules: list["Rule"], start_time: float, timeout: int = 3600) -> bool:
    del rules, start_time, timeout
    points = extract_points(proof)
    premises = extract_premises(proof)
    goals = extract_goals(proof)
    solved, _ = DDAR.run_ddar("", points, premises, goals, 500, True, True)
    return solved


def render_visual_prompt(
    *,
    proof: ProofState,
    problem,
    render_root: str | Path,
    stem: str,
    render_width: int,
) -> tuple[str, float]:
    render_root_path = Path(render_root)
    render_root_path.mkdir(parents=True, exist_ok=True)
    svg_path = render_root_path / f"{stem}.svg"
    png_path = render_root_path / f"{stem}.png"
    render_start = time.time()
    draw_clause_figure(
        proof,
        problem,
        str(svg_path),
        proof.rng,
        draw_annotations=True,
    )
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=render_width,
    )

    with Image.open(png_path) as img:
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            rgb_img = Image.merge("RGB", (r, g, b))
            inverted_rgb = ImageOps.invert(rgb_img)
            r_inv, g_inv, b_inv = inverted_rgb.split()
            img_out = Image.merge("RGBA", (r_inv, g_inv, b_inv, a))
        elif img.mode == "LA":
            lightness, alpha = img.split()
            lightness_inv = ImageOps.invert(lightness)
            img_out = Image.merge("LA", (lightness_inv, alpha))
        else:
            img_out = ImageOps.invert(img.convert("RGB"))
        img_out.save(png_path)

    return str(png_path), time.time() - render_start


@ray.remote(num_cpus=1)
def run_ddar_remote(
    problem,
    defs,
    rules: list["Rule"],
    start_time: float,
    timeout: int = 3600,
    *,
    return_proof: bool = False,
    render_visual_prompt_remote: bool = False,
    render_root: str | None = None,
    render_stem: str | None = None,
    render_width: int = 1024,
):
    # These timings describe work performed inside one remote DDAR task. They
    # are not main-thread wall-clock timings and can legitimately sum to more
    # than the end-to-end runtime when many DDAR tasks run in parallel.
    eval_start = time.time()
    ddar_build_work_time_s = 0.0
    try:
        build_start = time.time()
        proof = ProofState.build_problemJGEX(
            problemJGEX=problem,
            defsJGEX=defs,
            rng=np.random.default_rng(998244353),
            max_attempts=100,
            problem_path=None,
        )
        ddar_build_work_time_s = time.time() - build_start
    except Exception as exc:
        result = {
            "status": "invalid",
            "elapsed_time": time.time() - eval_start,
            "ddar_build_work_time_s": time.time() - build_start,
            "ddar_engine_work_time_s": 0.0,
            "ddar_render_work_time_s": 0.0,
            "error_type": classify_build_exception(exc),
            "error_message": str(exc),
            "problem_text": str(problem),
            "ddar_input": None,
        }
        if return_proof:
            result["proof"] = None
        return result

    try:
        ddar_start = time.time()
        solved = run_ddar_c(proof, rules, start_time, timeout)
        ddar_engine_work_time_s = time.time() - ddar_start
    except Exception as exc:
        result = {
            "status": "invalid",
            "elapsed_time": time.time() - eval_start,
            "ddar_build_work_time_s": ddar_build_work_time_s,
            "ddar_engine_work_time_s": time.time() - ddar_start,
            "ddar_render_work_time_s": 0.0,
            "error_type": "engine_error",
            "error_message": str(exc),
            "problem_text": str(problem),
            "ddar_input": proof_to_ddar_input(proof),
        }
        if return_proof:
            result["proof"] = None
        return result

    result = {
        "status": "solved" if solved else "unsolved",
        "elapsed_time": time.time() - eval_start,
        "ddar_build_work_time_s": ddar_build_work_time_s,
        "ddar_engine_work_time_s": ddar_engine_work_time_s,
        "ddar_render_work_time_s": 0.0,
        "problem_text": str(problem),
        "ddar_input": proof_to_ddar_input(proof),
    }
    if render_visual_prompt_remote and not solved:
        if render_root is None or render_stem is None:
            raise ValueError("render_root and render_stem are required when render_visual_prompt_remote=True")
        img_path, render_elapsed_s = render_visual_prompt(
            proof=proof,
            problem=problem,
            render_root=render_root,
            stem=render_stem,
            render_width=render_width,
        )
        result["img_path"] = img_path
        result["ddar_render_work_time_s"] = render_elapsed_s
    if return_proof:
        result["proof"] = proof
    return result
