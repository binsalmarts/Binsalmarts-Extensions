import importlib.util
import io
import os
from pathlib import Path
import unittest

import inkex
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'modern_grid'


def import_extension(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ModernGrid


ModernGrid = import_extension(DIRECTORY / 'modern_grid.py', 'modern_grid_updated')
LegacyGrid = import_extension(DIRECTORY / 'original/modern_grid.py', 'modern_grid_original')


def document(content='', pages='', width='800', height='600', viewbox='0 0 800 600', extra=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS["inkscape"]}" '
            f'xmlns:sodipodi="{inkex.NSS["sodipodi"]}" width="{width}" height="{height}" viewBox="{viewbox}" {extra}>'
            f'<sodipodi:namedview id="namedview">{pages}</sodipodi:namedview>{content}</svg>').encode()


def load(source=None, *args, cls=ModernGrid):
    extension = cls()
    extension.options = extension.arg_parser.parse_args(args)
    extension.load(io.BytesIO(source or document()))
    return extension


def convert(source=None, *args, cls=ModernGrid):
    extension = load(source, *args, cls=cls)
    extension.effect()
    return extension


def serialized(extension):
    return etree.tostring(extension.svg)


def group(extension, name):
    return extension.svg.getElementById(name)


PAGES = ('<inkscape:page id="a" x="0" y="0" width="800" height="600"/>'
         '<inkscape:page id="b" x="900" y="20" width="400" height="300"/>'
         '<inkscape:page id="c" x="-450" y="700" width="500" height="400"/>')
SHAPES = ('<rect id="box" x="50" y="60" width="300" height="200" fill="#dddddd"/>'
          '<circle id="circle" cx="550" cy="250" r="100" fill="#dddddd"/>')


class ModernGridTests(unittest.TestCase):
    def test_all_original_parameters_ranges_options_and_defaults_are_retained(self):
        original = etree.parse(str(DIRECTORY / 'original/modern_grid.inx'))
        updated = etree.parse(str(DIRECTORY / 'modern_grid.inx'))
        old = {p.get('name'): p for p in original.findall('.//{*}param')}
        new = {p.get('name'): p for p in updated.findall('.//{*}param')}
        self.assertEqual(set(new) - set(old), {'target'})
        self.assertTrue(set(old) <= set(new))
        for name, previous in old.items():
            current = new[name]
            for key in ('type', 'min', 'max', 'precision'):
                self.assertEqual(current.get(key), previous.get(key), (name, key))
            self.assertEqual((current.text or '').strip(), (previous.text or '').strip(), name)
            self.assertEqual([o.get('value') for o in current.findall('{*}option')],
                             [o.get('value') for o in previous.findall('{*}option')], name)
        self.assertEqual([p.get('name') for p in new['tab']], ['column', 'row', 'grid', 'bento'])
        for color in updated.findall('.//{*}param[@type="color"]'):
            self.assertEqual(color.get('appearance'), 'colorbutton')
        for page in new['tab']:
            self.assertIsNotNone(page.find('{*}hbox'))

    def test_descriptor_schema_and_ui_arguments(self):
        tree = etree.parse(str(DIRECTORY / 'modern_grid.inx'))
        schema = Path(inkex.__file__).parent / 'tester/inkscape.extension.rng'
        if schema.exists():
            etree.RelaxNG(etree.parse(str(schema))).assertValid(tree)
        args = []
        names = []
        for param in tree.findall('.//{*}param'):
            names.append(param.get('name'))
            if param.get('type') == 'notebook':
                value = param.find('{*}page').get('name')
            elif param.get('type') == 'optiongroup':
                value = param.find('{*}option').get('value')
            else:
                value = param.text.strip()
            args.append(f'--{param.get("name")}={value}')
        self.assertEqual(len(names), len(set(names)))
        extension = convert(None, *args)
        self.assertEqual(len(group(extension, 'mg-columns')[0]), 12)

    def test_single_page_output_matches_original_for_all_existing_features(self):
        cases = [
            ('--tab=column',),
            ('--tab=column', '--col_type=fixed', '--col_count=3', '--col_align=left', '--col_offset=13'),
            ('--tab=column', '--col_type=fixed', '--col_align=center', '--col_color=4278190335'),
            ('--tab=column', '--col_type=fixed', '--col_align=right', '--col_margin_lock=true', '--col_margin_all=30'),
            ('--tab=column', '--col_type=auto', '--col_margin_top=11', '--col_margin_right=40'),
            ('--tab=row',),
            ('--tab=row', '--row_type=fixed', '--row_align=top', '--row_offset=-12'),
            ('--tab=row', '--row_type=fixed', '--row_align=center', '--row_color=16711935'),
            ('--tab=row', '--row_type=fixed', '--row_align=bottom', '--row_margin_lock=true'),
            ('--tab=row', '--row_type=auto', '--row_margin_bottom=31'),
            ('--tab=grid',),
            ('--tab=grid', '--grd_style=outline', '--grd_border=false', '--grd_columns=3', '--grd_rows=4'),
            ('--tab=grid', '--grd_margin_lock=true', '--grd_margin_all=33', '--grd_opacity=0.4'),
            ('--tab=bento',),
            ('--tab=bento', '--bto_count=12', '--bto_seed=29', '--bto_sync=false', '--bto_rounded=0'),
            ('--tab=bento', '--bto_margin_lock=true', '--bto_margin_all=31', '--bto_gutter=20'),
        ]
        source = document(SHAPES)
        for args in cases:
            with self.subTest(args=args):
                old = convert(source, *args, cls=LegacyGrid)
                new = convert(source, *args)
                self.assertEqual(serialized(new), serialized(old))

    def test_every_native_artboard_uses_its_own_size_and_offset(self):
        extension = load(document(SHAPES, PAGES))
        self.assertEqual(extension._get_artboard_rects(), [(0, 0, 800, 600), (900, 20, 400, 300), (-450, 700, 500, 400)])
        extension.effect()
        groups = group(extension, 'mg-columns')
        self.assertEqual(len(groups), 3)
        self.assertEqual([float(g[0].get('x')) for g in groups], [20, 920, -430])
        self.assertEqual([float(g[0].get('height')) for g in groups], [560, 260, 360])

    def test_single_native_page_is_used_instead_of_root_viewbox(self):
        page = '<inkscape:page x="100" y="200" width="300" height="400"/>'
        extension = load(document(pages=page))
        self.assertEqual(extension._get_artboard_rects(), [(100, 200, 300, 400)])

    def test_rectangle_selection_uses_its_bounds_and_preserves_artwork(self):
        extension = load(document(SHAPES), '--target=selection', '--id=box', '--col_count=4')
        before = etree.tostring(group(extension, 'box'))
        extension.effect()
        columns = group(extension, 'mg-columns')
        self.assertEqual(len(columns), 1)
        self.assertEqual(len(columns[0]), 4)
        first = columns[0][0]
        self.assertEqual((float(first.get('x')), float(first.get('y')), float(first.get('height'))), (70, 80, 160))
        self.assertEqual(etree.tostring(group(extension, 'box')), before)

    def test_circle_selection_uses_surrounding_rectangle_without_shape_clipping(self):
        extension = convert(document(SHAPES), '--target=selection', '--id=circle', '--tab=grid',
                            '--grd_columns=2', '--grd_rows=2', '--grd_gutter=0',
                            '--grd_margin_lock=true', '--grd_margin_all=0')
        grid = group(extension, 'mg-grid')[0]
        self.assertEqual((float(grid[0].get('x')), float(grid[0].get('y'))), (450, 150))
        self.assertEqual((float(grid[-1].get('width')), float(grid[-1].get('height'))), (200, 200))
        self.assertIsNone(group(extension, 'mg-grid').get('clip-path'))
        self.assertIsNone(grid.get('clip-path'))
        self.assertFalse(any(isinstance(node, inkex.Circle) for node in extension.svg.defs.iter()))

    def test_multiple_selections_create_separate_grids(self):
        extension = convert(document(SHAPES), '--target=selection', '--id=box', '--id=circle', '--tab=row')
        groups = group(extension, 'mg-rows')
        self.assertEqual(len(groups), 2)
        self.assertEqual([float(g[0].get('x')) for g in groups], [70, 470])

    def test_transformed_group_and_nested_selection_are_handled_once(self):
        source = document('<g id="design" transform="translate(100,40) scale(2)">'
                          '<rect id="nested" x="10" y="20" width="100" height="80"/></g>')
        extension = load(source, '--target=selection', '--id=design', '--id=nested')
        before = serialized(extension)
        self.assertEqual(extension._get_selection_rects(), [(120, 80, 200, 160)])
        self.assertEqual(serialized(extension), before)
        extension.effect()
        self.assertEqual(len(group(extension, 'mg-columns')), 1)

    def test_transformed_path_and_image_bounds(self):
        source = document('<g transform="translate(50,30)"><path id="triangle" d="M0 0 L150 0 L75 100 Z"/></g>'
                          '<image id="image" x="400" y="50" width="160" height="120"/>')
        extension = load(source, '--target=selection', '--id=triangle', '--id=image')
        self.assertEqual(extension._get_selection_rects(), [(50, 30, 150, 100), (400, 50, 160, 120)])

    def test_switching_targets_updates_same_type_without_duplicates_and_cleans_clips(self):
        first = convert(document(SHAPES, PAGES))
        second = convert(serialized(first), '--target=selection', '--id=box', '--col_count=4')
        self.assertEqual(len(group(second, 'mg-columns')), 1)
        self.assertEqual(len(second.svg.findall('.//*[@id="mg-columns"]')), 1)
        clips = [node for node in second.svg.defs if node.get('id', '').startswith('mg-col-clip-')]
        self.assertEqual(len(clips), 4)
        third = convert(serialized(second), '--target=artboards', '--col_count=4')
        self.assertEqual(len(group(third, 'mg-columns')), 3)
        self.assertEqual(len([node for node in third.svg.defs if node.get('id', '').startswith('mg-col-clip-')]), 12)

    def test_each_type_still_coexists_without_removing_other_types(self):
        source = document(SHAPES)
        for tab in ('column', 'row', 'grid', 'bento'):
            source = serialized(convert(source, '--tab=' + tab, '--target=selection', '--id=box'))
        final = load(source)
        for identifier in ('mg-columns', 'mg-rows', 'mg-grid', 'mg-bento'):
            self.assertIsNotNone(group(final, identifier))

    def test_bento_sync_and_shuffle_still_work_on_multiple_targets(self):
        boxes = '<rect id="a" x="0" y="0" width="300" height="300"/><rect id="b" x="400" y="0" width="300" height="300"/>'
        same = convert(document(boxes), '--tab=bento', '--target=selection', '--id=a', '--id=b')
        first, second = group(same, 'mg-bento')
        dimensions = lambda g: [(n.get('width'), n.get('height')) for n in g]
        self.assertEqual(dimensions(first), dimensions(second))
        varied = convert(document(boxes), '--tab=bento', '--target=selection', '--id=a', '--id=b', '--bto_sync=false')
        first, second = group(varied, 'mg-bento')
        self.assertNotEqual(dimensions(first), dimensions(second))

    def test_missing_or_invalid_target_does_not_change_document(self):
        for args in [('--target=selection',), ('--target=invalid',), ('--tab=invalid',), ('--target=selection', '--id=namedview')]:
            with self.subTest(args=args):
                extension = load(document(SHAPES), *args)
                before = serialized(extension)
                with self.assertRaises(inkex.AbortExtension):
                    extension.effect()
                self.assertEqual(serialized(extension), before)

    def test_invalid_native_page_does_not_change_document(self):
        extension = load(document(pages='<inkscape:page width="0" height="100"/>'))
        before = serialized(extension)
        with self.assertRaises(inkex.AbortExtension):
            extension.effect()
        self.assertEqual(serialized(extension), before)

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape')
    def test_text_and_clone_measurement_uses_actual_renderer_bounds(self):
        source = document('<text id="title" x="40" y="100" style="font-size:40px">Grid test</text>'
                          '<rect id="original" x="10" y="20" width="100" height="80"/>'
                          '<use id="clone" href="#original" x="300" y="200"/>')
        extension = load(source, '--target=selection', '--id=title', '--id=clone')
        rects = extension._get_selection_rects()
        self.assertGreater(rects[0][2], 100)
        self.assertGreater(rects[0][3], 20)
        self.assertEqual(rects[1], (310, 220, 100, 80))
        extension.effect()
        self.assertEqual(len(group(extension, 'mg-columns')), 2)

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape')
    def test_rendered_bounds_convert_mm_and_shifted_viewbox_to_document_units(self):
        source = document('<rect id="original" x="65" y="90" width="30" height="40"/>'
                          '<use id="clone" href="#original" x="20" y="10"/>',
                          width='210mm', height='297mm', viewbox='50 70 210 297')
        extension = load(source, '--target=selection', '--id=clone')
        x, y, w, h = extension._get_selection_rects()[0]
        for actual, expected in zip((x, y, w, h), (85, 100, 30, 40)):
            self.assertAlmostEqual(actual, expected, delta=0.001)

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape')
    def test_rendered_bounds_convert_nonuniform_viewport(self):
        source = document('<rect id="original" x="50" y="60" width="100" height="80"/>'
                          '<use id="clone" href="#original" x="300" y="200"/>',
                          width='1600', height='600', extra='preserveAspectRatio="none"')
        extension = load(source, '--target=selection', '--id=clone')
        x, y, w, h = extension._get_selection_rects()[0]
        for actual, expected in zip((x, y, w, h), (350, 260, 100, 80)):
            self.assertAlmostEqual(actual, expected, delta=0.001)
