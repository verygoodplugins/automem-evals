# Session 2026-04-17 — evaluating the bare-tag 1M recall strategy

Scaffolding + first-run of the automem-evals framework, working against the local Docker stack (`automem/docker-compose.yml`).

## What we built

```
automem-evals/
├── rulesets/              # 12 pluggable recall configs (JSON)
│   ├── baseline_v1.json               — pre-today template
│   ├── bare_tag_1m_v2.json            — today's scheme
│   ├── bare_tag_1m_v3_expand.json     — today's scheme + expand_relations
│   └── iso_a..iso_j_*.json            — knob-isolation variants
├── scenarios/             # Query + expected-hit fixtures
│   ├── session_start_v1.json          — 10 Phase 1/2/3 scenarios
│   └── graph_expansion_v1.json        — 3 cross-boundary scenarios
├── scripts/
│   ├── generate_corpus.py             — 78-memory synthetic fixture
│   ├── seed_corpus.py                 — slow seed (real OpenAI embedding API)
│   ├── snapshot_corpus.py             — dump memory + Qdrant vector snapshot
│   ├── seed_from_snapshot.py          — fast reseed, no API calls ($0)
│   └── seed_associations.py           — adds 11 typed edges (within + cross-scope)
├── runners/
│   ├── compare_rulesets.py            — N×M matrix driver, markdown report output
│   └── client_side_expand.py          — prototype post-recall graph walker
└── data/
    ├── seed_memories/
    │   ├── corpus_v1.jsonl            — canonical seed
    │   ├── corpus_v1.embedded.jsonl   — with pre-computed 1024-dim vectors (1.1 MB)
    │   └── corpus_v1.manifest.json    — scenario → memory_id mapping
    └── results/
        ├── SUMMARY-20260417.md        — master report
        └── <timestamp>-comparison.md  — per-run detail reports
```

## What we learned

See `data/results/SUMMARY-20260417.md` for the full writeup. Three headline findings:

1. **bare-tag 1M (v2) is empirically optimal.** 10/10 scenarios fully recovered (24/24 Phase 2+3 hits) vs baseline's 3/10 (14/24).
2. **Individual knobs are underwhelming.** The v2 gain is emergent from **limit + time_query** compounding, not any single knob.
3. **`expand_relations` is blocked by tag gating.** Server-side expansion is a no-op whenever `tags: [<slug>]` is set. Client-side expansion (50-line walker over `.relations[]`) works — promising MCP-client feature.

## Reproducibility

```bash
# 1. Bring up server
cd /Users/jgarturo/Projects/OpenAI/automem && docker compose up -d

# 2. Seed from snapshot (fast, no API calls)
cd /Users/jgarturo/Projects/OpenAI/mcp-servers/automem-evals
python3 scripts/seed_from_snapshot.py
python3 scripts/seed_associations.py

# 3. Run any comparison
python3 runners/compare_rulesets.py --rulesets baseline_v1 bare_tag_1m_v2

# 4. Full knob isolation
python3 runners/compare_rulesets.py --rulesets iso_a_baseline_all_off iso_b_bump_limit iso_c_bump_time iso_d_add_decompose iso_e_drop_tag_gate iso_f_add_expand iso_g_all_new_v2 iso_h_v2_no_gate iso_i_v2_no_gate_expand iso_j_v2_expand

# 5. Client-side expansion prototype
python3 runners/client_side_expand.py --ruleset bare_tag_1m_v2 --scenarios graph_expansion_v1
```

## Natural next steps

- **Agent-matrix dimension** — this framework is recall-only today. Wrap runners so a "ruleset" can include an agent adapter (Claude Code CLI, Claude API, Codex API, Cursor, …). Reuse corpus + scenarios.
- **Negative controls** — current scenarios all have positive expected hits. Add scenarios where the correct answer is "nothing" to measure over-retrieval.
- **Propose client-expand as mcp-automem feature** — prototype validated, needs strength-weighted scoring + phase-awareness before shipping.
- **Server-side bug report** — file an issue on the AutoMem server repo about tag-gate blocking expansion.
