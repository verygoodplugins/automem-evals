# Local AutoMem graph diagnostics - 2026-05-01T17:32:42

Raw artifacts: `data/sweep_runs/20260501-173242-graph-diagnostics`

## Health

| Label | Endpoint | Status | Memories | Vectors | Sync | Dimensions |
|---|---|---|---:|---:|---|---|
| full | `http://localhost:8001` | healthy | 10750 | 10750 | synced | 1024 |
| cleaned | `http://localhost:8011` | healthy | 7618 | 7618 | synced | 1024 |

## Graph Shape

| Label | Nodes | Edges | PRECEDED_BY | System edges | Authorable edges | Memory type | INVALIDATED_BY | PREFERS_OVER | Legacy discovered | Risks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| full | 10750 | 116558 | 37.2% | 92.1% | 7.9% | 54.9% | 23 | 4 | 99.0% | high generic Memory type share, system-generated edges dominate the graph, sparse authorable edges, INVALIDATED_BY/PREFERS_OVER barely fire, legacy discovered relation types dominate discovered edges, legacy PARALLEL_CONTEXT similarities are all zero |
| cleaned | 7618 | 74281 | 35.0% | 90.5% | 9.5% | 55.3% | 23 | 4 | 99.4% | high generic Memory type share, system-generated edges dominate the graph, sparse authorable edges, INVALIDATED_BY/PREFERS_OVER barely fire, legacy discovered relation types dominate discovered edges, legacy PARALLEL_CONTEXT similarities are all zero |

## Exchange Claims

| Claim | Local status | Evidence |
|---|---|---|
| PRECEDED_BY dominates at ~87% | differs locally | Full local graph PRECEDED_BY share is 37.2%. |
| INVALIDATED_BY/PREFERS_OVER barely fire | confirmed locally | Full local graph has INVALIDATED_BY=23, PREFERS_OVER=4. |
| parallel_context similarity=0.0 | mixed | full: legacy zero=100.0%; full: DISCOVERED nonzero=283; cleaned: legacy zero=100.0%; cleaned: DISCOVERED nonzero=124 |
| clustering defaults need source verification | checked | hardcoded_similarity_threshold, hardcoded_min_cluster_size, cluster_interval_default_30d, eager_scheduler_tick |

## Threshold Evidence

### full
0.75 still returns 5878 sampled top-k neighbor hits; 0.65 returns 7764 (32.1% more). Top-1 median is 0.9754.

| Threshold | Sampled top-k neighbor hits |
|---:|---:|
| 0.55 | 9388 |
| 0.6 | 8843 |
| 0.65 | 7764 |
| 0.7 | 6818 |
| 0.75 | 5878 |
| 0.8 | 4963 |
| 0.85 | 3901 |

### cleaned
0.75 still returns 4112 sampled top-k neighbor hits; 0.65 returns 6617 (60.9% more). Top-1 median is 0.8551.

| Threshold | Sampled top-k neighbor hits |
|---:|---:|
| 0.55 | 9104 |
| 0.6 | 8016 |
| 0.65 | 6617 |
| 0.7 | 5140 |
| 0.75 | 4112 |
| 0.8 | 3247 |
| 0.85 | 2458 |

## Source Hypotheses

| Hypothesis | Status | Evidence |
|---|---|---|
| hardcoded_similarity_threshold | confirmed | consolidation.py:157 `self.similarity_threshold = 0.75` |
| hardcoded_min_cluster_size | confirmed | consolidation.py:156 `self.min_cluster_size = 3` |
| cluster_interval_default_30d | confirmed | config.py:38 `os.getenv("CONSOLIDATION_CLUSTER_INTERVAL_SECONDS", str(2592000))` |
| eager_scheduler_tick | confirmed | runtime_scheduler.py:100 `run_consolidation_tick_fn()` |

## Read

The diagnostics do not mutate AutoMem. They treat runtime fixes as follow-up PRs: readiness probe, configurable clustering, legacy edge normalization, and any supersession-discovery pass should remain separate from this measurement harness.
