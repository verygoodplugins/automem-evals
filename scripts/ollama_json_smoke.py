#!/usr/bin/env python3
"""
Sanity: Ollama's OpenAI-compat endpoint can produce schema-shaped JSON under
`response_format={"type": "json_object"}`. This is the single riskiest
assumption behind using a local model as BEAM's judge — if Ollama ignores
`response_format` or the model won't produce the expected keys, the judge
will crash on parse.

Mirrors BEAM's call shape from
`third_party/memory-benchmarks/benchmarks/common/llm_client.py:269-275`:
  chat.completions.create(
      model=…,
      messages=[…],
      response_format={"type": "json_object"},
      temperature=0,
  )

Exit 0 = endpoint works and returns valid JSON with the expected keys. Any
other exit = do NOT proceed with Phase 2; something in the local-inference
plumbing needs attention first.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

# BEAM's judge expects a specific schema from the "json_object" response. For
# this probe we approximate with a fact-check shape so we can assert keys
# without needing the exact BEAM prompt.
PROBE_SYSTEM = (
    "You are a strict evaluator. Respond ONLY with a JSON object with "
    "exactly these keys: `is_correct` (boolean), `reasoning` (string, ≤25 words)."
)
PROBE_USER = (
    "Question: What is the capital of France?\n"
    "Ground truth: Paris.\n"
    "Candidate answer: Paris, the capital city since 987 CE.\n"
    "Evaluate whether the candidate answer contains the ground truth."
)


def probe(base_url: str, model: str, timeout: float) -> int:
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": PROBE_SYSTEM},
            {"role": "user", "content": PROBE_USER},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except Exception as exc:
        print(f"[fail] HTTP error calling {url}: {exc}")
        return 2
    dt = time.monotonic() - t0
    try:
        resp = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[fail] envelope is not JSON: {exc}\n  raw: {raw[:300]!r}")
        return 3

    try:
        content = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"[fail] unexpected OpenAI envelope: {json.dumps(resp)[:300]}")
        return 4

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        print(f"[fail] model returned non-JSON content despite response_format: {exc}")
        print(f"  raw content: {content[:400]!r}")
        return 5

    missing = [k for k in ("is_correct", "reasoning") if k not in parsed]
    if missing:
        print(f"[fail] parsed JSON missing expected keys: {missing}")
        print(f"  got keys: {list(parsed.keys())}")
        return 6
    if not isinstance(parsed["is_correct"], bool):
        print(f"[fail] `is_correct` is {type(parsed['is_correct']).__name__}, not bool: {parsed['is_correct']!r}")
        return 7

    usage = resp.get("usage") or {}
    print(f"[ok] model={model} dt={dt:.1f}s tokens={usage.get('total_tokens','?')}")
    print(f"     parsed = {json.dumps(parsed)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--model", default="llama3.3:70b")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()
    return probe(args.base_url, args.model, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
