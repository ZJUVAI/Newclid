import json
import tempfile
import unittest
from pathlib import Path

from experiments.cot_sft_generation.run_artifacts import build_run_summary, build_semantic_audit_stub
from experiments.cot_sft_generation.semantic_review import (
    build_semantic_summary_fields,
    refresh_run_summary,
    validate_semantic_audit_alignment,
)


def _write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records):
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class CotSftReviewArtifactsTest(unittest.TestCase):
    def test_build_run_summary_tracks_surface_and_semantic_placeholders(self):
        item_record = {
            "sample_order": 0,
            "input_index": 1,
            "surface_pass": True,
            "success": True,
            "attempts_used": 2,
            "source_audit": {"has_issue": False},
            "generation_audit": {"has_issue": False},
        }
        semantic_record = build_semantic_audit_stub(item_record)

        summary = build_run_summary(
            input_jsonl="input.jsonl",
            total_candidates_with_aux=1,
            sampled_items=1,
            item_records=[item_record],
            semantic_audit_records=[semantic_record],
            source_audit_issue_items=0,
            generation_audit_issue_items=0,
            num_workers=1,
            max_retries_per_stage=3,
            model_name="model",
            output_jsonl="out.jsonl",
            artifacts_dir="artifacts",
            runtime_seconds=1.0,
        )

        self.assertEqual(summary["surface_pass_items"], 1)
        self.assertEqual(summary["surface_pass_rate"], 1.0)
        self.assertEqual(summary["semantic_review_status"], "not_reviewed")
        self.assertIsNone(summary["semantic_pass_rate"])
        self.assertIsNone(summary["manual_critical_error_rate"])
        self.assertEqual(summary["avg_attempts_used"], 2.0)

    def test_validate_semantic_audit_alignment_rejects_misaligned_rows(self):
        item_audits = [{"sample_order": 0, "input_index": 1, "surface_pass": True}]
        semantic_audits = [{"sample_order": 9, "input_index": 1, "surface_pass": True}]

        with self.assertRaises(ValueError) as ctx:
            validate_semantic_audit_alignment(item_audits, semantic_audits)

        self.assertIn("does not align", str(ctx.exception))

    def test_refresh_run_summary_updates_semantic_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            run_dir.mkdir()

            item_audits = [
                {
                    "sample_order": 0,
                    "input_index": 10,
                    "source_audit": {"has_issue": False},
                    "generation_audit": {"has_issue": False},
                    "surface_pass": True,
                    "success": True,
                },
                {
                    "sample_order": 1,
                    "input_index": 11,
                    "source_audit": {"has_issue": False},
                    "generation_audit": {"has_issue": True},
                    "surface_pass": False,
                    "success": False,
                },
            ]
            semantic_audits = [
                {
                    "sample_order": 0,
                    "input_index": 10,
                    "surface_pass": True,
                    "semantic_pass": True,
                    "manual_critical_error": False,
                    "review_status": "reviewed",
                    "issues": [],
                    "notes": "good",
                },
                {
                    "sample_order": 1,
                    "input_index": 11,
                    "surface_pass": False,
                    "semantic_pass": False,
                    "manual_critical_error": True,
                    "review_status": "reviewed",
                    "issues": ["bridge mismatch"],
                    "notes": "bad",
                },
            ]
            summary = {
                "input_jsonl": "input.jsonl",
                "total_candidates_with_aux": 2,
                "sampled_items": 2,
                "successful_items": 1,
                "failed_items": 1,
                "avg_attempts_used": 2.5,
            }

            _write_json(run_dir / "summary.json", summary)
            _write_jsonl(run_dir / "item_audits.jsonl", item_audits)
            _write_jsonl(run_dir / "semantic_audits.jsonl", semantic_audits)

            refreshed = refresh_run_summary(run_dir, write_summary=True)

            self.assertEqual(refreshed["surface_pass_rate"], 0.5)
            self.assertEqual(refreshed["semantic_review_status"], "fully_reviewed")
            self.assertEqual(refreshed["semantic_pass_rate"], 0.5)
            self.assertEqual(refreshed["manual_critical_error_items"], 1)
            self.assertEqual(refreshed["manual_critical_error_rate"], 0.5)
            self.assertEqual(refreshed["avg_attempts_used"], 2.5)

            persisted = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["semantic_fail_items"], 1)

    def test_build_semantic_summary_fields_handles_partial_review(self):
        item_audits = [
            {"sample_order": 0, "input_index": 1, "surface_pass": True},
            {"sample_order": 1, "input_index": 2, "surface_pass": True},
        ]
        semantic_audits = [
            {
                "sample_order": 0,
                "input_index": 1,
                "semantic_pass": True,
                "manual_critical_error": False,
            },
            {
                "sample_order": 1,
                "input_index": 2,
                "semantic_pass": None,
                "manual_critical_error": None,
            },
        ]

        summary_fields = build_semantic_summary_fields(item_audits, semantic_audits)

        self.assertEqual(summary_fields["semantic_review_status"], "partially_reviewed")
        self.assertEqual(summary_fields["semantic_reviewed_items"], 1)
        self.assertEqual(summary_fields["semantic_pass_rate"], 1.0)
        self.assertEqual(summary_fields["manual_critical_error_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
