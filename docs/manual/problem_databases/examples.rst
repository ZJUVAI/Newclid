examples
========

This miscelaneous file of problems contains straightforward problems used to test the engine, test new features, check if the reasoner knows basic geometry facts and theorems, as well as larger problems that were used to see the engine's overall capabilities. It started with the first four problems (orthocenter, orthocenter_aux, incenter_excenter, euler), released as examples with the original AlphaGeometry codebase, and was expanded during the process of getting to know and enhancing the capabilities of the engine. Most of them are simple, striaghtforward problems, meant to check one very specific theorem, rule or behavior, and should run quickly, although that is not always the case.

A more detailed crackdown of the problems is shown in the table below.

.. list-table::
    :widths: 20 30 30 10 10
    :header-rows: 1

    * - Problem Name
      - Description
      - Justification
      - Solved w/ original DDAR?
      - Solved w/ Newclid?
    * - orthocenter
      - Given a triangle ABC, and H the intersection of the heights relative to vertices B and C, H is also in the height relative to vertex A.
      - One of the original problems. It needs an auxiliary point to be solved, and could be solved by the original DDAR+LLM combination.
      - No
      - No
    * - orthocenter_aux
      - Given a triangle ABC, and D the intersection of the heights relative to vertices B and C, and E the foot of the height with respect to B, D is also in the height relative to vertex A.
      - One of the original problems. It is the orthocenter problem with the auxiliary point needed for a pure DDAR solution prescribed.
      - Yes
      - Yes
    * - euler
      - 
      - 
      - 
      - 
    * - pappus
      - 
      - 
      - 
      - 
    * - orthocenter_aux_bis
      - 
      - 
      - 
      - 
    * - orthocenter_consequence
      - 
      - 
      - 
      - 
    * - orthocenter_consequence_aux
      - 
      - 
      - 
      - 
    * - imo_2004_p1
      - 
      - 
      - 
      - 
    * - imo_2004_p1_generalized
      - 
      - 
      - 
      - 
    * - not_always_good
      - 
      - 
      - 
      - 
    * - r29_only
      - 
      - 
      - 
      - 
    * - rule_r29_not_found_disguise
      - 
      - 
      - 
      - 
    * - rule_r29_not_found_explicit
      - 
      - 
      - 
      - 
    * - find_r22
      - 
      - 
      - 
      - 
    * - two_paths_problem_aux
      - 
      - 
      - 
      - 
    * - two_paths_problem
      - 
      - 
      - 
      - 
    * - b23_may_need_BUILT_IN_FNS
      - 
      - 
      - 
      - 
    * - ratio_chase_incorrect_on_step_one
      - 
      - 
      - 
      - 
    * - forcing_ratio
      - 
      - 
      - 
      - 
    * - check_r00
      - 
      - 
      - 
      - 
    * - angles_in_triangle
      - 
      - 
      - 
      - 
    * - testing_aline0
      - 
      - 
      - 
      - 
    * - testing_iso_triangle_vertex_angle
      - 
      - 
      - 
      - 
    * - angles_eq_triangle
      - 
      - 
      - 
      - 
    * - angles_double_eq_triangle
      - 
      - 
      - 
      - 
    * - suplementary_angles
      - 
      - 
      - 
      - 
    * - square_side
      - 
      - 
      - 
      - 
    * - square_angle
      - 
      - 
      - 
      - 
    * - regular_pentagon_side
      - 
      - 
      - 
      - 
    * - regular_pentagon_angle
      - 
      - 
      - 
      - 
    * - regular_hexagon_side
      - 
      - 
      - 
      - 
    * - regular_hexagon_angle
      - 
      - 
      - 
      - 
    * - regular_triangle_side
      - 
      - 
      - 
      - 
    * - worlds_hardest_easy_geometry_problem1
      - 
      - 
      - 
      - 
    * - worlds_hardest_easy_geometry_problem1_with_construction
      - 
      - 
      - 
      - 
    * - worlds_hardest_easy_geometry_problem2
      - 
      - 
      - 
      - 
    * - geometric_ratios
      - 
      - 
      - 
      - 
    * - concatenating_ratios
      - 
      - 
      - 
      - 
    * - ar_example_paper_angle_chasing
      - 
      - 
      - 
      - 
    * - ar_example_paper_distance_chasing
      - 
      - 
      - 
      - 
    * - ar_example_paper_ratio_chasing
      - 
      - 
      - 
      - 
    * - test_get_two_intersections
      - 
      - 
      - 
      - 
    * - ar_two_triangles_angle_chasing
      - 
      - 
      - 
      - 
    * - ar_three_triangles_angle_chasing
      - 
      - 
      - 
      - 
    * - cong2_problem
      - 
      - 
      - 
      - 
    * - point_on_circle_eqdistant_from_center
      - 
      - 
      - 
      - 
    * - minimal_example_2l1c
      - 
      - 
      - 
      - 
    * - midpoint_splits_in_two
      - 
      - 
      - 
      - 
    * - central_angle_vs_internal_angle
      - 
      - 
      - 
      - 
    * - double_angle_implies_central_angle
      - 
      - 
      - 
      - 
    * - double_angle_implies_central_angle_2
      - 
      - 
      - 
      - 
    * - checking_rconst2
      - 
      - 
      - 
      - 
    * - menelaus_test
      - 
      - 
      - 
      - 
    * - menelaus_frac1_test
      - 
      - 
      - 
      - 
    * - menelaus_crossed_cong_test
      - 
      - 
      - 
      - 
    * - frac1_cong
      - 
      - 
      - 
      - 
    * - eqratio_lconst_check
      - 
      - 
      - 
      - 
    * - cong_lconst_check
      - 
      - 
      - 
      - 
    * - lconst_cong_check
      - 
      - 
      - 
      - 
    * - lconst_eqratio_check
      - 
      - 
      - 
      - 
    * - rconst_lconst_check
      - 
      - 
      - 
      - 
    * - lconst_rconst_check
      - 
      - 
      - 
      - 
    * - r50_vs_square_cyclic
      - 
      - 
      - 
      - 
    * - r50_vs_square_center
      - 
      - 
      - 
      - 
    * - r50_vs_square
      - 
      - 
      - 
      - 
    * - r50_vs_trapezoid
      - 
      - 
      - 
      - 
    * - pyt_test_formula_to_perp
      - 
      - 
      - 
      - 
    * - pyt_test_perp_to_formula
      - 
      - 
      - 
      - 
    * - two_goals_cong_aconst
      - 
      - 
      - 
      - 
    * - two_goals_perp_cong
      - 
      - 
      - 
      - 
    * - checking_ordering_r27_oac_obd
      - 
      - 
      - 
      - 
    * - checking_ordering_r27_aoc_bod
      - 
      - 
      - 
      - 
    * - checking_ordering_r27_aoc_bod_eqratio
      - 
      - 
      - 
      - 
    * - checking_ordering_r27_aoc_bod_sameside
      - 
      - 
      - 
      - 
    * - checking_ordering_r27_aoc_dob_sameside
      - 
      - 
      - 
      - 
    * - translated_obm_phase1_2016_p10
      - 
      - 
      - 
      - 
    * - translated_inmo_1995_p1
      - 
      - 
      - 
      - 
    * - doesntbuild_imo_2020_sl_g7
      - 
      - 
      - 
      - 
    * - acompute_test
      - 
      - 
      - 
      - 
    * - translated_imo_2009_sl_g3_excenters
      - 
      - 
      - 
      - 
    * - tangents_to_circle
      - 
      - 
      - 
      - 
    * - ninepoints
      - 
      - 
      - 
      - 
    * - finding_mutual_circles
      - 
      - 
      - 
      - 
    * - finding_center_giving_cyclic
      - 
      - 
      - 
      - 
    * - miquel_theorem
      - 
      - 
      - 
      - 
    * - miquel_theorem_angles
      - 
      - 
      - 
      - 
    * - miquel_quadrangle_theorem1
      - 
      - 
      - 
      - 
    * - miquel_quadrangle_theorem2
      - 
      - 
      - 
      - 
    * - two_perps_at_point_are_collinear
      - 
      - 
      - 
      - 
    * - miquel_theorem_circumcenter_implies_line
      - 
      - 
      - 
      - 
    * - miquel_theorem_line_implies_circumcenter
      - 
      - 
      - 
      - 
    * - pre_reflection_of_points_is_on_circumcenter_of_mirrors
      - 
      - 
      - 
      - 
    * - centers_of_miquels_circles_are_concyclic
      - 
      - 
      - 
      - 
    * - imo_2009_p2_angle_chase_verification
      - 
      - 
      - 
      - 
    * - translated_imo_2019_p2_with_extra_points_paper
      - 
      - 
      - 
      - 
    * - translated_imo_2018_p1
      - 
      - 
      - 
      - 
    * - translated_imo_2012_p5
      - 
      - 
      - 
      - 
    * - translated_imo_2004_p1
      - 
      - 
      - 
      - 
    * - translated_usamo_1988_p4
      - 
      - 
      - 
      - 
    * - euler_simplified
      - 
      - 
      - 
      - 
    * - testing_problem
      - 
      - 
      - 
      - 