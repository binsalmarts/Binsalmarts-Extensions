#!/usr/bin/env python3
"""Build the standalone Vector Effects Pro distribution with SVG examples only."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
names = ['vector_effects_pro.py', 'vector_effects_pro.inx', 'vector_effects_manage.inx',
         'vector_effects_grain.inx', 'vector_effects_noise.inx',
         'VECTOR_EFFECTS_README.md', 'VECTOR_EFFECTS_TEST_REPORT.md', 'LICENSE',
         'tests/test_vector_effects_pro.py', 'tests/run_tests.py',
         'tools/make_vector_effects_examples.py', 'tools/package_vector_effects.py']
files = [root / name for name in names] + sorted((root / 'examples/vector_effects').glob('*.svg'))
output = root / 'dist/Vector-Effects-Pro-1.2.0.zip'
output.parent.mkdir(exist_ok=True)
for path in files:
    if not path.is_file():
        raise SystemExit(f'Missing release file: {path}')
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, str(Path('Vector-Effects-Pro') / path.relative_to(root)))
print(output)
