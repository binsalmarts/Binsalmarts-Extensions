import io
import itertools
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import inkex
from lxml import etree

from logo_construction import LogoConstruction, MARKER, REFERENCE, color, ratio_label, document_transform

ROOT = Path(__file__).resolve().parents[1]


def document(body=None, extra="", viewport='width="1000" height="700" viewBox="0 0 1000 700"'):
    if body is None:
        body = ('<g id="logo" transform="translate(100,100)">'
                '<path id="ref" d="M0,0 H100 V100 H0 Z"/>'
                '<rect id="part-b" x="125" width="80" height="100"/>'
                '<rect id="part-c" x="225" width="100" height="100"/></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:inkscape="{inkex.NSS["inkscape"]}" {viewport} {extra}>{body}</svg>').encode()


def load(source=None, *args):
    ex = LogoConstruction()
    ex.options = ex.arg_parser.parse_args(args or ['--id=logo', '--reference_id=ref'])
    ex.load(io.BytesIO(source if source is not None else document()))
    return ex


def run(source=None, *args):
    ex = load(source, *args)
    ex.effect()
    return ex


def layer(ex, role="diagram"):
    return next(e for e in ex.svg if e.get(MARKER) and e.get("data-lc-role") == role)


def roles(ex):
    return {e.get("data-lc-role") for e in layer(ex) if e.get("data-lc-role")}


def measurements(ex, kind=None):
    return [e for e in layer(ex).iterdescendants() if e.get("data-lc-role") == "dimension"
            and (kind is None or e.get("data-lc-kind") == kind)]


class ConstructionTests(unittest.TestCase):
    def test_real_ratios_and_unmodified_original(self):
        before = etree.tostring(load().svg.getElementById("logo"))
        ex = run()
        self.assertEqual(etree.tostring(ex.svg.getElementById("logo")), before)
        self.assertEqual(float(layer(ex).get("data-lc-unit")), 100)
        self.assertEqual({float(d.get("data-lc-ratio")) for d in measurements(ex, "gap")}, {.25, .2})
        labels = {t.text for t in layer(ex).iterdescendants() if isinstance(t, inkex.TextElement)}
        self.assertTrue({"1X", "0.25X", "0.2X", "3.25X"}.issubset(labels))
        self.assertEqual(layer(ex).get("inkscape:groupmode"), "layer")

    def test_source_style_and_transform_serialization_remain_exact(self):
        source = document('<g id="logo" style="fill: #24354b; opacity: 0.9" '
                          'transform="matrix(1.123456789,0,0,2.123456789,12.123456789,8.5)">'
                          '<path id="ref" style="stroke: none; fill-rule: evenodd" d="M0,0 H100 V50 H0 Z"/></g>')
        before = etree.tostring(load(source).svg.getElementById('logo'))
        ex = run(source)
        self.assertEqual(etree.tostring(ex.svg.getElementById('logo')), before)

    def test_percentage_geometry_and_anisotropic_root_fail_clearly(self):
        ex = load(document('<g id="logo"><rect id="ref" width="50%" height="10"/></g>'))
        with self.assertRaisesRegex(inkex.AbortExtension, 'Percentage'):
            ex.effect()
        ex = load(document(extra='preserveAspectRatio="none"',
                           viewport='width="1000" height="500" viewBox="0 0 100 100"'))
        with self.assertRaisesRegex(inkex.AbortExtension, 'Non-uniform'):
            ex.effect()

    def test_all_fifteen_independent_checkbox_combinations(self):
        names = ["alignment", "axes", "nodes", "dimensions"]
        for combination in itertools.product((False, True), repeat=4):
            if not any(combination):
                continue
            with self.subTest(combination=combination):
                args = ['--id=logo', '--reference_id=ref'] + [f'--show_{n}={str(v).lower()}' for n, v in zip(names, combination)]
                self.assertEqual(roles(run(None, *args)), {n for n, v in zip(names, combination) if v})

    def test_axes_can_be_controlled_individually(self):
        ex = run(None, '--id=logo', '--reference_id=ref', '--horizontal_axis=false')
        axes = next(e for e in layer(ex) if e.get("data-lc-role") == "axes")
        self.assertEqual(len(axes), 1)
        self.assertEqual(axes[0].get("x1"), axes[0].get("x2"))

    def test_nested_nonuniform_scale_skew_and_rotation(self):
        body = ('<g id="parent" transform="translate(20,30) rotate(23) skewX(12)">'
                '<g id="logo" transform="scale(2,3)"><path id="ref" transform="translate(5,7)" '
                'd="M0,0 H100 V40 H0 Z"/></g></g>')
        ex = run(document(body))
        ref = ex.svg.getElementById("ref")
        transform = document_transform(ref, ex.svg)
        corners = [transform.apply_to_point(p) for p in [(0,0), (100,0), (100,40), (0,40)]]
        width = max(p.x for p in corners) - min(p.x for p in corners)
        self.assertAlmostEqual(float(layer(ex).get("data-lc-unit")), width, places=8)
        nodes = next(e for e in layer(ex) if e.get("data-lc-role") == "nodes")
        actual = {(round(float(n.get("x")) + 2, 7), round(float(n.get("y")) + 2, 7)) for n in nodes}
        self.assertEqual(actual, {(round(p.x, 7), round(p.y, 7)) for p in corners})

    def test_height_reference_and_saved_reference(self):
        saved = run(None, '--id=ref', '--mode=reference')
        self.assertEqual(saved.svg.get(REFERENCE), "ref")
        self.assertFalse(any(e.get(MARKER) for e in saved.svg))
        ex = run(etree.tostring(saved.svg), '--id=logo', '--reference_dimension=height')
        ref = measurements(ex, "reference")[0]
        self.assertEqual(ref.get("data-lc-axis"), "y")
        self.assertEqual(ref.get("data-lc-ratio"), "1")

    def test_transformed_bezier_uses_curve_extrema_not_control_bounds(self):
        ex = run(document('<g id="logo" transform="scale(2,3)"><path id="ref" '
                          'd="M0,0 C0,100 100,100 100,0"/></g>'),
                 '--id=logo', '--reference_id=ref', '--reference_dimension=height')
        # Cubic maximum y is 75, not 100; then scale by 3.
        self.assertEqual(float(layer(ex).get("data-lc-unit")), 225)

    def test_relative_arc_curve_nodes_and_closed_path_deduplication(self):
        ex = run(document('<g id="logo"><path id="ref" transform="translate(50,40)" '
                          'd="m0,0 h100 a20,20 0 0 1 20,20 v30 q-40,20 -80,0 z"/></g>'))
        shapes = ex.collect(ex.svg.getElementById("logo"))
        self.assertAlmostEqual(shapes[0].box.width, 120)
        nodes = next(e for e in layer(ex) if e.get("data-lc-role") == "nodes")
        self.assertEqual(len(nodes), 5)

    def test_physical_px_style_in_mm_viewbox_and_custom_appearance(self):
        source = document(viewport='width="1000px" height="700px" viewBox="0 0 250 175"')
        ex = run(source, '--id=logo', '--reference_id=ref', '--line_width=2', '--font_size=20',
                 '--node_size=8', '--alignment_color=4278190208', '--label_color=#ff3300',
                 '--node_shape=circle', '--font_family=serif', '--axis_style=dashed')
        alignment = next(e for e in layer(ex) if e.get("data-lc-role") == "alignment")
        self.assertEqual(float(alignment[0].style["stroke-width"]), .5)
        self.assertEqual(alignment[0].style["stroke"], '#ff0000')
        self.assertAlmostEqual(float(alignment[0].style['stroke-opacity']), 128/255)
        text = next(t for t in layer(ex).iterdescendants() if isinstance(t, inkex.TextElement))
        self.assertEqual(float(text.style["font-size"]), 5)
        self.assertEqual(text.style["font-family"], 'serif')

    def test_background_behind_artwork_and_keep_document_background(self):
        ex = run(None, '--id=logo', '--reference_id=ref', '--background=panel')
        self.assertEqual(ex.svg[0], layer(ex, 'background'))
        self.assertGreater(list(ex.svg).index(ex.svg.getElementById('logo')), 0)
        kept = run()
        self.assertFalse(any(e.get('data-lc-role') == 'background' for e in kept.svg))
        self.assertEqual(kept.svg.get('viewBox'), '0 0 1000 700')

    def test_replace_append_and_distinct_logos(self):
        ex = run(None, '--id=logo', '--reference_id=ref', '--background=panel')
        updated = run(etree.tostring(ex.svg), '--id=logo', '--reference_id=ref')
        self.assertEqual(len([e for e in updated.svg if e.get(MARKER)]), 1)
        appended = run(etree.tostring(updated.svg), '--id=logo', '--reference_id=ref', '--action=append')
        self.assertEqual(len([e for e in appended.svg if e.get(MARKER)]), 2)
        source = document('<g id="logo"><rect id="ref" width="100" height="50"/></g>'
                          '<g id="other"><rect id="other-ref" x="500" width="50" height="50"/></g>')
        first = run(source)
        second = run(etree.tostring(first.svg), '--id=other', '--reference_id=other-ref')
        self.assertEqual(len([e for e in second.svg if e.get(MARKER)]), 2)

    def test_save_reopen_editable_text_and_unique_ids(self):
        ex = run(None, '--id=logo', '--reference_id=ref', '--show_outlines=true')
        text = next(t for t in layer(ex).iterdescendants() if isinstance(t, inkex.TextElement))
        text.set('x', '777')
        text.text = 'CUSTOM 0.25X'
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'roundtrip.svg'
            etree.ElementTree(ex.svg).write(str(path))
            reopened = inkex.load_svg(str(path)).getroot()
        self.assertEqual(reopened.getElementById(text.get('id')).text, 'CUSTOM 0.25X')
        self.assertEqual(reopened.getElementById(text.get('id')).get('x'), '777')
        ids = [e.get('id') for e in reopened.iter() if e.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(reopened.xpath('//svg:image', namespaces=inkex.NSS))

    def test_precise_labels_and_nonzero_tiny_dimensions(self):
        self.assertEqual(ratio_label(25, 100, 3), '0.25X')
        self.assertEqual(ratio_label(20, 100, 3), '0.2X')
        self.assertEqual(ratio_label(.000001, 100, 3), '1e-08X')
        self.assertEqual(ratio_label(100, 100, 0), '1X')

    def test_overlapping_and_diagonal_components_do_not_invent_gaps(self):
        for body in ['<rect id="ref" width="100" height="100"/><rect x="50" width="100" height="100"/>',
                     '<rect id="ref" width="100" height="100"/><rect x="150" y="150" width="100" height="100"/>']:
            ex = run(document('<g id="logo">' + body + '</g>'))
            self.assertEqual(measurements(ex, 'gap'), [])

    def test_scope_choices_and_multiple_selection_no_double_count(self):
        body = ('<g id="logo"><g id="ref"><rect id="inner" width="100" height="50"/>'
                '<circle cx="20" cy="20" r="5"/></g><rect id="b" x="125" width="100" height="100"/></g>')
        counts = []
        for scope in ('selection', 'children', 'leaves'):
            ex = run(document(body), '--id=logo', '--id=inner', '--reference_id=ref',
                     '--component_scope=' + scope, '--measure_parts=true')
            counts.append(len(measurements(ex, 'part')))
        self.assertEqual(counts, [2, 4, 6])

    def test_hidden_objects_do_not_change_geometry(self):
        body = ('<g id="logo"><rect id="ref" width="100" height="50"/>'
                '<rect x="-9000" width="1" height="1" style="display:none"/></g>')
        ex = run(document(body))
        width = next(d for d in measurements(ex, 'overall') if d.get('data-lc-axis') == 'x')
        self.assertEqual(float(width.get('data-lc-value')), 100)

    def test_failure_cases_leave_document_unmodified(self):
        cases = [(document(), ['--id=logo']), (document(), []),
                 (document(), ['--id=logo', '--reference_id=missing']),
                 (document(), ['--id=logo', '--reference_id=ref', '--line_width=nan']),
                 (document(), ['--id=logo', '--reference_id=ref', '--node_color=invalid-color']),
                 (document(), ['--id=logo', '--reference_id=ref', '--show_alignment=false',
                               '--show_axes=false', '--show_nodes=false', '--show_dimensions=false']),
                 (document('<g id="logo"><path id="ref" d="M0,0 V100"/></g>'),
                  ['--id=logo', '--reference_id=ref']),
                 (document('<g id="logo"><text id="ref">Logo</text></g>'),
                  ['--id=logo', '--reference_id=ref']),
                 (document('<g id="logo"><rect id="ref" width="10" height="10"/></g>'
                           '<rect id="outside" width="100" height="100"/>'),
                  ['--id=logo', '--reference_id=outside'])]
        for source, args in cases:
            with self.subTest(args=args):
                ex = load(source, *(args or ['--reference_id=ref']))
                before = etree.tostring(ex.svg)
                with self.assertRaises(inkex.AbortExtension):
                    ex.effect()
                self.assertEqual(etree.tostring(ex.svg), before)

    def test_unsupported_effects_and_clones_fail_clearly(self):
        for attr in ['clip-path="url(#clip)"', 'mask="url(#mask)"', 'filter="url(#filter)"']:
            ex = load(document(f'<g id="logo" {attr}><rect id="ref" width="100" height="100"/></g>'))
            with self.assertRaisesRegex(inkex.AbortExtension, 'Clips'):
                ex.effect()
        ex = load(document('<g id="logo"><use id="ref" href="#original"/></g>'
                           '<rect id="original" width="100" height="100"/>'))
        with self.assertRaisesRegex(inkex.AbortExtension, 'unlink'):
            ex.effect()

    def test_arrow_bar_and_outline_variants(self):
        for style in ('arrows', 'bar', 'ticks'):
            ex = run(None, '--id=logo', '--reference_id=ref', '--dimension_style=' + style,
                     '--show_outlines=true', '--node_shape=circle')
            self.assertIn('outlines', roles(ex))
            self.assertTrue(measurements(ex))

    def test_inx_schema_and_parser_defaults_match(self):
        schema = etree.RelaxNG(etree.parse(str(Path(inkex.__file__).parent / 'tester/inkscape.extension.rng')))
        defaults = vars(LogoConstruction().arg_parser.parse_args([]))
        for filename in ['logo_construction.inx', 'logo_construction_reference.inx']:
            tree = etree.parse(str(ROOT / filename))
            self.assertTrue(schema.validate(tree), str(schema.error_log))
            for param in tree.xpath('//*[local-name()="param"]'):
                name, kind = param.get('name'), param.get('type')
                if kind == 'notebook' or name == 'mode':
                    continue
                value = param.text or ''
                if kind == 'optiongroup':
                    value = param[0].get('value')
                if kind == 'color':
                    self.assertEqual(color(defaults[name], 'fill'), color(value, 'fill'), name)
                elif kind == 'bool':
                    self.assertEqual(defaults[name], value == 'true', name)
                elif kind in ('int', 'float'):
                    self.assertEqual(defaults[name], float(value), name)
                else:
                    self.assertEqual(defaults[name], value, name)

    def test_extension_entrypoint_reads_selection_and_writes_svg_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            source_path = Path(td) / 'source.svg'
            source_path.write_bytes(document())
            bootstrap = ('import sys,runpy; sys.path=' + repr(sys.path) + '; '
                         'sys.argv[0]=' + repr(str(ROOT / 'logo_construction.py')) + '; '
                         'runpy.run_path(sys.argv[0],run_name="__main__")')
            completed = subprocess.run([sys.executable, '-c', bootstrap, str(source_path),
                                        '--id=logo', '--reference_id=ref', '--tab=appearance'],
                                       capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            svg = inkex.load_svg(io.BytesIO(completed.stdout)).getroot()
            self.assertTrue(svg.xpath('//svg:text[text()="0.25X"]', namespaces=inkex.NSS))
            self.assertEqual(svg.getElementById('logo').attrib['transform'], 'translate(100,100)')

    @unittest.skipUnless(os.environ.get('INKSCAPE_COMMAND'), 'Requires Inkscape CLI')
    def test_inkscape_opens_saves_svg_and_preserves_editable_text(self):
        command = os.environ['INKSCAPE_COMMAND']
        with tempfile.TemporaryDirectory() as td:
            input_path, output_path = Path(td) / 'input.svg', Path(td) / 'saved.svg'
            etree.ElementTree(run().svg).write(str(input_path))
            result = subprocess.run([command, str(input_path), '--export-type=svg',
                                     '--export-plain-svg', '--export-filename=' + str(output_path)],
                                    capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output_path.is_file(), result.stderr)
            reopened = inkex.load_svg(str(output_path)).getroot()
            self.assertTrue(reopened.xpath('//svg:text[text()="0.25X"]', namespaces=inkex.NSS))
            self.assertTrue(reopened.getElementById('ref').get('d'))


if __name__ == '__main__':
    unittest.main()
