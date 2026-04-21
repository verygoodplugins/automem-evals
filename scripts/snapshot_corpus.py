#!/usr/bin/env python3
"""
Snapshot a seeded corpus with embeddings for fast, offline, reproducible reseeding.

Reads every memory_id from data/seed_memories/corpus_v1.manifest.json, pulls the
full memory object from /memory/<id>, and pulls the 1024-dim vector from Qdrant
directly. Writes a combined snapshot so a later reseed does not need to call the
OpenAI (or any) embedding API again.

Usage:
  python3 scripts/snapshot_corpus.py
"""

import json
import pathlib
import sys
import urllib.request

import argparse

HERE = pathlib.Path(__file__).resolve().parent.parent
API = "http://localhost:8001"
QDRANT = "http://localhost:6333"
QDRANT_COLLECTION = "memories"


def http_get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus_v1",
                    help="Corpus base name, e.g. 'corpus_v1' or 'corpus_v2' (no suffix)")
    args = ap.parse_args()
    MANIFEST = HERE / "data" / "seed_memories" / f"{args.corpus}.manifest.json"
    SNAPSHOT = HERE / "data" / "seed_memories" / f"{args.corpus}.embedded.jsonl"

    manifest = json.loads(MANIFEST.read_text())
    memory_ids = list(manifest["memory_to_scenarios"].keys())
    print(f"snapshotting {len(memory_ids)} memories")

    snapshot: list[dict] = []
    for i, mid in enumerate(memory_ids):
        try:
            mem = http_get(f"{API}/memory/{mid}", {"X-Api-Key": "test-token"})["memory"]
        except Exception as e:
            print(f"  [{i+1}] failed to GET memory: {e}")
            continue

        try:
            qres = http_get(f"{QDRANT}/collections/{QDRANT_COLLECTION}/points/{mid}?with_vector=true")
            vector = qres["result"]["vector"]
        except Exception as e:
            print(f"  [{i+1}] failed to GET qdrant vector: {e}")
            vector = None

        # Preserve the seed-time scenario hits (manifest) even though we re-fetched
        # server-enriched metadata that replaces the original metadata block.
        hits = manifest["memory_to_scenarios"].get(mid, [])
        meta = mem.get("metadata") or {}
        meta["hits_scenarios"] = hits
        meta["synthetic"] = True

        entry = {
            "memory_id": mid,
            "content": mem["content"],
            "tags": mem.get("tags") or [],
            "type": mem.get("type") or "Context",
            "importance": mem.get("importance", 0.5),
            "confidence": mem.get("confidence", 0.9),
            "timestamp": mem.get("timestamp"),
            "t_valid": mem.get("t_valid"),
            "t_invalid": mem.get("t_invalid"),
            "metadata": meta,
            "embedding": vector,
        }
        snapshot.append(entry)
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(memory_ids)}]")

    with SNAPSHOT.open("w") as f:
        for e in snapshot:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    missing_vec = sum(1 for e in snapshot if not e.get("embedding"))
    size_mb = SNAPSHOT.stat().st_size / 1024 / 1024
    print(f"wrote {len(snapshot)} entries to {SNAPSHOT.relative_to(HERE)} ({size_mb:.1f} MB)")
    if missing_vec:
        print(f"WARN: {missing_vec} entries missing embedding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
