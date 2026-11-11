"""Run one disposable local graph-expansion comparison."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRODUCT = "46481560b6bf8570a7a43fc1d7e2a5bfdae4e236"
ERROR = re.compile(
    r"Traceback \(most recent call last\)|\| ERROR \||Query timed out", re.I
)


def cmd(args, **kwargs):
    result = subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)
    return result.stdout.strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-repo", type=Path, required=True)
    parser.add_argument("--model-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_output = args.output.with_name(args.output.stem + "-raw.json")
    if args.output.exists() or raw_output.exists():
        parser.error("output and raw output must not exist")
    repo = args.product_repo.resolve(strict=True)
    cache = args.model_cache.resolve(strict=True)
    if cmd(["git", "-C", str(repo), "rev-parse", PRODUCT + "^{commit}"]) != PRODUCT:
        raise RuntimeError("product commit unavailable")
    revision = cmd(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    for path in (
        HERE / "run.py",
        HERE / "scenario.py",
        HERE / "server.py",
        HERE / "compose.yaml",
    ):
        content = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{revision}:{path.relative_to(ROOT)}"],
            check=True,
            capture_output=True,
        ).stdout
        if hashlib.sha256(content).hexdigest() != sha(path):
            raise RuntimeError(f"uncommitted runner source: {path.name}")
    model = cache / "models--qdrant--bge-base-en-v1.5-onnx-q"
    model_revision = (model / "refs/main").read_text().strip()
    model_sha = sha(model / "snapshots" / model_revision / "model_optimized.onnx")
    image_ids = {
        image: cmd(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        for image in (
            "automem-flask-api:latest",
            "falkordb/falkordb:latest",
            "qdrant/qdrant:v1.11.3",
        )
    }
    project = "graphvalue" + uuid.uuid4().hex[:12]
    compose = ["docker", "compose", "-p", project, "-f", str(HERE / "compose.yaml")]
    container = project + "-api-1"
    failure = None
    result = None
    logs = ""
    with tempfile.TemporaryDirectory(prefix="graph-value-") as temp_name:
        temp = Path(temp_name)
        archive = temp / "source.tar"
        cmd(
            [
                "git",
                "-C",
                str(repo),
                "archive",
                "--format=tar",
                "-o",
                str(archive),
                PRODUCT,
            ]
        )
        source = temp / "source"
        source.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        env = dict(
            os.environ,
            AUTOMEM_SOURCE=str(source),
            MODEL_CACHE=str(cache),
            SCENARIO_FILE=str(HERE / "scenario.py"),
            SERVER_FILE=str(HERE / "server.py"),
        )
        try:
            cmd(compose + ["up", "-d", "--pull", "never"], env=env)
            check = (
                'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8001/health",timeout=2)); '
                'assert d.get("original_text_index")=="ready" and d.get("falkordb")=="connected" and d.get("qdrant")=="connected"'
            )
            for attempt in range(180):
                probe = subprocess.run(
                    ["docker", "exec", container, "python", "-c", check],
                    capture_output=True,
                )
                if probe.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise TimeoutError("isolated API failed readiness")
            result = json.loads(
                cmd(["docker", "exec", container, "python", "/experiment/scenario.py"])
            )
            # This contains only synthetic fixtures; keep full API envelopes
            # in the operator's local path, not in the published aggregate.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            cmd(
                ["docker", "cp", f"{container}:/tmp/graph-value-raw.json", str(raw_output)]
            )
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                logs = cmd(compose + ["logs", "--no-color", "api"], env=env)
            except Exception as exc:
                failure = (failure or "") + f" log capture failed: {type(exc).__name__}"
            cleanup = subprocess.run(
                compose + ["down", "-v", "--remove-orphans"],
                env=env,
                capture_output=True,
                text=True,
            )
            if cleanup.returncode:
                failure = (failure or "") + " isolated cleanup failed"
    errors = [line for line in logs.splitlines() if ERROR.search(line)]
    report = {
        "kind": "graph-value-diagnostic",
        "product_sha": PRODUCT,
        "runner_sha": revision,
        "runner_files": {
            path.name: sha(path)
            for path in (
                HERE / "run.py",
                HERE / "scenario.py",
                HERE / "server.py",
                HERE / "compose.yaml",
            )
        },
        "model": "BAAI/bge-base-en-v1.5",
        "model_revision": model_revision,
        "model_sha256": model_sha,
        "image_ids": image_ids,
        "network": "internal",
        "provider_calls": 0,
        "api_log_errors": len(errors),
        "failure": failure,
        "result": result,
        "raw_sha256": sha(raw_output) if raw_output.exists() else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(report, out, indent=2, sort_keys=True)
        out.write("\n")
    if failure or errors or result is None:
        raise RuntimeError("experiment failed; inspect isolated receipt")
    print(args.output)


if __name__ == "__main__":
    main()
