#!/usr/bin/env python3
"""FEB-30 release gate and store-inspection seam; not a benchmark runner yet."""
import argparse
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UPSTREAM = "https://github.com/amazon-science/feb-30-benchmark"
UPSTREAM_COMMIT = None  # No accessible official release: never invent a pin.


def request(url, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json", "User-Agent": "automem-feb30"}
    if token:
        headers["X-Api-Key"] = token
    req = urllib.request.Request(url, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    # Never send local benchmark traffic through inherited HTTP proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=30) as response:
        return json.load(response)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class StoreInspector:
    """Caller owns a fresh dedicated stack; tags alone do not isolate storage.

    Feed document text only. Gold operations/claims must never drive writes.
    No lifecycle inference, semantic matching, or official scoring is supplied.
    """
    def __init__(self, endpoint, token, run_tag):
        url = urllib.parse.urlsplit(endpoint)
        try:
            local = ipaddress.ip_address(url.hostname).is_loopback
        except ValueError:
            local = False
        if (url.scheme != "http" or not local or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("endpoint must be an HTTP loopback IP origin")
        if not run_tag.startswith("feb30-run-") or any(c.isspace() for c in run_tag):
            raise ValueError("expected a unique feb30-run-* tag")
        self.endpoint, self.token, self.tag = endpoint.rstrip("/"), token, run_tag
        self.ids = []

    def ingest_document(self, text):
        result = request(self.endpoint + "/memory", "POST",
                         {"content": text, "type": "Context", "tags": [self.tag]}, self.token)
        memory_id = result.get("memory_id") or result.get("id")
        if not isinstance(memory_id, str) or not memory_id:
            raise RuntimeError("store returned no memory id")
        self.ids.append(memory_id)
        return result

    def snapshot(self):
        # Direct ID reads retain invalidated history and persisted t_invalid.
        # This covers adapter-owned IDs only, not autonomous consolidation nodes.
        return {mid: request(self.endpoint + "/memory/" + urllib.parse.quote(mid, safe=""),
                             token=self.token) for mid in dict.fromkeys(self.ids)}


def release_preflight():
    url = "https://api.github.com/repos/amazon-science/feb-30-benchmark"
    probe = {"url": url}
    try:
        probe.update(status=200, body=request(url))
    except urllib.error.HTTPError as exc:
        probe.update(status=exc.code, body=exc.read().decode("utf-8", "replace"))
    except (OSError, ValueError) as exc:
        probe.update(status=None, error=str(exc))
    return {
        "benchmark": "FEB-30", "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked", "upstream": UPSTREAM, "upstream_commit": UPSTREAM_COMMIT,
        "reason": "Official revision, license, loader and scorer are not verified.",
        "release_probe": probe, "requested_maturation": "cold",
        "automem_executed": False, "trajectories_executed": 0,
        "intrinsic": None, "extrinsic_qa": None,
        "answerer_model": None, "judge_model": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = release_preflight()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the first raw evidence file instead of silently replacing it.
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report))
    return 2  # A preflight is never a successful AutoMem benchmark run.


if __name__ == "__main__":
    raise SystemExit(main())
