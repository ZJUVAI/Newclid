from geosolver.predicates.coll import Coll
from geosolver.predicates.coll import Collx
from geosolver.predicates.cong import Cong, Cong2
from geosolver.predicates.midpoint import MidPoint
from geosolver.predicates.para import Para
from geosolver.predicates.perp import Perp

from geosolver.predicates.cyclic import Cyclic
from geosolver.predicates.circumcenter import Circumcenter

from geosolver.predicates.eqangle import EqAngle, EqAngle6
from geosolver.predicates.eqratio import EqRatio, EqRatio6, EqRatio3

from geosolver.predicates.constant_length import ConstantLength
from geosolver.predicates.constant_ratio import ConstantRatio
from geosolver.predicates.constant_angle import ConstantAngle, SAngle

PREDICATES = (
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
)

NAME_TO_PREDICATE = {predicate.NAME: predicate for predicate in PREDICATES}

__all__ = ["NAME_TO_PREDICATE", "PREDICATES"] + [
    predicate.__name__ for predicate in PREDICATES
]
