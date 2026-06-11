import unittest
import sys
import tempfile
import json
import urllib.error
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_recall_endpoints as cre


class EndpointGuardTests(unittest.TestCase):
    def test_localhost_allowed(self):
        self.assertTrue(cre.is_local_endpoint("http://localhost:8011"))
        self.assertTrue(cre.is_local_endpoint("http://127.0.0.1:8011"))

    def test_remote_not_local(self):
        self.assertFalse(cre.is_local_endpoint("https://automem.example.com"))


class HttpTests(unittest.TestCase):
    def test_http_get_json_retries_timeout_with_configured_timeout(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true}'

        calls = []

        def fake_urlopen(req, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise TimeoutError("timed out")
            return FakeResponse()

        with mock.patch.object(
            cre.urllib.request, "urlopen", side_effect=fake_urlopen
        ), mock.patch.object(cre.time, "sleep") as sleep:
            payload = cre.http_get_json(
                "http://localhost:8011",
                "token",
                "/health",
                timeout_seconds=12,
                retries=1,
                retry_delay_seconds=0.01,
            )

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(calls, [12, 12])
        sleep.assert_called_once_with(0.01)

    def test_http_get_json_reraises_after_retry_budget(self):
        with mock.patch.object(
            cre.urllib.request, "urlopen", side_effect=urllib.error.URLError("down")
        ), mock.patch.object(cre.time, "sleep"):
            with self.assertRaises(urllib.error.URLError):
                cre.http_get_json(
                    "http://localhost:8011",
                    "token",
                    "/health",
                    timeout_seconds=12,
                    retries=1,
                    retry_delay_seconds=0,
                )


class DiffTests(unittest.TestCase):
    def test_summarize_response_includes_score_diagnostics(self):
        response = {
            "count": 1,
            "results": [
                {
                    "id": "m1",
                    "final_score": 0.7,
                    "original_score": 0.81,
                    "match_type": "vector",
                    "source": "qdrant",
                    "score_components": {"vector": 0.81, "tag": 0.25},
                    "memory": {
                        "id": "m1",
                        "tags": ["automem"],
                        "content": "Useful recall result",
                    },
                }
            ],
        }

        summary = cre.summarize_response(response)

        self.assertEqual(summary["top"][0]["original_score"], 0.81)
        self.assertEqual(summary["top"][0]["match_type"], "vector")
        self.assertEqual(summary["top"][0]["source"], "qdrant")
        self.assertEqual(summary["top"][0]["score_components"]["vector"], 0.81)

    def test_diff_summary_detects_top_changes_and_lost_ids(self):
        baseline = {"count": 3, "returned": 3, "top_ids": ["a", "b", "c"]}
        candidate = {"count": 2, "returned": 2, "top_ids": ["b", "d"]}
        diff = cre.diff_summary(baseline, candidate)
        self.assertEqual(diff["count_delta"], -1)
        self.assertTrue(diff["top_changed"])
        self.assertEqual(diff["lost_top5"], ["a", "c"])
        self.assertEqual(diff["gained_top5"], ["d"])

    def test_preserve_regression_status(self):
        diff = {
            "count_delta": 0,
            "returned_delta": 0,
            "top_changed": True,
            "lost_top5": [],
            "gained_top5": [],
        }
        self.assertEqual(cre.classify_status("preserve", diff), "REGRESSION")

    def test_preserve_near_tie_top_swap_is_review(self):
        baseline = {
            "count": 10,
            "returned": 10,
            "top_ids": ["a", "b", "c", "d", "e"],
            "top": [
                {"id": "a", "score": 0.6315270934615385},
                {"id": "b", "score": 0.6315239246153846},
                {"id": "c", "score": 0.59},
                {"id": "d", "score": 0.58},
                {"id": "e", "score": 0.57},
            ],
        }
        candidate = {
            "count": 10,
            "returned": 10,
            "top_ids": ["b", "a", "c", "d", "e"],
            "top": [
                {"id": "b", "score": 0.6317135896153846},
                {"id": "a", "score": 0.6316897734615384},
                {"id": "c", "score": 0.59},
                {"id": "d", "score": 0.58},
                {"id": "e", "score": 0.57},
            ],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertTrue(diff["top_changed"])
        self.assertTrue(diff["top_swap_near_tie"])
        self.assertLess(diff["top_swap_score_gap"], 0.001)
        self.assertEqual(cre.classify_status("preserve", diff), "review")

    def test_preserve_material_top_swap_is_regression(self):
        baseline = {
            "count": 2,
            "returned": 2,
            "top_ids": ["a", "b"],
            "top": [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.6}],
        }
        candidate = {
            "count": 2,
            "returned": 2,
            "top_ids": ["b", "a"],
            "top": [{"id": "b", "score": 0.91}, {"id": "a", "score": 0.59}],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertTrue(diff["top_changed"])
        self.assertFalse(diff["top_swap_near_tie"])
        self.assertEqual(cre.classify_status("preserve", diff), "REGRESSION")

    def test_preserve_top_five_churn_is_regression(self):
        diff = {
            "count_delta": 0,
            "returned_delta": 0,
            "top_changed": False,
            "lost_top5": ["a"],
            "gained_top5": ["b"],
        }
        self.assertEqual(cre.classify_status("preserve", diff), "REGRESSION")

    def test_preserve_count_drop_is_regression(self):
        diff = {
            "count_delta": -1,
            "returned_delta": -1,
            "top_changed": False,
            "lost_top5": [],
            "gained_top5": [],
        }
        self.assertEqual(cre.classify_status("preserve", diff), "REGRESSION")

    def test_noise_drop_is_improved(self):
        diff = {
            "count_delta": -5,
            "returned_delta": -5,
            "top_changed": True,
            "lost_top5": ["a"],
            "gained_top5": [],
        }
        self.assertEqual(cre.classify_status("noise", diff), "improved")

    def test_diff_summary_records_top1_scores_for_both_sides(self):
        baseline = {
            "count": 2,
            "returned": 2,
            "top_ids": ["a", "b"],
            "top": [{"id": "a", "score": 0.71}, {"id": "b", "score": 0.5}],
        }
        candidate = {
            "count": 2,
            "returned": 2,
            "top_ids": ["a", "b"],
            "top": [{"id": "a", "score": 0.42}, {"id": "b", "score": 0.3}],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(diff["top1_score_baseline"], 0.71)
        self.assertEqual(diff["top1_score_candidate"], 0.42)

    def test_diff_summary_top1_scores_are_none_for_empty_results(self):
        baseline = {"count": 0, "returned": 0, "top_ids": [], "top": []}
        candidate = {"count": 0, "returned": 0, "top_ids": [], "top": []}

        diff = cre.diff_summary(baseline, candidate)

        self.assertIsNone(diff["top1_score_baseline"])
        self.assertIsNone(diff["top1_score_candidate"])

    def test_negative_fewer_candidate_results_is_improved(self):
        baseline = {
            "count": 3,
            "returned": 3,
            "top_ids": ["a", "b", "c"],
            "top": [
                {"id": "a", "score": 0.7},
                {"id": "b", "score": 0.6},
                {"id": "c", "score": 0.5},
            ],
        }
        candidate = {"count": 0, "returned": 0, "top_ids": [], "top": []}

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(cre.classify_status("negative", diff), "improved")

    def test_negative_more_candidate_results_is_regression(self):
        baseline = {"count": 0, "returned": 0, "top_ids": [], "top": []}
        candidate = {
            "count": 2,
            "returned": 2,
            "top_ids": ["a", "b"],
            "top": [{"id": "a", "score": 0.6}, {"id": "b", "score": 0.5}],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(cre.classify_status("negative", diff), "REGRESSION")

    def test_negative_higher_top1_score_same_count_is_regression(self):
        baseline = {
            "count": 1,
            "returned": 1,
            "top_ids": ["a"],
            "top": [{"id": "a", "score": 0.45}],
        }
        candidate = {
            "count": 1,
            "returned": 1,
            "top_ids": ["a"],
            "top": [{"id": "a", "score": 0.62}],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(cre.classify_status("negative", diff), "REGRESSION")

    def test_negative_lower_top1_score_same_count_is_improved(self):
        baseline = {
            "count": 1,
            "returned": 1,
            "top_ids": ["a"],
            "top": [{"id": "a", "score": 0.62}],
        }
        candidate = {
            "count": 1,
            "returned": 1,
            "top_ids": ["a"],
            "top": [{"id": "a", "score": 0.45}],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(cre.classify_status("negative", diff), "improved")

    def test_negative_identical_results_is_ok(self):
        baseline = {
            "count": 1,
            "returned": 1,
            "top_ids": ["a"],
            "top": [{"id": "a", "score": 0.45}],
        }
        candidate = {
            "count": 1,
            "returned": 1,
            "top_ids": ["a"],
            "top": [{"id": "a", "score": 0.45}],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(cre.classify_status("negative", diff), "ok")

    def test_negative_both_empty_is_ok(self):
        baseline = {"count": 0, "returned": 0, "top_ids": [], "top": []}
        candidate = {"count": 0, "returned": 0, "top_ids": [], "top": []}

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(cre.classify_status("negative", diff), "ok")

    def test_negative_fewer_results_with_higher_top1_is_regression(self):
        # Safety-first: a higher-confidence false positive outweighs a count drop.
        baseline = {
            "count": 3,
            "returned": 3,
            "top_ids": ["a", "b", "c"],
            "top": [
                {"id": "a", "score": 0.45},
                {"id": "b", "score": 0.4},
                {"id": "c", "score": 0.35},
            ],
        }
        candidate = {
            "count": 1,
            "returned": 1,
            "top_ids": ["a"],
            "top": [{"id": "a", "score": 0.8}],
        }

        diff = cre.diff_summary(baseline, candidate)

        self.assertEqual(cre.classify_status("negative", diff), "REGRESSION")

    def test_negative_without_top1_scores_in_diff_falls_back_to_counts(self):
        # The .get() fallback covers hand-built or external diff dicts that lack
        # top1 keys. (In --baseline-summary mode diffs are always recomputed by
        # diff_summary from saved summaries, which carry "top", so this fallback
        # never serves a real saved-summary path.)
        diff = {
            "count_delta": 0,
            "returned_delta": 0,
            "top_changed": False,
            "lost_top5": [],
            "gained_top5": [],
        }
        self.assertEqual(cre.classify_status("negative", diff), "ok")

    def test_tag_filter_diagnostic_matches_recall_params(self):
        self.assertTrue(
            cre.passes_tag_filter(
                ["automem", "locomo"],
                {"tags": ["automem", "locomo"], "tag_mode": "all"},
            )
        )
        self.assertFalse(
            cre.passes_tag_filter(
                ["automem"],
                {"tags": ["automem", "locomo"], "tag_mode": "all"},
            )
        )
        self.assertTrue(
            cre.passes_tag_filter(
                ["automem"],
                {"tags": ["locomo", "automem"], "tag_mode": "any"},
            )
        )

    def test_write_regression_diagnostics_fetches_graph_and_qdrant_payloads(self):
        row = {
            "id": "Q1",
            "params": {"tags": ["automem", "locomo"], "tag_mode": "all"},
            "baseline": {
                "top": [
                    {
                        "id": "lost",
                        "score_components": {"vector": 0.8},
                        "tags": ["automem", "locomo"],
                    }
                ]
            },
            "candidate": {
                "top": [
                    {
                        "id": "gained",
                        "score_components": {"vector": 0.7},
                        "tags": ["automem", "locomo"],
                    }
                ]
            },
            "diff": {"lost_top5": ["lost"], "gained_top5": ["gained"]},
        }

        def fake_http(endpoint, token, path, params=None):
            memory_id = path.rsplit("/", 1)[-1]
            return {
                "memory": {
                    "id": memory_id,
                    "tags": (
                        ["automem", "locomo"] if memory_id == "lost" else ["automem"]
                    ),
                    "metadata": {"entities": {"tools": ["Qdrant"]}},
                }
            }

        def fake_qdrant(qdrant_url, collection, point_id, token=None):
            return {"id": point_id, "payload": {"tags": ["automem", "locomo"]}}

        with tempfile.TemporaryDirectory() as tmp:
            path = cre.write_regression_diagnostics(
                row=row,
                baseline_endpoint="http://localhost:8011",
                candidate_endpoint="http://localhost:8012",
                token="token",
                out_dir=Path(tmp),
                baseline_qdrant_url="http://localhost:6333",
                candidate_qdrant_url="http://localhost:6334",
                qdrant_collection="memories",
                http_get=fake_http,
                qdrant_get=fake_qdrant,
            )

            data = json.loads(path.read_text())

        self.assertEqual(data["query_id"], "Q1")
        self.assertEqual(data["lost"][0]["id"], "lost")
        self.assertTrue(data["lost"][0]["baseline"]["passes_tag_filter"])
        self.assertFalse(data["gained"][0]["candidate"]["passes_tag_filter"])
        self.assertEqual(
            data["lost"][0]["baseline"]["qdrant_payload"]["tags"], ["automem", "locomo"]
        )

    def test_diagnostics_include_scores_components_and_payload_filter_status(self):
        row = {
            "id": "Q2",
            "params": {"tags": ["automem", "locomo"], "tag_mode": "all"},
            "baseline": {
                "top": [
                    {
                        "id": "lost",
                        "score": 0.91,
                        "original_score": 0.97,
                        "score_components": {"vector": 0.88, "tag": 0.5},
                        "tags": ["automem", "locomo"],
                    }
                ]
            },
            "candidate": {
                "top": [
                    {
                        "id": "gained",
                        "score": 0.82,
                        "original_score": 0.84,
                        "score_components": {"vector": 0.79, "tag": 0.25},
                        "tags": ["automem", "locomo"],
                    }
                ]
            },
            "diff": {"lost_top5": ["lost"], "gained_top5": ["gained"]},
        }

        def fake_http(endpoint, token, path, params=None):
            memory_id = path.rsplit("/", 1)[-1]
            return {
                "memory": {
                    "id": memory_id,
                    "tags": ["automem", "locomo"],
                    "metadata": {"entities": {"tools": ["Qdrant"]}},
                }
            }

        def fake_qdrant(qdrant_url, collection, point_id, token=None):
            tags = ["automem", "locomo"] if point_id == "lost" else ["automem"]
            return {"id": point_id, "payload": {"tags": tags}}

        with tempfile.TemporaryDirectory() as tmp:
            path = cre.write_regression_diagnostics(
                row=row,
                baseline_endpoint="http://localhost:8011",
                candidate_endpoint="http://localhost:8012",
                token="token",
                out_dir=Path(tmp),
                baseline_qdrant_url="http://localhost:6333",
                candidate_qdrant_url="http://localhost:6334",
                http_get=fake_http,
                qdrant_get=fake_qdrant,
            )
            data = json.loads(path.read_text())

        baseline_lost = data["lost"][0]["baseline"]
        candidate_gained = data["gained"][0]["candidate"]
        self.assertEqual(baseline_lost["score"], 0.91)
        self.assertEqual(baseline_lost["original_score"], 0.97)
        self.assertEqual(
            baseline_lost["score_components"], {"vector": 0.88, "tag": 0.5}
        )
        self.assertTrue(baseline_lost["graph_passes_tag_filter"])
        self.assertTrue(baseline_lost["qdrant_passes_tag_filter"])
        self.assertTrue(candidate_gained["graph_passes_tag_filter"])
        self.assertFalse(candidate_gained["qdrant_passes_tag_filter"])

    def test_diagnostics_include_changed_top_ids_without_lost_or_gained_ids(self):
        row = {
            "id": "Q3",
            "params": {"tags": ["automem"], "tag_mode": "any"},
            "baseline": {
                "top": [
                    {
                        "id": "a",
                        "score_components": {"vector": 0.9},
                        "tags": ["automem"],
                    },
                    {
                        "id": "b",
                        "score_components": {"vector": 0.8},
                        "tags": ["automem"],
                    },
                ]
            },
            "candidate": {
                "top": [
                    {
                        "id": "b",
                        "score_components": {"vector": 0.91},
                        "tags": ["automem"],
                    },
                    {
                        "id": "a",
                        "score_components": {"vector": 0.79},
                        "tags": ["automem"],
                    },
                ]
            },
            "diff": {"top_changed": True, "lost_top5": [], "gained_top5": []},
        }

        def fake_http(endpoint, token, path, params=None):
            memory_id = path.rsplit("/", 1)[-1]
            return {"memory": {"id": memory_id, "tags": ["automem"], "metadata": {}}}

        def fake_qdrant(qdrant_url, collection, point_id, token=None):
            return {"id": point_id, "payload": {"tags": ["automem"]}}

        with tempfile.TemporaryDirectory() as tmp:
            path = cre.write_regression_diagnostics(
                row=row,
                baseline_endpoint="http://localhost:8011",
                candidate_endpoint="http://localhost:8012",
                token="token",
                out_dir=Path(tmp),
                baseline_qdrant_url="http://localhost:6333",
                candidate_qdrant_url="http://localhost:6334",
                http_get=fake_http,
                qdrant_get=fake_qdrant,
            )
            data = json.loads(path.read_text())

        self.assertEqual([entry["id"] for entry in data["changed_top"]], ["a", "b"])
        self.assertEqual(
            data["changed_top"][0]["baseline"]["score_components"], {"vector": 0.9}
        )
        self.assertEqual(
            data["changed_top"][1]["candidate"]["score_components"], {"vector": 0.91}
        )


class PreflightTests(unittest.TestCase):
    def test_health_preflight_rejects_unsynced_endpoint(self):
        errors = cre.validate_health_pair(
            {"status": "healthy", "memory_count": 10, "vector_count": 10},
            {"status": "healthy", "memory_count": 10, "vector_count": 9},
        )

        self.assertIn("candidate memory_count/vector_count mismatch: 10 != 9", errors)

    def test_recall_vector_component_detection_requires_positive_vector_score(self):
        response = {"results": [{"score_components": {"vector": 0.0}}]}

        ok, diagnostic = cre.recall_has_positive_vector_component(response)

        self.assertFalse(ok)
        self.assertEqual(diagnostic["max_vector_component"], 0.0)

    def test_preflight_writes_failure_artifact_and_refuses_classification(self):
        calls = []

        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 1, "vector_count": 1}
            calls.append((endpoint, path, params))
            return {"results": [{"score_components": {"vector": 0.0}}]}

        result = cre.run_preflight(
            baseline_endpoint="http://localhost:8011",
            candidate_endpoint="http://localhost:8012",
            token="token",
            probes=[{"id": "warmup", "query": "hello", "params": {}}],
            http_get=fake_get,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(any("vector component" in error for error in result["errors"]))
        self.assertEqual(len(calls), 2)

    def test_preflight_allows_zero_vector_probe_after_endpoint_positive_warmup(self):
        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 2, "vector_count": 2}
            if params["query"] == "healthy vector probe":
                return {"results": [{"id": "v1", "score_components": {"vector": 0.82}}]}
            return {"results": [{"id": "k1", "score_components": {"vector": 0.0}}]}

        result = cre.run_preflight(
            baseline_endpoint="http://localhost:8011",
            candidate_endpoint="http://localhost:8012",
            token="token",
            probes=[
                {"id": "vector", "query": "healthy vector probe", "params": {}},
                {"id": "keyword", "query": "keyword-like probe", "params": {}},
            ],
            http_get=fake_get,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["positive_vector_warmups"]["baseline"], 1)
        self.assertEqual(result["positive_vector_warmups"]["candidate"], 1)

    def test_preflight_fills_missing_health_vector_count_from_qdrant_count(self):
        def fake_get(endpoint, token, path, params=None):
            if path == "/health" and endpoint.endswith("8011"):
                return {"status": "healthy", "memory_count": 10, "vector_count": 10}
            if path == "/health":
                return {"status": "healthy", "memory_count": 10, "vector_count": None}
            return {"results": [{"id": "v1", "score_components": {"vector": 0.82}}]}

        qdrant_calls = []

        def fake_qdrant_count(qdrant_url, collection):
            qdrant_calls.append((qdrant_url, collection))
            return 10

        result = cre.run_preflight(
            baseline_endpoint="http://localhost:8011",
            candidate_endpoint="http://localhost:8012",
            token="token",
            probes=[{"id": "vector", "query": "healthy vector probe", "params": {}}],
            http_get=fake_get,
            baseline_qdrant_url="http://localhost:6843",
            candidate_qdrant_url="http://localhost:6844",
            qdrant_collection="memories",
            qdrant_count=fake_qdrant_count,
        )

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["candidate_health"]["vector_count"], 10)
        self.assertEqual(result["qdrant_count_fallbacks"]["candidate"], 10)
        self.assertEqual(qdrant_calls, [("http://localhost:6844", "memories")])

    def test_qdrant_count_points_retries_transient_connection_reset(self):
        calls = []
        original_urlopen = cre.urllib.request.urlopen

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"result":{"points_count":42}}'

        def fake_urlopen(request, timeout=30):
            calls.append((request.full_url, timeout))
            if len(calls) == 1:
                raise ConnectionResetError("connection reset by peer")
            return FakeResponse()

        try:
            cre.urllib.request.urlopen = fake_urlopen
            count = cre.qdrant_count_points(
                "http://qdrant",
                "memories",
                retries=1,
                retry_delay_seconds=0,
            )
        finally:
            cre.urllib.request.urlopen = original_urlopen

        self.assertEqual(count, 42)
        self.assertEqual(len(calls), 2)

    def test_preflight_requires_endpoint_positive_vector_across_warmups(self):
        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 2, "vector_count": 2}
            if endpoint.endswith("8011"):
                return {"results": [{"id": "v1", "score_components": {"vector": 0.82}}]}
            return {"results": [{"id": "k1", "score_components": {"vector": 0.0}}]}

        result = cre.run_preflight(
            baseline_endpoint="http://localhost:8011",
            candidate_endpoint="http://localhost:8012",
            token="token",
            probes=[
                {"id": "one", "query": "first", "params": {}},
                {"id": "two", "query": "second", "params": {}},
            ],
            http_get=fake_get,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                "candidate had no warm-up probe with a positive vector component"
                in error
                for error in result["errors"]
            )
        )

    def test_preflight_rejects_empty_warmup_results(self):
        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 2, "vector_count": 2}
            if params["query"] == "empty" and endpoint.endswith("8012"):
                return {"results": []}
            return {"results": [{"id": "v1", "score_components": {"vector": 0.82}}]}

        result = cre.run_preflight(
            baseline_endpoint="http://localhost:8011",
            candidate_endpoint="http://localhost:8012",
            token="token",
            probes=[
                {"id": "vector", "query": "healthy vector probe", "params": {}},
                {"id": "empty", "query": "empty", "params": {}},
            ],
            http_get=fake_get,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                "candidate warm-up probe empty returned no results" in error
                for error in result["errors"]
            )
        )


class MainGateTests(unittest.TestCase):
    def test_main_writes_diagnostics_for_top_changed_without_lost_ids(self):
        scenario = {
            "description": "top changed diagnostics fixture",
            "queries": [
                {
                    "id": "TOP-CHANGED",
                    "group": "preserve",
                    "description": "top result changed but top five set is stable",
                    "query": "what changed",
                    "params": {},
                }
            ],
        }
        diagnostics_rows = []

        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 2, "vector_count": 2}
            if endpoint.endswith("8011"):
                return {
                    "count": 2,
                    "results": [
                        {"id": "a", "score_components": {"vector": 0.9}},
                        {"id": "b", "score_components": {"vector": 0.8}},
                    ],
                }
            return {
                "count": 2,
                "results": [
                    {"id": "b", "score_components": {"vector": 0.91}},
                    {"id": "a", "score_components": {"vector": 0.79}},
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            scenario_path = Path(tmp) / "scenario.json"
            scenario_path.write_text(json.dumps(scenario))
            run_dir = Path(tmp) / "run"

            def fake_diagnostics(**kwargs):
                diagnostics_rows.append(kwargs["row"])
                diagnostics_path = (
                    run_dir / "diagnostics" / f"{kwargs['row']['id']}.json"
                )
                diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
                diagnostics_path.write_text("{}")
                return diagnostics_path

            argv = [
                "compare_recall_endpoints.py",
                "--scenario",
                str(scenario_path),
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
                "--run-dir",
                str(run_dir),
                "--report",
                str(Path(tmp) / "report.md"),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                cre, "http_get_json", side_effect=fake_get
            ), mock.patch.object(
                cre, "write_regression_diagnostics", side_effect=fake_diagnostics
            ):
                exit_code = cre.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual([row["id"] for row in diagnostics_rows], ["TOP-CHANGED"])

    def test_main_handles_negative_group_scenario_end_to_end(self):
        scenario = {
            "description": "negative control fixture",
            "queries": [
                {
                    "id": "NEG-PROBE",
                    "group": "negative",
                    "description": "correct answer is nothing relevant",
                    "query": "topic the corpus cannot contain",
                    "params": {"limit": 10},
                }
            ],
        }

        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 2, "vector_count": 2}
            if endpoint.endswith("8011"):
                return {
                    "count": 2,
                    "results": [
                        {
                            "id": "off-topic-a",
                            "final_score": 0.7,
                            "score_components": {"vector": 0.7},
                        },
                        {
                            "id": "off-topic-b",
                            "final_score": 0.6,
                            "score_components": {"vector": 0.6},
                        },
                    ],
                }
            return {"count": 0, "results": []}

        with tempfile.TemporaryDirectory() as tmp:
            scenario_path = Path(tmp) / "scenario.json"
            scenario_path.write_text(json.dumps(scenario))
            run_dir = Path(tmp) / "run"

            def fake_diagnostics(**kwargs):
                diagnostics_path = (
                    run_dir / "diagnostics" / f"{kwargs['row']['id']}.json"
                )
                diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
                diagnostics_path.write_text("{}")
                return diagnostics_path

            argv = [
                "compare_recall_endpoints.py",
                "--scenario",
                str(scenario_path),
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
                "--run-dir",
                str(run_dir),
                "--report",
                str(Path(tmp) / "report.md"),
                "--skip-vector-preflight",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                cre, "http_get_json", side_effect=fake_get
            ), mock.patch.object(
                cre, "write_regression_diagnostics", side_effect=fake_diagnostics
            ):
                exit_code = cre.main()

            summary = json.loads((run_dir / "summary.json").read_text())

        self.assertEqual(exit_code, 0)
        row = summary["rows"][0]
        self.assertEqual(row["group"], "negative")
        self.assertEqual(row["status"], "improved")
        self.assertEqual(row["diff"]["top1_score_baseline"], 0.7)
        self.assertIsNone(row["diff"]["top1_score_candidate"])

    def test_main_writes_failure_artifact_when_recall_times_out(self):
        scenario = {
            "description": "timeout fixture",
            "queries": [
                {
                    "id": "Q-TIMEOUT",
                    "group": "preserve",
                    "description": "timeout should be captured",
                    "query": "slow query",
                    "params": {},
                }
            ],
        }
        baseline_summary = {
            "candidate_endpoint": "saved baseline",
            "candidate_health": {
                "status": "healthy",
                "memory_count": 1,
                "vector_count": 1,
            },
            "rows": [
                {
                    "id": "Q-TIMEOUT",
                    "candidate": {
                        "count": 1,
                        "returned": 1,
                        "top_ids": ["m1"],
                        "top": [],
                    },
                }
            ],
        }

        def fake_get(endpoint, token, path, params=None):
            return {"status": "healthy", "memory_count": 1, "vector_count": 1}

        with tempfile.TemporaryDirectory() as tmp:
            scenario_path = Path(tmp) / "scenario.json"
            scenario_path.write_text(json.dumps(scenario))
            baseline_path = Path(tmp) / "baseline-summary.json"
            baseline_path.write_text(json.dumps(baseline_summary))
            run_dir = Path(tmp) / "run"
            argv = [
                "compare_recall_endpoints.py",
                "--scenario",
                str(scenario_path),
                "--baseline-summary",
                str(baseline_path),
                "--candidate-endpoint",
                "http://localhost:8012",
                "--run-dir",
                str(run_dir),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                cre, "http_get_json", side_effect=fake_get
            ), mock.patch.object(cre, "recall", side_effect=TimeoutError("timed out")):
                exit_code = cre.main()

            failure = json.loads((run_dir / "comparison-failed.json").read_text())

        self.assertEqual(exit_code, 2)
        self.assertEqual(failure["query_id"], "Q-TIMEOUT")
        self.assertEqual(failure["error_type"], "TimeoutError")
        self.assertEqual(failure["rows_completed"], 0)

    def test_fail_on_preserve_regression_exits_nonzero_for_top_five_churn(self):
        scenario = {
            "description": "preserve top five churn fixture",
            "queries": [
                {
                    "id": "PRESERVE-REGRESSION",
                    "group": "preserve",
                    "description": "top five churn should fail default regression gate",
                    "query": "what changed",
                    "params": {},
                }
            ],
        }

        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 2, "vector_count": 2}
            if endpoint.endswith("1"):
                return {
                    "count": 2,
                    "results": [
                        {"id": "same-top", "score_components": {"vector": 0.9}},
                        {"id": "lost", "score_components": {"vector": 0.8}},
                    ],
                }
            return {
                "count": 2,
                "results": [
                    {"id": "same-top", "score_components": {"vector": 0.9}},
                    {"id": "gained", "score_components": {"vector": 0.8}},
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            scenario_path = Path(tmp) / "scenario.json"
            scenario_path.write_text(json.dumps(scenario))
            run_dir = Path(tmp) / "run"

            def fake_diagnostics(**kwargs):
                diagnostics_path = (
                    run_dir / "diagnostics" / f"{kwargs['row']['id']}.json"
                )
                diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
                diagnostics_path.write_text("{}")
                return diagnostics_path

            argv = [
                "compare_recall_endpoints.py",
                "--scenario",
                str(scenario_path),
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
                "--run-dir",
                str(run_dir),
                "--report",
                str(Path(tmp) / "report.md"),
                "--fail-on-preserve-regression",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                cre, "http_get_json", side_effect=fake_get
            ), mock.patch.object(
                cre, "write_regression_diagnostics", side_effect=fake_diagnostics
            ):
                exit_code = cre.main()

        self.assertEqual(exit_code, 1)

    def test_fail_on_preserve_review_exits_nonzero_for_review_status(self):
        scenario = {
            "description": "strict preserve review fixture",
            "queries": [
                {
                    "id": "PRESERVE-REVIEW",
                    "group": "preserve",
                    "description": "review should fail strict gate",
                    "query": "what changed",
                    "params": {},
                }
            ],
        }

        def fake_get(endpoint, token, path, params=None):
            if path == "/health":
                return {"status": "healthy", "memory_count": 5, "vector_count": 5}
            if endpoint.endswith("1"):
                return {
                    "count": 5,
                    "results": [
                        {
                            "id": "a",
                            "final_score": 0.6315270934615385,
                            "score_components": {"vector": 0.9},
                        },
                        {
                            "id": "b",
                            "final_score": 0.6315239246153846,
                            "score_components": {"vector": 0.8},
                        },
                        {
                            "id": "c",
                            "final_score": 0.59,
                            "score_components": {"vector": 0.7},
                        },
                        {
                            "id": "d",
                            "final_score": 0.58,
                            "score_components": {"vector": 0.6},
                        },
                        {
                            "id": "e",
                            "final_score": 0.57,
                            "score_components": {"vector": 0.5},
                        },
                    ],
                }
            return {
                "count": 5,
                "results": [
                    {
                        "id": "b",
                        "final_score": 0.6317135896153846,
                        "score_components": {"vector": 0.9},
                    },
                    {
                        "id": "a",
                        "final_score": 0.6316897734615384,
                        "score_components": {"vector": 0.8},
                    },
                    {
                        "id": "c",
                        "final_score": 0.59,
                        "score_components": {"vector": 0.7},
                    },
                    {
                        "id": "d",
                        "final_score": 0.58,
                        "score_components": {"vector": 0.6},
                    },
                    {
                        "id": "e",
                        "final_score": 0.57,
                        "score_components": {"vector": 0.5},
                    },
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            scenario_path = Path(tmp) / "scenario.json"
            scenario_path.write_text(json.dumps(scenario))
            run_dir = Path(tmp) / "run"

            def fake_diagnostics(**kwargs):
                diagnostics_path = (
                    run_dir / "diagnostics" / f"{kwargs['row']['id']}.json"
                )
                diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
                diagnostics_path.write_text("{}")
                return diagnostics_path

            argv = [
                "compare_recall_endpoints.py",
                "--scenario",
                str(scenario_path),
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
                "--run-dir",
                str(run_dir),
                "--report",
                str(Path(tmp) / "report.md"),
                "--fail-on-preserve-review",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                cre, "http_get_json", side_effect=fake_get
            ), mock.patch.object(
                cre, "write_regression_diagnostics", side_effect=fake_diagnostics
            ):
                exit_code = cre.main()

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
