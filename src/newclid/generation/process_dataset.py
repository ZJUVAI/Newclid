import re
from typing import Dict, Any, List, Tuple, Optional, Callable, Mapping
import json
from tqdm import tqdm
import random

constr2premise = {
    "angle_bisector": [["angle_bisector x a b c", ["x", "a", "b", "c"], [["eqangle", "b", "a", "b", "x", "b", "x", "b", "c"]]]],
    "angle_mirror": [["angle_mirror x a b c", ["x", "a", "b", "c"], [["eqangle", "b", "a", "b", "c", "b", "c", "b", "x"]]]],
    "circle": [["circle x a b c", ["x", "a", "b", "c"], [["cong", "x", "a", "x", "b"], ["cong", "x", "b", "x", "c"]]]],
    "circumcenter": [["circumcenter x a b c", ["x", "a", "b", "c"], [["cong", "x", "a", "x", "b"], ["cong", "x", "b", "x", "c"]]]],
    "eq_quadrangle": [["eq_quadrangle a b c d", ["a", "b", "c", "d"], [["cong", "d", "a", "b", "c"]]]],
    "iso_trapezoid": [["iso_trapezoid a b c d", ["a", "b", "c", "d"], [["para", "d", "c", "a", "b"], ["cong", "d", "a", "b", "c"]]]],
    "eq_triangle": [["eq_triangle x b c", ["x", "b", "c"], [["cong", "x", "b", "b", "c"], ["cong", "b", "c", "c", "x"]]]],
    "eqangle2": [["eqangle2 x a b c", ["x", "a", "b", "c"], [["eqangle", "a", "b", "a", "x", "c", "x", "c", "b"]]]],
    "eqdia_quadrangle": [["eqdia_quadrangle a b c d", ["a", "b", "c", "d"], [["cong", "d", "b", "a", "c"]]]],
    "eqdistance": [["eqdistance x a b c", ["x", "a", "b", "c"], [["cong", "x", "a", "b", "c"]]]],
    "foot": [["foot x a b c", ["x", "a", "b", "c"], [["perp", "x", "a", "b", "c"], ["coll", "x", "b", "c"]]]],
    "free": [["free a", ["a"], []]],
    "incenter": [["incenter x a b c", ["x", "a", "b", "c"], [["eqangle", "a", "b", "a", "x", "a", "x", "a", "c"], ["eqangle", "c", "a", "c", "x", "c", "x", "c", "b"]]]],
    "incenter2": [["incenter2 x y z i a b c", ["x", "y", "z", "i", "a", "b", "c"], [["eqangle", "a", "b", "a", "i", "a", "i", "a", "c"], ["eqangle", "c", "a", "c", "i", "c", "i", "c", "b"], ["coll", "x", "b", "c"], ["perp", "i", "x", "b", "c"], ["coll", "y", "c", "a"], ["perp", "i", "y", "c", "a"], ["coll", "z", "a", "b"], ["perp", "i", "z", "a", "b"]]]],
    "excenter": [["excenter x a b c", ["x", "a", "b", "c"], [["eqangle", "a", "b", "a", "x", "a", "x", "a", "c"], ["eqangle", "c", "a", "c", "x", "c", "x", "c", "b"]]]],
    "excenter2": [["excenter2 x y z i a b c", ["x", "y", "z", "i", "a", "b", "c"], [["eqangle", "a", "b", "a", "i", "a", "i", "a", "c"], ["eqangle", "c", "a", "c", "i", "c", "i", "c", "b"], ["coll", "x", "b", "c"], ["perp", "i", "x", "b", "c"], ["coll", "y", "c", "a"], ["perp", "i", "y", "c", "a"], ["coll", "z", "a", "b"], ["perp", "i", "z", "a", "b"]]]],
    "centroid": [["centroid x y z i a b c", ["x", "y", "z", "i", "a", "b", "c"], [["coll", "x", "b", "c"], ["cong", "x", "b", "x", "c"], ["coll", "y", "c", "a"], ["cong", "y", "c", "y", "a"], ["coll", "z", "a", "b"], ["cong", "z", "a", "z", "b"], ["coll", "a", "x", "i"], ["coll", "b", "y", "i"]]]],
    "ninepoints": [["ninepoints x y z i a b c", ["x", "y", "z", "i", "a", "b", "c"], [["coll", "x", "b", "c"], ["cong", "x", "b", "x", "c"], ["coll", "y", "c", "a"], ["cong", "y", "c", "y", "a"], ["coll", "z", "a", "b"], ["cong", "z", "a", "z", "b"], ["cong", "i", "x", "i", "y"], ["cong", "i", "y", "i", "z"]]]],
    "intersection_cc": [["intersection_cc x o w a", ["x", "o", "w", "a"], [["cong", "o", "a", "o", "x"], ["cong", "w", "a", "w", "x"]]]],
    "intersection_lc": [["intersection_lc x a o b", ["x", "a", "o", "b"], [["coll", "x", "a", "b"], ["cong", "o", "b", "o", "x"]]]],
    "intersection_ll": [["intersection_ll x a b c d", ["x", "a", "b", "c", "d"], [["coll", "x", "a", "b"], ["coll", "x", "c", "d"]]]],
    "intersection_lp": [["intersection_lp x a b c m n", ["x", "a", "b", "c", "m", "n"], [["coll", "x", "a", "b"], ["para", "c", "x", "m", "n"]]]],
    "intersection_lt": [["intersection_lt x a b c d e", ["x", "a", "b", "c", "d", "e"], [["coll", "x", "a", "b"], ["perp", "x", "c", "d", "e"]]]],
    "intersection_pp": [["intersection_pp x a b c d e f", ["x", "a", "b", "c", "d", "e", "f"], [["para", "x", "a", "b", "c"], ["para", "x", "d", "e", "f"]]]],
    "intersection_tt": [["intersection_tt x a b c d e f", ["x", "a", "b", "c", "d", "e", "f"], [["perp", "x", "a", "b", "c"], ["perp", "x", "d", "e", "f"]]]],
    "iso_triangle": [["iso_triangle a b c", ["a", "b", "c"], [["eqangle", "b", "a", "b", "c", "c", "b", "c", "a"], ["cong", "a", "b", "a", "c"]]]],
    "lc_tangent": [["lc_tangent x a o", ["x", "a", "o"], [["perp", "a", "x", "a", "o"]]]],
    "midpoint": [["midpoint x a b", ["x", "a", "b"], [["midp", "x", "a", "b"]]]],
    "mirror": [["mirror x a b", ["x", "a", "b"], [["coll", "x", "a", "b"], ["cong", "b", "a", "b", "x"]]]],
    "nsquare": [["nsquare x a b", ["x", "a", "b"], [["cong", "x", "a", "a", "b"], ["perp", "x", "a", "a", "b"]]]],
    "on_aline": [["on_aline x a b c d e", ["x", "a", "b", "c", "d", "e"], [["eqangle", "a", "x", "a", "b", "d", "c", "d", "e"]]]],
    "on_bline": [["on_bline x a b", ["x", "a", "b"], [["cong", "x", "a", "x", "b"], ["eqangle", "a", "x", "a", "b", "b", "a", "b", "x"]]]],
    "on_circle": [["on_circle x o a", ["x", "o", "a"], [["cong", "o", "x", "o", "a"]]]],
    "on_line": [["on_line x a b", ["x", "a", "b"], [["coll", "x", "a", "b"]]]],
    "on_pline": [["on_pline x a b c", ["x", "a", "b", "c"], [["para", "x", "a", "b", "c"]]]],
    "on_tline": [["on_tline x a b c", ["x", "a", "b", "c"], [["perp", "x", "a", "b", "c"]]]],
    "orthocenter": [["orthocenter x a b c", ["x", "a", "b", "c"], [["perp", "x", "a", "b", "c"], ["perp", "x", "b", "c", "a"]]]],
    "parallelogram": [["parallelogram a b c x", ["a", "b", "c", "x"], [["para", "a", "b", "c", "x"], ["para", "a", "x", "b", "c"]]]],
    "pentagon": [["pentagon a b c d e", ["a", "b", "c", "d", "e"], []]],
    "psquare": [["psquare x a b", ["x", "a", "b"], [["cong", "x", "a", "a", "b"], ["perp", "x", "a", "a", "b"]]]],
    "quadrangle": [["quadrangle a b c d", ["a", "b", "c", "d"], []]],
    "r_trapezoid": [["r_trapezoid a b c d", ["a", "b", "c", "d"], [["para", "a", "b", "c", "d"], ["perp", "a", "b", "a", "d"]]]],
    "r_triangle": [["r_triangle a b c", ["a", "b", "c"], [["perp", "a", "b", "a", "c"]]]],
    "rectangle": [["rectangle a b c d", ["a", "b", "c", "d"], [["perp", "a", "b", "b", "c"], ["para", "a", "b", "c", "d"], ["para", "a", "d", "b", "c"]]]],
    "reflect": [["reflect x a b c", ["x", "a", "b", "c"], [["cong", "b", "a", "b", "x"], ["cong", "c", "a", "c", "x"]]]],
    "risos": [["risos a b c", ["a", "b", "c"], [["perp", "a", "b", "a", "c"], ["cong", "a", "b", "a", "c"]]]],
    "segment": [["segment a b", ["a", "b"], []]],
    "shift": [["shift x b c d", ["x", "b", "c", "d"], [["cong", "x", "b", "c", "d"], ["cong", "x", "c", "b", "d"]]]],
    "square": [["square a b x y", ["a", "b", "x", "y"], [["perp", "a", "b", "b", "x"], ["cong", "a", "b", "b", "x"], ["para", "a", "b", "x", "y"], ["para", "a", "y", "b", "x"]]]],
    "isquare": [["isquare a b c d", ["a", "b", "c", "d"], [["perp", "a", "b", "b", "c"], ["cong", "a", "b", "b", "c"], ["para", "a", "b", "c", "d"], ["para", "a", "d", "b", "c"]]]],
    "trapezoid": [["trapezoid a b c d", ["a", "b", "c", "d"], [["para", "a", "b", "c", "d"]]]],
    "triangle": [["triangle a b c", ["a", "b", "c"], []]],
    "triangle12": [["triangle12 a b c", ["a", "b", "c"], [["rconst", "a", "b", "a", "c", "1/2"]]]],
    "2l1c": [["2l1c x y z i a b c o", ["x", "y", "z", "i", "a", "b", "c", "o"], [["coll", "x", "a", "c"], ["coll", "y", "b", "c"], ["cong", "o", "a", "o", "z"], ["coll", "i", "o", "z"], ["cong", "i", "x", "i", "y"], ["cong", "i", "y", "i", "z"], ["perp", "i", "x", "a", "c"], ["perp", "i", "y", "b", "c"]]]],
    "e5128": [["e5128 x y a b c d", ["x", "y", "a", "b", "c", "d"], [["cong", "c", "b", "c", "x"], ["coll", "y", "a", "b"], ["coll", "x", "y", "d"], ["eqangle", "a", "b", "a", "d", "x", "a", "x", "y"]]]],
    "3peq": [["3peq x y z a b c", ["x", "y", "z", "a", "b", "c"], [["coll", "z", "b", "c"], ["coll", "x", "a", "b"], ["coll", "y", "a", "c"], ["coll", "x", "y", "z"], ["cong", "z", "x", "z", "y"]]]],
    "trisect": [["trisect x y a b c", ["x", "y", "a", "b", "c"], [["coll", "x", "a", "c"], ["coll", "y", "a", "c"], ["eqangle", "b", "a", "b", "x", "b", "x", "b", "y"], ["eqangle", "b", "x", "b", "y", "b", "y", "b", "c"]]]],
    "trisegment": [["trisegment x y a b", ["x", "y", "a", "b"], [["coll", "x", "a", "b"], ["coll", "y", "a", "b"], ["cong", "x", "a", "x", "y"], ["cong", "y", "x", "y", "b"]]]],
    "on_dia": [["on_dia x a b", ["x", "a", "b"], [["perp", "x", "a", "x", "b"]]]],
    "ieq_triangle": [["ieq_triangle a b c", ["a", "b", "c"], [["cong", "a", "b", "b", "c"], ["cong", "b", "c", "c", "a"]]]],
    "cc_tangent": [["cc_tangent x y z i o a w b", ["x", "y", "z", "i", "o", "a", "w", "b"], [["cong", "o", "x", "o", "a"], ["cong", "w", "y", "w", "b"], ["perp", "x", "o", "x", "y"], ["perp", "y", "w", "y", "x"], ["cong", "o", "z", "o", "a"], ["cong", "w", "i", "w", "b"], ["perp", "z", "o", "z", "i"], ["perp", "i", "w", "i", "z"]]]],
    "eqangle3": [["eqangle3 x a b d e f", ["x", "a", "b", "d", "e", "f"], [["eqangle", "x", "a", "x", "b", "d", "e", "d", "f"]]]],
    "tangent": [["tangent x y a o b", ["x", "y", "a", "o", "b"], [["cong", "o", "x", "o", "b"], ["perp", "a", "x", "o", "x"], ["cong", "o", "y", "o", "b"], ["perp", "a", "y", "o", "y"]]]],
    "on_circum": [["on_circum x a b c", ["x", "a", "b", "c"], [["cyclic", "a", "b", "c", "x"]]]],
    "on_pline0": [["on_pline0 x a b c", ["x", "a", "b", "c"], [["para", "x", "a", "b", "c"]]]],
    "iso_triangle0": [["iso_triangle0 a b c", ["a", "b", "c"], [["cong", "a", "b", "a", "c"]]]],
    "iso_triangle_vertex": [["iso_triangle_vertex x b c", ["x", "b", "c"], [["cong", "x", "b", "x", "c"]]]],
    "iso_triangle_vertex_angle": [["iso_triangle_vertex_angle x b c", ["x", "b", "c"], [["eqangle", "x", "b", "b", "c", "b", "c", "x", "c"]]]],
    "on_aline0": [["on_aline0 x a b c d e f g", ["x", "a", "b", "c", "d", "e", "f", "g"], [["eqangle", "a", "b", "c", "d", "e", "f", "g", "x"]]]],
    "eqratio": [["eqratio x a b c d e f g", ["x", "a", "b", "c", "d", "e", "f", "g"], [["eqratio", "a", "b", "c", "d", "e", "f", "g", "x"]]]],
    "eqratio6": [["eqratio6 x a c e f g h", ["x", "a", "c", "e", "f", "g", "h"], [["eqratio", "a", "x", "c", "x", "e", "f", "g", "h"]]]],
    "rconst": [["rconst a b c x r", ["a", "b", "c", "x", "r"], [["rconst", "a", "b", "c", "x", "r"]]]],
    "rconst2": [["rconst2 x a b r", ["x", "a", "b", "r"], [["rconst", "x", "a", "x", "b", "r"]]]],
    "aconst": [["aconst a b c x r", ["a", "b", "c", "x", "r"], [["aconst", "a", "b", "c", "x", "r"]]]],
    "s_angle": [["s_angle a b x y", ["a", "b", "x", "y"], [["aconst", "a", "b", "b", "x", "y"]]]],
    "lconst": [["lconst x a l", ["x", "a", "l"], [["lconst", "x", "a", "l"]]]], "between_bound": [["between_bound x a b", ["x", "a", "b"], [["coll", "x", "a", "b"]]]],
}

constr2nature = {
    'angle_bisector': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Place point {X} on the angle bisector of ∠{A}{B}{C}. ',
            'Construct point {X} such that it lies on the bisector of angle {A}{B}{C}. ',
            'Let {X} be a point located on the ray that bisects ∠{A}{B}{C}. ',
            'Point {X} is chosen to lie on the angle bisector emanating from vertex {B} of ∠{A}{B}{C}. ',
            'Let {B}{X} be the bisector of ∠{A}{B}{C}. ',
            'Let {X} be a point on the internal bisector of angle at {B} formed by points {A}, {B}, {C}. ',
            'Place {X} on the locus of points equidistant from rays {B}{A} and {B}{C}. ',
            'Construct point {X} lying on the angle bisector from {B} in triangle {A}{B}{C} (or its extension). ',
            'Let {X} be situated on the ray starting at {B} that splits ∠{A}{B}{C} into two equal angles. ',
            'Point {X} lies on the line from {B} that makes equal angles with sides {B}{A} and {B}{C}. ',
        ],
    },
    'angle_mirror': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Construct point {X} such that segment {B}{C} is the angle bisector of ∠{A}{B}{X}. ',
            'Place {X} so that {B}{C} bisects the angle ∠{A}{B}{X}. ',
            'Let {X} be the point for which ray {B}{C} is the bisector of angle at {B} between {A} and {X}. ',
            'Construct {X} such that ∠{A}{B}{C} = ∠{C}{B}{X}. ',
            'Point {X} is positioned so that {B}{C} acts as the angle bisector in ∠{A}{B}{X}. ',
            'Build {X} symmetrically to {A} with respect to the ray {B}{C}. ',
            'Let {X} be the reflection of point {A} over the angle bisector {B}{C}. ',
            'Construct point {X} so that {A} and {X} are symmetric with respect to the line {B}{C}. ',
            'Place {X} such that the ray {B}{C} splits ∠{A}{B}{X} into two congruent angles. ',
            'Point {X} is chosen so that {B} sees {A} and {X} under the same angle on both sides of {B}{C}. ',
        ],
    },
    'circle': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Let {X} be the center of the circle passing through points {A}, {B}, and {C}. ',
            'Construct {X} as the circumcenter of triangle {A}{B}{C}. ',
            'Place {X} as the center of the unique circle through {A}, {B}, and {C}. ',
            'Let {X} be the point equidistant from {A}, {B}, and {C}. ',
            'Construct the circumcenter {X} of △{A}{B}{C}. ',
            'Point {X} is the intersection of the perpendicular bisectors of segments {A}{B}, {B}{C}, and {C}{A}. ',
            'Let {X} be the center of the circle on which points {A}, {B}, and {C} lie. ',
            'Construct {X} such that {X}{A} = {X}{B} = {X}{C}. ',
            'Place {X} as the center of the circumcircle of triangle {A}{B}{C}. ',
            'Let points {A}, {B}, and {C} lie on the circle with center {X}. ',
        ],
    },
    'eq_quadrangle': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Construct quadrilateral {A}{B}{C}{D} with opposite sides equal: {A}{B} = {C}{D} and {B}{C} = {D}{A}. ',
            'Form quadrilateral {A}{B}{C}{D} such that {B}{C} = {A}{D} and {A}{B} = {D}{C}. ',
            'Build a quadrilateral {A}{B}{C}{D} having equal pairs of opposite sides. ',
            'Construct {A}{B}{C}{D} as a quadrilateral with {B}{C} ≅ {A}{D} and {A}{B} ≅ {D}{C}. ',
            'Let {A}{B}{C}{D} be a quadrilateral whose opposite sides are equal in length. ',
            'Form quadrilateral {A}{B}{C}{D} with {A}{B} = {C}{D} and {B}{C} = {A}{D}. ',
            'Construct an equilateral quadrilateral {A}{B}{C}{D} (opposite sides equal, not necessarily parallel). ',
            'Make quadrilateral {A}{B}{C}{D} with both pairs of opposite sides of equal length. ',
            'Build {A}{B}{C}{D} such that the side opposite {B}{C} equals {B}{C} in length, i.e., {A}{D} = {B}{C}. ',
            'Construct quadrilateral {A}{B}{C}{D} where the opposite sides {B}{C} and {A}{D} are congruent (and typically the other pair as well in standard interpretation). ',
        ],
    },
    'iso_trapezoid': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Construct isosceles trapezoid {A}{B}{C}{D} with parallel bases {A}{B} and {C}{D} and equal non-parallel legs. ',
            'Form an isosceles trapezoid {A}{B}{C}{D} having {A}{B} ∥ {C}{D} and {A}{D} = {B}{C}. ',
            'Build trapezoid {A}{B}{C}{D} with {A}{B} parallel to {C}{D} and equal legs {A}{D} = {B}{C}. ',
            'Construct isosceles trapezoid {A}{B}{C}{D} with bases {A}{B}, {C}{D} and non-parallel sides equal. ',
            'Let {A}{B}{C}{D} be an isosceles trapezoid with {A}{B} ∥ {C}{D} and {A}{D} ≅ {B}{C}. ',
            'Make a symmetric trapezoid {A}{B}{C}{D} with parallel sides {A}{B} and {C}{D} and equal legs. ',
            'Construct trapezoid {A}{B}{C}{D} having exactly one pair of parallel sides {A}{B} ∥ {C}{D} and equal non-parallel sides. ',
            'Form isosceles trapezoid {A}{B}{C}{D} with longer/shorter base {A}{B} parallel to {C}{D} and equal legs. ',
            'Build {A}{B}{C}{D} as an isosceles trapezoid with bases {A}{B} and {C}{D}. ',
            'Construct a trapezoid {A}{B}{C}{D} with {A}{B} ∥ {C}{D}, {A}{D} = {B}{C}, and base angles equal. ',
        ],
    },

    'eq_triangle': {
        'points': ['X', 'B', 'C'],
        'candidates': [
            'Triangle {X}{B}{C} is equilateral. ',
            '{X}{B}{C} is an equilateral triangle. ',
            '{X}{B} = {X}{C} = {B}{C}. ',
            'Point {X} is constructed so that △{X}{B}{C} is equilateral. ',
            'All sides of triangle {X}{B}{C} are equal. ',
            '{X} is a vertex of the equilateral triangle on base {B}{C}. ',
            'Triangle {X}{B}{C} has all sides congruent. ',
            '{X} is placed such that {X}{B} = {X}{C} = {B}{C}. ',
            '△{X}{B}{C} is equilateral. ',
            'The triangle formed by {X}, {B}, and {C} is equilateral. ',
        ],
    },
    'eqangle2': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Point {X} is constructed so that the quadrilateral {X}{A}{B}{C} has equal opposite angles at {A} and {C}, specifically angle {B}{A}{X} equals angle {X}{C}{B}. ',
            'The point {X} forms a quadrilateral {X}{A}{B}{C} where the angles at vertices {A} and {C} are equal, with ∠{B}{A}{X} = ∠{X}{C}{B}. ',
            'Construct {X} such that in quadrilateral {X}{A}{B}{C}, the opposite angles ∠{B}{A}{X} and ∠{X}{C}{B} are congruent. ',
            '{X} is positioned to ensure that quadrilateral {X}{A}{B}{C} features equal angles at {A} and {C}, namely ∠{B}{A}{X} and ∠{X}{C}{B}. ',
            'The construction places {X} so that ∠{B}{A}{X} in quadrilateral {X}{A}{B}{C} matches ∠{X}{C}{B}. ',
            'Point {X} creates a quadrilateral {X}{A}{B}{C} with congruent opposite angles ∠{B}{A}{X} and ∠{X}{C}{B}. ',
            'In the quadrilateral formed by {X}, {A}, {B}, and {C}, the angles at {A} and {C} are made equal through the placement of {X}. ',
            '{X} is determined such that the angle at {A} between {B}, {A}, {X} equals the angle at {C} between {X}, {C}, {B} in quadrilateral {X}{A}{B}{C}. ',
            'The point {X} ensures equality between the opposite angles of quadrilateral {X}{A}{B}{C}, specifically those at {A} and {C}. ',
            'Construct {X} to form quadrilateral {X}{A}{B}{C} where ∠{B}{A}{X} is congruent to ∠{X}{C}{B}. ',
        ],
    },
    'eqdia_quadrangle': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Quadrilateral {A}{B}{C}{D} is constructed with equal diagonals, such that the length of {A}{C} equals the length of {B}{D}. ',
            'The quadrilateral formed by points {A}, {B}, {C}, {D} has diagonals {A}{C} and {B}{D} of equal length. ',
            'Construct quadrilateral {A}{B}{C}{D} where the diagonals {A}{C} and {B}{D} are congruent. ',
            'Points {A}, {B}, {C}, {D} form a quadrilateral with equal diagonals connecting {A} to {C} and {B} to {D}. ',
            'The construction of quadrilateral {A}{B}{C}{D} ensures that diagonal {A}{C} matches the length of diagonal {B}{D}. ',
            'Quadrilateral {A}{B}{C}{D} features diagonals {A}{C} and {B}{D} that are of the same length. ',
            'In quadrilateral {A}{B}{C}{D}, the lengths of the diagonals from {A} to {C} and from {B} to {D} are equal. ',
            'Form quadrilateral {A}{B}{C}{D} such that {A}{C} = {B}{D} in terms of distance. ',
            'The quadrilateral with vertices {A}, {B}, {C}, {D} has congruent diagonals {A}{C} and {B}{D}. ',
            'Construct the quadrilateral {A}{B}{C}{D} where the diagonal between {A} and {C} equals the diagonal between {B} and {D}. ',
        ],
    },
    'eqdistance': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Point {X} is constructed such that the distance from {X} to {A} equals the distance from {B} to {C}. ',
            'The position of {X} ensures that {X}{A} matches the length of {B}{C}. ',
            'Construct {X} where the segment {X}{A} is equal in length to {B}{C}. ',
            '{X} is placed at a distance from {A} that is the same as the distance between {B} and {C}. ',
            'The construction determines {X} so that the length {X}{A} equals {B}{C}. ',
            'Point {X} satisfies the condition that its distance to {A} is congruent to the segment {B}{C}. ',
            '{X} is such that the distance {X}{A} is equal to the given distance {B}{C}. ',
            'Locate {X} where {X}{A} = {B}{C} in terms of length. ',
            'The point {X} is constructed with {X}{A} matching the length of {B}{C}. ',
            '{X} lies at a distance from {A} equal to that between {B} and {C}. ',
        ],
    },
    'foot': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Point {X} is the foot of the perpendicular from {A} to the line through {B} and {C}. ',
            'Construct {X} as the projection of {A} onto the line {B}{C}. ',
            '{X} is the point on line {B}{C} where the perpendicular from {A} meets it. ',
            'The construction places {X} as the foot of the perpendicular dropped from {A} to line {B}{C}. ',
            '{X} marks the intersection of the perpendicular from {A} with the line connecting {B} and {C}. ',
            'Point {X} is determined as the orthogonal projection of {A} onto line {B}{C}. ',
            'From {A}, draw a perpendicular to line {B}{C}, meeting at {X}. ',
            '{X} is the closest point on line {B}{C} to {A}, being the foot of the perpendicular. ',
            'Construct the foot {X} of the perpendicular from point {A} to the line {B}{C}. ',
            'The point {X} lies on {B}{C} such that {A}{X} is perpendicular to {B}{C}. ',
        ],
    },
    'free': {
        'points': ['A'],
        'candidates': [
            'Point {A} is an arbitrary point in the plane. ',
            'Construct a free point {A} with no specific constraints. ',
            '{A} is chosen as an arbitrary point. ',
            'Introduce point {A} freely without restrictions. ',
            'Point {A} is selected arbitrarily. ',
            '{A} serves as a free point in the construction. ',
            'Construct arbitrary point {A}. ',
            'Point {A} is placed freely in the configuration. ',
            '{A} is an unconstrained, arbitrary point. ',
            'Select point {A} as a free element. ',
        ],
    },
    'incenter': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Point {X} is the incenter of triangle {A}{B}{C}. ',
            'Construct {X} as the center of the incircle of triangle {A}{B}{C}. ',
            '{X} is the intersection point of the angle bisectors in triangle {A}{B}{C}. ',
            'The incenter {X} of triangle {A}{B}{C} is the point equidistant from all sides. ',
            '{X} marks the incenter where the angle bisectors of triangle {A}{B}{C} meet. ',
            'Construct the incenter {X} for triangle with vertices {A}, {B}, {C}. ',
            'Point {X} is the center of the circle tangent to all three sides of triangle {A}{B}{C}. ',
            'In triangle {A}{B}{C}, {X} is the incenter formed by the concurrence of angle bisectors. ',
            '{X} serves as the incenter of triangle {A}{B}{C}, equidistant to the sides. ',
            'The point {X} is constructed as the incenter of triangle {A}{B}{C}. ',
        ],
    },
    'incenter2': {
        'points': ['X', 'Y', 'Z', 'I', 'A', 'B', 'C'],
        'candidates': [
            'Point {I} is the incenter of triangle {A}{B}{C}, with the incircle touching side {B}{C} at {X}, {C}{A} at {Y}, and {A}{B} at {Z}. ',
            'Construct {I} as the incenter of triangle {A}{B}{C}, where the points of tangency are {X} on {B}{C}, {Y} on {C}{A}, and {Z} on {A}{B}. ',
            'The incenter {I} of triangle {A}{B}{C} has its incircle tangent to {B}{C} at {X}, to {C}{A} at {Y}, and to {A}{B} at {Z}. ',
            '{I} is positioned as the incenter of triangle {A}{B}{C}, with tangency points {X}, {Y}, {Z} on sides {B}{C}, {C}{A}, {A}{B} respectively. ',
            'In triangle {A}{B}{C}, the incenter {I} is such that the incircle touches {B}{C} at {X}, {C}{A} at {Y}, and {A}{B} at {Z}. ',
            'Construct points {X}, {Y}, {Z} as the tangency points of the incircle with sides {B}{C}, {C}{A}, {A}{B}, and {I} as the incenter. ',
            'The incenter {I} and tangency points {X} on {B}{C}, {Y} on {C}{A}, {Z} on {A}{B} are defined for triangle {A}{B}{C}. ',
            '{I} serves as the incenter of triangle {A}{B}{C}, with the circle tangent at {X} to {B}{C}, at {Y} to {C}{A}, and at {Z} to {A}{B}. ',
            'For triangle {A}{B}{C}, {I} is the incenter, and {X}, {Y}, {Z} are the points where the incircle meets sides {B}{C}, {C}{A}, {A}{B}. ',
            'The construction includes {I} as the incenter of triangle {A}{B}{C}, tangent to the sides at {X}, {Y}, {Z} on {B}{C}, {C}{A}, {A}{B} respectively. ',
        ],
    },
    'excenter': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Point {X} is the excenter of triangle {A}{B}{C} opposite vertex {A}. ',
            'Construct {X} as the intersection of the external angle bisectors at {B} and {C} and the internal angle bisector at {A} in triangle {A}{B}{C}. ',
            '{X} is the excenter opposite {A} in triangle {A}{B}{C}, center of the excircle tangent to side {B}{C} and extensions of the other sides. ',
            'The excenter {X} opposite {A} is formed by the concurrence of the specified angle bisectors in triangle {A}{B}{C}. ',
            'In triangle {A}{B}{C}, {X} marks the excenter across from {A}, where external bisectors at {B} and {C} meet the internal at {A}. ',
            'Construct the excenter {X} opposite vertex {A} for triangle {A}{B}{C}. ',
            '{X} is the center of the excircle opposite {A}, intersecting the external angle bisectors at {B} and {C} with the internal at {A}. ',
            'The point {X} serves as the excenter of triangle {A}{B}{C} opposite {A}. ',
            '{X} is determined as the excenter opposite {A} in triangle {A}{B}{C}, via the angle bisectors described. ',
            'For triangle {A}{B}{C}, {X} is the excenter facing opposite {A}, at the junction of external bisectors from {B} and {C} and internal from {A}. ',
        ],
    },
    'excenter2': {
        'points': ['X', 'Y', 'Z', 'I', 'A', 'B', 'C'],
        'candidates': [
            'Point {I} is the excenter opposite {A} in triangle {A}{B}{C}, with the excircle touching side {B}{C} at {X}, and extensions of {C}{A} at {Y}, {A}{B} at {Z}. ',
            'Construct {I} as the excenter opposite {A}, where the excircle is tangent to {B}{C} at {X}, to the extension of {C}{A} at {Y}, and to the extension of {A}{B} at {Z}. ',
            'The excenter {I} opposite {A} in triangle {A}{B}{C} has tangency points {X} on {B}{C}, {Y} on the extension of {C}{A}, and {Z} on the extension of {A}{B}. ',
            '{I} is positioned as the excenter across from {A}, with excircle contacts at {X}, {Y}, {Z} on {B}{C} and the extensions of the other sides. ',
            'In triangle {A}{B}{C}, the excenter {I} opposite {A} touches {B}{C} at {X}, extended {C}{A} at {Y}, and extended {A}{B} at {Z}. ',
            'Construct points {X}, {Y}, {Z} as the tangency points of the excircle opposite {A} with {B}{C}, extended {C}{A}, extended {A}{B}, and {I} as the excenter. ',
            'The excenter {I} and tangency points {X} on {B}{C}, {Y} on extended {C}{A}, {Z} on extended {A}{B} are defined for triangle {A}{B}{C}. ',
            '{I} serves as the excenter opposite {A} in triangle {A}{B}{C}, with the circle tangent at {X} to {B}{C}, at {Y} to extended {C}{A}, and at {Z} to extended {A}{B}. ',
            'For triangle {A}{B}{C}, {I} is the excenter opposite {A}, and {X}, {Y}, {Z} are the points where the excircle meets {B}{C} and the extensions of {C}{A}, {A}{B}. ',
            'The construction includes {I} as the excenter opposite {A} of triangle {A}{B}{C}, tangent to the side and extensions at {X}, {Y}, {Z} respectively. ',
        ],
    },
    'centroid': {
        'points': ['X', 'Y', 'Z', 'I', 'A', 'B', 'C'],
        'candidates': [
            'Point {I} is the centroid of triangle {A}{B}{C}, where {X}, {Y}, {Z} are the midpoints of sides {B}{C}, {C}{A}, {A}{B} respectively. ',
            'Construct {I} as the centroid of triangle {A}{B}{C}, with midpoints {X} on {B}{C}, {Y} on {C}{A}, and {Z} on {A}{B}. ',
            'The centroid {I} of triangle {A}{B}{C} is the intersection of the medians from vertices to midpoints {X}, {Y}, {Z}. ',
            '{I} is the center of mass of triangle {A}{B}{C}, defined using midpoints {X}, {Y}, {Z} of the opposite sides. ',
            'In triangle {A}{B}{C}, {I} marks the centroid, with {X} midpoint of {B}{C}, {Y} of {C}{A}, {Z} of {A}{B}. ',
            'Construct midpoints {X}, {Y}, {Z} on sides {B}{C}, {C}{A}, {A}{B}, and {I} as their centroid intersection. ',
            'The centroid {I} and midpoints {X} on {B}{C}, {Y} on {C}{A}, {Z} on {A}{B} are established for triangle {A}{B}{C}. ',
            '{I} serves as the centroid of triangle {A}{B}{C}, averaged from vertices, with specified midpoints {X}, {Y}, {Z}. ',
            'For triangle {A}{B}{C}, {I} is the centroid, and {X}, {Y}, {Z} are midpoints of {B}{C}, {C}{A}, {A}{B}. ',
            'The construction places {I} as the centroid of triangle {A}{B}{C}, utilizing midpoints {X}, {Y}, {Z} on the respective sides. ',
        ],
    },
    'ninepoints': {
        'points': ['X', 'Y', 'Z', 'I', 'A', 'B', 'C'],
        'candidates': [
            'Let {I} be the nine-point center of triangle {A}{B}{C}, with {X}, {Y}, and {Z} as the midpoints of sides {B}{C}, {C}{A}, and {A}{B}, respectively. ',
            'Define {I} as the center of the nine-point circle for triangle {A}{B}{C}, where {X} is the midpoint of {B}{C}, {Y} of {C}{A}, and {Z} of {A}{B}. ',
            '{I} serves as the nine-point center of triangle {A}{B}{C}, and {X}, {Y}, {Z} are the midpoints of the sides opposite to {A}, {B}, and {C}, respectively. ',
            'Construct the nine-point center {I} of triangle {A}{B}{C}, identifying {X} as the midpoint of {B}{C}, {Y} as that of {C}{A}, and {Z} as that of {A}{B}. ',
            'In triangle {A}{B}{C}, {I} is the nine-point center, while {X}, {Y}, and {Z} represent the midpoints of sides {B}{C}, {C}{A}, and {A}{B}. ',
            '{I} denotes the nine-point center associated with triangle {A}{B}{C}, with midpoints {X} on {B}{C}, {Y} on {C}{A}, and {Z} on {A}{B}. ',
            'The nine-point center of triangle {A}{B}{C} is {I}, and the midpoints of its sides {B}{C}, {C}{A}, {A}{B} are {X}, {Y}, {Z}, in that order. ',
            'Establish {I} as the nine-point center for triangle {A}{B}{C}, defining {X}, {Y}, and {Z} as midpoints of {B}{C}, {C}{A}, and {A}{B}. ',
            'For triangle {A}{B}{C}, let {I} be its nine-point center, and assign {X}, {Y}, {Z} as the respective midpoints of sides {B}{C}, {C}{A}, {A}{B}. ',
            '{I} is positioned as the nine-point center of triangle {A}{B}{C}, with {X} midway between {B} and {C}, {Y} between {C} and {A}, and {Z} between {A} and {B}. ',
        ],
    },
    'intersection_cc': {
        'points': ['X', 'O', 'W', 'A'],
        'candidates': [
            'Let {X} be the second intersection point of the circle centered at {O} with radius {O}{A} and the circle centered at {W} with radius {W}{A}. ',
            '{X} is defined as the other point where the circle with center {O} and radius {O}{A} intersects the circle with center {W} and radius {W}{A}. ',
            'Construct {X} as the secondary intersection of two circles: one centered at {O} passing through {A}, and the other centered at {W} passing through {A}. ',
            'The point {X} represents the second common point of the circle about {O} with radius to {A} and the circle about {W} with radius to {A}. ',
            '{X} lies at the second intersection of the circle having center {O} and radius {O}{A} with the circle having center {W} and radius {W}{A}. ',
            'Define {X} as the alternate intersection point between the {O}-centered circle through {A} and the {W}-centered circle through {A}. ',
            '{X} is the additional point of intersection for the two circles, one with center {O} and radius equal to the distance to {A}, the other with center {W} and similar radius to {A}. ',
            'Let {X} denote the second point where these two circles meet: centered at {O} with radius {O}{A}, and centered at {W} with radius {W}{A}. ',
            'Construct point {X} at the other intersection of the circle centered on {O} passing through {A} and the circle centered on {W} passing through {A}. ',
            '{X} serves as the secondary crossing point of the {O}-circle with radius to {A} and the {W}-circle with radius to {A}. ',
        ],
    },
    'intersection_lc': {
        'points': ['X', 'A', 'O', 'B'],
        'candidates': [
            'Let {X} be the second intersection point of line {A}{B} and the circle centered at {O} with radius {O}{B}. ',
            '{X} is defined as the other point where line {A}{B} intersects the circle with center {O} and radius {O}{B}. ',
            'Construct {X} as the secondary intersection of the line through {A} and {B} with the circle centered at {O} passing through {B}. ',
            'The point {X} represents the second common point between line {A}{B} and the circle about {O} with radius to {B}. ',
            '{X} lies at the alternate intersection of line {A}{B} and the circle having center {O} and radius {O}{B}. ',
            'Define {X} as the additional intersection point of the line connecting {A} and {B} with the {O}-centered circle through {B}. ',
            '{X} is the other point of intersection for line {A}{B} and the circle centered at {O} with radius equal to the distance to {B}. ',
            'Let {X} denote the second crossing of the line from {A} to {B} with the circle about {O} passing through {B}. ',
            'Construct point {X} at the secondary meeting of line {A}{B} and the circle with center {O} and radius {O}{B}. ',
            '{X} serves as the alternate point where line {A}{B} meets the {O}-circle with radius to {B}. ',
        ],
    },
    'intersection_ll': {
        'points': ['X', 'A', 'B', 'C', 'D'],
        'candidates': [
            'Let {X} be the intersection point of line {A}{B} and line {C}{D}. ',
            '{X} is defined as the point where line {A}{B} meets line {C}{D}. ',
            'Construct {X} as the intersection of the line through {A} and {B} with the line through {C} and {D}. ',
            'The point {X} represents the crossing of lines {A}{B} and {C}{D}. ',
            '{X} lies at the intersection of line {A}{B} and line {C}{D}. ',
            'Define {X} as the point of intersection between the lines connecting {A} to {B} and {C} to {D}. ',
            '{X} is the common point where line {A}{B} intersects line {C}{D}. ',
            'Let {X} denote the meeting point of line {A}{B} and line {C}{D}. ',
            'Construct point {X} where the line from {A} to {B} crosses the line from {C} to {D}. ',
            '{X} serves as the intersection of lines {A}{B} and {C}{D}. ',
        ],
    },
    'intersection_lp': {
        'points': ['X', 'A', 'B', 'C', 'M', 'N'],
        'candidates': [
            'Let {X} be the intersection point of line {A}{B} and the line through {C} parallel to {M}{N}. ',
            '{X} is defined as the point where line {A}{B} meets the line passing through {C} that is parallel to {M}{N}. ',
            'Construct {X} as the intersection of the line through {A} and {B} with the line through {C} parallel to the direction of {M}{N}. ',
            'The point {X} represents the crossing of line {A}{B} and the parallel line to {M}{N} passing through {C}. ',
            '{X} lies at the intersection of line {A}{B} and the line from {C} that parallels {M}{N}. ',
            'Define {X} as the point of intersection between line {A}{B} and the line through {C} parallel to segment {M}{N}. ',
            '{X} is the common point where line {A}{B} intersects the line parallel to {M}{N} and containing {C}. ',
            'Let {X} denote the meeting point of line {A}{B} and the parallel to {M}{N} through {C}. ',
            'Construct point {X} where line {A}{B} crosses the line through {C} that is parallel to {M}{N}. ',
            '{X} serves as the intersection of line {A}{B} and the line parallel to {M}{N} passing through {C}. ',
        ],
    },
    'intersection_lt': {
        'points': ['X', 'A', 'B', 'C', 'D', 'E'],
        'candidates': [
            'Let {X} be the intersection point of line {A}{B} and the line through {C} perpendicular to {D}{E}. ',
            '{X} is defined as the point where line {A}{B} meets the line passing through {C} that is perpendicular to {D}{E}. ',
            'Construct {X} as the intersection of the line through {A} and {B} with the line through {C} perpendicular to the direction of {D}{E}. ',
            'The point {X} represents the crossing of line {A}{B} and the perpendicular line to {D}{E} passing through {C}. ',
            '{X} lies at the intersection of line {A}{B} and the line from {C} that is perpendicular to {D}{E}. ',
            'Define {X} as the point of intersection between line {A}{B} and the line through {C} perpendicular to segment {D}{E}. ',
            '{X} is the common point where line {A}{B} intersects the line perpendicular to {D}{E} and containing {C}. ',
            'Let {X} denote the meeting point of line {A}{B} and the perpendicular to {D}{E} through {C}. ',
            'Construct point {X} where line {A}{B} crosses the line through {C} that is perpendicular to {D}{E}. ',
            '{X} serves as the intersection of line {A}{B} and the line perpendicular to {D}{E} passing through {C}. ',
        ],
    },
    'intersection_pp': {
        'points': ['X', 'A', 'B', 'C', 'D', 'E', 'F'],
        'candidates': [
            'Let {X} be the intersection point of the line through {A} parallel to {B}{C} and the line through {D} parallel to {E}{F}. ',
            '{X} is defined as the point where the line passing through {A} parallel to {B}{C} meets the line passing through {D} parallel to {E}{F}. ',
            'Construct {X} as the intersection of the parallel to {B}{C} through {A} and the parallel to {E}{F} through {D}. ',
            'The point {X} represents the crossing of the line through {A} in the direction parallel to {B}{C} and the line through {D} parallel to {E}{F}. ',
            '{X} lies at the intersection of the line from {A} parallel to {B}{C} and the line from {D} parallel to {E}{F}. ',
            'Define {X} as the point of intersection between the parallel line to {B}{C} containing {A} and the parallel line to {E}{F} containing {D}. ',
            '{X} is the common point where the {A}-line parallel to {B}{C} intersects the {D}-line parallel to {E}{F}. ',
            'Let {X} denote the meeting point of the line through {A} parallel to {B}{C} and the line through {D} parallel to {E}{F}. ',
            'Construct point {X} where the parallel to {B}{C} through {A} crosses the parallel to {E}{F} through {D}. ',
            '{X} serves as the intersection of the two lines: one through {A} parallel to {B}{C}, the other through {D} parallel to {E}{F}. ',
        ],
    },
    'intersection_tt': {
        'points': ['X', 'A', 'B', 'C', 'D', 'E', 'F'],
        'candidates': [
            'Let {X} be the intersection point of the line through {A} perpendicular to {B}{C} and the line through {D} perpendicular to {E}{F}. ',
            '{X} is defined as the point where the line passing through {A} perpendicular to {B}{C} meets the line passing through {D} perpendicular to {E}{F}. ',
            'Construct {X} as the intersection of the perpendicular to {B}{C} through {A} and the perpendicular to {E}{F} through {D}. ',
            'The point {X} represents the crossing of the line through {A} at right angles to {B}{C} and the line through {D} at right angles to {E}{F}. ',
            '{X} lies at the intersection of the line from {A} perpendicular to {B}{C} and the line from {D} perpendicular to {E}{F}. ',
            'Define {X} as the point of intersection between the perpendicular line to {B}{C} containing {A} and the perpendicular line to {E}{F} containing {D}. ',
            '{X} is the common point where the {A}-line perpendicular to {B}{C} intersects the {D}-line perpendicular to {E}{F}. ',
            'Let {X} denote the meeting point of the line through {A} perpendicular to {B}{C} and the line through {D} perpendicular to {E}{F}. ',
            'Construct point {X} where the perpendicular to {B}{C} through {A} crosses the perpendicular to {E}{F} through {D}. ',
            '{X} serves as the intersection of the two lines: one through {A} perpendicular to {B}{C}, the other through {D} perpendicular to {E}{F}. ',
        ],
    },
    'iso_triangle': {
        'points': ['A', 'B', 'C'],
        'candidates': [
            'Construct isosceles triangle {A}{B}{C} with vertex at {A}, such that sides {A}{B} and {A}{C} are equal. ',
            'Form triangle {A}{B}{C} as isosceles with base {B}{C} and equal sides from vertex {A}. ',
            'Let triangle {A}{B}{C} be isosceles with {A} as the apex, where {A}{B} equals {A}{C}. ',
            'Build an isosceles triangle {A}{B}{C} having {A} as the vertex and congruent legs {A}{B} and {A}{C}. ',
            'Triangle {A}{B}{C} is isosceles with vertex {A}, ensuring the distances from {A} to {B} and {A} to {C} are identical. ',
            'Create isosceles triangle {A}{B}{C} where {A} is the vertex point, and {A}{B} = {A}{C}. ',
            'Define triangle {A}{B}{C} as isosceles with equal sides {A}{B} and {A}{C} emanating from vertex {A}. ',
            'Establish triangle {A}{B}{C} as isosceles, with {A} serving as the vertex and {A}{B} congruent to {A}{C}. ',
            'Construct the isosceles triangle {A}{B}{C} featuring vertex {A} and equal lengths {A}{B} and {A}{C}. ',
            'Let {A}{B}{C} be an isosceles triangle with apex at {A}, such that the sides from {A} to {B} and {A} to {C} are of equal length. ',
        ],
    },
    'lc_tangent': {
        'points': ['X', 'A', 'O'],
        'candidates': [
            'Construct point {X} on the tangent line to the circle centered at {O} with radius {O}{A} at the point {A}. ',
            'Let {X} be a point lying on the tangent to the circle with center {O} and radius {O}{A}, touching at {A}. ',
            '{X} is positioned on the tangent line at {A} to the circle about {O} passing through {A}. ',
            'Define {X} as a point on the tangent to the {O}-centered circle with radius to {A}, at the tangency point {A}. ',
            'Place {X} along the tangent line to the circle (center {O}, radius {O}{A}) that touches it at {A}. ',
            '{X} resides on the line tangent to the circle centered at {O} with radius {O}{A}, at point {A}. ',
            'Construct {X} upon the tangent at {A} to the circle having center {O} and radius equal to {O}{A}. ',
            'Let {X} denote a point on the tangent line touching the circle at {A}, where the circle is centered at {O} with radius {O}{A}. ',
            '{X} is located on the tangent to the circle about {O} through {A}, specifically at the point of tangency {A}. ',
            'Position {X} on the line that is tangent to the circle centered at {O} with radius {O}{A} at the point {A}. ',
        ],
    },
    'midpoint': {
        'points': ['X', 'A', 'B'],
        'candidates': [
            'Let {X} be the midpoint of the segment connecting {A} and {B}. ',
            '{X} is defined as the midpoint of segment {A}{B}. ',
            'Construct {X} as the point midway between {A} and {B}. ',
            'The point {X} represents the center of the line segment {A}{B}. ',
            '{X} lies at the midpoint of {A}{B}. ',
            'Define {X} as the midpoint dividing segment {A}{B} into two equal parts. ',
            '{X} is the point equidistant from {A} and {B} on the line through them. ',
            'Let {X} denote the midpoint of the segment from {A} to {B}. ',
            'Construct point {X} halfway along the segment {A}{B}. ',
            '{X} serves as the midpoint of {A}{B}. ',
        ],
    },
    'mirror': {
        'points': ['X', 'A', 'B'],
        'candidates': [
            'Let {X} be the reflection of point {A} over point {B}. ',
            '{X} is defined as the point symmetric to {A} with respect to {B}. ',
            'Construct {X} as the point reflection of {A} across {B}. ',
            'The point {X} represents the image of {A} under point symmetry about {B}. ',
            '{X} is the reflection of {A} with center of symmetry at {B}. ',
            'Define {X} as the point such that {B} is the midpoint of {A}{X}. ',
            '{X} is positioned so that {B} lies midway between {A} and {X}. ',
            'Let {X} denote the symmetric point of {A} relative to {B}. ',
            'Construct point {X} as the reflection of {A} over the point {B}. ',
            '{X} serves as the point reflection of {A} with respect to {B}. ',
        ],
    },
    'on_aline': {
        'points': ['X', 'A', 'B', 'C', 'D', 'E'],
        'candidates': [
            'Construct point {X} such that the angle {X}{A}{B} equals the angle {C}{D}{E}. ',
            'Let {X} be a point where ∠{X}{A}{B} is equal to ∠{C}{D}{E}. ',
            '{X} is positioned so that the angle at {A} between {X} and {B} matches the angle at {D} between {C} and {E}. ',
            'Define {X} such that ∠{X}{A}{B} = ∠{C}{D}{E}. ',
            'Place {X} to ensure the angle formed by {X}, {A}, {B} is congruent to the angle formed by {C}, {D}, {E}. ',
            '{X} satisfies the condition that the measure of angle {X}{A}{B} equals that of angle {C}{D}{E}. ',
            'Construct {X} with ∠{X}{A}{B} equivalent to ∠{C}{D}{E}. ',
            'Let {X} be chosen so that angle {X}{A}{B} is equal in measure to angle {C}{D}{E}. ',
            '{X} is a point making ∠{X}{A}{B} congruent to ∠{C}{D}{E}. ',
            'Position {X} such that the angle at {A} from {X} to {B} matches the angle at {D} from {C} to {E}. ',
        ],
    },
    'on_bline': {
        'points': ['X', 'A', 'B'],
        'candidates': [
            'Construct point {X} on the perpendicular bisector of segment {A}{B}. ',
            'Let {X} lie on the perpendicular bisector of {A}{B}. ',
            '{X} is positioned along the line that perpendicularly bisects segment {A}{B}. ',
            'Define {X} as a point on the perpendicular bisector passing through the midpoint of {A}{B}. ',
            'Place {X} upon the perpendicular bisector of the segment connecting {A} and {B}. ',
            '{X} resides on the line that is the perpendicular bisector of {A}{B}. ',
            'Construct {X} to be on the perpendicular bisector of {A}{B}. ',
            'Let {X} be a point lying on the perpendicular bisector of segment {A}{B}. ',
            '{X} is located on the line perpendicular to {A}{B} at its midpoint. ',
            'Position {X} along the perpendicular bisector of {A}{B}. ',
        ],
    },
    'on_circle': {
        'points': ['X', 'O', 'A'],
        'candidates': [
            'Construct point {X} on the circle with center {O} and radius {O}{A}. ',
            'Let {X} lie on the circle centered at {O} with radius equal to the distance from {O} to {A}. ',
            '{X} is positioned on the circumference of the circle about {O} passing through {A}. ',
            'Define {X} as a point on the circle having center {O} and radius {O}{A}. ',
            'Place {X} upon the circle with {O} as center and {A} as a point on it. ',
            '{X} resides on the circle centered at {O} with radius to {A}. ',
            'Construct {X} to be on the circle about {O} with radius {O}{A}. ',
            'Let {X} be a point lying on the circle centered at {O} passing through {A}. ',
            '{X} is located on the circle with center {O} and radius equal to {O}{A}. ',
            'Position {X} along the circumference of the circle centered at {O} with radius {O}{A}. ',
        ],
    },
    'on_line': {
        'points': ['X', 'A', 'B'],
        'candidates': [
            'Place point {X} on the line passing through {A} and {B}. ',
            'Let {X} be a point lying on the segment between {A} and {B}. ',
            '{X} lies on the straight line connecting {A} and {B}. ',
            'Position {X} along the line {A}{B}. ',
            '{X} is located on the line that goes through points {A} and {B}. ',
            'Ensure {X} is collinear with {A} and {B}. ',
            'Point {X} belongs to the line defined by {A} and {B}. ',
            '{X} is situated on the infinite line extending from {A} through {B}. ',
            'The line {A}{B} contains point {X}. ',
            '{X} resides on the ray starting at {A} and passing through {B}, or its extension. ',
        ],
    },
    'on_pline': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Position {X} so that the line from {X} to {A} is parallel to the line from {B} to {C}. ',
            'Let {X} be such that segment {X}{A} runs parallel to {B}{C}. ',
            '{X} is placed where {X}{A} is parallel to the direction of {B}{C}. ',
            'Ensure the vector from {X} to {A} is parallel to the vector from {B} to {C}. ',
            'Point {X} makes {X}{A} parallel to {B}{C}. ',
            'Locate {X} with {X}{A} aligned parallel to {B}{C}. ',
            '{X} is chosen so that the line {X}{A} does not intersect {B}{C} extended, being parallel. ',
            'The segment {X}{A} is parallel to {B}{C} by placing {X} appropriately. ',
            '{X} ensures that {X}{A} and {B}{C} are parallel lines. ',
            'Place {X} to make the direction from {X} to {A} match the parallelism of {B} to {C}. ',
        ],
    },
    'on_tline': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Position {X} so that the line from {X} to {A} is perpendicular to the line from {B} to {C}. ',
            'Let {X} be such that segment {X}{A} forms a right angle with {B}{C}. ',
            '{X} is placed where {X}{A} is at 90 degrees to {B}{C}. ',
            'Ensure the vector from {X} to {A} is perpendicular to the vector from {B} to {C}. ',
            'Point {X} makes {X}{A} orthogonal to {B}{C}. ',
            'Locate {X} with {X}{A} perpendicular to the direction of {B}{C}. ',
            '{X} is chosen so that {X}{A} meets {B}{C} at a right angle if extended. ',
            'The segment {X}{A} is perpendicular to {B}{C} by placing {X} accordingly. ',
            '{X} ensures that {X}{A} and {B}{C} form perpendicular lines. ',
            'Place {X} to make the direction from {X} to {A} perpendicular to {B} to {C}. ',
        ],
    },
    'orthocenter': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            '{X} is the orthocenter of triangle {A}{B}{C}, where the altitudes intersect. ',
            'Let {X} be the point where the altitudes from {A}, {B}, and {C} meet. ',
            'Position {X} as the intersection of the altitudes in triangle {A}{B}{C}. ',
            '{X} serves as the orthocenter for vertices {A}, {B}, and {C}. ',
            'The altitudes of triangle {A}{B}{C} concur at point {X}. ',
            '{X} is the common intersection point of the three altitudes from {A}{B}{C}. ',
            'In triangle {A}{B}{C}, {X} is the orthocenter. ',
            'Locate {X} at the orthocenter formed by points {A}, {B}, and {C}. ',
            '{X} marks the orthocenter of the triangle with vertices {A}, {B}, {C}. ',
            'The point {X} is where the perpendiculars from each vertex to the opposite side meet in triangle {A}{B}{C}. ',
        ],
    },
    'parallelogram': {
        'points': ['A', 'B', 'C', 'X'],
        'candidates': [
            'Position {X} to complete the parallelogram with vertices {A}, {B}, {C}, and {X}. ',
            'Let {X} be the fourth vertex making {A}{B}{C}{X} a parallelogram. ',
            '{X} is placed such that opposite sides {A}{B} parallel to {X}{C} and {A}{X} parallel to {B}{C}. ',
            'Form a parallelogram {A}{B}{C}{X} by locating {X}. ',
            '{X} completes the quadrilateral {A}{B}{C}{X} as a parallelogram. ',
            'The point {X} ensures {A}{B}{C}{X} has parallel opposite sides. ',
            'Locate {X} so that vectors {A} to {B} and {X} to {C} are equal, forming a parallelogram. ',
            '{X} is the vertex that makes {A}{B}{C}{X} a parallelogram with equal opposite sides. ',
            'In quadrilateral {A}{B}{C}{X}, {X} is positioned for parallelogram properties. ',
            '{X} is found by adding vectors from {A} to {B} and {A} to {C} in parallelogram {A}{B}{C}{X}. ',
        ],
    },
    'pentagon': {
        'points': ['A', 'B', 'C', 'D', 'E'],
        'candidates': [
            'Form the pentagon with vertices {A}, {B}, {C}, {D}, and {E} in order. ',
            'Let the five-sided polygon be {A}{B}{C}{D}{E}. ',
            'The pentagon is defined by points {A}, {B}, {C}, {D}, {E}. ',
            'Connect {A} to {B} to {C} to {D} to {E} to form a pentagon. ',
            '{A}{B}{C}{D}{E} constitutes the pentagon. ',
            'The polygon with five sides is {A}{B}{C}{D}{E}. ',
            'Establish the pentagon using vertices {A}, {B}, {C}, {D}, and {E}. ',
            'The five vertices {A}, {B}, {C}, {D}, {E} outline the pentagon. ',
            'Form pentagon {A}{B}{C}{D}{E} by sequencing the points. ',
            'The pentagonal shape is created with points {A}, {B}, {C}, {D}, {E}. ',
        ],
    },
    'quadrangle': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Form the quadrilateral with vertices {A}, {B}, {C}, and {D} in sequence. ',
            'Let the four-sided polygon be {A}{B}{C}{D}. ',
            'The quadrangle is defined by points {A}, {B}, {C}, {D}. ',
            'Connect {A} to {B} to {C} to {D} to create a quadrilateral. ',
            '{A}{B}{C}{D} forms the quadrangle. ',
            'The polygon with four sides is {A}{B}{C}{D}. ',
            'Establish the quadrilateral using vertices {A}, {B}, {C}, and {D}. ',
            'The four vertices {A}, {B}, {C}, {D} outline the quadrangle. ',
            'Form quadrilateral {A}{B}{C}{D} by linking the points. ',
            'The four-sided figure is made with points {A}, {B}, {C}, {D}. ',
        ],
    },
    'r_trapezoid': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Form a right trapezoid {A}{B}{C}{D} with right angles at {A} and {D}, and {A}{B} perpendicular to {A}{D}. ',
            'Let {A}{B}{C}{D} be a trapezoid with right angles at vertices {A} and {D}, where {A}{B} is perpendicular to {A}{D}. ',
            'The trapezoid {A}{B}{C}{D} has right angles at {A} and {D}, with {A}{B} at 90 degrees to {A}{D}. ',
            'Construct trapezoid {A}{B}{C}{D} featuring right angles at {A} and {D}, and perpendicular sides {A}{B} and {A}{D}. ',
            '{A}{B}{C}{D} is a right-angled trapezoid with angles at {A} and {D} being 90 degrees, {A}{B} ⊥ {A}{D}. ',
            'The quadrilateral {A}{B}{C}{D} is a right trapezoid, right-angled at {A} and {D}, with {A}{B} perpendicular to {A}{D}. ',
            'Form the right trapezoid {A}{B}{C}{D} where corners at {A} and {D} are right angles, and {A}{B} is orthogonal to {A}{D}. ',
            '{A}{B}{C}{D} constitutes a trapezoid with right angles specifically at {A} and {D}, ensuring {A}{B} ⊥ {A}{D}. ',
            'The right trapezoid is {A}{B}{C}{D}, having perpendicular intersections at {A} and {D} between {A}{B} and {A}{D}. ',
            'Establish trapezoid {A}{B}{C}{D} as right-angled at {A} and {D}, with side {A}{B} perpendicular to {A}{D}. ',
        ],
    },
    'r_triangle': {
        'points': ['A', 'B', 'C'],
        'candidates': [
            'Form a right triangle {A}{B}{C} with the right angle at vertex {A}. ',
            'Let {A}{B}{C} be a right-angled triangle, with the 90-degree angle at {A}. ',
            'The triangle {A}{B}{C} has a right angle located at point {A}. ',
            'Construct triangle {A}{B}{C} featuring a right angle at {A}. ',
            '{A}{B}{C} is a right triangle with the right angle at vertex {A}. ',
            'The three-sided figure {A}{B}{C} is right-angled at {A}. ',
            'Form the right triangle using vertices {A}, {B}, {C}, with right angle at {A}. ',
            'Triangle {A}{B}{C} includes a 90-degree angle at {A}. ',
            'The right angle in triangle {A}{B}{C} is at point {A}. ',
            'Establish {A}{B}{C} as a right triangle where angle at {A} is 90 degrees. ',
        ],
    },
    'rectangle': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Form the rectangle with vertices {A}, {B}, {C}, and {D} in order. ',
            'Let {A}{B}{C}{D} be a rectangle. ',
            'The rectangular quadrilateral is defined by points {A}, {B}, {C}, {D}. ',
            'Connect {A} to {B} to {C} to {D} to create a rectangle. ',
            '{A}{B}{C}{D} constitutes the rectangle. ',
            'The four-sided figure with right angles is {A}{B}{C}{D}. ',
            'Establish the rectangle using vertices {A}, {B}, {C}, and {D}. ',
            'The points {A}, {B}, {C}, {D} outline the rectangle. ',
            'Form rectangle {A}{B}{C}{D} by sequencing the vertices. ',
            'The rectangular shape is created with points {A}, {B}, {C}, {D}. ',
        ],
    },
    'reflect': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            '{X} is the reflection of point {A} across the line {B}{C}. ',
            'Let {X} be the mirror image of {A} over the line connecting {B} and {C}. ',
            'Position {X} as the reflection of {A} with respect to line {B}{C}. ',
            '{X} is obtained by reflecting {A} over the axis {B}{C}. ',
            'The point {X} is the symmetric counterpart of {A} across {B}{C}. ',
            'Reflect {A} over {B}{C} to get point {X}. ',
            '{X} mirrors {A} with the line {B}{C} as the axis of symmetry. ',
            'Locate {X} such that {B}{C} is the perpendicular bisector of {X}{A}. ',
            '{X} is the image of {A} under reflection through line {B}{C}. ',
            'The reflection of {A} over {B}{C} yields point {X}. ',
        ],
    },
    'risos': {
        'points': ['A', 'B', 'C'],
        'candidates': [
            'Form an isosceles right triangle {A}{B}{C} with right angle at {A} and equal legs {A}{B} and {A}{C}. ',
            'Let {A}{B}{C} be a right-angled isosceles triangle, right at {A}, with {A}{B} equal to {A}{C}. ',
            'The triangle {A}{B}{C} is isosceles and right-angled at {A}, where {A}{B} = {A}{C}. ',
            'Construct isosceles right triangle {A}{B}{C} with 90 degrees at {A} and equal sides {A}{B}, {A}{C}. ',
            '{A}{B}{C} is a right isosceles triangle with right angle at vertex {A} and {A}{B} = {A}{C}. ',
            'The figure {A}{B}{C} is an isosceles triangle with a right angle at {A} and legs {A}{B} = {A}{C}. ',
            'Form the isosceles right triangle using {A}, {B}, {C}, right at {A}, equal sides from {A}. ',
            'Triangle {A}{B}{C} has equal lengths {A}{B} and {A}{C}, with 90-degree angle at {A}. ',
            'The right isosceles triangle {A}{B}{C} features {A}{B} = {A}{C} and right angle at {A}. ',
            'Establish {A}{B}{C} as isosceles with right angle at {A} and congruent sides {A}{B}, {A}{C}. ',
        ],
    },
    'segment': {
        'points': ['A', 'B'],
        'candidates': [
            'Draw the segment connecting {A} and {B}. ',
            'Let there be a line segment from {A} to {B}. ',
            'The segment {A}{B} is constructed. ',
            'Connect points {A} and {B} with a segment. ',
            '{A}{B} forms the straight segment. ',
            'Establish the line segment between {A} and {B}. ',
            'The connection from {A} to {B} is a segment. ',
            'Form segment {A}{B}. ',
            'The straight line piece from {A} to {B} is the segment. ',
            'Create the segment linking {A} and {B}. ',
        ],
    },
    'square': {
        'points': ['A', 'B', 'X', 'Y'],
        'candidates': [
            'Position {X} and {Y} to complete the square with vertices {A}, {B}, {X}, {Y}. ',
            'Let {X} and {Y} be the remaining vertices making {A}{B}{X}{Y} a square. ',
            '{X} and {Y} are placed such that {A}{B}{X}{Y} forms a square. ',
            'Form a square {A}{B}{X}{Y} by locating {X} and {Y}. ',
            '{X} and {Y} complete the square starting from {A} and {B}. ',
            'The points {X} and {Y} ensure {A}{B}{X}{Y} has equal sides and right angles. ',
            'Locate {X} and {Y} so that the quadrilateral {A}{B}{X}{Y} is a square. ',
            '{X} and {Y} are the vertices that make {A}{B}{X}{Y} a perfect square. ',
            'In figure {A}{B}{X}{Y}, {X} and {Y} are positioned for square properties. ',
            '{X} and {Y} are found to create square {A}{B}{X}{Y} with equal sides. ',
        ],
    },
    'isquare': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Form the square with vertices {A}, {B}, {C}, and {D} in order. ',
            'Let {A}{B}{C}{D} be a square. ',
            'The square is defined by points {A}, {B}, {C}, {D}. ',
            'Connect {A} to {B} to {C} to {D} to create a square. ',
            '{A}{B}{C}{D} constitutes the square. ',
            'The four-sided equal figure is {A}{B}{C}{D}. ',
            'Establish the square using vertices {A}, {B}, {C}, and {D}. ',
            'The points {A}, {B}, {C}, {D} outline the square. ',
            'Form square {A}{B}{C}{D} by sequencing the vertices. ',
            'The square shape is created with points {A}, {B}, {C}, {D}. ',
        ],
    },
    'trapezoid': {
        'points': ['A', 'B', 'C', 'D'],
        'candidates': [
            'Form trapezoid {A}{B}{C}{D} with {A}{B} parallel to {C}{D}. ',
            'Create the trapezoid having vertices {A}, {B}, {C}, {D} where {A}{B} is parallel to {C}{D}. ',
            'Build trapezoid {A}{B}{C}{D} such that sides {A}{B} and {C}{D} are parallel. ',
            'Construct the trapezoid with points {A}, {B}, {C}, {D} ensuring {A}{B} ∥ {C}{D}. ',
            'Assemble trapezoid {A}{B}{C}{D} where the non-parallel sides connect the parallel bases {A}{B} and {C}{D}. ',
            'Set up trapezoid {A}{B}{C}{D} with {A}{B} and {C}{D} as the parallel sides. ',
            'Draw trapezoid {A}{B}{C}{D} featuring parallel lines {A}{B} and {C}{D}. ',
            'Establish the trapezoid labeled {A}{B}{C}{D} in which {A}{B} runs parallel to {C}{D}. ',
            'Configure trapezoid {A}{B}{C}{D} so that segment {A}{B} is parallel to segment {C}{D}. ',
            'Shape the trapezoid with corners {A}, {B}, {C}, {D} and parallel edges {A}{B} and {C}{D}. ',
        ],
    },
    'triangle': {
        'points': ['A', 'B', 'C'],
        'candidates': [
            'Form triangle {A}{B}{C}. ',
            'Create the triangle with vertices {A}, {B}, and {C}. ',
            'Build triangle {A}{B}{C}. ',
            'Construct the triangle labeled {A}{B}{C}. ',
            'Assemble triangle {A}{B}{C} using points {A}, {B}, {C}. ',
            'Set up the triangle having corners {A}, {B}, {C}. ',
            'Draw triangle {A}{B}{C}. ',
            'Establish triangle {A}{B}{C} with the given points. ',
            'Configure the triangle formed by {A}, {B}, and {C}. ',
            'Shape triangle {A}{B}{C}. ',
        ],
    },
    'triangle12': {
        'points': ['A', 'B', 'C'],
        'candidates': [
            'Form triangle {A}{B}{C} where {A}{B} equals half of {A}{C}. ',
            'Create triangle {A}{B}{C} such that the length {A}{B} is one-half the length {A}{C}. ',
            'Build triangle {A}{B}{C} with {A}{B} = (1/2) {A}{C}. ',
            'Construct the triangle {A}{B}{C} ensuring side {A}{B} is half as long as side {A}{C}. ',
            'Assemble triangle {A}{B}{C} where the distance from {A} to {B} is half the distance from {A} to {C}. ',
            'Set up triangle {A}{B}{C} so that {A}{B} measures half of {A}{C}. ',
            'Draw triangle {A}{B}{C} with the condition that {A}{B} is one-half {A}{C}. ',
            'Establish triangle {A}{B}{C} such that segment {A}{B} is half the length of segment {A}{C}. ',
            'Configure the triangle with vertices {A}, {B}, {C} where {A}{B} = 0.5 × {A}{C}. ',
            'Shape triangle {A}{B}{C} featuring {A}{B} as half the size of {A}{C}. ',
        ],
    },
    'trisect': {
        'points': ['X', 'Y', 'A', 'B', 'C'],
        'candidates': [
            'Draw the two rays that trisect angle {B}{A}{C}, meeting side {A}{C} at {X} and {Y}. ',
            'Construct the trisectors of angle at {A} between {B} and {C}, intersecting {A}{C} at points {X} and {Y}. ',
            'From {A}, draw the two lines that divide angle {B}{A}{C} into three equal parts, hitting {A}{C} at {X} and {Y}. ',
            'Create the two trisecting rays for ∠{B}{A}{C}, which cross segment {A}{C} at {X} and {Y}. ',
            'Establish the trisectors emanating from {A} in angle {B}{A}{C}, intersecting {A}{C} at {X} and {Y}. ',
            'Divide angle {B}{A}{C} into three equal angles with rays from {A} that meet {A}{C} at {X} and {Y}. ',
            'Set up the two lines from {A} trisecting ∠{B}{A}{C} and reaching {A}{C} at points {X} and {Y}. ',
            'Form the trisecting segments within angle {B}{A}{C}, touching {A}{C} at {X} and {Y}. ',
            'Construct rays from vertex {A} that trisect the angle formed by {B} and {C}, intersecting the opposite side at {X} and {Y}. ',
            'Create the pair of trisectors for ∠{B}{A}{C} that land on {A}{C} at {X} and {Y}. ',
        ],
    },
    'trisegment': {
        'points': ['X', 'Y', 'A', 'B'],
        'candidates': [
            'Locate the two points {X} and {Y} that divide segment {A}{B} into three equal parts. ',
            'Find points {X} and {Y} trisecting the line segment from {A} to {B}. ',
            'Mark the trisection points {X} and {Y} on segment {A}{B}. ',
            'Divide {A}{B} into three equal segments using points {X} and {Y}. ',
            'Place {X} and {Y} such that they trisect the length of {A}{B}. ',
            'Identify the points {X} and {Y} that split {A}{B} into thirds. ',
            'Construct {X} and {Y} as the trisection points along {A}{B}. ',
            'Position {X} and {Y} to trisect the segment connecting {A} and {B}. ',
            'Establish {X} and {Y} dividing {A}{B} equally into three parts. ',
            'Set {X} and {Y} as the points that trisect line {A}{B}. ',
        ],
    },
    'on_dia': {
        'points': ['X', 'A', 'B'],
        'candidates': [
            'Place point {X} on the circle that has {A}{B} as its diameter. ',
            'Locate {X} on the circumference of the circle with diameter {A}{B}. ',
            'Find point {X} lying on the circle whose diameter is segment {A}{B}. ',
            'Position {X} along the circle defined by diameter {A}{B}. ',
            'Set {X} on the circle where {A}{B} serves as the diameter. ',
            'Choose {X} as a point on the circle with {A}{B} as diameter. ',
            'Mark {X} on the boundary of the circle having diameter {A}{B}. ',
            'Establish {X} on the circle that uses {A}{B} as its diameter. ',
            'Place {X} somewhere on the circle diametrically spanned by {A} and {B}. ',
            'Identify {X} as belonging to the circle with diameter from {A} to {B}. ',
        ],
    },
    'ieq_triangle': {
        'points': ['A', 'B', 'C'],
        'candidates': [
            'Form equilateral triangle {A}{B}{C}. ',
            'Create the equilateral triangle with vertices {A}, {B}, and {C}. ',
            'Build triangle {A}{B}{C} where all sides are equal. ',
            'Construct the equilateral triangle labeled {A}{B}{C}. ',
            'Assemble triangle {A}{B}{C} with equal lengths for {A}{B}, {B}{C}, and {C}{A}. ',
            'Set up the equilateral triangle having corners {A}, {B}, {C}. ',
            'Draw equilateral triangle {A}{B}{C}. ',
            'Establish triangle {A}{B}{C} such that it is equilateral. ',
            'Configure the triangle formed by {A}, {B}, and {C} with all sides congruent. ',
            'Shape equilateral triangle {A}{B}{C}. ',
        ],
    },
    'cc_tangent': {
        'points': ['X', 'Y', 'Z', 'I', 'O', 'A', 'W', 'B'],
        'candidates': [
            'Draw the two external common tangents to the circles centered at {O} with radius {O}{A} and at {W} with radius {W}{B}, touching the first circle at {X} and {Z}, and the second at {Y} and {I}. ',
            'Construct the external tangents shared by circle ({O}, {O}{A}) and circle ({W}, {W}{B}), with contact points {X}, {Z} on the first and {Y}, {I} on the second. ',
            'Form the pair of external common tangent lines for the two circles: one with center {O} and radius {O}{A}, the other with center {W} and radius {W}{B}, touching at {X}/{Y} and {Z}/{I} respectively. ',
            'Create the external tangents that touch circle {O} at {X} and {Z}, and circle {W} at {Y} and {I}. ',
            'Establish the two lines that are externally tangent to both circles ({O}, {O}{A}) and ({W}, {W}{B}), with points of tangency {X}, {Z} on the first and {Y}, {I} on the second. ',
            'Set up the external common tangents connecting the circles at {O} and {W}, touching at specified points {X}/{Y} and {Z}/{I}. ',
            'Build the two external tangents shared between the circle centered at {O} through {A} and the one at {W} through {B}, with touches at {X}, {Z} and {Y}, {I}. ',
            'Draw lines that externally touch both circles, contacting the {O}-circle at {X} and {Z}, and the {W}-circle at {Y} and {I}. ',
            'Configure the external common tangent segments for the given circles, with tangency points {X}/{Y} and {Z}/{I}. ',
            'Position the two external tangents that graze circle ({O}, {O}{A}) at {X} and {Z}, and circle ({W}, {W}{B}) at {Y} and {I}. ',
        ],
    },
    'eqangle3': {
        'points': ['X', 'A', 'B', 'D', 'E', 'F'],
        'candidates': [
            'Locate point {X} such that angle {A}{X}{B} equals angle {E}{D}{F}. ',
            'Find {X} where ∠{A}{X}{B} matches the measure of ∠{E}{D}{F}. ',
            'Position {X} so that the angle at {X} between {A} and {B} is equal to the angle at {D} between {E} and {F}. ',
            'Place {X} ensuring ∠{A}{X}{B} = ∠{E}{D}{F}. ',
            'Set {X} such that the angle formed by {A}, {X}, {B} is congruent to the angle formed by {E}, {D}, {F}. ',
            'Identify {X} where the measure of ∠{A}{X}{B} is the same as ∠{E}{D}{F}. ',
            'Establish point {X} with ∠{A}{X}{B} equal in degree to ∠{E}{D}{F}. ',
            'Choose {X} so that angle {A}{X}{B} replicates angle {E}{D}{F}. ',
            'Mark {X} such that the angles ∠{A}{X}{B} and ∠{E}{D}{F} are equal. ',
            'Construct {X} where the vertex angle at {X} from {A} to {B} matches that at {D} from {E} to {F}. ',
        ],
    },
    'tangent': {
        'points': ['X', 'Y', 'A', 'O', 'B'],
        'candidates': [
            'From {B}, draw the two tangent lines to the circle centered at {O} with radius {O}{A}, touching at {X} and {Y}. ',
            'Construct tangents from point {B} to the circle ({O}, {O}{A}), with points of tangency {X} and {Y}. ',
            'Draw from {B} the pair of tangents touching the circle at center {O} through {A} at points {X} and {Y}. ',
            'Create the two lines from {B} that are tangent to the circle with center {O} and radius {O}{A}, contacting at {X} and {Y}. ',
            'Establish tangents originating at {B} to the circle ({O}, {O}{A}), grazing it at {X} and {Y}. ',
            'From external point {B}, form the tangents to circle centered at {O} with radius to {A}, touching at {X} and {Y}. ',
            'Set up the tangent segments from {B} to the circle, meeting it at {X} and {Y}, where the circle has center {O} and radius {O}{A}. ',
            'Draw lines from {B} tangent to the circle at {X} and {Y}, with the circle defined by center {O} and point {A}. ',
            'Position the two tangents from {B} that touch the {O}-centered circle of radius {O}{A} at {X} and {Y}. ',
            'Build the pair of tangent rays from {B} contacting the circle ({O}, {O}{A}) at points {X} and {Y}. ',
        ],
    },
    'on_circum': {
        'points': ['X', 'A', 'B', 'C'],
        'candidates': [
            'Place point {X} on the circumcircle of triangle {A}{B}{C}. ',
            'Locate {X} on the circle passing through points {A}, {B}, and {C}. ',
            'Find {X} lying on the circumcircle surrounding triangle {A}{B}{C}. ',
            'Position {X} along the circumcircle of {A}{B}{C}. ',
            'Set {X} on the circle that circumscribes triangle {A}{B}{C}. ',
            'Choose {X} as a point on the circumcircle defined by {A}, {B}, {C}. ',
            'Mark {X} on the circumference of the circle through {A}, {B}, {C}. ',
            'Establish {X} on the circumcircle for triangle {A}{B}{C}. ',
            'Place {X} somewhere on the circle encircling points {A}, {B}, {C}. ',
            'Identify {X} belonging to the circumcircle of {A}{B}{C}. ',
        ],
    },
    'eqratio': {
        'points': ['X', 'A', 'B', 'C', 'D', 'E', 'F', 'G'],
        'candidates': [
            'Locate point {X} such that the ratio {A}{B} to {C}{D} equals {E}{F} to {G}{X}. ',
            'Find {X} where {A}{B}/{C}{D} = {E}{F}/{G}{X}. ',
            'Position {X} so that the proportion {A}{B} : {C}{D} = {E}{F} : {G}{X} holds. ',
            'Place {X} ensuring {A}{B} / {C}{D} = {E}{F} / {G}{X}. ',
            'Set {X} such that the ratios {A}{B} over {C}{D} and {E}{F} over {G}{X} are equal. ',
            'Identify {X} where the equality {A}{B} ÷ {C}{D} = {E}{F} ÷ {G}{X} is satisfied. ',
            'Establish point {X} with {A}{B}/{C}{D} matching {E}{F}/{G}{X}. ',
            'Choose {X} so that {A}{B} to {C}{D} is as {E}{F} to {G}{X}. ',
            'Mark {X} such that the ratio involving {G}{X} makes {E}{F}/{G}{X} = {A}{B}/{C}{D}. ',
            'Construct {X} where the proportional relationship {A}{B} : {C}{D} :: {E}{F} : {G}{X} applies. ',
        ],
    },
    'eqratio6': {
        'points': ['X', 'A', 'C', 'E', 'F', 'G', 'H'],
        'candidates': [
            'Locate point {X} such that the ratio {A}{X} to {C}{X} equals {E}{F} to {G}{H}. ',
            'Find {X} where {A}{X}/{C}{X} = {E}{F}/{G}{H}. ',
            'Position {X} so that {A}{X} : {C}{X} = {E}{F} : {G}{H}. ',
            'Place {X} ensuring {A}{X} / {C}{X} = {E}{F} / {G}{H}. ',
            'Set {X} such that the ratios {A}{X} over {C}{X} and {E}{F} over {G}{H} are equal. ',
            'Identify {X} where {A}{X} ÷ {C}{X} = {E}{F} ÷ {G}{H}. ',
            'Establish point {X} with {A}{X}/{C}{X} matching {E}{F}/{G}{H}. ',
            'Choose {X} so that {A}{X} to {C}{X} is as {E}{F} to {G}{H}. ',
            'Mark {X} such that the ratio {A}{X}:{C}{X} equals {E}{F}:{G}{H}. ',
            'Construct {X} where the proportion {A}{X} : {C}{X} :: {E}{F} : {G}{H} holds. ',
        ],
    },
    's_angle': {
        'points': ['A', 'B', 'X', 'Y'],
        'candidates': [
            'Locate point {X} such that angle {A}{B}{X} measures equal to {Y}. ',
            'Find {X} where the measure of ∠{A}{B}{X} is {Y}. ',
            'Position {X} so that ∠{A}{B}{X} equals the angle value or reference {Y}. ',
            'Place {X} ensuring the angle at {B} between {A} and {X} is {Y}. ',
            'Set {X} such that ∠{A}{B}{X} has measure {Y}. ',
            'Identify {X} where the degree of angle {A}{B}{X} matches {Y}. ',
            'Establish point {X} with ∠{A}{B}{X} equal to {Y}. ',
            'Choose {X} so that the angle formed by {A}, {B}, {X} is {Y}. ',
            'Mark {X} such that ∠{A}{B}{X} measures the same as {Y}. ',
            'Construct {X} where the vertex angle at {B} from {A} to {X} is given by {Y}. ',
        ],
    },
}

premise2nature = {
    'eqangle': {
        'points': ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
        'nature': '∠({A}{B},{C}{D}) = ∠({E}{F},{G}{H})',
    },
    'eqratio': {
        'points': ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
        'nature': '{A}{B}:{C}{D} = {E}{F}:{G}{H}',
    },
    'perp': {
        'points': ['A', 'B', 'C', 'D'],
        'nature': '{A}{B} ⟂ {C}{D}',
    },
    'para': {
        'points': ['A', 'B', 'C', 'D'],
        'nature': '{A}{B} ∥ {C}{D}',
    },
    'cyclic': {
        'points': ['A', 'B', 'C', 'D'],
        'nature': '{A}, {B}, {C}, {D} are cyclic',
    },
    'rconst': {
        'points': ['A', 'B', 'C', 'D', 'R'],
        'nature': '{A}{B}:{C}{D} = {R}',
    },
    'coll': {
        'points': ['A', 'B', 'C'],
        'nature': '{A}, {B}, {C} are collinear',
    },
    'cong': {
        'points': ['A', 'B', 'C', 'D'],
        'nature': '{A}{B} = {C}{D}',
    },
    'simtri': {
        'points': ['A', 'B', 'C', 'D', 'E', 'F'],
        'nature': '▲{A}{B}{C} ≅ ▲{D}{E}{F}',
    },
    'simtrir': {
        'points': ['A', 'B', 'C', 'D', 'E', 'F'],
        'nature': '▲{A}{B}{C} ≅ ▲{D}{E}{F}',
    },
    'contri': {
        'points': ['A', 'B', 'C', 'D', 'E', 'F'],
        'nature': '▲{A}{B}{C} ≡ ▲{D}{E}{F}',
    },
    'contrir': {
        'points': ['A', 'B', 'C', 'D', 'E', 'F'],
        'nature': '▲{A}{B}{C} ≡ ▲{D}{E}{F}',
    },

}


def analyze_geometry_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析给定的几何数据集条目，返回指定的分析字典。

    参数:
        data: 输入的字典数据（与问题中示例格式相同）

    返回:
        包含5部分分析的字典
    """
    fl_problem = data["fl_problem"]
    llm_input = data["llm_input_renamed"]

    # 点名字的映射（逆映射，用于变换回去）
    point_mapping = data.get("point_mapping", {})
    reverse_mapping = {v: k for k, v in point_mapping.items()}

    def remap_point(name: str) -> str:
        return reverse_mapping.get(name, name)

    def remap_args(args: List[str]) -> List[str]:
        def should_remap(arg: str) -> bool:
            POINT_PATTERN = re.compile(r'^[a-zA-Z]\d*$')
            return bool(POINT_PATTERN.fullmatch(arg))

        return [
            remap_point(arg) if should_remap(arg) else arg
            for arg in args
        ]

    # 所有点的名字及其坐标
    point_pattern = r"([a-z])@([-\d\.]+)_([-\d\.]+)"
    points_coordinates: Dict[str, Tuple[float, float]] = {}
    for match in re.finditer(point_pattern, fl_problem):
        name = match.group(1)
        x = float(match.group(2))
        y = float(match.group(3))
        points_coordinates[name] = (x, y)

    # 所有的构造（fl_problem中等号后面的部分，每个点定义的谓词列表）
    constructions: List[List[str]] = []
    clauses = [c.strip() for c in fl_problem.split(';') if c.strip()]
    for clause in clauses:
        if '=' not in clause:
            continue
        left, right = clause.split('=', 1)
        constr_part = right.strip().split('?', 1)[0].strip().rstrip(',')
        constr_list = [c.strip() for c in constr_part.split(',') if c.strip()]
        for constr in constr_list:
            parts = constr.split()
            if parts:
                predicate = parts[0]
                args = parts[1:]
                constructions.append([predicate] + args)

    # 提取前提谓词（只提取 ? 之前的真实几何谓词语句，忽略 x : 空行，点名全部映射回去）
    inner = re.search(r"<problem>(.*?)</problem>", llm_input, re.S).group(1)

    # 精确分割：先找到 ? 的位置，只取 ? 之前的内容
    problem_part = inner.split('?', 1)[0]

    pattern = r'([a-zA-Z0-9\s]+?)\s*(?=\[\d+\])'
    matches = re.findall(pattern, problem_part)
    premises = [m.strip() for m in matches]

    predicates: List[List[str]] = []
    for premise in premises:
        parts = premise.split()
        if parts:
            predicate = parts[0]
            args = remap_args(parts[1:])
            predicates.append([predicate] + args)

    # 所有的问题
    formal_question = None
    if '?' in fl_problem:
        formal_question = fl_problem.split('?', 1)[1].strip()

    questions: List[List[str]] = formal_question.split()

    # 点名字的映射
    point_mapping = data.get("point_mapping", {})

    return {
        "points_coordinates": points_coordinates,
        "constructions": constructions,
        "predicates": predicates,
        "questions": questions,
        # "point_name_mapping": point_mapping
    }


def check_construction(statement: List[str]) -> Optional[List[List[str]]]:
    """
    输入： ["on_pline0", "o", "f", "a", "j"]
    输出： 匹配成功 → 标准化后的前提列表（这里是 [["para", "o", "f", "a", "j"]]）
           失败 → None
    """
    if not statement:
        return None

    pred_name = statement[0]
    args = statement[1:]

    candidates = (
        constr2premise.get(pred_name, [])
    )

    for templ_str, var_order, normalized_premises in candidates:
        if len(var_order) != len(args):
            continue  # 参数个数不匹配

        # 建立变量 → 实际参数 的映射
        substitution: Dict[str, str] = {}
        for var, arg in zip(var_order, args):
            substitution[var] = arg

        # 对每条标准化前提进行变量替换
        result: List[List[str]] = []
        for premise in normalized_premises:
            substituted = [substitution.get(token, token) for token in premise]
            result.append(substituted)

        return result

    # 没匹配到
    return None


def check_predicate(
    x: List[str],
    all: List[List[str]],
    f: Callable[[List[str], List[str]], bool]
) -> bool:
    """
    使用自定义相等判断函数 f, 在 all 中查找第一个满足 f(item, x) 为 True 的元素，
    如果找到就删除它并返回 True, 否则返回 False。

    注意: all 会被原地修改！
    """
    for i, item in enumerate(all):
        if f(item, x):       # 用你提供的比较逻辑判断是否“相等”
            del all[i]
            return True
    return False


def check_eq(statement1: List[str], statement2: List[str]) -> bool:
    type1 = statement1[0]
    type2 = statement2[0]
    if type1 != type2:
        return False
    args1 = statement1[1:]
    args2 = statement2[1:]
    if len(args1) != len(args2):
        return False
    if type1 in ["coll", "cyclic",]:
        return set(args1) == set(args2)
    elif type1 in ["cong", "para", "perp",]:
        if len(args1) != 4 or len(args2) != 4:
            return False
        group1_a = sorted(args1[:2])
        group2_a = sorted(args1[2:])
        group1_b = sorted(args2[:2])
        group2_b = sorted(args2[2:])
        return (
            (group1_a == group1_b and group2_a == group2_b) or
            (group1_a == group2_b and group2_a == group1_b)
        )
    elif type1 in ["eqangle", "eqratio",]:
        def preparse(args: tuple[str, ...]):
            a, b, c, d, e, f, g, h = args
            if a == b or c == d or e == f or g == h:
                return
            if a > b:
                a, b = b, a
            if c > d:
                c, d = d, c
            if e > f:
                e, f = f, e
            if g > h:
                g, h = h, g

            g1a = (a, b, c, d)
            g1b = (e, f, g, h)
            g2a = (c, d, a, b)
            g2b = (g, h, e, f)
            if g1a <= g1b:
                groups1 = g1a + g1b
            else:
                groups1 = g1b + g1a
            if g2a <= g2b:
                groups2 = g2a + g2b
            else:
                groups2 = g2b + g2a
            groups1 = groups1 if groups1 <= groups2 else groups2
            a, b, c, d, e, f, g, h = groups1
            groups2 = (a, b, e, f, c, d, g, h)
            return groups1 if groups1 <= groups2 else groups2
        norm1 = preparse(args1)
        norm2 = preparse(args2)
        return norm1 == norm2
    elif type1 in ["circle", "midp",]:
        return args1[0] == args2[0] and set(args1[1:]) == set(args2[1:])
    else:
        print(type1)
        return False


def replace_braced_placeholders(template: str, mapping: Mapping[str, Any]) -> str:
    """
    将模板字符串中所有形如 {key} 的占位符替换为 mapping 中对应的值。

    参数:
        template (str): 待替换的原始字符串，例如 "Hello {name}, welcome to {city}!"
        mapping (Mapping[str, Any]): 键值映射表，键为占位符名称（不含大括号），
                                   值为要替换的内容。可以是 str、int、float 等任意可转换为字符串的对象。

    返回:
        str: 替换完成后的字符串。

    异常:
        KeyError: 如果模板中出现了 mapping 中不存在的键，则抛出 KeyError（与 str.format 行为一致）。
    """

    def replacer(match: re.Match) -> str:
        key = match.group(1)          # 去掉大括号后的键名
        # 直接使用 mapping 的 __getitem__，缺失会抛 KeyError
        value = mapping[key]
        return str(value)             # 确保返回字符串

    # 正则解释：
    #   \{          : 匹配字面的 '{'
    #   ([^{}]+)    : 捕获大括号内的一个或多个非 { 和 } 的字符（即键名）
    #   \}          : 匹配字面的 '}'
    pattern = r'\{([^{}]+)\}'

    return re.sub(pattern, replacer, template)


def process_data(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8') as outfile:
        for line in tqdm(infile, desc="Processing data", unit="line"):
            data = json.loads(line.strip())
            analyze_result = analyze_geometry_data(data)

            constructions = analyze_result["constructions"]
            predicates = analyze_result["predicates"]

            used_constr: List[List[str]] = []
            for constr in constructions:
                candidate_predicate = check_construction(constr)
                for candidate in candidate_predicate:
                    if check_predicate(candidate, predicates, check_eq):
                        used_constr.append(constr)
                        break

            problem_texts = []
            for constr in used_constr:
                type_ = constr[0]
                points = constr[1:]

                if type_ not in constr2nature:
                    print(f"{type_} is not defined.")
                    continue

                nature = constr2nature[type_]
                expected_points = nature['points']
                candidates = nature['candidates']

                if len(points) != len(expected_points):
                    print(f"Wrong points in {type_}.")
                    continue

                mapping = dict(zip(expected_points, points))
                template = random.choice(candidates)
                text = replace_braced_placeholders(template, mapping)

                problem_texts.append(text)

            questions = analyze_result['questions']
            type_ = questions[0]
            points = questions[1:]

            if type_ not in premise2nature:
                print(f"{type_} is not defined.")

            nature = premise2nature[type_]
            expected_points = nature['points']
            template = nature['nature']

            if len(points) != len(expected_points):
                print(f"Wrong points in {type_}.")

            mapping = dict(zip(expected_points, points))
            text = replace_braced_placeholders(template, mapping)

            result = {}
            # result["points"] = analyze_result["points_coordinates"]
            # result["questions"] = analyze_result["questions"]
            # result["constructions"] = used_constr
            result["problem"] = "".join(problem_texts)
            result["question"] = "Please prove that " + text
            json.dump(result, outfile, ensure_ascii=False)
            outfile.write('\n')


if __name__ == "__main__":
    input_file = '/c23474/home/jisizhe/dubhe/GenesisGeo/datasets/geometry_clauses15_samples20k.jsonl'
    output_file = '/c23474/home/jisizhe/dubhe/GenesisGeo/datasets/22.jsonl'

    process_data(input_file, output_file)
