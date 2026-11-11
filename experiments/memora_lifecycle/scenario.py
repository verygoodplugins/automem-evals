"""Exercise the actual PR #88 adapter against a disposable AutoMem API."""

import json
import sys
import time

from fastembed import TextEmbedding

sys.path.insert(0, "/experiment/scripts/benchmarks")
from memora_fama_adapter import AutoMemFamaSystem, _json_request

ENDPOINT = "http://127.0.0.1:8001"
TOKEN = "memora-lifecycle-fixture-token"
requests = []
model = None


def embedding(text):
    global model
    if model is None:
        model = TextEmbedding(
            model_name="BAAI/bge-base-en-v1.5",
            cache_dir="/experiment/models",
            threads=1,
        )
    return next(model.embed([text])).tolist()


def audited(endpoint, token, method, path, **kwargs):
    # Supply local vectors explicitly; the isolated server deliberately has no
    # background embedding worker. Lifecycle operations still use the real adapter.
    if method == "POST" and path == "/memory":
        kwargs["body"] = dict(kwargs.get("body") or {})
        kwargs["body"]["embedding"] = embedding(kwargs["body"]["content"])
    if method == "GET" and path == "/recall" and (kwargs.get("params") or {}).get("query"):
        kwargs["params"] = dict(kwargs["params"])
        kwargs["params"]["embedding"] = ",".join(map(str, embedding(kwargs["params"]["query"])))
    start = time.perf_counter()
    event = {
        "method": method,
        "path_class": "/memory/:id" if path.startswith("/memory/") else path,
    }
    try:
        result = _json_request(endpoint, token, method, path, **kwargs)
        event["outcome"] = "ok"
        if method == "POST" and path == "/memory":
            event["vector_storage"] = result.get("qdrant")
        return result
    except Exception as exc:
        event["outcome"] = "error"
        event["error"] = type(exc).__name__
        raise
    finally:
        event["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        requests.append(event)


def session(n, operation, item, message="", old_item=None):
    details = {"item": item}
    if old_item is not None:
        details["old_item"] = old_item
    return {
        "session_id": n,
        "date": f"2025-06-{n:02d}",
        "operation": operation,
        "operation_details": details,
        "conversation": [{"speaker": "user_agent", "message": message, "share_memory": True}],
    }


def recall(tags, *, query="", history=False, limit=50):
    params = {
        "tags": tags,
        "tag_mode": "all",
        "tag_match": "exact",
        "limit": limit,
        "state_mode": "history" if history else "current",
        "adaptive_floor": False,
        "min_score": 0,
    }
    if query:
        params["query"] = query
    response = audited(ENDPOINT, TOKEN, "GET", "/recall", params=params)
    return response.get("results", [])


def id_for(row):
    return str(row.get("id") or (row.get("memory") or {}).get("id") or "")


def has_inline_content(rows, parent, target):
    for row in rows:
        if id_for(row) != parent:
            continue
        for relation in row.get("relations") or []:
            memory = relation.get("memory") or {}
            if str(memory.get("id") or "") == target:
                return bool(memory.get("content") or memory.get("summary"))
    return None


def check(name, passed, failure, **evidence):
    return {
        "scenario": name,
        "passed": bool(passed),
        "failure_cause": None if passed else failure,
        "evidence": evidence,
    }


def main():
    alpha = AutoMemFamaSystem(
        "lifecycle-alpha",
        endpoint=ENDPOINT,
        token=TOKEN,
        run_tag="memora-lifecycle-alpha",
        request_json=audited,
    )
    beta = AutoMemFamaSystem(
        "lifecycle-beta",
        endpoint=ENDPOINT,
        token=TOKEN,
        run_tag="memora-lifecycle-beta",
        request_json=audited,
    )
    if not alpha.initialize_client() or not beta.initialize_client():
        raise RuntimeError("disposable API is not healthy")
    original = alpha.add_conversation_to_memory(
        session(
            1,
            "add",
            "favorite editor",
            "The Orion team uses Vim for development; marker maplealpha.",
        )
    )
    renamed = alpha.add_conversation_to_memory(
        session(
            2,
            "update",
            "preferred editor",
            "The Orion team now uses Zed for development; marker birchbeta.",
            old_item="favorite editor",
        )
    )
    updated = alpha.add_conversation_to_memory(
        session(
            3,
            "update",
            "preferred editor",
            "The Orion team now uses Helix for development; marker cedargamma.",
        )
    )
    seed = alpha.add_conversation_to_memory(
        session(
            4,
            "add",
            "development context",
            "Orion development context anchor amberanchor.",
        )
    )
    foreign = beta.add_conversation_to_memory(
        session(
            1,
            "add",
            "favorite editor",
            "The Vega team uses VSCode; marker mapledistractor.",
        )
    )
    ids = [original["memory_id"], renamed["memory_id"], updated["memory_id"]]
    seed_id, foreign_id = seed["memory_id"], foreign["memory_id"]
    cases = []
    cases.append(
        check(
            "rename_predecessor",
            renamed.get("superseded") == ids[0],
            "rename did not supersede the explicitly named old item",
        )
    )
    cases.append(
        check(
            "second_update_predecessor",
            updated.get("superseded") == ids[1],
            "second update did not supersede the renamed record",
        )
    )
    retired = alpha.add_conversation_to_memory(session(5, "delete", "favorite editor"))
    cases.append(
        check(
            "retired_key_delete_skipped",
            retired.get("status") == "skipped",
            "deleting retired name did not skip",
            status=retired.get("status"),
        )
    )
    for target in (ids[0], ids[1], ids[2]):
        audited(
            ENDPOINT,
            TOKEN,
            "POST",
            "/associate",
            body={
                "memory1_id": seed_id,
                "memory2_id": target,
                "type": "RELATES_TO",
                "strength": 0.7,
            },
        )
    tags = ["memora", alpha.user_tag, alpha.run_tag]
    current = recall(tags)
    history = recall(tags, history=True)
    current_ids, history_ids = {id_for(row) for row in current}, {id_for(row) for row in history}
    cases.append(
        check(
            "current_only_latest",
            ids[2] in current_ids and not current_ids.intersection(ids[:2]),
            "current results omit latest or contain superseded memory",
            latest_present=ids[2] in current_ids,
            obsolete_top_level=sum(mid in current_ids for mid in ids[:2]),
        )
    )
    cases.append(
        check(
            "history_all_versions",
            all(mid in history_ids for mid in ids),
            "history results omitted one or more versions",
            versions_present=sum(mid in history_ids for mid in ids),
        )
    )
    cases.append(
        check(
            "scope_current",
            foreign_id not in current_ids,
            "different-user memory crossed exact scope",
            foreign_leaks=int(foreign_id in current_ids),
        )
    )
    inline_current = [has_inline_content(current, seed_id, mid) for mid in ids]
    inline_history = [has_inline_content(history, seed_id, mid) for mid in ids]
    cases.append(
        check(
            "inline_current_hides_old",
            inline_current[:2] == [False, False] and inline_current[2] is True,
            "inline relation missing or exposes obsolete content",
            states=inline_current,
        )
    )
    cases.append(
        check(
            "inline_history_shows_versions",
            inline_history == [True, True, True],
            "history omitted inline relation content",
            states=inline_history,
        )
    )
    mapped = alpha.search_memories("Orion team preferred editor", limit=50)
    mapped_ids = {str(row.get("memory_id") or "") for row in mapped}
    cases.append(
        check(
            "adapter_search_latest",
            ids[2] in mapped_ids and not mapped_ids.intersection(ids[:2]),
            "adapter returned old version or missed latest",
            latest_present=ids[2] in mapped_ids,
            obsolete_top_level=sum(mid in mapped_ids for mid in ids[:2]),
        )
    )
    deleted = alpha.add_conversation_to_memory(session(6, "delete", "preferred editor"))
    after = recall(tags)
    after_history = recall(tags, history=True)
    after_ids, after_history_ids = {id_for(row) for row in after}, {id_for(row) for row in after_history}
    deleted_inline = has_inline_content(after, seed_id, ids[2])
    cases.append(
        check(
            "delete_current_excluded",
            deleted.get("status") == "invalidated" and ids[2] not in after_ids,
            "deleted active fact remained in current results",
            status=deleted.get("status"),
            deleted_top_level=int(ids[2] in after_ids),
        )
    )
    cases.append(
        check(
            "delete_inline_hidden",
            deleted_inline is False,
            "deleted inline payload was visible or relation missing",
            state=deleted_inline,
        )
    )
    cases.append(
        check(
            "delete_history_retained",
            all(mid in after_history_ids for mid in ids),
            "history omitted pre-deletion versions",
            versions_present=sum(mid in after_history_ids for mid in ids),
        )
    )
    neg = recall(tags, query="Orion planning meeting nonexistenttopic zxqv9182")
    neg_ids = {id_for(row) for row in neg}
    cases.append(
        check(
            "negative_no_stale_evidence",
            not neg_ids.intersection(ids),
            "negative query returned an obsolete or deleted fact",
            returned_count=len(neg),
            stale_top_level=len(neg_ids.intersection(ids)),
            unrelated_nonempty=bool(neg),
        )
    )
    cases.append(
        check(
            "negative_abstains",
            not neg,
            "no-answer query returned unrelated in-scope evidence",
            returned_count=len(neg),
        )
    )
    wrong = recall(["memora", beta.user_tag, beta.run_tag], query="cedargamma Helix Orion")
    wrong_ids = {id_for(row) for row in wrong}
    cases.append(
        check(
            "wrong_scope_no_cross_leak",
            not wrong_ids.intersection(ids + [seed_id]),
            "wrong scope returned alpha memory",
            returned_count=len(wrong),
            cross_scope_leaks=len(wrong_ids.intersection(ids + [seed_id])),
        )
    )
    cases.append(
        check(
            "wrong_scope_abstains",
            not wrong,
            "wrong-scope question returned unrelated in-scope evidence",
            returned_count=len(wrong),
        )
    )
    repeated_delete = alpha.add_conversation_to_memory(session(7, "delete", "preferred editor"))
    cases.append(
        check(
            "repeated_delete_skipped",
            repeated_delete.get("status") == "skipped",
            "repeated deletion did not skip",
            status=repeated_delete.get("status"),
        )
    )
    reintroduced = alpha.add_conversation_to_memory(
        session(
            8,
            "update",
            "preferred editor",
            "The Orion team later uses Nova for development; marker firrenewed.",
        )
    )
    renewed_current = {id_for(row) for row in recall(tags)}
    cases.append(
        check(
            "update_after_delete_reintroduces",
            reintroduced.get("status") == "stored"
            and reintroduced.get("superseded") is None
            and reintroduced.get("memory_id") in renewed_current
            and not renewed_current.intersection(ids),
            "post-deletion update did not create a current fact without a predecessor",
            status=reintroduced.get("status"),
            has_predecessor=bool(reintroduced.get("superseded")),
            obsolete_top_level=len(renewed_current.intersection(ids)),
        )
    )
    health = audited(ENDPOINT, TOKEN, "GET", "/health")
    stores = [
        r.get("vector_storage") for r in requests if r["method"] == "POST" and r["path_class"] == "/memory"
    ]
    cases.append(
        check(
            "vector_index_coverage",
            health.get("memory_count") == 6
            and health.get("vector_count") == 6
            and all(value == "stored" for value in stores),
            "graph and vector coverage or a store response was incomplete",
            graph_count=health.get("memory_count"),
            vector_count=health.get("vector_count"),
            store_responses=stores,
        )
    )
    out = {
        "kind": "memora-lifecycle-diagnostic",
        "fama_score": None,
        "embedding_method": "local BGE vectors supplied on store and query",
        "cases": cases,
        "passed": sum(case["passed"] for case in cases),
        "total": len(cases),
        "request_audit": {
            "count": len(requests),
            "errors": [r for r in requests if r["outcome"] != "ok"],
            "methods": {
                method: sum(r["method"] == method for r in requests) for method in ("GET", "POST", "PATCH")
            },
        },
    }
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
