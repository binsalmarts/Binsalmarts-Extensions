#!/usr/bin/env python3
"""Create editable SVG examples for the standalone page numbering extension."""
import argparse
import io
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--inkex-dir")
parser.add_argument("--extra-packages")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
for path in (args.inkex_dir, args.extra_packages):
    if path:
        sys.path.append(path)

import inkex
from lxml import etree
from page_numbering_pro import PageNumberingPro

output = root / "examples" / "page_numbering"
output.mkdir(parents=True, exist_ok=True)
positions = (0, 350, 700)
pages = "".join(f'<inkscape:page id="page-{i}" x="{x}" y="0" width="320" height="420"/>'
                for i, x in enumerate(positions, 1))
art = ""
for index, x in enumerate(positions, 1):
    art += (f'<rect x="{x}" y="0" width="320" height="420" fill="#ffffff"/>'
            f'<rect x="{x + 24}" y="24" width="272" height="5" rx="2" fill="#2563eb"/>'
            f'<text x="{x + 296}" y="65" style="font-family:sans-serif;font-size:22px;text-anchor:start;direction:rtl;fill:#172033">صفحة {index}</text>')
    for row in range(7):
        art += f'<rect x="{x + 24}" y="{100 + row * 22}" width="{272 if row % 3 else 210}" height="7" rx="3" fill="#dce3ed"/>'
    art += (f'<rect x="{x + 24}" y="280" width="272" height="64" rx="8" fill="#eff6ff"/>'
            f'<line x1="{x + 24}" y1="366" x2="{x + 296}" y2="366" stroke="#dce3ed"/>')
source = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS["inkscape"]}" '
          f'xmlns:sodipodi="{inkex.NSS["sodipodi"]}" width="320" height="420" viewBox="0 0 320 420">'
          f'<sodipodi:namedview id="namedview">{pages}</sodipodi:namedview>{art}</svg>').encode()
(output / "input.svg").write_bytes(source)


def convert(content, options):
    extension = PageNumberingPro()
    extension.options = extension.arg_parser.parse_args(options)
    extension.load(io.BytesIO(content))
    extension.effect()
    return extension


def save(extension, name):
    etree.ElementTree(extension.svg).write(str(output / name), encoding="utf-8", xml_declaration=True)


numbered = convert(source, [])
save(numbered, "numbered.svg")
target = numbered.existing_numbers()[1]
updated = convert(etree.tostring(numbered.svg), ["--id=" + target.get("id"), "--change_selected_value=true",
                                               "--selected_number=8", "--color=#2563eb", "--font_size=22"])
save(updated, "selected_updated.svg")
arabic = convert(source, ["--digits=indic", "--alignment=right", "--side_margin=24",
                         "--color=#2563eb", "--font_size=20", "--font_style=bold"])
save(arabic, "arabic_digits.svg")
save(convert(source, ["--minimum_digits=3", "--font_size=20"]), "leading_zeros.svg")
save(convert(source, ["--minimum_digits=3", "--digits=indic", "--font_size=20"]),
     "arabic_leading_zeros.svg")
top = convert(source, ["--vertical_position=top", "--bottom_margin=60", "--font_size=24",
                       "--color=#7c3aed", "--font_style=bold"])
save(top, "top_center.svg")
model_source = inkex.load_svg(io.BytesIO(source)).getroot()
model = inkex.TextElement(id="designed-number", x="160", y="398")
model.style = {"font-family": "serif", "font-size": "32px", "font-weight": "bold",
               "font-style": "italic", "fill": "#b42367", "text-anchor": "middle"}
span = inkex.Tspan(id="designed-number-span", x="160", y="398")
span.text = "1"
model.append(span)
model_source.append(model)
etree.ElementTree(model_source).write(str(output / "template_input.svg"), encoding="utf-8", xml_declaration=True)
template = convert(etree.tostring(model_source), ["--placement_mode=template", "--id=designed-number"])
save(template, "template_numbered.svg")
target = template.existing_numbers()[1]
cascade = convert(etree.tostring(template.svg), ["--id=" + target.get("id"), "--placement_mode=template",
                                                "--change_selected_value=true", "--selected_number=3",
                                                "--renumber_following=true"])
save(cascade, "cascade_updated.svg")
single = inkex.load_svg(io.BytesIO(source)).getroot()
namedview = single.find(inkex.addNS("namedview", "sodipodi"))
for page in list(namedview):
    namedview.remove(page)
for element in list(single):
    x = element.get("x") or element.get("x1")
    if x is not None and float(x) >= 350:
        single.remove(element)
save(convert(etree.tostring(single), ["--font_size=18"]), "single_page.svg")
print(output)
