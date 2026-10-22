#!/usr/bin/env python3
"""Loopback-only, fail-closed paid API guard (stdlib; no upstream retries).

Prices must be supplied in JSON; this module intentionally has no price defaults.
See --help and docs/eval/paid-budget.md for launch instructions.
The caller MUST monitor /status and abort its harness when halted becomes true:
benchmark harnesses may catch even nonretryable HTTP errors as empty evidence.
"""
from __future__ import annotations

import argparse
import hmac
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import socket
import sys
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

NUSD_PER_USD = 1_000_000_000
MAX_BODY_BYTES = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_ERROR_BYTES = 16 * 1024
SAFE_PROVIDER_CODES = {"insufficient_quota", "rate_limit_exceeded", "model_not_found", "invalid_api_key"}
VALIDATION_REASONS = {"unexpected_upstream_status", "response_too_large", "invalid_upstream_json",
                      "missing_usage", "unexpected_service_tier", "invalid_usage"}
ALLOWED_MODELS = {
    "openai": {"gpt-5-mini", "gpt-5.4-mini-2026-03-17"},
    "voyage": {"voyage-4"},
    "openai_embeddings": {"text-embedding-3-small"},
}
ROUTES = {"/openai/v1/chat/completions": "openai", "/voyage/v1/embeddings": "voyage",
          "/openai/v1/embeddings": "openai_embeddings"}


CONFIG_REASON_CODES = {
    "Positive finite amount required": "invalid_price",
    "Explicit model pricing required": "missing_price",
    "Only standard service tier supported": "unsupported_service_tier",
    "Unsupported lane or request": "unsupported_request",
    "Unsupported model": "unsupported_model",
    "Unsupported chat request fields": "unsupported_fields",
    "Exactly one positive output token cap required": "invalid_output_cap",
    "Nonempty text messages required": "invalid_messages",
    "Only text messages supported": "invalid_messages",
    "Unsupported message role": "invalid_message_role",
    "Only text content parts supported": "invalid_text_content",
    "Only text content supported": "invalid_text_content",
    "Unsupported embedding request fields": "unsupported_fields",
    "Only 1024-dimensional float embeddings supported": "unsupported_dimensions",
    "Unsupported embedding input type": "invalid_embedding_input_type",
    "One to 128 text inputs required": "invalid_embedding_input",
    "Unsupported OpenAI embedding fields": "unsupported_fields",
    "Unsupported embedding encoding": "unsupported_encoding",
    "Unsupported embedding dimensions": "unsupported_dimensions",
    "Invalid JSON text request": "invalid_json",
    "Request too large": "invalid_request_size",
    "Cap must not exceed 20 USD": "invalid_budget_cap",
    "Invalid reservation": "invalid_reservation",
    "Upstream must be a /v1 base URL without credentials": "invalid_upstream",
    "Invalid upstream URL": "invalid_upstream",
    "Plain HTTP upstream must be loopback": "invalid_upstream",
    "Listener must bind to 127.0.0.1": "invalid_listener",
    "Positive finite timeout required": "invalid_timeout",
    "Unsupported route": "unsupported_route",
    "Unsupported request framing": "invalid_framing",
    "Content-Length required": "invalid_framing",
    "Invalid request size": "invalid_request_size",
    "Incomplete request": "incomplete_request",
    "Invalid JSON request": "invalid_json",
    "--pricing required": "missing_price",
}


class ConfigError(ValueError):
    """Only exact hardcoded messages select a public diagnostic reason."""
    def __init__(self, message):
        self.reason = CONFIG_REASON_CODES.get(message, "invalid_request") if isinstance(message, str) else "invalid_request"
        super().__init__(message)


class BudgetHalted(RuntimeError):
    pass


class _ResponseValidationError(ValueError):
    def __init__(self, reason):
        self.reason = reason if reason in VALIDATION_REASONS else "invalid_usage"
        super().__init__(self.reason)


def _safe_failure_details(exc):
    """Return only fixed reason labels, status integers and exact code matches."""
    if isinstance(exc, _ResponseValidationError):
        return {"failure_reason": exc.reason}
    if not isinstance(exc, urllib.error.HTTPError):
        return {"failure_reason": "upstream_or_accounting_error"}
    details = {"failure_reason": "upstream_http_error", "upstream_error_code": "other"}
    if type(exc.code) is int and 100 <= exc.code <= 599:
        details["upstream_status"] = exc.code
    try:
        encoded = exc.read(MAX_ERROR_BYTES + 1)
        if len(encoded) <= MAX_ERROR_BYTES:
            body = json.loads(encoded)
            error = body.get("error") if isinstance(body, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            if isinstance(code, str) and code in SAFE_PROVIDER_CODES:
                details["upstream_error_code"] = code
    except Exception:
        pass  # Malformed/oversized/unreadable errors are classified as other.
    finally:
        exc.close()
    return details


def _integer(value, minimum=0, maximum=None):
    return type(value) is int and value >= minimum and (maximum is None or value <= maximum)


def _decimal(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0:
            raise ConfigError("Positive finite amount required")
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise ConfigError("Positive finite amount required") from None


def _rate(pricing, model, kind):
    try:
        return _decimal(pricing["models"][model][kind + "_usd_per_million"])
    except (KeyError, TypeError):
        raise ConfigError("Explicit model pricing required") from None


def _charge(pricing, model, input_tokens, output_tokens, lane):
    cost = Decimal(input_tokens) * _rate(pricing, model, "input")
    if lane == "openai":
        cost += Decimal(output_tokens) * _rate(pricing, model, "output")
    return int((cost * 1000).to_integral_value(rounding=ROUND_CEILING))


def _canonical_body(lane, body):
    if lane == "openai" and isinstance(body, dict):
        if body.get("service_tier", "default") != "default":
            raise ConfigError("Only standard service tier supported")
        # Omission means auto/project settings upstream. Pin the priced tier and
        # include the injected field in the byte bound before reserving spend.
        return dict(body, service_tier="default")
    return body


def quote_request(lane, body, pricing):
    """Reserve at most one token per serialized UTF-8 byte plus protocol slack.

    One byte/token is a deliberately expensive upper bound for text tokenizers.
    JSON serialization also includes response schemas and field names. Unsupported
    modalities, tools and multiple completions are rejected instead of guessed.
    """
    body = _canonical_body(lane, body)
    if lane not in ALLOWED_MODELS or not isinstance(body, dict):
        raise ConfigError("Unsupported lane or request")
    model = body.get("model")
    if not isinstance(model, str) or model not in ALLOWED_MODELS[lane]:
        raise ConfigError("Unsupported model")
    output_tokens = 0
    if lane == "openai":
        allowed = {"model", "messages", "max_tokens", "max_completion_tokens", "response_format",
                   "temperature", "top_p", "seed", "stop", "reasoning_effort", "verbosity", "stream", "n", "user", "service_tier"}
        if set(body) - allowed or body.get("stream", False) is not False or body.get("n", 1) != 1:
            raise ConfigError("Unsupported chat request fields")
        caps = [key for key in ("max_tokens", "max_completion_tokens") if key in body]
        if len(caps) != 1 or not _integer(body[caps[0]], 1, 1_000_000):
            raise ConfigError("Exactly one positive output token cap required")
        output_tokens = body[caps[0]]
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ConfigError("Nonempty text messages required")
        for message in messages:
            if not isinstance(message, dict) or set(message) - {"role", "content", "name"}:
                raise ConfigError("Only text messages supported")
            role = message.get("role")
            if not isinstance(role, str) or role not in {"system", "developer", "user", "assistant"}:
                raise ConfigError("Unsupported message role")
            content = message.get("content")
            if isinstance(content, list):
                if not content or any(not isinstance(part, dict) or set(part) != {"type", "text"}
                    or part.get("type") != "text" or not isinstance(part.get("text"), str) for part in content):
                    raise ConfigError("Only text content parts supported")
            elif not isinstance(content, str):
                raise ConfigError("Only text content supported")
        overhead_items = len(messages)
    elif lane == "voyage":
        if set(body) - {"model", "input", "input_type", "output_dimension", "output_dtype", "truncation"}:
            raise ConfigError("Unsupported embedding request fields")
        if body.get("output_dimension", 1024) != 1024 or body.get("output_dtype", "float") != "float":
            raise ConfigError("Only 1024-dimensional float embeddings supported")
        if "input_type" in body and (not isinstance(body["input_type"], str) or body["input_type"] not in {"query", "document"}):
            raise ConfigError("Unsupported embedding input type")
        texts = body.get("input")
        if isinstance(texts, str):
            texts = [texts]
        if not isinstance(texts, list) or not 1 <= len(texts) <= 128 or any(not isinstance(t, str) for t in texts):
            raise ConfigError("One to 128 text inputs required")
        overhead_items = len(texts)
    else:
        if set(body) - {"model", "input", "encoding_format", "dimensions", "user"}:
            raise ConfigError("Unsupported OpenAI embedding fields")
        encoding_format = body.get("encoding_format", "float")
        if not isinstance(encoding_format, str) or encoding_format not in {"float", "base64"}:
            raise ConfigError("Unsupported embedding encoding")
        if "dimensions" in body and not _integer(body["dimensions"], 1, 1536):
            raise ConfigError("Unsupported embedding dimensions")
        texts = body.get("input")
        if isinstance(texts, str):
            texts = [texts]
        if not isinstance(texts, list) or not 1 <= len(texts) <= 128 or any(not isinstance(t, str) for t in texts):
            raise ConfigError("One to 128 text inputs required")
        overhead_items = len(texts)
    try:
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise ConfigError("Invalid JSON text request") from None
    if len(encoded) > MAX_BODY_BYTES:
        raise ConfigError("Request too large")
    input_tokens = len(encoded) + 1024 + 64 * overhead_items
    return {"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "reservation_nusd": _charge(pricing, model, input_tokens, output_tokens, lane)}


def _read_ledger_status(db):
    # A single read transaction keeps cap/halt and attempt totals consistent.
    db.execute("BEGIN")
    cap, halted = db.execute("SELECT cap_nusd, halted FROM budget WHERE id=1").fetchone()
    count, charged, pending = db.execute("SELECT count(*), coalesce(sum(charged_nusd),0), coalesce(sum(state='reserved'),0) FROM attempts").fetchone()
    return {"cap_nusd": cap, "charged_nusd": charged, "remaining_nusd": max(0, cap - charged),
            "attempts": count, "pending_or_ambiguous": pending, "halted": bool(halted), "halt_reason": halted}


def read_ledger_status(path):
    """Inspect an existing ledger without initialization or cap changes."""
    # mode=ro refuses missing paths and prevents SQLite database writes. Do not
    # use immutable=1: summaries must include a live writer's WAL transactions.
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        return _read_ledger_status(db)
    finally:
        db.close()


class BudgetLedger:
    """SQLite transactions serialize admission across threads AND processes.

    A reserved attempt is immediately charged at its worst case. Crash, timeout,
    HTTP errors and absent/invalid usage leave it charged. Only verified successful
    usage reduces that charge; late requests cannot clear a persistent halt.
    """
    def __init__(self, path, cap_usd="20"):
        cap_decimal = _decimal(cap_usd)
        if cap_decimal > 20:
            raise ConfigError("Cap must not exceed 20 USD")
        self.cap_nusd = int((cap_decimal * NUSD_PER_USD).to_integral_value(rounding=ROUND_CEILING))
        self.path = Path(path).resolve()
        self.rejection_path = Path(str(self.path) + ".rejections.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), cap_nusd INTEGER NOT NULL, halted TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, lane TEXT NOT NULL, model TEXT NOT NULL, reserved_nusd INTEGER NOT NULL CHECK(reserved_nusd>0), charged_nusd INTEGER NOT NULL CHECK(charged_nusd>=0), state TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER)")
            db.execute("INSERT OR IGNORE INTO budget VALUES (1, ?, NULL)", (self.cap_nusd,))
            # An existing ledger may be made stricter, never reset or raised.
            db.execute("UPDATE budget SET cap_nusd=min(cap_nusd, ?) WHERE id=1", (self.cap_nusd,))
            db.execute("UPDATE budget SET halted=coalesce(halted, 'cap_reduced') WHERE id=1 AND cap_nusd < (SELECT coalesce(sum(charged_nusd),0) FROM attempts)")
    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()
    def reserve(self, lane, model, amount):
        if not _integer(amount, 1):
            raise ConfigError("Invalid reservation")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cap, halted = db.execute("SELECT cap_nusd, halted FROM budget WHERE id=1").fetchone()
            total = db.execute("SELECT coalesce(sum(charged_nusd),0) FROM attempts").fetchone()[0]
            if halted or total + amount > cap:
                db.execute("UPDATE budget SET halted=coalesce(halted, 'budget_cap') WHERE id=1")
                db.commit()  # Raising inside a transaction would roll back the halt.
                raise BudgetHalted("Paid budget halted")
            attempt_id = str(uuid.uuid4())
            db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, 'reserved', NULL, NULL)",
                       (attempt_id, lane, model, amount, amount))
        return attempt_id
    def halt(self, reason="accounting_error"):
        if reason not in {"accounting_error", "reservation_exceeded", "request_rejected"}:
            reason = "accounting_error"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE budget SET halted=coalesce(halted, ?) WHERE id=1", (reason,))
    def reject_request(self, reason, route):
        # Serialize sidecar appends with the shared ledger's write lock. The
        # diagnostic is fsynced before the halt becomes visible to the monitor.
        reason = reason if reason in CONFIG_REASON_CODES.values() else "invalid_request"
        route = route if route in ROUTES.values() else "unsupported_route"
        record = {"reason": reason, "route": route, "at_ns": time.time_ns()}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE budget SET halted=coalesce(halted, 'request_rejected') WHERE id=1")
            try:
                fd = os.open(self.rejection_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                with os.fdopen(fd, "a") as stream:
                    stream.write(json.dumps(record) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                db.commit()  # Diagnostic I/O failure must never roll back a halt.
                raise
    def settle(self, attempt_id, actual_nusd, input_tokens, output_tokens, bound_exceeded=False):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT reserved_nusd, state FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if row is None or row[1] != "reserved" or not _integer(actual_nusd):
                db.execute("UPDATE budget SET halted=coalesce(halted, 'accounting_error') WHERE id=1")
                db.commit()
                raise BudgetHalted("Invalid accounting transition")
            exceeded = bound_exceeded or actual_nusd > row[0]
            db.execute("UPDATE attempts SET charged_nusd=?, state=?, input_tokens=?, output_tokens=? WHERE id=?",
                (max(row[0], actual_nusd) if exceeded else actual_nusd,
                 "bound_exceeded" if exceeded else "settled", input_tokens, output_tokens, attempt_id))
            if exceeded:
                db.execute("UPDATE budget SET halted=coalesce(halted, 'reservation_exceeded') WHERE id=1")
        if exceeded:
            raise BudgetHalted("Usage exceeded reservation")
    def status(self):
        with self._connect() as db:
            return _read_ledger_status(db)


def _upstream_url(base):
    try:
        parsed = urllib.parse.urlsplit(base)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/v1":
            raise ConfigError("Upstream must be a /v1 base URL without credentials")
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or not parsed.port and parsed.netloc.endswith(":"):
            raise ConfigError("Invalid upstream URL")
        if parsed.scheme == "http":
            try:
                loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                loopback = parsed.hostname == "localhost"
            if not loopback:
                raise ConfigError("Plain HTTP upstream must be loopback")
    except (ValueError, TypeError):
        raise ConfigError("Invalid upstream URL") from None
    return base.rstrip("/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128
    def handle_error(self, request, client_address):
        # Base implementation prints traceback, potentially including user data.
        pass


class BudgetProxy:
    def __init__(self, *, ledger_path, pricing, cap_usd="20", host="127.0.0.1", port=0,
                 openai_upstream="https://api.openai.com/v1", voyage_upstream="https://api.voyageai.com/v1", timeout=120,
                 client_token=None):
        if host != "127.0.0.1":
            raise ConfigError("Listener must bind to 127.0.0.1")
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ConfigError("Positive finite timeout required")
        if client_token is not None and (not isinstance(client_token, str) or not client_token
                or not client_token.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in client_token)):
            raise ConfigError("Invalid local client token")
        self.client_auth_required = client_token is not None
        self.upstreams = {"openai": _upstream_url(openai_upstream), "voyage": _upstream_url(voyage_upstream)}
        if not isinstance(pricing, dict) or not isinstance(pricing.get("models"), dict):
            raise ConfigError("Explicit model pricing required")
        self.pricing = json.loads(json.dumps(pricing))
        self.timeout = timeout
        self.ledger = BudgetLedger(ledger_path, cap_usd)
        # Only proxy startup treats existing reservations as orphaned; ordinary
        # ledger opens and summaries must not halt a live in-flight request.
        if self.ledger.status()["pending_or_ambiguous"]:
            self.ledger.halt()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"
            def setup(self):
                super().setup()
                self.connection.settimeout(15)
            def log_message(self, *args):
                pass
            def send_error(self, code, message=None, explain=None):
                self.reply(code, {"error": {"code": "invalid_request", "message": "Request rejected"}})
            def reply(self, status, body):
                encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Connection", "close")
                self.send_header("x-should-retry", "false")
                self.end_headers()
                self.wfile.write(encoded)
            def do_GET(self):
                if self.path not in {"/status", "/health"}:
                    self.reply(400, {"error": {"code": "unsupported_route", "message": "Unsupported route"}})
                    return
                try:
                    self.reply(200, owner.ledger.status())
                except Exception:
                    self.reply(503, {"error": {"code": "accounting_unavailable", "message": "Accounting unavailable; abort run"}})
            def do_POST(self):
                # Authenticate before route/body validation can mutate accounting.
                # Never forward or record this local credential.
                if client_token is not None:
                    headers = self.headers.get_all("Authorization", [])
                    scheme, _, supplied = headers[0].partition(" ") if len(headers) == 1 else ("", "", "")
                    if (scheme.lower() != "bearer" or not supplied.isascii()
                            or not hmac.compare_digest(supplied, client_token)):
                        self.reply(401, {"error": {"code": "unauthorized", "message": "Local client authentication required"}})
                        return
                try:
                    lane = ROUTES.get(self.path)
                    if lane is None:
                        raise ConfigError("Unsupported route")
                    if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                        raise ConfigError("Unsupported request framing")
                    try:
                        length = int(self.headers["Content-Length"])
                    except (ValueError, TypeError):
                        raise ConfigError("Content-Length required") from None
                    if not 0 < length <= MAX_BODY_BYTES:
                        raise ConfigError("Invalid request size")
                    try:
                        raw = self.rfile.read(length)
                    except OSError:
                        raise ConfigError("Incomplete request") from None
                    if len(raw) != length:
                        raise ConfigError("Incomplete request")
                    try:
                        body = json.loads(raw)
                    except (ValueError, UnicodeError):
                        raise ConfigError("Invalid JSON request") from None
                    body = _canonical_body(lane, body)
                    quote = quote_request(lane, body, owner.pricing)
                    key = os.environ.get("VOYAGE_API_KEY" if lane == "voyage" else "OPENAI_API_KEY")
                    if not key:
                        owner.ledger.halt("request_rejected")
                        self.reply(503, {"error": {"code": "credentials_unavailable", "message": "Provider credentials unavailable"}})
                        return
                    # This durable commit MUST happen before any network activity.
                    attempt = owner.ledger.reserve(lane, quote["model"], quote["reservation_nusd"])
                except ConfigError as exc:
                    # A harness can swallow this 400 and silently fall back.
                    # Persist the rejection so its monitor still stops the run.
                    try:
                        owner.ledger.reject_request(exc.reason, lane)
                    except Exception:
                        self.reply(503, {"error": {"code": "accounting_unavailable", "message": "Accounting unavailable; abort run"}})
                        return
                    self.reply(400, {"error": {"code": "invalid_request", "message": "Unsupported, invalid, or unpriced request", "failure_reason": exc.reason}})
                    return
                except BudgetHalted:
                    self.reply(402, {"error": {"code": "budget_halted", "message": "Paid budget halted; abort benchmark run"}})
                    return
                except Exception:
                    self.reply(503, {"error": {"code": "accounting_unavailable", "message": "Accounting unavailable; abort run"}})
                    return
                suffix = "/chat/completions" if lane == "openai" else "/embeddings"
                provider = "voyage" if lane == "voyage" else "openai"
                canonical = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
                request = urllib.request.Request(owner.upstreams[provider] + suffix, data=canonical,
                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + key}, method="POST")
                try:
                    with owner.opener.open(request, timeout=owner.timeout) as response:
                        if response.status != 200:
                            raise _ResponseValidationError("unexpected_upstream_status")
                        encoded = response.read(MAX_RESPONSE_BYTES + 1)
                        if len(encoded) > MAX_RESPONSE_BYTES:
                            raise _ResponseValidationError("response_too_large")
                        try:
                            result = json.loads(encoded)
                            # Validate the exact response encoding before settling:
                            # nonfinite numbers and lone surrogates cannot be sent.
                            json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
                        except (ValueError, UnicodeError):
                            raise _ResponseValidationError("invalid_upstream_json") from None
                    usage = result.get("usage") if isinstance(result, dict) and "error" not in result else None
                    if not isinstance(usage, dict):
                        raise _ResponseValidationError("missing_usage")
                    if lane == "openai":
                        # Never reconcile standard rates against another paid
                        # tier, or against an unconfirmed processing tier.
                        if result.get("service_tier") != "default":
                            raise _ResponseValidationError("unexpected_service_tier")
                        input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
                        if not _integer(input_tokens) or not _integer(output_tokens) or not _integer(usage.get("total_tokens")) or usage["total_tokens"] != input_tokens + output_tokens:
                            raise _ResponseValidationError("invalid_usage")
                    else:
                        input_tokens, output_tokens = usage.get("total_tokens"), 0
                        if not _integer(input_tokens):
                            raise _ResponseValidationError("invalid_usage")
                        if lane == "openai_embeddings" and (not _integer(usage.get("prompt_tokens")) or usage["prompt_tokens"] != input_tokens):
                            raise _ResponseValidationError("invalid_usage")
                    exceeded = input_tokens > quote["input_tokens"] or output_tokens > quote["output_tokens"]
                    if exceeded:
                        # Halt before arithmetic/SQLite conversion: pathological usage
                        # must not bypass the halt by overflowing numeric storage.
                        owner.ledger.halt("reservation_exceeded")
                    actual = _charge(owner.pricing, quote["model"], input_tokens, output_tokens, lane)
                    owner.ledger.settle(attempt, actual, input_tokens, output_tokens, exceeded)
                except (TimeoutError, socket.timeout):
                    owner.ledger.halt()
                    self.reply(504, {"error": {"code": "upstream_timeout", "message": "Upstream timeout; reservation retained", "failure_reason": "upstream_timeout"}})
                    return
                except Exception as exc:
                    # No raw provider errors, response text, URL credentials or keys.
                    owner.ledger.halt()
                    details = _safe_failure_details(exc)
                    self.reply(502, {"error": {"code": "upstream_or_accounting_error", "message": "Upstream or usage validation failed; reservation retained", **details}})
                    return
                try:
                    self.reply(200, result)
                except OSError:
                    # Usage is settled, but failed delivery can trigger a hidden
                    # harness fallback. Retain the actual charge and stop the run.
                    owner.ledger.halt()
        self.server = _QuietServer((host, port), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = None
    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    def close(self):
        if self.thread:
            self.server.shutdown()
            self.thread.join(timeout=5)
        self.server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True, help="One shared SQLite ledger for ALL paid lanes/processes")
    parser.add_argument("--pricing", type=Path, help="JSON models with input_usd_per_million/output_usd_per_million rates")
    parser.add_argument("--cap-usd", default="20", help="May only lower the total $20 cap, including across restarts; ignored by --summary")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--openai-upstream", default="https://api.openai.com/v1")
    parser.add_argument("--voyage-upstream", default="https://api.voyageai.com/v1")
    parser.add_argument("--client-token-env", help="Require a local Bearer token from this environment variable on POSTs; unset preserves legacy behavior")
    parser.add_argument("--summary", action="store_true", help="Read an existing ledger without creating or changing it; no network")
    args = parser.parse_args()
    try:
        if args.summary:
            print(json.dumps(read_ledger_status(args.ledger), sort_keys=True))
            return 0
        if args.pricing is None:
            raise ConfigError("--pricing required")
        client_token = None
        if args.client_token_env is not None:
            client_token = os.environ.get(args.client_token_env)
            if not client_token:
                raise ConfigError("Local client token environment variable required")
        pricing = json.loads(args.pricing.read_text())
        proxy = BudgetProxy(ledger_path=args.ledger, pricing=pricing, cap_usd=args.cap_usd, host=args.host,
                            port=args.port, timeout=args.timeout, openai_upstream=args.openai_upstream,
                            voyage_upstream=args.voyage_upstream, client_token=client_token)
        print(json.dumps({"openai_base_url": proxy.url + "/openai/v1", "voyage_base_url": proxy.url + "/voyage/v1", "status_url": proxy.url + "/status", "client_auth_required": proxy.client_auth_required}), flush=True)
        try:
            proxy.server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            proxy.server.server_close()
        return 0
    except Exception:
        print("Paid budget proxy configuration/accounting failure; no request sent", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
