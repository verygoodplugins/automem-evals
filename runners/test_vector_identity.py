from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import runners.vector_identity as vi


class VectorIdentityTests(unittest.TestCase):
    def test_compare_vector_maps_accepts_identical_vectors(self) -> None:
        result = vi.compare_vector_maps(
            {"m1": [0.1, 0.2], "m2": [0.3]},
            {"m1": [0.1, 0.2], "m2": [0.3]},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["baseline_points"], 2)
        self.assertEqual(result["candidate_points"], 2)
        self.assertEqual(result["changed_vectors"], 0)

    def test_compare_vector_maps_reports_missing_and_changed_vectors(self) -> None:
        result = vi.compare_vector_maps(
            {"m1": [0.1, 0.2], "m2": [0.3]},
            {"m1": [0.1, 0.25], "m3": [0.4]},
            sample_limit=2,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_in_candidate"], 1)
        self.assertEqual(result["missing_in_baseline"], 1)
        self.assertEqual(result["changed_vectors"], 1)
        self.assertEqual(result["missing_in_candidate_sample"], ["m2"])
        self.assertEqual(result["missing_in_baseline_sample"], ["m3"])
        self.assertEqual(result["changed_vectors_sample"], ["m1"])

    def test_fetch_qdrant_vectors_retries_transient_timeouts(self) -> None:
        calls: list[dict[str, object]] = []
        original = vi._request_json

        def fake_request(url: str, body: dict[str, object], api_key=None, timeout_seconds=60):
            calls.append({"url": url, "body": body, "timeout_seconds": timeout_seconds})
            if len(calls) == 1:
                raise TimeoutError("timed out")
            return {
                "result": {
                    "points": [{"id": "m1", "vector": [0.1, 0.2]}],
                    "next_page_offset": None,
                }
            }

        try:
            vi._request_json = fake_request
            vectors = vi.fetch_qdrant_vectors(
                "http://qdrant",
                "memories",
                batch_size=64,
                request_timeout_seconds=2,
                retries=1,
                retry_delay_seconds=0,
            )
        finally:
            vi._request_json = original

        self.assertEqual(vectors, {"m1": [0.1, 0.2]})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["timeout_seconds"], 2)

    def test_write_failure_summary_records_vector_fetch_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "vector-identity.json"
            summary = vi.write_failure_summary(out, RuntimeError("qdrant unavailable"))

            self.assertFalse(summary["ok"])
            self.assertEqual(summary["error"], "qdrant unavailable")
            self.assertEqual(summary["error_type"], "RuntimeError")
            self.assertEqual(summary, vi.json.loads(out.read_text()))


if __name__ == "__main__":
    unittest.main()
