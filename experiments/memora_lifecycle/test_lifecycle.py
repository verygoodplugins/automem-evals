"""Deterministic fixture and safety checks; no Docker or external services."""

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts/benchmarks"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A local stub keeps these tests stdlib-only; the real vector model is only
# initialized when a live diagnostic explicitly calls embedding().
sys.modules.setdefault("fastembed", types.SimpleNamespace(TextEmbedding=object))
scenario = load("memora_lifecycle_scenario", HERE / "scenario.py")
runner = load("memora_lifecycle_runner", HERE / "run.py")


class LifecycleFixtureTest(unittest.TestCase):
    def setUp(self):
        scenario.requests.clear()

    def test_session_preserves_explicit_predecessor(self):
        row = scenario.session(2, "update", "new name", "new value", old_item="old name")
        self.assertEqual(row["operation_details"], {"item": "new name", "old_item": "old name"})
        self.assertEqual(row["date"], "2025-06-02")
        self.assertTrue(row["conversation"][0]["share_memory"])

    def test_inline_distinguishes_absent_redacted_and_visible(self):
        rows = [
            {
                "id": "parent",
                "relations": [
                    {"memory": {"id": "redacted"}},
                    {"memory": {"id": "visible", "content": "fact"}},
                ],
            }
        ]
        self.assertIsNone(scenario.has_inline_content(rows, "parent", "missing"))
        self.assertFalse(scenario.has_inline_content(rows, "parent", "redacted"))
        self.assertTrue(scenario.has_inline_content(rows, "parent", "visible"))

    def test_audited_transport_injects_local_store_and_query_vectors(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append((args, kwargs))
            return {"qdrant": "stored"}

        with patch.object(scenario, "embedding", return_value=[0.1, 0.2]), patch.object(
            scenario, "_json_request", side_effect=fake
        ):
            scenario.audited(
                "http://isolated",
                "fixture",
                "POST",
                "/memory",
                body={"content": "fact"},
            )
            scenario.audited(
                "http://isolated",
                "fixture",
                "GET",
                "/recall",
                params={"query": "fact", "limit": 5},
            )
        self.assertEqual(calls[0][1]["body"]["embedding"], [0.1, 0.2])
        self.assertEqual(calls[1][1]["params"]["embedding"], "0.1,0.2")
        self.assertEqual(scenario.requests[0]["vector_storage"], "stored")
        self.assertTrue(all(event["outcome"] == "ok" for event in scenario.requests))

    def test_audited_transport_records_errors_before_raising(self):
        with patch.object(scenario, "_json_request", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                scenario.audited("http://isolated", "fixture", "PATCH", "/memory/synthetic")
        self.assertEqual(scenario.requests[0]["path_class"], "/memory/:id")
        self.assertEqual(scenario.requests[0]["outcome"], "error")

    def test_negative_result_is_not_misreported_as_pass(self):
        result = scenario.check("negative_abstains", False, "unrelated evidence", returned_count=1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failure_cause"], "unrelated evidence")

    def test_stack_is_internal_and_has_no_published_ports_or_paid_provider(self):
        text = (HERE / "compose.yaml").read_text()
        self.assertIn("internal: true", text)
        self.assertNotIn("ports:", text)
        self.assertIn('OPENAI_API_KEY: ""', text)
        self.assertIn('VOYAGE_API_KEY: ""', text)
        self.assertIn('HF_HUB_OFFLINE: "1"', text)

    def test_log_audit_catches_hidden_graph_timeout(self):
        self.assertTrue(
            runner.ERROR_PATTERN.search("Failed to load current-state replacements for 100 memories")
        )
        self.assertTrue(runner.ERROR_PATTERN.search("redis.exceptions.ResponseError: Query timed out"))
        self.assertFalse(runner.ERROR_PATTERN.search("diagnostic completed successfully"))

    def test_committed_source_check_rejects_dirty_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = pathlib.Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            path = repo / "fixture.py"
            path.write_text("original\n")
            subprocess.run(["git", "-C", str(repo), "add", "fixture.py"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                check=True,
            )
            runner.require_committed(repo, "HEAD", [path])
            path.write_text("modified\n")
            with self.assertRaisesRegex(ValueError, "source differs"):
                runner.require_committed(repo, "HEAD", [path])


if __name__ == "__main__":
    unittest.main()
