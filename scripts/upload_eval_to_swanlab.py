#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path

try:
    import swanlab
except ImportError:
    swanlab = None


def parse_bool(value: str) -> bool:
    value = value.lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def add_common_swanlab_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--workspace", default="")
    parser.add_argument("--experiment_name", required=True)
    parser.add_argument("--mode", default="cloud")
    parser.add_argument("--token", default="")


def init_swanlab(args: argparse.Namespace) -> None:
    if swanlab is None:
        raise RuntimeError("swanlab is required for init-run.")
    if args.token:
        swanlab.login(args.token)

    config = {
        "model_name": args.model_name,
        "model_dir": args.model_dir,
        "datasets": args.datasets,
        "checkpoints": args.checkpoints,
        "eval_configs": args.eval_configs,
        "agent": args.agent,
        "search_version": args.search_version,
        "max_workers": args.max_workers,
        "search_depth": args.search_depth,
        "timeout": args.timeout,
    }

    kwargs = {
        "project": args.project,
        "experiment_name": args.experiment_name,
        "config": config,
        "mode": args.mode,
    }
    if args.workspace:
        kwargs["workspace"] = args.workspace

    run = swanlab.init(**kwargs)
    print(f"RUN_ID={run.id}")
    swanlab.finish()


def parse_eval_csv(
    csv_path: Path,
) -> tuple[str, str | None, str | None, int, int, float, list[str], list[list[str]]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if len(rows) < 2 or not rows[0]:
        raise ValueError(f"Unexpected evaluation CSV format: {csv_path}")

    summary = (
        rows[0][0]
        if len(rows[0]) == 1
        else ", ".join(part.strip() for part in rows[0])
    )
    match = re.match(
        r"^Dataset: (?P<dataset>.*?)(?:, Model: (?P<model>.*?), Checkpoint: (?P<checkpoint>.*?))?, Solved: (?P<solved>\d+)/(?P<total>\d+), Total Time: (?P<time>[0-9.]+)s$",
        summary,
    )
    if match is None:
        raise ValueError(f"Unexpected summary row: {summary}")

    dataset_name = match.group("dataset")
    model_name = match.group("model")
    checkpoint_name = match.group("checkpoint")
    solved_count = int(match.group("solved"))
    total_count = int(match.group("total"))
    total_time = float(match.group("time"))
    headers = rows[1]
    csv_rows = rows[2:]
    return (
        dataset_name,
        model_name,
        checkpoint_name,
        solved_count,
        total_count,
        total_time,
        headers,
        csv_rows,
    )


def upload_eval(args: argparse.Namespace) -> None:
    if swanlab is None:
        raise RuntimeError("swanlab is required for upload.")
    if args.token:
        swanlab.login(args.token)

    kwargs = {
        "project": args.project,
        "experiment_name": args.experiment_name,
        "mode": args.mode,
    }
    if args.workspace:
        kwargs["workspace"] = args.workspace
    if args.run_id:
        kwargs["id"] = args.run_id
        kwargs["resume"] = args.resume

    swanlab.init(**kwargs)

    csv_path = Path(args.csv_path)
    (
        dataset_name,
        csv_model_name,
        csv_checkpoint_name,
        solved_count,
        total_count,
        total_time,
        csv_headers,
        csv_rows,
    ) = parse_eval_csv(csv_path)
    solved_rate = solved_count / total_count if total_count else 0.0
    avg_time = total_time / total_count if total_count else 0.0
    key_prefix = f"eval/{dataset_name}/{args.checkpoint_label}"

    swanlab.log({
        f"{key_prefix}/solved_count": solved_count,
        f"{key_prefix}/total_count": total_count,
        f"{key_prefix}/solved_rate": solved_rate,
        f"{key_prefix}/total_time_s": total_time,
        f"{key_prefix}/avg_time_s": avg_time,
        f"{key_prefix}/decoding_size": args.decoding_size,
        f"{key_prefix}/beam_size": args.beam_size,
        f"{key_prefix}/search_depth": args.search_depth,
        f"{key_prefix}/search_version": args.search_version,
        f"{key_prefix}/timeout": args.timeout,
        f"{key_prefix}/max_workers": args.max_workers,
    })

    if args.log_table:
        table = swanlab.echarts.Table()
        table.add(headers=csv_headers, rows=csv_rows)
        swanlab.log({f"{key_prefix}/results": table})

    summary_table = swanlab.echarts.Table()
    summary_table.add(
        headers=[
            "Dataset",
            "Checkpoint",
            "Model Name",
            "Model Path",
            "Agent",
            "Search Version",
            "Solved",
            "Total",
            "Solved Rate",
            "Total Time (s)",
            "Avg Time (s)",
            "Decoding Size",
            "Beam Size",
            "Search Depth",
            "CSV Path",
        ],
        rows=[[
            args.dataset_name,
            csv_checkpoint_name or args.checkpoint_label,
            csv_model_name or args.model_name,
            args.model_path,
            args.agent,
            args.search_version,
            solved_count,
            total_count,
            round(solved_rate, 6),
            round(total_time, 2),
            round(avg_time, 2),
            args.decoding_size,
            args.beam_size,
            args.search_depth,
            str(csv_path),
        ]],
    )
    swanlab.log({f"{key_prefix}/summary": summary_table})
    swanlab.finish()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize or upload evaluation results to SwanLab.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-run")
    add_common_swanlab_args(init_parser)
    init_parser.add_argument("--model_name", required=True)
    init_parser.add_argument("--model_dir", required=True)
    init_parser.add_argument("--datasets", required=True)
    init_parser.add_argument("--checkpoints", required=True)
    init_parser.add_argument("--eval_configs", required=True)
    init_parser.add_argument("--agent", required=True)
    init_parser.add_argument("--search_version", required=True)
    init_parser.add_argument("--max_workers", type=int, required=True)
    init_parser.add_argument("--search_depth", type=int, required=True)
    init_parser.add_argument("--timeout", type=int, required=True)
    init_parser.set_defaults(func=init_swanlab)

    upload_parser = subparsers.add_parser("upload")
    add_common_swanlab_args(upload_parser)
    upload_parser.add_argument("--csv_path", required=True)
    upload_parser.add_argument("--run_id", default="")
    upload_parser.add_argument("--resume", default="allow")
    upload_parser.add_argument("--dataset_name", required=True)
    upload_parser.add_argument("--checkpoint_label", required=True)
    upload_parser.add_argument("--model_name", required=True)
    upload_parser.add_argument("--model_path", required=True)
    upload_parser.add_argument("--agent", required=True)
    upload_parser.add_argument("--search_version", required=True)
    upload_parser.add_argument("--decoding_size", type=int, required=True)
    upload_parser.add_argument("--beam_size", type=int, required=True)
    upload_parser.add_argument("--search_depth", type=int, required=True)
    upload_parser.add_argument("--timeout", type=int, required=True)
    upload_parser.add_argument("--max_workers", type=int, required=True)
    upload_parser.add_argument("--log_table", type=parse_bool, default=True)
    upload_parser.set_defaults(func=upload_eval)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
