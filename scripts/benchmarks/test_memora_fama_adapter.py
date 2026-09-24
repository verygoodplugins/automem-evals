"""Contract tests for the Memora Track 2 AutoMem adapter."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from memora_fama_adapter import AutoMemFamaSystem, ingest


class RecordingAutoMem:
    """Small transport fake that records the MCP client's HTTP orchestration."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []
        self.next_id = 1

    def request(
        self,
        _endpoint: str,
        _token: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        del timeout
        self.calls.append((method, path, params, body))
        if path == "/health":
            return {"status": "healthy"}
        if method == "POST" and path == "/memory":
            memory_id = f"memory-{self.next_id}"
            self.next_id += 1
            return {"memory_id": memory_id}
        if method == "GET" and path == "/recall":
            return {"results": [{"memory_id": "memory-2", "memory": {"content": "Current fact"}, "final_score": 0.9}]}
        return {"status": "success"}


def conversation(operation: str, date: str, message: str) -> dict[str, Any]:
    return {
        "session_id": 1,
        "date": date,
        "operation": operation,
        "operation_details": {"item": "favorite editor"},
        "conversation": [
            {"speaker": "user_agent", "message": message, "share_memory": True}
        ],
    }


class AutoMemFamaSystemTest(unittest.TestCase):
    def test_ingest_orders_unpadded_session_filenames_numerically(self) -> None:
        class RecordingSystem:
            seen: list[str] = []

            def process_conversation_file(self, path: str) -> dict[str, str]:
                self.seen.append(pathlib.Path(path).name)
                return {"status": "stored"}

        with tempfile.TemporaryDirectory() as temporary_directory:
            conversations = pathlib.Path(temporary_directory)
            for name in ("session_10.json", "session_2.json", "session_1.json"):
                (conversations / name).write_text("{}", encoding="utf-8")
            system = RecordingSystem()
            outcomes = ingest(system, conversations)

        self.assertEqual(system.seen, ["session_1.json", "session_2.json", "session_10.json"])
        self.assertEqual(outcomes["stored"], 3)

    def test_updates_supersede_previous_fact_and_searches_current_state(self) -> None:
        transport = RecordingAutoMem()
        subject = AutoMemFamaSystem(
            "software_engineer_weekly",
            request_json=transport.request,
        )

        subject.add_conversation_to_memory(
            conversation("add", "2025-06-01", "My favorite editor is Vim.")
        )
        subject.add_conversation_to_memory(
            conversation("update", "2025-06-02", "My favorite editor is now Zed.")
        )
        memories = subject.search_memories("What is my favorite editor?")

        self.assertEqual(subject.client.store_calls[1]["supersedes_memory_id"], "memory-1")
        self.assertEqual(subject.client.store_calls[1]["supersede_relation"], "EVOLVED_INTO")
        self.assertIn(
            ("PATCH", "/memory/memory-1", None, {"t_invalid": "2025-06-02T00:00:00+00:00"}),
            transport.calls,
        )
        self.assertIn(
            ("POST", "/associate", None, {"memory1_id": "memory-1", "memory2_id": "memory-2", "type": "EVOLVED_INTO", "strength": 1.0}),
            transport.calls,
        )
        recall_call = next(call for call in transport.calls if call[1] == "/recall")
        self.assertEqual(recall_call[2]["current_only"], True)
        self.assertEqual(memories, [{"memory": "Current fact", "score": 0.9, "memory_id": "memory-2"}])

    def test_deletes_invalidate_the_current_fact_without_storing_a_tombstone(self) -> None:
        transport = RecordingAutoMem()
        subject = AutoMemFamaSystem("software_engineer_weekly", request_json=transport.request)

        subject.add_conversation_to_memory(
            conversation("add", "2025-06-01", "My favorite editor is Vim.")
        )
        result = subject.add_conversation_to_memory(
            conversation("delete", "2025-06-03", "I no longer use Vim.")
        )

        self.assertEqual(result["status"], "invalidated")
        self.assertEqual(len(subject.client.store_calls), 1)
        self.assertIn(
            ("PATCH", "/memory/memory-1", None, {"t_invalid": "2025-06-03T00:00:00+00:00"}),
            transport.calls,
        )


if __name__ == "__main__":
    unittest.main()
