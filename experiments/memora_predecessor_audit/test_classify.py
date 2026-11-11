import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import classify_unresolved


class ClassificationTests(unittest.TestCase):
    def test_update_after_delete_with_matching_recorded_history(self):
        previous = [{"session_id": 7, "operation": "delete", "status": "invalidated"}]
        history = [{"session_id": 7, "operation": "delete"}]
        self.assertEqual(
            classify_unresolved("update", {"status": "stored"}, previous, history, {}),
            ("update|delete|invalidated|delete", None, False),
        )

    def test_skipped_delete_without_history_reports_shape(self):
        previous = [{"session_id": 4, "operation": "delete", "status": "skipped"}]
        self.assertEqual(
            classify_unresolved("delete", {"status": "skipped"}, previous, [], {}),
            ("delete|delete|skipped|not_supplied", "delete|native|none", False),
        )

    def test_unmatched_history_and_missing_prior_are_not_conflated(self):
        previous = [{"session_id": 1, "operation": "delete", "status": "invalidated"}]
        history = [{"session_id": 2, "operation": "delete"}]
        self.assertTrue(
            classify_unresolved("delete", {"status": "skipped"}, previous, history, {})[
                2
            ]
        )
        self.assertEqual(
            classify_unresolved("update", {"status": "stored"}, [], [], {})[0],
            "update|none|none|not_supplied",
        )

    def test_successful_supersession_is_not_an_unresolved_event(self):
        self.assertIsNone(
            classify_unresolved(
                "update", {"status": "stored", "superseded": True}, [], [], {}
            )
        )
        self.assertIsNone(
            classify_unresolved("delete", {"status": "invalidated"}, [], [], {})
        )

    def test_committed_receipt_has_no_examples_and_reconciles_counts(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "data/results/memora-predecessor-audit-20261111/aggregate.json"
        )
        data = json.loads(path.read_text())
        self.assertNotIn("sanitized_examples", data)
        groups = data["unresolved_by_last_same_key_and_recorded_history"]
        self.assertEqual(sum(groups.values()), 486)
        self.assertTrue(all(key.split("|")[1] == "delete" for key in groups))
        self.assertEqual(
            data["totals"]["renamed_predecessor_present"]
            + data["totals"]["renamed_predecessor_missing"],
            data["totals"]["renamed_updates"],
        )
        self.assertEqual(data["recorded_history_last_session_mismatches"], 0)


if __name__ == "__main__":
    unittest.main()
