"""SWIFT plugin entrypoint for GRPO auxiliary-point rewards."""

from collections import Counter
import inspect
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from swift.rewards import ORM, orms
except ImportError:  # pragma: no cover - keeps local imports/testing lightweight.
    class ORM:  # type: ignore[no-redef]
        pass

    orms = {}

from newclid.training.grpo_rewards import AuxReward as _AuxReward


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
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
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
            os.getenv("NEWCLID_GRPO_REWARD_LOG_INTERVAL", "50"),
        )
        breakdown_path = kwargs.pop(
            "reward_breakdown_path",
            os.getenv("NEWCLID_GRPO_REWARD_BREAKDOWN_PATH"),
        )
        _AuxReward.__init__(self, **kwargs)
        self._reward_log_interval = max(0, int(reward_log_interval))
        self._call_count = 0
        self._last_log_bucket = -1
        self._window_status_counts = Counter()
        self._window_reward_sums = Counter()
        self._window_sample_count = 0
        self._window_aux_signatures = set()
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

    def _record_reward_window(self, results, kwargs) -> None:
        self._call_count += 1
        self._window_status_counts.update(result.ddar_status for result in results)
        for result in results:
            self._window_reward_sums[result.ddar_status] += result.reward
        self._window_sample_count += len(results)
        self._window_aux_signatures.update(
            result.normalized_aux for result in results if result.normalized_aux
        )
        if self._reward_log_interval <= 0 or self._window_sample_count == 0:
            return

        step = self._extract_step(kwargs)
        marker = step if step is not None else self._call_count
        bucket = marker // self._reward_log_interval
        if marker <= 0 or bucket <= self._last_log_bucket:
            return

        solved = self._window_status_counts.get("solved", 0)
        valid_unsolved = self._window_status_counts.get("unsolved", 0)
        build_invalid = self._window_status_counts.get("build_invalid", 0)
        format_invalid = self._window_status_counts.get("format_invalid", 0)
        engine_error = self._window_status_counts.get("engine_error", 0)
        total = self._window_sample_count
        aux_unique_ratio = len(self._window_aux_signatures) / total if total > 0 else 0.0
        reward_sum = sum(self._window_reward_sums.values())
        avg_reward = reward_sum / total if total > 0 else 0.0

        # Classify the dominant cause when zero-std collapse is likely
        zero_std_cause = ""
        if solved / total >= 0.8:
            zero_std_cause = " [collapse-cause: all-solved, data may be too easy]"
        elif (valid_unsolved + build_invalid + format_invalid) / total >= 0.8:
            zero_std_cause = " [collapse-cause: all-failed, exploration may be insufficient]"

        logger.info(
            "GRPO reward states up to step=%s: solved=%.3f valid=%.3f build_invalid=%.3f"
            " format_invalid=%.3f engine_error=%.3f aux_unique_ratio=%.3f samples=%d%s",
            marker,
            solved / total,
            valid_unsolved / total,
            build_invalid / total,
            format_invalid / total,
            engine_error / total,
            aux_unique_ratio,
            total,
            zero_std_cause,
        )
        self._append_breakdown_record(
            {
                "type": "window",
                "step": marker,
                "samples": total,
                "avg_reward": avg_reward,
                "aux_unique_ratio": aux_unique_ratio,
                "status_counts": dict(self._window_status_counts),
                "status_ratios": {
                    "solved": solved / total,
                    "valid_unsolved": valid_unsolved / total,
                    "build_invalid": build_invalid / total,
                    "format_invalid": format_invalid / total,
                    "engine_error": engine_error / total,
                },
                "reward_contributions": {
                    "solved": self._window_reward_sums.get("solved", 0.0) / total,
                    "valid_unsolved": self._window_reward_sums.get("unsolved", 0.0)
                    / total,
                    "build_invalid": self._window_reward_sums.get(
                        "build_invalid", 0.0
                    )
                    / total,
                    "format_invalid": self._window_reward_sums.get(
                        "format_invalid", 0.0
                    )
                    / total,
                    "engine_error": self._window_reward_sums.get("engine_error", 0.0)
                    / total,
                },
                "collapse_cause": zero_std_cause.strip(" []") or None,
            }
        )
        self._window_status_counts.clear()
        self._window_reward_sums.clear()
        self._window_sample_count = 0
        self._window_aux_signatures.clear()
        self._last_log_bucket = bucket

    def __call__(self, completions=None, **kwargs) -> list[float]:
        """SWIFT-compatible __call__ that accepts completions as positional or kwarg."""
        # Handle completions passed as positional or keyword argument
        if completions is None:
            completions = kwargs.pop('completions', kwargs.pop('completion', None))

        if completions is None:
            raise ValueError("Missing 'completions' in reward function call")

        # Extract fl_problem from kwargs
        fl_problem = kwargs.pop('fl_problem', None)

        results = self.evaluate_batch(
            completions, fl_problem=fl_problem, **kwargs
        )
        self._record_reward_window(results, kwargs)
        return [result.reward for result in results]


orms["aux_reward"] = AuxReward
