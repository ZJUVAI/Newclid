Rules
=====

Rules are the deduction rules that allow, from a given set of true facts, the derivation of new ones. Each rule asks for a collection of arguments, demanded by its premise predicates, that has to be "matched". Next, the rule is "applied", at which point the corresponding predicate is added to the proof state.

As a standard, rules are labelled in order (r00 to r49), but some rules have more specific names, for readability. The naming shows in the proof step, as the reason a proof step is true.

Legacy rules
------------

r00 : Perpendiculars give parallel
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r00|
     - :math:`\begin{cases}AB \perp CD\\ CD \perp EF \\ABE \text{ non-collinear}\end{cases} \implies AB \parallel EF`
     - Two lines AB, EF, that are orthogonal to a same line CD are parallel to one another.

.. |r00| image:: ../../_static/images/rules/r00.png
    :width: 100%



r01 : Definition of circle
^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r01|
     - :math:`|OA|=|OB|=|OC|=|OD|\implies ABCD\text{ on a circle}`
     - Four points A, B, C, D equidistant from a center O all lie on a same circle. (One side of the definition of a circle.)

.. |r01| image:: ../../_static/images/rules/r01.png
    :width: 100%

r02 : eqangle2para
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r02|
     - :math:`\angle (AB \times PQ)=\angle (CD \times PQ)\implies AB \parallel CD`
     - If two lines AB and CD define the same angle with respect to a fixed transverse line PQ, they are parallel.

.. |r02| image:: ../../_static/images/rules/r02.png
    :width: 100%

r03 : cyclic2eqangle
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r03|
     - :math:`ABPQ\text{ on a circle}\implies \angle (PA\times PB)=\angle (QA\times QB)`
     - Two angles with the vertices P, Q on a circle that determine the same arc AB on that same circle are congruent.

.. |r03| image:: ../../_static/images/rules/r03.png
    :width: 100%

r04 : eqangle2cyclic
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r04|
     - :math:`\angle (PA\times PB)=\angle (QA\times QB) \implies ABPQ\text{ on a circle}`
     - Reverse direction of r03: If P, Q are vertices of congruent angles, and A and B are the intersections of the legs of the angles with vertices P and Q, there is a circle through A, B, P, and Q.

.. |r04| image:: ../../_static/images/rules/r04.png
    :width: 100%

r05 : eqangle_on_circle2cong
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r05|
     - :math:`\begin{cases}ABCPQR\text{ on a circle}\\ \angle (CA\times CB)=\angle (RP\times RQ)\end{cases}\implies |AB|=|PQ|`
     - From r03, two congruent angles on a circle determine arcs on that circle of the same length. This rule says that arcs of the same length determine chords of the same length on the same circle.

.. |r05| image:: ../../_static/images/rules/r05.png
    :width: 100%

r06 : Base of half triangle
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r06|
     - :math:`\begin{cases}E\text{ midpoint of } AB\\ F\text{ midpoint of }AC\end{cases} \implies EF \parallel BC`
     - The line connecting the midpoints of two sides of a triangle is parallel to the third side of the same triangle. (This is a special instance of Thales' Theorem with "midpoint" predicates).

.. |r06| image:: ../../_static/images/rules/r06.png
    :width: 100%

r07 : para2eqratio3
^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r07|
     - :math:`\begin{cases}AB\parallel CD\\ OAC \text{ collinear}\\ OBD\text{ collinear}\end{cases}\implies \begin{cases}\frac{OA}{OC}=\frac{OB}{OD}\\ \frac{AO}{AC}=\frac{BO}{BD}\\ \frac{OC}{AC}=\frac{OD}{BD}\end{cases}`
     - This is an instance of Thales's theorem, saying that two parallel lines AB and CD cut by two intersecting transverse lines AC and BD, will determine a collection of proportional segments.

.. |r07| image:: ../../_static/images/rules/r07.png
    :width: 100%

r08 : perp_perp2eqangle
^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r08|
     - :math:`AB \perp CD \wedge EF \perp GH \implies \angle (AB\times EF) = \angle (CD\times GH)`
     -

.. |r08| image:: ../../_static/images/rules/r08.png
    :width: 100%

r09 : Sum of angles of a triangle
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r09|
     - :math:`\begin{cases}\angle (AB\times CD)=\angle (MN\times PQ)\\ \angle (CD\times EF)=\angle (PQ\times RU)\end{cases}\implies \angle(AB\times EF)=\angle(MN\times RU)`
     - This rule says that if two triangles have two pairs of congruent angles, the third pair of angles will be congruent as well. It is a non-numerical version of the statement that the angles of a triangle always add to a given constant.

.. |r09| image:: ../../_static/images/rules/r09.png
    :width: 100%

r10 : Ratio cancellation
^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - (Just a multiplication)
     - :math:`\frac{AB}{CD} = \frac{MN}{PQ} \wedge \frac{CD}{EF} = \frac{PQ}{RU} \implies \frac{AB}{EF} = \frac{MN}{RU}`
     - This is a simple algebraic fact: if you multiply the two equalities from the hypothesis together, there will be a cancellation of numerators and denominators giving you the consequence.

r11 : eqratio2angle_bisector
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r11|
     - :math:`\begin{cases}\frac{DB}{DC} = \frac{AB}{AC} \\DBC\text{ collinear} \end{cases}\implies \angle (AB\times AD)=\angle(AD\times AC)`
     -

.. |r11| image:: ../../_static/images/rules/r11.png
    :width: 100%

r12 : Bisector theorem
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r12|
     - :math:`\begin{cases}\angle (AB\times AD) = \angle (AD\times AC) \\ DBC\text{ collinear}\end{cases} \implies \frac{DB}{DC} = \frac{AB}{AC}`
     -

.. |r12| image:: ../../_static/images/rules/r12.png
    :width: 100%

r13 : Isosceles triangle equal angles
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r13|
     - :math:`|OA|=|OB| \implies \angle (OA\times AB) = \angle (AB\times OB)`
     - The theorem says that the base angles of an isosceles triangle are congruent.

.. |r13| image:: ../../_static/images/rules/r13.png
    :width: 100%

r14 : Equal base angles imply isosceles
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r14|
     - :math:`\angle (AO\times AB) = \angle (BA\times BO) \implies |OA|=|OB|`
     - This is the reverse direction of r13, saying that if the base angles of a triangle are congruent, the triangle is isosceles.

.. |r14| image:: ../../_static/images/rules/r14.png
    :width: 100%

r15 : circle_perp2eqangle
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r15|
     - :math:`\begin{cases} O\text{ center of circle }ABC \\ OA \perp AX\end{cases} \implies \angle (AX\times AB) = \angle (CA\times CB)`
     -

.. |r15| image:: ../../_static/images/rules/r15.png
    :width: 100%

r16 : circle_eqangle2perp
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r16|
     - :math:`\begin{cases} O\text{ center of circle }ABC \\ \angle (AX\times AB)=\angle(CA\times CB)\end{cases} \implies OA\perp AX`
     -

.. |r16| image:: ../../_static/images/rules/r16.png
    :width: 100%

r17 : circle_midp2eqangle
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r17|
     - :math:`\begin{cases} O\text{ center of circle }ABC \\ M\text{ midpoint of }BC\end{cases} \implies \angle(AB\times AC)=\angle(OB\times OM)`
     -

.. |r17| image:: ../../_static/images/rules/r17.png
    :width: 100%

r18 : eqangle2midp
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r18|
     - :math:`\begin{cases} O\text{ center of circle }ABC \\ MBC\text{ collinear}\\ \angle(AB\times AC)=\angle(OB\times OM)\end{cases} \implies M\text{ midpoint of }BC`
     -

.. |r18| image:: ../../_static/images/rules/r18.png
    :width: 100%

r19 : Hypothenuse is diameter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r19|
     - :math:`\begin{cases}AB\perp BC \\ M\text{ midpoint of}AC\end{cases} \implies |AM|=|BM|`
     - This rule says that the hypothenuse of a right triangle is a diameter of its circumcircle, or that the midpoint of the hypothenuse is the circumcenter of the right triangle.

.. |r19| image:: ../../_static/images/rules/r19.png
    :width: 100%

r20 : Diameter is hypotenuse
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r20|
     - :math:`\begin{cases}O \text{ center of the circle } ABC \\ OAC\text{ collinear} \end{cases}\implies AB \perp BC`
     - This theorem is the reverse direction of r19. It says that if two points are the edges of the diameter of a circle, and at the same time are vertices of an inscribed triangle, the triangle has a right angle at the third vertex.

.. |r20| image:: ../../_static/images/rules/r20.png
    :width: 100%

r21 : cyclic_para2eqangle
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r21|
     - :math:`\begin{cases}ABCD\text{ on a circle} \\ AB \parallel CD\end{cases} \implies \angle (AD\times CD) = \angle (CD\times CB)`
     -

.. |r21| image:: ../../_static/images/rules/r21.png
    :width: 100%

r22 : Bisector Construction
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r22|
     - :math:`\begin{cases}M \text{ midpoint of }AB \\ OM\perp AB \end{cases} \implies |OA|=|OB|`
     - This rule says that the perpendicular line through the midpoint of the segment is the perpendicular bisector of the segment (the locus of all equidistant points to the vertices of the segment).

.. |r22| image:: ../../_static/images/rules/r22.png
    :width: 100%

r23 : Bisector is perpendicular
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r23|
     - :math:`|AP|=|BP| \wedge |AQ|=|BQ| \implies AB\perp PQ`
     - This rule is the reverse direction of r22. It says that the locus of the points that are equidistant to the two vertices of a segment AB is a straight line perpendicular to AB.

.. |r23| image:: ../../_static/images/rules/r23.png
    :width: 100%

r24 : cong_cyclic2perp
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r24|
     - :math:`\begin{cases}|AP|=|BP| \\ |AQ|=|BQ| \\ ABPQ\text{ on a circle}\end{cases} \implies PA\perp AQ`
     -

.. |r24| image:: ../../_static/images/rules/r24.png
    :width: 100%

r25 : midp2para
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r25|
     - :math:`\begin{cases}M\text{ midpoint of }AB \\M \text{ midpoint of }CD\end{cases} \implies AC \parallel BD`
     -

.. |r25| image:: ../../_static/images/rules/r25.png
    :width: 100%

r26 : Diagonals of parallelogram
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r26|
     - :math:`\begin{cases}M \text{ midpoint of }AB \\ AC \parallel BD \\ AD \parallel BC \end{cases}\implies M \text{ midpoint of }CD`
     -

.. |r26| image:: ../../_static/images/rules/r26.png
    :width: 100%

r27 : eqratio_sameside2para
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r27|
     - :math:`\begin{cases}\frac{OA}{AC}=\frac{OB}{BD}\\ OAC\text{ collinear}\\OBD\text{ collinear}\\ OAC\text{ has the same orientation as }BOD\implies AB\parallel CD\end{cases}\implies AB\parallel CD`
     -

.. |r27| image:: ../../_static/images/rules/r27.png
    :width: 100%

r28 : para2coll
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r28|
     - :math:`AB \parallel AC \implies ABC\text{ collinear}`
     -

.. |r28| image:: ../../_static/images/rules/r28.png
    :width: 100%

r29 : midp2eqratio
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r29|
     - :math:`\begin{cases} M \text{ midpoint of }AB \\ N\text{ midpoint of } CD \end{cases}\implies \frac{MA}{AB} = \frac{NC}{CD}`
     -

.. |r29| image:: ../../_static/images/rules/r29.png
    :width: 100%

r30 : eqangle_perp2perp
^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r30|
     - :math:`\begin{cases}\angle (AB\times PQ)=\angle (CD\times UV) \\ PQ\perp UV \end{cases}\implies AB\perp CD`
     -

.. |r30| image:: ../../_static/images/rules/r30.png
    :width: 100%

r31 : eqratio_cong2cong
^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r31|
     - :math:`\frac{AB}{PQ} = \frac{CD}{UV} \wedge |PQ| = |UV| \implies |AB| = |CD|`
     -

.. |r31| image:: ../../_static/images/rules/r06.png
    :width: 100%

r32 : cong_cong2contri
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r32|
     - :math:`\begin{cases}|AB| = |PQ| \\ |BC| = |QR| \\ |CA| = |RP|\end{cases}\implies \Delta ABC\cong^\ast \Delta PQR`
     -

.. |r32| image:: ../../_static/images/rules/r32.png
    :width: 100%

r33 : cong_eqangle2contri
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r33|
     - :math:`\begin{cases}|AB| = |PQ| \\ |BC| = |QR| \\ \angle (BA\times BC) = \angle (QP\times QR)\end{cases}\implies \Delta ABC\cong^\ast\Delta PQR`
     -

.. |r33| image:: ../../_static/images/rules/r33.png
    :width: 100%

r34 : eqangle2simtri
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r34|
     - :math:`\begin{cases}\angle (BA\times BC) = \angle (QP\times QR) \\ \angle (CA\times CB) = \angle (RP\times RQ)\end{cases}\implies \Delta ABC\sim \Delta PQR`
     -

.. |r34| image:: ../../_static/images/rules/r34.png
    :width: 100%

r35 : eqangle2simtri2
^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r35|
     - :math:`\begin{cases}\angle (BA\times BC) = \angle (QR\times QP) \\ \angle (CA\times CB) = \angle (RQ\times RP)\end{cases}\implies \Delta ABC\sim^2 \Delta PQR`
     -

.. |r35| image:: ../../_static/images/rules/r35.png
    :width: 100%

r36 : eqangle_cong2contri
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r36|
     - :math:`\begin{cases}\angle (BA\times BC) = \angle (QP\times QR) \\ \angle (CA\times CB) = \angle (RP\times RQ)\\ |AB| = |PQ| \\ ABC\text{ non-collinear} \end{cases}\implies \Delta ABC\cong \Delta PQR`
     -

.. |r36| image:: ../../_static/images/rules/r36.png
    :width: 100%

r37 : eqangle_cong2contri
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r37|
     - :math:`\begin{cases}\angle (BA\times BC) = \angle (QP\times QR) \\ \angle (CA\times CB) = \angle (RP\times RQ)\\ |AB| = |PQ| \\ ABC\text{ non-collinear} \end{cases}\implies \Delta ABC\cong^2 \Delta PQR`
     -

.. |r37| image:: ../../_static/images/rules/r37.png
    :width: 100%

r38 : eqratio_eqangle2simtri
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r38|
     - :math:`\begin{cases}\frac{BA}{BC} = \frac{QP}{QR} \\ \frac{CA}{CB} = \frac{RP}{RQ}\\ ABC\text{ non-collinear} \end{cases}\implies \Delta ABC\sim^\ast \Delta PQR`
     -

.. |r38| image:: ../../_static/images/rules/r38.png
    :width: 100%

r39 : eqratio_eqangle2simtri
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r39|
     - :math:`\begin{cases}\frac{BA}{BC} = \frac{QP}{QR} \\ \angle (BA\times BC)\rangle = \angle (QP\times QR)\\ ABC\text{ non-collinear}\end{cases} \implies \Delta ABC\sim^\ast \Delta PQR`
     -

.. |r39| image:: ../../_static/images/rules/r39.png
    :width: 100%

r40 : eqratio_eqratio_cong2contri
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r40|
     - :math:`\begin{cases}\frac{BA}{BC} = \frac{QP}{QR} \\ \frac{CA}{CB} = \frac{RP}{RQ}\\ ABC\text{ non-collinear} \\ |AB| = |PQ|\end{cases}\implies ABC\cong^\ast PQR`
     -

.. |r40| image:: ../../_static/images/rules/r40.png
    :width: 100%

r41 : para2eqratio
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r41|
     - :math:`\begin{cases}AB\parallel CD \\ MAD\text{ collinear} \\ NBC \text{ collinear} \\ \frac{MA}{MD}=\frac{NB}{NC}\\ MAD \text{ has the same orientation as }NBC \end{cases}\implies MN\parallel A B`
     -

.. |r41| image:: ../../_static/images/rules/r41.png
    :width: 100%

r42 : eqratio62para
^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r42|
     - :math:`\begin{cases}AB\parallel CD \\ MAD\text{ collinear} \\ NBC\text{ collinear}\end{cases}\implies \frac{MA}{MD}=\frac{NB}{NC}`
     -

.. |r42| image:: ../../_static/images/rules/r42.png
    :width: 100%

New rules
---------

r43 : Orthocenter theorem
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r43|
     - :math:`AB\perp CD \wedge AC\perp BD\implies AD\perp BC`
     -

.. |r43| image:: ../../_static/images/rules/r43.png
    :width: 100%

r44 : Pappus's theorem
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r44|
     - :math:`\begin{cases}ABC\text{ collinear} \\ PQR\text{ collinear} \\ XAQ\text{ collinear}\\ XPB\text{ collinear} \\ YAR\text{ collinear} \\ YPC\text{ collinear}\\ ZBR\text{ collinear} \\ ZCQ\text{ collinear}\end{cases}\implies XYZ\text{ collinear}`
     -

.. |r44| image:: ../../_static/images/rules/r44.png
    :width: 100%

r45 : Simson line theorem
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r45|
     - :math:`\begin{cases} ABCP\text{ on a circle} \\ ALC\text{ collinear} \\ PL\perp AC\\ \text{coll}(M, B, C) \\ PM\perp BC\\ NAB\text{ collinear} \\ PN\perp AB\end{cases}\implies LMN\text{ collinear}`
     -

.. |r45| image:: ../../_static/images/rules/r45.png
    :width: 100%

r46 : Incenter theorem
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r46|
     - :math:`\begin{cases}\angle(AB\times AX)=\angle (AX\times AC) \\ \angle(BA\times BX)=\angle (BX\times BC)\\ ABC\text{ non-collinear}\end{cases}\implies \angle (CB\times CX)=\angle (CX\times CA)`
     -

.. |r46| image:: ../../_static/images/rules/r46.png
    :width: 100%

r47 : Circumcenter theorem
^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r47|
     - :math:`\begin{cases}M\text{ midpoint of }AB \\ XM\perp AB \\ N\text{ midpoint of }BC\\ XN\perp BC \\ P\text{ midpoint of }CA\end{cases}\implies XP\perp CA`
     -

.. |r47| image:: ../../_static/images/rules/r47.png
    :width: 100%

r48 : Centroid theorem
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r48|
     - :math:`\begin{cases}M\text{ midpoint of }AB \\ MXC\text{ collinear}\\ N\text{ midpoint of }BC \\ NXC\text{ collinear}\\ P\text{ midpoint of }CA\end{cases}\implies XPB\text{ collinear}`
     -

.. |r48| image:: ../../_static/images/rules/r48.png
    :width: 100%

r49 : Recognize center of cyclic (circle)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r49|
     - :math:`\begin{cases}O\text{ center of the circle }ABC \\ABCD\text{ on a circle}\end{cases}\implies OA= OD`
     -

.. |r49| image:: ../../_static/images/rules/r49.png
    :width: 100%

r50 : Recognize center of cyclic (cong)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r50|
     - :math:`\begin{cases}ABCD\text{ on a circle}\\ OA=OB\\ OC=OD\\ AB\not\parallel CD\end{cases}\implies OA=OC`
     -

.. |r50| image:: ../../_static/images/rules/r50.png
    :width: 100%

r51 : Midpoint splits in two
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - (Feeds algebraic module)
     - :math:`M\text{ midpoint of AB}\implies \frac{MA}{AB}=\frac{1}{2}`
     - This rule converts a symbolic statement (M is the midpoint of AB) into an algebraic one (the ratio between AM and AB is 1/2). This allows AR to process information from midpoints.