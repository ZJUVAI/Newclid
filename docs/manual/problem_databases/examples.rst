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
    * - incenter_excenter
      - Given a triangle ABC, with incenter D and excenter E, center of a circle externally tangent to the side BC, the lines CD and CE are perpendicular.
      - One of the original problems.
      - 
      - Yes
    * - euler
      - In a triangle ABC with orthocenter H, centroid G, and circumcenter O, the points H, G, and O are collinear.
      - One of the original problems.
      - 
      - Yes
    * - pappus
      - 
      - A straight application of Pappus hexagon's theorem. It was created to first check if the engine could originally prove this theorem (it could not), and then to see if we could add Pappus theorem as a rule.
      - No
      - No
    * - orthocenter_consequence
      - 
      - A trivial consequence of the result of the orthocenter problem, created to test the dependency graph and see how it changes when a new rule (the orthocenter theorem) was added, the first one to be successfully added. It still lacks the auxiliary point needed for a simple DDAR/Newclid solution, but it can be solved with the assistance of the LLM.
      - No
      - No
    * - orthocenter_consequence_aux
      - 
      - The previous orthocenter_consequence problem, but now with the auxiliary point necessary for a pure DDAR solution prescribed.
      - Yes
      - Yes
    * - imo_2004_p1
      - 
      - The statement of problem 1 from the IMO 2004 exam, added the auxiliary points prescribed by the LLM as mentioned in the original paper. This problem was brought to the examples so we had a "bigger" problem to test the engine against, with more complexity. This problem is also discussed in the original paper as one that could be generalized by AlphaGeometry.
      - Yes
      - Yes
    * - imo_2004_p1_generalized
      - 
      - This is the statement of imo_2004_p1 with the generalization of point O as proposed in the original AlphaGeometry paper. This generalization should allow for the solution to be found only in a fraction of the sample space allowed for O, and to investigate this phenomenon better we created the simpler not_always_good problem below.
      - 
      - Yes
    * - not_always_good
      - 
      - A smaller version of the problem imo_2004_p1_generalized, for faster testing, that is not true for all choices of the free point O. It revealed that the building routine for problems will check the goal, erase the construction in case it is not met, and try new random attributions until finding a good one. This could result in an infinite loop, so we introduced a limit to the number of trials.
      - 
      - Yes
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
      - This is part of a series of problems created to check the capabilites of the original AlphaGeometry engine when it came to angle chasing. It is supposed to check if it can find the third angle of a triangle given the other two, but the goal had to ask for a 90o angle because that could be stated as a perp statement, the software originally could not treat aconst or s_angle as full predicates.
      - Yes
      - Yes
    * - testing_aline0
      - (Verification problem) Given points A, B, C, D, E, F, G, if H is built in a way that the angle between EF and GH is equal to the angle between AB and CD, than we have the equality of the angles between AB and CD and between EF and GH.
      - This problem was created to check the definition on_aline0 we introduced was working properly.
      - No
      - Yes
    * - testing_iso_triangle_vertex_angle
      - 
      - This problem was created to check the definition iso_triangle_vertex_angle we introduced was working properly.
      - No
      - Yes
    * - angles_eq_triangle
      - An internal angle of an equilateral triangle is 60o.
      - This is part of a sequence of problems created to check the capabilities of the original AlphaGeometry engine when it came to angle chasing. The fact that it could solve this problem, for example, showed its ability to recognize (even indirectly) that the sum of the angles of a triangle was 180o and to actually use the system to find the numerical value of an angle it didn't know before. The question could not be posed on the original AlphaGeometry, though, as aconst did not have full capabilities as a predicate.
      - No
      - Yes
    * - angles_double_eq_triangle
      - 
      - This problem was meant to check if the algebra module could somehow sum the values of two adjacent angles even if it had to find their values by itself, knowing it could find each value due to the solution of the angles_eq_triangle problem. The question could not be posed to the original AlphaGeometry, as aconst did not have full capabilities as a predicate.
      - No
      - Yes
    * - suplementary_angles
      - If an angle between two lines is 30o, the other angle between the same lines is 150o.
      - This problem was meant to check in a very straightforward way if the algebra engine could find the value of the angle supplementary to a given one (it actually generated both angles in the symbols graph at instantiation). The question could not be posed to the original AlphaGeometry, as aconst did not have full capabilities as a predicate.
      - No
      - Yes
    * - square_side
      - 
      - This is part of a series of problems trying to investigate the capacity of the engine to develop an extended reasoning made of small steps, namely to prove that the first and last sides provided in a construction of a polygon are congruent. The solution for a square is too simple to need a complex line of reasoning.
      - 
      - Yes
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
      - This problem was given in the original AlphaGeometry paper in Extended Data Table 2 as an example of the functioning of angle chasing as done by AR. The actual proof provided by DDAR diverged a little from the one presented in the paper, but it could still solve the problem.
      - 
      - Yes
    * - ar_example_paper_distance_chasing
      - 
      - This problem was given in the original AlphaGeometry paper in Extended Data Table 2 as an example of the functioning of distance chasing as done by AR. When examining the code we found no evidence that the procedure described in the paper could be done, and running the problem with DDAR revealed the engine could not actually solve the problem given.
      - No
      - Yes
    * - ar_example_paper_ratio_chasing
      - 
      - This problem was given in the original AlphaGeometry paper in Extended Data Table 2 as an example of the functioning of angle chasing as done by AR. The actual proof provided by DDAR does not look like the one presented in the paper, but it could still solve the problem.
      - 
      - Yes
    * - test_get_two_intersections
      - Given a segment AB, if C and D are the two intersections of the circle of center A and radius AB and of the circle of center B and radius AB, AB is perpendicular to CD.
      - This problem was created to check the behavior of the builder when two points were prescribed with the same description (the two intersections of a pair of circles). It shows the choice of intersections will be made at random, but without points overlapping, and this procedure only checks the numerical structure, it doesn't matter if two points are symbolically the same.
      - 
      - Yes
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
      - The specific content of this problem is not relevant. It was created as a placeholder to make quick tests on the engine, without the need to change the problem name on the scripts and, later, the commands. This cannot be done as easily since the implementation of the caching mechanism.
      - 
      - 