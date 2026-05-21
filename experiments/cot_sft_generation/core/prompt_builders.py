#!/usr/bin/env python3
"""
Prompt-building helpers for the model_evidence CoT SFT pipeline.
"""

from __future__ import annotations

import json

try:
    from .geometry_text import (
        build_hidden_aux_brief,
        build_public_problem_text,
        extract_problem_goal,
    )
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (
        build_hidden_aux_brief,
        build_public_problem_text,
        extract_problem_goal,
    )


def build_supervisor_payload(record, aux_part, sanitized_rest):
    public_fields = {}
    if isinstance(record, dict):
        for key, value in record.items():
            if str(key).startswith("_"):
                continue
            if key in {"llm_output_renamed", "point_coords_grid", "grid_coord"}:
                continue
            public_fields[key] = value
    public_fields["exact_aux"] = aux_part
    public_fields["hidden_rest_sanitized"] = sanitized_rest
    return json.dumps(public_fields, ensure_ascii=False, indent=2)


def build_plan_json_example():
    return json.dumps(
        {
            "selected_text_fact_ids": ["T1", "T2"],
            "selected_coordinate_candidate_ids": ["C1", "C2"],
            "image_observations": [
                "segments ab and cd look parallel",
                "point f looks like the midpoint of ac",
            ],
            "coordinate_derivations": [
                {
                    "candidate_id": "C1",
                    "relation": "segments ab and cd look parallel",
                    "points": ["a", "b", "c", "d"],
                    "calc_type": "parallel",
                    "render_mode": "vector",
                    "why_it_matters": "this fixes one direction comparison that can be reused later.",
                }
            ],
            "goal_bottleneck": "the target still lacks a concrete bridge from the visible outer side back to the goal relation.",
            "helper_idea": "a helper is needed that first creates a local consequence around the new point and then transfers it through the selected visible and coordinate-backed facts.",
            "construction": "construct point h so that ah equals dh and bh equals ch.",
            "aux_direct_relations": ["ah equals dh", "bh equals ch"],
            "bridge_steps": [
                {
                    "relation": "ah equals bh",
                    "support_refs": ["C2", "T2"],
                    "why_it_helps": "this creates the first shared equality needed for the d-side and c-side transfer.",
                    "proof_alignment": "bridge",
                    "focus_points": ["a", "b", "h"],
                },
                {
                    "relation": "dh equals ch",
                    "support_refs": ["B1", "T2"],
                    "why_it_helps": "this puts d and c under the same local control before the final goal relation.",
                    "proof_alignment": "goal_finish",
                    "focus_points": ["c", "d", "h"],
                },
            ],
            "goal_finish": "ad equals bc",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_raw_record_plan_json_example():
    return json.dumps(
        {
            "text_facts_used": [
                "line ab is parallel to line cd",
                "ab equals bc",
            ],
            "image_observations": [
                "point f looks like the midpoint of ac",
                "points b, d, f appear collinear",
            ],
            "coordinate_derivations": [
                {
                    "relation": "point f looks like the midpoint of ac",
                    "points": ["f", "a", "c"],
                    "calc_type": "midpoint",
                    "render_mode": "midpoint",
                    "why_it_matters": "this gives one concrete balance relation that can be reused after the auxiliary construction.",
                }
            ],
            "goal_bottleneck": "the target still lacks a concrete bridge from the local helper configuration back to the goal relation.",
            "helper_idea": "the helper should first create a direct local consequence and then transfer it through the visible and coordinate-backed relations.",
            "construction": "construct point h so that ah equals dh and bh equals ch.",
            "aux_direct_relations": ["ah equals dh", "bh equals ch"],
            "bridge_steps": [
                {
                    "relation": "ah equals bh",
                    "supports": ["text_facts_used[2]", "coordinate_derivations[1]"],
                    "why_it_helps": "this creates the first shared equality inside the helper frame.",
                    "focus_points": ["a", "b", "h"],
                },
                {
                    "relation": "dh equals ch",
                    "supports": ["bridge_steps[1]", "text_facts_used[2]"],
                    "why_it_helps": "this transfers the helper control to the d-side and c-side before the final closing step.",
                    "focus_points": ["c", "d", "h"],
                },
            ],
            "goal_finish": "ad equals bc",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_dossier_plan_json_example():
    return json.dumps(
        {
            "visible_facts": [
                "line ab is parallel to line cd",
                "ab equals ac",
            ],
            "image_scan": [
                "points b, d, and f appear nearly collinear",
                "point f looks like the midpoint of ac",
            ],
            "coordinate_checks": [
                {
                    "relation": "point f looks like the midpoint of ac",
                    "points": ["f", "a", "c"],
                    "calc_type": "midpoint",
                    "why_it_matters": "this gives one concrete balance cue that can be reused after the helper is added.",
                }
            ],
            "goal_obstacle": "the visible figure still lacks one clean bridge from the helper frame back to the target relation.",
            "aux_motivation": "the helper should create one local consequence first and then reconnect that consequence to the broader figure.",
            "construction": "construct point h so that ah equals dh and bh equals ch.",
            "aux_immediate_effects": [
                "ah equals dh",
                "bh equals ch",
            ],
            "bridge_chain": [
                {
                    "claim": "ah equals bh",
                    "supports": ["visible_facts[2]", "coordinate_checks[1]"],
                    "why_next": "this creates one shared equality inside the helper frame before the transfer to the d-side and c-side.",
                },
                {
                    "claim": "dh equals ch",
                    "supports": ["aux_immediate_effects[1]", "bridge_chain[1]"],
                    "why_next": "this transfers the helper control to the d-side and c-side before the final close.",
                },
            ],
            "goal_closure": [
                {
                    "claim": "ad equals bc",
                    "supports": ["bridge_chain[2]", "visible_facts[2]"],
                    "why_next": "this is the target relation.",
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_formal_language_guide():
    return (
        "- `cong a b c d`: segment ab equals segment cd.\n"
        "- `perp a b c d`: line ab is perpendicular to line cd.\n"
        "- `para a b c d`: line ab is parallel to line cd.\n"
        "- `coll a b c`: points a, b, c are collinear.\n"
        "- `cyclic a b c d`: points a, b, c, d are concyclic.\n"
        "- `midp a b c`: point a is the midpoint of segment bc.\n"
        "- `eqratio a b c d e f g h`: ratio ab to cd equals ratio ef to gh.\n"
        "- `eqangle a b c d e f g h`: angle ab/cd equals angle ef/gh.\n"
        "- `simtri` or `simtrir`: the two named triangles are similar.\n"
        "- `contri` or `contrir`: the two named triangles are congruent.\n"
        "- Point coordinates may be used to check midpoint, collinear, equal-length, parallel, or perpendicular relations."
    )


def build_planning_guidance():
    return (
        "- Return exactly one JSON object.\n"
        "- Distinguish text facts from image observations and from coordinate-derived relations.\n"
        "- If coordinates matter, include at least one explicit coordinate derivation with points, calc_type, and why_it_matters.\n"
        "- Keep the route ordered as goal_bottleneck -> helper_idea -> construction -> aux_direct_relations -> bridge_steps -> goal_finish.\n"
        "- Every bridge step should cite earlier support using only text_facts_used[i], image_observations[i], coordinate_derivations[i], or earlier bridge_steps[i].\n"
        "- Multi-point auxiliary constructions must describe the stages explicitly.\n"
        "- Do not mention proof ids, rule names, hidden hints, supervisor language, or coordinate-table wording.\n"
        "- Do not use LaTeX or markdown code fences inside JSON values."
    )


def build_plan_prompt(
    record,
    aux_part,
    visible_text_facts,
    image_coordinate_candidates,
    hidden_route_hints,
):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    hidden_aux_brief = build_hidden_aux_brief(aux_part)
    return (
        "You are planning a geometry CoT training example under a model-evidence protocol.\n\n"
        "[Visible Inputs]\n"
        "The final student will only see the image and the public problem text below.\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Task]\n"
        "Return exactly one JSON object. Choose which visible text facts matter, which image/coordinate candidates matter, "
        "which explicit coordinate derivations should be surfaced in the final thinking, and how the post-aux route should move "
        "from the immediate construction consequences to the goal.\n\n"
        "[Visible Text Facts]\n"
        f"{json.dumps(visible_text_facts, ensure_ascii=False, indent=2)}\n\n"
        "[Image / Coordinate Candidates]\n"
        "These come only from visible-point coordinates. They may overlap visible givens, but if you use them as image evidence "
        "you must treat them as observed or computed facts, not as formal givens.\n"
        f"{json.dumps(image_coordinate_candidates, ensure_ascii=False, indent=2)}\n\n"
        "[Hidden Route Hints]\n"
        "These are soft guidance only. They help keep the route realistic after the auxiliary construction, but they do not lock the exact wording or step count.\n"
        f"{json.dumps(hidden_route_hints, ensure_ascii=False, indent=2)}\n\n"
        "[Hidden Aux Target]\n"
        f"{hidden_aux_brief}\n\n"
        "[Critical Requirements]\n"
        "- Distinguish text-derived facts from image/coordinate-derived facts.\n"
        "- If you choose a coordinate candidate, also choose the coordinate derivation that will justify it in the final thinking.\n"
        "- Use one of these render_mode values only: vector, distance, midpoint, area.\n"
        "- The final route must include the immediate aux consequences, at least two bridge steps, and a final goal-side closing step.\n"
        "- support_refs may only cite text facts `T*`, coordinate candidates `C*`, or earlier bridge steps `B*`.\n"
        "- Do not mention hidden proof IDs, rule names, or that hidden hints were supplied.\n"
        "- Do not use LaTeX or markdown code fences in the JSON values.\n\n"
        "[Output Schema Example]\n"
        f"{build_plan_json_example()}\n"
    )


def build_raw_record_plan_prompt(record):
    raw_problem = record.get("llm_input_renamed") or build_public_problem_text(record)
    raw_output = record.get("llm_output_renamed") or ""
    point_coords = record.get("point_coords_grid") or record.get("grid_coord") or {}
    return (
        "You are planning a geometry CoT training example from the raw teacher-side record.\n\n"
        "[Student Visibility]\n"
        "The student will only see the image and the public problem text, but you may use the full raw teacher-side record below to plan a realistic route.\n\n"
        "[Raw Problem Text]\n"
        f"{raw_problem}\n\n"
        "[Raw Teacher Output]\n"
        f"{raw_output}\n\n"
        "[Visible Point Coordinates]\n"
        f"{json.dumps(point_coords, ensure_ascii=False, indent=2)}\n\n"
        "[Formal Language Guide]\n"
        f"{build_formal_language_guide()}\n\n"
        "[Planning Guidance]\n"
        f"{build_planning_guidance()}\n\n"
        "[Output Schema Example]\n"
        f"{build_raw_record_plan_json_example()}\n"
    )


def build_dossier_plan_prompt(
    record,
    aux_part,
    visible_text_facts,
    point_coords,
    hidden_milestone_summary,
):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    hidden_aux_brief = build_hidden_aux_brief(aux_part)
    return (
        "You are planning a geometry CoT training example under a dossier protocol.\n\n"
        "[Visible Inputs]\n"
        "The final student will only see the image and the public problem text below.\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Visible Facts Extracted From The Public Problem]\n"
        f"{json.dumps(visible_text_facts, ensure_ascii=False, indent=2)}\n\n"
        "[Visible Point Coordinates]\n"
        f"{json.dumps(point_coords, ensure_ascii=False, indent=2)}\n\n"
        "[Hidden Milestone Summary]\n"
        "These are soft supervision milestones only. They are here to keep the route plausible, "
        "not to lock wording or exact step count.\n"
        f"{json.dumps(hidden_milestone_summary, ensure_ascii=False, indent=2)}\n\n"
        "[Hidden Aux Target]\n"
        f"{hidden_aux_brief}\n\n"
        "[Task]\n"
        "Return exactly one JSON object that captures a full visible-only reasoning dossier. "
        "The dossier should scan the figure, explain the obstacle, motivate the auxiliary construction, "
        "state the immediate consequences, bridge back to the old figure, and close to the goal.\n\n"
        "[Critical Requirements]\n"
        "- Keep the reasoning visible-only in tone, even though hidden milestones are available.\n"
        "- `visible_facts` should restate only public givens or direct public goal-side facts.\n"
        "- `image_scan` should state concrete figure relations such as midpoint, collinear, equal-length, parallel, perpendicular, or cyclic cues, not generic scene description.\n"
        "- Prefer direct relation sentences such as `a, c, e are collinear`, `line ae is perpendicular to line cf`, or `g is the midpoint of be`.\n"
        "- `coordinate_checks` are optional. Use them only when they genuinely support a later bridge or closure step.\n"
        "- If you use `coordinate_checks`, each one must name visible points only and explain why the check matters later.\n"
        "- `construction` must match the hidden aux target itself. Do not invent a different helper condition.\n"
        "- `aux_immediate_effects` must be direct consequences of the construction itself.\n"
        "- `bridge_chain` and `goal_closure` must use supports of the form `visible_facts[i]`, `image_scan[i]`, `coordinate_checks[i]`, `aux_immediate_effects[i]`, or earlier `bridge_chain[i]`.\n"
        "- Multi-point auxiliary constructions must explain the stages explicitly.\n"
        "- Avoid vague phrases such as desired angle equality, desired ratio, specific angle conditions, necessary relationships, or this point is crucial.\n"
        "- Do not mention proof ids, rule names, hidden hints, or coordinate-table wording.\n"
        "- Do not use LaTeX or markdown code fences in JSON values.\n\n"
        "[Output Schema Example]\n"
        f"{build_dossier_plan_json_example()}\n"
    )


def build_plan_retry_feedback(validation_message, aux_part):
    hints = [
        "Return exactly one JSON object with all required top-level keys.",
        "Use only support_refs of the form T*, C*, or earlier B*.",
        "If a coordinate-backed fact matters later, include it under selected_coordinate_candidate_ids and add a matching coordinate_derivations entry.",
    ]
    if "support_refs" in validation_message:
        hints.append("Each bridge step must cite only earlier evidence items, never a future bridge step.")
    if "coordinate_derivations" in validation_message:
        hints.append("Each coordinate_derivations entry must match a chosen coordinate candidate and explain why that computation matters.")
    if "goal_finish" in validation_message:
        hints.append("State one concrete final goal-side relation, not a vague closing sentence.")
    if "aux_direct_relations" in validation_message:
        hints.append("Keep aux_direct_relations to direct local consequences of the construction itself.")
    if aux_part and aux_part.count("x00") > 1:
        hints.append("Because the auxiliary target introduces multiple points, construction should describe the stages explicitly.")
    return "\n".join(f"- {hint}" for hint in hints)


def build_dossier_plan_retry_feedback(validation_message, aux_part):
    hints = [
        "Return exactly one JSON object with all required dossier keys.",
        "Use only support strings of the form visible_facts[i], image_scan[i], coordinate_checks[i], aux_immediate_effects[i], or earlier bridge_chain[i].",
        "Keep the route visible-only in tone and avoid proof-engine phrasing.",
        "Construction should match the hidden aux target instead of inventing a different helper condition.",
    ]
    if "image_scan" in validation_message:
        hints.append("Each image_scan item should name a concrete geometric relation cue, not a generic description of the scene or the target.")
        hints.append("Prefer direct relation sentences such as 'a, c, e are collinear' or 'line ae is perpendicular to line cf'.")
    if "coordinate_checks" in validation_message:
        hints.append("Coordinate checks are optional, but if present they must use visible points only and must support a later bridge or closure step.")
    if "aux_immediate_effects" in validation_message:
        hints.append("Keep aux_immediate_effects to direct consequences of the construction itself.")
        hints.append("Mirror the hidden aux target exactly instead of inventing a different condition for the new point.")
    if "goal_closure" in validation_message:
        hints.append("Goal closure must end on the correct goal-side relation family and must mention the goal-side points.")
    if "construction" in validation_message:
        hints.append("Construction must mention the auxiliary point names explicitly, match the hidden aux target, and keep staged wording for multi-point constructions.")
    if "forbidden pattern" in validation_message:
        hints.append("Avoid phrases like desired angle equality, desired ratio, specific angle conditions, necessary relationships, or this point is crucial.")
    if aux_part and aux_part.count("x00") > 1:
        hints.append("Because the auxiliary target introduces multiple points, the construction and follow-up should say first/then/finally or an equivalent staged strategy.")
    return "\n".join(f"- {hint}" for hint in hints)


def build_raw_plan_retry_feedback(validation_message, aux_part):
    del aux_part
    hints = [
        "Return exactly one JSON object with the required top-level keys.",
        "Use only support strings of the form text_facts_used[i], image_observations[i], coordinate_derivations[i], or earlier bridge_steps[i].",
        "Keep coordinate_derivations explicit: relation, points, calc_type, render_mode, and why_it_matters.",
    ]
    if "bridge_steps" in validation_message:
        hints.append("Bridge steps must be ordered and may reference only earlier bridge_steps[i].")
    if "goal_finish" in validation_message:
        hints.append("State one concrete goal-side closing relation using goal points near the end.")
    if "coordinate_derivations" in validation_message:
        hints.append("Coordinate derivations must use visible points only and stay grounded in a concrete midpoint, collinear, equal-length, parallel, or perpendicular check.")
    if "construction" in validation_message:
        hints.append("Construction must mention the auxiliary point names explicitly.")
    return "\n".join(f"- {hint}" for hint in hints)


def build_dossier_critic_prompt(record, dossier, hidden_milestone_summary):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    return (
        "You are checking a geometry reasoning dossier before it is rendered into final thinking.\n\n"
        "[Visible Problem]\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Candidate Dossier]\n"
        f"{json.dumps(dossier, ensure_ascii=False, indent=2)}\n\n"
        "[Hidden Milestone Summary]\n"
        f"{json.dumps(hidden_milestone_summary, ensure_ascii=False, indent=2)}\n\n"
        "[Task]\n"
        "Return exactly one JSON object with keys `approved`, `issues`, `summary`, and optional `revised_dossier`.\n"
        "- `approved` must be true only if the dossier stays visible-only, avoids unsupported jumps, and genuinely closes to the visible goal.\n"
        "- `issues` must be a short JSON list of concrete problems if not approved.\n"
        "- `summary` must be one short sentence.\n"
        "- `revised_dossier` may be included only when you can repair the route while preserving the same overall strategy.\n"
        "Do not output prose outside the JSON object.\n"
    )


def build_plan_critic_prompt(record, plan, hidden_route_hints):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    return (
        "You are checking a geometry CoT plan before it is rendered into final thinking.\n\n"
        "[Visible Problem]\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Candidate Plan]\n"
        f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        "[Hidden Route Hints]\n"
        f"{json.dumps(hidden_route_hints, ensure_ascii=False, indent=2)}\n\n"
        "[Task]\n"
        "Return exactly one JSON object with keys `approved`, `issues`, and `summary`.\n"
        "- `approved` must be true only if every bridge step is supported by its cited evidence and the ending still aligns with the hidden goal-side hints.\n"
        "- `issues` must be a short JSON list of concrete problems if not approved.\n"
        "- `summary` must be one short sentence.\n"
        "Do not rewrite the plan and do not output prose outside the JSON object.\n"
    )


def build_dossier_write_prompt(record, dossier, aux_part, coordinate_derivation_block):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    return (
        "You are writing the final geometry thinking trace for SFT from an approved reasoning dossier.\n\n"
        "[Visible Inputs]\n"
        "The student will only see the image and the public problem text below.\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Approved Dossier]\n"
        f"{json.dumps(dossier, ensure_ascii=False, indent=2)}\n\n"
        "[Approved Coordinate Snippets]\n"
        "These snippets are optional. Use one only when the dossier really depends on it, and keep it exactly as written.\n"
        f"{coordinate_derivation_block}\n\n"
        "[Hidden Aux Target]\n"
        f"{build_hidden_aux_brief(aux_part)}\n\n"
        "[Write Requirements]\n"
        "- Output only the plain-text content that should go inside one <thinking>...</thinking> block.\n"
        "- Write as if the reasoning comes from the image and the public problem text.\n"
        "- Start from the real obstacle and auxiliary motivation, then carry the route through the construction to the goal.\n"
        "- Distinguish public givens from figure observations in wording.\n"
        "- You may omit coordinates entirely. If you use coordinates, reuse one approved snippet verbatim.\n"
        "- Never assign coordinates to auxiliary points.\n"
        "- Do not mention hidden proofs, hidden hints, a coordinate table, or external supervision.\n"
        "- Do not use LaTeX, $...$, backticks, or XML tags.\n"
        "- Make the auxiliary effects, bridge chain, and goal closure explicit.\n"
    )


def build_write_prompt(record, plan, aux_part, coordinate_derivation_block):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    return (
        "You are writing the final geometry thinking trace for SFT.\n\n"
        "[Visible Inputs]\n"
        "The student will only see the image and the public problem text below.\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Approved Plan]\n"
        f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        "[Approved Coordinate Derivations]\n"
        "Reuse these plain-text computation snippets when they are relevant. Keep the coordinates exactly as written when you cite them.\n"
        f"{coordinate_derivation_block}\n\n"
        "[Hidden Aux Target]\n"
        f"{build_hidden_aux_brief(aux_part)}\n\n"
        "[Write Requirements]\n"
        "- Output only the plain-text content that should go inside one <thinking>...</thinking> block.\n"
        "- Start from the actual obstacle and helper idea, not from generic scene description.\n"
        "- Distinguish formal givens from image/coordinate observations in wording.\n"
        "- You may explicitly write visible-point coordinates and plain-text calculations.\n"
        "- Never assign coordinates to auxiliary points.\n"
        "- Do not mention hidden proofs, hidden hints, a coordinate table, or any external supervision.\n"
        "- Do not use LaTeX, $...$, backticks, or XML tags.\n"
        "- Keep the route faithful to aux_direct_relations, bridge_steps, and goal_finish.\n"
        "- Make each bridge step explicit and connect it to at least one cited support.\n"
    )


def build_dossier_writer_retry_feedback(validation_message, dossier):
    hints = [
        "Output only plain text, not <thinking> tags.",
        "Keep the body faithful to the approved dossier.",
    ]
    if "coordinate snippet" in validation_message:
        hints.append("If you use coordinates, reuse one approved coordinate snippet verbatim.")
    if "aux_immediate_effects" in validation_message:
        hints.append("State at least one direct consequence of the auxiliary construction before the bridge chain moves on.")
    if "bridge_chain" in validation_message:
        hints.append("Make each bridge claim explicit in order, without skipping the middle of the route.")
    if "goal_closure" in validation_message:
        hints.append("State the goal-side closing claim explicitly near the end.")
    if "first-person" in validation_message:
        hints.append("Use impersonal phrasing such as 'the obstacle is' or 'this gives'.")
    focus_points = []
    for step in dossier.get("bridge_chain", []) if isinstance(dossier, dict) else []:
        for support in step.get("supports", []) or []:
            if isinstance(support, str) and support not in focus_points:
                focus_points.append(support)
    if focus_points:
        hints.append(f"Keep the body grounded in dossier items such as {', '.join(focus_points[:5])}.")
    return "\n".join(f"- {hint}" for hint in hints)


def build_writer_retry_feedback(validation_message, plan):
    hints = [
        "Output only plain text, not <thinking> tags.",
        "Keep the route faithful to the approved bridge steps and goal_finish.",
    ]
    if "coordinate computation" in validation_message:
        hints.append("Reuse at least one approved coordinate derivation snippet when a coordinate-backed relation is part of the route.")
    if "goal_finish" in validation_message:
        hints.append("State the final approved goal_finish relation explicitly near the end.")
    if "bridge_steps" in validation_message:
        hints.append("Mention each approved bridge relation in order and include at least one supporting relation in the same local sentence.")
    if "first-person" in validation_message:
        hints.append("Use impersonal phrasing such as 'the obstacle is' or 'this gives'.")
    focus_points = []
    for step in plan.get("bridge_steps", []) if isinstance(plan, dict) else []:
        for point in step.get("focus_points", []) or []:
            if isinstance(point, str) and point not in focus_points:
                focus_points.append(point)
    if focus_points:
        hints.append(f"Keep the route tied to points such as {', '.join(focus_points[:6])}.")
    return "\n".join(f"- {hint}" for hint in hints)


__all__ = [
    "build_dossier_critic_prompt",
    "build_dossier_plan_json_example",
    "build_dossier_plan_prompt",
    "build_dossier_plan_retry_feedback",
    "build_dossier_write_prompt",
    "build_dossier_writer_retry_feedback",
    "build_formal_language_guide",
    "build_plan_json_example",
    "build_plan_prompt",
    "build_plan_retry_feedback",
    "build_plan_critic_prompt",
    "build_planning_guidance",
    "build_raw_record_plan_json_example",
    "build_raw_plan_retry_feedback",
    "build_raw_record_plan_prompt",
    "build_supervisor_payload",
    "build_write_prompt",
    "build_writer_retry_feedback",
]
