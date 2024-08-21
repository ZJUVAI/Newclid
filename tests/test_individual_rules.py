from pathlib import Path
import pytest

from geosolver.api import GeometricSolverBuilder


@pytest.mark.parametrize(  # type: ignore
    "rule_name,rule_txt,problem_txt,seed",
    [
        (
            "r00",
            "perp A B C D, perp C D E F, ncoll A B E => para A B E F",
            "a = free a; b = free b; c = free c; d = on_tline d c a b; e = free e; f = on_tline f e c d ? para a b e f",
            123,
        ),
        (
            "r01",
            "cong O A O B, cong O B O C, cong O C O D => cyclic A B C D",
            "o = free o; a = free a; b = eqdistance b o o a; c = eqdistance c o o b; d = eqdistance d o o c ? cyclic a b c d",
            123,
        ),
        (
            "r02",
            "eqangle A B P Q C D P Q => para A B C D",
            "p = free p; q = free q; a = free a; b = free b; c = free c; d = on_aline0 d p q a b p q c ? para a b c d",
            123,
        ),
        (
            "r03",
            "cyclic A B P Q => eqangle P A P B Q A Q B",
            "a = free a; b = free b; p = free p; q = on_circum q a b p ? eqangle p a p b q a q b",
            123,
        ),
        (
            "r04",
            "eqangle P A P B Q A Q B, ncoll P Q A B => cyclic A B P Q",
            "a = free a; b = free b; q = free q; p = eqangle3 p a b q a b ? cyclic a b p q",
            123,
        ),
        (
            "r05",
            "cyclic A B C P Q R, eqangle C A C B R P R Q => cong A B P Q",
            "a = free a; b = free b; c = free c; p = on_circum p a b c; r = on_circum r a b c; q = on_circum q a b c, on_aline q r p b c a ? cong a b p q",
            123,
        ),
        (
            "r06",
            "cong M A M B, coll M A B => midp M A B\n"
            "midp E A B, midp F A C => para E F B C",
            "a = free a; b = free b; c = free c; e = midpoint e a b; f = midpoint f a c ? para e f b c",
            123,
        ),
        (
            "r07",
            "para A B C D, coll O A C, coll O B D, ncoll O A B => eqratio3 A B C D O O",
            "a = free a; b = free b; c = free c; d = on_pline d c a b; o = on_line o a c, on_line o b d ? eqratio3 a b c d o o",
            123,
        ),
        (
            "r08",
            "perp A B C D, perp E F G H, npara A B E F => eqangle A B E F C D G H",
            "a = free a; b = free b; c = free c; d = on_tline d c a b; e = free e; f = free f; g = free g; h = on_tline h g e f ? eqangle a b e f c d g h",
            123,
        ),
        (
            "r09",
            "eqangle a b c d m n p q, eqangle c d e f p q r u => eqangle a b e f m n r u",
            "c = free c; d = free d; p = free p; q = free q; a = free a; b = free b; m = free m; n = on_aline0 n c d a b p q m; e = free e; f = free f; r = free r; u = on_aline0 u c d e f p q r ? eqangle a b e f m n r u",
            123,
        ),
        (
            "r10",
            "eqratio a b c d m n p q, eqratio c d e f p q r u => eqratio a b e f m n r u",
            "a = free a; b = free b; c = free c; d = free d; m = free m; n = free n; p = free p; q = eqratio q a b c d m n p; e = free e; f = free f; r = free r; u = eqratio u c d e f p q r ? eqratio a b e f m n r u",
            123,
        ),
        (
            "r11",
            "eqratio d b d c a b a c, coll d b c, ncoll a b c => eqangle a b a d a d a c",
            "a = free a; b = free b; c = free c; d = eqratio6 d b c a b a c, on_line d b c ? eqangle a b a d a d a c",
            123,
        ),
        (
            "r12",
            "eqangle a b a d a d a c, coll d b c, ncoll a b c => eqratio d b d c a b a c",
            "a = free a; b = free b; d = free d; c = on_line c b d, on_aline c a d d a b ? eqratio d b d c a b a c",
            123,
        ),
        (
            "r13",
            "cong O A O B, ncoll O A B => eqangle O A A B A B O B",
            "o = free o; a = free a; b = eqdistance b o o a ? eqangle o a a b a b o b",
            123,
        ),
        (
            "r14",
            "eqangle A O A B B A B O, ncoll O A B => cong O A O B",
            "a = free a; b = free b; o = iso_triangle_vertex_angle o a b ? cong o a o b",
            123,
        ),
        (
            "r15",
            "circle O A B C, perp O A A X => eqangle A X A B C A C B",
            "a = free a; b = free b; c = free c; o = circle o a b c; x = on_tline x a a o ? eqangle a x a b c a c b",
            123,
        ),
        (
            "r16",
            "circle O A B C, eqangle A X A B C A C B => perp O A A X",
            "a = free a; b = free b; c = free c; o = circle o a b c; x = on_aline x a b a c b ? perp o a a x",
            123,
        ),
        (
            "r17",
            "cong M A M B, coll M A B => midp M A B\n"
            "circle O A B C, midp M B C => eqangle A B A C O B O M",
            "a = free a; b = free b; c = free c; o = circle o a b c; m = midpoint m b c ? eqangle a b a c o b o m",
            123,
        ),
        (
            "r18",
            "circle O A B C, coll M B C, eqangle A B A C O B O M => midp M B C",
            "a = free a; b = free b; c = free c; o = circle o a b c; m = on_line m b c, on_aline m o b c a b ? midp m b c",
            123,
        ),
        (
            "r19",
            "cong M A M B, coll M A B => midp M A B\n"
            "perp A B B C, midp M A C => cong A M B M",
            "a = free a; b = free b; c = on_tline c b b a; m = midpoint m a c ? cong a m b m",
            123,
        ),
        (
            "r20",
            "circle O A B C, coll O A C => perp A B B C",
            "o = free o; a = free a; b = on_circle b o a; c = on_circle c o a, on_line c o a ? perp a b b c",
            123,
        ),
        (
            "r21",
            "cyclic A B C D, para A B C D => eqangle A D C D C D C B",
            "a = free a; b = free b; c = free c; d = on_pline d c a b, on_circum d a b c ? eqangle a d c d c d c b",
            123,
        ),
        (
            "r22",
            "cong M A M B, coll M A B => midp M A B\n"
            "midp M A B, perp O M A B => cong O A O B",
            "a = free a; b = free b; m = midpoint m a b; o = on_tline o m a b ? cong o a o b",
            123,
        ),
        (
            "r23",
            "cong A P B P, cong A Q B Q => perp A B P Q",
            "a = free a; p = free p; q = free q; b = eqdistance b p a p, eqdistance b q a q ? perp a b p q",
            123,
        ),
        (
            "r24",
            "cong A P B P, cong A Q B Q, cyclic A B P Q => perp P A A Q",
            "a = free a; b = free b; p = iso_triangle_vertex p a b; q = iso_triangle_vertex q a b, on_circum q a b p ? perp p a a q",
            123,
        ),
        (
            "r25",
            "cong M A M B, coll M A B => midp M A B\n"
            "midp M A B, midp M C D => para A C B D",
            "a = free a; b = free b; c = free c; m = midpoint m a b; d = on_line d c m, eqdistance d m c m ? para a c b d",
            123,
        ),
        (
            "r26",
            "cong M A M B, coll M A B => midp M A B\n"
            "midp M A B, para A C B D, para A D B C => midp M C D",
            "a = free a; b = free b; c = free c; d = on_pline d b a c, on_pline d a b c; m = midpoint m a b ? midp m c d",
            123,
        ),
        (
            "r27",
            "eqratio O A A C O B B D, coll O A C, coll O B D, ncoll A B C, sameside A O C B O D => para A B C D",
            "o = free o; a = free a; b = free b; c = on_line c a o; d = eqratio d o a a c o b b, on_line d o b ? para a b c d",
            123,
        ),
        (
            "r28",
            "para A B A C => coll A B C",
            "a = free a; b = free b; c = on_pline0 c a b a ? coll a b c",
            123,
        ),
        (
            "r29",
            "cong M A M B, coll M A B => midp M A B\n"
            "midp M A B, midp N C D => eqratio M A A B N C C D",
            "a = free a; b = free b; c = free c; d = free d; m = midpoint m a b; n = midpoint n c d ? eqratio m a a b n c c d",
            123,
        ),
        (
            "r30",
            "eqangle A B P Q C D U V, perp P Q U V => perp A B C D",
            "p = free p; q = free q; u = free u; v = on_tline v u p q; a = free a; b = free b; c = free c; d = on_aline0 d p q a b u v c ? perp a b c d",
            123,
        ),
        (
            "r31",
            "eqratio A B P Q C D U V, cong P Q U V => cong A B C D",
            "p = free p; q = free q; u = free u; v = eqdistance v u p q; a = free a; b = free b; c = free c; d = eqratio d p q a b u v c ? cong a b c d",
            123,
        ),
        (
            "r33",
            "cong A B P Q, cong B C Q R, eqangle B A B C Q P Q R, ncoll A B C => contri A B C P Q R",
            "a = free a; b = free b; c = free c; q = free q; p = eqdistance p q b a; r = eqdistance r q b c, on_aline r q p c b a ? contri a b c p q r",
            123,
        ),
        (
            "r34",
            "eqangle B A B C Q P Q R, eqangle C A C B R P R Q, ncoll A B C => simtri A B C P Q R",
            "a = free a; b = free b; c = free c; q = free q; r = free r; p = on_aline p q r a b c, on_aline p r q a c b ? simtri a b c p q r",
            123,
        ),
        (
            "r35",
            "eqangle B A B C Q R Q P, eqangle C A C B R Q R P, ncoll A B C => simtrir A B C P Q R",
            "a = free a; b = free b; c = free c; q = free q; r = free r; p = on_aline p q r c b a , on_aline p r q b c a ? simtrir a b c p q r",
            123,
        ),
        (
            "r36",
            "eqangle B A B C Q P Q R, eqangle C A C B R P R Q, ncoll A B C, cong A B P Q => contri A B C P Q R",
            "a = free a; b = free b; p = free p; q = eqdistance q p a b; r = free r; c = on_aline c b a r q p, eqangle3 c a b r p q ? contri a b c p q r",
            1223,
        ),
        (
            "r37",
            "eqangle B A B C Q R Q P, eqangle C A C B R Q R P, ncoll A B C, cong A B P Q => contrir A B C P Q R",
            "a = free a; b = free b; p = free p; q = eqdistance q p a b; r = free r; c = on_aline c b a p q r, eqangle3 c a b r q p ? contrir a b c p q r",
            1232312,
        ),
        (
            "r38",
            "eqratio B A B C Q P Q R, eqratio C A C B R P R Q, ncoll A B C => simtri A B C P Q R",
            "a = free a; b = free b; c = free c; q = free q; r = free r; p = eqratio p b c b a q r q, eqratio p c b c a r q r ? simtri a b c p q r",
            123,
        ),
        (
            "r39",
            "eqratio B A B C Q P Q R, eqangle B A B C Q P Q R, ncoll A B C => simtri A B C P Q R",
            "a = free a; b = free b; c = free c; p = free p; q = free q; r = eqratio r b a b c q p q, on_aline r q p c b a ? simtri a b c p q r",
            123,
        ),
        (
            "r41",
            "para a b c d, coll m a d, coll n b c, eqratio m a m d n b n c, sameside m a d n b c => para m n a b",
            "a = free a; b = free b; c = free c; d = on_pline d c a b; n = on_line n b c; m = eqratio6 m a d n b n c, on_line m a d ? para m n a b",
            123,
        ),
        (
            "r42",
            "para a b c d, coll m a d, coll n b c, para m n a b, ncoll a b c => eqratio m a m d n b n c",
            "a = free a; b = free b; c = free c; d = on_pline d c a b; m = on_line m a d; n = on_line n b c, on_pline n m a b ? eqratio m a m d n b n c",
            123,
        ),
        (
            "r50",
            "cong M A M B, coll M A B => midp M A B\n"
            "midp M A B => rconst M A A B 1/2",
            "a b = segment a b; m = midpoint m a b ? rconst m a a b 1/2",
            123,
        ),
        (
            "pyt_formula_to_perp",
            "PythagoreanPremises a b c => PythagoreanConclusions a b c",
            "a = free a; b = lconst b a 4; c = lconst c a 5, lconst c b 3 ? perp a b b c",
            123,
        ),
        (
            "pyt_test_perp_to_formula",
            "PythagoreanPremises a b c => PythagoreanConclusions a b c",
            "a = free a; b = lconst b a 4; c = on_tline c b a b, lconst c b 3 ? lconst a c 5",
            123,
        ),
    ],
)
def test_rule_used_to_solve_in_one_step(
    rule_name: str, rule_txt: str, problem_txt: str, seed: int
):
    solver_builder = (
        GeometricSolverBuilder(seed=seed)
        .load_problem_from_txt(problem_txt)
        .load_rules_from_txt(rule_txt)
    )
    solver = solver_builder.build()

    success = solver.run()

    assert success
    if "r" == rule_name[0]:
        Path("individual_rules_out").mkdir(exist_ok=True)
        solver.draw_figure(out_file=Path("individual_rules_out") / (rule_name + ".svg"))
        solver.write_proof_steps(
            out_file=Path("individual_rules_out") / (rule_name + "_proof.txt")
        )
