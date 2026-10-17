# MemTrace adapter plan (artifact-blocked)

[MemTrace: Probing What Final Accuracy Misses in Long-Term Memory](https://arxiv.org/abs/2606.17328) evaluates each knowledge point across memory age, question type, and evidence condition. Its question types are `current`, `earlier`, and `trajectory`; its evidence conditions are `present`, `missing`, and `false-premise`.

## Status

**Blocked on official benchmark artifacts.** As of 2026-10-02, the arXiv record exposes the paper, PDF, HTML, and TeX source, but no author code/data link. The authors' public publication page links MemTrace to the paper only. Targeted searches for the exact title and authors found no official repository, dataset, or downloadable benchmark package.

Do not create a synthetic replacement under the MemTrace name and do not report an AutoMem score. The paper describes its benchmark as derived from HaluMem-Medium; that source material does not substitute for MemTrace's knowledge-point annotations, age windows, evidence-condition variants, prompts, or gold abstention/false-premise labels.

## Planned adapter contract after release

Pin the official repository/data revision, checksum, license, and loader schema before adding `runners/memtrace/`. The loader must provide, for every official row:

- an isolated session history and typed knowledge point;
- its source session or memory-age boundary;
- question text and type (`current`, `earlier`, `trajectory`);
- evidence condition (`present`, `missing`, `false-premise`);
- gold answer / acceptable abstention or false-premise correction label; and
- the source-data revision identifier.

The future runner must reject a non-local AutoMem endpoint unless the caller passes an explicit override, must use a unique per-run tag, and must clean up its seeded records by default.

| MemTrace probe | AutoMem write/retrieval treatment | Required assertion |
| --- | --- | --- |
| Current state | Store the active fact with `t_valid`; on a replacement, write the new node with `supersedes_memory_id=<old-id>`. | Default current-only recall exposes the active node and suppresses the old node. |
| Earlier state | Preserve the historical node, including its `t_valid`/`t_invalid` boundary; use `current_only=false` for the historical evidence retrieval. | The answer path is explicitly labelled historical; it must not silently answer from the current node. |
| Trajectory | Preserve each state transition in chronological order. Use `INVALIDATED_BY` for correction and `EVOLVED_INTO` for ordinary evolution, always old -> new. | Retrieved evidence contains the required ordered transition(s), not merely the final state. |
| Present evidence | Issue `/recall` from the official question with the run tag and record the returned evidence IDs. | Score answer quality separately from whether the official support was retrieved. |
| Missing evidence | Do not seed the fact. | Require the official abstention outcome; retrieved distractors cannot count as support. |
| False premise | Seed only the official counterevidence; preserve the question's false premise unchanged. | Require correction or abstention according to the official label, and report support-retrieved vs. support-used separately. |

`INVALIDATED_BY` and `EVOLVED_INTO` must always point **old -> new**. A reversed lifecycle edge suppresses the new node in current-only recall and invalidates the probe.

## Smoke run after release

Once official artifacts are public, add a small official subset with at least one row for each question type and evidence condition. A smoke command should look like:

```bash
python3 runners/memtrace/run.py \
  --dataset /path/to/official/memtrace \
  --subset smoke \
  --endpoint http://localhost:8001 \
  --token test-token \
  --output data/results/memtrace/smoke
```

The emitted JSON and Markdown must identify the source revision/checksum, exact command, cold/matured label, per-cell row counts, retrieval-support rate, answer-support-use rate, and abstention/correction outcomes. It must state `not_scored` if an official answer-generation or scoring dependency cannot run.

## Acceptance criteria

- [ ] Official code/data is public and its revision, checksum, license, and schema are pinned.
- [ ] `runners/memtrace/` maps official rows through the lifecycle and temporal treatment above, with unit tests for edge direction, temporal mode, and non-local endpoint rejection.
- [ ] A real official smoke subset covers all three question types and all three evidence conditions.
- [ ] Smoke output contains the exact command and only measured results; no synthetic MemTrace score is reported.
- [ ] Repository tests and lint pass.

## Follow-up reading

- [A-TMA](https://arxiv.org/abs/2607.01935)
- [DynamicMem](https://arxiv.org/abs/2606.22877)
- [MEMPROBE](https://arxiv.org/abs/2606.24595)

Related AutoMem trackers remain separate: #50 StateMemBench (artifact-blocked), #48/#49 MemDelta, #31 ForgetEval, and #22/#23 Memora/FAMA.
