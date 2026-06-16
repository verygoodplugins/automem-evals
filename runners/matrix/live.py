"""Live provider: provision an isolated AutoMem stack with a baked config,
score it, tear it down. Used by the matrix orchestrator for real runs.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

from . import override as ov_mod
from . import resources
from . import score as score_mod

AUTOMEM_DIR = os.environ.get("AUTOMEM_DIR", "/Users/jgarturo/Projects/OpenAI/automem")
API_TOKEN = os.environ.get("AUTOMEM_API_TOKEN", "benchmark-token")


def _project(name: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in name.lower())
    return f"automem_eval_{safe}"


def compose_up_cmd(
    project: str, automem_dir: str, override_path: str, ports: Dict[str, int]
) -> List[str]:
    return [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(Path(automem_dir) / "docker-compose.yml"),
        "-f",
        override_path,
        "up",
        "-d",
    ]


def compose_down_cmd(project: str) -> List[str]:
    return ["docker", "compose", "-p", project, "down", "-v", "--remove-orphans"]


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}


class LiveProvider:
    def __init__(self, automem_dir: str = AUTOMEM_DIR, base_api: int = 18001):
        self.automem_dir = automem_dir
        self.base_api = base_api
        self._ports: Dict[str, Dict[str, int]] = {}
        self._index = 0

    def provision(self, name: str, config: Dict[str, Any]) -> str:
        ports = resources.cell_ports(self._index, base_api=self.base_api)
        self._index += 1
        self._ports[name] = ports
        ov_path = Path(tempfile.gettempdir()) / f"matrix-override-{_project(name)}.yml"
        # Bake the API token into the override so it matches our headers.
        baked = {"AUTOMEM_API_TOKEN": API_TOKEN, **config}
        ov_path.write_text(ov_mod.render_override(ports, baked))
        # Pass port env-vars so the base compose interpolates the correct host
        # ports (docker compose merges the ports list — we rely on base compose
        # var substitution so each overlay stack gets unique host bindings).
        env = {
            **os.environ,
            "FALKORDB_HOST_PORT": str(ports["falkor"]),
            "FALKORDB_BROWSER_HOST_PORT": str(ports["falkor_ui"]),
            "QDRANT_HOST_PORT": str(ports["qdrant"]),
            "QDRANT_GRPC_HOST_PORT": str(ports["qdrant"] + 1),
            "AUTOMEM_API_HOST_PORT": str(ports["api"]),
        }
        subprocess.run(
            compose_up_cmd(_project(name), self.automem_dir, str(ov_path), ports),
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        url = f"http://localhost:{ports['api']}"
        self._wait_healthy(url)
        return url

    def _wait_healthy(self, url: str, timeout: int = 120) -> None:
        last = None
        for _ in range(timeout):
            try:
                if requests.get(f"{url}/health", timeout=2).status_code == 200:
                    return
            except Exception as e:  # noqa: BLE001
                last = e
            time.sleep(1)
        raise TimeoutError(f"stack at {url} never became healthy: {last}")

    def score(
        self,
        api_url: str,
        name: str,
        config: Dict[str, Any],
        queries=None,
        distractor_ids=None,
        recall_params=None,
    ) -> Dict[str, Any]:
        return score_mod.score_stack(
            api_url,
            _headers(),
            queries or [],
            distractor_ids=distractor_ids,
            recall_params=recall_params,
            config=config,
        )

    def teardown(self, name: str) -> None:
        subprocess.run(
            compose_down_cmd(_project(name)),
            check=False,
            capture_output=True,
            text=True,
        )
