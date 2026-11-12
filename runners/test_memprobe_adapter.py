import hashlib
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memprobe import adapter as mp


def synthetic_bank(n_users=2):
    users = [
        {
            "user_id": f"user_{i:03d}",
            "memory_bank": {
                cat: [
                    {"dimension": f"{cat}_{j}", "short": f"SECRET-{i}-{cat}-{j}", "explanation": f"EXPL-{i}"}
                    for j in range(count)
                ]
                for cat, count in mp.CATEGORY_COUNTS.items()
            },
        }
        for i in range(1, n_users + 1)
    ]
    return json.dumps({"users": users}).encode()


def detail(category, score, predicted="x"):
    return {"category": category, "score": score, "predicted": predicted}


class GuardTests(unittest.TestCase):
    def test_loopback_only(self):
        for ok in ("http://localhost:8001", "http://127.0.0.1:8001/", "http://[::1]:8001"):
            self.assertTrue(mp.assert_loopback(ok))
        for bad in ("http://automem.example.com", "http://127.0.0.1@evil.example.com", "localhost:8001", ""):
            with self.assertRaises(SystemExit):
                mp.assert_loopback(bad)

    def test_user_tags_are_isolated_and_validated(self):
        self.assertNotEqual(mp.user_tag("r1", "user_001"), mp.user_tag("r1", "user_002"))
        self.assertNotEqual(mp.user_tag("r1", "user_001"), mp.user_tag("r2", "user_001"))
        for run_id, user_id in (("R1", "user_001"), ("r1", "user:001"), ("", "user_001")):
            with self.assertRaises(ValueError):
                mp.user_tag(run_id, user_id)

    def test_verify_checkout_pins_commit(self):
        run = lambda *a, **k: SimpleNamespace(stdout=mp.UPSTREAM_COMMIT + "\n")
        mp.verify_checkout(Path("."), run=run)
        with self.assertRaises(SystemExit):
            mp.verify_checkout(Path("."), run=lambda *a, **k: SimpleNamespace(stdout="deadbeef\n"))

        def not_a_repo(*a, **k):
            raise mp.subprocess.CalledProcessError(128, "git")

        with self.assertRaisesRegex(SystemExit, "cannot read git HEAD"):
            mp.verify_checkout(Path("."), run=not_a_repo)


class TransportTests(unittest.TestCase):
    """http_transport against real loopback servers; nothing leaves 127.0.0.1."""

    def serve(self, respond):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                respond(self)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        for cleanup in (lambda: thread.join(5), server.server_close, server.shutdown):  # run in reverse
            self.addCleanup(cleanup)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_returns_json_and_sends_api_key(self):
        seen = {}

        def ok(handler):
            seen.update(path=handler.path, key=handler.headers.get("X-Api-Key"))
            body = b'{"status": "success"}'
            handler.send_response(200)
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)

        get = mp.http_transport(self.serve(ok), "tok", timeout=5)
        self.assertEqual(get("/memory/by-tag", {"tags": "t", "limit": 1}), {"status": "success"})
        self.assertEqual(seen["key"], "tok")
        self.assertTrue(seen["path"].startswith("/memory/by-tag?"))

    def test_redirects_are_refused_and_never_forward_the_api_key(self):
        hits = []

        def record(handler):
            hits.append(handler.headers.get("X-Api-Key"))
            handler.send_response(200)
            handler.send_header("Content-Length", "2")
            handler.end_headers()
            handler.wfile.write(b"{}")

        bystander = self.serve(record)
        for location in (f"{bystander}/recall", "http://redirect-target.invalid/recall"):
            with self.subTest(location=location):

                def redirect(handler, location=location):
                    handler.send_response(302)
                    handler.send_header("Location", location)
                    handler.send_header("Content-Length", "0")
                    handler.end_headers()

                get = mp.http_transport(self.serve(redirect), "tok", timeout=5)
                with self.assertRaisesRegex(mp.ProtocolError, "refusing HTTP 302 redirect"):
                    get("/recall", {"query": "q"})
        self.assertEqual(hits, [])  # the redirect target was never contacted

    def test_environment_proxies_are_ignored(self):
        proxied = []

        def reply(handler, payload):
            handler.send_response(200)
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        def via_proxy(handler):
            proxied.append(handler.headers.get("X-Api-Key"))
            reply(handler, b"{}")

        proxy_url = self.serve(via_proxy)
        target = self.serve(lambda handler: reply(handler, b'{"via": "direct"}'))
        with patch.dict(os.environ, {"http_proxy": proxy_url, "HTTP_PROXY": proxy_url}):
            for name in ("no_proxy", "NO_PROXY"):
                os.environ.pop(name, None)
            # The opener reads the environment when it is built, so build it inside the patch.
            get = mp.http_transport(target, "tok", timeout=5)
            self.assertEqual(get("/recall", {"query": "q"}), {"via": "direct"})
        self.assertEqual(proxied, [])  # the proxy never saw the request or the key


class BankTests(unittest.TestCase):
    def write(self, raw):
        path = Path(tempfile.mkdtemp()) / "bank.json"
        path.write_bytes(raw)
        return path

    def test_load_bank_checks_hash_and_shape(self):
        raw = synthetic_bank()
        digest = hashlib.sha256(raw).hexdigest()
        targets = mp.load_bank(self.write(raw), expected_sha256=digest, expected_users=2)
        self.assertEqual(len(targets), 2 * 31)
        with self.assertRaises(SystemExit):
            mp.load_bank(self.write(raw), expected_sha256="0" * 64, expected_users=2)
        with self.assertRaisesRegex(ValueError, "expected 3 users"):
            mp.load_bank(self.write(raw), expected_sha256=digest, expected_users=3)

    def test_load_bank_rejects_wrong_category_counts(self):
        data = json.loads(synthetic_bank(1))
        data["users"][0]["memory_bank"]["self_model"].pop()
        raw = json.dumps(data).encode()
        with self.assertRaisesRegex(ValueError, "self_model"):
            mp.load_bank(self.write(raw), expected_sha256=hashlib.sha256(raw).hexdigest(), expected_users=1)

    def test_probe_never_carries_reference_value_or_explanation(self):
        raw = synthetic_bank(1)
        target = mp.load_bank(self.write(raw), expected_sha256=hashlib.sha256(raw).hexdigest(), expected_users=1)[0]
        seen = json.dumps(target.probe()) + repr(target) + mp.probe_query(target.category, target.dimension, "guide")
        self.assertNotIn("SECRET", seen)
        self.assertNotIn("EXPL", seen)
        self.assertEqual(mp.probe_query("self_model", "risk_tolerance"), "What best describes the user's risk tolerance?")


class ReaderTests(unittest.TestCase):
    TAG = "memprobe:r1:user_001"

    def test_full_store_pages_and_drops_prefix_overmatches(self):
        calls = []
        pages = [
            {"memories": [{"id": "a", "tags": [self.TAG]}, {"id": "x", "tags": [self.TAG + "0"]}], "has_more": True},
            {"memories": [{"id": "b", "tags": [self.TAG.upper()]}], "has_more": False},
        ]

        def transport(path, params):
            calls.append((path, dict(params)))
            return pages[len(calls) - 1]

        got = mp.AutoMemReader(transport, page_size=2).full_store(self.TAG)
        self.assertEqual([m["id"] for m in got], ["a", "b"])
        self.assertEqual([c[1]["offset"] for c in calls], [0, 2])
        self.assertTrue(all(c[0] == "/memory/by-tag" and c[1]["tags"] == self.TAG for c in calls))

    def test_full_store_fails_closed(self):
        with self.assertRaises(mp.ProtocolError):
            mp.AutoMemReader(lambda p, q: {"status": "error"}).full_store(self.TAG)
        with self.assertRaises(mp.ProtocolError):  # has_more forever, empty pages
            mp.AutoMemReader(lambda p, q: {"memories": [], "has_more": True}).full_store(self.TAG)

    def test_top_k_uses_exact_isolated_tag_and_normalizes(self):
        seen = {}

        def transport(path, params):
            seen.update(path=path, params=params)
            hit = {"memory": {"id": "m1", "content": "c", "tags": [self.TAG], "t_invalid": "2026-02-01"}, "score": 0.9}
            return {"results": [hit] * 7}

        got = mp.AutoMemReader(transport).top_k(self.TAG, "q")
        self.assertEqual(len(got), mp.TOP_K)
        self.assertEqual(got[0]["id"], "m1")
        self.assertEqual(got[0]["t_invalid"], "2026-02-01")
        self.assertEqual(seen["path"], "/recall")
        self.assertEqual(seen["params"]["tags"], [self.TAG])
        self.assertEqual((seen["params"]["tag_match"], seen["params"]["tag_mode"]), ("exact", "all"))
        self.assertEqual(seen["params"]["limit"], mp.TOP_K)

    def test_transport_errors_are_not_swallowed(self):
        def boom(path, params):
            raise OSError("connection refused")

        with self.assertRaises(OSError):
            mp.AutoMemReader(boom).top_k(self.TAG, "q")

    def test_footprint_counts_superseded_records(self):
        fp = mp.footprint([{"content": "abcd"}, {"content": "ab", "t_invalid": "2026-02-01"}])
        self.assertEqual(fp, {"items": 2, "mean_chars": 3.0, "invalidated": 1})
        self.assertEqual(mp.footprint([])["mean_chars"], 0.0)


class MetricTests(unittest.TestCase):
    def test_no_judge_is_not_scored_with_null_metrics(self):
        s = mp.summarize([detail("skill_memory", 1.0)], judge_available=False)
        self.assertEqual(s["status"], "not_scored")
        for key in ("recovery", "answer_rate", "abstention_rate", "answered_recovery"):
            self.assertIsNone(s[key])
        self.assertEqual(mp.summarize([], judge_available=True)["status"], "not_scored")

    def test_missing_judge_score_is_not_scored(self):
        s = mp.summarize([detail("skill_memory", 1.0), detail("self_model", None)], judge_available=True)
        self.assertEqual((s["status"], s["n_scored"], s["recovery"]), ("not_scored", 1, None))

    def test_recovery_is_category_balanced_and_separate_from_answer_and_abstention(self):
        details = [
            detail("skill_memory", 1.0),
            detail("skill_memory", 1.0),
            detail("skill_memory", 1.0),
            detail("self_model", 0.0, predicted="unknown"),
        ]
        s = mp.summarize(details, judge_available=True)
        self.assertEqual(s["status"], "scored")
        self.assertAlmostEqual(s["recovery"], 0.5)  # flat mean would be 0.75
        self.assertAlmostEqual(s["answer_rate"], 0.75)
        self.assertAlmostEqual(s["abstention_rate"], 0.25)
        self.assertAlmostEqual(s["answered_recovery"], 1.0)

    def test_wrong_answer_is_not_an_abstention(self):
        s = mp.summarize([detail("skill_memory", 0.0, predicted="plumber")], judge_available=True)
        self.assertEqual((s["recovery"], s["answer_rate"], s["abstention_rate"]), (0.0, 1.0, 0.0))

    def test_off_scale_score_raises(self):
        with self.assertRaises(ValueError):
            mp.summarize([detail("skill_memory", 0.6)], judge_available=True)


class ReportTests(unittest.TestCase):
    def test_report_is_never_paper_comparable_and_loopback_only(self):
        summary = mp.summarize([], judge_available=False)
        full = mp.build_report(access_mode="full_store", run_id="r1", endpoint="http://localhost:8001/", summary=summary)
        top = mp.build_report(access_mode="top_k", run_id="r1", endpoint="http://localhost:8001", summary=summary)
        self.assertEqual((full["k"], top["k"]), (None, mp.TOP_K))
        self.assertFalse(full["paper_comparable"])
        self.assertIsNone(full["recovery"])
        with self.assertRaises(SystemExit):
            mp.build_report(access_mode="top_k", run_id="r1", endpoint="http://10.0.0.5:8001", summary=summary)
        with self.assertRaises(ValueError):
            mp.build_report(access_mode="oracle", run_id="r1", endpoint="http://localhost:8001", summary=summary)

    def test_cli_emits_only_not_scored_reports(self):
        raw = synthetic_bank(2)
        targets = mp.load_bank(
            self._path(raw),
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            expected_users=2,
        )
        out = Path(tempfile.mkdtemp()) / "plan.json"
        with patch.object(mp, "verify_checkout"), patch.object(mp, "load_bank", return_value=targets):
            self.assertEqual(mp.main(["--checkout", ".", "--run-id", "r1", "--out", str(out)]), 0)
        plan = json.loads(out.read_text())
        self.assertEqual((plan["n_users"], plan["n_targets"]), (2, 62))
        self.assertEqual({r["status"] for r in plan["reports"]}, {"not_scored"})
        self.assertEqual({r["access_mode"] for r in plan["reports"]}, set(mp.ACCESS_MODES))

    @staticmethod
    def _path(raw):
        path = Path(tempfile.mkdtemp()) / "bank.json"
        path.write_bytes(raw)
        return path


if __name__ == "__main__":
    unittest.main()
