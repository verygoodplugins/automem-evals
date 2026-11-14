# Supersede: LongMemEval knowledge-update supersession gap track

Track: [#105](https://github.com/verygoodplugins/automem-evals/issues/105). Candidate: `opportunity:automem-graph-rag-research-scout`. Related, not duplicated: [#50](https://github.com/verygoodplugins/automem-evals/issues/50) (StateMemBench), [#31](https://github.com/verygoodplugins/automem-evals/issues/31) (ForgetEval), [#22](https://github.com/verygoodplugins/automem-evals/issues/22) / [#23](https://github.com/verygoodplugins/automem-evals/issues/23) ([Memora/FAMA](../benchmarks/memora-fama.md)), [#48](https://github.com/verygoodplugins/automem-evals/issues/48) / [#49](https://github.com/verygoodplugins/automem-evals/pull/49) (MemDelta), [#102](https://github.com/verygoodplugins/automem-evals/issues/102) / [#103](https://github.com/verygoodplugins/automem-evals/pull/103) (mempoison), [maturation](maturation.md).

**Desk review plus an offline scaffold. Nothing was run against AutoMem, no upstream code was executed, and no model credits were spent.** Every figure below is paper-reported or recomputed from the pinned dataset file. None is an AutoMem score. Checked 2026-11-14.

## Source, license and pins

| Artifact | Pin |
| --- | --- |
| [Paper](https://arxiv.org/abs/2606.27472) | "Supersede: Diagnosing and Training the Memory-Update Gap in LLM Agents", one author (Vedant Patel, Vrin), cs.CL, v1 2026-06-25, no later version, no venue (preprint). v1 PDF sha256 `ba7175324f30b02ff1967242250d421afdb0a6f1f80c3f48d2576f4f77de7e1b` |
| [Code `Vrin-cloud/supersede`](https://github.com/Vrin-cloud/supersede/tree/677993d3713c265329ac935262d3c08cbfa4cd63) | **Apache-2.0** (GitHub API, root `LICENSE` text, README badge and `CITATION.cff` agree). Pinned at `main` `677993d3713c265329ac935262d3c08cbfa4cd63` (2026-06-30, root tree `1c4a7f3d8a965e8fc821bd2e9b8d878ccc77dcab`); tag `v0.2.3` predates the paper |
| Dataset [`xiaowu0162/longmemeval-cleaned`](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/tree/98d7416c24c778c2fee6e6f3006e7a073259d48f) | MIT (card; the LongMemEval repo is MIT too). Revision `98d7416c24c778c2fee6e6f3006e7a073259d48f`. `longmemeval_oracle.json`: 15,388,478 bytes, sha256 `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` (downloaded and re-hashed). `longmemeval_s_cleaned.json`: 277,383,467 bytes, sha256 `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` (HF metadata only) |

Upstream's env downloads `.../resolve/main/longmemeval_oracle.json` **unpinned**, so its data can drift; this track pins the revision and fails closed on the hash. The license permits reuse, but the rules still hold: commit no upstream code or data, fetch into an ignored directory, and write adapter code from the documented protocol. Duplicate check (2026-11-14): all 37 issues and 67 PRs, with issue comments, contain no `2606.27472`, `Vrin-cloud` or title hit.

## What the data is (verified at the pin)

The oracle file has 500 questions; **78 are `knowledge-update`**. Each has exactly **two dated, chronological sessions** (earlier and later evidence session, no distractors; 20 to 24 turns, 1,830 in total). `has_answer` flags user turns only. Flagged turns per question (earlier, later): **68 are (1, 1), 2 are (2, 1), 2 are (0, 1), 6 are (0, 0)**; the six `(0, 0)` are the `_abs` abstention items. Two golds are integers. **LongMemEval ships no superseded value**, so upstream's `stale_penalty` is inert here (its README: "gold-only"). 

**Session order is not a currency label.** The gold is not always the latest value. Nine questions ask for the earlier one (`initially`, `previous`, `before X`) and five need both (`now vs previously`, `did I switch`). Treating the later session as `current` for them would mark the gold-bearing earlier turn `stale` and, in the oracle arm, invalidate it. A pre-PR review caught this (e.g. `07741c44` "Where do I *initially* keep my old sneakers?" gold "under my bed"; `9bbe84a2` "previous goal", gold "level 100"; `031748ae` needs both). Audit: all 72 non-abstention questions read, plus the gold text searched in the flagged turns (every earlier-only match is in the historical set). Annotated in `adapter.py`; each can be checked against the pin:

- `historical` (9): `07741c44`, `50635ada`, `e66b632c`, `0ddfec37`, `dfde3500`, `9bbe84a2`, `0977f2af`, `89941a94`, `10e09553`
- `mixed` (5): `031748ae`, `f685340e`, `6071bd76`, `c4ea545c`, `c6853660`

Strata used below: `both_labeled` 56, `late_only` 2, `historical` 9, `mixed` 5, `abstention` 6. Only the first two (58 questions) feed the three rates and the oracle links; the other three are reported with their n and excluded. This is a human-judgment audit by one reviewer, not an upstream label: a stale-value annotation pass (see Gates) should re-check it.

## Paper-reported results (not AutoMem scores)

Bounded 300-character self-rewritten notes vs full context, n = 78, oracle, LLM judge `gpt-4.1-mini`: gpt-4.1-mini 82% vs 63% (McNemar p = 0.0035), gpt-4.1 91% vs 64%, **gpt-5.4 92% vs 77%** (p = 0.0033). Scale study (gpt-4.1-mini, **n = 25**, programmatic matcher): oracle (~2 sessions) 68%, `_s` (~48 sessions) 28%, `_s` with 24x memory 28%. GRPO Qwen2.5-3B: 9.0% to 16.7%, **one run**. The paper's reader keeps a fixed-size notes string and never re-reads raw sessions, so it is a different construct from AutoMem's unbounded store behind `/recall`. These rows are context, never a target or comparator.

## Mapping to AutoMem

| Construct | AutoMem surface |
| --- | --- |
| Turns | `POST /memory/batch`, one memory per turn, `timestamp` (to `t_valid`) = session time (+1 s per turn for a total order), tag `supersede:<run>:<question_id>`, `tag_match=exact`. The `has_answer` label never enters a payload |
| Revision | `supersedes_memory_id=<earlier evidence>` (MCP-level: write replacement, patch old `t_invalid`, associate old to new). `INVALIDATED_BY` (correction) or `EVOLVED_INTO` (evolution), as in [memora-fama.md](../benchmarks/memora-fama.md) |
| Read | `GET /recall`, `current_only=true` (drops `t_invalid` / superseded records, inline relation payloads included) vs `false` for history; `end` = `question_date` as the leakage guard |

| Variant | Write path | Note |
| --- | --- | --- |
| `plain` | All turns, no lifecycle fields | Cold substrate |
| `supersede_oracle` | Later evidence supersedes earlier evidence, **chosen from `has_answer` labels** | Oracle upper bound for the read path (does `current_only` suppress the stale record?); 58 links over 56 questions (the `both_labeled` stratum; `historical`, `mixed` and abstention get none). Not a measure of AutoMem detecting revisions |
| `supersede_detected` | Agent or consolidation decides, no labels | Not scaffolded; owner decision; always a separate column |

Read params (`current_only=true`, limit 10, exact tag, `end`) are identical across variants, so the write path is the only experimental variable. A live smoke should also run `current_only=false` as a diagnostic.

## Scoring: current / stale / other

Exclusive classes per scorable question: `current` (current value, no stale), `stale` (stale value, not current), `other` (neither, or both; sub-counts `neither` and `both` always reported). Two levels: **retrieval** (`classify_recall`: ranks of the later/earlier evidence turns in the recalled top-k, no model) and **answer** (`classify_text`: reader output vs gold and stale values, word-boundary match). Answer-level `stale` needs stale values LongMemEval does not ship: a hand-annotated sidecar for the 58 scored questions, or `stale = null`. `aggregate` returns every rate as null (`not_scored`) unless every scorable question has a verdict. Report per-stratum n with every rate.

## Cold and matured

Per [maturation.md](maturation.md), every result carries `cold` and `matured` and their delta. Only `cold` is wired, so reports emit `matured: {"status": "not_run", ...}` with the reason. The open question for this track is whether consolidation and invalidation passes close the `plain` vs `supersede_oracle` gap without labels.

## Scaffold

`runners/supersede_gap/adapter.py` (stdlib only; no network, model or AutoMem calls) and `runners/test_supersede_adapter.py`:

```bash
python3 runners/supersede_gap/adapter.py --data /path/to/longmemeval_oracle.json --run-id smoke \
  --out report.json --plan-out plan.jsonl [--limit N]
python3 -m unittest runners.test_supersede_adapter     # SUPERSEDE_ORACLE_JSON=<file> adds the pinned-shape test
```

It refuses any file whose sha256 or shape differs from the pin, builds deterministic `plain` / `supersede_oracle` plans, and emits a `not_scored` report (`paper_comparable: false`). The CLI has no recall transport, so it cannot emit a score.

## Gates

- **Spend:** none approved. Retrieval-level scoring needs only the AutoMem server (its embedding calls must still use [paid-budget.md](paid-budget.md)'s proxy). The paper's readers (`gpt-4.1-mini`, `gpt-4.1`, `gpt-5.4`) are not routable through it (supported: `gpt-5-mini`, `gpt-5.4-mini-2026-03-17`, `voyage-4`, `text-embedding-3-small`): use a supported reader and publish a **non-comparable** column, or extend the proxy with verified prices first.
- **Boundary:** LongMemEval claims stay in `automem` ([REPO_BOUNDARY.md](../REPO_BOUNDARY.md)); anything run here is experimental.
- **Next:** live adapter (loopback only, isolated tags, delete only own UUIDs, count protocol errors), then a 10-question retrieval smoke after approval. Checklist: issue #105.
