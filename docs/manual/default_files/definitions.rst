Definitions
===========

Definitions are the basic building blocks for the statement of problems. Each definition works as a function, demanding a certain collection of arguments, in order to create new points, and add corresponding predicates to the proof state (see details in :ref:`Adding new problems`).

The definitions available in the defs.txt file are the following (definitions in section :ref:`New Definitions` were added by us and are available in new_defs.txt):

- **angle_bisector x a b c:** From non-collinear points a, b, c, creates x in the internal bisector of angle abc, with vertex at b. Adds the statement that angle abx and angle xbc are congruent. Can be subjected to intersections.

- **angle_mirror x a b c:**

- **circle x a b c:** From non-collinear points a, b, c, creates x the center of the circle through a, b, c. Adds the congruence statements that xa=xb and xb=xc.

- **circumcenter x a b c:** Same construction as **circle x a b c**.

- **eq_quadrangle a b c d:** From nothings, adds four points in a quadrilateral abcd with two opposing sides (AD and BC) of same length. Adds the congruence statement that ad=bc.

- **iso_trapezoid a b c d:** From nothing, adds four points on a trapezoid abcd with parallel opposing sides ab and cd and non-parallel opposing sides ad and bc of same length. Adds the congruence statement that ad=bc and the parallel statement that ab//cd.

- **eq_triangle x b c:** From two different points b, c, adds a third point x such that the triangle xbc is equilateral. Adds the two side congruence statements xb=bc and xc=bc, as well as the two angle congruence statements that the angles xbc and xcb are congruent, as well as angles xbc and cxb.

- **eqangle2 x a b c:** From three non-collinear points a, b, c, adds a third point x such that the quadrilateral abcx has two opposed angles that are congruent, bax and bcx. Adds the statement that angles bax and bcx are congruent.

- **eqdia_quadrangle a b c d:**

- **eqdistance x a b c:**

- **foot x a b c:**

- **free a:** Adds a point a with random coordinates.

- **incenter x a b c:**

- **incenter2 x y z i a b c:**

- **excenter x a b c:**

- **excenter2 x y z i a b c:**

- centroid x y z i a b c

- ninepoints x y z i a b c

- intersection_cc x o w a

- intersection_lc x a o b

- intersection_ll x a b c d

- intersection_lp x a b c m n

- intersection_lt x a b c d e

- intersection_pp x a b c d e f

- intersection_tt x a b c d e f

- iso_triangle a b c

- lc_tangent x a o

- midpoint x a b

- mirror x a b

- nsquare x a b

- on_aline x a b c d e

- on_bline x a b

- on_circle x o a

- on_line x a b

- on_pline x a b c

- on_tline x a b c

- orthocenter x a b c

- parallelogram a b c x

- pentagon a b c d e

- psquare x a b

- quadrangle a b c d

- r_trapezoid a b c d

- r_triangle a b c

- rectangle a b c d

- reflect x a b c

- risos a b c

- segment a b

- shift x b c d

- square a b x y

- isquare a b c d

- trapezoid a b c d

- triangle a b c

- triangle12 a b c

- 2l1c x y z i a b c o

- e5128 x y a b c d

- 3peq x y z a b c

- trisect x y a b c

- trisegment x y a b

- on_dia x a b

- ieq_triangle a b c

- on_opline x a b

- cc_tangent0 x y o a w b

- cc_tangent x y z i o a w b

- eqangle3 x a b d e f

- tangent x y a o b

- on_circum x a b c

New Definitions
---------------

- on_pline0 x a b c

- iso_triangle0 a b c

- iso_triangle_vertex x b c

- iso_triangle_vertex_angle x b c

- on_aline0 x a b c d e f g

- eqratio x a b c d e f g

- eqratio6 x a c e f g h

- rconst a b c x r

- aconst a b c x r

- s_angle a b x y

- lconst x a y