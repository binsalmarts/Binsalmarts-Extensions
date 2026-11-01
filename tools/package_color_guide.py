#!/usr/bin/env python3
"""Build the standalone Color Guide Pro ZIP with editable SVG examples."""
import json
from pathlib import Path
from build_release import package_files,write_zip

root=Path(__file__).resolve().parents[1]
package=next(p for p in json.loads((root/'tools/release_manifest.json').read_text())['packages'] if p['name']=='Color-Guide-Pro')
write_zip(root/'dist'/f'Color-Guide-Pro-{package["version"]}.zip',package_files(package))
