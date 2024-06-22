from enum import Enum


class PredicateName(Enum):
    SIMILAR_TRIANGLE = "simtri"
    """simtri A B C P Q R - True if triangles ABC and PQR are similar under orientation-preserving transformations taking A to P, B to Q and C to R. It is equivalent to the three eqangle and eqratio predicates on the corresponding angles and sides."""
    SIMILAR_TRIANGLE_REFLECTED = "simtri2"
    """simtri2 A B C P Q R - True if triangle ABC is similar to a reflection of triangle PQR under orientation-preserving transformations taking A to the reflection of P, B to the reflection of Q and C to the reflection of R. It is equivalent to the three eqangle and eqratio predicates on the corresponding angles and sides."""
    SIMILAR_TRIANGLE_BOTH = "simtri*"
    """simtri* A B C P Q R - True if either simtri A B C P Q R or simtri2 A B C P Q R is true."""
    CONTRI_TRIANGLE = "contri"
    """contri A B C P Q R - True if triangles ABC and PQR are congruent under orientation-preserving transformations taking A to P, B to Q and C to R. It is equivalent to the three eqangle and cong predicates on the corresponding angles and sides."""
    CONTRI_TRIANGLE_REFLECTED = "contri2"
    """contri2 A B C P Q R - True if triangle ABC is congruent to a reflection of triangle PQR under orientation-preserving transformations taking A to the reflection of P, B to the reflection of Q and C to the reflection of R. It is equivalent to the three eqangle and cong predicates on the corresponding angles and sides."""
    CONTRI_TRIANGLE_BOTH = "contri*"
    """contri* A B C P Q R - True if either contri A B C P Q R or contri2 A B C P Q R is true."""
    CONSTANT_ANGLE = "aconst"
    """aconst A B C D r - True if the angle needed to go from line AB to line CD, around the intersection point, on the clockwise direction is r, in radians. The syntax of y should be a fraction of pi, as 2pi/3 for an angle of 120 degrees."""
    CONSTANT_RATIO = "rconst"
    """rconst A B C D r - True if AB/CD=r, r should be given with numerator and denominator separated by /, as in 2/3."""
    CONSTANT_LENGTH = "lconst"
    """rconst A B l - True if AB=l, l should be given as a float."""
    COMPUTE_ANGLE = "acompute"
    COMPUTE_RATIO = "rcompute"
    S_ANGLE = "s_angle"
    """s_angle A B C y - True if the angle ABC, with vertex at B and going counter clockwise from A to C, is y in degrees. The syntax of y should be as 123o for an angle of 123 degrees."""
    # Numericals
    SAMESIDE = "sameside"
    DIFFERENT = "diff"
    """diff A B - True is points A and B are NOT the same. It can only be numerically checked."""
    NON_COLLINEAR = "ncoll"
    """ncoll A B C - True if all the 3 (or more) points on the arguments do NOT lie on the same line. It can only be numerically checked."""
    NON_PARALLEL = "npara"
    """npara A B C D - True if lines AB and CD are NOT parallel. It can only be numerically checked (the check uses the angular coefficient of the equations of the lines)."""
    NON_PERPENDICULAR = "nperp"
    """nperp A B C D - True if lines AB and CD are NOT perpendicular."""
    # Fix_x ? What is that ?
    FIX_L = "fixl"
    FIX_C = "fixc"
    FIX_B = "fixb"
    FIX_T = "fixt"
    FIX_P = "fixp"
    # What is that also ?
    IND = "ind"
    INCI = "inci"


NUMERICAL_PREDICATES = (
    PredicateName.NON_COLLINEAR,
    PredicateName.NON_PARALLEL,
    PredicateName.NON_PERPENDICULAR,
    PredicateName.DIFFERENT,
    PredicateName.SAMESIDE,
)
