#!/usr/bin/env python3
"""Container entrypoint: install the selected retrieval arm, then run AutoMem's app.py.

``MEILI_ARM`` = ``baseline`` (untouched Qdrant + FalkorDB) | ``keyword_swap``.
Patches land before ``app`` is imported, so ``from ... import _graph_keyword_search`` and
``qdrant_client_cls=QdrantClient`` bind the replacements; AutoMem's scorer is never edited.

Every arm (baseline included) gets the same timing wrappers around the keyword function and
``search()``. They record store-side leg latency, which excludes the query-embedding time that
dominates end-to-end ``/recall`` when embeddings are local and is identical across arms.
"""

from __future__ import annotations

import faulthandler
import json
import os
import runpy
import signal
import sys
import threading
import time

sys.path.insert(0, os.getcwd())  # /app, so `import automem` resolves
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meili_backend as mb  # noqa: E402

TIMING_FILE = os.environ.get("MEILI_TIMING_FILE", "/tmp/leg_timings.jsonl")
_lock = threading.Lock()


def record(leg: str, started: float) -> None:
    line = json.dumps({"leg": leg, "ms": (time.perf_counter() - started) * 1000})
    with _lock, open(TIMING_FILE, "a") as fh:
        fh.write(line + "\n")


def timed(leg: str, fn):
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            record(leg, started)

    return wrapper


class TimedClient:
    """Proxy for whichever vector client the arm uses; times only ``search``."""

    def __init__(self, inner):
        self._inner = inner
        self.search = timed("vector_search", inner.search)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install(arm: str) -> None:
    if arm not in {"baseline", "keyword_swap"}:
        raise SystemExit(f"unknown MEILI_ARM={arm!r}")
    import qdrant_client as qc

    import automem.search.runtime_recall_helpers as h

    client = mb.MeiliClient(os.environ.get("MEILI_URL", "http://meilisearch:7700"), os.environ.get("MEILI_MASTER_KEY"))
    real_cls, make = qc.QdrantClient, None
    if arm == "keyword_swap":
        index = os.environ.get("MEILI_INDEX", "automem_keyword")
        client.ensure_index(index)
        strategy = os.environ.get("MEILI_MATCHING_STRATEGY") or mb.MATCHING_STRATEGY
        h._graph_keyword_search = mb.make_keyword_search(client, index, h._graph_keyword_search, strategy)
        make = lambda *a, **k: mb.MirrorQdrant(real_cls(*a, **k), client, index)  # noqa: E731
    else:
        make = real_cls
    h._graph_keyword_search = timed("keyword_leg", h._graph_keyword_search)
    if os.environ.get("MEILI_KEYWORD_ONLY"):
        # recall only calls the keyword leg for slots the vector leg leaves empty (recall.py: remaining_slots),
        # so to measure the leg itself the vector leg is forced to return nothing.
        h._vector_search = lambda *a, **k: []
    qc.QdrantClient = lambda *a, **k: TimedClient(make(*a, **k))
    print(f"[meili_launch] arm={arm} meili={mb.PINNED_VERSION}", flush=True)


if __name__ == "__main__":
    faulthandler.register(signal.SIGUSR1, all_threads=True)  # `docker kill -s USR1`: thread stacks to docker logs
    install(os.environ.get("MEILI_ARM", "baseline"))
    sys.argv = ["app.py"]
    runpy.run_path(os.path.join(os.getcwd(), "app.py"), run_name="__main__")
