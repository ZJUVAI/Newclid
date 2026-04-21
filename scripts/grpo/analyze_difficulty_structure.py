#!/usr/bin/env python3
"""Analyze how difficulty relates to aux count and premise count."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _resolve_pass_key(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        pass_keys = sorted(
            (key for key in row if key.startswith("pass_at_")),
            key=lambda key: int(key.split("_")[-1]),
            reverse=True,
        )
        if pass_keys:
            return pass_keys[0]
    raise KeyError("No pass_at_* field found")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _success_count(row: dict[str, Any], pass_key: str, *, num_samples: int) -> int:
    return int(round(float(row.get(pass_key, 0.0)) * num_samples))


def _rankdata(values: list[float]) -> list[float]:
    if not values:
        return []
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(ordered):
        end = idx + 1
        while end < len(ordered) and ordered[end][1] == ordered[idx][1]:
            end += 1
        avg_rank = (idx + 1 + end) / 2.0
        for pos in range(idx, end):
            ranks[ordered[pos][0]] = avg_rank
        idx = end
    return ranks


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    x_std = float(x_arr.std())
    y_std = float(y_arr.std())
    if x_std == 0.0 or y_std == 0.0:
        return None
    return float(np.corrcoef(x_arr, y_arr)[0, 1])


def spearman_correlation(x: list[float], y: list[float]) -> dict[str, Any]:
    rho = _pearson(_rankdata(x), _rankdata(y))
    return {
        "n": len(x),
        "rho": rho,
    }


def _normal_p_value_from_z(z_value: float) -> float:
    return math.erfc(abs(z_value) / math.sqrt(2.0))


def _log_likelihood(successes: np.ndarray, trials: np.ndarray, probs: np.ndarray) -> float:
    probs = np.clip(probs, 1e-9, 1.0 - 1e-9)
    failures = trials - successes
    return float(np.sum(successes * np.log(probs) + failures * np.log(1.0 - probs)))


def fit_grouped_binomial_logit(
    rows: list[dict[str, Any]],
    *,
    pass_key: str,
    num_samples: int,
    aux_key: str,
    premises_key: str,
    binary_nonzero: bool = False,
    max_iter: int = 200,
    tol: float = 1e-8,
) -> dict[str, Any] | None:
    usable_rows = []
    for row in rows:
        aux = _safe_float(row.get(aux_key))
        premises = _safe_float(row.get(premises_key))
        pass_value = _safe_float(row.get(pass_key))
        if aux is None or premises is None or pass_value is None:
            continue
        usable_rows.append((aux, premises, row))

    if len(usable_rows) < 8:
        return None

    x_data = []
    successes = []
    trials = []
    for aux, premises, row in usable_rows:
        x_data.append([1.0, aux, premises, aux * premises])
        if binary_nonzero:
            successes.append(1.0 if float(row.get(pass_key, 0.0)) > 0.0 else 0.0)
            trials.append(1.0)
        else:
            successes.append(float(_success_count(row, pass_key, num_samples=num_samples)))
            trials.append(float(num_samples))

    x = np.asarray(x_data, dtype=float)
    y = np.asarray(successes, dtype=float)
    n = np.asarray(trials, dtype=float)

    if np.all(y == 0.0) or np.all(y == n):
        return None

    beta = np.zeros(x.shape[1], dtype=float)
    converged = False
    for _ in range(max_iter):
        eta = x @ beta
        mu = 1.0 / (1.0 + np.exp(-np.clip(eta, -30.0, 30.0)))
        mu = np.clip(mu, 1e-6, 1.0 - 1e-6)
        weights = n * mu * (1.0 - mu)
        if np.any(weights <= 0.0):
            return None
        z = eta + (y - n * mu) / weights
        sqrt_w = np.sqrt(weights)
        x_w = x * sqrt_w[:, None]
        z_w = z * sqrt_w
        beta_next, *_ = np.linalg.lstsq(x_w, z_w, rcond=None)
        if np.max(np.abs(beta_next - beta)) < tol:
            beta = beta_next
            converged = True
            break
        beta = beta_next

    eta = x @ beta
    mu = 1.0 / (1.0 + np.exp(-np.clip(eta, -30.0, 30.0)))
    mu = np.clip(mu, 1e-6, 1.0 - 1e-6)
    weights = n * mu * (1.0 - mu)
    x_w = x * np.sqrt(weights)[:, None]
    xtwx = x_w.T @ x_w
    cov = np.linalg.pinv(xtwx)
    stderr = np.sqrt(np.maximum(np.diag(cov), 0.0))
    z_values = np.divide(
        beta,
        stderr,
        out=np.zeros_like(beta),
        where=stderr > 0.0,
    )
    p_values = [_normal_p_value_from_z(float(value)) for value in z_values]

    intercept_prob = np.clip(float(np.mean(y / n)), 1e-9, 1.0 - 1e-9)
    intercept_ll = _log_likelihood(y, n, np.full_like(y, intercept_prob))
    model_ll = _log_likelihood(y, n, mu)
    pseudo_r2 = 1.0 - (model_ll / intercept_ll) if intercept_ll != 0.0 else None

    feature_names = ["intercept", aux_key, premises_key, f"{aux_key}*{premises_key}"]
    coefficients = []
    for idx, name in enumerate(feature_names):
        coefficients.append(
            {
                "feature": name,
                "coef": float(beta[idx]),
                "stderr": float(stderr[idx]),
                "z": float(z_values[idx]),
                "p_value": float(p_values[idx]),
                "odds_ratio": float(math.exp(beta[idx])),
            }
        )

    return {
        "n_rows": len(usable_rows),
        "converged": converged,
        "binary_nonzero": binary_nonzero,
        "pseudo_r2_mcfadden": pseudo_r2,
        "log_likelihood": model_ll,
        "coefficients": coefficients,
    }


def summarize_grouped_relation(
    rows: list[dict[str, Any]],
    *,
    group_key: str,
    pass_key: str,
    num_samples: int,
) -> dict[str, Any]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group_value = _safe_int(row.get(group_key))
        if group_value is None:
            continue
        grouped[group_value].append(row)

    summary = {}
    for value in sorted(grouped):
        group_rows = grouped[value]
        pass_values = [float(row.get(pass_key, 0.0)) for row in group_rows]
        successes = [_success_count(row, pass_key, num_samples=num_samples) for row in group_rows]
        summary[str(value)] = {
            "count": len(group_rows),
            "avg_pass": sum(pass_values) / len(pass_values),
            "median_pass": statistics.median(pass_values),
            "zero_ratio": sum(item == 0.0 for item in pass_values) / len(pass_values),
            "one_ratio": sum(item == 1.0 for item in pass_values) / len(pass_values),
            "avg_success_count": sum(successes) / len(successes),
        }
    return summary


def build_heatmap_summary(
    rows: list[dict[str, Any]],
    *,
    aux_key: str,
    premises_key: str,
    pass_key: str,
) -> dict[str, Any]:
    cells: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row in rows:
        aux = _safe_int(row.get(aux_key))
        premises = _safe_int(row.get(premises_key))
        pass_value = _safe_float(row.get(pass_key))
        if aux is None or premises is None or pass_value is None:
            continue
        cells[(aux, premises)].append(pass_value)

    avg_pass = defaultdict(dict)
    zero_ratio = defaultdict(dict)
    count = defaultdict(dict)
    for (aux, premises), pass_values in sorted(cells.items()):
        avg_pass[str(aux)][str(premises)] = sum(pass_values) / len(pass_values)
        zero_ratio[str(aux)][str(premises)] = (
            sum(value == 0.0 for value in pass_values) / len(pass_values)
        )
        count[str(aux)][str(premises)] = len(pass_values)

    return {
        "avg_pass": {key: dict(value) for key, value in avg_pass.items()},
        "zero_ratio": {key: dict(value) for key, value in zero_ratio.items()},
        "count": {key: dict(value) for key, value in count.items()},
    }


def _prepare_numeric_pairs(
    rows: list[dict[str, Any]],
    *,
    x_key: str,
    y_key: str,
) -> tuple[list[float], list[float]]:
    x_values: list[float] = []
    y_values: list[float] = []
    for row in rows:
        x = _safe_float(row.get(x_key))
        y = _safe_float(row.get(y_key))
        if x is None or y is None:
            continue
        x_values.append(x)
        y_values.append(y)
    return x_values, y_values


def maybe_write_plots(
    summary: dict[str, Any],
    *,
    plots_dir: Path | None,
    aux_key: str,
    aux_segment_key: str,
    premises_key: str,
) -> list[str]:
    if plots_dir is None:
        return []
    import matplotlib.pyplot as plt

    plots_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    def _plot_grouped(grouped: dict[str, Any], x_label: str, output_name: str) -> None:
        x = [int(item) for item in grouped]
        avg_pass = [grouped[str(item)]["avg_pass"] for item in x]
        zero_ratio = [grouped[str(item)]["zero_ratio"] for item in x]

        fig, ax1 = plt.subplots(figsize=(8, 5))
        ax1.plot(x, avg_pass, marker="o", color="#1f77b4")
        ax1.set_xlabel(x_label)
        ax1.set_ylabel("avg pass@16", color="#1f77b4")
        ax1.tick_params(axis="y", labelcolor="#1f77b4")

        ax2 = ax1.twinx()
        ax2.plot(x, zero_ratio, marker="s", color="#d62728")
        ax2.set_ylabel("zero ratio", color="#d62728")
        ax2.tick_params(axis="y", labelcolor="#d62728")

        fig.tight_layout()
        output_path = plots_dir / output_name
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        created.append(str(output_path))

    _plot_grouped(summary["grouped_by_aux"], aux_key, "avg_pass_vs_aux.png")
    _plot_grouped(
        summary["grouped_by_aux_segments"],
        aux_segment_key,
        "avg_pass_vs_aux_segments.png",
    )
    _plot_grouped(
        summary["grouped_by_premises"],
        premises_key,
        "avg_pass_vs_premises.png",
    )

    heatmap = summary["heatmap"]["avg_pass"]
    aux_values = sorted(int(item) for item in heatmap)
    premises_values = sorted(
        {int(inner) for value in heatmap.values() for inner in value.keys()}
    )
    matrix = np.full((len(aux_values), len(premises_values)), np.nan)
    for i, aux in enumerate(aux_values):
        for j, premises in enumerate(premises_values):
            value = heatmap.get(str(aux), {}).get(str(premises))
            if value is not None:
                matrix[i, j] = value

    fig, ax = plt.subplots(figsize=(10, 6))
    image = ax.imshow(matrix, aspect="auto", cmap="viridis", vmin=0.0, vmax=1.0)
    ax.set_xticks(range(len(premises_values)))
    ax.set_xticklabels(premises_values, rotation=45, ha="right")
    ax.set_yticks(range(len(aux_values)))
    ax.set_yticklabels(aux_values)
    ax.set_xlabel(premises_key)
    ax.set_ylabel(aux_key)
    ax.set_title("avg pass@16 heatmap")
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    heatmap_path = plots_dir / "avg_pass_heatmap.png"
    fig.savefig(heatmap_path, dpi=150)
    plt.close(fig)
    created.append(str(heatmap_path))

    heatmap_segments = summary["heatmap_aux_segments"]["avg_pass"]
    aux_segment_values = sorted(int(item) for item in heatmap_segments)
    segment_matrix = np.full((len(aux_segment_values), len(premises_values)), np.nan)
    for i, aux_segment in enumerate(aux_segment_values):
        for j, premises in enumerate(premises_values):
            value = heatmap_segments.get(str(aux_segment), {}).get(str(premises))
            if value is not None:
                segment_matrix[i, j] = value

    fig, ax = plt.subplots(figsize=(10, 6))
    image = ax.imshow(
        segment_matrix, aspect="auto", cmap="viridis", vmin=0.0, vmax=1.0
    )
    ax.set_xticks(range(len(premises_values)))
    ax.set_xticklabels(premises_values, rotation=45, ha="right")
    ax.set_yticks(range(len(aux_segment_values)))
    ax.set_yticklabels(aux_segment_values)
    ax.set_xlabel(premises_key)
    ax.set_ylabel(aux_segment_key)
    ax.set_title("avg pass@16 heatmap by aux segments")
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    heatmap_segment_path = plots_dir / "avg_pass_heatmap_aux_segments.png"
    fig.savefig(heatmap_segment_path, dpi=150)
    plt.close(fig)
    created.append(str(heatmap_segment_path))
    return created


def build_summary(
    rows: list[dict[str, Any]],
    *,
    pass_key: str,
    aux_key: str,
    aux_segment_key: str,
    premises_key: str,
    num_samples: int,
) -> dict[str, Any]:
    usable_rows = []
    skipped_rows = 0
    for row in rows:
        if (
            _safe_float(row.get(pass_key)) is None
            or _safe_int(row.get(premises_key)) is None
        ):
            skipped_rows += 1
            continue
        usable_rows.append(row)

    pass_values = [float(row.get(pass_key, 0.0)) for row in usable_rows]
    aux_rows = [row for row in usable_rows if _safe_int(row.get(aux_key)) is not None]
    aux_segment_rows = [
        row for row in usable_rows if _safe_int(row.get(aux_segment_key)) is not None
    ]
    aux_values, aux_pass_values = _prepare_numeric_pairs(
        aux_rows, x_key=aux_key, y_key=pass_key
    )
    aux_segment_values, aux_segment_pass_values = _prepare_numeric_pairs(
        aux_segment_rows, x_key=aux_segment_key, y_key=pass_key
    )
    premises_values, premises_pass_values = _prepare_numeric_pairs(
        usable_rows, x_key=premises_key, y_key=pass_key
    )

    summary = {
        "total_rows": len(rows),
        "usable_rows": len(usable_rows),
        "skipped_rows": skipped_rows,
        "pass_key": pass_key,
        "num_samples": num_samples,
        "aux_key": aux_key,
        "aux_segment_key": aux_segment_key,
        "premises_key": premises_key,
        "overall": {
            "avg_pass": sum(pass_values) / len(pass_values) if pass_values else 0.0,
            "median_pass": statistics.median(pass_values) if pass_values else 0.0,
            "zero_ratio": (
                sum(value == 0.0 for value in pass_values) / len(pass_values)
                if pass_values
                else 0.0
            ),
            "one_ratio": (
                sum(value == 1.0 for value in pass_values) / len(pass_values)
                if pass_values
                else 0.0
            ),
        },
        "grouped_by_aux": summarize_grouped_relation(
            aux_rows,
            group_key=aux_key,
            pass_key=pass_key,
            num_samples=num_samples,
        ),
        "grouped_by_aux_segments": summarize_grouped_relation(
            aux_segment_rows,
            group_key=aux_segment_key,
            pass_key=pass_key,
            num_samples=num_samples,
        ),
        "grouped_by_premises": summarize_grouped_relation(
            usable_rows,
            group_key=premises_key,
            pass_key=pass_key,
            num_samples=num_samples,
        ),
        "heatmap": build_heatmap_summary(
            aux_rows,
            aux_key=aux_key,
            premises_key=premises_key,
            pass_key=pass_key,
        ),
        "heatmap_aux_segments": build_heatmap_summary(
            aux_segment_rows,
            aux_key=aux_segment_key,
            premises_key=premises_key,
            pass_key=pass_key,
        ),
        "spearman": {
            f"{aux_key}_vs_{pass_key}": spearman_correlation(aux_values, aux_pass_values),
            f"{aux_segment_key}_vs_{pass_key}": spearman_correlation(
                aux_segment_values, aux_segment_pass_values
            ),
            f"{premises_key}_vs_{pass_key}": spearman_correlation(
                premises_values, premises_pass_values
            ),
        },
        "models": {
            "binomial_pass_rate": fit_grouped_binomial_logit(
                aux_rows,
                pass_key=pass_key,
                num_samples=num_samples,
                aux_key=aux_key,
                premises_key=premises_key,
                binary_nonzero=False,
            ),
            "logit_nonzero_pass": fit_grouped_binomial_logit(
                aux_rows,
                pass_key=pass_key,
                num_samples=num_samples,
                aux_key=aux_key,
                premises_key=premises_key,
                binary_nonzero=True,
            ),
            "binomial_pass_rate_by_aux_segments": fit_grouped_binomial_logit(
                aux_segment_rows,
                pass_key=pass_key,
                num_samples=num_samples,
                aux_key=aux_segment_key,
                premises_key=premises_key,
                binary_nonzero=False,
            ),
            "logit_nonzero_pass_by_aux_segments": fit_grouped_binomial_logit(
                aux_segment_rows,
                pass_key=pass_key,
                num_samples=num_samples,
                aux_key=aux_segment_key,
                premises_key=premises_key,
                binary_nonzero=True,
            ),
        },
    }
    return summary


def print_summary(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Difficulty labels JSONL")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional JSON summary output path",
    )
    parser.add_argument(
        "--plots-dir",
        type=Path,
        default=None,
        help="Optional directory for PNG plots",
    )
    parser.add_argument(
        "--pass-key",
        type=str,
        default=None,
        help="Explicit pass_at_* field; default resolves the largest available one",
    )
    parser.add_argument(
        "--aux-key",
        type=str,
        default="aux_points_total",
        help="Field name for aux count analysis",
    )
    parser.add_argument(
        "--aux-segment-key",
        type=str,
        default="aux_segment_count",
        help="Field name for aux segment count analysis",
    )
    parser.add_argument(
        "--premises-key",
        type=str,
        default="n_premises",
        help="Field name for premise count analysis",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=None,
        help="Sampling count for pass_at_k; default inferred from pass key",
    )
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    pass_key = args.pass_key or _resolve_pass_key(rows)
    num_samples = args.num_samples
    if num_samples is None:
        num_samples = int(pass_key.split("_")[-1])

    summary = build_summary(
        rows,
        pass_key=pass_key,
        aux_key=args.aux_key,
        aux_segment_key=args.aux_segment_key,
        premises_key=args.premises_key,
        num_samples=num_samples,
    )
    if args.plots_dir is not None:
        summary["plots"] = maybe_write_plots(
            summary,
            plots_dir=args.plots_dir,
            aux_key=args.aux_key,
            aux_segment_key=args.aux_segment_key,
            premises_key=args.premises_key,
        )
    if args.summary_output is not None:
        write_json(args.summary_output, summary)
    print_summary(summary)


if __name__ == "__main__":
    main()
