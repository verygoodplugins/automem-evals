"""Unit tests for hook_metrics.py.

Each test builds a minimal hand-crafted snapshot and asserts a single metric.
The signature regexes come straight from the 2026-04-28 production audit
appendix (Appendix → Findings #1, #2, #3, #4, #5).

Run: python3 -m unittest runners.test_hook_metrics
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hook_metrics as hm


def _snapshot(queue=None, recall=None, fired=None):
    return {
        "variant": "test",
        "eval_run_id": "test1234",
        "fired_fixtures": fired or [],
        "queue_records": queue or [],
        "recall_memories": recall or [],
    }


class AntiPatternSignaturesTests(unittest.TestCase):
    def test_session_summary_signature_counts_only_audit_pattern(self):
        # Audit Appendix finding #1: content matching /^Claude session in /
        queue = [
            {"content": "Claude session in vgp-edd-stats. on branch chore/untrack."},
            {"content": "Claude session in autohub. - Modified 11 files."},
            {"content": "Build succeeded in automem-evals using npm"},
            {"content": "Random other memory mentioning Claude session inside it"},  # not start-anchored
        ]
        m = hm.count_session_summary_content(queue)
        self.assertEqual(m, 2)

    def test_hallucinated_entity_tags_counts_audit_examples(self):
        # Audit Appendix finding #2: entity:.*:(eof|bash|context|decision)
        recall = [
            {"memory": {"tags": ["build", "entity:organizations:eof"]}},
            {"memory": {"tags": ["entity:people:bash", "test"]}},
            {"memory": {"tags": ["entity:projects:context"]}},
            {"memory": {"tags": ["entity:tools:decision"]}},
            {"memory": {"tags": ["entity:people:jack"]}},  # legitimate, not flagged
        ]
        m = hm.count_hallucinated_entity_tags(recall)
        self.assertEqual(m, 4)

    def test_platform_unknown_counts_in_deployment_content(self):
        # Audit finding #3: deploy hook excludes 'unknown' from tags but leaves
        # it in content ('Deployed X to Y on unknown'), which is the actual
        # bleed into the corpus + server-side NER hallucination source.
        queue = [
            {"tags": ["deployment", "production"], "content": "Deployed automem to production on unknown in 12s"},
            {"tags": ["deployment", "railway"], "content": "Deployed automem to production on railway"},
            {"tags": ["build", "npm"], "content": "Build succeeded"},
            {"tags": ["test"], "content": "On unknown framework"},  # not a deployment record
        ]
        m = hm.count_unknown_platform_in_content(queue)
        self.assertEqual(m, 1)


class FieldPresenceTests(unittest.TestCase):
    # Audit Appendix finding #4: hooks never set confidence, originSessionId, t_valid

    def test_pct_with_confidence_counts_only_explicit_field(self):
        queue = [
            {"confidence": 0.9},
            {"content": "no confidence"},
            {"confidence": None},  # explicit None — not present
        ]
        self.assertEqual(hm.pct_with_field(queue, "confidence"), 1 / 3)

    def test_pct_origin_session_id_in_metadata(self):
        queue = [
            {"metadata": {"originSessionId": "sess1"}},
            {"metadata": {"foo": "bar"}},
            {"metadata": {"originSessionId": "sess2"}},
        ]
        self.assertEqual(
            hm.pct_with_metadata_field(queue, "originSessionId"), 2 / 3
        )

    def test_pct_deploys_with_t_valid(self):
        queue = [
            {"tags": ["deployment", "railway"], "t_valid": "2026-04-28T00:00:00Z"},
            {"tags": ["deployment", "vercel"]},  # no t_valid
            {"tags": ["build", "npm"], "t_valid": "2026-04-28T00:00:00Z"},  # not a deploy
        ]
        self.assertEqual(hm.pct_deploys_with_t_valid(queue), 0.5)


class ContentShapeTests(unittest.TestCase):
    def test_length_distribution(self):
        queue = [
            {"content": "x" * 50},
            {"content": "x" * 200},
            {"content": "x" * 600},
            {"content": "x" * 1500},
        ]
        d = hm.content_length_distribution(queue)
        self.assertEqual(d["le_150"], 1)
        self.assertEqual(d["151_300"], 1)
        self.assertEqual(d["301_1000"], 1)
        self.assertEqual(d["gt_1000"], 1)

    def test_near_duplicate_rate(self):
        # First-80-char comparison; pad records to >80 so the prefixes can
        # actually collide.
        prefix = "X" * 90  # > 80 so the prefix collision is unambiguous
        assert len(prefix) >= 80
        queue = [
            {"content": prefix + " variant 1"},
            {"content": prefix + " variant 2 with different suffix"},
            {"content": "Test failures in automem-evals: 1 failed using jest/vitest XYZWVUTSRQPO"},
        ]
        # First two share the same first 80 chars → 1 duplicate / 3 records.
        rate = hm.near_duplicate_rate(queue)
        self.assertAlmostEqual(rate, 1 / 3)


class TagDriftTests(unittest.TestCase):
    # Audit Appendix finding #3: tag-discipline drift

    def test_jest_collision_counts(self):
        queue = [
            {"tags": ["test", "jest-vitest"]},
            {"tags": ["test", "jest/vitest"]},
            {"tags": ["test", "jest-vitest", "automem-evals"]},
            {"tags": ["test", "pytest"]},
        ]
        # Three records use jest variants — both forms occur, that's the bug
        self.assertEqual(hm.count_jest_slug_drift(queue), 3)

    def test_date_derived_tags(self):
        # Pattern: /^20\d\d(-\d\d)?$/
        queue = [
            {"tags": ["preference", "2026-04"]},
            {"tags": ["build", "2026"]},
            {"tags": ["test", "automem-evals"]},
            {"tags": ["preference", "2024-12-31"]},  # full date — not matched
        ]
        self.assertEqual(hm.count_date_tags(queue), 2)


class TypeValidityTests(unittest.TestCase):
    # Audit Appendix finding #5: type-field demotion silently mis-types
    # Public enum: Decision|Pattern|Preference|Style|Habit|Insight|Context

    def test_invalid_type_count(self):
        queue = [
            {"type": "Memory"},
            {"type": "Context"},
            {"type": "Insight"},
            {"type": "memory"},  # case-sensitive
            {"type": None},
        ]
        result = hm.type_validity(queue)
        self.assertEqual(result["invalid_count"], 3)  # Memory, memory, None
        self.assertEqual(result["valid_count"], 2)


class TopLevelComputeTests(unittest.TestCase):
    def test_compute_metrics_aggregates_all(self):
        snap = _snapshot(
            queue=[
                {"content": "Claude session in foo. - Modified 5 files.",
                 "tags": ["session-milestone"], "type": "Memory"},
                {"content": "Build succeeded in automem-evals using npm",
                 "tags": ["build", "npm", "automem-evals"], "type": "Context",
                 "confidence": 0.7},
                {"content": "Deployed to production on unknown",
                 "tags": ["deployment", "unknown"], "type": "Context"},
            ],
            recall=[{"memory": {"tags": ["entity:organizations:eof"]}}],
            fired=["fx1", "fx2", "fx3"],
        )
        m = hm.compute_metrics(snap)
        self.assertEqual(m["queue_record_count"], 3)
        self.assertEqual(m["fixture_count"], 3)
        self.assertEqual(m["anti_patterns"]["session_summary_content"], 1)
        self.assertEqual(m["anti_patterns"]["hallucinated_entity_tags"], 1)
        self.assertEqual(m["anti_patterns"]["platform_unknown"], 1)
        self.assertEqual(m["type_validity"]["invalid_count"], 1)


class FailClosedPropagationTests(unittest.TestCase):
    """Codex adversarial review caught: a broken variant can fake an
    improvement by silently dropping records when hooks crash. Metrics
    must propagate run_failed so the diff renderer can refuse to
    issue a verdict.
    """

    def test_run_failed_explicit_in_snapshot(self):
        snap = _snapshot(queue=[])
        snap["run_failed"] = True
        m = hm.compute_metrics(snap)
        self.assertTrue(m["run_failed"])

    def test_run_failed_inferred_from_hook_failures(self):
        snap = _snapshot(queue=[])
        snap["hook_failures"] = [{"fixture_id": "fx1", "returncode": 1}]
        m = hm.compute_metrics(snap)
        self.assertTrue(m["run_failed"])
        self.assertEqual(m["hook_failure_count"], 1)

    def test_run_failed_inferred_from_post_failures(self):
        snap = _snapshot(queue=[])
        snap["post_failures"] = [{"status": 500, "response_body_excerpt": "{}"}]
        m = hm.compute_metrics(snap)
        self.assertTrue(m["run_failed"])
        self.assertEqual(m["post_failure_count"], 1)

    def test_clean_run_has_run_failed_false(self):
        snap = _snapshot(queue=[{"content": "ok", "tags": ["build"], "type": "Context"}])
        m = hm.compute_metrics(snap)
        self.assertFalse(m["run_failed"])
        self.assertEqual(m["hook_failure_count"], 0)
        self.assertEqual(m["post_failure_count"], 0)


if __name__ == "__main__":
    unittest.main()
