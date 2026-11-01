import base64
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import inkex
from lxml import etree
from PIL import Image, ImageChops, ImageDraw

from ascii_art_pro import AsciiArtPro, analyze, character_sequence, map_characters, rgba_color


ROOT = Path(__file__).resolve().parents[1]
NS = inkex.NSS


def data_uri(image, format="PNG"):
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    return "data:image/" + format.lower() + ";base64," + base64.b64encode(buffer.getvalue()).decode()


def svg_source(image=None, href=None, image_attrs="", parent_attrs="", href_name="href"):
    href = href or data_uri(image or Image.new("RGB", (100, 60), "black"))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="{NS["xlink"]}" '
            f'xmlns:inkscape="{NS["inkscape"]}" width="200" height="100" viewBox="0 0 200 100">'
            f'<g id="parent" {parent_attrs}><image id="source" x="10" y="5" width="100" '
            f'height="60" {href_name}="{href}" {image_attrs}/></g></svg>').encode()


def convert(source=None, *args):
    extension = AsciiArtPro()
    extension.options = extension.arg_parser.parse_args(["--id=source", *args])
    extension.load(io.BytesIO(source or svg_source()))
    extension.effect()
    return extension


class MappingTests(unittest.TestCase):
    def test_extremes_and_single_inversion(self):
        gray = Image.new("L", (2, 1))
        gray.putdata([0, 255])
        alpha = Image.new("L", gray.size, 255)
        self.assertEqual(map_characters(gray, alpha, character_sequence("standard", "")), ["@", " "])
        self.assertEqual(map_characters(gray, alpha, character_sequence("standard", "", True)), [" ", "@"])

    def test_minimal_has_an_empty_highlight(self):
        gray = Image.new("L", (3, 1))
        gray.putdata([0, 127, 255])
        self.assertEqual(map_characters(gray, Image.new("L", gray.size, 255), "█ "), ["█", "█", " "])

    def test_transparency_does_not_become_a_dense_cell_on_invert(self):
        result, colors = analyze(Image.new("RGBA", (20, 20), (255, 0, 0, 0)),
                                 20, 10, 1, "none", (255, 255, 255, 0), 1, 1, False, False, " @")
        self.assertEqual(set(result), {" "})
        self.assertTrue(all(c[3] == 0 for c in colors))

    def test_rgb_is_average_of_original_pixels_despite_effects(self):
        image = Image.new("RGBA", (80, 40), (255, 0, 0, 255))
        ImageDraw.Draw(image).rectangle((40, 0, 79, 39), fill=(0, 0, 255, 255))
        _, colors = analyze(image, 1, 1, 2, "none", (255, 255, 255, 255), 3, 0.2, False, False, "@ ")
        self.assertAlmostEqual(colors[0][0], 128, delta=1)
        self.assertAlmostEqual(colors[0][2], 128, delta=1)
        self.assertEqual(colors[0][1], 0)

    def test_flat_white_has_no_false_edge_frame(self):
        chars, _ = analyze(Image.new("RGBA", (80, 80), "white"), 20, 10, 1,
                           "none", (255, 255, 255, 255), 1, 1, True, False, "@ ")
        self.assertEqual(set(chars), {" "})

    def test_edges_detect_shape_instead_of_flat_fill(self):
        image = Image.new("RGBA", (100, 100), "white")
        ImageDraw.Draw(image).rectangle((20, 20, 80, 80), fill="black")
        chars, _ = analyze(image, 20, 20, 1, "none", (255, 255, 255, 255), 1, 1, True, False, "@ ")
        self.assertEqual(chars[10 * 20 + 10], " ")
        self.assertGreater(chars.count("@"), 0)

    def test_color_picker_decimal_and_css(self):
        self.assertEqual(rgba_color("4278190208"), (255, 0, 0, 128))
        self.assertEqual(rgba_color("#abc"), (170, 187, 204, 255))

    def test_translucent_background_uses_white_page_for_luma(self):
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 64))
        chars, _ = analyze(image, 1, 1, 1, "none", (0, 0, 0, 0), 1, 1, False, False, "@ ")
        self.assertEqual(chars, [" "])

    def test_bad_custom_characters_report_errors(self):
        for sequence in ("", "   ", "x\ny", "\u064eب", "ب \u0651", "ب\u200dت", "x" * 257):
            with self.subTest(sequence=sequence), self.assertRaises(inkex.AbortExtension):
                character_sequence("custom", sequence)

    def test_arabic_letters_and_harakat_form_independent_symbols(self):
        self.assertEqual(character_sequence("custom", "شَمّبِ "), ("شَ", "مّ", "بِ", " "))
        self.assertEqual(character_sequence("custom", "شَمّبِ ", True), (" ", "بِ", "مّ", "شَ"))
        self.assertEqual(character_sequence("custom", "مرحبا"), tuple("مرحبا"))
        self.assertTrue(all(isinstance(symbol, str) for symbol in character_sequence("arabic", "")))


class ExtensionTests(unittest.TestCase):
    def test_embedded_png_and_jpeg_both_href_versions(self):
        for format in ("PNG", "JPEG"):
            for href_name in ("href", "xlink:href"):
                with self.subTest(format=format, href_name=href_name):
                    svg = convert(svg_source(href=data_uri(Image.new("RGB", (100, 60), "black"), format),
                                             href_name=href_name)).svg
                    group = svg.xpath('//*[@data-ascii-art-pro-version]')[0]
                    self.assertEqual(group.get("data-ascii-columns"), "80")
                    self.assertEqual(len(group.xpath(".//svg:text")), 24)
                    self.assertTrue(all(len("".join(t.itertext())) == 80 for t in group.xpath(".//svg:text")))

    def test_transform_and_parent_coordinate_system_are_preserved(self):
        source = svg_source(image_attrs='transform="rotate(25,60,35)"', parent_attrs='transform="translate(7,9) scale(2)"')
        extension = convert(source)
        group = extension.svg.xpath('//*[@data-ascii-art-pro-version]')[0]
        for actual, expected in zip(group.transform.to_hexad(), inkex.Transform("rotate(25,60,35)").to_hexad()):
            self.assertAlmostEqual(actual, expected, places=4)
        self.assertEqual(group.getparent().get("id"), "parent")
        clip = extension.svg.xpath("//svg:clipPath/svg:rect")[0]
        self.assertEqual(tuple(float(clip.get(k)) for k in ("x", "y", "width", "height")), (10, 5, 100, 60))

    def test_svg_units_do_not_apply_document_scale_twice(self):
        source = svg_source().replace(b'x="10" y="5" width="100" height="60"',
                                      b'x="1mm" y="2mm" width="10mm" height="6mm"')
        clip = convert(source).svg.xpath("//svg:clipPath/svg:rect")[0]
        self.assertAlmostEqual(float(clip.get("width")), 10 * 96 / 25.4, places=6)

    def test_percentages_use_viewbox_dimensions(self):
        source = svg_source().replace(b'x="10" y="5" width="100" height="60"',
                                      b'x="10%" y="5%" width="50%" height="60%"')
        clip = convert(source).svg.xpath("//svg:clipPath/svg:rect")[0]
        self.assertEqual(tuple(float(clip.get(k)) for k in ("x", "y", "width", "height")), (20, 5, 100, 60))

    def test_meet_letterboxing_and_slice_cropping(self):
        image = Image.new("RGBA", (60, 60), "black")
        letterbox = convert(svg_source(image=image, image_attrs='preserveAspectRatio="xMidYMid meet"'))
        row = letterbox.svg.xpath("//svg:text")[0]
        text = "".join(row.itertext())
        self.assertTrue(text.startswith(" " * 16))
        self.assertTrue(text.endswith(" " * 16))
        sliced = convert(svg_source(image=image, image_attrs='preserveAspectRatio="xMidYMid slice"'))
        self.assertEqual(set("".join(sliced.svg.xpath("//svg:text")[0].itertext())), {"@"})

    def test_hidden_preserved_source_attributes_are_unchanged(self):
        extension = convert(svg_source(image_attrs='transform="scale(2)" style="opacity:0.6"'))
        source = extension.svg.getElementById("source")
        self.assertEqual(source.transform.to_hexad(), inkex.Transform("scale(2)").to_hexad())
        self.assertEqual(source.get("style"), "opacity:0.6")
        self.assertEqual(source.getparent().get("inkscape:label"), "Original Image")
        self.assertEqual(source.getparent().style["display"], "none")
        output = extension.svg.xpath('//*[@data-ascii-art-pro-version]')[0]
        self.assertEqual(float(output.style["opacity"]), 0.6)

    def test_replace_and_overlay_do_not_depend_on_original(self):
        svg = convert(None, "--original_action=replace", "--overlay_original=true",
                      "--blur_strength=2", "--background=black").svg
        self.assertIsNone(svg.getElementById("source"))
        overlay = svg.xpath("//svg:image")[0]
        self.assertTrue(overlay.get("xlink:href").startswith("data:image/png;base64,"))
        self.assertEqual(len(svg.xpath("//svg:feGaussianBlur")), 1)
        self.assertEqual(float(overlay.style["opacity"]), 0.25)
        self.assertEqual(svg.xpath("//svg:filter")[0].get("filterUnits"), "userSpaceOnUse")

    def test_color_text_uses_one_row_with_spans_and_explicit_positions(self):
        image = Image.new("RGB", (100, 60), "red")
        ImageDraw.Draw(image).rectangle((50, 0, 99, 59), fill="blue")
        svg = convert(svg_source(image=image), "--original_colors=true").svg
        rows = svg.xpath("//svg:text")
        self.assertEqual(len(rows), 24)
        self.assertEqual(len(rows[0].get("x").split()), 80)
        self.assertLess(len(rows[0]), 6)
        self.assertEqual(rows[0][0].style["fill"], "#ff0000")
        self.assertEqual(rows[0][-1].style["fill"], "#0000ff")

    def test_quality_and_fixed_font_controls(self):
        group = convert(None, "--quality=high").svg.xpath('//*[@data-ascii-art-pro-version]')[0]
        self.assertEqual(group.get("data-ascii-columns"), "120")
        svg = convert(None, "--layout=font", "--font_size=10", "--font_scale=2").svg
        text = svg.xpath("//svg:text")[0]
        self.assertEqual(float(text.style["font-size"]), 20)
        self.assertAlmostEqual(float(text.get("x").split()[1]) - float(text.get("x").split()[0]), 12)

    def test_arabic_cells_keep_image_order_colors_and_diacritics(self):
        image = Image.new("RGB", (100, 60), "black")
        ImageDraw.Draw(image).rectangle((50, 0, 99, 59), fill="red")
        svg = convert(svg_source(image=image), "--sequence=custom", "--custom_characters=شَAبِ١",
                      "--columns=20", "--original_colors=true").svg
        row = svg.xpath("//svg:text")[0]
        self.assertEqual(len(svg.xpath("//svg:text")), 6)
        self.assertEqual(len(row), 20)
        self.assertEqual([span.text for span in row[:10]], ["شَ"] * 10)
        self.assertEqual([span.text for span in row[10:]], ["A"] * 10)
        self.assertEqual([float(span.get("x")) for span in row], [12.5 + col * 5 for col in range(20)])
        self.assertEqual(row[0].style["fill"], "#000000")
        self.assertEqual(row[-1].style["fill"], "#ff0000")
        self.assertEqual(row[0].style["direction"], "rtl")
        self.assertEqual(row[-1].style["direction"], "ltr")

    def test_validation_errors_are_in_english(self):
        with self.assertRaisesRegex(inkex.AbortExtension, "Columns"):
            convert(None, "--columns=501")
        with self.assertRaisesRegex(inkex.AbortExtension, "Custom characters"):
            convert(None, "--sequence=custom", "--custom_characters=")

    def test_bad_input_fails_before_mutating_document(self):
        for args, source in ((["--columns=501"], svg_source()),
                             (["--contrast=nan"], svg_source()),
                             ([], svg_source(href="data:image/png;base64,INVALID!")),
                             ([], svg_source(href="https://example.com/image.png")),
                             ([], svg_source().replace(b'height="60"', b'height="60000"'))):
            with self.subTest(args=args, source=source[:20]):
                extension = AsciiArtPro()
                extension.options = extension.arg_parser.parse_args(["--id=source", *args])
                extension.load(io.BytesIO(source))
                before = etree.tostring(extension.svg)
                with self.assertRaises(inkex.AbortExtension):
                    extension.effect()
                self.assertEqual(before, etree.tostring(extension.svg))

    def test_selection_requires_exactly_one_image(self):
        for ids in ([], ["parent"], ["source", "parent"]):
            extension = AsciiArtPro()
            extension.options = extension.arg_parser.parse_args([f"--id={i}" for i in ids])
            extension.load(io.BytesIO(svg_source()))
            with self.assertRaises(inkex.AbortExtension):
                extension.effect()

    def test_relative_link_uses_saved_document_path_not_temporary_svg(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, "linked image.png")
            Image.new("RGB", (100, 60), "black").save(image)
            with patch.dict(os.environ, {"DOCUMENT_PATH": str(Path(directory, "drawing.svg"))}):
                extension = convert(svg_source(href="linked%20image.png"))
            self.assertEqual(len(extension.svg.xpath("//svg:text")), 24)

    def test_unique_ids_are_reserved_before_document_commit(self):
        svg = convert(None, "--columns=500").svg
        ids = [n.get("id") for n in svg.iter() if n.get("id")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_failed_path_conversion_does_not_delete_original_or_add_defs(self):
        extension = AsciiArtPro()
        extension.options = extension.arg_parser.parse_args(["--id=source", "--convert_to_paths=true",
                                                           "--original_action=replace", "--overlay_original=true",
                                                           "--blur_strength=2"])
        extension.load(io.BytesIO(svg_source()))
        before = etree.tostring(extension.svg)
        with patch.object(extension, "to_paths", side_effect=inkex.AbortExtension("Renderer failed")):
            with self.assertRaises(inkex.AbortExtension):
                extension.effect()
        self.assertEqual(before, etree.tostring(extension.svg))

    @unittest.skipUnless(os.environ.get("INKSCAPE_COMMAND"), "Set INKSCAPE_COMMAND for renderer integration")
    def test_real_inkscape_paths_only_convert_generated_text(self):
        source = svg_source().replace(b'</g></svg>', b'<text id="other" x="2" y="2">Keep me editable</text><path id="path1" d="M0 0L1 1"/></g></svg>')
        svg = convert(source, "--columns=20", "--convert_to_paths=true").svg
        output = svg.xpath('//*[@data-ascii-art-pro-version]')[0]
        self.assertEqual(len(output.xpath(".//svg:text")), 0)
        self.assertGreater(len(output.xpath(".//svg:path")), 0)
        self.assertEqual(svg.getElementById("other").tag, inkex.addNS("text", "svg"))
        ids = [n.get("id") for n in svg.iter() if n.get("id")]
        self.assertEqual(len(ids), len(set(ids)))

    @unittest.skipUnless(os.environ.get("INKSCAPE_COMMAND"), "Set INKSCAPE_COMMAND for renderer integration")
    def test_arabic_rendering_matches_isolated_letters_and_paths(self):
        from inkex.command import inkscape
        # Reference uses separate SVG text elements. Production uses one text per row.
        # Equality catches joining/ligatures, bidi reversal and displaced vowel marks.
        cells = ["ل", "ا", "بَ", "تِ", "A", "١", "مّ", "."]
        extension = convert(None, "--sequence=arabic")
        extension.font = "'DejaVu Sans', sans-serif"
        production = extension.make_text(cells, [(0, 0, 0, 255)] * len(cells),
                                         len(cells), 1, 20, 20, 48, 60, 36)
        root = inkex.SvgDocumentElement()
        root.set("width", "430")
        root.set("height", "100")
        root.append(production)
        reference = inkex.SvgDocumentElement()
        reference.set("width", "430")
        reference.set("height", "100")
        for span in production[0]:
            text = inkex.TextElement()
            text.set("x", span.get("x"))
            text.set("y", span.get("y"))
            text.text = span.text
            text.style = {**dict(production[0].style), **dict(span.style)}
            reference.append(text)
        paths = extension.to_paths(production, (0, 0, 430, 100))
        self.assertFalse(paths.xpath(".//svg:text"))
        self.assertTrue(paths.xpath(".//svg:path"))
        path_root = inkex.SvgDocumentElement()
        path_root.set("width", "430")
        path_root.set("height", "100")
        path_root.append(paths)
        with tempfile.TemporaryDirectory() as directory:
            images = []
            for name, svg in (("production", root), ("reference", reference), ("paths", path_root)):
                source = str(Path(directory, name + ".svg"))
                png = str(Path(directory, name + ".png"))
                etree.ElementTree(svg).write(source, encoding="utf-8")
                inkscape(source, export_type="png", export_filename=png)
                with Image.open(png) as rendered:
                    images.append(rendered.convert("RGBA"))
            self.assertIsNone(ImageChops.difference(images[0], images[1]).getbbox())
            # Text and outlined glyphs may differ by antialiasing; silhouettes must agree.
            silhouettes = [img.getchannel("A").point(lambda v: 255 if v >= 128 else 0) for img in images]
            diff = ImageChops.difference(silhouettes[0], silhouettes[2])
            self.assertLess(sum(diff.tobytes()) / 255, 80)


class DescriptorTests(unittest.TestCase):
    def test_schema_and_interface_arguments(self):
        schema_path = Path(inkex.__file__).parent / "tester" / "inkscape.extension.rng"
        if schema_path.exists():
            schema = etree.RelaxNG(etree.parse(str(schema_path)))
            schema.assertValid(etree.parse(str(ROOT / "ascii_art_pro.inx")))
        descriptor = etree.parse(str(ROOT / "ascii_art_pro.inx"))
        parameters = descriptor.findall(".//{*}param")
        names = [param.get("name") for param in parameters]
        self.assertEqual(len(names), len(set(names)))
        extension = AsciiArtPro()
        defaults = []
        for param in parameters:
            kind = param.get("type")
            if kind == "optiongroup":
                value = param.find("{*}option").get("value")
            elif kind == "notebook":
                value = param.find("{*}page").get("name")
            elif kind == "color":
                value = str(int(param.text, 0))
            else:
                value = param.text
            defaults.append(f'--{param.get("name")}={value}')
        options = extension.arg_parser.parse_args(defaults)
        self.assertEqual(options.columns, 80)
        self.assertEqual(options.sequence, "standard")
