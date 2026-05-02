import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_matrix as rm


class EndpointParsingTests(unittest.TestCase):
    def test_parse_endpoint_label_and_url(self):
        endpoint = rm.parse_endpoint("baseline=http://localhost:8001/")
        self.assertEqual(endpoint.label, "baseline")
        self.assertEqual(endpoint.url, "http://localhost:8001")

    def test_parse_endpoint_rejects_missing_label(self):
        with self.assertRaises(ValueError):
            rm.parse_endpoint("=http://localhost:8001")

    def test_parse_endpoint_rejects_relative_url(self):
        with self.assertRaises(ValueError):
            rm.parse_endpoint("baseline=localhost:8001")

    def test_parse_endpoints_rejects_duplicate_labels(self):
        with self.assertRaises(ValueError):
            rm.parse_endpoints(
                [
                    "baseline=http://localhost:8001",
                    "baseline=http://localhost:8011",
                ]
            )

    def test_local_endpoint_guard(self):
        self.assertTrue(rm.is_local_endpoint("http://localhost:8001"))
        self.assertTrue(rm.is_local_endpoint("http://127.0.0.1:8011"))
        self.assertFalse(rm.is_local_endpoint("https://automem.example.com"))


class TaskExpansionTests(unittest.TestCase):
    def test_build_tasks_cross_product(self):
        endpoints = [
            rm.EndpointSpec("baseline", "http://localhost:8001"),
            rm.EndpointSpec("atomic", "http://localhost:8011"),
        ]
        scenarios = [{"id": "S1", "phase": 1}, {"id": "S2", "phase": 2}]
        tasks = rm.build_tasks(
            endpoints,
            ["r1", "r2"],
            scenarios,
            {"baseline": "corpus_v1.manifest.json", "atomic": "atomic.manifest.json"},
        )
        self.assertEqual(len(tasks), 8)
        self.assertEqual(tasks[0].endpoint.label, "baseline")
        self.assertEqual(tasks[0].ruleset_name, "r1")
        self.assertEqual(tasks[0].scenario["id"], "S1")
        self.assertEqual(tasks[0].manifest_name, "corpus_v1.manifest.json")
        self.assertEqual(tasks[-1].endpoint.label, "atomic")
        self.assertEqual(tasks[-1].ruleset_name, "r2")
        self.assertEqual(tasks[-1].scenario["id"], "S2")
        self.assertEqual(tasks[-1].manifest_name, "atomic.manifest.json")


class ManifestConfigTests(unittest.TestCase):
    def test_resolve_manifest_names_defaults_and_overrides(self):
        endpoints = [
            rm.EndpointSpec("baseline", "http://localhost:8001"),
            rm.EndpointSpec("atomic", "http://localhost:8011"),
        ]
        names = rm.resolve_manifest_names(
            endpoints,
            "corpus_v1.manifest.json",
            ["atomic=atomic.manifest.json"],
        )
        self.assertEqual(
            names,
            {
                "baseline": "corpus_v1.manifest.json",
                "atomic": "atomic.manifest.json",
            },
        )

    def test_resolve_manifest_names_rejects_unknown_endpoint(self):
        endpoints = [rm.EndpointSpec("baseline", "http://localhost:8001")]
        with self.assertRaises(ValueError):
            rm.resolve_manifest_names(
                endpoints,
                "corpus_v1.manifest.json",
                ["missing=other.manifest.json"],
            )

    def test_validate_endpoint_manifest_reports_missing_ids(self):
        endpoint = rm.EndpointSpec("baseline", "http://localhost:8001")
        manifest = {"memory_to_scenarios": {"a": [], "b": [], "c": []}}
        original = rm.memory_exists
        try:
            rm.memory_exists = lambda _endpoint, _token, memory_id: memory_id != "b"
            check = rm.validate_endpoint_manifest(
                endpoint,
                "token",
                manifest,
                {"memory_count": 3},
            )
        finally:
            rm.memory_exists = original

        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["found_count"], 2)
        self.assertEqual(check["missing_count"], 1)
        self.assertEqual(check["missing_sample"], ["b"])

    def test_validate_endpoint_manifest_strict_count_fails_on_extra_memories(self):
        endpoint = rm.EndpointSpec("baseline", "http://localhost:8001")
        manifest = {"memory_to_scenarios": {"a": []}}
        original = rm.memory_exists
        try:
            rm.memory_exists = lambda _endpoint, _token, _memory_id: True
            check = rm.validate_endpoint_manifest(
                endpoint,
                "token",
                manifest,
                {"memory_count": 10},
                strict_memory_count=True,
            )
        finally:
            rm.memory_exists = original

        self.assertEqual(check["status"], "failed")
        self.assertIn("memory_count 10 != manifest count 1", check["problems"])


class AggregationTests(unittest.TestCase):
    def test_aggregate_results_groups_endpoint_ruleset_pairs(self):
        rows = [
            {
                "endpoint": "baseline",
                "ruleset": "r1",
                "status": "ok",
                "metrics": {
                    "expected_in_corpus": 4,
                    "hits_total": 2,
                    "precision_at_k": 0.2,
                    "rank_of_first_hit": 2,
                },
            },
            {
                "endpoint": "baseline",
                "ruleset": "r1",
                "status": "error",
                "metrics": {
                    "expected_in_corpus": 6,
                    "hits_total": 3,
                    "precision_at_k": 0.4,
                    "rank_of_first_hit": None,
                },
            },
            {
                "endpoint": "atomic",
                "ruleset": "r2",
                "status": "ok",
                "metrics": {
                    "expected_in_corpus": 5,
                    "hits_total": 5,
                    "precision_at_k": 1.0,
                    "rank_of_first_hit": 1,
                },
            },
        ]

        aggregate = rm.aggregate_results(rows)
        by_pair = {(row["endpoint"], row["ruleset"]): row for row in aggregate}

        baseline = by_pair[("baseline", "r1")]
        self.assertEqual(baseline["scenarios"], 2)
        self.assertEqual(baseline["errors"], 1)
        self.assertEqual(baseline["hits"], 5)
        self.assertEqual(baseline["expected"], 10)
        self.assertAlmostEqual(baseline["recall"], 0.5)
        self.assertAlmostEqual(baseline["mean_precision_at_5"], 0.3)
        self.assertEqual(baseline["mean_first_hit_rank"], 2)

        atomic = by_pair[("atomic", "r2")]
        self.assertEqual(atomic["errors"], 0)
        self.assertEqual(atomic["mean_first_hit_rank"], 1)


class MarkdownTests(unittest.TestCase):
    def test_display_path_allows_external_results_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.json"
            self.assertEqual(rm.display_path(path), str(path))

    def test_render_markdown_contains_aggregate_and_cell_rows(self):
        run = {
            "generated_at": "2026-05-02T00:00:00+00:00",
            "scenarios_name": "session_start_v1",
            "manifest_name": "corpus_v1.manifest.json",
            "json_path": "data/results/matrix/test.json",
            "endpoints": [
                {
                    "label": "baseline",
                    "url": "http://localhost:8001",
                    "manifest": "corpus_v1.manifest.json",
                }
            ],
            "health": {
                "baseline": {
                    "status": "healthy",
                    "memory_count": 78,
                    "vector_count": 78,
                    "sync_status": "synced",
                }
            },
            "manifest_checks": {
                "baseline": {
                    "status": "ok",
                    "missing_count": 0,
                }
            },
            "aggregate": [
                {
                    "endpoint": "baseline",
                    "ruleset": "r1",
                    "scenarios": 1,
                    "errors": 0,
                    "hits": 1,
                    "expected": 2,
                    "recall": 0.5,
                    "mean_precision_at_5": 0.2,
                    "mean_first_hit_rank": 3,
                }
            ],
            "rows": [
                {
                    "endpoint": "baseline",
                    "ruleset": "r1",
                    "scenario_id": "S1",
                    "status": "ok",
                    "error": None,
                    "metrics": {
                        "hits_total": 1,
                        "expected_in_corpus": 2,
                        "precision_at_k": 0.2,
                        "rank_of_first_hit": 3,
                    },
                }
            ],
        }

        text = rm.render_markdown(run)
        self.assertIn("## Aggregate", text)
        self.assertIn("| baseline | r1 | 1 | 0 | 1 | 2 | 0.500 | 0.200 | 3.00 |", text)
        self.assertIn("`baseline` / `r1` / `S1`", text)


if __name__ == "__main__":
    unittest.main()
