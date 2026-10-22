"""Offline contract/regression tests; every upstream is a loopback fake."""
import contextlib
import concurrent.futures
import http.client
import io
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paid_budget_proxy import BudgetLedger, BudgetProxy, ConfigError, quote_request, _safe_failure_details
import paid_budget_proxy


PRICES = {"models": {
    "gpt-5-mini": {"input_usd_per_million": "1", "output_usd_per_million": "1"},
    "gpt-5.4-mini-2026-03-17": {"input_usd_per_million": "1", "output_usd_per_million": "2"},
    "voyage-4": {"input_usd_per_million": "1"},
    "text-embedding-3-small": {"input_usd_per_million": "1"},
}}
CHAT = {"model": "gpt-5-mini", "messages": [{"role": "user", "content": "private-prompt-秘密"}], "max_completion_tokens": 20}


def reserve_in_process(path, amount):
    ledger = BudgetLedger(path, "0.01")
    try:
        ledger.reserve("openai", "gpt-5-mini", amount)
        return True
    except Exception:
        return False


class FakeUpstream:
    def __init__(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        owner = self
        self.calls = []
        self.reply = {"model": "gpt-5-mini", "service_tier": "default", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, "choices": [{"message": {"content": "private-answer"}}]}
        self.status = 200
        self.delay = 0
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                owner.calls.append((self.path, json.loads(body), self.headers.get("Authorization")))
                time.sleep(owner.delay)
                encoded = json.dumps(owner.reply).encode()
                self.send_response(owner.status)
                if owner.status == 302:
                    self.send_header("Location", owner.url + "/redirect-target")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class PaidBudgetProxyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "budget.sqlite3"
        self.fake = FakeUpstream()
        self.env = unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": "private-api-key", "VOYAGE_API_KEY": "private-voyage-key"})
        self.env.start()
        self.proxy = None
    def tearDown(self):
        if self.proxy:
            self.proxy.close()
        self.fake.close()
        self.env.stop()
        self.tmp.cleanup()
    def start(self, cap="20", timeout=1, client_token=None):
        self.proxy = BudgetProxy(ledger_path=self.path, pricing=PRICES, cap_usd=cap,
            openai_upstream=self.fake.url, voyage_upstream=self.fake.url, timeout=timeout, client_token=client_token)
        self.proxy.start()
        return self.proxy
    def request(self, body=CHAT, route="/openai/v1/chat/completions", method="POST"):
        req = urllib.request.Request(self.proxy.url + route, data=json.dumps(body).encode() if method == "POST" else None, method=method, headers={"Content-Type": "application/json", "Authorization": "Bearer client-secret"})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)
    def test_usage_reconciles_and_exposes_only_safe_status(self):
        self.start()
        self.assertEqual(self.request()[0], 200)
        status = self.proxy.ledger.status()
        self.assertEqual(status["charged_nusd"], 15000)
        self.assertEqual(status["attempts"], 1)
        self.assertFalse(status["halted"])
        self.assertEqual(self.fake.calls[0][2], "Bearer private-api-key")
        self.assertEqual(self.request(route="/status", method="GET")[1], status)

    def test_unrelated_unauthorized_posts_leave_accounting_untouched(self):
        self.start(client_token="client-secret")
        initial = self.proxy.ledger.status()
        for headers in ([], ["Bearer wrong-private-token"], ["Bearer client-secret", "Bearer client-secret"],
                        ["Bearer nonascii-\u00e9"], ["Basic client-secret"]):
            with self.subTest(headers=len(headers)):
                connection = http.client.HTTPConnection("127.0.0.1", self.proxy.server.server_port, timeout=5)
                try:
                    connection.putrequest("POST", "/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary")
                    for value in headers:
                        connection.putheader("Authorization", value)
                    # Neither framing nor body is valid: authentication must run first.
                    connection.endheaders()
                    response = connection.getresponse()
                    self.assertEqual(response.status, 401)
                    self.assertEqual(json.loads(response.read())["error"]["code"], "unauthorized")
                finally:
                    connection.close()
                self.assertEqual(self.proxy.ledger.status(), initial)
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.proxy.ledger.rejection_path.exists())
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(self.proxy.url + "/status", timeout=5) as response:
            self.assertEqual(json.load(response), initial)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], 15000)
        self.assertEqual(self.fake.calls[0][2], "Bearer private-api-key")
        status, result = self.request(dict(CHAT, max_completion_tokens=None))
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["failure_reason"], "invalid_output_cap")
        state = self.proxy.ledger.status()
        self.assertTrue(state["halted"])
        self.assertEqual(state["attempts"], 1)
        self.assertEqual(self.request()[0], 402)
        self.proxy.close()
        self.start(client_token="client-secret")
        self.assertEqual(self.proxy.ledger.status(), state)
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertNotIn("client-secret", self.proxy.ledger.rejection_path.read_text())

    def test_authenticated_unsupported_route_still_halts(self):
        self.start(client_token="client-secret")
        status, result = self.request(route="/unsupported-private-route")
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["failure_reason"], "unsupported_route")
        self.assertTrue(self.proxy.ledger.status()["halted"])
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(self.fake.calls, [])

    def test_authenticated_embedding_lanes_use_only_provider_credentials(self):
        self.start(client_token="client-secret")
        self.fake.reply = {"usage": {"total_tokens": 5, "prompt_tokens": 5}, "data": []}
        for model, route, key in (("voyage-4", "/voyage/v1/embeddings", "private-voyage-key"),
                                  ("text-embedding-3-small", "/openai/v1/embeddings", "private-api-key")):
            self.assertEqual(self.request({"model": model, "input": ["private embedding"]}, route)[0], 200)
            self.assertEqual(self.fake.calls[-1][2], "Bearer " + key)
        self.assertEqual(self.proxy.ledger.status()["attempts"], 2)
        self.assertFalse(self.proxy.ledger.status()["halted"])

    def test_invalid_client_token_configuration_creates_no_ledger(self):
        for token in ("", 123, b"token", "with space", "newline\n", "nonascii-\u00e9", "delete\x7f"):
            with self.subTest(token_type=type(token).__name__), self.assertRaises(ConfigError):
                BudgetProxy(ledger_path=self.path, pricing=PRICES, client_token=token)
            self.assertFalse(self.path.exists())

    def test_cli_client_token_env_missing_or_empty_fails_before_accounting(self):
        for value in (None, ""):
            with unittest.mock.patch.dict(os.environ, {}, clear=True):
                if value is not None:
                    os.environ["TEST_LOCAL_CLIENT_TOKEN"] = value
                output, errors = io.StringIO(), io.StringIO()
                with unittest.mock.patch.object(sys, "argv", ["proxy", "--ledger", str(self.path),
                        "--pricing", "unused-pricing.json", "--client-token-env", "TEST_LOCAL_CLIENT_TOKEN"]), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    self.assertEqual(paid_budget_proxy.main(), 2)
                self.assertEqual(output.getvalue(), "")
                self.assertNotIn("TEST_LOCAL_CLIENT_TOKEN", errors.getvalue())
                self.assertFalse(self.path.exists())

    def test_cli_receipt_labels_auth_without_recording_token(self):
        pricing_path = Path(self.tmp.name) / "prices.json"
        pricing_path.write_text(json.dumps(PRICES))
        for enabled in (False, True):
            argv = ["proxy", "--ledger", str(self.path), "--pricing", str(pricing_path)]
            if enabled:
                argv += ["--client-token-env", "TEST_LOCAL_CLIENT_TOKEN"]
            output = io.StringIO()
            with unittest.mock.patch.dict(os.environ, {"TEST_LOCAL_CLIENT_TOKEN": "private-local-token"}), \
                    unittest.mock.patch.object(sys, "argv", argv), \
                    unittest.mock.patch.object(paid_budget_proxy, "BudgetProxy") as factory, \
                    contextlib.redirect_stdout(output):
                factory.return_value.url = "http://127.0.0.1:12345"
                factory.return_value.client_auth_required = enabled
                self.assertEqual(paid_budget_proxy.main(), 0)
                self.assertEqual(factory.call_args.kwargs["client_token"], "private-local-token" if enabled else None)
            self.assertEqual(json.loads(output.getvalue())["client_auth_required"], enabled)
            self.assertNotIn("private-local-token", output.getvalue())
            self.assertNotIn("TEST_LOCAL_CLIENT_TOKEN", output.getvalue())
    def test_standard_service_tier_is_injected_before_quote_and_forward(self):
        self.start()
        self.assertEqual(self.request()[0], 200)
        forwarded = self.fake.calls[0][1]
        self.assertEqual(forwarded.get("service_tier"), "default")
        self.assertEqual(quote_request("openai", CHAT, PRICES), quote_request("openai", forwarded, PRICES))
        self.assertEqual(self.request(dict(CHAT, service_tier="default"))[0], 200)
        for tier in ("auto", "priority", "fast", "flex", "scale", None):
            self.assertEqual(self.request(dict(CHAT, service_tier=tier))[0], 400)
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual(self.proxy.ledger.status()["attempts"], 2)

    def test_priority_response_halts_and_retains_standard_reservation(self):
        self.start()
        self.fake.reply["service_tier"] = "priority"
        expected = quote_request("openai", CHAT, PRICES)["reservation_nusd"]
        status, error = self.request()
        self.assertEqual(status, 502)
        self.assertEqual(error["error"].get("failure_reason"), "unexpected_service_tier")
        state = self.proxy.ledger.status()
        self.assertTrue(state["halted"])
        self.assertEqual(state["halt_reason"], "accounting_error")
        self.assertEqual(state["charged_nusd"], expected)
        self.assertEqual(state["pending_or_ambiguous"], 1)
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(len(self.fake.calls), 1)

    def test_missing_response_tier_halts_and_retains_reservation(self):
        self.start()
        del self.fake.reply["service_tier"]
        expected = quote_request("openai", CHAT, PRICES)["reservation_nusd"]
        self.assertEqual(self.request()[0], 502)
        self.assertTrue(self.proxy.ledger.status()["halted"])
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], expected)

    def test_explicit_standard_response_reconciles_normally(self):
        self.start()
        self.fake.reply["service_tier"] = "default"
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], 15000)
        self.assertFalse(self.proxy.ledger.status()["halted"])

    def test_unknown_price_model_routes_and_streaming_deny_before_network(self):
        self.start()
        invalid = [(dict(CHAT, model="unknown"), "/openai/v1/chat/completions"),
            (dict(CHAT, stream=True), "/openai/v1/chat/completions"),
            (dict(CHAT, n=2), "/openai/v1/chat/completions"),
            (dict(CHAT, tools=[]), "/openai/v1/chat/completions"),
            (CHAT, "/openai/v1/responses"), (CHAT, "/openai/v1/chat/completions?extra=1"),
            (dict(CHAT, max_completion_tokens=None), "/openai/v1/chat/completions")]
        for body, route in invalid:
            self.assertEqual(self.request(body, route)[0], 400)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.proxy.ledger.status()["attempts"], 0)
        with self.assertRaises(ConfigError):
            quote_request("openai", CHAT, {"models": {}})
    def test_missing_or_invalid_price_denies_before_network(self):
        self.start()
        for price in ({}, {"input_usd_per_million": "1"},
                      {"input_usd_per_million": "NaN", "output_usd_per_million": "1"}):
            self.proxy.pricing = {"models": {"gpt-5-mini": price}}
            self.assertEqual(self.request()[0], 400)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.proxy.ledger.status()["attempts"], 0)

    def test_uncapped_extractor_request_halts_campaign_before_network(self):
        self.start()
        uncapped = {"model": "gpt-5-mini", "messages": CHAT["messages"]}
        self.assertEqual(self.request(uncapped)[0], 400)
        state = self.request(route="/status", method="GET")[1]
        self.assertTrue(state["halted"])
        self.assertEqual(state["halt_reason"], "request_rejected")
        self.assertEqual(state["attempts"], 0)
        self.assertEqual(state["charged_nusd"], 0)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(self.fake.calls, [])
        self.proxy.close()
        self.proxy = None
        self.start()
        self.assertTrue(self.proxy.ledger.status()["halted"])
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(self.fake.calls, [])

    def test_summary_missing_path_does_not_create_parent_or_ledger(self):
        missing = Path(self.tmp.name) / "not-created" / "budget.sqlite3"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("paid_budget_proxy.py")),
            "--ledger", str(missing), "--summary"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertFalse(missing.exists())
        self.assertFalse(missing.parent.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_summary_ignores_cap_and_preserves_existing_ledger(self):
        ledger = BudgetLedger(self.path, "20")
        ledger.reserve("openai", "gpt-5-mini", 1000000)
        expected = ledger.status()
        before = self.path.read_bytes()
        before_stat = self.path.stat()
        for cap in ("0.0001", "20.01", "not-a-price"):
            with self.subTest(cap=cap):
                result = subprocess.run([sys.executable, str(Path(__file__).with_name("paid_budget_proxy.py")),
                    "--ledger", str(self.path), "--summary", "--cap-usd", cap], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.path.stat().st_mtime_ns, before_stat.st_mtime_ns)
                self.assertEqual(ledger.status(), expected)

    def test_summary_reads_committed_live_wal_with_uri_characters(self):
        path = Path(self.tmp.name) / "budget #?.sqlite3"
        ledger = BudgetLedger(path, "20")
        writer = sqlite3.connect(path)
        try:
            self.assertEqual(writer.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            ledger.reserve("openai", "gpt-5-mini", 1000000)
            expected = ledger.status()
            wal = Path(str(path) + "-wal")
            self.assertGreater(wal.stat().st_size, 0)
            before_db, before_wal = path.read_bytes(), wal.read_bytes()
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("paid_budget_proxy.py")),
                "--ledger", str(path), "--summary", "--cap-usd", "0.0001"], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual(path.read_bytes(), before_db)
            self.assertEqual(wal.read_bytes(), before_wal)
        finally:
            writer.close()

    def test_summary_empty_existing_file_is_not_initialized(self):
        self.path.touch()
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("paid_budget_proxy.py")),
            "--ledger", str(self.path), "--summary"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.path.read_bytes(), b"")
        self.assertEqual(result.stdout, "")

    def test_unhashable_admission_fields_halt_without_spend(self):
        cases = []
        for value in ([], {}):
            cases.extend([
                ({"model": "gpt-5-mini", "messages": [{"role": value, "content": "text"}], "max_completion_tokens": 20}, "/openai/v1/chat/completions"),
                ({"model": "voyage-4", "input": ["text"], "input_type": value, "output_dimension": 1024}, "/voyage/v1/embeddings"),
                ({"model": "text-embedding-3-small", "input": "text", "encoding_format": value}, "/openai/v1/embeddings"),
            ])
        for index, (body, route) in enumerate(cases):
            with self.subTest(case=index):
                self.path = Path(self.tmp.name) / f"admission-{index}.sqlite3"
                self.start()
                try:
                    self.assertEqual(self.request(body, route)[0], 400)
                    state = self.request(route="/status", method="GET")[1]
                    self.assertTrue(state["halted"])
                    self.assertEqual(state["halt_reason"], "request_rejected")
                    self.assertEqual(state["attempts"], 0)
                    self.assertEqual(state["charged_nusd"], 0)
                    self.assertEqual(self.request()[0], 402)
                    self.assertEqual(self.fake.calls, [])
                finally:
                    self.proxy.close()
                    self.proxy = None

    def test_missing_voyage_key_halts_without_spend(self):
        self.start()
        body = {"model": "voyage-4", "input": ["text"], "output_dimension": 1024}
        with unittest.mock.patch.dict(os.environ, {"VOYAGE_API_KEY": ""}):
            self.assertEqual(self.request(body, "/voyage/v1/embeddings")[0], 503)
        state = self.request(route="/status", method="GET")[1]
        self.assertTrue(state["halted"])
        self.assertEqual(state["halt_reason"], "request_rejected")
        self.assertEqual(state["attempts"], 0)
        self.assertEqual(state["charged_nusd"], 0)
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(self.fake.calls, [])

    def test_fixed_rejection_reasons_and_durable_safe_ledger_sidecar(self):
        cases = [
            (dict(CHAT), "/private-api-key?private-prompt=private-answer", "unsupported_route", "unsupported_route"),
            (dict(CHAT, model="private-api-key"), "/openai/v1/chat/completions", "unsupported_model", "openai"),
            (dict(CHAT, **{"private-prompt": "private-answer"}), "/openai/v1/chat/completions", "unsupported_fields", "openai"),
            (dict(CHAT, max_completion_tokens=None), "/openai/v1/chat/completions", "invalid_output_cap", "openai"),
            (dict(CHAT, service_tier="priority"), "/openai/v1/chat/completions", "unsupported_service_tier", "openai"),
        ]
        for index, (body, route, reason, classification) in enumerate(cases):
            with self.subTest(reason=reason):
                self.path = Path(self.tmp.name) / f"diagnostic-{index}.sqlite3"
                self.start()
                buffer = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                        status, result = self.request(body, route)
                    self.assertEqual(status, 400)
                    self.assertEqual(result["error"].get("failure_reason"), reason)
                    state = self.proxy.ledger.status()
                    self.assertTrue(state["halted"])
                    self.assertEqual(state["halt_reason"], "request_rejected")
                    self.assertEqual(state["attempts"], 0)
                    self.assertEqual(state["charged_nusd"], 0)
                    sidecar = Path(str(self.path) + ".rejections.jsonl")
                    recorded = sidecar.read_bytes()
                    rows = [json.loads(line) for line in recorded.splitlines()]
                    self.assertEqual(rows[0]["reason"], reason)
                    self.assertEqual(rows[0]["route"], classification)
                    for secret in ("private-api-key", "private-prompt", "private-answer", "client-secret"):
                        self.assertNotIn(secret, recorded.decode() + json.dumps(result) + buffer.getvalue())
                    self.proxy.close()
                    self.proxy = None
                    self.start()
                    self.assertTrue(self.proxy.ledger.status()["halted"])
                    self.assertEqual(sidecar.read_bytes(), recorded)
                    self.assertEqual(self.request()[0], 402)
                    self.assertEqual(self.fake.calls, [])
                finally:
                    self.proxy.close()
                    self.proxy = None

    def test_rejection_sidecar_write_failure_still_commits_halt(self):
        self.start()
        self.proxy.ledger.rejection_path = Path(self.tmp.name) / "unavailable-directory" / "rejections.jsonl"
        status, result = self.request(dict(CHAT, max_completion_tokens=None))
        self.assertEqual(status, 503)
        self.assertEqual(result["error"]["code"], "accounting_unavailable")
        state = self.proxy.ledger.status()
        self.assertTrue(state["halted"])
        self.assertEqual(state["halt_reason"], "request_rejected")
        self.assertEqual(state["charged_nusd"], 0)
        self.assertEqual(state["attempts"], 0)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.request()[0], 402)

    def test_shared_ledger_serializes_safe_rejection_sidecar_rows(self):
        ledger = BudgetLedger(self.path)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: BudgetLedger(self.path).reject_request("unsupported_fields", "openai"), range(8)))
        rows = [json.loads(line) for line in ledger.rejection_path.read_text().splitlines()]
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(row["reason"] == "unsupported_fields" and row["route"] == "openai" for row in rows))
        self.assertTrue(ledger.status()["halted"])
        self.assertEqual(ledger.status()["charged_nusd"], 0)
        self.assertEqual(ledger.status()["attempts"], 0)

    def test_unknown_config_message_never_becomes_a_diagnostic_value(self):
        self.assertEqual(getattr(ConfigError("private-api-key private-prompt"), "reason", None), "invalid_request")

    def test_invalid_usage_remains_charged(self):
        self.start()
        expected = quote_request("openai", CHAT, PRICES)["reservation_nusd"]
        self.fake.reply["usage"] = {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2}
        self.assertEqual(self.request()[0], 502)
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], expected)
        self.assertTrue(self.proxy.ledger.status()["halted"])
        self.assertEqual(self.request()[0], 402)

    def test_nested_unicode_and_protocol_overhead_reservation(self):
        # Regression: len(str)/4 under-reserves non-ASCII and structured content.
        body = dict(CHAT, messages=[{"role": "user", "content": [{"type": "text", "text": "秘密😀" * 100}]}])
        quote = quote_request("openai", body, PRICES)
        self.assertGreaterEqual(quote["input_tokens"], len(json.dumps(body, ensure_ascii=False).encode("utf-8")))
        self.assertEqual(quote["output_tokens"], 20)
        for field in ("max_tokens", "max_completion_tokens"):
            capped = {"model": "gpt-5-mini", "messages": CHAT["messages"], field: 300}
            self.assertEqual(quote_request("openai", capped, PRICES)["output_tokens"], 300)
        with self.assertRaises(ConfigError):
            quote_request("openai", dict(body, max_tokens=2), PRICES)
    def test_timeout_halts_and_keeps_reservation(self):
        self.start(timeout=0.05)
        expected = quote_request("openai", CHAT, PRICES)["reservation_nusd"]
        self.fake.delay = 0.15
        self.assertEqual(self.request()[0], 504)
        state = self.proxy.ledger.status()
        self.assertEqual(state["charged_nusd"], expected)
        self.assertTrue(state["halted"])
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(len(self.fake.calls), 1)

    def test_missing_usage_halts_and_keeps_reservation(self):
        self.start()
        expected = quote_request("openai", CHAT, PRICES)["reservation_nusd"]
        self.fake.reply = {"choices": []}
        status, error = self.request()
        self.assertEqual(status, 502)
        self.assertEqual(error["error"].get("failure_reason"), "missing_usage")
        state = self.proxy.ledger.status()
        self.assertEqual(state["charged_nusd"], expected)
        self.assertTrue(state["halted"])
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(len(self.fake.calls), 1)

    def test_sdk_style_repeated_attempts_are_independently_counted(self):
        self.start()
        for _ in range(3):
            self.assertEqual(self.request()[0], 200)
        state = self.proxy.ledger.status()
        self.assertEqual(state["charged_nusd"], 15000 * 3)
        self.assertEqual(state["attempts"], 3)
        self.assertEqual(len(self.fake.calls), 3)

    def test_restart_retains_pending_and_settled_spend(self):
        self.start()
        self.assertEqual(self.request()[0], 200)
        self.proxy.ledger.reserve("voyage", "voyage-4", 2000)
        self.proxy.close()
        self.proxy = None
        self.start()
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], 17000)
        self.assertEqual(self.proxy.ledger.status()["attempts"], 2)
    def test_concurrent_processes_cannot_overspend(self):
        BudgetLedger(self.path, "0.01")
        ctx = multiprocessing.get_context("spawn")
        with concurrent.futures.ProcessPoolExecutor(max_workers=4, mp_context=ctx) as pool:
            admitted = list(pool.map(reserve_in_process, [str(self.path)] * 12, [3000000] * 12))
        status = BudgetLedger(self.path, "0.01").status()
        self.assertEqual(sum(admitted), 3)
        self.assertEqual(status["charged_nusd"], 9000000)
        self.assertTrue(status["halted"])
    def test_concurrent_http_cap_halts_and_denies_following_attempts(self):
        quote = quote_request("openai", CHAT, PRICES)["reservation_nusd"]
        self.start(cap=str(quote / 1e9))
        self.fake.delay = 0.1
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.request()[0], range(8)))
        self.assertEqual(results.count(200), 1)
        self.assertEqual(results.count(402), 7)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertTrue(self.proxy.ledger.status()["halted"])
        self.assertEqual(self.request()[0], 402)
    def test_pathological_usage_overflow_still_persists_a_halt(self):
        self.start()
        self.fake.reply["usage"] = {"prompt_tokens": 10 ** 100, "completion_tokens": 1, "total_tokens": 10 ** 100 + 1}
        self.assertEqual(self.request()[0], 502)
        self.assertTrue(self.proxy.ledger.status()["halted"])
        self.assertEqual(self.request()[0], 402)

    def test_usage_above_bound_halts_even_if_charge_would_fit_cap(self):
        self.start()
        self.fake.reply["usage"] = {"prompt_tokens": 10, "completion_tokens": 100000, "total_tokens": 100010}
        self.assertEqual(self.request()[0], 502)
        self.assertTrue(self.proxy.ledger.status()["halted"])
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], 100010000)
        self.assertEqual(self.request()[0], 402)
    def test_openai_scorer_embedding_reconciles_input_only_usage(self):
        self.start()
        self.fake.reply = {"data": [{"embedding": [0.0]}], "usage": {"prompt_tokens": 5, "total_tokens": 5}}
        body = {"model": "text-embedding-3-small", "input": "scorer text", "encoding_format": "base64"}
        self.assertEqual(self.request(body, "/openai/v1/embeddings")[0], 200)
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], 5000)
        self.assertEqual(self.fake.calls[0][2], "Bearer private-api-key")
        self.assertEqual(self.fake.calls[0][0], "/v1/embeddings")
        self.assertEqual(self.request(dict(body, model="voyage-4"), "/openai/v1/embeddings")[0], 400)

    def test_voyage_reconciles_input_usage(self):
        self.start()
        self.fake.reply = {"data": [{"embedding": [0.0] * 1024}], "usage": {"total_tokens": 5}}
        body = {"model": "voyage-4", "input": ["秘密😀", "hello"], "output_dimension": 1024}
        self.assertEqual(self.request(body, "/voyage/v1/embeddings")[0], 200)
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], 5000)
        self.assertEqual(self.fake.calls[0][0], "/v1/embeddings")
        self.assertEqual(self.request(dict(body, output_dimension=256), "/voyage/v1/embeddings")[0], 400)
    def test_errors_logs_and_ledger_do_not_leak_sensitive_data_or_redirect(self):
        self.start()
        self.fake.reply = {"error": {"message": "private-api-key private-prompt-秘密 private-answer"}}
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer), contextlib.redirect_stdout(buffer):
            self.fake.status = 500
            status, error = self.request()
            self.assertEqual(status, 502)
            self.assertEqual(self.request()[0], 402)
        self.assertEqual(len(self.fake.calls), 1)
        expected = quote_request("openai", CHAT, PRICES)["reservation_nusd"]
        self.assertEqual(self.proxy.ledger.status()["charged_nusd"], expected)
        combined = json.dumps(error) + buffer.getvalue()
        with sqlite3.connect(self.path) as db:
            combined += "\n".join(db.iterdump())
        for secret in ("private-api-key", "private-prompt", "private-answer", "client-secret"):
            self.assertNotIn(secret, combined)
    def test_safe_http_error_codes_and_malformed_bodies(self):
        codes = ("insufficient_quota", "rate_limit_exceeded", "model_not_found", "invalid_api_key", "private-api-key", None, ["private-prompt"])
        for code in codes:
            with self.subTest(code=code):
                encoded = json.dumps({"error": {"code": code, "message": "private-prompt"}}).encode()
                exc = urllib.error.HTTPError("https://client-secret.invalid", 401, "private-api-key", {}, io.BytesIO(encoded))
                details = _safe_failure_details(exc)
                expected = code if isinstance(code, str) and code in codes[:4] else "other"
                self.assertEqual(details, {"failure_reason": "upstream_http_error", "upstream_status": 401, "upstream_error_code": expected})
                self.assertNotIn("private", json.dumps(details))
        for encoded in (b"private-api-key", b"x" * (16 * 1024 + 1)):
            exc = urllib.error.HTTPError("https://client-secret.invalid", 500, "private-prompt", {}, io.BytesIO(encoded))
            self.assertEqual(_safe_failure_details(exc)["upstream_error_code"], "other")

    def test_http_error_diagnostics_are_allowlisted_and_never_leak(self):
        self.start()
        self.fake.status = 429
        self.fake.reply = {"error": {"code": "insufficient_quota",
            "message": "private-api-key private-prompt-秘密 private-answer", "param": "client-secret"}}
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer), contextlib.redirect_stdout(buffer):
            status, body = self.request()
        self.assertEqual(status, 502)
        error = body["error"]
        self.assertEqual(error.get("upstream_status"), 429)
        self.assertEqual(error.get("upstream_error_code"), "insufficient_quota")
        self.assertEqual(error.get("failure_reason"), "upstream_http_error")
        state = self.proxy.ledger.status()
        self.assertTrue(state["halted"])
        self.assertEqual(state["charged_nusd"], quote_request("openai", CHAT, PRICES)["reservation_nusd"])
        combined = json.dumps(body) + buffer.getvalue()
        with sqlite3.connect(self.path) as db:
            combined += "\n".join(db.iterdump())
        for secret in ("private-api-key", "private-prompt", "private-answer", "client-secret"):
            self.assertNotIn(secret, combined)

    def test_http_error_unknown_code_is_replaced_without_raw_message(self):
        self.start()
        self.fake.status = 400
        self.fake.reply = {"error": {"code": "private-api-key", "message": "private-prompt-秘密"}}
        status, body = self.request()
        self.assertEqual(status, 502)
        self.assertEqual(body["error"].get("upstream_status"), 400)
        self.assertEqual(body["error"].get("upstream_error_code"), "other")
        self.assertNotIn("private", json.dumps(body))

    def test_redirect_is_rejected_without_following_and_halts(self):
        self.start()
        self.fake.status = 302
        self.assertEqual(self.request()[0], 502)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertTrue(self.proxy.ledger.status()["halted"])

    def test_invalid_cli_config_is_sanitized_and_nonzero(self):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("paid_budget_proxy.py")),
            "--ledger", str(self.path), "--pricing", str(Path(self.tmp.name) / "private-api-key-missing.json")],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("configuration/accounting failure", result.stderr)
        self.assertNotIn("private-api-key", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.fake.calls, [])

    def test_remote_listening_missing_keys_and_unpriced_config_fail_closed(self):
        with self.assertRaises(ConfigError):
            BudgetProxy(ledger_path=self.path, pricing=PRICES, host="0.0.0.0")
        with self.assertRaises(ConfigError):
            BudgetLedger(self.path, "20.01")
        self.start()
        with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            self.assertEqual(self.request()[0], 503)
        state = self.request(route="/status", method="GET")[1]
        self.assertTrue(state["halted"])
        self.assertEqual(state["halt_reason"], "request_rejected")
        self.assertEqual(state["charged_nusd"], 0)
        self.assertEqual(self.request()[0], 402)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(state["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
