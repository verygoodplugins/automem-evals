import argparse
import contextlib
import importlib.util
import io
import json
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))


def load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


# The earlier PR #289 benchmark rebased by hand on this date: 210 days for v1,
# 209 for v2.
PR289_RUN = utc(2026, 11, 13, 17, 29)


class ShiftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_rebase")

    def test_shift_keeps_z_suffix(self):
        self.assertEqual(
            self.mod.shift_iso("2026-04-16T12:00:00Z", 210),
            "2026-11-12T12:00:00Z",
        )

    def test_shift_keeps_offset_suffix(self):
        self.assertEqual(
            self.mod.shift_iso("2026-04-16T12:00:00+00:00", 210),
            "2026-11-12T12:00:00+00:00",
        )

    def test_shift_entry_moves_all_time_fields(self):
        entry = {
            "content": "x",
            "timestamp": "2026-04-15T12:00:00+00:00",
            "t_valid": "2026-04-15T12:00:00+00:00",
            "t_invalid": "2026-05-01T00:00:00Z",
        }
        shifted = self.mod.shift_entry(entry, 10)
        self.assertEqual(shifted["timestamp"], "2026-04-25T12:00:00+00:00")
        self.assertEqual(shifted["t_valid"], "2026-04-25T12:00:00+00:00")
        self.assertEqual(shifted["t_invalid"], "2026-05-11T00:00:00Z")
        self.assertEqual(shifted["content"], "x")

    def test_shift_entry_leaves_missing_and_null_fields_and_original(self):
        embedding = [0.1, 0.2]
        entry = {
            "timestamp": "2026-04-15T12:00:00Z",
            "t_invalid": None,
            "embedding": embedding,
        }
        shifted = self.mod.shift_entry(entry, 3)
        self.assertIsNone(shifted["t_invalid"])
        self.assertNotIn("t_valid", shifted)
        self.assertIs(shifted["embedding"], embedding)
        self.assertEqual(entry["timestamp"], "2026-04-15T12:00:00Z")

    def test_zero_shift_is_identity(self):
        entry = {"timestamp": "2026-04-15T12:00:00Z"}
        self.assertIs(self.mod.shift_entry(entry, 0), entry)


class RebaseDaysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_rebase")

    def test_matches_pr289_manual_shift(self):
        anchors = self.mod.KNOWN_ANCHORS
        self.assertEqual(self.mod.rebase_days(anchors["corpus_v1"], PR289_RUN), 210)
        self.assertEqual(self.mod.rebase_days(anchors["corpus_v2"], PR289_RUN), 209)

    def test_morning_run_never_lands_anchor_in_future(self):
        anchor = self.mod.KNOWN_ANCHORS["corpus_v1"]  # 12:00 UTC
        morning = utc(2026, 11, 13, 8, 0)
        days = self.mod.rebase_days(anchor, morning)
        self.assertEqual(days, 209)
        self.assertLessEqual(anchor + timedelta(days=days), morning)

    def test_exactly_on_the_hour_lands_today(self):
        anchor = self.mod.KNOWN_ANCHORS["corpus_v1"]
        self.assertEqual(self.mod.rebase_days(anchor, utc(2026, 11, 13, 12, 0)), 210)

    def test_future_anchor_shifts_backwards(self):
        self.assertEqual(
            self.mod.rebase_days(utc(2026, 11, 20, 0, 0), utc(2026, 11, 13, 0, 0)),
            -7,
        )


class ResolveAnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_rebase")

    def test_known_corpus_uses_generator_now(self):
        entries = [{"timestamp": "2026-04-16T12:00:00+00:00"}]
        anchor, _ = self.mod.resolve_anchor("corpus_v1.embedded.jsonl", entries)
        self.assertEqual(anchor, utc(2026, 4, 17, 12, 0))
        anchor, _ = self.mod.resolve_anchor("corpus_v2.jsonl", entries)
        self.assertEqual(anchor, utc(2026, 4, 18, 12, 0))

    def test_corpus_key_accepts_paths(self):
        self.assertEqual(
            self.mod.corpus_key(Path("/x/data/seed_memories/corpus_v2.embedded.jsonl")),
            "corpus_v2",
        )

    def test_unknown_corpus_falls_back_to_newest_timestamp(self):
        entries = [
            {"timestamp": "2026-01-01T00:00:00Z"},
            {"timestamp": "2026-02-03T04:00:00Z"},
            {"content": "no timestamp"},
        ]
        anchor, source = self.mod.resolve_anchor("custom.jsonl", entries)
        self.assertEqual(anchor, utc(2026, 2, 3, 4, 0))
        self.assertIn("newest", source)

    def test_already_rebased_snapshot_uses_data_not_generator_now(self):
        # A snapshot re-captured after a rebased seed still carries the
        # corpus_v1 name; shifting it from the April anchor would put every
        # record months in the future.
        entries = [{"timestamp": "2026-11-12T12:00:00+00:00"}]
        anchor, _ = self.mod.resolve_anchor("corpus_v1.embedded.jsonl", entries)
        self.assertEqual(anchor, utc(2026, 11, 12, 12, 0))
        self.assertEqual(self.mod.rebase_days(anchor, PR289_RUN), 1)

    def test_override_date_means_midnight_utc(self):
        anchor, source = self.mod.resolve_anchor("corpus_v1.jsonl", [], "2026-04-10")
        self.assertEqual(anchor, utc(2026, 4, 10, 0, 0))
        self.assertEqual(source, "--rebase-anchor")

    def test_override_datetime(self):
        anchor, _ = self.mod.resolve_anchor("x.jsonl", [], "2026-04-10T06:30:00Z")
        self.assertEqual(anchor, utc(2026, 4, 10, 6, 30))

    def test_no_timestamps_means_no_anchor(self):
        anchor, _ = self.mod.resolve_anchor("custom.jsonl", [{"content": "x"}])
        self.assertIsNone(anchor)


class KnownAnchorsMatchGeneratorsTests(unittest.TestCase):
    """Read NOW from generator source; importing a generator rewrites its corpus."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_rebase")

    def generator_now(self, filename: str) -> datetime:
        source = (SCRIPTS / filename).read_text()
        match = re.search(
            r"^NOW = datetime\((\d+), (\d+), (\d+), (\d+), (\d+), (\d+), tzinfo=timezone\.utc\)",
            source,
            re.MULTILINE,
        )
        self.assertIsNotNone(match, f"NOW not found in {filename}")
        return utc(*(int(g) for g in match.groups()))

    def test_v1_anchor(self):
        self.assertEqual(
            self.mod.KNOWN_ANCHORS["corpus_v1"],
            self.generator_now("generate_corpus.py"),
        )

    def test_v2_anchor(self):
        self.assertEqual(
            self.mod.KNOWN_ANCHORS["corpus_v2"],
            self.generator_now("generate_corpus_v2.py"),
        )


class PlanRebaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_rebase")

    def parse(self, argv):
        parser = argparse.ArgumentParser()
        self.mod.add_rebase_args(parser)
        return parser.parse_args(argv)

    def plan(self, argv, name="corpus_v1.jsonl", entries=None, now=PR289_RUN):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.mod.plan_rebase(self.parse(argv), name, entries or [], now)

    def test_rebase_is_on_by_default(self):
        self.assertEqual(self.plan([]), 210)

    def test_no_rebase_opt_out(self):
        self.assertEqual(self.plan(["--no-rebase"]), 0)

    def test_anchor_override(self):
        self.assertEqual(self.plan(["--rebase-anchor", "2026-11-03"]), 10)

    def test_flags_are_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.parse(["--no-rebase", "--rebase-anchor", "2026-04-17"])


class CommittedV1SnapshotTests(unittest.TestCase):
    """End to end over the committed v1 snapshot (v2 is gitignored)."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_rebase")
        cls.path = SCRIPTS.parent / "data" / "seed_memories" / "corpus_v1.embedded.jsonl"
        cls.entries = [
            json.loads(line) for line in cls.path.read_text().splitlines() if line.strip()
        ]

    def test_rebased_v1_lands_inside_ninety_day_window_and_not_in_future(self):
        anchor, _ = self.mod.resolve_anchor(self.path, self.entries)
        for now in (PR289_RUN, utc(2026, 11, 13, 8, 0), utc(2030, 1, 1, 0, 0)):
            days = self.mod.rebase_days(anchor, now)
            shifted = [self.mod.shift_entry(e, days) for e in self.entries]
            stamps = [self.mod.parse_iso(e["timestamp"]) for e in shifted]
            valid = [self.mod.parse_iso(e["t_valid"]) for e in shifted if e.get("t_valid")]
            self.assertLessEqual(max(stamps + valid), now)
            self.assertGreater(max(stamps), now - timedelta(days=2))
            recent = [s for s in stamps if s >= now - timedelta(days=90)]
            self.assertGreater(len(recent), len(stamps) // 2)

    def test_relative_ages_are_preserved(self):
        shifted = [self.mod.shift_entry(e, 210) for e in self.entries]
        for before, after in zip(self.entries, shifted):
            delta = self.mod.parse_iso(after["timestamp"]) - self.mod.parse_iso(
                before["timestamp"]
            )
            self.assertEqual(delta, timedelta(days=210))
            self.assertIs(after["embedding"], before["embedding"])


if __name__ == "__main__":
    unittest.main()
