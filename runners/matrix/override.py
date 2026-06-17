"""Per-stack docker-compose override: maps host ports for this cell and bakes
the cell's config into the flask-api environment (AutoMem reads config at boot).
"""

from typing import Any, Dict

import yaml


def build_override(ports: Dict[str, int], config: Dict[str, Any]) -> Dict[str, Any]:
    environment = {str(k): str(v) for k, v in config.items()}
    environment.setdefault("PORT", "8001")
    return {
        "services": {
            "falkordb": {
                "ports": [f"{ports['falkor']}:6379", f"{ports['falkor_ui']}:3000"]
            },
            "qdrant": {"ports": [f"{ports['qdrant']}:6333"]},
            "flask-api": {
                "ports": [f"{ports['api']}:8001"],
                "environment": environment,
            },
        }
    }


def render_override(ports: Dict[str, int], config: Dict[str, Any]) -> str:
    return yaml.safe_dump(build_override(ports, config), sort_keys=False)
