#!/usr/bin/env python3
"""Build the SVG-only demo with text outlined by Inkscape, then annotate it."""
import argparse
import io
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--inkex-dir')
parser.add_argument('--extra-packages')
parser.add_argument('--inkscape', default='inkscape')
args = parser.parse_args()
for path in (args.inkex_dir, args.extra_packages):
    if path:
        sys.path.append(path)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import inkex
from lxml import etree
from logo_construction import LogoConstruction, REFERENCE, number

source = '''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="720" viewBox="0 0 1000 720">
  <g id="logo" fill="#24354b">
    <text id="arabic" x="0" y="100" style="font-family:Arial;font-size:100px;direction:rtl;text-anchor:end">نواة</text>
    <text id="english" x="0" y="220" style="font-family:Arial;font-weight:bold;font-size:100px;letter-spacing:6px">NAWA</text>
    <g id="x-reference" transform="translate(545,290)">
      <path d="M25,0 H75 Q100,0 100,25 V75 Q100,100 75,100 H25 Q0,100 0,75 V25 Q0,0 25,0 Z
               M25,38 V70 H37 V51 L63,70 H75 V30 H63 V49 L37,30 H25 Z" fill-rule="evenodd"/>
    </g>
  </g>
</svg>'''
with tempfile.TemporaryDirectory() as td:
    src, dest = Path(td) / 'text.svg', Path(td) / 'outlined.svg'
    src.write_text(source, encoding='utf-8')
    result = subprocess.run([args.inkscape, str(src), '--actions=select-by-id:arabic,english;object-to-path',
                             '--export-type=svg', '--export-filename=' + str(dest)],
                            capture_output=True, text=True, timeout=45)
    if result.returncode or not dest.is_file():
        raise SystemExit(result.stderr or 'Inkscape did not create the outlined SVG')
    svg = inkex.load_svg(str(dest)).getroot()

# Scale the demo wordmarks to known geometric bounds, including descenders/dots.
ex = LogoConstruction()
ex.svg = svg
for element_id, x, y, width, height in [('arabic', 235, 290, 285, 50), ('english', 235, 360, 285, 55)]:
    el = svg.getElementById(element_id)
    box = ex.union(ex.collect(el))
    sx, sy = width / box.width, height / box.height
    el.attrib['transform'] = f'matrix({number(sx)},0,0,{number(sy)},{number(x - sx*box.left)},{number(y - sy*box.top)})'

svg.set(REFERENCE, 'x-reference')
namedview = svg.find(inkex.addNS('namedview', 'sodipodi'))
if namedview is None:
    namedview = inkex.NamedView()
    svg.insert(0, namedview)
namedview.set('pagecolor', '#ffffff')
namedview.set('inkscape:pageopacity', '1')
for x, y, size, text, fill in [
    (80, 65, 13, 'LOGO CONSTRUCTION / EDITABLE SVG', '#718096'),
    (80, 108, 32, 'NAWA — construction study', '#24354b'),
    (80, 142, 14, 'X = icon width · 100 SVG units. Original paths + independent annotation layers.', '#718096'),
    (80, 635, 15, '0.25X = 25-unit horizontal gap      0.2X = 20-unit vertical gap', '#24354b'),
    (80, 665, 13, 'Select logo → Extensions → Logo Construction. Reference ID: x-reference', '#718096'),
    (80, 688, 13, 'Labels remain text. Move them freely; save as Inkscape SVG to keep layer organization.', '#718096')]:
    node = inkex.TextElement(x=str(x), y=str(y))
    node.text = text
    node.style = {'font-family': 'sans-serif', 'font-size': str(size), 'fill': fill}
    svg.append(node)

output = ROOT / 'examples' / 'logo_construction'
output.mkdir(parents=True, exist_ok=True)
etree.ElementTree(svg).write(str(output / 'source-logo.svg'), encoding='utf-8', xml_declaration=True)
ex = LogoConstruction()
ex.options = ex.arg_parser.parse_args(['--id=logo', '--background=panel', '--show_outlines=true',
                                       '--dimension_style=bar', '--font_size=13', '--node_size=3',
                                       '--line_width=0.6', '--dimension_offset=0.4'])
ex.load(io.BytesIO(etree.tostring(svg)))
ex.effect()
etree.ElementTree(ex.svg).write(str(output / 'construction-demo.svg'), encoding='utf-8', xml_declaration=True)
print(output / 'construction-demo.svg')
