#!/usr/bin/env python3
"""
Generate corpus v2 — parameterized, ~400-memory fixture for scaled recall evals.

v1 was a hand-authored 78-memory fixture. v2 uses templates + varied fill-ins
to produce realistic breadth across 6 projects, 50 preferences, and ~30 noise
memories without becoming obviously repetitive.

Design goals:
  - 6 projects (2 active, 2 mature, 2 sunsetting) — exercises tag gate in
    varied conditions. One slug (`video`) is deliberately collision-prone
    to enable slug-collision experiments.
  - 50 preferences (up from 20) so limit=20 becomes a real quality floor.
  - 300 project memories (50 per project) across decisions / bugs / patterns /
    milestones / context / discussion.
  - Dense association graph designed as intra-project chains
    (decision → bug → fix → milestone) plus cross-project bridges.
  - Multi-hop paths (A→B→C, A→B→D) for future multi-hop expansion tests.
  - Age distribution: 50% 0-30d, 25% 31-60d, 15% 61-90d, 10% 91+d.

Writes: data/seed_memories/corpus_v2.jsonl
Scenario hits are assigned per memory via metadata.hits_scenarios; scoring is
manifest-based (see seed_corpus_v2.py / runner).
"""

from __future__ import annotations

import json
import pathlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "seed_memories" / "corpus_v2.jsonl"
NOW = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
RNG = random.Random(42)


def iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago, hours=RNG.randint(0, 23))).isoformat().replace("+00:00", "Z")


@dataclass
class ProjectSpec:
    slug: str
    status: str  # "active" | "mature" | "sunsetting"
    lang: str
    description: str
    age_bias_days: int  # Higher = older memories. Shifts the age distribution.


PROJECTS = [
    ProjectSpec("tensor-pipeline", "active", "typescript",
                "ML inference pipeline with vector indexing and async workers", 0),
    ProjectSpec("payment-service", "active", "go",
                "Payment processor with idempotency and compliance logging", 0),
    ProjectSpec("dashboard-app", "mature", "typescript",
                "Admin dashboard with RSC + data grids + role-based access", 15),
    ProjectSpec("search-engine", "mature", "python",
                "Full-text + semantic search backend with Elasticsearch", 20),
    ProjectSpec("old-service", "sunsetting", "python",
                "Pre-refactor monolith being replaced by tensor-pipeline", 60),
    ProjectSpec("video", "active", "typescript",
                "Video transcoding + CDN service (slug deliberately collision-prone)", 10),
]


# Age sampler: draws days_ago biased by project status
def sample_age(project: ProjectSpec) -> int:
    # Base buckets
    buckets = [
        (0, 30, 0.50),
        (31, 60, 0.25),
        (61, 90, 0.15),
        (91, 180, 0.10),
    ]
    # Shift probabilities for sunsetting projects (more old memories)
    if project.status == "sunsetting":
        buckets = [
            (0, 30, 0.15),
            (31, 60, 0.20),
            (61, 90, 0.30),
            (91, 180, 0.35),
        ]
    elif project.status == "mature":
        buckets = [
            (0, 30, 0.35),
            (31, 60, 0.30),
            (61, 90, 0.20),
            (91, 180, 0.15),
        ]
    r = RNG.random()
    cum = 0.0
    for lo, hi, p in buckets:
        cum += p
        if r <= cum:
            return RNG.randint(lo, hi) + project.age_bias_days
    return 30 + project.age_bias_days


def mem(
    content: str,
    tags: list[str],
    mem_type: str,
    importance: float,
    days_ago: int,
    hits: list[str] | None = None,
    extra_meta: dict | None = None,
) -> dict:
    md = {"synthetic": True, "corpus_version": 2, "hits_scenarios": hits or []}
    if extra_meta:
        md.update(extra_meta)
    return {
        "content": content,
        "tags": sorted(set(tags)),
        "type": mem_type,
        "importance": importance,
        "timestamp": iso(max(0, days_ago)),
        "metadata": md,
    }


corpus: list[dict] = []

# ────────────────────────────────────────────────────────────────────────────
# Preferences (50) — 30 domain-scoped + 20 general. Bare `preference` tag.
# ────────────────────────────────────────────────────────────────────────────

PREF_GROUPS: list[tuple[str, list[tuple[str, float, int]]]] = [
    ("git-workflow", [
        ("Use Conventional Commits for all PRs. Titles must follow feat:/fix:/chore:/docs:/refactor:/test:. Release-Please depends on it.", 0.95, 3),
        ("Never merge PRs yourself. Jack handles all merges. Learned after accidentally merging 3 PRs without review.", 0.95, 6),
        ("Squash-merge is the default; the PR title becomes the merge commit. Keep titles Conventional so Release-Please can parse them.", 0.85, 12),
        ("Commit messages explain WHY, not WHAT. The diff already shows what.", 0.85, 20),
        ("Branch names follow pattern `<type>/<short-description>`. feat/oauth-pkce, fix/rate-limiter, chore/deps.", 0.75, 35),
        ("Rebase feature branches on main before requesting review. Keep history linear.", 0.80, 50),
    ]),
    ("code-style", [
        ("Default to writing no code comments. Only add when WHY is non-obvious — hidden constraint, subtle invariant, workaround.", 0.85, 10),
        ("Don't add error handling or fallbacks for scenarios that can't happen. Validate only at system boundaries.", 0.85, 14),
        ("Three similar lines beat a premature abstraction. Don't design for hypothetical future requirements.", 0.80, 25),
        ("Prefer editing existing files to creating new ones. Never create docs unless explicitly requested.", 0.85, 30),
        ("Avoid backwards-compat hacks (rename _vars, re-export types, '// removed' comments). Delete dead code completely.", 0.85, 45),
        ("TypeScript strict mode on all new projects. No implicit any.", 0.75, 55),
    ]),
    ("testing", [
        ("Integration tests hit a real database, not mocks. Got burned when mocked tests passed but prod migration failed.", 0.90, 8),
        ("Test pyramid: 70% unit, 20% integration, 10% e2e. Don't over-invest in e2e.", 0.80, 40),
        ("Unit tests run in <1s each. Anything slower is a smell — move it to integration tier.", 0.80, 22),
        ("Every bug fix ships with a regression test. No exceptions.", 0.85, 18),
        ("Feature-flag new behavior; test both legs of the flag before merging.", 0.80, 60),
    ]),
    ("deployment", [
        ("Always deploy through staging first. No 'quick fix to prod'.", 0.95, 45),
        ("Feature flags for anything user-visible. Rollback via flag, not hotfix.", 0.85, 55),
        ("Prod deploys only during business hours. Never on Fridays unless security incident.", 0.85, 75),
        ("Database migrations are forward-compatible for one release. Rollback window = current prod version.", 0.85, 90),
    ]),
    ("collaboration", [
        ("Ask clarifying questions before jumping into a substantive rewrite. Bias toward understanding over speed.", 0.85, 18),
        ("Keep responses terse. No trailing 'here's what I did' summaries — the diff shows that.", 0.85, 28),
        ("When proposing a plan, include deltas from existing code, not a full rewrite.", 0.80, 35),
        ("Use AskUserQuestion for design-sensitive decisions. Don't assume.", 0.80, 42),
    ]),
    ("automem", [
        ("Jack does not want markdown file-based memory. Use AutoMem MCP tools exclusively on this machine.", 0.95, 4),
        ("AutoMem tags are a hard gate — use bare tags, not namespace-prefixed. Corpus convention: 'preference', 'mcp-automem', 'typescript', not 'project/mcp-automem'.", 0.95, 1),
        ("Every store_memory must set type (Decision/Pattern/Preference/Style/Habit/Insight/Context) and include project slug tag.", 0.90, 5),
        ("After storing user corrections, find and link old memory via INVALIDATED_BY (strength 0.9).", 0.85, 11),
        ("Prefer update_memory + low importance (0.1) + metadata.deprecated over delete_memory.", 0.80, 25),
    ]),
    ("tooling", [
        ("Use pnpm workspaces for monorepos, not lerna.", 0.75, 110),
        ("ESLint + Prettier on save; no unsaved-lint commits.", 0.70, 50),
        ("Bun for scripts, Node for production. Speed vs stability tradeoff accepted.", 0.70, 70),
        ("Use Vitest, not Jest. 3x faster, compatible API.", 0.75, 80),
    ]),
    ("security", [
        ("Secrets live in 1Password vault, never in .env.local committed anywhere.", 0.95, 15),
        ("Rotate Railway tokens quarterly. Calendar-scheduled.", 0.85, 100),
        ("Sensitive PII fields (emails, phones) must use the field-level encryption helper.", 0.90, 65),
    ]),
    ("review", [
        ("Every PR touching auth requires a second reviewer explicitly.", 0.90, 50),
        ("Changes to infrastructure config (Terraform, k8s) need a Slack heads-up before merge.", 0.85, 85),
    ]),
]

pref_count = 0
for scope, items in PREF_GROUPS:
    for content, importance, days in items:
        corpus.append(mem(
            content, ["preference", scope], "Preference", importance, days,
            hits=[f"PREF-{scope.upper().replace('-', '_')}"],
        ))
        pref_count += 1

# Fill to 50 with cross-cutting preferences
extra_prefs = [
    ("On-call rotation is 1 week, primary + secondary. Escalation runbook in /docs/oncall.md.", 0.80, 40, "oncall"),
    ("Release cadence: every 2 weeks for mature services, weekly for active.", 0.75, 55, "release"),
    ("Post-mortem culture: blameless, written within 5 business days, template in /docs/post-mortem.md.", 0.85, 100, "culture"),
    ("Meeting notes go in the shared Notion; decisions get a memory with Decision type.", 0.75, 70, "process"),
]
for content, imp, days, scope in extra_prefs:
    corpus.append(mem(content, ["preference", scope], "Preference", imp, days, hits=[f"PREF-{scope.upper()}"]))
    pref_count += 1

while pref_count < 50:
    # Filler prefs (lower signal)
    filler = [
        ("Console.log in commits is a warning, not an error. Reviewer judgment call.", 0.55, 60),
        ("Docker tags always include the git SHA, never 'latest' in CI.", 0.70, 90),
        ("Slack notifications should have a direct link to the relevant log line or dashboard.", 0.60, 30),
        ("Code review turnaround target: 4 business hours for <200 lines, 1 business day for larger.", 0.65, 45),
        ("Prefer named exports over default exports in TypeScript. Easier to refactor.", 0.60, 55),
    ]
    content, imp, days = filler[pref_count % len(filler)]
    corpus.append(mem(content, ["preference", "minor"], "Preference", imp, days + pref_count, hits=["PREF-MINOR"]))
    pref_count += 1

# ────────────────────────────────────────────────────────────────────────────
# Project memories — 50 per project, templated
# ────────────────────────────────────────────────────────────────────────────

# Per-project content banks. Each project gets 50 memories distributed across
# types. scenario_id follows {SLUG_UPPER}-{THEME} pattern.

PROJECT_MEMORIES: dict[str, dict[str, list[tuple[str, float, str, list[str] | None]]]] = {
    "tensor-pipeline": {
        "decisions": [
            ("Decided to use Postgres pgvector for tensor-pipeline embeddings instead of Pinecone. Cheaper self-host, acceptable recall at scale.", 0.90, "Decision", ["TP-VECTORSTORE"]),
            ("Decided to split tensor-pipeline ingest worker from API pod. Dedicated node pool isolates GPU jobs.", 0.90, "Decision", ["TP-ARCH"]),
            ("Decided to adopt OAuth2 with PKCE for tensor-pipeline public auth. Previously used bespoke JWTs.", 0.95, "Decision", ["TP-AUTH"]),
            ("Decided to cap tensor-pipeline retry budget at 3 attempts with exponential backoff.", 0.85, "Decision", ["TP-RETRY"]),
            ("Decided to migrate tensor-pipeline from Express to Fastify. 3x throughput on workload.", 0.90, "Decision", ["TP-FASTIFY"]),
            ("Decided to adopt voyage-4 embeddings for tensor-pipeline vector quality.", 0.85, "Decision", ["TP-EMBED"]),
            ("Decided tensor-pipeline writes will go through a queue, not direct Postgres. Backpressure protection.", 0.85, "Decision", ["TP-QUEUE"]),
            ("Decided to drop tensor-pipeline Python SDK in favor of REST-only. Reduced maintenance surface.", 0.80, "Decision", ["TP-SDK"]),
        ],
        "bugs": [
            ("Fixed tensor-pipeline rate-limiter timeout. Root cause: Redis SCAN over full keyspace per request. Solution: scoped key prefix + pattern scan.", 0.80, "Insight", ["TP-RATE", "DEBUG-RATE"]),
            ("Fixed tensor-pipeline OAuth token rotation. Old tokens weren't invalidated on user-initiated logout.", 0.80, "Insight", ["TP-AUTH", "DEBUG-AUTH"]),
            ("Fixed tensor-pipeline memory leak in ingest worker. pg pool wasn't releasing connections on error paths.", 0.80, "Insight", ["TP-MEM", "DEBUG-MEM"]),
            ("Fixed tensor-pipeline CI flakiness. Port 5432 race condition; solved with per-suite Docker network isolation.", 0.75, "Insight", ["TP-CI", "DEBUG-CI"]),
            ("Fixed tensor-pipeline deploy hang. Railway spun up 2 instances before old drained; added SIGTERM handler.", 0.85, "Insight", ["TP-DEPLOY"]),
            ("Fixed tensor-pipeline queue processing order. FIFO guarantees broken by parallel workers; added job ordering by sequence_id.", 0.80, "Insight", ["TP-QUEUE", "DEBUG-ORDER"]),
            ("Fixed tensor-pipeline stale cache on schema migration. Migration now invalidates query cache keys.", 0.75, "Insight", ["TP-CACHE"]),
        ],
        "patterns": [
            ("Pattern: tensor-pipeline uses a request-scoped context.Context at router boundary. All downstream calls accept ctx as first arg.", 0.80, "Pattern", ["TP-CTX", "PATTERN-CTX"]),
            ("Pattern: tensor-pipeline DB migrations are gated by a pre-flight SELECT to detect schema drift.", 0.80, "Pattern", ["TP-MIGRATE"]),
            ("Pattern: tensor-pipeline feature flags via LaunchDarkly. New features bake for 1 week before GA.", 0.75, "Pattern", ["TP-FLAGS", "PATTERN-FLAGS"]),
            ("Pattern: tensor-pipeline uses OpenTelemetry spans with correlation IDs propagated via W3C traceparent.", 0.80, "Pattern", ["TP-OBSERVABILITY", "PATTERN-OTEL"]),
            ("Pattern: tensor-pipeline shuts down gracefully: drain queue, close pg pool, deregister from load balancer.", 0.75, "Pattern", ["TP-SHUTDOWN"]),
        ],
        "milestones": [
            ("Milestone: tensor-pipeline v2.3.0 shipped with new OAuth flow. Feature-flagged to 5% for 24h.", 0.70, "Context", ["TP-AUTH"]),
            ("Milestone: onboarded new ingest partner schema into tensor-pipeline. Added fuzz tests for malformed input.", 0.60, "Context", []),
            ("Milestone: removed legacy tensor-pipeline v1 API. 30-day deprecation notice expired.", 0.70, "Context", []),
            ("Milestone: tensor-pipeline observability sweep. Added OTel tracing at every external HTTP boundary.", 0.65, "Context", ["TP-OBSERVABILITY"]),
            ("Milestone: tensor-pipeline retry budget shipped. Saw P99 latency drop 15% in first week.", 0.70, "Context", ["TP-RETRY"]),
            ("Milestone: tensor-pipeline CI isolation fix deployed. Flake rate dropped from 8% to 0.3%.", 0.65, "Context", ["TP-CI"]),
            ("Milestone: tensor-pipeline Fastify migration complete. All endpoints ported; 2.8x p50 improvement.", 0.75, "Context", ["TP-FASTIFY"]),
            ("Milestone: tensor-pipeline queue backend swapped from BullMQ to a simpler Redis streams wrapper.", 0.65, "Context", ["TP-QUEUE"]),
        ],
        "context": [
            ("tensor-pipeline production runs on Railway in us-east-1. 2 API pods, 1 worker; scales to 4 on queue depth >1000.", 0.80, "Context", ["TP-DEPLOY"]),
            ("tensor-pipeline staging is single-pod Railway at tp-staging.up.railway.app. Weekly prod snapshot seed.", 0.75, "Context", ["TP-DEPLOY"]),
            ("tensor-pipeline log retention: 30 days in Grafana Loki, 1 year archived to S3.", 0.65, "Context", []),
            ("tensor-pipeline dashboard: grafana.internal/d/tp-health. Primary gauge: queue depth and p99 latency.", 0.70, "Context", ["TP-OBSERVABILITY"]),
        ],
    },
    "payment-service": {
        "decisions": [
            ("Decided payment-service will use Stripe as primary PSP and Adyen as failover. Routing logic in a small Go service.", 0.95, "Decision", ["PS-PSP"]),
            ("Decided payment-service writes are idempotent via client-provided request IDs stored with TTL 48h.", 0.90, "Decision", ["PS-IDEMPOTENT"]),
            ("Decided payment-service will not store PAN; tokenize at capture via Stripe Radar.", 0.95, "Decision", ["PS-PCI"]),
            ("Decided payment-service audit log uses append-only ledger table, no updates or deletes.", 0.90, "Decision", ["PS-AUDIT"]),
            ("Decided payment-service retries failed charges at 1h/6h/24h with circuit breaker on third failure.", 0.85, "Decision", ["PS-RETRY"]),
            ("Decided payment-service keeps PII encryption keys in AWS KMS, one key per tenant.", 0.90, "Decision", ["PS-KMS"]),
        ],
        "bugs": [
            ("Fixed payment-service idempotency collision: two concurrent requests with same client ID got different charges. Solution: SELECT FOR UPDATE on the idempotency table.", 0.85, "Insight", ["PS-IDEMPOTENT", "DEBUG-LOCK"]),
            ("Fixed payment-service double-charge on Stripe webhook retries. Webhooks now deduped by event.id in-memory with 24h TTL.", 0.85, "Insight", ["PS-WEBHOOK", "DEBUG-DOUBLE"]),
            ("Fixed payment-service currency-conversion rounding. Was truncating; now uses banker's rounding per ISO 4217.", 0.75, "Insight", ["PS-MONEY"]),
            ("Fixed payment-service timezone bug in daily settlement. CET/UTC offset caused 23hr and 25hr days.", 0.75, "Insight", ["PS-SETTLEMENT", "DEBUG-TZ"]),
            ("Fixed payment-service rate limit on Adyen API. Was hitting 100 rps cap; now respects 429 + Retry-After header.", 0.80, "Insight", ["PS-RATE", "DEBUG-RATE"]),
            ("Fixed payment-service TLS renewal. cert-manager was scheduling renewals too close to expiry; bumped buffer to 30 days.", 0.80, "Insight", ["PS-TLS"]),
        ],
        "patterns": [
            ("Pattern: payment-service uses a state machine for charge lifecycle: pending → authorized → captured → settled. Transitions are audited.", 0.85, "Pattern", ["PS-FSM"]),
            ("Pattern: payment-service responses include request_id echo + server_id for tracing.", 0.75, "Pattern", ["PS-TRACING"]),
            ("Pattern: payment-service money amounts are always int64 cents, never float. Currency is ISO 4217 3-letter code.", 0.80, "Pattern", ["PS-MONEY"]),
            ("Pattern: payment-service domain errors extend PaymentError. HTTP layer maps to status codes centrally.", 0.75, "Pattern", ["PS-ERRORS"]),
        ],
        "milestones": [
            ("Milestone: payment-service v1.0 shipped to 100% with Stripe as primary.", 0.75, "Context", ["PS-PSP"]),
            ("Milestone: payment-service Adyen failover tested in staging with chaos injection.", 0.65, "Context", ["PS-PSP"]),
            ("Milestone: payment-service PCI Q2 audit passed. Zero findings.", 0.85, "Context", ["PS-PCI"]),
            ("Milestone: payment-service idempotency collision bug fix shipped. Customer refund issued.", 0.80, "Context", ["PS-IDEMPOTENT"]),
            ("Milestone: payment-service added multi-currency support for EUR, GBP, CAD.", 0.70, "Context", ["PS-MONEY"]),
            ("Milestone: payment-service tokenization of legacy accounts complete.", 0.75, "Context", ["PS-PCI"]),
            ("Milestone: payment-service migrated its DB from RDS to Aurora Serverless v2.", 0.70, "Context", []),
        ],
        "context": [
            ("payment-service runs on AWS ECS Fargate, us-east-1 + us-west-2 active-active.", 0.80, "Context", []),
            ("payment-service staging env at pay-stg.internal. Sanitized prod data refreshed nightly.", 0.70, "Context", []),
            ("payment-service uses Datadog for metrics + APM, PagerDuty for alerts.", 0.65, "Context", []),
            ("payment-service on-call runbook: /docs/oncall/payment.md. Covers PSP outage, DB failover, KMS key rotation.", 0.75, "Context", []),
        ],
    },
    "dashboard-app": {
        "decisions": [
            ("Decided to adopt React Server Components in dashboard-app. Lower initial render cost; slower dev HMR.", 0.85, "Decision", ["DA-RSC"]),
            ("Decided dashboard-app uses SWR over React Query for data fetching. Simpler API.", 0.80, "Decision", ["DA-DATA"]),
            ("Decided dashboard-app charts use Recharts (replaced Chart.js). Native React integration.", 0.80, "Decision", ["DA-CHARTS"]),
            ("Decided dashboard-app role-based access is server-side. Never trust client role claims.", 0.90, "Decision", ["DA-RBAC"]),
            ("Decided dashboard-app uses Zustand for global state, not Redux. Smaller footprint.", 0.75, "Decision", ["DA-STATE"]),
        ],
        "bugs": [
            ("Fixed dashboard-app hydration mismatch on dates. UTC server vs local client; fixed with Intl.DateTimeFormat.", 0.80, "Insight", ["DA-HYDRATION", "DEBUG-HYDRATE"]),
            ("Fixed dashboard-app infinite re-render on filter change. useEffect dep was a new object literal per render.", 0.80, "Insight", ["DA-REACT", "DEBUG-LOOP"]),
            ("Fixed dashboard-app N+1 query on users-with-teams view. Added JOIN with aggregation.", 0.75, "Insight", ["DA-PERF"]),
            ("Fixed dashboard-app session expiry race. Multiple tabs; solved with BroadcastChannel sync.", 0.75, "Insight", ["DA-SESSION", "DEBUG-AUTH"]),
            ("Fixed dashboard-app PDF export cutoff. @page CSS rule needed explicit size directive.", 0.60, "Insight", ["DA-EXPORT"]),
        ],
        "patterns": [
            ("Pattern: dashboard-app components follow feature-folder structure with colocated hooks/types/tests.", 0.75, "Pattern", ["DA-STRUCT", "DA-PATTERN"]),
            ("Pattern: dashboard-app uses discriminated unions for async state (loading | success | error). No three-boolean anti-pattern.", 0.80, "Pattern", ["DA-ASYNC", "DA-PATTERN"]),
            ("Pattern: dashboard-app data grids use virtualization via react-window. Rows only render in viewport.", 0.75, "Pattern", ["DA-PERF"]),
            ("Pattern: dashboard-app keyboard shortcuts via a global provider. Components register via useShortcut hook.", 0.70, "Pattern", ["DA-KEYBOARD"]),
        ],
        "milestones": [
            ("Milestone: dashboard-app v4.0 shipped with Server Components. All pages migrated except admin.", 0.75, "Context", ["DA-RSC"]),
            ("Milestone: dashboard-app accessibility audit complete. Fixed contrast, 3 keyboard traps, added aria-labels.", 0.65, "Context", []),
            ("Milestone: dashboard-app bundle size reduced 30% (moment.js → date-fns).", 0.60, "Context", []),
            ("Milestone: dashboard-app RBAC refactor shipped. Admin role check now server-authoritative.", 0.80, "Context", ["DA-RBAC"]),
            ("Milestone: dashboard-app charts migrated from Chart.js to Recharts. No visual regressions.", 0.60, "Context", ["DA-CHARTS"]),
        ],
        "context": [
            ("dashboard-app deploys to Vercel at app.example.com. Preview per PR; staging is main branch preview.", 0.75, "Context", ["DA-DEPLOY"]),
            ("dashboard-app uses Playwright for e2e on preview deploys. ~3 min per run, triggered via GHA.", 0.70, "Context", ["DA-CI"]),
            ("dashboard-app session secret rotates every 90 days via GHA workflow.", 0.70, "Context", []),
            ("dashboard-app internal URL: admin.internal.example.com (VPN-only).", 0.65, "Context", []),
        ],
    },
    "search-engine": {
        "decisions": [
            ("Decided search-engine uses Elasticsearch 8.x with dense_vector fields for hybrid keyword + semantic.", 0.90, "Decision", ["SE-ES", "SE-HYBRID"]),
            ("Decided search-engine keeps a reverse-proxy layer (nginx) for rate limiting and regional routing.", 0.80, "Decision", ["SE-ARCH"]),
            ("Decided search-engine analyzer pipeline uses per-language stemmers. ICU tokenizer fallback for ambiguous scripts.", 0.85, "Decision", ["SE-LANG"]),
            ("Decided search-engine query DSL is stable; internal changes expose via SDK only.", 0.80, "Decision", ["SE-API"]),
            ("Decided search-engine indexing uses bulk API with 5MB batches, single refresh per batch.", 0.80, "Decision", ["SE-INGEST"]),
        ],
        "bugs": [
            ("Fixed search-engine Elasticsearch mapping explosion from dynamic templates. Capped at 1000 fields per index.", 0.80, "Insight", ["SE-ES", "DEBUG-MAPPING"]),
            ("Fixed search-engine unicode normalization inconsistency. Switched to NFC everywhere; added migration for existing docs.", 0.75, "Insight", ["SE-LANG", "DEBUG-UNICODE"]),
            ("Fixed search-engine slow faceting on high-cardinality fields. Switched to eager global ordinals.", 0.70, "Insight", ["SE-PERF"]),
            ("Fixed search-engine partial-word matches failing on Thai/Japanese. Added language-specific tokenizers.", 0.75, "Insight", ["SE-LANG"]),
            ("Fixed search-engine connection leak under sustained load. Circuit breaker was retaining ES client refs.", 0.80, "Insight", ["SE-PERF", "DEBUG-MEM"]),
        ],
        "patterns": [
            ("Pattern: search-engine query builder composes Lucene syntax via a type-safe DSL. No raw string concat.", 0.80, "Pattern", ["SE-API"]),
            ("Pattern: search-engine uses a two-stage ranker: BM25 for recall, semantic rerank for precision on top-100.", 0.85, "Pattern", ["SE-HYBRID", "PATTERN-RERANK"]),
            ("Pattern: search-engine health endpoint returns cluster + index + node health. /health shallow, /health/deep expensive.", 0.75, "Pattern", ["SE-OBSERVABILITY"]),
        ],
        "milestones": [
            ("Milestone: search-engine launched hybrid semantic search. P95 latency 120ms for 50-doc responses.", 0.75, "Context", ["SE-HYBRID"]),
            ("Milestone: search-engine index size grew past 50M docs; upgraded to 3-node ES cluster.", 0.75, "Context", ["SE-ES"]),
            ("Milestone: search-engine multilingual rollout complete (12 languages).", 0.70, "Context", ["SE-LANG"]),
            ("Milestone: search-engine faceting perf fix in production. Latency -40% at p95.", 0.70, "Context", ["SE-PERF"]),
        ],
        "context": [
            ("search-engine ES cluster runs on Elastic Cloud, eu-west-1.", 0.75, "Context", ["SE-ES"]),
            ("search-engine indexer uses Kafka as a buffer between producers and ES. Kafka retention 7d.", 0.70, "Context", ["SE-INGEST"]),
            ("search-engine dashboard: grafana.internal/d/se-health. Top gauge: query p95 and reject rate.", 0.70, "Context", ["SE-OBSERVABILITY"]),
        ],
    },
    "old-service": {
        "decisions": [
            ("Decided to sunset old-service in favor of tensor-pipeline. 6-month deprecation, read-only in month 3.", 0.85, "Decision", ["OS-SUNSET"]),
            ("Decided old-service stops accepting new integrations after sunset announcement.", 0.80, "Decision", ["OS-SUNSET"]),
            ("Decided old-service DB upgrade from MySQL 5.7 to 8 is descoped.", 0.75, "Decision", ["OS-DB"]),
        ],
        "bugs": [
            ("Fixed old-service OAuth refresh for pre-2025-11-01 tokens. Grace-period path; removal scheduled for 6 months.", 0.70, "Insight", ["OS-AUTH", "DEBUG-AUTH"]),
            ("Fixed old-service SSL cert automation. Switched from webroot to DNS-01 challenge.", 0.75, "Insight", ["OS-TLS"]),
            ("Fixed old-service cron runaway. Added a 30-min max runtime with kill signal.", 0.65, "Insight", ["OS-CRON"]),
        ],
        "patterns": [
            ("Pattern: old-service uses MVC layout. Pre-dates the shift to feature folders.", 0.55, "Pattern", ["OS-LEGACY"]),
        ],
        "milestones": [
            ("Milestone: old-service sunset announcement sent. 12 customers requested extension, 3 migrated now.", 0.75, "Context", ["OS-SUNSET"]),
            ("Milestone: old-service read-only mode deployed. Writes return 410 Gone with migration instructions.", 0.75, "Context", ["OS-SUNSET"]),
            ("Milestone: old-service Prometheus metrics added. Grafana dashboard grafana.internal/os-legacy.", 0.55, "Context", []),
        ],
        "context": [
            ("old-service runs on an EC2 box in us-west-2. No autoscaling. Planned teardown Q4 2026.", 0.70, "Context", []),
            ("old-service DB: MySQL 5.7 (yes, still). Upgrade was descoped.", 0.60, "Context", ["OS-DB"]),
            ("Post-mortem: old-service 2025 incident was a 4hr outage caused by cron holding table locks.", 0.60, "Context", ["OS-POSTMORTEM"]),
        ],
    },
    "video": {
        "decisions": [
            ("Decided video uses ffmpeg + a custom shim for HLS segmentation. Cheaper than Mux on current volume.", 0.85, "Decision", ["VID-ARCH"]),
            ("Decided video CDN is CloudFront, fronted by a Lambda@Edge for auth token validation.", 0.85, "Decision", ["VID-CDN"]),
            ("Decided video transcoding uses a queue (SQS) with priority lanes for live vs VOD.", 0.80, "Decision", ["VID-QUEUE"]),
            ("Decided video thumbnails generate on upload + every 10s of duration. Sprite sheet in S3.", 0.75, "Decision", ["VID-THUMB"]),
            ("Decided video player is a thin wrapper over shaka-player. Custom UI only.", 0.75, "Decision", ["VID-PLAYER"]),
        ],
        "bugs": [
            ("Fixed video transcode queue deadlock under sustained upload. Priority lane wasn't yielding to live.", 0.85, "Insight", ["VID-QUEUE", "DEBUG-DEADLOCK"]),
            ("Fixed video DRM token race. Token refresh raced with playback start; fixed with 60s token overlap.", 0.80, "Insight", ["VID-DRM", "DEBUG-RACE"]),
            ("Fixed video CDN invalidation storm after a bulk delete. Batched invalidations instead of one per key.", 0.75, "Insight", ["VID-CDN", "DEBUG-INVALIDATE"]),
            ("Fixed video captions not syncing on HLS switches. Track selection was resetting on ABR change.", 0.70, "Insight", ["VID-CAPTIONS"]),
        ],
        "patterns": [
            ("Pattern: video uploads chunk via TUS protocol. Resumable on network hiccup.", 0.80, "Pattern", ["VID-UPLOAD"]),
            ("Pattern: video transcoding profiles defined in a single JSON; CI verifies backward compat on change.", 0.75, "Pattern", ["VID-ARCH"]),
        ],
        "milestones": [
            ("Milestone: video HLS + DASH dual-packaging shipped. All outputs now served in both formats.", 0.75, "Context", ["VID-ARCH"]),
            ("Milestone: video live streaming beta launched with 3 pilot customers.", 0.80, "Context", ["VID-LIVE"]),
            ("Milestone: video daily transcoded minutes crossed 100k for first time.", 0.65, "Context", []),
            ("Milestone: video DRM integration with Widevine + FairPlay complete.", 0.80, "Context", ["VID-DRM"]),
        ],
        "context": [
            ("video runs on AWS us-east-1 with a secondary transcoding cluster in eu-west-1.", 0.75, "Context", []),
            ("video storage: S3 Standard for hot tier (30 days), Glacier Deep Archive for cold.", 0.70, "Context", []),
            ("video player is embedded on app.example.com/watch and the mobile-app SDK.", 0.65, "Context", ["VID-PLAYER"]),
        ],
    },
}


def fill_project(project: ProjectSpec, target_count: int) -> int:
    """Add project memories, rotating through categories until target reached."""
    bank = PROJECT_MEMORIES[project.slug]
    added = 0
    categories = [
        ("decisions", ["decision", project.slug, project.lang]),
        ("bugs", ["bugfix", "solution", project.slug, project.lang]),
        ("patterns", ["pattern", project.slug, project.lang]),
        ("milestones", ["session-milestone", project.slug]),
        ("context", ["deployment" if "runs on" in "" else "context", project.slug]),
    ]
    # Primary pass: use the curated bank
    for cat_name, base_tags in categories:
        for content, importance, mtype, hits in bank[cat_name]:
            days = sample_age(project)
            tags = base_tags.copy()
            if cat_name == "context":
                # A memory saying "runs on" should be tagged 'deployment'
                if any(w in content.lower() for w in ["runs on", "deploys to", "production", "staging"]):
                    tags = ["deployment", project.slug]
                    # Add platform if we can infer
                    lowered = content.lower()
                    for plat in ("aws", "railway", "vercel", "ec2", "gcp", "fly", "elastic cloud"):
                        if plat in lowered:
                            tags.append(plat.replace(" ", "-"))
                else:
                    tags = [project.slug]
            corpus.append(mem(content, tags, mtype, importance, days, hits))
            added += 1
    # Fill to target with lower-signal filler memories
    while added < target_count:
        # Cycle template
        idx = added % 6
        templates = [
            (f"Minor update in {project.slug}: refactored the logger middleware to pass correlation IDs through structured fields.", 0.45, "Context"),
            (f"Routine dependency bump in {project.slug}. Upgraded {project.lang} toolchain to latest LTS.", 0.40, "Context"),
            (f"Chore in {project.slug}: removed unused feature flag after 60 days of 100% rollout.", 0.40, "Context"),
            (f"Session in {project.slug}: added integration test coverage for the new endpoint.", 0.50, "Context"),
            (f"Internal docs update for {project.slug}: captured runbook for incident response.", 0.50, "Context"),
            (f"Perf experiment in {project.slug}: tried alternative serializer; 12% improvement; decided to keep current for simplicity.", 0.55, "Context"),
        ]
        content, imp, mtype = templates[idx]
        days = sample_age(project)
        corpus.append(mem(content, [project.slug], mtype, imp, days))
        added += 1
    return added


for p in PROJECTS:
    count = fill_project(p, 50)

# ────────────────────────────────────────────────────────────────────────────
# Noise — cross-project patterns + slug-collision bait (~30)
# ────────────────────────────────────────────────────────────────────────────

noise = [
    # Generic patterns that cross-boundary associations can point to
    ("Generic note: rate limiters should use token-bucket over fixed-window to handle bursts gracefully.", ["pattern", "general", "rate-limiting"], 0.55, 8, ["CROSS-RATE"]),
    ("Generic auth note: prefer short-lived access tokens (5-15 min) with refresh tokens for SPAs.", ["pattern", "auth", "general"], 0.60, 14, ["CROSS-AUTH"]),
    ("Cross-project pattern: structured logging with correlation IDs on all request-scoped logs. Adopted in 4 services so far.", ["pattern", "observability", "general"], 0.75, 18, ["CROSS-LOG"]),
    ("Generic pattern: idempotency keys on mutating endpoints, stored 48h. Matches Stripe and OpenAI API conventions.", ["pattern", "api-design", "general"], 0.70, 25, ["CROSS-IDEMPOTENT"]),
    ("Reference: OAuth 2.0 authorization code flow with PKCE is the IETF BCP 240 recommendation for public clients.", ["reference", "auth", "general"], 0.55, 40, []),
    ("Reference: RFC 7807 problem+json is our canonical error response format across all HTTP APIs.", ["reference", "api-design", "general"], 0.60, 55, []),
    # Slug-collision bait — `video` slug collides with general video topics
    ("Note on video content strategy: publish cadence is twice a month for the main feed, weekly for product-education shorts.", ["content-marketing", "video"], 0.60, 12, ["NOISE-VIDEO"]),
    ("Research note on video generation models: Sora, Veo, Runway Gen-4 comparison. Veo leads on temporal coherence at present.", ["research", "video", "ai"], 0.55, 20, ["NOISE-VIDEO"]),
    ("Old video-production cost breakdown: pre-production 25%, shoot 40%, post 35%. Pre-AI-pipeline numbers.", ["reference", "video"], 0.40, 110, []),
    ("Video podcast episode planning for Q3: 4 guests confirmed, theme 'building for long-term memory.'", ["content-marketing", "video", "podcast"], 0.50, 35, []),
    # Technical noise unrelated to any project
    ("Found a good terraform pattern on Hacker News: module per cloud-account, outputs flow via remote state.", ["reference", "terraform"], 0.45, 30, []),
    ("Book recommendation: Designing Data-Intensive Applications still the best intro to distributed systems, per Luka.", ["reference", "reading"], 0.50, 80, []),
    ("Article link: the 'smol models' thesis — small specialized models beating large generalists on narrow tasks.", ["reference", "ai"], 0.55, 45, []),
    # Low-signal ephemera
    ("Cleaned up unused GitHub Actions workflows. Kept the release + lint, removed experimental canary deploy.", ["chore"], 0.30, 7, []),
    ("Upgraded Homebrew packages. Nothing broken.", ["chore"], 0.20, 12, []),
    ("Set up a new local tool alias: `tf = terraform`.", ["tooling", "minor"], 0.25, 18, []),
    # Duplicate-ish conversation snippets (potential dedup targets)
    ("Quick conversation: Jack asked about the Fastify migration; answered yes, shipped already.", ["conversation"], 0.30, 28, []),
    ("Quick conversation: Luka pinged re rate limiter bug status; resolved in v2.3.", ["conversation"], 0.30, 33, []),
    # Unrelated project mention
    ("Fixed rendering bug in mystery-project SSR pipeline. Unicode codepoint edge case.", ["bugfix", "solution", "mystery-project"], 0.50, 10, []),
    ("Deployed unrelated-thing to Fly.io. 8-minute build.", ["deployment", "unrelated-thing", "fly"], 0.45, 15, []),
]

for row in noise:
    content, tags, imp, days, hits = row
    mtype = "Pattern" if "pattern" in tags else "Insight" if "bugfix" in tags else "Context"
    corpus.append(mem(content, tags, mtype, imp, days, hits))


# ────────────────────────────────────────────────────────────────────────────
# Write + stats
# ────────────────────────────────────────────────────────────────────────────

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8") as f:
    for m in corpus:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")

print(f"wrote {len(corpus)} memories to {OUT.relative_to(HERE)}")

by_type: dict[str, int] = {}
for m in corpus:
    by_type[m["type"]] = by_type.get(m["type"], 0) + 1
print(f"types: {by_type}")

by_slug: dict[str, int] = {"none": 0}
for p in PROJECTS:
    by_slug[p.slug] = 0
for m in corpus:
    scoped = False
    for p in PROJECTS:
        if p.slug in m["tags"]:
            by_slug[p.slug] += 1
            scoped = True
            break
    if not scoped:
        by_slug["none"] += 1
print(f"project scope: {by_slug}")

by_age = {"0-30d": 0, "31-60d": 0, "61-90d": 0, "91+d": 0}
for m in corpus:
    ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
    days = (NOW - ts).days
    if days <= 30:
        by_age["0-30d"] += 1
    elif days <= 60:
        by_age["31-60d"] += 1
    elif days <= 90:
        by_age["61-90d"] += 1
    else:
        by_age["91+d"] += 1
print(f"age distribution: {by_age}")

# Count scenarios covered
scen_counts: dict[str, int] = {}
for m in corpus:
    for s in m.get("metadata", {}).get("hits_scenarios", []):
        scen_counts[s] = scen_counts.get(s, 0) + 1
print(f"scenario coverage: {len(scen_counts)} distinct scenario ids, {sum(scen_counts.values())} total hits across memories")
