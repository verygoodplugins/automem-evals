#!/usr/bin/env python3
"""
Smoke test for runners/beam_shim.py — round-trips one conversation through
the shim → AutoMem and asserts the expected shape back.

Run with the shim already up (defaults to http://127.0.0.1:8888). Will also
spawn one itself with --self-spawn if you want a zero-setup sanity check.

Exit 0 = all assertions passed and cleanup succeeded. Anything else = stop,
read the traceback, do not scale up to the full runner.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SHIM_PATH = os.path.join(REPO, "runners", "beam_shim.py")

SMOKE_USER = "beam-shim-smoke"
SMOKE_QUERY = "What color did the user say their bike was painted?"
SMOKE_CONTENT_HINT = "teal"  # appears in the conversation text

CONVERSATION = [
    {"role": "user", "content": "I finally got my fixie painted teal last weekend — happiest I've been with a bike in years."},
    {"role": "assistant", "content": "That sounds great! Teal is a fun choice. What route are you riding it on most?"},
    {"role": "user", "content": "Mostly the lakefront path. I commute from Ravenswood down to the Loop."},
]


def _post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def _delete(url: str) -> dict:
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def wait_for_health(shim_url: str, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = _get_json(f"{shim_url}/health")
            if resp.get("status") == "ok":
                return
        except (urllib.error.URLError, ConnectionError, json.JSONDecodeError) as exc:
            last_err = exc
        time.sleep(0.2)
    raise SystemExit(f"shim at {shim_url} never became healthy: {last_err}")


def run_smoke(shim_url: str, automem_url: str, token: str) -> None:
    print(f"[1/5] /health round-trip", flush=True)
    health = _get_json(f"{shim_url}/health")
    assert health.get("status") == "ok", health

    print(f"[2/5] POST /memories (user_id={SMOKE_USER})", flush=True)
    add_resp = _post_json(f"{shim_url}/memories", {
        "user_id": SMOKE_USER,
        "messages": CONVERSATION,
        "timestamp": 1_700_000_000,
    })
    results = add_resp.get("results") or []
    assert len(results) == 1, f"expected 1 stored memory, got {len(results)}: {add_resp}"
    stored_id = results[0].get("id")
    assert stored_id, f"no id in add response: {add_resp}"
    stored_memory = results[0].get("memory") or ""
    assert SMOKE_CONTENT_HINT in stored_memory, f"expected conversation text to survive: got {stored_memory[:200]!r}"
    print(f"       stored memory id: {stored_id}", flush=True)

    print(f"[3/5] POST /search ({SMOKE_QUERY!r})", flush=True)
    search_resp = _post_json(f"{shim_url}/search", {
        "user_id": SMOKE_USER,
        "query": SMOKE_QUERY,
        "limit": 10,
    })
    hits = search_resp.get("results") or []
    assert hits, f"search returned no results: {search_resp}"
    top = hits[0]
    assert top.get("id") == stored_id, f"top hit id ({top.get('id')}) != stored id ({stored_id})"
    assert SMOKE_CONTENT_HINT in (top.get("memory") or ""), f"top hit missing {SMOKE_CONTENT_HINT}: {top}"
    print(f"       top hit score={top.get('score')} id={top.get('id')}", flush=True)

    print(f"[4/5] direct AutoMem recall confirms tag gate", flush=True)
    automem_params = urllib.parse.urlencode([("tags", SMOKE_USER), ("limit", "10"), ("query", "")])
    req = urllib.request.Request(
        f"{automem_url}/recall?{automem_params}",
        headers={"X-Api-Key": token},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        automem_resp = json.loads(r.read())
    tagged = automem_resp.get("results") or []
    assert len(tagged) >= 1, f"AutoMem /recall with tag={SMOKE_USER} returned nothing: {automem_resp}"
    print(f"       AutoMem sees {len(tagged)} memor{'y' if len(tagged) == 1 else 'ies'} under tag={SMOKE_USER}", flush=True)

    print(f"[5/5] DELETE /memories?user_id={SMOKE_USER}", flush=True)
    del_resp = _delete(f"{shim_url}/memories?user_id={urllib.parse.quote(SMOKE_USER)}")
    print(f"       {del_resp.get('message')}", flush=True)
    # Confirm the tag is actually empty on AutoMem now.
    with urllib.request.urlopen(
        urllib.request.Request(f"{automem_url}/recall?{automem_params}", headers={"X-Api-Key": token}),
        timeout=30,
    ) as r:
        after = json.loads(r.read())
    leftover = after.get("results") or []
    assert not leftover, f"cleanup left {len(leftover)} memories behind: {leftover}"
    print("       AutoMem confirms cleanup", flush=True)

    print("\nOK — shim round-trip passed.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shim-url", default="http://127.0.0.1:8888")
    ap.add_argument("--automem-url", default="http://localhost:8001")
    ap.add_argument("--token", default="test-token")
    ap.add_argument("--self-spawn", action="store_true", help="Spawn a shim on a free port instead of using --shim-url")
    args = ap.parse_args()

    proc: subprocess.Popen | None = None
    shim_url = args.shim_url
    try:
        if args.self_spawn:
            import socket as _socket
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            shim_url = f"http://127.0.0.1:{port}"
            proc = subprocess.Popen(
                [sys.executable, SHIM_PATH, "--host", "127.0.0.1", "--port", str(port),
                 "--upstream", args.automem_url, "--token", args.token],
                stdout=sys.stdout, stderr=sys.stderr,
            )
            wait_for_health(shim_url)
        else:
            wait_for_health(shim_url, timeout_s=3.0)

        run_smoke(shim_url, args.automem_url, args.token)
        return 0
    finally:
        if proc is not None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
