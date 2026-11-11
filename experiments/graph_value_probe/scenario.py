"""Run paired graph expansion probes against an isolated, seeded API."""

import hashlib
import json
import statistics
import time
import urllib.parse
import urllib.request

from falkordb import FalkorDB
from fastembed import TextEmbedding

BASE = "http://127.0.0.1:8001"
TOKEN = "graph-value-fixture-token"
MODEL = TextEmbedding(
    model_name="BAAI/bge-base-en-v1.5", cache_dir="/experiment/models", threads=1
)


def vector(text):
    return next(MODEL.embed([text])).tolist()


def request(path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Api-Key": TOKEN, "Content-Type": "application/json"},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as response:
        data = response.read()
        return json.loads(data), (time.perf_counter() - start) * 1000, len(data)


def fixture():
    docs = [
        (
            "single",
            "graph-single",
            "The ember plan owner is Mara; lookup ember plan owner.",
        ),
        (
            "single-noise",
            "graph-single",
            "The neighboring service rotates backups each Tuesday.",
        ),
        (
            "linked-seed",
            "graph-linked",
            "Atlas relay uses a special shipping profile; lookup atlas relay.",
        ),
        (
            "linked-fact",
            "graph-linked",
            "The shipping permit signature is cobalt quartz.",
        ),
        (
            "scope-seed",
            "graph-scope",
            "The meadow project owner is Nia; lookup meadow project owner.",
        ),
        ("foreign", "graph-foreign", "The other project's secret code is cedar jade."),
        (
            "history-seed",
            "graph-history",
            "The north deployment handbook notes a migration; lookup north deployment handbook.",
        ),
        ("old", "graph-history", "The former deployment region was west-south."),
        ("new", "graph-history", "The current deployment region is east-north."),
    ]
    for i in range(14):
        docs.append(
            (
                f"distractor-{i}",
                "graph-linked",
                f"Atlas relay shipping profile planning note {i}; routine tasks and review.",
            )
        )
    queries = [
        {
            "name": "single",
            "scope": "graph-single",
            "query": "ember plan owner",
            "expected": ["single"],
        },
        {
            "name": "linked",
            "scope": "graph-linked",
            "query": "atlas relay shipping profile",
            "expected": ["linked-seed", "linked-fact"],
        },
        {
            "name": "scope",
            "scope": "graph-scope",
            "query": "meadow project owner",
            "expected": ["scope-seed"],
        },
        {
            "name": "negative",
            "scope": "graph-single",
            "query": "ember plan secret destination",
            "expected": [],
        },
        {
            "name": "current",
            "scope": "graph-history",
            "query": "north deployment handbook",
            "expected": ["history-seed", "new"],
            "current": True,
        },
        {
            "name": "history",
            "scope": "graph-history",
            "query": "north deployment handbook",
            "expected": ["history-seed", "old"],
            "current": False,
        },
    ]
    edges = [
        ("single", "single-noise", "RELATES_TO"),
        ("linked-seed", "linked-fact", "RELATES_TO"),
        ("scope-seed", "foreign", "RELATES_TO"),
        ("history-seed", "old", "RELATES_TO"),
        ("history-seed", "new", "RELATES_TO"),
        ("old", "new", "INVALIDATED_BY"),
    ]
    return docs, queries, edges


def id_of(row):
    return str(row.get("id") or (row.get("memory") or {}).get("id") or "")


def measure(rows, query, inverse, scopes, budget=200):
    """Treat whitespace words as an explicit context-budget proxy, not model tokens."""
    expected = set(query["expected"])
    ranks = [inverse.get(id_of(row), "unknown") for row in rows]
    all_rank = (
        max((ranks.index(x) + 1 for x in expected), default=None)
        if expected.issubset(ranks)
        else None
    )
    words, visible, inline_foreign, inline_stale = 0, set(), 0, 0
    for row in rows:
        memory = row.get("memory") or {}
        segments = [(id_of(row), memory.get("content") or "")]
        for rel in row.get("relations") or []:
            target = rel.get("memory") or {}
            if target.get("content") or target.get("summary"):
                segments.append(
                    (
                        str(target.get("id") or ""),
                        target.get("content") or target.get("summary") or "",
                    )
                )
        for mid, text in segments:
            count = len(str(text).split())
            if words + count > budget:
                continue
            words += count
            key = inverse.get(mid, "unknown")
            visible.add(key)
            if mid != id_of(row):
                inline_foreign += scopes.get(key) != query["scope"]
                inline_stale += bool(query.get("current", True) and key == "old")
    return {
        "all_rank": all_rank,
        "top5_all": bool(expected and all_rank is not None and all_rank <= 5),
        "top10_all": bool(expected and all_rank is not None and all_rank <= 10),
        "context_all": bool(expected and expected.issubset(visible)),
        "context_words": words,
        "off_label": sum(key not in expected for key in ranks),
        "result_count": len(ranks),
        "foreign_top": sum(scopes.get(key) != query["scope"] for key in ranks),
        "stale_top": (
            sum(key == "old" for key in ranks) if query.get("current", True) else 0
        ),
        "foreign_inline": inline_foreign,
        "stale_inline": inline_stale,
    }


def main():
    docs, queries, edges = fixture()
    ids, scopes = {}, {key: scope for key, scope, _ in docs}
    for key, scope, content in docs:
        payload = {
            "content": content,
            "tags": [scope],
            "type": "Context",
            "importance": 0.5,
            "timestamp": "2022-01-01T00:00:00Z",
            "embedding": vector(content),
        }
        if key == "old":
            payload["t_invalid"] = "2021-01-01T00:00:00Z"
        result, _, _ = request("/memory", payload)
        if result.get("qdrant") != "stored" or not result.get("memory_id"):
            raise RuntimeError("fixture memory was not stored in both backends")
        ids[key] = result["memory_id"]
    health, _, _ = request("/health")
    if health.get("memory_count") != len(docs) or health.get("vector_count") != len(
        docs
    ):
        raise RuntimeError("graph/vector corpus mismatch")
    for source, target, kind in edges:
        request(
            "/associate",
            {
                "memory1_id": ids[source],
                "memory2_id": ids[target],
                "type": kind,
                "strength": 0.8,
            },
        )
    graph = FalkorDB(host="falkordb", port=6379).select_graph("memories")

    def snapshot():
        rows = graph.query(
            "MATCH (m:Memory) RETURN m.id, m.last_accessed ORDER BY m.id"
        ).result_set
        return hashlib.sha256(json.dumps(rows).encode()).hexdigest()

    before = snapshot()
    inverse = {value: key for key, value in ids.items()}
    output = []
    for idx, query in enumerate(queries):
        embed = ",".join(map(str, vector(query["query"])))
        for limit in (5, 10):
            # Alternate order to reduce fixed warm-cache order bias.
            order = (False, True) if (idx + limit) % 2 else (True, False)
            for expansion in order:
                params = {
                    "query": query["query"],
                    "tags": query["scope"],
                    "tag_match": "exact",
                    "limit": limit,
                    "expand_relations": str(expansion).lower(),
                    "expand_respect_tags": "true",
                    "relation_limit": 5,
                    "expansion_limit": 5,
                    "adaptive_floor": "false",
                    "auto_decompose": "false",
                    "min_score": 0,
                    "current_only": str(query.get("current", True)).lower(),
                    "recency_bias": "off",
                    "embedding": embed,
                }
                response, elapsed, size = request(
                    "/recall?" + urllib.parse.urlencode(params)
                )
                rows = response.get("results") or []
                summary = measure(rows, query, inverse, scopes)
                summary.update(
                    {
                        "scenario": query["name"],
                        "limit": limit,
                        "expand": expansion,
                        "http_ms": round(elapsed, 3),
                        "response_bytes": size,
                    }
                )
                output.append(summary)
    after = snapshot()
    if before != after:
        raise RuntimeError("last_accessed changed during paired recall")
    result = {
        "fixture_sha256": hashlib.sha256(
            json.dumps([docs, queries, edges], sort_keys=True).encode()
        ).hexdigest(),
        "memories": len(docs),
        "relations": len(edges),
        "access_updates_disabled": True,
        "access_snapshot_unchanged": True,
        "word_budget": 200,
        "rows": output,
        "latency_median_ms": round(statistics.median(r["http_ms"] for r in output), 3),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
