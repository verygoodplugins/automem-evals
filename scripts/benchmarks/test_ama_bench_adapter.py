#!/usr/bin/env python3
"""Protocol-level tests for the AMA-Bench AutoMem adapter (stdlib only)."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "scripts" / "benchmarks" / "ama_bench_adapter.py"


class _Server(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.memories: dict[str, dict] = {}
        self.posts: list[dict] = []
        self.deletes: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/memory":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.posts.append(body)
        memory_id = f"m{len(self.server.posts)}"
        self.server.memories[memory_id] = body
        self._send({"memory_id": memory_id})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/recall":
            self.send_error(404)
            return
        tag = parse_qs(parsed.query).get("tags", [""])[0]
        results = [
            {"id": memory_id, "memory": {"content": item["content"]}}
            for memory_id, item in self.server.memories.items()
            if tag in item.get("tags", [])
        ]
        self._send({"results": results})

    def do_DELETE(self) -> None:  # noqa: N802
        memory_id = self.path.rsplit("/", 1)[-1]
        self.server.deletes.append(memory_id)
        self.server.memories.pop(memory_id, None)
        self._send({"ok": True})


class AutoMemAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "src" / "method").mkdir(parents=True)
        (root / "src" / "__init__.py").touch()
        (root / "src" / "method" / "__init__.py").touch()
        (root / "src" / "method" / "base_method.py").write_text(
            "from abc import ABC\nclass BaseMethod(ABC):\n"
            "    @staticmethod\n    def _load_config(path):\n"
            "        import json\n        return json.load(open(path))\n",
            encoding="utf-8",
        )
        shutil.copy2(ADAPTER, root / "src" / "method" / "automem.py")
        sys.path.insert(0, str(root))
        for name in list(sys.modules):
            if name == "src" or name.startswith("src."):
                del sys.modules[name]
        self.module = importlib.import_module("src.method.automem")
        self.server = _Server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        sys.path.remove(self.temp.name)
        self.temp.cleanup()

    def test_store_recall_and_between_trajectory_cleanup(self) -> None:
        state = Path(self.temp.name) / "state.json"
        method = self.module.AutoMemMethod(
            endpoint=f"http://127.0.0.1:{self.server.server_port}",
            token="test-token",
            chunk_chars=256,
            state_file=str(state),
        )
        first = method.memory_construction("First trajectory stores the blue widget.", "Find widgets")
        self.assertEqual(len(first.memory_ids), 1)
        self.assertEqual(self.server.posts[0]["tags"], ["ama-bench-eval"])
        self.assertEqual(self.server.posts[0]["importance"], 0.7)
        self.assertIn("blue widget", method.memory_retrieve(first, "What color is the widget?"))
        second = method.memory_construction("Second trajectory stores the red valve.")
        self.assertEqual(self.server.deletes, ["m1"])
        self.assertEqual(len(second.memory_ids), 1)
        self.assertEqual(json.loads(state.read_text())["memory_ids"], ["m2"])
        method.cleanup()
        self.assertEqual(self.server.deletes, ["m1", "m2"])
        self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
