"""SWIFT plugin entrypoint for GRPO auxiliary-point rewards."""

import inspect
import logging

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
        _AuxReward.__init__(self)
        # Don't call ORM.__init__ as it's just a marker class

    def __call__(self, completions=None, **kwargs) -> list[float]:
        """SWIFT-compatible __call__ that accepts completions as positional or kwarg."""
        # Handle completions passed as positional or keyword argument
        if completions is None:
            completions = kwargs.pop('completions', kwargs.pop('completion', None))

        if completions is None:
            raise ValueError("Missing 'completions' in reward function call")

        # Extract fl_problem from kwargs
        fl_problem = kwargs.pop('fl_problem', None)

        # Call parent implementation
        return _AuxReward.__call__(self, completions, fl_problem=fl_problem, **kwargs)


orms["aux_reward"] = AuxReward
