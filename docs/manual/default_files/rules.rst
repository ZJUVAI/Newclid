Rules
-----

Rules are the deduction rules that allow, from a given set of true facts, the derivation of new ones. Each rule asks for a collection of arguments, demanded by its premise predicates, that has to be "matched". Next, the rule is "applied", at which point the corresponding predicate is added to the proof state.

As a standard, rules are labelled in order (r00 to r49), but some rules have more specific names, for readability. The naming shows in the proof step, as the reason a proof step is true.

Legacy rules
------------

r00 : perp2para
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`AB \perp CD \wedge CD \perp ED \wedge \text{ncoll}(ABE) \implies AB \parallel EF`
   * -
      .. image:: ../../_static/Images/rules/r00.png
     -
       .. code-block :: text

         perp A B C D, perp C D E F, ncoll A B E
         => para A B E F

r01 : cong2cyclic
^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`|OA|=|OB|=|OC|=|OD|\implies \text{cyclic}(ABCD)`
   * -
      .. image:: ../../_static/Images/rules/r01.png
     -
       .. code-block :: text

         cong O A O B, cong O B O C, cong O C O D
         => cyclic A B C D

r02 : eqangle2para
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle AB, PQ\rangle=\langle CD, PQ\rangle\implies AB \parallel CD`
   * -
      .. image:: ../../_static/Images/rules/r02.png
     -
       .. code-block :: text

         eqangle A B P Q C D P Q
         => para A B C D

r03 : cyclic2eqangle
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{cyclic}(ABPQ)\implies \langle PA,PB\rangle=\langle QA,QB\rangle`
   * -
      .. image:: ../../_static/Images/rules/r03.png
     -
       .. code-block :: text

         cyclic A B P Q
         => eqangle P A P B Q A Q B

r04 : eqangle2cyclic
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle PA,PB\rangle=\langle QA,QB\rangle \implies \text{cyclic}(ABPQ)`
   * -
      .. image:: ../../_static/Images/rules/r04.png
     -
       .. code-block :: text

         eqangle6 P A P B Q A Q B, ncoll P A B, ncoll Q A B
         => cyclic A B P Q

r05 : eqangle_on_circle2cong
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{cyclic}(ABCPQR)\wedge \langle CA,CB\rangle=\langle RP,RQ\rangle\implies |AB|=|PQ|`
   * -
      .. image:: ../../_static/Images/rules/r05.png
     -
       .. code-block :: text

         cyclic A B C P Q R, eqangle C A C B R P R Q
         => cong A B P Q

r06 : midp2para
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{midp}(E, AB) \wedge \text{midp}(F, AC) \implies EF \parallel BC`
   * -
      .. image:: ../../_static/Images/rules/r06.png
     -
       .. code-block :: text

         midp E A B, midp F A C
         => para E F B C

r07 : para2eqratio3
^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`AB \parallel CD \wedge \text{coll}(OAC) \wedge \text{coll}(OBD)`
       :math:`\implies \text{eqratio3}(A, B, C, D, O, O)`
   * -
      .. image:: ../../_static/Images/rules/r07.png
     -
       .. code-block :: text

         para A B C D, coll O A C, coll O B D
         => eqratio3 A B C D O O

r08 : perp_perp2eqangle
^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`AB \perp CD \wedge EF \perp GH \implies \langle AB, EF\rangle = \langle CD, GH\rangle`
   * -
      .. image:: ../../_static/Images/rules/r08.png
     -
       .. code-block :: text

         perp A B C D, perp E F G H, npara A B E F
         => eqangle A B E F C D G H

r09 : eqangle2eqangle_sum
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle ab, cd\rangle = \langle mn, pq\rangle \wedge \langle cd, ef\rangle = \langle pq, ru\rangle`
       :math:`\implies \langle ab, ef\rangle = \langle mn, ru\rangle`
   * -
      .. image:: ../../_static/Images/rules/r09.png
     -
       .. code-block :: text

         eqangle a b c d m n p q, eqangle c d e f p q r u
         => eqangle a b e f m n r u

r10 : eqratio_mul
^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\frac{ab}{cd} = \frac{mn}{pq} \wedge \frac{cd}{ef} = \frac{pq}{ru} \implies \frac{ab}{ef} = \frac{mn}{ru}`
   * - no need
     -
       .. code-block :: text

         eqratio a b c d m n p q, eqratio c d e f p q r u
         => eqratio a b e f m n r u

r11 : eqratio2angle_bisector
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - Formula
   * -
      .. image:: ../../_static/Images/rules/r11.png
     -
       :math:`\frac{db}{dc} = \frac{ab}{ac} \wedge \text{coll}(dbc) \implies \langle ab, ad, ad, ac\rangle`

       .. code-block :: text

         eqratio6 d b d c a b a c, coll d b c, ncoll a b c
         => eqangle6 a b a d a d a c

r12 : angle_bisector2eqratio
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle ab, ad\rangle = \langle ad, ac\rangle \wedge \text{coll}(dbc) \implies \frac{db}{dc} = \frac{ab}{ac}`
   * -
      .. image:: ../../_static/Images/rules/r12.png
     -
       .. code-block :: text

         eqangle6 a b a d a d a c, coll d b c, ncoll a b c
         => eqratio6 d b d c a b a c

r13 : isosceles_cong2eqangle
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - Formula
   * -
      .. image:: ../../_static/Images/rules/r13.png
     -
       :math:`|OA|=|OB| \implies \langle OA, AB\rangle = \langle AB, OB\rangle`

       .. code-block :: text

         cong O A O B, ncoll O A B
         => eqangle O A A B A B O B

r14 : isosceles_eqangle2cong
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle AO, AB\rangle = \langle BA, BO\rangle \implies |OA|=|OB|`
   * -
      .. image:: ../../_static/Images/rules/r14.png
     -
       .. code-block :: text

         eqangle6 A O A B B A B O, ncoll O A B
         => cong O A O B

r15 : circle_perp2eqangle
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{circle}(O, ABC) \wedge OA \perp AX \implies \langle AX, AB\rangle = \langle CA, CB\rangle`
   * -
      .. image:: ../../_static/Images/rules/r15.png
     -
       .. code-block :: text

         circle O A B C, perp O A A X
         => eqangle A X A B C A C B

r16 : circle_eqangle2perp
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{circle}(O, ABC) \wedge \langle AX, AB\rangle=\langle CA, CB\rangle \implies \text{perp}(OA, AX)`
       :math:`\implies \text{perp}(OA, AX)`
   * -
      .. image:: ../../_static/Images/rules/r16.png
     -
       .. code-block :: text

         circle O A B C, eqangle A X A B C A C B
         => perp O A A X

r17 : circle_midp2eqangle
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{circle}(O,ABC) \wedge \text{midp}(M, BC)`
       :math:`\implies \langle AB, AC\rangle=\langle OB, OM\rangle`
   * -
      .. image:: ../../_static/Images/rules/r17.png
     -
       .. code-block :: text

         circle O A B C, midp M B C
         => eqangle A B A C O B O M

r18 : eqangle2midp
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{circle}(O,ABC) \wedge \text{coll}(MBC) \wedge \langle AB, AC\rangle=\langle OB, OM\rangle`
       :math:`\implies \text{midp}(M, BC)`
   * -
      .. image:: ../../_static/Images/rules/r18.png
     -
       .. code-block :: text

         circle O A B C, coll M B C, eqangle A B A C O B O M
         => midp M B C

r19 : right_triangle_midp2cong
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{perp}(AB, BC) \wedge \text{midp}(M, AC) \implies |AM|=|BM|`
   * -
      .. image:: ../../_static/Images/rules/r19.png
     -
       .. code-block :: text

         perp A B B C, midp M A C
         => cong A M B M

r20 : circle2perp
^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{circle}(OABC) \wedge \text{coll}(OAC) \implies \text{perp}(AB, BC)`
   * -
      .. image:: ../../_static/Images/rules/r20.png
     -
       .. code-block :: text

         circle O A B C, coll O A C
         => perp A B B C

r21 : cyclic_para2eqangle
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{cyclic}(ABCD) \wedge AB \parallel CD \implies \langle AD, CD\rangle = \langle CD, CB\rangle`
   * -
      .. image:: ../../_static/Images/rules/r21.png
     -
       .. code-block :: text

         cyclic A B C D, para A B C D
         => eqangle A D C D C D C B

r22 : midp_perp2cong
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{midp}(M, AB) \wedge \text{perp}(OM, AB) \implies |OA|=|OB|`
   * -
      .. image:: ../../_static/Images/rules/r22.png
     -
       .. code-block :: text

         midp M A B, perp O M A B
         => cong O A O B

r23 : cong2perp
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`|AP|=|BP| \wedge |AQ|=|BQ| \implies \text{perp}(AB, PQ)`
   * -
      .. image:: ../../_static/Images/rules/r23.png
     -
       .. code-block :: text

         cong A P B P, cong A Q B Q
         => perp A B P Q

r24 : cong_cyclic2perp
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`|AP|=|BP| \wedge |AQ|=|BQ| \wedge \text{cyclic}(ABPQ) \implies \text{perp}(PA, AQ)`
   * -
      .. image:: ../../_static/Images/rules/r24.png
     -
       .. code-block :: text

         cong A P B P, cong A Q B Q, cyclic A B P Q
         => perp P A A Q

r25 : midp2para
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{midp}(M, AB) \wedge \text{midp}(M, CD) \implies AC \parallel BD`
   * -
      .. image:: ../../_static/Images/rules/r25.png
     -
       .. code-block :: text

         midp M A B, midp M C D
         => para A C B D

r26 : midp_para2midp
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{midp}(M, AB) \wedge AC \parallel BD \wedge AD \parallel BC \implies \text{midp}(M, CD)`
   * -
      .. image:: ../../_static/Images/rules/r26.png
     -
       .. code-block :: text

         midp M A B, para A C B D, para A D B C
         => midp M C D

r27 : eqratio_sameside2para
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\frac{OA}{AC} = \frac{OB}{BD} \wedge \text{coll}(OAC)`
       :math:`\text{coll}(OBD) \wedge \text{sameside}(AOC, BOD)`
       :math:`\implies AB \parallel CD`
   * -
      .. image:: ../../_static/Images/rules/r27.png
     -
       .. code-block :: text

         eqratio O A A C O B B D, coll O A C,
         coll O B D, ncoll A B C, sameside A O C B O D
         => para A B C D

r28 : para2coll
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`AB \parallel AC \implies \text{coll}(ABC)`
   * -
      .. image:: ../../_static/Images/rules/r28.png
     -
       .. code-block :: text

         para A B A C
         => coll A B C

r29 : midp2eqratio
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{midp}(M, AB) \wedge \text{midp}(N, CD) \implies \frac{MA}{AB} = \frac{NC}{CD}`
   * -
      .. image:: ../../_static/Images/rules/r29.png
     -
       .. code-block :: text

         midp M A B, midp N C D
         => eqratio M A A B N C C D

r30 : eqangle_perp2perp
^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle AB, PQ\rangle=\langle CD, UV\rangle \wedge \text{perp}(PQ, UV) \implies \text{perp}(AB, CD)`
   * -
      .. image:: ../../_static/Images/rules/r30.png
     -
       .. code-block :: text

         eqangle A B P Q C D U V, perp P Q U V
         => perp A B C D

r31 : eqratio_cong2cong
^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\frac{AB}{PQ} = \frac{CD}{UV} \wedge |PQ| = |UV| \implies |AB| = |CD|`
   * -
      .. image:: ../../_static/Images/rules/r31.png
     -
       .. code-block :: text

         eqratio A B P Q C D U V, cong P Q U V
         => cong A B C D

r32 : cong_cong2contri
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`|AB| = |PQ| \wedge |BC| = |QR| \wedge |CA| = |RP|`
       :math:`\implies \text{contri*}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r32.png
     -
       .. code-block :: text

         cong A B P Q, cong B C Q R, cong C A R P, ncoll A B C
         => contri* A B C P Q R

r33 : cong_eqangle2contri
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`|AB| = |PQ| \wedge |BC| = |QR| \wedge \langle BA, B\rangle = \langle QP, QR\rangle`
       :math:`\implies \text{contri*}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r33.png
     -
       .. code-block :: text

         cong A B P Q, cong B C Q R, eqangle6 B A B C Q P Q R, ncoll A B C
         => contri* A B C P Q R

r34 : eqangle2simtri
^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle BA, BC\rangle = \langle QP, QR\rangle \wedge \langle CA, CB\rangle = \langle RP, RQ\rangle`
       :math:`\implies \text{simtri}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r34.png
     -
       .. code-block :: text

         eqangle6 B A B C Q P Q R, eqangle6 C A C B R P R Q, ncoll A B C
         => simtri A B C P Q R

r35 : eqangle2simtri2
^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle BA, BC\rangle = \langle QP, QR\rangle \wedge \langle CA, CB\rangle = \langle RP, RQ\rangle`
       :math:`\implies \text{simtri2}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r35.png
     -
       .. code-block :: text

         eqangle6 B A B C Q R Q P, eqangle6 C A C B R Q R P, ncoll A B C
         => simtri2 A B C P Q R

r36 : eqangle_cong2contri
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle BA, BC\rangle = \langle QP, QR\rangle \wedge \langle CA, CB\rangle = \langle RP, RQ\rangle`
       :math:`\wedge |AB| = |PQ| \wedge |BC| = |QR| \wedge \text{ncoll}(ABC)`
       :math:`\wedge |AP| = |QB| \implies \text{contri}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r36.png
     -
       .. code-block :: text

         eqangle6 B A B C Q R Q P, eqangle6 C A C B R Q R P,
         ncoll A B C, cong A B P Q
         => contri A B C P Q R

r37 : eqangle_cong2contri
^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\langle BA, BC\rangle = \langle QP, QR\rangle \wedge \langle CA, CB\rangle = \langle RP, RQ\rangle`
       :math:`\wedge |AB| = |PQ| \wedge |BC| = |QR| \wedge \text{ncoll}(ABC)`
       :math:`\wedge |AP| = |QB| \implies \text{contri2}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r37.png
     -
       .. code-block :: text

         eqangle6 B A B C Q R Q P, eqangle6 C A C B R Q R P,
         ncoll A B C, cong A B P Q
         => contri2 A B C P Q R

r38 : eqratio_eqangle2simtri
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\frac{BA}{BC} = \frac{QP}{QR} \wedge \frac{CA}{CB} = \frac{RP}{RQ}`
       :math:`\wedge \text{ncoll}(ABC) \implies \text{simtri*}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r38.png
     -
       .. code-block :: text

         eqratio6 B A B C Q P Q R, eqratio6 C A C B R P R Q,
         ncoll A B C
         => simtri* A B C P Q R

r39 : eqratio_eqangle2simtri
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\frac{BA}{BC} = \frac{QP}{QR} \wedge \langle BA, B\rangle = \langle QP, Q\rangle`
       :math:`\wedge \text{ncoll}(ABC) \implies \text{simtri*}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r39.png
     -
       .. code-block :: text

         eqratio6 B A B C Q P Q R, eqangle6 B A B C Q P Q R,
         ncoll A B C
         => simtri* A B C P Q R

r40 : eqratio_eqratio_cong2contri
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\frac{BA}{BC} = \frac{QP}{QR} \wedge \frac{CA}{CB} = \frac{RP}{RQ}`
       :math:`\wedge \text{ncoll}(ABC) \wedge |AB| = |PQ|`
       :math:`\implies \text{contri*}(ABC, PQR)`
   * -
      .. image:: ../../_static/Images/rules/r40.png
     -
       .. code-block :: text

         eqratio6 B A B C Q P Q R, eqratio6 C A C B R P R Q,
         ncoll A B C, cong A B P Q
         => contri* A B C P Q R

r41 : para2eqratio
^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{para}(A, B, C, D) \wedge \text{coll}(M, A, D) \wedge \text{coll}(N, B, C)`
       :math:`\wedge \text{eqratio6}(M, A, M, D, N, B, N, C)`
       :math:`\wedge \text{sameside}(M, A, D, N, B, C)`
       :math:`\implies \text{para}(M, N, A, B)`
   * -
      .. image:: ../../_static/Images/rules/r41.png
     -
       .. code-block :: text

         para A B C D, coll M A D, coll N B C,
         eqratio6 M A M D N B N C, sameside M A D N B C
         => para M N A B

r42 : eqratio62para
^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{para}(A, B, C, D) \wedge \text{coll}(M, A, D) \wedge \text{coll}(N, B, C)`
       :math:`\implies \text{eqratio6}(M, A, M, D, N, B, N, C)`
   * -
      .. image:: ../../_static/Images/rules/r42.png
     -
       .. code-block :: text

         para A B C D, coll M A D, coll N B C, para M N A B
         => eqratio6 M A M D N B N C

r43 : perp_flip
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{perp}(A, B, C, D) \wedge \text{perp}(A, C, B, D)`
       :math:`\implies \text{perp}(A, D, B, C)`
   * -
      .. image:: ../../_static/Images/rules/r43.png
     -
       .. code-block :: text

         perp A B C D, perp A C B D
         => perp A D B C

r44 : coll_transitive
^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{coll}(A, B, C) \wedge \text{coll}(P, Q, R) \wedge \text{coll}(X, A, Q)`
       :math:`\wedge \text{coll}(X, P, B) \wedge \text{coll}(Y, A, R) \wedge \text{coll}(Y, P, C)`
       :math:`\wedge \text{coll}(Z, B, R) \wedge \text{coll}(Z, C, Q)`
       :math:`\implies \text{coll}(X, Y, Z)`
   * -
      .. image:: ../../_static/Images/rules/r44.png
     -
       .. code-block :: text

         coll A B C, coll P Q R, coll X A Q, coll X P B, coll Y A R, coll Y P C, coll Z B R, coll Z C Q
         => coll X Y Z

r45 : cyclic_perp_coll
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{cyclic}(A, B, C, P) \wedge \text{coll}(A, L, C) \wedge \text{perp}(P, L, A, C)`
       :math:`\wedge \text{coll}(M, B, C) \wedge \text{perp}(P, M, B, C)`
       :math:`\wedge \text{coll}(N, A, B) \wedge \text{perp}(P, N, A, B)`
       :math:`\implies \text{coll}(L, M, N)`
   * -
      .. image:: ../../_static/Images/rules/r45.png
     -
       .. code-block :: text

         cyclic A B C P, coll A L C, perp P L A C, coll M B C, perp P M B C, coll N A B, perp P N A B
         => coll L M N

r46 : eqangle_opposite
^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{eqangle}(A, B, A, X, A, X, A, C) \wedge \text{eqangle}(B, A, B, X, B, X, B, C)`
       :math:`\wedge \text{ncoll}(A, B, C)`
       :math:`\implies \text{eqangle}(C, B, C, X, C, X, C, A)`
   * -
      .. image:: ../../_static/Images/rules/r46.png
     -
       .. code-block :: text

         eqangle A B A X A X A C, eqangle B A B X B X B C, ncoll A B C
         => eqangle C B C X C X C A

r47 : perp_midp
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - Formula
   * -
      .. image:: ../../_static/Images/rules/r47.png
     -
       :math:`\text{midp}(m, a, b) \wedge \text{perp}(x, m, a, b) \wedge \text{midp}(n, b, c)`
       :math:`\wedge \text{perp}(x, n, b, c) \wedge \text{midp}(p, c, a)`
       :math:`\implies \text{perp}(x, p, c, a)`

       .. code-block :: text

         midp m a b, perp x m a b, midp n b c, perp x n b c, midp p c a
         => perp x p c a

r48 : midp_coll
^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - figure
     - :math:`\text{midp}(m, a, b) \wedge \text{coll}(m, x, c)`
       :math:`\wedge \text{midp}(n, b, c) \wedge \text{coll}(n, x, c)`
       :math:`\wedge \text{midp}(p, c, a)`
       :math:`\implies \text{coll}(x, p, b)`
   * -
      .. image:: ../../_static/images/rules/r48.png
     -
       .. code-block :: text

         midp m a b, coll m x c, midp n b c, coll n x c, midp p c a
         => coll x p b

r49 : circle_cyclic_cong
^^^^^^^^^^^^^^^^^^^^^^^^
.. list-table::
   :widths: 50 25
   :header-rows: 1

   * - Figure
     - :math:`\text{circle}(O, A, B, C) \wedge \text{cyclic}(A, B, C, D)`
       :math:`\implies \text{cong}(O, A, O, D)`
   * -
      .. image:: ../../_static/Images/rules/r49.png
     -
       .. code-block :: text

         circle O A B C, cyclic A B C D
         => cong O A O D