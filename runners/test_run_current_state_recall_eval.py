import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_current_state_recall_eval as rcse


class RecallParamTests(unittest.TestCase):
    def test_assert_endpoint_allowed_rejects_malformed_endpoint(self):
        with self.assertRaisesRegex(SystemExit, "invalid endpoint"):
            rcse.assert_endpoint_allowed("localhost:8001", allow_non_local=False)

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

    def test_result_id_accepts_memory_id_alias(self):
        self.assertEqual(
            rcse._result_id({"memory": {"memory_id": "mem-1"}}),
            "mem-1",
        )


class RequestTests(unittest.TestCase):
    class _Response:
        def __init__(self, body: bytes):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self.body

    def test_json_request_returns_empty_dict_for_empty_response_body(self):
        with patch(
            "run_current_state_recall_eval.urllib.request.urlopen",
            return_value=self._Response(b""),
        ):
            response = rcse._json_request(
                "http://localhost:8001",
                "test-token",
                "DELETE",
                "/memory/mem-1",
            )

        self.assertEqual(response, {})

    def test_seed_fixtures_accepts_id_response_alias(self):
        fixture = rcse.MemoryFixture(
            key="fixture",
            content="fixture content",
            tags=["fixture"],
            importance=0.5,
        )

        def fake_request(endpoint, token, method, path, *, params=None, body=None, timeout=30):
            self.assertEqual(method, "POST")
            self.assertEqual(path, "/memory")
            return {"id": "mem-fixture"}

        with patch.object(rcse, "FIXTURES", [fixture]), patch.object(rcse, "RELATIONS", []), patch(
            "run_current_state_recall_eval._json_request",
            side_effect=fake_request,
        ):
            memory_ids = rcse.seed_fixtures(
                "http://localhost:8001",
                "test-token",
                run_tag="run-1",
                now=rcse.dt.datetime.now(rcse.dt.timezone.utc),
            )

        self.assertEqual(memory_ids, {"fixture": "mem-fixture"})

    def test_cleanup_run_tag_deletes_each_recalled_memory_id(self):
        calls = []

        def fake_request(endpoint, token, method, path, *, params=None, body=None, timeout=30):
            if method == "GET":
                self.assertEqual(path, "/recall")
                self.assertEqual(params["tags"], ["run-1"])
                return {
                    "results": [
                        {"id": "mem-1"},
                        {"memory": {"id": "mem-2"}},
                        {"memory": {"memory_id": "mem-3"}},
                    ]
                }
            if method == "DELETE":
                calls.append(path)
                return {}
            raise AssertionError(f"unexpected request: {method} {path}")

        with patch(
            "run_current_state_recall_eval._json_request",
            side_effect=fake_request,
        ):
            result = rcse.cleanup_run_tag(
                "http://localhost:8001",
                "test-token",
                "run-1",
            )

        self.assertEqual(calls, ["/memory/mem-1", "/memory/mem-2", "/memory/mem-3"])
        self.assertEqual(result["strategy"], "per-id")
        self.assertEqual(result["deleted_count"], 3)


if __name__ == "__main__":
    unittest.main()
