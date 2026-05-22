import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_writ as rw


class FakeHealthResponse:
    def __init__(self, status: str):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self):
        return json.dumps({"status": self.status}).encode("utf-8")


class AutomemHealthCheckTests(unittest.TestCase):
    def test_accepts_healthy_status(self):
        original = rw.urllib.request.urlopen
        try:
            rw.urllib.request.urlopen = lambda _req, timeout: FakeHealthResponse(
                "healthy"
            )
            try:
                rw._check_automem("http://localhost:8001", "test-token")
            except SystemExit as exc:
                self.fail(f"healthy status should be accepted, got: {exc}")
        finally:
            rw.urllib.request.urlopen = original


class HistoryAwareInterpretationTests(unittest.TestCase):
    def _scenario(self, capabilities):
        return {"probe": {"required_capabilities": capabilities}}

    def _result(
        self,
        *,
        recall_correct=True,
        drift_detected=True,
        detected_failures=None,
        scenario_id="drift-001",
    ):
        return {
            "scenario_id": scenario_id,
            "scores": {
                "recall_correct": recall_correct,
                "drift_detected": drift_detected,
            },
            "detected_failures": detected_failures
            if detected_failures is not None
            else ["stale_memory"],
        }

    def test_classifies_history_preservation_stale_memory_as_likely_false_positive(self):
        self.assertTrue(
            rw._is_history_query_stale_false_positive(
                self._result(),
                self._scenario(["retrieval", "history_preservation"]),
            )
        )

    def test_does_not_classify_when_history_preservation_absent(self):
        self.assertFalse(
            rw._is_history_query_stale_false_positive(
                self._result(),
                self._scenario(["retrieval", "update_tracking"]),
            )
        )

    def test_does_not_classify_when_recall_incorrect(self):
        self.assertFalse(
            rw._is_history_query_stale_false_positive(
                self._result(recall_correct=False),
                self._scenario(["history_preservation"]),
            )
        )

    def test_does_not_classify_when_drift_not_detected(self):
        scenario = self._scenario(["history_preservation"])
        self.assertFalse(
            rw._is_history_query_stale_false_positive(
                self._result(drift_detected=False),
                scenario,
            )
        )
        self.assertFalse(
            rw._is_history_query_stale_false_positive(
                self._result(drift_detected=None),
                scenario,
            )
        )

    def test_summary_counts_raw_stale_and_history_false_positives_separately(self):
        report = {
            "scenario_results": [
                self._result(scenario_id="history-hit"),
                self._result(scenario_id="ordinary-stale"),
                self._result(
                    scenario_id="missing-stale",
                    recall_correct=False,
                    detected_failures=["stale_memory", "retrieval_miss"],
                ),
                self._result(
                    scenario_id="clean-history",
                    detected_failures=[],
                ),
            ]
        }
        scenarios = {
            "history-hit": self._scenario(["history_preservation"]),
            "ordinary-stale": self._scenario(["retrieval"]),
            "missing-stale": self._scenario(["history_preservation"]),
            "clean-history": self._scenario(["history_preservation"]),
        }

        summary = rw._summarize_history_aware_stale_failures(report, scenarios)

        self.assertEqual(summary["raw_stale_memory_failures"], 3)
        self.assertEqual(summary["history_query_stale_false_positives"], 1)
        self.assertEqual(summary["remaining_stale_memory_failures"], 2)


class MetricInterpretationTests(unittest.TestCase):
    def _report(self, aggregate, scores):
        return {
            "aggregate": aggregate,
            "scenario_results": [
                {"scores": score}
                for score in scores
            ],
        }

    def test_classifies_applicable_pass_metric(self):
        report = self._report(
            {"recall_accuracy": 1.0},
            [{"recall_correct": True}, {"recall_correct": True}],
        )

        self.assertEqual(
            rw._classify_aggregate_metric(report, "recall_accuracy")["status"],
            "pass",
        )

    def test_classifies_applicable_fail_metric(self):
        report = self._report(
            {"recall_accuracy": 0.5},
            [{"recall_correct": True}, {"recall_correct": False}],
        )

        self.assertEqual(
            rw._classify_aggregate_metric(report, "recall_accuracy")["status"],
            "fail",
        )

    def test_classifies_lower_is_better_metric(self):
        report = self._report(
            {"drift_rate": 0.0},
            [{"drift_detected": True}, {"drift_detected": True}],
        )

        interpretation = rw._classify_aggregate_metric(report, "drift_rate")

        self.assertEqual(interpretation["status"], "pass")
        self.assertEqual(interpretation["direction"], "lower_is_better")

    def test_classifies_not_exercised_metric(self):
        report = self._report(
            {"provenance_completeness": 0.0},
            [{"provenance_complete": None}, {"provenance_complete": None}],
        )

        self.assertEqual(
            rw._classify_aggregate_metric(report, "provenance_completeness")[
                "status"
            ],
            "not_exercised",
        )


if __name__ == "__main__":
    unittest.main()
