#!/usr/bin/env python3
"""Color Guide Pro: modular, editable brand color guides for Inkscape 1.4+."""
from copy import deepcopy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import uuid

import inkex
from lxml import etree
from color_guide_colors import Swatch, rgba, hex_rgb, nearest_name, name_overrides, rgb_cmyk, rgb_hsl
from color_guide_render import GuideRenderer, node, SVG, W, H

VERSION='1.0.1'
MARKER='data-color-guide-pro'
SETTINGS='data-cgp-settings'
SOURCES='data-cgp-sources'
ACTIVE='data-cgp-active'
URL_RE=re.compile(r'url\(\s*[\'"]?#([^\s)\'"]+)[\'"]?\s*\)')
DEFAULTS={
    'tab':'sections','action':'create','page_cover':False,'page_palette':True,'page_tones':False,
    'page_pairings':False,'page_combinations':False,'page_gradients':False,'include_fill':True,
    'include_stroke':True,'include_gradients':True,'max_colors':24,'language':'en',
    'brand_name':'Brand Color Guide','brand_subtitle':'A considered color system.',
    'logo_id':'','custom_names':'','font_family':'DejaVu Sans','font_scale':1.,
    'show_hex':True,'show_rgb':True,'show_cmyk':True,'show_hsl':False,
    'palette_layout':'editorial','palette_tones':True,'tone_count':11,'base_tone':0,
    'symbol':'diamond','symbol_id':'','combination_details':False,
    'combination_layout':'editorial','combination_description':'','include_neutrals':True,'pair_filter':'all',
    'pair_sort':'palette','max_pairs':24,'paper':'#FFFFFF','page_preset':'widescreen',
    'page_width':1600.,'page_height':900.,'page_gap':70.,'native_pages':True,
    'export_dir':'','export_name':'Color-Guide','export_svg':False,'export_pdf':False,
    'export_png':False,'export_gpl':False,'export_json':False,'export_csv':False,'png_width':1600,
}
CHOICES={
    'action':('create','update','refresh'),'language':('en','ar'),
    'palette_layout':('editorial','cards','compact'),'symbol':('diamond','circle','square','custom'),
    'combination_layout':('editorial','matrix'),'pair_filter':('all','normal','large'),'pair_sort':('palette','contrast'),
    'page_preset':('widescreen','a4','custom'),
}
DRAWABLE={'path','rect','circle','ellipse','polygon','polyline','line','text','tspan'}
SKIP={'defs','metadata','namedview','clipPath','mask','pattern','style','script','title','desc'}


def local_tag(element):
    return etree.QName(element).localname if isinstance(element.tag,str) else ''


def number(value):
    return format(float(value),'.12g')


def opacity(element,key='opacity'):
    return max(0.,min(1.,float(element.get_computed_style(key))))


def managed(element):
    return any(e.get(MARKER) for e in [element,*element.iterancestors()])


class ColorReader:
    def __init__(self,svg,options):
        self.svg,self.o=svg,options
        self.colors={};self.gradients={};self.unsupported=set();self.visited=0

    def add(self,value,source):
        if value is None or value[3]<=0: return
        swatch=Swatch(tuple(value),[source]);key=swatch.key
        if key in self.colors:
            if source not in self.colors[key].sources: self.colors[key].sources.append(source)
        else:
            self.colors[key]=swatch
        if len(self.colors)>self.o.max_colors:
            raise inkex.AbortExtension(f'More than {self.o.max_colors} colors. Narrow the selection or raise Maximum colors (up to 32).')

    def gradient(self,gradient,alpha,source):
        current=gradient;seen=set()
        while not any(local_tag(s)=='stop' for s in current):
            identifier=current.get('id')
            if identifier in seen: raise inkex.AbortExtension('Circular gradient reference in the selection.')
            seen.add(identifier)
            href=current.get('href') or current.get(inkex.addNS('href','xlink')) or ''
            target=self.svg.getElementById(href[1:]) if href.startswith('#') else None
            if not isinstance(target,(inkex.LinearGradient,inkex.RadialGradient)):
                self.unsupported.add('empty gradient');return
            current=target
        stops=[];previous=0.
        for stop in current:
            if local_tag(stop)!='stop': continue
            raw=stop.get('offset','0')
            try: offset=float(raw.rstrip('%'))/(100 if raw.endswith('%') else 1)
            except ValueError as e: raise inkex.AbortExtension('A gradient stop has an invalid offset.') from e
            offset=max(previous,min(1.,max(0.,offset)));previous=offset
            value=rgba(stop.get_computed_style('stop-color'))
            if value is None: continue
            value=(*value[:3],value[3]*opacity(stop,'stop-opacity')*alpha)
            stops.append({'offset':offset,'value':value})
            self.add(value,source+' / gradient')
        if len(stops)>128: raise inkex.AbortExtension('A gradient has more than 128 stops.')
        if not stops: return
        record={'source_id':gradient.get('id'),'label':gradient.get(inkex.addNS('label','inkscape')) or gradient.get('id') or 'Gradient',
                'type':'radial' if isinstance(gradient,inkex.RadialGradient) else 'linear','stops':stops}
        self.gradients.setdefault(json.dumps(record,sort_keys=True),record)

    def paint(self,paint,alpha,source,element):
        if isinstance(paint,(inkex.LinearGradient,inkex.RadialGradient)):
            if self.o.include_gradients: self.gradient(paint,alpha,source)
            return
        if paint is None: return
        try:
            if str(paint)=='currentColor': paint=element.get_computed_style('color')
            value=rgba(paint)
        except (ValueError,TypeError):
            self.unsupported.add('unsupported paint');return
        if value: self.add((*value[:3],value[3]*alpha),source)

    def walk(self,element,parent_alpha,clones=(),inherited=None):
        self.visited+=1
        if self.visited>50000: raise inkex.AbortExtension('The selection exceeds 50,000 nodes.')
        tag=local_tag(element)
        if tag in SKIP or managed(element): return
        if str(element.get_computed_style('display'))=='none': return
        alpha=parent_alpha*opacity(element)
        if alpha<=0: return
        if isinstance(element,inkex.Use):
            href=element.get('href') or element.get(inkex.addNS('href','xlink')) or ''
            if not href.startswith('#') or href in clones:
                self.unsupported.add('unresolved clone');return
            target=self.svg.getElementById(href[1:])
            if target is None: self.unsupported.add('unresolved clone');return
            inherited={key:element.get_computed_style(key) for key in ('fill','stroke','fill-opacity','stroke-opacity','color')}
            self.walk(target,alpha,clones+(href,),inherited)
            return
        style=dict(inherited or {})
        if inherited is not None:
            cascade=element.cascaded_style()
            for key in ('fill','stroke','fill-opacity','stroke-opacity','color'):
                if key in cascade and str(cascade[key]) not in ('inherit','unset'):
                    style[key]=element.get_computed_style(key)
        if tag in DRAWABLE and str(element.get_computed_style('visibility')) not in ('hidden','collapse'):
            for key,enabled in [('fill',self.o.include_fill),('stroke',self.o.include_stroke)]:
                if not enabled: continue
                if key=='fill' and tag=='line': continue
                if tag in ('text','tspan') and not (element.text or '').strip() and not any((c.tail or '').strip() for c in element): continue
                paint=style.get(key) if inherited is not None else element.get_computed_style(key)
                paint_alpha=float(style.get(key+'-opacity',1)) if inherited is not None else opacity(element,key+'-opacity')
                if key=='stroke' and float(element.get_computed_style('stroke-width'))==0: continue
                self.paint(paint,alpha*paint_alpha,element.get('id',tag)+' / '+key,element)
        elif tag=='image': self.unsupported.add('raster image')
        for child in element:
            self.walk(child,alpha,clones,style if inherited is not None else None)

    def read(self,roots):
        for element in roots:
            alpha=1.
            if any(str(a.get_computed_style('display'))=='none' for a in element.iterancestors()): continue
            for ancestor in element.iterancestors(): alpha*=opacity(ancestor)
            self.walk(element,alpha)
        if not self.colors:
            raise inkex.AbortExtension('No supported visible colors found. Select vector artwork and enable its fill, stroke or gradient types.')
        overrides=name_overrides(self.o.custom_names)
        colors=list(self.colors.values())
        for swatch in colors: swatch.name=overrides.get(swatch.hex) or nearest_name(swatch.value[:3])
        return colors,list(self.gradients.values())


def copy_symbol(svg,source,defs,prefix,monochrome=False):
    """Snapshot vector artwork and its local definition references, with unique IDs."""
    if any(local_tag(n)=='image' for n in source.iter()):
        raise inkex.AbortExtension('Use vector artwork for the logo or custom symbol. Raster images are not supported there.')
    bounds=source.bounding_box(source.getparent().composed_transform() if source.getparent() is not None else None)
    if bounds is None or not all(math.isfinite(v) for v in (bounds.left,bounds.top,bounds.width,bounds.height)) or min(bounds.width,bounds.height)<=0:
        raise inkex.AbortExtension('The logo or custom symbol has no measurable vector bounds. Convert its text to paths if needed.')
    symbol=node(defs,'symbol',id=prefix,viewBox=' '.join(map(number,(bounds.left,bounds.top,bounds.width,bounds.height))),preserveAspectRatio='xMidYMid meet')
    container=node(symbol,'g',transform=str(source.getparent().composed_transform()) if source.getparent() is not None else '')
    clone=deepcopy(source);container.append(clone)
    # Freeze CSS inherited from the original document, then recolor the custom silhouette.
    for original,copied in zip(source.iter(),clone.iter()):
        if not isinstance(original.tag,str): continue
        copied.set('style',str(original.specified_style()))
        if monochrome and 'color' in copied.style: copied.style.pop('color')
        if monochrome and local_tag(original) in DRAWABLE:
            for key in ('fill','stroke'):
                if original.get_computed_style(key) is not None: copied.style[key]='currentColor'
    pending=[clone];dependencies=set()
    while pending:
        branch=pending.pop()
        for child in branch.iter():
            for key,value in child.attrib.items():
                refs=URL_RE.findall(value)
                if etree.QName(key).localname=='href' and value.startswith('#'): refs.append(value[1:])
                for identifier in refs:
                    if identifier in dependencies or any(n.get('id')==identifier for n in clone.iter()): continue
                    dependencies.add(identifier)
                    target=svg.getElementById(identifier)
                    if target is not None:
                        dependency=deepcopy(target);defs.append(dependency);pending.append(dependency)
                    if len(dependencies)>256: raise inkex.AbortExtension('The custom artwork has too many linked definitions.')
    branches=[symbol]+[n for n in list(defs) if n.get('id') in dependencies]
    mapping={n.get('id'):prefix+'-'+n.get('id') for branch in branches for n in branch.iter() if n.get('id') and n is not symbol}
    for branch in branches:
        for n in branch.iter():
            for key,value in list(n.attrib.items()):
                if key=='id' and value in mapping: n.set(key,mapping[value])
                elif etree.QName(key).localname=='href' and value.startswith('#'): n.set(key,'#'+mapping.get(value[1:],value[1:]))
                else: n.set(key,URL_RE.sub(lambda m:'url(#'+mapping.get(m[1],m[1])+')',value))
    return prefix


def seal_styles(root):
    """Prevent normal document-wide SVG CSS rules from recoloring generated artwork."""
    defaults={'opacity':'1','display':'inline','visibility':'visible','filter':'none',
              'mix-blend-mode':'normal','clip-path':'none','mask':'none','stroke':'none',
              'fill':'#000000','fill-opacity':'1','stroke-opacity':'1','stroke-width':'1','color':'inherit'}
    properties=set(defaults)|{'stop-color','stop-opacity','fill-rule','text-anchor','direction','unicode-bidi'}
    for item in root.iter():
        if not isinstance(item.tag,str): continue
        style=inkex.Style(defaults)
        for key in properties:
            if item.get(key) is not None: style[key]=item.get(key)
        style.update(item.style)
        item.style=style


def snapshot_svg(pages,defs,width,height,gap):
    svg=inkex.SvgDocumentElement()
    svg.set('width',number(width));svg.set('height',number(height*len(pages)+gap*(len(pages)-1)))
    svg.set('viewBox',f'0 0 {number(width)} {number(height*len(pages)+gap*(len(pages)-1))}')
    svg.append(deepcopy(defs))
    nv=inkex.NamedView();svg.append(nv)
    factor=min(width/W,height/H)
    for i,page in enumerate(pages):
        y=i*(height+gap)
        native=inkex.Page(x='0',y=number(y),width=number(width),height=number(height))
        native.set('id','guide-page-'+str(i+1));native.set(inkex.addNS('label','inkscape'),page.get(inkex.addNS('label','inkscape'),'Page'))
        nv.append(native)
        wrapper=inkex.Group(transform=f'translate({number((width-W*factor)/2)},{number(y+(height-H*factor)/2)}) scale({number(factor)})')
        node(svg,'rect',x=0,y=y,width=width,height=height,fill=page[0].get('fill','#FFFFFF'))
        wrapper.append(deepcopy(page));svg.append(wrapper)
    return svg


class ColorGuidePro(inkex.EffectExtension):
    def add_arguments(self,pars):
        for key,default in DEFAULTS.items():
            kind=inkex.Boolean if isinstance(default,bool) else type(default)
            pars.add_argument('--'+key,type=kind,default=default)

    def previous_guide(self):
        selected=list(self.svg.selection.values())
        for element in selected:
            for ancestor in [element,*element.iterancestors()]:
                if ancestor.get(MARKER)=='guide': return ancestor
        identifier=self.svg.get(ACTIVE)
        guide=self.svg.getElementById(identifier) if identifier else None
        return guide if guide is not None and guide.get(MARKER)=='guide' else None

    def validate(self):
        o=self.options
        for key,choices in CHOICES.items():
            if getattr(o,key) not in choices: raise inkex.AbortExtension('Unknown '+key+'.')
        for key,low,high in [('max_colors',1,32),('tone_count',5,11),('base_tone',0,11),('max_pairs',1,240),
                             ('page_width',800,8000),('page_height',500,8000),('page_gap',0,1000),
                             ('font_scale',.75,1.15),('png_width',400,8000)]:
            value=getattr(o,key)
            if not math.isfinite(value) or not low<=value<=high: raise inkex.AbortExtension(f'{key}: choose a value between {low} and {high}.')
        if o.tone_count not in (5,7,9,11) or o.base_tone>o.tone_count: raise inkex.AbortExtension('Choose 5, 7, 9 or 11 tones and a valid original tone position.')
        if not any(getattr(o,'page_'+s) for s in ('cover','palette','tones','pairings','combinations','gradients')):
            raise inkex.AbortExtension('Enable at least one output section.')
        if not o.include_fill and not o.include_stroke: raise inkex.AbortExtension('Enable Fill or Stroke to read colors.')
        for key,limit in [('brand_name',90),('brand_subtitle',180),('font_family',120)]:
            text=getattr(o,key)
            if not text.strip() or len(text)>limit or any(ord(c)<32 for c in text): raise inkex.AbortExtension(f'{key}: enter 1–{limit} printable characters.')
        if len(o.combination_description)>240 or any(ord(c)<32 and c not in '\n\t' for c in o.combination_description):
            raise inkex.AbortExtension('The combination description is limited to 240 characters.')
        try:
            paper=rgba(o.paper)
            if paper is None or paper[3]!=1: raise ValueError()
            o.paper_rgb=paper[:3];o.paper_color=hex_rgb(paper[:3])
            name_overrides(o.custom_names)
        except (ValueError,TypeError) as error: raise inkex.AbortExtension(str(error) or 'Choose an opaque paper color.') from error
        if o.page_preset=='widescreen': o.page_width,o.page_height=1600.,900.
        elif o.page_preset=='a4': o.page_width,o.page_height=297*96/25.4,210*96/25.4
        if o.page_width*o.page_height*(o.png_width/o.page_width)**2>40_000_000: raise inkex.AbortExtension('PNG would exceed 40 million pixels. Reduce its width.')
        if any(getattr(o,'export_'+fmt) for fmt in ('svg','pdf','png','gpl','json','csv')):
            if not o.export_dir.strip(): raise inkex.AbortExtension('Choose an export folder or disable the export formats.')
            if not re.fullmatch(r'[\w .-]{1,70}',o.export_name,re.UNICODE) or o.export_name.strip(' .')!=o.export_name:
                raise inkex.AbortExtension('Use a file name of 1–70 letters, numbers, spaces, dots or hyphens.')

    def geometry(self):
        box=self.svg.get_viewbox()
        vw,vh=self.svg.viewport_width,self.svg.viewport_height
        if box==[0,0,0,0]: box=[0,0,vw,vh]
        if any(not math.isfinite(v) for v in (*box,vw,vh)) or min(box[2],box[3],vw,vh)<=0:
            raise inkex.AbortExtension('The document has invalid width, height or viewBox.')
        return box,vw/box[2],vh/box[3]

    def saved_sources(self,guide):
        try: identifiers=json.loads(guide.get(SOURCES,''))
        except (ValueError,TypeError) as error: raise inkex.AbortExtension('The saved source references are damaged.') from error
        if not isinstance(identifiers,list) or not identifiers or len(identifiers)>1000 or any(not isinstance(v,str) or len(v)>256 for v in identifiers): raise inkex.AbortExtension('Invalid saved source list.')
        roots=[]
        for identifier in identifiers:
            source=self.svg.getElementById(identifier)
            if source is None: raise inkex.AbortExtension('A source object was deleted: '+str(identifier)+'. Select the source artwork and create a new guide.')
            if managed(source): raise inkex.AbortExtension('A guide cannot be its own color source.')
            roots.append(source)
        return roots

    def export(self,pages,defs,colors,gradients):
        o=self.options
        formats=[fmt for fmt in ('svg','pdf','png','gpl','json','csv') if getattr(o,'export_'+fmt)]
        if not formats: return None
        parent=Path(o.export_dir).expanduser().resolve()
        if not parent.is_dir(): raise inkex.AbortExtension('The export folder must already exist.')
        destination=parent/o.export_name
        suffix=2
        while destination.exists():
            destination=parent/(o.export_name+'-'+str(suffix));suffix+=1
        stage=Path(tempfile.mkdtemp(prefix='.color-guide-',dir=parent))
        try:
            whole=snapshot_svg(pages,defs,o.page_width,o.page_height,o.page_gap)
            master=stage/(o.export_name+'.svg')
            etree.ElementTree(whole).write(str(master),encoding='UTF-8',xml_declaration=True)
            if 'pdf' in formats or 'png' in formats:
                from inkex.command import inkscape
                if 'pdf' in formats:
                    inkscape(str(master),batch_process=True,export_type='pdf',export_area_page=True,export_text_to_path=True,export_filename=str(stage/(o.export_name+'.pdf')))
                    pdf=stage/(o.export_name+'.pdf')
                    if not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-'):
                        raise RuntimeError('Inkscape did not produce the requested PDF.')
                if 'png' in formats:
                    for i,page in enumerate(pages):
                        single=snapshot_svg([page],defs,o.page_width,o.page_height,0)
                        with tempfile.TemporaryDirectory(prefix='color-guide-render-') as tmp:
                            source=Path(tmp)/'page.svg';etree.ElementTree(single).write(str(source),encoding='UTF-8',xml_declaration=True)
                            inkscape(str(source),batch_process=True,export_type='png',export_area_page=True,export_width=str(o.png_width),export_filename=str(stage/(f'{o.export_name}-{i+1:02}.png')))
                            bitmap=stage/(f'{o.export_name}-{i+1:02}.png')
                            if not bitmap.is_file() or not bitmap.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                                raise RuntimeError('Inkscape did not produce the requested PNG.')
            records=[]
            for c in colors:
                records.append({'hex':c.hex,'rgb':list(c.value[:3]),'alpha':c.value[3],'display_rgb':list(c.effective(o.paper_rgb)),
                                'cmyk_approx':rgb_cmyk(c.value[:3]),'hsl':rgb_hsl(c.value[:3]),'name':c.name,'sources':c.sources})
            if 'json' in formats:
                data={'generator':'Color Guide Pro '+VERSION,'brand':o.brand_name,'paper':o.paper_color,
                      'naming_source':'https://xkcd.com/color/rgb.txt','colors':records,'gradients':gradients,
                      'sections':[p.get('data-cgp-section') for p in pages]}
                (stage/(o.export_name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
            if 'gpl' in formats:
                lines=['GIMP Palette','Name: '+o.brand_name,'Columns: 6','# Alpha flattened onto '+o.paper_color]
                for c in colors: lines.append('%3d %3d %3d\t%s' % (*c.effective(o.paper_rgb),c.name['en']))
                (stage/(o.export_name+'.gpl')).write_text('\n'.join(lines)+'\n',encoding='utf8')
            if 'csv' in formats:
                with (stage/(o.export_name+'.csv')).open('w',encoding='utf-8-sig',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow(['Name EN','Name AR','HEX','R','G','B','Alpha','C~','M~','Y~','K~'])
                    for c in colors: writer.writerow([c.name['en'],c.name['ar'],c.hex,*c.value,*rgb_cmyk(c.value[:3])])
            if 'svg' not in formats: master.unlink()
            # Rename only after all requested formats have succeeded. Existing exports are never overwritten.
            stage.rename(destination)
            return destination
        except Exception as error:
            shutil.rmtree(stage,ignore_errors=True)
            if isinstance(error,inkex.AbortExtension): raise
            raise inkex.AbortExtension('Export failed; the document was not changed. '+str(error)) from error

    def effect(self):
        previous=self.previous_guide()
        if self.options.action=='refresh':
            if previous is None: raise inkex.AbortExtension('Select a generated guide or create one first.')
            try:
                settings=json.loads(previous.get(SETTINGS,''))
                if not isinstance(settings,dict) or set(settings)-set(DEFAULTS): raise ValueError()
                args=['--'+key+'='+str(value) for key,value in settings.items()]
                self.options=self.arg_parser.parse_args(args)
                self.options.action='refresh'
            except (ValueError,TypeError,SystemExit) as error: raise inkex.AbortExtension('Saved guide settings are damaged.') from error
        self.validate();o=self.options
        box,sx,sy=self.geometry()
        selected=[n for n in self.svg.selection.values() if not managed(n)]
        roots=[n for n in selected if not any(a in selected for a in n.iterancestors())]
        if o.action=='refresh' and previous is not None: roots=self.saved_sources(previous)
        elif o.action=='update' and previous is not None and not roots: roots=self.saved_sources(previous)
        if not roots: raise inkex.AbortExtension('Select vector artwork or a group whose colors should be collected.')
        if len(roots)>1000: raise inkex.AbortExtension('Select at most 1,000 source objects, or group them.')
        reader=ColorReader(self.svg,o);colors,gradients=reader.read(roots)
        token='cgp-'+uuid.uuid4().hex[:12]
        defs=inkex.Defs();assets={}
        for kind,identifier,enabled,mono in [('logo',o.logo_id,o.page_cover and bool(o.logo_id),False),
                                             ('symbol',o.symbol_id,o.page_combinations and o.symbol=='custom',True)]:
            if not enabled: continue
            element=self.svg.getElementById(identifier.strip()) if identifier.strip() else None
            if element is None or managed(element): raise inkex.AbortExtension('Enter a valid '+kind+' object ID from the original artwork.')
            assets[kind]=copy_symbol(self.svg,element,defs,token+'-'+kind,mono)
        renderer=GuideRenderer(o,colors,gradients,defs,token,assets)
        pages=renderer.render()
        width,height=o.page_width,o.page_height
        namedview=self.svg.find(inkex.addNS('namedview','sodipodi'))
        existing=namedview.findall(inkex.addNS('page','inkscape')) if namedview is not None else []
        old=previous if o.action in ('update','refresh') else None
        old_pages=[p for p in existing if old is not None and p.get('data-cgp-owner')==old.get('id')]
        retained=[p for p in existing if p not in old_pages]
        # Validate existing page rectangles before any mutation or file export.
        for p in existing:
            if any(not math.isfinite(v) for v in (p.x,p.y,p.width,p.height)) or min(p.width,p.height)<=0:
                raise inkex.AbortExtension('An existing document page has invalid dimensions.')
        if old is not None:
            origin=json.loads(old.get('data-cgp-origin','[0,0]'))
        else:
            right=max([box[0]+box[2]]+[p.x+p.width for p in retained])
            origin=[right+80/sx,box[1]]
        guide=inkex.Group();guide.set('id',token);guide.set(MARKER,'guide')
        guide.set(inkex.addNS('groupmode','inkscape'),'layer');guide.set(inkex.addNS('label','inkscape'),'Color Guide Pro · '+o.brand_name)
        guide.set('transform',f'translate({number(origin[0])},{number(origin[1])}) scale({number(1/sx)},{number(1/sy)})')
        guide.set('data-cgp-version',VERSION);guide.set('data-cgp-origin',json.dumps(origin))
        guide.append(defs)
        factor=min(width/W,height/H)
        for i,page in enumerate(pages):
            outer=inkex.Group();outer.set('transform',f'translate(0,{number(i*(height+o.page_gap))})')
            node(outer,'rect',width=width,height=height,fill=o.paper_color)
            inner=inkex.Group(transform=f'translate({number((width-W*factor)/2)},{number((height-H*factor)/2)}) scale({number(factor)})')
            inner.append(page);outer.append(inner);guide.append(outer)
        reserved=set(self.svg.get_ids());assignments=[];source_ids=[]
        for i,root in enumerate(roots):
            identifier=root.get('id')
            if not identifier:
                identifier=token+'-source-'+str(i);assignments.append((root,identifier))
            source_ids.append(identifier)
        guide.set(SOURCES,json.dumps(source_ids))
        saved={key:getattr(o,key) for key in DEFAULTS if key!='action' and not key.startswith('export_')}
        saved.update({key:False for key in DEFAULTS if key.startswith('export_') and isinstance(DEFAULTS[key],bool)})
        guide.set(SETTINGS,json.dumps(saved,ensure_ascii=False,separators=(',',':')))
        guide.set('data-cgp-color-count',str(len(colors)))
        if reader.unsupported: guide.set('data-cgp-skipped',', '.join(sorted(reader.unsupported)))
        planned=[]
        if o.native_pages:
            for i,page in enumerate(pages):
                native=inkex.Page(x=number(origin[0]),y=number(origin[1]+i*(height+o.page_gap)/sy),width=number(width/sx),height=number(height/sy))
                native.set('id',token+'-page-'+str(i+1));native.set('data-cgp-owner',token)
                native.set(inkex.addNS('label','inkscape'),page.get(inkex.addNS('label','inkscape'),'Color Guide'))
                planned.append(native)
        if len(retained)+len(planned)+int(not existing and o.native_pages)>1000:
            raise inkex.AbortExtension('The document would exceed 1,000 native pages.')
        seal_styles(guide)
        self.export(pages,defs,colors,gradients)
        # All validation, page rendering and requested exports succeeded. Commit the document once.
        for root,identifier in assignments: root.set('id',identifier)
        if namedview is None:
            namedview=inkex.NamedView();self.svg.insert(0,namedview)
        if not existing and o.native_pages:
            original=inkex.Page(x=number(box[0]),y=number(box[1]),width=number(box[2]),height=number(box[3]))
            original.set('id',token+'-original-page');original.set(inkex.addNS('label','inkscape'),'Original artwork');namedview.append(original)
        for page in old_pages: namedview.remove(page)
        if old is not None: old.getparent().remove(old)
        self.svg.append(guide)
        for page in planned: namedview.append(page)
        self.svg.set(ACTIVE,token)


if __name__=='__main__':
    ColorGuidePro().run()
