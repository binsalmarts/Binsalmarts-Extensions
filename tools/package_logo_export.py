#!/usr/bin/env python3
"""Build the standalone Logo Export Pro release."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
output = root / 'dist' / 'Logo-Export-Pro-2.0.0.zip'
files = {
    'logo_export_pro.py': root / 'logo_export_pro.py',
    'logo_export_kit.py': root / 'logo_export_kit.py',
    'logo_export_pro.inx': root / 'logo_export_pro.inx',
    'README.md': root / 'LOGO_EXPORT_README.md',
    'LICENSE': root / 'LICENSE',
}
for example in sorted((root / 'examples/logo_export').glob('*.svg')):
    files['examples/' + example.name] = example
for source in files.values():
    if not source.is_file():
        raise SystemExit(f'Missing release file: {source}')
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name, source in files.items():
        archive.write(source, 'Logo-Export-Pro/' + name)
print(output)
