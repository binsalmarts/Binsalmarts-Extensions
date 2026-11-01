#!/usr/bin/env python3
"""Generate public Color Guide Pro examples from self-contained vector artwork."""
import argparse
import io
from pathlib import Path
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inkex-dir');parser.add_argument('--extra-packages')
args=parser.parse_args()
for path in (args.inkex_dir,args.extra_packages):
    if path: sys.path.append(path)
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lxml import etree
import inkex
from color_guide_pro import ColorGuidePro, MARKER, snapshot_svg

OUT=ROOT/'examples/color_guide';OUT.mkdir(parents=True,exist_ok=True)


def source(colors):
    svg=inkex.SvgDocumentElement();svg.set('width','1000');svg.set('height','500');svg.set('viewBox','0 0 1000 500')
    group=inkex.Group();group.set('id','brand-colors');svg.append(group)
    for i,value in enumerate(colors):
        rect=inkex.Rectangle.new(40+i*130,230,110,150);rect.set('id','brand-color-'+str(i+1));rect.style={'fill':value};group.append(rect)
    mark=inkex.PathElement();mark.set('id','brand-mark');mark.set('d','M120 25 200 105 120 185 40 105Z M120 67 82 105 120 143 158 105Z');mark.style={'fill':colors[0],'fill-rule':'evenodd'};svg.append(mark)
    title=inkex.TextElement(x='245',y='120');title.style={'font-family':'DejaVu Sans','font-size':'40px','fill':'#172132'};title.text='MADAR / Select brand-colors';svg.append(title)
    return etree.tostring(svg)


def build(filename,data,options):
    ex=ColorGuidePro();ex.options=ex.arg_parser.parse_args(['--id=brand-colors']+options);ex.load(io.BytesIO(data));ex.effect()
    (OUT/filename).write_bytes(etree.tostring(ex.svg,xml_declaration=True,encoding='UTF-8'))
    guide=next(n for n in ex.svg if n.get(MARKER)=='guide')
    pages=[n for n in guide.xpath('.//*[@data-cgp-section]')]
    standalone=snapshot_svg(pages,guide[0],1600,900,70)
    (OUT/filename.replace('.svg','-pages.svg')).write_bytes(etree.tostring(standalone,xml_declaration=True,encoding='UTF-8'))
    return ex

english=source(['#0E5E6F','#D96A2C','#E3D7B4','#2E2D33'])
(OUT/'source.svg').write_bytes(english)
names='#0E5E6F=Petrol|بترولي;#D96A2C=Terracotta|طوبي;#E3D7B4=Sand|رملي;#2E2D33=Charcoal|فحمي'
build('brand-guide-en.svg',english,['--page_cover=true','--page_tones=true','--page_pairings=true','--page_combinations=true',
    '--brand_name=MADAR COFFEE','--brand_subtitle=Color guidelines / Edition 2026','--logo_id=brand-mark','--custom_names='+names])
arabic=source(['#5153AD','#D9A84D','#E6E2CF','#B9B59B','#111522','#F5F1E9','#93966B'])
(OUT/'combinations-source.svg').write_bytes(arabic)
build('combinations-ar.svg',arabic,['--page_palette=false','--page_combinations=true','--language=ar','--brand_name=مدار — نظام الهوية',
    '--brand_subtitle=دليل استخدام الألوان','--symbol=diamond'])
build('custom-symbol-ar.svg',arabic,['--page_palette=false','--page_combinations=true','--language=ar','--brand_name=مدار — تكوينات الشعار',
    '--symbol=custom','--symbol_id=brand-mark'])
build('cards-ar.svg',english,['--palette_layout=cards','--language=ar','--brand_name=مدار — لوحة الألوان','--custom_names='+names])
print('Created source artwork and bilingual modular guides in',OUT)

gradient_source=b'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500" viewBox="0 0 1000 500"><defs><linearGradient id="ocean"><stop stop-color="#0E5E6F"/><stop offset="50%" stop-color="#64B6AC"/><stop offset="1" stop-color="#E3D7B4"/></linearGradient><radialGradient id="warm"><stop stop-color="#F5E6C8"/><stop offset="1" stop-color="#D96A2C"/></radialGradient></defs><g id="brand-colors"><rect x="80" y="80" width="350" height="300" fill="url(#ocean)"/><circle cx="680" cy="240" r="150" fill="url(#warm)"/></g></svg>'''
(OUT/'gradient-source.svg').write_bytes(gradient_source)
build('gradients-en.svg',gradient_source,['--page_palette=false','--page_gradients=true','--brand_name=MADAR / GRADIENTS'])
