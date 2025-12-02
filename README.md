# AutoMem Evals

Evaluation framework for testing and comparing AutoMem rule sets across different AI agents.

## Purpose

The [mcp-automem](https://github.com/verygoodplugins/mcp-automem) server provides persistent memory to AI agents. But how do we know if a given set of instructions (rules) helps the AI use memory effectively?

This repo provides:
1. **Benchmark scenarios** - Reproducible test cases with expected outcomes
2. **Metrics** - Quantitative measures of memory quality
3. **Comparison tools** - A/B testing different rule sets
4. **Analysis** - Reports and visualizations

## Evaluation Dimensions

### 1. Recall Precision
*Does the AI retrieve the right memories?*

```
Scenario: Given 50 stored memories about a project, ask "What architecture decisions did we make?"
Expected: Retrieve memories tagged [decision, architecture] with >0.8 importance
Metric: Precision@K, Recall@K, NDCG
```

### 2. Storage Quality (Signal-to-Noise)
*Does the AI store meaningful information?*

```
Scenario: Complete a 30-minute coding session fixing 3 bugs
Expected: ~3-5 memories (one per significant fix), not 50 trivial edits
Metric: 
  - Storage rate (memories/hour)
  - Importance distribution (should be bimodal, not uniform)
  - Human-rated usefulness (sample review)
```

### 3. Association Quality
*Are relationships between memories meaningful?*

```
Scenario: Store a bug fix, then ask about related decisions
Expected: Bug fix memory should RELATES_TO or DERIVED_FROM the original feature
Metric:
  - Association coverage (% of memories with relationships)
  - Relationship accuracy (human-rated)
  - Graph connectivity (isolated nodes = bad)
```

### 4. Context Awareness
*Does the AI use context hints effectively?*

```
Scenario: Working in Python file, ask about "error handling patterns"
Expected: Prioritize Python-specific memories over JavaScript ones
Metric: Language/context match rate
```

### 5. Multi-hop Reasoning
*Can the AI follow relationship chains?*

```
Scenario: Store "Alice's manager is Bob" and "Bob works in Engineering"
Query: "What department does Alice's manager work in?"
Expected: Engineering (requires 2-hop traversal)
Metric: Multi-hop accuracy by hop count
```

## Proposed Structure

```
automem-evals/
├── scenarios/                    # Test scenario definitions
│   ├── recall/
│   │   ├── basic_query.yaml
│   │   ├── multi_query.yaml
│   │   ├── time_filtered.yaml
│   │   └── entity_expansion.yaml
│   ├── storage/
│   │   ├── coding_session.yaml
│   │   ├── decision_making.yaml
│   │   └── bug_fixing.yaml
│   └── association/
│       ├── feature_to_bug.yaml
│       └── decision_chain.yaml
│
├── rulesets/                     # Rule sets to compare
│   ├── baseline/                 # Minimal rules
│   │   └── rules.md
│   ├── cursor_v1/                # Current Cursor template
│   │   └── rules.md
│   ├── claude_code_v1/           # Current Claude Code template
│   │   └── rules.md
│   └── experimental/             # New variations to test
│       ├── aggressive_storage/
│       └── conservative_storage/
│
├── runners/                      # Test execution
│   ├── scenario_runner.py        # Execute scenarios against rules
│   ├── transcript_analyzer.py    # Parse session transcripts
│   └── metrics.py                # Calculate evaluation metrics
│
├── data/                         # Test data and results
│   ├── seed_memories/            # Pre-populated memory sets
│   ├── transcripts/              # Session transcripts for analysis
│   └── results/                  # Evaluation results
│
├── analysis/                     # Reporting
│   ├── compare_rulesets.py       # Generate comparison reports
│   └── visualize.py              # Charts and graphs
│
└── docs/
    ├── SCENARIOS.md              # How to write scenarios
    ├── METRICS.md                # Metric definitions
    └── CONTRIBUTING.md           # How to add rule sets
```

## Scenario Format (Draft)

```yaml
# scenarios/recall/basic_query.yaml
name: basic_semantic_recall
description: Test basic semantic search retrieval

setup:
  seed_memories:
    - content: "Decided to use PostgreSQL for user data. ACID compliance needed."
      tags: [project-x, decision, database]
      importance: 0.9
    - content: "Using Redis for session caching. Sub-millisecond latency."
      tags: [project-x, decision, caching]
      importance: 0.85
    - content: "Fixed login bug - null check was missing."
      tags: [project-x, bug-fix, auth]
      importance: 0.7

test_cases:
  - query: "What database did we choose?"
    expected_ids: [mem-1]  # PostgreSQL decision
    min_score: 0.8
    
  - query: "Tell me about caching"
    expected_ids: [mem-2]  # Redis decision
    min_score: 0.75

metrics:
  - precision_at_1
  - recall_at_3
  - mean_reciprocal_rank
```

## Metrics Reference

| Metric | Description | Good Value |
|--------|-------------|------------|
| **Precision@K** | % of top-K results that are relevant | >0.8 |
| **Recall@K** | % of relevant items in top-K | >0.7 |
| **MRR** | Mean Reciprocal Rank of first relevant | >0.8 |
| **NDCG** | Normalized Discounted Cumulative Gain | >0.75 |
| **Storage Rate** | Memories stored per hour | 2-10 |
| **Importance Spread** | Std dev of importance scores | >0.15 |
| **Association Coverage** | % memories with relationships | >30% |
| **Multi-hop Accuracy** | Correct answers requiring traversal | >0.6 |

## Running Evaluations

```bash
# Run all scenarios against a rule set
python runners/scenario_runner.py --ruleset cursor_v1

# Compare two rule sets
python analysis/compare_rulesets.py cursor_v1 experimental/aggressive

# Analyze a session transcript
python runners/transcript_analyzer.py data/transcripts/session_001.json
```

## Ideas for Future Work

1. **Synthetic session generation** - Use an LLM to generate realistic coding sessions, then evaluate memory behavior

2. **Crowdsourced relevance judgments** - Have humans rate memory relevance for ground truth

3. **Longitudinal studies** - Track memory quality over weeks/months of real usage

4. **Cross-agent comparison** - Same scenarios on Claude, GPT-4, Gemini with same rules

5. **Ablation studies** - Remove specific rule components to measure their impact

6. **Prompt optimization** - Use techniques like DSPy to automatically tune rule prompts

## Related

- [mcp-automem](https://github.com/verygoodplugins/mcp-automem) - MCP server for AutoMem
- [automem](https://github.com/verygoodplugins/automem) - Backend memory service

## License

MIT

