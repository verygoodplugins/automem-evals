"""Launch the real server with background mutation disabled for this diagnostic."""
import sys
sys.path.insert(0, "/app")
import app

app.init_enrichment_pipeline = lambda: None
app.init_consolidation_scheduler = lambda: None
app.init_sync_worker = lambda: None
app.run_default_server(module=app)
