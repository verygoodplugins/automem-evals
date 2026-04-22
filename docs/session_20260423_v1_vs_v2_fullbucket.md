# BEAM diff — beam_results_20260422_035020.json vs beam_results_20260422_121026.json

## Run metadata

| | A (before) | B (after) |
|---|---|---|
| run_id | f4be4e81 | 247928c1 |
| answerer_model | gpt-5-mini | gpt-5-mini |
| judge_model | gpt-5-mini | gpt-5-mini |
| top_k | 200 | 200 |
| top_k_cutoffs | ['top_100'] | ['top_100'] |
| chat_sizes | ['100K'] | ['100K'] |
| conversations | 0-19 | 0-19 |
| total_questions | 400 | 400 |

## Overall

| metric | A | B | Δ |
|---|---:|---:|---:|
| questions | 400 | 400 | 0 |
| pass_rate | 76.25% | 73.75% | -2.50pp |
| avg_score | 0.677 | 0.653 | -0.025 |

## Per-category

| category | n | A pass | B pass | Δ pass | A avg | B avg | Δ avg |
|---|---:|---:|---:|---:|---:|---:|---:|
| abstention | 40 | 55.0% | 70.0% | +15.00pp | 0.550 | 0.700 | +0.150 |
| contradiction_resolution | 40 | 90.0% | 87.5% | -2.50pp | 0.675 | 0.666 | -0.009 |
| event_ordering | 40 | 70.0% | 50.0% | -20.00pp | 0.594 | 0.438 | -0.156 |
| information_extraction | 40 | 97.5% | 85.0% | -12.50pp | 0.938 | 0.784 | -0.153 |
| instruction_following | 40 | 90.0% | 80.0% | -10.00pp | 0.794 | 0.713 | -0.081 |
| knowledge_update | 40 | 57.5% | 65.0% | +7.50pp | 0.569 | 0.637 | +0.069 |
| multi_session_reasoning | 40 | 70.0% | 62.5% | -7.50pp | 0.619 | 0.542 | -0.077 |
| preference_following | 40 | 95.0% | 95.0% | +0.00pp | 0.875 | 0.863 | -0.012 |
| summarization | 40 | 65.0% | 70.0% | +5.00pp | 0.466 | 0.510 | +0.044 |
| temporal_reasoning | 40 | 72.5% | 72.5% | +0.00pp | 0.694 | 0.675 | -0.019 |

## Question-level flips

- Newly passing (A=FAIL → B=PASS): **51**
- Newly failing (A=PASS → B=FAIL): **61**
- Net flips in B's favor: **-10**

### Newly passing (sample up to 20)

- [abstention] `100K_0_q0_abstention` (A score=0.00 → B score=1.00)
- [temporal_reasoning] `100K_0_q19_temporal_reasoning` (A score=0.00 → B score=1.00)
- [summarization] `100K_10_q17_summarization` (A score=0.00 → B score=0.80)
- [abstention] `100K_12_q0_abstention` (A score=0.00 → B score=1.00)
- [multi_session_reasoning] `100K_12_q12_multi_session_reasoning` (A score=0.00 → B score=0.67)
- [multi_session_reasoning] `100K_15_q13_multi_session_reasoning` (A score=0.00 → B score=1.00)
- [summarization] `100K_15_q17_summarization` (A score=0.00 → B score=0.62)
- [multi_session_reasoning] `100K_16_q13_multi_session_reasoning` (A score=0.00 → B score=0.50)
- [preference_following] `100K_16_q14_preference_following` (A score=0.00 → B score=1.00)
- [summarization] `100K_16_q16_summarization` (A score=0.00 → B score=0.50)
- [abstention] `100K_17_q0_abstention` (A score=0.00 → B score=1.00)
- [abstention] `100K_18_q0_abstention` (A score=0.00 → B score=1.00)
- [multi_session_reasoning] `100K_18_q13_multi_session_reasoning` (A score=0.00 → B score=0.57)
- [summarization] `100K_18_q16_summarization` (A score=0.00 → B score=0.67)
- [contradiction_resolution] `100K_18_q2_contradiction_resolution` (A score=0.00 → B score=0.75)
- [knowledge_update] `100K_19_q11_knowledge_update` (A score=0.00 → B score=1.00)
- [event_ordering] `100K_19_q4_event_ordering` (A score=0.42 → B score=0.58)
- [abstention] `100K_1_q0_abstention` (A score=0.00 → B score=1.00)
- [knowledge_update] `100K_1_q11_knowledge_update` (A score=0.00 → B score=1.00)
- [multi_session_reasoning] `100K_1_q13_multi_session_reasoning` (A score=0.00 → B score=0.50)
- ...and 31 more.

### Newly failing (sample up to 20)

- [multi_session_reasoning] `100K_0_q12_multi_session_reasoning` (A score=0.50 → B score=0.25)
- [multi_session_reasoning] `100K_0_q13_multi_session_reasoning` (A score=0.75 → B score=0.00)
- [instruction_following] `100K_0_q8_instruction_following` (A score=1.00 → B score=0.00)
- [abstention] `100K_10_q0_abstention` (A score=1.00 → B score=0.00)
- [temporal_reasoning] `100K_10_q18_temporal_reasoning` (A score=1.00 → B score=0.00)
- [event_ordering] `100K_10_q5_event_ordering` (A score=0.60 → B score=0.40)
- [temporal_reasoning] `100K_11_q18_temporal_reasoning` (A score=1.00 → B score=0.00)
- [information_extraction] `100K_11_q6_information_extraction` (A score=1.00 → B score=0.00)
- [information_extraction] `100K_11_q7_information_extraction` (A score=1.00 → B score=0.38)
- [instruction_following] `100K_11_q9_instruction_following` (A score=0.50 → B score=0.00)
- [multi_session_reasoning] `100K_12_q13_multi_session_reasoning` (A score=0.75 → B score=0.25)
- [summarization] `100K_12_q17_summarization` (A score=0.60 → B score=0.40)
- [abstention] `100K_12_q1_abstention` (A score=1.00 → B score=0.00)
- [multi_session_reasoning] `100K_13_q13_multi_session_reasoning` (A score=0.75 → B score=0.00)
- [summarization] `100K_13_q16_summarization` (A score=0.62 → B score=0.25)
- [event_ordering] `100K_13_q4_event_ordering` (A score=0.70 → B score=0.40)
- [event_ordering] `100K_13_q5_event_ordering` (A score=0.83 → B score=0.25)
- [knowledge_update] `100K_14_q10_knowledge_update` (A score=1.00 → B score=0.00)
- [multi_session_reasoning] `100K_14_q12_multi_session_reasoning` (A score=0.50 → B score=0.00)
- [multi_session_reasoning] `100K_14_q13_multi_session_reasoning` (A score=1.00 → B score=0.00)
- ...and 41 more.

### Flip balance per category

| category | ↑ new-pass | ↓ new-fail | net |
|---|---:|---:|---:|
| abstention | 11 | 5 | +6 |
| contradiction_resolution | 3 | 4 | -1 |
| event_ordering | 4 | 12 | -8 |
| information_extraction | 0 | 5 | -5 |
| instruction_following | 4 | 8 | -4 |
| knowledge_update | 7 | 4 | +3 |
| multi_session_reasoning | 5 | 8 | -3 |
| preference_following | 2 | 2 | +0 |
| summarization | 9 | 7 | +2 |
| temporal_reasoning | 6 | 6 | +0 |
