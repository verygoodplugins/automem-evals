#!/usr/bin/env python3
"""
BEAM → AutoMem HTTP shim (V2, with mem0-style fact extraction).

Same wire contract as `beam_shim.py` (V1) — impersonates the mem0-OSS REST
surface at `/memories`, `/search`, `/memories?user_id=...`. Only ingestion
behavior differs.

**V1 behavior (baseline):** concatenate messages to one blob, POST to AutoMem
as a single memory.

**V2 behavior (this file):** before POST /memory, call gpt-4o-mini with
mem0's verbatim `FACT_RETRIEVAL_PROMPT` (pinned in
`runners/prompts/mem0_prompts_daa4495.py`) to extract atomic facts. Each
extracted fact becomes its own AutoMem memory under the same `user_id` tag.

Why this matters for AutoMem evaluation:
- V1's single-blob storage cannot be superseded (AutoMem's `INVALIDATED_BY`
  edge needs fact-level units to compare). Failure analysis of V1 on BEAM
  100K showed 94% of `knowledge_update` failures are either retrieval-miss
  (A) or chronology-confusion (B) — both of which fact extraction addresses.
- The V1 50K truncation cap on `POST /memory` disappears naturally because
  individual facts are small.
- mem0-OSS uses this exact pipeline. Running AutoMem under this shim is as
  close to apples-to-apples with mem0 as we can get without forking.

What we deliberately do NOT replicate from mem0:
- The UPDATE_MEMORY_PROMPT pass that decides ADD/UPDATE/DELETE/NONE per fact.
  This shim is ADD-only: every extracted fact becomes a new memory. Rationale:
  (a) keeps the shim simple and the V1→V2 diff clean — any improvement is
  attributable to extraction alone, not to extraction+update-logic jointly;
  (b) AutoMem's graph layer (supersession edges, enrichment) is meant to
  handle conflicts server-side; making mem0-style UPDATE decisions in the
  shim would mask whether AutoMem's graph is doing its job.

Isolation: same per-user_id tag, same sweep-tag replacement as V1.

Upstream contract (unchanged):
  POST /memories, POST /search, DELETE /memories?user_id=, GET /health
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import socket
import sys
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("beam-shim-v2")

# Load mem0's pinned FACT_RETRIEVAL_PROMPT from our vendored copy.
REPO = pathlib.Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO / "runners" / "prompts"
sys.path.insert(0, str(PROMPTS_DIR))
from mem0_prompts_daa4495 import FACT_RETRIEVAL_PROMPT  # noqa: E402

import openai  # noqa: E402  (openai SDK: installed in .venv-beam)

BEAM_TAG = "beam"
DEFAULT_UPSTREAM = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"
DEFAULT_EXTRACTION_MODEL = "gpt-4o-mini"
DEFAULT_EXTRACTION_TIMEOUT = 60
RECALL_PAGE = 500
# Not strictly needed in V2 (facts are tiny) but kept as a defense-in-depth
# guard against bizarre prompts or model outputs.
AUTOMEM_MAX_CONTENT = 49_000


def _messages_to_conversation_block(messages: list[dict]) -> str:
    """Render role-labeled conversation for the extraction prompt.

    mem0 passes messages as the user turn to the extraction call; we do the
    same, formatted so the model sees who said what.
    """
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        label = "User" if role == "user" else "Assistant" if role == "assistant" else role.capitalize()
        lines.append(f"{label}: {m.get('content', '')}")
    return "\n".join(lines)


class FactExtractor:
    """Thin wrapper around OpenAI chat completions. Uses JSON response format
    because mem0's prompt explicitly requests JSON and the decoder guarantee
    saves a defensive parse/retry loop."""

    def __init__(self, model: str, timeout: float):
        self.model = model
        self.timeout = timeout
        # One shared client; the SDK is thread-safe.
        self.client = openai.OpenAI(timeout=timeout)

    def extract(self, conversation: str) -> tuple[list[str], dict]:
        """Return (facts, diagnostics). On any error, returns ([], diagnostics)
        so the caller can fall back to V1-style blob storage."""
        t0 = time.monotonic()
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": FACT_RETRIEVAL_PROMPT},
                    {"role": "user", "content": conversation},
                ],
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            parsed = json.loads(content)
            facts = parsed.get("facts") or []
            if not isinstance(facts, list):
                facts = []
            # Coerce to strings, strip blanks
            facts = [str(f).strip() for f in facts if str(f).strip()]
            dt_ms = (time.monotonic() - t0) * 1000
            return facts, {
                "ok": True,
                "model": self.model,
                "latency_ms": round(dt_ms, 1),
                "n_facts": len(facts),
                "usage": {
                    "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(resp.usage, "completion_tokens", None),
                },
            }
        except Exception as exc:
            dt_ms = (time.monotonic() - t0) * 1000
            logger.warning("extraction failed after %.0fms: %s", dt_ms, exc)
            return [], {
                "ok": False,
                "model": self.model,
                "latency_ms": round(dt_ms, 1),
                "error": f"{type(exc).__name__}: {exc}",
            }


class AutomemClient:
    """Same shape as V1's AutomemClient — kept parallel for easy diffing."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "X-Api-Key": self.token}

    def post_memory(self, content: str, tags: list[str], metadata: dict, importance: float = 0.7) -> dict:
        body = json.dumps({
            "content": content,
            "tags": tags,
            "importance": importance,
            "metadata": metadata,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/memory", data=body, method="POST", headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def recall(self, query: str, tags: list[str], limit: int) -> dict:
        params: list[tuple[str, str]] = [("limit", str(limit))]
        if query:
            params.append(("query", query))
        for t in tags:
            params.append(("tags", t))
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{self.base_url}/recall?{qs}", method="GET", headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def delete_memory(self, memory_id: str) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/memory/{memory_id}", method="DELETE", headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()


class BeamShimV2Handler(BaseHTTPRequestHandler):
    automem: "AutomemClient" = None  # type: ignore[assignment]
    extractor: "FactExtractor" = None  # type: ignore[assignment]
    sweep_tag: str = BEAM_TAG
    fallback_on_empty: bool = True
    stats_path: pathlib.Path | None = None

    def log_message(self, fmt: str, *args) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw) if raw else {}

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _reject_unknown(self) -> None:
        self._send(405, {"error": f"shim does not implement {self.command} {self.path}"})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"status": "ok", "shim": "beam-automem-v2"})
            return
        self._reject_unknown()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/memories":
                self._handle_add()
            elif parsed.path == "/search":
                self._handle_search()
            else:
                self._reject_unknown()
        except Exception as exc:
            logger.exception("handler failure on %s", self.path)
            self._send(500, {"error": str(exc)})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/memories":
            self._reject_unknown()
            return
        try:
            self._handle_delete(parsed)
        except Exception as exc:
            logger.exception("delete failure")
            self._send(500, {"error": str(exc)})

    def _append_stats(self, record: dict) -> None:
        if not self.stats_path:
            return
        try:
            with self.stats_path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.warning("stats write failed: %s", exc)

    def _handle_add(self) -> None:
        body = self._read_json()
        messages = body.get("messages") or []
        user_id = body.get("user_id")
        if not user_id:
            self._send(400, {"error": "user_id is required"})
            return

        conversation = _messages_to_conversation_block(messages)
        if not conversation.strip():
            self._send(200, {"results": []})
            return

        # Extraction (the V2-specific step)
        facts, diag = self.extractor.extract(conversation)

        # Decide what to store:
        #  - If extraction returned facts → store each as its own memory.
        #  - If extraction failed OR returned empty AND fallback is enabled →
        #    store the raw conversation as one memory (V1 behavior) so BEAM
        #    still has something to retrieve. A conversation legitimately
        #    containing no facts (e.g. "Hi.") should indeed yield no memories,
        #    so we only fall back when extraction ERRORED, not when it
        #    successfully returned zero facts.
        tags = [user_id, self.sweep_tag]
        ts = body.get("timestamp")
        extra_md = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}

        results: list[dict] = []

        if facts:
            for fact_idx, fact in enumerate(facts):
                content = fact
                if len(content) > AUTOMEM_MAX_CONTENT:
                    content = content[:AUTOMEM_MAX_CONTENT]
                md = {
                    "bench": BEAM_TAG,
                    "sweep_tag": self.sweep_tag,
                    "user_id": user_id,
                    "shim_version": "v2-extraction",
                    "extraction_model": self.extractor.model,
                    "fact_idx": fact_idx,
                    "fact_count_in_chunk": len(facts),
                }
                if ts is not None:
                    md["timestamp"] = ts
                md.update(extra_md)
                try:
                    resp = self.automem.post_memory(content, tags, md)
                    mid = resp.get("memory_id") or resp.get("id")
                    if mid:
                        results.append({"id": mid, "memory": content, "event": "ADD"})
                except Exception as exc:
                    logger.warning("post_memory failed for fact %d: %s", fact_idx, exc)

        elif not diag.get("ok") and self.fallback_on_empty:
            # Extraction errored — fall back to V1-style blob so we don't
            # silently drop this chunk.
            content = conversation[:AUTOMEM_MAX_CONTENT]
            md = {
                "bench": BEAM_TAG,
                "sweep_tag": self.sweep_tag,
                "user_id": user_id,
                "shim_version": "v2-extraction-fallback-v1blob",
                "extraction_error": diag.get("error"),
            }
            if ts is not None:
                md["timestamp"] = ts
            md.update(extra_md)
            resp = self.automem.post_memory(content, tags, md)
            mid = resp.get("memory_id") or resp.get("id")
            if mid:
                results.append({"id": mid, "memory": content, "event": "ADD"})

        # Record stats line per call for post-run analysis
        self._append_stats({
            "ts": time.time(),
            "user_id": user_id,
            "messages_len": sum(len(m.get("content", "") or "") for m in messages),
            "conversation_chars": len(conversation),
            "extraction_ok": diag.get("ok", False),
            "extraction_latency_ms": diag.get("latency_ms"),
            "extraction_error": diag.get("error"),
            "n_facts": len(facts),
            "n_memories_stored": len(results),
            "fallback_used": (not facts) and (not diag.get("ok")) and self.fallback_on_empty,
            "usage": diag.get("usage"),
        })

        self._send(200, {"results": results})

    def _handle_search(self) -> None:
        body = self._read_json()
        query = body.get("query") or ""
        user_id = body.get("user_id")
        limit = int(body.get("limit") or 200)
        if not user_id:
            self._send(400, {"error": "user_id is required"})
            return

        resp = self.automem.recall(query, [user_id], limit)
        out: list[dict] = []
        for r in resp.get("results") or []:
            mem = r.get("memory") or {}
            out.append({
                "id": mem.get("id") or r.get("id") or "",
                "memory": mem.get("content") or r.get("content") or "",
                "score": r.get("final_score") or r.get("score") or 0,
            })
        out.sort(key=lambda x: x.get("score", 0), reverse=True)
        self._send(200, {"results": out})

    def _handle_delete(self, parsed: urllib.parse.ParseResult) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        user_id = (params.get("user_id") or [""])[0]
        if not user_id:
            self._send(400, {"error": "user_id query param is required"})
            return

        deleted = 0
        while True:
            resp = self.automem.recall("", [user_id], RECALL_PAGE)
            results = resp.get("results") or []
            if not results:
                break
            for r in results:
                mem = r.get("memory") or {}
                mid = mem.get("id") or r.get("id")
                if not mid:
                    continue
                try:
                    self.automem.delete_memory(mid)
                    deleted += 1
                except Exception as exc:
                    logger.warning("delete %s failed: %s", mid, exc)
            if len(results) < RECALL_PAGE:
                break

        self._send(200, {"message": f"deleted {deleted} memories for {user_id}"})


def build_server(
    host: str,
    port: int,
    automem: AutomemClient,
    extractor: FactExtractor,
    sweep_tag: str = BEAM_TAG,
    stats_path: pathlib.Path | None = None,
) -> ThreadingHTTPServer:
    handler = type(
        "BoundHandler",
        (BeamShimV2Handler,),
        {
            "automem": automem,
            "extractor": extractor,
            "sweep_tag": sweep_tag,
            "stats_path": stats_path,
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="BEAM → AutoMem REST shim (V2, with fact extraction)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM, help="AutoMem base URL")
    ap.add_argument("--token", default=DEFAULT_TOKEN, help="AutoMem API token")
    ap.add_argument("--sweep-tag", default=BEAM_TAG)
    ap.add_argument("--extraction-model", default=DEFAULT_EXTRACTION_MODEL)
    ap.add_argument("--extraction-timeout", type=float, default=DEFAULT_EXTRACTION_TIMEOUT)
    ap.add_argument("--stats-path", default=None, help="If set, append per-call stats as JSONL")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for V2 shim (fact extraction).")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    automem = AutomemClient(args.upstream, args.token)
    extractor = FactExtractor(args.extraction_model, args.extraction_timeout)
    port = args.port or find_free_port()
    stats_path = pathlib.Path(args.stats_path) if args.stats_path else None
    if stats_path:
        stats_path.parent.mkdir(parents=True, exist_ok=True)

    server = build_server(args.host, port, automem, extractor, sweep_tag=args.sweep_tag, stats_path=stats_path)
    logger.info(
        "V2 shim listening on http://%s:%d (upstream=%s, sweep_tag=%s, extractor=%s)",
        args.host, port, args.upstream, args.sweep_tag, args.extraction_model,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
