#!/usr/bin/env python3
"""Editable SVG page layouts for Color Guide Pro. No bitmap screenshots are used."""
import math
import textwrap
from lxml import etree
import inkex

from color_guide_colors import contrast, contrast_level, hex_rgb, readable_ink, rgb_cmyk, rgb_hsl, tonal_scale

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
INK = 'http://www.inkscape.org/namespaces/inkscape'
W, H = 1600., 900.
DARK, MUTED, LINE = '#172132', '#657184', '#DFE3E6'
TEXT = {
    'guide':('Color guidelines','دليل الألوان'), 'cover':('Brand color system','نظام ألوان الهوية'),
    'palette':('Color palette','لوحة الألوان'), 'tones':('Tonal scales','درجات الألوان'),
    'pairings':('Color pairings','تباين النص والخلفية'), 'combinations':('Color combinations','تكوينات الألوان'),
    'gradients':('Gradient library','مكتبة التدرجات'), 'sample':('Clear words. Confident color.','ألوان واضحة، وهوية متكاملة.'),
    'original':('Original','الأصلي'), 'approx':('≈ nearest documented name · CMYK is an unprofiled approximation','≈ أقرب اسم موثق · قيم CMYK تقريبية دون ملف طباعة'),
    'contrast_note':('WCAG 2.2 text contrast · AAA ≥7 · AA ≥4.5 · Large AA ≥3','تباين النص WCAG 2.2 · AAA ≥7 · AA ≥4.5 · للنص الكبير ≥3'),
    'decorative':('* Low text contrast. Decorative previews are not an accessibility approval.','* تباين نص منخفض. العرض الزخرفي لا يعني اعتماد سهولة القراءة.'),
    'gradient_note':('Normalized gradient swatches · source geometry stays unchanged','عينات تدرج موحّدة · هندسة العناصر الأصلية تبقى كما هي'),
    'large':('Large text only','نص كبير فقط'), 'low':('Low text contrast','تباين نص منخفض'),
}


def node(parent, tag, **attrs):
    item = etree.SubElement(parent, '{%s}%s' % (SVG,tag))
    for key,value in attrs.items():
        item.set(key.replace('_','-'), str(value))
    return item


class GuideRenderer:
    def __init__(self, options, colors, gradients, defs, token, assets=None):
        self.o, self.colors, self.gradients, self.defs, self.token = options, colors, gradients, defs, token
        self.assets = assets or {}
        self.rtl = options.language == 'ar'
        self.paper = options.paper_color
        self.background = options.paper_rgb
        self.counter = 0

    def tr(self, key):
        return TEXT[key][int(self.rtl)]

    def x(self, x, width=0):
        return W-x-width if self.rtl else x

    def rect(self, p, x, y, width, height, fill, radius=0, **extra):
        return node(p,'rect',x=self.x(x,width),y=y,width=width,height=height,rx=radius,fill=fill,**extra)

    def text(self, p, x, y, value, size=18, fill=DARK, weight=400, code=False, anchor=None, width=None, max_lines=3):
        if width:
            capacity = max(8, int(width/(size*self.o.font_scale*.60)))
            lines = textwrap.wrap(str(value),capacity,break_long_words=True,break_on_hyphens=False)[:max_lines]
        else:
            lines = [str(value)]
        element = node(p,'text',x=self.x(x),y=y,fill=fill)
        element.set('style',f'font-family:{self.o.font_family};font-size:{size*self.o.font_scale}px;font-weight:{weight};')
        element.set('text-anchor',anchor or ('end' if self.rtl and code else 'start'))
        element.set('direction','ltr' if code or not self.rtl else 'rtl')
        element.set('unicode-bidi','embed')
        for i,line in enumerate(lines):
            if len(lines)==1:
                element.text=line
            else:
                span=node(element,'tspan',x=self.x(x),dy=0 if i==0 else size*1.35)
                span.text=line
        return element

    def page(self, section, index=0, subtitle=''):
        p=inkex.Group()
        self.counter+=1
        p.set('data-cgp-section',section)
        p.set('data-cgp-page-number',str(self.counter))
        p.set(inkex.addNS('label','inkscape'),self.tr(section)+(' '+str(index+1) if index else ''))
        node(p,'rect',width=W,height=H,fill=self.paper)
        self.text(p,70,47,self.o.brand_name.upper() if not self.rtl else self.o.brand_name,12,MUTED,500)
        self.text(p,70,104,self.tr(section),38,weight=500)
        if subtitle:
            self.text(p,1530,57,subtitle,12,MUTED,code=True,anchor='start' if self.rtl else 'end')
        node(p,'path',d='M70 128H1530',stroke=LINE,stroke_width=1,fill='none')
        self.text(p,70,858,self.tr('guide'),11,MUTED)
        self.text(p,1530,858,f'{self.counter:02}',11,MUTED,code=True,anchor='start' if self.rtl else 'end')
        return p

    def swatch(self,p,color,x,y,w,h,radius=0):
        # Alpha is explicitly flattened onto the configured paper for a reproducible sample.
        self.rect(p,x,y,w,h,hex_rgb(color.effective(self.background)),radius)

    def codes(self,p,color,x,y,size=12,leading=21):
        rows=[]
        rgb=color.value[:3]
        if self.o.show_hex: rows.append(('HEX',color.hex))
        if self.o.show_rgb: rows.append(('RGB',', '.join(map(str,rgb))))
        if self.o.show_cmyk: rows.append(('CMYK~',', '.join(map(str,rgb_cmyk(rgb)))))
        if self.o.show_hsl: rows.append(('HSL',f'{rgb_hsl(rgb)[0]}°, {rgb_hsl(rgb)[1]}%, {rgb_hsl(rgb)[2]}%'))
        if color.value[3]<1: rows.append(('Alpha',f'{color.value[3]*100:.1f}%'))
        for i,(label,value) in enumerate(rows):
            self.text(p,x,y+i*leading,label+'  '+value,size,MUTED,code=True)

    def strip(self,p,color,x,y,width,height,labels=True):
        scale=tonal_scale(color.effective(self.background),self.o.tone_count,self.o.base_tone)
        cw=width/len(scale)
        for i,(number,rgb,original) in enumerate(scale):
            px=x+i*cw
            self.rect(p,px,y,cw+.2,height,hex_rgb(rgb))
            ink=readable_ink(rgb)
            if original:
                node(p,'circle',cx=self.x(px+cw/2),cy=y+15,r=4.5,fill=ink)
            if labels:
                self.text(p,px+cw/2,y+height-29,str(number),11,ink,600,code=True,anchor='middle')
                if cw>=58:
                    self.text(p,px+cw/2,y+height-12,hex_rgb(rgb)[1:],8.5,ink,code=True,anchor='middle')

    def cover(self):
        p=self.page('cover')
        if self.assets.get('logo'):
            node(p,'use',href='#'+self.assets['logo'],x=self.x(80,280),y=178,width=280,height=100)
        title_size=64 if len(self.o.brand_name)<=44 else 48 if len(self.o.brand_name)<=70 else 38
        self.text(p,80,385,self.o.brand_name,title_size,weight=500,width=1420)
        self.text(p,80,486,self.o.brand_subtitle,23,MUTED,width=1280)
        self.text(p,80,608,self.tr('guide'),16,MUTED)
        if self.colors:
            cw=1460/len(self.colors)
            for i,color in enumerate(self.colors):
                x=70+i*cw
                rgb=color.effective(self.background)
                self.swatch(p,color,x,674,cw+.3,145)
                if cw>85:
                    self.text(p,x+14,704,color.title(self.o.language),12,readable_ink(rgb),500,width=cw-25)
                    self.text(p,x+14,791,color.hex,11,readable_ink(rgb),code=True)
        return [p]

    def palette(self):
        pages=[]
        count=6 if self.o.palette_layout=='cards' else 8 if self.o.palette_layout=='compact' else 4
        for offset in range(0,len(self.colors),count):
            p=self.page('palette',len(pages),f'{len(self.colors)} COLORS / {self.o.tone_count} TONES')
            for i,color in enumerate(self.colors[offset:offset+count]):
                if self.o.palette_layout=='cards':
                    col,row=i%3,i//3; x=70+col*495; y=160+row*325
                    self.rect(p,x,y,470,300,'#FFFFFF',14,stroke=LINE)
                    self.swatch(p,color,x,y,470,128,14)
                    self.text(p,x+22,y+163,color.title(self.o.language),22,weight=500,width=430)
                    self.codes(p,color,x+22,y+205,12,20)
                elif self.o.palette_layout=='compact':
                    y=167+i*77
                    self.swatch(p,color,70,y,60,55,7)
                    self.text(p,155,y+32,color.title(self.o.language),19,weight=500,width=300)
                    self.codes(p,color,560,y+10,12,15)
                else:
                    y=164+i*153
                    self.text(p,70,y+16,f'{offset+i+1:02}',11,MUTED,code=True)
                    self.text(p,70,y+55,color.title(self.o.language),18 if len(color.title(self.o.language))>24 else 22,weight=500,width=205)
                    self.swatch(p,color,305,y,112,112,6)
                    if self.o.palette_tones:
                        self.strip(p,color,449,y,765,112)
                    else:
                        self.swatch(p,color,449,y,765,112,6)
                    self.codes(p,color,1260,y+18,11.5,22)
                    node(p,'path',d=f'M70 {y+133}H1530',stroke=LINE,stroke_width=.6)
            self.text(p,70,815,self.tr('approx'),10,MUTED)
            pages.append(p)
        return pages

    def tones(self):
        pages=[]
        for offset in range(0,len(self.colors),3):
            p=self.page('tones',len(pages),f'{self.o.tone_count} TONES / OKLAB')
            for i,color in enumerate(self.colors[offset:offset+3]):
                y=168+i*211
                self.text(p,70,y+20,color.title(self.o.language),22,weight=500)
                self.text(p,1530,y+20,color.hex,12,MUTED,code=True,anchor='start' if self.rtl else 'end')
                self.strip(p,color,70,y+42,1460,133)
            self.text(p,70,816,'● '+self.tr('original'),11,MUTED)
            pages.append(p)
        return pages

    def pairings(self):
        colors=list(self.colors)
        if self.o.include_neutrals:
            from color_guide_colors import Swatch, nearest_name
            for rgb in ((255,255,255),(0,0,0)):
                if not any(c.effective(self.background)==rgb for c in colors):
                    colors.append(Swatch((*rgb,1),name=nearest_name(rgb)))
        pairs=[]
        for bg in colors:
            for fg in colors:
                if fg is bg: continue
                ratio=contrast(fg.effective(self.background),bg.effective(self.background))
                if self.o.pair_filter=='normal' and ratio<4.5: continue
                if self.o.pair_filter=='large' and ratio<3: continue
                pairs.append((fg,bg,ratio))
        if self.o.pair_sort=='contrast': pairs.sort(key=lambda item:-item[2])
        total=len(pairs); pairs=pairs[:self.o.max_pairs]
        pages=[]
        for offset in range(0,len(pairs),12):
            p=self.page('pairings',len(pages),f'{len(pairs)} / {total} PAIRS')
            for i,(fg,bg,ratio) in enumerate(pairs[offset:offset+12]):
                col,row=i%4,i//4; x=70+col*370; y=160+row*214
                self.swatch(p,bg,x,y,350,194,13)
                foreground=hex_rgb(fg.effective(self.background)); level=contrast_level(ratio)
                self.text(p,x+20,y+72,'أب' if self.rtl else 'Aa',55,foreground,500)
                self.text(p,x+329,y+37,f'{ratio:.2f}:1',26,foreground,700,code=True,anchor='start' if self.rtl else 'end')
                # The sample remains large even for combinations classified only for large text.
                self.text(p,x+20,y+111,'ألوان واضحة' if self.rtl else 'Clear color',32,foreground,500)
                self.rect(p,x+12,y+137,326,45,'#FFFFFF',8)
                badge=level if level in ('AA','AAA') else self.tr('large') if level=='Large AA' else self.tr('low')
                self.text(p,x+23,y+157,badge,11,DARK,600)
                self.text(p,x+23,y+174,fg.hex+' / '+bg.hex,9,MUTED,code=True)
            self.text(p,70,819,self.tr('contrast_note'),10,MUTED)
            pages.append(p)
        if not pages:
            p=self.page('pairings')
            self.text(p,70,220,'لا توجد تركيبات ضمن الفلتر المحدد.' if self.rtl else 'No color pairs match the selected filter.',22)
            pages=[p]
        return pages

    def shape(self,p,x,y,size,fill):
        actual_x=self.x(x,size)
        if self.o.symbol=='custom':
            node(p,'use',href='#'+self.assets['symbol'],x=actual_x,y=y,width=size,height=size,color=fill)
        elif self.o.symbol=='circle':
            node(p,'circle',cx=actual_x+size/2,cy=y+size/2,r=size/2,fill=fill)
        elif self.o.symbol=='square':
            node(p,'rect',x=actual_x,y=y,width=size,height=size,rx=size*.1,fill=fill)
        else:
            node(p,'path',d=f'M{actual_x+size/2},{y} L{actual_x+size},{y+size/2} L{actual_x+size/2},{y+size} L{actual_x},{y+size/2} Z',fill=fill)

    def combinations(self):
        pages=[]
        # Every directed foreground/background pair is shown; blocks paginate rather than truncate.
        rows_per_page=min(7,len(self.colors))
        row_height=min(150,630/rows_per_page)
        size=min(106,row_height-(31 if self.o.combination_details else 8))
        for bg_offset in range(0,len(self.colors),rows_per_page):
            for fg_offset in range(0,len(self.colors),7):
                p=self.page('combinations',len(pages))
                editorial=self.o.combination_layout=='editorial'
                if editorial:
                    description=self.o.combination_description or (
                        'تُظهر هذه الصفحة تكوينات ألوان الهوية. أعطِ الأولوية للتباين الواضح عند استخدام النصوص والعناصر الوظيفية، وراجع النسبة بحسب حجم النص وطبيعة الاستخدام.'
                        if self.rtl else 'Explore your brand color combinations. Prioritize clear contrast for text and functional elements. Review contrast against the intended text size and context.')
                    self.text(p,70,360,description,22,DARK,width=405,max_lines=10)
                    self.text(p,70,730,self.tr('decorative'),15,MUTED,width=405,max_lines=4)
                for row,bg in enumerate(self.colors[bg_offset:bg_offset+rows_per_page]):
                    y=166+row*row_height
                    if not editorial:
                        self.text(p,70,y+min(47,size*.55),bg.title(self.o.language),16,weight=500,width=205)
                        self.text(p,70,y+min(70,size*.55+26),bg.hex,10,MUTED,code=True)
                    for col,fg in enumerate(self.colors[fg_offset:fg_offset+7]):
                        x=(550+col*140) if editorial else (320+col*172)
                        if fg is bg: continue
                        bgrgb=bg.effective(self.background); fgrgb=fg.effective(self.background)
                        ratio=contrast(fgrgb,bgrgb)
                        # Use the same silhouette for frame and foreground so custom logos remain recognizable.
                        self.shape(p,x,y,size,hex_rgb(bgrgb))
                        self.shape(p,x+size/4,y+size/4,size/2,hex_rgb(fgrgb))
                        if self.o.combination_details:
                            self.text(p,x+size/2,y+size+13,f'{ratio:.2f}:1'+(' *' if ratio<4.5 else ''),10,MUTED,code=True,anchor='middle')
                            self.text(p,x+size/2,y+size+26,fg.hex,9,MUTED,code=True,anchor='middle')
                        elif ratio<4.5:
                            self.text(p,x+size+10,y+13,'*',15,DARK,code=True)
                if not editorial: self.text(p,70,813,self.tr('decorative'),10,MUTED,width=1460)
                pages.append(p)
        return pages

    def gradient_pages(self):
        pages=[]
        for offset in range(0,len(self.gradients),4):
            p=self.page('gradients',len(pages))
            for i,gradient in enumerate(self.gradients[offset:offset+4]):
                y=164+i*153; identifier=self.token+'-gradient-'+str(offset+i)
                kind='radialGradient' if gradient['type']=='radial' else 'linearGradient'
                g=node(self.defs,kind,id=identifier)
                if kind=='linearGradient':
                    g.set('x1','0');g.set('y1','0');g.set('x2','1');g.set('y2','0')
                for stop in gradient['stops']:
                    node(g,'stop',offset=stop['offset'],stop_color=hex_rgb(stop['value'][:3]),stop_opacity=stop['value'][3])
                self.text(p,70,y+25,gradient['label'],18,weight=500,width=230)
                self.text(p,70,y+55,str(len(gradient['stops']))+' STOPS',11,MUTED,code=True)
                self.rect(p,330,y,1200,96,'url(#'+identifier+')',7)
                # Printed stop values stay editable. Long gradients wrap onto up to two lines.
                value=' · '.join(hex_rgb(s['value'][:3]) for s in gradient['stops'])
                self.text(p,330,y+119,value,10,MUTED,code=True,width=1200)
            self.text(p,70,815,self.tr('gradient_note'),10,MUTED)
            pages.append(p)
        if not pages:
            p=self.page('gradients')
            self.text(p,70,220,'لا توجد تدرجات في التحديد.' if self.rtl else 'No gradients found in the selection.',22)
            pages=[p]
        return pages

    def render(self):
        pages=[]
        for key,method in [('cover',self.cover),('palette',self.palette),('tones',self.tones),
                           ('pairings',self.pairings),('combinations',self.combinations),('gradients',self.gradient_pages)]:
            if getattr(self.o,'page_'+key): pages.extend(method())
        if not pages:
            raise inkex.AbortExtension('Choose at least one output section.')
        if len(pages)>128:
            raise inkex.AbortExtension('The guide would exceed 128 pages. Reduce colors or disable sections.')
        return pages
