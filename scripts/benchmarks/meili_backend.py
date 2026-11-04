#!/usr/bin/env python3
"""Meilisearch retrieval backend for AutoMem (verygoodplugins/automem-evals#83).

Two swaps behind AutoMem's existing seams, scoring untouched:

* keyword leg: replaces ``runtime_recall_helpers._graph_keyword_search``. Meilisearch
  ranks; FalkorDB still hydrates the node + relations, so result shape is identical.
  Writes are mirrored into the Meilisearch index by ``MirrorQdrant`` (Qdrant stays
  the vector store).
* vector leg: ``MeiliQdrantShim`` implements the subset of the ``QdrantClient`` API
  AutoMem calls (search/upsert/retrieve/scroll/delete/set_payload/collection admin).
  Unsupported methods raise instead of silently falling back, so an arm can never
  be quietly measuring Qdrant. Scores are re-computed as exact cosine from the
  returned vectors so they sit on Qdrant's scale and the blended scorer is unchanged.

Stdlib only; ``automem`` is imported lazily so this module is unit-testable on a host.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from typing import Any, Iterable, Optional

PINNED_VERSION = "v1.56.1"  # getmeili/meilisearch image tag; recorded in every result
EMBEDDER = "default"
FILTERABLE = ["id", "tags", "tag_prefixes", "type", "archived", "ts_epoch"]
# Pinned index settings (issue #83: ranking rules, typo tolerance, stop words).
PINNED_SETTINGS: dict[str, Any] = {
    "searchableAttributes": ["content", "tag_text"],
    "filterableAttributes": FILTERABLE,
    "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
    "stopWords": [],  # AutoMem's _extract_keywords already strips stop words from the query
    "typoTolerance": {"enabled": True, "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9}},
    "pagination": {"maxTotalHits": 1000},
}
MATCHING_STRATEGY = "last"


class MeiliError(RuntimeError):
    pass


class MeiliClient:
    def __init__(self, url: str, api_key: Optional[str] = None, timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise MeiliError(f"{method} {path} -> {exc.code}: {exc.read()[:300]!r}") from exc
        return json.loads(raw) if raw else None

    def wait(self, task: dict, timeout: float = 120.0) -> dict:
        uid, deadline, delay = task["taskUid"], time.monotonic() + timeout, 0.002
        while time.monotonic() < deadline:
            info = self.request("GET", f"/tasks/{uid}")
            if info["status"] == "succeeded":
                return info
            if info["status"] in {"failed", "canceled"}:
                raise MeiliError(f"task {uid} {info['status']}: {info.get('error')}")
            time.sleep(delay)
            delay = min(delay * 2, 0.1)
        raise MeiliError(f"task {uid} timed out")

    def ensure_index(self, uid: str, dimensions: Optional[int] = None) -> None:
        try:
            self.request("GET", f"/indexes/{uid}")
        except MeiliError:
            self.wait(self.request("POST", "/indexes", {"uid": uid, "primaryKey": "id"}))
        settings = dict(PINNED_SETTINGS)
        if dimensions:
            settings["embedders"] = {EMBEDDER: {"source": "userProvided", "dimensions": dimensions}}
        self.wait(self.request("PATCH", f"/indexes/{uid}/settings", settings))

    def write_docs(self, uid: str, docs: list[dict], partial: bool = False) -> None:
        if docs:
            self.wait(self.request("PUT" if partial else "POST", f"/indexes/{uid}/documents", docs))

    def delete_docs(self, uid: str, ids: Optional[list[str]] = None, filt: Optional[str] = None) -> None:
        if ids is not None:
            self.wait(self.request("POST", f"/indexes/{uid}/documents/delete-batch", ids))
        elif filt:
            self.wait(self.request("POST", f"/indexes/{uid}/documents/delete", {"filter": filt}))

    def search(self, uid: str, body: dict) -> dict:
        return self.request("POST", f"/indexes/{uid}/search", body)

    def fetch(self, uid: str, **body: Any) -> dict:
        return self.request("POST", f"/indexes/{uid}/documents/fetch", body)

    def provenance(self, uid: str) -> dict:
        """Version + effective settings, written into every result for reproducibility."""
        return {
            "version": self.request("GET", "/version"),
            "settings": self.request("GET", f"/indexes/{uid}/settings"),
            "stats": self.request("GET", f"/indexes/{uid}/stats"),
            "matching_strategy": MATCHING_STRATEGY,
        }


def to_epoch(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def to_document(point_id: Any, payload: dict, vector: Optional[list[float]] = None) -> dict:
    """Qdrant payload -> Meilisearch document (derived fields kept in sync)."""
    doc = {k: v for k, v in payload.items() if k != "metadata"}
    doc["id"] = str(point_id)
    if "metadata" in payload:  # partial updates must not wipe metadata they do not carry
        doc["metadata_json"] = json.dumps(payload["metadata"] or {})
    if "tags" in payload:
        doc["tag_text"] = " ".join(payload.get("tags") or [])
    if "timestamp" in payload:
        doc["ts_epoch"] = to_epoch(payload.get("timestamp"))
    if vector is not None:
        doc["_vectors"] = {EMBEDDER: list(vector)}
    return doc


def from_document(doc: dict) -> dict:
    payload = {k: v for k, v in doc.items() if k not in {"id", "tag_text", "ts_epoch", "_vectors", "metadata_json", "_rankingScore"}}
    payload["metadata"] = json.loads(doc.get("metadata_json") or "{}")
    return payload


def _q(value: Any) -> str:
    return json.dumps(value)


def build_filter(
    *,
    tags: Optional[Iterable[str]] = None,
    mode: str = "any",
    match: str = "prefix",
    excluded_types: Iterable[str] = (),
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> str:
    """Mirror of the baseline's WHERE clause: not archived, type/time/tag constraints."""
    clauses = ["NOT archived = true"]
    tag_list = list(tags or [])
    key = "tag_prefixes" if match == "prefix" else "tags"
    if tag_list:
        if mode == "all":
            clauses += [f"{key} = {_q(t)}" for t in tag_list]
        else:
            clauses.append(f"{key} IN {_q(tag_list)}")
    excluded = [t for t in excluded_types if t]
    if excluded:
        clauses.append(f"NOT type IN {_q(excluded)}")
    for op, bound in ((">=", start_time), ("<=", end_time)):
        epoch = to_epoch(bound)
        if epoch is not None:
            clauses.append(f"ts_epoch {op} {epoch}")
    return " AND ".join(clauses)


def qdrant_filter_to_meili(flt: Any) -> Optional[str]:
    """Translate the qdrant Filter AutoMem builds (Match{Any,Value} only) to Meilisearch."""
    if flt is None:
        return None

    def cond(c: Any) -> str:
        match = getattr(c, "match", None)
        if match is not None and getattr(match, "any", None) is not None:
            return f"{c.key} IN {_q(list(match.any))}"
        if match is not None and getattr(match, "value", None) is not None:
            return f"{c.key} = {_q(match.value)}"
        raise NotImplementedError(f"unsupported qdrant condition: {c!r}")

    clauses = [cond(c) for c in getattr(flt, "must", None) or []]
    clauses += [f"NOT ({cond(c)})" for c in getattr(flt, "must_not", None) or []]
    should = [cond(c) for c in getattr(flt, "should", None) or []]
    if should:
        clauses.append("(" + " OR ".join(should) + ")")
    return " AND ".join(clauses) or None


def point_ids(points: Any) -> list[str]:
    """Ids from a list, a PointIdsList, or a Filter's HasIdCondition (its other guards are not replayed)."""
    if isinstance(points, (list, tuple)):
        return [str(i) for i in points]
    if getattr(points, "points", None) is not None:
        return [str(i) for i in points.points]
    return [str(i) for c in getattr(points, "must", None) or [] for i in (getattr(c, "has_id", None) or [])]


def apply_set_payload(client: MeiliClient, index: str, payload: dict, points: Any, key: Optional[str] = None) -> None:
    """Qdrant set_payload semantics: merge ``payload`` at top level, or under a nested ``metadata.*`` key."""
    ids = point_ids(points)
    if not key:
        client.write_docs(index, [to_document(i, payload) for i in ids], partial=True)
        return
    path = key.split(".")
    if path[0] != "metadata" or len(path) < 2:
        raise NotImplementedError(f"set_payload key {key!r}: only metadata.* paths are supported")
    updates = []
    for doc in client.fetch(index, filter=f"id IN {_q(ids)}", limit=max(len(ids), 1))["results"]:
        meta = json.loads(doc.get("metadata_json") or "{}")
        node = meta
        for part in path[1:-1]:
            node = node.setdefault(part, {})
        node.setdefault(path[-1], {}).update(payload)
        updates.append({"id": doc["id"], "metadata_json": json.dumps(meta)})
    client.write_docs(index, updates, partial=True)


class MirrorQdrant:
    """Real Qdrant plus a write-through mirror into the keyword index (keyword-leg arm)."""

    def __init__(self, real: Any, client: MeiliClient, index: str):
        self._real, self._client, self._index = real, client, index

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def upsert(self, collection_name: str, points: Any, **kw: Any):
        points = list(points)
        result = self._real.upsert(collection_name=collection_name, points=points, **kw)
        self._client.write_docs(self._index, [to_document(p.id, p.payload or {}) for p in points])
        return result

    def set_payload(self, collection_name: str, payload: dict, points: Any, **kw: Any):
        result = self._real.set_payload(collection_name=collection_name, payload=payload, points=points, **kw)
        apply_set_payload(self._client, self._index, payload, points, kw.get("key"))
        return result

    def delete(self, collection_name: str, points_selector: Any, **kw: Any):
        result = self._real.delete(collection_name=collection_name, points_selector=points_selector, **kw)
        ids = getattr(points_selector, "points", None)
        if ids is not None:
            self._client.delete_docs(self._index, ids=[str(i) for i in ids])
        else:
            self._client.delete_docs(self._index, filt=qdrant_filter_to_meili(points_selector.filter))
        return result


def make_keyword_search(client: MeiliClient, index: str, original: Any) -> Any:
    """Build the drop-in for ``_graph_keyword_search`` (same signature, same result dicts)."""
    import logging

    import automem.search.runtime_recall_helpers as h  # lazy: only inside the server

    log = logging.getLogger("meili_keyword")

    def meili_keyword_search(graph, query_text, limit, seen_ids, start_time=None, end_time=None,
                             tag_filters=None, tag_mode="any", tag_match="prefix"):
        normalized = (query_text or "").strip().lower()
        if not normalized or normalized == "*":
            return original(graph, query_text, limit, seen_ids, start_time, end_time, tag_filters, tag_mode, tag_match)
        keywords = h._extract_keywords(normalized)
        tags = h._prepare_tag_filters(tag_filters) if tag_filters else []
        if tags and tag_match == "prefix":
            tags = h._canonicalize_prefix_filters(tags)
        body = {
            "q": " ".join(keywords) if keywords else normalized,
            "limit": limit,
            "showRankingScore": True,
            "matchingStrategy": MATCHING_STRATEGY,
            "filter": build_filter(tags=tags, mode=tag_mode, match=tag_match,
                                   excluded_types=h.RECALL_EXCLUDED_TYPES, start_time=start_time, end_time=end_time),
        }
        try:
            hits = client.search(index, body)["hits"]
            ids = [str(x["id"]) for x in hits]
            if not ids:
                return []
            rows = graph.query("MATCH (m:Memory) WHERE m.id IN $ids RETURN m", {"ids": ids}).result_set
        except Exception:
            log.exception("Meilisearch keyword search failed")
            return []
        nodes = {str(h._serialize_node(r[0]).get("id")): r[0] for r in rows}
        out = []
        for hit in hits:
            node = nodes.get(str(hit["id"]))
            record = h._format_graph_result(graph, node, hit.get("_rankingScore"), "keyword", seen_ids) if node is not None else None
            if record is not None:
                out.append(record)
        return out

    return meili_keyword_search
