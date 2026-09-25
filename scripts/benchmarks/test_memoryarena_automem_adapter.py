"""Contract tests for the MemoryArena-to-AutoMem smoke adapter."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memoryarena_automem_adapter import AutoMemMemorySystem


class _RecordingHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, format, *args):  # noqa: A002 - silence test server
        return

    def _send_json(self, status, body):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):  # noqa: N802 - stdlib hook name
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        self.requests.append(("POST", self.path, dict(self.headers), body))
        self._send_json(201, {"memory_id": "memory-1"})

    def do_GET(self):  # noqa: N802 - stdlib hook name
        self.requests.append(("GET", self.path, dict(self.headers), None))
        self._send_json(
            200,
            {
                "results": [
                    {"memory": {"content": "Earlier traveler prefers rail."}},
                    {"content": "Budget is 500 euros."},
                ]
            },
        )


class AutoMemMemorySystemTests(unittest.TestCase):
    def setUp(self):
        _RecordingHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_add_and_wrap_use_a_user_scoped_automem_protocol(self):
        memory = AutoMemMemorySystem(
            user_id="group-17",
            endpoint=self.endpoint,
            token="smoke-token",
            benchmark_tag="memoryarena-smoke",
        )

        stored = memory.add_chunk("Traveler A prefers rail over flights.")
        wrapped = memory.wrap_user_prompt("Plan traveler B's trip.")

        self.assertEqual(stored["memory_id"], "memory-1")
        self.assertIn("<memory_context>", wrapped)
        self.assertIn("Earlier traveler prefers rail.", wrapped)
        self.assertIn("Budget is 500 euros.", wrapped)
        self.assertTrue(wrapped.endswith("User Prompt: Plan traveler B's trip."))

        post = _RecordingHandler.requests[0]
        self.assertEqual(post[0:2], ("POST", "/memory"))
        self.assertEqual(post[2]["Authorization"], "Bearer smoke-token")
        self.assertEqual(post[3]["tags"], ["memoryarena-smoke", "memoryarena", "user-group-17"])
        self.assertEqual(post[3]["metadata"]["memoryarena_user_id"], "group-17")

        get = _RecordingHandler.requests[1]
        self.assertEqual(get[0], "GET")
        self.assertIn("query=Plan+traveler+B%27s+trip.", get[1])
        self.assertIn("tags=memoryarena-smoke", get[1])
        self.assertIn("tags=user-group-17", get[1])

    def test_empty_chunks_do_not_call_automem(self):
        memory = AutoMemMemorySystem(user_id="empty", endpoint=self.endpoint, token="token")

        self.assertIsNone(memory.add_chunk("  \n"))
        self.assertEqual(_RecordingHandler.requests, [])


if __name__ == "__main__":
    unittest.main()
