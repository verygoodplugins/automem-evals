#!/usr/bin/env python3
"""Run a frozen synthetic scorer probe against a loopback Ollama server only."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import build_opener

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FIXTURE = HERE / "fixture.json"
MODEL = "qwen3.6:35b-a3b"
HELDOUT_SHA256 = "28e130cdf90f0704141667476463345f4a348ff1fc1f495a52a9d0d15b5dab76"
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 768}
SYSTEM = """Evaluate an answer against every required criterion using only the given answer.
Optional guidance must never become a requirement. Paraphrases count when they clearly satisfy a criterion. For every criterion give its zero-based index and one status: met, unmet, contradicted, or uncertain. A met or contradicted status must include a short exact, contiguous quotation copied from the answer. An unmet status may use null when no passage exists. If a criterion has multiple requirements, all must be met. If the answer explicitly conflicts with any requirement mark it contradicted. Abstaining without satisfying a requirement is unmet. Use uncertain when the answer does not clearly establish satisfaction or failure. Overall verdict is fail if any criterion is unmet or contradicted, ambiguous if none fail and any is uncertain, otherwise pass. Return only the requested JSON."""
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "judgments"],
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail", "ambiguous"]},
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion_index", "status", "quote"],
                "properties": {
                    "criterion_index": {"type": "integer"},
                    "status": {
                        "type": "string",
                        "enum": ["met", "unmet", "contradicted", "uncertain"],
                    },
                    "quote": {"type": ["string", "null"]},
                },
            },
        },
    },
}


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def load_fixture(path: Path = FIXTURE) -> dict:
    data = json.loads(path.read_text())
    rows = data["cases"]
    if data.get("version") != 1 or not rows:
        raise ValueError("Unsupported or empty fixture")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate fixture IDs")
    if {row["split"] for row in rows} != {"development", "heldout"}:
        raise ValueError("Fixture needs exactly the two frozen splits")
    for row in rows:
        if row["expected"] not in {"pass", "fail"} or not row["criteria"]:
            raise ValueError(f"Invalid manual label or criteria: {row['id']}")
    heldout = [row for row in rows if row["split"] == "heldout"]
    if canonical_sha(heldout) != HELDOUT_SHA256:
        raise ValueError(
            "Held-out fixture changed; create a new version instead of reusing it"
        )
    return data


def loopback_url(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "http"
        or parts.hostname not in {"127.0.0.1", "::1"}
        or parts.username
        or parts.password
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "Ollama URL must be an HTTP loopback origin with no credentials or path"
        )
    return value.rstrip("/")


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Do not allow a loopback server to redirect requests off the machine."""

    def http_error_302(self, request, response, code, message, headers):
        response.close()
        raise URLError("Redirects are disabled")

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def transport_json(
    origin: str, path: str, payload: dict | None = None, timeout: int = 180
) -> dict:
    # Validate at the boundary and disable proxies and redirects, even when
    # called directly instead of through run().
    origin = loopback_url(origin)
    opener = build_opener(urllib.request.ProxyHandler({}), RejectRedirects())
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        origin + path, data=data, headers={"Content-Type": "application/json"}
    )
    with opener.open(request, timeout=timeout) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict):
        raise ValueError("Ollama response must be an object")
    return result


def model_digest(tags: dict) -> str:
    found = [row for row in tags.get("models", []) if row.get("name") == MODEL]
    if len(found) != 1 or not re.fullmatch(
        r"[0-9a-f]{64}", str(found[0].get("digest", ""))
    ):
        raise ValueError(
            f"Expected exactly one locally installed {MODEL} with a full digest"
        )
    if (
        not isinstance(found[0].get("size"), int)
        or found[0]["size"] <= 0
        or found[0].get("remote_model")
        or found[0].get("remote_host")
    ):
        raise ValueError("Model must be locally stored, not a remote model reference")
    return found[0]["digest"]


def payload_for(row: dict) -> dict:
    # Never send the label, split, fixture category, or case ID to the scorer.
    packet = {key: row[key] for key in ("question", "criteria", "optional", "answer")}
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
        ],
        "format": SCHEMA,
        "stream": False,
        "think": False,
        "options": OPTIONS,
    }


def validate_result(result: object, row: dict) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    if not isinstance(result, dict) or set(result) != {"verdict", "judgments"}:
        return None, ["response must contain only verdict and judgments"]
    verdict, judgments = result["verdict"], result["judgments"]
    if verdict not in {"pass", "fail", "ambiguous"} or not isinstance(judgments, list):
        return None, ["invalid verdict or judgments"]
    indices: list[int] = []
    statuses: list[str] = []
    for judgment in judgments:
        if not isinstance(judgment, dict) or set(judgment) != {
            "criterion_index",
            "status",
            "quote",
        }:
            errors.append("invalid judgment fields")
            continue
        idx, state, quote = (
            judgment["criterion_index"],
            judgment["status"],
            judgment["quote"],
        )
        if type(idx) is not int or idx < 0 or idx >= len(row["criteria"]):
            errors.append("invalid criterion index")
        else:
            indices.append(idx)
        if state not in {"met", "unmet", "contradicted", "uncertain"}:
            errors.append("invalid criterion status")
        else:
            statuses.append(state)
        if quote is not None and (
            not isinstance(quote, str)
            or not quote.strip()
            or quote not in row["answer"]
        ):
            errors.append("quote must be a nonempty literal substring of the answer")
        if state in {"met", "contradicted"} and (
            not isinstance(quote, str) or not quote.strip()
        ):
            errors.append("met and contradicted criteria require a literal quote")
    if sorted(indices) != list(range(len(row["criteria"]))):
        errors.append("every required criterion must be evaluated exactly once")
    inferred = (
        "fail"
        if any(s in {"unmet", "contradicted"} for s in statuses)
        else "ambiguous" if "uncertain" in statuses else "pass"
    )
    if len(statuses) != len(row["criteria"]) or verdict != inferred:
        errors.append("overall verdict must agree with per-criterion judgments")
    return (verdict if not errors else None), errors


def frozen_config(data: dict, digest: str) -> dict:
    return {
        "fixture_sha256": canonical_sha(data),
        "heldout_sha256": HELDOUT_SHA256,
        "model": MODEL,
        "model_digest": digest,
        "system_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
        "schema_sha256": canonical_sha(SCHEMA),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "options": OPTIONS,
        "think": False,
    }


def run(phase: str, origin: str, output: Path, freeze: Path | None = None) -> dict:
    origin = loopback_url(origin)
    output = output.resolve()
    if output == REPO or REPO in output.parents:
        raise ValueError(
            "Output must be outside the git worktree; raw results stay local"
        )
    data = load_fixture()
    digest = model_digest(transport_json(origin, "/api/tags", timeout=15))
    config = frozen_config(data, digest)
    if phase == "heldout":
        if freeze is None or json.loads(freeze.read_text()) != config:
            raise ValueError(
                "Held-out run requires the exact development frozen.json config"
            )
    elif freeze is not None:
        raise ValueError("--freeze is only used for heldout")
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n"
    )
    rows = [row for row in data["cases"] if row["split"] == phase]
    random.Random(42).shuffle(rows)
    observations = []
    started = time.time()
    for row in rows:
        observation = {
            "id": row["id"],
            "kind": row["kind"],
            "expected": row["expected"],
        }
        try:
            response = transport_json(origin, "/api/chat", payload_for(row))
            model_text = response["message"]["content"]
            result = json.loads(model_text)
            verdict, errors = validate_result(result, row)
            observation.update(
                {
                    "verdict": verdict,
                    "validation_errors": errors,
                    "response": result,
                    "model_eval_count": response.get("eval_count"),
                    "model_eval_duration_ns": response.get("eval_duration"),
                }
            )
        except Exception as exc:
            observation.update(
                {"verdict": None, "validation_errors": [f"{type(exc).__name__}: {exc}"]}
            )
        observations.append(observation)
        # Flush after each case so interruption cannot be mistaken for completion.
        with (output / "cases.jsonl").open("a") as file:
            file.write(json.dumps(observation, ensure_ascii=False) + "\n")
    valid = [row for row in observations if row["verdict"] is not None]
    by_kind = {}
    for kind in sorted({row["kind"] for row in observations}):
        group = [row for row in observations if row["kind"] == kind]
        by_kind[kind] = {
            "cases": len(group),
            "valid": sum(row["verdict"] is not None for row in group),
            "correct": sum(row["verdict"] == row["expected"] for row in group),
        }
    summary = {
        "phase": phase,
        "cases": len(rows),
        "valid": len(valid),
        "invalid": len(rows) - len(valid),
        "correct": sum(row["verdict"] == row["expected"] for row in valid),
        "ambiguous": sum(row["verdict"] == "ambiguous" for row in valid),
        "false_passes": sum(
            row["expected"] == "fail" and row["verdict"] == "pass" for row in valid
        ),
        "false_fails": sum(
            row["expected"] == "pass" and row["verdict"] == "fail" for row in valid
        ),
        "by_kind": by_kind,
        "elapsed_seconds": time.time() - started,
        "config": config,
        "interpretation": "Synthetic diagnostic; literal-quote validation does not prove semantic support.",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    if phase == "development" and not summary["invalid"]:
        (output / "frozen.json").write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n"
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("development", "heldout"), required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--freeze", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.phase, args.ollama_url, args.output_dir, args.freeze)
    except Exception as exc:
        print(f"Probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["invalid"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
