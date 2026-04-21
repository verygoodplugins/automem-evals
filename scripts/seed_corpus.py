#!/usr/bin/env python3
"""
Seed a JSONL corpus into the local AutoMem server.

  - Reads: data/seed_memories/corpus_v1.jsonl
  - Writes: data/seed_memories/corpus_v1.manifest.json (memory_id → scenario hits)
  - Waits for embedding enrichment to drain before returning.

Usage:
  python3 scripts/seed_corpus.py [--endpoint http://localhost:8001] [--token test-token]
"""

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent


def request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": token,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def wait_for_enrichment(endpoint: str, token: str, expected_min: int) -> None:
    """Poll /health until enrichment queue is drained AND memory_count reached."""
    last_pending = None
    for i in range(180):  # up to 3 min
        try:
            h = request("GET", f"{endpoint}/health", token)
        except Exception as e:
            print(f"  health poll error ({e}); retrying")
            time.sleep(2)
            continue
        enrich = h.get("enrichment", {})
        mc = h.get("memory_count", 0)
        pending = enrich.get("pending", 0) + enrich.get("inflight", 0)
        if pending != last_pending or i % 10 == 0:
            print(f"  [{i:3d}] memory_count={mc} enrichment.pending={enrich.get('pending')} inflight={enrich.get('inflight')} processed={enrich.get('processed')}")
            last_pending = pending
        if mc >= expected_min and pending == 0:
            print("  enrichment drained")
            return
        time.sleep(1)
    print("  WARN: enrichment did not fully drain within timeout; continuing")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8001")
    ap.add_argument("--token", default="test-token")
    ap.add_argument("--corpus", default="corpus_v1.jsonl",
                    help="Corpus filename under data/seed_memories/ (default: corpus_v1.jsonl)")
    args = ap.parse_args()

    CORPUS = HERE / "data" / "seed_memories" / args.corpus
    MANIFEST = HERE / "data" / "seed_memories" / args.corpus.replace(".jsonl", ".manifest.json")

    if not CORPUS.exists():
        print(f"corpus not found: {CORPUS}. run scripts/generate_corpus*.py first.", file=sys.stderr)
        return 2

    # Verify server is up
    try:
        h = request("GET", f"{args.endpoint}/health", args.token)
        print(f"server: falkordb={h.get('falkordb')} qdrant={h.get('qdrant')} existing_count={h.get('memory_count')}")
    except Exception as e:
        print(f"server not reachable at {args.endpoint}: {e}", file=sys.stderr)
        return 2

    memories = [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]
    print(f"seeding {len(memories)} memories")

    manifest: dict[str, list[str]] = {}  # memory_id → scenario_hits
    scenario_to_mids: dict[str, list[str]] = {}  # scenario_id → [memory_id]

    failures = 0
    for i, m in enumerate(memories):
        try:
            resp = request("POST", f"{args.endpoint}/memory", args.token, m)
            mid = resp.get("memory_id") or resp.get("id")
            if not mid:
                print(f"  [{i+1}] no memory_id in response: {resp}")
                failures += 1
                continue
            hits = m.get("metadata", {}).get("hits_scenarios", [])
            manifest[mid] = hits
            for s in hits:
                scenario_to_mids.setdefault(s, []).append(mid)
            if (i + 1) % 10 == 0:
                print(f"  stored {i+1}/{len(memories)}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            print(f"  [{i+1}] HTTP {e.code}: {body}")
            failures += 1
        except Exception as e:
            print(f"  [{i+1}] error: {e}")
            failures += 1

    print(f"stored {len(manifest)}/{len(memories)} (failures: {failures})")

    print("waiting for enrichment to drain")
    wait_for_enrichment(args.endpoint, args.token, expected_min=len(manifest))

    MANIFEST.write_text(json.dumps({
        "memory_to_scenarios": manifest,
        "scenario_to_memories": scenario_to_mids,
    }, indent=2))
    print(f"manifest: {MANIFEST.relative_to(HERE)}")
    print(f"scenarios mapped: {list(scenario_to_mids.keys())}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
