#!/usr/bin/env python3
"""AutoMem adapter for Memora's Track 2 (memory-agent) evaluation.

The released Memora factory does not dynamically discover third-party agents.
This module implements its ``BaseMemorySystem`` contract and drives its two
pipeline stages without modifying the cloned harness.  ``AutoMemMCPClient`` is
the Python equivalent of AutoMem's MCP ``store_memory``/``recall_memory``
surface: superseding a fact is deliberately expanded into fetch, store,
invalidate, and associate HTTP operations, exactly as the MCP client does.

This is exploratory evaluation plumbing, not an official benchmark harness or
leaderboard submission path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from typing import Any, Callable, Optional


REPO = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_ENDPOINT = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"


def _iso_day(value: str) -> str:
    """Return the UTC beginning of a Memora session date."""
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc).isoformat()


def _safe_tag(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


def _json_request(
    endpoint: str,
    token: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    query: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, list):
            query.extend((key, str(item)) for item in value)
        elif isinstance(value, bool):
            query.append((key, "true" if value else "false"))
        else:
            query.append((key, str(value)))
    url = f"{endpoint.rstrip('/')}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    encoded = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Api-Key": token}
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=encoded, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AutoMem {method} {path} failed ({exc.code}): {detail}") from exc
    return json.loads(raw) if raw else {}


class AutoMemMCPClient:
    """Small transport client preserving AutoMem MCP tool semantics.

    ``supersedes_memory_id`` is an MCP-level field, not a ``POST /memory``
    field.  The MCP implementation expands it to old-memory retrieval, write
    of the replacement, invalidation of the old memory, then a lifecycle edge.
    The explicit timestamp is important here: Memora sessions are historical.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        token: str = DEFAULT_TOKEN,
        *,
        request_json: Callable[..., dict[str, Any]] = _json_request,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.request_json = request_json
        self.store_calls: list[dict[str, Any]] = []

    def health(self) -> dict[str, Any]:
        return self.request_json(self.endpoint, self.token, "GET", "/health", timeout=10)

    def store_memory(self, **payload: Any) -> str:
        """Implement MCP ``store_memory``, including supersede mode."""
        self.store_calls.append(dict(payload))
        old_id = str(payload.pop("supersedes_memory_id", "") or "").strip()
        relation = str(payload.pop("supersede_relation", "INVALIDATED_BY"))
        payload.pop("supersede_reason", None)
        if relation not in {"INVALIDATED_BY", "EVOLVED_INTO"}:
            raise ValueError("supersede_relation must be INVALIDATED_BY or EVOLVED_INTO")

        if old_id:
            # Preserve the MCP client's safety check before changing lifecycle state.
            self.request_json(self.endpoint, self.token, "GET", f"/memory/{old_id}")

        response = self.request_json(
            self.endpoint, self.token, "POST", "/memory", body=payload, timeout=120
        )
        memory_id = str(response.get("memory_id") or response.get("id") or "")
        if not memory_id:
            raise RuntimeError("AutoMem store_memory returned no memory_id")

        if old_id:
            invalid_at = str(payload.get("timestamp") or payload.get("t_valid") or "")
            if not invalid_at:
                invalid_at = dt.datetime.now(dt.timezone.utc).isoformat()
            self.request_json(
                self.endpoint,
                self.token,
                "PATCH",
                f"/memory/{old_id}",
                body={"t_invalid": invalid_at},
            )
            self.request_json(
                self.endpoint,
                self.token,
                "POST",
                "/associate",
                body={
                    "memory1_id": old_id,
                    "memory2_id": memory_id,
                    "type": relation,
                    "strength": 1.0,
                },
            )
        return memory_id

    def invalidate_memory(self, memory_id: str, *, invalid_at: str) -> None:
        """Invalidate a deleted fact without creating a retrievable tombstone."""
        self.request_json(
            self.endpoint,
            self.token,
            "PATCH",
            f"/memory/{memory_id}",
            body={"t_invalid": invalid_at},
        )

    def recall_memory(self, query: str, *, tags: list[str], limit: int) -> list[dict[str, Any]]:
        response = self.request_json(
            self.endpoint,
            self.token,
            "GET",
            "/recall",
            params={
                "query": query,
                "tags": tags,
                "tag_mode": "all",
                "tag_match": "exact",
                "limit": limit,
                # This is the central FAMA behavior under evaluation.
                "current_only": True,
            },
            timeout=60,
        )
        results = response.get("results", [])
        return results if isinstance(results, list) else []


try:
    from base_evaluator import BaseMemorySystem as _MemoraBaseMemorySystem
except ImportError:
    class _MemoraBaseMemorySystem:  # type: ignore[no-redef]
        """Fallback keeps the adapter importable without a Memora checkout."""

        def __init__(self, user_id: str, **_: Any) -> None:
            self.user_id = user_id
            self.system_name = self.get_system_name()


class AutoMemFamaSystem(_MemoraBaseMemorySystem):
    """Memora Track 2 ``BaseMemorySystem`` implementation for AutoMem."""

    def __init__(
        self,
        user_id: str,
        *,
        endpoint: str | None = None,
        token: str | None = None,
        run_tag: str | None = None,
        request_json: Callable[..., dict[str, Any]] = _json_request,
        **kwargs: Any,
    ) -> None:
        super().__init__(user_id, **kwargs)
        self.run_tag = run_tag or f"memora-{_safe_tag(user_id)}"
        self.user_tag = f"memora-user-{_safe_tag(user_id)}"
        self.client = AutoMemMCPClient(
            endpoint or os.getenv("AUTOMEM_ENDPOINT", DEFAULT_ENDPOINT),
            token or os.getenv("AUTOMEM_TOKEN", DEFAULT_TOKEN),
            request_json=request_json,
        )
        self._current_by_fact: dict[str, str] = {}

    def get_system_name(self) -> str:
        return "automem"

    def get_required_env_vars(self) -> list[str]:
        # AutoMem is deliberately local-only by default; token has a safe local default.
        return []

    def initialize_client(self) -> bool:
        try:
            self.client.health()
        except Exception as exc:
            print(f"AutoMem health check failed: {exc}", file=sys.stderr)
            return False
        return True

    @staticmethod
    def _fact_key(conversation: dict[str, Any]) -> str:
        details = conversation.get("operation_details") or {}
        item = details.get("item")
        if isinstance(item, str) and item.strip():
            return _safe_tag(item)
        if isinstance(item, dict):
            for key in ("description", "event_name", "title", "name"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return _safe_tag(f"{details.get('category', 'item')}-{value}")
        content = details.get("content_data")
        if isinstance(content, dict):
            for key in ("project_title", "meeting_title", "email_purpose"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return _safe_tag(f"content-{value}")
        return f"session-{conversation.get('session_id', 'unknown')}"

    @staticmethod
    def _shared_content(conversation: dict[str, Any]) -> str:
        messages = [
            str(turn.get("message", "")).strip()
            for turn in conversation.get("conversation", [])
            if turn.get("share_memory") and str(turn.get("message", "")).strip()
        ]
        return "\n".join(messages)

    def add_conversation_to_memory(self, conversation_data: dict[str, Any]) -> dict[str, Any]:
        """Store one Memora session, applying its explicit lifecycle operation."""
        operation = str(conversation_data.get("operation") or "add").lower()
        fact_key = self._fact_key(conversation_data)
        timestamp = _iso_day(str(conversation_data.get("date")))
        content = self._shared_content(conversation_data)
        previous_id = self._current_by_fact.get(fact_key)

        if operation == "delete":
            if not previous_id:
                return {"status": "skipped", "reason": "no active fact", "fact_key": fact_key}
            self.client.invalidate_memory(previous_id, invalid_at=timestamp)
            del self._current_by_fact[fact_key]
            return {"status": "invalidated", "memory_id": previous_id, "fact_key": fact_key}

        if not content:
            return {"status": "skipped", "reason": "no share_memory turn", "fact_key": fact_key}

        payload: dict[str, Any] = {
            "content": content,
            "type": "Context",
            "importance": 0.8,
            "confidence": 1.0,
            "timestamp": timestamp,
            "t_valid": timestamp,
            "tags": ["memora", self.user_tag, self.run_tag, f"memora-operation-{operation}"],
            "metadata": {
                "memora_session_id": conversation_data.get("session_id"),
                "memora_date": conversation_data.get("date"),
                "memora_operation": operation,
                "memora_fact_key": fact_key,
            },
        }
        if operation == "update" and previous_id:
            payload.update(
                {
                    "supersedes_memory_id": previous_id,
                    "supersede_relation": "EVOLVED_INTO",
                    "supersede_reason": "Memora ground-truth update operation",
                }
            )
        memory_id = self.client.store_memory(**payload)
        self._current_by_fact[fact_key] = memory_id
        return {
            "status": "stored",
            "memory_id": memory_id,
            "fact_key": fact_key,
            "superseded": previous_id if operation == "update" else None,
        }

    def search_memories(
        self,
        query: str,
        limit: int = 50,
        session_date: Optional[str] = None,
        date_range: Optional[tuple] = None,
    ) -> list[dict[str, Any]]:
        del session_date, date_range  # The question's final-state semantics are current_only.
        rows = self.client.recall_memory(query, tags=["memora", self.user_tag, self.run_tag], limit=limit)
        mapped: list[dict[str, Any]] = []
        for row in rows:
            memory = row.get("memory", {}) if isinstance(row, dict) else {}
            text = memory.get("content") if isinstance(memory, dict) else None
            if not text and isinstance(row, dict):
                text = row.get("content")
            if not text:
                continue
            mapped.append(
                {
                    "memory": str(text),
                    "score": float(row.get("final_score", row.get("match_score", 0.0)) or 0.0),
                    "memory_id": row.get("memory_id") or row.get("id"),
                }
            )
        return mapped

    def process_conversation_file(self, file_path: str) -> dict[str, Any]:
        with open(file_path, encoding="utf-8") as handle:
            return self.add_conversation_to_memory(json.load(handle))


class _ProtocolSmokeTransport:
    """In-process AutoMem API double for the no-cost protocol smoke."""

    def __init__(self) -> None:
        self.memories: dict[str, dict[str, Any]] = {}
        self.associations: list[dict[str, Any]] = []

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
        if path == "/health":
            return {"status": "healthy"}
        if method == "GET" and path.startswith("/memory/"):
            return {"memory": self.memories.get(path.rsplit("/", 1)[-1], {})}
        if method == "POST" and path == "/memory":
            memory_id = str(uuid.uuid4())
            self.memories[memory_id] = dict(body or {})
            return {"memory_id": memory_id}
        if method == "PATCH" and path.startswith("/memory/"):
            self.memories[path.rsplit("/", 1)[-1]].update(body or {})
            return {"status": "success"}
        if method == "POST" and path == "/associate":
            self.associations.append(dict(body or {}))
            return {"status": "success"}
        if method == "GET" and path == "/recall":
            requested_tags = set((params or {}).get("tags", []))
            rows = []
            for memory_id, memory in self.memories.items():
                if memory.get("t_invalid"):
                    continue
                if requested_tags.issubset(set(memory.get("tags", []))):
                    rows.append({"memory_id": memory_id, "memory": memory, "final_score": 1.0})
            return {"results": rows[: int((params or {}).get("limit", 50))]}
        raise AssertionError(f"unexpected smoke request: {method} {path}")


def _paths(memora_dir: pathlib.Path, period: str, persona: str) -> tuple[pathlib.Path, pathlib.Path]:
    root = memora_dir / "data" / period / persona
    return root / "conversations", root / f"evaluation_questions_{persona}.json"


def ingest(
    system: AutoMemFamaSystem, conversations_dir: pathlib.Path, *, limit: int | None = None
) -> Counter[str]:
    outcomes: Counter[str] = Counter()
    def session_order(path: pathlib.Path) -> int:
        """Order unpadded ``session_N.json`` files by their numeric N."""
        match = re.fullmatch(r"session_(\d+)\.json", path.name)
        if not match:
            raise ValueError(f"unexpected Memora conversation filename: {path.name}")
        return int(match.group(1))

    paths = sorted(conversations_dir.glob("session_*.json"), key=session_order)
    if limit is not None:
        paths = paths[:limit]
    for path in paths:
        outcomes[system.process_conversation_file(str(path))["status"]] += 1
    return outcomes


def protocol_smoke(memora_dir: pathlib.Path, period: str, persona: str) -> dict[str, Any]:
    conversations_dir, questions_file = _paths(memora_dir, period, persona)
    if not conversations_dir.is_dir() or not questions_file.is_file():
        raise SystemExit(f"Memora data missing: expected {conversations_dir} and {questions_file}")
    transport = _ProtocolSmokeTransport()
    system = AutoMemFamaSystem(
        f"{persona}_{period}", run_tag="memora-protocol-smoke", request_json=transport.request
    )
    outcomes = ingest(system, conversations_dir)
    with open(questions_file, encoding="utf-8") as handle:
        questions = json.load(handle)
    first_bucket = next(iter(questions["questions"].values()))
    answerable = system.search_memories(first_bucket[0]["question"])
    if not answerable:
        raise RuntimeError("protocol smoke retrieved no current memories")
    summary = {
        "kind": "memora-fama-protocol-smoke",
        "period": period,
        "persona": persona,
        "sessions": sum(outcomes.values()),
        "outcomes": dict(sorted(outcomes.items())),
        "stored_memories": len(transport.memories),
        "lifecycle_edges": len(transport.associations),
        "current_recall_results": len(answerable),
        "fama": None,
        "fama_status": "not_scored: released Track 2 uses paid answer and judge LLMs; no exact-match scorer exists",
    }
    return summary


def evaluate_with_memora(
    memora_dir: pathlib.Path,
    system: AutoMemFamaSystem,
    questions_file: pathlib.Path,
    *,
    question_limit: int | None,
) -> pathlib.Path:
    """Run Memora's official Track 2 answer + multi-judge classes unmodified."""
    agent_eval = memora_dir / "evals" / "agent_eval"
    if not agent_eval.is_dir():
        raise RuntimeError(f"Memora agent_eval directory not found: {agent_eval}")
    sys.path.insert(0, str(agent_eval))
    import base_evaluator  # type: ignore
    import memory_to_answer  # type: ignore

    def factory(name: str, user_id: str, **kwargs: Any) -> AutoMemFamaSystem:
        if name.lower() != "automem":
            raise ValueError(f"adapter only supplies automem, not {name}")
        return AutoMemFamaSystem(
            user_id,
            endpoint=system.client.endpoint,
            token=system.client.token,
            run_tag=system.run_tag,
            **kwargs,
        )

    # The modules imported the factory directly, so patch both bindings.
    base_evaluator.get_memory_system = factory
    memory_to_answer.get_memory_system = factory
    output_dir = questions_file.parent / "eval_results" / "automem"
    qa = memory_to_answer.MemoryQuestionAnswering(
        "automem",
        system.user_id,
        output_dir=output_dir,
        use_multi_judge=True,
        strict_judges=True,
    )
    questions_data = qa.load_questions(str(questions_file))
    questions = qa.extract_all_questions(questions_data)
    results = qa.process_questions(qa.filter_questions(questions, limit=question_limit))
    result_file = qa.save_results(results)
    return pathlib.Path(result_file)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memora-dir", type=pathlib.Path, default=pathlib.Path(os.getenv("MEMORA_DIR", REPO / "third_party" / "memora")))
    parser.add_argument("--period", default="weekly", choices=("weekly", "monthly", "quarterly"))
    parser.add_argument("--persona", default="software_engineer")
    parser.add_argument("--endpoint", default=os.getenv("AUTOMEM_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--token", default=os.getenv("AUTOMEM_TOKEN", DEFAULT_TOKEN))
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--ingest", action="store_true", help="run Track 2 ingestion only")
    parser.add_argument("--evaluate", action="store_true", help="run the official answer + judge stage")
    parser.add_argument("--limit", type=int, default=None, help="limit sessions for ingestion or questions for evaluation")
    parser.add_argument("--smoke", action="store_true", help="run no-cost weekly protocol smoke with an in-process AutoMem transport")
    args = parser.parse_args()

    if args.smoke:
        summary = protocol_smoke(args.memora_dir, args.period, args.persona)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    if not args.ingest and not args.evaluate:
        parser.error("choose --ingest, --evaluate, or --smoke")
    conversations_dir, questions_file = _paths(args.memora_dir, args.period, args.persona)
    system = AutoMemFamaSystem(
        f"{args.persona}_{args.period}",
        endpoint=args.endpoint,
        token=args.token,
        run_tag=args.run_tag,
    )
    if args.ingest:
        if not system.initialize_client():
            raise SystemExit("AutoMem is unavailable; start the local stack before ingestion")
        print(json.dumps({"ingest": dict(ingest(system, conversations_dir, limit=args.limit))}, sort_keys=True))
    if args.evaluate:
        print(evaluate_with_memora(args.memora_dir, system, questions_file, question_limit=args.limit))


if __name__ == "__main__":
    main()
