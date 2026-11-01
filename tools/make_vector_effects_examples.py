#!/usr/bin/env python3
"""Build SVG sources and a gallery with the actual Vector Effects Pro engine."""
import argparse
import io
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
from vector_effects_pro import VectorEffectsPro

output = ROOT / 'examples/vector_effects'
output.mkdir(parents=True, exist_ok=True)
NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
VIEW = '<sodipodi:namedview xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" pagecolor="#ffffff" inkscape:pageopacity="1"/>'
MOTIF = 'M-95,-33 H95 V33 H-95 Z M-55,-15 H-35 V15 H-55 Z M-10,-15 H10 V15 H-10 Z M35,-15 H55 V15 H35 Z'


def apply(svg, *options):
    ex = VectorEffectsPro()
    ex.options = ex.arg_parser.parse_args(options)
    ex.load(io.BytesIO(etree.tostring(svg)))
    ex.effect()
    return ex.svg


def save(svg, filename):
    etree.ElementTree(svg).write(str(output / filename), encoding='UTF-8', xml_declaration=True)


source = f'''<svg {NS} width="1000" height="600" viewBox="0 0 1000 600">{VIEW}
 <rect width="1000" height="600" fill="#f4f6fa"/>
 <text x="70" y="70" style="font-family:sans-serif;font-size:28px;fill:#17243d">Vector Effects Pro — editable source</text>
 <text x="70" y="108" style="font-family:sans-serif;font-size:15px;fill:#68748c">Select the purple motif. Extensions → Binsalmarts Extensions → Vector Effects Pro.</text>
 <g id="design" transform="translate(500,310) scale(2)">
  <path id="motif" d="{MOTIF}" fill="#635bff" fill-rule="evenodd"/>
 </g>
 <text x="70" y="540" style="font-family:sans-serif;font-size:14px;fill:#68748c">Original ID: design. Group paths first to warp a logo or word as one object.</text>
</svg>'''
svg = inkex.load_svg(io.BytesIO(source.encode())).getroot()
save(svg, 'effects-source.svg')
combined = apply(svg, '--id=design', '--geometry=arc', '--amount=30', '--shadow=true',
                 '--glow=true', '--glow_blur=4', '--glow_opacity=0.4', '--outline=true',
                 '--outline_width=2', '--outline_color=#ff744f')
save(combined, 'effects-combined.svg')

cards = [
    ('Original', 'Unmodified vector source', [], False),
    ('Roughen · Corner', 'Random edge displacement', ['--geometry=roughen','--size=6','--detail=12'], False),
    ('Roughen · Smooth', 'Soft irregular contours', ['--geometry=roughen','--points=smooth','--size=6'], False),
    ('Zig Zag · Corner', '12 ridges per subpath', ['--geometry=zigzag','--size=6','--zigzag_cycles=12'], False),
    ('Zig Zag · Smooth', 'Rounded repeating waves', ['--geometry=zigzag','--points=smooth','--size=6'], False),
    ('Pucker', 'Anchors out, handles in', ['--geometry=pucker_bloat','--amount=-55'], False),
    ('Bloat', 'Anchors in, handles out', ['--geometry=pucker_bloat','--amount=55'], False),
    ('Warp · Arc', 'Circular bend, 35%', ['--geometry=arc','--amount=35'], False),
    ('Warp · Bulge', 'Expanded middle, 70%', ['--geometry=bulge','--amount=70'], False),
    ('Warp · Wave', 'Smooth sinusoidal warp', ['--geometry=wave','--size=14','--wave_cycles=1'], False),
    ('Drop Shadow', 'Offset and Gaussian softness', ['--geometry=none','--shadow=true','--shadow_blur=5'], False),
    ('Inner Shadow', 'Carved appearance inside alpha', ['--geometry=none','--shadow=true','--shadow_mode=inner','--shadow_opacity=0.7','--shadow_dx=5','--shadow_dy=5'], False),
    ('Outer Glow', 'Colored light behind the object', ['--geometry=none','--glow=true','--glow_color=#65b8ff','--glow_opacity=0.9'], True),
    ('Inner Glow', 'Soft light clipped to the interior', ['--geometry=none','--glow=true','--glow_mode=inner','--glow_color=#ffffff','--glow_opacity=0.9','--glow_spread=0'], True),
    ('Outline · Outside', 'Four-pixel external edge', ['--geometry=none','--outline=true','--outline_width=4','--outline_color=#ff744f'], False),
    ('Outline · Inside', 'Five-pixel internal edge', ['--geometry=none','--outline=true','--outline_position=inner','--outline_width=5','--outline_color=#21c7a8'], False),
    ('Outline · Centered', 'Straddles the existing silhouette', ['--geometry=none','--outline=true','--outline_position=center','--outline_width=4','--outline_color=#ff744f'], False),
    ('Combined effects', 'Arc + shadow + glow + edge', ['--geometry=arc','--amount=30','--shadow=true','--glow=true','--glow_blur=3','--glow_opacity=0.4','--outline=true','--outline_width=2','--outline_color=#ff744f'], False),
]
body = [f'<svg {NS} width="1280" height="1770" viewBox="0 0 1280 1770">', VIEW,
        '<rect width="1280" height="1770" fill="#f4f6fa"/>',
        '<text x="48" y="59" style="font-family:sans-serif;font-size:12px;letter-spacing:2px;fill:#6c7892">BINSALMARTS / INKSCAPE EXTENSIONS</text>',
        '<text x="48" y="111" style="font-family:sans-serif;font-size:38px;font-weight:600;fill:#17243d">Vector Effects Pro</text>',
        '<text x="48" y="147" style="font-family:sans-serif;font-size:16px;fill:#68748c">Distort, warp, shade and glow. Editable paths + standard SVG filters. Original artwork preserved.</text>']
for index, (title, subtitle, options, dark) in enumerate(cards):
    col, row = index % 3, index // 3
    x, y = 40 + col * 408, 184 + row * 252
    text_color, muted = ('#f4f6fa', '#b4c1da') if dark else ('#17243d', '#68748c')
    bg = '#17243d' if dark else '#ffffff'
    fill = '#a0d9ff' if title == 'Outer Glow' else '#635bff'
    body.extend([f'<g id="card-{index}">',
                 f'<rect x="{x}" y="{y}" width="384" height="228" rx="16" fill="{bg}"/>',
                 f'<text x="{x+24}" y="{y+34}" style="font-family:sans-serif;font-size:16px;font-weight:600;fill:{text_color}">{index+1:02d} / {title}</text>',
                 f'<text x="{x+24}" y="{y+59}" style="font-family:sans-serif;font-size:12px;fill:{muted}">{subtitle}</text>',
                 f'<g id="sample-{index}" transform="translate({x+192},{y+141})">',
                 f'<path id="motif-{index}" d="{MOTIF}" fill="{fill}" fill-rule="evenodd"/>', '</g></g>'])
body.extend(['<text x="48" y="1720" style="font-family:sans-serif;font-size:14px;fill:#17243d">Select an effect group → Manage Effects → Edit original, Refresh, or Remove effect.</text>',
             '<text x="48" y="1750" style="font-family:sans-serif;font-size:13px;fill:#68748c">All examples are generated by the extension. Save as Inkscape SVG. Shape changes are paths; appearance remains an SVG filter.</text>', '</svg>'])
svg = inkex.load_svg(io.BytesIO(''.join(body).encode())).getroot()
for index, (_, _, options, _) in enumerate(cards):
    if options:
        svg = apply(svg, '--id=sample-' + str(index), *options)
save(svg, 'effects-gallery.svg')
print(output / 'effects-gallery.svg')

gradient = '''<defs><linearGradient id="grain-gradient" x1="0" y1="0" x2="1" y2="0.35">
 <stop offset="0" stop-color="#ffad8d"/><stop offset="0.48" stop-color="#df78b4"/><stop offset="1" stop-color="#635bff"/>
 </linearGradient></defs>'''
grain_source = f'''<svg {NS} width="1000" height="600" viewBox="0 0 1000 600">{VIEW}{gradient}
 <rect width="1000" height="600" fill="#f4f6fa"/>
 <text x="70" y="70" style="font-family:sans-serif;font-size:28px;fill:#17243d">Grain — gradient source</text>
 <text x="70" y="108" style="font-family:sans-serif;font-size:15px;fill:#68748c">Select the gradient shape → Extensions → Vector Effects Pro → Grain.</text>
 <g id="grain-design" transform="translate(500,300)">
  <path id="grain-motif" d="M-300,-80 H300 V80 H-300 Z M-100,-35 H-55 V35 H-100 Z M55,-35 H100 V35 H55 Z"
   fill="url(#grain-gradient)" fill-rule="evenodd"/>
 </g>
 <text x="70" y="540" style="font-family:sans-serif;font-size:14px;fill:#68748c">Procedural SVG texture. Original gradient and transparency are preserved.</text>
</svg>'''
svg = inkex.load_svg(io.BytesIO(grain_source.encode())).getroot()
save(svg, 'grain-source.svg')
save(apply(svg, '--id=grain-design', '--geometry=none', '--grain=true', '--grain_intensity=65',
           '--grain_contrast=65', '--grain_size=1.5'), 'grain-example.svg')

grain_cards = [
    ('Original gradient', None, []), ('Regular', 'regular', []), ('Soft', 'soft', []),
    ('Sprinkles · colored', 'sprinkles', ['--grain_monochrome=false']),
    ('Clumped', 'clumped', ['--grain_size=2']), ('Contrasty', 'contrasty', []),
    ('Enlarged', 'enlarged', ['--grain_size=3']), ('Stippled', 'stippled', ['--grain_blend=multiply']),
    ('Horizontal', 'horizontal', []), ('Vertical', 'vertical', []),
    ('Speckle', 'speckle', ['--grain_blend=multiply']),
    ('Grain + shadow + edge', 'regular', ['--shadow=true','--outline=true','--outline_width=2','--outline_color=#635bff']),
]
body = [f'<svg {NS} width="1280" height="1250" viewBox="0 0 1280 1250">', VIEW, gradient,
        '<rect width="1280" height="1250" fill="#f4f6fa"/>',
        '<text x="48" y="59" style="font-family:sans-serif;font-size:12px;letter-spacing:2px;fill:#6c7892">VECTOR EFFECTS PRO 1.2 / GRAIN</text>',
        '<text x="48" y="111" style="font-family:sans-serif;font-size:38px;font-weight:600;fill:#17243d">Grain · texture your gradients</text>',
        '<text x="48" y="147" style="font-family:sans-serif;font-size:16px;fill:#68748c">Intensity, contrast, size, seed and blending. Editable SVG filters with preserved source alpha.</text>']
for index, (title, preset, extra) in enumerate(grain_cards):
    x, y = 40 + index % 3 * 408, 184 + index // 3 * 248
    body.extend([f'<g id="grain-card-{index}">',
                 f'<rect x="{x}" y="{y}" width="384" height="224" rx="16" fill="white"/>',
                 f'<text x="{x+24}" y="{y+36}" style="font-family:sans-serif;font-size:16px;font-weight:600;fill:#17243d">{index+1:02d} / {title}</text>',
                 f'<text x="{x+24}" y="{y+63}" style="font-family:sans-serif;font-size:12px;fill:#68748c">' +
                 ('Unmodified editable gradient' if preset is None else 'Procedural grain, not an embedded image') + '</text>',
                 f'<rect id="grain-sample-{index}" x="{x+40}" y="{y+96}" width="304" height="92" rx="12" fill="url(#grain-gradient)"/>', '</g>'])
body.extend(['<text x="48" y="1201" style="font-family:sans-serif;font-size:14px;fill:#17243d">Extensions → Binsalmarts Extensions → Vector Effects Pro → Grain. Or use the Grain tab in the main dialog.</text>',
             '<text x="48" y="1230" style="font-family:sans-serif;font-size:13px;fill:#68748c">These are independent visual grain presets. Adobe grain algorithms and numeric scales are not replicated exactly.</text>', '</svg>'])
svg = inkex.load_svg(io.BytesIO(''.join(body).encode())).getroot()
for index, (_, preset, extra) in enumerate(grain_cards):
    if preset is not None:
        svg = apply(svg, '--id=grain-sample-' + str(index), '--geometry=none', '--grain=true',
                    '--grain_type=' + preset, '--grain_intensity=65', '--grain_contrast=65', *extra)
save(svg, 'grain-gallery.svg')
print(output / 'grain-gallery.svg')

noise_gradient = '''<defs><linearGradient id="noise-gradient" x1="0" y1="0" x2="1" y2="0.5">
 <stop offset="0" stop-color="#6a65d8"/><stop offset="0.5" stop-color="#a671b1"/><stop offset="1" stop-color="#e59482"/>
 </linearGradient></defs>'''
noise_source = f'''<svg {NS} width="1000" height="600" viewBox="0 0 1000 600">{VIEW}{noise_gradient}
 <rect width="1000" height="600" fill="#f4f6fa"/>
 <text x="70" y="70" style="font-family:sans-serif;font-size:28px;fill:#17243d">Noise — editable gradient source</text>
 <text x="70" y="108" style="font-family:sans-serif;font-size:15px;fill:#68748c">Select the gradient shape → Extensions → Binsalmarts Extensions → Vector Effects Pro → Noise.</text>
 <g id="noise-design" transform="translate(500,300)">
  <path id="noise-motif" d="M-300,-80 H300 V80 H-300 Z M-100,-35 H-55 V35 H-100 Z M55,-35 H100 V35 H55 Z"
   fill="url(#noise-gradient)" fill-rule="evenodd"/>
 </g>
 <text x="70" y="540" style="font-family:sans-serif;font-size:14px;fill:#68748c">Select only the motif. Amount, size, seed and monochrome/colored noise are editable.</text>
</svg>'''
svg = inkex.load_svg(io.BytesIO(noise_source.encode())).getroot()
save(svg, 'noise-source.svg')
save(apply(svg, '--id=noise-design', '--geometry=none', '--noise=true', '--noise_amount=55'), 'noise-example.svg')

noise_cards = [
    ('Original gradient', None, []),
    ('Additive · monochrome', 'additive', ['--noise_amount=55']),
    ('Additive · colored', 'additive', ['--noise_amount=65', '--noise_monochrome=false']),
    ('Speckle · monochrome', 'speckle', ['--noise_amount=65']),
    ('Speckle · colored', 'speckle', ['--noise_amount=65', '--noise_monochrome=false']),
    ('Salt and Pepper', 'salt_pepper', ['--noise_amount=90', '--noise_size=1.5']),
    ('Sparse dots', 'salt_pepper', ['--noise_amount=100', '--noise_density=10']),
    ('Dense dots', 'salt_pepper', ['--noise_amount=100', '--noise_density=75']),
    ('Noise + Grain + shadow', 'additive', ['--noise_amount=35', '--grain=true', '--grain_intensity=30', '--shadow=true']),
]
body = [f'<svg {NS} width="1280" height="1020" viewBox="0 0 1280 1020">', VIEW, noise_gradient,
        '<rect width="1280" height="1020" fill="#f4f6fa"/>',
        '<text x="48" y="59" style="font-family:sans-serif;font-size:12px;letter-spacing:2px;fill:#6c7892">VECTOR EFFECTS PRO 1.2 / NOISE</text>',
        '<text x="48" y="111" style="font-family:sans-serif;font-size:38px;font-weight:600;fill:#17243d">Noise · add texture to your artwork</text>',
        '<text x="48" y="147" style="font-family:sans-serif;font-size:16px;fill:#68748c">Additive, Speckle, Salt and Pepper. Amount, size, seed and color. Original artwork and alpha preserved.</text>']
for index, (title, preset, extra) in enumerate(noise_cards):
    x, y = 40 + index % 3 * 408, 184 + index // 3 * 248
    body.extend([f'<g id="noise-card-{index}">',
                 f'<rect x="{x}" y="{y}" width="384" height="224" rx="16" fill="white"/>',
                 f'<text x="{x+24}" y="{y+36}" style="font-family:sans-serif;font-size:16px;font-weight:600;fill:#17243d">{index+1:02d} / {title}</text>',
                 f'<text x="{x+24}" y="{y+63}" style="font-family:sans-serif;font-size:12px;fill:#68748c">' +
                 ('Unmodified editable gradient' if preset is None else 'Native SVG filter · source holes stay clear') + '</text>',
                 f'<g id="noise-sample-{index}" transform="translate({x+192},{y+143})">',
                 '<path d="M-152,-44 H152 V44 H-152 Z M-55,-20 H-25 V20 H-55 Z M25,-20 H55 V20 H25 Z" '
                 'fill="url(#noise-gradient)" fill-rule="evenodd"/>', '</g></g>'])
body.extend(['<text x="48" y="959" style="font-family:sans-serif;font-size:14px;fill:#17243d">Extensions → Binsalmarts Extensions → Vector Effects Pro → Noise. Combine effects from the main dialog.</text>',
             '<text x="48" y="990" style="font-family:sans-serif;font-size:13px;fill:#68748c">Procedural SVG textures, not bitmap pixels or exact Gaussian noise. Save as Inkscape SVG to retain editable settings.</text>', '</svg>'])
svg = inkex.load_svg(io.BytesIO(''.join(body).encode())).getroot()
for index, (_, preset, extra) in enumerate(noise_cards):
    if preset is not None:
        svg = apply(svg, '--id=noise-sample-' + str(index), '--geometry=none', '--noise=true',
                    '--noise_type=' + preset, *extra)
save(svg, 'noise-gallery.svg')
print(output / 'noise-gallery.svg')
