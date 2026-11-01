#!/usr/bin/env python3
"""Create an SVG-only standalone extension release (no unrelated project assets)."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
files = [root / name for name in ('logo_construction.py', 'logo_construction.inx',
                                 'logo_construction_reference.inx', 'LOGO_CONSTRUCTION_README.md',
                                 'LOGO_CONSTRUCTION_TEST_REPORT.md', 'LICENSE',
                                 'tests/test_logo_construction.py', 'tests/run_tests.py',
                                 'tools/make_logo_construction_example.py', 'tools/package_logo_construction.py')]
files += sorted((root / 'examples' / 'logo_construction').glob('*.svg'))
output = root / 'dist' / 'Logo-Construction-1.0.0.zip'
output.parent.mkdir(exist_ok=True)
for path in files:
    if not path.is_file():
        raise SystemExit(f'Missing release file: {path}')
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, str(Path('Logo-Construction') / path.relative_to(root)))
print(output)
