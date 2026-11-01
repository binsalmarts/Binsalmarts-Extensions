import io
import json
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import inkex
from lxml import etree
from PIL import Image, ImageChops
from pypdf import PdfReader

from logo_export_pro import (Component, LogoExportPro, build_master, css_color,
                             artwork_role, visual_distance, visual_signature,
                             component_gap, current_geometry, export_geometry,
                             layout_geometry, monochrome, parse_raster_sizes,
                             prefix_ids, safe_stem)

ROOT = Path(__file__).resolve().parents[1]
NS = 'http://www.w3.org/2000/svg'


def document(name='BinSalem', extra='', fill='url(#paint)'):
    return (f'<svg xmlns="{NS}" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'xmlns:inkscape="{inkex.NSS["inkscape"]}" xmlns:sodipodi="{inkex.NSS["sodipodi"]}" '
            'width="800" height="600" viewBox="0 0 800 600">'
            '<sodipodi:namedview><inkscape:page x="0" y="0" width="800" height="600"/>'
            '<inkscape:page x="900" y="0" width="800" height="600"/></sodipodi:namedview>'
            '<defs><linearGradient id="paint"><stop stop-color="#2563eb"/>'
            '<stop offset="1" stop-color="#7c3aed"/></linearGradient></defs>'
            f'<g id="icon" transform="translate(10,15)"><rect id="body" width="100" height="100" rx="20" fill="{fill}"/>'
            '<circle cx="50" cy="50" r="25" fill="#fff"/></g>'
            f'<g id="name" transform="translate(180,75)" fill="#172033"><text x="0" y="0" '
            f'style="font-family:DejaVu Sans;font-size:48px">{name}</text></g>'
            f'<text id="secret" x="50" y="500">Do not export this</text>{extra}</svg>').encode()


def load(source=None, *args):
    ext = LogoExportPro()
    ext.options = ext.arg_parser.parse_args(['--open_folder=false', '--source_mode=paired',
        '--role_assignment=icon_first', '--sizing_mode=manual', '--gap_mode=manual', '--layout_as_designed=false', *args])
    ext.load(io.BytesIO(source or document()))
    return ext


def current_load(source=None, *args):
    return load(source, '--source_mode=complete', '--role_assignment=assigned', '--sizing_mode=original',
                '--gap_mode=current', '--layout_as_designed=true', *args)


def component(width, height, artwork='<rect width="100" height="100" fill="#2563eb"/>'):
    svg = inkex.load_svg(io.BytesIO(f'<svg xmlns="{NS}" width="{width}" height="{height}" '
                                    f'viewBox="0 0 {width} {height}">{artwork}</svg>'.encode())).getroot()
    return Component(svg, width, height)


def ready_document(flat=False, duplicate=False):
    icon = ('<path d="M50 0A50 50 0 0 1 100 50H78A28 28 0 0 0 50 22Z" fill="#e52b20"/>'
            '<path d="M0 50A50 50 0 0 0 50 100V78A28 28 0 0 1 22 50Z" fill="#e52b20"/>'
            '<path d="M40 35H60V65H40Z" fill="#e52b20"/>')
    name = ('<path d="M0 0H210V12H0Z" fill="#111"/>'
            '<path d="M10 28H220V42H10Z" fill="#111"/>'
            '<path d="M0 48H180V65H0Z" fill="#111"/>')
    def part(artwork, transform, identifier):
        if not flat:
            return f'<g id="{identifier}" transform="{transform}">{artwork}</g>'
        tree = etree.fromstring(('<g>' + artwork + '</g>').encode())
        for index, node in enumerate(tree):
            node.set('transform', transform)
            node.set('id', identifier + str(index))
        return ''.join(etree.tostring(node).decode() for node in tree)
    horizontal = part(icon, 'translate(260,0)', 'hi') + part(name, 'translate(0,20)', 'hn')
    vertical = part(icon, 'translate(60,0) scale(1.6)', 'vi') + part(name, 'translate(0,210) scale(1.2727272727)', 'vn')
    extra = f'<g id="duplicate" transform="translate(650,480) scale(0.6)">{icon}</g>' if duplicate else ''
    return (f'<svg xmlns="{NS}" xmlns:inkscape="{inkex.NSS["inkscape"]}" width="900" height="700">'
            f'<g id="h" transform="translate(20,30)">{horizontal}</g>'
            f'<g id="v" transform="translate(500,30)">{vertical}</g>'
            f'<g id="i" transform="translate(320,450) scale(1.2)">{icon}</g>{extra}</svg>').encode()


class LogoExportUnitTests(unittest.TestCase):
    def test_empty_visual_signature_can_be_ignored_only_when_requested(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'empty.png'
            Image.new('RGBA', (64, 64)).save(path)
            with self.assertRaisesRegex(inkex.AbortExtension, 'component is empty'):
                visual_signature(path)
            self.assertIsNone(visual_signature(path, allow_empty=True))

    def test_layouts_preserve_aspect_ratio_and_right_position(self):
        icon, name = component(100, 50), component(200, 40)
        width, height, places = layout_geometry(icon, name, 'horizontal', 100, 40, 12, 10, 'right')
        self.assertEqual((width, height), (432, 120))
        self.assertEqual([(p.role, p.x, p.y, p.width, p.height) for p in places],
                         [('icon', 222, 10, 200, 100), ('wordmark', 10, 40, 200, 40)])
        width, height, places = layout_geometry(icon, name, 'vertical', 100, 40, 12, 10)
        self.assertEqual((width, height), (220, 172))
        self.assertEqual(places[1].y, 122)
        self.assertEqual(layout_geometry(icon, name, 'icon', 100, 40, 12, 10)[0:2], (220, 220))
        self.assertEqual(layout_geometry(icon, name, 'icon', 100, 40, 12, 10, square=False)[0:2], (220, 120))

    def test_raster_sizes_reject_invalid_or_excessive_dimensions(self):
        self.assertEqual(parse_raster_sizes('2048, 512;1024 512'), [512, 1024, 2048])
        for value in ('', '0', '8193', 'nan', '٥١٢', '1.5', ','.join(['64'] * 9)):
            with self.subTest(value=value), self.assertRaises(inkex.AbortExtension):
                parse_raster_sizes(value)

    def test_filename_and_background_conversion(self):
        self.assertEqual(safe_stem(' شركة / السلام; '), 'شركة-السلام')
        self.assertEqual(safe_stem('CON'), 'brand-CON')
        self.assertEqual(css_color('0x172033ff'), '#172033')
        self.assertEqual(css_color('4294967295'), '#ffffff')
        with self.assertRaises(inkex.AbortExtension):
            safe_stem('///')

    def test_roles_use_text_or_document_order_independent_of_click_order(self):
        ext = load(None, '--id=name', '--id=icon')
        self.assertEqual({r: n.get('id') for r, n in ext.selected_components().items()}, {'icon': 'icon', 'wordmark': 'name'})
        ext.options.role_assignment = 'icon_last'
        self.assertEqual(ext.selected_components()['icon'].get('id'), 'name')
        ext = load(document().replace(b'<text x=', b'<path d="M0 0h50v20h-50z" x=').replace(b'>BinSalem</text>', b'/>'), '--id=name', '--id=icon')
        self.assertEqual(ext.selected_components()['icon'].get('id'), 'icon')

    def test_invalid_selection_reports_actionable_error(self):
        for args in ([], ['--id=icon'], ['--id=icon', '--id=body'], ['--id=icon', '--id=name', '--id=secret']):
            with self.subTest(args=args), self.assertRaises(inkex.AbortExtension):
                load(None, *args).selected_components()

    def test_invalid_options_leave_source_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            for args in (['--gap=nan'], ['--padding=-1'], ['--icon_height=0'], ['--jpeg_quality=101'],
                         ['--role_assignment=missing'], ['--output_dir=/missing-logo-directory']):
                ext = load(None, '--id=icon', '--id=name', '--output_dir=' + folder, *args)
                before = etree.tostring(ext.svg)
                with self.subTest(args=args), self.assertRaises(inkex.AbortExtension):
                    ext.effect()
                self.assertEqual(etree.tostring(ext.svg), before)

    def test_prefixes_cover_css_selectors_urls_clones_and_aria(self):
        svg = component(100, 100, '<defs><linearGradient id="paint"/></defs>'
                        '<style>#body {fill:url(#paint)} @media screen {#clone {stroke:#fff}}</style>'
                        '<rect id="body" fill="url(\'#paint\')" aria-labelledby="body clone"/>'
                        '<use id="clone" href="#body"/>').svg
        prefix_ids(svg, 'icon-')
        self.assertEqual(svg.getElementById('icon-clone').get('href'), '#icon-body')
        self.assertEqual(svg.getElementById('icon-body').get('aria-labelledby'), 'icon-body icon-clone')
        self.assertEqual(svg.getElementById('icon-body').get('fill'), 'url(#icon-paint)')
        css = svg.find(inkex.addNS('style', 'svg')).text
        self.assertIn('#icon-body', css)
        self.assertIn('url(#icon-paint)', css)
        self.assertIn('#icon-clone', css)
        self.assertIn('#fff', css)

    def test_composition_has_no_duplicate_ids_or_source_mutation(self):
        artwork = '<defs><linearGradient id="paint"/></defs><rect id="body" fill="url(#paint)"/>'
        parts = {'icon': component(100, 100, artwork), 'wordmark': component(100, 100, artwork)}
        before = etree.tostring(parts['icon'].svg)
        svg = build_master(parts, 'horizontal', load().options)
        ids = [node.get('id') for node in svg.iter() if node.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(etree.tostring(parts['icon'].svg), before)

    def test_white_cutouts_and_all_white_components(self):
        icon = component(100, 100, '<rect width="100" height="100" fill="#2563eb"/><circle cx="50" cy="50" r="25" fill="#fff"/>')
        white = component(100, 100, '<rect width="100" height="100" fill="#fff"/>')
        master = build_master({'icon': icon, 'wordmark': white}, 'horizontal', load().options)
        result = monochrome(master, '#000000')
        self.assertEqual(result.xpath('.//svg:circle')[0].style['fill'], '#000000')
        self.assertEqual(result.xpath('.//svg:svg[@data-logo-export-component="wordmark"]/svg:rect')[0].style['fill'], '#ffffff')
        result = monochrome(master, '#000000', False)
        self.assertEqual(result.xpath('.//svg:circle')[0].style['fill'], '#ffffff')

    def test_linked_image_is_embedded_on_copy_without_loading_unselected_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'logo image.png'
            Image.new('RGBA', (20, 20), '#2563eb').save(path)
            extra = (f'<image id="linked" href="{path.as_uri()}" width="20" height="20"/>'
                     '<image id="fff" href="missing.png" width="20" height="20"/>')
            ext = load(document(extra=extra))
            before = etree.tostring(ext.svg)
            root = ext.prepare_source(ext.svg, 'linked')
            self.assertTrue(root.getElementById('linked').get('href').startswith('data:image/png;base64,'))
            self.assertFalse(root.xpath('.//sodipodi:namedview'))
            # A hex color is not a link to an object whose ID happens to be "fff".
            ext.prepare_source(ext.svg, 'icon')
            self.assertEqual(etree.tostring(ext.svg), before)

    def test_missing_or_remote_linked_images_have_clear_errors(self):
        for href in ('missing.png', 'https://example.com/logo.png'):
            ext = load(document(extra=f'<image id="linked" href="{href}" width="20" height="20"/>'))
            with self.subTest(href=href), self.assertRaises(inkex.AbortExtension):
                ext.prepare_source(ext.svg, 'linked')

    def test_external_clone_is_rejected(self):
        ext = load(document(extra='<use id="external" href="file.svg#shape"/>'))
        with self.assertRaises(inkex.AbortExtension):
            ext.prepare_source(ext.svg, 'external')

    def test_prepared_source_retains_original_inline_css_importance(self):
        source = document().replace(b'id="body"', b'id="body" style="fill:#ef4444 !important"')
        ext = load(source)
        root = ext.prepare_source(ext.svg, 'icon')
        self.assertEqual(root.getElementById('body').attrib['style'], 'fill:#ef4444 !important')

    def test_failed_export_cleans_partial_folder_and_keeps_existing_kit(self):
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / 'My-Brand-logo-kit'
            existing.mkdir()
            (existing / 'keep.txt').write_text('saved kit')
            ext = load(None, '--id=icon', '--id=name', '--output_dir=' + folder)
            before = etree.tostring(ext.svg)
            with patch.object(ext, 'extract_component', return_value=component(100, 100)), \
                 patch.object(ext, 'measure_components', return_value={'icon': (0, 0, 100, 100), 'wordmark': (150, 0, 100, 100)}), \
                 patch.object(ext, 'export_variant', side_effect=OSError('disk error')):
                with self.assertRaisesRegex(inkex.AbortExtension, 'disk error'):
                    ext.effect()
            self.assertEqual(list(Path(folder).iterdir()), [existing])
            self.assertEqual((existing / 'keep.txt').read_text(), 'saved kit')
            self.assertEqual(etree.tostring(ext.svg), before)

    def test_descriptor_schema_and_english_interface_match_defaults(self):
        tree = etree.parse(str(ROOT / 'logo_export_pro.inx'))
        schema = Path(inkex.__file__).parent / 'tester/inkscape.extension.rng'
        if schema.exists():
            etree.RelaxNG(etree.parse(str(schema))).assertValid(tree)
        args = []
        for param in tree.findall('.//{*}param'):
            kind = param.get('type')
            if kind == 'notebook':
                value = param.find('{*}page').get('name')
            elif kind == 'optiongroup':
                value = param.find('{*}option').get('value')
            else:
                value = (param.text or '').strip()
            args.append('--' + param.get('name') + '=' + value)
        ext = load(None, *args)
        self.assertEqual(ext.options.raster_sizes, '512, 1024, 2048')
        self.assertFalse(any('\u0600' <= c <= '\u06ff' for c in ''.join(tree.getroot().itertext())))
        self.assertEqual(tree.find('.//{*}submenu').get('name'), 'Binsalmarts Extensions >')
        self.assertEqual(tree.find('{*}effect').get('needs-live-preview'), 'false')
        self.assertEqual(ext.options.source_mode, 'templates')
        self.assertEqual(ext.options.role_assignment, 'assigned')
        self.assertEqual(ext.options.sizing_mode, 'original')

    def test_complete_logo_accepts_one_group_or_any_number_of_selected_parts(self):
        self.assertEqual(list(current_load(None, '--id=icon').selected_components()), ['logo'])
        parts = current_load(None, '--id=name', '--id=icon', '--id=secret').selected_components()
        self.assertEqual([node.get('id') for node in parts.values()], ['icon', 'name', 'secret'])

    def test_explicit_ids_determine_roles_without_text_detection_or_selection_order(self):
        ext = current_load(None, '--source_mode=paired', '--icon_id=name', '--wordmark_id=icon')
        parts = ext.selected_components()
        self.assertEqual(parts['icon'].get('id'), 'name')
        self.assertEqual(parts['wordmark'].get('id'), 'icon')
        with self.assertRaisesRegex(inkex.AbortExtension, 'Assign the icon'):
            current_load(None, '--source_mode=paired', '--id=icon', '--id=name').selected_components()
        with self.assertRaisesRegex(inkex.AbortExtension, 'two separate'):
            current_load(None, '--source_mode=paired', '--icon_id=icon', '--wordmark_id=body').selected_components()

    def test_roles_can_be_assigned_individually_and_only_role_metadata_changes(self):
        ext = current_load(None, '--id=icon', '--source_action=assign_icon')
        icon_before = etree.tostring(ext.svg.getElementById('icon'))
        ext.effect()
        self.assertEqual(ext.svg.get('data-logo-export-icon-id'), 'icon')
        ext.svg.getElementById('icon').attrib.pop('data-logo-export-role')
        self.assertEqual(etree.tostring(ext.svg.getElementById('icon')), icon_before)
        ext = current_load(etree.tostring(ext.svg), '--id=name', '--source_action=assign_wordmark')
        ext.effect()
        data = etree.tostring(ext.svg)
        assigned = current_load(data, '--source_mode=paired')
        self.assertEqual({role: node.get('id') for role, node in assigned.selected_components().items()}, {'icon': 'icon', 'wordmark': 'name'})
        ext = current_load(data, '--source_action=clear_roles')
        ext.effect()
        self.assertIsNone(ext.svg.get('data-logo-export-icon-id'))
        self.assertIsNone(ext.svg.get('data-logo-export-wordmark-id'))

    def test_assignment_rejects_multiple_objects_and_the_same_object_for_both_roles(self):
        with self.assertRaisesRegex(inkex.AbortExtension, 'Select just'):
            current_load(None, '--id=icon', '--id=name', '--source_action=assign_icon').effect()
        ext = current_load(None, '--id=icon', '--source_action=assign_icon')
        ext.effect()
        ext = current_load(etree.tostring(ext.svg), '--id=icon', '--source_action=assign_wordmark')
        before = etree.tostring(ext.svg)
        with self.assertRaisesRegex(inkex.AbortExtension, 'same object'):
            ext.effect()
        self.assertEqual(etree.tostring(ext.svg), before)

    def test_ready_variant_assignments_and_optional_labels(self):
        ext = current_load(None, '--id=icon', '--source_action=assign_horizontal')
        before = etree.tostring(ext.svg.getElementById('icon'))
        ext.effect()
        node = ext.svg.getElementById('icon')
        self.assertEqual(artwork_role(node), 'horizontal')
        node.attrib.pop('data-logo-export-role')
        self.assertEqual(etree.tostring(node), before)
        for label, role in [('logo-vertical', 'vertical'), ('أيقونة', 'icon'), ('Name', 'wordmark')]:
            node.set(inkex.addNS('label', 'inkscape'), label)
            self.assertEqual(artwork_role(node), role)
        node.set('data-logo-export-role', 'horizontal')
        self.assertEqual(artwork_role(node), 'horizontal')
        ext.options.source_action = 'clear_roles'
        ext.effect()
        self.assertIsNone(node.get('data-logo-export-role'))

    def test_original_sizes_current_gap_balancing_and_manual_sizes(self):
        icon, name = component(100, 50), component(200, 40)
        icon.x, icon.y, name.x, name.y = 10, 15, 160, 20
        parts = {'icon': icon, 'wordmark': name}
        opts = current_load().options
        opts.padding = 0
        width, height, placements = export_geometry(parts, 'horizontal', opts)
        self.assertEqual((width, height), (350, 50))
        self.assertEqual(component_gap(icon, name), 50)
        self.assertEqual((placements[0].width, placements[0].height), (100, 50))
        opts.sizing_mode = 'balanced'
        opts.horizontal_balance, opts.vertical_balance = 1.5, 0.5
        self.assertEqual(export_geometry(parts, 'horizontal', opts)[2][0].height, 60)
        self.assertEqual(export_geometry(parts, 'vertical', opts)[2][0].width, 100)
        opts.sizing_mode, opts.gap_mode = 'manual', 'manual'
        opts.icon_height, opts.wordmark_height, opts.gap = 25, 20, 8
        self.assertEqual(export_geometry(parts, 'horizontal', opts)[:2], (158, 25))

    def test_as_designed_ignores_rebuild_settings_and_uses_current_coordinates(self):
        icon, name = component(100, 50), component(200, 40)
        icon.x, icon.y, name.x, name.y = 30, 90, 180, 20
        opts = current_load().options
        opts.padding, opts.icon_height, opts.wordmark_height, opts.gap = 0, 1, 1, 900
        opts.sizing_mode = 'manual'
        dimensions = export_geometry({'icon': icon, 'wordmark': name}, 'as_designed', opts)
        self.assertEqual(dimensions[:2], (350, 120))
        self.assertEqual([(p.x, p.y, p.width, p.height) for p in dimensions[2]], [(0, 70, 100, 50), (150, 0, 200, 40)])
        name.x = 280
        self.assertEqual(current_geometry({'icon': icon, 'wordmark': name}, 0)[:2], (450, 120))

    def test_single_modes_need_no_second_component_and_preserve_outlined_names(self):
        for mode, identifier in (('icon', 'icon'), ('wordmark', 'body')):
            with self.subTest(mode=mode):
                ext = current_load(None, '--source_mode=' + mode, '--id=' + identifier)
                self.assertEqual(list(ext.selected_components()), [mode])
                with tempfile.TemporaryDirectory() as folder:
                    ext.options.output_dir = folder
                    ext.validate_options()
                    self.assertEqual(ext.layouts, [mode])
                part = component(80, 20)
                ext.options.padding, ext.options.square_icon = 0, False
                self.assertEqual(build_master({mode: part}, mode, ext.options).viewport_width, 80)


@unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Native export requires --inkscape')
class LogoExportNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='logo-kit-tests-')
        cls.ext = load(document(name='السلام'), '--id=icon', '--id=name', '--brand_name=السلام',
                       '--output_dir=' + cls.directory.name, '--raster_sizes=32,64,128')
        cls.before = etree.tostring(cls.ext.svg)
        cls.ext.effect()
        cls.kit = cls.ext.output_path

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def file(self, layout, color, suffix):
        return self.kit / layout / color / f'السلام-{layout}-{color}{suffix}'

    def test_all_108_requested_files_are_valid_and_source_is_unchanged(self):
        self.assertEqual(self.ext.manifest['exported_file_count'], 108)
        self.assertEqual(len(self.ext.manifest['variants']), 12)
        self.assertEqual(etree.tostring(self.ext.svg), self.before)
        for variant in self.ext.manifest['variants']:
            for filename in variant['files']:
                file = self.kit / filename
                self.assertGreater(file.stat().st_size, 0)
                if file.suffix in ('.png', '.jpg'):
                    with Image.open(file) as image:
                        image.verify()
                elif file.suffix == '.svg':
                    svg = inkex.load_svg(str(file)).getroot()
                    self.assertFalse(svg.xpath('.//svg:text'))
                    self.assertNotIn(b'Do not export this', file.read_bytes())
                    ids = [n.get('id') for n in svg.iter() if n.get('id')]
                    self.assertEqual(len(ids), len(set(ids)))
                elif file.suffix == '.pdf':
                    reader = PdfReader(file)
                    self.assertEqual(len(reader.pages), 1)
                    self.assertAlmostEqual(float(reader.pages[0].mediabox.width), variant['width_px'] * 0.75, places=2)
                    self.assertAlmostEqual(float(reader.pages[0].mediabox.height), variant['height_px'] * 0.75, places=2)
                elif file.suffix == '.eps':
                    self.assertTrue(file.read_bytes().startswith(b'%!PS-Adobe-'))

    def test_arabic_shaping_produces_paths_and_correct_crop(self):
        svg = inkex.load_svg(str(self.file('wordmark', 'original', '.svg'))).getroot()
        self.assertTrue(svg.xpath('.//svg:path'))
        self.assertGreater(svg.viewport_width, 100)
        self.assertEqual(svg.viewport_height, 112)
        original = inkex.load_svg(str(self.file('icon', 'original', '.svg'))).getroot()
        self.assertEqual((original.viewport_width, original.viewport_height), (192, 192))

    def test_monochrome_rendering_retains_holes_and_transparency(self):
        for color, rgb in (('black', (0, 0, 0)), ('white', (255, 255, 255))):
            with Image.open(self.file('icon', color, '-128px.png')) as image:
                rgba = image.convert('RGBA')
                self.assertEqual(rgba.getpixel((64, 64))[3], 0)
                self.assertEqual(rgba.getpixel((64, 32)), (*rgb, 255))
                self.assertEqual(rgba.getpixel((0, 0))[3], 0)
        with Image.open(self.file('icon', 'original', '-128px.png')) as image:
            self.assertEqual(image.convert('RGBA').getpixel((64, 64)), (255, 255, 255, 255))

    def test_raster_longest_edge_and_white_jpeg_background(self):
        for layout in ('horizontal', 'vertical', 'icon', 'wordmark'):
            for size in (32, 64, 128):
                with Image.open(self.file(layout, 'original', f'-{size}px.png')) as image:
                    self.assertEqual(max(image.size), size)
        with Image.open(self.file('icon', 'white', '-128px.jpg')) as image:
            corner = image.getpixel((0, 0))
            self.assertTrue(all(abs(a - b) <= 3 for a, b in zip(corner, (23, 32, 51))))
            self.assertTrue(all(v >= 250 for v in image.getpixel((64, 32))))

    def test_white_eps_remains_visible_after_postscript_flattening(self):
        executable = Path(os.environ['INKSCAPE_COMMAND']).resolve()
        bundled = executable.parent.parent / 'Resources/bin/gs'
        gs = shutil.which('gs') or (str(bundled) if bundled.exists() else None)
        if not gs:
            self.skipTest('EPS rendering check requires Ghostscript')
        output = Path(self.directory.name) / 'eps-white.png'
        subprocess.run([gs, '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dEPSCrop', '-sDEVICE=png16m',
                        '-r96', '-sOutputFile=' + str(output), str(self.file('icon', 'white', '.eps'))],
                       check=True, capture_output=True, timeout=45)
        with Image.open(output) as image:
            # EPS integer BoundingBox rounding can add one raster pixel.
            self.assertIn(image.width, (192, 193))
            self.assertIn(image.height, (192, 193))
            self.assertEqual(image.getpixel((2, 2)), (23, 32, 51))
            self.assertEqual(image.getpixel((96, 96)), (23, 32, 51))
            self.assertEqual(image.getpixel((96, 48)), (255, 255, 255))

    def test_gallery_and_manifest_are_offline_and_account_for_exports(self):
        data = json.loads((self.kit / 'manifest.json').read_text())
        self.assertEqual(data['source_ids'], {'icon': 'icon', 'wordmark': 'name'})
        page = (self.kit / 'preview.html').read_text()
        self.assertEqual(page.count('<article>'), 12)
        self.assertIn('PNG · 128 px', page)
        self.assertNotIn('src="https:', page)
        self.assertTrue((self.kit / 'preview/horizontal-white.svg').is_file())

    def test_editable_arabic_svg_and_existing_exports_are_preserved(self):
        ext = load(document(name='السلام'), '--id=icon', '--id=name', '--brand_name=السلام',
                   '--output_dir=' + self.directory.name, '--text_to_paths=false',
                   '--layout_horizontal=false', '--layout_vertical=false', '--layout_icon=false',
                   '--color_black=false', '--color_white=false', '--format_png=false', '--format_jpg=false',
                   '--format_eps=false', '--format_pdf=false', '--include_preview=false')
        ext.effect()
        self.assertEqual(ext.output_path.name, 'السلام-logo-kit-2')
        svg = inkex.load_svg(str(next(ext.output_path.rglob('*.svg')))).getroot()
        self.assertEqual(svg.xpath('.//svg:text')[0].text, 'السلام')
        self.assertFalse((ext.output_path / 'preview.html').exists())
        self.assertEqual((self.kit / 'manifest.json').read_text(), json.dumps(self.ext.manifest, ensure_ascii=False, indent=2) + '\n')

    def test_clone_with_inherited_css_and_all_white_artwork_remains_visible(self):
        source = (f'<svg xmlns="{NS}" width="500" height="300"><style>rect {{fill:#fff !important}}</style>'
                  '<defs><rect id="shape" width="100" height="100"/></defs>'
                  '<use id="icon" href="#shape"/><rect id="name" x="150" width="200" height="40"/></svg>').encode()
        ext = load(source, '--id=icon', '--id=name', '--brand_name=Clone', '--output_dir=' + self.directory.name,
                   '--layout_horizontal=false', '--layout_vertical=false', '--layout_wordmark=false',
                   '--color_original=false', '--color_white=false', '--format_jpg=false',
                   '--format_pdf=false', '--format_eps=false', '--raster_sizes=128')
        ext.effect()
        with Image.open(next(ext.output_path.rglob('*.png'))) as image:
            self.assertEqual(image.convert('RGBA').getpixel((64, 64)), (0, 0, 0, 255))

    def quick_export(self, source, *args, **kwargs):
        ext = current_load(source, '--brand_name=Current', '--output_dir=' + self.directory.name,
                           '--color_black=false', '--color_white=false', '--format_pdf=false',
                           '--format_eps=false', '--format_jpg=false', '--raster_sizes=128',
                           '--padding=0', '--include_preview=false', *args)
        before = etree.tostring(ext.svg)
        ext.effect()
        self.assertEqual(etree.tostring(ext.svg), before)
        return ext

    def new_variant(self, ext, layout):
        file = ext.output_path / layout / 'original' / f'Current-{layout}-original.svg'
        return inkex.load_svg(str(file)).getroot()

    def transformed_document(self):
        return (f'<svg xmlns="{NS}" width="400" height="200" viewBox="10 20 200 100">'
                '<g id="whole"><g transform="translate(30,15) scale(2)">'
                '<rect id="icon" x="10" y="15" width="20" height="10" fill="#2563eb"/></g>'
                '<rect id="name" x="140" y="30" width="50" height="20" fill="#7c3aed"/></g>'
                '<rect id="unrelated" x="15" y="90" width="20" height="10" fill="red"/></svg>').encode()

    def test_complete_group_matches_native_artwork_with_transforms_and_viewbox(self):
        from inkex.command import inkscape
        source = self.transformed_document()
        ext = self.quick_export(source, '--id=whole', '--sizing_mode=manual', '--icon_height=1', '--gap=999')
        self.assertEqual(ext.layouts, ['as_designed'])
        svg = self.new_variant(ext, 'as_designed')
        self.assertEqual((svg.viewport_width, svg.viewport_height), (280, 70))
        reference = Path(self.directory.name) / 'reference.png'
        input_path = Path(self.directory.name) / 'reference-source.svg'
        input_path.write_bytes(source)
        inkscape(str(input_path), batch_process=True, export_id='whole', export_id_only=True,
                 export_type='png', export_width=128, export_filename=str(reference))
        actual = next(ext.output_path.rglob('*.png'))
        with Image.open(actual) as actual_image, Image.open(reference) as expected_image:
            self.assertEqual(actual_image.size, expected_image.size)
            def opaque(image):
                rgba = image.convert('RGBA')
                result = Image.new('RGB', rgba.size, 'white')
                result.paste(rgba, mask=rgba.getchannel('A'))
                return result
            extrema = ImageChops.difference(opaque(actual_image), opaque(expected_image)).getextrema()
            self.assertLessEqual(max(high for _, high in extrema), 2)

    def test_multiple_selected_parts_keep_actual_coordinates_and_sizes(self):
        ext = self.quick_export(self.transformed_document(), '--id=icon', '--id=name')
        svg = self.new_variant(ext, 'as_designed')
        self.assertEqual((svg.viewport_width, svg.viewport_height), (280, 70))
        nested = svg.xpath('./svg:svg')
        self.assertEqual([(float(n.get('x')), float(n.get('y')), float(n.get('width')), float(n.get('height')))
                         for n in nested], [(0, 30, 80, 40), (180, 0, 100, 40)])

    def outlined_document(self):
        return (f'<svg xmlns="{NS}" width="500" height="200">'
                '<path id="name" d="M10 10h200v40H10z" fill="#172033"/>'
                '<rect id="icon" x="300" y="40" width="70" height="70" fill="#2563eb"/></svg>').encode()

    def test_assigned_outlined_name_and_icon_keep_original_sizes_when_rebuilding(self):
        source = self.outlined_document()
        first = current_load(source, '--id=name', '--source_action=assign_wordmark')
        first.effect()
        second = current_load(etree.tostring(first.svg), '--id=icon', '--source_action=assign_icon')
        second.effect()
        ext = self.quick_export(etree.tostring(second.svg), '--source_mode=paired',
                               '--layout_icon=false', '--layout_wordmark=false')
        self.assertEqual(ext.manifest['source_ids'], {'wordmark': 'name', 'icon': 'icon'})
        designed = self.new_variant(ext, 'as_designed')
        self.assertEqual((designed.viewport_width, designed.viewport_height), (360, 100))
        horizontal = self.new_variant(ext, 'horizontal')
        self.assertEqual((horizontal.viewport_width, horizontal.viewport_height), (360, 70))
        parts = horizontal.xpath('./svg:svg')
        self.assertEqual([(p.get('data-logo-export-component'), float(p.get('width')), float(p.get('height')))
                         for p in parts], [('icon', 70, 70), ('wordmark', 200, 40)])
        self.assertEqual(float(parts[1].get('x')), 160)
        self.assertNotIn(b'data-logo-export-icon-id', etree.tostring(horizontal))

    def test_balancing_and_manual_overrides_use_measured_name_dimensions(self):
        options = ['--source_mode=paired', '--icon_id=icon', '--wordmark_id=name', '--layout_as_designed=false',
                   '--layout_icon=false', '--layout_wordmark=false', '--format_png=false']
        ext = self.quick_export(self.outlined_document(), *options, '--sizing_mode=balanced',
                               '--horizontal_balance=1.25', '--vertical_balance=0.5')
        horizontal = self.new_variant(ext, 'horizontal').xpath('./svg:svg')
        vertical = self.new_variant(ext, 'vertical').xpath('./svg:svg')
        self.assertEqual(float(horizontal[0].get('height')), 50)
        self.assertEqual(float(vertical[0].get('width')), 100)
        self.assertEqual(float(horizontal[1].get('height')), 40)
        ext = self.quick_export(self.outlined_document(), *options, '--sizing_mode=manual',
                               '--icon_height=30', '--wordmark_height=20', '--gap_mode=manual', '--gap=12')
        svg = self.new_variant(ext, 'horizontal')
        self.assertEqual((svg.viewport_width, svg.viewport_height), (142, 30))

    def test_single_arabic_name_exports_all_formats_without_an_icon(self):
        ext = self.quick_export(document(name='السلام'), '--source_mode=wordmark', '--id=name',
                               '--color_black=true', '--color_white=true', '--format_pdf=true',
                               '--format_eps=true', '--format_jpg=true', '--raster_sizes=64')
        self.assertEqual(ext.manifest['exported_file_count'], 15)
        self.assertEqual(ext.manifest['source_ids'], {'wordmark': 'name'})
        self.assertTrue(all(v['layout'] == 'wordmark' for v in ext.manifest['variants']))
        svg = self.new_variant(ext, 'wordmark')
        self.assertTrue(svg.xpath('.//svg:path'))
        self.assertFalse(svg.xpath('.//svg:text'))
        self.assertAlmostEqual(svg.viewport_height, ext.manifest['source_bounds_px']['wordmark'][3], places=2)

    def test_single_icon_keeps_its_aspect_ratio_and_current_design_is_read_again(self):
        source = self.transformed_document()
        ext = self.quick_export(source, '--source_mode=icon', '--id=icon', '--square_icon=false')
        svg = self.new_variant(ext, 'icon')
        self.assertEqual((svg.viewport_width, svg.viewport_height), (80, 40))
        original = self.quick_export(source, '--id=whole', '--format_png=false')
        modified = source.replace(b'x="140"', b'x="190"')
        updated = self.quick_export(modified, '--id=whole', '--format_png=false')
        self.assertEqual(self.new_variant(original, 'as_designed').viewport_width, 280)
        self.assertEqual(self.new_variant(updated, 'as_designed').viewport_width, 380)

    def test_ready_variants_detect_rtl_layouts_and_extract_each_part_once(self):
        source = ready_document(duplicate=True)
        ext = self.quick_export(source, '--source_mode=ready', '--id=v', '--id=i', '--id=h', '--id=duplicate',
                               '--sizing_mode=manual', '--icon_height=5', '--gap=999')
        self.assertEqual(ext.layouts, ['horizontal', 'vertical', 'icon', 'wordmark'])
        self.assertEqual(ext.manifest['exported_file_count'], 8)
        self.assertEqual(len(ext.manifest['recognized_layouts']), 4)
        self.assertEqual((self.new_variant(ext, 'horizontal').viewport_width,
                          self.new_variant(ext, 'horizontal').viewport_height), (360, 100))
        self.assertAlmostEqual(self.new_variant(ext, 'vertical').viewport_width, 280, places=4)
        self.assertEqual((self.new_variant(ext, 'icon').viewport_width,
                          self.new_variant(ext, 'icon').viewport_height), (120, 120))
        name = self.new_variant(ext, 'wordmark')
        self.assertEqual((name.viewport_width, name.viewport_height), (220, 65))
        self.assertNotIn(b'#e52b20', etree.tostring(name))
        self.assertFalse((ext.output_path / 'as_designed').exists())
        # Compare the complete finished designs with the native reference crop.
        from inkex.command import inkscape
        input_path = Path(self.directory.name) / 'ready-reference.svg'
        input_path.write_bytes(source)
        for layout, identifier in [('horizontal', 'h'), ('vertical', 'v')]:
            reference = Path(self.directory.name) / (layout + '-reference.png')
            inkscape(str(input_path), batch_process=True, export_id=identifier, export_id_only=True,
                     export_type='png', export_width=128 if layout == 'horizontal' else 0,
                     export_height=128 if layout == 'vertical' else 0, export_filename=str(reference))
            actual = next((ext.output_path / layout).rglob('*.png'))
            self.assertLess(visual_distance(visual_signature(actual), visual_signature(reference)), 0.001)

    def test_ready_variants_match_flat_outlined_parts_without_names_or_subgroups(self):
        ext = self.quick_export(ready_document(flat=True), '--source_mode=ready', '--id=h', '--id=v', '--id=i',
                               '--format_png=false')
        self.assertEqual(ext.layouts, ['horizontal', 'vertical', 'icon', 'wordmark'])
        self.assertEqual(self.new_variant(ext, 'wordmark').viewport_width, 220)
        self.assertEqual(ext.manifest['exported_file_count'], 4)

    def test_ready_variants_can_find_shared_icon_without_standalone_icon(self):
        ext = self.quick_export(ready_document(), '--source_mode=ready', '--id=h', '--id=v', '--format_png=false')
        self.assertEqual(ext.layouts, ['horizontal', 'vertical', 'icon', 'wordmark'])
        self.assertEqual(self.new_variant(ext, 'icon').viewport_width, 100)

    def test_ready_assignments_override_detection_and_duplicate_types_need_correction(self):
        root = inkex.load_svg(io.BytesIO(ready_document())).getroot()
        root.getElementById('h').set('data-logo-export-role', 'vertical')
        root.getElementById('v').set('data-logo-export-role', 'horizontal')
        root.getElementById('i').set('data-logo-export-role', 'icon')
        ext = self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=h', '--id=v', '--id=i',
                               '--format_png=false')
        self.assertAlmostEqual(self.new_variant(ext, 'horizontal').viewport_width, 280, places=4)
        self.assertEqual(self.new_variant(ext, 'vertical').viewport_width, 360)
        root.getElementById('v').set('data-logo-export-role', 'vertical')
        with self.assertRaisesRegex(inkex.AbortExtension, 'two different vertical'):
            self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=h', '--id=v', '--id=i')

    def test_ready_single_assigned_name_exports_once_and_unknown_groups_are_actionable(self):
        root = inkex.load_svg(io.BytesIO(ready_document())).getroot()
        root.getElementById('hn').set('data-logo-export-role', 'wordmark')
        ext = self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=hn', '--format_png=false')
        self.assertEqual(ext.layouts, ['wordmark'])
        self.assertEqual(ext.manifest['exported_file_count'], 1)
        with self.assertRaisesRegex(inkex.AbortExtension, 'Source > Action'):
            self.quick_export(ready_document(), '--source_mode=ready', '--id=i')

    def test_ready_flat_regions_preserve_ancestor_opacity_and_css_without_duplicate_paint(self):
        from inkex.command import inkscape
        root = inkex.load_svg(io.BytesIO(ready_document(flat=True))).getroot()
        layer = inkex.Group(id='logos', style='opacity:0.7')
        layer.set(inkex.addNS('groupmode', 'inkscape'), 'layer')
        for child in list(root):
            root.remove(child)
            layer.append(child)
        root.append(layer)
        style = inkex.StyleElement()
        style.text = '#h path, #v path, #i path {stroke:#172033;stroke-width:0.4}'
        root.insert(0, style)
        source = etree.tostring(root)
        ext = self.quick_export(source, '--source_mode=ready', '--id=logos')
        self.assertEqual(ext.layouts, ['horizontal', 'vertical', 'icon', 'wordmark'])
        input_path = Path(self.directory.name) / 'opacity-reference.svg'
        input_path.write_bytes(source)
        expected = Path(self.directory.name) / 'opacity-reference.png'
        inkscape(str(input_path), batch_process=True, export_id='h', export_id_only=True,
                 export_type='png', export_width=128, export_filename=str(expected))
        actual = next((ext.output_path / 'horizontal').rglob('*.png'))
        self.assertLess(visual_distance(visual_signature(actual), visual_signature(expected)), 0.001)
        name = next((ext.output_path / 'wordmark').rglob('*.png'))
        with Image.open(name) as image:
            self.assertLessEqual(image.convert('RGBA').getchannel('A').getextrema()[1], 180)

    def test_ready_arabic_name_extraction_and_reexport_reads_modified_geometry(self):
        root = inkex.load_svg(io.BytesIO(ready_document())).getroot()
        for identifier in ('hn', 'vn'):
            group = root.getElementById(identifier)
            for child in list(group):
                group.remove(child)
            text = inkex.TextElement(x='0', y='48', style='font-family:DejaVu Sans;font-size:48px;fill:#111')
            text.text = 'السلام'
            group.append(text)
        ext = self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=h', '--id=v', '--id=i', '--format_png=false')
        name = self.new_variant(ext, 'wordmark')
        self.assertFalse(name.xpath('.//svg:text'))
        self.assertTrue(name.xpath('.//svg:path'))
        first = self.new_variant(ext, 'horizontal').viewport_width
        root.getElementById('hi').set('transform', 'translate(360,0)')
        updated = self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=h', '--id=v', '--id=i', '--format_png=false')
        self.assertAlmostEqual(self.new_variant(updated, 'horizontal').viewport_width, first + 100, places=4)

    def test_ready_live_arabic_text_with_line_and_word_spans_exports_whole_name(self):
        root = inkex.load_svg(io.BytesIO(ready_document())).getroot()
        for group_id in ('hn', 'vn'):
            group = root.getElementById(group_id)
            for child in list(group):
                group.remove(child)
            text = inkex.load_svg(io.BytesIO((
                f'<svg xmlns="{NS}" xmlns:sodipodi="{inkex.NSS["sodipodi"]}">'
                f'<text id="{group_id}-text" x="220" y="60" '
                'style="font-family:DejaVu Sans;font-size:48px;direction:rtl;fill:#fff">'
                f'<tspan id="{group_id}-line" sodipodi:role="line" x="220" y="60">'
                f'<tspan id="{group_id}-word">السلام</tspan></tspan></text></svg>'
            ).encode())).getroot()[0]
            group.append(text)
        # Empty descendants are optional matching candidates, not empty logos.
        root.getElementById('h').append(inkex.PathElement(
            id='unpainted', d='M0 0h80v80h-80z', style='fill:none;stroke:none'))
        ext = self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=h', '--id=v', '--id=i',
                                '--preserve_white_cutouts=false', '--color_black=true', '--color_white=true')
        self.assertEqual(ext.layouts, ['horizontal', 'vertical', 'icon', 'wordmark'])
        self.assertEqual(len(ext.manifest['recognized_layouts']), 4)
        for layout in ('horizontal', 'vertical', 'wordmark'):
            svg = self.new_variant(ext, layout)
            self.assertFalse(svg.xpath('.//svg:text'))
            self.assertTrue(svg.xpath('.//svg:path'))
            for color in ('original', 'black', 'white'):
                with Image.open(next((ext.output_path / layout / color).glob('*.png'))) as image:
                    self.assertIsNotNone(image.convert('RGBA').getchannel('A').getbbox())

    def test_ready_does_not_silently_skip_an_empty_selected_logo(self):
        root = inkex.load_svg(io.BytesIO(ready_document())).getroot()
        root.getElementById('i').style['opacity'] = '0'
        with self.assertRaisesRegex(inkex.AbortExtension, "'i'.*renders empty|no measurable visible area"):
            self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=h', '--id=v', '--id=i')

    def test_ready_uses_assigned_components_inside_a_lockup_without_separate_selection(self):
        root = inkex.load_svg(io.BytesIO(ready_document())).getroot()
        root.getElementById('hi').set('data-logo-export-role', 'icon')
        root.getElementById('hn').set('data-logo-export-role', 'wordmark')
        root.set('data-logo-export-icon-id', 'hi')
        root.set('data-logo-export-wordmark-id', 'hn')
        ext = self.quick_export(etree.tostring(root), '--source_mode=ready', '--id=h', '--id=v', '--format_png=false')
        self.assertEqual(ext.layouts, ['horizontal', 'vertical', 'icon', 'wordmark'])
        self.assertEqual(ext.manifest['source_ids']['icon'], 'hi')
        self.assertEqual(ext.manifest['source_ids']['wordmark'], 'hn')
        self.assertEqual(self.new_variant(ext, 'wordmark').viewport_width, 220)


if __name__ == '__main__':
    unittest.main()
