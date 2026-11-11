# Precision threshold probe

This offline analysis reads the two strict targeted-run JSON receipts and
writes only aggregate counts to a **new** output path. It validates the pinned
baseline/candidate revisions, fixture hash, row pairing, counts and finite
top scores. It does not call AutoMem, load embeddings or access a network.

```sh
python3 experiments/precision_threshold_probe/sweep.py \
  --baseline /tmp/automem-eval-resume-20261111/final-targeted-4431d20/baseline.json \
  --candidate /tmp/automem-eval-resume-20261111/final-targeted-4431d20/candidate.json \
  --output /tmp/precision-threshold-probe-aggregate.json
cmp /tmp/precision-threshold-probe-aggregate.json \
  data/results/precision-threshold-probe-20261111/aggregate.json
python3 -m unittest discover -s experiments/precision_threshold_probe -p 'test_*.py' -v
```

The local inputs contain per-question experiment results and must not be
committed or published. Their SHA-256 hashes are recorded in the aggregate.
They can be recreated using the strict runner and the synthetic fixture; a fresh
run may differ byte-for-byte because memory IDs and timing change. The actual
0.4 server rows are observed; other thresholds are an all-or-none client gate
projected onto saved zero-floor lists. The aggregate is a research diagnostic,
not a valid untouched holdout, server `min_score` sweep, agent-success measure
or recommended production threshold. Retained target@5 counts are upper bounds
for item-by-item filtering on those same lists; a fresh server request can
produce different candidates, so these do not bound its actual outcome.
