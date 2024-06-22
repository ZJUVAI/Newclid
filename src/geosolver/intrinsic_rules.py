from __future__ import annotations
from enum import Enum
from typing import Optional


class IntrinsicRules(Enum):
    PARA_FROM_PERP = "i00"
    CYCLIC_FROM_CONG = "i01"
    CONG_FROM_EQRATIO = "i02"
    PARA_FROM_EQANGLE = "i03"

    POINT_ON_SAME_LINE = "i04"
    PARA_FROM_LINES = "i05"
    PERP_FROM_LINES = "i06"
    PERP_FROM_ANGLE = "i07"
    EQANGLE_FROM_LINES = "i08"
    EQANGLE_FROM_CONGRUENT_ANGLE = "i09"
    EQRATIO_FROM_PROPORTIONAL_SEGMENTS = "i10"
    CYCLIC_FROM_CIRCLE = "i11"

    ACONST_FROM_LINES = "i12"
    ACONST_FROM_ANGLE = "i13"
    SANGLE_FROM_ANGLE = "i14"
    RCONST_FROM_RATIO = "i15"

    PERP_FROM_PARA = "i16"
    EQANGLE_FROM_PARA = "i17"
    EQRATIO_FROM_CONG = "i18"
    ACONST_FROM_PARA = "i19"
    RCONST_FROM_CONG = "i20"

    SANGLE_FROM_LINES = "i21"
    SANGLE_FROM_PARA = "i22"


ALL_INTRINSIC_RULES = [rule for rule in IntrinsicRules]


def validate_disabled_rules(
    disabled_intrinsic_rules: Optional[list[str | IntrinsicRules]],
) -> list[IntrinsicRules]:
    if disabled_intrinsic_rules is None:
        disabled_intrinsic_rules = []
    return [IntrinsicRules(r) for r in disabled_intrinsic_rules]
