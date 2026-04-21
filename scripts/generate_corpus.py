#!/usr/bin/env python3
"""
Generate a synthetic test corpus for ruleset comparison.

Produces ~130 memories across 3 fake projects with:
  - Mix of memory types (Preference, Decision, Pattern, Insight, Context)
  - Mix of ages (0-120 days) to exercise time_query windows
  - Metadata.hits_scenarios: each memory carries a list of scenario IDs it
    should surface for. The runner uses this to compute precision/recall.
  - Bare-tag convention (no namespace prefixes).

Writes: data/seed_memories/corpus_v1.jsonl
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "seed_memories" / "corpus_v1.jsonl"

NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def mem(
    content: str,
    tags: list[str],
    mem_type: str,
    importance: float,
    days_ago: int,
    hits: list[str] | None = None,
) -> dict:
    return {
        "content": content,
        "tags": tags,
        "type": mem_type,
        "importance": importance,
        "timestamp": iso(days_ago),
        "metadata": {
            "synthetic": True,
            "hits_scenarios": hits or [],
        },
    }


corpus: list[dict] = []

# ────────────────────────────────────────────────────────────────────────────
# Global preferences (20) — all tagged "preference", some with project scope.
# Scenario PREF-* expects these.
# ────────────────────────────────────────────────────────────────────────────
prefs = [
    # Conventional commits — 4 variants so Phase-1 limit (10 vs 20) shows effect
    ("Use Conventional Commits for all PRs. Jack's explicit preference: PR titles must follow feat:/fix:/chore:/docs:/refactor:/test:. Release-Please depends on it.", ["preference", "git-workflow"], 0.9, 2, ["PREF-COMMITS"]),
    ("Never merge PRs yourself. Jack handles all merges. Learned after accidentally merging 3 PRs in rapid succession without review.", ["preference", "git-workflow"], 0.95, 5, ["PREF-COMMITS"]),
    ("Squash-merge is the default; the PR title becomes the merge commit. Keep titles Conventional so Release-Please can parse them.", ["preference", "git-workflow"], 0.85, 15, ["PREF-COMMITS"]),
    ("Commit messages should explain WHY, not WHAT. Diff already shows what.", ["preference", "git-workflow"], 0.85, 25, ["PREF-COMMITS"]),
    # Code style
    ("Default to writing no comments in code. Only add when the WHY is non-obvious (hidden constraint, subtle invariant, workaround).", ["preference", "code-style"], 0.85, 10, ["PREF-STYLE"]),
    ("Don't add error handling or fallbacks for scenarios that can't happen. Trust internal code and framework guarantees. Validate only at system boundaries.", ["preference", "code-style"], 0.85, 12, ["PREF-STYLE"]),
    ("Three similar lines is better than a premature abstraction. Don't design for hypothetical future requirements.", ["preference", "code-style"], 0.8, 20, ["PREF-STYLE"]),
    ("Prefer editing existing files to creating new ones. Never create documentation files unless explicitly requested.", ["preference", "code-style"], 0.85, 30, ["PREF-STYLE"]),
    # Testing
    ("Integration tests must hit a real database, not mocks. Previously got burned when mocked tests passed but prod migration failed.", ["preference", "testing"], 0.9, 8, ["PREF-TESTING"]),
    ("Keep the test pyramid: 70% unit, 20% integration, 10% e2e. Don't over-invest in e2e if unit covers it.", ["preference", "testing"], 0.8, 40, ["PREF-TESTING"]),
    ("Tests should be fast enough to run on every save. >1s per unit test is a smell.", ["preference", "testing"], 0.8, 22, ["PREF-TESTING"]),
    # Memory / AutoMem
    ("Jack does not want markdown file-based memory. Use AutoMem MCP tools (store_memory, recall_memory) exclusively on this machine.", ["preference", "automem"], 0.95, 3, ["PREF-MEMORY"]),
    ("AutoMem tags are a hard gate — use bare tags, not namespace-prefixed. Corpus convention: 'preference', 'mcp-automem', 'typescript', not 'project/mcp-automem'.", ["preference", "automem"], 0.95, 1, ["PREF-MEMORY"]),
    # Collaboration
    ("Ask clarifying questions before jumping into a substantive rewrite. Bias toward understanding over speed on design-sensitive tasks.", ["preference", "collaboration"], 0.85, 18, ["PREF-COLLAB"]),
    ("Keep responses terse. No trailing 'here's what I did' summaries — the diff shows that.", ["preference", "collaboration"], 0.85, 28, ["PREF-COLLAB"]),
    ("When proposing a plan, include deltas from existing code, not a full rewrite proposal.", ["preference", "collaboration"], 0.8, 35, ["PREF-COLLAB"]),
    # Deploy
    ("Always run a production deploy through staging first. No 'quick fix to prod'.", ["preference", "deployment"], 0.9, 45, ["PREF-DEPLOY"]),
    ("Feature flags for anything that changes user-visible behavior. Rollback via flag, not hotfix.", ["preference", "deployment"], 0.85, 55, ["PREF-DEPLOY"]),
    # Older preferences (>90 days) — outside both time windows
    ("Old preference: prefer TypeScript strict mode on all new projects.", ["preference", "code-style"], 0.7, 100, ["PREF-STYLE-OLD"]),
    ("Old preference: use pnpm workspaces for monorepos, not lerna.", ["preference", "tooling"], 0.7, 110, ["PREF-TOOLING-OLD"]),
]

for c, t, imp, age, hits in prefs:
    corpus.append(mem(c, t, "Preference", imp, age, hits))

# ────────────────────────────────────────────────────────────────────────────
# Project: tensor-pipeline (active, ~40 memories, wide age spread)
# ────────────────────────────────────────────────────────────────────────────
TP = "tensor-pipeline"

tp_memories = [
    # Decisions (recent — within 30 days)
    ("Decided to use Postgres pgvector for tensor-pipeline embeddings instead of Pinecone. Cheaper self-host, acceptable recall at our scale.", ["decision", TP], 0.9, 5, ["TP-AUTH", "TP-ARCH"]),
    ("Decided to split the tensor-pipeline ingest worker from the API pod. Worker now runs on a dedicated node pool to isolate noisy-neighbor GPU jobs.", ["decision", TP], 0.9, 12, ["TP-ARCH"]),
    ("Decided to adopt OAuth2 with PKCE for tensor-pipeline public auth. Previously used bespoke JWTs.", ["decision", TP, "auth"], 0.95, 8, ["TP-AUTH"]),
    # Decisions (31-60 days — only new scheme)
    ("Decided to cap tensor-pipeline retry budget at 3 attempts with exponential backoff. More attempts just extend outage without helping.", ["decision", TP], 0.85, 45, ["TP-RETRY"]),
    # Decisions (61-90 days)
    ("Decided to migrate tensor-pipeline from Express to Fastify. 3x throughput on our workload.", ["decision", TP], 0.9, 75, ["TP-ARCH"]),
    # Decisions (>90 days — outside both)
    ("Decided to write tensor-pipeline in TypeScript instead of Go. Ecosystem of ML libs was the tie-breaker.", ["decision", TP], 0.8, 100, []),

    # Bug fixes (recent)
    ("Fixed tensor-pipeline rate-limiter timeout. Root cause: Redis SCAN was scanning the full keyspace per request. Solution: scoped key prefix + pattern scan.", ["bugfix", "solution", TP], 0.8, 4, ["TP-RATE", "DEBUG-RATE"]),
    ("Fixed tensor-pipeline OAuth token rotation. Old tokens weren't being invalidated on user-initiated logout. Added INVALIDATE event to the audit log.", ["bugfix", "solution", TP, "auth"], 0.8, 10, ["TP-AUTH", "DEBUG-AUTH"]),
    ("Fixed tensor-pipeline memory leak in ingest worker. pg pool wasn't releasing connections on error paths. Added try/finally + pool.release() in each handler.", ["bugfix", "solution", TP], 0.8, 18, ["TP-MEM", "DEBUG-MEM"]),
    # Bug fixes (31-60)
    ("Fixed tensor-pipeline flakiness in CI. Root cause: test containers racing on port 5432. Solution: docker compose per-test-suite network isolation.", ["bugfix", "solution", TP, "testing"], 0.75, 50, ["TP-CI", "DEBUG-CI"]),
    # Bug fixes (61-90)
    ("Fixed tensor-pipeline deploy hang. Railway was spinning up 2 instances before the old one drained; solved with proper graceful-shutdown SIGTERM handling.", ["bugfix", "solution", TP, "deployment"], 0.85, 80, ["TP-DEPLOY"]),

    # Patterns (recent)
    ("Pattern: tensor-pipeline uses a request-scoped context.Context injected at router boundary. All downstream calls accept ctx as first arg.", ["pattern", TP], 0.8, 6, ["TP-ARCH", "PATTERN-CTX"]),
    ("Pattern: tensor-pipeline database migrations are gated by a pre-flight SELECT to detect schema drift before applying. Prevents destructive ALTER.", ["pattern", TP], 0.8, 20, ["TP-ARCH", "PATTERN-MIGRATE"]),
    # Patterns (older)
    ("Pattern: tensor-pipeline feature flags via LaunchDarkly. Every new user-facing feature ships behind a flag with a 1-week bake period.", ["pattern", TP, "deployment"], 0.75, 65, ["PATTERN-FLAGS"]),

    # Session milestones (recent)
    ("Session milestone: shipped tensor-pipeline v2.3.0 with the new OAuth flow. Feature-flagged to 5% of users for the first 24h.", ["session-milestone", TP], 0.7, 2, ["TP-AUTH"]),
    ("Session milestone: onboarded the new ingest partner schema into tensor-pipeline. Added fuzz tests for malformed input.", ["session-milestone", TP], 0.6, 7, []),
    ("Session milestone: removed legacy tensor-pipeline v1 API. 30 day deprecation notice expired.", ["session-milestone", TP], 0.7, 14, []),
    ("Session milestone: tensor-pipeline observability sweep. Added OTel tracing at every external HTTP boundary.", ["session-milestone", TP], 0.6, 22, []),
    # Session milestones (31-60)
    ("Session milestone: tensor-pipeline retry budget shipped. Saw P99 latency drop 15% in the first week.", ["session-milestone", TP], 0.6, 40, ["TP-RETRY"]),
    ("Session milestone: tensor-pipeline CI isolation fix deployed. Flake rate dropped from 8% to 0.3%.", ["session-milestone", TP], 0.6, 55, ["TP-CI"]),
    # Session milestones (61-90)
    ("Session milestone: tensor-pipeline Fastify migration complete. All endpoints ported; benchmark shows 2.8x improvement on p50.", ["session-milestone", TP], 0.65, 78, ["TP-ARCH"]),

    # Context
    ("tensor-pipeline production runs on Railway in us-east-1 with 2 API pods and 1 worker pod. Scales to 4 API pods on queue depth > 1000.", ["deployment", TP, "railway", "production"], 0.8, 1, ["TP-DEPLOY"]),
    ("tensor-pipeline staging is a single-pod Railway environment at tp-staging.up.railway.app. Data is seeded weekly from a prod snapshot.", ["deployment", TP, "railway", "staging"], 0.7, 3, ["TP-DEPLOY"]),
]

for c, t, imp, age, hits in tp_memories:
    mtype = "Decision" if "decision" in t else \
            "Insight" if "bugfix" in t else \
            "Pattern" if "pattern" in t else \
            "Context"
    corpus.append(mem(c, t, mtype, imp, age, hits))

# ────────────────────────────────────────────────────────────────────────────
# Project: dashboard-app (active, ~25 memories, mostly recent)
# ────────────────────────────────────────────────────────────────────────────
DA = "dashboard-app"

da_memories = [
    ("Decided to adopt React Server Components in dashboard-app. Initial render cost dropped but dev-mode HMR is slower.", ["decision", DA], 0.85, 6, ["DA-RSC"]),
    ("Decided to use SWR for dashboard-app data fetching over React Query. Simpler API, adequate features for our case.", ["decision", DA], 0.8, 18, ["DA-DATA"]),
    ("Decided to drop the dashboard-app v1 charts library (Chart.js) for Recharts. Native React integration beat custom wrappers.", ["decision", DA], 0.8, 35, []),

    ("Fixed dashboard-app hydration mismatch when rendering user dates. Root cause: server used UTC, client used local. Solution: explicit Intl.DateTimeFormat on both.", ["bugfix", "solution", DA, "typescript"], 0.8, 5, ["DA-HYDRATION", "DEBUG-HYDRATE"]),
    ("Fixed dashboard-app infinite re-render loop on filter change. useEffect dependency included a new object literal per render. Memoized with useMemo.", ["bugfix", "solution", DA], 0.8, 12, ["DA-HYDRATION", "DEBUG-LOOP"]),
    ("Fixed dashboard-app N+1 query on the users-with-teams view. Added a single JOIN with aggregation instead of per-row fetch.", ["bugfix", "solution", DA], 0.75, 20, []),

    ("Pattern: dashboard-app components follow feature-folder structure. Each folder has index.tsx, hooks.ts, types.ts, *.test.tsx.", ["pattern", DA, "typescript"], 0.75, 8, ["DA-PATTERN"]),
    ("Pattern: dashboard-app uses discriminated unions for async states (loading | success | error). Avoids the three-boolean anti-pattern.", ["pattern", DA, "typescript"], 0.8, 15, ["DA-PATTERN"]),

    ("Session milestone: dashboard-app v4.0 shipped with Server Components. All pages migrated except the admin panel.", ["session-milestone", DA], 0.7, 3, ["DA-RSC"]),
    ("Session milestone: dashboard-app accessibility audit complete. Added aria-labels, fixed contrast ratios, removed 3 keyboard traps.", ["session-milestone", DA], 0.65, 10, []),
    ("Session milestone: dashboard-app bundle size reduced 30% by removing moment.js in favor of date-fns.", ["session-milestone", DA], 0.6, 25, []),

    ("dashboard-app is deployed to Vercel at app.example.com. Preview deploys per PR. Staging env is the main branch preview.", ["deployment", DA, "vercel", "production"], 0.75, 2, ["DA-DEPLOY"]),
    ("dashboard-app uses Playwright for e2e on preview deploys. Test run time ~3min; triggered via GitHub Actions.", ["testing", DA], 0.7, 4, ["DA-CI"]),
]

for c, t, imp, age, hits in da_memories:
    mtype = "Decision" if "decision" in t else \
            "Insight" if "bugfix" in t else \
            "Pattern" if "pattern" in t else \
            "Context"
    corpus.append(mem(c, t, mtype, imp, age, hits))

# ────────────────────────────────────────────────────────────────────────────
# Project: old-service (inactive, ~12 memories, mostly 60-120 days old)
# Exercises the 90-day cutoff.
# ────────────────────────────────────────────────────────────────────────────
OS = "old-service"

os_memories = [
    ("Decided to sunset old-service in favor of tensor-pipeline. Migration plan: 6 month deprecation, read-only mode in month 3.", ["decision", OS], 0.85, 35, ["OS-SUNSET"]),
    ("Decided old-service would stop accepting new integrations after the sunset announcement. Existing ones stay on support tier 2.", ["decision", OS], 0.8, 60, ["OS-SUNSET"]),

    ("Fixed old-service OAuth refresh bug where tokens issued before 2025-11-01 couldn't renew. Added a grace-period path; scheduled for removal in 6 months.", ["bugfix", "solution", OS, "auth"], 0.7, 50, ["DEBUG-AUTH"]),
    ("Fixed old-service SSL cert renewal automation. Let's Encrypt webroot misconfigured; switched to DNS-01 challenge.", ["bugfix", "solution", OS], 0.75, 85, []),

    ("Pattern: old-service uses MVC layout. Keep in mind when reading; it's pre-dates our shift to feature folders.", ["pattern", OS], 0.6, 100, []),

    ("Session milestone: old-service sunset announcement sent to customers. Response: 12 requests to extend, 3 to migrate now.", ["session-milestone", OS], 0.75, 30, ["OS-SUNSET"]),
    ("Session milestone: old-service read-only mode deployed. Writes now return 410 Gone with migration instructions.", ["session-milestone", OS], 0.75, 65, ["OS-SUNSET"]),

    ("old-service runs on an EC2 box in us-west-2. No autoscaling. Planned teardown Q4 2026 after the last customer migrates.", ["deployment", OS, "aws", "production"], 0.7, 40, []),
    ("old-service DB is MySQL 5.7 (yes, still). Upgrade to 8 was descoped when sunset was decided.", ["deployment", OS], 0.6, 90, []),
    # Very old
    ("old-service original architecture note: monolithic Flask app with a single Postgres 11 DB. History of the codebase.", ["pattern", OS], 0.5, 120, []),
    ("old-service post-mortem from the 2025 incident: 4hr outage caused by a runaway cron job holding table locks.", ["bugfix", "solution", OS], 0.6, 110, []),
    ("old-service added prometheus metrics. Grafana dashboard at grafana.internal/os-legacy.", ["deployment", OS], 0.55, 95, []),
]

for c, t, imp, age, hits in os_memories:
    mtype = "Decision" if "decision" in t else \
            "Insight" if "bugfix" in t else \
            "Pattern" if "pattern" in t else \
            "Context"
    corpus.append(mem(c, t, mtype, imp, age, hits))

# ────────────────────────────────────────────────────────────────────────────
# Noise memories (10) — semantically near some scenarios but untagged for the
# project, to test whether the scheme correctly excludes / includes.
# ────────────────────────────────────────────────────────────────────────────
noise = [
    # Rate limiter content, but no tensor-pipeline tag
    ("Generic note: rate limiters should use token-bucket over fixed-window to handle bursts gracefully.", ["pattern", "general"], 0.5, 7, []),
    # Auth content, no project tag
    ("Generic auth note: prefer short-lived access tokens (5-15 min) with refresh tokens for SPAs.", ["pattern", "auth"], 0.55, 12, []),
    # Random other project
    ("Fixed mystery-project rendering bug where SSR crashed on certain Unicode codepoints in user bios.", ["bugfix", "solution", "mystery-project"], 0.6, 8, []),
    # Preference-like content but not tagged preference
    ("Note: conventional-commits has a nice CLI wrapper called commitizen. Some teams use it; we don't.", ["tooling", "git-workflow"], 0.4, 20, []),
    # OAuth content, generic
    ("OAuth 2.0 authorization code flow with PKCE is the current recommendation for public clients per IETF BCP 240.", ["reference", "auth"], 0.5, 30, []),
    # Memory-related noise
    ("AutoMem storage note: large memories (>500 chars) are auto-summarized by the server. Plan accordingly.", ["reference", "automem"], 0.6, 15, []),
    # Decay memories
    ("Low-importance session note: adjusted some eslint rules in dashboard-app/eslint.config.js.", ["session-milestone", "dashboard-app"], 0.3, 5, []),
    ("Low-importance session note: formatted all Python files in old-service.", ["session-milestone", "old-service"], 0.25, 25, []),
    # Deployment noise from unrelated project
    ("Deployed some-other-service to Fly.io. Initial build was 8 minutes.", ["deployment", "some-other-service", "fly"], 0.5, 10, []),
    # Cross-project pattern (no specific project tag)
    ("Cross-project pattern: structured logging with correlation IDs on all request-scoped logs. Adopted in 3 services so far.", ["pattern", "observability"], 0.7, 18, []),
]

for c, t, imp, age, hits in noise:
    corpus.append(mem(c, t, "Context", imp, age, hits))


OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8") as f:
    for m in corpus:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")

print(f"wrote {len(corpus)} memories to {OUT.relative_to(HERE)}")
# Quick stats
by_type = {}
for m in corpus:
    by_type[m["type"]] = by_type.get(m["type"], 0) + 1
print(f"types: {by_type}")
by_slug = {}
for m in corpus:
    slug = next((t for t in m["tags"] if t in {TP, DA, OS}), "none")
    by_slug[slug] = by_slug.get(slug, 0) + 1
print(f"project scope: {by_slug}")
by_age = {"0-30d": 0, "31-60d": 0, "61-90d": 0, "91+d": 0}
for m in corpus:
    # Parse the timestamp, compute days ago
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
