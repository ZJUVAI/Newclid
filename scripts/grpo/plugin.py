"""SWIFT plugin entrypoint for GRPO auxiliary-point rewards."""

try:
    from swift.rewards import ORM, orms
except ImportError:  # pragma: no cover - keeps local imports/testing lightweight.
    class ORM:  # type: ignore[no-redef]
        pass

    orms = {}

from newclid.training.grpo_rewards import AuxReward as _AuxReward


class AuxReward(ORM, _AuxReward):
    """SWIFT-compatible wrapper around the aux evaluator."""

    def __init__(self, *args, **kwargs):
        _AuxReward.__init__(self)


orms["aux_reward"] = AuxReward
