# BEAM diff — v1_convs_0_1.json vs beam_results_20260422_051643.json

## Run metadata

| | A (before) | B (after) |
|---|---|---|
| run_id | f4be4e81 | 25853835 |
| answerer_model | gpt-5-mini | gpt-5-mini |
| judge_model | gpt-5-mini | gpt-5-mini |
| top_k | 200 | 200 |
| top_k_cutoffs | ['top_100'] | ['top_100'] |
| chat_sizes | ['100K'] | ['100K'] |
| conversations | 0-1 | 0-1 |
| total_questions | 40 | 40 |

## Overall

| metric | A | B | Δ |
|---|---:|---:|---:|
| questions | 40 | 40 | 0 |
| pass_rate | 62.50% | 72.50% | +10.00pp |
| avg_score | 0.507 | 0.629 | +0.123 |

## Per-category

| category | n | A pass | B pass | Δ pass | A avg | B avg | Δ avg |
|---|---:|---:|---:|---:|---:|---:|---:|
| abstention | 4 | 0.0% | 50.0% | +50.00pp | 0.000 | 0.500 | +0.500 |
| contradiction_resolution | 4 | 100.0% | 100.0% | +0.00pp | 0.688 | 0.594 | -0.094 |
| event_ordering | 4 | 100.0% | 75.0% | -25.00pp | 0.667 | 0.658 | -0.008 |
| information_extraction | 4 | 100.0% | 75.0% | -25.00pp | 1.000 | 0.771 | -0.229 |
| instruction_following | 4 | 50.0% | 75.0% | +25.00pp | 0.375 | 0.625 | +0.250 |
| knowledge_update | 4 | 75.0% | 75.0% | +0.00pp | 0.750 | 0.750 | +0.000 |
| multi_session_reasoning | 4 | 50.0% | 50.0% | +0.00pp | 0.312 | 0.500 | +0.188 |
| preference_following | 4 | 100.0% | 100.0% | +0.00pp | 0.875 | 0.750 | -0.125 |
| summarization | 4 | 50.0% | 75.0% | +25.00pp | 0.400 | 0.646 | +0.246 |
| temporal_reasoning | 4 | 0.0% | 50.0% | +50.00pp | 0.000 | 0.500 | +0.500 |

## Question-level flips

- Newly passing (A=FAIL → B=PASS): **9**
- Newly failing (A=PASS → B=FAIL): **5**
- Net flips in B's favor: **4**

### Newly passing (sample up to 20)

- [temporal_reasoning] `100K_0_q19_temporal_reasoning` (A score=0.00 → B score=1.00)
- [abstention] `100K_1_q0_abstention` (A score=0.00 → B score=1.00)
- [multi_session_reasoning] `100K_1_q13_multi_session_reasoning` (A score=0.00 → B score=1.00)
- [summarization] `100K_1_q16_summarization` (A score=0.00 → B score=0.83)
- [summarization] `100K_1_q17_summarization` (A score=0.00 → B score=0.75)
- [temporal_reasoning] `100K_1_q18_temporal_reasoning` (A score=0.00 → B score=1.00)
- [abstention] `100K_1_q1_abstention` (A score=0.00 → B score=1.00)
- [instruction_following] `100K_1_q8_instruction_following` (A score=0.00 → B score=1.00)
- [instruction_following] `100K_1_q9_instruction_following` (A score=0.00 → B score=1.00)

### Newly failing (sample up to 20)

- [multi_session_reasoning] `100K_0_q12_multi_session_reasoning` (A score=0.50 → B score=0.25)
- [summarization] `100K_0_q17_summarization` (A score=0.90 → B score=0.30)
- [event_ordering] `100K_0_q4_event_ordering` (A score=0.67 → B score=0.33)
- [instruction_following] `100K_0_q8_instruction_following` (A score=1.00 → B score=0.00)
- [information_extraction] `100K_1_q7_information_extraction` (A score=1.00 → B score=0.33)

### Flip balance per category

| category | ↑ new-pass | ↓ new-fail | net |
|---|---:|---:|---:|
| abstention | 2 | 0 | +2 |
| contradiction_resolution | 0 | 0 | +0 |
| event_ordering | 0 | 1 | -1 |
| information_extraction | 0 | 1 | -1 |
| instruction_following | 2 | 1 | +1 |
| knowledge_update | 0 | 0 | +0 |
| multi_session_reasoning | 1 | 1 | +0 |
| preference_following | 0 | 0 | +0 |
| summarization | 2 | 1 | +1 |
| temporal_reasoning | 2 | 0 | +2 |
