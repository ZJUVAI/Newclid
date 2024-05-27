Definitions
===========

Definitions are the basic building blocks for the statement of problems. Each definition works as a function, demanding a certain collection of arguments, in order to create new points, and add corresponding predicates to the proof state (see details in :ref:`Adding new problems`).

The definitions available in the defs.txt file are the following (definitions in section :ref:`New Definitions` were added by us and are available in new_defs.txt):

- **angle_bisector x a b c:** From non-collinear points a, b, c, creates x in the internal bisector of angle abc, with vertex at b. Adds the statement that angle abx and angle xbc are congruent. Construction returns a line that can be subjected to intersections.

- **angle_mirror x a b c:** From non-collinear points a, b, c, creates x on the opposite side of bc with respect to a in a way that angle abx doubles angle abc. Adds the statement that angle abc and angle cbx are congruent. Construction returns a ray that can be subjected to intersections.

- **circle x a b c:** From non-collinear points a, b, c, creates x the center of the circle through a, b, c. Adds the congruence statements that xa=xb and xb=xc.

- **circumcenter x a b c:** Same construction as **circle x a b c**.

- **eq_quadrangle a b c d:** From nothings, adds four points in a quadrilateral abcd with two opposing sides (AD and BC) of same length. Adds the congruence statement that ad=bc.

- **iso_trapezoid a b c d:** From nothing, adds four points on a trapezoid abcd with parallel opposing sides ab and cd and non-parallel opposing sides ad and bc of same length. Adds the congruence statement that ad=bc and the parallel statement that ab//cd.

- **eq_triangle x b c:** From two different points b, c, adds a third point x such that the triangle xbc is equilateral. Adds the two side congruence statements xb=bc and xc=bc, as well as the two angle congruence statements that the angles xbc and xcb are congruent, as well as angles xbc and cxb.

- **eqangle2 x a b c:** From three non-collinear points a, b, c, adds a third point x such that the quadrilateral abcx has two opposed angles that are congruent, bax and bcx. Adds the statement that angles bax and bcx are congruent. Should be able to be subjected to intersections.

- **eqdia_quadrangle a b c d:** From nothing, adds four points on a quadrilateral abcd with the two diagonals of same length. Adds the congruence statement that bd=ac.

- **eqdistance x a b c:** From two different points b, c, and with a base point a (that can be b or c themselves), adds x such that the distance from x to a is equal to the distance from b to c. Adds the congruence statement that ax=bc. Construction returns a circle that can be subjected to intersections.

- **foot x a b c:** From three non-collinear points a, b, c, adds x that is the perpendicular projection of a onto line bc. Adds the statements that x, b, and c are collinear, and that ax is perpendicular to bc.

- **free a:** Adds a point a with random coordinates.

- **incenter x a b c:** From three non-collinear points a, b, c, adds x the incenter of the triangle abc. Adds the corresponding three angle congruence statements corresponding to the fact that the incenter is the meeting of the three internal bisctors of the angles of the triangle.

- **incenter2 x y z i a b c:** From three non-collinear points a, b, c, adds i, the incenter of the triangle abc, as well as x, y, and z, the tangent points of the incircle with sides bc, ac, and ab, respectively. Adds the three angle congruence statements corresponding to the fact that the incenter is the meeting of the three internal bisectors of the angles of the triangle, as well as the three collinear statements that place x, y, and z in the corresponding sides of the triangle abc. It also adds the perpendicular statements that ix is perpendicular to bc, that iy is perpendicular to ac, and that iz is perpendicular to ab, given by the tangency of circle and triangle. Finally, it adds the congruence statements ix=iy and iy=iz, given by the fact that x, y, z are in the circle of center i.

- **excenter x a b c:** From three non-collinear points a, b, c, adds x the excenter of triangle abc in a way that the corresponding excircle is externally tangent to side bc. Symbolically, it works exactly as the incenter construction because the angle constructions in DD do not differentiate the two bisectors of an angle crossing.

- **excenter2 x y z i a b c:** From three non-collinear points a, b, c, adds i, the excenter of the triangle abc in a way that the corresponding excircle is externally tangent to side bc. It also adds x, y, and z, the tangent points of the incircle with the lines containing sides bc, ac, and ab, respectively. Symbolically, it works exactly as the incenter construction because the angle constructions in DD do not differentiate the two bisectors of an angle crossing.

- **centroid x y z i a b c:** 

- **ninepoints x y z i a b c:** 

- **intersection_cc x o w a:** From three non-colinear points, o, w, and a, adds x, the other intersection of the circle of center o through a and the circle of center w through a. Adds the two congruence statements oa=ox and wa=wx corresponding to x being in the circle of center o through and in the circle of center w through a, respectively.

- **intersection_lc x a o b:** From three points, a, o, and b, b different from both a and o, such that bo is not perpendicular to ba (to avoid the situation of a line tangent to a circle at b), adds point x, the second intersection of line ab with the circle of center o going through b. Adds the statements of the colinearity between a, b, and x, and the congruence statement ob=ox, that guarantees that x is in the circle of center o and going through b.

- **intersection_ll x a b c d:** 

- **intersection_lp x a b c m n:** 

- **intersection_lt x a b c d e:** 

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