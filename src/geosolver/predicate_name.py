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
    COMPUTE_ANGLE = "acompute"
    COMPUTE_RATIO = "rcompute"
    # Fix_x ? What is that ?
    FIX_L = "fixl"
    FIX_C = "fixc"
    FIX_B = "fixb"
    FIX_T = "fixt"
    FIX_P = "fixp"
    # What is that also ?
    IND = "ind"
    INCI = "inci"
