# External baseline matrix verification — 2026-10-24

Scope: documentation/reference data only. No AutoMem evaluation, benchmark model call, adapter implementation, external comment, submission, push or PR creation occurred. Local branch: `agent/kernel-worker/34f6a055`. The orchestrator owns publishing and signed AutoVault babysit finalization.

## Repository checks

Used `/opt/homebrew/opt/python@3.12/bin/python3.12` (3.12.13); system `python3` is 3.9.6 and below this repository's documented minimum. No Python source changed and no separate documentation linter is configured.

| Existing command | Observed result |
| --- | --- |
| `python3.12 -m unittest discover -s runners -p 'test_*.py'` | 233 tests, OK, 13 skipped |
| `python3.12 -m unittest discover -s scripts -p 'test_*.py'` | 30 tests, OK |
| `python3.12 -m unittest discover -s scripts/benchmarks -p 'test_*.py'` | 7 tests, OK |
| `uv run --python 3.12 --with pytest --with pyyaml --with requests python -m pytest tests/matrix/ -q` | 12 passed |
| `git diff --check` | Passed |

The runner log includes expected negative-path fixtures; the suite exits 0. Logs are retained locally in `.agent-drafts/{runners,scripts,benchmarks,matrix}-tests.txt`.

## Source and data checks

JSON parses; 22 unique rows have owner, answerer, judge, score/unit/status and canonical HTTPS source URL fields. Every URL occurs in the Markdown. All vendor rows carry the unverified-field-report label; four Mem0 rows preserve null answerer/judge fields. No row is an AutoMem result. All 12 AMB rows were compared against the pinned source for system/version, k, questions, hits/question, score, answerer and judge. Markdown matches JSON's score values. Evidence: `.agent-drafts/matrix-validation.json` and `amb-results-source.md`.

AMB's source pin is `3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91`; past.dev's harness pin is `a712cd993e249cadd214168c3c3ee674f89bd5e4`. Live vendor pages remain mutable. Inspected the supplied press release, vendor result pages, Mem0 post, AMB results/methodology/contribution template, issue #274, and FEB-30 abstract. Reading public claims does not reproduce them.

Connected GitHub reads checked local open/closed issues and PRs (#45/#54/#61/#73/#74), #45's existing follow-up, and upstream AMB `AutoMem` issues/comments and all-state PR searches (zero matches). #73 is a dashboard PR containing a different AMB summary, not an upstream submission issue. Memory MCP tools were unavailable; no memory recall/store was performed.

## Browser evidence

Rendered the actual Markdown with Python Markdown's tables extension and served the worktree on loopback. Headless Chromium checked the preview at `http://127.0.0.1:18864/.agent-drafts/baseline-preview.html`: 6 + 4 + 12 matrix rows, 22 canonical source links, eight “not disclosed” model/judge cells, JSON and handoff links HTTP 200, JSON length 22, and vendor labeling visible. Desktop (1440px) and mobile (390px) have no page overflow; tables scroll within their containers. Inspected the desktop screenshot. This is a documentation preview, not a deployed website or a benchmark UI claim.

Local artifacts: `.agent-drafts/matrix-dom.json`, `matrix-desktop.png`, `matrix-mobile.png`, and `baseline-preview.html`. Preview styling is not a repository/product change. The publishing drafts in `external-baselines-handoff.md` include verification and remain unsubmitted; main-branch matrix links must be posted after merge or replaced with finalized PR-head links.
