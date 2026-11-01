#!/usr/bin/env python3
"""Generate the public Logo Export example from self-contained vector artwork."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inkex-dir')
parser.add_argument('--extra-packages')
args = parser.parse_args()
for path in (args.inkex_dir, args.extra_packages):
    if path:
        sys.path.append(path)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_logo_export_kit import fixture

output = ROOT / 'examples/logo_export/named-templates.svg'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(fixture())
print(output)
