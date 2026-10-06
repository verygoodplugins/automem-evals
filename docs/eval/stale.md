# track: STALE implicit-conflict benchmark (arXiv:2605.06527)

Candidate fingerprint: `opportunity:automem-graph-rag-research-scout`.
Feasibility checked on 2026-10-06. This is a publication-ready issue body for
`verygoodplugins/automem-evals`. Publication remains pending: this worker may
read external systems but may write only to the workspace. No issue/comment was
created, and no STALE issue URL exists for this handoff.

## Duplicate check

Searched open and closed issues with `gh issue list --state all` for `STALE`,
`2605.06527`, and `"implicit conflict"`. The latter two returned no matches;
STALE returned #14, #18, #24, #28, #50, #53, #57, none tracking this paper.
Recheck immediately before publication. Related work remains separate:

- [#14 BEAM knowledge_update](https://github.com/verygoodplugins/automem-evals/issues/14): explicit update ingestion and stale-value misses.
- [#22](https://github.com/verygoodplugins/automem-evals/issues/22) / [#23 Memora/FAMA](https://github.com/verygoodplugins/automem-evals/issues/23): forgetting-aware invalid-memory behavior.
- [#50 StateMemBench](https://github.com/verygoodplugins/automem-evals/issues/50): current/superseded outcomes and derived-state traps.
- [#57 A-TMA/LTP](https://github.com/verygoodplugins/automem-evals/issues/57): ghost-memory state views, blocked on official artifacts.

STALE's distinct target is implicit invalidation without explicit negation,
including downstream related facts. This is experimental evaluation planning;
official benchmark claims remain in `automem` under the
[repository boundary](https://github.com/verygoodplugins/automem-evals/blob/main/docs/REPO_BOUNDARY.md).

## Official artifacts: public and pinned

The [paper v1](https://arxiv.org/abs/2605.06527v1), submitted 2026-05-07,
links both releases in [Appendix G](https://arxiv.org/html/2605.06527v1).

| Artifact | Immutable pin and license | Status |
| --- | --- | --- |
| Official code/CUPMem | [icedreamc/STALE at `ea7d391103a151927cd29d2f01d87597a782bdcb`](https://github.com/icedreamc/STALE/tree/ea7d391103a151927cd29d2f01d87597a782bdcb); [MIT](https://github.com/icedreamc/STALE/blob/ea7d391103a151927cd29d2f01d87597a782bdcb/LICENSE) | Public; recursive tree inspected, not truncated. |
| Official dataset | [STALEproj/STALE at `617c51dc200b5ab09970834144c7e51c77959af0`](https://huggingface.co/datasets/STALEproj/STALE/tree/617c51dc200b5ab09970834144c7e51c77959af0); [CC BY 4.0](https://huggingface.co/datasets/STALEproj/STALE/blob/617c51dc200b5ab09970834144c7e51c77959af0/LICENSE) | Public, ungated, enabled; `T1_T2_400_FULL.json`. |
| Packaged LongMemEval distractors | [Included MIT notice](https://huggingface.co/datasets/STALEproj/STALE/blob/617c51dc200b5ab09970834144c7e51c77959af0/LongMemEval_LICENSE) | Preserve this notice and dataset attribution. |

The [pinned dataset tree API](https://huggingface.co/api/datasets/STALEproj/STALE/tree/617c51dc200b5ab09970834144c7e51c77959af0)
reports 305,908,212 bytes and LFS SHA-256
`5f3ec375179e20e2e94469e018189188f34e2e7e5f21cbecbd99fcfa648c1876`.
This is upstream metadata, not a locally computed full-file checksum. A 4 MiB
HTTP range returned 206 and a complete official record passing the pinned
dataset validator. The full corpus was not downloaded or independently counted.
Artifact availability is **not blocked**, unlike #57. A scored AutoMem run is
pending an adapter, configured reader/judge endpoints, and a real smoke run.
No AutoMem score is reported.

## Loader/scorer inspection

- [Target runner](https://github.com/icedreamc/STALE/blob/ea7d391103a151927cd29d2f01d87597a782bdcb/STALE/Evaluation/run_target_model.py) loads a JSON list, renders `haystack_session` with aligned `timestamps`, submits three independent probes, and emits `uid` plus `target_model_responses.dim1_response`, `dim2_response`, `dim3_response`. Optional trimming protects `relevant_session_index`; record seed/removals when used. Full-context runs omit `--enable-trim`.
- [Dataset card](https://huggingface.co/datasets/STALEproj/STALE/blob/617c51dc200b5ab09970834144c7e51c77959af0/README.md) documents `uid`, `M_old`, `M_new`, `explanation`, `probing_queries`, `haystack_session`, `relevant_session_index`, `timestamps`, `type`. The inspected first T1 record has 50 sessions/timestamps and evidence indices `[13, 33]`.
- [Scorer](https://github.com/icedreamc/STALE/blob/ea7d391103a151927cd29d2f01d87597a782bdcb/STALE/Evaluation/full_eval_performance.py) accepts a list or `{ "data": [...] }`, validates inputs, and joins by UID. One judge call assesses all three answers against old/new observations and hidden explanation using the [official rubric](https://github.com/icedreamc/STALE/blob/ea7d391103a151927cd29d2f01d87597a782bdcb/STALE/Evaluation/judge_prompts.py). Outputs include dimension pass/reasoning, correct/total, usage, timing, and details. Keep hidden logic exclusively in scoring.
- `--conflict-type` is a **report label, not a filter**: split T1/T2 first. Unmatched answer UIDs are skipped, missing answers reduce the denominator, duplicate UIDs overwrite lookup entries, and judge errors become three failures. Require unique IDs, exact answer/data coverage, JSON boolean verdicts, and a separate judge-error count before accepting a score; preserve the official scorer.
- [CUPMem sample runner](https://github.com/icedreamc/STALE/blob/ea7d391103a151927cd29d2f01d87597a782bdcb/cup_mem/core/sample_runner.py) resets per sample and supports full/evidence-only replay. Its [update resolver](https://github.com/icedreamc/STALE/blob/ea7d391103a151927cd29d2f01d87597a782bdcb/cup_mem/write/update_resolver.py) includes `REPLACE` and `INDIRECT_INVALIDATE`; its [stale linker](https://github.com/icedreamc/STALE/blob/ea7d391103a151927cd29d2f01d87597a782bdcb/cup_mem/write/stale_linker.py) searches across tracks/buckets. Evidence-only replay is a diagnostic, not a full-haystack result.

## Lifecycle mapping and gap

| Need | Proposed AutoMem treatment | Required assertion |
| --- | --- | --- |
| Inferred replacement | Write replacement with `supersedes_memory_id=<old-id>` after detecting the change from dialogue. | Old `t_invalid` set; history retained. |
| Correction provenance | `INVALIDATED_BY`, **old -> new**. | Inspect actual stored direction. |
| State evolution | `EVOLVED_INTO`, **old -> new**, where appropriate. | Current recall suppresses stale state, retaining audit history. |
| Current state | Explicit `current_only=true`, run isolation, narrative query boundary. | Verify returned IDs, stale/future leakage; historical `current_only=false` is a separate diagnostic. |
| Indirect related-fact invalidation | Re-evaluate affected candidates and create justified lifecycle links/invalidation with causal provenance. | Edge coverage/precision and unrelated-fact preservation; never invalidate all `RELATED` neighbors indiscriminately. |

**Key gap: write-time edge quality and propagation.** `RELATED` identifies
candidates, not proof of invalidation. An upstream implicit change can retire
downstream memories without explicit negation or a matching attribute.
`current_only` can suppress correctly marked records; it cannot infer missing
lifecycle edges. Do not claim automatic cascading invalidation already exists.
If no replacement is known, retain a justified invalidation/unknown state rather
than inventing a fact. CUPMem motivates write-time consolidation and
propagation-aware search; AutoMem support needs separate product verification.

## Adapter plan

1. Add experimental `runners/stale/` after feasibility review. Pin code/data,
   checksum/notices, model IDs, prompts, budgets, retries, seeds. Load the public
   release directly; never generate a STALE-like substitute.
2. Validate UIDs, T1/T2, probes, timestamps, evidence bounds, and turn schemas.
   Smoke-test real official cases of both types. Isolate each case/variant with
   a unique tag against a local-only AutoMem endpoint.
3. Replay full dialogue chronologically with narrative timestamps/provenance.
   Hidden explanations, old/new gold annotations, and evidence indices must
   not guide autonomous writes or candidate selection; reserve them for scoring
   and diagnostics.
4. Compare `plain`, `inferred-supersession`, and `propagation-aware` at matched
   reader/retrieval budgets. Re-evaluate affected related facts with evidence;
   trace lifecycle decisions and unaffected-fact preservation. Any gold-linked
   upper bound is a separate oracle diagnostic, excluded from autonomous scores.
5. Ingest once, freeze the bank, ask SR/PR/IPA independently, and never write
   answers back. Emit the official answer envelope and use the pinned scorer.
   Trace bank maintenance, retrieval/stale leakage, and final-answer behavior.
6. Report T1/T2 x SR/PR/IPA plus overall correct/total, coverage, errors, usage,
   costs, IDs/edges/validity, exclusions. Follow the
   [maturation contract](https://github.com/verygoodplugins/automem-evals/blob/main/docs/eval/maturation.md)
   with separate cold/matured results; unavailable narrative-clock consolidation
   means `matured: blocked`, never a relabelled cold result.

## Exact upstream commands (source-verified, not executed)

These run the **upstream full-context reader and scorer**, not AutoMem.
Prerequisites: Python 3.10+, Git/curl, upstream requirements, and configured
reader/judge endpoints. Set provider credentials privately in the environment
or `STALE/.env`. `GEMINI_API_KEY`/`GEMINI_BASE_URL` configure a Gemini
OpenAI-compatible endpoint through upstream's provider-prefix client. The
model labels below follow the pinned `.env.example`; endpoint/model availability
was not execution-verified. No inference calls were made here.

```bash
git clone https://github.com/icedreamc/STALE.git stale-upstream
cd stale-upstream
git checkout ea7d391103a151927cd29d2f01d87597a782bdcb
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r STALE/requirements.txt
mkdir -p STALE/outputs
curl --fail --location \
  https://huggingface.co/datasets/STALEproj/STALE/resolve/617c51dc200b5ab09970834144c7e51c77959af0/T1_T2_400_FULL.json \
  --output STALE/outputs/T1_T2_400_FULL.json
python - <<'PY'
import hashlib, json
from pathlib import Path
path = Path('STALE/outputs/T1_T2_400_FULL.json')
assert hashlib.sha256(path.read_bytes()).hexdigest() == '5f3ec375179e20e2e94469e018189188f34e2e7e5f21cbecbd99fcfa648c1876'
records = json.loads(path.read_text())
assert len(records) == 400 and len({r['uid'] for r in records}) == 400
assert {r['type'] for r in records} == {'T1', 'T2'}
for kind in ('T1', 'T2'):
    subset = [r for r in records if r['type'] == kind]
    assert subset
    Path(f'STALE/outputs/{kind}_official.json').write_text(json.dumps(subset))
PY
cd STALE
for kind in T1 T2; do
  python Evaluation/run_target_model.py \
    --icds-path "outputs/${kind}_official.json" \
    --output-path "outputs/${kind}_answers.json" \
    --model gemini-3.1-flash-lite-preview --provider GEMINI --concurrency 1
  python Evaluation/full_eval_performance.py \
    --answers-path "outputs/${kind}_answers.json" \
    --dataset-path "outputs/${kind}_official.json" \
    --output-path "outputs/${kind}_eval.json" \
    --conflict-type "$kind" --model-method upstream-full-context \
    --judge-model gemini-3.1-flash-lite-preview --judge-provider GEMINI \
    --concurrency 1
done
```

No exact **AutoMem** command exists yet: the adapter is proposed, not implemented.
The commands above have not been execution-verified with models/endpoints.

## Paper baselines and acceptance

The paper describes 400 expert-validated scenarios / 1,200 queries, up to 150K
tokens, State Resolution, Premise Resistance, and Implicit Policy Adaptation.
Its strongest evaluated standalone model achieves 55.2% overall; CUPMem is the
write-time consolidation/propagation-aware prototype. **55.2% is a paper
baseline, never an AutoMem score.**
[Source: paper abstract/manuscript](https://arxiv.org/abs/2605.06527v1).

- [x] Search open/closed issues; distinguish adjacent trackers.
- [x] Pin public code/data and licenses; inspect loader/scorer.
- [x] Map lifecycle primitives and implicit propagation gap; propose adapter.
- [x] Supply source-verified upstream commands and real-record schema evidence.
- [ ] Publish this issue body and record its actual issue URL.
- [ ] Implement and verify an adapter in a separate authorized pass.
- [ ] Run a real official smoke subset before any AutoMem score.
