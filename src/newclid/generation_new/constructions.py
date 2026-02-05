"""
Construction type constants.

Defines the different types of geometric constructions available.
"""

# Basic constructions that create initial shapes
BASIC = [
    'segment',
    'triangle',
    'triangle12',
    'r_triangle',
    'iso_triangle',
    # 'iso_triangle0',
    'ieq_triangle',
    'risos',
    'quadrangle',
    'rectangle',
    'isquare',
    'trapezoid',
    'r_trapezoid',
    'iso_trapezoid',
    'eq_quadrangle',
    'eqdia_quadrangle',
    'pentagon',
]

# Free point construction
BASIC_FREE = [
    'free',
]

# Intersection-based constructions (create points from intersecting objects)
INTERSECT = [
    'angle_bisector',  # => bisect => LineNum
    'angle_mirror',    # => amirror => LineNum
    'eqdistance',      # => circle => CircleNum
    'on_line',         # => line => LineNum
    'on_aline',        # => aline => LineNum
    # 'on_aline0',     # => aline => LineNum
    'on_bline',        # => bline => LineNum
    'on_pline',        # => pline => LineNum
    # 'on_pline0',     # => pline => LineNum
    'on_tline',        # => tline => LineNum
    'on_dia',          # => dia => CircleNum
    'on_circle',       # => circle => CircleNum
    # 'eqangle3',        # => eqangle3 => CircleNum
    'on_circum',       # => cyclic => CircleNum
    'eqratio',         # => eqratio => CircleNum
    # 'eqratio6',        # => eqratio6 => LineNum / CircleNum
    'lc_tangent',      # => tline => LineNum
    # TODO: double check. do we need this?
    # 'rconst',        # => rconst => CircleNum
    # 'rconst2',       # => rconst2 => LineNum / CircleNum
    # 'aconst',        # => aconst => LineNum (usually in goal, may not need)
    # 's_angle',         # => s_angle => LineNum
    # 'lconst',        # => lconst => CircleNum
]

# Other constructions (single-point constructions)
OTHER = [
    'circle',
    # 'circumcenter',
    'eq_triangle',
    # 'eqangle2',
    'foot',
    'incenter',
    'incenter2',
    'excenter',
    'excenter2',
    'centroid',
    # 'ninepoints',
    'intersection_cc',
    'intersection_lc',
    'intersection_ll',
    'intersection_lp',
    'intersection_lt',
    'intersection_pp',
    'intersection_tt',
    'midpoint',
    'mirror',
    # 'nsquare',
    'orthocenter',
    'parallelogram',
    # 'psquare',
    'reflect',
    # 'shift',
    'square',
    # '2l1c',
    # 'e5128',
    # '3peq',
    # 'trisect',
    # 'trisegment',
    'cc_tangent',
    'tangent',
    # 'iso_triangle_vertex',
    # 'iso_triangle_vertex_angle',
]
