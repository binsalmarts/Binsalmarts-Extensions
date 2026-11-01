import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import inkex
from lxml import etree

from blend_tool_pro import (BlendToolPro, MARKER, SETTINGS, SOURCES, SPINE,
                            ArcTable, Morph, aligned_target, mix_paint, transform_to_root)

ROOT = Path(__file__).resolve().parents[1]


def document(body=None, viewport='width="800" height="600" viewBox="0 0 800 600"'):
    if body is None:
        body = ('<rect id="a" x="10" y="10" width="40" height="40" fill="#ff0000"/>'
                '<rect id="b" x="310" y="10" width="80" height="80" fill="#0000ff"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS["inkscape"]}" '
            f'{viewport}>{body}</svg>').encode()


def load(source=None, *args):
    ex = BlendToolPro()
    ex.options = ex.arg_parser.parse_args(args or ['--id=a', '--id=b', '--steps=3'])
    ex.load(io.BytesIO(document() if source is None else source))
    return ex


def run(source=None, *args):
    ex = load(source, *args)
    ex.effect()
    return ex


def blends(ex):
    return [el for el in ex.svg.iter() if el.get(MARKER)]


def steps(ex):
    return [el for el in blends(ex)[-1] if el.get('data-blend-role') == 'step']


def serialize(ex):
    return etree.tostring(ex.svg)


def box_in_document(ex, path):
    return path.path.transform(transform_to_root(path, ex.svg)).bounding_box()


def gradients(ex):
    return ex.svg.xpath('//svg:linearGradient | //svg:radialGradient', namespaces=inkex.NSS)


def assert_paint_references(test, ex):
    for path in ex.svg.xpath('//svg:path', namespaces=inkex.NSS):
        for paint in ('fill', 'stroke'):
            value = path.style.get(paint, '')
            if value.startswith('url(#'):
                test.assertIsNotNone(ex.svg.getElementById(value[5:-1]), value)


class BlendTests(unittest.TestCase):
    def test_count_midpoint_shape_color_and_originals_unchanged(self):
        before = load()
        originals = [etree.tostring(before.svg.getElementById(i)) for i in ['a', 'b']]
        ex = run()
        self.assertEqual(len(steps(ex)), 3)
        middle = steps(ex)[1][0]
        box = box_in_document(ex, middle)
        self.assertAlmostEqual(box.width, 60, places=3)
        self.assertAlmostEqual(box.center_x, 190, places=3)
        self.assertAlmostEqual(box.center_y, 40, places=3)
        self.assertEqual(middle.style['fill'], '#800080')
        self.assertEqual([etree.tostring(ex.svg.getElementById(i)) for i in ['a', 'b']], originals)

    def test_all_checkbox_appearance_controls_are_independent(self):
        source = document('<rect id="a" width="40" height="40" fill="red" stroke="black" stroke-width="2" opacity="0.2"/>'
                          '<rect id="b" x="200" width="40" height="40" fill="blue" stroke="white" stroke-width="6" opacity="0.8"/>')
        for name, prop, expected in [('blend_fill', 'fill', '#ff0000'),
                                     ('blend_stroke', 'stroke-width', '2'),
                                     ('blend_opacity', 'opacity', '0.2')]:
            ex = run(source, '--id=a', '--id=b', '--steps=1', '--' + name + '=false')
            self.assertEqual(steps(ex)[0][0].style[prop], expected)
        ex = run(source, '--id=a', '--id=b', '--steps=1')
        self.assertEqual(float(steps(ex)[0][0].style['stroke-width']), 4)
        self.assertAlmostEqual(float(steps(ex)[0][0].style['opacity']), .5)

    def test_distance_and_smooth_count_and_limits(self):
        source = document('<circle id="a" cx="100" cy="100" r="10" fill="red"/>'
                          '<circle id="b" cx="400" cy="100" r="10" fill="red"/>')
        ex = run(source, '--id=a', '--id=b', '--spacing=distance', '--distance=100')
        self.assertEqual(len(steps(ex)), 2)
        for step, expected_x in zip(steps(ex), [200, 300]):
            x, y = map(float, step.get('data-blend-center').split(','))
            self.assertAlmostEqual(x, expected_x, places=3)
            self.assertAlmostEqual(y, 100, places=3)
        smooth = run(source, '--id=a', '--id=b', '--spacing=smooth', '--smooth_spacing=10')
        self.assertEqual(len(steps(smooth)), 29)
        with self.assertRaises(inkex.AbortExtension):
            run(source, '--id=a', '--id=b', '--spacing=distance', '--distance=0.1')

    def test_multi_stage_order_and_reverse_stacking(self):
        source = document('<circle id="c" cx="500" cy="100" r="30" fill="blue"/>'
                          '<circle id="a" cx="100" cy="100" r="10" fill="red"/>'
                          '<circle id="b" cx="300" cy="100" r="20" fill="green"/>')
        ex = run(source, '--id=c', '--id=a', '--id=b', '--steps=2', '--order=left_right')
        self.assertEqual(json.loads(blends(ex)[0].get(SOURCES)), ['a', 'b', 'c'])
        self.assertEqual(len(steps(ex)), 4)
        reverse = run(source, '--source_ids=a,b,c', '--steps=2', '--reverse_objects=true', '--reverse_stack=true')
        self.assertEqual(steps(reverse)[0].get('data-blend-stage'), '1')
        self.assertEqual(steps(reverse)[0].get('data-blend-t'), '0.666666666667')

    def test_nested_transform_and_idless_parent_geometry(self):
        source = document('<g transform="translate(20.123456789,30) rotate(20)"><g transform="scale(2,3)">'
                          '<rect id="a" width="40" height="20" fill="red"/>'
                          '<rect id="b" x="200" width="40" height="20" fill="blue"/></g></g>')
        before = load(source)
        original_parent_attrs = dict(before.svg[0].attrib)
        ex = run(source, '--id=a', '--id=b', '--steps=1')
        self.assertEqual(blends(ex)[0].getparent(), ex.svg[0][0])
        self.assertEqual(dict(ex.svg[0].attrib), original_parent_attrs)
        bounds = box_in_document(ex, steps(ex)[0][0])
        matrix = transform_to_root(ex.svg.getElementById('a'), ex.svg)
        expected = matrix.apply_to_point((120, 10))
        self.assertAlmostEqual(bounds.center_x, expected.x, places=3)
        self.assertAlmostEqual(bounds.center_y, expected.y, places=3)

    def test_source_group_correspondence_and_inherited_colors(self):
        source = document('<g id="a" fill="red"><circle cx="20" cy="20" r="20"/>'
                          '<path d="M0,50 H40" fill="none" stroke="black"/></g>'
                          '<g id="b" fill="blue" transform="translate(200,0)"><circle cx="20" cy="20" r="10"/>'
                          '<path d="M0,50 H40" fill="none" stroke="white"/></g>')
        ex = run(source, '--id=a', '--id=b', '--steps=1')
        self.assertEqual(len(steps(ex)[0]), 2)
        self.assertEqual(steps(ex)[0][0].style['fill'], '#800080')
        self.assertEqual(steps(ex)[0][1].style['stroke'], '#808080')

    def test_common_parent_opacity_is_not_applied_twice(self):
        source = document('<g id="layer" opacity="0.5"><rect id="a" width="40" height="40" fill="red"/>'
                          '<rect id="b" x="200" width="40" height="40" fill="blue"/></g>')
        ex = run(source, '--id=a', '--id=b', '--steps=1')
        self.assertIs(blends(ex)[0].getparent(), ex.svg.getElementById('layer'))
        self.assertEqual(float(steps(ex)[0][0].style['opacity']), 1)

    def test_morph_open_curves_and_different_node_counts(self):
        source = document('<path id="a" d="M0,0 H100" fill="none" stroke="red"/>'
                          '<path id="b" d="M200,100 Q250,0 300,100" fill="none" stroke="blue"/>')
        ex = run(source, '--id=a', '--id=b', '--steps=4')
        self.assertEqual(len(steps(ex)), 4)
        self.assertFalse(steps(ex)[0][0].path[-1].letter.lower() == 'z')

    def test_holes_are_retained_and_mismatched_holes_fail(self):
        source = document('<path id="a" d="M0,0 H100 V100 H0 Z M20,20 V80 H80 V20 Z" fill-rule="evenodd"/>'
                          '<path id="b" d="M200,0 H300 V100 H200 Z M220,20 V80 H280 V20 Z" fill-rule="evenodd"/>')
        ex = run(source, '--id=a', '--id=b', '--steps=1')
        self.assertEqual(len(steps(ex)[0][0].path.break_apart()), 2)
        with self.assertRaises(inkex.AbortExtension):
            run(document('<path id="a" d="M0,0 H100 V100 H0 Z M20,20 V80 H80 V20 Z"/>'
                         '<rect id="b" x="200" width="100" height="100"/>'))

    def test_manual_reverse_and_target_node_shift(self):
        a = inkex.Path('M0,0 H100 V100 H0 Z')
        b = inkex.Path('M200,0 H300 V100 H200 Z')
        regular = aligned_target(a, b, True, False, 0)
        reverse = aligned_target(a, b, True, True, 0)
        shifted = aligned_target(a, b, True, False, 1)
        self.assertNotEqual(str(regular), str(reverse))
        self.assertNotEqual(next(regular.end_points), next(shifted.end_points))

    def test_spine_arc_length_uniformity_and_curvature(self):
        table = ArcTable(inkex.Path('M0,0 L30,0 L30,70'), .01)
        self.assertEqual(table.length, 100)
        self.assertEqual(table.at(.5)[0], (30, 20))
        source = document('<circle id="a" cx="100" cy="200" r="10" fill="red"/>'
                          '<circle id="b" cx="500" cy="200" r="20" fill="blue"/>'
                          '<path id="guide" d="M0,0 Q200,-200 400,0" fill="none" stroke="black"/>')
        ex = run(source, '--id=a', '--id=b', '--id=guide', '--steps=3', '--follow_spine=true', '--spine_id=guide')
        center = [float(v) for v in steps(ex)[1].get('data-blend-center').split(',')]
        self.assertAlmostEqual(center[0], 300, places=3)
        self.assertAlmostEqual(center[1], 100, places=3)
        self.assertEqual(ex.svg.getElementById('guide').get('d'), 'M0,0 Q200,-200 400,0')

    def test_set_saved_spine_ranges_and_orientation(self):
        source = document('<rect id="a" x="90" y="190" width="20" height="20" fill="red"/>'
                          '<rect id="b" x="490" y="190" width="20" height="20" fill="blue"/>'
                          '<path id="guide" d="M0,0 C0,-200 400,-200 400,0"/>')
        saved = run(source, '--id=guide', '--action=set_spine')
        self.assertEqual(saved.svg.get(SPINE), 'guide')
        ex = run(serialize(saved), '--id=a', '--id=b', '--steps=3', '--follow_spine=true',
                 '--orientation=path', '--spine_start=10', '--spine_end=90', '--show_spine=true')
        self.assertTrue(any(e.get('data-blend-role') == 'spine-preview' for e in blends(ex)[0]))
        self.assertEqual(len(steps(ex)), 3)
        first = box_in_document(ex, steps(ex)[0][0])
        self.assertGreater(first.width, 20)

    def test_biases_and_copy_scale_modes(self):
        ex = run(None, '--id=a', '--id=b', '--steps=1', '--position_bias=2', '--shape_bias=2', '--color_bias=2')
        self.assertEqual(steps(ex)[0].get('data-blend-center'), '110,35')
        self.assertAlmostEqual(box_in_document(ex, steps(ex)[0][0]).width, 50, places=3)
        self.assertEqual(steps(ex)[0][0].style['fill'], '#bf0040')
        for mode, expected in [('copy', 40), ('scale', 60)]:
            ex = run(None, '--id=a', '--id=b', '--steps=1', '--shape_mode=' + mode)
            self.assertAlmostEqual(box_in_document(ex, steps(ex)[0][0]).width, expected, places=3)

    def test_color_space_and_none_fade(self):
        self.assertEqual(mix_paint((0,0,0,1), (255,255,255,1), .5)[0], '#808080')
        self.assertEqual(mix_paint((0,0,0,1), (255,255,255,1), .5, True)[0], '#bcbcbc')
        self.assertEqual(mix_paint(None, (255,0,0,1), .5), ('#ff0000', .5))
        self.assertEqual(mix_paint(None, None, .5), ('none', 0))

    def test_fully_transparent_source_and_effective_paint_alpha(self):
        source = document('<rect id="a" width="40" height="40" fill="red" opacity="0"/>'
                          '<rect id="b" x="200" width="40" height="40" fill="blue" opacity="1"/>')
        ex = run(source, '--id=a', '--id=b', '--steps=1')
        self.assertEqual(float(steps(ex)[0][0].style['opacity']), .5)
        source = document('<rect id="a" width="40" height="40" fill="none"/>'
                          '<rect id="b" x="200" width="40" height="40" fill="red" fill-opacity="0.5"/>')
        ex = run(source, '--id=a', '--id=b', '--steps=1')
        self.assertEqual(float(steps(ex)[0][0].style['fill-opacity']), .25)

    def test_replace_append_refresh_and_original_edits(self):
        ex = run()
        updated = run(serialize(ex), '--id=a', '--id=b', '--steps=5')
        self.assertEqual(len(blends(updated)), 1)
        self.assertEqual(len(steps(updated)), 5)
        appended = run(serialize(updated), '--id=a', '--id=b', '--steps=2', '--on_apply=append')
        self.assertEqual(len(blends(appended)), 2)
        updated.svg.getElementById('b').set('fill', '#00ff00')
        identifier = blends(updated)[0].get('id')
        refreshed = run(serialize(updated), '--id=' + identifier, '--action=refresh')
        self.assertEqual(len(steps(refreshed)), 5)
        self.assertEqual(steps(refreshed)[2][0].style['fill'], '#808000')

    def test_main_dialog_can_edit_a_generated_group(self):
        ex = run()
        edited = run(serialize(ex), '--id=' + blends(ex)[0].get('id'), '--steps=7')
        self.assertEqual(len(blends(edited)), 1)
        self.assertEqual(len(steps(edited)), 7)

    def test_release_and_expand_preserve_source_objects(self):
        for action in ['release', 'expand']:
            ex = run()
            source_before = etree.tostring(ex.svg.getElementById('a'))
            managed_id = blends(ex)[0].get('id')
            result = run(serialize(ex), '--id=' + managed_id, '--action=' + action)
            self.assertEqual(blends(result), [])
            self.assertEqual(etree.tostring(result.svg.getElementById('a')), source_before)
            self.assertEqual(result.svg.getElementById(managed_id) is not None, action == 'expand')

    def test_mm_viewbox_spacing_and_stroke_scaling(self):
        source = document('<circle id="a" cx="100" cy="100" r="10" fill="none" stroke="red" stroke-width="2"/>'
                          '<circle id="b" cx="400" cy="100" r="10" fill="none" stroke="blue" stroke-width="2"/>',
                          viewport='width="3200px" height="2400px" viewBox="0 0 800 600"')
        ex = run(source, '--id=a', '--id=b', '--spacing=distance', '--distance=400')
        self.assertEqual(len(steps(ex)), 2)
        self.assertEqual(float(steps(ex)[0][0].style['stroke-width']), 2)

    def test_all_failures_leave_xml_unchanged(self):
        cases = [(document(), ['--id=a']), (document(), ['--id=a','--id=b','--steps=1001']),
                 (document(), ['--id=a','--id=b','--position_bias=nan']),
                 (document(), ['--id=a','--id=b','--follow_spine=true']),
                 (document('<text id="a">A</text><rect id="b" width="40" height="40"/>'), ['--id=a','--id=b']),
                 (document('<rect id="a" width="40" height="40" filter="url(#f)"/><rect id="b" x="200" width="40" height="40"/>'), ['--id=a','--id=b']),
                 (document('<rect id="a" width="40" height="40" fill="url(#gradient)"/><rect id="b" x="200" width="40" height="40"/>'), ['--id=a','--id=b']),
                 (document('<rect id="a" width="40" height="40"/><path id="b" d="M200,0 H250"/>'), ['--id=a','--id=b']),
                 (document('<path id="a" d="M0,0 L0,0"/><path id="b" d="M200,0 H250"/>'), ['--id=a','--id=b'])]
        for source, args in cases:
            ex = load(source, *args)
            before = serialize(ex)
            with self.subTest(args=args), self.assertRaises(inkex.AbortExtension):
                ex.effect()
            self.assertEqual(serialize(ex), before)

    def test_schema_defaults_and_preview_declaration(self):
        schema = etree.RelaxNG(etree.parse(str(Path(inkex.__file__).parent / 'tester/inkscape.extension.rng')))
        defaults = vars(BlendToolPro().arg_parser.parse_args([]))
        for name in ['blend_tool_pro.inx', 'blend_tool_manage.inx', 'blend_tool_spine.inx']:
            tree = etree.parse(str(ROOT / name))
            self.assertTrue(schema.validate(tree), str(schema.error_log))
            if name != 'blend_tool_pro.inx':
                continue
            effect = tree.xpath('//*[local-name()="effect"]')[0]
            self.assertEqual(effect.get('needs-live-preview'), 'true')
            for param in tree.xpath('//*[local-name()="param"]'):
                name, kind = param.get('name'), param.get('type')
                if kind == 'notebook':
                    continue
                value = param.text or ''
                if kind == 'optiongroup': value = param[0].get('value')
                if kind == 'bool': value = value == 'true'
                if kind in ('int', 'float'): value = float(value)
                self.assertEqual(defaults[name], value, name)

    def test_extension_protocol_and_svg_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'source.svg'
            path.write_bytes(document())
            bootstrap = ('import sys,runpy; sys.path=' + repr(sys.path) + '; sys.argv[0]='
                         + repr(str(ROOT / 'blend_tool_pro.py')) + '; runpy.run_path(sys.argv[0],run_name="__main__")')
            result = subprocess.run([sys.executable, '-c', bootstrap, str(path), '--id=a', '--id=b', '--steps=4'],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            ex = load(result.stdout, '--id=a', '--id=b')
            self.assertEqual(len(steps(ex)), 4)
            ids = [el.get('id') for el in ex.svg.iter() if el.get('id')]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertFalse(ex.svg.xpath('//svg:image', namespaces=inkex.NSS))

    def test_3d_modes_use_editable_gradients_without_images_or_filters(self):
        for mode, tag in [('tube', 'linearGradient'), ('sphere', 'radialGradient')]:
            with self.subTest(mode=mode):
                ex = run(None, '--id=a', '--id=b', '--steps=3', '--shading_mode=' + mode)
                self.assertEqual(len(steps(ex)), 3)
                self.assertEqual(len(gradients(ex)), 5)  # Three steps plus two opaque endpoints.
                for gradient in gradients(ex):
                    self.assertEqual(gradient.tag_name, tag)
                    self.assertEqual(gradient.get('gradientUnits'), 'userSpaceOnUse')
                    offsets = [float(stop.get('offset')) for stop in gradient]
                    self.assertEqual(offsets, sorted(offsets))
                    self.assertEqual((offsets[0], offsets[-1]), (0, 1))
                    self.assertGreater(len({stop.get('stop-color') for stop in gradient}), 10)
                self.assertFalse(ex.svg.xpath('//svg:image | //svg:filter | //svg:mask', namespaces=inkex.NSS))
                assert_paint_references(self, ex)

    def test_3d_off_or_zero_strength_leaves_flat_output(self):
        for option in ['--shading_mode=off', '--shading_mode=tube --shading_strength=0']:
            ex = run(None, '--id=a', '--id=b', '--steps=1', '--cast_shadow=true', *option.split())
            self.assertFalse(gradients(ex))
            self.assertEqual(steps(ex)[0][0].style['fill'], '#800080')
            self.assertEqual(blends(ex)[0].get('data-blend-cap-count'), '0')
            self.assertFalse(ex.svg.xpath('//*[@data-blend-role="shadow"]'))

    def test_3d_opaque_endpoints_cover_sources_without_changing_them(self):
        source = document('<g id="art"><rect id="a" x="10" y="10" width="40" height="40" fill="red"/>'
                          '<rect id="b" x="310" y="10" width="80" height="80" fill="blue"/></g>')
        before = load(source)
        originals = [etree.tostring(before.svg.getElementById(i)) for i in ['a', 'b']]
        ex = run(source, '--id=a', '--id=b', '--steps=3', '--shading_mode=tube')
        self.assertEqual([etree.tostring(ex.svg.getElementById(i)) for i in ['a', 'b']], originals)
        caps = ex.svg.xpath('//*[@data-blend-role="endpoint"]')
        self.assertEqual({cap.get('data-blend-source') for cap in caps}, {'a', 'b'})
        parent = ex.svg.getElementById('art')
        self.assertGreater(parent.index(blends(ex)[0]), parent.index(ex.svg.getElementById('b')))
        for cap in caps:
            original = ex.svg.getElementById(cap.get('data-blend-source'))
            expected = original.path.bounding_box()
            actual = box_in_document(ex, cap[0])
            self.assertAlmostEqual(actual.center_x, expected.center_x, places=3)
            self.assertAlmostEqual(actual.center_y, expected.center_y, places=3)

    def test_3d_transparent_endpoints_are_not_duplicated_and_alpha_is_preserved(self):
        source = document('<rect id="a" width="40" height="40" fill="red" opacity="0.5"/>'
                          '<rect id="b" x="200" width="40" height="40" fill="blue" fill-opacity="0.6"/>')
        flat = run(source, '--id=a', '--id=b', '--steps=1')
        lit = run(source, '--id=a', '--id=b', '--steps=1', '--shading_mode=sphere')
        self.assertFalse(lit.svg.xpath('//*[@data-blend-role="endpoint"]'))
        for property_name in ('opacity', 'fill-opacity', 'stroke-opacity'):
            self.assertEqual(steps(lit)[0][0].style[property_name], steps(flat)[0][0].style[property_name])
        self.assertEqual(len(gradients(lit)), 1)

    def test_3d_endpoint_checkbox_can_keep_original_flat_endpoints(self):
        ex = run(None, '--id=a', '--id=b', '--steps=3', '--shading_mode=tube', '--shade_endpoints=false')
        self.assertEqual(blends(ex)[0].get('data-blend-cap-count'), '0')
        self.assertEqual(len(gradients(ex)), 3)

    def test_3d_lighting_and_gloss_controls_change_the_surface(self):
        def colors(*args):
            ex = run(None, '--id=a', '--id=b', '--steps=1', '--shading_mode=tube',
                     '--shade_endpoints=false', *args)
            return [s.get('stop-color') for s in gradients(ex)[0]]
        self.assertNotEqual(colors('--light_angle=90'), colors('--light_angle=270'))
        self.assertNotEqual(colors('--gloss=0'), colors('--gloss=1'))
        self.assertNotEqual(colors('--ambient=0.1'), colors('--ambient=0.8'))
        self.assertNotEqual(colors('--shading_strength=0.2'), colors('--shading_strength=1'))
        self.assertNotEqual(colors('--shininess=4'), colors('--shininess=64'))

    def test_3d_stroke_shading_can_be_disabled_independently(self):
        source = document('<path id="a" d="M0,20 H80" fill="none" stroke="red" stroke-width="8"/>'
                          '<path id="b" d="M200,20 H280" fill="none" stroke="blue" stroke-width="8"/>')
        for enabled in [False, True]:
            ex = run(source, '--id=a', '--id=b', '--steps=1', '--shading_mode=tube',
                     '--shade_stroke=' + str(enabled).lower(), '--shade_endpoints=false')
            self.assertEqual(steps(ex)[0][0].style['fill'], 'none')
            self.assertEqual(bool(gradients(ex)), enabled)
            self.assertEqual(steps(ex)[0][0].style['stroke'].startswith('url(#'), enabled)
            if enabled:
                self.assertAlmostEqual(abs(float(gradients(ex)[0].get('y2')) - float(gradients(ex)[0].get('y1'))), 8)

    def test_3d_shadow_uses_one_group_opacity_and_correct_physical_offset(self):
        source = document(viewport='width="3200px" height="2400px" viewBox="0 0 800 600"')
        ex = run(source, '--id=a', '--id=b', '--steps=1', '--shading_mode=tube',
                 '--shade_endpoints=false', '--cast_shadow=true', '--shadow_opacity=0.2',
                 '--shadow_distance=12', '--light_angle=225')
        shadow = ex.svg.xpath('//*[@data-blend-role="shadow"]')[0]
        self.assertEqual(float(shadow.style['opacity']), .2)
        expected = box_in_document(ex, steps(ex)[0][0])
        actual = box_in_document(ex, shadow[0])
        self.assertAlmostEqual(actual.center_x - expected.center_x, 3 / math.sqrt(2), places=3)
        self.assertAlmostEqual(actual.center_y - expected.center_y, 3 / math.sqrt(2), places=3)
        self.assertEqual(shadow[0].style['fill'], '#000000')

    def test_3d_refresh_and_release_do_not_leave_duplicate_or_orphan_gradients(self):
        ex = run(None, '--id=a', '--id=b', '--steps=3', '--shading_mode=sphere', '--cast_shadow=true')
        first_ids = {g.get('id') for g in gradients(ex)}
        refreshed = run(serialize(ex), '--id=' + blends(ex)[0].get('id'), '--action=refresh')
        self.assertEqual(len(gradients(refreshed)), 5)
        self.assertTrue(first_ids.isdisjoint(g.get('id') for g in gradients(refreshed)))
        self.assertEqual(json.loads(blends(refreshed)[0].get(SETTINGS))['shading_mode'], 'sphere')
        assert_paint_references(self, refreshed)
        released = run(serialize(refreshed), '--id=' + blends(refreshed)[0].get('id'), '--action=release')
        self.assertEqual(gradients(released), [])
        self.assertFalse(released.svg.xpath('//*[@data-blend-role="shadow"]'))
        self.assertIsNotNone(released.svg.getElementById('a'))

    def test_3d_expand_keeps_gradients_and_all_paint_references(self):
        ex = run(None, '--id=a', '--id=b', '--steps=3', '--shading_mode=tube', '--cast_shadow=true')
        identifier = blends(ex)[0].get('id')
        expanded = run(serialize(ex), '--id=' + identifier, '--action=expand')
        self.assertEqual(blends(expanded), [])
        self.assertEqual(len(gradients(expanded)), 5)
        self.assertIsNotNone(expanded.svg.getElementById(identifier))
        assert_paint_references(self, expanded)

    def test_refresh_legacy_1_0_settings_defaults_to_flat(self):
        ex = run()
        group = blends(ex)[0]
        group.set(MARKER, '1.0.0')
        saved = json.loads(group.get(SETTINGS))
        for key in ('shading_mode', 'shade_stroke', 'shade_endpoints', 'cast_shadow', 'shading_strength',
                    'light_angle', 'light_elevation', 'ambient', 'gloss', 'shininess', 'shadow_distance', 'shadow_opacity'):
            saved.pop(key)
        group.set(SETTINGS, json.dumps(saved))
        refreshed = run(serialize(ex), '--id=' + group.get('id'), '--action=refresh')
        self.assertEqual(len(steps(refreshed)), 3)
        self.assertEqual(gradients(refreshed), [])
        self.assertEqual(json.loads(blends(refreshed)[0].get(SETTINGS))['shading_mode'], 'off')

    def test_3d_invalid_settings_do_not_modify_document(self):
        for option in ['--shading_strength=1.1', '--light_angle=361', '--light_elevation=-1',
                       '--ambient=nan', '--gloss=-0.1', '--shininess=0', '--shadow_opacity=1.1', '--shadow_distance=-1']:
            ex = load(None, '--id=a', '--id=b', '--shading_mode=tube', option)
            before = serialize(ex)
            with self.subTest(option=option), self.assertRaises(inkex.AbortExtension):
                ex.effect()
            self.assertEqual(serialize(ex), before)

    def test_3d_curve_tangents_are_continuous_at_sampling_boundaries(self):
        table = ArcTable(inkex.Path('M0,0 C0,200 400,200 400,0'), .05)
        for length in table.lengths[1:-1]:
            fraction = length / table.length
            before = table.at(fraction - 1e-7, True)[1]
            after = table.at(fraction + 1e-7, True)[1]
            jump = abs(math.atan2(math.sin(after - before), math.cos(after - before)))
            self.assertLess(jump, .001)

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_inkscape_preserves_3d_gradients_through_save_refresh_and_expand(self):
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td) / '3d.svg', Path(td) / 'saved.svg'
            ex = run(None, '--id=a', '--id=b', '--steps=3', '--shading_mode=sphere', '--cast_shadow=true')
            etree.ElementTree(ex.svg).write(str(source))
            proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(source), '--export-type=svg',
                                   '--export-filename=' + str(target)], capture_output=True, text=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(target.is_file())
            reopened = load(target.read_bytes())
            self.assertEqual(len(gradients(reopened)), 5)
            assert_paint_references(self, reopened)
            refreshed = run(target.read_bytes(), '--id=' + blends(reopened)[0].get('id'), '--action=refresh')
            self.assertEqual(len(gradients(refreshed)), 5)
            self.assertTrue(refreshed.svg.xpath('//*[@data-blend-role="shadow"]'))
            expanded = run(serialize(refreshed), '--id=' + blends(refreshed)[0].get('id'), '--action=expand')
            self.assertEqual(len(gradients(expanded)), 5)
            assert_paint_references(self, expanded)

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_inkscape_saves_reopens_and_can_refresh_saved_blend(self):
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td) / 'blend.svg', Path(td) / 'saved.svg'
            ex = run()
            etree.ElementTree(ex.svg).write(str(source))
            proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(source), '--export-type=svg',
                                   '--export-filename=' + str(target)], capture_output=True, text=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(target.is_file())
            reopened = load(target.read_bytes())
            refreshed = run(target.read_bytes(), '--id=' + blends(reopened)[0].get('id'), '--action=refresh')
            self.assertEqual(len(steps(refreshed)), 3)


if __name__ == '__main__':
    unittest.main()
