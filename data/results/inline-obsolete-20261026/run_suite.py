"""Run the unchanged frozen free suite against an already isolated local stack."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--adapter', type=Path, required=True)
parser.add_argument('--upstream', type=Path, required=True)
parser.add_argument('--checkout', type=Path, required=True)
parser.add_argument('--revision', required=True)
parser.add_argument('--endpoint', required=True)
parser.add_argument('--graph', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
expected = '29bfb22c154a0c7d427fbd7931197de58f80422482f2cad2c069b2a147158ba6'
assert hashlib.sha256(args.adapter.read_bytes()).hexdigest() == expected
spec = importlib.util.spec_from_file_location('forgeteval_frozen', args.adapter)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.AUTOMEM_REVISION = args.revision
os.environ['AUTOMEM_CHECKOUT'] = str(args.checkout.resolve())
sys.argv = [str(args.adapter), '--upstream', str(args.upstream), '--endpoint', args.endpoint,
            '--graph', args.graph, '--output', str(args.output)]
module.main()
