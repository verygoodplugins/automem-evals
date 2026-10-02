# MERIT AutoMem adapter

This adapter connects the official [MERIT benchmark](https://github.com/smshweta/merit-bench)
to a local AutoMem endpoint. It is experimental infrastructure, not an official
AutoMem benchmark claim.

## Pinned upstream artifact

- Repository: `https://github.com/smshweta/merit-bench`
- Revision: `293933d96b1d1849e1f20d1bb324def5de9ed33f`
- License: MIT
- Released artifacts: benchmark harness, deterministic mock mode, results, and
  full episode traces under the upstream `runs/` directory.

Clone the official release and verify the pin before running:

```bash
git clone https://github.com/smshweta/merit-bench.git ../merit-bench
git -C ../merit-bench checkout 293933d96b1d1849e1f20d1bb324def5de9ed33f
python3 -m unittest runners.test_merit_automem_adapter -v
python3 runners/merit/run_merit.py --merit-root ../merit-bench \
  --variant plain --maturation both -- --model mock --arcs 2 --episodes 5
```

The adapter assigns one generated `merit-run-*` tag to every memory and restricts
recall to that tag. It has two write policies:

| Variant | Write policy |
| --- | --- |
| `plain` | Stores every deterministic MERIT fact observation without lifecycle mutation. |
| `supersede-on-write` | On a changed `(entity, attribute)`, stores the new observation with `supersedes_memory_id=<old>` and `INVALIDATED_BY` (old → new). |

It records server-reported usage separately from request/response token estimates.
Unknown dollar cost remains `null`; it is never silently reported as zero.

## Maturation reporting

`--maturation both` writes a cold-ready / matured-blocked report. This is
intentional: the documented mature profile needs a narrative-clock
`/consolidate reference_time` API, which AutoMem does not currently expose. The
adapter will not relabel a cold run as mature. Once that API exists, run cold and
matured separately and publish both according to
[`docs/eval/maturation.md`](../../docs/eval/maturation.md).

## Scoring boundary

No AutoMem score is included here. MERIT's published figures are paper baselines,
not AutoMem results. A future run must preserve the official task checker, model,
seed, trace revision, cost record, isolated run tag, and cold/matured labels.
