import io
import itertools
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

from vector_effects_pro import (VectorEffectsPro, MARKER, ROLE, SETTINGS, SOURCE,
                                CHOICES, GRAIN_PRESETS, Contour, color, composed, displaced,
                                puckered, warp_function, warped)

ROOT = Path(__file__).resolve().parents[1]


def document(body=None, viewport='width="800" height="600" viewBox="0 0 800 600"'):
    body = body if body is not None else ('<g id="logo" transform="translate(100,100)">'
           '<rect id="part" width="200" height="80" fill="#635bff"/></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS["inkscape"]}" '
            f'{viewport}>{body}</svg>').encode()


def load(source=None, *args):
    ex = VectorEffectsPro()
    ex.options = ex.arg_parser.parse_args(args or ['--id=logo'])
    ex.load(io.BytesIO(document() if source is None else source))
    return ex


def run(source=None, *args):
    ex = load(source, *args)
    ex.effect()
    return ex


def serialized(ex):
    return etree.tostring(ex.svg)


def wrappers(ex):
    return [el for el in ex.svg.iter() if el.get(MARKER)]


def artwork(ex, index=0):
    return next(el for el in wrappers(ex)[index].iter() if el.get(ROLE) == 'artwork')


def manage(ex, action):
    return run(serialized(ex), *['--id=' + el.get('id') for el in wrappers(ex)], '--action=' + action)


def filters(ex):
    return ex.svg.xpath('//svg:filter', namespaces=inkex.NSS)


class VectorEffectsTests(unittest.TestCase):
    def test_every_geometry_preserves_original_and_creates_editable_paths(self):
        before = etree.tostring(load().svg.getElementById('logo'))
        for effect in CHOICES['geometry']:
            with self.subTest(effect=effect):
                ex = run(None, '--id=logo', '--geometry=' + effect, '--shadow=true')
                self.assertEqual(etree.tostring(ex.svg.getElementById('logo')), before)
                self.assertTrue(all(isinstance(p, inkex.PathElement) for p in artwork(ex)))
                self.assertEqual(ex.svg.getElementById('logo').getparent().get(ROLE), 'original')
                self.assertEqual(ex.svg.getElementById('logo').getparent().style['display'], 'none')
                self.assertEqual(len(filters(ex)), 1)
                self.assertFalse(ex.svg.xpath('//svg:image', namespaces=inkex.NSS))

    def test_release_restores_exact_original_xml_and_stacking(self):
        source = document('<rect id="back" width="1" height="1"/>'
                          '<g id="logo" transform="matrix(1.123456789,0,0,2.1,20,30)" style="fill: #635bff; opacity: 0.8">'
                          '<rect id="part" width="200" height="80"/></g><circle id="front" r="3"/>')
        before = etree.tostring(load(source).svg.getElementById('logo'))
        ex = run(source, '--id=logo', '--glow=true', '--outline=true')
        released = manage(ex, 'release')
        self.assertEqual(etree.tostring(released.svg.getElementById('logo')), before)
        self.assertEqual([el.get('id') for el in released.svg], ['back', 'logo', 'front'])
        self.assertEqual(filters(released), [])

    def test_all_seven_appearance_combinations_are_independent(self):
        names = ['shadow', 'glow', 'outline']
        for flags in itertools.product((False, True), repeat=3):
            if not any(flags):
                continue
            ex = run(None, '--id=logo', '--geometry=none', *['--' + k + '=' + str(v).lower() for k, v in zip(names, flags)])
            saved = json.loads(wrappers(ex)[0].get(SETTINGS))
            self.assertEqual([saved[name] for name in names], list(flags))
            self.assertEqual(len(filters(ex)), 1)
            merges = filters(ex)[0].xpath('./svg:feMerge/svg:feMergeNode', namespaces=inkex.NSS)
            self.assertEqual(len(merges), 1 + sum(flags))
            self.assertEqual(sum(node.get('in') == 'SourceGraphic' for node in merges), 1)

    def test_roughen_is_repeatable_and_seed_changes_result(self):
        first, repeated = run(), run()
        self.assertEqual(str(artwork(first)[0].path), str(artwork(repeated)[0].path))
        other = run(None, '--id=logo', '--seed=25')
        self.assertNotEqual(str(artwork(first)[0].path), str(artwork(other)[0].path))
        refreshed = manage(first, 'refresh')
        self.assertEqual(str(artwork(first)[0].path), str(artwork(refreshed)[0].path))

    def test_roughen_detail_and_smooth_points(self):
        low = run(None, '--id=logo', '--detail=5')
        high = run(None, '--id=logo', '--detail=25', '--points=smooth')
        self.assertGreater(len(artwork(high)[0].path), len(artwork(low)[0].path))
        self.assertTrue(any(command.letter == 'C' for command in artwork(high)[0].path))

    def test_zigzag_measures_amplitude_and_keeps_open_endpoints(self):
        source = document('<path id="logo" d="M0,0 H100" fill="none" stroke="red"/>')
        ex = run(source, '--id=logo', '--geometry=zigzag', '--size=8', '--zigzag_cycles=5')
        points = list(artwork(ex)[0].path.end_points)
        self.assertEqual(tuple(points[0]), (0, 0))
        self.assertEqual(tuple(points[-1]), (100, 0))
        self.assertEqual(max(p.y for p in points), 8)
        self.assertEqual(min(p.y for p in points), -8)
        self.assertEqual(len(points), 11)

    def test_open_endpoints_can_be_displaced_and_closed_paths_stay_closed(self):
        source = document('<path id="logo" d="M0,0 H100" fill="none" stroke="red"/>')
        ex = run(source, '--id=logo', '--geometry=zigzag', '--preserve_endpoints=false')
        self.assertNotEqual(tuple(next(artwork(ex)[0].path.end_points)), (0, 0))
        for effect in ['roughen', 'zigzag', 'pucker_bloat', 'arc', 'bulge', 'wave']:
            ex = run(None, '--id=logo', '--geometry=' + effect)
            self.assertEqual(artwork(ex)[0].path[-1].letter.lower(), 'z')

    def test_pucker_bloat_moves_anchors_and_handles_in_opposite_directions(self):
        path = inkex.Path('M0,0 H100 V100 H0 Z')
        box = path.bounding_box()
        bloated = puckered(path, box, .5).to_superpath()[0]
        puckered_path = puckered(path, box, -.5).to_superpath()[0]
        self.assertEqual(bloated[0][1], [25, 25])
        self.assertEqual(puckered_path[0][1], [-25, -25])
        self.assertEqual(bloated[0][2], [-25, -25])
        self.assertEqual(puckered_path[0][2], [25, 25])

    def test_zero_strength_preserves_geometry(self):
        baseline = run(None, '--id=logo', '--geometry=none', '--outline=true')
        for effect, option in [('roughen', '--size=0'), ('zigzag', '--size=0'), ('pucker_bloat', '--amount=0'),
                               ('arc', '--amount=0'), ('bulge', '--amount=0'), ('wave', '--size=0')]:
            ex = run(None, '--id=logo', '--geometry=' + effect, option)
            self.assertEqual(str(artwork(ex)[0].path), str(artwork(baseline)[0].path))

    def test_circular_arc_warp_follows_expected_circle(self):
        options = load(None, '--geometry=arc', '--amount=50').options
        line = inkex.Path('M0,0 H100')
        fn = warp_function(line.bounding_box(), options, 0)
        radius = 100 / (math.pi / 2)
        path = warped(line, fn, .05)
        for sub in path.to_superpath():
            for left, right in zip(sub, sub[1:]):
                for t in [0, .25, .5, .75, 1]:
                    from vector_effects_pro import cubic
                    point = cubic((left[1], left[2], right[0], right[1]), t)
                    self.assertAlmostEqual(math.hypot(point[0] - 50, point[1] - radius), radius, delta=.06)

    def test_bulge_and_wave_have_expected_center_displacement(self):
        path = inkex.Path('M0,0 H100 V40 H0 Z')
        options = load(None, '--geometry=bulge', '--amount=50').options
        fn = warp_function(path.bounding_box(), options, 6)
        self.assertEqual(fn((50, 0)), (50, -10))
        self.assertEqual(fn((0, 0)), (0, 0))
        options.geometry = 'wave'
        options.wave_cycles = 1
        fn = warp_function(path.bounding_box(), options, 8)
        self.assertAlmostEqual(fn((25, 0))[1], 8)
        self.assertAlmostEqual(fn((75, 0))[1], -8)
        options.axis = 'vertical'
        fn = warp_function(path.bounding_box(), options, 8)
        self.assertAlmostEqual(fn((0, 10))[0], 8)

    def test_group_warp_uses_shared_group_frame(self):
        source = document('<g id="logo"><rect id="left" width="40" height="40"/>'
                          '<rect id="right" x="160" width="40" height="40"/></g>')
        ex = run(source, '--id=logo', '--geometry=wave', '--size=10')
        self.assertEqual(len(artwork(ex)), 2)
        first, second = [p.path.bounding_box() for p in artwork(ex)]
        self.assertGreater(first.center_y, 20)
        self.assertLess(second.center_y, 20)

    def test_nested_transforms_and_physical_appearance_units(self):
        source = document('<g transform="translate(30,40) rotate(20)"><g transform="scale(2,3)">'
                          '<rect id="logo" width="100" height="40" fill="red"/></g></g>',
                          viewport='width="3200px" height="2400px" viewBox="0 0 800 600"')
        before = load(source)
        matrix = composed(before.svg.getElementById('logo'), before.svg)
        expected = before.svg.getElementById('logo').path.transform(matrix).bounding_box()
        ex = run(source, '--id=logo', '--geometry=none', '--shadow=true', '--shadow_dx=12', '--shadow_blur=8')
        generated = artwork(ex)[0]
        actual = generated.path.transform(composed(generated, ex.svg)).bounding_box()
        self.assertAlmostEqual(actual.center_x, expected.center_x, places=3)
        self.assertAlmostEqual(actual.center_y, expected.center_y, places=3)
        offset = filters(ex)[0].find(inkex.addNS('feOffset', 'svg'))
        blur = filters(ex)[0].find(inkex.addNS('feGaussianBlur', 'svg'))
        self.assertEqual(float(offset.get('dx')), 3)
        self.assertEqual(float(blur.get('stdDeviation')), 2)

    def test_common_parent_opacity_is_not_doubled(self):
        source = document('<g id="layer" opacity="0.5"><rect id="logo" width="100" height="40" fill="red"/></g>')
        ex = run(source, '--id=logo', '--geometry=none', '--shadow=true')
        self.assertEqual(float(artwork(ex)[0].style['opacity']), 1)
        self.assertEqual(ex.svg.getElementById('layer').get('opacity'), '0.5')

    def test_rgba_color_and_flood_opacity(self):
        self.assertEqual(color(4278190208)[0], '#ff0000')
        ex = run(None, '--id=logo', '--geometry=none', '--glow=true', '--glow_color=4278190208', '--glow_opacity=0.5')
        flood = filters(ex)[0].find(inkex.addNS('feFlood', 'svg'))
        self.assertEqual(flood.get('flood-color'), '#ff0000')
        self.assertAlmostEqual(float(flood.get('flood-opacity')), 128/255*.5)

    def test_inner_shadow_and_glow_use_inverted_alpha_and_inside_clip(self):
        for flag in ['shadow', 'glow']:
            ex = run(None, '--id=logo', '--geometry=none', '--' + flag + '=true', '--' + flag + '_mode=inner')
            self.assertTrue(filters(ex)[0].xpath('./svg:feComponentTransfer/svg:feFuncA[@tableValues="1 0"]', namespaces=inkex.NSS))
            composites = filters(ex)[0].xpath('./svg:feComposite[@in2="SourceAlpha"]', namespaces=inkex.NSS)
            self.assertTrue(composites)
            merges = filters(ex)[0].xpath('./svg:feMerge/svg:feMergeNode', namespaces=inkex.NSS)
            self.assertEqual(merges[0].get('in'), 'SourceGraphic')

    def test_outline_positions_use_expected_morphology_and_layers(self):
        for position, count, source_first in [('outer', 1, False), ('inner', 1, True), ('center', 2, True)]:
            ex = run(None, '--id=logo', '--geometry=none', '--outline=true', '--outline_position=' + position, '--outline_width=8')
            morphs = filters(ex)[0].xpath('./svg:feMorphology', namespaces=inkex.NSS)
            self.assertEqual(len(morphs), count)
            self.assertEqual(float(morphs[0].get('radius')), 4 if position == 'center' else 8)
            merge = filters(ex)[0].xpath('./svg:feMerge/svg:feMergeNode', namespaces=inkex.NSS)
            self.assertEqual(merge[0].get('in') == 'SourceGraphic', source_first)

    def test_filter_region_contains_large_shadow_and_glow(self):
        ex = run(None, '--id=logo', '--geometry=none', '--shadow=true', '--shadow_dx=-50', '--shadow_dy=60',
                 '--shadow_blur=20', '--glow=true', '--glow_blur=10')
        effect = filters(ex)[0]
        self.assertLessEqual(float(effect.get('x')), 100-50-80)
        self.assertGreaterEqual(float(effect.get('y')) + float(effect.get('height')), 180+60+80)
        self.assertEqual(effect.get('filterUnits'), 'userSpaceOnUse')

    def test_filter_graph_has_valid_inputs_and_unique_results(self):
        ex = run(None, '--id=logo', '--shadow=true', '--glow=true', '--outline=true', '--shadow_mode=inner')
        seen = {'SourceGraphic', 'SourceAlpha'}
        for node in filters(ex)[0]:
            for child in [node, *node]:
                for key in ['in', 'in2']:
                    if child.get(key): self.assertIn(child.get(key), seen)
            self.assertNotIn(node.get('result'), seen)
            seen.add(node.get('result'))

    def test_edit_original_and_refresh_rebuilds_without_accumulating_filters(self):
        ex = run(None, '--id=logo', '--geometry=bulge', '--shadow=true')
        edited = manage(ex, 'edit')
        wrapper = wrappers(edited)[0]
        self.assertEqual(wrapper.get('data-vep-editing'), 'true')
        render = next(el for el in wrapper if el.get(ROLE) == 'render')
        self.assertEqual(render.style['display'], 'none')
        edited.svg.getElementById('part').set('width', '300')
        refreshed = manage(edited, 'refresh')
        self.assertEqual(len(filters(refreshed)), 1)
        self.assertEqual(refreshed.svg.getElementById('part').get('width'), '300')
        self.assertGreater(artwork(refreshed)[0].path.bounding_box().width, 299)
        self.assertIsNone(wrappers(refreshed)[0].get('data-vep-editing'))

    def test_main_dialog_can_change_existing_effect(self):
        ex = run()
        original_id = wrappers(ex)[0].get(SOURCE)
        updated = run(serialized(ex), '--id=' + wrappers(ex)[0].get('id'), '--geometry=zigzag', '--glow=true')
        self.assertEqual(len(wrappers(updated)), 1)
        self.assertEqual(wrappers(updated)[0].get(SOURCE), original_id)
        self.assertEqual(json.loads(wrappers(updated)[0].get(SETTINGS))['geometry'], 'zigzag')

    def test_moving_effect_group_survives_refresh_and_release(self):
        ex = run(None, '--id=logo', '--geometry=none', '--outline=true')
        wrappers(ex)[0].attrib['transform'] = 'translate(30,20)'
        wrappers(ex)[0].style = {'opacity': '50%'}
        for _ in range(2):
            ex = manage(ex, 'refresh')
            path = artwork(ex)[0]
            box = path.path.transform(composed(path, ex.svg)).bounding_box()
            self.assertAlmostEqual(box.left, 130, places=3)
            self.assertAlmostEqual(box.top, 120, places=3)
            self.assertEqual(float(path.style['opacity']), 1)
            self.assertEqual(float(wrappers(ex)[0].style('opacity')), .5)
        released = manage(ex, 'release')
        source = released.svg.getElementById('logo')
        matrix = composed(source, released.svg)
        corner = matrix.apply_to_point((0, 0))
        self.assertEqual(tuple(corner), (130, 120))
        self.assertEqual(float(source.style['opacity']), .5)

    def test_multiple_objects_and_nested_selection_are_not_processed_twice(self):
        source = document('<g id="a"><rect id="part" width="100" height="40"/></g>'
                          '<circle id="b" cx="300" cy="100" r="30"/>')
        ex = run(source, '--id=a', '--id=part', '--id=b', '--glow=true')
        self.assertEqual(len(wrappers(ex)), 2)
        refreshed = manage(ex, 'refresh')
        self.assertEqual(len(filters(refreshed)), 2)
        released = manage(refreshed, 'release')
        self.assertEqual([el.get('id') for el in released.svg], ['a', 'b'])

    def test_open_zero_length_path_is_rejected_cleanly_if_not_drawable(self):
        ex = load(document('<path id="logo" d="M0,0"/>'))
        with self.assertRaises(inkex.AbortExtension): ex.effect()

    def test_invalid_inputs_do_not_modify_original_document(self):
        cases = [(document(), ['--geometry=none']), (document(), ['--size=nan']),
                 (document(), ['--shadow_color=invalid-color']), (document(), ['--detail=1001']),
                 (document('<text id="logo">TEXT</text>'), []),
                 (document('<rect id="logo" width="100" height="40" fill="url(#gradient)"/>'), []),
                 (document('<g id="logo" clip-path="url(#clip)"><rect width="100" height="40"/></g>'), []),
                 (document('<rect id="logo" width="50%" height="40"/>'), []),
                 (document('<path id="logo" d="M0,0 V100"/>'), ['--geometry=arc']),
                 (document(), ['--geometry=zigzag', '--zigzag_cycles=2001'])]
        for source, args in cases:
            ex = load(source, '--id=logo', *args)
            before = serialized(ex)
            with self.subTest(args=args), self.assertRaises(inkex.AbortExtension): ex.effect()
            self.assertEqual(serialized(ex), before)

    def test_no_selection_and_manage_on_ordinary_artwork_fail(self):
        for args in [['--size=5'], ['--id=logo','--action=release'], ['--id=logo','--action=refresh']]:
            ex = load(None, *args)
            with self.assertRaises(inkex.AbortExtension): ex.effect()

    def test_batch_error_is_atomic_and_does_not_hide_valid_objects(self):
        source = document('<rect id="valid" width="100" height="40"/><text id="invalid">TEXT</text>')
        ex = load(source, '--id=valid', '--id=invalid', '--shadow=true')
        before = serialized(ex)
        with self.assertRaises(inkex.AbortExtension): ex.effect()
        self.assertEqual(serialized(ex), before)
        self.assertEqual(wrappers(ex), [])

    def test_compound_path_holes_remain_separate_closed_subpaths(self):
        source = document('<path id="logo" d="M0,0 H200 V80 H0 Z M50,20 H70 V60 H50 Z" fill-rule="evenodd"/>')
        for effect in ['roughen', 'zigzag', 'pucker_bloat', 'arc', 'bulge', 'wave']:
            with self.subTest(effect=effect):
                ex = run(source, '--id=logo', '--geometry=' + effect)
                parts = artwork(ex)[0].path.break_apart()
                self.assertEqual(len(parts), 2)
                self.assertTrue(all(part[-1].letter.lower() == 'z' for part in parts))
                self.assertEqual(artwork(ex)[0].style['fill-rule'], 'evenodd')

    def test_invalid_saved_metadata_fails_without_touching_original(self):
        ex = run()
        wrappers(ex)[0].set(SETTINGS, '[1,2]')
        attempted = load(serialized(ex), '--id=' + wrappers(ex)[0].get('id'), '--action=refresh')
        before = serialized(attempted)
        with self.assertRaisesRegex(inkex.AbortExtension, 'Invalid saved settings'): attempted.effect()
        self.assertEqual(serialized(attempted), before)

    def test_inx_schema_preview_and_parser_defaults_match(self):
        schema = etree.RelaxNG(etree.parse(str(Path(inkex.__file__).parent / 'tester/inkscape.extension.rng')))
        defaults = vars(VectorEffectsPro().arg_parser.parse_args([]))
        for filename in ['vector_effects_pro.inx', 'vector_effects_manage.inx', 'vector_effects_grain.inx', 'vector_effects_noise.inx']:
            tree = etree.parse(str(ROOT / filename))
            self.assertTrue(schema.validate(tree), str(schema.error_log))
            if filename != 'vector_effects_pro.inx': continue
            self.assertEqual(tree.xpath('//*[local-name()="effect"]')[0].get('needs-live-preview'), 'true')
            for param in tree.xpath('//*[local-name()="param"]'):
                name, kind = param.get('name'), param.get('type')
                if kind == 'notebook': continue
                value = param.text or ''
                if kind == 'optiongroup': value = param[0].get('value')
                if kind == 'bool': value = value == 'true'
                if kind in ('int', 'float'): value = float(value)
                if kind == 'color': self.assertEqual(color(defaults[name]), color(value), name)
                else: self.assertEqual(defaults[name], value, name)

    def test_grain_ten_presets_generate_procedural_svg_textures(self):
        self.assertEqual(len(GRAIN_PRESETS), 10)
        frequencies = set()
        for preset in GRAIN_PRESETS:
            ex = run(None, '--id=logo', '--geometry=none', '--grain=true', '--grain_type=' + preset)
            noises = filters(ex)[0].xpath('./svg:feTurbulence', namespaces=inkex.NSS)
            self.assertEqual(len(noises), 1)
            frequencies.add(noises[0].get('baseFrequency'))
            self.assertFalse(ex.svg.xpath('//svg:image', namespaces=inkex.NSS))
            self.assertTrue(filters(ex)[0].xpath('./svg:feComposite[@operator="in"][@in2="SourceAlpha"]', namespaces=inkex.NSS))
        self.assertGreater(len(frequencies), 5)

    def test_grain_zero_intensity_is_a_passthrough_and_does_not_change_geometry(self):
        baseline = run(None, '--id=logo', '--geometry=none', '--outline=true')
        ex = run(None, '--id=logo', '--geometry=none', '--grain=true', '--grain_intensity=0')
        self.assertFalse(filters(ex)[0].xpath('./svg:feTurbulence', namespaces=inkex.NSS))
        self.assertEqual(str(artwork(ex)[0].path), str(artwork(baseline)[0].path))
        merge = filters(ex)[0].xpath('./svg:feMerge/svg:feMergeNode', namespaces=inkex.NSS)
        self.assertEqual([node.get('in') for node in merge], ['SourceGraphic'])

    def test_grain_physical_size_is_consistent_across_viewbox_scales(self):
        normal = run(None, '--id=logo', '--geometry=none', '--grain=true', '--grain_size=2')
        scaled = run(document(viewport='width="3200px" height="2400px" viewBox="0 0 800 600"'),
                     '--id=logo', '--geometry=none', '--grain=true', '--grain_size=2')
        def frequency(ex):
            noise = filters(ex)[0].find(inkex.addNS('feTurbulence', 'svg'))
            return list(map(float, noise.get('baseFrequency').split()))
        for a, b in zip(frequency(normal), frequency(scaled)):
            self.assertAlmostEqual(b / 4, a)

    def test_grain_direction_and_colored_mode_are_independent(self):
        for preset, lower_axis in [('horizontal', 0), ('vertical', 1)]:
            ex = run(None, '--id=logo', '--geometry=none', '--grain=true', '--grain_type=' + preset)
            noise = filters(ex)[0].find(inkex.addNS('feTurbulence', 'svg'))
            fx, fy = map(float, noise.get('baseFrequency').split())
            self.assertEqual(fx < fy, lower_axis == 0)
        colored = run(None, '--id=logo', '--geometry=none', '--grain=true', '--grain_monochrome=false')
        self.assertFalse(filters(colored)[0].xpath('./svg:feColorMatrix[@type="saturate"]', namespaces=inkex.NSS))

    def test_grain_blend_modes_replace_surface_once_and_keep_all_graph_inputs_valid(self):
        for mode in CHOICES['grain_blend']:
            ex = run(None, '--id=logo', '--grain=true', '--grain_blend=' + mode, '--shadow=true', '--glow=true', '--outline=true')
            seen = {'SourceGraphic', 'SourceAlpha'}
            graph = filters(ex)[0]
            self.assertEqual(graph.find(inkex.addNS('feBlend', 'svg')).get('mode'), mode)
            for node in graph:
                for child in [node, *node]:
                    for key in ('in', 'in2'):
                        if child.get(key): self.assertIn(child.get(key), seen)
                seen.add(node.get('result'))
            merge = graph.xpath('./svg:feMerge/svg:feMergeNode', namespaces=inkex.NSS)
            self.assertEqual(len(merge), 4)
            self.assertFalse(any(node.get('in') == 'SourceGraphic' for node in merge))

    def test_grain_refresh_saves_parameters_and_release_removes_filter(self):
        ex = run(None, '--id=logo', '--geometry=none', '--grain=true', '--grain_seed=32', '--grain_type=stippled')
        refreshed = manage(ex, 'refresh')
        self.assertEqual(len(filters(refreshed)), 1)
        saved = json.loads(wrappers(refreshed)[0].get(SETTINGS))
        self.assertEqual(saved['grain_seed'], 32)
        self.assertEqual(saved['grain_type'], 'stippled')
        self.assertEqual(filters(refreshed)[0].find(inkex.addNS('feTurbulence', 'svg')).get('seed'), '32')
        self.assertEqual(filters(manage(refreshed, 'release')), [])

    def test_legacy_settings_without_grain_refresh_with_grain_disabled(self):
        ex = run()
        settings = json.loads(wrappers(ex)[0].get(SETTINGS))
        settings = {key: value for key, value in settings.items() if not key.startswith('grain')}
        wrappers(ex)[0].set(SETTINGS, json.dumps(settings))
        refreshed = manage(ex, 'refresh')
        self.assertFalse(json.loads(wrappers(refreshed)[0].get(SETTINGS))['grain'])
        self.assertEqual(filters(refreshed), [])

    def test_gradient_sources_keep_native_paint_transforms_and_unique_internal_ids(self):
        source = document('<g id="logo" transform="translate(100,100) rotate(25)"><defs>'
                          '<linearGradient id="internal"><stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient>'
                          '</defs><rect id="part" width="200" height="80" fill="url(#internal)"/></g>')
        before = etree.tostring(load(source).svg.getElementById('logo'))
        ex = run(source, '--id=logo', '--geometry=none', '--grain=true')
        self.assertEqual(etree.tostring(ex.svg.getElementById('logo')), before)
        self.assertEqual(artwork(ex).get('data-vep-native-paint'), 'true')
        self.assertEqual(len(ex.svg.xpath('//svg:linearGradient', namespaces=inkex.NSS)), 2)
        ids = [el.get('id') for el in ex.svg.iter() if el.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        cloned_shape = artwork(ex).xpath('.//svg:rect', namespaces=inkex.NSS)[0]
        reference = cloned_shape.style['fill'][5:-1]
        self.assertNotEqual(reference, 'internal')
        self.assertIsNotNone(ex.svg.getElementById(reference))
        actual = cloned_shape.path.transform(composed(cloned_shape, ex.svg)).bounding_box()
        original = ex.svg.getElementById('part')
        expected = original.path.transform(composed(original, ex.svg)).bounding_box()
        self.assertAlmostEqual(actual.center_x, expected.center_x, places=3)
        self.assertAlmostEqual(actual.center_y, expected.center_y, places=3)
        released = manage(ex, 'release')
        self.assertEqual(etree.tostring(released.svg.getElementById('logo')), before)

    def test_gradients_require_appearance_only_and_invalid_grain_values_are_atomic(self):
        source = document('<defs><radialGradient id="g"><stop offset="0" stop-color="red"/></radialGradient></defs>'
                          '<rect id="logo" width="100" height="40" fill="url(#g)"/>')
        ex = load(source, '--id=logo', '--geometry=arc', '--grain=true')
        before = serialized(ex)
        with self.assertRaisesRegex(inkex.AbortExtension, 'Shape=None'): ex.effect()
        self.assertEqual(serialized(ex), before)
        for option in ['--grain_size=0', '--grain_intensity=101', '--grain_contrast=nan', '--grain_seed=-1']:
            ex = load(None, '--id=logo', '--geometry=none', '--grain=true', option)
            before = serialized(ex)
            with self.assertRaises(inkex.AbortExtension): ex.effect()
            self.assertEqual(serialized(ex), before)

    def test_grain_shortcut_enables_grain_without_geometry(self):
        tree = etree.parse(str(ROOT / 'vector_effects_grain.inx'))
        arguments = []
        for param in tree.xpath('//*[local-name()="param"]'):
            value = param[0].get('value') if param.get('type') == 'optiongroup' else param.text or ''
            arguments.append('--' + param.get('name') + '=' + value)
        ex = run(None, '--id=logo', *arguments)
        saved = json.loads(wrappers(ex)[0].get(SETTINGS))
        self.assertTrue(saved['grain'])
        self.assertEqual(saved['geometry'], 'none')
        self.assertFalse(any(saved[key] for key in ['shadow', 'glow', 'outline']))

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_grain_gradient_svg_survives_native_save_refresh_and_release(self):
        source = document('<defs><linearGradient id="g"><stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs>'
                          '<g id="logo" transform="rotate(15,200,100)"><rect id="part" x="100" y="50" width="200" height="100" fill="url(#g)"/></g>')
        ex = run(source, '--id=logo', '--geometry=none', '--grain=true', '--grain_type=enlarged')
        with tempfile.TemporaryDirectory() as td:
            path, saved = Path(td) / 'grain.svg', Path(td) / 'saved.svg'
            path.write_bytes(serialized(ex))
            proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(path), '--export-type=svg', '--export-filename=' + str(saved)],
                                  capture_output=True, text=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(saved.is_file())
            reopened = load(saved.read_bytes())
            refreshed = manage(reopened, 'refresh')
            self.assertEqual(len(filters(refreshed)), 1)
            self.assertTrue(filters(refreshed)[0].xpath('./svg:feTurbulence', namespaces=inkex.NSS))
            released = manage(refreshed, 'release')
            self.assertEqual(filters(released), [])
            self.assertIsNotNone(released.svg.getElementById('g'))
            self.assertEqual(released.svg.getElementById('part').get('fill'), 'url(#g)')

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_grain_pixels_are_repeatable_preserve_alpha_and_respond_to_controls(self):
        from PIL import Image, ImageChops, ImageStat
        source = document('<g id="logo" opacity="0.45"><defs><linearGradient id="g">'
                          '<stop offset="0" stop-color="#635bff"/><stop offset="1" stop-color="#ff744f"/>'
                          '</linearGradient></defs><path d="M20,20 H180 V120 H20 Z M80,50 H120 V90 H80 Z" fill="url(#g)" fill-rule="evenodd"/></g>',
                          viewport='width="200" height="140" viewBox="0 0 200 140"')
        with tempfile.TemporaryDirectory() as td:
            def render(name, data):
                svg, png = Path(td) / (name + '.svg'), Path(td) / (name + '.png')
                svg.write_bytes(data)
                proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(svg), '--export-type=png', '--export-width=200',
                                       '--export-background-opacity=0', '--export-filename=' + str(png)], capture_output=True, text=True, timeout=40)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(png.is_file())
                return Image.open(png).convert('RGBA')
            def texture(name, *options):
                ex = run(source, '--id=logo', '--geometry=none', '--grain=true', '--grain_blend=normal', *options)
                return render(name, serialized(ex))
            baseline = render('baseline', source)
            zero = texture('zero', '--grain_intensity=0')
            high = texture('high', '--grain_intensity=70', '--grain_contrast=60')
            repeated = texture('repeated', '--grain_intensity=70', '--grain_contrast=60')
            other_seed = texture('seed', '--grain_intensity=70', '--grain_contrast=60', '--grain_seed=29')
            low_contrast = texture('contrast', '--grain_intensity=70', '--grain_contrast=5')
            low_intensity = texture('intensity', '--grain_intensity=15', '--grain_contrast=60')
            self.assertEqual(ImageChops.difference(baseline, zero).getextrema(), ((0,0),) * 4)
            self.assertEqual(ImageChops.difference(high, repeated).getextrema(), ((0,0),) * 4)
            self.assertIsNotNone(ImageChops.difference(high.convert('RGB'), other_seed.convert('RGB')).getbbox())
            alpha_error = ImageChops.difference(baseline.getchannel('A'), high.getchannel('A'))
            self.assertLessEqual(alpha_error.getextrema()[1], 1)
            self.assertEqual(high.getpixel((100,70))[3], 0)
            self.assertEqual(high.getpixel((5,5))[3], 0)
            def variation(image):
                return ImageStat.Stat(image.crop((25,25,70,115)).getchannel('R')).stddev[0]
            self.assertGreater(variation(high), 4)
            self.assertGreater(variation(high), variation(low_contrast))
            self.assertGreater(variation(high), variation(low_intensity))

    def test_noise_modes_combine_with_other_appearance_effects_and_preserve_source(self):
        before = etree.tostring(load().svg.getElementById('logo'))
        for mode in CHOICES['noise_type']:
            for flags in itertools.product((False, True), repeat=4):
                names = ['grain', 'shadow', 'glow', 'outline']
                with self.subTest(mode=mode, flags=flags):
                    ex = run(None, '--id=logo', '--geometry=none', '--noise=true', '--noise_type=' + mode,
                             *['--' + k + '=' + str(v).lower() for k, v in zip(names, flags)])
                    graph = filters(ex)[0]
                    self.assertEqual(etree.tostring(ex.svg.getElementById('logo')), before)
                    self.assertFalse(ex.svg.xpath('//svg:image', namespaces=inkex.NSS))
                    self.assertEqual(len(graph.xpath('./svg:feTurbulence', namespaces=inkex.NSS)), 1+flags[0])
                    seen = {'SourceGraphic', 'SourceAlpha'}
                    for node in graph:
                        for child in [node, *node]:
                            for key in ('in', 'in2'):
                                if child.get(key): self.assertIn(child.get(key), seen)
                        self.assertNotIn(node.get('result'), seen)
                        seen.add(node.get('result'))
                    merge = graph.xpath('./svg:feMerge/svg:feMergeNode', namespaces=inkex.NSS)
                    self.assertEqual(len(merge), 1+sum(flags[1:]))
                    self.assertFalse(any(n.get('in') == 'SourceGraphic' for n in merge))

    def test_noise_zero_amount_and_zero_impulse_density_bypass_texture(self):
        for mode in CHOICES['noise_type']:
            ex = run(None, '--id=logo', '--geometry=none', '--noise=true', '--noise_type=' + mode, '--noise_amount=0')
            self.assertFalse(filters(ex)[0].xpath('./svg:feTurbulence', namespaces=inkex.NSS))
        ex = run(None, '--id=logo', '--geometry=none', '--noise=true', '--noise_type=salt_pepper', '--noise_density=0')
        self.assertFalse(filters(ex)[0].xpath('./svg:feTurbulence', namespaces=inkex.NSS))
        ex = run(None, '--id=logo', '--geometry=none', '--grain=true', '--noise=true', '--noise_amount=0')
        self.assertEqual(len(filters(ex)[0].xpath('./svg:feTurbulence', namespaces=inkex.NSS)), 1)

    def test_noise_size_uses_document_px_and_color_switch_is_independent(self):
        frequencies = []
        for viewport in ['width="800" height="600" viewBox="0 0 800 600"',
                         'width="800" height="600" viewBox="0 0 80 60"']:
            ex = run(document(viewport=viewport), '--id=logo', '--geometry=none', '--noise=true', '--noise_size=2')
            frequencies.append(float(filters(ex)[0].find(inkex.addNS('feTurbulence', 'svg')).get('baseFrequency')))
        self.assertAlmostEqual(frequencies[1], 10*frequencies[0])
        for monochrome in (False, True):
            ex = run(None, '--id=logo', '--geometry=none', '--noise=true', '--noise_monochrome=' + str(monochrome).lower())
            self.assertEqual(bool(filters(ex)[0].xpath('./svg:feColorMatrix[@type="saturate"]', namespaces=inkex.NSS)), monochrome)

    def test_noise_refresh_release_and_legacy_settings(self):
        before = etree.tostring(load().svg.getElementById('logo'))
        ex = run(None, '--id=logo', '--geometry=none', '--noise=true', '--noise_type=salt_pepper',
                 '--noise_seed=71', '--noise_density=62', '--noise_monochrome=false', '--noise_amount=44', '--noise_size=2')
        refreshed = manage(ex, 'refresh')
        settings = json.loads(wrappers(refreshed)[0].get(SETTINGS))
        self.assertEqual([settings[k] for k in ['noise', 'noise_type', 'noise_seed', 'noise_density', 'noise_monochrome', 'noise_amount', 'noise_size']],
                         [True, 'salt_pepper', 71, 62, False, 44, 2])
        self.assertEqual(filters(refreshed)[0].find(inkex.addNS('feTurbulence', 'svg')).get('seed'), '71')
        released = manage(refreshed, 'release')
        self.assertEqual(filters(released), [])
        self.assertEqual(etree.tostring(released.svg.getElementById('logo')), before)
        old = run(None, '--id=logo', '--geometry=none', '--grain=true')
        saved = {k:v for k,v in json.loads(wrappers(old)[0].get(SETTINGS)).items() if not k.startswith('noise')}
        wrappers(old)[0].set(SETTINGS, json.dumps(saved))
        self.assertFalse(json.loads(wrappers(manage(old, 'refresh'))[0].get(SETTINGS))['noise'])

    def test_invalid_noise_values_leave_document_unchanged(self):
        for option in ['--noise_amount=-1', '--noise_amount=nan', '--noise_size=0', '--noise_size=101',
                       '--noise_density=101', '--noise_seed=-1', '--noise_seed=2147483648']:
            ex = load(None, '--id=logo', '--geometry=none', '--noise=true', option)
            before = serialized(ex)
            with self.assertRaises(inkex.AbortExtension): ex.effect()
            self.assertEqual(serialized(ex), before)

    def test_noise_shortcut_enables_only_noise_and_has_live_preview(self):
        tree = etree.parse(str(ROOT / 'vector_effects_noise.inx'))
        self.assertEqual(tree.xpath('//*[local-name()="effect"]')[0].get('needs-live-preview'), 'true')
        arguments = []
        for param in tree.xpath('//*[local-name()="param"]'):
            value = param[0].get('value') if param.get('type') == 'optiongroup' else param.text or ''
            arguments.append('--' + param.get('name') + '=' + value)
        ex = run(None, '--id=logo', *arguments)
        saved = json.loads(wrappers(ex)[0].get(SETTINGS))
        self.assertTrue(saved['noise'])
        self.assertEqual(saved['geometry'], 'none')
        self.assertFalse(any(saved[k] for k in ['grain', 'shadow', 'glow', 'outline']))

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_noise_gradient_native_save_edit_refresh_and_release(self):
        source = document('<defs><radialGradient id="g"><stop offset="0" stop-color="white"/><stop offset="1" stop-color="#635bff"/></radialGradient></defs>'
                          '<g id="logo" transform="rotate(15,200,100)"><rect id="part" x="100" y="50" width="200" height="100" fill="url(#g)"/></g>')
        ex = run(source, '--id=logo', '--geometry=none', '--noise=true', '--noise_seed=17', '--grain=true')
        with tempfile.TemporaryDirectory() as td:
            path, saved = Path(td) / 'noise.svg', Path(td) / 'saved.svg'
            path.write_bytes(serialized(ex))
            proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(path), '--export-type=svg', '--export-filename=' + str(saved)],
                                  capture_output=True, text=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            edited = manage(load(saved.read_bytes()), 'edit')
            edited.svg.getElementById('part').set('width', '230')
            refreshed = manage(edited, 'refresh')
            settings = json.loads(wrappers(refreshed)[0].get(SETTINGS))
            self.assertTrue(settings['noise'] and settings['grain'])
            self.assertEqual(settings['noise_seed'], 17)
            self.assertEqual(len(filters(refreshed)[0].xpath('./svg:feTurbulence', namespaces=inkex.NSS)), 2)
            released = manage(refreshed, 'release')
            self.assertEqual(released.svg.getElementById('part').get('width'), '230')
            self.assertEqual(released.svg.getElementById('part').get('fill'), 'url(#g)')
            self.assertEqual(filters(released), [])

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_noise_pixels_modes_seed_amount_color_density_and_alpha(self):
        from PIL import Image, ImageChops, ImageStat
        source = document('<g id="logo" opacity="0.45"><defs><linearGradient id="g">'
                          '<stop offset="0" stop-color="#777777"/><stop offset="1" stop-color="#aaaaaa"/>'
                          '</linearGradient></defs><path d="M20,20 H180 V120 H20 Z M80,50 H120 V90 H80 Z" fill="url(#g)" fill-rule="evenodd"/></g>',
                          viewport='width="200" height="140" viewBox="0 0 200 140"')
        with tempfile.TemporaryDirectory() as td:
            def render(name, data):
                svg, png = Path(td) / (name + '.svg'), Path(td) / (name + '.png')
                svg.write_bytes(data)
                proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(svg), '--export-type=png', '--export-width=200',
                                       '--export-background-opacity=0', '--export-filename=' + str(png)], capture_output=True, text=True, timeout=40)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                with Image.open(png) as img: return img.convert('RGBA')
            def texture(name, *options):
                ex = run(source, '--id=logo', '--geometry=none', '--noise=true', *options)
                return render(name, serialized(ex))
            def variation(image):
                return ImageStat.Stat(image.crop((25,25,70,115)).getchannel('R')).stddev[0]
            baseline = render('baseline', source)
            for mode in CHOICES['noise_type']:
                with self.subTest(mode=mode):
                    params = ['--noise_type=' + mode, '--noise_amount=80', '--noise_density=65']
                    zero = texture(mode+'zero', '--noise_type='+mode, '--noise_amount=0')
                    high = texture(mode+'high', *params)
                    repeated = texture(mode+'repeat', *params)
                    other_seed = texture(mode+'seed', *params, '--noise_seed=29')
                    low = texture(mode+'low', *params, '--noise_amount=10')
                    colored = texture(mode+'colored', *params, '--noise_monochrome=false')
                    self.assertEqual(ImageChops.difference(baseline, zero).getextrema(), ((0,0),)*4)
                    self.assertEqual(ImageChops.difference(high, repeated).getextrema(), ((0,0),)*4)
                    self.assertIsNotNone(ImageChops.difference(high.convert('RGB'), other_seed.convert('RGB')).getbbox())
                    self.assertGreater(variation(high), variation(low))
                    self.assertLessEqual(ImageChops.difference(baseline.getchannel('A'), high.getchannel('A')).getextrema()[1], 1)
                    self.assertEqual(high.getpixel((100,70))[3], 0)
                    self.assertEqual(high.getpixel((5,5))[3], 0)
                    self.assertIsNone(ImageChops.difference(high.getchannel('R'), high.getchannel('G')).getbbox())
                    self.assertIsNotNone(ImageChops.difference(colored.getchannel('R'), colored.getchannel('G')).getbbox())
            sparse = texture('sparse', '--noise_type=salt_pepper', '--noise_amount=100', '--noise_density=5')
            dense = texture('dense', '--noise_type=salt_pepper', '--noise_amount=100', '--noise_density=80')
            self.assertGreater(variation(dense), variation(sparse))
            no_spots = texture('none', '--noise_type=salt_pepper', '--noise_density=0')
            self.assertEqual(ImageChops.difference(baseline, no_spots).getextrema(), ((0,0),)*4)

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_noise_additive_changes_black_and_white_but_speckle_preserves_black(self):
        from PIL import Image, ImageStat
        source = document('<g id="logo"><rect width="100" height="80" fill="black"/>'
                          '<rect x="100" width="100" height="80" fill="white"/></g>',
                          viewport='width="200" height="80" viewBox="0 0 200 80"')
        with tempfile.TemporaryDirectory() as td:
            for mode in ['additive', 'speckle']:
                ex = run(source, '--id=logo', '--geometry=none', '--noise=true', '--noise_type='+mode, '--noise_amount=80')
                svg, png = Path(td)/(mode+'.svg'), Path(td)/(mode+'.png')
                svg.write_bytes(serialized(ex))
                proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(svg), '--export-type=png', '--export-filename='+str(png)],
                                      capture_output=True, text=True, timeout=40)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                with Image.open(png) as img:
                    black = ImageStat.Stat(img.convert('RGB').crop((5,5,95,75))).mean[0]
                    white = ImageStat.Stat(img.convert('RGB').crop((105,5,195,75))).mean[0]
                self.assertGreater(white, 128)
                self.assertLess(white, 254)
                if mode == 'additive': self.assertGreater(black, 1)
                else: self.assertEqual(black, 0)

    def test_extension_protocol_writes_valid_svg_and_unique_ids(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'input.svg'; source.write_bytes(document())
            bootstrap = ('import sys,runpy;sys.path=' + repr(sys.path) + ';sys.argv[0]=' +
                         repr(str(ROOT / 'vector_effects_pro.py')) + ';runpy.run_path(sys.argv[0],run_name="__main__")')
            proc = subprocess.run([sys.executable, '-c', bootstrap, str(source), '--id=logo', '--shadow=true', '--glow=true'],
                                  capture_output=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())
            ex = load(proc.stdout)
            ids = [el.get('id') for el in ex.svg.iter() if el.get('id')]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(len(filters(ex)), 1)

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires real Inkscape CLI')
    def test_inkscape_save_reopen_edit_refresh_and_release(self):
        with tempfile.TemporaryDirectory() as td:
            source, saved = Path(td) / 'effects.svg', Path(td) / 'saved.svg'
            ex = run(None, '--id=logo', '--geometry=arc', '--shadow=true', '--glow=true', '--outline=true')
            source.write_bytes(serialized(ex))
            proc = subprocess.run([os.environ['INKSCAPE_COMMAND'], str(source), '--export-type=svg', '--export-filename=' + str(saved)],
                                  capture_output=True, text=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(saved.is_file())
            reopened = load(saved.read_bytes())
            self.assertEqual(len(filters(reopened)), 1)
            edited = manage(reopened, 'edit')
            edited.svg.getElementById('part').set('fill', '#ff744f')
            refreshed = manage(edited, 'refresh')
            self.assertEqual(artwork(refreshed)[0].style['fill'], '#ff744f')
            self.assertEqual(len(filters(refreshed)), 1)
            released = manage(refreshed, 'release')
            self.assertEqual(filters(released), [])
            self.assertEqual(released.svg.getElementById('part').get('fill'), '#ff744f')


if __name__ == '__main__':
    unittest.main()
