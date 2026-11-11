import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def load_scenario():
    fake_embed = types.ModuleType("fastembed")
    fake_embed.TextEmbedding = lambda **_kwargs: object()
    fake_graph = types.ModuleType("falkordb")
    fake_graph.FalkorDB = object
    spec = importlib.util.spec_from_file_location(
        "graph_scenario", Path(__file__).with_name("scenario.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"fastembed": fake_embed, "falkordb": fake_graph}):
        spec.loader.exec_module(module)
    return module


class GraphValueTest(unittest.TestCase):
    def test_fixture_has_scoped_negative_and_history_controls(self):
        module = load_scenario()
        docs, queries, edges = module.fixture()
        self.assertEqual(len({key for key, _, _ in docs}), len(docs))
        self.assertTrue(any(not query["expected"] for query in queries))
        self.assertTrue(any(query.get("current") is False for query in queries))
        self.assertIn(("scope-seed", "foreign", "RELATES_TO"), edges)
        self.assertIn(("old", "new", "INVALIDATED_BY"), edges)

    def test_inline_evidence_and_leaks_are_counted_within_budget(self):
        module = load_scenario()
        row = {
            "id": "s",
            "memory": {"id": "s", "content": "seed text"},
            "relations": [
                {"memory": {"id": "e", "content": "linked fact"}},
                {"memory": {"id": "f", "content": "foreign text"}},
                {"memory": {"id": "o", "content": "old text"}},
            ],
        }
        query = {"scope": "alpha", "expected": ["seed", "evidence"], "current": True}
        inverse = {"s": "seed", "e": "evidence", "f": "foreign", "o": "old"}
        scopes = {
            "seed": "alpha",
            "evidence": "alpha",
            "foreign": "beta",
            "old": "alpha",
        }
        result = module.measure([row], query, inverse, scopes, budget=6)
        self.assertFalse(result["top5_all"])
        self.assertTrue(result["context_all"])
        self.assertEqual(result["context_words"], 6)
        self.assertEqual(result["foreign_inline"], 1)
        self.assertEqual(result["stale_inline"], 0)
        result = module.measure([row], query, inverse, scopes, budget=8)
        self.assertEqual(result["stale_inline"], 1)

    def test_negative_is_not_scored_as_positive_support(self):
        module = load_scenario()
        row = {"id": "s", "memory": {"id": "s", "content": "unrelated"}}
        result = module.measure(
            [row], {"scope": "alpha", "expected": []}, {"s": "seed"}, {"seed": "alpha"}
        )
        self.assertEqual(result["off_label"], 1)
        self.assertFalse(result["context_all"])
        self.assertEqual(result["result_count"], 1)


if __name__ == "__main__":
    unittest.main()
