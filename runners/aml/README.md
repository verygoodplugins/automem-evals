# AutoMem AML adapter

HTTP adapter for the [Agent Memory Leaderboard (AML)](https://agentmemoryleaderboard.ai/) Add/Search contract, for AutoMem's Cycle 2 entry (Cycle 2 opens 2026-09-20). AML generates answers and scores them. This service only stores the messages AML sends and returns ranked AutoMem evidence. It never produces an answer, and it doesn't expose AutoMem administration.

Dependency-free Node (24+). No `package.json`, no install step.

## Endpoints

- `GET /health`: unauthenticated, as AML requires. Returns 200 when AutoMem's `/health` answers, 503 when it doesn't.
- `POST /add`: accepts `request_id`, `user_id`, `session_id` and `messages[]` (`role`, `content`, optional Unix-millisecond `timestamp`). Waits until every message is written to AutoMem, then echoes the three IDs:
  `{"success":true,"request_id":"...","user_id":"...","session_id":"..."}`.
  Replaying a `request_id` with the same body returns the same response without writing again. Replaying it with a different body returns 409.
- `POST /search`: accepts `query`, `user_id`, `top_k` and optional `options`. Returns `{"data":[{"id","content","score","created_at"}]}` in AutoMem's ranked order, capped at `top_k` (AutoMem is asked for at most 100).

Errors use `{"detail":{"reason":"..."}}`:

| Status | Cause |
|---|---|
| 401 | Bad key |
| 413 | Body over 1 MB |
| 422 | Contract violation |
| 503 | AutoMem failure |

`/add` and `/search` accept the Memory System Key as `Authorization: Bearer <key>`, `Authorization: Token <key>`, or `X-Api-Key: <key>`. Set `AML_ADAPTER_API_KEY` in any deployment: with it unset, the adapter accepts every request.

## User isolation

Each message is stored as an AutoMem `Context` record tagged `aml-evaluation` plus `aml-user-<sha256(user_id)>`. The raw `user_id` never appears in AutoMem tags. The message timestamp is stored as the memory `timestamp`, and `metadata` carries the AML request, session, role and message index.

Search recalls only the exact user tag and pins every recall option that could return another user's records, instead of relying on server defaults:

| Recall option | Value | Why |
|---|---|---|
| `tag_match` | `exact` | The server default is `prefix`. |
| `expand_relations` | `false` | Relation expansion can reach records outside the tag scope. |
| `expand_entities` | `false` | Entity expansion can reach records outside the tag scope. |
| `scope_fallback` | `false` | This option fills leftover slots from an unscoped search. |

## Retention

Every record gets `t_invalid` 30 days after ingestion, so it drops out of recall. AML also requires evaluation data and derived copies to be *deleted* within 30 days of a run. Pair the deployment with a job that deletes `aml-evaluation`-tagged records.

## Run

```sh
AUTOMEM_API_URL=https://your-automem.example \
AUTOMEM_API_KEY=... \
AML_ADAPTER_API_KEY=... \
node runners/aml/server.mjs            # listens on $PORT, default 8790
```

Docker (the AML academic code route builds a fixed commit):

```sh
docker build -t automem-aml-adapter:cycle-2 runners/aml
docker run --rm -p 8790:8790 \
  -e AUTOMEM_API_URL -e AUTOMEM_API_KEY -e AML_ADAPTER_API_KEY \
  automem-aml-adapter:cycle-2
```

Configure AML with `https://<adapter>/add`, `/search` and `/health`. Never put credentials in those URLs. The image contains no credentials.

## Verification

```sh
node --test runners/aml/adapter.test.mjs
```

This runs the contract tests against a local AutoMem stub. They cover:
- Add/echo, Search shape and ranking;
- strict `user_id` isolation and the pinned recall options;
- `request_id` idempotency and 409 on conflict;
- 401/413/422 errors, and 503 health when AutoMem is down.

```sh
AUTOMEM_API_URL=... AUTOMEM_API_KEY=... node runners/aml/smoke-live.mjs
```

This is a real-AutoMem round trip. It stores one random non-sensitive sentinel, checks a scoped Add → Search and that a different `user_id` gets nothing, then deletes the record. Point it at a disposable or local AutoMem when possible.

Neither command is an AML-issued smoke. That needs Cycle 2 access and an Eval Key.

## Submission and operations

**Owner sign-off is required before any AML evaluation request, smoke, Full run, or publication request.**

Deployment:
- Deploy the pinned image behind HTTPS with a dedicated `AML_ADAPTER_API_KEY` and a secret-managed `AUTOMEM_API_KEY`.
- Run at least two instances, with health checks on `/health`.
- Size edge rate limits for AML's declared Add/Search concurrency (64/256). Don't turn legitimate evaluation bursts into 429s.
- Alert on `/health` failures, p95 latency, 5xx rate, and AutoMem errors.

Access and uptime:
- Once Cycle 2 opens, request evaluation access and bind the endpoints and key.
- Run AML's non-scored compatibility smoke before any Full run.
- Keep the endpoint and image revision reachable for at least 30 days after submission.

The application must disclose:
- the API URL and auth scheme;
- the capacity, timeout and rate-limit values;
- the Docker command;
- the AutoMem revision under test;
- attribution to [AutoMem's research foundation](https://github.com/verygoodplugins/automem#research-foundation);
- the fact that this adapter only translates the AML schema and enforces isolation.

References: [AML rules](https://agentmemoryleaderboard.ai/rules), [public evaluation repository](https://github.com/AML-memory/agent-memory-leaderboard).

## Provenance

This is a port of an adapter first built in a private automation repo, the version that passed a live-AutoMem smoke. It adds hardening and the operations plan from a second, duplicate implementation there. This repo is now its home.
