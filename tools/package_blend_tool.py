#!/usr/bin/env python3
"""Package only the standalone Blend Tool Pro extension and SVG examples."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
names = ['blend_tool_pro.py', 'blend_tool_pro.inx', 'blend_tool_manage.inx', 'blend_tool_spine.inx',
         'BLEND_TOOL_README.md', 'BLEND_TOOL_TEST_REPORT.md', 'LICENSE',
         'tests/test_blend_tool_pro.py', 'tests/run_tests.py',
         'tools/make_blend_examples.py', 'tools/package_blend_tool.py']
files = [root / name for name in names] + sorted((root / 'examples/blend_tool').glob('*.svg'))
output = root / 'dist/Blend-Tool-Pro-1.1.0.zip'
output.parent.mkdir(exist_ok=True)
for path in files:
    if not path.is_file():
        raise SystemExit(f'Missing release file: {path}')
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, str(Path('Blend-Tool-Pro') / path.relative_to(root)))
print(output)
