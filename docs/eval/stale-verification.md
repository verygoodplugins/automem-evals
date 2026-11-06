# STALE feasibility verification report

Date: 2026-10-06. Task: `agent-fp-4aaeadaaa69cbc8d66975d0c`.
Branch: `agent/kernel-worker/66975d0c`.
Base revision: `35fa73d78703b4af6387762df7b74884520dc29f`.

## Route and acceptance status

Used read-only GitHub CLI/API and arXiv/Hugging Face HTTP access, then workspace
documentation writes. No companion repository changed. No issue/comment, push,
PR, review/CI finalization, or merge was performed. The orchestrator owns the
signed AutoVault babysit finalizer after this implementation handoff.

**Publication blocked by execution boundary:** the task requests an issue, but
the immutable effects permit only `read` and `workspace-write`, and the execution
mode explicitly prohibits external mutations. The complete issue body is
`docs/eval/stale.md`; its title is
`track: STALE implicit-conflict benchmark (arXiv:2605.06527)`.
Issue URL: **not available; no issue was created or updated**. Artifact research
is complete; the external issue acceptance criterion remains unmet.

No memory MCP recall tool was exposed in this session, so the prescribed early
recalls were unavailable. No persistent memory was written.

## Evidence

- Duplicate search: three successful `gh issue list --repo verygoodplugins/automem-evals --state all --limit 100 --search ...` calls for `STALE`, `2605.06527`, and `"implicit conflict"`. Matches are recorded in the issue body; no STALE-paper tracker was found.
- Code pin: GitHub commit API returned `ea7d391103a151927cd29d2f01d87597a782bdcb`; recursive tree reported `truncated=false`. The pinned LICENSE is MIT. Loader, scorer, judge rubric, provider client, and CUPMem update/sample/stale-link sources were inspected.
- Data pin: Hugging Face API returned `617c51dc200b5ab09970834144c7e51c77959af0`, `private=false`, `gated=false`, `disabled=false`, with CC BY 4.0 metadata and a separate LongMemEval MIT notice. Full-file size/LFS checksum metadata are recorded in the issue body.
- Actual data: HTTP 206, `Content-Range: bytes 0-4194303/305908212`. First complete record UID `7c0ae4e7-6b5a-42a2-891b-0ccf553bfe7f`, type T1, 50 sessions/timestamps, evidence indices `[13, 33]`. Turn fields, timestamp/session alignment, and all three query keys passed assertions.
- The pinned scorer's actual `validate_dataset_record` and `get_query_text` functions were extracted through Python AST and executed on that real record without importing provider clients. Both passed. No gold annotation was written into AutoMem.

## Repository verification

All commands completed successfully:

```bash
python3 -m unittest discover -s runners -p 'test_run_current_state_recall_eval.py' -v
python3 -m unittest discover -s scripts -p 'test_experiment_index.py' -v
git diff --check
```

Results: 10 current-state tests and 14 experiment-index tests passed (24 total).
The documented bash block passed `bash -n`; its embedded Python block compiled
successfully. The full newly added files were also checked for trailing
whitespace/conflict markers through the staged diff before commit.

This was a feasibility review, not an experiment run: no adapter, synthetic
corpus, full download, provider calls, AutoMem score, or experiment-registry
score change was added. Upstream commands are source/syntax-verified only.

Next step: an external-write-authorized orchestrator rechecks duplicates,
publishes the prepared issue (or comments on a newly discovered matching issue),
and records its actual URL. Adapter execution belongs to a separate pass.
