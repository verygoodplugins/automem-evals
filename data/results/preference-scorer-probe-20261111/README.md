# Synthetic scorer probe — prepared, not run

A small synthetic, disjoint development/held-out diagnostic has been prepared at [`experiments/preference_scorer_probe`](../../../experiments/preference_scorer_probe/README.md). No model inference or scoring result has been produced by this preparation. The fixture is not copied from saved benchmark answers or private user traces, and it is not a benchmark score.

The prior blinded preference calibration was an independent single-local-model analysis of saved benchmark answers; it is not human gold. Its unmerged acceptance candidate failed two of four held-out cases. This synthetic probe targets the underlying failure modes without reusing or tuning on that held-out set. Running it does not by itself validate an official scoring policy.
