#!/usr/bin/env python3
"""Real-data, cold MemDerive plumbing pilot; requires the official DerivEval src."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import uuid


def instant(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=dt.timezone.utc) if not parsed.tzinfo else parsed


def local_endpoint(value):
    url = urllib.parse.urlsplit(value)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.path not in {"", "/"}
            or url.query or url.fragment):
        raise ValueError("endpoint must be an HTTP loopback origin")
    return value.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("redirect refused")


def request(url, body=None, *, method=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-API-Key"] = token
    req = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode(),
        headers=headers, method=method,
    )
    with urllib.request.build_opener(NoRedirect).open(req, timeout=180) as response:
        return json.load(response)


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


class AutoMem:
    """One public event per memory; ID manifest isolates reads and cleanup."""
    def __init__(self, endpoint, token, output):
        self.endpoint = local_endpoint(endpoint)
        self.token, self.output = token, output
        self.tag = "memderive-" + uuid.uuid4().hex
        self.events = {}

    def call(self, path, body=None, method=None):
        return request(self.endpoint + path, body, token=self.token, method=method)

    def store(self, events):
        for event in sorted(events, key=lambda e: instant(e["time"])):
            payload = self.call("/memory", {
                "content": event["text"],
                "timestamp": instant(event["time"]).isoformat(),
                "tags": [self.tag], "type": "Context", "importance": 0.5,
                "metadata": {"event_id": event["event_id"], "source": event["source"]},
            })
            memory_id = payload.get("memory_id") or payload.get("id")
            if not memory_id or memory_id in self.events:
                raise RuntimeError("missing or reused memory ID")
            self.events[memory_id] = event
            save(self.output / "memories.json",
                 {"tag": self.tag, "events": self.events})

    def recall(self, question, cutoff, k):
        params = urllib.parse.urlencode({
            "query": question, "tags": self.tag, "tag_match": "exact",
            "limit": k, "end": instant(cutoff).isoformat(), "current_only": "false",
        })
        response = self.call("/recall?" + params)
        selected = []
        for result in response.get("results", []):
            memory = result.get("memory", result)
            memory_id = memory.get("id") or result.get("id")
            if memory_id not in self.events:
                raise RuntimeError("recall returned an unmanifested memory")
            event = self.events[memory_id]
            if instant(event["time"]) > instant(cutoff):
                raise RuntimeError("future event returned")
            selected.append(event)
        return selected[:k]

    def cleanup(self):
        for memory_id in list(self.events):
            self.call("/memory/" + urllib.parse.quote(memory_id, safe=""),
                      method="DELETE")
        save(self.output / "cleanup.json", {"deleted_ids": list(self.events)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="DeriveMem root")
    parser.add_argument("--output", type=Path, required=True, help="New run directory")
    parser.add_argument("--endpoint", type=local_endpoint,
                        default="http://localhost:8001")
    parser.add_argument("--reader", type=local_endpoint,
                        default="http://localhost:11434")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--k", type=int, default=15)
    args = parser.parse_args()
    if not 1 <= args.k <= 100:
        parser.error("k must be between 1 and 100")
    # The official libraries own BM25, the shared v9 prompt and v2 answer scoring.
    from memory_bench.backends.retrieval import BM25
    from memory_bench.benchmarks.derivemem.prompts import PROMPT_VERSION, reader_prompt
    from memory_bench.scorers.derivemem import answer_matches, score

    world, qid = "tripops_w1", "q055"  # smallest world, small answerable official DAG
    base = args.data / "benchmark"
    panel = base / "microbench/generated/formal-set-v1.16/shape-40-v3"
    queries = rows(base / "data" / world / "queries.jsonl")
    query = next(q for q in queries if q["query_id"] == qid)
    cutoff = query["as_of"]
    events = [e for e in rows(base / "data" / world / "chronicle.jsonl")
              if instant(e["time"]) <= instant(cutoff)]
    nodes = [n for n in rows(panel / "node_occurrences.jsonl")
             if n["root_key"] == f"{world}/{qid}"]
    edges = [e for e in rows(panel / "edge_probes.jsonl")
             if e["root_key"] == f"{world}/{qid}"]
    if not nodes or not edges:
        raise ValueError("official diagnostic panel is missing")
    args.output.mkdir(parents=True, exist_ok=False)
    bank = AutoMem(args.endpoint, os.environ.get("AUTOMEM_TOKEN", "test-token"),
                   args.output)
    report = {"status": "not_scored", "world": world, "query_id": qid,
              "events": len(events), "nodes": len(nodes), "edges": len(edges),
              "endpoint": args.endpoint, "reader": args.reader,
              "model": args.model, "k": args.k, "prompt": PROMPT_VERSION,
              "reader_options": {"temperature": 0, "seed": 0, "num_predict": 2048},
              "mode": "cold", "matured": "not_run", "arms": {},
              "health_before": bank.call("/health"),
              "reader_model": next(
                  m for m in request(args.reader + "/api/tags")["models"]
                  if m["name"] == args.model), "hashes": {
                  str(p.relative_to(args.data)):
                  hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [base / "data" / world / "chronicle.jsonl",
                            base / "data" / world / "queries.jsonl",
                            base / "data" / world / "gold.json",
                            panel / "node_occurrences.jsonl",
                            panel / "edge_probes.jsonl"]}}
    save(args.output / "report.json", report)
    try:
        bank.store(events)
        index = BM25([e["text"] for e in events])

        def bm25(question):
            ranking = sorted(enumerate(index.scores(question)),
                             key=lambda x: -x[1])
            return [events[i] for i, _ in ranking[:args.k]]

        call_count = 0

        def answer(question, evidence):
            nonlocal call_count
            lines = [f'{e["event_id"]} | {e["time"]} | {e["source"]} | {e["text"]}'
                     for e in sorted(evidence, key=lambda e: instant(e["time"]))]
            prompt = reader_prompt({**query, "question": question},
                                   lines, dataset=world)
            response = request(args.reader + "/api/chat", {
                "model": args.model, "messages": [{"role": "user", "content": prompt}],
                "stream": False, "format": "json", "think": False,
                "options": {"temperature": 0, "seed": 0, "num_predict": 2048},
            })
            call_count += 1
            save(args.output / f"answer-{call_count:03d}.json",
                 {"prompt": prompt, "response": response})
            prediction = json.loads(response["message"]["content"])
            return {"prediction": prediction, "response": response, "prompt": prompt,
                    "event_ids": [e["event_id"] for e in evidence]}

        for name, retrieve in [("bm25", bm25), ("automem", lambda question:
                               bank.recall(question, cutoff, args.k))]:
            contexts, targeted, inherited = {}, {}, []
            for node in nodes:
                evidence = retrieve(node["question"])
                contexts[node["node_id"]] = evidence
                targeted[node["node_id"]] = answer(node["question"], evidence)
            for edge in edges:
                result = answer(edge["evaluation_question"],
                                contexts[edge["parent_node_id"]])
                pred = result["prediction"]
                result.update({"edge_id": edge["edge_probe_id"], "correct":
                               pred.get("answerability") ==
                               edge["evaluation_answerability"]
                               and answer_matches(pred.get("answer"),
                                                  edge["evaluation_gold_answer"])})
                inherited.append(result)
            root = next(n for n in nodes if n["kind"] == "query")
            prediction = targeted[root["node_id"]]["prediction"]
            prediction["query_id"] = qid
            path = args.output / f"{name}-predictions.jsonl"
            path.write_text(json.dumps(prediction) + "\n")
            metrics = score(path, base / "data" / world / "gold.json", [qid])
            for node in nodes:
                pred = targeted[node["node_id"]]["prediction"]
                targeted[node["node_id"]]["correct"] = (
                    pred.get("answerability") == node["answerability"]
                    and answer_matches(pred.get("answer"), node["gold_answer"]))
            save(args.output / f"{name}-traces.json", {
                "targeted": targeted, "inherited": inherited})
            report["arms"][name] = metrics
            save(args.output / "report.json", report)
        report["status"] = "completed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            bank.cleanup()
            report["cleanup"] = "completed"
        finally:
            save(args.output / "report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
