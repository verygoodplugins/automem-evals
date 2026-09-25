#!/usr/bin/env python3
"""Minimal MemoryArena memory-system adapter backed by AutoMem's HTTP API.

The official MemoryArena preview calls ``add_chunk`` after each subtask and
``wrap_user_prompt`` before the next one.  This module implements exactly that
interface without modifying the upstream checkout.  It is a protocol smoke
adapter, not a MemoryArena leaderboard runner.
"""

import argparse
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class AutoMemMemorySystem:
    """Store and retrieve one MemoryArena user's trajectory in AutoMem."""

    def __init__(
        self,
        user_id: str,
        endpoint: str | None = None,
        token: str | None = None,
        benchmark_tag: str = "memoryarena-smoke",
        limit: int = 5,
        timeout: int = 30,
    ) -> None:
        self.user_id = str(user_id)
        self.endpoint = (
            endpoint or os.environ.get("AUTOMEM_ENDPOINT", "http://127.0.0.1:8001")
        ).rstrip("/")
        self.token = token if token is not None else os.environ.get("AUTOMEM_TOKEN", "test-token")
        self.benchmark_tag = benchmark_tag
        self.limit = limit
        self.timeout = timeout
        if not self.user_id:
            raise ValueError("user_id must not be empty")
        if not self.benchmark_tag:
            raise ValueError("benchmark_tag must not be empty")
        if limit < 1:
            raise ValueError("limit must be a positive integer")

    @property
    def tags(self) -> list[str]:
        return [self.benchmark_tag, "memoryarena", f"user-{self.user_id}"]

    def add_chunk(self, chunk: str) -> dict[str, Any] | None:
        """Persist a MemoryArena action/observation chunk under the user scope."""
        content = str(chunk).strip()
        if not content:
            return None
        return self._request(
            "POST",
            "/memory",
            {
                "content": content,
                "type": "Context",
                "tags": self.tags,
                "importance": 0.7,
                "confidence": 0.9,
                "metadata": {
                    "benchmark": "MemoryArena",
                    "memoryarena_user_id": self.user_id,
                },
            },
        )

    def wrap_user_prompt(self, prompt: str) -> str:
        """Return the upstream-required memory block followed by the prompt."""
        question = str(prompt)
        query = urlencode(
            [("query", question), *(("tags", tag) for tag in self.tags), ("limit", str(self.limit))]
        )
        payload = self._request("GET", f"/recall?{query}")
        lines = ["<memory_context>"]
        for item in payload.get("results", []):
            content = _result_content(item)
            if content:
                lines.append(content)
        if len(lines) == 1:
            lines.append("None")
        lines.extend(["</memory_context>", f"User Prompt: {question}"])
        return "\n".join(lines)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.endpoint}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - caller chooses local endpoint
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError(f"AutoMem {method} {path} failed: {error}") from error


def _result_content(item: Any) -> str:
    """Accept current AutoMem recall response variants without scoring them."""
    if not isinstance(item, dict):
        return ""
    memory = item.get("memory")
    if isinstance(memory, dict):
        return str(memory.get("content") or memory.get("summary") or "").strip()
    return str(item.get("content") or item.get("summary") or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MemoryArena/AutoMem protocol smoke.")
    parser.add_argument("--endpoint", default=os.environ.get("AUTOMEM_ENDPOINT", "http://127.0.0.1:8001"))
    parser.add_argument("--token", default=os.environ.get("AUTOMEM_TOKEN", "test-token"))
    parser.add_argument("--user-id", default="memoryarena-smoke")
    parser.add_argument("--tag", default="memoryarena-smoke")
    parser.add_argument("--chunk", action="append", required=True, help="Action/observation chunk; repeatable")
    parser.add_argument("--query", required=True, help="Later dependent-subtask prompt")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    memory = AutoMemMemorySystem(
        user_id=args.user_id,
        endpoint=args.endpoint,
        token=args.token,
        benchmark_tag=args.tag,
        limit=args.limit,
    )
    stored = [memory.add_chunk(chunk) for chunk in args.chunk]
    print(
        json.dumps(
            {
                "benchmark": "MemoryArena",
                "mode": "protocol_smoke",
                "stored_chunks": sum(item is not None for item in stored),
                "wrapped_prompt": memory.wrap_user_prompt(args.query),
                "not_scored": "protocol smoke only; no upstream environment, agent, or judge was run",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
