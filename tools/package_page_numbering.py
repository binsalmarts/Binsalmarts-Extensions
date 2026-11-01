#!/usr/bin/env python3
"""Package the page numbering extension independently of ASCII Art Pro."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
output = root / "dist" / "Page-Numbering-Pro-1.2.0.zip"
output.parent.mkdir(exist_ok=True)
files = [root / name for name in ("page_numbering_pro.py", "page_numbering_pro.inx",
                                 "PAGE_NUMBERING_README.md", "LICENSE")]
files += sorted((root / "examples" / "page_numbering").glob("*.svg"))
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, str(Path("Page-Numbering-Pro") / path.relative_to(root)))
print(output)
