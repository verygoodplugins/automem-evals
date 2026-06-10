import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_vector_identity as checker


class VectorIdentityTests(unittest.TestCase):
    def test_compare_vector_hashes_reports_identical_sets(self):
        summary = checker.compare_vector_hashes(
            {"a": "hash-a", "b": "hash-b"},
            {"a": "hash-a", "b": "hash-b"},
            variant="server-metadata-search",
        )

        self.assertTrue(summary["vectors_identical"])
        self.assertEqual(summary["changed_vector_count"], 0)
        self.assertEqual(summary["missing_candidate_count"], 0)
        self.assertEqual(summary["extra_candidate_count"], 0)

    def test_compare_vector_hashes_reports_changed_missing_and_extra_ids(self):
        summary = checker.compare_vector_hashes(
            {"a": "hash-a", "b": "hash-b"},
            {"a": "changed", "c": "hash-c"},
            variant="server-metadata-search",
        )

        self.assertFalse(summary["vectors_identical"])
        self.assertEqual(summary["changed_vector_ids_sample"], ["a"])
        self.assertEqual(summary["missing_candidate_ids_sample"], ["b"])
        self.assertEqual(summary["extra_candidate_ids_sample"], ["c"])

    def test_write_identity_artifacts_writes_preflight_summary_and_empty_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = checker.compare_vector_hashes(
                {"a": "hash-a"}, {"a": "hash-a"}, variant="server-metadata-search"
            )

            checker.write_identity_artifacts(
                summary,
                plan_output=root / "transform_plan.jsonl",
                summary_output=root / "transform_summary.json",
                vector_preflight_output=root / "vector_preflight.json",
            )

            self.assertEqual((root / "transform_plan.jsonl").read_text(), "")
            self.assertIn('"vector_identity"', (root / "transform_summary.json").read_text())
            self.assertIn('"vectors_identical": true', (root / "vector_preflight.json").read_text())


if __name__ == "__main__":
    unittest.main()
