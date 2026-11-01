import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import inkex
from lxml import etree

from color_guide_colors import (contrast,contrast_level,from_oklab,oklab,tonal_scale,luminance,nearest_name,name_overrides,rgba)
from color_guide_pro import ColorGuidePro, ColorReader, MARKER, SOURCES, SETTINGS, DEFAULTS

ROOT=Path(__file__).resolve().parents[1]


def document(content='',extra=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" width="800" height="600" viewBox="0 0 800 600" {extra}>{content}</svg>').encode()


ART='<g id="art"><rect id="one" width="50" height="50" fill="#0E5E6F"/><circle id="two" cx="120" cy="50" r="25" fill="#D96A2C"/></g>'


def load(source=None,*args):
    ex=ColorGuidePro();ex.options=ex.arg_parser.parse_args(args);ex.load(io.BytesIO(source or document(ART)));return ex


def apply(source=None,*args):
    ex=load(source,*args);ex.effect();return ex


def guide(ex):
    return next(n for n in ex.svg if n.get(MARKER)=='guide')


def reader(ex):
    ex.validate();r=ColorReader(ex.svg,ex.options);return r.read([ex.svg.getElementById('art')])


class ColorMathTests(unittest.TestCase):
    def test_wcag_known_values_and_unrounded_boundaries(self):
        self.assertAlmostEqual(contrast((0,0,0),(255,255,255)),21)
        self.assertEqual(contrast((8,50,100),(8,50,100)),1)
        self.assertEqual(contrast_level(4.499999),'Large AA')
        self.assertEqual(contrast_level(4.5),'AA')
        self.assertEqual(contrast_level(6.99999),'AA')
        self.assertEqual(contrast_level(7),'AAA')
        self.assertEqual(contrast_level(2.99999),'Low')

    def test_oklab_roundtrip_reference_colors(self):
        for rgb in [(255,0,0),(0,255,0),(0,0,255),(0,0,0),(255,255,255),(14,94,111),(227,215,180)]:
            self.assertTrue(all(abs(a-b)<=1 for a,b in zip(rgb,from_oklab(oklab(rgb)))))
        self.assertAlmostEqual(oklab((255,0,0))[0],0.62795536,places=6)

    def test_tones_preserve_original_and_progress_from_light_to_dark(self):
        for rgb in [(14,94,111),(255,0,0),(255,255,255),(0,0,0),(227,215,180)]:
            for count in (5,7,9,11):
                scale=tonal_scale(rgb,count)
                self.assertEqual(len(scale),count)
                self.assertEqual([s[1] for s in scale if s[2]],[rgb])
                brightness=[luminance(s[1]) for s in scale]
                self.assertTrue(all(a>=b-.002 for a,b in zip(brightness,brightness[1:])),(rgb,count))
        self.assertEqual(tonal_scale((14,94,111),11,8)[7][1],(14,94,111))
        with self.assertRaises(ValueError): tonal_scale((1,2,3),7,10)

    def test_names_are_attributed_and_approximate_matches_are_not_claimed_exact(self):
        data=json.loads((ROOT/'color_guide_names.json').read_text())
        self.assertEqual(data['license'],'CC0-1.0')
        self.assertGreaterEqual(len(data['colors']),100)
        for entry in data['colors']:
            found=nearest_name(rgba(entry['hex'])[:3])
            self.assertTrue(found['exact']);self.assertTrue(found['ar'])
        self.assertFalse(nearest_name((1,2,3))['exact'])
        self.assertEqual(name_overrides('#0e5e6f=Petrol|بترولي')['#0E5E6F']['ar'],'بترولي')
        with self.assertRaises(ValueError): name_overrides('bad=name')

    def test_css_rgba_and_inx_color_uint(self):
        self.assertEqual(rgba('4294967295'),(255,255,255,1))
        self.assertEqual(rgba('rgba(10,20,30,0.5)'),(10,20,30,.5))


class SourceTests(unittest.TestCase):
    def test_group_css_currentcolor_stroke_and_alpha(self):
        src=document('<style>.paint{fill:currentColor;stroke:rgb(10,20,30);stroke-width:2}</style>'
                     '<g id="art" color="#00AA33" opacity="0.5"><rect class="paint" width="50" height="50" fill-opacity="0.5"/></g>')
        colors,_=reader(load(src))
        self.assertEqual({c.value for c in colors},{(0,170,51,.25),(10,20,30,.5)})

    def test_hidden_sources_are_ignored(self):
        colors,_=reader(load(document('<g id="art"><rect width="1" height="1" fill="red"/>'
                     '<g display="none"><rect width="1" height="1" fill="blue"/></g></g>')))
        self.assertEqual([c.hex for c in colors],['#FF0000'])

    def test_repeated_colors_are_deduplicated_and_fill_stroke_switches_work(self):
        src=document('<g id="art" fill="red"><rect width="1" height="1" stroke="blue"/>'
                     '<circle cx="3" cy="3" r="1"/></g>')
        colors,_=reader(load(src,'--include_stroke=false'));self.assertEqual(len(colors),1)
        colors,_=reader(load(src,'--include_fill=false'));self.assertEqual([c.hex for c in colors],['#0000FF'])

    def test_linked_gradient_stops_and_opacity(self):
        src=document('<defs><linearGradient id="base"><stop stop-color="red"/><stop offset="100%" stop-color="blue" stop-opacity="0.5"/></linearGradient>'
                     '<linearGradient id="mid" xlink:href="#base"/><radialGradient id="gradient" xlink:href="#mid"/></defs>'
                     '<g id="art" opacity="0.5"><rect width="50" height="50" fill="url(#gradient)"/></g>')
        colors,gradients=reader(load(src));self.assertEqual({c.value for c in colors},{(255,0,0,.5),(0,0,255,.25)})
        self.assertEqual(gradients[0]['type'],'radial');self.assertEqual(gradients[0]['stops'][-1]['offset'],1)
        with self.assertRaises(inkex.AbortExtension): reader(load(src,'--include_gradients=false'))

    def test_local_clone_inherits_instance_fill(self):
        src=document('<defs><rect id="shape" width="20" height="20"/></defs><g id="art"><use href="#shape" fill="#123456"/></g>')
        colors,_=reader(load(src));self.assertEqual([c.hex for c in colors],['#123456'])

    def test_line_and_empty_text_container_do_not_invent_black_fill(self):
        src=document('<g id="art"><line x1="0" y1="0" x2="100" y2="100" stroke="blue"/>'
                     '<text><tspan fill="red">Color</tspan></text></g>')
        colors,_=reader(load(src));self.assertEqual({c.hex for c in colors},{'#FF0000','#0000FF'})

    def test_distinct_alpha_values_are_not_merged_to_eight_bit_alpha(self):
        src=document('<g id="art"><rect width="20" height="20" fill="red" opacity="0.5"/>'
                     '<rect x="30" width="20" height="20" fill="red" opacity="0.501"/></g>')
        colors,_=reader(load(src));self.assertEqual(len(colors),2)

    def test_circular_gradient_fails_without_changing_document(self):
        src=document('<defs><linearGradient id="a" href="#b"/><linearGradient id="b" href="#a"/></defs>'
                     '<g id="art"><rect width="20" height="20" fill="url(#a)"/></g>')
        ex=load(src,'--id=art');before=etree.tostring(ex.svg)
        with self.assertRaises(inkex.AbortExtension): ex.effect()
        self.assertEqual(etree.tostring(ex.svg),before)


class GuideTests(unittest.TestCase):
    def test_default_creates_only_palette_and_preserves_source_artwork(self):
        ex=load(None,'--id=art');original=etree.tostring(ex.svg.getElementById('art'));ex.effect()
        self.assertEqual(etree.tostring(ex.svg.getElementById('art')),original)
        self.assertEqual([p.get('data-cgp-section') for p in guide(ex).xpath('.//*[@data-cgp-section]')],['palette'])
        self.assertEqual(len(ex.svg.xpath('//inkscape:page',namespaces=inkex.NSS)),2)

    def test_each_section_can_be_generated_independently(self):
        for section in ('cover','palette','tones','pairings','combinations','gradients'):
            options=['--id=art','--page_palette=false','--page_'+section+'=true']
            ex=apply(None,*options)
            self.assertEqual({p.get('data-cgp-section') for p in guide(ex).xpath('.//*[@data-cgp-section]')},{section})

    def test_disabled_native_pages_do_not_add_page_rectangles(self):
        ex=apply(None,'--id=art','--native_pages=false')
        self.assertFalse(ex.svg.xpath('//inkscape:page',namespaces=inkex.NSS))

    def test_refresh_reads_changed_source_and_uses_saved_brand_settings(self):
        first=apply(None,'--id=art','--brand_name=Test Brand','--custom_names=#0E5E6F=Petrol|بترولي')
        first.svg.getElementById('one').style['fill']='#00FF00'
        second=apply(etree.tostring(first.svg),'--action=refresh')
        self.assertEqual(len([n for n in second.svg if n.get(MARKER)=='guide']),1)
        self.assertIn('#00FF00',''.join(guide(second).itertext()))
        self.assertIn('Test Brand',guide(second).get(inkex.addNS('label','inkscape')))
        self.assertEqual(len(second.svg.xpath('//inkscape:page',namespaces=inkex.NSS)),2)
        self.assertNotIn('export_dir',json.loads(guide(second).get(SETTINGS)))

    def test_saved_refresh_keeps_all_original_sources_when_one_source_is_selected(self):
        first=apply(None,'--id=art')
        second=apply(etree.tostring(first.svg),'--action=refresh','--id=one')
        self.assertEqual(json.loads(guide(second).get(SOURCES)),['art'])
        self.assertEqual(guide(second).get('data-cgp-color-count'),'2')

    def test_missing_source_on_refresh_fails_atomically(self):
        first=apply(None,'--id=art');first.svg.getElementById('art').delete()
        second=load(etree.tostring(first.svg),'--action=refresh');before=etree.tostring(second.svg)
        with self.assertRaises(inkex.AbortExtension): second.effect()
        self.assertEqual(etree.tostring(second.svg),before)

    def test_bad_options_and_excess_colors_leave_artwork_unchanged(self):
        for arg in ('--max_colors=1','--tone_count=6','--font_scale=nan','--custom_names=invalid','--page_palette=false'):
            ex=load(None,'--id=art',arg);before=etree.tostring(ex.svg)
            with self.assertRaises(inkex.AbortExtension): ex.effect()
            self.assertEqual(etree.tostring(ex.svg),before,arg)

    def test_parent_and_child_selected_are_read_only_once(self):
        ex=apply(None,'--id=art','--id=one')
        self.assertEqual(json.loads(guide(ex).get(SOURCES)),['art'])

    def test_arabic_output_has_rtl_text_and_translated_names(self):
        ex=apply(None,'--id=art','--language=ar')
        self.assertIn('لوحة الألوان',''.join(guide(ex).itertext()))
        self.assertTrue(guide(ex).xpath('.//svg:text[@direction="rtl"]',namespaces=inkex.NSS))

    def test_mm_viewbox_scale_preserves_existing_page_geometry(self):
        src=document(ART).replace(b'width="800" height="600"',b'width="200mm" height="150mm"')
        ex=apply(src,'--id=art')
        pages=ex.svg.xpath('//inkscape:page',namespaces=inkex.NSS)
        sx=(200*96/25.4)/800
        self.assertAlmostEqual(pages[-1].width,1600/sx)
        self.assertEqual(ex.svg.get('width'),'200mm')

    def test_custom_symbol_copies_geometry_with_unique_ids_and_currentcolor(self):
        src=document(ART+'<g id="mark" transform="translate(200,0)"><path id="mark-path" d="M0 0H50V50H0Z M10 10V40H40V10Z" fill-rule="evenodd" fill="red"/></g>')
        ex=apply(src,'--id=art','--page_palette=false','--page_combinations=true','--symbol=custom','--symbol_id=mark')
        ids=[n.get('id') for n in ex.svg.iter() if n.get('id')]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(guide(ex).xpath('.//svg:use',namespaces=inkex.NSS))
        self.assertIn('currentColor',etree.tostring(guide(ex)).decode())
        self.assertEqual(ex.svg.getElementById('mark-path').get('fill'),'red')

    def test_document_wide_css_does_not_recolor_generated_samples(self):
        src=document('<style>rect{fill:#F00000;stroke:blue} g{opacity:0.5} text{fill:red}</style>'+ART)
        ex=apply(src,'--id=art')
        generated=guide(ex)
        self.assertEqual(generated.get_computed_style('opacity'),1)
        for n in generated.xpath('.//svg:rect[@fill] | .//svg:text[@fill]',namespaces=inkex.NSS):
            self.assertEqual(str(n.get_computed_style('fill')).upper(),n.get('fill').upper())

    def test_seven_color_combination_matrix_fits_one_page(self):
        shapes=''.join(f'<rect x="{i*30}" width="20" height="20" fill="#{i+1:02x}0080"/>' for i in range(7))
        ex=apply(document('<g id="art">'+shapes+'</g>'),'--id=art','--page_palette=false','--page_combinations=true')
        pages=guide(ex).xpath('.//*[@data-cgp-section]')
        self.assertEqual(len(pages),1)
        self.assertEqual(pages[0].get('data-cgp-section'),'combinations')

    def test_rtl_heading_glyph_anchor_starts_at_right_edge(self):
        ex=apply(None,'--id=art','--language=ar')
        headings=[n for n in guide(ex).xpath('.//svg:text',namespaces=inkex.NSS) if n.text=='لوحة الألوان']
        self.assertEqual(headings[0].get('direction'),'rtl')
        self.assertEqual(headings[0].get('text-anchor'),'start')

    def test_custom_page_size_export_snapshot_uses_requested_paper(self):
        from color_guide_pro import snapshot_svg
        ex=apply(None,'--id=art','--page_preset=custom','--page_width=1000','--page_height=1000','--paper=#F5F1E9')
        g=guide(ex);pages=g.xpath('.//*[@data-cgp-section]')
        svg=snapshot_svg(pages,g[0],1000,1000,70)
        backgrounds=svg.xpath('./svg:rect',namespaces=inkex.NSS)
        self.assertEqual(backgrounds[0].get('fill'),'#F5F1E9')
        self.assertEqual(float(backgrounds[0].get('height')),1000)

    def test_descriptors_schema_and_frontend_parameter_values(self):
        schema=etree.RelaxNG(etree.parse(str(Path(inkex.__file__).parent/'tester/inkscape.extension.rng')))
        for name in ('color_guide_pro.inx','color_guide_manage.inx'): schema.assertValid(etree.parse(str(ROOT/name)))
        tree=etree.parse(str(ROOT/'color_guide_pro.inx'));args=['--id=art'];names=[]
        for param in tree.findall('.//{*}param'):
            name=param.get('name');names.append(name)
            if param.get('type')=='notebook': value=param.find('{*}page').get('name')
            elif param.get('type')=='optiongroup': value=param.find('{*}option').get('value')
            else: value=param.text or ''
            args.append('--'+name+'='+value)
        self.assertEqual(len(names),len(set(names)))
        self.assertEqual(set(names),set(DEFAULTS))
        apply(None,*args)


class ExportTests(unittest.TestCase):
    def test_svg_json_gpl_csv_and_existing_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            args=['--id=art','--export_dir='+folder,'--export_svg=true','--export_json=true','--export_gpl=true','--export_csv=true']
            apply(None,*args);first=Path(folder)/'Color-Guide'
            self.assertEqual({p.suffix for p in first.iterdir()},{'.svg','.json','.gpl','.csv'})
            snapshot=inkex.load_svg(str(first/'Color-Guide.svg')).getroot()
            self.assertEqual(len(snapshot.xpath('//inkscape:page',namespaces=inkex.NSS)),1)
            data=json.loads((first/'Color-Guide.json').read_text());self.assertEqual(len(data['colors']),2)
            original=(first/'Color-Guide.json').read_bytes();apply(None,*args)
            self.assertEqual((first/'Color-Guide.json').read_bytes(),original)
            self.assertTrue((Path(folder)/'Color-Guide-2').is_dir())

    def test_renderer_export_failure_leaves_no_partial_files_or_svg_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            ex=load(None,'--id=art','--export_dir='+folder,'--export_pdf=true');before=etree.tostring(ex.svg)
            with mock.patch('inkex.command.inkscape',side_effect=RuntimeError('renderer unavailable')):
                with self.assertRaises(inkex.AbortExtension): ex.effect()
            self.assertEqual(etree.tostring(ex.svg),before);self.assertFalse(list(Path(folder).iterdir()))

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'),'Requires real Inkscape')
    def test_native_multipage_pdf_and_png_only_contain_chosen_sections(self):
        from pypdf import PdfReader
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            apply(None,'--id=art','--page_cover=true','--page_pairings=true','--export_dir='+folder,
                  '--export_pdf=true','--export_png=true','--png_width=800')
            out=Path(folder)/'Color-Guide'
            pdf=PdfReader(out/'Color-Guide.pdf')
            self.assertEqual(len(pdf.pages),3)
            images=sorted(out.glob('*.png'));self.assertEqual(len(images),3)
            for image in images:
                with Image.open(image) as bitmap: self.assertEqual(bitmap.size,(800,450))
