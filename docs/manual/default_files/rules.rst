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

.. |r00| image:: ../../_static/Images/rules/r00.png
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
     - :math:`|OA|=|OB|=|OC|=|OD|\implies ABCD\text{ in a circle}`
     - Four points A, B, C, D equidistant from a center O all lie on a same circle. (One side of the definition of a circle.)

.. |r01| image:: ../../_static/Images/rules/r01.png
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
     - 

.. |r02| image:: ../../_static/Images/rules/r02.png
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
     - :math:`ABPQ\text{ in a circle}\implies \angle (PA\times PB)=\angle (QA\times QB)`
     - 

.. |r03| image:: ../../_static/Images/rules/r03.png
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
     - :math:`\angle (PA\times PB)=\angle (QA\times QB) \implies ABPQ\text{ in a circle}`
     - 

.. |r04| image:: ../../_static/Images/rules/r04.png
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
     - :math:`\begin{cases}ABCPQR\text{ in a circle}\\ \angle (CA\times CB)=\angle (RP\times RQ)\end{cases}\implies |AB|=|PQ|`
     - 

.. |r05| image:: ../../_static/Images/rules/r05.png
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
     - 

.. |r06| image:: ../../_static/Images/rules/r06.png
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
     - 

.. |r07| image:: ../../_static/Images/rules/r07.png
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

.. |r08| image:: ../../_static/Images/rules/r08.png
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
     - 

.. |r09| image:: ../../_static/Images/rules/r09.png
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

.. |r11| image:: ../../_static/Images/rules/r11.png
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

.. |r12| image:: ../../_static/Images/rules/r12.png
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
     - 

.. |r13| image:: ../../_static/Images/rules/r13.png
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
     - 

.. |r14| image:: ../../_static/Images/rules/r14.png
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

.. |r15| image:: ../../_static/Images/rules/r15.png
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

.. |r16| image:: ../../_static/Images/rules/r16.png
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

.. |r17| image:: ../../_static/Images/rules/r17.png
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

.. |r18| image:: ../../_static/Images/rules/r18.png
    :width: 100%

r19 : right_triangle_midp2cong
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r19|
     - :math:`\begin{cases}AB\perp BC \\ M\text{ midpoint of}AC\end{cases} \implies |AM|=|BM|`
     - 

.. |r19| image:: ../../_static/Images/rules/r19.png
    :width: 100%

r20 : circle2perp
^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r20|
     - :math:`\begin{cases}O \text{ center of the circle } ABC \\ OAC\text{ collinear} \end{cases}\implies AB \perp BC`
     - 

.. |r20| image:: ../../_static/Images/rules/r20.png
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
     - :math:`\begin{cases}ABCD\text{ in a circle} \\ AB \parallel CD\end{cases} \implies \angle (AD\times CD) = \angle (CD\times CB)`
     - 

.. |r21| image:: ../../_static/Images/rules/r21.png
    :width: 100%

r22 : midp_perp2cong
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r22|
     - :math:`\begin{cases}M \text{ midpoint of }AB \\ OM\perp AB \end{cases} \implies |OA|=|OB|`
     - 

.. |r22| image:: ../../_static/Images/rules/r22.png
    :width: 100%

r23 : cong2perp
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Statement
     - Description
   * - |r23|
     - :math:`|AP|=|BP| \wedge |AQ|=|BQ| \implies AB\perp PQ`
     - 

.. |r23| image:: ../../_static/Images/rules/r23.png
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
     - :math:`\begin{cases}|AP|=|BP| \\ |AQ|=|BQ| \\ ABPQ\text{ in a circle}\end{cases} \implies PA\perp AQ`
     - 

.. |r24| image:: ../../_static/Images/rules/r24.png
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

.. |r25| image:: ../../_static/Images/rules/r25.png
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

.. |r26| image:: ../../_static/Images/rules/r26.png
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

.. |r27| image:: ../../_static/Images/rules/r27.png
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

.. |r28| image:: ../../_static/Images/rules/r28.png
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

.. |r29| image:: ../../_static/Images/rules/r29.png
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

.. |r30| image:: ../../_static/Images/rules/r30.png
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

.. |r31| image:: ../../_static/Images/rules/r06.png
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

.. |r32| image:: ../../_static/Images/rules/r32.png
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

.. |r33| image:: ../../_static/Images/rules/r33.png
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

.. |r34| image:: ../../_static/Images/rules/r34.png
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

.. |r35| image:: ../../_static/Images/rules/r35.png
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
     - :math:`\begin{cases}\angle (BA\times BC) = \angle (QP\times QR) \\ \angle (CA\times CB) = \angle (RP\times RQ)\\ |AB| = |PQ| \\ |BC| = |QR| \\ ABC\text{ non-collinear}\\ |AP| = |QB| \end{cases}\implies \Delta ABC\cong \Delta PQR`
     - 

.. |r36| image:: ../../_static/Images/rules/r36.png
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
     - :math:`\begin{cases}\angle (BA\times BC) = \angle (QP\times QR) \\ \angle (CA\times CB) = \angle (RP\times RQ)\\ |AB| = |PQ| \\ |BC| = |QR| \\ ABC\text{ non-collinear}\\|AP| = |QB| \end{cases}\implies \Delta ABC\cong^2 \Delta PQR`
     - 

.. |r37| image:: ../../_static/Images/rules/r37.png
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

.. |r38| image:: ../../_static/Images/rules/r38.png
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

.. |r39| image:: ../../_static/Images/rules/r39.png
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

.. |r40| image:: ../../_static/Images/rules/r40.png
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

.. |r41| image:: ../../_static/Images/rules/r41.png
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

.. |r42| image:: ../../_static/Images/rules/r42.png
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

.. |r43| image:: ../../_static/Images/rules/r43.png
    :width: 100%

r44 : Pappus's theorem
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - :math:`\text{coll}(A, B, C) \wedge \text{coll}(P, Q, R) \wedge \text{coll}(X, A, Q)`
       :math:`\wedge \text{coll}(X, P, B) \wedge \text{coll}(Y, A, R) \wedge \text{coll}(Y, P, C)`
       :math:`\wedge \text{coll}(Z, B, R) \wedge \text{coll}(Z, C, Q)`
       :math:`\implies \text{coll}(X, Y, Z)`
     - Description
   * - |r44|
     -
       .. code-block :: text

         coll A B C, coll P Q R, coll X A Q, coll X P B, coll Y A R, coll Y P C, coll Z B R, coll Z C Q
         => coll X Y Z
     -

.. |r44| image:: ../../_static/Images/rules/r44.png
    :width: 100%

r45 : Simson line theorem
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - :math:`\text{cyclic}(A, B, C, P) \wedge \text{coll}(A, L, C) \wedge \text{perp}(P, L, A, C)`
       :math:`\wedge \text{coll}(M, B, C) \wedge \text{perp}(P, M, B, C)`
       :math:`\wedge \text{coll}(N, A, B) \wedge \text{perp}(P, N, A, B)`
       :math:`\implies \text{coll}(L, M, N)`
     - Description
   * - |r45|
     -
       .. code-block :: text

         cyclic A B C P, coll A L C, perp P L A C, coll M B C, perp P M B C, coll N A B, perp P N A B
         => coll L M N
     - 

.. |r45| image:: ../../_static/Images/rules/r45.png
    :width: 100%

r46 : Incenter theorem
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - :math:`\text{eqangle}(A, B, A, X, A, X, A, C) \wedge \text{eqangle}(B, A, B, X, B, X, B, C)`
       :math:`\wedge \text{ncoll}(A, B, C)`
       :math:`\implies \text{eqangle}(C, B, C, X, C, X, C, A)`
     - Description
   * - |r46|
     -
       .. code-block :: text

         eqangle A B A X A X A C, eqangle B A B X B X B C, ncoll A B C
         => eqangle C B C X C X C A
     - 

.. |r46| image:: ../../_static/Images/rules/r46.png
    :width: 100%

r47 : Circumcenter theorem
^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - Formal Description
     - Description
   * - |r47|
     -
       :math:`\text{midp}(m, a, b) \wedge \text{perp}(x, m, a, b) \wedge \text{midp}(n, b, c)`
       :math:`\wedge \text{perp}(x, n, b, c) \wedge \text{midp}(p, c, a)`
       :math:`\implies \text{perp}(x, p, c, a)`

       .. code-block :: text

         midp m a b, perp x m a b, midp n b c, perp x n b c, midp p c a
         => perp x p c a
     - 

.. |r47| image:: ../../_static/Images/rules/r47.png
    :width: 100%

r48 : Centroid theorem
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - :math:`\text{midp}(m, a, b) \wedge \text{coll}(m, x, c)`
       :math:`\wedge \text{midp}(n, b, c) \wedge \text{coll}(n, x, c)`
       :math:`\wedge \text{midp}(p, c, a)`
       :math:`\implies \text{coll}(x, p, b)`
     - Description
   * - |r48|
     -
       .. code-block :: text

         midp m a b, coll m x c, midp n b c, coll n x c, midp p c a
         => coll x p b
     - 

.. |r48| image:: ../../_static/Images/rules/r48.png
    :width: 100%

r49 : Recognize center of cyclic
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25 25
   :header-rows: 1

   * - Figure
     - :math:`\text{circle}(O, A, B, C) \wedge \text{cyclic}(A, B, C, D)`
       :math:`\implies \text{cong}(O, A, O, D)`
     - Description
   * - |r49|
     -
       .. code-block :: text

         circle O A B C, cyclic A B C D
         => cong O A O D
     - 

.. |r49| image:: ../../_static/Images/rules/r49.png
    :width: 100%