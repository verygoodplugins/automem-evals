# Capped benchmark API calls

Start one loopback proxy for every server, answerer, judge and auxiliary scorer:

```bash
python3 scripts/benchmarks/paid_budget_proxy.py --ledger /absolute/shared.sqlite3 --pricing prices.json --cap-usd 20
```

Supply provider keys in the proxy process environment only. Pricing JSON is `{"models":{"gpt-5-mini":{"input_usd_per_million":"0.25","output_usd_per_million":"2"}}}`; supply verified prices for every requested model. Prices have no defaults. Supported models are `gpt-5-mini`, `gpt-5.4-mini-2026-03-17`, `voyage-4` (1024d) and `text-embedding-3-small`. Reverify official pricing before each campaign.

Use the printed OpenAI base URL for SDK clients. Redirect the frozen server's Voyage URL to the printed Voyage base plus `/embeddings` at launch. All paid callers must use the same proxy/absolute ledger. Direct calls bypass protection.

**Monitor `/status` and terminate owned benchmark processes if `halted` is true or accounting is unavailable.** Harnesses can swallow provider exceptions. Unsupported, invalid or unpriced POSTs persist a `request_rejected` halt before returning HTTP 400, so silent extraction/scoring fallbacks cannot leave the campaign healthy; they make no upstream call or reservation, and later valid requests are denied. Chat calls must specify an output cap; the proxy pins standard service tier. Admission reserves a conservative byte-based input bound plus the complete output cap before network. Successful usage reconciles the charge; errors, timeouts or missing usage retain the reservation and halt persistently. The proxy performs no retries and never logs keys, prompts or raw provider errors.

`--summary --ledger /absolute/shared.sqlite3` opens an existing ledger through SQLite read-only mode and reads accounting without network. It never creates a ledger or initializes schema, and rejects missing paths or uninitialized files. `--cap-usd` is ignored in summary mode: inspecting accounting cannot change a stored cap, halt flag or liabilities. Summaries include committed transactions from an active WAL writer. One USD is 1,000,000,000 nUSD. Never delete/reset a campaign ledger or raise its cap. Any reviewed rollover must retain all prior liabilities and lower the new cap by their total, with only one active proxy.

Run fake-only verification with `python3 -m unittest discover -s scripts/benchmarks -p test_paid_budget_proxy.py`. The guard is an experiment-specific accounting boundary; it cannot protect calls sent elsewhere or incorrect configured prices.
