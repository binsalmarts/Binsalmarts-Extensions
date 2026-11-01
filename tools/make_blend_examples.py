#!/usr/bin/env python3
"""Generate SVG-only Blend Tool Pro examples from native vector shapes."""
import argparse
import io
import math
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--inkex-dir')
parser.add_argument('--extra-packages')
args = parser.parse_args()
for path in (args.inkex_dir, args.extra_packages):
    if path:
        sys.path.append(path)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import inkex
from lxml import etree
from blend_tool_pro import BlendToolPro

output = ROOT / 'examples' / 'blend_tool'
output.mkdir(parents=True, exist_ok=True)


def star(cx, cy, radius, inner, count=5):
    points = []
    for i in range(count * 2):
        angle = -math.pi / 2 + i * math.pi / count
        r = radius if i % 2 == 0 else inner
        points.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    return 'M' + ' L'.join(f'{x:.6f},{y:.6f}' for x, y in points) + ' Z'


def apply(svg, args):
    ex = BlendToolPro()
    ex.options = ex.arg_parser.parse_args(args)
    ex.load(io.BytesIO(etree.tostring(svg)))
    ex.effect()
    return ex.svg


source = '''<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
 width="1000" height="600" viewBox="0 0 1000 600">
 <sodipodi:namedview xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" pagecolor="#ffffff" inkscape:pageopacity="1"/>
 <rect width="1000" height="600" fill="white"/>
 <text x="70" y="70" style="font-family:sans-serif;font-size:26px;fill:#17243d">Blend Tool Pro — select both colored shapes</text>
 <text x="70" y="105" style="font-family:sans-serif;font-size:15px;fill:#68748c">For a curved blend: enable Follow a curved spine and enter spine ID: guide</text>
 <g id="artwork">
   <circle id="blend-start" cx="180" cy="340" r="32" fill="#ff744f"/>
   <rect id="blend-end" x="750" y="285" width="110" height="110" fill="#5b44e8"/>
 </g>
 <path id="guide" d="M180,340 C320,90 650,90 805,340" style="fill:none;stroke:#c2c9d5;stroke-width:1;stroke-dasharray:5,5"/>
</svg>'''
svg = inkex.load_svg(io.BytesIO(source.encode())).getroot()
etree.ElementTree(svg).write(str(output / 'blend-source.svg'), encoding='UTF-8', xml_declaration=True)
straight = apply(svg, ['--id=blend-start', '--id=blend-end', '--steps=14'])
etree.ElementTree(straight).write(str(output / 'blend-straight.svg'), encoding='UTF-8', xml_declaration=True)
curved = apply(svg, ['--id=blend-start', '--id=blend-end', '--steps=22', '--follow_spine=true',
                      '--spine_id=guide', '--orientation=path'])
etree.ElementTree(curved).write(str(output / 'blend-curved.svg'), encoding='UTF-8', xml_declaration=True)

demo = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
 width="1280" height="1080" viewBox="0 0 1280 1080">
 <sodipodi:namedview xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" pagecolor="#ffffff" inkscape:pageopacity="1"/>
 <rect width="1280" height="1080" fill="#f4f6fa"/>
 <text x="64" y="61" style="font-family:sans-serif;font-size:12px;letter-spacing:2px;fill:#6c7892">BINSALMARTS / INKSCAPE EXTENSIONS</text>
 <text x="64" y="113" style="font-family:sans-serif;font-weight:600;font-size:38px;fill:#17243d">Blend Tool Pro</text>
 <text x="64" y="146" style="font-family:sans-serif;font-size:16px;fill:#68748c">Shape, size and color transitions. Editable SVG paths. Original endpoints preserved.</text>
 <rect x="48" y="184" width="1184" height="220" rx="16" fill="white"/>
 <rect x="48" y="424" width="1184" height="290" rx="16" fill="white"/>
 <rect x="48" y="734" width="1184" height="242" rx="16" fill="white"/>
 <g style="font-family:sans-serif;font-size:14px;fill:#68748c">
   <text x="80" y="221">01 / SHAPE + COLOR · 12 intermediate objects</text>
   <text x="80" y="461">02 / CURVED SPINE · 80 overlapping steps</text>
   <text x="80" y="771">03 / MULTI-STAGE · 6 steps per stage · editable strokes</text>
 </g>
 <g id="example-morph">
   <circle id="morph-a" cx="140" cy="306" r="22" fill="#ff744f"/>
   <path id="morph-b" d="{star(1110,306,62,28)}" fill="#5b44e8"/>
 </g>
 <g id="example-spine">
   <circle id="curve-a" cx="145" cy="650" r="30" fill="#ff744f"/>
   <circle id="curve-b" cx="1110" cy="650" r="42" fill="#4d43de"/>
 </g>
 <path id="curved-guide" d="M145,650 C360,490 850,490 1110,650" style="display:none;fill:none"/>
 <g id="example-stages" fill="none" stroke-width="1.6">
   <circle id="stage-a" cx="145" cy="872" r="26" stroke="#ff744f"/>
   <path id="stage-b" d="{star(640,872,43,23)}" stroke="#b44eea"/>
   <rect id="stage-c" x="1070" y="842" width="80" height="60" stroke="#3c65e8"/>
 </g>
 <text x="64" y="1016" style="font-family:sans-serif;font-size:14px;fill:#17243d">Edit an original → select its generated blend group → Manage Blend → Refresh saved settings.</text>
 <text x="64" y="1047" style="font-family:sans-serif;font-size:13px;fill:#68748c">Save as Inkscape SVG. Release removes intermediates. Expand keeps the paths and detaches update metadata.</text>
</svg>'''
svg = inkex.load_svg(io.BytesIO(demo.encode())).getroot()
for options in [
    ['--id=morph-a', '--id=morph-b', '--steps=12', '--group_name=01 · Morph + color'],
    ['--id=curve-a', '--id=curve-b', '--steps=80', '--follow_spine=true', '--spine_id=curved-guide', '--group_name=02 · Curved blend'],
    ['--id=stage-a', '--id=stage-b', '--id=stage-c', '--steps=6', '--order=left_right', '--group_name=03 · Multiple stages']]:
    svg = apply(svg, options)
etree.ElementTree(svg).write(str(output / 'blend-demo.svg'), encoding='UTF-8', xml_declaration=True)
print(output / 'blend-demo.svg')

lighting_demo = '''<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
 width="1280" height="1100" viewBox="0 0 1280 1100">
 <sodipodi:namedview xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" pagecolor="#ffffff" inkscape:pageopacity="1"/>
 <rect width="1280" height="1100" fill="#f4f6fa"/>
 <text x="64" y="61" style="font-family:sans-serif;font-size:12px;letter-spacing:2px;fill:#6c7892">BINSALMARTS / BLEND TOOL PRO 1.1</text>
 <text x="64" y="113" style="font-family:sans-serif;font-weight:600;font-size:38px;fill:#17243d">A new dimension for your blends</text>
 <text x="64" y="146" style="font-family:sans-serif;font-size:16px;fill:#68748c">Directional lighting, glossy highlights and cast shadows. All editable SVG vectors.</text>
 <rect x="48" y="184" width="1184" height="244" rx="16" fill="white"/>
 <rect x="48" y="448" width="1184" height="290" rx="16" fill="white"/>
 <rect x="48" y="758" width="1184" height="252" rx="16" fill="white"/>
 <g style="font-family:sans-serif;font-size:14px;fill:#68748c">
   <text x="80" y="221">01 / FLAT BLEND · shading off</text>
   <text x="80" y="485">02 / ROUNDED TUBE · light + gloss + vector shadow</text>
   <text x="80" y="795">03 / ROUNDED BEADS · soft surface and focused highlights</text>
 </g>
 <g id="flat-example">
   <circle id="flat-a" cx="145" cy="365" r="30" fill="#ff744f"/>
   <circle id="flat-b" cx="1110" cy="365" r="42" fill="#5b44e8"/>
 </g>
 <path id="flat-guide" d="M145,365 C360,245 850,245 1110,365" style="display:none;fill:none"/>
 <g id="tube-example">
   <circle id="tube-a" cx="145" cy="680" r="30" fill="#ff744f"/>
   <circle id="tube-b" cx="1110" cy="680" r="42" fill="#5b44e8"/>
 </g>
 <path id="tube-guide" d="M145,680 C360,560 850,560 1110,680" style="display:none;fill:none"/>
 <g id="bead-example">
   <circle id="bead-a" cx="145" cy="900" r="28" fill="#ff744f"/>
   <circle id="bead-b" cx="1110" cy="900" r="45" fill="#5b44e8"/>
 </g>
 <text x="64" y="1050" style="font-family:sans-serif;font-size:14px;fill:#17243d">Blend Tool Pro → 3D → Rounded tube or Rounded beads. Adjust light, depth and highlights.</text>
 <text x="64" y="1078" style="font-family:sans-serif;font-size:13px;fill:#68748c">Originals stay intact. Lighting uses SVG gradients; the optional cast shadow is an editable vector group.</text>
</svg>'''
svg = inkex.load_svg(io.BytesIO(lighting_demo.encode())).getroot()
for options in [
    ['--id=flat-a', '--id=flat-b', '--steps=110', '--follow_spine=true', '--spine_id=flat-guide', '--group_name=01 · Flat blend'],
    ['--id=tube-a', '--id=tube-b', '--steps=110', '--follow_spine=true', '--spine_id=tube-guide',
     '--shading_mode=tube', '--cast_shadow=true', '--shadow_distance=12', '--light_angle=225', '--gloss=0.55',
     '--group_name=02 · 3D tube'],
    ['--id=bead-a', '--id=bead-b', '--steps=8', '--shading_mode=sphere', '--cast_shadow=true',
     '--light_angle=225', '--gloss=0.65', '--shadow_opacity=0.1', '--group_name=03 · 3D beads']]:
    svg = apply(svg, options)
etree.ElementTree(svg).write(str(output / 'blend-3d-demo.svg'), encoding='UTF-8', xml_declaration=True)
print(output / 'blend-3d-demo.svg')
