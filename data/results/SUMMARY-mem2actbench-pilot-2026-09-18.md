# Mem2ActBench AutoMem pilot (2026-09-18)

Tracking: #24. Runner: [`runners/mem2actbench/`](../../runners/mem2actbench/README.md).
Aggregate: [`mem2actbench/pilot-results-2026-09-18.json`](mem2actbench/pilot-results-2026-09-18.json).

Exploratory result, not a benchmark claim (see [`docs/REPO_BOUNDARY.md`](../../docs/REPO_BOUNDARY.md)).

## Benchmark

[Mem2ActBench](https://arxiv.org/abs/2601.19935) (Shen, Li, Zhou and Hu;
[ACL 2026 long paper 370](https://aclanthology.org/2026.acl-long.370/)) is a
memory-to-action benchmark. It tests whether an agent retrieves and applies
implicit prior preferences or task state when grounding tool-call parameters.
The released full split has 2,029 sessions and 400 tool-use tasks. Each task
carries per-argument grounding labels (`explicit`, `inferred`, `default`) and a
complexity level from L1 (direct copy) to L4 (conflict resolution).

The authors' repository,
[Cantaloupe-M/Mem2ActBench](https://github.com/Cantaloupe-M/Mem2ActBench), is
the source of record for the data. It is untagged, and while its README says
MIT, GitHub does not identify a license file. Pin a commit for any rerun and do
not redistribute the data; the clone location is gitignored here.

## Result

The pilot completed all **400 full-split QA tasks** at **k=5**. For each task
it stored only the task's labelled `evolution_chain` facts under a unique run
tag, linked consecutive facts with `RELATES_TO`, recalled facts for the task
query, and deleted the stored facts before the next task. AutoMem accepted every
association (`0` failures).

| Measurement | F1 | Accuracy | Scope |
| --- | ---: | ---: | --- |
| AutoMem parameter-grounding evidence (this pilot) | **77.81%** | **75.67%** | 398 of 526 labelled non-default parameters supported by recalled evidence |
| AutoMem strict task evidence | — | **75.75%** | Every labelled non-default parameter supported |
| Paper oracle retrieval | 53.8% | — | Published end-to-end memory-to-action baseline |
| Paper passive hybrid retrieval (k=5) | 30.7% | — | Published end-to-end memory-to-action baseline |

Evidence precision was 80.08% (99 false-positive evidence items).

A first pass on the quick-test split (`toolmembench_small`) also ran 400 tasks:
76.62% evidence F1 and 72.64% parameter accuracy. That split packages fewer
sessions (429) than the full release, so the full-split numbers above are the
ones to cite.

### Metric boundary: read this before comparing numbers

This is an **evidence-retrieval** score, not the paper's end-to-end tool-call
F1. A non-default parameter counts as supported when a recalled memory contains
that parameter's labelled source text or source fact. A recalled fact that
supports no labelled parameter is a false-positive evidence item. Tool defaults
(254) and arguments with no grounding label (6) are excluded because they are
not historical memory facts.

So 77.81% does **not** mean AutoMem beats the paper's 53.8% oracle. The paper's
score also requires applying the evidence to produce a valid tool call, and
this pilot stops before any argument-synthesis step. The paper itself reads the
53.8-vs-30.7 oracle/passive gap as mainly a retrieval (evidence-hitting)
bottleneck. This pilot measures that retrieval half in isolation, and it seeds
only the labelled facts rather than the full session history, which makes
retrieval easier than in the paper's setting.

## Failure shape

| Complexity | Tasks | Evidence F1 | Parameter accuracy |
| --- | ---: | ---: | ---: |
| L1 direct copy | 237 | 86.14% | 81.27% |
| L2 inferred | 101 | 80.29% | 72.37% |
| L3 aggregation | 17 | 67.80% | 80.00% |
| L4 conflict resolution | 45 | **48.72%** | **57.58%** |

Of 400 tasks, 58 returned no facts and 39 returned some evidence but missed at
least one labelled parameter. L4 alone produced 52 of the 99 false-positive
evidence items. Three hypotheses worth testing next:

1. Plain recall picks semantically related facts but makes no graph-expansion
   or temporal-conflict request. The stored `RELATES_TO` chain edges alone did
   not resolve competing historical states.
2. L2 conversion and inference need an action-time synthesis layer (for
   example, turning a remembered natural-language date into a schema value),
   which a retrieval-only score correctly does not credit.
3. The labelled chain is narrow and isolated per run. A realistic pass has to
   ingest the full interrupted session histories.

## Recommendation

**Go on a second, paper-comparable pass.** The pilot is cheap and reproducible,
and it exposes an L4 temporal/conflict gap that recall-only benchmarks do not
isolate. Keep this evidence-only harness as the write/retrieval diagnostic, and
add, separately labelled:

- full session-history ingestion through the normal store path, instead of
  seeding only the labelled chain;
- a plain recall vs relation-expanded vs time-aware recall comparison;
- argument synthesis through an inert tool that only records the proposed
  `{name, arguments}`, scored against the gold arguments (parameter F1, BLEU-1,
  exact tool accuracy), with no-memory, full-history and oracle-evidence
  control arms under the same model. The oracle arm must pass only historical
  supporting text, never the gold tool name or argument values.

## Provenance

The pilot ran against a live AutoMem deployment in ten 40-task batches
(`--offset 0..360 step 40 --limit 40 --recall-k 5`). Every batch succeeded and
cleaned up its facts after each task. It used this harness's pre-port copy from
a private automation repo; the port changed module paths and default
locations only, not the storage, recall or scoring logic.

The harness writes one report per batch and does not aggregate across batches
or by complexity. The 400-task aggregate and the per-complexity table were
derived from the per-case records of those ten raw reports, which are not
committed.
