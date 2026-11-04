#!/usr/bin/env python3
"""Measurement tooling for the Meilisearch backend bench (issue #83).

Free, deterministic pieces only: latency percentiles, resource probes, a LoCoMo evidence
hit-rate probe over AutoMem's ``/recall``, and the $20 spend gate. No LLM judge is called here.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any, Optional

CAP_USD = Decimal("20")


class BudgetExceeded(RuntimeError):
    pass


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (no interpolation, so p99 of 100 samples is the 99th value)."""
    if not values:
        raise ValueError("no samples")
    ordered = sorted(values)
    rank = max(1, -(-int(p * len(ordered)) // 100)) if p < 100 else len(ordered)
    return ordered[min(rank, len(ordered)) - 1]


def latency_summary(ms: list[float]) -> dict[str, float]:
    return {"n": len(ms), "p50_ms": percentile(ms, 50), "p95_ms": percentile(ms, 95),
            "p99_ms": percentile(ms, 99), "mean_ms": sum(ms) / len(ms), "max_ms": max(ms)}


def check_budget(spent_usd: Any, per_run_usd: Any, remaining_runs: int, cap_usd: Any = CAP_USD) -> dict[str, str]:
    """Raise BudgetExceeded if spent + remaining x smoke-estimated per-run cost passes the cap."""
    spent, per_run, cap = Decimal(str(spent_usd)), Decimal(str(per_run_usd)), Decimal(str(cap_usd))
    projected = spent + per_run * remaining_runs
    report = {"spent_usd": str(spent), "per_run_usd": str(per_run), "remaining_runs": str(remaining_runs),
              "projected_usd": str(projected), "cap_usd": str(cap)}
    if projected > cap:
        raise BudgetExceeded(f"projected ${projected} exceeds cap ${cap}: stop and report ({report})")
    return report


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def _mib(text: str) -> float:
    num, unit = re.match(r"([\d.]+)\s*([KMG]i?B)", text).groups()
    return float(num) * {"KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024}[unit]


def container_rss_mib(project: str) -> dict[str, float]:
    """RSS-equivalent (docker stats MemUsage, excludes page cache) per container of a compose project."""
    out = _run(["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}"])
    return {n: round(_mib(m.split("/")[0].strip()), 1) for n, m in (l.split("\t") for l in out.splitlines()) if n.startswith(project)}


def dir_size_mib(container: str, path: str) -> float:
    return round(int(_run(["docker", "exec", container, "du", "-sk", path]).split()[0]) / 1024, 2)


DISK_PATHS = {"qdrant": "/qdrant/storage", "falkordb": "/var/lib/falkordb/data", "meilisearch": "/meili_data"}


def disk_footprint_mib(project: str) -> dict[str, Optional[float]]:
    """On-disk size of each store's data dir (None if the path is absent in that image)."""
    out: dict[str, Optional[float]] = {}
    for svc, path in DISK_PATHS.items():
        try:
            out[svc] = dir_size_mib(f"{project}-{svc}-1", path)
        except subprocess.CalledProcessError:
            out[svc] = None
    return out


def leg_timings(container: str, reset: bool = False) -> dict[str, dict[str, float]]:
    """Store-side leg latency recorded in-process by meili_launch (reset=True clears the file)."""
    path = "/tmp/leg_timings.jsonl"
    if reset:
        _run(["docker", "exec", container, "sh", "-c", f": > {path}"])
        return {}
    rows = [json.loads(l) for l in _run(["docker", "exec", container, "cat", path]).splitlines() if l]
    legs: dict[str, list[float]] = {}
    for row in rows:
        legs.setdefault(row["leg"], []).append(row["ms"])
    return {leg: latency_summary(ms) for leg, ms in legs.items()}


def _recall(endpoint: str, token: str, query: str, limit: int) -> tuple[list[dict], float]:
    url = f"{endpoint}/recall?" + urllib.parse.urlencode({"query": query, "limit": limit})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    return body.get("results", []), (time.perf_counter() - start) * 1000


def _post(endpoint: str, token: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(endpoint + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def locomo_turns(conv: dict) -> list[tuple[str, str, str]]:
    """(dia_id, timestamp-ish session label, 'Speaker: text') for every turn of one LoCoMo conversation."""
    c, out = conv["conversation"], []
    for key in sorted((k for k in c if re.fullmatch(r"session_\d+", k)), key=lambda k: int(k.split("_")[1])):
        for turn in c[key]:
            out.append((turn["dia_id"], c.get(f"{key}_date_time", ""), f"{turn['speaker']}: {turn['text']}"))
    return out


def locomo_ingest(endpoint: str, token: str, conv: dict, tag: str) -> dict:
    """Seed one LoCoMo conversation; returns ingestion wall time to the point /health is queue-drained."""
    start, turns = time.perf_counter(), locomo_turns(conv)
    for dia_id, when, text in turns:
        _post(endpoint, token, "/memory", {"content": text, "tags": [tag, f"dia:{dia_id.lower()}"], "importance": 0.5,
                                           "metadata": {"dia_id": dia_id, "session_date": when}})
    ingest_s = time.perf_counter() - start
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:  # wait for vector writes AND enrichment (it also hits the vector store)
        health = json.load(urllib.request.urlopen(urllib.request.Request(endpoint + "/health"), timeout=30))
        busy = sum(health.get(q, {}).get(k, 0) for q in ("embedding", "enrichment") for k in ("queue_depth", "inflight", "pending"))
        if health.get("memory_count") == health.get("vector_count") and not busy:
            break
        time.sleep(1)
    return {"turns": len(turns), "post_s": round(ingest_s, 2), "drained_s": round(time.perf_counter() - start, 2)}


def locomo_eval(endpoint: str, token: str, conv: dict, top_k: int, repeat: int = 1) -> dict:
    """Evidence hit-rate: a question hits if any gold evidence turn is in the top-k recall results."""
    per_cat: dict[int, list[int]] = {}
    latencies: list[float] = []
    for qa in conv["qa"]:
        gold = {f"dia:{e.lower()}" for e in qa.get("evidence", []) if re.fullmatch(r"D\d+:\d+", e)}
        if not gold or qa.get("category") == 5:  # skip adversarial (no gold evidence) like the official scorer
            continue
        for i in range(repeat):
            results, ms = _recall(endpoint, token, qa["question"], top_k)
            latencies.append(ms)
        got = {t.lower() for r in results for t in (r.get("memory") or {}).get("tags", [])}
        per_cat.setdefault(qa["category"], []).append(int(bool(gold & got)))
    flat = [h for v in per_cat.values() for h in v]
    return {"questions": len(flat), "evidence_hit_rate": round(sum(flat) / len(flat), 4), "top_k": top_k,
            "by_category": {c: {"n": len(v), "hit_rate": round(sum(v) / len(v), 4)} for c, v in sorted(per_cat.items())},
            "latency": latency_summary(latencies), "official_locomo_score": False,
            "note": "retrieval proxy over one conversation; no LLM judge"}


def load_burst(endpoint: str, token: str, queries: list[str], top_k: int, workers: int = 8, rounds: int = 3) -> dict:
    with ThreadPoolExecutor(workers) as pool:
        times = list(pool.map(lambda q: _recall(endpoint, token, q, top_k)[1], queries * rounds))
    return latency_summary(times)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lo = sub.add_parser("locomo", help="ingest + evaluate one LoCoMo conversation")
    lo.add_argument("--data", required=True)
    lo.add_argument("--conv", type=int, default=0)
    lo.add_argument("--endpoint", required=True, help="explicit; the 8001 default would hit a real stack")
    lo.add_argument("--token", default="test-token")
    lo.add_argument("--top-k", type=int, default=10)
    lo.add_argument("--project", required=True, help="compose project name, for RSS probes")
    lo.add_argument("--out", required=True)
    lo.add_argument("--meili-url", default=None, help="record pinned version + effective index settings")
    lo.add_argument("--meili-key", default="bench-master-key")
    bud = sub.add_parser("budget", help="check projected spend against the cap")
    bud.add_argument("--spent", required=True)
    bud.add_argument("--per-run", required=True)
    bud.add_argument("--remaining-runs", type=int, required=True)
    args = ap.parse_args(argv)

    if args.cmd == "budget":
        print(json.dumps(check_budget(args.spent, args.per_run, args.remaining_runs), indent=2))
        return 0
    conv = json.load(open(args.data))[args.conv]
    result: dict[str, Any] = {"benchmark": "locomo-retrieval-proxy", "conv": args.conv}
    api = f"{args.project}-flask-api-1"
    result["ingest"] = locomo_ingest(args.endpoint, args.token, conv, tag=f"locomo-{args.conv}")
    result["rss_idle_mib"] = container_rss_mib(args.project)  # post-ingest, queues drained, no traffic
    result["disk_mib"] = disk_footprint_mib(args.project)
    if args.meili_url:
        import meili_backend as mb

        meili = mb.MeiliClient(args.meili_url, args.meili_key)
        result["meili"] = {i["uid"]: meili.provenance(i["uid"]) for i in meili.request("GET", "/indexes")["results"]}
    leg_timings(api, reset=True)
    result["eval"] = locomo_eval(args.endpoint, args.token, conv, args.top_k)
    result["leg_latency_serial"] = leg_timings(api)
    leg_timings(api, reset=True)
    queries = [qa["question"] for qa in conv["qa"]][:40]
    result["load_burst"] = load_burst(args.endpoint, args.token, queries, args.top_k)
    result["leg_latency_load"] = leg_timings(api)
    result["rss_load_mib"] = container_rss_mib(args.project)
    json.dump(result, open(args.out, "w"), sort_keys=True)  # one line: result files count toward PR size
    print(json.dumps({k: result[k] for k in ("ingest", "load_burst")} | {"hit_rate": result["eval"]["evidence_hit_rate"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
