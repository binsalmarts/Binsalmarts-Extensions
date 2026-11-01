import io
import os
from pathlib import Path
import tempfile
import unittest

import inkex
from lxml import etree
from PIL import Image
from pypdf import PdfReader

from logo_export_pro import LogoExportPro
from logo_export_kit import (ROLE, LABEL, TemplateKit, combinations, contrast, discover,
                             palette, recolor, template_info)


def fixture():
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS['inkscape']}" width="600" height="400" viewBox="0 0 300 200">
    <g id="h" inkscape:label="-ex-horizontal-bg" transform="translate(10 20)">
      <rect id="bg" inkscape:label="-bg-" width="100" height="100" fill="#ffffff"/>
      <path id="mark" inkscape:label="-icon-" d="M10 60H30V80H10Z" fill="#397ce0"/>
      <path id="word" inkscape:label="-text-" d="M35 65H75V70H35Z" fill="#0f1b34"/>
      <circle id="keep" inkscape:label="-keep-" cx="92" cy="92" r="2" fill="#ff0088"/>
    </g>
    <g id="safe" inkscape:label="-ex-icon-safe" transform="translate(130 20)">
      <rect id="frame" inkscape:label="-frame-" width="100" height="100" fill="none"/>
      <path id="white" inkscape:label="-icon-" d="M10 60H30V80H10Z" fill="white"/>
    </g>
    <g id="custom" inkscape:label="-ex-footer-tight" transform="translate(130 140)">
      <text id="arabic" inkscape:label="-text-" x="0" y="0" style="font-family:DejaVu Sans;font-size:20px;fill:#0f1b34">سلام</text>
    </g>
    <rect id="private" x="250" y="100" width="10" height="10" fill="red"/>
    <g id="nested" inkscape:label="-ex-nested-bg" transform="translate(10 140)">
      <rect id="nestedframe" inkscape:label="-frame-" width="50" height="50" fill="none"/>
      <svg width="50" height="50" viewBox="0 0 100 100">
        <rect id="nestedbg" inkscape:label="-bg-" width="100" height="100" fill="#0f1b34"/>
        <rect id="nestedicon" inkscape:label="-icon-" x="20" y="20" width="20" height="20" fill="#397ce0"/>
      </svg>
    </g>
    </svg>'''.encode()


def extension(*args):
    ext = LogoExportPro()
    ext.options = ext.arg_parser.parse_args(['--source_mode=templates', '--template_scope=document', '--open_folder=false', *args])
    ext.load(io.BytesIO(fixture()))
    return ext


class KitUnitTests(unittest.TestCase):
    def test_palette_normalizes_and_rejects_bad_inputs(self):
        self.assertEqual([c.color for c in palette('Blue=#37e; Same=#3377ee; Navy=#001122', True)],
                         ['#3377ee', '#001122', '#ffffff', '#000000'])
        for text in ('', 'Blue=red', 'Blue=#12345678', 'X=#111;X=#222'):
            with self.subTest(text=text), self.assertRaises(inkex.AbortExtension):
                palette(text)

    def test_contrast_and_recipes_omit_low_contrast_and_duplicates(self):
        self.assertEqual(contrast('#ffffff', '#000000'), 21)
        o = extension().options
        colors = palette('White=#fff; Black=#000; Blue=#397ce0')
        variants = combinations(colors, colors, True, True, o)
        keys = [(v['ink'].color, v['text'].color, v['bg'].color) for v in variants]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(contrast(i, b) >= 3 and contrast(t, b) >= 3 for i, t, b in keys))
        self.assertTrue(any(i == '#397ce0' and t != i for i, t, _ in keys))

    def test_discovery_accepts_custom_templates_and_selection_scope(self):
        root = extension().svg
        self.assertEqual([n.get('id') for n in discover(root, [], '-ex-', 'document')], ['h', 'safe', 'custom', 'nested'])
        self.assertEqual([n.get('id') for n in discover(root, [root.getElementById('safe')], '-ex-', 'selection')], ['safe'])
        with self.assertRaisesRegex(inkex.AbortExtension, 'No named'):
            discover(root, [], '-ex-', 'selection')
        self.assertEqual(template_info('-ex-event-badge-safe', '-ex-'), ('event-badge', 'safe'))
        self.assertEqual(template_info('-ex-hz-bg', '-ex-'), ('horizontal', 'background'))

    def test_name_only_recipes_are_not_repeated_for_nonexistent_icons(self):
        o = extension().options
        colors = palette('Navy=#0f1b34; Blue=#397ce0', True)
        variants = combinations(colors, colors, True, False, o, has_icon=False)
        names = [v['text'].color for v in variants]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), {s.color for s in colors})

    def test_nested_and_duplicate_templates_are_actionable(self):
        root = extension().svg
        root.getElementById('mark').set(LABEL, '-ex-child-tight')
        with self.assertRaisesRegex(inkex.AbortExtension, 'nested'):
            discover(root, [], '-ex-', 'document')
        root.getElementById('mark').set(LABEL, '-icon-')
        root.getElementById('safe').set(LABEL, '-ex-horizontal-bg')
        with self.assertRaisesRegex(inkex.AbortExtension, 'unique'):
            discover(root, [], '-ex-', 'document')

    def test_recolor_preserves_geometry_holes_opacity_and_keep(self):
        root = extension().svg
        before = etree.tostring(root)
        recolored = recolor(root, {'icon': '#397ce0', 'text': '#ffffff', 'bg': '#0f1b34'})
        self.assertEqual(etree.tostring(root), before)
        self.assertEqual(recolored.getElementById('h').transform, root.getElementById('h').transform)
        self.assertEqual(recolored.getElementById('keep').get('fill'), '#ff0088')
        self.assertEqual(recolored.getElementById('word').specified_style()['fill'], '#ffffff')
        self.assertEqual(recolored.getElementById('bg').specified_style()['fill'], '#0f1b34')

    def test_assign_role_changes_only_metadata(self):
        ext = extension('--source_action=kit_text', '--id=mark')
        d = ext.svg.getElementById('mark').get('d')
        ext.effect()
        self.assertEqual(ext.svg.getElementById('mark').get(ROLE), 'text')
        self.assertEqual(ext.svg.getElementById('mark').get('d'), d)

    def test_descriptor_parameters_match_runtime_defaults(self):
        root = etree.parse(str(Path(__file__).resolve().parents[1] / 'logo_export_pro.inx'))
        ns = {'e': 'http://www.inkscape.org/namespace/inkscape/extension'}
        options = extension().options
        for param in root.xpath('//e:param[not(@type="notebook")]', namespaces=ns):
            self.assertTrue(hasattr(options, param.get('name')), param.get('name'))
        self.assertEqual(options.source_mode, 'templates')


@unittest.skipUnless(os.environ.get('LOGO_KIT_NATIVE_TEST') == '1', 'Set LOGO_KIT_NATIVE_TEST=1 for real Inkscape integration.')
class KitNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.ext = extension('--output_dir=' + cls.temp.name, '--identity_palette=Navy=#0f1b34;Blue=#397ce0',
                            '--identity_bw=false', '--raster_sizes=128', '--format_webp=true')
        cls.before = etree.tostring(cls.ext.svg)
        cls.ext.effect()
        cls.kit = cls.ext.output_path

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_format_is_valid_and_original_unchanged(self):
        self.assertEqual(etree.tostring(self.ext.svg), self.before)
        formats = set()
        for variant in self.ext.manifest['variants']:
            for filename in variant['files']:
                file = self.kit / filename
                formats.add(file.suffix)
                if file.suffix in ('.png', '.jpg', '.webp'):
                    with Image.open(file) as image:
                        image.verify()
                elif file.suffix == '.pdf':
                    reader = PdfReader(file)
                    self.assertEqual(len(reader.pages), 1)
                    self.assertAlmostEqual(float(reader.pages[0].mediabox.width), variant['width_px'] * .75, places=2)
                elif file.suffix == '.eps':
                    self.assertTrue(file.read_bytes().startswith(b'%!PS-Adobe-'))
                elif file.suffix == '.svg':
                    svg = inkex.load_svg(str(file)).getroot()
                    self.assertFalse(svg.xpath('.//svg:text'))
                    self.assertIsNone(svg.getElementById('private'))
                    self.assertIsNone(svg.getElementById('frame'))
        self.assertEqual(formats, {'.svg', '.png', '.jpg', '.pdf', '.eps', '.webp'})

    def test_safe_frame_preserves_blank_space_and_offcenter_position(self):
        item = next(v for v in self.ext.manifest['variants'] if v['template'] == '-ex-icon-safe' and v['recipe'] == 'original')
        self.assertAlmostEqual(item['width_px'], 200)
        self.assertAlmostEqual(item['height_px'], 200)
        png = self.kit / next(f for f in item['files'] if f.endswith('.png'))
        with Image.open(png) as image:
            self.assertEqual(image.size, (128, 128))
            bounds = image.getchannel('A').getbbox()
            self.assertLess(bounds[0], 20)
            self.assertGreater(bounds[1], 70)
        jpg = self.kit / next(f for f in item['files'] if f.endswith('.jpg'))
        with Image.open(jpg) as image:
            self.assertLess(sum(image.getpixel((0, 0))), 200)

    def test_embedded_svg_preserves_canvas_and_normalized_artwork_position(self):
        item = next(v for v in self.ext.manifest['variants'] if v['template'] == '-ex-nested-bg' and v['recipe'] == 'original')
        self.assertEqual((item['width_px'], item['height_px']), (100, 100))
        with Image.open(self.kit / next(f for f in item['files'] if f.endswith('.png'))) as image:
            self.assertEqual(image.getchannel('A').getextrema(), (255, 255))
            self.assertEqual(image.getpixel((0, 0))[:3], (15, 27, 52))
            self.assertEqual(image.getpixel((38, 38))[:3], (57, 124, 224))

    def test_mixed_colors_and_html_links_match_manifest(self):
        item = next(v for v in self.ext.manifest['variants'] if v['template'] == '-ex-horizontal-bg' and v['icon'] == '#397ce0' and v['name'] == '#ffffff')
        svg = inkex.load_svg(str(self.kit / next(f for f in item['files'] if f.endswith('.svg')))).getroot()
        self.assertEqual(svg.getElementById('mark').specified_style()['fill'], '#397ce0')
        self.assertEqual(svg.getElementById('word').specified_style()['fill'], '#ffffff')
        self.assertEqual(svg.getElementById('keep').specified_style()['fill'], '#ff0088')
        page = etree.HTML((self.kit / 'index.html').read_bytes())
        self.assertEqual(len(page.xpath('//article')), len(self.ext.manifest['variants']))
        for img in page.xpath('//img'):
            self.assertTrue((self.kit / img.get('src')).is_file())
        name_only = [v for v in self.ext.manifest['variants'] if v['template'] == '-ex-footer-tight' and v['recipe'] != 'original']
        self.assertTrue(all(v['icon'] is None for v in name_only))
        self.assertEqual(len(name_only), len({v['name'] for v in name_only}))


if __name__ == '__main__':
    unittest.main()
