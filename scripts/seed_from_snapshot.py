#!/usr/bin/env python3
"""
Fast reseed from a previously captured embedding snapshot.

Unlike generate_corpus.py + seed_corpus.py (which hits OpenAI's embedding API
for every memory), this reseeds from data/seed_memories/corpus_v1.embedded.jsonl
(or another snapshot via --snapshot) with pre-computed vectors. Typical runtime
is seconds instead of minutes and costs $0 in embedding API credits.

Timestamps are rebased by default: `timestamp`, `t_valid` and `t_invalid` move
forward by whole days so the corpus generator's NOW lands on today, keeping the
corpus inside phase-2 `time_query` windows. See scripts/seed_rebase.py. Pass
--no-rebase to seed the stored dates, or --rebase-anchor to choose the instant
that becomes today.

Requirements:
  - Server volumes should be empty (memory_count == 0) before seeding, or you'll
    get duplicates. Use `docker compose down -v && docker compose up -d` in the
    automem repo to reset.

Usage:
  python3 scripts/seed_from_snapshot.py [--endpoint http://localhost:8001] [--token test-token]
  python3 scripts/seed_from_snapshot.py \
      --endpoint http://localhost:8011 \
      --manifest-output corpus_v1-8011.manifest.json
  python3 scripts/seed_from_snapshot.py \
      --endpoint http://localhost:8011 \
      --snapshot corpus_v2.embedded.jsonl \
      --manifest-output corpus_v2-8011.manifest.json
"""

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

from seed_rebase import add_rebase_args, corpus_key, plan_rebase, shift_entry

HERE = pathlib.Path(__file__).resolve().parent.parent
SEED_DIR = HERE / "data" / "seed_memories"
SNAPSHOT = SEED_DIR / "corpus_v1.embedded.jsonl"
MANIFEST = SEED_DIR / "corpus_v1.manifest.json"


def request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Api-Key": token},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def resolve_seed_path(value: str) -> pathlib.Path:
    """Bare filenames live under data/seed_memories/; paths are used as given."""
    path = pathlib.Path(value)
    if path.is_absolute() or path.parent != pathlib.Path("."):
        return path
    return SEED_DIR / path


def resolve_snapshot(value: str | None) -> pathlib.Path:
    return resolve_seed_path(value) if value else SNAPSHOT


def default_manifest_for(snapshot: pathlib.Path) -> pathlib.Path:
    """`corpus_v2.embedded.jsonl` -> data/seed_memories/corpus_v2.manifest.json."""
    return SEED_DIR / f"{corpus_key(snapshot)}.manifest.json"


def resolve_manifest_output(
    value: str | None, default: pathlib.Path = MANIFEST
) -> pathlib.Path:
    return resolve_seed_path(value) if value else default


def wait_for_enrichment(endpoint: str, token: str, expected_min: int) -> None:
    for i in range(60):
        h = request("GET", f"{endpoint}/health", token)
        enrich = h.get("enrichment", {})
        pending = enrich.get("pending", 0) + enrich.get("inflight", 0)
        mc = h.get("memory_count", 0)
        if i % 5 == 0:
            print(f"  [{i:2d}] memory_count={mc} pending={enrich.get('pending')} inflight={enrich.get('inflight')}")
        if mc >= expected_min and pending == 0:
            print("  enrichment drained")
            return
        time.sleep(1)
    print("  WARN: enrichment not fully drained within 60s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8001")
    ap.add_argument("--token", default="test-token")
    ap.add_argument(
        "--snapshot",
        default=None,
        help=(
            "Embedded snapshot to seed. Bare filenames are read from "
            "data/seed_memories/. Defaults to corpus_v1.embedded.jsonl."
        ),
    )
    ap.add_argument(
        "--manifest-output",
        default=None,
        help=(
            "Manifest output path. Bare filenames are written under "
            "data/seed_memories/. Defaults to <corpus>.manifest.json for the "
            "snapshot (corpus_v1.manifest.json for the default snapshot)."
        ),
    )
    add_rebase_args(ap)
    args = ap.parse_args()
    snapshot = resolve_snapshot(args.snapshot)
    manifest_path = resolve_manifest_output(
        args.manifest_output, default_manifest_for(snapshot)
    )

    if not snapshot.exists():
        print(f"snapshot not found: {snapshot}. run snapshot_corpus.py first.", file=sys.stderr)
        return 2

    t0 = time.time()
    h = request("GET", f"{args.endpoint}/health", args.token)
    if h.get("memory_count", 0) > 0:
        print(f"WARN: server already has {h['memory_count']} memories. Reseed will add more.", file=sys.stderr)

    entries = [json.loads(l) for l in snapshot.read_text().splitlines() if l.strip()]
    print(f"reseeding {len(entries)} memories from {snapshot.name} (with precomputed embeddings)")
    shift_days = plan_rebase(args, snapshot, entries)
    entries = [shift_entry(e, shift_days) for e in entries]

    manifest: dict[str, list[str]] = {}
    scenario_to_mids: dict[str, list[str]] = {}
    failures = 0

    for i, e in enumerate(entries):
        payload = {
            "content": e["content"],
            "tags": e["tags"],
            "type": e["type"],
            "importance": e["importance"],
            "confidence": e.get("confidence", 0.9),
            "timestamp": e.get("timestamp"),
            "metadata": {
                "synthetic": True,
                "hits_scenarios": e["metadata"].get("hits_scenarios", []),
            },
            "embedding": e["embedding"],
        }
        if e.get("t_valid"):
            payload["t_valid"] = e["t_valid"]
        if e.get("t_invalid"):
            payload["t_invalid"] = e["t_invalid"]
        try:
            resp = request("POST", f"{args.endpoint}/memory", args.token, payload)
            mid = resp.get("memory_id") or resp.get("id")
            if not mid:
                failures += 1
                continue
            hits = e["metadata"].get("hits_scenarios", [])
            manifest[mid] = hits
            for s in hits:
                scenario_to_mids.setdefault(s, []).append(mid)
            if (i + 1) % 20 == 0:
                print(f"  stored {i+1}/{len(entries)} in {time.time()-t0:.1f}s")
        except urllib.error.HTTPError as ex:
            body = ex.read().decode(errors="replace")[:200]
            print(f"  [{i+1}] HTTP {ex.code}: {body}")
            failures += 1
        except Exception as ex:
            print(f"  [{i+1}] error: {ex}")
            failures += 1

    elapsed = time.time() - t0
    print(f"stored {len(manifest)}/{len(entries)} in {elapsed:.1f}s (failures: {failures})")

    print("waiting for enrichment")
    wait_for_enrichment(args.endpoint, args.token, expected_min=len(manifest))

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "memory_to_scenarios": manifest,
        "scenario_to_memories": scenario_to_mids,
    }, indent=2))
    try:
        display = manifest_path.relative_to(HERE)
    except ValueError:
        display = manifest_path
    print(f"manifest: {display}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
