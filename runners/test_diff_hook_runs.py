"""Golden-output test for diff_hook_runs.py.

Builds a hand-crafted two-metrics-pair and asserts that the rendered
markdown table contains the expected per-metric rows, deltas, and the
'verdict' summary lines.

Run: python3 -m unittest runners.test_diff_hook_runs
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diff_hook_runs as dh


def _metrics(variant, eval_run_id, q_count, recall_count, ap, fp, cs, td, tv):
    return {
        "variant": variant,
        "eval_run_id": eval_run_id,
        "fixture_count": 9,
        "queue_record_count": q_count,
        "recall_count": recall_count,
        "anti_patterns": ap,
        "field_presence": fp,
        "content_shape": cs,
        "tag_drift": td,
        "type_validity": tv,
    }


class DiffRenderTests(unittest.TestCase):
    def setUp(self):
        self.a = _metrics(
            "baseline", "aaaaaaaaaaaa", 7, 7,
            ap={"session_summary_content": 1, "hallucinated_entity_tags": 0, "platform_unknown": 1},
            fp={"with_confidence_pct": 0.0, "with_origin_session_id_pct": 0.0, "deploys_with_t_valid_pct": 0.0},
            cs={"length_distribution": {"le_150": 3, "151_300": 4, "301_1000": 0, "gt_1000": 0}, "near_duplicate_rate": 0.0},
            td={"jest_collisions": 1, "date_derived_tags": 0},
            tv={"valid_count": 5, "invalid_count": 2, "invalid_examples": ["None", "None"]},
        )
        self.b = _metrics(
            "fix-v1-no-session", "bbbbbbbbbbbb", 5, 5,
            ap={"session_summary_content": 0, "hallucinated_entity_tags": 0, "platform_unknown": 1},
            fp={"with_confidence_pct": 0.0, "with_origin_session_id_pct": 0.0, "deploys_with_t_valid_pct": 0.0},
            cs={"length_distribution": {"le_150": 2, "151_300": 3, "301_1000": 0, "gt_1000": 0}, "near_duplicate_rate": 0.0},
            td={"jest_collisions": 1, "date_derived_tags": 0},
            tv={"valid_count": 5, "invalid_count": 0, "invalid_examples": []},
        )

    def test_header_includes_both_variants(self):
        out = dh.render_markdown(self.a, self.b)
        self.assertIn("baseline", out)
        self.assertIn("fix-v1-no-session", out)
        self.assertIn("aaaaaaaaaaaa", out)
        self.assertIn("bbbbbbbbbbbb", out)

    def test_anti_patterns_table_includes_session_summary_delta(self):
        out = dh.render_markdown(self.a, self.b)
        # Row should show 1 → 0 with a -1 delta
        self.assertIn("session_summary_content", out)
        # Find the line containing session_summary_content
        line = next(l for l in out.splitlines() if "session_summary_content" in l)
        self.assertIn("1", line)
        self.assertIn("0", line)
        self.assertIn("-1", line)

    def test_anti_patterns_unchanged_metric_shows_zero_delta(self):
        out = dh.render_markdown(self.a, self.b)
        # platform_unknown is 1 in both → delta 0
        line = next(l for l in out.splitlines() if "platform_unknown" in l)
        # delta column should not show a sign for 0
        self.assertNotIn("-1", line)
        self.assertNotIn("+1", line)

    def test_type_validity_invalid_drops_to_zero(self):
        out = dh.render_markdown(self.a, self.b)
        line = next(l for l in out.splitlines() if "invalid_count" in l)
        self.assertIn("2", line)
        self.assertIn("0", line)
        self.assertIn("-2", line)

    def test_verdict_section_exists(self):
        out = dh.render_markdown(self.a, self.b)
        self.assertIn("## Verdict", out)
        # Verdict should call out the eliminated session summary
        self.assertIn("session_summary_content", out.lower().split("verdict")[1])


if __name__ == "__main__":
    unittest.main()
