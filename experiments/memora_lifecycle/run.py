"""Run an isolated, no-provider lifecycle diagnostic on a pinned product commit."""

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
ADAPTER_HEAD = "a99366cd21a29c2d7aabaf600884f07c9d8e4f5e"
ERROR_PATTERN = re.compile(
    r"Traceback \(most recent call last\)|\| ERROR \||Query timed out|Failed to load current-state replacements",
    re.I,
)


def command(args, **kwargs):
    try:
        return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"command failed ({exc.returncode}): {args[0]}: {exc.stderr[-4000:]}") from exc


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_committed(repo, revision, paths):
    """Refuse to label mutable experiment/adapter files as a pinned revision."""
    for path in paths:
        relative = path.relative_to(repo).as_posix()
        snapshot = subprocess.run(
            ["git", "-C", str(repo), "show", f"{revision}:{relative}"],
            check=True,
            capture_output=True,
        ).stdout
        if hashlib.sha256(snapshot).hexdigest() != sha(path):
            raise ValueError(f"experiment source differs from {revision}: {relative}")


def wait_ready(container):
    check = (
        "import json,urllib.request; "
        'd=json.load(urllib.request.urlopen("http://127.0.0.1:8001/health",timeout=2)); '
        'assert d.get("original_text_index")=="ready"; '
        'assert d.get("falkordb")=="connected" and d.get("qdrant")=="connected"'
    )
    for _ in range(180):
        proc = subprocess.run(
            ["docker", "exec", container, "python", "-c", check],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if proc.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError("isolated API did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-repo", type=Path, required=True)
    parser.add_argument("--model-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must not already exist")
    repo = args.product_repo.resolve(strict=True)
    model_cache = args.model_cache.resolve(strict=True)
    git_head = command(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    if (
        command(
            [
                "git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                ADAPTER_HEAD,
                git_head,
            ]
        )
        != ""
    ):
        raise RuntimeError("adapter ancestry check returned unexpected output")
    require_committed(
        ROOT,
        git_head,
        [
            HERE / "run.py",
            HERE / "scenario.py",
            HERE / "server.py",
            HERE / "compose.yaml",
            ROOT / "scripts/benchmarks/memora_fama_adapter.py",
        ],
    )
    product_sha = command(["git", "-C", str(repo), "rev-parse", PRODUCT + "^{commit}"])
    if product_sha != PRODUCT:
        raise RuntimeError("product revision does not match requested pin")
    model = model_cache / "models--qdrant--bge-base-en-v1.5-onnx-q"
    model_revision = (model / "refs/main").read_text().strip()
    model_hash = sha(model / "snapshots" / model_revision / "model_optimized.onnx")
    images = {
        image: command(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        for image in (
            "automem-flask-api:latest",
            "falkordb/falkordb:latest",
            "qdrant/qdrant:v1.11.3",
        )
    }
    project = "memoralife" + uuid.uuid4().hex[:12]
    compose = ["docker", "compose", "-p", project, "-f", str(HERE / "compose.yaml")]
    container = project + "-api-1"
    result = None
    failure = None
    logs = ""
    log_failure = None
    with tempfile.TemporaryDirectory(prefix="memora-lifecycle-") as temp:
        temp = Path(temp)
        archive = temp / "source.tar"
        command(
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
        with tarfile.open(archive) as source_tar:
            source_tar.extractall(source, filter="data")
        env = dict(
            os.environ,
            AUTOMEM_SOURCE=str(source),
            MODEL_CACHE=str(model_cache),
            ADAPTER_FILE=str(ROOT / "scripts/benchmarks/memora_fama_adapter.py"),
            SCENARIO_FILE=str(HERE / "scenario.py"),
            SERVER_FILE=str(HERE / "server.py"),
        )
        try:
            command(compose + ["up", "-d", "--pull", "never"], env=env)
            wait_ready(container)
            output = command(["docker", "exec", container, "python", "/experiment/scenario.py"])
            result = json.loads(output)
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                logs = command(compose + ["logs", "--no-color", "api"], env=env)
            except Exception as exc:
                log_failure = f"{type(exc).__name__}: {exc}"
            cleanup = subprocess.run(
                compose + ["down", "-v", "--remove-orphans"],
                env=env,
                text=True,
                capture_output=True,
            )
            if cleanup.returncode:
                failure = (failure or "") + f" cleanup failed for {project}: {cleanup.stderr}"
    if result is None:
        result = {
            "kind": "memora-lifecycle-diagnostic",
            "fama_score": None,
            "passed": 0,
            "total": 0,
            "request_audit": {"errors": []},
        }
    error_lines = [line for line in logs.splitlines() if ERROR_PATTERN.search(line)]
    result["api_log_audit"] = {
        "errors": len(error_lines),
        "clean": not error_lines and not log_failure,
        "log_collection_failed": bool(log_failure),
    }
    result["failure"] = failure
    result["product_sha"] = PRODUCT
    result["adapter_pr88_head"] = ADAPTER_HEAD
    result["eval_sha"] = git_head
    result["model"] = "BAAI/bge-base-en-v1.5"
    result["model_revision"] = model_revision
    result["model_sha256"] = model_hash
    result["image_ids"] = images
    result["scenario_sha256"] = sha(HERE / "scenario.py")
    result["runner_sha256"] = sha(HERE / "run.py")
    result["compose_sha256"] = sha(HERE / "compose.yaml")
    result["server_sha256"] = sha(HERE / "server.py")
    result["adapter_sha256"] = sha(ROOT / "scripts/benchmarks/memora_fama_adapter.py")
    result["provider_calls"] = 0
    result["isolation"] = {"network": "internal", "published_ports": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "passed": result["passed"],
                "total": result["total"],
                "api_log_audit": result["api_log_audit"],
            },
            sort_keys=True,
        )
    )
    if failure or result["request_audit"]["errors"] or not result["api_log_audit"]["clean"]:
        raise SystemExit("diagnostic finished with API errors; see output")
    if result["passed"] != result["total"]:
        raise SystemExit("one or more diagnostic cases failed; see output")


if __name__ == "__main__":
    main()
