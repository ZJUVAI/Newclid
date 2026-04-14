from __future__ import annotations

from pathlib import Path
import re


def sanitize_problem_name(problem_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", problem_name).strip("_") or "problem"


def normalize_agent_type(agent_type: str) -> str:
    if agent_type == "qwen35":
        return "qwen35_vl"
    return agent_type


def build_eval_output_stem(
    *,
    agent_type: str,
    problems_path: Path,
    model_path: str,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    gpu_batch_size: int,
    gpu_batch_timeout_ms: int,
    torch_seed: int = 123,
) -> str:
    agent_type = normalize_agent_type(agent_type)
    problems_name = problems_path.stem
    path_obj = Path(model_path)
    deepest_folder = path_obj.name
    parent_folder = path_obj.parent.name
    model_name = (
        f"{parent_folder}_{deepest_folder}" if parent_folder else deepest_folder
    )
    return (
        f"eval_single_problem_multi_gpu_{agent_type}_{problems_name}_{model_name}"
        f"_d{decoding_size}_b{beam_size}_s{search_depth}"
        f"_gbs{gpu_batch_size}_gbt{gpu_batch_timeout_ms}_seed{torch_seed}"
    )


def build_timestamped_output_stem(output_name_stem: str, timestamp: str) -> str:
    return f"{output_name_stem}_{timestamp}"


__all__ = [
    "build_eval_output_stem",
    "build_timestamped_output_stem",
    "normalize_agent_type",
    "sanitize_problem_name",
]
