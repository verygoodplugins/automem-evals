"""Unit tests for the no-network MERIT AutoMem adapter contract."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "merit"))
from automem_adapter import AutoMemMemory, extract_merit_facts, is_local_endpoint
import run_merit


class FakeAutoMem:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.next_id = 1
        self.recall_results: list[dict] = []

    def __call__(self, method: str, path: str, body: dict | None) -> dict:
        self.calls.append((method, path, body))
        if method == "POST":
            response = {"memory_id": f"memory-{self.next_id}", "usage": {"prompt_tokens": 3}}
            self.next_id += 1
            return response
        return {"results": self.recall_results, "usage": {"completion_tokens": 2}}


class MeritAutoMemAdapterTests(unittest.TestCase):
    def test_fact_extraction_uses_official_structured_fact_keys(self) -> None:
        facts = extract_merit_facts('agreed amount of 4200 cents for order ORD-111111')
        self.assertEqual(facts[0].key, "ORD-111111.agreed_refund_cents")
        self.assertEqual(facts[0].value, "4200")

    def test_plain_variant_never_sends_supersession(self) -> None:
        fake = FakeAutoMem()
        memory = AutoMemMemory(variant="plain", run_tag="merit-test", request=fake)
        memory.write("e1", 'agreed amount of 4200 cents for order ORD-111111')
        memory.write("e2", 'agreed amount of 5000 cents for order ORD-111111')
        payloads = [body for method, _, body in fake.calls if method == "POST"]
        self.assertNotIn("supersedes_memory_id", payloads[1])
        self.assertEqual(payloads[0]["tags"][0], "merit-test")

    def test_supersede_variant_links_old_to_new_on_changed_fact(self) -> None:
        fake = FakeAutoMem()
        memory = AutoMemMemory(variant="supersede-on-write", run_tag="merit-test", request=fake)
        memory.write("e1", 'agreed amount of 4200 cents for order ORD-111111')
        memory.write("e2", 'agreed amount of 5000 cents for order ORD-111111')
        payload = [body for method, _, body in fake.calls if method == "POST"][1]
        self.assertEqual(payload["supersedes_memory_id"], "memory-1")
        self.assertEqual(payload["supersede_relation"], "INVALIDATED_BY")

    def test_recall_is_tag_isolated_current_only_and_bounded(self) -> None:
        fake = FakeAutoMem()
        fake.recall_results = [
            {"memory": {"content": "latest value"}},
            {"memory": {"content": "x" * 100}},
        ]
        memory = AutoMemMemory(run_tag="merit-isolated", request=fake)
        self.assertEqual(memory.read("current order", budget_chars=20), "latest value")
        _, path, _ = fake.calls[-1]
        self.assertIn("tags=merit-isolated", path)
        self.assertIn("current_only=true", path)

    def test_metering_discloses_estimates_and_measured_usage(self) -> None:
        fake = FakeAutoMem()
        memory = AutoMemMemory(run_tag="merit-meter", request=fake)
        memory.write("e1", 'agreed amount of 4200 cents for order ORD-111111')
        memory.read("order")
        record = memory.metering_record()
        self.assertGreater(record["http"]["estimated_input_tokens"], 0)
        self.assertEqual(record["server_usage_only"]["prompt_tokens"], 3)
        self.assertEqual(record["server_usage_only"]["completion_tokens"], 2)
        self.assertIsNone(record["http"]["measured_cost_usd"])

    def test_rejects_nonlocal_endpoint_without_explicit_opt_in(self) -> None:
        self.assertTrue(is_local_endpoint("http://localhost:8001"))
        self.assertFalse(is_local_endpoint("https://automem.example"))
        with self.assertRaisesRegex(ValueError, "non-local"):
            AutoMemMemory(endpoint="https://automem.example")

    def test_matured_status_is_explicitly_blocked_not_relabelled_cold(self) -> None:
        report = run_merit._maturation_report("both")
        self.assertEqual(report["cold"]["status"], "ready")
        self.assertEqual(report["matured"]["status"], "blocked")
        self.assertIn("reference_time", report["matured"]["reason"])


if __name__ == "__main__":
    unittest.main()
