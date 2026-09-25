#!/usr/bin/env python3
"""AutoMem's memory-tool seam for a DolphinBench participant harness.

This module deliberately owns only the memory backend.  DolphinBench supplies
the history/test loops, simulated MCP applications, and graders; a participant
still supplies its agent loop and records its model usage.  Keeping that
boundary explicit prevents this protocol scaffold from being mistaken for a
benchmark run or score.

The two public methods retain AutoMem's normal tool names:

* ``store_memory`` is available only during history ingestion;
* ``recall_memory`` is available during ingestion and read-only tests.

Use a unique ``scope_tag`` for each DolphinBench configuration.  AutoMem tags
are hard filters, so the scope tag plus persona tag keeps three completed
persona stores and concurrent candidate runs from leaking into one another.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_ENDPOINT = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"
BENCHMARK_TAG = "dolphinbench"


class AutoMemHTTPError(RuntimeError):
    """A non-success response from the configured AutoMem service."""


def _persona_tag(persona: str) -> str:
    normalized = persona.strip().lower()
    if normalized not in {"alex", "morgan", "riley"}:
        raise ValueError("persona must be one of: alex, morgan, riley")
    return f"dolphinbench-persona-{normalized}"


@dataclass(frozen=True)
class RecallResult:
    """A compact, agent-facing representation of a recalled AutoMem memory."""

    memory_id: str
    content: str
    score: float | None


class AutoMemDolphinBenchBackend:
    """Small stdlib-only HTTP client for a DolphinBench memory integration.

    A harness invokes ``store_memory`` only when its ingestion agent decides a
    fact is worth storing.  Calling ``freeze`` after ingestion makes this
    backend reject later writes locally; the harness must also avoid exposing
    the write tool to its test-time agent.  This is the explicit guard required
    by DolphinBench's read-only completed-memory rule.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        token: str = DEFAULT_TOKEN,
        scope_tag: str = "dolphinbench-run-local",
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not scope_tag or any(char.isspace() for char in scope_tag):
            raise ValueError("scope_tag must be a non-empty tag without whitespace")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.scope_tag = scope_tag
        self._opener = opener
        self._frozen_personas: set[str] = set()

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "X-Api-Key": self.token}

    def _request(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise AutoMemHTTPError(f"AutoMem {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise AutoMemHTTPError(f"AutoMem request failed: {exc.reason}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AutoMemHTTPError("AutoMem returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AutoMemHTTPError("AutoMem returned a non-object JSON response")
        return payload

    def tags_for(self, persona: str) -> list[str]:
        return [BENCHMARK_TAG, self.scope_tag, _persona_tag(persona)]

    def store_memory(
        self,
        *,
        persona: str,
        content: str,
        narrative_time: str,
        source_message_id: str,
        importance: float = 0.7,
        memory_type: str = "Context",
    ) -> str:
        """Store an agent-selected memory from an ingestion interaction.

        The source message's narrative timestamp is retained as both the
        visible memory timestamp and metadata.  ``content`` must be the
        material selected by the agent's normal memory-writing policy, not an
        injected fact annotation or benchmark answer.
        """
        persona_tag = _persona_tag(persona)
        if persona_tag.removeprefix("dolphinbench-persona-") in self._frozen_personas:
            raise RuntimeError(f"{persona} memory is frozen for DolphinBench tests")
        if not content.strip():
            raise ValueError("content is required")
        if not source_message_id:
            raise ValueError("source_message_id is required")
        body = {
            "content": content,
            "tags": self.tags_for(persona),
            "importance": importance,
            "type": memory_type,
            "timestamp": narrative_time,
            "metadata": {
                "benchmark": BENCHMARK_TAG,
                "scope_tag": self.scope_tag,
                "persona": persona.lower(),
                "source_message_id": source_message_id,
                "narrative_time": narrative_time,
            },
        }
        request = urllib.request.Request(
            f"{self.endpoint}/memory",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=self._headers(),
        )
        payload = self._request(request)
        memory_id = payload.get("memory_id") or payload.get("id")
        if not isinstance(memory_id, str) or not memory_id:
            raise AutoMemHTTPError("AutoMem POST /memory returned no memory id")
        return memory_id

    def recall_memory(self, *, persona: str, query: str, limit: int = 20) -> list[RecallResult]:
        """Retrieve only memories from this exact benchmark configuration/persona."""
        if not query.strip():
            raise ValueError("query is required")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        params: list[tuple[str, str]] = [("query", query), ("limit", str(limit))]
        params.extend(("tags", tag) for tag in self.tags_for(persona))
        request = urllib.request.Request(
            f"{self.endpoint}/recall?{urllib.parse.urlencode(params)}",
            method="GET",
            headers=self._headers(),
        )
        payload = self._request(request)
        results: list[RecallResult] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            memory = item.get("memory") if isinstance(item.get("memory"), dict) else item
            memory_id = memory.get("id") or item.get("id")
            content = memory.get("content") or item.get("content")
            score = item.get("final_score", item.get("score"))
            if isinstance(memory_id, str) and isinstance(content, str):
                results.append(RecallResult(memory_id, content, float(score) if isinstance(score, (int, float)) else None))
        return results

    def freeze(self, persona: str) -> dict[str, str]:
        """Close local writes after ingestion; checkpoint the query namespace."""
        normalized = _persona_tag(persona).removeprefix("dolphinbench-persona-")
        self._frozen_personas.add(normalized)
        return {"persona": normalized, "scope_tag": self.scope_tag, "write_mode": "closed"}

    @staticmethod
    def format_recall_context(results: list[RecallResult]) -> str:
        """Format retrievals for the participant's agent prompt, never graders."""
        if not results:
            return "No relevant long-term memories were recalled."
        return "\n\n".join(
            f"[AutoMem memory {index}; id={result.memory_id}]\n{result.content}"
            for index, result in enumerate(results, start=1)
        )


def memory_tool_definitions() -> list[dict[str, Any]]:
    """Tool declarations an agent harness can register beside DolphinBench apps."""
    return [
        {
            "name": "store_memory",
            "description": "Store an agent-selected durable memory during history ingestion only.",
            "input_schema": {
                "type": "object",
                "properties": {"content": {"type": "string"}, "importance": {"type": "number"}},
                "required": ["content"],
            },
        },
        {
            "name": "recall_memory",
            "description": "Search the completed long-term memory for the current user request.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
        },
    ]
