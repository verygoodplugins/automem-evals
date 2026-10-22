"""Refresh existing generated views using live archives plus this branch's artifacts.

Run from the repository root with --data-root pointing to the raw-results checkout.
Historical score parsing remains the existing generator's responsibility.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts import experiment_index as dashboard

original_discover = dashboard.discover_artifacts
original_write = dashboard.write_outputs

def discover_with_overlay(data_root):
    artifacts = {a['path']: a for a in original_discover(data_root)}
    artifacts.update({a['path']: a for a in original_discover(ROOT)})
    return list(artifacts.values())

def write_with_provenance(index, *args):
    index['artifact_overlay_root'] = str(ROOT)
    return original_write(index, *args)

dashboard.discover_artifacts = discover_with_overlay
dashboard.write_outputs = write_with_provenance
if __name__ == '__main__':
    raise SystemExit(dashboard.main())
