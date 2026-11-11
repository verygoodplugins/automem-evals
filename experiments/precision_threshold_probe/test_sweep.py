import json
import tempfile
import unittest
from pathlib import Path

import sweep


def row(query_id, *, kind="paraphrase", floor=0.0, score=0.3, rank=3):
    return {
        "query_id": query_id,
        "kind": kind,
        "floor": floor,
        "count": 5 if score is not None else 0,
        "top_score": score,
        "any_rank": rank,
        "expected": ["synthetic-target"],
        "scope_leaks": [],
        "inactive_leaks": [],
    }


class GateTests(unittest.TestCase):
    def test_gate_keeps_entire_result_list_and_abstains_only_below_threshold(self):
        rows = [row("kept", score=0.3, rank=3), row("dropped", score=0.2, rank=1)]
        result = sweep.gate(rows, 0.3)
        self.assertEqual(result["queries"], 2)
        self.assertEqual(result["nonempty"], 1)
        self.assertEqual(result["nonempty_rate"], 0.5)
        self.assertEqual(result["abstained"], 1)
        # Rank 3 is retained even though the individual target score is unknown.
        self.assertEqual(result["target_at_1"], 0)
        self.assertEqual(result["target_at_5"], 1)

    def test_gate_does_not_treat_empty_as_a_zero_scored_result(self):
        rows = [row("empty", score=None, rank=None)]
        self.assertEqual(sweep.gate(rows, 0)["nonempty"], 0)
        self.assertEqual(sweep.gate(rows, 0)["abstained"], 1)

    def test_actual_server_floor_is_kept_distinct_from_gate(self):
        zero = row("q", score=0.5, rank=3)
        actual = row("q", floor=0.4, score=0.5, rank=1)
        rows = {("paraphrase", "q", 0.0): zero, ("paraphrase", "q", 0.4): actual}
        summary = sweep.analyze(rows, rows)["arms"]["candidate"]
        self.assertEqual(
            summary["projected_query_gate"]["0.40"]["paraphrase"]["target_at_1"], 0
        )
        self.assertEqual(
            summary["observed_server_floor_0_4"]["paraphrase"]["target_at_1"], 1
        )
        self.assertEqual(
            summary["gate_vs_server_0_4_disagreements"]["paraphrase"]["target_at_1"], 1
        )

    def test_arm_pairing_rejects_different_query_sets_or_targets(self):
        a = {("paraphrase", "q", 0.0): row("q")}
        b = {("paraphrase", "other", 0.0): row("other")}
        with self.assertRaisesRegex(ValueError, "same query"):
            sweep.analyze(a, b)
        b = {("paraphrase", "q", 0.0): {**row("q"), "expected": ["different"]}}
        with self.assertRaisesRegex(ValueError, "different expected"):
            sweep.analyze(a, b)

    def test_load_refuses_wrong_candidate_and_incomplete_rows(self):
        doc = {
            "mode": "candidate",
            "baseline_sha": sweep.BASELINE,
            "candidate_sha": "wrong",
            "fixture_sha256": sweep.FIXTURE,
            "result": {"evaluation": {"rows": []}},
        }
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "receipt.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidate or arm"):
                sweep.load_rows(path, "candidate")
            doc["candidate_sha"] = sweep.CANDIDATE
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing or mismatched"):
                sweep.load_rows(path, "candidate")


if __name__ == "__main__":
    unittest.main()
