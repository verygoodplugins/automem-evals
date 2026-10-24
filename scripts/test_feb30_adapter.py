"""Release gating and direct store inspection; no synthetic FEB-30 score."""
import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

spec = importlib.util.spec_from_file_location(
    "feb30_adapter", Path(__file__).parent / "benchmarks/feb30_adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class Feb30Tests(unittest.TestCase):
    def test_real_loopback_ignores_proxy_and_refuses_redirect(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://example.com/")
                else:
                    self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"t_invalid": "retained"}).encode())

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            origin = "http://127.0.0.1:" + str(server.server_port)
            try:
                with patch.dict("os.environ", {"http_proxy": "http://127.0.0.1:1", "no_proxy": ""}):
                    self.assertEqual(adapter.request(origin)["t_invalid"], "retained")
                    with self.assertRaises(HTTPError) as error:
                        adapter.request(origin + "/redirect")
                    self.assertEqual(error.exception.code, 302)
            finally:
                server.shutdown()
                thread.join()

    def test_refuses_remote_and_ambiguous_origins(self):
        for endpoint in ("https://127.0.0.1", "http://example.com", "http://localhost",
                         "http://127.0.0.1@evil.test", "http://127.0.0.1/path",
                         "http://127.0.0.1?proxy=1"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                adapter.StoreInspector(endpoint, "test-token", "feb30-run-test")

    def test_snapshots_history_without_recall_filtering(self):
        backend = adapter.StoreInspector("http://127.0.0.1:18031", "test-token", "feb30-run-test")
        with patch.object(adapter, "request", side_effect=[
                {"memory_id": "old"}, {"id": "new"},
                {"id": "old", "t_invalid": "2026-10-24T00:00:00Z"},
                {"id": "new"}]) as http:
            backend.ingest_document("Original document")
            backend.ingest_document("Revised document")
            state = backend.snapshot()
        self.assertIsNotNone(state["old"]["t_invalid"])
        self.assertEqual(set(state), {"old", "new"})
        self.assertEqual(http.call_args_list[2].args[0], "http://127.0.0.1:18031/memory/old")
        self.assertNotIn("supersedes_memory_id", http.call_args_list[1].args[2])

    def test_blocked_release_does_not_emit_scores(self):
        error = HTTPError("release", 404, "Not Found", {}, BytesIO(b'{"message":"Not Found"}'))
        with patch.object(adapter, "request", side_effect=error):
            report = adapter.release_preflight()
        self.assertEqual(report["release_probe"]["status"], 404)
        self.assertIn("Not Found", report["release_probe"]["body"])
        self.assertFalse(report["automem_executed"])
        self.assertIsNone(report["intrinsic"])
        self.assertIsNone(report["extrinsic_qa"])

    def test_accessible_repository_still_requires_verified_pin_and_loader(self):
        with patch.object(adapter, "request", return_value={"default_branch": "main"}):
            self.assertEqual(adapter.release_preflight()["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
