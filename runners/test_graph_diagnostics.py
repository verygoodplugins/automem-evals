import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import graph_diagnostics as gd


class EndpointGuardTests(unittest.TestCase):
    def test_local_endpoints_allowed(self):
        self.assertTrue(gd.is_local_endpoint("http://localhost:8001"))
        self.assertTrue(gd.is_local_endpoint("http://127.0.0.1:8011"))
        self.assertTrue(gd.is_local_endpoint("https://[::1]:8001"))

    def test_remote_endpoint_rejected(self):
        self.assertFalse(gd.is_local_endpoint("https://automem.example.com"))


class ParsingTests(unittest.TestCase):
    def test_parse_label_value(self):
        self.assertEqual(gd.parse_label_value("full=http://localhost:8001"), ("full", "http://localhost:8001"))

    def test_parse_label_value_rejects_missing_equals(self):
        with self.assertRaises(Exception):
            gd.parse_label_value("localhost:8001")

    def test_parse_thresholds(self):
        self.assertEqual(gd.parse_thresholds("0.55, 0.65,0.75"), [0.55, 0.65, 0.75])


class RelationshipClassificationTests(unittest.TestCase):
    def test_classifies_system_authorable_and_unknown_edges(self):
        self.assertEqual(gd.classify_relationship("PRECEDED_BY"), "system")
        self.assertEqual(gd.classify_relationship("INVALIDATED_BY"), "authorable")
        self.assertEqual(gd.classify_relationship("CUSTOM_EDGE"), "unknown")


class GraphShapeTests(unittest.TestCase):
    def test_summarize_graph_shape_computes_percentages(self):
        stats = {
            "totals": {"nodes": 10, "edges": 100},
            "by_type": {"Memory": 6, "Decision": 4},
            "by_relationship": {
                "PRECEDED_BY": 40,
                "SIMILAR_TO": 20,
                "DISCOVERED": 5,
                "PARALLEL_CONTEXT": 10,
                "SUMMARIZES": 5,
                "INVALIDATED_BY": 3,
                "PREFERS_OVER": 2,
                "RELATES_TO": 10,
                "CUSTOM": 5,
            },
        }
        shape = gd.summarize_graph_shape(stats)
        self.assertEqual(shape["total_nodes"], 10)
        self.assertEqual(shape["total_edges"], 100)
        self.assertAlmostEqual(shape["system_edge_share"], 0.80)
        self.assertAlmostEqual(shape["author_edge_share"], 0.15)
        self.assertAlmostEqual(shape["generic_memory_share"], 0.60)
        self.assertEqual(shape["supersession_edges"], 5)
        self.assertAlmostEqual(shape["legacy_discovered_share"], 10 / 15)

    def test_graph_shape_risks_include_deep_probe_parallel_zero_similarity(self):
        stats = {
            "totals": {"nodes": 1000, "edges": 1000},
            "by_type": {"Memory": 700},
            "by_relationship": {"PRECEDED_BY": 900, "INVALIDATED_BY": 1, "PREFERS_OVER": 0},
        }
        shape = gd.summarize_graph_shape(stats)
        deep_probe = {
            "legacy_relation_similarity": {
                "PARALLEL_CONTEXT": {"count": 100, "zero_similarity_share": 1}
            }
        }
        risks = gd.graph_shape_risks(shape, deep_probe)
        self.assertIn("high generic Memory type share", risks)
        self.assertIn("system-generated edges dominate the graph", risks)
        self.assertIn("INVALIDATED_BY/PREFERS_OVER barely fire", risks)
        self.assertIn("legacy PARALLEL_CONTEXT similarities are all zero", risks)


class ThresholdEvidenceTests(unittest.TestCase):
    def test_threshold_evidence_reports_lift_without_recommending_patch(self):
        evidence = gd.threshold_evidence(
            {
                "threshold_probe": {
                    "top1_similarity": {"p50": 0.82},
                    "top_k_neighbor_edges_at_thresholds": {
                        "0.65": 150,
                        "0.75": 100,
                    },
                }
            }
        )
        self.assertEqual(evidence["status"], "measured")
        self.assertIn("0.75 still returns 100", evidence["summary"])
        self.assertIn("50.0% more", evidence["summary"])

    def test_threshold_evidence_marks_no_hits_at_075_as_supporting_lowering(self):
        evidence = gd.threshold_evidence(
            {
                "threshold_probe": {
                    "top_k_neighbor_edges_at_thresholds": {
                        "0.65": 25,
                        "0.75": 0,
                    }
                }
            }
        )
        self.assertEqual(evidence["status"], "supports-lowering")


class DockerCommandTests(unittest.TestCase):
    def test_build_docker_exec_command(self):
        self.assertEqual(
            gd.build_docker_exec_command("automem-flask-api-1"),
            ["docker", "exec", "-i", "automem-flask-api-1", "python", "-"],
        )


class SourceInspectionTests(unittest.TestCase):
    def test_inspect_source_hypotheses_confirms_expected_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "automem" / "consolidation").mkdir(parents=True)
            (root / "consolidation.py").write_text(
                "self.min_cluster_size = 3\nself.similarity_threshold = 0.75\n"
            )
            (root / "automem" / "config.py").write_text(
                'CONSOLIDATION_CLUSTER_INTERVAL_SECONDS = int(os.getenv("CONSOLIDATION_CLUSTER_INTERVAL_SECONDS", str(2592000)))\n'
            )
            (root / "automem" / "consolidation" / "runtime_scheduler.py").write_text(
                "state.consolidation_thread.start()\nrun_consolidation_tick_fn()\n"
            )

            result = gd.inspect_source_hypotheses(root)
            statuses = {k: v["status"] for k, v in result["hypotheses"].items()}
            self.assertEqual(
                statuses,
                {
                    "hardcoded_similarity_threshold": "confirmed",
                    "hardcoded_min_cluster_size": "confirmed",
                    "cluster_interval_default_30d": "confirmed",
                    "eager_scheduler_tick": "confirmed",
                },
            )


class MarkdownReportTests(unittest.TestCase):
    def test_write_markdown_report_contains_claims_and_thresholds(self):
        analyses = {
            "full": {
                "endpoint": "http://localhost:8001",
                "health": {"status": "healthy", "memory_count": 10, "vector_count": 10, "sync_status": "synced"},
                "shape": gd.summarize_graph_shape(
                    {
                        "totals": {"nodes": 10, "edges": 100},
                        "by_type": {"Memory": 5},
                        "by_relationship": {"PRECEDED_BY": 40, "INVALIDATED_BY": 1, "PREFERS_OVER": 0},
                    }
                ),
                "deep_probe": {
                    "threshold_probe": {
                        "top_k_neighbor_edges_at_thresholds": {"0.65": 2, "0.75": 1}
                    }
                },
                "risks": ["example risk"],
            }
        }
        source = {"status": "skipped", "reason": "test"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            gd.write_markdown_report(
                path,
                generated_at="2026-05-01T00:00:00",
                run_dir=Path("data/sweep_runs/test"),
                analyses=analyses,
                source=source,
            )
            text = path.read_text()
            self.assertIn("Exchange Claims", text)
            self.assertIn("Threshold Evidence", text)
            self.assertIn("0.75 still returns 1", text)


if __name__ == "__main__":
    unittest.main()
