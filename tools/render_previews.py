#!/usr/bin/env python3
"""Render README previews from committed SVGs and existing screenshots."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--inkscape", default="inkscape")
args = parser.parse_args()
output = ROOT / "docs/images"
output.mkdir(parents=True, exist_ok=True)
for name, source in {
    "ascii-art": "examples/color.png",
    "page-numbering": "examples/page_numbering/preview.png",
    "artboard-maker": "examples/artboard_maker/mixed_preview.png",
}.items():
    shutil.copyfile(ROOT / source, output / f"{name}.png")
for name, source in {
    "logo-export": "examples/logo_export/named-templates.svg",
    "modern-grid": "examples/modern_grid/grid.svg",
    "blend-tool": "examples/blend_tool/blend-3d-demo.svg",
    "logo-construction": "examples/logo_construction/construction-demo.svg",
    "vector-effects": "examples/vector_effects/effects-gallery.svg",
}.items():
    subprocess.run([args.inkscape, str(ROOT / source), "--export-type=png", "--export-width=1200",
                    "--export-background=white", f"--export-filename={output / (name + '.png')}"], check=True)
    print(output / f"{name}.png")
