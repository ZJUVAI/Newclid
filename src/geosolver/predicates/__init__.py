from geosolver.predicates.collinearity import Coll, NColl
from geosolver.predicates.congruence import Cong, Cong2
from geosolver.predicates.midpoint import MidPoint
from geosolver.predicates.parallelism import Para, NPara
from geosolver.predicates.perpendicularity import Perp, NPerp

from geosolver.predicates.cyclic import Cyclic
from geosolver.predicates.circumcenter import Circumcenter

from geosolver.predicates.equal_angles import EqAngle
from geosolver.predicates.equal_ratios import EqRatio, EqRatio3

from geosolver.predicates.constant_length import ConstantLength
from geosolver.predicates.constant_ratio import ConstantRatio
from geosolver.predicates.constant_angle import ConstantAngle

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
from geosolver.predicates.predicate import Predicate as Predicate

SYMBOLIC_PREDICATES = (
    Coll,
    Cong,
    Cong2,
    MidPoint,
    Para,
    Perp,
    Cyclic,
    Circumcenter,
    EqAngle,
    EqRatio,
    EqRatio3,
    ConstantLength,
    ConstantRatio,
    ConstantAngle,
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
