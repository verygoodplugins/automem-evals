#!/usr/bin/env python3
"""AutoMem adapter for AMA-Hub's two-stage ``BaseMethod`` interface.

The file is deliberately dependency-light so ``run_ama_bench.sh`` can copy it
into an AMA-Hub checkout without installing that project's CUDA/vLLM extras.
It stores trajectory chunks through AutoMem's HTTP API and returns the content
of the tagged recall results as AMA-Hub context.

AutoMem has no delete-by-tag endpoint.  The adapter therefore records only the
IDs it created, deletes them before constructing the next trajectory, and can
persist the currently live IDs to ``state_file`` for the runner's EXIT trap.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from src.method.base_method import BaseMethod


DEFAULT_ENDPOINT = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"
DEFAULT_TAG = "ama-bench-eval"


class AutoMemRequestError(RuntimeError):
    """A concise error that retains the HTTP status without leaking payloads."""


def _request(
    endpoint: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Api-Key": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise AutoMemRequestError(f"AutoMem {method} {path}: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AutoMemRequestError(f"AutoMem {method} {path}: {exc.reason}") from exc
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AutoMemRequestError(f"AutoMem {method} {path}: non-JSON response") from exc


def cleanup_state_file(endpoint: str, token: str, state_file: str | pathlib.Path) -> int:
    """Delete exactly the IDs recorded by this adapter state file.

    This is safe to use from a shell EXIT trap: a missing/already-deleted
    record is ignored, while other AutoMem memories are never enumerated.
    """
    path = pathlib.Path(state_file)
    if not path.exists():
        return 0
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AutoMemRequestError(f"Invalid AutoMem state file {path}: {exc}") from exc
    ids = state.get("memory_ids", []) if isinstance(state, dict) else []
    failures = 0
    for memory_id in ids:
        try:
            _request(endpoint, token, "DELETE", f"/memory/{urllib.parse.quote(str(memory_id), safe='')}")
        except AutoMemRequestError as exc:
            # A prior trajectory cleanup may have won the race.  Do not hide
            # unexpected server failures, but keep trying the remaining IDs.
            print(f"[automem] cleanup warning: {exc}")
            failures += 1
    path.unlink(missing_ok=True)
    return failures


@dataclass
class AutoMemMemory:
    """Opaque AMA-Hub memory object containing only this trajectory's IDs."""

    memory_ids: list[str]
    tag: str
    trajectory_id: str


class AutoMemMethod(BaseMethod):
    """Store trajectory chunks in AutoMem and retrieve tagged semantic context."""

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        token: str = DEFAULT_TOKEN,
        tag: str = DEFAULT_TAG,
        top_k: int = 8,
        chunk_chars: int = 12000,
        importance: float = 0.7,
        state_file: str | None = None,
        config_path: str | None = None,
        embedding_engine: Any = None,
    ) -> None:
        config: dict[str, Any] = self._load_config(config_path) if config_path else {}
        self.endpoint = str(config.get("endpoint", os.environ.get("AUTOMEM_ENDPOINT", endpoint))).rstrip("/")
        self.token = str(config.get("token", os.environ.get("AUTOMEM_API_TOKEN", token)))
        self.tag = str(config.get("tag", os.environ.get("AUTOMEM_TAG", tag)))
        self.top_k = int(config.get("top_k", top_k))
        self.chunk_chars = int(config.get("chunk_chars", chunk_chars))
        self.importance = float(config.get("importance", importance))
        configured_state = config.get("state_file", state_file)
        self.state_file = pathlib.Path(configured_state) if configured_state else None
        self.embedding_engine = embedding_engine  # Interface compatibility; AutoMem embeds server-side.
        self._live_ids: list[str] = []

        if self.top_k < 1:
            raise ValueError("top_k must be at least 1")
        if self.chunk_chars < 256:
            raise ValueError("chunk_chars must be at least 256")

    def _write_state(self) -> None:
        if self.state_file is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps({"memory_ids": self._live_ids, "tag": self.tag}, indent=2),
            encoding="utf-8",
        )

    def cleanup(self) -> None:
        """Delete the current trajectory before another one is constructed."""
        failures: list[str] = []
        for memory_id in self._live_ids:
            try:
                _request(
                    self.endpoint,
                    self.token,
                    "DELETE",
                    f"/memory/{urllib.parse.quote(memory_id, safe='')}",
                )
            except AutoMemRequestError as exc:
                failures.append(str(exc))
        self._live_ids = []
        if self.state_file is not None:
            self.state_file.unlink(missing_ok=True)
        if failures:
            raise AutoMemRequestError("; ".join(failures))

    def _chunks(self, traj_text: str, task: str) -> list[str]:
        prefix = f"Task: {task}\n\n" if task else ""
        source = prefix + traj_text
        if not source:
            return [prefix or "(empty trajectory)"]

        chunks: list[str] = []
        remaining = source
        while len(remaining) > self.chunk_chars:
            boundary = remaining.rfind("\n", 0, self.chunk_chars)
            if boundary < self.chunk_chars // 2:
                boundary = self.chunk_chars
            chunks.append(remaining[:boundary].strip())
            remaining = remaining[boundary:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks

    def memory_construction(self, traj_text: str, task: str = "") -> AutoMemMemory:
        # AMA-Hub processes an episode at a time.  Removing prior IDs here
        # prevents the next episode's retrieval from seeing its predecessor.
        self.cleanup()
        trajectory_id = uuid.uuid4().hex
        stored_ids: list[str] = []
        try:
            for index, content in enumerate(self._chunks(traj_text, task)):
                response = _request(
                    self.endpoint,
                    self.token,
                    "POST",
                    "/memory",
                    {
                        "content": content,
                        "tags": [self.tag],
                        "importance": self.importance,
                        "type": "Context",
                        "metadata": {
                            "benchmark": "AMA-Bench",
                            "trajectory_id": trajectory_id,
                            "chunk_index": index,
                        },
                    },
                )
                memory_id = response.get("memory_id") or response.get("id")
                if not memory_id and isinstance(response.get("memory"), dict):
                    memory_id = response["memory"].get("id")
                if not memory_id:
                    raise AutoMemRequestError(f"AutoMem POST /memory returned no memory ID: {response}")
                stored_ids.append(str(memory_id))
        except Exception:
            self._live_ids = stored_ids
            self.cleanup()
            raise

        self._live_ids = stored_ids
        self._write_state()
        return AutoMemMemory(memory_ids=stored_ids, tag=self.tag, trajectory_id=trajectory_id)

    def memory_retrieve(self, memory: AutoMemMemory, question: str) -> str:
        if not isinstance(memory, AutoMemMemory):
            raise ValueError("memory must be an AutoMemMemory instance")
        query = urllib.parse.urlencode(
            {"query": question, "tags": memory.tag, "tag_match": "exact", "limit": self.top_k}
        )
        response = _request(self.endpoint, self.token, "GET", f"/recall?{query}")
        owned = set(memory.memory_ids)
        contexts: list[str] = []
        for result in response.get("results", []):
            memory_id = result.get("id") or result.get("memory_id")
            nested = result.get("memory") if isinstance(result.get("memory"), dict) else {}
            memory_id = memory_id or nested.get("id")
            # Tag gates isolate benchmark memory from other local activity, and
            # ID filtering additionally protects concurrent AMA runs sharing it.
            if memory_id not in owned:
                continue
            content = nested.get("content") or result.get("content")
            if isinstance(content, str) and content.strip():
                contexts.append(content.strip())
        return "\n\n".join(contexts) or "No relevant AutoMem context was retrieved."


def _main() -> int:
    parser = argparse.ArgumentParser(description="Clean an AMA-Bench AutoMem adapter state file")
    parser.add_argument("--cleanup-state", type=pathlib.Path, required=True)
    parser.add_argument("--endpoint", default=os.environ.get("AUTOMEM_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--token", default=os.environ.get("AUTOMEM_API_TOKEN", DEFAULT_TOKEN))
    args = parser.parse_args()
    return 1 if cleanup_state_file(args.endpoint, args.token, args.cleanup_state) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
