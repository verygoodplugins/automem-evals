# Inline obsolete-memory relation comparison

| Arm | ForgetEval | Query errors | Full graph rows | Top-k graph |
| --- | ---: | ---: | ---: | ---: |
| baseline | 234/385 | 0 | 5/10 | 10/10 |
| candidate | 234/385 | 0 | 10/10 | 10/10 |

All 385 paired case inputs match. Verdicts: 0 fixed, 0 newly failing, 234 unchanged pass, 151 unchanged fail.
Changed 385-case IDs: none.
Changed graph fixtures: supersede-0, supersede-1, supersede-2, supersede-3, supersede-4.

The five supersession probes exercise obsolete content nested in active neighbors’ inline relations. Top-k content was already clean. Purge fixtures remain unchanged. The exact existing diagnostic/scoring function is retained.

All expected checks passed: True. Paid API calls: 0. Newly owned containers/volumes cleaned: True.

The full 385-case classification/input equality index and raw HTTP result rows are in the ignored sweep directory, bound by manifest hashes. These free exploratory results do not replace official benchmark claims.

## Separate real-store contract probe

Four checks pass: current mode preserves the active inline payload and reduces the expired target to its ID; history mode preserves both payloads. This small additional contract probe is separate from the matched385/10 benchmark.

API log audit: no inline-state verification failures, graph/query exceptions or tracebacks. Two candidate Werkzeug protocol HTTP400 entries (bad request version) have unknown caller attribution; they are retained explicitly and did not produce case query errors. The contrastive probe log has no errors. All newly owned stacks/volumes were removed.
