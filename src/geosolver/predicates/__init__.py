from geosolver.predicates.coll import Coll
from geosolver.predicates.collx import Collx
from geosolver.predicates.para import Para
from geosolver.predicates.perp import Perp
from geosolver.predicates.eqangle import EqAngle, EqAngle6

PREDICATES = (
    Coll,
    Collx,
    Para,
    Perp,
    EqAngle,
    EqAngle6,
)

NAME_TO_PREDICATE = {predicate.NAME: predicate for predicate in PREDICATES}

__all__ = [predicate.__name__ for predicate in PREDICATES]
