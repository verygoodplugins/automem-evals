"""Unit tests for replay_hooks.py — pure-logic functions only.

Integration coverage (HTTP, subprocess, fixture firing) is provided by the
smoke run in data/results/hook-replay/. These tests just guard the
deterministic pieces: variant resolution, matcher filtering by tool_name,
and eval_run_id injection into queue records.

Run: python3 -m unittest runners.test_replay_hooks
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import replay_hooks as rh


class ResolveVariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.variants = self.root / "variants"
        self.variants.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_variant(self, name: str, manifest: dict, files: dict) -> Path:
        vdir = self.variants / name
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "manifest.json").write_text(json.dumps(manifest))
        for relpath, content in files.items():
            target = vdir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        return vdir

    def test_resolve_baseline_returns_own_files(self):
        self._make_variant(
            "baseline",
            {"name": "baseline"},
            {
                "settings.json": '{"hooks": {}}',
                "hooks/capture-build-result.sh": "#!/bin/bash\necho hi",
                "scripts/python-command.sh": "#!/bin/bash\nautomem_run_python(){ python3 \"$@\"; }",
            },
        )
        resolved = rh.resolve_variant("baseline", variants_dir=self.variants)
        self.assertIn("settings.json", resolved)
        self.assertTrue(resolved["settings.json"].name == "settings.json")
        self.assertIn("hooks/capture-build-result.sh", resolved)

    def test_resolve_extends_inherits_baseline_files(self):
        self._make_variant(
            "baseline",
            {"name": "baseline"},
            {
                "settings.json": '{"baseline": true}',
                "hooks/capture-build-result.sh": "#!/bin/bash\necho baseline",
                "scripts/python-command.sh": "#!/bin/bash\necho python-helper",
            },
        )
        self._make_variant(
            "fix-v1",
            {"name": "fix-v1", "extends": "baseline"},
            {"settings.json": '{"baseline": false, "overridden": true}'},
        )
        resolved = rh.resolve_variant("fix-v1", variants_dir=self.variants)
        # Override: settings.json is from fix-v1
        self.assertEqual(
            json.loads(resolved["settings.json"].read_text())["overridden"], True
        )
        # Inherit: hook from baseline
        self.assertIn("baseline", resolved["hooks/capture-build-result.sh"].read_text())

    def test_resolve_unknown_variant_raises(self):
        with self.assertRaises(FileNotFoundError):
            rh.resolve_variant("does-not-exist", variants_dir=self.variants)


class MatchersForToolTests(unittest.TestCase):
    SETTINGS = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash hooks/build.sh"}]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash hooks/test.sh"}]},
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "bash hooks/edit.sh"}]},
            ],
            "Stop": [
                {"matcher": "*", "hooks": [
                    {"type": "command", "command": "bash hooks/session-memory.sh"},
                    {"type": "command", "command": "bash scripts/queue-cleanup.sh"},
                    {"type": "command", "command": "npx -y @verygoodplugins/mcp-automem queue --file foo.jsonl"},
                ]},
            ],
        }
    }

    def test_post_tool_use_bash_matches_two_hooks(self):
        out = rh.matchers_for_tool(self.SETTINGS, "Bash", "PostToolUse")
        commands = [h["command"] for h in out]
        self.assertEqual(len(commands), 2)
        self.assertIn("bash hooks/build.sh", commands)
        self.assertIn("bash hooks/test.sh", commands)

    def test_post_tool_use_read_matches_no_hook(self):
        # Negative control — Read is not in any matcher
        out = rh.matchers_for_tool(self.SETTINGS, "Read", "PostToolUse")
        self.assertEqual(out, [])

    def test_post_tool_use_edit_matches_edit_only(self):
        out = rh.matchers_for_tool(self.SETTINGS, "Edit", "PostToolUse")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["command"], "bash hooks/edit.sh")

    def test_stop_wildcard_returns_only_actual_hook_scripts(self):
        # Per design decision: skip queue-cleanup.sh and npx queue commands;
        # fire only commands that invoke a *.sh under hooks/
        out = rh.matchers_for_tool(self.SETTINGS, None, "Stop")
        commands = [h["command"] for h in out]
        self.assertEqual(commands, ["bash hooks/session-memory.sh"])


class InjectEvalRunIdTests(unittest.TestCase):
    def test_appends_tag_and_metadata(self):
        record = {
            "content": "Build succeeded",
            "tags": ["build", "npm"],
            "type": "Context",
            "metadata": {"build_tool": "npm"},
        }
        rid = "abcd1234"
        out = rh.inject_eval_run_id(record, rid)
        self.assertIn("eval-run-abcd1234", out["tags"])
        self.assertIn("build", out["tags"])
        self.assertEqual(out["metadata"]["eval_run_id"], rid)
        self.assertEqual(out["metadata"]["build_tool"], "npm")

    def test_handles_record_missing_tags_or_metadata(self):
        record = {"content": "minimal"}
        out = rh.inject_eval_run_id(record, "x" * 8)
        self.assertEqual(out["tags"], ["eval-run-xxxxxxxx"])
        self.assertEqual(out["metadata"], {"eval_run_id": "xxxxxxxx"})

    def test_does_not_mutate_input(self):
        record = {"tags": ["a"], "metadata": {"k": "v"}}
        before = json.dumps(record, sort_keys=True)
        rh.inject_eval_run_id(record, "abc12345")
        after = json.dumps(record, sort_keys=True)
        self.assertEqual(before, after)


class ManifestHelpersTests(unittest.TestCase):
    def test_main_rejects_manifest_output_with_cleanup_before_health_check(self):
        with self.assertRaises(SystemExit) as ctx:
            rh.main(
                [
                    "--variant", "baseline",
                    "--cleanup",
                    "--manifest-output", "hook.manifest.json",
                ]
            )
        self.assertIn("cannot be combined", str(ctx.exception))

    def test_resolve_manifest_output_bare_filename_uses_seed_dir(self):
        path = rh.resolve_manifest_output("hook-v2.manifest.json")
        self.assertEqual(path, rh.DEFAULT_MANIFEST_DIR / "hook-v2.manifest.json")

    def test_build_manifest_from_successful_posts(self):
        manifest = rh.build_manifest_from_posts(
            [
                {"memory_id": "m1", "fixture_id": "02_build_success", "status": 200},
                {"memory_id": "m2", "fixture_id": "04_test_fail_heredoc", "status": 200},
                {"memory_id": None, "fixture_id": "ignored", "status": 500},
            ]
        )
        self.assertEqual(
            manifest["memory_to_scenarios"],
            {
                "m1": ["02_build_success"],
                "m2": ["04_test_fail_heredoc"],
            },
        )
        self.assertEqual(
            manifest["scenario_to_memories"],
            {
                "02_build_success": ["m1"],
                "04_test_fail_heredoc": ["m2"],
            },
        )


class SanitizedHookReplayTests(unittest.TestCase):
    def test_sanitized_build_failure_keeps_compiler_diagnostics(self):
        fixture_path = rh.REPO_ROOT / "data" / "hook_fixtures" / "03_build_fail_short.json"
        fixture = json.loads(fixture_path.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp) / "home"
            sandbox.mkdir()
            resolved = rh.resolve_variant("fix-v2-sanitize-content")
            settings = rh.materialize_variant(resolved, sandbox)
            records, failures, fixture_ids = rh.fire_fixtures(
                [fixture],
                settings,
                sandbox,
                git_significant=None,
                git_trivial=None,
            )

        self.assertEqual(failures, [])
        self.assertEqual(fixture_ids, ["03_build_fail_short"])
        self.assertEqual(len(records), 1)
        record = records[0]
        text = record["content"] + "\n" + record["metadata"]["error_details"]
        self.assertIn("src/server.ts", text)
        self.assertIn("TS2304", text)
        self.assertNotIn('"stdout"', text)
        self.assertNotIn("cat <<", text)


class AddFieldsHookReplayTests(unittest.TestCase):
    def test_v3_build_failure_adds_storage_fields(self):
        fixture_path = rh.REPO_ROOT / "data" / "hook_fixtures" / "03_build_fail_short.json"
        fixture = json.loads(fixture_path.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp) / "home"
            sandbox.mkdir()
            resolved = rh.resolve_variant("fix-v3-add-fields")
            settings = rh.materialize_variant(resolved, sandbox)
            records, failures, fixture_ids = rh.fire_fixtures(
                [fixture],
                settings,
                sandbox,
                git_significant=None,
                git_trivial=None,
            )

        self.assertEqual(failures, [])
        self.assertEqual(fixture_ids, ["03_build_fail_short"])
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["confidence"], 0.9)
        self.assertIn("t_valid", record)
        self.assertNotIn("t_invalid", record)
        self.assertEqual(
            record["metadata"]["originSessionId"],
            "fixture-03-build-fail-short",
        )


if __name__ == "__main__":
    unittest.main()
