#!/usr/bin/env python3
"""Generate reproducible examples; uses Pillow, Inkex and the extension itself."""
import argparse
import base64
import io
import os
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

from lxml import etree
from PIL import Image, ImageDraw
from ascii_art_pro import AsciiArtPro

examples = root / "examples"
examples.mkdir(exist_ok=True)
width, height = 720, 480
image = Image.new("RGB", (width, height))
draw = ImageDraw.Draw(image)
for y in range(height):
    ratio = y / height
    draw.line((0, y, width, y), fill=(round(22 + 168 * ratio), round(35 + 111 * ratio), round(80 + 71 * ratio)))
draw.ellipse((450, 46, 576, 172), fill=(255, 218, 133))
draw.polygon([(0, 300), (190, 90), (360, 315)], fill=(116, 111, 151))
draw.polygon([(115, 174), (190, 90), (257, 177), (201, 159), (171, 177)], fill=(241, 222, 219))
draw.polygon([(225, 345), (431, 175), (661, 343)], fill=(77, 99, 132))
draw.polygon([(0, 347), (130, 287), (294, 357), (512, 275), (720, 321), (720, 480), (0, 480)], fill=(32, 79, 105))
draw.rectangle((0, 368, width, height), fill=(33, 91, 119))
for y in range(381, 480, 15):
    offset = (y - 381) * 1.4
    draw.line((410 - offset, y, 580 + offset, y), fill=(155, 164, 148), width=3)
for x, y, size in ((77, 310, 53), (128, 320, 65), (610, 328, 55), (650, 323, 77)):
    draw.rectangle((x - 3, y, x + 3, y + size), fill=(17, 38, 45))
    draw.polygon([(x, y - size), (x - size * 0.38, y + size * 0.3),
                  (x + size * 0.38, y + size * 0.3)], fill=(14, 43, 49))
image.save(examples / "source.png")
buffer = io.BytesIO()
image.save(buffer, format="PNG")
href = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
source = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
          f'width="720" height="480" viewBox="0 0 720 480">'
          f'<image id="source-image" x="0" y="0" width="720" height="480" xlink:href="{href}"/>'
          f'</svg>').encode()
(examples / "input.svg").write_bytes(source)
variants = {
    "arabic": ["--quality=medium", "--sequence=arabic", "--font_family=Noto Sans Arabic",
               "--contrast=1.4", "--background=white", "--character_spacing=0.8", "--line_height=1.6"],
    "monochrome": ["--quality=high", "--contrast=1.4", "--background=white"],
    "color": ["--quality=high", "--original_colors=true", "--sequence=blocks", "--background=white"],
    "edges": ["--quality=high", "--edge_detection=true", "--sequence=dense", "--background=white"],
    "overlay": ["--quality=high", "--original_colors=true", "--overlay_original=true",
                "--overlay_opacity=0.35", "--blur_strength=2", "--background=white"],
}
for name, options in variants.items():
    extension = AsciiArtPro()
    extension.options = extension.arg_parser.parse_args(["--id=source-image", "--original_action=replace", *options])
    extension.load(io.BytesIO(source))
    extension.effect()
    etree.ElementTree(extension.svg).write(str(examples / f"{name}.svg"), encoding="utf-8", xml_declaration=True)
    print(f"Created examples/{name}.svg")
