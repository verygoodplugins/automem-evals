import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_current_state_recall_eval as rcse


class RecallParamTests(unittest.TestCase):
    def test_build_recall_params_applies_global_current_only_flag(self):
        probe = rcse.Probe(
            id="temporal",
            query="favorite editor",
            params={"tags": ["RUN_TAG", "temporal"], "tag_mode": "all"},
            current_present=["active"],
            current_absent=["expired"],
            unfiltered_present=["active", "expired"],
        )

        params = rcse.build_recall_params(
            probe,
            run_tag="eval-123",
            current_only="false",
        )

        self.assertEqual(params["tags"], ["eval-123", "temporal"])
        self.assertEqual(params["current_only"], False)
        self.assertEqual(params["state_debug"], True)

    def test_probe_current_only_override_wins(self):
        probe = rcse.Probe(
            id="history",
            query="favorite editor",
            params={"tags": ["RUN_TAG", "temporal"], "current_only": False},
            current_present=["active"],
            current_absent=["expired"],
            unfiltered_present=["active", "expired"],
            expect_mode="unfiltered",
        )

        params = rcse.build_recall_params(
            probe,
            run_tag="eval-123",
            current_only="true",
        )

        self.assertEqual(params["current_only"], False)


class ScoringTests(unittest.TestCase):
    def _response(self, ids, suppressed_count=0):
        return {
            "results": [{"id": memory_id, "memory": {"id": memory_id}} for memory_id in ids],
            "state_filter": {"suppressed_count": suppressed_count},
        }

    def test_current_mode_requires_present_and_absent_sets(self):
        probe = rcse.Probe(
            id="temporal",
            query="favorite editor",
            params={},
            current_present=["active"],
            current_absent=["expired", "future"],
            unfiltered_present=["active", "expired", "future"],
            min_suppressed_current=2,
        )
        memory_ids = {
            "active": "mem-active",
            "expired": "mem-expired",
            "future": "mem-future",
        }

        score = rcse.score_probe(
            probe,
            self._response(["mem-active"], suppressed_count=2),
            memory_ids,
            default_expect_mode="current",
        )

        self.assertTrue(score["passed"])
        self.assertEqual(score["missing"], [])
        self.assertEqual(score["unexpected"], [])

    def test_current_mode_fails_on_stale_leak(self):
        probe = rcse.Probe(
            id="temporal",
            query="favorite editor",
            params={},
            current_present=["active"],
            current_absent=["expired"],
            unfiltered_present=["active", "expired"],
        )
        memory_ids = {"active": "mem-active", "expired": "mem-expired"}

        score = rcse.score_probe(
            probe,
            self._response(["mem-active", "mem-expired"], suppressed_count=0),
            memory_ids,
            default_expect_mode="current",
        )

        self.assertFalse(score["passed"])
        self.assertEqual(score["unexpected"], ["expired"])

    def test_unfiltered_mode_requires_historical_memories(self):
        probe = rcse.Probe(
            id="temporal",
            query="favorite editor",
            params={},
            current_present=["active"],
            current_absent=["expired"],
            unfiltered_present=["active", "expired"],
        )
        memory_ids = {"active": "mem-active", "expired": "mem-expired"}

        score = rcse.score_probe(
            probe,
            self._response(["mem-active", "mem-expired"], suppressed_count=0),
            memory_ids,
            default_expect_mode="unfiltered",
        )

        self.assertTrue(score["passed"])
        self.assertEqual(score["missing"], [])


if __name__ == "__main__":
    unittest.main()
