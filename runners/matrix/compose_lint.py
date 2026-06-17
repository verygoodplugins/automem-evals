"""Lint a docker-compose / override for matrix-isolation anti-patterns:
fixed container_name (breaks per-cell isolation) and literal host ports
(breaks parallel stacks). Host ports must be variables like ${API_PORT}.
"""

import re
from typing import List

import yaml

_FIXED_HOST_PORT = re.compile(r"^\s*\d+:\d+\s*$")


def lint_compose(yaml_text: str) -> List[str]:
    errors: List[str] = []
    doc = yaml.safe_load(yaml_text) or {}
    services = doc.get("services", {}) or {}
    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        if "container_name" in svc:
            errors.append(
                f"service '{svc_name}' sets container_name (breaks isolation)"
            )
        for port in svc.get("ports", []) or []:
            if isinstance(port, str) and _FIXED_HOST_PORT.match(port):
                errors.append(f"service '{svc_name}' uses fixed host port '{port}'")
    return errors
