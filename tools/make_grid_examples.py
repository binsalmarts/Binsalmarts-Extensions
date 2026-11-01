#!/usr/bin/env python3
"""Generate four editable Modern Grid examples using the actual extension."""
import argparse
import io
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--inkex-dir")
parser.add_argument("--extra-packages")
args = parser.parse_args()
for path in (args.inkex_dir, args.extra_packages):
    if path:
        sys.path.append(path)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modern_grid"))
from lxml import etree
from modern_grid import ModernGrid

output = ROOT / "examples/modern_grid"
output.mkdir(parents=True, exist_ok=True)
for tab, title, options in [
    ("column", "12-column layout", ["--col_color=#6757e8", "--col_opacity=0.35"]),
    ("row", "8-row layout", ["--row_color=#0f968c", "--row_opacity=0.35"]),
    ("grid", "Modular grid", ["--grd_columns=6", "--grd_rows=4", "--grd_color=#456de5", "--grd_opacity=0.35"]),
    ("bento", "Bento grid", ["--bto_seed=42", "--bto_color=#e27145", "--bto_opacity=0.35"]),
]:
    source = f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="640" viewBox="0 0 960 640">
    <rect width="960" height="640" fill="#f7f8fc"/>
    <text x="50" y="82" style="font-family:sans-serif;font-size:32px;fill:#18223c">Modern Grid / {title}</text>
    <rect x="50" y="120" width="860" height="460" rx="12" fill="white"/>
    </svg>'''
    extension = ModernGrid()
    extension.options = extension.arg_parser.parse_args([f"--tab={tab}"] + options)
    extension.load(io.BytesIO(source.encode()))
    extension.effect()
    etree.ElementTree(extension.svg).write(str(output / f"{tab}.svg"), encoding="UTF-8", xml_declaration=True)
    print(output / f"{tab}.svg")
