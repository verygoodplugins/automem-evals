#!/usr/bin/env python3
"""
BEAM → AutoMem HTTP shim.

Impersonates the mem0-OSS REST surface that
`third_party/memory-benchmarks/benchmarks/common/mem0_client.py` calls when
`--backend oss` is set, and translates each call into AutoMem's REST API at
http://localhost:8001 (or --upstream).

Upstream contract (verified against upstream SHA f75666d):

  POST /memories           body: {messages:[{role,content}], user_id, timestamp?, metadata?,
                                  custom_instructions?}
                           resp: {"results": [{"id": "...", "memory": "...", "event": "ADD"}]}
  POST /search             body: {query, user_id, limit, rerank?}
                           resp: {"results": [{"id": "...", "memory": "...", "score": ...}]}
  DELETE /memories?user_id=X   resp: {"message": "..."}
  GET /health              resp: {"status": "ok"}

Every unknown path returns 405 — we want loud failures, not silent data loss.

V1 design note — no fact extraction. The real mem0-OSS server runs an LLM
fact-extraction pass before writing to Qdrant. This shim does NOT replicate
that: it concatenates the raw messages into a single content string and POSTs
that to AutoMem. If BEAM scores come back weak, that's a likely culprit worth
eliminating before calling AutoMem itself deficient on any category.

Per-conversation isolation is enforced by tagging every memory with the
supplied `user_id`, and passing `tags=<user_id>` on every /recall. That tag
is AutoMem's hard filter — without it, conversation N's facts bleed into
conversation N+1 and the whole BEAM score collapses.

Every memory also gets a *sweep tag*: the default is `beam` (bench-wide
marker), but when `--sweep-tag <x>` is passed the shim REPLACES `beam` with
`<x>` — it does not supplement. This is the isolation knob for running two
BEAM runs concurrently against the same AutoMem: give each a unique sweep
tag (e.g. `beam-run-<uuid8>`) and the end-of-run sweep in runners/run_beam.py
will only delete its own memories. Replacing (not supplementing) is what
makes this safe against an already-running run_beam.py whose cached blanket
`beam` sweep would otherwise wipe the newer run.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("beam-shim")

BEAM_TAG = "beam"                      # default sweep tag (bench-wide marker)
DEFAULT_UPSTREAM = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"
RECALL_PAGE = 500                      # delete_user pagination
# AutoMem's POST /memory rejects content >50K chars with 400. BEAM's upstream
# CHUNK_SIZE=2 keeps each call's payload tiny (typically <5K), so this is a
# belt-and-suspenders guard. If it ever trips, proper multi-memory chunking
# is the next iteration.
AUTOMEM_MAX_CONTENT = 49_000


def _messages_to_content(messages: list[dict]) -> str:
    """Join a list of {role, content} messages into a single block.

    Mirrors memorybench/src/providers/automem/index.ts:78-84 — same label
    shape so two AutoMem-backed benchmark adapters stay readable the same way.
    """
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        label = "User" if role == "user" else "Assistant" if role == "assistant" else role.capitalize()
        lines.append(f"{label}: {m.get('content', '')}")
    return "\n".join(lines)


class AutomemClient:
    """Tiny urllib wrapper around the AutoMem REST API we need."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Api-Key": self.token,
        }

    def post_memory(self, content: str, tags: list[str], metadata: dict) -> dict:
        body = json.dumps({
            "content": content,
            "tags": tags,
            "importance": 0.7,
            "metadata": metadata,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/memory",
            data=body,
            method="POST",
            headers=self._headers(),
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
            f"{self.base_url}/recall?{qs}",
            method="GET",
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def delete_memory(self, memory_id: str) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/memory/{memory_id}",
            method="DELETE",
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()


class BeamShimHandler(BaseHTTPRequestHandler):
    """Handle the three BEAM-facing endpoints + /health."""

    # Set by the server factory.
    automem: "AutomemClient" = None  # type: ignore[assignment]
    sweep_tag: str = BEAM_TAG

    # Silence the default request log line unless we opt into it.
    def log_message(self, fmt: str, *args) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)

    # ---------------- helpers ----------------

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        return json.loads(raw)

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _reject_unknown(self) -> None:
        self._send(405, {"error": f"shim does not implement {self.command} {self.path}"})

    # ---------------- routing ----------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"status": "ok", "shim": "beam-automem"})
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
            logger.exception("shim handler failure on %s", self.path)
            self._send(500, {"error": str(exc)})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/memories":
            self._reject_unknown()
            return
        try:
            self._handle_delete(parsed)
        except Exception as exc:
            logger.exception("shim delete failure")
            self._send(500, {"error": str(exc)})

    # ---------------- endpoints ----------------

    def _handle_add(self) -> None:
        body = self._read_json()
        messages = body.get("messages") or []
        user_id = body.get("user_id")
        if not user_id:
            self._send(400, {"error": "user_id is required"})
            return

        content = _messages_to_content(messages)
        if not content.strip():
            # Upstream treats empty responses as "no extracted memories" — mirror that.
            self._send(200, {"results": []})
            return
        if len(content) > AUTOMEM_MAX_CONTENT:
            logger.warning(
                "user_id=%s content=%d chars exceeds AutoMem cap %d — truncating. "
                "If you see this at scale, upgrade the shim to store multiple memories per chunk.",
                user_id, len(content), AUTOMEM_MAX_CONTENT,
            )
            content = content[:AUTOMEM_MAX_CONTENT]

        tags = [user_id, self.sweep_tag]
        metadata = {
            "bench": BEAM_TAG,
            "sweep_tag": self.sweep_tag,
            "user_id": user_id,
            "shim_version": "v1-passthrough",
        }
        ts = body.get("timestamp")
        if ts is not None:
            metadata["timestamp"] = ts
        extra_md = body.get("metadata")
        if isinstance(extra_md, dict):
            metadata.update(extra_md)

        resp = self.automem.post_memory(content, tags, metadata)
        memory_id = resp.get("memory_id") or resp.get("id")
        if not memory_id:
            self._send(502, {"error": "AutoMem POST /memory returned no id", "upstream": resp})
            return

        self._send(200, {"results": [{"id": memory_id, "memory": content, "event": "ADD"}]})

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


def build_server(host: str, port: int, automem: AutomemClient, sweep_tag: str = BEAM_TAG) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (BeamShimHandler,), {"automem": automem, "sweep_tag": sweep_tag})
    return ThreadingHTTPServer((host, port), handler)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="BEAM → AutoMem REST shim")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="0 = pick a free port (printed on startup)")
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM, help="AutoMem base URL")
    ap.add_argument("--token", default=DEFAULT_TOKEN, help="AutoMem API token")
    ap.add_argument(
        "--sweep-tag",
        default=BEAM_TAG,
        help=(
            "Tag applied to every stored memory in place of the default 'beam'. "
            "Use a per-run value (e.g. 'beam-run-<uuid8>') to isolate concurrent "
            "runs from each other's end-of-run sweeps."
        ),
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    automem = AutomemClient(args.upstream, args.token)
    port = args.port or find_free_port()
    server = build_server(args.host, port, automem, sweep_tag=args.sweep_tag)
    logger.info(
        "shim listening on http://%s:%d (upstream=%s, sweep_tag=%s)",
        args.host, port, args.upstream, args.sweep_tag,
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
