#!/usr/bin/env python3
"""Generate editable native-page examples with sample artwork for visibility."""
import argparse
import io
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--inkex-dir")
parser.add_argument("--extra-packages")
options = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
for dependency in (options.inkex_dir, options.extra_packages):
    if dependency:
        sys.path.append(dependency)

import inkex
from lxml import etree
from artboard_maker_pro import ArtboardMakerPro, svg_number

output = root / "examples" / "artboard_maker"
output.mkdir(parents=True, exist_ok=True)
source = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS["inkscape"]}" '
          f'xmlns:sodipodi="{inkex.NSS["sodipodi"]}" width="800" height="600" viewBox="0 0 800 600"/>').encode()
variants = {
    "uniform": ["--width=320", "--height=240", "--gap_x=40", "--gap_y=50"],
    "mixed": ["--size_mode=mixed", "--mixed_sizes=320x240; 240x360; 400x240; 320x180; 240x300; 400x180",
              "--gap_x=40", "--gap_y=50"],
}
colors = ("#2563eb", "#7c3aed", "#0f766e", "#e11d48", "#b45309", "#4338ca")
for name, arguments in variants.items():
    extension = ArtboardMakerPro()
    extension.options = extension.arg_parser.parse_args(arguments)
    extension.load(io.BytesIO(source))
    extension.effect()
    native = extension.svg.find(inkex.addNS("namedview", "sodipodi")).findall(inkex.addNS("page", "inkscape"))
    layer = inkex.Layer()
    layer.set("inkscape:label", "Example artwork")
    extension.svg.append(layer)
    for index, page in enumerate(native):
        x, y, width, height = page.x, page.y, page.width, page.height
        group = inkex.Group()
        group.set("inkscape:label", page.get("inkscape:label"))
        layer.append(group)
        group.append(inkex.Rectangle(x=svg_number(x), y=svg_number(y), width=svg_number(width),
                                     height=svg_number(height), style="fill:#ffffff;stroke:#cbd5e1;stroke-width:1"))
        group.append(inkex.Rectangle(x=svg_number(x + 20), y=svg_number(y + 20), width=svg_number(width - 40),
                                     height="5", rx="2", style="fill:" + colors[index % len(colors)]))
        for offset, content, size, color in ((62, page.get("inkscape:label"), 23, "#172033"),
                                              (91, f"{width:g} × {height:g} px", 16, "#64748b")):
            text = inkex.TextElement(x=svg_number(x + 20), y=svg_number(y + offset))
            text.text = content
            text.style = {"font-family": "sans-serif", "font-size": f"{size}px", "fill": color}
            group.append(text)
        group.append(inkex.Rectangle(x=svg_number(x + 20), y=svg_number(y + 115), width=svg_number(width - 40),
                                     height=svg_number(height - 135), rx="8", style="fill:#f1f5f9"))
    etree.ElementTree(extension.svg).write(str(output / f"{name}.svg"), encoding="UTF-8", xml_declaration=True)
    print(output / f"{name}.svg")
