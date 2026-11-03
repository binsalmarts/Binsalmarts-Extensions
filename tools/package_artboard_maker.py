#!/usr/bin/env python3
"""Build the standalone Artboard Maker Pro release."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
output = root / "dist" / "Artboard-Maker-Pro-1.1.0.zip"
files = [root / name for name in ("artboard_maker_pro.py", "artboard_maker_pro.inx", "ARTBOARD_MAKER_README.md", "LICENSE")]
files += sorted((root / "examples" / "artboard_maker").glob("*.svg"))
output.parent.mkdir(exist_ok=True)
for path in files:
    if not path.is_file():
        raise SystemExit(f"Missing release file: {path}")
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, str(Path("Artboard-Maker-Pro") / path.relative_to(root)))
print(output)
