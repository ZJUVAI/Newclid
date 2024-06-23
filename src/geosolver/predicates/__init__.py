from geosolver.predicates.collinearity import Coll, Collx, NColl
from geosolver.predicates.congruence import Cong, Cong2
from geosolver.predicates.midpoint import MidPoint
from geosolver.predicates.parallelism import Para, NPara
from geosolver.predicates.perpendicularity import Perp, NPerp

from geosolver.predicates.cyclic import Cyclic
from geosolver.predicates.circumcenter import Circumcenter

from geosolver.predicates.equal_angles import EqAngle, EqAngle6
from geosolver.predicates.equal_ratios import EqRatio, EqRatio6, EqRatio3

from geosolver.predicates.constant_length import ConstantLength
from geosolver.predicates.constant_ratio import ConstantRatio
from geosolver.predicates.constant_angle import ConstantAngle, SAngle

from geosolver.predicates.different import Diff
from geosolver.predicates.sameside import SameSide

from geosolver.predicates.triangles_similar import (
    SimtriAny,
    SimtriClock,
    SimtriReflect,
)
from geosolver.predicates.triangles_congruent import (
    ContriAny,
    ContriClock,
    ContriReflect,
)

SYMBOLIC_PREDICATES = (
    Coll,
    Collx,
    Cong,
    Cong2,
    MidPoint,
    Para,
    Perp,
    Cyclic,
    Circumcenter,
    EqAngle,
    EqAngle6,
    EqRatio,
    EqRatio6,
    EqRatio3,
    ConstantLength,
    ConstantRatio,
    ConstantAngle,
    SAngle,
    SimtriClock,
    SimtriReflect,
    SimtriAny,
    ContriClock,
    ContriReflect,
    ContriAny,
)

NUMERICAL_PREDICATES = (
    Diff,
    NColl,
    NPara,
    NPerp,
    SameSide,
)

PREDICATES = SYMBOLIC_PREDICATES + NUMERICAL_PREDICATES

NAME_TO_PREDICATE = {predicate.NAME: predicate for predicate in PREDICATES}

__all__ = [
    "PREDICATES",
    "NAME_TO_PREDICATE",
    "SYMBOLIC_PREDICATES",
    "NUMERICAL_PREDICATES",
] + [predicate.__name__ for predicate in PREDICATES]
