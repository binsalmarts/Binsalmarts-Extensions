#!/usr/bin/env python3
"""Build the installable archive without development tools or test dependencies."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
output = root / "dist" / "ASCII-Art-Pro-1.2.0.zip"
output.parent.mkdir(exist_ok=True)
files = [root / name for name in ("ascii_art_pro.py", "ascii_art_pro.inx", "ASCII_ART_README.md", "LICENSE")]
files += sorted((root / "examples").glob("*.svg"))
for path in files:
    if not path.is_file():
        raise SystemExit(f"Missing release file: {path}")
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, str(Path("ASCII-Art-Pro") / path.relative_to(root)))
print(output)
