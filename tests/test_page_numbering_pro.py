import io
import os
from pathlib import Path
import tempfile
import unittest

import inkex
from lxml import etree

from page_numbering_pro import (MARKER, PAGE_KEY, PageNumberingPro, number_content,
                               replace_number_content, root_transform)


ROOT = Path(__file__).resolve().parents[1]


def document(pages=None, width="800", height="600", viewbox="0 0 800 600", extra=""):
    page_xml = "" if pages is None else "".join(
        f'<inkscape:page id="{key}" x="{x}" y="{y}" width="{w}" height="{h}"/>'
        for key, x, y, w, h in pages)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{inkex.NSS["inkscape"]}" '
            f'xmlns:sodipodi="{inkex.NSS["sodipodi"]}" width="{width}" height="{height}" '
            f'viewBox="{viewbox}" {extra}>'
            f'<sodipodi:namedview id="namedview">{page_xml}</sodipodi:namedview>'
            '<text id="design-text" x="15" y="30">2026</text>'
            '<g id="artwork" transform="translate(100,40) scale(3)"><rect width="30" height="10"/></g>'
            '</svg>').encode()


PAGES = [("page-a", 0, 0, 800, 600), ("page-b", 860, 0, 640, 480), ("page-c", -850, 650, 800, 700)]


def load(source=None, *args):
    extension = PageNumberingPro()
    extension.options = extension.arg_parser.parse_args(args)
    extension.load(io.BytesIO(source if source is not None else document()))
    return extension


def convert(source=None, *args):
    extension = load(source, *args)
    extension.effect()
    return extension


def serialized(extension):
    return etree.tostring(extension.svg)


def template_document():
    source = document(PAGES)
    template = ('<style>.model {font-family:serif; font-weight:bold; font-style:italic; fill:#b42367;}</style>'
                '<g transform="translate(40,20) scale(2)" style="font-size:36px;opacity:0.7">'
                '<text id="model" class="model" style="text-anchor:middle">'
                '<tspan id="model-span" x="80" y="240" style="font-size:30px">٧</tspan>'
                '</text></g>')
    return source.replace(b'</svg>', template.encode() + b'</svg>')


class NumberingTests(unittest.TestCase):
    def test_minimum_digits_pads_both_scripts_without_truncating(self):
        for script, expected in (("western", ["009", "010", "011"]),
                                 ("indic", ["٠٠٩", "٠١٠", "٠١١"])):
            with self.subTest(script=script):
                extension = convert(document(PAGES), "--minimum_digits=3", "--start_number=9",
                                    "--digits=" + script)
                self.assertEqual([number_content(n) for n in extension.existing_numbers()], expected)
                self.assertEqual([n.get("data-page-numbering-value") for n in extension.existing_numbers()],
                                 ["9", "10", "11"])
        for width, expected in ((1, "1"), (2, "01"), (3, "001"), (12, "000000000001")):
            self.assertEqual(convert(None, "--minimum_digits=" + str(width)).existing_numbers()[0].text,
                             expected)
        large = convert(None, "--minimum_digits=2", "--start_number=123")
        self.assertEqual(large.existing_numbers()[0].text, "123")

    def test_padding_can_be_changed_on_rerun_with_ids_and_values_preserved(self):
        first = convert(document(PAGES), "--minimum_digits=2")
        ids = [n.get("id") for n in first.existing_numbers()]
        second = convert(serialized(first), "--minimum_digits=3")
        self.assertEqual([n.get("id") for n in second.existing_numbers()], ids)
        self.assertEqual([n.text for n in second.existing_numbers()], ["001", "002", "003"])
        third = convert(serialized(second), "--minimum_digits=1")
        self.assertEqual([n.text for n in third.existing_numbers()], ["1", "2", "3"])

    def test_template_padding_preserves_all_supported_digit_scripts_and_can_grow(self):
        for sample, expected in (("007", ["007", "008", "009"]),
                                 ("٠٠٧", ["٠٠٧", "٠٠٨", "٠٠٩"]),
                                 ("۰۰۷", ["۰۰۷", "۰۰۸", "۰۰۹"])):
            with self.subTest(sample=sample):
                source = template_document().replace("٧".encode(), sample.encode())
                extension = convert(source, "--placement_mode=template", "--id=model")
                self.assertEqual([number_content(n) for n in extension.existing_numbers()], expected)
                enlarged = convert(serialized(extension), "--placement_mode=template",
                                   "--template_source=first", "--minimum_digits=4")
                zero = sample[0]
                self.assertEqual([number_content(n) for n in enlarged.existing_numbers()],
                                 [zero + item for item in expected])
                self.assertEqual(enlarged.existing_numbers()[0].find(inkex.addNS("tspan", "svg")).style["font-size"],
                                 "30px")

    def test_selected_and_following_numbers_receive_padding_without_touching_prior_pages(self):
        first = convert(document(PAGES), "--minimum_digits=2", "--digits=indic")
        a, b, c = first.existing_numbers()
        prior = etree.tostring(a)
        following_style = c.get("style")
        second = convert(serialized(first), "--id=" + b.get("id"), "--digits=indic", "--minimum_digits=3",
                         "--change_selected_value=true", "--selected_number=9", "--renumber_following=true")
        self.assertEqual(etree.tostring(second.svg.getElementById(a.get("id"))), prior)
        self.assertEqual(second.svg.getElementById(b.get("id")).text, "٠٠٩")
        self.assertEqual(second.svg.getElementById(c.get("id")).text, "٠١٠")
        self.assertEqual(second.svg.getElementById(c.get("id")).get("style"), following_style)
        # Default width keeps the existing padding of later numbers.
        third = convert(serialized(second), "--id=" + b.get("id"), "--digits=indic",
                        "--change_selected_value=true", "--selected_number=5", "--renumber_following=true")
        self.assertEqual(third.svg.getElementById(c.get("id")).text, "٠٠٦")

    def test_all_nine_positions_use_pixel_margins(self):
        for vertical, y in (("top", 32), ("middle", 300), ("bottom", 568)):
            for horizontal, x in (("left", 40), ("center", 400), ("right", 760)):
                with self.subTest(vertical=vertical, horizontal=horizontal):
                    extension = convert(None, "--vertical_position=" + vertical,
                                        "--alignment=" + horizontal, "--bottom_margin=32", "--side_margin=40")
                    text = extension.existing_numbers()[0]
                    self.assertEqual((float(text.get("x")), float(text.get("y"))), (x, y))

    def test_template_adopts_designed_number_and_copies_inherited_format_and_position(self):
        extension = convert(template_document(), "--placement_mode=template", "--id=model-span")
        numbers = extension.existing_numbers()
        self.assertEqual([number_content(n) for n in numbers], ["٧", "٨", "٩"])
        self.assertEqual(numbers[0].get("id"), "model")
        self.assertEqual(len([n for n in extension.svg.iter() if n.get("id") == "model"]), 1)
        self.assertEqual(extension.svg.getElementById("design-text").text, "2026")
        expected = [(200, 500), (1020, 400), (-650, 650 + 700 * 5 / 6)]
        for number, position in zip(numbers, expected):
            anchor = extension.template_anchor(number)
            self.assertAlmostEqual(anchor[0], position[0], places=7)
            self.assertAlmostEqual(anchor[1], position[1], places=7)
            span = number.find(inkex.addNS("tspan", "svg"))
            self.assertEqual(span.style["font-size"], "30px")
            self.assertEqual(span.style["fill"], "#b42367")
            self.assertEqual(span.style["font-family"], "serif")
            self.assertEqual(span.style["font-weight"], "bold")
            self.assertEqual(span.style["font-style"], "italic")
            self.assertAlmostEqual(root_transform(number).a, 2)
            self.assertAlmostEqual(float(number.style["opacity"]), 0.7)
        ids = [n.get("id") for n in extension.svg.iter() if n.get("id")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_template_first_reuses_latest_manual_edits_without_duplicate_numbers(self):
        first = convert(template_document(), "--placement_mode=template", "--id=model")
        model = first.existing_numbers()[0]
        ids = [n.get("id") for n in first.existing_numbers()]
        span = model.find(inkex.addNS("tspan", "svg"))
        span.text = "١٠"
        span.set("x", "100")
        span.style["font-size"] = "42px"
        span.style["fill"] = "#008800"
        second = convert(serialized(first), "--placement_mode=template", "--template_source=first")
        self.assertEqual([n.get("id") for n in second.existing_numbers()], ids)
        self.assertEqual([number_content(n) for n in second.existing_numbers()], ["١٠", "١١", "١٢"])
        for n in second.existing_numbers():
            span = n.find(inkex.addNS("tspan", "svg"))
            self.assertEqual(span.style["font-size"], "42px")
            self.assertEqual(span.style["fill"], "#008800")
        self.assertEqual(second.template_anchor(second.existing_numbers()[1]), (1052, 400))

    def test_template_from_middle_page_keeps_its_value_and_page_order(self):
        first = load(document(PAGES))
        template = inkex.TextElement(id="middle-model", x="1180", y="240")
        template.text = "17"
        template.style = {"font-size": "28px", "fill": "#123456"}
        first.svg.append(template)
        second = convert(serialized(first), "--placement_mode=template", "--scope=all", "--id=middle-model")
        self.assertEqual([number_content(n) for n in second.existing_numbers()], ["16", "17", "18"])
        self.assertEqual([second.template_anchor(n) for n in second.existing_numbers()],
                         [(400, 300), (1180, 240), (-450, 1000)])
        self.assertEqual(second.existing_numbers()[1].get("id"), "middle-model")

    def test_template_cancels_existing_layer_transform(self):
        first = convert(document(PAGES))
        layer = first.existing_numbers()[0].getparent()
        layer.set("transform", "translate(100,40) scale(1.5)")
        before = first.template_anchor(first.existing_numbers()[0])
        second = convert(serialized(first), "--placement_mode=template", "--template_source=first")
        self.assertEqual(second.template_anchor(second.existing_numbers()[0]), before)
        self.assertAlmostEqual(root_transform(second.existing_numbers()[1]).a, 1.5)

    def test_template_keeps_physical_size_in_millimeter_document(self):
        source = document([("a", 0, 0, 210, 297), ("b", 220, 0, 210, 297)],
                          width="210mm", height="297mm", viewbox="0 0 210 297")
        first = load(source)
        model = inkex.TextElement(id="mm-model", x="105", y="285")
        model.text = "1"
        model.style = {"font-size": "5px", "fill": "#008800"}
        first.svg.append(model)
        second = convert(serialized(first), "--placement_mode=template", "--id=mm-model")
        self.assertEqual([second.template_anchor(n) for n in second.existing_numbers()], [(105, 285), (325, 285)])
        self.assertEqual([n.style["font-size"] for n in second.existing_numbers()], ["5px", "5px"])
        self.assertAlmostEqual(root_transform(second.existing_numbers()[1]).a, 1)

    def test_template_does_not_multiply_layer_opacity_on_repeated_apply(self):
        first = convert(document(PAGES))
        first.existing_numbers()[0].getparent().style["opacity"] = "0.5"
        second = convert(serialized(first), "--placement_mode=template", "--template_source=first")
        third = convert(serialized(second), "--placement_mode=template", "--template_source=first")
        for extension in (second, third):
            self.assertEqual([n.style["opacity"] for n in extension.existing_numbers()], ["1", "1", "1"])
            self.assertEqual(extension.existing_numbers()[0].getparent().style["opacity"], "0.5")

    def test_cascade_is_optional_and_preserves_later_styles_and_positions(self):
        first = convert(document(PAGES))
        a, b, c = first.existing_numbers()
        before_a = etree.tostring(a)
        c.set("x", "-700")
        c.set("y", "720")
        c.style["font-size"] = "33px"
        c.style["fill"] = "#ee7700"
        c.set("transform", "rotate(10)")
        attrs = dict(c.attrib)
        second = convert(serialized(first), "--id=" + b.get("id"), "--change_selected_value=true",
                         "--selected_number=3", "--renumber_following=true", "--font_size=22")
        self.assertEqual(etree.tostring(second.svg.getElementById(a.get("id"))), before_a)
        self.assertEqual(second.svg.getElementById(b.get("id")).text, "3")
        updated = second.svg.getElementById(c.get("id"))
        self.assertEqual(updated.text, "4")
        for attr in ("style", "x", "y", "transform", "id", PAGE_KEY):
            self.assertEqual(updated.get(attr), attrs[attr])
        ordinary = convert(serialized(first), "--id=" + b.get("id"), "--change_selected_value=true", "--selected_number=3")
        self.assertEqual(etree.tostring(ordinary.svg.getElementById(c.get("id"))), etree.tostring(c))

    def test_cascade_uses_manually_edited_value_and_template_style(self):
        first = convert(document(PAGES), "--digits=indic")
        a, b, c = first.existing_numbers()
        b.text = "٨"
        b.style["font-size"] = "30px"
        second = convert(serialized(first), "--id=" + b.get("id"), "--placement_mode=template",
                         "--renumber_following=true")
        self.assertEqual(second.svg.getElementById(a.get("id")).text, "١")
        self.assertEqual(second.svg.getElementById(b.get("id")).text, "٨")
        self.assertEqual(second.svg.getElementById(c.get("id")).text, "٩")
        self.assertEqual(second.svg.getElementById(b.get("id")).style["font-size"], "30px")

    def test_cascade_creates_missing_later_page_number(self):
        first = convert(document(PAGES))
        target = first.existing_numbers()[1]
        final = first.existing_numbers()[2]
        final.getparent().remove(final)
        second = convert(serialized(first), "--id=" + target.get("id"), "--renumber_following=true",
                         "--change_selected_value=true", "--selected_number=50")
        numbers = {n.get(PAGE_KEY): number_content(n) for n in second.existing_numbers()}
        self.assertEqual(numbers, {"page-a": "1", "page-b": "50", "page-c": "51"})

    def test_template_and_cascade_invalid_inputs_leave_source_unchanged(self):
        for source, args in (
            (document(), ("--placement_mode=template",)),
            (document(), ("--placement_mode=template", "--template_source=first")),
            (document(), ("--vertical_position=unknown",)),
            (document(), ("--renumber_following=true",)),
            (template_document(), ("--placement_mode=template", "--id=model", "--bottom_margin=nan")),
        ):
            extension = load(source, *args)
            before = serialized(extension)
            with self.assertRaises(inkex.AbortExtension):
                extension.effect()
            self.assertEqual(serialized(extension), before)
        first = convert(document(PAGES))
        target = first.existing_numbers()[1]
        extension = load(serialized(first), "--id=" + target.get("id"), "--renumber_following=true",
                         "--change_selected_value=true", "--selected_number=999999")
        before = serialized(extension)
        with self.assertRaises(inkex.AbortExtension):
            extension.effect()
        self.assertEqual(serialized(extension), before)

    def test_single_page_bottom_center_and_editable_text(self):
        extension = convert()
        numbers = extension.existing_numbers()
        self.assertEqual(len(numbers), 1)
        self.assertEqual(numbers[0].text, "1")
        self.assertEqual((float(numbers[0].get("x")), float(numbers[0].get("y"))), (400, 576))
        self.assertEqual(float(numbers[0].style["font-size"][:-2]), 16)
        self.assertEqual(numbers[0].getparent().get("inkscape:label"), "Page Numbering")
        self.assertEqual(extension.svg.getElementById("design-text").text, "2026")

    def test_all_pages_follow_document_order_with_offsets_and_sizes(self):
        extension = convert(document(PAGES), "--start_number=10")
        self.assertEqual([n.text for n in extension.existing_numbers()], ["10", "11", "12"])
        self.assertEqual([(float(n.get("x")), float(n.get("y"))) for n in extension.existing_numbers()],
                         [(400, 576), (1180, 456), (-450, 1326)])
        self.assertEqual([n.get(PAGE_KEY) for n in extension.existing_numbers()], ["page-a", "page-b", "page-c"])

    def test_repeated_apply_updates_without_duplicates_and_preserves_ids(self):
        first = convert(document(PAGES))
        ids = [n.get("id") for n in first.existing_numbers()]
        second = convert(serialized(first), "--start_number=20", "--alignment=right", "--side_margin=30",
                         "--bottom_margin=40", "--color=#ff0000", "--font_family=Amiri", "--font_size=22")
        self.assertEqual(len(second.existing_numbers()), 3)
        self.assertEqual([n.get("id") for n in second.existing_numbers()], ids)
        self.assertEqual([n.text for n in second.existing_numbers()], ["20", "21", "22"])
        first_number = second.existing_numbers()[0]
        self.assertEqual((float(first_number.get("x")), float(first_number.get("y"))), (770, 560))
        self.assertEqual(first_number.style["fill"], "#ff0000")
        self.assertIn("Amiri", str(first_number.style["font-family"]))

    def test_page_insertion_deletion_and_reordering_use_page_ids(self):
        first = convert(document(PAGES))
        old_ids = {n.get(PAGE_KEY): n.get("id") for n in first.existing_numbers()}
        namedview = first.svg.find(inkex.addNS("namedview", "sodipodi"))
        page_a, page_b, page_c = namedview.findall(inkex.addNS("page", "inkscape"))
        namedview.remove(page_b)
        namedview.remove(page_c)
        namedview.insert(0, page_c)
        page_c.set("y", "10")
        namedview.append(inkex.Page.new(300, 250, 1700, 30))
        second = convert(serialized(first))
        numbers = second.existing_numbers()
        self.assertEqual([n.text for n in numbers], ["1", "2", "3"])
        self.assertEqual(numbers[0].get("id"), old_ids["page-c"])
        self.assertEqual(numbers[1].get("id"), old_ids["page-a"])
        self.assertIsNone(second.svg.getElementById(old_ids["page-b"]))
        self.assertEqual(float(numbers[0].get("y")), 686)
        self.assertTrue(namedview[-1].get("id") is None)
        self.assertTrue(second.svg.find(inkex.addNS("namedview", "sodipodi"))[-1].get("id"))

    def test_selected_update_changes_only_that_number(self):
        first = convert(document(PAGES))
        selected = first.existing_numbers()[1]
        untouched = [(n.get("id"), etree.tostring(n)) for n in first.existing_numbers() if n is not selected]
        second = convert(serialized(first), "--id=" + selected.get("id"), "--change_selected_value=true",
                         "--selected_number=88", "--font_style=bold", "--alignment=left", "--side_margin=12")
        new = second.svg.getElementById(selected.get("id"))
        self.assertEqual(new.text, "88")
        self.assertEqual(new.style["font-weight"], "bold")
        self.assertEqual(float(new.get("x")), 872)
        for identifier, before in untouched:
            self.assertEqual(etree.tostring(second.svg.getElementById(identifier)), before)

    def test_selected_style_update_preserves_manual_text_value(self):
        first = convert(document(PAGES))
        number = first.existing_numbers()[1]
        number.text = "٧٥"
        second = convert(serialized(first), "--id=" + number.get("id"), "--color=#008800", "--digits=indic")
        updated = second.svg.getElementById(number.get("id"))
        self.assertEqual(updated.text, "٧٥")
        self.assertEqual(updated.style["fill"], "#008800")

    def test_selected_tspan_is_recognized(self):
        first = convert()
        number = first.existing_numbers()[0]
        number.text = None
        span = inkex.Tspan(id="selected-span")
        span.text = "24"
        number.append(span)
        second = convert(serialized(first), "--id=selected-span")
        self.assertEqual(second.existing_numbers()[0].text, "24")

    def test_all_pages_option_overrides_selected_number(self):
        first = convert(document(PAGES))
        second = convert(serialized(first), "--id=" + first.existing_numbers()[1].get("id"),
                         "--scope=all", "--start_number=30")
        self.assertEqual([n.text for n in second.existing_numbers()], ["30", "31", "32"])

    def test_indic_digits_color_alpha_and_font_style(self):
        extension = convert(document(PAGES), "--start_number=9", "--digits=indic", "--color=0xff000080",
                            "--font_family=custom", "--custom_font=Cairo", "--font_style=bold_italic")
        self.assertEqual([n.text for n in extension.existing_numbers()], ["٩", "١٠", "١١"])
        text = extension.existing_numbers()[0]
        self.assertAlmostEqual(float(text.style["fill-opacity"]), 128 / 255)
        self.assertEqual(text.style["font-style"], "italic")

    def test_pixel_values_are_correct_in_millimeter_document(self):
        # 210mm-wide viewport with a 210-unit viewBox: one user unit is 3.7795 px.
        extension = convert(document(width="210mm", height="297mm", viewbox="0 0 210 297"),
                            "--bottom_margin=48", "--font_size=20")
        text = extension.existing_numbers()[0]
        px_per_unit = 96 / 25.4
        transform = inkex.Transform(text.attrib.get("transform"))
        point = transform.apply_to_point((float(text.get("x")), float(text.get("y"))))
        self.assertAlmostEqual(point.x, 105, places=8)
        self.assertAlmostEqual((297 - point.y) * px_per_unit, 48, places=7)
        self.assertAlmostEqual(transform.a * px_per_unit, 1, places=8)
        self.assertEqual(text.style["font-size"], "20.0px")

    def test_nonzero_viewbox_and_single_explicit_page(self):
        implicit = convert(document(viewbox="50 70 800 600"))
        number = implicit.existing_numbers()[0]
        self.assertEqual((float(number.get("x")), float(number.get("y"))), (450, 646))
        explicit = convert(document([("single", 40, 20, 100, 100)]))
        number = explicit.existing_numbers()[0]
        self.assertEqual((float(number.get("x")), float(number.get("y"))), (90, 96))

    def test_nonuniform_svg_viewport_keeps_real_pixel_font_and_margins(self):
        extension = convert(document(width="1600", height="600", extra='preserveAspectRatio="none"'),
                            "--alignment=left", "--side_margin=32", "--bottom_margin=16")
        text = extension.existing_numbers()[0]
        point = text.transform.apply_to_point((float(text.get("x")), float(text.get("y"))))
        self.assertEqual((point.x, point.y), (16, 584))
        self.assertEqual(text.transform.a, 0.5)

    def test_transformed_numbering_layer_is_compensated(self):
        first = convert()
        layer = first.existing_numbers()[0].getparent()
        layer.set("transform", "translate(70,30) scale(2)")
        second = convert(serialized(first), "--scope=all")
        text = second.existing_numbers()[0]
        point = text.composed_transform().apply_to_point((float(text.get("x")), float(text.get("y"))))
        self.assertEqual((point.x, point.y), (400, 576))

    def test_implicit_to_explicit_page_transition_preserves_first_number(self):
        first = convert()
        identifier = first.existing_numbers()[0].get("id")
        namedview = first.svg.find(inkex.addNS("namedview", "sodipodi"))
        namedview.append(inkex.Page.new(800, 600, 0, 0))
        namedview.append(inkex.Page.new(800, 600, 850, 0))
        second = convert(serialized(first))
        self.assertEqual(second.existing_numbers()[0].get("id"), identifier)
        self.assertEqual(len(second.existing_numbers()), 2)

    def test_duplicate_numbers_are_cleaned_without_touching_unmanaged_text(self):
        first = convert()
        duplicated = inkex.TextElement(id="duplicate")
        duplicated.set(MARKER, "number")
        duplicated.set(PAGE_KEY, "document")
        duplicated.text = "99"
        first.svg.append(duplicated)
        second = convert(serialized(first))
        self.assertEqual(len(second.existing_numbers()), 1)
        self.assertIsNone(second.svg.getElementById("duplicate"))
        self.assertEqual(second.svg.getElementById("design-text").text, "2026")

    def test_invalid_options_or_missing_selection_do_not_mutate(self):
        for args in (("--scope=selected",), ("--bottom_margin=700",), ("--font_size=nan",),
                     ("--color=none",), ("--font_family=custom", "--custom_font=;"),
                     ("--minimum_digits=0",), ("--minimum_digits=13",)):
            with self.subTest(args=args):
                extension = load(None, *args)
                before = serialized(extension)
                with self.assertRaises(inkex.AbortExtension):
                    extension.effect()
                self.assertEqual(serialized(extension), before)

    def test_deleted_page_cannot_be_edited_individually(self):
        first = convert(document(PAGES))
        target = first.existing_numbers()[1]
        page = first.svg.getElementById("page-b")
        page.getparent().remove(page)
        extension = load(serialized(first), "--id=" + target.get("id"))
        before = serialized(extension)
        with self.assertRaisesRegex(inkex.AbortExtension, "deleted"):
            extension.effect()
        self.assertEqual(serialized(extension), before)

    def test_singular_layer_transform_fails_without_document_mutation(self):
        first = convert()
        first.existing_numbers()[0].getparent().attrib["transform"] = "scale(0)"
        extension = load(serialized(first))
        before = serialized(extension)
        with self.assertRaisesRegex(inkex.AbortExtension, "zero scale"):
            extension.effect()
        self.assertEqual(serialized(extension), before)

    def test_schema_and_all_ui_parameters_match_parser_defaults(self):
        descriptor = etree.parse(str(ROOT / "page_numbering_pro.inx"))
        schema = Path(inkex.__file__).parent / "tester" / "inkscape.extension.rng"
        if schema.is_file():
            etree.RelaxNG(etree.parse(str(schema))).assertValid(descriptor)
        args = []
        names = []
        for param in descriptor.findall(".//{*}param"):
            names.append(param.get("name"))
            if param.get("type") == "notebook":
                value = param.find("{*}page").get("name")
            elif param.get("type") == "optiongroup":
                value = param.find("{*}option").get("value")
            elif param.get("type") == "color":
                value = str(int(param.text, 0))
            else:
                value = param.text
            args.append(f'--{param.get("name")}={value}')
        self.assertEqual(len(names), len(set(names)))
        extension = convert(None, *args)
        self.assertEqual(len(extension.existing_numbers()), 1)

    @unittest.skipUnless(os.environ.get("INKSCAPE_COMMAND"), "Set INKSCAPE_COMMAND for renderer integration")
    def test_real_renderer_plain_text_default_font_is_preserved(self):
        from inkex.command import inkscape
        source = document(PAGES)
        template = convert(source, "--placement_mode=template", "--id=design-text")
        boxes = []
        with tempfile.TemporaryDirectory() as directory:
            for index, content in enumerate((source, serialized(template))):
                filename = str(Path(directory, f"default-font-{index}.svg"))
                Path(filename).write_bytes(content)
                output = inkscape(filename, query_all=True)
                row = next(row for row in output.splitlines() if row.startswith("design-text,"))
                boxes.append([float(v) for v in row.split(",")[1:]])
        for value, expected in zip(boxes[1], boxes[0]):
            self.assertAlmostEqual(value, expected, delta=0.05)

    @unittest.skipUnless(os.environ.get("INKSCAPE_COMMAND"), "Set INKSCAPE_COMMAND for renderer integration")
    def test_real_renderer_template_matches_source_glyph_bounds_and_positions(self):
        from inkex.command import inkscape
        source = template_document()
        template = convert(source, "--placement_mode=template", "--id=model")
        # Query identical glyphs: Arabic digits themselves have different ink heights.
        for number in template.existing_numbers():
            replace_number_content(number, 7, number_content(number))
        boxes = []
        with tempfile.TemporaryDirectory() as directory:
            for index, content in enumerate((source, serialized(template))):
                filename = str(Path(directory, f"template-{index}.svg"))
                Path(filename).write_bytes(content)
                output = inkscape(filename, query_all=True)
                rows = {row.split(",")[0]: [float(v) for v in row.split(",")[1:]] for row in output.splitlines()}
                boxes.append(rows)
        for value, expected in zip(boxes[1]["model"], boxes[0]["model"]):
            self.assertAlmostEqual(value, expected, delta=0.05)
        # Glyph dimensions and baseline offset must survive page-relative translation.
        for number in template.existing_numbers()[1:]:
            box = boxes[1][number.get("id")]
            anchor = template.template_anchor(number)
            self.assertAlmostEqual(box[2], boxes[0]["model"][2], delta=0.05)
            self.assertAlmostEqual(box[3], boxes[0]["model"][3], delta=0.05)
            self.assertAlmostEqual(box[1] - anchor[1], boxes[0]["model"][1] - 500, delta=0.05)

    @unittest.skipUnless(os.environ.get("INKSCAPE_COMMAND"), "Set INKSCAPE_COMMAND for renderer integration")
    def test_real_inkscape_renders_pixel_and_mm_footers_at_same_size(self):
        from inkex.command import inkscape
        # Export the same physical page expressed in px and mm; text query boxes must agree.
        px = convert(document(width="793.700787401575", height="1122.51968503937",
                              viewbox="0 0 793.700787401575 1122.51968503937"), "--font_size=24")
        mm = convert(document(width="210mm", height="297mm", viewbox="0 0 210 297"), "--font_size=24")
        boxes = []
        with tempfile.TemporaryDirectory() as directory:
            for index, extension in enumerate((px, mm)):
                filename = str(Path(directory, f"number-{index}.svg"))
                etree.ElementTree(extension.svg).write(filename, encoding="utf-8")
                identifier = extension.existing_numbers()[0].get("id")
                output = inkscape(filename, query_all=True)
                row = next(row for row in output.splitlines() if row.startswith(identifier + ","))
                boxes.append([float(value) for value in row.split(",")[1:]])
        for value, expected in zip(boxes[0], boxes[1]):
            self.assertAlmostEqual(value, expected, delta=0.05)
