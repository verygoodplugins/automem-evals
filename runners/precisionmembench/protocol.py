"""Local-only HTTP protocol for the pinned official PrecisionMemBench harness."""
import argparse
import hashlib
import json
import os
import subprocess
import uuid
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REVISION = "61a712a1754e7d27b6dee42da32a2c214b003ece"


def local_url(value):
    url = urlsplit(value)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("Use an isolated loopback HTTP AutoMem endpoint")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Redirects are forbidden")


class Protocol:
    def __init__(self, endpoint, token, beliefs, trace):
        self.endpoint, self.token = local_url(endpoint), token
        self.fixtures = {b["_id"]: b for b in beliefs}
        self.ids, self.reverse = {}, {}
        self.run_tag = "precisionmembench-" + uuid.uuid4().hex
        self.trace = trace

    def call(self, method, path, data=None):
        request = Request(self.endpoint + path, method=method,
                          data=json.dumps(data).encode() if data is not None else None,
                          headers={"Authorization": "Bearer " + self.token,
                                   "Content-Type": "application/json"})
        with build_opener(NoRedirect).open(request, timeout=120) as response:
            result = json.load(response)
        with self.trace.open("a") as stream:
            stream.write(json.dumps({"method": method, "path": path,
                                     "request": data, "response": result}) + "\n")
        return result

    def tag(self, user, scope=None):
        return "pmb-" + hashlib.sha256(json.dumps([user, scope]).encode()).hexdigest()

    def reset(self):
        for memory_id in list(self.ids.values()):
            self.call("DELETE", "/memory/" + memory_id)
        self.ids.clear()
        self.reverse.clear()
        return {"ok": True}

    def add(self, body, update=False):
        key = body["metadata"]["beliefId"]
        source = {**body["metadata"], **self.fixtures.get(key, {})}
        user = body["user_id"]
        scopes = source.get("scope", [])
        scopes = [scopes] if isinstance(scopes, str) else scopes
        payload = {"content": body["text"], "type": "Context", "importance": 0.5,
                   "tags": [self.run_tag, self.tag(user)] + [self.tag(user, s) for s in scopes],
                   "metadata": {"beliefId": key, "user_id": user, "scope": scopes}}
        if source.get("created_at"):
            payload["timestamp"] = source["created_at"]
        if source.get("resolved_at"):
            payload["t_invalid"] = source["resolved_at"]
        if update:
            self.call("PATCH", "/memory/" + self.ids[key], {"content": body["text"]})
        else:
            if key in self.ids:
                raise ValueError("Duplicate belief ID")
            memory_id = self.call("POST", "/memory", payload)["memory_id"]
            self.ids[key], self.reverse[memory_id] = memory_id, key
            # Resolve fixture lifecycle links only after both endpoints are ingested.
            for old, belief in self.fixtures.items():
                new = belief.get("superseded_by")
                if new and old in self.ids and new in self.ids and key in {old, new}:
                    self.call("POST", "/associate", {"memory1_id": self.ids[old],
                              "memory2_id": self.ids[new], "type": "INVALIDATED_BY", "strength": 1.0})
                    invalid = self.fixtures[new]["created_at"]
                    self.call("PATCH", "/memory/" + self.ids[old], {"t_invalid": invalid})
                    state = self.call("GET", "/memory/" + self.ids[old])["memory"]
                    if not state.get("t_invalid"):
                        raise ValueError("Supersession did not persist t_invalid")
        self.wait()
        return {"id": key}

    def wait(self):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            health = self.call("GET", "/health")
            if health.get("memory_count") == health.get("vector_count") == len(self.ids):
                return {"ok": True}
            time.sleep(0.1)
        raise TimeoutError("AutoMem vector indexing did not finish")

    def search(self, body):
        scope = body.get("scope")
        if isinstance(scope, list):
            raise ValueError("Configure upstream supportsMultiScope=false")
        tags = [self.run_tag, self.tag(body["user_id"])]
        if scope is not None:
            tags.append(self.tag(body["user_id"], scope))
        params = {"query": body["query"], "tags": tags, "tag_mode": "all",
                  "tag_match": "exact", "current_only": "true", "limit": body.get("limit", 20)}
        result = self.call("GET", "/recall?" + urlencode(params, doseq=True))
        # Never remove noise using expectations, lifecycle labels, or fixture scope.
        return {"results": [{"id": self.reverse[r.get("id") or r["memory"]["id"]]}
                            for r in result["results"]]}


def prepare(upstream, port):
    actual = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if actual != REVISION:
        raise ValueError("Official checkout revision mismatch: " + actual)
    subprocess.run(["git", "-C", str(upstream), "diff", "--exit-code", REVISION,
                    "--", "fixtures", "src/utils/buildRetrievalReport.ts"], check=True)
    config = upstream / "providers.config.json"
    providers = json.loads(config.read_text())
    providers["automem"] = {"envVar": "PRECISIONMEMBENCH_URL", "defaultUrl": f"http://127.0.0.1:{port}",
                            "seedDelayMs": 0, "supportsUpdate": True, "supportsMultiScope": False}
    config.write_text(json.dumps(providers, indent=2) + "\n")
    session = upstream / "src/session-retrieval.external.eval.test.ts"
    # Upstream forgets to await alias writes; retain all assertions, fix ordering only.
    session.write_text(session.read_text().replace("          adapter.updateBeliefAliases(",
                                                  "          await adapter.updateBeliefAliases("))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--isolated", action="store_true", required=True)
    parser.add_argument("--port", type=int, default=18099)
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    endpoint = local_url(args.endpoint)
    prepare(args.upstream, args.port)
    beliefs = json.loads((args.upstream / "fixtures/beliefs.seed.json").read_text())
    protocol = Protocol(endpoint, os.getenv("AUTOMEM_EVAL_TOKEN", "test-token"), beliefs, args.trace)

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                route = (self.command, self.path)
                if route == ("DELETE", "/reset"):
                    result = protocol.reset()
                elif route in {("POST", "/add"), ("PUT", "/update")}:
                    result = protocol.add(body, self.command == "PUT")
                elif route == ("POST", "/wait"):
                    result = protocol.wait()
                elif route == ("POST", "/search"):
                    result = protocol.search(body)
                else:
                    raise ValueError("Unsupported protocol operation")
                status = 200
            except Exception as exc:
                status, result = 500, {"error": str(exc)}
                with protocol.trace.open("a") as stream:
                    stream.write(json.dumps({"error": str(exc), "route": self.path}) + "\n")
                print(result, flush=True)
            raw = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_POST = do_PUT = do_DELETE = handle_request

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        protocol.reset()
        server.server_close()


if __name__ == "__main__":
    main()
