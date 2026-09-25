from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


def load_adapter():
    path = Path(__file__).resolve().parent / "dolphinbench_adapter.py"
    spec = importlib.util.spec_from_file_location("dolphinbench_adapter", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class Recorder:
    def __init__(self):
        self.requests = []
        self.responses = [
            {"memory_id": "memory-1"},
            {"results": [{"memory": {"id": "memory-1", "content": "Use #eng-releases."}, "final_score": 0.91}]},
        ]

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return Response(self.responses.pop(0))


class DolphinBenchAutoMemAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter()

    def test_store_scopes_history_to_persona_and_preserves_narrative_time(self):
        recorder = Recorder()
        backend = self.adapter.AutoMemDolphinBenchBackend(
            "http://automem.test", "token", "dolphinbench-run-test", opener=recorder
        )

        memory_id = backend.store_memory(
            persona="morgan",
            content="Release notes stay in #eng-releases until green.",
            narrative_time="2023-04-25T09:00:00-07:00",
            source_message_id="000437",
        )

        self.assertEqual(memory_id, "memory-1")
        request, timeout = recorder.requests[0]
        self.assertEqual(timeout, 60)
        self.assertEqual(request.full_url, "http://automem.test/memory")
        body = json.loads(request.data)
        self.assertEqual(body["tags"], ["dolphinbench", "dolphinbench-run-test", "dolphinbench-persona-morgan"])
        self.assertEqual(body["timestamp"], "2023-04-25T09:00:00-07:00")
        self.assertEqual(body["metadata"]["source_message_id"], "000437")

    def test_recall_uses_full_scope_and_freeze_rejects_test_time_writes(self):
        recorder = Recorder()
        backend = self.adapter.AutoMemDolphinBenchBackend(
            "http://automem.test", "token", "dolphinbench-run-test", opener=recorder
        )
        backend.store_memory(
            persona="morgan", content="A remembered channel rule.",
            narrative_time="2023-04-25T09:00:00-07:00", source_message_id="000437",
        )

        results = backend.recall_memory(persona="morgan", query="Where should I post release notes?", limit=7)
        self.assertEqual(results[0].content, "Use #eng-releases.")
        self.assertIn("tags=dolphinbench", recorder.requests[1][0].full_url)
        self.assertIn("tags=dolphinbench-run-test", recorder.requests[1][0].full_url)
        self.assertIn("tags=dolphinbench-persona-morgan", recorder.requests[1][0].full_url)
        self.assertIn("tag_mode=all", recorder.requests[1][0].full_url)
        self.assertIn("tag_match=exact", recorder.requests[1][0].full_url)
        self.assertEqual(
            backend.freeze("morgan"),
            {"persona": "morgan", "scope_tag": "dolphinbench-run-test", "write_mode": "closed"},
        )
        with self.assertRaisesRegex(RuntimeError, "frozen"):
            backend.store_memory(
                persona="morgan", content="A prohibited test write.",
                narrative_time="2026-09-14T09:00:00-07:00", source_message_id="test-018",
            )


if __name__ == "__main__":
    unittest.main()
