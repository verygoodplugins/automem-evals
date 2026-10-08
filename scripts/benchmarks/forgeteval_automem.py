#!/usr/bin/env python3
"""Exploratory ForgetEval adapter; stdlib, local-only, no model judge."""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


AUTOMEM_REVISION = "3caa9d5d396ba4cb303df1fb39da7602126f60c9"


def verify_automem_checkout(checkout):
    if not checkout:
        raise ValueError("Set AUTOMEM_CHECKOUT to the pinned local source used by Compose")
    command = ["git", "-C", str(Path(checkout).resolve())]
    revision = subprocess.check_output(command + ["rev-parse", "HEAD"], text=True).strip()
    if revision != AUTOMEM_REVISION:
        raise ValueError("Unexpected AutoMem revision: " + revision)
    if subprocess.check_output(command + ["status", "--porcelain"], text=True).strip():
        raise ValueError("AutoMem checkout must be clean")
    return revision


class AutoMemAdapter:
    name = "automem-cold-local-primitives"

    def __init__(self, endpoint, graph, token="forgeteval-isolated-test"):
        url = urlsplit(endpoint)
        if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1"}
                or not url.port or url.port == 8001 or url.path or url.query
                or url.fragment or url.username or not graph.startswith("forgeteval-")):
            raise ValueError("Use a dedicated loopback port and forgeteval-* graph")
        self.endpoint, self.token = endpoint.rstrip("/"), token
        self.ids, self.trace = [], []
        self.tag = "forgeteval-" + uuid.uuid4().hex
        if self.request("GET", "/health").get("graph") != graph:
            raise ValueError("Dedicated graph identity does not match")

    def request(self, method, path, body=None):
        req = Request(self.endpoint + path, method=method,
                      data=None if body is None else json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + self.token,
                               "Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            return json.load(response)

    def reset(self):
        for mid in self.ids[:]:
            self.request("DELETE", "/memory/" + mid)
            self.ids.remove(mid)
        self.trace = []
        self.tag = "forgeteval-" + uuid.uuid4().hex

    def inscribe(self, text):
        result = self.request("POST", "/memory", {
            "content": text, "tags": [self.tag], "type": "Context", "importance": 0.7})
        mid = result["memory_id"]
        self.ids.append(mid)
        return mid

    def rows(self, query, k=10, **options):
        # Wait for real queued vectors, rather than scoring unembedded writes.
        deadline = time.monotonic() + 60
        while True:
            health = self.request("GET", "/health")
            if health.get("sync_status") == "synced":
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Embedding/vector synchronization did not finish")
            time.sleep(0.05)
        params = dict(query=query, limit=k, tags=self.tag, tag_mode="all",
                      tag_match="exact", current_only="true", **options)
        return self.request("GET", "/recall?" + urlencode(params))["results"]

    def recall_texts(self, query, k=5):
        return [row["memory"]["content"] for row in self.rows(query, k)]

    def targets(self, query):
        candidates = [dict(row["memory"], id=row["id"]) for row in self.rows(query, 100)]
        literal = [m for m in candidates if query.lower() in m["content"].lower()]
        # Literal identifier/duplicate match, otherwise semantic top-1. No gold
        # substrings, case IDs, equivalence router, or compound-fact planner.
        return literal or candidates[:1]

    def invalidate(self, mid):
        return self.request("PATCH", "/memory/" + mid, {
            "t_invalid": datetime.now(timezone.utc).isoformat()})

    def supersede(self, old_query, new_text, fail_after=None):
        targets = self.targets(old_query)
        if not targets:
            raise LookupError("No supersession candidate")
        old = targets[0]
        new = self.inscribe(new_text)
        self.trace.append({"op": "supersede", "query": old_query,
                           "old": old, "new_id": new, "stage": "stored"})
        if fail_after == "store":
            raise RuntimeError("Injected interruption after replacement store")
        self.invalidate(old["id"])
        self.trace[-1]["stage"] = "invalidated"
        if fail_after == "invalidate":
            raise RuntimeError("Injected interruption after source invalidation")
        self.request("POST", "/associate", {"memory1_id": old["id"],
                     "memory2_id": new, "type": "INVALIDATED_BY", "strength": 1})
        self.trace[-1]["stage"] = "associated"

    def mutate(self, op, query):
        targets = self.targets(query)
        for m in targets:
            if op == "release":
                self.invalidate(m["id"])
            else:
                self.request("DELETE", "/memory/" + m["id"])
                self.ids.remove(m["id"])
        self.trace.append({"op": op, "query": query, "targets": targets})
        return len(targets)

    def release(self, query):
        return self.mutate("release", query)

    def purge(self, query):
        return self.mutate("purge", query)


def oracle(texts, required, forbidden):
    blob = " ".join(texts).lower()
    missing = [s for s in required if s.lower() not in blob]
    leaked = [s for s in forbidden if s.lower() in blob]
    return {"passed": not missing and not leaked, "missing": missing, "leaked": leaked}


def run(adapter, categories, output):
    output.mkdir(parents=True, exist_ok=True)
    counts = {}
    for category, cases in categories.items():
        records = []
        for case in cases:
            adapter.reset()
            record = {"id": case.id, "family": case.family, "case": vars(case)}
            try:
                for fact in case.setup_facts:
                    adapter.inscribe(fact)
                for op, *args in case.mutations:
                    getattr(adapter, op)(*args)
                texts = adapter.recall_texts(case.final_query, k=10)
                record.update(oracle(texts, case.must_contain, case.must_not_contain), texts=texts)
            except Exception as exc:
                record.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            record["trace"] = adapter.trace[:]
            records.append(record)
        counts[category] = {"passed": sum(r["passed"] for r in records),
                            "total": len(records), "errors": sum("error" in r for r in records)}
        (output / (category + ".json")).write_text(json.dumps({
            "exploratory": True, **counts[category], "cases": records}, ensure_ascii=False) + "\n")
        print(category, counts[category], flush=True)
    adapter.reset()
    return counts


def diagnostics(adapter):
    residual, partial = [], []
    for op in ("supersede", "purge"):
        for n in range(5):
            adapter.reset()
            old_text = f"We spoke with Maya about obsolete access code retired-{n}."
            old = adapter.inscribe(old_text)
            neighbor = adapter.inscribe(f"We met with Maya about active-neighbor-{n} support.")
            adapter.request("POST", "/associate", {"memory1_id": neighbor,
                "memory2_id": old, "type": "RELATES_TO", "strength": 1})
            adapter.rows("Maya", 100)  # Populate server entity metadata when JIT is enabled.
            if op == "supersede":
                adapter.supersede(old_text, "We spoke with Maya about access code current-code.")
            else:
                adapter.purge(old_text)
            rows = adapter.rows("Maya support access code", expand_relations="true",
                                expand_entities="true", expand_depth=2)
            texts = [r["memory"]["content"] for r in rows]
            residual.append({"id": f"{op}-{n}", "rows": rows,
                "entity_seed": any("entity:people:maya" in r["memory"]["tags"] for r in rows),
                "top_k": oracle(texts, [f"active-neighbor-{n}"], [f"retired-{n}"]),
                **oracle([json.dumps(rows)], [f"active-neighbor-{n}"], [f"retired-{n}"])})
    for stage in ("store", "invalidate"):
        adapter.reset()
        old = adapter.inscribe("Maya employer OldCo.")
        try:
            adapter.supersede("Maya employer OldCo", "Maya employer NewCo.", fail_after=stage)
        except RuntimeError as exc:
            partial.append({"interruption": stage, "error": str(exc),
                "source": adapter.request("GET", "/memory/" + old),
                "replacement": adapter.request("GET", "/memory/" + adapter.ids[-1]),
                "rows": adapter.rows("Maya employer"), "trace": adapter.trace[:]})
    adapter.reset()
    return {"exploratory": True, "graph_residual": residual, "partial_failures": partial}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostics-only", action="store_true")
    args = parser.parse_args()
    automem_revision = verify_automem_checkout(os.environ.get("AUTOMEM_CHECKOUT"))
    pin = subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip()
    if pin != "b6053b7bdacc78a91b9ea4bb25f32edad278c495":
        raise ValueError("Unexpected Lethe revision")
    subprocess.run(["git", "-C", str(args.upstream), "diff", "--exit-code", pin,
                    "--", "bench/forgeteval"], check=True, stdout=subprocess.DEVNULL)
    sys.path.insert(0, str(args.upstream.resolve()))
    from bench.forgeteval.adversarial import ATTACK_CATEGORIES
    if sum(map(len, ATTACK_CATEGORIES.values())) != 385:
        raise ValueError("Expected all 385 upstream cases")
    adapter = AutoMemAdapter(args.endpoint, args.graph)
    counts = (json.loads((args.output / "summary.json").read_text())["categories"]
              if args.diagnostics_only else run(adapter, ATTACK_CATEGORIES, args.output))
    diagnostic = diagnostics(adapter)
    (args.output / "graph-residual.json").write_text(json.dumps(diagnostic, ensure_ascii=False) + "\n")
    (args.output / "summary.json").write_text(json.dumps({
        "exploratory": True, "upstream": pin, "automem_checkout_revision": automem_revision,
        "categories": counts,
        "oracle": "case-insensitive joined top-10 substring; errors count as failures",
        "graph_residual": {"passed": sum(r["passed"] for r in diagnostic["graph_residual"]), "total": 10},
        "graph_top_k": {"passed": sum(r["top_k"]["passed"] for r in diagnostic["graph_residual"]), "total": 10},
        "health": adapter.request("GET", "/health")}, indent=2) + "\n")


if __name__ == "__main__":
    main()
