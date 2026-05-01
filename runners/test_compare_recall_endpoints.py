import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_recall_endpoints as cre


class EndpointGuardTests(unittest.TestCase):
    def test_localhost_allowed(self):
        self.assertTrue(cre.is_local_endpoint("http://localhost:8011"))
        self.assertTrue(cre.is_local_endpoint("http://127.0.0.1:8011"))

    def test_remote_not_local(self):
        self.assertFalse(cre.is_local_endpoint("https://automem.example.com"))


class DiffTests(unittest.TestCase):
    def test_diff_summary_detects_top_changes_and_lost_ids(self):
        baseline = {"count": 3, "returned": 3, "top_ids": ["a", "b", "c"]}
        candidate = {"count": 2, "returned": 2, "top_ids": ["b", "d"]}
        diff = cre.diff_summary(baseline, candidate)
        self.assertEqual(diff["count_delta"], -1)
        self.assertTrue(diff["top_changed"])
        self.assertEqual(diff["lost_top5"], ["a", "c"])
        self.assertEqual(diff["gained_top5"], ["d"])

    def test_preserve_regression_status(self):
        diff = {
            "count_delta": 0,
            "returned_delta": 0,
            "top_changed": True,
            "lost_top5": [],
            "gained_top5": [],
        }
        self.assertEqual(cre.classify_status("preserve", diff), "REGRESSION")

    def test_noise_drop_is_improved(self):
        diff = {
            "count_delta": -5,
            "returned_delta": -5,
            "top_changed": True,
            "lost_top5": ["a"],
            "gained_top5": [],
        }
        self.assertEqual(cre.classify_status("noise", diff), "improved")


if __name__ == "__main__":
    unittest.main()
