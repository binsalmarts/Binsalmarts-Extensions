#!/usr/bin/env python3
"""Package the theme without caches or local installation state."""
from pathlib import Path
import hashlib
import zipfile

root = Path(__file__).resolve().parent
output = root.parent / "dist/Studio-Dark-Compact-2.3.zip"
output.parent.mkdir(exist_ok=True)
paths = sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store" and not p.name.startswith(("preview-compact-v2.", "preview-wheel-v2.", "preview-balanced-v21.", "preview-wheel-v21.", "preview-soft-v22.", "preview-controls-before-v23.")))
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in paths:
        archive.write(path, "Studio-Dark-Compact/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
checksum = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix(".zip.sha256").write_text(checksum + "  " + output.name + "\n")
print(str(output))
print("SHA256: " + checksum)
