"""Launch only a disposable real API, with write-on-recall disabled."""

import sys

sys.path.insert(0, "/app")
import automem.enrichment.runtime_queue_bindings as bindings

bindings._update_last_accessed_runtime = lambda **_kwargs: None
import app

app.init_enrichment_pipeline = lambda: None
app.init_consolidation_scheduler = lambda: None
app.init_sync_worker = lambda: None
app.run_default_server(module=app)
