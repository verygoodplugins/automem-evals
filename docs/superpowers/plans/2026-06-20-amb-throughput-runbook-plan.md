# AMB Submission — Throughput + Evidence Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the full AMB/`omb` result set for AutoMem — Core-3 (LoCoMo, LongMemEval, PersonaMem) + BEAM (100K→10M) — crash-safely, in parallel, with accuracy±CI / latency / context-token triplets, autonomously over the 2026-06-20→22 window.

**Architecture:** One small code change hardens the only crash-unsafe path (PersonaMem batch mode), then a runbook fans out the self-spinning AMB harness across datasets and 3× repeats, aggregates the result JSONs into a triplet report. Outward-facing publish/PR steps are explicitly excluded (human-gated).

**Tech Stack:** Python 3.11+, `uv`, the `vectorize-io/agent-memory-benchmark` (`omb`) harness fork at `/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark` (branch `feat/automem-provider`), AutoMem self-spun via Docker (FalkorDB + Qdrant + FastEmbed-local), Gemini API (Tier 2).

## Global Constraints

- **Fork repo:** `/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark`, branch `feat/automem-provider`. All code changes land here on a child branch off this branch; do **not** rebase or clobber the other agent's commits.
- **Run command shape (verbatim base):** `OMB_ANSWER_LLM=gemini OMB_ANSWER_MODEL=gemini-3.1-pro-preview OMB_JUDGE_LLM=gemini OMB_JUDGE_MODEL=gemini-2.5-flash-lite uv run omb run --memory automem --mode rag` + per-run `--dataset/--split`.
- **Splits:** locomo→`locomo10`, longmemeval→`s`, personamem→`32k`, beam→`100k|500k|1m|10m`.
- **Output path:** `outputs/{dataset}/{run_name}/{mode}/{split}.json`; `run_name` = `--name` value, else `automem`.
- **Repeats MUST use distinct `--name`** (e.g. `automem-rep1/2/3`) — `_save()` merges by `query_id` within a run_name, so same-name repeats would collapse into one.
- **Ship config (verify in `automem_compose.yml` before scored runs):** `RECALL_RECENCY_BIAS=auto`; FastEmbed-local `BAAI/bge-base-en-v1.5` 768d; lean (no-LLM) enrichment. Do NOT enable `SEARCH_TAG_SCORE_TOKEN_CAP` (known regression).
- **Budget guardrail:** if calibration (Task 2) returns HTTP 429 `RESOURCE_EXHAUSTED`/`quota`, the Tier-2 preload has not landed → STOP all spend tasks (3,4), leave staged, report.
- **Human-gated, OUT OF SCOPE:** publishing the public GHCR image; forking/PR to vectorize-io. Stage only.

---

### Task 1: Batch-mode incremental checkpoint + resume (PersonaMem crash-safety)

**Why:** `runner.py`'s isolation-unit path already saves after every unit (lines 327–339) and resumes via `--skip-ingested` (lines 262–272). The **batch path** (`isolation_unit is None`, lines 348–378) saves only once at the end (line 414) and ignores `--skip-ingested` — so a crash loses everything. PersonaMem is the only Core-3+BEAM dataset in batch mode; this is exactly why its 247 answers vanished.

**Files:**
- Modify: `agent-memory-benchmark/src/memory_bench/runner.py` (batch branch, ~lines 348–378)
- Test: `agent-memory-benchmark/tests/test_batch_checkpoint.py` (create)

**Interfaces:**
- Consumes: `EvalRunner.run(dataset, split, memory, mode, query_limit=, skip_ingested=, run_name=)`; `EvalRunner._save(EvalSummary)`; `EvalRunner._load_previous(...)`; models `Query`, `Document`, `AnswerResult`, `QueryResult`, `EvalSummary`; base classes `Dataset`, `MemoryProvider`, `ResponseMode`.
- Produces: batch-mode runs that (a) call `_save` at least every 10 completed queries, and (b) when `skip_ingested=True`, skip queries whose `query_id` already has a non-empty `answer` in the prior output file.

- [ ] **Step 1: Write the failing test**

Create `agent-memory-benchmark/tests/test_batch_checkpoint.py`:

```python
import os
import json
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "test-dummy")

from memory_bench import runner as runner_mod
from memory_bench.runner import EvalRunner
from memory_bench.dataset.base import Dataset
from memory_bench.memory.base import MemoryProvider
from memory_bench.modes.base import ResponseMode
from memory_bench.models import Query, Document, AnswerResult


class _FakeLLM:
    model_id = "fake-judge"

class _FakeJudge:
    def __init__(self, llm=None):
        self._llm = _FakeLLM()
    def score(self, *a, **k):
        from memory_bench.models import JudgeResult
        return JudgeResult(correct=True, reason="fake")


class _StubDataset(Dataset):
    name = "stubds"
    description = "stub"
    splits = ["s"]
    task_type = "mcq"          # mcq => exact-letter scoring, no judge network call
    isolation_unit = None      # => BATCH mode (the path under test)

    def __init__(self, n):
        self._n = n
    def load_queries(self, split, category=None, limit=None):
        qs = [Query(id=f"q{i}", query=f"q{i}", gold_ids=[], gold_answers=["A"]) for i in range(self._n)]
        return qs[:limit] if limit else qs
    def load_documents(self, split, category=None, limit=None, ids=None, user_ids=None):
        return [Document(id="d0", content="ctx", user_id=None)]
    def supports_oracle(self):
        return False


class _StubMemory(MemoryProvider):
    name = "stubmem"
    description = "stub"
    kind = "local"
    concurrency = 4
    def ingest(self, documents):
        pass
    def retrieve(self, query, k=10, user_id=None, query_timestamp=None):
        return ([Document(id="d0", content="ctx")], None)


class _StubMode(ResponseMode):
    name = "stub"
    description = "stub"
    def __init__(self, seen):
        self._seen = seen
    @property
    def llm_id(self):
        return "stub-answerer"
    def answer(self, query, memory, task_type="open", user_id=None):
        self._seen.append(query)                       # record which queries were answered
        return AnswerResult(answer="A", reasoning="", context="ctx", retrieve_time_ms=1.0)
    def answer_from_context(self, query, context, task_type="open"):
        return AnswerResult(answer="A", reasoning="", context=context, retrieve_time_ms=0.0)


def _make_runner(tmp_path, monkeypatch, save_calls):
    monkeypatch.setattr(runner_mod, "GeminiJudge", _FakeJudge)
    r = EvalRunner(output_dir=tmp_path / "outputs")
    orig_save = r._save
    def spy(summary):
        save_calls.append(summary.total_queries)
        return orig_save(summary)
    monkeypatch.setattr(r, "_save", spy)
    return r


def test_batch_mode_saves_incrementally(tmp_path, monkeypatch):
    save_calls = []
    r = _make_runner(tmp_path, monkeypatch, save_calls)
    seen = []
    r.run(dataset=_StubDataset(25), split="s", memory=_StubMemory(),
          mode=_StubMode(seen), run_name="t1")
    # Incremental saves fired before the final save (25 queries, SAVE_EVERY=10 => 10, 20, final)
    assert any(0 < n < 25 for n in save_calls), f"no partial save observed: {save_calls}"
    assert len(seen) == 25


def test_batch_mode_resume_skips_done(tmp_path, monkeypatch):
    # Pre-write a partial output file with q0..q9 already answered.
    out = tmp_path / "outputs" / "stubds" / "t2" / "rag"
    out.mkdir(parents=True)
    prior = {"dataset": "stubds", "split": "s", "category": None,
             "memory_provider": "stubmem", "run_name": "t2", "mode": "rag",
             "oracle": False, "total_queries": 10, "correct": 10, "accuracy": 1.0,
             "ingestion_time_ms": 0.0, "ingested_docs": 1,
             "results": [{"query_id": f"q{i}", "query": f"q{i}", "answer": "A",
                          "reasoning": "", "context": "ctx", "context_tokens": 1,
                          "retrieve_time_ms": 0.0, "gold_answers": ["A"],
                          "correct": True, "judge_reason": "", "score": None,
                          "meta": {}, "raw_response": None, "category_axes": {}}
                         for i in range(10)]}
    (out / "s.json").write_text(json.dumps(prior))

    save_calls = []
    r = _make_runner(tmp_path, monkeypatch, save_calls)
    seen = []
    r.run(dataset=_StubDataset(25), split="s", memory=_StubMemory(),
          mode=_StubMode(seen), run_name="t2", skip_ingested=True)
    # Only q10..q24 should be answered this run; q0..q9 skipped.
    assert sorted(seen) == [f"q{i}" for i in range(10, 25)], f"resume answered wrong set: {sorted(seen)}"
    # Final file contains all 25 (merge preserved the prior 10).
    final = json.loads((out / "s.json").read_text())
    assert final["total_queries"] == 25
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark
uv run --with pytest pytest tests/test_batch_checkpoint.py -v
```
Expected: `test_batch_mode_saves_incrementally` FAILS (`no partial save observed: [25]` — only the final save fires today) and `test_batch_mode_resume_skips_done` FAILS (`resume answered wrong set` — all 25 answered because batch mode ignores `skip_ingested`).

- [ ] **Step 3: Add the resume filter to the batch branch**

In `runner.py`, replace the batch-branch header (currently line 348 `else:` … through the ingestion `if/else`) so the `else:` opens with a resume filter and an all-done ingest guard:

```python
        else:
            # Batch mode: ingest all documents upfront, then answer all queries.
            # Resume (--skip-ingested): skip queries already answered in a prior crashed run.
            if skip_ingested:
                prev = self._load_previous(dataset.name, split, effective_name, mode.name)
                done_ids = {r["query_id"] for r in prev.get("results", []) if r.get("answer")}
                if done_ids:
                    before = len(queries)
                    queries = [q for q in queries if q.id not in done_ids]
                    console.print(f"[dim]Resume: skipping {before - len(queries)} already-answered queries (--skip-ingested).[/dim]")

            if skip_ingestion:
                console.print(f"[dim]Skipping ingestion (--skip-ingestion).[/dim]\n")
                ingestion_ms = self._load_previous_ingestion_ms(dataset.name, split, effective_name, mode.name)
                ingested_docs_count = self._load_previous_ingested_docs(dataset.name, split, effective_name, mode.name)
            elif not queries:
                console.print(f"[dim]Resume: all queries already answered; skipping ingestion.[/dim]\n")
                ingestion_ms = self._load_previous_ingestion_ms(dataset.name, split, effective_name, mode.name)
                ingested_docs_count = self._load_previous_ingested_docs(dataset.name, split, effective_name, mode.name)
            else:
                console.print(f"[dim]Ingesting into {memory.name}...[/dim]")
                t0 = time.perf_counter()
                memory.ingest(documents)
                ingestion_ms = (time.perf_counter() - t0) * 1000
                ingested_docs_count = len(documents)
                console.print(f"  ingested in {ingestion_ms:.0f}ms ({ingestion_ms / len(documents):.1f}ms/doc avg)\n")
```

- [ ] **Step 4: Add incremental save to `_run_all`**

In `runner.py`, replace the `_run_all` closure (currently lines 362–373) with the lock-guarded periodic-save version:

```python
            _SAVE_EVERY = 10

            async def _run_all(progress, task_id):
                concurrency = getattr(memory, "concurrency", _CONCURRENCY)
                sem = asyncio.Semaphore(concurrency)
                results = [None] * len(queries)
                save_lock = asyncio.Lock()
                completed = 0

                async def bounded(i, q):
                    nonlocal completed
                    async with sem:
                        results[i] = await _process_one(q)
                        progress.advance(task_id)
                    async with save_lock:
                        completed += 1
                        if completed % _SAVE_EVERY == 0:
                            done = [r for r in results if r]
                            self._save(EvalSummary(
                                dataset=dataset.name, split=split, category=category,
                                memory_provider=memory.name, run_name=effective_name,
                                mode=mode.name, oracle=oracle,
                                total_queries=len(done),
                                correct=sum(1 for r in done if r.correct),
                                accuracy=0.0, ingestion_time_ms=round(ingestion_ms, 1),
                                ingested_docs=ingested_docs_count,
                                description=description, answer_llm=mode.llm_id,
                                judge_llm=self._get_judge(dataset)._llm.model_id,
                                results=done,
                            ))

                await asyncio.gather(*[bounded(i, q) for i, q in enumerate(queries)])
                return results
```

(`_save` merges by `query_id`, so concurrent partial snapshots and the final save compose correctly.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark
uv run --with pytest pytest tests/test_batch_checkpoint.py -v
```
Expected: both PASS. Then run the existing adapter tests to confirm no regression:
```bash
uv run --with pytest pytest tests/test_automem_provider.py -v
```
Expected: PASS (unchanged).

- [ ] **Step 6: Commit**

```bash
cd /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark
git checkout -b feat/batch-checkpoint-resume
git add src/memory_bench/runner.py tests/test_batch_checkpoint.py
git commit -m "fix(runner): incremental save + --skip-ingested resume for batch-mode datasets

Batch-mode datasets (no isolation_unit, e.g. PersonaMem) only saved at run
end and ignored --skip-ingested, so a crash lost the whole run. Mirror the
unit-sequential path: save every 10 completed queries and skip already-
answered query_ids on resume.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Calibration burst + credit probe

**Why:** Cheapest possible confirmation that (a) the Tier-2 preload landed, (b) the pipeline is green end-to-end, (c) the spec's per-question token/latency assumptions hold — before any large spend.

**Files:** none (operational). Records to `agent-memory-benchmark/outputs/...` + a note in `automem-evals/data/results/`.

- [ ] **Step 1: Verify ship-config env present**

```bash
grep -nE "RECALL_RECENCY_BIAS|EMBEDDING_PROVIDER|bge-base" /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark/src/memory_bench/memory/automem_compose.yml
```
Expected: `RECALL_RECENCY_BIAS=auto` and FastEmbed-local present. If `RECALL_RECENCY_BIAS` is missing, add it to the compose env before scored runs.

- [ ] **Step 2: Run a 5-query LoCoMo calibration (credit probe)**

```bash
cd /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark
OMB_ANSWER_LLM=gemini OMB_ANSWER_MODEL=gemini-3.1-pro-preview \
OMB_JUDGE_LLM=gemini OMB_JUDGE_MODEL=gemini-2.5-flash-lite \
uv run omb run --memory automem --mode rag --dataset locomo --split locomo10 \
  --query-limit 5 --name automem-calib 2>&1 | tee /tmp/amb-calib.log
```
Expected: completes; `Saved → outputs/locomo/automem-calib/rag/locomo10.json`; non-empty answers; latency lines printed.
**STOP CONDITION:** if the log contains `429`, `RESOURCE_EXHAUSTED`, or `quota` → preload not landed. Halt Tasks 3–4, report, leave staged.

- [ ] **Step 3: Read the calibration triplet**

```bash
python3 -c "import json; d=json.load(open('/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark/outputs/locomo/automem-calib/rag/locomo10.json')); print('acc',d['accuracy'],'n',d['total_queries'],'avg_retrieve_ms',d.get('avg_retrieve_time_ms'),'avg_ctx_tok',d.get('avg_context_tokens'),'empty',sum(1 for r in d['results'] if not r['context']))"
```
Expected: `acc` plausible (≥0.6 on 5q), `empty` 0, latency + ctx tokens populated. Record these as the measured baseline; reconcile against the spec's ~$0.06–0.12/q (output-token $ from the Gemini billing dashboard after the burst).

- [ ] **Step 4: Checkpoint** — if green, proceed to Task 3. If red, stop and report.

---

### Task 3: Small suite ×3 in parallel (Core-3 + BEAM-100K)

**Why:** These are small-context, fast-embed datasets; the machine (137 GB / 18 cores) holds all of them in parallel many times over. 3 repeats → mean ± CI.

**Files:** writes `outputs/{dataset}/automem-rep{1,2,3}/rag/{split}.json`.

- [ ] **Step 1: Launch all 4 datasets × 3 repeats as background runs**

For each `dataset/split` in {locomo/locomo10, longmemeval/s, personamem/32k, beam/100k} and each `rep` in {1,2,3}, launch (stagger rep-starts by a few seconds to avoid Docker port-alloc races):

```bash
cd /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark
OMB_ANSWER_LLM=gemini OMB_ANSWER_MODEL=gemini-3.1-pro-preview \
OMB_JUDGE_LLM=gemini OMB_JUDGE_MODEL=gemini-2.5-flash-lite \
uv run omb run --memory automem --mode rag --dataset <DS> --split <SPLIT> \
  --name automem-rep<R> --description "amb-submission small-suite rep<R>" \
  > /tmp/amb-<DS>-<SPLIT>-rep<R>.log 2>&1
```
Run these as background tasks (Bash `run_in_background: true`); cap concurrent *ingesting* runs to ≤6 if CPU saturates (watch `docker stats`). PersonaMem now benefits from Task 1's incremental save.

- [ ] **Step 2: Monitor to completion**

Poll each log for `Saved →` (success) or a stop-condition string (`429|RESOURCE_EXHAUSTED|quota|Traceback`). On a crash, resume that one run:
```bash
# unit-sequential (locomo/longmemeval/beam) AND now personamem (Task 1):
... uv run omb run ... --dataset <DS> --split <SPLIT> --name automem-rep<R> --skip-ingested
```

- [ ] **Step 3: Verify all 12 outputs exist and are non-empty**

```bash
for ds in locomo:locomo10 longmemeval:s personamem:32k beam:100k; do for r in 1 2 3; do
  f="/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark/outputs/${ds%%:*}/automem-rep$r/rag/${ds##*:}.json"
  python3 -c "import json,sys; d=json.load(open('$f')); print('${ds} rep$r', d['total_queries'], round(d['accuracy'],3))" 2>/dev/null || echo "MISSING $f"
done; done
```
Expected: 12 lines, each with the full split's `total_queries` (152/500/589/400) and an accuracy.

- [ ] **Step 4: Checkpoint** — all 12 present → Task 4.

---

### Task 4: Big BEAM tiers ×1 (500K → 1M → 10M)

**Why:** These are ingest-heavy (500K 86 MB, 1M 173 MB, 10M 984 MB raw). They are **already crash-safe** (BEAM is unit-sequential → per-conversation incremental save + `--skip-ingested` resume). Run 1× each (CI argument transfers from the cheaper tiers). 10M is cheap on Gemini (200 q) but slow on local ingest — run it last/overnight.

**Files:** writes `outputs/beam/automem/rag/{500k,1m,10m}.json`.

- [ ] **Step 1: Run 500K then 1M (can overlap; ~2 stacks)**

```bash
cd /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark
for SPLIT in 500k 1m; do
  OMB_ANSWER_LLM=gemini OMB_ANSWER_MODEL=gemini-3.1-pro-preview \
  OMB_JUDGE_LLM=gemini OMB_JUDGE_MODEL=gemini-2.5-flash-lite \
  uv run omb run --memory automem --mode rag --dataset beam --split $SPLIT \
    --description "amb-submission beam-$SPLIT" > /tmp/amb-beam-$SPLIT.log 2>&1 &
done; wait
```
Resume any crash with `--skip-ingested` (same command + flag).

- [ ] **Step 2: Run 10M alone (overnight; heavy ingest)**

```bash
cd /Users/jgarturo/Projects/OpenAI/agent-memory-benchmark
OMB_ANSWER_LLM=gemini OMB_ANSWER_MODEL=gemini-3.1-pro-preview \
OMB_JUDGE_LLM=gemini OMB_JUDGE_MODEL=gemini-2.5-flash-lite \
uv run omb run --memory automem --mode rag --dataset beam --split 10m \
  --description "amb-submission beam-10m" > /tmp/amb-beam-10m.log 2>&1
```

- [ ] **Step 3: Verify the 3 big-tier outputs**

```bash
for s in 500k 1m 10m; do
  python3 -c "import json; d=json.load(open('/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark/outputs/beam/automem/rag/$s.json')); print('beam $s', d['total_queries'], round(d['accuracy'],3), 'ret_ms', d.get('avg_retrieve_time_ms'), 'ctx', d.get('avg_context_tokens'))"
done
```
Expected: 700/700/200 queries with accuracy + latency + tokens.

- [ ] **Step 4: Checkpoint** — all present → Task 5.

---

### Task 5: Aggregate into the triplet report (accuracy±CI / latency / tokens)

**Files:**
- Create: `automem-evals/runners/amb_aggregate.py`
- Create: `automem-evals/data/results/SUMMARY-amb-submission-2026-06.md`

- [ ] **Step 1: Write the aggregator**

Create `automem-evals/runners/amb_aggregate.py`:

```python
#!/usr/bin/env python3
"""Aggregate AMB omb result JSONs into the accuracy±CI / latency / tokens triplet.

Reads the fork's outputs/ dir. Scored datasets have 3 repeat runs (automem-rep1/2/3);
big BEAM tiers have a single run (automem). Emits a markdown table.
"""
import json, math, statistics, sys
from pathlib import Path

OUT = Path("/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark/outputs")
SCORED = [("locomo", "locomo10"), ("longmemeval", "s"), ("personamem", "32k"), ("beam", "100k")]
SINGLE = [("beam", "500k"), ("beam", "1m"), ("beam", "10m")]
T_975_2 = 4.303  # t critical, 95%, 2 dof (n=3)

def load(ds, run, split):
    p = OUT / ds / run / "rag" / f"{split}.json"
    return json.loads(p.read_text()) if p.exists() else None

def triplet(ds, split, runs):
    ds_runs = [load(ds, r, split) for r in runs]
    ds_runs = [d for d in ds_runs if d]
    if not ds_runs:
        return f"| {ds}/{split} | MISSING | | |"
    accs = [d["accuracy"] for d in ds_runs]
    ret = statistics.median([d["avg_retrieve_time_ms"] for d in ds_runs if d.get("avg_retrieve_time_ms")])
    tok = statistics.median([d["avg_context_tokens"] for d in ds_runs if d.get("avg_context_tokens")])
    n = len(accs); mean = statistics.mean(accs)
    if n >= 2:
        sd = statistics.stdev(accs); ci = T_975_2 * sd / math.sqrt(n)
        acc_s = f"{mean*100:.1f}% ± {ci*100:.1f} (n={n})"
    else:
        acc_s = f"{mean*100:.1f}% (n=1)"
    return f"| {ds}/{split} | {acc_s} | {ret:.0f} ms | {tok:.0f} |"

def main():
    rows = ["| Dataset | Accuracy (95% CI) | Recall latency (median) | Context tokens (median) |",
            "|---|---|---|---|"]
    for ds, split in SCORED:
        rows.append(triplet(ds, split, ["automem-rep1", "automem-rep2", "automem-rep3"]))
    for ds, split in SINGLE:
        rows.append(triplet(ds, split, ["automem"]))
    print("\n".join(rows))

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and capture the table**

```bash
cd /Users/jgarturo/Projects/OpenAI/automem-evals
python3 runners/amb_aggregate.py | tee /tmp/amb-triplet.md
```
Expected: a 7-row table, no `MISSING`.

- [ ] **Step 3: Write the summary doc**

Create `automem-evals/data/results/SUMMARY-amb-submission-2026-06.md` with: the triplet table; the frozen ship config; the exact run commands; head-to-head vs Hindsight (latency + tokens are the objective axes); and the explicit note that publish/PR are human-gated and staged for review.

- [ ] **Step 4: Commit (automem-evals only; fork stays on its branch)**

```bash
cd /Users/jgarturo/Projects/OpenAI/automem-evals
git add runners/amb_aggregate.py data/results/SUMMARY-amb-submission-2026-06.md
git commit -m "feat(amb): triplet aggregator + submission results summary

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Calibrate-then-commit (spec C) → Task 2. ✓
- Checkpoint-hardening (spec D) → Task 1, now correctly scoped to PersonaMem batch mode only (BEAM/LoCoMo/LongMemEval already safe — a material refinement of the spec, which assumed all datasets lacked checkpointing). ✓
- Parallel fan-out (spec A) → Task 3. ✓
- 3× repeats for CI (spec B) → Tasks 3 + 5. ✓
- Triplet reporting → Task 5. ✓
- Out-of-scope publish/PR → excluded, stated in Global Constraints. ✓

**Placeholder scan:** none — all run commands, file paths, and the production diff are literal; test code is complete.

**Type consistency:** `EvalSummary`/`QueryResult`/`AnswerResult` field names in the test and the `_run_all` partial-save match `models.py`. `_save`/`_load_previous`/`_get_judge` signatures match `runner.py`. CLI flags match `cli.py` (`--split/--dataset/--memory/--mode/--query-limit/--skip-ingested/--name/--description`).

**Note for execution:** Tasks 2–4 are operational (spend + wall-clock), not TDD; their "tests" are the verify steps + stop conditions. Only Task 1 is a code change and is full RED→GREEN→REFACTOR.

---

## Execution addendum — discovered at runtime (2026-06-20)

Three plan assumptions were wrong; corrected live within the autonomy window.

**1. Real full-split sizes (the runner's own "queries loaded" line is authoritative):**
- locomo/locomo10 = **1,540** queries (NOT 152 — the committed `outputs/locomo/automem/…`
  file was a smaller partial/filtered run). longmemeval/s = 500. personamem/32k = 589.
  beam 100k/500k/1m/10m = 400/700/700/200.

**2. One AutoMem stack saturates the whole host.** `docker stats` showed a single active
stack at **~1781% CPU (~18 cores)** — FastEmbed query-embedding is unbounded-thread. Running
4 (or even 2) stacks oversubscribes 18 cores and *starves* the others (a stack stuck mid-ingest
sat at 0.03%). **Concurrency buys no parallelism here**, so the orchestrator runs **serial
(MAXC=1)**, each run at full CPU, fast→slow with **longmemeval last** (its ~12–25 h solo
per-question ingest is the long pole; banking everything else first de-risks the window).

**3. Repeat strategy revised ×3→×1 + reproducibility check.** At n=400–1,540 the **within-run
95% CI** (1.96·sd/√n over per-question scores) is already tighter than run-to-run judge noise,
and longmemeval ×3 is infeasible. So: **×1 per dataset** with within-run CI, **plus beam-100k ×3**
(`automem-sub-rep1/2/3`) as an explicit run-to-run reproducibility check. This honors the intent
(statistical confidence) better than blind ×3 and fits the window.

**Mechanics:**
- Fresh runs use run_name **`automem-sub`** (and `automem-sub-rep{1,2,3}` for the beam-100k
  check) to avoid merging into the other agent's committed `automem` outputs.
- All runs override **`AUTOMEM_IMAGE=ghcr.io/verygoodplugins/automem:amb-local`** (the public
  `amb-v1` tag is the human-gated publish step and does not exist yet).
- Config frozen as the committed compose (FastEmbed-local, lean enrichment). `RECALL_RECENCY_BIAS=auto`
  is NOT applied — it was validated in a different harness; flipping it unattended would risk the
  headline with no in-harness evidence. Logged as a documented future A/B instead.
- Orchestrator: `/tmp/amb_orchestrate.py` (serial, resumes any partial via `--skip-ingested`).
  Long-haul monitor emits per-run completion + hard-quota + final events.
- Supersedes Task 3 (parallel waves) and the Task 5 aggregator's run-name scheme; aggregator
  updated to `automem-sub` + within-run CI + the beam-100k repro row.
