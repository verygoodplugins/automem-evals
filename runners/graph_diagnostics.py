#!/usr/bin/env python3
"""
Read-only diagnostics for local AutoMem graph health.

The runner compares one or more local AutoMem endpoints, stores raw health,
/graph/stats, and optional Docker-side deep probes, then writes a markdown
report focused on graph shape and clustering-threshold evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import random
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_ENDPOINTS = [
    ("full", "http://localhost:8001"),
    ("cleaned", "http://localhost:8011"),
]
DEFAULT_CONTAINERS = {
    "full": "automem-flask-api-1",
    "cleaned": "automem-script-test-flask-api-1",
}
DEFAULT_THRESHOLDS = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]

AUTHORABLE_RELATIONS = {
    "RELATES_TO",
    "LEADS_TO",
    "OCCURRED_BEFORE",
    "PREFERS_OVER",
    "EXEMPLIFIES",
    "CONTRADICTS",
    "REINFORCES",
    "INVALIDATED_BY",
    "EVOLVED_INTO",
    "DERIVED_FROM",
    "PART_OF",
}
SYSTEM_RELATIONS = {
    "SIMILAR_TO",
    "PRECEDED_BY",
    "DISCOVERED",
    "EXPLAINS",
    "SHARES_THEME",
    "PARALLEL_CONTEXT",
    "SUMMARIZES",
}
LEGACY_DISCOVERED_RELATIONS = {"EXPLAINS", "SHARES_THEME", "PARALLEL_CONTEXT"}
SUPERSESSION_RELATIONS = {"INVALIDATED_BY", "PREFERS_OVER"}


def is_local_endpoint(endpoint: str) -> bool:
    parsed = urllib.parse.urlparse(endpoint)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def assert_local_endpoint(endpoint: str) -> None:
    if not is_local_endpoint(endpoint):
        raise SystemExit(f"refusing non-local endpoint: {endpoint}")


def parse_label_value(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError("expected LABEL=VALUE")
    label, value = spec.split("=", 1)
    label = label.strip()
    value = value.strip()
    if not label or not value:
        raise argparse.ArgumentTypeError("expected non-empty LABEL=VALUE")
    return label, value


def parse_thresholds(raw: str) -> list[float]:
    thresholds = []
    for item in raw.split(","):
        value = item.strip()
        if value:
            thresholds.append(float(value))
    if not thresholds:
        raise argparse.ArgumentTypeError("at least one threshold is required")
    return thresholds


def endpoint_slug(endpoint: str) -> str:
    parsed = urllib.parse.urlparse(endpoint)
    host = parsed.hostname or "unknown"
    port = f"-{parsed.port}" if parsed.port else ""
    return f"{host}{port}".replace(":", "-")


def http_get_json(endpoint: str, token: str, path: str) -> dict[str, Any]:
    url = f"{endpoint.rstrip('/')}{path}"
    req = urllib.request.Request(url, headers={"X-Api-Key": token})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def safe_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def classify_relationship(relation_type: str) -> str:
    normalized = relation_type.upper()
    if normalized in SYSTEM_RELATIONS:
        return "system"
    if normalized in AUTHORABLE_RELATIONS:
        return "authorable"
    return "unknown"


def summarize_graph_shape(stats: dict[str, Any]) -> dict[str, Any]:
    totals = stats.get("totals") or {}
    rel_counts = {str(k): safe_count(v) for k, v in (stats.get("by_relationship") or {}).items()}
    type_counts = {str(k): safe_count(v) for k, v in (stats.get("by_type") or {}).items()}

    total_edges = safe_count(totals.get("edges")) or sum(rel_counts.values())
    total_nodes = safe_count(totals.get("nodes")) or sum(type_counts.values())
    system_edges = sum(count for rel, count in rel_counts.items() if classify_relationship(rel) == "system")
    author_edges = sum(
        count for rel, count in rel_counts.items() if classify_relationship(rel) == "authorable"
    )
    unknown_edges = max(0, total_edges - system_edges - author_edges)
    legacy_discovered = sum(rel_counts.get(rel, 0) for rel in LEGACY_DISCOVERED_RELATIONS)
    discovered_total = rel_counts.get("DISCOVERED", 0) + legacy_discovered
    supersession_edges = sum(rel_counts.get(rel, 0) for rel in SUPERSESSION_RELATIONS)
    generic_memory_count = type_counts.get("Memory", 0)

    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "system_edges": system_edges,
        "system_edge_share": ratio(system_edges, total_edges),
        "author_edges": author_edges,
        "author_edge_share": ratio(author_edges, total_edges),
        "unknown_edges": unknown_edges,
        "unknown_edge_share": ratio(unknown_edges, total_edges),
        "generic_memory_count": generic_memory_count,
        "generic_memory_share": ratio(generic_memory_count, total_nodes),
        "legacy_discovered_count": legacy_discovered,
        "discovered_total": discovered_total,
        "legacy_discovered_share": ratio(legacy_discovered, discovered_total),
        "invalidated_by": rel_counts.get("INVALIDATED_BY", 0),
        "prefers_over": rel_counts.get("PREFERS_OVER", 0),
        "supersession_edges": supersession_edges,
        "relationship_counts": rel_counts,
        "type_counts": type_counts,
    }


def graph_shape_risks(shape: dict[str, Any], deep_probe: dict[str, Any] | None = None) -> list[str]:
    risks: list[str] = []
    if shape["generic_memory_share"] >= 0.50:
        risks.append("high generic Memory type share")
    elif shape["generic_memory_share"] >= 0.30:
        risks.append("elevated generic Memory type share")

    if shape["system_edge_share"] >= 0.80:
        risks.append("system-generated edges dominate the graph")
    elif shape["system_edge_share"] >= 0.70:
        risks.append("system-generated edges are the majority")

    if shape["author_edge_share"] < 0.05:
        risks.append("very sparse authorable edges")
    elif shape["author_edge_share"] < 0.10:
        risks.append("sparse authorable edges")

    supersession_floor = max(10, int(shape["total_nodes"] * 0.005))
    if shape["supersession_edges"] < supersession_floor:
        risks.append("INVALIDATED_BY/PREFERS_OVER barely fire")

    if shape["legacy_discovered_share"] >= 0.50:
        risks.append("legacy discovered relation types dominate discovered edges")

    legacy = (deep_probe or {}).get("legacy_relation_similarity") or {}
    parallel = legacy.get("PARALLEL_CONTEXT") or {}
    if parallel.get("count") and parallel.get("zero_similarity_share") == 1:
        risks.append("legacy PARALLEL_CONTEXT similarities are all zero")

    return risks


def percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = round((percent / 100) * (len(ordered) - 1))
    return ordered[min(len(ordered) - 1, idx)]


def threshold_evidence(deep_probe: dict[str, Any] | None) -> dict[str, Any]:
    if not deep_probe:
        return {"status": "missing", "summary": "deep probe skipped"}
    probe = deep_probe.get("threshold_probe") or {}
    counts = probe.get("top_k_neighbor_edges_at_thresholds") or {}
    if not counts:
        return {"status": "missing", "summary": "threshold probe unavailable"}

    def count_at(threshold: str) -> int:
        return safe_count(counts.get(threshold))

    at_65 = count_at("0.65")
    at_75 = count_at("0.75")
    lift = ratio(at_65 - at_75, at_75) if at_75 else 0.0
    top1 = probe.get("top1_similarity") or {}
    median = top1.get("p50")

    if at_75 > 0:
        summary = (
            f"0.75 still returns {at_75} sampled top-k neighbor hits; "
            f"0.65 returns {at_65} ({lift * 100:.1f}% more)."
        )
        status = "measured"
    else:
        summary = f"0.75 returns no sampled top-k hits; 0.65 returns {at_65}."
        status = "supports-lowering"
    if median is not None:
        summary += f" Top-1 median is {float(median):.4f}."
    return {"status": status, "summary": summary, "counts": counts}


def build_docker_exec_command(container: str) -> list[str]:
    return ["docker", "exec", "-i", container, "python", "-"]


DEEP_PROBE_SCRIPT = r"""
import json
import os
import random
import statistics
import time

from falkordb import FalkorDB
from qdrant_client import QdrantClient

sample_size = int(os.environ.get("GRAPH_DIAG_SAMPLE_SIZE", "500"))
top_k = int(os.environ.get("GRAPH_DIAG_TOP_K", "20"))
thresholds = [float(x) for x in os.environ.get("GRAPH_DIAG_THRESHOLDS", "0.55,0.60,0.65,0.70,0.75,0.80,0.85").split(",") if x]
random.seed(int(os.environ.get("GRAPH_DIAG_RANDOM_SEED", "42")))
started = time.time()


def connect_graph():
    host = os.getenv("FALKORDB_HOST", "falkordb")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    password = os.getenv("FALKORDB_PASSWORD") or None
    attempts = [{"host": host, "port": port}]
    if password:
        attempts.append({"host": host, "port": port, "password": password})
    last_error = None
    for kwargs in attempts:
        try:
            return FalkorDB(**kwargs).select_graph(os.getenv("FALKORDB_GRAPH", "memories"))
        except Exception as exc:
            last_error = exc
    raise last_error


def rows(query, params=None):
    return [list(row) for row in connect_graph().query(query, params or {}).result_set]


def summarize_similarity(rows_):
    out = {}
    grouped = {}
    for rel_type, kind, similarity in rows_:
        key = kind if rel_type == "DISCOVERED" else rel_type
        key = key or "unknown"
        grouped.setdefault(str(key), []).append(similarity)
    for key, values in grouped.items():
        numeric = []
        none_count = 0
        for value in values:
            if value is None:
                none_count += 1
            else:
                numeric.append(float(value))
        zero_count = sum(1 for value in numeric if value == 0.0)
        out[key] = {
            "count": len(values),
            "missing_similarity": none_count,
            "zero_similarity": zero_count,
            "zero_similarity_share": zero_count / len(values) if values else 0,
            "nonzero_similarity": len([value for value in numeric if value != 0.0]),
            "min_similarity": min(numeric) if numeric else None,
            "max_similarity": max(numeric) if numeric else None,
            "mean_similarity": statistics.mean(numeric) if numeric else None,
        }
    return out


deep = {
    "relation_counts": {},
    "discovered_by_kind": {},
    "discovered_similarity": {},
    "legacy_relation_similarity": {},
    "threshold_probe": {},
}

for rel, count in rows("MATCH ()-[r]->() RETURN type(r) as rel, count(r) as count ORDER BY count DESC"):
    deep["relation_counts"][str(rel)] = int(count)

for kind, count in rows("MATCH ()-[r:DISCOVERED]->() RETURN r.kind as kind, count(r) as count ORDER BY count DESC"):
    deep["discovered_by_kind"][str(kind or "unknown")] = int(count)

deep["discovered_similarity"] = summarize_similarity(
    rows("MATCH ()-[r:DISCOVERED]->() RETURN type(r), r.kind, r.similarity")
)
deep["legacy_relation_similarity"] = summarize_similarity(
    rows("MATCH ()-[r]->() WHERE type(r) IN ['EXPLAINS','SHARES_THEME','PARALLEL_CONTEXT'] RETURN type(r), null, r.similarity")
)

graph = connect_graph()
candidate_rows = graph.query("MATCH (m:Memory) WHERE m.relevance_score > 0.3 RETURN m.id").result_set
ids = [str(row[0]) for row in candidate_rows if row and row[0]]
sample_ids = random.sample(ids, min(sample_size, len(ids)))

client = QdrantClient(
    url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
    api_key=os.getenv("QDRANT_API_KEY") or None,
)
points_by_id = {}
for idx in range(0, len(sample_ids), 100):
    points = client.retrieve(
        collection_name=os.getenv("QDRANT_COLLECTION", "memories"),
        ids=sample_ids[idx : idx + 100],
        with_vectors=True,
        with_payload=False,
    )
    for point in points:
        if point.vector:
            points_by_id[str(point.id)] = point

threshold_labels = [f"{threshold:g}" for threshold in thresholds]
edge_counts = {label: 0 for label in threshold_labels}
neighbors_per_query = {label: [] for label in threshold_labels}
top1_scores = []

for point_id, point in points_by_id.items():
    hits = client.search(
        collection_name=os.getenv("QDRANT_COLLECTION", "memories"),
        query_vector=point.vector,
        limit=top_k + 1,
        with_payload=False,
        score_threshold=min(thresholds),
    )
    non_self = [hit for hit in hits if str(hit.id) != point_id]
    if non_self:
        top1_scores.append(float(non_self[0].score))
    for threshold, label in zip(thresholds, threshold_labels):
        matching = [hit for hit in non_self[:top_k] if float(hit.score) >= threshold]
        edge_counts[label] += len(matching)
        neighbors_per_query[label].append(len(matching))

top1_summary = {}
ordered_top1 = sorted(top1_scores)
for percent in [50, 75, 90, 95, 99]:
    if ordered_top1:
        index = round((percent / 100) * (len(ordered_top1) - 1))
        top1_summary[f"p{percent}"] = ordered_top1[index]

deep["threshold_probe"] = {
    "candidate_ids_relevance_gt_0_3": len(ids),
    "sample_queries_requested": sample_size,
    "sample_queries_with_vectors": len(points_by_id),
    "top_k": top_k,
    "thresholds": thresholds,
    "top1_similarity": top1_summary,
    "top1_mean": statistics.mean(top1_scores) if top1_scores else None,
    "top_k_neighbor_edges_at_thresholds": edge_counts,
    "mean_neighbors_per_query_at_thresholds": {
        label: (statistics.mean(values) if values else 0)
        for label, values in neighbors_per_query.items()
    },
}
deep["elapsed_seconds"] = round(time.time() - started, 2)
print(json.dumps(deep, indent=2, default=str))
"""


def run_deep_probe_with_params(
    container: str,
    *,
    sample_size: int,
    top_k: int,
    thresholds: list[float],
    timeout: int,
) -> dict[str, Any]:
    prefix = "\n".join(
        [
            "import os",
            f"os.environ['GRAPH_DIAG_SAMPLE_SIZE'] = {str(sample_size)!r}",
            f"os.environ['GRAPH_DIAG_TOP_K'] = {str(top_k)!r}",
            "os.environ['GRAPH_DIAG_THRESHOLDS'] = "
            + repr(",".join(f"{threshold:g}" for threshold in thresholds)),
            "",
        ]
    )
    try:
        completed = subprocess.run(
            build_docker_exec_command(container),
            input=prefix + DEEP_PROBE_SCRIPT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "error": "docker probe timed out",
            "timeout_seconds": timeout,
            "stdout": (exc.stdout or "")[-2000:],
            "stderr": (exc.stderr or "")[-2000:],
        }
    if completed.returncode != 0:
        return {
            "error": "docker probe failed",
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "stdout": completed.stdout[-2000:],
        }
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"error": "probe returned non-json", "stdout": completed.stdout[-2000:]}


def find_line(path: pathlib.Path, pattern: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "file": str(path)}
    regex = re.compile(pattern)
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if regex.search(line):
            return {
                "status": "confirmed",
                "file": str(path),
                "line": line_no,
                "evidence": line.strip(),
            }
    return {"status": "not_found", "file": str(path)}


def find_line_after(
    path: pathlib.Path,
    anchor_pattern: str,
    pattern: str,
    *,
    max_lines: int = 8,
) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "file": str(path)}
    anchor = re.compile(anchor_pattern)
    regex = re.compile(pattern)
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        if not anchor.search(line):
            continue
        for next_index in range(index + 1, min(len(lines), index + 1 + max_lines)):
            if regex.search(lines[next_index]):
                return {
                    "status": "confirmed",
                    "file": str(path),
                    "line": next_index + 1,
                    "evidence": lines[next_index].strip(),
                    "anchor_line": index + 1,
                    "anchor": line.strip(),
                }
    return {"status": "not_found", "file": str(path)}


def inspect_source_hypotheses(source_root: pathlib.Path | None) -> dict[str, Any]:
    if source_root is None or not source_root.exists():
        return {"status": "skipped", "reason": "source root not found"}

    return {
        "status": "checked",
        "source_root": str(source_root),
        "hypotheses": {
            "hardcoded_similarity_threshold": find_line(
                source_root / "consolidation.py",
                r"self\.similarity_threshold\s*=\s*0\.75",
            ),
            "hardcoded_min_cluster_size": find_line(
                source_root / "consolidation.py",
                r"self\.min_cluster_size\s*=\s*3",
            ),
            "cluster_interval_default_30d": find_line(
                source_root / "automem" / "config.py",
                r"2592000",
            ),
            "eager_scheduler_tick": find_line_after(
                source_root / "automem" / "consolidation" / "runtime_scheduler.py",
                r"state\.consolidation_thread\.start\(\)",
                r"run_consolidation_tick_fn\(\)",
            ),
        },
    }


def write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def claim_rows(analyses: dict[str, dict[str, Any]], source: dict[str, Any]) -> list[tuple[str, str, str]]:
    full_shape = analyses.get("full", {}).get("shape") or next(iter(analyses.values())).get("shape", {})
    preceded_share = full_shape.get("relationship_counts", {}).get("PRECEDED_BY", 0)
    total_edges = full_shape.get("total_edges", 0)
    preceded_pct = pct(ratio(preceded_share, total_edges))

    invalidated = full_shape.get("invalidated_by", 0)
    prefers = full_shape.get("prefers_over", 0)

    parallel_notes = []
    for label, analysis in analyses.items():
        legacy = (analysis.get("deep_probe") or {}).get("legacy_relation_similarity") or {}
        parallel = legacy.get("PARALLEL_CONTEXT") or {}
        discovered = (analysis.get("deep_probe") or {}).get("discovered_similarity") or {}
        discovered_parallel = discovered.get("parallel_context") or {}
        if parallel:
            parallel_notes.append(
                f"{label}: legacy zero={pct(parallel.get('zero_similarity_share', 0))}"
            )
        if discovered_parallel:
            parallel_notes.append(
                f"{label}: DISCOVERED nonzero={discovered_parallel.get('nonzero_similarity', 0)}"
            )

    source_hypotheses = (source.get("hypotheses") or {}) if source.get("status") == "checked" else {}
    confirmed_source = [
        key
        for key, value in source_hypotheses.items()
        if isinstance(value, dict) and value.get("status") == "confirmed"
    ]

    rows = [
        (
            "PRECEDED_BY dominates at ~87%",
            "differs locally",
            f"Full local graph PRECEDED_BY share is {preceded_pct}.",
        ),
        (
            "INVALIDATED_BY/PREFERS_OVER barely fire",
            "confirmed locally",
            f"Full local graph has INVALIDATED_BY={invalidated}, PREFERS_OVER={prefers}.",
        ),
        (
            "parallel_context similarity=0.0",
            "mixed",
            "; ".join(parallel_notes) if parallel_notes else "deep probe skipped",
        ),
        (
            "clustering defaults need source verification",
            "checked",
            ", ".join(confirmed_source) if confirmed_source else source.get("reason", "not confirmed"),
        ),
    ]
    return rows


def write_markdown_report(
    path: pathlib.Path,
    *,
    generated_at: str,
    run_dir: pathlib.Path,
    analyses: dict[str, dict[str, Any]],
    source: dict[str, Any],
) -> None:
    lines = [
        f"# Local AutoMem graph diagnostics - {generated_at}",
        "",
        f"Raw artifacts: `{run_dir}`",
        "",
        "## Health",
        "",
        "| Label | Endpoint | Status | Memories | Vectors | Sync | Dimensions |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for label, analysis in analyses.items():
        health = analysis["health"]
        dims = health.get("vector_dimensions") or {}
        lines.append(
            "| {label} | `{endpoint}` | {status} | {memories} | {vectors} | {sync} | {dims} |".format(
                label=label,
                endpoint=analysis["endpoint"],
                status=health.get("status"),
                memories=health.get("memory_count"),
                vectors=health.get("vector_count"),
                sync=health.get("sync_status"),
                dims=dims.get("effective") or dims.get("collection") or "",
            )
        )

    lines.extend(
        [
            "",
            "## Graph Shape",
            "",
            "| Label | Nodes | Edges | PRECEDED_BY | System edges | Authorable edges | Memory type | INVALIDATED_BY | PREFERS_OVER | Legacy discovered | Risks |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for label, analysis in analyses.items():
        shape = analysis["shape"]
        rels = shape["relationship_counts"]
        lines.append(
            "| {label} | {nodes} | {edges} | {preceded} | {system} | {author} | {memory} | {invalidated} | {prefers} | {legacy} | {risks} |".format(
                label=label,
                nodes=shape["total_nodes"],
                edges=shape["total_edges"],
                preceded=pct(ratio(rels.get("PRECEDED_BY", 0), shape["total_edges"])),
                system=pct(shape["system_edge_share"]),
                author=pct(shape["author_edge_share"]),
                memory=pct(shape["generic_memory_share"]),
                invalidated=shape["invalidated_by"],
                prefers=shape["prefers_over"],
                legacy=pct(shape["legacy_discovered_share"]),
                risks=", ".join(analysis["risks"]) or "none",
            )
        )

    lines.extend(["", "## Exchange Claims", "", "| Claim | Local status | Evidence |", "|---|---|---|"])
    for claim, status, evidence in claim_rows(analyses, source):
        lines.append(f"| {claim} | {status} | {evidence} |")

    lines.extend(["", "## Threshold Evidence", ""])
    for label, analysis in analyses.items():
        evidence = threshold_evidence(analysis.get("deep_probe"))
        lines.append(f"### {label}")
        lines.append(evidence["summary"])
        counts = evidence.get("counts") or {}
        if counts:
            lines.append("")
            lines.append("| Threshold | Sampled top-k neighbor hits |")
            lines.append("|---:|---:|")
            for threshold, count in counts.items():
                lines.append(f"| {threshold} | {count} |")
        lines.append("")

    lines.extend(["## Source Hypotheses", ""])
    if source.get("status") != "checked":
        lines.append(f"Source inspection skipped: {source.get('reason')}")
    else:
        lines.append("| Hypothesis | Status | Evidence |")
        lines.append("|---|---|---|")
        for name, result in (source.get("hypotheses") or {}).items():
            evidence = result.get("evidence") or result.get("file") or ""
            if result.get("line"):
                evidence = f"{pathlib.Path(result['file']).name}:{result['line']} `{evidence}`"
            lines.append(f"| {name} | {result.get('status')} | {evidence} |")

    lines.extend(
        [
            "",
            "## Read",
            "",
            "The diagnostics do not mutate AutoMem. They treat runtime fixes as follow-up PRs: readiness probe, configurable clustering, legacy edge normalization, and any supersession-discovery pass should remain separate from this measurement harness.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def default_source_root() -> pathlib.Path | None:
    candidate = HERE.parent / "automem"
    return candidate if candidate.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--endpoint",
        action="append",
        type=parse_label_value,
        help="Endpoint as LABEL=URL. Defaults to full=8001 and cleaned=8011.",
    )
    parser.add_argument(
        "--docker-container",
        action="append",
        type=parse_label_value,
        help="Docker API container as LABEL=CONTAINER for deep probes.",
    )
    parser.add_argument("--token", default="test-token")
    parser.add_argument("--skip-deep-probes", action="store_true")
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--thresholds", type=parse_thresholds, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--probe-timeout", type=int, default=120)
    parser.add_argument("--source-root", default=str(default_source_root() or ""))
    parser.add_argument("--skip-source-inspection", action="store_true")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    endpoints = args.endpoint or DEFAULT_ENDPOINTS
    containers = dict(DEFAULT_CONTAINERS)
    if args.docker_container:
        containers.update(dict(args.docker_container))

    for _, endpoint in endpoints:
        assert_local_endpoint(endpoint)

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    generated_at = dt.datetime.now().isoformat(timespec="seconds")
    run_dir = (
        pathlib.Path(args.run_dir)
        if args.run_dir
        else HERE / "data" / "sweep_runs" / f"{timestamp}-graph-diagnostics"
    )
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    analyses: dict[str, dict[str, Any]] = {}
    for label, endpoint in endpoints:
        print(f"probing {label}: {endpoint}")
        health = http_get_json(endpoint, args.token, "/health")
        stats = http_get_json(endpoint, args.token, "/graph/stats")
        write_json(raw_dir / f"{label}-health.json", health)
        write_json(raw_dir / f"{label}-graph-stats.json", stats)

        deep_probe = None
        container = containers.get(label)
        if not args.skip_deep_probes and container:
            print(f"deep probe {label}: {container}")
            deep_probe = run_deep_probe_with_params(
                container,
                sample_size=args.sample_size,
                top_k=args.top_k,
                thresholds=args.thresholds,
                timeout=args.probe_timeout,
            )
            write_json(raw_dir / f"{label}-deep-probe.json", deep_probe)

        shape = summarize_graph_shape(stats)
        analyses[label] = {
            "endpoint": endpoint,
            "health": health,
            "stats": stats,
            "shape": shape,
            "deep_probe": deep_probe,
            "risks": graph_shape_risks(shape, deep_probe),
        }

    source_root = None
    if not args.skip_source_inspection and args.source_root:
        source_root = pathlib.Path(args.source_root)
    source = inspect_source_hypotheses(source_root)
    write_json(raw_dir / "source-hypotheses.json", source)

    summary = {
        "generated_at": generated_at,
        "endpoints": [{"label": label, "endpoint": endpoint} for label, endpoint in endpoints],
        "analyses": analyses,
        "source": source,
    }
    write_json(run_dir / "summary.json", summary)

    report_path = (
        pathlib.Path(args.report)
        if args.report
        else HERE / "data" / "results" / f"{timestamp}-graph-diagnostics.md"
    )
    write_markdown_report(
        report_path,
        generated_at=generated_at,
        run_dir=run_dir.relative_to(HERE) if run_dir.is_relative_to(HERE) else run_dir,
        analyses=analyses,
        source=source,
    )
    print(f"summary: {run_dir.relative_to(HERE) if run_dir.is_relative_to(HERE) else run_dir}/summary.json")
    print(f"report: {report_path.relative_to(HERE) if report_path.is_relative_to(HERE) else report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
