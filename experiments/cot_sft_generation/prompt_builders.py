#!/usr/bin/env python3
"""
Prompt-building helpers for CoT SFT generation.

This module isolates the long planner/writer prompts and retry feedback so
prompt maintenance does not keep bloating the main generation script.
"""

from __future__ import annotations

import json
import re

try:
    from .geometry_text import (
        build_hidden_aux_brief,
        build_multi_aux_instruction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_problem_goal,
    )
    from .writer_contracts import (
        build_bridge_sentence_checklist,
        build_prefix_coverage_notes,
        build_prefix_reuse_guidance,
        build_writer_bridge_contracts,
        build_writer_handoff,
        build_writer_sentence_blueprints,
        build_writer_sentence_duties,
        enrich_bridge_steps_with_targets,
        join_natural_list,
    )
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (
        build_hidden_aux_brief,
        build_multi_aux_instruction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_problem_goal,
    )
    from writer_contracts import (
        build_bridge_sentence_checklist,
        build_prefix_coverage_notes,
        build_prefix_reuse_guidance,
        build_writer_bridge_contracts,
        build_writer_handoff,
        build_writer_sentence_blueprints,
        build_writer_sentence_duties,
        enrich_bridge_steps_with_targets,
        join_natural_list,
    )


def build_plan_json_example():
    return json.dumps(
        {
            "anchor_points": ["a", "b", "c"],
            "anchor_relation": "triangle abc is the main visible frame, with ab perpendicular to ac and ab equal to ac.",
            "figure_overview": "point g lies on ac while d and j extend the right side of the figure beyond the main triangle.",
            "coordinate_relations": [
                "point g looks like the midpoint of segment ac",
                "points b, d, and i look nearly collinear",
            ],
            "visible_relations": [
                "ab is perpendicular to ac",
                "ab equals ac",
                "g is the midpoint of ac",
            ],
            "coordinate_hints": "the midpoint at g and the straight-looking b-d-i alignment suggest that any new helper should connect the central structure to the right side through d.",
            "goal_bottleneck": "the goal angle at g still does not have a controlled link to the direction through bj.",
            "helper_idea": "we need a local helper that first creates a tight relation around the new point and then transfers it toward d and j.",
            "construction": "construct point k so that kb equals kc and line ck is perpendicular to line dk.",
            "aux_direct_relations": [
                "kb equals kc",
                "line ck is perpendicular to line dk",
            ],
            "bridge_steps": [
                {
                    "relation": "kc equals kd",
                    "depends_on": [
                        "kb equals kc",
                        "line ck is perpendicular to line dk",
                    ],
                    "why_it_helps": "this brings d into the same local balance around k and sets up the next relation kb equals kd.",
                },
                {
                    "relation": "kb equals kd",
                    "depends_on": [
                        "kb equals kc",
                        "kc equals kd",
                    ],
                    "why_it_helps": "this lets the k-based balance control the d-side direction and prepares the next angle relation with bj.",
                },
                {
                    "relation": "angle bk/bj equals angle dj/dk",
                    "depends_on": [
                        "kb equals kd",
                        "bj equals dj",
                    ],
                    "why_it_helps": "this prepares the goal angle by connecting bj to bg and the target angle on cg and fg.",
                },
            ],
            "goal_finish": "then the angle between bg and bj can match the target angle between cg and fg.",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_aux_specific_plan_guidance(aux_part):
    if not aux_part:
        return ""
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").lower()
    if "midp" in inner:
        return (
            "[Midpoint Aux Guidance]\n"
            "This target introduces a midpoint auxiliary point.\n"
            "- Before the construction field, do not mention the new midpoint name.\n"
            "- In aux_direct_relations, stay with midpoint-local facts only: the midpoint statement itself, the equal halves, and the resulting collinearity.\n"
            "- Do not jump from 'midpoint' directly to extra altitude, perpendicular-bisector, or circumcenter claims unless those relations already appear in the hidden proof guidance route.\n"
            "- For bridge_steps, prefer the concrete bridge_relations already hinted by the hidden proof guidance, such as equal-length transfers or congruent/angle consequences that explicitly reuse the midpoint facts.\n"
            "Midpoint-flavored example:\n"
            "{\n"
            '  "construction": "construct point h as the midpoint of segment bc.",\n'
            '  "aux_direct_relations": ["h is the midpoint of bc", "bh equals ch", "b, c, h are collinear"],\n'
            '  "bridge_steps": [\n'
            '    {\n'
            '      "relation": "ah equals ch",\n'
            '      "depends_on": ["h is the midpoint of bc", "bh equals ch"],\n'
            '      "why_it_helps": "this equality is required to prove the next congruent-triangle or angle relation involving h and f."\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
        )
    new_points = [point.lower() for point in extract_aux_new_points(aux_part)]
    cong_clauses = re.findall(r"\bcong\s+([a-z]\w*)\s+([a-z]\w*)\s+([a-z]\w*)\s+([a-z]\w*)", inner)
    if len(new_points) == 1 and len(cong_clauses) >= 2:
        point_set = set()
        point_hits = 0
        for clause in cong_clauses[:2]:
            point_set.update(clause)
            if new_points[0] in clause:
                point_hits += 1
        if len(point_set) == 3 and point_hits == 2:
            return (
                "[Equal-Length Aux Guidance]\n"
                "This target introduces one new point through two immediate equal-length facts on the same local frame.\n"
                "- Before the construction field, do not name the new point and do not say 'point h' or 'triangle adh'.\n"
                "- In helper_idea, describe the missing mechanism without the point name, for example: 'we need a point built from segment ad that gives two equal-length links and then bridges toward line ac.'\n"
                "- In construction, explicitly introduce the new point and restate both equalities from the hidden target summary in plain language.\n"
                "- In aux_direct_relations, stay with those immediate equalities only; do not jump early to collinearity, symmetry, rotation, or congruent-triangle claims.\n"
                "- In bridge_steps, prefer the approved hidden route items such as a collinearity step, an equal-length transfer like ah equals ag or dh equals de, and then the final old-figure comparison.\n"
                "- Each why_it_helps sentence should name the next concrete relation directly, such as 'this is required to prove cg equals hg next', rather than mentioning a generic triangle argument.\n"
                "Equal-length example:\n"
                "{\n"
                '  "helper_idea": "we need a point built from segment ad that gives two equal-length links and then bridges toward line ac.",\n'
                '  "construction": "construct point h such that ad equals ah and ah equals dh.",\n'
                '  "aux_direct_relations": ["ad equals ah", "ah equals dh"],\n'
                '  "bridge_steps": [\n'
                '    {\n'
                '      "relation": "a, c, h are collinear",\n'
                '      "depends_on": ["ad equals ah", "ah equals dh", "ad is parallel to bc"],\n'
                '      "why_it_helps": "this alignment is required to prove cg equals hg next."\n'
                '    },\n'
                '    {\n'
                '      "relation": "cg equals hg",\n'
                '      "depends_on": ["a, c, h are collinear", "cg equals eg"],\n'
                '      "why_it_helps": "this equality is required to prove df equals cg next."\n'
                '    }\n'
                '  ]\n'
                "}\n\n"
            )
    return ""


def build_plan_retry_feedback(validation_message, aux_part):
    targeted_hints = []
    if "depends_on" in validation_message:
        targeted_hints.append(
            "- bridge_steps must be a JSON array of objects, and each depends_on field must itself be a JSON list of earlier relation strings rather than one free-form paragraph."
        )
    if "depends_on" in validation_message and "must name at least two concrete points" in validation_message:
        targeted_hints.append(
            "- every depends_on item should be a full earlier relation string with named points, such as 'ab equals bi', 'a, d, i are collinear', or 'line ac is perpendicular to line di'; do not write shorthand like 'the equality', 'the perpendicular setup', or a single-point fragment."
        )
    if "depends_on" in validation_message and "must be a list with" in validation_message:
        targeted_hints.append(
            "- if only one support is needed, still return it inside JSON brackets, for example: \"depends_on\": [\"ab equals bi\"]."
        )
    if "depends_on" in validation_message and "must mention a concrete geometric relation" in validation_message:
        targeted_hints.append(
            "- every depends_on item should copy an earlier concrete relation almost verbatim, such as 'ah equals ch' or 'line ad is parallel to line bc'; do not replace it with abstract support labels like 'the midpoint property' or 'the equal-length setup'."
        )
    if "depends_on must reuse an earlier visible, coordinate, direct, or bridge relation" in validation_message:
        targeted_hints.append(
            "- every depends_on item should be copied from coordinate_relations, visible_relations, aux_direct_relations, or an earlier bridge_steps relation with nearly the same surface form; do not invent a fresh paraphrase when an earlier approved support already exists."
        )
    if "aux_direct_relations" in validation_message and "must mention a concrete geometric relation" in validation_message:
        targeted_hints.append(
            "- every aux_direct_relations item must state the immediate construction consequence itself, such as 'ah equals dh', 'line ck is perpendicular to line dk', or 'b, c, h are collinear'; do not write vague summaries like 'the construction creates symmetry' or 'an isosceles shape appears'."
        )
        targeted_hints.append(
            "- if the direct consequence is that a point lies on a known line, write it as a concrete collinearity such as 'a, b, h are collinear' instead of 'h lies on line ab'."
        )
    if "aux_direct_relations" in validation_message and "must be a list with" in validation_message:
        targeted_hints.append(
            "- aux_direct_relations must be an actual JSON list, for example: [\"a, d, i are collinear\", \"ab equals bi\", \"bd equals di\"]. Do not collapse the list into one sentence or one quoted paragraph."
        )
        targeted_hints.append(
            "- prefer copying 1 to 4 items from Hidden Proof Guidance.immediate_aux_consequences almost verbatim, starting from the most local construction consequences first."
        )
    if "bridge_steps" in validation_message and "must mention a concrete geometric relation" in validation_message:
        targeted_hints.append(
            "- every bridge_steps relation should name the exact approved equality, angle, ratio, collinearity, parallel, or perpendicular statement, not a high-level summary like 'the triangles match' or 'an isosceles configuration forms'."
        )
        targeted_hints.append(
            "- avoid point-identification wording like 'h coincides with f'; if you must express that identification, rewrite it as a concrete equality or another approved route relation."
        )
    if "coordinate_hints" in validation_message:
        targeted_hints.append(
            "- include coordinate_hints as one or two plain-language sentences summarizing which coordinate_relations matter and why."
        )
    if "coordinate_relations must stay grounded in the hidden coordinate candidates" in validation_message:
        targeted_hints.append(
            "- coordinate_relations should be chosen from the hidden structured coordinate candidates, not copied from visible premises like a given parallel or equal-length statement."
        )
        targeted_hints.append(
            "- rewrite abstract shape summaries like 'triangle adc looks isosceles' into the concrete candidate relation they imply, such as 'ad looks equal to cd', only if that exact equality appears in the hidden coordinate candidate list."
        )
    if "coordinate_relations should cover at least" in validation_message and "visible non-anchor points" in validation_message:
        targeted_hints.append(
            "- spread coordinate_relations across the broader visible figure, especially outer or goal-side non-anchor points, instead of stacking several variations on the same anchor triangle."
        )
        targeted_hints.append(
            "- prefer coordinate candidates from different local regions so the plan has more than one coordinate-backed handle on the figure."
        )
        targeted_hints.append(
            "- do not absorb too many coordinate-rich outer points into anchor_points. Anchor points are only the tagged orientation frame; leave some goal-side or bridge-side points outside anchor_points so coordinate_relations can still cover them as non-anchor evidence."
        )
    if "coordinate_relations" in validation_message and "symmetry or rotation claims" in validation_message:
        targeted_hints.append(
            "- rewrite coordinate_relations as concrete cues like midpoint, collinear, equal-length, parallel, or perpendicular observations; do not say points look symmetric or that there is a rotation."
        )
    if "coordinate_hints must explain concrete midpoint" in validation_message:
        targeted_hints.append(
            "- rewrite coordinate_hints to summarize the concrete cues themselves, such as a midpoint, collinearity, equal-length, parallel, or perpendicular observation, instead of saying the figure suggests symmetry or rotation."
        )
    if "coordinate_hints contains forbidden pattern: midpoint propert" in validation_message:
        targeted_hints.append(
            "- do not write 'midpoint property' in coordinate_hints; instead name the concrete midpoint fact itself, such as 'm is the midpoint of ab' or 'am equals bm'."
        )
    if "bridge_steps must connect the auxiliary point to existing visible points" in validation_message:
        targeted_hints.append(
            "- make the first bridge relation explicitly combine the new auxiliary point with old visible points in a concrete relation, such as 'ag equals dg', 'a, c, e, g are concyclic', or 'angle bg/bj equals angle gi/ij'; do not let the bridge route drift into pure old-figure statements."
        )
        targeted_hints.append(
            "- prefer compact point-pair surface forms like 'ag equals dg' over looser wrappers such as 'segment ag equals segment dg' when you describe an approved bridge relation."
        )
    if "must advance beyond earlier visible, direct, or bridge relations" in validation_message:
        targeted_hints.append(
            "- each bridge_steps relation must be a new checkpoint beyond the visible_relations, aux_direct_relations, and earlier bridge steps; do not repeat an aux-direct equality such as 'bj equals dj' as a separate bridge step."
        )
        targeted_hints.append(
            "- if a hidden route relation is already unlocked directly by the auxiliary construction, move to the next realistic checkpoint instead of repeating the same relation."
        )
        targeted_hints.append(
            "- do not restate an earlier bridge checkpoint later in the route. Once a relation has already appeared as visible support, aux-direct support, or a prior bridge step, the next bridge step should move to a later approved checkpoint."
        )
    if "introduces unsupported angle/ratio/similar segments" in validation_message:
        missing_segments_match = re.search(r"segments before they are grounded by required_supports: (\[[^\]]+\])", validation_message)
        targeted_hints.append(
            "- for angle, ratio, or similar-triangle bridge steps, do not introduce fresh segment pairs that were never grounded by the chosen supports. If the step names bd, df, dk, or similar objects, the required_supports should already mention those lines directly or through a concrete collinearity/cyclic relation that contains them."
        )
        targeted_hints.append(
            "- if a high-order checkpoint still needs several new line objects, split it into an earlier bridge step instead of compressing the whole jump into one relation."
        )
        targeted_hints.append(
            "- choose bridge steps whose same-sentence required_supports already cover almost all of the segments used by that angle/ratio/similar relation."
        )
        if missing_segments_match:
            targeted_hints.append(
                f"- the current failed bridge still leaves these segment objects ungrounded: {missing_segments_match.group(1)}. Insert an earlier checkpoint or rewrite depends_on so those objects are already named before the high-order relation appears."
            )
    if "missing prerequisite:" in validation_message:
        missing_prerequisite_match = re.search(r"missing prerequisite:\s*(.+)$", validation_message)
        targeted_hints.append(
            "- do not skip the earlier approved checkpoint that the validator named. Insert that missing checkpoint as its own earlier bridge_steps relation before the later similarity, ratio, or angle step that depends on it."
        )
        if missing_prerequisite_match:
            targeted_hints.append(
                f"- specifically, add the missing checkpoint '{missing_prerequisite_match.group(1).strip()}' before the later bridge step instead of trying to compress past it."
            )
    if "must avoid vague shape shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; replace them with the concrete perpendicular, equal-length, midpoint, or parallel facts that are actually visible."
        )
    if "must avoid unsupported center shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'common center', 'reference center', 'center of symmetry', or 'serve as the center'; replace them with the concrete midpoint, equal-length, perpendicular, or collinear relations that justify the step."
        )
    if "must avoid generic symmetry shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'axis of symmetry', 'symmetry', 'symmetric', or 'mirror'; replace them with the concrete midpoint, equal-length, parallel, perpendicular, or collinear relations that justify the step."
        )
    if "visible_relations" in validation_message:
        targeted_hints.append(
            "- visible_relations should contain only old-figure relations that are already visible before the auxiliary point is introduced; do not place new-point relations there."
        )
    if "construction is missing an expected" in validation_message:
        targeted_hints.append(
            "- construction must restate the hidden auxiliary facts in natural geometry language, including the required equal/perpendicular/parallel/circle cue."
        )
    if "helper_idea contains forbidden pattern" in validation_message:
        targeted_hints.append(
            "- rewrite helper_idea as a concrete missing mechanism such as an equal-length transfer, perpendicular link, midpoint, or angle relation; do not use filler like 'facilitate' or 'help establish'."
        )
        targeted_hints.append(
            "- do not describe the helper as a center of symmetry, symmetric center, or rotation center; name the concrete midpoint, equal-length, parallel, or perpendicular mechanism instead."
        )
        targeted_hints.append(
            "- do not say 'midpoint property' inside helper_idea; say the concrete midpoint fact itself, such as 'the midpoint of ad gives equal halves', instead."
        )
    if "goal_finish contains forbidden pattern" in validation_message:
        targeted_hints.append(
            "- rewrite goal_finish as the concrete final goal-side relation itself; do not use summary labels such as 'midpoint property', 'symmetry', or other shorthand in place of the actual ratio, angle, or equality statement."
        )
    if "midpoint propert" in validation_message:
        targeted_hints.append(
            "- do not write 'midpoint property' or 'midpoint properties' in any plan field; restate the concrete midpoint fact itself, such as 'e is the midpoint of ad' or 'ae equals de'."
        )
    if "must not appear before the construction field" in validation_message:
        targeted_hints.append(
            "- helper_idea and every pre-construction field must avoid the new point name; say 'a point built from segment ad that creates two equal-length links' rather than 'point h forms ...'."
        )
    if "aux_direct_relations" in validation_message and "direct auxiliary relation should stay on the direct aux consequence" in validation_message:
        targeted_hints.append(
            "- aux_direct_relations must stay local to the new point and the immediately constructed line/circle/perpendicular/equal relation; do not pull old-figure points like a, b, or c into later consequences unless they are part of the construction itself."
        )
        targeted_hints.append(
            "- if a relation still uses the auxiliary point but reaches out to older figure points beyond the construction scope, move it into bridge_steps and use the Preferred Aux-Bridge Checkpoints bucket instead of aux_direct_relations."
        )
    if "bridge_steps[0].relation must still reference the auxiliary point" in validation_message:
        targeted_hints.append(
            "- the first bridge_steps relation must still contain the new auxiliary point together with at least one old visible point; do not start the bridge route with a pure old-figure angle or ratio relation."
        )
        targeted_hints.append(
            "- when a Preferred Aux-Bridge Checkpoints bucket is shown, copy the first bridge relation from that bucket or stay very close to it before moving on to older goal-side checkpoints."
        )
    if "why_it_helps" in validation_message:
        targeted_hints.append(
            "- each why_it_helps string should say what the current step unlocks next in plain geometry language, but the exact next target relation will be derived by the script for the writer."
        )
    if "must stay close to the hidden proof guidance route" in validation_message:
        targeted_hints.append(
            "- do not replace the approved bridge route with a different one; reuse bridge relations that are semantically close to the hidden proof guidance, such as equalities, angle relations, or the final parallel relation already indicated there."
        )
        targeted_hints.append(
            "- when a hidden bridge relation pool is shown, copy those route relations almost verbatim into bridge_steps.relation instead of swapping in a different structure like a new similar-triangle, cyclic, or equal-length route."
        )
        targeted_hints.append(
            "- if the approved route pool lists only equalities, angle relations, ratios, collinearities, or one specific triangle step, do not invent a fresh congruent-triangle relation such as 'triangles abc and abe are congruent' unless that same triangle relation already appears explicitly in the pool."
        )
        targeted_hints.append(
            "- follow the approved route checkpoints in order: the first bridge step should match an earlier checkpoint, and later bridge steps should progress forward rather than jumping to a later finish relation or inventing a new parallel relation."
        )
        targeted_hints.append(
            "- do not postpone an earlier approved checkpoint behind a later one. If the ordered route starts with an equality like 'ai equals eg', that equality must appear before later checkpoints like 'di equals de' or 'be equals ie', not after them."
        )
        targeted_hints.append(
            "- if the approved checkpoints are angle, ratio, equality, collinearity, or parallel relations, do not wrap them into an invented triangle-congruent or triangle-similar bridge unless that same triangle relation already appears in the approved checkpoint list."
        )
        targeted_hints.append(
            "- do not invent a point-identification step like 'h equals f' unless that same identification or an equivalent equality already appears explicitly in the approved checkpoint list."
        )
        targeted_hints.append(
            "- do not insert a fresh collinearity bridge just because an earlier support already places one point on a visible line and the construction places another point on that same line; unless that exact collinearity appears in the approved checkpoint list, keep it as support and move to the next approved route relation."
        )
        if re.search(r"unmatched items:\s*\[[^]]*(center|circumcenter|circle passing through)", validation_message, re.IGNORECASE):
            targeted_hints.append(
                "- do not upgrade a midpoint or equal-distance checkpoint into a 'center of the circle', 'circumcenter', or similar center claim unless that exact center relation appears in the approved route pool."
            )
            targeted_hints.append(
                "- if the approved route pool lists equalities like 'ag equals eg' or 'cg equals eg', keep those as the bridge checkpoints themselves rather than paraphrasing them as a circle-center statement."
            )
        if re.search(r"unmatched items:\s*\[[^]]*congruent", validation_message, re.IGNORECASE):
            targeted_hints.append(
                "- do not swap an approved similar-triangle, equality, angle, or ratio checkpoint into a fresh congruent-triangle relation unless that same congruent-triangle relation appears explicitly in the approved route pool."
            )
            targeted_hints.append(
                "- if the route pool names 'triangles afg and cfg are similar', keep it as similar; do not rewrite it as a congruent-triangle checkpoint."
            )
        if re.search(r"unmatched items:\s*\[[^]]*collinear", validation_message, re.IGNORECASE):
            targeted_hints.append(
                "- your previous bridge route promoted a support collinearity into a new checkpoint. Keep that collinearity only inside depends_on, and choose the next approved checkpoint from the route pool as bridge_steps.relation."
            )
            targeted_hints.append(
                "- if visible_relations or aux_direct_relations already put two points on a line and the construction places a third point on that same line, do not use the resulting three-point collinearity as a new bridge relation unless the approved checkpoint list names it explicitly."
            )
    if "last bridge_steps relation must stay before goal_finish" in validation_message:
        targeted_hints.append(
            "- the final bridge_steps relation should stop at the last pre-finish checkpoint, such as an angle, ratio, equality, or collinearity relation, and goal_finish alone should state the final target relation."
        )
        targeted_hints.append(
            "- if the approved route pool already contains the final goal relation, keep that relation only in goal_finish and move the last bridge step back to the preceding approved checkpoint."
        )
        targeted_hints.append(
            "- do not use the last bridge step for a substitution-version of the goal such as 'ratio dg to cg equals ratio de to df' when goal_finish is 'ratio ac to bc equals ratio de to df'; stop one checkpoint earlier and let goal_finish make the final substitution."
        )
    if "unsupported high-level" in validation_message:
        targeted_hints.append(
            "- do not introduce new routes such as triangle similarity, cyclic quadrilaterals, or parallelograms inside why_it_helps unless that same structure is already stated in the approved relation chain."
        )
        targeted_hints.append(
            "- rewrite why_it_helps as a direct next-step statement like 'this is required to prove kc equals kd next' or 'this prepares the goal angle involving bg, bj, cg, and fg'."
        )
    if "Planner JSON missing keys" in validation_message:
        targeted_hints.append(
            "- return all 12 required top-level keys exactly once; do not omit coordinate_hints, bridge_steps, or goal_finish."
        )
    if aux_part and len(extract_aux_new_points(aux_part)) > 1:
        targeted_hints.append(
            "- because multiple new points are introduced, construction should use stage markers such as first, then, and finally."
        )
    targeted_hint_block = "\n".join(targeted_hints)
    if targeted_hint_block:
        targeted_hint_block += "\n"
    return (
        "Your previous JSON plan was invalid.\n"
        f"Validation error: {validation_message}\n"
        "Return a corrected JSON object that satisfies every schema and quality constraint.\n"
        "Use natural-language geometry statements rather than raw formal predicates such as 'cong b j d j'.\n"
        "Repeat earlier relations verbatim inside depends_on instead of inventing new support strings.\n"
        f"{targeted_hint_block}"
        "Schema reminder:\n"
        f"{build_plan_json_example()}"
    )


def build_writer_retry_feedback(validation_message, plan, injected_prefix=""):
    bridge_contract_items = (
        build_writer_bridge_contracts(plan)
        if isinstance(plan, dict) else []
    )
    bridge_steps = plan.get("bridge_steps", []) if isinstance(plan, dict) else []
    bridge_summary = json.dumps(bridge_steps, ensure_ascii=False, indent=2) if bridge_steps else "[]"
    bridge_blueprints = (
        json.dumps(build_writer_sentence_blueprints(plan), ensure_ascii=False, indent=2)
        if isinstance(plan, dict) else "[]"
    )
    bridge_sentence_checklist = (
        build_bridge_sentence_checklist(plan)
        if isinstance(plan, dict) else ""
    )
    bridge_contracts = (
        json.dumps(bridge_contract_items, ensure_ascii=False, indent=2)
        if isinstance(plan, dict) else "[]"
    )
    prefix_coverage_notes = build_prefix_coverage_notes(plan)
    prefix_reuse_guidance = build_prefix_reuse_guidance(plan)
    coverage_targets = (
        json.dumps(plan.get("coverage_targets", {}), ensure_ascii=False, indent=2)
        if isinstance(plan, dict) else "{}"
    )
    targeted_hints = []
    if "overlaps too much with the injected prefix" in validation_message:
        targeted_hints.append(
            "- do not re-describe the anchors, figure overview, coordinate hints, or visible givens from the injected prefix; start directly from the bottleneck sentence."
        )
        targeted_hints.append(
            "- if a bridge sentence needs a visible given that already appears in the prefix, paraphrase it instead of copying the exact wording, such as 'because ad runs parallel to bc' instead of repeating 'line ad is parallel to line bc'."
        )
        targeted_hints.append(
            "- apply the same rule to coordinate cues: if the prefix already says 'point g looks like the midpoint of cd', rewrite it as 'the midpoint-looking point g on cd' or another short paraphrase instead of copying the whole cue sentence."
        )
        targeted_hints.append(
            "- the first two body sentences should avoid every item listed under Prefix-Covered Facts; use those sentences only for the bottleneck and the missing helper."
        )
        targeted_hints.append(
            "- if a later bridge sentence needs one of the visible givens from the prefix, follow Prefix Reuse Guidance and switch to the suggested paraphrase instead of reusing the exact same clause."
        )
    if "first-person narration" in validation_message:
        targeted_hints.append(
            "- stay impersonal: do not use 'i', 'we', 'our', or 'let us'; write 'construct point k' instead of 'we construct point k'."
        )
        targeted_hints.append(
            "- avoid openings like 'we need' or 'we construct'; rewrite them as 'a helper is needed' and 'construct point k'."
        )
        targeted_hints.append(
            "- preferred impersonal rewrites: 'the obstacle is ...', 'a helper is needed ...', 'construct point k ...', and 'this gives ...'."
        )
    if "opening sentence must mention at least one approved non-anchor opening focus point" in validation_message:
        targeted_hints.append(
            "- in the first sentence, name at least one point from opening_focus_points under Global Coverage Targets so the bottleneck is tied to the real goal-side region, not only to the anchor frame."
        )
        targeted_hints.append(
            "- preferred shape: mention the target relation together with one of those points, such as 'the goal angle involving d, h, i, j ...' or 'the target ratio around ae, af, ce, cj ...'."
        )
    if "helper sentence must mention at least one approved non-anchor bridge focus point" in validation_message:
        targeted_hints.append(
            "- in the second sentence, name at least one point from bridge_focus_points under Global Coverage Targets so the missing helper is attached to the broader visible figure."
        )
        targeted_hints.append(
            "- preferred shape: describe the helper through the line, circle, or side around those points, such as 'a point on line cd', 'a point on be', or 'a helper around g and h'."
        )
    if "approved coordinate relation cue" in validation_message and "must explicitly reuse at least" in validation_message:
        coordinate_relations = [
            relation
            for relation in (plan.get("coordinate_relations") or [])
            if isinstance(relation, str) and relation.strip()
        ] if isinstance(plan, dict) else []
        coverage_targets_dict = plan.get("coverage_targets", {}) if isinstance(plan, dict) else {}
        coordinate_focus_points = [
            point
            for point in (coverage_targets_dict.get("coordinate_focus_points") or [])
            if isinstance(point, str) and point.strip()
        ]
        targeted_hints.append(
            "- after the prefix, mention the approved coordinate relations again in natural language so the body actually uses the visual cues instead of leaving them only in the injected prefix."
        )
        if coordinate_relations:
            targeted_hints.append(
                f"- approved coordinate cues available for reuse: {json.dumps(coordinate_relations[:3], ensure_ascii=False)}."
            )
        if coordinate_focus_points:
            targeted_hints.append(
                f"- keep those coordinate cues tied to non-anchor points such as {join_natural_list(coordinate_focus_points)} rather than drifting back to anchor-only narration."
            )
        targeted_hints.append(
            "- preferred shape: connect that cue directly to the helper or first bridge, such as 'because f is the midpoint of ac...' or 'because c, d, and g stay collinear...'."
        )
    if "Writer early body must connect the bottleneck/helper to at least one approved non-anchor coordinate cue" in validation_message:
        coverage_targets_dict = plan.get("coverage_targets", {}) if isinstance(plan, dict) else {}
        coordinate_focus_relations = [
            relation
            for relation in (coverage_targets_dict.get("coordinate_focus_relations") or [])
            if isinstance(relation, str) and relation.strip()
        ]
        coordinate_focus_points = [
            point
            for point in (coverage_targets_dict.get("coordinate_focus_points") or [])
            if isinstance(point, str) and point.strip()
        ]
        targeted_hints.append(
            "- within the first three body sentences, tie the obstacle or helper to at least one approved non-anchor coordinate cue instead of waiting until the final bridge."
        )
        if coordinate_focus_relations:
            targeted_hints.append(
                f"- preferred early coordinate cues: {json.dumps(coordinate_focus_relations[:3], ensure_ascii=False)}."
            )
        if coordinate_focus_points:
            targeted_hints.append(
                f"- preferred non-anchor coordinate region: {join_natural_list(coordinate_focus_points)}."
            )
    if "must mention at least one approved bridge focus point from its contract" in validation_message:
        targeted_hints.append(
            "- in that bridge sentence, mention at least one point from focus_points in the matching Bridge Sentence Contract so the step stays tied to the intended non-anchor region."
        )
        targeted_hints.append(
            "- preferred shape: cite one required support around that point first, then land on the approved relation, instead of stating the bridge in anchor-only language."
        )
    if "generic shortcut" in validation_message:
        targeted_hints.append(
            "- in each bridge sentence, name the concrete depends_on relations and also state the next approved bridge relation or goal-side relation that this sentence unlocks."
        )
        targeted_hints.append(
            "- do not summarize the support as 'symmetry', 'center of symmetry', or 'midpoint property'; explicitly restate the approved support relations such as 'h is the midpoint of bc' or 'bh equals ch'."
        )
        targeted_hints.append(
            "- when a bridge step includes internal required_supports, mention those support relations explicitly in the same sentence before landing on the new bridge relation."
        )
        targeted_hints.append(
            "- keep the bridge tied to the non-anchor focus points listed under Global Coverage Targets instead of drifting back to generic anchor-only language."
        )
    if "approved supporting relation" in validation_message:
        targeted_hints.append(
            "- every bridge sentence must name at least one concrete approved support relation from its required_supports or depends_on list; do not jump straight to the new relation with no cited support."
        )
        targeted_hints.append(
            "- preferred bridge sentence shape: support relation first, then the new approved bridge relation, then one short clause about the next target."
        )
        targeted_hints.append(
            "- if needed, follow the preferred_sentence_shell in the bridge contracts almost verbatim and only smooth the wording lightly."
        )
    if "overlaps too much with the injected prefix" in validation_message:
        targeted_hints.append(
            "- use the Global Coverage Targets block to move into the non-anchor obstacle or bridge region instead of rephrasing the already-covered overview."
        )
    if "must explicitly realize goal_finish after the bridge steps" in validation_message:
        targeted_hints.append(
            "- add one final sentence after the last bridge sentence that explicitly states the approved goal_finish relation, rather than stopping one step early."
        )
        targeted_hints.append(
            "- do not end with a vague phrase like 'this gives the claim' or 'so the target follows'; restate the exact approved goal-side ratio, angle, or congruence relation."
        )
    if "too long" in validation_message:
        targeted_hints.append(
            "- shorten the body by compressing helper or bridge prose; keep the approved relation names, but trim extra explanation and repeated restatements."
        )
        targeted_hints.append(
            "- prefer one short sentence per bridge step: one relation, one or two concrete supports, and one brief forward-looking clause."
        )
    if "contains forbidden pattern" in validation_message:
        targeted_hints.append(
            "- remove all $...$ formatting, colon-style math snippets, and proof-like shorthand; restate ratios and angles as plain English geometry relations."
        )
        targeted_hints.append(
            "- examples: write 'the ratio ab over bg' instead of '$ab:bg$', and write 'angle bk/bj equals angle dj/dk' as plain text rather than math markup."
        )
        targeted_hints.append(
            "- never wrap a point pair or line name in dollar signs: write 'line be' or 'segment bh', not '$be$' or '$bh$'."
        )
    if "midpoint propert" in validation_message:
        targeted_hints.append(
            "- do not summarize support as 'midpoint property' or 'midpoint properties'; restate the concrete midpoint facts themselves, such as 'm is the midpoint of ab' and 'am equals bm'."
        )
    if "rotational symmetry" in validation_message or "center of symmetry" in validation_message:
        targeted_hints.append(
            "- remove high-level phrases like 'rotational symmetry' or 'center of symmetry'; replace them with the concrete equalities, parallels, or midpoint facts that are actually visible in the approved plan."
        )
    if "must avoid generic symmetry shorthand" in validation_message:
        targeted_hints.append(
            "- remove generic phrases like 'symmetry', 'symmetry axis', 'axis of symmetry', 'axis points', or 'symmetric'; replace them with the concrete equalities, parallels, midpoint facts, or collinearities that the approved plan actually uses."
        )
        targeted_hints.append(
            "- if a sentence needs the role of a bisector or balanced point set, name the exact relation instead, such as 'ah equals bh', 'e and f lie on the perpendicular bisector of ab', or 'a, c, h are collinear', rather than summarizing that role as symmetry."
        )
    if "must explicitly realize bridge_steps" in validation_message:
        targeted_hints.append(
            "- include one explicit sentence for every approved bridge_steps relation in order; do not skip the last angle or parallel relation before the goal_finish sentence."
        )
        targeted_hints.append(
            "- when a bridge relation is an angle or ratio, restate it in nearly the same point ordering and surface form as the approved relation, such as 'angle bg/bj equals angle gi/ij' or 'ac over ce equals hf over ch'."
        )
        match = re.search(r"bridge_steps\[(\d+)\]", validation_message)
        if match:
            step_idx = int(match.group(1))
            contract_idx = step_idx
            if 0 <= contract_idx < len(bridge_contract_items):
                contract = bridge_contract_items[contract_idx]
                relation = contract.get("relation", "")
                if relation:
                    targeted_hints.append(
                        f"- the next retry must include an explicit sentence for bridge_steps[{step_idx}] stating '{relation}'."
                    )
                required_supports = contract.get("required_supports", [])
                if required_supports:
                    targeted_hints.append(
                        f"- before or while stating that relation, cite at least one of these approved supports: {json.dumps(required_supports, ensure_ascii=False)}."
                    )
                focus_points = contract.get("focus_points", [])
                if focus_points:
                    targeted_hints.append(
                        f"- keep that sentence tied to at least one of these focus points: {join_natural_list(focus_points)}."
                    )
    if "must avoid vague shape shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; name the concrete perpendicular, equal-length, midpoint, or parallel relations instead."
        )
    if "must avoid unsupported center shorthand" in validation_message:
        targeted_hints.append(
            "- do not write phrases like 'common center', 'reference center', 'center of symmetry', or 'serve as the center'; name the concrete midpoint, equal-length, perpendicular, or collinear relations instead."
        )
    targeted_hint_block = "\n".join(targeted_hints)
    if targeted_hint_block:
        targeted_hint_block += "\n"
    return (
        "Your previous body text was invalid.\n"
        f"Validation error: {validation_message}\n"
        "Return a corrected plain-text body that satisfies every format and quality constraint.\n"
        "Keep one sentence for each bridge step, and explicitly name concrete supporting relations instead of using vague shortcuts.\n"
        "Global Coverage Targets:\n"
        f"{coverage_targets}\n\n"
        "Non-Skippable Bridge Checklist:\n"
        f"{bridge_sentence_checklist}\n\n"
        "Prefix-Covered Facts:\n"
        f"{prefix_coverage_notes}\n\n"
        "Prefix Reuse Guidance:\n"
        f"{prefix_reuse_guidance}\n\n"
        "Injected Prefix Block:\n"
        f"{injected_prefix}\n\n"
        f"{targeted_hint_block}"
        "Approved bridge steps to realize in order:\n"
        f"{bridge_summary}\n\n"
        "Bridge contracts:\n"
        f"{bridge_contracts}\n\n"
        "Sentence blueprints:\n"
        f"{bridge_blueprints}"
    )


def build_supervisor_payload(record, aux_part, sanitized_rest):
    payload = {
        key: value
        for key, value in record.items()
        if not key.startswith("_")
    }
    payload["exact_aux"] = aux_part
    payload["rest_of_output_sanitized"] = sanitized_rest
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def build_plan_prompt(
    record,
    aux_part,
    sanitized_rest,
    point_coords,
    coordinate_hints,
    coordinate_guidance,
    visible_premise_summaries,
    proof_guidance_payload,
):
    public_problem = build_public_problem_text(record)
    supervisor_payload = build_supervisor_payload(record, aux_part, sanitized_rest)
    visible_goal = extract_problem_goal(record)
    hidden_aux_brief = build_hidden_aux_brief(aux_part)
    new_points = extract_aux_new_points(aux_part)
    new_points_text = ", ".join(new_points) if new_points else "the hidden auxiliary point"
    multi_aux_instruction = build_multi_aux_instruction(aux_part)
    coord_table = json.dumps(point_coords, ensure_ascii=False, sort_keys=True)
    visible_premise_guidance = (
        json.dumps(visible_premise_summaries, ensure_ascii=False, indent=2)
        if visible_premise_summaries else "[]"
    )
    plan_example = build_plan_json_example()
    aux_specific_guidance = build_aux_specific_plan_guidance(aux_part)
    proof_guidance = json.dumps(
        proof_guidance_payload,
        ensure_ascii=False,
        indent=2,
    )
    immediate_aux_pool = proof_guidance_payload.get("immediate_aux_consequences", [])
    immediate_aux_block = json.dumps(immediate_aux_pool, ensure_ascii=False, indent=2) if immediate_aux_pool else "[]"
    aux_bridge_pool = proof_guidance_payload.get("aux_bridge_relations", [])
    aux_bridge_block = json.dumps(aux_bridge_pool, ensure_ascii=False, indent=2) if aux_bridge_pool else "[]"
    route_relation_pool = proof_guidance_payload.get("ordered_route_relations") or (
        aux_bridge_pool
        + proof_guidance_payload.get("bridge_relations", [])
        + proof_guidance_payload.get("goal_finish_relations", [])
    )
    route_relation_block = json.dumps(route_relation_pool, ensure_ascii=False, indent=2) if route_relation_pool else "[]"
    ordered_route_checkpoint_block = (
        "\n".join(f"{idx + 1}. {relation}" for idx, relation in enumerate(route_relation_pool))
        if route_relation_pool else "1. (no hidden route checkpoints available)"
    )
    return (
        "You are planning a geometry CoT training example.\n\n"
        "[What the future student model will see at training/eval time]\n"
        "1. The geometry image.\n"
        "2. The problem text below.\n\n"
        "[Problem Text]\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Hidden Supervisor-Only Reference]\n"
        "The JSON block below is available only while generating the dataset. It exists "
        "to keep the final answer correct, logically aligned with the true aux, and "
        "coordinate-accurate. You may use it internally, but the final thinking trace "
        "must read as if it was produced from the image and the problem text alone.\n"
        "Do not mention the hidden reference, do not mention proof IDs, do not quote "
        "the proof engine, and do not say that some fact was provided to you.\n"
        f"{supervisor_payload}\n\n"
        "[Hidden Visible-Point Coordinate Table]\n"
        f"{coord_table}\n\n"
        "[Hidden Coordinate Hints]\n"
        "These hints are computed from the visible point coordinates only. Use them to "
        "sanity-check visually plausible lines, equal lengths, midpoint structure, or "
        "parallel/perpendicular cues, but do not cite the coordinate table explicitly in the final text.\n"
        f"{coordinate_hints}\n\n"
        "[Hidden Structured Coordinate Candidates]\n"
        "Each item below is derived only from visible-point coordinates. Prefer choosing 2 to 4 of these "
        "as the concrete relation checks in your plan instead of jumping directly to high-level symmetry claims, and try to cover more than one local region of the figure rather than repeating variations on the same anchor-side cue.\n"
        f"{coordinate_guidance}\n\n"
        "[Visible Premise Summaries]\n"
        "These are plain-language summaries of the visible formal premises. When you describe the existing figure, "
        "prefer reusing these concrete relations instead of inventing new high-level geometry claims.\n"
        f"{visible_premise_guidance}\n\n"
        "[Hidden Target Summary]\n"
        f"New point name(s): {new_points_text}\n"
        f"Target auxiliary facts: {hidden_aux_brief}\n\n"
        f"{multi_aux_instruction}"
        "[Hidden Proof Guidance]\n"
        "These grouped checkpoints show how the true solution moves from the aux toward the goal. "
        "Use them only to keep the verification chain realistic; do not expose proof-engine syntax.\n"
        f"{proof_guidance}\n\n"
        "[Preferred Immediate Aux Consequences]\n"
        "Choose aux_direct_relations from or very close to this bucket whenever possible. "
        "These are the local consequences that should appear immediately after the construction, before any broader bridge step.\n"
        f"{immediate_aux_block}\n\n"
        "[Preferred Aux-Bridge Checkpoints]\n"
        "If the first useful bridge relation still needs the auxiliary point, choose it from or very close to this bucket before moving on to older goal-side checkpoints.\n"
        f"{aux_bridge_block}\n\n"
        "[Approved Route Relation Pool]\n"
        "Choose bridge_steps.relation items from or very close to this relation pool, in a realistic order. "
        "Do not replace this route with a different high-level structure unless that same structure already appears below.\n"
        f"{route_relation_block}\n\n"
        "[Approved Ordered Route Checkpoints]\n"
        "Your bridge_steps should usually form an ordered subsequence of the checkpoints below. "
        "Earlier bridge steps should match earlier checkpoints, and later bridge steps should move toward the goal-side checkpoints rather than inventing a new route.\n"
        f"{ordered_route_checkpoint_block}\n\n"
        "[Task]\n"
        "Return exactly one JSON object with these keys:\n"
        "1. anchor_points: a list of 3 to 5 original visible points that are the best tagged anchors for orienting the figure.\n"
        "2. anchor_relation: one sentence describing the key visible relation or shape cue involving those anchors.\n"
        "3. figure_overview: one or two sentences surveying the broader visible figure beyond the anchors, including other relevant points or sub-structures.\n"
        "4. coordinate_relations: a list of 2 to 4 short relation checks inferred from the visible placement; spread them across the visible figure so the later reasoning does not stay trapped on the anchor frame or on one tiny local cluster.\n"
        "5. visible_relations: a list of 2 to 5 concrete existing-figure relations that the later reasoning should actively reuse.\n"
        "6. coordinate_hints: one or two sentences synthesizing those coordinate-backed relation checks and why they matter.\n"
        "7. goal_bottleneck: one sentence describing the main obstacle to reaching the visible goal from the current figure.\n"
        "8. helper_idea: one sentence describing what kind of helper is missing, without naming the new point yet.\n"
        "9. construction: one or two sentences that finally introduce the new point or staged point sequence in plain geometry language.\n"
        "10. aux_direct_relations: a list of 1 to 4 direct consequences that come immediately from the construction itself.\n"
        "11. bridge_steps: a list of 2 to 5 ordered objects; each object must contain relation, depends_on, and why_it_helps.\n"
        "12. goal_finish: one sentence stating the goal-side angle/ratio/congruence relation that closes the argument.\n\n"
        "[Schema Example]\n"
        "Follow this JSON shape closely. In particular, bridge_steps must be a JSON list of objects, and each depends_on value must be a JSON list of earlier relation strings.\n"
        f"{plan_example}\n\n"
        "[why_it_helps Guidance]\n"
        "Good: 'this equality is required before the next bridge relation can be justified.'\n"
        "Good: 'this prepares the final goal-side angle comparison.'\n"
        "Bad: 'this enables similar triangles involving j.'\n"
        "Bad: 'this helps form a cyclic quadrilateral and later gives a parallel line.'\n\n"
        "[helper_idea / aux_direct Guidance]\n"
        "Good helper_idea: 'we need a point that creates an equal-length transfer from k toward d while keeping a perpendicular link through c.'\n"
        "Good helper_idea: 'we need the midpoint of ad so that the equal halves can be used on the d-side.'\n"
        "Bad helper_idea: 'we need a point that will facilitate the proof.'\n"
        "Bad helper_idea: 'we need a center of symmetry' or 'we need a symmetric center' when no concrete midpoint, equal-length, parallel, or perpendicular cue has been stated.\n"
        "Bad helper_idea: 'we need the midpoint property' when the concrete midpoint fact itself has not been stated.\n"
        "Bad helper_idea: 'we need point k so that ...' because the new point name should first appear in construction.\n"
        "Good aux_direct_relations: ['kb equals kc', 'line ck is perpendicular to line dk']\n"
        "Good aux_direct_relations: ['h is the midpoint of bc', 'b, c, h are collinear']\n"
        "Good aux_direct_relations: if Hidden Proof Guidance.immediate_aux_consequences starts with ['a, d, i are collinear', 'ab equals bi', 'bd equals di'], copy 1 to 4 of those local items almost verbatim before introducing any broader equality like 'ai equals eg'.\n"
        "Bad aux_direct_relations: if a candidate relation needs old points outside the construction scope, such as a later bridge equality or a goal-side angle relation, do not place it in aux_direct_relations; use a later bridge step instead.\n"
        "Bad aux_direct_relations: ['h lies on line bc'] when the same fact should be written as 'b, c, h are collinear'.\n"
        "Bad aux_direct_relations: ['kb equals kc', 'angle akd equals ...'] when a is not part of the immediate construction.\n\n"
        "[bridge_steps Surface Guidance]\n"
        "Good bridge relation: 'ah equals bh' or 'angle ak/aj equals angle gk/gj'.\n"
        "Good bridge relation: if aux_direct_relations already give 'bj equals dj', then a later bridge step should use that equality to reach the next checkpoint, not repeat 'bj equals dj' itself.\n"
        "Good bridge ordering: if the approved ordered route checkpoints are ['ai equals eg', 'di equals de', 'be equals ie'], then the bridge steps should keep that order or take an ordered subsequence such as ['ai equals eg', 'di equals de']; do not write ['di equals de', 'be equals ie', 'ai equals eg'].\n"
        "Bad bridge relation: 'triangles abc and abe are congruent' when the approved route pool only lists equalities, angle relations, ratios, collinearities, or a different named triangle relation.\n"
        "Bad bridge relation: 'g is the center of the circle passing through a, c, d, e' when the approved route pool only lists equalities such as 'ag equals eg' and 'cg equals eg'.\n"
        "Bad bridge relation: rewriting an approved similar-triangle checkpoint as a congruent-triangle checkpoint when the approved route pool names only the similar-triangle version.\n"
        "Bad bridge relation: 'h coincides with f' when the same idea should be written as a concrete equality or another approved route relation.\n\n"
        "[coordinate_relations / visible_relations Guidance]\n"
        "Good coordinate_relations: items chosen from the hidden structured coordinate candidates, such as 'point g looks like the midpoint of ac' or 'points b, d, and i look nearly collinear', with enough spread that outer or goal-side visible points also appear when the figure is richer than the anchor frame.\n"
        "Bad coordinate_relations: copying a visible premise such as 'line ad is parallel to line bc' when that relation is not one of the hidden coordinate candidates.\n"
        "Good coordinate_hints: 'the midpoint at g and the near-collinearity of b, d, and i suggest a bridge through d.'\n"
        "Bad coordinate_hints: 'the figure suggests a symmetry between e and f' or 'a rotation seems present'.\n"
        "Good visible_relations: old-figure relations like 'ab equals ac' or 'line ad is parallel to line bc'.\n"
        "Bad visible_relations: any relation involving the new auxiliary point before construction, such as 'ah equals ch'.\n\n"
        f"{aux_specific_guidance}"
        "Constraints:\n"
        "- Use only lowercase point names exactly as in the problem text.\n"
        "- Do not use <point> tags, <coord> tags, LaTeX, $...$ math formatting, backticks, <aux>, <proof>, IDs, or rule names.\n"
        "- Do not restate every premise. Focus on the visible configuration, the likely useful relations, and the bottleneck toward the visible goal.\n"
        "- Survey the whole visible figure, not just the anchor points.\n"
        "- When there are visible points beyond the anchors, let coordinate_relations cover those outer or goal-side points too; do not spend all coordinate checks on one anchor-only triangle.\n"
        "- Use the hidden coordinate table only as an internal consistency check for relations that also look plausible in the image.\n"
        "- The coordinate_relations field should stay close to the structured coordinate candidates when possible. Avoid unsupported jumps like 'there is a rotation symmetry' unless you first name the concrete equal, parallel, perpendicular, midpoint, or collinear cues behind it.\n"
        "- In coordinate_relations and coordinate_hints, do not describe points as symmetric or invoke rotation directly; spell out the concrete equal, parallel, perpendicular, midpoint, or collinear cues instead.\n"
        "- In bridge_steps, do not rename an approved equality checkpoint as a circle-center or circumcenter claim unless that exact center relation appears in the approved route pool.\n"
        "- If the approved route pool contains a specific triangle relation such as a similar-triangle checkpoint, keep that exact modality; do not rewrite it into a congruent-triangle checkpoint unless the pool explicitly does so.\n"
        "- In coordinate_hints, do not use words like symmetry, symmetric, mirror, or rotation; summarize the actual midpoint, collinear, equal-length, parallel, or perpendicular cue instead.\n"
        "- Do not use vague shape shorthand or high-level shape labels such as 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; if that cue matters, spell out the concrete perpendicular, equal-length, midpoint, and parallel facts instead.\n"
        "- The visible_relations field should preferentially reuse the visible premise summaries above, plus a small number of visually obvious derived facts. It should not introduce invented centers, rotations, or unnamed transformations.\n"
        "- The coordinate_relations and visible_relations fields must stay separate: coordinate_relations are coordinate-backed visual checks, while visible_relations are existing-figure givens or obvious old-figure consequences.\n"
        "- The coordinate_hints field must be written as ordinary visual geometry language. Do not say 'the coordinates show', 'the coordinates indicate', or anything similar.\n"
        "- Do not mention the new point name before the construction field.\n"
        "- Avoid vague filler such as 'this point is crucial' or 'this will help'.\n"
        "- The helper_idea field should describe a concrete missing mechanism such as an equal-length transfer, perpendicular link, midpoint control, or goal-side angle connection. Avoid filler such as 'facilitate', 'make progress', or 'help establish'.\n"
        "- In helper_idea, do not use phrases like symmetry, symmetric center, center of symmetry, rotation center, or mirror center unless the same concrete structure is already explicitly stated in the approved visible or coordinate relations.\n"
        "- Do not describe the helper as a common center, reference center, center of symmetry, or generic center of the figure; if a midpoint or equal-distance fact matters, spell out that concrete relation directly.\n"
        "- Do not invent named centers, rotation claims, square/parallelogram claims, or similarity claims unless they are already supported by the approved coordinate checks or by the approved relation buckets.\n"
        "- The construction field must describe the same geometric facts as the hidden target summary in plain language; do not invent a different line, circle, or intersection.\n"
        "- When multiple new points are introduced, construction must explicitly describe a staged or combined strategy with markers such as 'first', 'then', 'next', or 'finally', rather than naming all points in one flat sentence.\n"
        "- Each item in aux_direct_relations must stay local to the auxiliary construction itself. Do not pull unrelated old-figure points into those direct relations.\n"
        "- aux_direct_relations should usually be copied from the Preferred Immediate Aux Consequences bucket above with only light natural-language cleanup. Do not replace those local items with later bridge equalities or broad summaries.\n"
        "- If a useful relation contains the auxiliary point but also reaches outside the construction scope, place it in bridge_steps, not aux_direct_relations. Use the Preferred Aux-Bridge Checkpoints bucket for that handoff.\n"
        "- Each bridge_steps relation should explicitly mention how the auxiliary point interacts with existing visible points or substructures, in a realistic order.\n"
        "- The first bridge_steps relation must explicitly contain the new auxiliary point together with at least one old visible point, and it should be written in a compact relation form such as 'ag equals dg' or 'angle bg/bj equals angle gi/ij'.\n"
        "- A bridge_steps relation must be a new checkpoint beyond visible_relations, aux_direct_relations, and earlier bridge_steps. If the construction already gives a relation directly, treat that relation as support and move to the next bridge checkpoint instead of repeating it.\n"
        "- For any angle, ratio, or similar-triangle bridge step, the depends_on list should already name almost all of the segment or ray objects used in that relation. If a step still needs fresh objects like dg, dk, bd, or df, insert an earlier bridge checkpoint instead of skipping ahead.\n"
        "- Each bridge_steps relation should stay semantically close to the hidden proof guidance bridge_relations or goal_finish_relations; do not swap in a different high-level route.\n"
        "- Treat the Approved Ordered Route Checkpoints as the preferred bridge-step order. Do not jump to a later checkpoint first, and do not invent a fresh parallel/similarity/angle route when an earlier approved checkpoint is already available.\n"
        "- When the ordered route begins with a concrete equality or collinearity checkpoint, do not postpone that earlier checkpoint behind a later checkpoint. Keep the bridge steps monotone in the listed order.\n"
        "- If a candidate bridge relation is not visibly close to one of the Approved Ordered Route Checkpoints, do not use it. In particular, do not inject a fresh goal-side equality or ratio relation just because it sounds useful unless that same relation family already appears in the approved checkpoint list.\n"
        "- If the approved route checkpoints are angle, ratio, collinearity, equality, or parallel relations, do not wrap them into a new triangle-congruent or triangle-similar route unless that same triangle route already appears explicitly in the checkpoint list.\n"
        "- Do not invent a point-identification bridge such as 'h equals f' unless that same identification, or an equivalent old-figure equality using h and f, already appears in the approved route checkpoints.\n"
        "- Do not insert a fresh collinearity bridge just because an earlier visible relation already places one point on a line and the construction places another point on that same line. Unless that exact collinearity appears in the approved checkpoint list, treat it as support only and move to the next approved route relation.\n"
        "- When the approved route relation pool lists a concrete relation such as 'line bg is parallel to line cd' or 'bk = dk', prefer using that relation directly instead of inventing an alternative route like a new similar-triangle claim.\n"
        "- The last bridge_steps relation must stay before the final goal statement. Do not make the last bridge step a substitution-flavored restatement of goal_finish such as 'ratio dg to cg equals ratio de to df' when goal_finish is 'ratio ac to bc equals ratio de to df'.\n"
        "- Each bridge_steps depends_on list should reuse concrete items from coordinate_relations, visible_relations, aux_direct_relations, or an earlier bridge_steps relation, instead of inventing unsupported leaps.\n"
        "- Each depends_on item should be a full earlier relation string with at least two named points, such as 'ab equals bi' or 'a, d, i are collinear'. Do not write shorthand like 'the equality setup' or 'the perpendicular condition'.\n"
        "- Each depends_on item must be copied as a natural-language relation string, not written as a raw formal predicate such as 'cong b j d j'.\n"
        "- Each bridge_steps why_it_helps string should explain what the current step unlocks next in plain geometry language. The script will internally attach the exact next target relation for the writer.\n"
        "- Do not use why_it_helps to smuggle in a new route such as 'similar triangles', 'cyclic quadrilateral', or 'parallelogram' unless that same structure is already explicitly present in the approved relation chain.\n"
        "- The goal_finish field must mention the actual goal-side relation, not just say that the construction is useful.\n"
        "- If multiple new points appear in the hidden target summary, describe whether they are introduced together or in stages and what each stage unlocks.\n"
        "- The wording must sound supportable from the image and visible problem text alone.\n"
    )


def build_write_prompt(record, plan, aux_part, injected_prefix_block, proof_guidance_payload):
    plan = enrich_bridge_steps_with_targets(plan)
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    hidden_aux_brief = build_hidden_aux_brief(aux_part)
    new_points = extract_aux_new_points(aux_part)
    new_points_text = ", ".join(new_points) if new_points else "the hidden auxiliary point"
    multi_aux_instruction = build_multi_aux_instruction(aux_part)
    proof_guidance = json.dumps(
        proof_guidance_payload,
        ensure_ascii=False,
        indent=2,
    )
    writer_handoff = json.dumps(
        build_writer_handoff(plan),
        ensure_ascii=False,
        indent=2,
    )
    sentence_duties = build_writer_sentence_duties(plan)
    bridge_sentence_checklist = build_bridge_sentence_checklist(plan)
    prefix_coverage_notes = build_prefix_coverage_notes(plan)
    prefix_reuse_guidance = build_prefix_reuse_guidance(plan)
    bridge_steps = plan.get("bridge_steps", []) if isinstance(plan, dict) else []
    expected_sentence_count = 4 + len(bridge_steps) + (1 if plan.get("aux_direct_relations") else 0)
    return (
        "You are polishing a geometry CoT example for SFT.\n\n"
        "[Visible Inputs]\n"
        "The final trained model will only see the image and the problem text below.\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Hidden Target Summary]\n"
        f"New point name(s): {new_points_text}\n"
        f"Target auxiliary facts: {hidden_aux_brief}\n\n"
        f"{multi_aux_instruction}"
        "[Hidden Proof Guidance]\n"
        "Use these only to keep the post-aux verification path faithful to the actual solvable route. "
        "Do not quote them, and do not surface proof-engine artifacts.\n"
        f"{proof_guidance}\n\n"
        "[Approved Writer Handoff]\n"
        "This is the compact plan-to-write payload. Follow it faithfully instead of inventing a different route.\n"
        "If a bridge step includes preferred_sentence_shell, stay close to that local order and wording while still writing natural English.\n"
        f"{writer_handoff}\n\n"
        "[Non-Skippable Bridge Checklist]\n"
        "Each item below must appear as its own sentence in order. Do not merge bridge step i into bridge step i+1, and do not replace an approved relation with a later stronger-looking relation.\n"
        f"{bridge_sentence_checklist}\n\n"
        "[Sentence Duties]\n"
        "Use this outline internally to keep the body stepwise, concrete, and impersonal. Do not quote these lines verbatim, and do not repeat the injected prefix.\n"
        f"{sentence_duties}\n\n"
        "[Global Coverage Targets]\n"
        "These are derived from the approved plan so the body keeps track of the broader visible figure beyond the tagged anchors. Use them to keep the obstacle, helper, and bridge sentences connected to the whole diagram instead of circling only around the anchor frame.\n"
        f"{json.dumps(plan.get('coverage_targets', {}), ensure_ascii=False, indent=2)}\n\n"
        "[Compression Target]\n"
        f"Aim for about {expected_sentence_count} sentences total in the body. Keep each bridge sentence compact and concrete, usually one relation plus one or two named supports, rather than a long recap of the whole chain.\n\n"
        "[Injected Prefix Block]\n"
        "The script will prepend the following block exactly before your body. Do not restate these claims; start after them.\n"
        f"{injected_prefix_block}\n\n"
        "[Prefix-Covered Facts]\n"
        "The facts below are already stated by the injected prefix. Do not repeat them in the first two body sentences, and later references should usually be paraphrased rather than copied verbatim.\n"
        f"{prefix_coverage_notes}\n\n"
        "[Prefix Reuse Guidance]\n"
        "If a later bridge sentence needs one of the prefix-covered visible relations, prefer these paraphrase patterns instead of copying the same wording again.\n"
        f"{prefix_reuse_guidance}\n\n"
        "[Write Requirements]\n"
        "Write only the body text that comes after the script-supplied prefix block: an anchor sentence with coordinate tags, a full-figure overview sentence, a coordinate-focused prefix built from the approved relation checks, and a visible-relations sentence injected from the approved plan.\n"
        "Do NOT output <thinking>, <point>, or <coord> tags; the script will add the prefix sentences and the coordinate tags itself.\n"
        "The body must satisfy all of the following:\n"
        "1. It should sound supportable from the image and visible problem text alone.\n"
        "2. It should be logically coherent and centered on discovering the auxiliary construction and then checking that the construction can genuinely advance the visible goal.\n"
        "3. Follow this order: bottleneck -> missing helper idea -> final introduction of the new point or staged points -> explicit realization of aux_direct_relations -> each bridge_steps relation in order, using its depends_on and why_it_helps -> goal_finish.\n"
        "4. Most of the reasoning should happen before the new auxiliary point is named; only introduce that point in the later part of the body.\n"
        "5. Use the plan faithfully, but rewrite it into smooth prose instead of JSON fragments.\n"
        "6. Replace vague statements like 'this point is crucial' with a concrete bottleneck, relation, or next-step verification claim.\n"
        "7. Use the original lowercase point names exactly as in the problem text; do not rewrite them as uppercase, LaTeX, $...$ math formatting, or backticks.\n"
        "8. Keep the body concise and specific, roughly 120 to 230 words.\n"
        "9. The construction and post-aux verification must stay faithful to the hidden target summary; do not invent a different construction than the approved plan.\n"
        "10. It must not contain <aux>, <proof>, <numerical_check>, [012]-style IDs, AR/r63/a01-style rule tokens, or meta-talk.\n"
        "11. It must not say that some coordinate table, hidden answer, proof, or reference was provided.\n"
        "12. It must not assign coordinates to newly introduced auxiliary points.\n"
        "13. Do not repeat the prefix sentences verbatim; continue from them.\n"
        "14. Do not mention coordinates explicitly; describe those cues as visual placement, alignment, equal-looking lengths, or perpendicular/parallel structure.\n"
        "15. Keep the post-aux reasoning faithful to the approved visible_relations, aux_direct_relations, bridge_steps, and goal_finish; do not replace them with a different invented route.\n"
        "16. Do not introduce extra named centers, rotational symmetries, square/parallelogram claims, or triangle-similarity claims unless the approved plan already states them and the immediate aux step really supports them.\n"
        "16a. Do not use vague shape shorthand or high-level shape labels such as 'square-like', 'square structure', 'square abcd', 'rectangle', or 'parallelogram'; replace them with the concrete perpendicular, equal-length, midpoint, or parallel relations that justify the step.\n"
        "16b. Do not use unsupported center shorthand such as 'common center', 'reference center', 'center of symmetry', or 'serve as the center'; replace it with the concrete midpoint, equal-length, perpendicular, or collinear relations that justify the step.\n"
        "17. Reuse the approved visible_relations when connecting the new point back to the old figure, rather than inventing fresh structural claims.\n"
        "18. Stay impersonal. Do not write in the first person.\n"
        "19. The very first sentence of your body should state the bottleneck or goal-side obstacle. Do not spend the first sentence re-describing triangle abc, the midpoint layout, or the visible givens already covered by the injected prefix block.\n"
        "19a. The second sentence should state the missing helper idea, not repeat any overview, coordinate cue, or visible relation already listed under Prefix-Covered Facts.\n"
        "19b. Use the Global Coverage Targets block to keep the obstacle and helper tied to non-anchor visible points or substructures whenever the approved plan depends on them.\n"
        "19c. Reuse the approved coordinate cues early, especially the ones attached to non-anchor visible points, so the body keeps extracting geometry from the broader coordinate layout instead of falling back to anchor-only narration.\n"
        "20. Give each bridge_steps relation its own sentence. In that sentence, explicitly name at least one concrete depends_on relation before or while stating the new bridge relation.\n"
        "20a. When a bridge step lists internal required_supports, mention those support relations explicitly in the same sentence unless doing so would repeat the exact prefix wording; in that case paraphrase them.\n"
        "20b. When a bridge contract includes a preferred_sentence_shell, stay very close to that local order and only smooth the wording lightly.\n"
        "20c. When a bridge contract includes non-empty focus_points, mention at least one of those points in the same sentence so the bridge stays tied to the intended non-anchor region.\n"
        "20d. Do not skip bridge_steps[i] just because bridge_steps[i+1] feels more informative; each approved bridge relation must appear explicitly before the next one starts.\n"
        "21. Avoid shortcuts such as 'by symmetry', 'from the setup', or 'it follows' unless the same sentence explicitly names the concrete supporting relations.\n"
        "22. Do not hedge with phrases like 'similarity or angle equality'; state the specific approved relation you are using.\n"
        "23. Each bridge_steps object includes an internal next_target_relation and next_target_purpose chosen by the script. Use them to keep the reasoning pointed toward the next approved relation instead of inventing a different route.\n"
        "24. Use impersonal sentence forms such as 'the obstacle is ...', 'a helper is needed ...', 'construct point h ...', and 'this gives ...'; avoid first-person forms like 'we need' or 'we construct'.\n"
        "25. If you need to reuse a visible given that already appears in the injected prefix, paraphrase it instead of copying the exact wording from the prefix sentence.\n"
        "26. In bridge sentences, do not replace the approved supports with summary labels such as 'symmetry', 'center of symmetry', or 'midpoint property'; name the actual equalities, collinearities, parallels, or perpendicularities instead.\n"
        "27. When an approved bridge relation is an angle or ratio relation, write it in nearly the same point ordering and surface form as the approved relation, rather than paraphrasing it into a looser sentence like 'the angle formed by ...'.\n"
        "28. Keep the bridge sentences tight: usually one approved relation, one or two concrete supports, and one short forward-looking unlock clause. Do not spend multiple clauses re-explaining the same visible setup.\n"
        "29. Never wrap a point pair, line name, segment name, ratio, or angle label in dollar signs or LaTeX-style math. Write 'line be', 'segment bh', or 'ratio de to di' as plain text, not '$be$', '$bh$', or '$de:di$'.\n"
        "30. Within each bridge sentence, prefer this local order unless the English becomes ungrammatical: approved support relation -> approved bridge relation -> short unlock clause. Avoid inserting a fresh geometric claim between those parts.\n"
        "31. Do not mechanically repeat the phrase 'which prepares ...' in every bridge sentence. Vary the final clause by saying what correspondence, alignment, ratio, or angle comparison the current step now makes available.\n"
        "Output only the plain-text body.\n"
    )


__all__ = [
    "build_aux_specific_plan_guidance",
    "build_plan_json_example",
    "build_plan_prompt",
    "build_plan_retry_feedback",
    "build_supervisor_payload",
    "build_write_prompt",
    "build_writer_retry_feedback",
]
