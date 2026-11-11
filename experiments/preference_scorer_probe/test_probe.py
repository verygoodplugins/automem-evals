"""Offline tests: no network, model inference or real data."""

import json
import tempfile
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import BaseHandler, build_opener
from urllib.response import addinfourl

import run


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.data = run.load_fixture()
        self.row = self.data["cases"][0]

    def test_fixture_has_disjoint_balanced_synthetic_splits(self):
        dev = [row for row in self.data["cases"] if row["split"] == "development"]
        heldout = [row for row in self.data["cases"] if row["split"] == "heldout"]
        self.assertEqual((len(dev), len(heldout)), (8, 8))
        self.assertEqual({row["kind"] for row in dev}, {row["kind"] for row in heldout})
        self.assertFalse(
            {row["question"] for row in dev} & {row["question"] for row in heldout}
        )
        for group in (dev, heldout):
            self.assertEqual(sum(row["expected"] == "pass" for row in group), 4)
            self.assertEqual(sum(row["expected"] == "fail" for row in group), 4)
        self.assertEqual(run.canonical_sha(heldout), run.HELDOUT_SHA256)

    def test_modified_heldout_is_rejected(self):
        self.data["cases"][-1]["answer"] = "changed"
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "fixture.json"
            file.write_text(json.dumps(self.data))
            with self.assertRaisesRegex(ValueError, "Held-out fixture changed"):
                run.load_fixture(file)

    def test_rejects_nonloopback_credentials_and_paths(self):
        for url in (
            "https://127.0.0.1:11434",
            "http://example.com",
            "http://localhost:11434",
            "http://127.0.0.1:11434/path",
            "http://user@127.0.0.1",
            "http://127.0.0.1?x=1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                run.loopback_url(url)
        self.assertEqual(
            run.loopback_url("http://127.0.0.1:11434/"), "http://127.0.0.1:11434"
        )
        self.assertEqual(run.loopback_url("http://[::1]:11434"), "http://[::1]:11434")

    def test_loopback_redirects_never_reach_a_remote_host(self):
        for path, payload in (("/api/tags", None), ("/api/chat", {"messages": []})):
            for code in (301, 302, 303, 307, 308):
                seen = []

                class FakeHTTP(BaseHandler):
                    handler_order = 400

                    def http_open(self, request):
                        seen.append(request.full_url)
                        headers = Message()
                        if request.host == "127.0.0.1:11434":
                            headers["Location"] = "http://198.51.100.10/receiver"
                            response = addinfourl(
                                BytesIO(b""), headers, request.full_url, code
                            )
                            response.msg = "redirect"
                            return response
                        response = addinfourl(
                            BytesIO(b'{"redirected":true}'),
                            headers,
                            request.full_url,
                            200,
                        )
                        response.msg = "OK"
                        return response

                def fake_opener(*handlers):
                    return build_opener(*handlers, FakeHTTP())

                with self.subTest(path=path, code=code), patch.object(
                    run, "build_opener", side_effect=fake_opener
                ):
                    with self.assertRaisesRegex(URLError, "Redirects are disabled"):
                        run.transport_json("http://127.0.0.1:11434", path, payload)
                    self.assertEqual(seen, [f"http://127.0.0.1:11434{path}"])

    def test_transport_rejects_nonloopback_before_opening(self):
        with patch.object(run, "build_opener") as opener:
            with self.assertRaises(ValueError):
                run.transport_json("http://example.com", "/api/tags")
        opener.assert_not_called()

    def test_model_payload_never_exposes_labels_or_split(self):
        payload = run.payload_for(self.row)
        packet = json.loads(payload["messages"][1]["content"])
        self.assertEqual(set(packet), {"question", "criteria", "optional", "answer"})
        self.assertNotIn("expected", packet)
        self.assertNotIn("split", packet)
        self.assertFalse(payload["stream"])

    def test_evidence_schema_and_overall_consistency(self):
        good = {
            "verdict": "pass",
            "judgments": [
                {"criterion_index": 0, "status": "met", "quote": "tea"},
                {"criterion_index": 1, "status": "met", "quote": "chilled"},
            ],
        }
        self.assertEqual(run.validate_result(good, self.row), ("pass", []))
        cases = [
            {"verdict": "pass", "judgments": [good["judgments"][0]]},
            {
                "verdict": "pass",
                "judgments": [good["judgments"][0], good["judgments"][0]],
            },
            {
                "verdict": "pass",
                "judgments": [
                    good["judgments"][0],
                    {"criterion_index": 1, "status": "met", "quote": "cold"},
                ],
            },
            {
                "verdict": "pass",
                "judgments": [
                    good["judgments"][0],
                    {"criterion_index": 1, "status": "unmet", "quote": None},
                ],
            },
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertIsNone(run.validate_result(case, self.row)[0])
        fail = {
            "verdict": "fail",
            "judgments": [
                {"criterion_index": 0, "status": "met", "quote": "tea"},
                {"criterion_index": 1, "status": "unmet", "quote": None},
            ],
        }
        self.assertEqual(run.validate_result(fail, self.row), ("fail", []))

    def test_full_fake_run_freezes_config_before_heldout(self):
        by_answer = {row["answer"]: row for row in self.data["cases"]}
        calls = []

        def fake_transport(_origin, path, payload=None, **_kwargs):
            if path == "/api/tags":
                return {
                    "models": [{"name": run.MODEL, "digest": "a" * 64, "size": 100}]
                }
            packet = json.loads(payload["messages"][1]["content"])
            calls.append(packet)
            row = by_answer[packet["answer"]]
            state = "met" if row["expected"] == "pass" else "unmet"
            verdict = row["expected"]
            result = {
                "verdict": verdict,
                "judgments": [
                    {
                        "criterion_index": i,
                        "status": state,
                        "quote": row["answer"] if state == "met" else None,
                    }
                    for i in range(len(row["criteria"]))
                ],
            }
            return {"message": {"content": json.dumps(result)}}

        with tempfile.TemporaryDirectory() as directory, patch.object(
            run, "transport_json", fake_transport
        ):
            root = Path(directory)
            dev = run.run("development", "http://127.0.0.1:11434", root / "dev")
            self.assertEqual((dev["cases"], dev["valid"], dev["correct"]), (8, 8, 8))
            held = run.run(
                "heldout",
                "http://127.0.0.1:11434",
                root / "held",
                root / "dev" / "frozen.json",
            )
            self.assertEqual((held["cases"], held["valid"], held["correct"]), (8, 8, 8))
            self.assertEqual(len(calls), 16)
            self.assertTrue(
                all(
                    set(row) == {"question", "criteria", "optional", "answer"}
                    for row in calls
                )
            )
            bad = json.loads((root / "dev" / "frozen.json").read_text())
            bad["model_digest"] = "b" * 64
            (root / "bad.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "exact development"):
                run.run(
                    "heldout",
                    "http://127.0.0.1:11434",
                    root / "other",
                    root / "bad.json",
                )
            with self.assertRaises(FileExistsError):
                run.run("development", "http://127.0.0.1:11434", root / "dev")

    def test_invalid_development_does_not_enable_heldout(self):
        def fake_transport(_origin, path, payload=None, **_kwargs):
            if path == "/api/tags":
                return {
                    "models": [{"name": run.MODEL, "digest": "a" * 64, "size": 100}]
                }
            return {"message": {"content": "not json"}}

        with tempfile.TemporaryDirectory() as directory, patch.object(
            run, "transport_json", fake_transport
        ):
            out = Path(directory) / "dev"
            result = run.run("development", "http://127.0.0.1:11434", out)
            self.assertEqual(result["invalid"], 8)
            self.assertFalse((out / "frozen.json").exists())

    def test_no_output_in_repo_or_remote_model(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            run.run(
                "development", "http://127.0.0.1:11434", run.REPO / "ignored-output"
            )
        with self.assertRaises(ValueError):
            run.model_digest({"models": [{"name": run.MODEL, "digest": "abc"}]})
        with self.assertRaises(ValueError):
            run.model_digest(
                {
                    "models": [
                        {
                            "name": run.MODEL,
                            "digest": "a" * 64,
                            "size": 100,
                            "remote_host": "elsewhere",
                        }
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
