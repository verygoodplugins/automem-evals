from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "real_data_entity_repair_eval.sh"


class RealDataEntityRepairEvalWrapperTests(unittest.TestCase):
    def test_help_exposes_staged_repair_and_audit_controls(self) -> None:
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--repair-mode MODE", result.stdout)
        self.assertIn("--skip-entity-audit", result.stdout)
        self.assertIn("--audit-timeout-seconds N", result.stdout)
        self.assertIn("--skip-vector-preflight", result.stdout)
        self.assertIn("--skip-vector-identity", result.stdout)
        self.assertIn("--sync-baseline-first", result.stdout)
        self.assertIn("--staged-loop", result.stdout)
        self.assertIn("--print-staged-loop", result.stdout)
        self.assertIn("--full-entity-audit", result.stdout)
        self.assertIn("--baseline-api-port PORT", result.stdout)
        self.assertIn("--candidate-api-port PORT", result.stdout)
        self.assertIn("--baseline-qdrant-url URL", result.stdout)
        self.assertIn("--candidate-qdrant-url URL", result.stdout)
        self.assertIn("--baseline-qdrant-port PORT", result.stdout)
        self.assertIn("--candidate-qdrant-port PORT", result.stdout)
        self.assertIn("--baseline-qdrant-grpc-port PORT", result.stdout)
        self.assertIn("--candidate-qdrant-grpc-port PORT", result.stdout)
        self.assertIn("--baseline-falkordb-port PORT", result.stdout)
        self.assertIn("--candidate-falkordb-port PORT", result.stdout)
        self.assertIn("--baseline-browser-port PORT", result.stdout)
        self.assertIn("--candidate-browser-port PORT", result.stdout)
        self.assertIn("--run-entity-migration", result.stdout)
        self.assertIn("--strict-preserve-review", result.stdout)
        self.assertIn("--graph-update-timeout-seconds N", result.stdout)
        self.assertIn("--qdrant-ready-timeout-seconds N", result.stdout)
        self.assertIn("--cleanup-existing-lab-stacks", result.stdout)

    def test_refuses_non_local_candidate_endpoint(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--write-probes-only",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "https://automem.example.com",
                "--run-id",
                "unit-non-local",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing non-local candidate endpoint", result.stderr)

    def test_write_probes_only_writes_under_ignored_sweep_runs(self) -> None:
        run_id = "unit-real-data-entity-repair"
        run_dir = ROOT / "data" / "sweep_runs" / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)

        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--write-probes-only",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://127.0.0.1:8012",
                "--run-id",
                run_id,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: shutil.rmtree(run_dir, ignore_errors=True))

        self.assertEqual(result.returncode, 0, result.stderr)
        probe_path = run_dir / "real_data_entity_repair_probes.json"
        self.assertTrue(probe_path.exists())
        self.assertTrue(probe_path.is_relative_to(ROOT / "data" / "sweep_runs"))
        data = json.loads(probe_path.read_text())
        self.assertIn("queries", data)
        self.assertGreater(len(data["queries"]), 0)

    def test_staged_loop_plan_orders_modes_and_syncs_baseline(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        stdout = result.stdout
        sync_index = stdout.index("--repair-mode sync-only")
        reject_index = stdout.index("--repair-mode reject-only")
        canon_index = stdout.index("--repair-mode canonicalize-safe")
        migration_index = stdout.index("--run-entity-migration")
        self.assertLess(sync_index, reject_index)
        self.assertLess(reject_index, canon_index)
        self.assertLess(canon_index, migration_index)
        self.assertGreaterEqual(stdout.count("--sync-baseline-first"), 4)

    def test_non_sync_mode_enables_baseline_sync_by_default_in_plan(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged",
                "--repair-mode",
                "reject-only",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--sync-baseline-first", result.stdout)

    def test_strict_preserve_review_flag_is_forwarded_to_comparator(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged-strict",
                "--strict-preserve-review",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.count("--strict-preserve-review"), 4)

    def test_staged_loop_forwards_skip_restore_to_each_stage(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--skip-restore",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged-skip-restore",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.count("--skip-restore"), 4)

    def test_staged_loop_forwards_graph_update_timeout_to_each_stage(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged-graph-timeout",
                "--graph-update-timeout-seconds",
                "12",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.count("--graph-update-timeout-seconds 12"), 4)

    def test_staged_loop_forwards_qdrant_ready_timeout_to_each_stage(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged-qdrant-ready",
                "--qdrant-ready-timeout-seconds",
                "77",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.count("--qdrant-ready-timeout-seconds 77"), 4)

    def test_staged_loop_forwards_cleanup_existing_lab_stacks(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged-cleanup",
                "--cleanup-existing-lab-stacks",
                "--baseline-endpoint",
                "http://localhost:8011",
                "--candidate-endpoint",
                "http://localhost:8012",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.count("--cleanup-existing-lab-stacks"), 4)

    def test_staged_loop_forwards_custom_stack_ports(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--staged-loop",
                "--print-staged-loop",
                "--snapshot",
                "prod-api-test",
                "--run-id",
                "unit-staged-custom-ports",
                "--baseline-api-port",
                "8481",
                "--candidate-api-port",
                "8482",
                "--baseline-qdrant-port",
                "7213",
                "--candidate-qdrant-port",
                "7214",
                "--baseline-qdrant-grpc-port",
                "7215",
                "--candidate-qdrant-grpc-port",
                "7216",
                "--baseline-falkordb-port",
                "7161",
                "--candidate-falkordb-port",
                "7162",
                "--baseline-browser-port",
                "3781",
                "--candidate-browser-port",
                "3782",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        stdout = result.stdout
        self.assertGreaterEqual(stdout.count("--baseline-api-port 8481"), 4)
        self.assertGreaterEqual(stdout.count("--candidate-api-port 8482"), 4)
        self.assertGreaterEqual(stdout.count("--baseline-qdrant-port 7213"), 4)
        self.assertGreaterEqual(stdout.count("--candidate-qdrant-port 7214"), 4)
        self.assertGreaterEqual(stdout.count("--baseline-falkordb-port 7161"), 4)
        self.assertGreaterEqual(stdout.count("--candidate-falkordb-port 7162"), 4)
        self.assertGreaterEqual(stdout.count("--baseline-browser-port 3781"), 4)
        self.assertGreaterEqual(stdout.count("--candidate-browser-port 3782"), 4)
        self.assertIn("--baseline-endpoint http://localhost:8481", stdout)
        self.assertIn("--candidate-endpoint http://localhost:8482", stdout)
        self.assertIn("--baseline-qdrant-url http://localhost:7213", stdout)
        self.assertIn("--candidate-qdrant-url http://localhost:7214", stdout)

    def test_wrapper_restores_db_only_and_starts_local_api_processes(self) -> None:
        script = SCRIPT.read_text()

        self.assertIn("--qdrant-grpc-port \"$BASELINE_QDRANT_GRPC_PORT\"", script)
        self.assertIn("--qdrant-grpc-port \"$CANDIDATE_QDRANT_GRPC_PORT\"", script)
        self.assertGreaterEqual(script.count("--skip-api"), 2)
        self.assertIn("start_local_api baseline", script)
        self.assertIn("start_local_api candidate", script)
        self.assertIn("trap cleanup_local_apis EXIT", script)
        self.assertIn("cleanup_existing_lab_stacks", script)
        self.assertIn("QDRANT_ENSURE_PAYLOAD_INDEXES=false", script)
        self.assertIn("QDRANT_TIMEOUT_SECONDS=\"${QDRANT_TIMEOUT_SECONDS:-60}\"", script)

    def test_entity_migration_output_is_saved_as_artifact_log(self) -> None:
        script = SCRIPT.read_text()

        self.assertIn("entity-migration.log", script)
        self.assertIn("tail -n 40", script)


if __name__ == "__main__":
    unittest.main()
