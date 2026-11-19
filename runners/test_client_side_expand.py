import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client_side_expand as cse


class ClientSideExpandArgsTests(unittest.TestCase):
    def test_defaults_match_module_constants(self):
        args = cse.parse_args([])
        self.assertEqual(args.endpoint, cse.ENDPOINT)
        self.assertEqual(args.token, cse.TOKEN)
        self.assertEqual(cse.resolve_manifest(args.manifest), cse.MANIFEST)

    def test_endpoint_token_manifest_overrides(self):
        args = cse.parse_args([
            "--endpoint", "http://localhost:8311",
            "--token", "t",
            "--manifest", "corpus_v1-8311.manifest.json",
        ])
        self.assertEqual(args.endpoint, "http://localhost:8311")
        self.assertEqual(args.token, "t")
        self.assertEqual(
            cse.resolve_manifest(args.manifest),
            cse.HERE / "data" / "seed_memories" / "corpus_v1-8311.manifest.json",
        )

    def test_explicit_manifest_path_is_preserved(self):
        self.assertEqual(
            cse.resolve_manifest("/tmp/x.manifest.json"), Path("/tmp/x.manifest.json")
        )

    def test_run_phase2_uses_given_endpoint_and_token(self):
        ruleset = {"phase_2_task_context": {"limit": 5, "time_query": "last 90 days"}}
        scenario = {"query": "q", "project_slug": "tensor-pipeline"}
        with mock.patch.object(cse, "http", return_value={"results": []}) as http:
            cse.run_phase2("http://localhost:8311", "t", ruleset, scenario)
        method, url, token, params = http.call_args.args
        self.assertEqual(url, "http://localhost:8311/recall")
        self.assertEqual(token, "t")
        self.assertEqual(params["time_query"], "last 90 days")


if __name__ == "__main__":
    unittest.main()
