from geosolver.predicates.coll import Coll
from geosolver.predicates.coll import Collx
from geosolver.predicates.cong import Cong, Cong2
from geosolver.predicates.cyclic import Cyclic
from geosolver.predicates.circumcenter import Circumcenter
from geosolver.predicates.midpoint import MidPoint
from geosolver.predicates.para import Para
from geosolver.predicates.perp import Perp
from geosolver.predicates.eqangle import EqAngle, EqAngle6
from geosolver.predicates.eqratio import EqRatio, EqRatio6, EqRatio3

PREDICATES = (
    Coll,
    Collx,
    Cong,
    Cong2,
    MidPoint,
    Cyclic,
    Circumcenter,
    Para,
    Perp,
    EqAngle,
    EqAngle6,
    EqRatio,
    EqRatio6,
    EqRatio3,
)

NAME_TO_PREDICATE = {predicate.NAME: predicate for predicate in PREDICATES}

__all__ = [predicate.__name__ for predicate in PREDICATES]
