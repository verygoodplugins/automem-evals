import gzip
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def write_synthetic_snapshot(run_dir: Path) -> Path:
    snapshot = run_dir / "snapshot"
    (snapshot / "falkordb").mkdir(parents=True)
    (snapshot / "qdrant").mkdir(parents=True)
    props = {
        "id": "m1",
        "content": "Local evaluation note.",
        "tags": ["automem-evals"],
        "metadata": json.dumps({"source_agent": "hub-developer"}),
    }
    with gzip.open(snapshot / "falkordb" / "falkordb_20260609_000000.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({"nodes": [{"id": 1, "labels": ["Memory"], "properties": props}], "relationships": []}, handle)
    with gzip.open(snapshot / "qdrant" / "qdrant_20260609_000000.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({"points": [{"id": "m1", "vector": [0.1], "payload": props}]}, handle)
    return snapshot


def metadata_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(overrides)
    return env


class RealDataMetadataEvalShellTests(unittest.TestCase):
    def test_write_probes_only_writes_ignored_sweep_run_artifacts(self):
        sweep_root = HERE / "data" / "sweep_runs"
        sweep_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="test-metadata-probes-only-", dir=sweep_root))
        snapshot = write_synthetic_snapshot(run_dir)

        try:
            result = subprocess.run(
                [
                    "bash",
                    str(HERE / "scripts" / "real_data_metadata_eval.sh"),
                    "--snapshot",
                    str(snapshot),
                    "--variant",
                    "metadata-tags",
                    "--write-probes-only",
                    "--run-dir",
                    str(run_dir),
                ],
                cwd=HERE,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            scenario = json.loads((run_dir / "metadata_probe_scenario.json").read_text())
            self.assertEqual(scenario["scenarios"][0]["expected_ids"], ["m1"])
            self.assertTrue((run_dir / "README.md").exists())
            readme = (run_dir / "README.md").read_text()
            self.assertIn("baseline compose project: `automem_metadata_baseline`", readme)
            self.assertIn("candidate compose project: `automem_metadata_candidate`", readme)
            self.assertIn("baseline qdrant grpc port: `6345`", readme)
            self.assertIn("candidate qdrant grpc port: `6346`", readme)
        finally:
            if run_dir.exists():
                shutil.rmtree(run_dir)

    def test_worktree_env_overrides_are_recorded_in_readme(self):
        sweep_root = HERE / "data" / "sweep_runs"
        sweep_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="test-metadata-env-", dir=sweep_root))
        snapshot = write_synthetic_snapshot(run_dir)

        try:
            result = subprocess.run(
                [
                    "bash",
                    str(HERE / "scripts" / "real_data_metadata_eval.sh"),
                    "--snapshot",
                    str(snapshot),
                    "--variant",
                    "metadata-tags",
                    "--write-probes-only",
                    "--run-dir",
                    str(run_dir),
                ],
                cwd=HERE,
                env=metadata_env(
                    BASELINE_COMPOSE_PROJECT="automem_metadata_502e_baseline",
                    CANDIDATE_COMPOSE_PROJECT="automem_metadata_502e_candidate",
                    BASELINE_API_PORT="8111",
                    BASELINE_QDRANT_GRPC_PORT="6445",
                    CANDIDATE_API_PORT="8112",
                    CANDIDATE_QDRANT_GRPC_PORT="6446",
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            readme = (run_dir / "README.md").read_text()
            self.assertIn("baseline compose project: `automem_metadata_502e_baseline`", readme)
            self.assertIn("candidate compose project: `automem_metadata_502e_candidate`", readme)
            self.assertIn("baseline endpoint: `http://localhost:8111`", readme)
            self.assertIn("candidate endpoint: `http://localhost:8112`", readme)
            self.assertIn("baseline qdrant grpc port: `6445`", readme)
            self.assertIn("candidate qdrant grpc port: `6446`", readme)
        finally:
            if run_dir.exists():
                shutil.rmtree(run_dir)

    def test_restore_plan_only_prints_configured_compose_projects(self):
        sweep_root = HERE / "data" / "sweep_runs"
        sweep_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="test-metadata-restore-plan-", dir=sweep_root))
        snapshot = write_synthetic_snapshot(run_dir)

        try:
            result = subprocess.run(
                [
                    "bash",
                    str(HERE / "scripts" / "real_data_metadata_eval.sh"),
                    "--snapshot",
                    str(snapshot),
                    "--variant",
                    "metadata-tags",
                    "--restore-plan-only",
                    "--run-dir",
                    str(run_dir),
                ],
                cwd=HERE,
                env=metadata_env(
                    BASELINE_COMPOSE_PROJECT="automem_metadata_502e_baseline",
                    CANDIDATE_COMPOSE_PROJECT="automem_metadata_502e_candidate",
                    BASELINE_QDRANT_GRPC_PORT="6445",
                    CANDIDATE_QDRANT_GRPC_PORT="6446",
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("--compose-project automem_metadata_502e_baseline", result.stdout)
            self.assertIn("--compose-project automem_metadata_502e_candidate", result.stdout)
            self.assertIn("--qdrant-grpc-port 6445", result.stdout)
            self.assertIn("--qdrant-grpc-port 6446", result.stdout)
            self.assertNotIn("[2/6] Restoring baseline stack", result.stdout)
        finally:
            if run_dir.exists():
                shutil.rmtree(run_dir)


if __name__ == "__main__":
    unittest.main()
