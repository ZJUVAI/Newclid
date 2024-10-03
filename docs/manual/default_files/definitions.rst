Definitions
===========

Definitions are the basic building blocks for the statement of problems. Each definition works as a function, demanding a certain collection of arguments, in order to create new points, and add corresponding predicates to the proof state (see details in :ref:`Adding new problems`).

The definitions available in the defs.txt file are the following (definitions in section :ref:`New Definitions` were added by us and are available in new_defs.txt):

Constructions that are not points directly should be subject to intersection.

Legacy definitions
------------------

angle_bisector x a b c
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |angle_bisector|
     - From non-collinear points a, b, c, creates x in the internal bisector of angle abc, with vertex at b.
     - :math:`\widehat{abx}=\widehat{xbc}` (eqangle b a b x b x b c).
     - Line

.. |angle_bisector| image:: ../../_static/images/defs/angle_bisector.png
    :width: 100%


angle_mirror x a b c
^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |angle_mirror|
     - From non-collinear points a, b, c, creates x on the opposite side of bc with respect to a in a way that angle abx doubles angle abc.
     - :math:`\widehat{abc}=\widehat{cbx}` (eqangle b a b c b c b x).
     - Ray

.. |angle_mirror| image:: ../../_static/images/defs/angle_mirror.png
    :width: 100%


circle x a b c
^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |circle|
     - From non-collinear points a, b, c, creates x the center of the circle through a, b, c.
     - :math:`xa=xb \wedge xb=xc`  (cong x a x b, cong x b x c)
     - Point

.. |circle| image:: ../../_static/images/defs/circle.png
    :width: 100%


circumcenter x a b c
^^^^^^^^^^^^^^^^^^^^

Same construction as **circle x a b c**.

eq_quadrangle a b c d
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |eq_quadrangle|
     - From nothings, adds four points in a quadrilateral abcd with two opposing sides (AD and BC) of same length.
     - :math:`ad=bc`  (cong d a b c)
     - Points

.. |eq_quadrangle| image:: ../../_static/images/defs/eq_quadrangle.png
    :width: 100%

iso_trapezoid a b c d
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |iso_trapezoid|
     - From nothing, adds four points on a trapezoid abcd with parallel opposing sides ab and cd and non-parallel opposing sides ad and bc of same length. Adds the congruence statement that ad=bc and the parallel statement that ab//cd.
     - :math:`ab//cd \wedge ad=bc`  (para d c a b, cong d a b c)
     - Points

.. |iso_trapezoid| image:: ../../_static/images/defs/iso_trapezoid.png
    :width: 100%

eq_triangle x b c
^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |eq_triangle|
     - From two different points b, c, adds a third point x such that the triangle xbc is equilateral.
     - :math:`\begin{cases}xb=bx \wedge bc=cx \\ \widehat{xbc} = \widehat{bcx} \wedge \widehat{cxb} = \widehat{xbc}\end{cases}`  (cong x b b c, cong b c c x; eqangle b x b c c b c x, eqangle x c x b b x b c)
     - Point

.. |eq_triangle| image:: ../../_static/images/defs/eq_triangle.png
    :width: 100%

eqangle2 x a b c
^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |eqangle2|
     - From three non-collinear points a, b, c, adds a third point x such that the quadrilateral abcx has two opposite angles that are congruent, bax and bcx.
     - :math:`\widehat{bax} = \widehat{xcb}`  (eqangle a b a x c x c b)
     - Point (Locus could be hyperbola.)

.. |eqangle2| image:: ../../_static/images/defs/eqangle2.png
    :width: 100%

eqdia_quadrangle a b c d
^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |eqdia_quadrangle|
     - From nothing, adds four points on a quadrilateral abcd with the two diagonals of same length.
     - :math:`bd=ac`  (cong d b a c)
     - Points

.. |eqdia_quadrangle| image:: ../../_static/images/defs/eqdia_quadrangle.png
    :width: 100%

eqdistance x a b c
^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |eqdistance|
     - From two different points b, c, and with a base point a (that can be either b or c itself), adds x such that the distance from x to a is equal to the distance from b to c.
     - :math:`ax=bc`  (cong x a b c)
     - Circle

.. |eqdistance| image:: ../../_static/images/defs/eqdistance.png
    :width: 100%

foot x a b c
^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |foot|
     - From three non-collinear points a, b, c, adds x that is the perpendicular projection of a onto line bc.
     - :math:`\begin{cases}x,b,c\ collinear\\ ax\perp bc\end{cases}`  (coll x b c, perp x a b c)
     - Point

.. |foot| image:: ../../_static/images/defs/foot.png
    :width: 100%

free a
^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |free|
     - From nothing, adds point a with random coordinates.
     - No statement added
     - Point

.. |free| image:: ../../_static/images/defs/free.png
    :width: 100%

incenter x a b c
^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |incenter|
     - From three non-collinear points a, b, c, adds x the incenter of the triangle abc. It acknowledges the fact that it is the intersection of the three internal bisectors of the angles of the triangle.
     - :math:`\begin{cases}\widehat{bax}=\widehat{xac}\\ \widehat{acx}=\widehat{xcb}\\ \widehat{cbx}=\widehat{xba}\end{cases}`  (eqangle a b a x a x a c, eqangle c a c x c x c b, eqangle b c b x b x b a)
     - Point

.. |incenter| image:: ../../_static/images/defs/incenter.png
    :width: 100%

incenter2 x y z i a b c
^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |incenter2|
     - From three non-collinear points a, b, c, adds i, the incenter of the triangle abc, as well as x, y, and z, the tangent points of the incircle with sides bc, ac, and ab, respectively. It acknowledges the fact that the incenter is the intersection of the three internal bisectors of the angles of the triangle, and that a radius of a circle and the tangent line are perpendicular at the point of tangency.
     - :math:`\begin{cases}\widehat{bax}=\widehat{xac}\\ \widehat{acx}=\widehat{xcb}\\ \widehat{cbx}=\widehat{xba}\\ x,b,c\ collinear\\ ix\perp bc\\ y,c,a\ collinear\\ iy\perp ca\\ z,a,b\ collinear\\ iz\perp ab\\ ix=iy, iy=iz\end{cases}`  (eqangle a b a i a i a c, eqangle c a c i c i c b, eqangle b c b i b i b a, coll x b c, perp i x b c, coll y c a, perp i y c a, coll z a b, perp i z a b, cong i x i y, cong i y i z)
     - Points

.. |incenter2| image:: ../../_static/images/defs/incenter2.png
    :width: 100%

excenter x a b c
^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |excenter|
     - From three non-collinear points a, b, c, adds x the excenter of triangle abc in a way that the corresponding excircle is externally tangent to side bc. Symbolically, it works exactly as the incenter construction because the angle constructions in DD do not differentiate the two bisectors of an angle crossing.
     - :math:`\begin{cases}\widehat{bax}=\widehat{xac}\\ \widehat{acx}=\widehat{xcb}\\ \widehat{cbx}=\widehat{xba}\end{cases}` (eqangle a b a x a x a c, eqangle c a c x c x c b, eqangle b c b x b x b a)
     - Point

.. |excenter| image:: ../../_static/images/defs/excenter.png
    :width: 100%

excenter2 x y z i a b c
^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |excenter2|
     - From three non-collinear points a, b, c, adds i, the excenter of the triangle abc in a way that the corresponding excircle is externally tangent to side bc. It also adds x, y, and z, the tangent points of the incircle with the lines containing sides bc, ac, and ab, respectively. Symbolically, it works exactly as the incenter construction because the angle constructions in DD do not differentiate the two bisectors of an angle crossing.
     - :math:`\begin{cases}\widehat{bax}=\widehat{xac}\\ \widehat{acx}=\widehat{xcb}\\ \widehat{cbx}=\widehat{xba}\\ x,b,c\ collinear\\ ix\perp bc\\ y,c,a\ collinear\\ iy\perp ca\\ z,a,b\ collinear\\ iz\perp ab\\ ix=iy, iy=iz\end{cases}`  (eqangle a b a i a i a c, eqangle c a c i c i c b, eqangle b c b i b i b a, coll x b c, perp i x b c, coll y c a, perp i y c a, coll z a b, perp i z a b, cong i x i y, cong i y i z)
     - Points

.. |excenter2| image:: ../../_static/images/defs/excenter2.png
    :width: 100%

- **centroid x y z i a b c:**

- **ninepoints x y z i a b c:**

intersection_cc x o w a
^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |intersection_cc|
     - From three non-colinear points, o, w, and a, adds x, the other intersection of the circle of center o through a and the circle of center w through a.
     - :math:`\begin{cases}oa=ox\\ wa=wx\end{cases}`  (cong o a o x, cong w a w x)
     - Point

.. |intersection_cc| image:: ../../_static/images/defs/intersection_cc.png
    :width: 100%

intersection_lc x a o b
^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |intersection_lc|
     - From three points, a, o, and b, b different from both a and o, such that bo is not perpendicular to ba (to avoid the situation of a line tangent to a circle at b), adds point x, the second intersection of line ab with the circle of center o going through b.
     - :math:`\begin{cases}x, a, b\ collinear\\ ob=ox\end{cases}`  (coll x a b, cong o b o x)
     - Point

.. |intersection_lc| image:: ../../_static/images/defs/intersection_lc.png
    :width: 100%

intersection_ll x a b c d
^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |intersection_ll|
     - From four points a, b, c, d, such that lines ab and cd are not parallel and such that they do are not all collinear, build point x on the intersection of lines ab and cd.
     - :math:`\begin{cases}x, a, b\ collinear\\ x, c, d\ collinear\end{cases}`  (coll x a b, coll x c d)
     - Point

.. |intersection_ll| image:: ../../_static/images/defs/intersection_ll.png
    :width: 100%

intersection_lp x a b c m n
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |intersection_lp|
     - From five points a, b, c, m, and n, such that lines ab and mn are not parallel, and that c is neither on line ab nor on line mn, builds x, the intersection of line ab with the line through c that is parallel to mn.
     - :math:`\begin{cases}x, a, b\ collinear\\ cx\parallel mn\end{cases}`  (coll x a b, para c x m n)
     - Point

.. |intersection_lp| image:: ../../_static/images/defs/intersection_lp.png
    :width: 100%

intersection_lt x a b c d e
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |intersection_lt|
     - From five points a, b, c, d, and e, such that lines ab and de are not perpendicular and c is not on line ab, build x, the intersection of line ab and the line through c perpendicular to de.
     - :math:`\begin{cases}x, a, b\ collinear\\ cx\perp de\end{cases}`  (coll x a b, perp x c d e)
     - Point

.. |intersection_lt| image:: ../../_static/images/defs/intersection_lt.png
    :width: 100%

intersection_pp x a b c d e f
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |intersection_pp|
     - From six points, a, b, c, d, e, f, such that a and d are different and that lines bc and ef are not parallel, builds point x in the intersection of the line through a parallel to bc and the line through d parallel to ef.
     - :math:`\begin{cases}xa\parallel bc\\ xd\parallel ef\end{cases}`  (para x a b c, para x d e f)
     - Point

.. |intersection_pp| image:: ../../_static/images/defs/intersection_pp.png
    :width: 100%

intersection_tt x a b c d e f
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |intersection_tt|
     - From six points, a, b, c, d, e, f, such that a and d are different and lines bc and ef are not parallel, build point x in the intersection of the line through a perpendicular to bc and the line through d perpendicular to ef.
     - :math:`\begin{cases}xa\perp bc\\ xd\perp ef\end{cases}`  (perp x a b c, perp x d e f)
     - Point

.. |intersection_tt| image:: ../../_static/images/defs/intersection_tt.png
    :width: 100%

iso_triangle a b c
^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |iso_triangle|
     - From nothing, creates the three vertices a, b, c of an isosceles triangle with ab=ac. (Compare to iso_triangle0, iso_triangle_vertex, and iso_triangle_vertext_angle below).
     - :math:`\begin{cases}ab= ac\\ \widehat{abc}=\widehat{bca}\end{cases}`  (cong a b a c, eqangle b a b c c b c a)
     - Points

.. |iso_triangle| image:: ../../_static/images/defs/iso_triangle.png
    :width: 100%

lc_tangent x a o
^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |lc_tangent|
     - From two different points a, o, builds x, a point on the line perpendicular to ao through a (the line tangent to the circle of center o through a, with tangent point a). It is equivalent to on_tline x a a o (see on_tline below).
     - :math:`ax \perp ao`  (perp a x a o)
     - Line

.. |lc_tangent| image:: ../../_static/images/defs/lc_tangent.png
    :width: 100%

midpoint x a b
^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |midpoint|
     - From a pair of points a, b, that are different, builds x, the midpoint of a and b.
     - :math:`x\text{ midpoint of }ab`  (midp x a b)
     - Point

.. |midpoint| image:: ../../_static/images/defs/midpoint.png
    :width: 100%

mirror x a b
^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |mirror|
     - From two points a, b that are different, builds x, the reflection of point a with respect to point b (so that b is the midpoint of ax).
     - :math:`\begin{cases}x, a, b\text{ collinear}\\ ba=bx\end{cases}`  (coll x a b, cong b a b x)
     - Point

.. |mirror| image:: ../../_static/images/defs/mirror.png
    :width: 100%

nsquare x a b
^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |nsquare|
     - Given two distinct points a, b, builds x such that the triangle xab is an isosceles right triangle.
     - :math:`\begin{cases}xa=ab\\ xa\perp ab\end{cases}`  (cong x a a b, perp x a a b)
     - Point

.. |nsquare| image:: ../../_static/images/defs/nsquare.png
    :width: 100%

- **on_aline x a b c d e:**

- **on_bline x a b:**

- **on_circle x o a:** From two distinct points o, a, builds x a point on the circle of center o through a. Adds the congruence statement saying ox=oa. Construction returns a circle, so can be subjected to intersections. Equivalent to eqdistance x a a o (see eqdistance above).

- **on_line x a b:** From tow distinct point a, b, builds x another point on the line ab. Adds the collinearity statement saying a, b, c are on the same line. Construction returns a line, so can be subject to intersections.

- **on_pline x a b c:** From three non-colinear points a, b, c, with b different from c, builds x on the line parallel to bc through a. Adds the parallel statement saying xa is parallel to bc. Construction returns a line, so can be subjected to intersections. (Compare to the simpler on_pline0 below).

- **on_tline x a b c:** From three points a, b, c, with b different from c, builds x on the line through a perpendicular to bc. Adds the perpendicularity statement saying xa is perpendicular to bc. Construction returns a line, so can be subjected to intersections.

- **orthocenter x a b c:** From three non-collinear points a, b, and c, builds x the orthocenter of the triangle abc. Adds the three perpendicularity statement corresponding to the fact that x is in the intersection of the heights of the triangle, that is, that ax is perpendicular to bc, that bx is perpendicular to ac and that cx is perpendicular to ab.

- **parallelogram a b c x:** From three non-collinear points a, b, and c, builds x such that abcx is a parallelogram. Adds the parallel statements that ab//cx and ax//bc, as well as the congruence statements ab=cx and ax=bc.

- **pentagon a b c d e:** From nothing, creates five points a, b, c, d, e. The coordinates are a random conformal deformation (isometry combined with scaling) of a random inscribed convex pentagon.

- **psquare x a b:**

- **quadrangle a b c d:** From nothing, creates four points, a, b, c, d which are vertices of a random convex quadrilateral.

- **r_trapezoid a b c d:**

- **r_triangle a b c:**

- **rectangle a b c d:**

- **reflect x a b c:** From three non-collinear points a, b, c, in particular with b different from c, builds x the reflection of a by the line bc. Adds the congruence statements for the reflection saying ab=xb and ac=xc, as well as the perpendiculatity statement saying ax is perpendicular to bc.

- **risos a b c:** From nothing, builds a, b, c such that the triangle abc is an isosceles right triangle with a right angle at a. Adds the congruence statement ab=ac, the perpendicular statement saying ab is perpendicular ac, and also the statement refering to the congruence of the base angles, that is, that angle abc is congruent to angle bca.

- **segment a b:** From nothing, adds two points a, b, with random coordinates.

- **shift x b c d:** From three points b, c, d, with b different from d (presents the building of two points with the same coordinates), build x, the translation of b by the vector from d to c. Adds the (natural) congruence statement bx=cd and the (less natural) condition for the parallelogram xc=bd.

- **square a b x y:**

- **isquare a b c d:**

- **trapezoid a b c d:** From nothing, creates four vertices of a trapezoid abcd, with ab parallel to cd. Adds the parallel statement saying ab=cd.

- **triangle a b c:** From nothing, creates three points a, b, and c, with random coordinates.

- **triangle12 a b c:**

- **2l1c x y z i a b c o:**

2l1c x y z i a b c o
^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |2l1c|
     - Given three points o, a, b, with b in the center through a of center o, and c a point not in the line ab, build i, the center of a circle tangent to the circle centered at o through a, to the line ac and to the line bc. It also builds the tangency points x to ac, y to bc and z to the circle of center o through a.
     - :math:`\begin{cases}x, a, c\text{ collinear}\\y, b, c\text{ collinear}\\ i, o, z\text{ collinear}\\ oa=oz\\ ix=iy\\ iy=iz\\ ix\perp ac\\ iy\perp bc\end{cases}`  (coll x a c, coll y b c, coll i o z, cong o a o z, cong i y i z, perp i x a c, perp i y b c)
     - Points

.. |2l1c| image:: ../../_static/images/defs/2l1c.png
    :width: 100%

- **e5128 x y a b c d:**

- **3peq x y z a b c:**

- **trisect x y a b c:**

- **trisegment x y a b:** Given two different points a, b, builds x, y the two points trisecting the segment ab. Adds the collinearity statements saying x is in the segment ab, and the one saying y is in the segment ab, as well as the two congruent statements associated to the trisection: ax=xy and xy=yb.

- **on_dia x a b:** Given two different points a, b, builds x a point such that the triangle axb is a right triangle with a right angle at x. Adds the perpendicularity statement saying ax is perpendicular to bx. Construction returns a circle, so it can be subjected to intersections.

- **ieq_triangle a b c:**

- **on_opline x a b:** From a pair of different points a, b, builds x, a point on the line ab such that a is NOT between x and b. Adds the statement that a, b, and x are collinear. Construction returns a half-line, so can be subjected to intersections.

cc_tangent x y z i o a w b
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |cc_tangent|
     - From four points o, a, w, b, such that o is neither a nor w, and such that w and b are distinct, builds x, y, z, i on a pair of lines xy and zi that are simultaneously tangent to both the circle of center o through a and the circle of center w through b. x and z are the tangent points on the circle centered at o through a, and y and i are the tangent points on the circle centered at w through b.
     - :math:`\begin{cases}ox=oa\\ wy=wb\\ ox\perp xy\\ wy\perp yx\\oz=oa\\wi=wb\\oz\perp zi\\wi\perp iz\end{cases}`  (cong o x o a, cong w y w b, perp x o x y, perp y w y x, cong o z o a, cong w i w b, perp z o z i, perp i w i z)
     - Points

.. |cc_tangent| image:: ../../_static/images/defs/cc_tangent.png
    :width: 100%

- **eqangle3 x a b d e f:**

tangent x y a o b
^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |tangent|
     - From three different points a, b, c, builds x and y, the points of tangency of the two lines through a tangent to the circle of center o through b.
     - :math:`\begin{cases}ox=ob\\ ax\perp ox\\ oy=ob\\ ay\perp yo\end{cases}`  (cong o x o b, perp a x o x, cong o y o b, perp a y o y)
     - Points

.. |tangent| image:: ../../_static/images/defs/tangent.png
    :width: 100%

on_circum x a b c
^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 50 25 23 2
   :header-rows: 1

   * - Figure
     - Description
     - Added Statements
     - Construction
   * - |on_circum|
     - From three non-collinear points a, b, and c, builds x a point on the circle through a, b, and c.
     - :math:`\begin{cases}x, a, b, c\text{ concyclic}\end{cases}`  (cyclic a b c x)
     - Point

.. |on_circum| image:: ../../_static/images/defs/on_circum.png
    :width: 100%

New Definitions
---------------

- **on_pline0 x a b c:** From three points a, b, c, with b different from c, builds x on the line parallel to bc through a. Adds the parallel statement saying xa is parallel to bc. Construction returns a line, so can be subjected to intersections. (Compare to on_pline above). This definition was created to allow for the addition of a parallel statement on overlapping lines, by dismissing the restriction of a, b, c being non-collinear, without which r28 would be a rule that could not occur.

- **iso_triangle0 a b c:**

- **iso_triangle_vertex x b c:**

- **iso_triangle_vertex_angle x b c:**

- **on_aline0 x a b c d e f g:**

- **eqratio x a b c d e f g:** From seven points a, b, c, d, e, f, g, builds x, a point such that ab/cd=ef/gx. Adds the ratio equality statement corresponding to ab/cd=ef/gx. Construction returns a circle, that can be subjected to intersection. This definition was created to allow for the explicit prescription of eqratio statements on problems.

- **eqratio6 x a c e f g h:** From six points a, c, e, f, g, h, builds x,  a point such that ax/cx=ef/gh. Adds the ratio equality statement corresponding to ax/cx=ef/gh. Construction returns a line if ef/gh=1, and a circle otherwise, and can be subjected to intersection in any case. This definition was created to allow a common case for prescription of eqratio statements, when the new point shows up twice in the ratio equality (particularly common when subdividing a segment).

- **rconst a b c x r:** Given three points a, b, c such that a is different from b, and a fraction r, builds x a point such that ab/cx=r. r should be entered as a fraction m/n, m, n two integers separated by "/". Adds the statement corresponding exactly to ab/cx=r. The construction returns a circle, so can be subjected to intersections. This definition was created to allow for the prescription of pairs of segments satisfying a given constant ratio.

- **aconst a b c x r:**

- **s_angle a b x y:**

- **lconst x a y:** From a point a, builds x with an integer distance y from a to x. Adds the statement that the distance from a to x is y. Construction returns a circle that can be subjected to intersections. This definition was created as an entry point to add the manipulation of lengths to DDAR.