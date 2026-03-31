from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/figures/fig_rule_extraction.py"
SPEC = importlib.util.spec_from_file_location("fig_rule_extraction", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_resolve_conclusion_prefers_rule_text_over_node_order() -> None:
    pruned_rendered = {
        "nodes": [
            {"idx": 0, "type": "fact", "label": "contrir(c,e,f,d,e,f)"},
            {"idx": 1, "type": "fact", "label": "eqangle(c,e,e,f,e,f,d,e)"},
        ],
        "edges": [[1, 0]],
    }

    result = MODULE._resolve_conclusion_label(
        pruned_rendered,
        rule_text="para a b c d, cong a d b c => contrir c e f d e f",
    )

    assert result == "contrir(c,e,f,d,e,f)"


def test_resolve_conclusion_falls_back_to_unique_sink_fact() -> None:
    pruned_rendered = {
        "nodes": [
            {"idx": 0, "type": "fact", "label": "contrir(c,e,f,d,e,f)"},
            {"idx": 1, "type": "fact", "label": "eqangle(c,e,e,f,e,f,d,e)"},
            {"idx": 2, "type": "rule", "label": "r102"},
        ],
        "edges": [[1, 2], [2, 0]],
    }

    result = MODULE._resolve_conclusion_label(pruned_rendered, rule_text=None)

    assert result == "contrir(c,e,f,d,e,f)"


def test_prepare_figure_data_marks_true_conclusion() -> None:
    full_raw = {
        "nodes": [
            {"id": "f0", "type": "fact", "short": "eqangle", "full": "eqangle(c,e,e,f,e,f,d,e)"},
            {"id": "f1", "type": "fact", "short": "contrir", "full": "contrir(c,e,f,d,e,f)"},
        ],
        "edges": [("f0", "f1")],
        "aux_points": set(),
    }
    pruned_rendered = {
        "nodes": [
            {"idx": 0, "type": "fact", "label": "contrir(c,e,f,d,e,f)"},
            {"idx": 1, "type": "fact", "label": "eqangle(c,e,e,f,e,f,d,e)"},
        ],
        "edges": [[1, 0]],
    }

    prepared = MODULE.prepare_figure_data(
        full_raw,
        pruned_rendered,
        rule_text="para a b c d, cong a d b c => contrir c e f d e f",
    )

    assert prepared["conclusion_id"] == "f1"


def test_select_pruned_render_picks_matching_subgraph_for_rule_conclusion() -> None:
    rendered_list = [
        {
            "nodes": [
                {"idx": 0, "type": "fact", "label": "eqangle(c,e,e,f,e,f,d,e)"},
            ],
            "edges": [],
        },
        {
            "nodes": [
                {"idx": 0, "type": "fact", "label": "contrir(c,e,f,d,e,f)"},
                {"idx": 1, "type": "fact", "label": "simtrir(c,e,f,d,e,f)"},
            ],
            "edges": [[1, 0]],
        },
    ]

    selected = MODULE._select_pruned_render(
        rendered_list,
        rule_text="para a b c d, cong a d b c => contrir c e f d e f",
    )

    assert MODULE._resolve_conclusion_label(selected) == "contrir(c,e,f,d,e,f)"