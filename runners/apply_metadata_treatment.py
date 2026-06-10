#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from metadata_eval_common import (
    compact_metadata_excerpt,
    compute_tag_prefixes,
    extract_metadata_signals,
    hash_vector,
    normalize_tags,
    parse_metadata,
)

HERE = Path(__file__).resolve().parent.parent


def default_automem_dir() -> Path:
    candidates = [
        HERE.parent / "automem",
        Path.home() / "Projects" / "OpenAI" / "automem",
    ]
    for candidate in candidates:
        if (candidate / "automem").is_dir():
            return candidate
    return candidates[0]


DEFAULT_AUTOMEM_DIR = default_automem_dir()
VALID_VARIANTS = {"metadata-tags", "metadata-embedding", "combined"}


def is_local_host(value: str | None) -> bool:
    return (value or "").strip().lower() in {"localhost", "127.0.0.1", "::1"}


def assert_local_db_targets() -> None:
    falkor_host = os.getenv("FALKORDB_HOST", "localhost")
    if not is_local_host(falkor_host):
        raise SystemExit(f"refusing non-local FalkorDB host: {falkor_host}")

    qdrant_url = os.getenv("QDRANT_URL")
    if not qdrant_url:
        raise SystemExit("QDRANT_URL is required")
    parsed = urllib.parse.urlparse(qdrant_url)
    if parsed.scheme not in {"http", "https"} or not is_local_host(parsed.hostname):
        raise SystemExit(f"refusing non-local Qdrant URL: {qdrant_url}")


def build_tag_update(
    memory: dict[str, Any],
    *,
    max_tags: int = 8,
    compute_prefixes_fn: Callable[[list[str]], list[str]] | None = None,
) -> dict[str, Any] | None:
    existing_tags = normalize_tags(memory.get("tags"))
    existing_lower = {tag.lower() for tag in existing_tags}
    generated_tags: list[str] = []
    for signal in extract_metadata_signals(memory, max_tags=max_tags):
        if signal.tag.lower() not in existing_lower:
            existing_lower.add(signal.tag.lower())
            generated_tags.append(signal.tag)
    if not generated_tags:
        return None
    tags = existing_tags + generated_tags
    compute_prefixes = compute_prefixes_fn or compute_tag_prefixes
    return {
        "id": str(memory.get("id") or ""),
        "content": memory.get("content") or "",
        "metadata": parse_metadata(memory.get("metadata")),
        "tags": tags,
        "tag_prefixes": compute_prefixes([tag.lower() for tag in tags]),
        "generated_tags": generated_tags,
    }


def build_embedding_update(memory: dict[str, Any], *, max_items: int = 8) -> dict[str, Any] | None:
    excerpt = compact_metadata_excerpt(memory, max_items=max_items)
    if not excerpt:
        return None
    content = str(memory.get("content") or "")
    return {
        "id": str(memory.get("id") or ""),
        "content": content,
        "tags": normalize_tags(memory.get("tags")),
        "metadata_excerpt": excerpt,
        "embedding_text": f"{content}\n\nMetadata: {excerpt}",
    }


def _ensure_automem_path(automem_dir: Path) -> None:
    automem_dir = automem_dir.resolve()
    if str(automem_dir) not in sys.path:
        sys.path.insert(0, str(automem_dir))


def _load_compute_tag_prefixes(automem_dir: Path) -> Callable[[list[str]], list[str]]:
    try:
        _ensure_automem_path(automem_dir)
        from automem.utils.tags import _compute_tag_prefixes  # type: ignore

        return _compute_tag_prefixes
    except Exception:
        return compute_tag_prefixes


def _connect_graph() -> Any:
    from falkordb import FalkorDB  # type: ignore

    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    password = os.getenv("FALKORDB_PASSWORD") or None
    username = os.getenv("FALKORDB_USERNAME") or ("default" if password else None)
    graph_name = os.getenv("FALKORDB_GRAPH", "memories")
    client = FalkorDB(host=host, port=port, password=password, username=username)
    return client.select_graph(graph_name)


def _connect_qdrant() -> tuple[Any, str]:
    from qdrant_client import QdrantClient  # type: ignore

    url = os.getenv("QDRANT_URL")
    if not url:
        raise RuntimeError("QDRANT_URL is required")
    api_key = os.getenv("QDRANT_API_KEY") or None
    collection = os.getenv("QDRANT_COLLECTION", "memories")
    return QdrantClient(url=url, api_key=api_key), collection


def fetch_graph_memories(graph: Any, *, batch_size: int = 500, limit: int = 0) -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []
    skip = 0
    while True:
        page_size = batch_size
        if limit and len(memories) + page_size > limit:
            page_size = max(0, limit - len(memories))
        if page_size <= 0:
            break
        result = graph.query(
            """
            MATCH (m:Memory)
            RETURN m.id, m.content, m.tags, m.metadata, m.importance, m.timestamp,
                   m.type, m.confidence, m.updated_at, m.last_accessed
            ORDER BY m.timestamp, m.id
            SKIP $skip
            LIMIT $limit
            """,
            {"skip": skip, "limit": page_size},
        )
        rows = list(getattr(result, "result_set", []) or [])
        if not rows:
            break
        for row in rows:
            memories.append(
                {
                    "id": row[0],
                    "content": row[1] or "",
                    "tags": normalize_tags(row[2]),
                    "metadata": parse_metadata(row[3]),
                    "importance": row[4],
                    "timestamp": row[5],
                    "type": row[6],
                    "confidence": row[7],
                    "updated_at": row[8],
                    "last_accessed": row[9],
                }
            )
        skip += len(rows)
        if len(rows) < page_size:
            break
    return memories


def _iter_qdrant_points(qdrant: Any, collection: str, *, with_vectors: bool) -> Iterable[Any]:
    offset = None
    while True:
        points, next_offset = qdrant.scroll(
            collection_name=collection,
            limit=250,
            offset=offset,
            with_payload=True,
            with_vectors=with_vectors,
        )
        for point in points or []:
            yield point
        if next_offset is None:
            break
        offset = next_offset


def qdrant_vector_hashes(qdrant: Any, collection: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for point in _iter_qdrant_points(qdrant, collection, with_vectors=True):
        vector = getattr(point, "vector", None)
        if vector is None:
            continue
        hashes[str(point.id)] = hash_vector(vector)
    return hashes


def execute_tag_updates(
    graph: Any,
    qdrant: Any,
    collection: str,
    updates: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    batch_size: int = 250,
) -> dict[str, int]:
    if dry_run or not updates:
        return {"graph_updates": 0, "qdrant_updates": 0}
    graph_updates = 0
    for idx in range(0, len(updates), batch_size):
        batch = updates[idx : idx + batch_size]
        graph_rows = [
            {
                "id": update["id"],
                "tags": update["tags"],
                "tag_prefixes": update["tag_prefixes"],
            }
            for update in batch
        ]
        graph.query(
            """
            UNWIND $rows AS row
            MATCH (m:Memory {id: row.id})
            SET m.tags = row.tags,
                m.tag_prefixes = row.tag_prefixes
            """,
            {"rows": graph_rows},
        )
        graph_updates += len(batch)
    qdrant_updates = 0
    for update in updates:
        qdrant.set_payload(
            collection_name=collection,
            points=[update["id"]],
            payload={
                "tags": update["tags"],
                "tag_prefixes": update["tag_prefixes"],
                "metadata": update["metadata"],
            },
        )
        qdrant_updates += 1
    return {"graph_updates": graph_updates, "qdrant_updates": qdrant_updates}


def _init_embedding_provider(automem_dir: Path) -> Any:
    _ensure_automem_path(automem_dir)
    from automem.config import EMBEDDING_MODEL, VECTOR_SIZE  # type: ignore
    from automem.embedding.provider_init import init_embedding_provider  # type: ignore

    state = SimpleNamespace(embedding_provider=None, qdrant=None, effective_vector_size=VECTOR_SIZE)
    noop = lambda *_a, **_k: None
    init_embedding_provider(
        state=state,
        logger=SimpleNamespace(info=noop, warning=noop, error=noop, exception=noop),
        vector_size_config=VECTOR_SIZE,
        embedding_model=EMBEDDING_MODEL,
    )
    if state.embedding_provider is None:
        raise RuntimeError("embedding provider could not be initialized")
    return state.embedding_provider


def execute_embedding_updates(
    qdrant: Any,
    collection: str,
    updates: list[dict[str, Any]],
    *,
    automem_dir: Path,
    batch_size: int = 32,
    dry_run: bool = False,
) -> dict[str, int]:
    if dry_run or not updates:
        return {"vector_updates": 0}
    _ensure_automem_path(automem_dir)
    from qdrant_client.models import PointVectors  # type: ignore

    provider = _init_embedding_provider(automem_dir)
    vector_updates = 0
    for idx in range(0, len(updates), batch_size):
        batch = updates[idx : idx + batch_size]
        texts = [item["embedding_text"] for item in batch]
        if hasattr(provider, "generate_embeddings_batch"):
            vectors = provider.generate_embeddings_batch(texts)
        else:
            vectors = [provider.generate_embedding(text) for text in texts]
        qdrant.update_vectors(
            collection_name=collection,
            points=[
                PointVectors(id=item["id"], vector=vector)
                for item, vector in zip(batch, vectors, strict=True)
            ],
        )
        vector_updates += len(batch)
    return {"vector_updates": vector_updates}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply metadata retrieval treatment to local AutoMem")
    parser.add_argument("--variant", required=True, choices=sorted(VALID_VARIANTS))
    parser.add_argument("--automem-dir", type=Path, default=DEFAULT_AUTOMEM_DIR)
    parser.add_argument("--plan-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--vector-preflight-output", required=True, type=Path)
    parser.add_argument("--max-tags-per-memory", type=int, default=8)
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    assert_local_db_targets()
    graph = _connect_graph()
    qdrant, collection = _connect_qdrant()
    memories = fetch_graph_memories(graph, limit=max(0, args.limit))
    before_hashes = qdrant_vector_hashes(qdrant, collection)

    plan_rows: list[dict[str, Any]] = []
    tag_updates: list[dict[str, Any]] = []
    embedding_updates: list[dict[str, Any]] = []
    compute_prefixes_fn = _load_compute_tag_prefixes(args.automem_dir)

    if args.variant in {"metadata-tags", "combined"}:
        for memory in memories:
            update = build_tag_update(
                memory,
                max_tags=max(1, args.max_tags_per_memory),
                compute_prefixes_fn=compute_prefixes_fn,
            )
            if update:
                tag_updates.append(update)
                plan_rows.append(
                    {
                        "id": update["id"],
                        "action": "metadata-tags",
                        "generated_tags": update["generated_tags"],
                    }
                )

    if args.variant in {"metadata-embedding", "combined"}:
        for memory in memories:
            update = build_embedding_update(memory, max_items=max(1, args.max_tags_per_memory))
            if update:
                embedding_updates.append(update)
                plan_rows.append(
                    {
                        "id": update["id"],
                        "action": "metadata-embedding",
                        "metadata_excerpt": update["metadata_excerpt"],
                    }
                )

    _write_jsonl(args.plan_output, plan_rows)

    tag_result = execute_tag_updates(
        graph, qdrant, collection, tag_updates, dry_run=args.dry_run
    )
    embedding_result = execute_embedding_updates(
        qdrant,
        collection,
        embedding_updates,
        automem_dir=args.automem_dir,
        batch_size=max(1, args.embedding_batch_size),
        dry_run=args.dry_run,
    )

    # Give Qdrant a moment to apply vector-only updates before hashing.
    if not args.dry_run:
        time.sleep(0.25)
    after_hashes = qdrant_vector_hashes(qdrant, collection)
    changed_ids = sorted(
        memory_id
        for memory_id, before in before_hashes.items()
        if after_hashes.get(memory_id) is not None and after_hashes[memory_id] != before
    )
    missing_after = sorted(set(before_hashes) - set(after_hashes))
    unexpected_vector_change = args.variant == "metadata-tags" and bool(changed_ids)

    preflight = {
        "variant": args.variant,
        "before_vector_count": len(before_hashes),
        "after_vector_count": len(after_hashes),
        "changed_vector_count": len(changed_ids),
        "changed_vector_ids_sample": changed_ids[:20],
        "missing_after_count": len(missing_after),
        "missing_after_sample": missing_after[:20],
        "vectors_identical": not changed_ids and not missing_after,
        "unexpected_vector_change": unexpected_vector_change,
        "dry_run": bool(args.dry_run),
    }
    args.vector_preflight_output.parent.mkdir(parents=True, exist_ok=True)
    args.vector_preflight_output.write_text(json.dumps(preflight, indent=2) + "\n")

    summary = {
        "variant": args.variant,
        "memory_count": len(memories),
        "tag_plan_count": len(tag_updates),
        "embedding_plan_count": len(embedding_updates),
        **tag_result,
        **embedding_result,
        "vector_preflight": preflight,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n")

    print(json.dumps(summary, indent=2))
    return 2 if unexpected_vector_change else 0


if __name__ == "__main__":
    raise SystemExit(main())
