"""Protocol, isolation and interruption checks without a running stack."""
import unittest
from unittest.mock import patch

from forgeteval_automem import AutoMemAdapter, oracle


class AdapterTests(unittest.TestCase):
    def test_isolation_refuses_remote_shared_and_wrong_graph(self):
        for endpoint, graph in [("https://example.org", "forgeteval-test"),
                                ("http://127.0.0.1:8001", "forgeteval-test"),
                                ("http://127.0.0.1:18031", "memories")]:
            with self.assertRaises(ValueError):
                AutoMemAdapter(endpoint, graph)
        with patch.object(AutoMemAdapter, "request", return_value={"graph": "memories"}):
            with self.assertRaises(ValueError):
                AutoMemAdapter("http://127.0.0.1:18031", "forgeteval-test")

    def test_oracle_preserves_upstream_substring_semantics(self):
        self.assertTrue(oracle(["NewCo", "Berlin"], ["newco", "berlin"], ["OldCo"])["passed"])
        self.assertEqual(oracle(["alice.smith"], [], ["alice"])["leaked"], ["alice"])
        self.assertFalse(oracle([], ["retained"], ["deleted"])["passed"])

    def test_supersede_stages_and_edge_direction(self):
        for stop, methods in [("store", ["POST"]), ("invalidate", ["POST", "PATCH"]),
                              (None, ["POST", "PATCH", "POST"])]:
            with patch.object(AutoMemAdapter, "request", return_value={"graph": "forgeteval-test"}):
                adapter = AutoMemAdapter("http://127.0.0.1:18031", "forgeteval-test")
            with patch.object(adapter, "targets", return_value=[{"id": "old", "content": "old fact"}]), \
                    patch.object(adapter, "request", return_value={"memory_id": "new"}) as request:
                if stop:
                    with self.assertRaises(RuntimeError):
                        adapter.supersede("query", "new fact", fail_after=stop)
                else:
                    adapter.supersede("query", "new fact")
                    self.assertEqual(request.call_args.args[2], {
                        "memory1_id": "old", "memory2_id": "new",
                        "type": "INVALIDATED_BY", "strength": 1})
                self.assertEqual([c.args[0] for c in request.call_args_list], methods)


if __name__ == "__main__":
    unittest.main()
