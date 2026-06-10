import gzip
import json
import os
import shlex
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

    def test_runtime_env_file_records_embedding_config_without_secrets(self):
        sweep_root = HERE / "data" / "sweep_runs"
        sweep_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="test-metadata-runtime-env-", dir=sweep_root))
        snapshot = write_synthetic_snapshot(run_dir)
        runtime_env = run_dir / "automem.env"
        runtime_env.write_text(
            "EMBEDDING_PROVIDER=voyage\n"
            "VOYAGE_API_KEY=secret-value\n"
            "VECTOR_SIZE=1024\n"
            "QDRANT_URL=https://prod.example.invalid\n"
        )

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
                env=metadata_env(AUTOMEM_RUNTIME_ENV_FILE=str(runtime_env)),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            readme = (run_dir / "README.md").read_text()
            self.assertIn(f"runtime env file: `{runtime_env}`", readme)
            self.assertIn("embedding provider: `voyage`", readme)
            self.assertIn("vector size: `1024`", readme)
            self.assertNotIn("secret-value", readme + result.stdout + result.stderr)
            self.assertNotIn("prod.example.invalid", readme + result.stdout + result.stderr)
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

    def test_restore_plan_quotes_paths_and_arguments(self):
        sweep_root = HERE / "data" / "sweep_runs"
        sweep_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="test metadata restore plan ", dir=sweep_root))
        snapshot = write_synthetic_snapshot(run_dir)
        automem_dir = run_dir / "automem path; touch nope"
        automem_python = automem_dir / ".venv" / "bin" / "python"

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
                    AUTOMEM_DIR=str(automem_dir),
                    AUTOMEM_PYTHON=str(automem_python),
                    BASELINE_COMPOSE_PROJECT="automem metadata baseline",
                    CANDIDATE_COMPOSE_PROJECT="automem metadata candidate",
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            line = next(
                item for item in result.stdout.splitlines() if item.startswith("baseline restore: ")
            )
            argv = shlex.split(line.removeprefix("baseline restore: "))
            self.assertEqual(argv[0], "bash")
            self.assertEqual(argv[1], str(automem_dir / "scripts" / "lab" / "clone_production.sh"))
            self.assertIn(str(snapshot), argv)
            self.assertIn("automem metadata baseline", argv)
            self.assertIn(str(automem_python), argv)
        finally:
            if run_dir.exists():
                shutil.rmtree(run_dir)

    def test_restore_plan_server_variant_uses_separate_automem_dirs(self):
        sweep_root = HERE / "data" / "sweep_runs"
        sweep_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="test-metadata-server-plan-", dir=sweep_root))
        snapshot = write_synthetic_snapshot(run_dir)
        baseline_dir = run_dir / "automem-baseline"
        candidate_dir = run_dir / "automem-candidate"
        baseline_python = baseline_dir / ".venv" / "bin" / "python"
        candidate_python = candidate_dir / ".venv" / "bin" / "python"

        try:
            result = subprocess.run(
                [
                    "bash",
                    str(HERE / "scripts" / "real_data_metadata_eval.sh"),
                    "--snapshot",
                    str(snapshot),
                    "--variant",
                    "server-metadata-search",
                    "--restore-plan-only",
                    "--run-dir",
                    str(run_dir),
                ],
                cwd=HERE,
                env=metadata_env(
                    AUTOMEM_DIR=str(baseline_dir),
                    BASELINE_AUTOMEM_DIR=str(baseline_dir),
                    CANDIDATE_AUTOMEM_DIR=str(candidate_dir),
                    BASELINE_AUTOMEM_PYTHON=str(baseline_python),
                    CANDIDATE_AUTOMEM_PYTHON=str(candidate_python),
                    BASELINE_COMPOSE_PROJECT="automem_metadata_server_baseline",
                    CANDIDATE_COMPOSE_PROJECT="automem_metadata_server_candidate",
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            lines = result.stdout.splitlines()
            baseline_line = next(line for line in lines if line.startswith("baseline restore: "))
            candidate_line = next(line for line in lines if line.startswith("candidate restore: "))
            baseline_argv = shlex.split(baseline_line.removeprefix("baseline restore: "))
            candidate_argv = shlex.split(candidate_line.removeprefix("candidate restore: "))
            self.assertEqual(
                baseline_argv[1], str(baseline_dir / "scripts" / "lab" / "clone_production.sh")
            )
            self.assertEqual(
                candidate_argv[1], str(candidate_dir / "scripts" / "lab" / "clone_production.sh")
            )
            self.assertIn(str(baseline_python), baseline_argv)
            self.assertIn(str(candidate_python), candidate_argv)
            readme = (run_dir / "README.md").read_text()
            self.assertIn(f"baseline automem dir: `{baseline_dir}`", readme)
            self.assertIn(f"candidate automem dir: `{candidate_dir}`", readme)
            self.assertIn("run label: `metadata-sidecar-enabled`", readme)
        finally:
            if run_dir.exists():
                shutil.rmtree(run_dir)


if __name__ == "__main__":
    unittest.main()
