import io
import os
from pathlib import Path
import tempfile
import unittest

import inkex
from lxml import etree

from artboard_maker_pro import (ACTIVE_BATCH, BATCH, MARKER, PRESETS, UNITS,
                               ArtboardMakerPro, parse_sizes)

ROOT = Path(__file__).resolve().parents[1]


def document(width="800px", height="600px", viewbox="0 0 800 600", pages="", extra="", namedview=True):
    metadata = (f'<sodipodi:namedview id="namedview"><sodipodi:guide position="10,20" orientation="0,1"/>'
                f'{pages}</sodipodi:namedview>') if namedview else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS["inkscape"]}" '
            f'xmlns:sodipodi="{inkex.NSS["sodipodi"]}" width="{width}" height="{height}" '
            f'viewBox="{viewbox}" {extra}>{metadata}'
            '<g id="artwork" transform="translate(20,30) scale(2)">'
            '<rect id="design" x="10" y="10" width="30" height="40" fill="#2563eb"/></g></svg>').encode()


def load(source=None, *args):
    extension = ArtboardMakerPro()
    extension.options = extension.arg_parser.parse_args(args)
    extension.load(io.BytesIO(document() if source is None else source))
    return extension


def convert(source=None, *args):
    extension = load(source, *args)
    extension.effect()
    return extension


def serialized(extension):
    return etree.tostring(extension.svg)


def pages(extension):
    nv = extension.svg.find(inkex.addNS("namedview", "sodipodi"))
    return nv.findall(inkex.addNS("page", "inkscape"))


def rectangles(extension):
    return [(p.x, p.y, p.width, p.height) for p in pages(extension)]


class ArtboardTests(unittest.TestCase):
    def test_new_document_creates_exact_grid_and_preserves_artwork_and_guides(self):
        before = load()
        artwork = etree.tostring(before.svg.getElementById("artwork"))
        extension = convert(None, "--width=200", "--height=100", "--gap_x=20", "--gap_y=30")
        self.assertEqual(rectangles(extension), [(0, 0, 200, 100), (220, 0, 200, 100), (440, 0, 200, 100),
                                                (0, 130, 200, 100), (220, 130, 200, 100), (440, 130, 200, 100)])
        self.assertEqual(extension.svg.get("width"), "200px")
        self.assertEqual(extension.svg.get("height"), "100px")
        self.assertEqual(extension.svg.get_viewbox(), [0, 0, 200, 100])
        self.assertEqual(etree.tostring(extension.svg.getElementById("artwork")), artwork)
        self.assertEqual(len(extension.svg.findall(".//" + inkex.addNS("guide", "sodipodi"))), 1)
        self.assertEqual([p.get("inkscape:label") for p in pages(extension)],
                         ["Artboard " + str(i) for i in range(1, 7)])

    def test_without_names_supports_all_page_actions_and_ignores_the_prefix(self):
        native = '<inkscape:page id="original" x="0" y="0" width="800" height="600" inkscape:label="Design"/>'
        for action in ("update", "append", "replace_all"):
            for prefix in ("", "Unused", "\t"):
                with self.subTest(action=action, prefix=prefix):
                    extension = convert(document(pages=native), "--action=" + action,
                                        "--rows=1", "--columns=2", "--without_names=true",
                                        "--label_prefix=" + prefix)
                    generated = [p for p in pages(extension) if p.get(MARKER) == "page"]
                    self.assertEqual(len(generated), 2)
                    self.assertTrue(all(p.get("inkscape:label") is None for p in generated))
                    if action != "replace_all":
                        self.assertEqual(pages(extension)[0].get("inkscape:label"), "Design")

    def test_names_can_be_removed_and_restored_only_on_the_last_grid(self):
        first = convert(None, "--rows=1", "--columns=2", "--label_prefix=Keep")
        retained = [etree.tostring(p) for p in pages(first)]
        second = convert(serialized(first), "--action=append", "--rows=1", "--columns=2")
        identifiers = [p.get("id") for p in pages(second)[2:]]
        unnamed = convert(serialized(second), "--rows=1", "--columns=3", "--without_names=true")
        self.assertEqual([etree.tostring(p) for p in pages(unnamed)[:2]], retained)
        self.assertEqual([p.get("id") for p in pages(unnamed)[2:4]], identifiers)
        self.assertTrue(all(p.get("inkscape:label") is None for p in pages(unnamed)[2:]))
        restored = convert(serialized(unnamed), "--rows=1", "--columns=2", "--without_names=false",
                           "--label_prefix=لوحة")
        self.assertEqual([etree.tostring(p) for p in pages(restored)[:2]], retained)
        self.assertEqual([p.get("id") for p in pages(restored)[2:]], identifiers)
        self.assertEqual([p.get("inkscape:label") for p in pages(restored)[2:]], ["لوحة 1", "لوحة 2"])

    def test_mixed_sizes_repeat_and_tracks_keep_the_requested_minimum_gaps(self):
        extension = convert(None, "--size_mode=mixed", "--mixed_sizes=100x80; 200x120; 60x50",
                            "--rows=2", "--columns=3", "--gap_x=10", "--gap_y=20")
        self.assertEqual(rectangles(extension), [(0, 0, 100, 80), (110, 0, 200, 120), (320, 0, 60, 50),
                                                (0, 140, 100, 80), (110, 140, 200, 120), (320, 140, 60, 50)])

    def test_column_order_and_cell_alignment_use_maximum_track_sizes(self):
        extension = convert(None, "--size_mode=mixed", "--mixed_sizes=100x80; 200x120; 60x50",
                            "--rows=2", "--columns=2", "--order=columns", "--gap_x=10", "--gap_y=20",
                            "--cell_alignment=center")
        self.assertEqual(rectangles(extension), [(50, 0, 100, 80), (0, 100, 200, 120),
                                                (230, 15, 60, 50), (210, 120, 100, 80)])
        end = convert(None, "--size_mode=mixed", "--mixed_sizes=100x80; 200x120; 60x50",
                      "--rows=2", "--columns=2", "--order=columns", "--gap_x=10", "--gap_y=20",
                      "--cell_alignment=end")
        self.assertEqual(rectangles(end)[0], (100, 0, 100, 80))

    def test_all_presets_keep_physical_sizes_independently_of_custom_unit(self):
        for key, size in PRESETS.items():
            with self.subTest(preset=key):
                extension = convert(None, "--preset=" + key, "--rows=1", "--columns=1", "--unit=in")
                self.assertAlmostEqual(pages(extension)[0].width, size[0], places=7)
                self.assertAlmostEqual(pages(extension)[0].height, size[1], places=7)

    def test_mixed_units_and_presets_and_swapped_dimensions(self):
        sizes = parse_sizes("210x297mm; 8.5in x 11in\nA5; 10cm × 50mm; .5x1", "in")
        self.assertAlmostEqual(sizes[0][0], 210 * UNITS["mm"])
        self.assertEqual(sizes[1], PRESETS["letter"])
        self.assertEqual(sizes[2], PRESETS["a5"])
        self.assertAlmostEqual(sizes[3][0], 100 * UNITS["mm"])
        self.assertAlmostEqual(sizes[3][1], 50 * UNITS["mm"])
        self.assertEqual(sizes[4], (48, 96))
        extension = convert(None, "--size_mode=mixed", "--mixed_sizes=100x80; 200x120",
                            "--rows=1", "--columns=2", "--swap_dimensions=true")
        self.assertEqual([(p.width, p.height) for p in pages(extension)], [(80, 100), (120, 200)])

    def test_millimeter_document_uses_literal_pixel_gaps_and_preserves_scale(self):
        source = document("210mm", "297mm", "0 0 210 297")
        extension = convert(source, "--unit=mm", "--width=100", "--height=80", "--rows=1", "--columns=2",
                            "--gap_x=96")
        self.assertAlmostEqual(pages(extension)[0].width, 100)
        self.assertAlmostEqual(pages(extension)[0].height, 80)
        self.assertAlmostEqual(pages(extension)[1].x, 125.4)
        self.assertEqual(extension.svg.get("width"), "100mm")
        self.assertEqual(extension.svg.get("height"), "80mm")
        self.assertEqual(extension.svg.get_viewbox(), [0, 0, 100, 80])

    def test_nonzero_viewbox_and_nonuniform_scale_and_custom_position(self):
        extension = convert(document("800px", "600px", "20 30 400 200", extra='preserveAspectRatio="none"'),
                            "--width=200", "--height=90", "--rows=1", "--columns=2", "--gap_x=20",
                            "--position=custom", "--origin_x=-40", "--origin_y=60")
        self.assertEqual(rectangles(extension), [(-20, 20, 100, 30), (90, 20, 100, 30)])
        self.assertEqual(extension.svg.get_viewbox(), [20, 30, 100, 30])
        self.assertEqual(extension.svg.get("width"), "200px")
        self.assertEqual(extension.svg.get("height"), "90px")

    def test_update_keeps_ids_adds_and_removes_only_generated_pages(self):
        first = convert(None, "--width=200", "--height=100")
        ids = [p.get("id") for p in pages(first)]
        second = convert(serialized(first), "--width=300", "--height=150", "--rows=1", "--columns=2")
        self.assertEqual([p.get("id") for p in pages(second)], ids[:2])
        self.assertEqual(len(pages(second)), 2)
        self.assertEqual(second.svg.get("width"), "300px")
        third = convert(serialized(second), "--rows=2", "--columns=2")
        self.assertEqual([p.get("id") for p in pages(third)][:2], ids[:2])
        self.assertEqual(len(pages(third)), 4)
        all_ids = [e.get("id") for e in third.svg.iter() if e.get("id")]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_single_native_page_is_retained_and_new_grid_goes_to_its_right(self):
        native = '<inkscape:page id="original" x="100" y="-20" width="300" height="200" inkscape:label="Design"/>'
        extension = convert(document(pages=native), "--rows=1", "--columns=1", "--width=100", "--height=100", "--gap_x=25")
        self.assertEqual(rectangles(extension), [(100, -20, 300, 200), (425, -20, 100, 100)])
        self.assertEqual(pages(extension)[0].get("id"), "original")
        self.assertEqual(pages(extension)[0].get("inkscape:label"), "Design")
        self.assertEqual(extension.svg.get("width"), "800px")

    def test_append_preserves_implicit_page_and_update_targets_latest_batch(self):
        first = convert(None, "--action=append", "--rows=1", "--columns=2", "--width=100", "--height=100", "--gap_x=20")
        self.assertEqual(rectangles(first), [(0, 0, 800, 600), (820, 0, 100, 100), (940, 0, 100, 100)])
        old = [etree.tostring(p) for p in pages(first)]
        second = convert(serialized(first), "--action=append", "--rows=1", "--columns=1", "--width=200", "--height=150", "--gap_x=20")
        self.assertEqual(rectangles(second)[-1], (1060, 0, 200, 150))
        third = convert(serialized(second), "--rows=1", "--columns=2", "--width=50", "--height=50")
        self.assertEqual([etree.tostring(p) for p in pages(third)[:3]], old)
        self.assertEqual(rectangles(third)[3:], [(1060, 0, 50, 50), (1150, 0, 50, 50)])

    def test_replace_all_changes_only_page_definitions_and_keeps_namespaced_metadata(self):
        native = '<inkscape:page id="original" x="0" y="0" width="800" height="600"/>'
        first = load(document(pages=native))
        art = etree.tostring(first.svg.getElementById("artwork"))
        extension = convert(serialized(first), "--action=replace_all", "--rows=1", "--columns=1", "--label_prefix=صفحة")
        self.assertEqual(len(pages(extension)), 1)
        self.assertIsNone(extension.svg.getElementById("original"))
        self.assertEqual(pages(extension)[0].get("inkscape:label"), "صفحة 1")
        self.assertEqual(etree.tostring(extension.svg.getElementById("artwork")), art)

    def test_namedview_is_created_when_missing_and_zero_gaps_work(self):
        extension = convert(document(namedview=False), "--width=20", "--height=30", "--rows=1", "--columns=2", "--gap_x=0", "--gap_y=0")
        self.assertEqual(rectangles(extension), [(0, 0, 20, 30), (20, 0, 20, 30)])

    def test_generated_pages_work_with_numbering_and_modern_grid(self):
        from page_numbering_pro import PageNumberingPro, PAGE_KEY, number_content
        from modern_grid.modern_grid import ModernGrid
        maker = convert(None, "--rows=1", "--columns=3", "--size_mode=mixed",
                        "--mixed_sizes=300x200; 240x360; 400x200")
        identifiers = [p.get("id") for p in pages(maker)]
        grid = ModernGrid()
        grid.options = grid.arg_parser.parse_args(["--target=artboards", "--tab=grid"])
        grid.load(io.BytesIO(serialized(maker)))
        self.assertEqual(grid._get_artboard_rects(), rectangles(maker))
        grid.effect()
        numbering = PageNumberingPro()
        numbering.options = numbering.arg_parser.parse_args(["--minimum_digits=2"])
        numbering.load(io.BytesIO(etree.tostring(grid.svg)))
        numbering.effect()
        self.assertEqual([number_content(n) for n in numbering.existing_numbers()], ["01", "02", "03"])
        self.assertEqual([n.get(PAGE_KEY) for n in numbering.existing_numbers()], identifiers)
        changed = convert(etree.tostring(numbering.svg), "--rows=1", "--columns=3", "--width=500", "--height=300")
        numbering.load(io.BytesIO(serialized(changed)))
        numbering.effect()
        self.assertEqual([n.get(PAGE_KEY) for n in numbering.existing_numbers()], identifiers)
        self.assertEqual(len(numbering.existing_numbers()), 3)

    def test_invalid_options_and_sizes_fail_without_mutation(self):
        for args in (("--rows=0",), ("--columns=101",), ("--rows=100", "--columns=100"),
                     ("--gap_x=-1",), ("--gap_y=nan",), ("--width=0",), ("--height=inf",),
                     ("--unit=invalid",), ("--position=invalid",), ("--label_prefix=",), ("--label_prefix=Bad\tname",),
                     ("--size_mode=mixed", "--mixed_sizes="), ("--size_mode=mixed", "--mixed_sizes=0x100"),
                     ("--size_mode=mixed", "--mixed_sizes=A0"), ("--size_mode=mixed", "--mixed_sizes=100xNaN"),
                     ("--size_mode=mixed", "--rows=1", "--columns=1", "--mixed_sizes=100x100; 200x200")):
            with self.subTest(args=args):
                extension = load(None, *args)
                before = serialized(extension)
                with self.assertRaises(inkex.AbortExtension):
                    extension.effect()
                self.assertEqual(serialized(extension), before)

    def test_invalid_existing_page_and_unsupported_resize_scale_fail_before_mutation(self):
        for source in (document(pages='<inkscape:page x="0" y="0" width="-20" height="100"/>'),
                       document("800px", "600px", "0 0 400 200")):
            extension = load(source)
            before = serialized(extension)
            with self.assertRaises(inkex.AbortExtension):
                extension.effect()
            self.assertEqual(serialized(extension), before)

    def test_schema_and_ui_parameters_match_parser_defaults_and_shared_menu(self):
        tree = etree.parse(str(ROOT / "artboard_maker_pro.inx"))
        schema = Path(inkex.__file__).parent / "tester" / "inkscape.extension.rng"
        if schema.exists():
            etree.RelaxNG(etree.parse(str(schema))).assertValid(tree)
        args, names = [], []
        defaults = ArtboardMakerPro().arg_parser.parse_args([])
        for param in tree.findall(".//{*}param"):
            name = param.get("name")
            names.append(name)
            kind = param.get("type")
            value = param.find("{*}page").get("name") if kind == "notebook" else (
                param.find("{*}option").get("value") if kind == "optiongroup" else param.text)
            args.append(f"--{name}={value}")
        options = ArtboardMakerPro().arg_parser.parse_args(args)
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertEqual(getattr(options, name), getattr(defaults, name))
        self.assertEqual(tree.find(".//{*}submenu").get("name"), "Binsalmarts Extensions >")
        self.assertEqual(len(pages(convert(None, *args))), 6)

    @unittest.skipUnless(os.environ.get("INKSCAPE_COMMAND"), "Requires actual Inkscape renderer")
    def test_real_renderer_exports_native_mixed_pages_at_their_exact_sizes(self):
        from inkex.command import inkscape
        from PIL import Image
        # Start with a plain SVG, including no Inkscape namespaces or metadata.
        source = b'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600"/>'
        extension = convert(source, "--rows=1", "--columns=3", "--size_mode=mixed", "--mixed_sizes=200x100; 80x160; 120x90")
        with tempfile.TemporaryDirectory() as directory:
            filename = str(Path(directory, "mixed.svg"))
            Path(filename).write_bytes(serialized(extension))
            for index, expected in enumerate(((200, 100), (80, 160), (120, 90)), 1):
                output = str(Path(directory, f"page-{index}.png"))
                inkscape(filename, export_page=str(index), export_type="png", export_filename=output)
                with Image.open(output) as image:
                    self.assertEqual(image.size, expected)

    @unittest.skipUnless(os.environ.get("INKSCAPE_COMMAND"), "Requires actual Inkscape renderer")
    def test_real_renderer_preserves_artwork_size_and_position_after_canvas_resize(self):
        from inkex.command import inkscape
        for source in (document(), document("210mm", "297mm", "10 20 210 297"),
                       document("800px", "600px", "20 30 400 200", extra='preserveAspectRatio="none"')):
            extension = convert(source, "--rows=1", "--columns=1", "--width=400", "--height=500")
            with tempfile.TemporaryDirectory() as directory:
                boxes = []
                for index, content in enumerate((source, serialized(extension))):
                    filename = str(Path(directory, f"design-{index}.svg"))
                    Path(filename).write_bytes(content)
                    output = inkscape(filename, query_all=True)
                    row = next(r for r in output.splitlines() if r.startswith("design,"))
                    boxes.append([float(v) for v in row.split(",")[1:]])
                for actual, expected in zip(boxes[1], boxes[0]):
                    self.assertAlmostEqual(actual, expected, delta=0.001)
