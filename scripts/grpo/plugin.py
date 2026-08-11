"""SWIFT plugin entrypoint for GRPO auxiliary-point rewards."""

from collections import Counter
import inspect
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
_STATUS_KEYS = (
    "solved",
    "unsolved",
    "build_invalid",
    "format_invalid",
    "engine_error",
)

try:
    from swift.rewards import ORM, orms
except ImportError:  # pragma: no cover - keeps local imports/testing lightweight.

    class ORM:  # type: ignore[no-redef]
        pass

    orms = {}

from newclid.training.grpo_rewards import AuxReward as _AuxReward  # noqa: E402


def _patch_validate_model_kwargs() -> None:
    """Patch transformers to drop unknown kwargs instead of raising.

    SWIFT's GRPO trainer passes all dataset columns (e.g. fl_problem) as
    kwargs to model.generate(), but the model only accepts its own inputs.
    This patch silently removes unrecognised kwargs so generation succeeds
    while the reward function still receives them via the batch.
    """
    try:
        from transformers.generation import utils as gen_utils

        _original = gen_utils.GenerationMixin._validate_model_kwargs

        def _patched(self, model_kwargs: dict) -> None:  # type: ignore[override]
            # Determine which kwargs the model actually accepts.
            try:
                accepted = set(
                    inspect.signature(
                        self.prepare_inputs_for_generation
                    ).parameters.keys()
                )
            except (ValueError, TypeError):
                accepted = set()

            # If prepare_inputs_for_generation accepts **kwargs, nothing to do.
            sig = inspect.signature(self.prepare_inputs_for_generation)
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if has_var_keyword:
                return

            # Remove keys the model won't use rather than raising.
            extra = [k for k in list(model_kwargs) if k not in accepted]
            if extra:
                logger.debug("Dropping extra model_kwargs: %s", extra)
                for k in extra:
                    model_kwargs.pop(k)

        gen_utils.GenerationMixin._validate_model_kwargs = _patched
        logger.info("Applied _validate_model_kwargs patch for GRPO extra columns.")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not patch _validate_model_kwargs: %s", exc)


_patch_validate_model_kwargs()


class AuxReward(_AuxReward, ORM):
    """SWIFT-compatible wrapper around the aux evaluator."""

    def __init__(self, *args, **kwargs):
        reward_log_interval = kwargs.pop(
            "reward_log_interval",
            os.getenv("NEWCLID_GRPO_REWARD_LOG_INTERVAL", "1"),
        )
        breakdown_path = kwargs.pop(
            "reward_breakdown_path",
            os.getenv("NEWCLID_GRPO_REWARD_BREAKDOWN_PATH"),
        )
        _AuxReward.__init__(self, **kwargs)
        self._reward_log_interval = max(0, int(reward_log_interval))
        self._call_count = 0
        self._current_step = None
        self._step_rollout_call = 0
        self._step_status_counts = Counter()
        self._step_reward_sums = Counter()
        self._step_sample_count = 0
        self._step_aux_signatures = set()
        self._breakdown_path = self._resolve_breakdown_path(breakdown_path)
        self._breakdown_initialized = False
        # Don't call ORM.__init__ as it's just a marker class

    @staticmethod
    def _resolve_breakdown_path(path_value: str | None) -> Path | None:
        if not path_value:
            return None
        path = Path(path_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _write_breakdown_header(self) -> None:
        if self._breakdown_initialized or self._breakdown_path is None:
            return
        reward_cfg = self.evaluator
        with self._breakdown_path.open("w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "type": "header",
                        "reward_log_interval": self._reward_log_interval,
                        "reward_config": {
                            "solved_reward": reward_cfg.solved_reward,
                            "valid_reward": reward_cfg.valid_reward,
                            "invalid_build_reward": reward_cfg.invalid_build_reward,
                            "invalid_format_reward": reward_cfg.invalid_format_reward,
                            "engine_error_reward": reward_cfg.engine_error_reward,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        self._breakdown_initialized = True

    def _append_breakdown_record(self, record: dict) -> None:
        if self._breakdown_path is None:
            return
        self._write_breakdown_header()
        with self._breakdown_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _extract_step(kwargs) -> int | None:
        for key in ("global_step", "step", "trainer_step"):
            value = kwargs.get(key)
            if isinstance(value, int):
                return value
        for key in ("state", "trainer_state"):
            state = kwargs.get(key)
            if isinstance(state, dict):
                for inner_key in ("global_step", "step"):
                    value = state.get(inner_key)
                    if isinstance(value, int):
                        return value
            for inner_key in ("global_step", "step"):
                value = getattr(state, inner_key, None)
                if isinstance(value, int):
                    return value
        return None

    @staticmethod
    def _distributed_context():
        try:
            import torch.distributed as dist
        except ImportError:
            return None
        return dist if dist.is_available() and dist.is_initialized() else None

    def _aggregate_results(self, results) -> dict:
        local_payload = {
            "status_counts": Counter(result.ddar_status for result in results),
            "reward_sums": Counter(),
            "sample_count": len(results),
            "aux_signatures": {
                result.normalized_aux for result in results if result.normalized_aux
            },
        }
        for result in results:
            local_payload["reward_sums"][result.ddar_status] += result.reward

        dist = self._distributed_context()
        if dist is None:
            payloads = [local_payload]
        else:
            payloads = [None] * dist.get_world_size()
            dist.all_gather_object(payloads, local_payload)

        status_counts = Counter()
        reward_sums = Counter()
        aux_signatures = set()
        sample_count = 0
        for payload in payloads:
            status_counts.update(payload["status_counts"])
            reward_sums.update(payload["reward_sums"])
            aux_signatures.update(payload["aux_signatures"])
            sample_count += payload["sample_count"]
        return {
            "status_counts": status_counts,
            "reward_sums": reward_sums,
            "sample_count": sample_count,
            "aux_signatures": aux_signatures,
        }

    def _is_main_process(self) -> bool:
        dist = self._distributed_context()
        return dist is None or dist.get_rank() == 0

    @staticmethod
    def _log_breakdown_to_wandb(record: dict) -> None:
        try:
            import wandb
        except ImportError:
            return
        if wandb.run is None:
            return

        ratios = record["status_ratios"]
        contributions = record["reward_contributions"]
        metrics = {
            "reward_breakdown/avg_reward": record["avg_reward"],
            "reward_breakdown/samples": record["samples"],
            "reward_breakdown/aux_unique_ratio": record["aux_unique_ratio"],
            "reward_breakdown/solved_ratio": ratios["solved"],
            "reward_breakdown/valid_unsolved_ratio": ratios["valid_unsolved"],
            "reward_breakdown/build_invalid_ratio": ratios["build_invalid"],
            "reward_breakdown/format_invalid_ratio": ratios["format_invalid"],
            "reward_breakdown/engine_error_ratio": ratios["engine_error"],
        }
        metrics.update(
            {
                f"reward_breakdown/{name}_reward_contribution": value
                for name, value in contributions.items()
            }
        )
        wandb.log(metrics, commit=False)

    def _record_reward_rollout(self, results, kwargs) -> None:
        self._call_count += 1
        step = self._extract_step(kwargs)
        marker = step if step is not None else self._call_count
        if (
            self._reward_log_interval <= 0
            or marker % self._reward_log_interval != 0
            or not results
        ):
            return

        aggregate = self._aggregate_results(results)
        if marker != self._current_step:
            self._current_step = marker
            self._step_rollout_call = 0
            self._step_status_counts.clear()
            self._step_reward_sums.clear()
            self._step_sample_count = 0
            self._step_aux_signatures.clear()
        self._step_rollout_call += 1
        self._step_status_counts.update(aggregate["status_counts"])
        self._step_reward_sums.update(aggregate["reward_sums"])
        self._step_sample_count += aggregate["sample_count"]
        self._step_aux_signatures.update(aggregate["aux_signatures"])

        status_counts = self._step_status_counts
        reward_sums = self._step_reward_sums
        total = self._step_sample_count
        solved = status_counts.get("solved", 0)
        valid_unsolved = status_counts.get("unsolved", 0)
        build_invalid = status_counts.get("build_invalid", 0)
        format_invalid = status_counts.get("format_invalid", 0)
        engine_error = status_counts.get("engine_error", 0)
        aux_unique_ratio = len(self._step_aux_signatures) / total
        reward_sum = sum(reward_sums.values())
        avg_reward = reward_sum / total if total > 0 else 0.0

        # Classify the dominant cause when zero-std collapse is likely
        zero_std_cause = ""
        if solved / total >= 0.8:
            zero_std_cause = " [collapse-cause: all-solved, data may be too easy]"
        elif (valid_unsolved + build_invalid + format_invalid) / total >= 0.8:
            zero_std_cause = (
                " [collapse-cause: all-failed, exploration may be insufficient]"
            )

        record = {
            "type": "rollout",
            "scope": "step_cumulative",
            "step": marker,
            "rollout_call": self._call_count,
            "step_rollout_call": self._step_rollout_call,
            "samples": total,
            "avg_reward": avg_reward,
            "aux_unique_ratio": aux_unique_ratio,
            "status_counts": {key: status_counts.get(key, 0) for key in _STATUS_KEYS},
            "status_ratios": {
                "solved": solved / total,
                "valid_unsolved": valid_unsolved / total,
                "build_invalid": build_invalid / total,
                "format_invalid": format_invalid / total,
                "engine_error": engine_error / total,
            },
            "reward_contributions": {
                "solved": reward_sums.get("solved", 0.0) / total,
                "valid_unsolved": reward_sums.get("unsolved", 0.0) / total,
                "build_invalid": reward_sums.get("build_invalid", 0.0) / total,
                "format_invalid": reward_sums.get("format_invalid", 0.0) / total,
                "engine_error": reward_sums.get("engine_error", 0.0) / total,
            },
            "collapse_cause": zero_std_cause.strip(" []") or None,
        }
        if not self._is_main_process():
            return

        logger.info(
            "GRPO reward states at step=%s step_rollout_call=%d:"
            " solved=%.3f valid=%.3f"
            " build_invalid=%.3f format_invalid=%.3f engine_error=%.3f"
            " aux_unique_ratio=%.3f samples=%d%s",
            marker,
            self._step_rollout_call,
            solved / total,
            valid_unsolved / total,
            build_invalid / total,
            format_invalid / total,
            engine_error / total,
            aux_unique_ratio,
            total,
            zero_std_cause,
        )
        self._append_breakdown_record(record)
        self._log_breakdown_to_wandb(record)

    def __call__(self, completions=None, **kwargs) -> list[float]:
        """SWIFT-compatible __call__ that accepts completions as positional or kwarg."""
        # Handle completions passed as positional or keyword argument
        if completions is None:
            completions = kwargs.pop("completions", kwargs.pop("completion", None))

        if completions is None:
            raise ValueError("Missing 'completions' in reward function call")

        # Extract fl_problem from kwargs
        fl_problem = kwargs.pop("fl_problem", None)

        results = self.evaluate_batch(completions, fl_problem=fl_problem, **kwargs)
        self._record_reward_rollout(results, kwargs)
        return [result.reward for result in results]


orms["aux_reward"] = AuxReward
