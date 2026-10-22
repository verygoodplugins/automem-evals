"""Boundary checks for the MemDerive HTTP seam; no external services needed."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "memderive_pilot", Path(__file__).parent / "memderive/pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class MemDeriveTests(unittest.TestCase):
    def test_endpoint_and_redirect_boundaries(self):
        for value in ["https://localhost", "http://example.com", "http://localhost/x",
                      "http://user:pass@localhost", "http://localhost?token=x"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                pilot.local_endpoint(value)
        self.assertEqual(pilot.local_endpoint("http://[::1]:8001/"),
                         "http://[::1]:8001")
        with self.assertRaisesRegex(RuntimeError, "redirect refused"):
            pilot.NoRedirect().redirect_request(
                None, None, 302, "", {}, "http://elsewhere")

    def test_public_ingest_manifest_cutoff_and_cleanup(self):
        event = {"event_id": "e1", "text": "Public fact", "source": "Wiki",
                 "time": "2026-01-01 09:00", "gold_answer": "must not be ingested"}
        with tempfile.TemporaryDirectory() as directory:
            bank = pilot.AutoMem("http://localhost:8001", "test", Path(directory))
            with patch.object(bank, "call", return_value={"memory_id": "m1"}) as call:
                bank.store([event])
                body = call.call_args.args[1]
                self.assertNotIn("gold_answer", str(body))
                self.assertEqual(body["timestamp"], "2026-01-01T09:00:00+00:00")
                self.assertEqual(body["tags"], [bank.tag])
            with patch.object(bank, "call", return_value={"results": [{"id": "m1"}]}):
                self.assertEqual(bank.recall("question", "2026-01-02", 1), [event])
                with self.assertRaisesRegex(RuntimeError, "future event"):
                    bank.recall("question", "2025-12-31", 1)
            with patch.object(bank, "call",
                              return_value={"results": [{"id": "foreign"}]}):
                with self.assertRaisesRegex(RuntimeError, "unmanifested"):
                    bank.recall("question", "2026-01-02", 1)
            with patch.object(bank, "call", return_value={}) as call:
                bank.cleanup()
                call.assert_called_once_with("/memory/m1", method="DELETE")
            self.assertTrue((Path(directory) / "cleanup.json").exists())

    def test_timestamp_precision_and_timezone(self):
        self.assertEqual(pilot.instant("2026-01-01 09:00"),
                         pilot.instant("2026-01-01T10:00:00+01:00"))
