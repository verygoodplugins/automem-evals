# Memora predecessor classification (offline diagnostic)

This audit replays the pinned public Memora sessions through the adapter proposed
in [PR #88](https://github.com/verygoodplugins/automem-evals/pull/88), using an
in-process AutoMem protocol double. It records aggregate adapter bookkeeping and
same-normalized-key chronology. It does not score FAMA, exercise a real AutoMem
server, or demonstrate retrieval quality.

Across 27,614 sessions, 932 updates supplied an explicit renamed predecessor:
931 had an active predecessor; the remaining case had no predecessor and an
active destination, and was skipped. Separately, 323 stored updates did not
supersede an active predecessor and 163 deletes were skipped. All 486 events had
a prior delete for the same adapter-normalized key. Among 171 events with
explicit prior-session history, the recorded prior session matched that delete;
the other 315 were classified by chronological key replay.

These observations support a no-active-predecessor explanation, but do not
prove semantic identity or a valid server lifecycle: normalized keys can merge
distinct strings, an update after a delete may be a valid reintroduction, and
whole-conversation capture can contain facts beyond the tracked item. The public
receipt contains only aggregate counts and hashes, not conversation text,
questions, per-example identifiers, or user traces.

## Reproduction

Use a separately acquired local checkout of the public Memora dataset at
`a6493188efc836d6511ed5e4163fe3ba87da30ff`, and an eval checkout at PR #88
adapter commit `a99366cd21a29c2d7aabaf600884f07c9d8e4f5e`. No network,
AutoMem server, provider calls, or credentials are needed during the replay.
Both HEADs, the adapter source SHA-256, and the ordered dataset path/content
fingerprint are checked before the adapter is imported or sessions are run.
The output path must be new; an existing file is never overwritten.

```sh
python3 experiments/memora_predecessor_audit/classify.py \
  --dataset /path/to/pinned/memora \
  --adapter-worktree /path/to/pinned/automem-evals \
  --output /tmp/memora-predecessor-audit.json
cmp data/results/memora-predecessor-audit-20261111/aggregate.json \
  /tmp/memora-predecessor-audit.json
python3 -m unittest discover -s experiments/memora_predecessor_audit -p 'test_*.py' -v
```

The dataset fingerprint is
`7835f7a353a0cbb81f9db2539c554e8fd852ffd0d31191cc9298fad2b93c4736`;
the adapter source SHA-256 is
`40f264c1235b545bdd8d8e6cab14a612ea4c9fc7d87d8de7bf5ace73a8fae25a`.
The aggregate receipt SHA-256 is
`b8a4925ad41f07d23986bc44df2e9fcbd51434bf0aeab2bb1d2a579e9a0ff08d`.
