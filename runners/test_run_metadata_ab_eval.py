import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_metadata_ab_eval as evaluator


class MetadataEvaluatorTests(unittest.TestCase):
    def test_local_endpoint_guard(self):
        self.assertTrue(evaluator.is_local_endpoint("http://localhost:8011"))
        self.assertTrue(evaluator.is_local_endpoint("http://127.0.0.1:8012"))
        self.assertFalse(evaluator.is_local_endpoint("https://automem.example.com"))

    def test_rank_expected_ids_finds_first_rank(self):
        response = {
            "results": [
                {"id": "a"},
                {"memory": {"id": "target-2"}},
                {"id": "target-1"},
            ]
        }
        rank, found = evaluator.rank_expected_ids(response, {"target-1", "target-2"})
        self.assertEqual(rank, 2)
        self.assertEqual(found, ["target-2", "target-1"])

    def test_score_pair_computes_hit_mrr_and_gain_loss(self):
        scenario = {
            "id": "S1",
            "expected_field": "source_agent",
            "expected_ids": ["target"],
        }
        baseline = {"results": [{"id": "noise"}, {"id": "target"}]}
        candidate = {"results": [{"id": "target"}, {"id": "noise"}]}

        row = evaluator.score_pair(scenario, baseline, candidate)

        self.assertEqual(row["baseline"]["rank"], 2)
        self.assertEqual(row["candidate"]["rank"], 1)
        self.assertTrue(row["candidate"]["hit_at_1"])
        self.assertEqual(row["rank_delta"], -1)
        self.assertEqual(row["gained_ids"], [])
        self.assertEqual(row["lost_ids"], [])

    def test_score_pair_tracks_top10_gain_and_loss(self):
        scenario = {"id": "S1", "expected_field": "tool", "expected_ids": ["target"]}
        baseline = {"results": [{"id": f"n{i}"} for i in range(10)]}
        candidate = {"results": [{"id": "target"}]}

        row = evaluator.score_pair(scenario, baseline, candidate)

        self.assertEqual(row["gained_ids"], ["target"])
        self.assertEqual(row["lost_ids"], [])

    def test_aggregate_rows_reports_rates_and_per_field_deltas(self):
        rows = [
            {
                "expected_field": "source_agent",
                "baseline": {"hit_at_5": False, "mrr": 0.0, "rank": None},
                "candidate": {"hit_at_5": True, "mrr": 1.0, "rank": 1},
                "rank_delta": None,
                "gained_ids": ["a"],
                "lost_ids": [],
            },
            {
                "expected_field": "source_agent",
                "baseline": {"hit_at_5": True, "mrr": 0.5, "rank": 2},
                "candidate": {"hit_at_5": True, "mrr": 0.5, "rank": 2},
                "rank_delta": 0,
                "gained_ids": [],
                "lost_ids": [],
            },
        ]

        aggregate = evaluator.aggregate_rows(rows)

        self.assertEqual(aggregate["scenario_count"], 2)
        self.assertEqual(aggregate["baseline"]["hit_at_5"], 0.5)
        self.assertEqual(aggregate["candidate"]["hit_at_5"], 1.0)
        self.assertEqual(aggregate["gained_expected_id_count"], 1)
        self.assertEqual(aggregate["per_field"]["source_agent"]["hit_at_5_delta"], 0.5)

    def test_load_warmup_queries_uses_unscored_scenario_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            path.write_text(
                '{"warmup_queries":[{"id":"WARMUP-001","query":"ordinary content","params":{"limit":5}}],"scenarios":[]}'
            )

            rows = evaluator.load_warmup_queries(path)

        self.assertEqual(rows[0]["id"], "WARMUP-001")
        self.assertEqual(rows[0]["query"], "ordinary content")

    def test_merge_vector_preflight_preserves_transform_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vector_preflight.json"
            path.write_text('{"vectors_identical": true}')

            merged = evaluator.merge_vector_preflight(
                path, {"baseline": {"status": "ok"}, "candidate": {"status": "ok"}}
            )

        self.assertTrue(merged["transform"]["vectors_identical"])
        self.assertEqual(merged["recall_warmup"]["baseline"]["status"], "ok")

    def test_write_markdown_report_accepts_merged_vector_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            evaluator.write_markdown_report(
                path,
                baseline_endpoint="http://localhost:8011",
                candidate_endpoint="http://localhost:8012",
                run_label="metadata-sidecar-enabled",
                aggregate={
                    "baseline": {"hit_at_5": 0.0, "mrr": 0.0, "mean_target_rank": 0.0},
                    "candidate": {"hit_at_5": 1.0, "mrr": 1.0, "mean_target_rank": 1.0},
                    "hit_at_5_delta": 1.0,
                    "mrr_delta": 1.0,
                },
                rows=[],
                vector_preflight={
                    "transform": {"vectors_identical": True},
                    "recall_warmup": {
                        "baseline": {"status": "ok", "checked": 2, "nonzero_results": 5},
                        "candidate": {"status": "ok", "checked": 2, "nonzero_results": 6},
                    },
                },
            )

            report = path.read_text()

        self.assertIn("Run label: `metadata-sidecar-enabled`", report)
        self.assertIn("| baseline | ok | 2 | 5 |", report)
        self.assertIn("| candidate | ok | 2 | 6 |", report)


if __name__ == "__main__":
    unittest.main()
