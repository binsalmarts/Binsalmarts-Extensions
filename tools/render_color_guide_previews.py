#!/usr/bin/env python3
"""Render selected native guide pages into README thumbnails."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inkex-dir');parser.add_argument('--extra-packages');parser.add_argument('--inkscape',default='inkscape')
args=parser.parse_args()
for path in (args.inkex_dir,args.extra_packages):
    if path: sys.path.append(path)
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import inkex
from lxml import etree
from color_guide_pro import snapshot_svg

output=ROOT/'docs/images';output.mkdir(exist_ok=True)
for source,index,name in [('brand-guide-en-pages.svg',1,'color-guide-palette'),
                          ('combinations-ar-pages.svg',0,'color-guide-combinations-ar'),
                          ('custom-symbol-ar-pages.svg',0,'color-guide-custom-symbol'),
                          ('cards-ar-pages.svg',0,'color-guide-cards-ar'),
                          ('brand-guide-en-pages.svg',4,'color-guide-contrast')]:
    svg=inkex.load_svg(str(ROOT/'examples/color_guide'/source)).getroot()
    pages=svg.xpath('.//*[@data-cgp-section]');defs=svg.find(inkex.addNS('defs','svg'))
    single=snapshot_svg([pages[index]],defs,1600,900,0)
    with tempfile.TemporaryDirectory(prefix='color-guide-preview-') as folder:
        path=Path(folder)/'page.svg';etree.ElementTree(single).write(str(path),encoding='utf8',xml_declaration=True)
        subprocess.run([args.inkscape,str(path),'--export-area-page','--export-type=png','--export-width=1280',
                        '--export-filename='+str(output/(name+'.png'))],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print(name+'.png')
