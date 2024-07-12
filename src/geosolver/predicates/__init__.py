from geosolver.predicates.collinearity import Coll as Coll, NColl as NColl
from geosolver.predicates.congruence import Cong as Cong, Cong2 as Cong2
from geosolver.predicates.midpoint import MidPoint as MidPoint
from geosolver.predicates.parallelism import Para as Para, NPara as NPara
from geosolver.predicates.perpendicularity import Perp as Perp, NPerp as NPerp

from geosolver.predicates.cyclic import Cyclic as Cyclic
from geosolver.predicates.circumcenter import Circumcenter as Circumcenter

from geosolver.predicates.equal_angles import EqAngle as EqAngle
from geosolver.predicates.equal_ratios import EqRatio as EqRatio, EqRatio3 as EqRatio3

from geosolver.predicates.constant_length import ConstantLength as ConstantLength
from geosolver.predicates.constant_ratio import ConstantRatio as ConstantRatio
from geosolver.predicates.constant_angle import ConstantAngle as ConstantAngle

from geosolver.predicates.different import Diff as Diff
from geosolver.predicates.sameclock import SameClock as SameClock
from geosolver.predicates.sameside import SameSide as SameSide

from geosolver.predicates.triangles_similar import (
    SimtriClock as SimtriClock,
    SimtriReflect as SimtriReflect,
)
from geosolver.predicates.triangles_congruent import (
    ContriClock as ContriClock,
    ContriReflect as ContriReflect,
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
    ContriClock,
    ContriReflect,
)

NUMERICAL_PREDICATES = (
    Diff,
    NColl,
    NPara,
    NPerp,
    SameSide,
    SameClock,
)

PREDICATES = SYMBOLIC_PREDICATES + NUMERICAL_PREDICATES

NAME_TO_PREDICATE = {predicate.NAME: predicate for predicate in PREDICATES}
