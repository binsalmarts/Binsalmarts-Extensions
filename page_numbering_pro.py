#!/usr/bin/env python3
"""Editable page numbers, placement templates and optional sequential updates."""

from copy import deepcopy
from dataclasses import dataclass
import math
import re

import inkex


VERSION = "1.2.0"
MARKER = "data-page-numbering-pro"
PAGE_KEY = "data-page-numbering-page"
MAX_PAGES = 2000
# SP_CSS_FONT_SIZE_DEFAULT in Inkscape's style.h; confirmed by renderer tests.
DEFAULT_FONT_SIZE = 12.0
FONTS = ("sans-serif", "serif", "Arial", "Liberation Sans", "DejaVu Sans",
         "Noto Sans Arabic", "Amiri", "Cairo", "Tajawal", "custom")
INDIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def root_transform(node):
    """Read transforms without the wrapped getter rewriting the source XML."""
    result = inkex.Transform()
    for ancestor in (node, *node.iterancestors()):
        result = inkex.Transform(ancestor.attrib.get("transform")) @ result
    if any(not math.isfinite(value) for value in result.to_hexad()):
        raise inkex.AbortExtension("Invalid number or layer transform.")
    return result


def set_transform(node, transform):
    if transform:
        node.attrib["transform"] = "matrix(" + " ".join(map(svg_number, transform.to_hexad())) + ")"
    else:
        node.attrib.pop("transform", None)


def effective_opacity(node):
    opacity = 1.0
    for ancestor in (node, *node.iterancestors()):
        raw = ancestor.cascaded_style().get("opacity", "1")
        value = float(raw[:-1]) / 100 if raw.endswith("%") else float(raw)
        opacity *= max(0.0, min(1.0, value))
    return opacity


def number_slots(node):
    """Text content only: SVG titles and descriptions are not part of the number."""
    yield node, "text"
    for element in node:
        if isinstance(element, inkex.Tspan):
            yield from number_slots(element)
        yield element, "tail"


def number_content(node):
    return "".join(getattr(element, slot) or "" for element, slot in number_slots(node)).strip()


def formatted_value(value, sample, minimum_digits=1):
    # A template's leading zeros are part of its numeric formatting.
    sample = sample.strip()
    width = max(minimum_digits, len(sample) if sample.isdecimal() and sample[0] in "0٠۰" else 1)
    content = str(value).zfill(width)
    digits = PERSIAN_DIGITS if any(c in "۰۱۲۳۴۵۶۷۸۹" for c in sample) else (
        INDIC_DIGITS if any(c in "٠١٢٣٤٥٦٧٨٩" for c in sample) else None)
    return content.translate(digits) if digits else content


def replace_number_content(node, value, sample, minimum_digits=1):
    # Preserve styled runs. Extra digits use the final run's formatting.
    slots = [(element, slot, getattr(element, slot)) for element, slot in number_slots(node)
             if (getattr(element, slot) or "").strip()]
    content = formatted_value(value, sample, minimum_digits)
    for index, (element, slot, old) in enumerate(slots):
        count = len(content) if index == len(slots) - 1 else min(len(old.strip()), len(content))
        setattr(element, slot, content[:count] or None)
        content = content[count:]
    if not slots:
        node.text = content


def svg_number(value):
    return format(float(value), ".12g")


def bounded(value, minimum, maximum, label):
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise inkex.AbortExtension(f"{label} must be between {minimum} and {maximum}.")


def color_style(value):
    """INX sends an unsigned decimal RGBA integer; accept CSS on the CLI as well."""
    try:
        raw = str(value).strip()
        if raw.startswith("0x") or raw.lstrip("-").isdigit():
            number = int(raw, 0) if raw.startswith("0x") else int(raw)
            if not 0 <= number <= 0xFFFFFFFF:
                raise ValueError("Invalid RGBA")
            rgb = tuple((number >> shift) & 255 for shift in (24, 16, 8))
            alpha = (number & 255) / 255
        else:
            if raw.lower() in ("none", ""):
                raise ValueError("No color")
            rgba = inkex.Color(raw).to_rgba()
            if len(rgba) != 4:
                raise ValueError("No color")
            rgb, alpha = tuple(rgba[:3]), rgba[3]
        return {"fill": "#{:02x}{:02x}{:02x}".format(*rgb), "fill-opacity": svg_number(alpha)}
    except (ValueError, TypeError, KeyError) as error:
        raise inkex.AbortExtension("Choose a valid number color.") from error


@dataclass
class PageInfo:
    key: str
    x: float
    y: float
    width: float
    height: float
    element: object = None


class PageNumberingPro(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="numbering")
        pars.add_argument("--scope", default="auto")
        pars.add_argument("--start_number", type=int, default=1)
        pars.add_argument("--change_selected_value", type=inkex.Boolean, default=False)
        pars.add_argument("--selected_number", type=int, default=1)
        pars.add_argument("--renumber_following", type=inkex.Boolean, default=False)
        pars.add_argument("--digits", default="western")
        pars.add_argument("--minimum_digits", type=int, default=1)
        pars.add_argument("--placement_mode", default="manual")
        pars.add_argument("--template_source", default="selected")
        pars.add_argument("--alignment", default="center")
        pars.add_argument("--vertical_position", default="bottom")
        pars.add_argument("--bottom_margin", type=float, default=24)
        pars.add_argument("--side_margin", type=float, default=24)
        pars.add_argument("--font_family", default="sans-serif")
        pars.add_argument("--custom_font", default="Noto Sans Arabic")
        pars.add_argument("--font_size", type=float, default=16)
        pars.add_argument("--font_style", default="normal")
        pars.add_argument("--color", default="255")

    def validate_options(self):
        o = self.options
        for value, minimum, maximum, label in (
            (o.start_number, 0, 999999, "Start number"),
            (o.selected_number, 0, 999999, "New selected number"),
            (o.minimum_digits, 1, 12, "Minimum digits"),
            (o.font_size, 1, 300, "Font size"),
            (o.bottom_margin, 0, 10000, "Top / bottom margin"),
            (o.side_margin, 0, 10000, "Side margin"),
        ):
            bounded(value, minimum, maximum, label)
        if o.scope not in ("auto", "all", "selected"):
            raise inkex.AbortExtension("Unknown update scope.")
        if o.placement_mode not in ("manual", "template") or o.template_source not in ("selected", "first"):
            raise inkex.AbortExtension("Unknown styling mode or template source.")
        if o.vertical_position not in ("top", "middle", "bottom"):
            raise inkex.AbortExtension("Unknown vertical position.")
        if o.alignment not in ("left", "center", "right") or o.digits not in ("western", "indic"):
            raise inkex.AbortExtension("Unknown alignment or digit style.")
        if o.font_family not in FONTS or o.font_style not in ("normal", "bold", "italic", "bold_italic"):
            raise inkex.AbortExtension("Unknown font family or style.")
        font = o.custom_font.strip() if o.font_family == "custom" else o.font_family
        if not font or any(ord(c) < 32 or c in ";{}" for c in font):
            raise inkex.AbortExtension("Enter a valid custom font name.")
        self.font = font if font in ("sans-serif", "serif") else "'" + font.replace("'", "") + "', sans-serif"
        self.fill = color_style(o.color)

    def unique_id(self, prefix):
        identifier = self.svg.get_unique_id(prefix, blacklist=self.reserved_ids)
        self.reserved_ids.add(identifier)
        return identifier

    def document_geometry(self):
        """Page metadata is in root user units. Convert px without assuming 1 unit = 1 px."""
        try:
            viewbox = self.svg.get_viewbox()
            if viewbox == [0, 0, 0, 0]:
                viewbox = [0, 0, self.svg.viewport_width, self.svg.viewport_height]
            vx, vy, vw, vh = viewbox
            width, height = self.svg.viewport_width, self.svg.viewport_height
            if any(not math.isfinite(v) for v in (vx, vy, vw, vh, width, height)) or min(vw, vh, width, height) <= 0:
                raise ValueError("Invalid viewport")
            sx, sy = width / vw, height / vh
            par = self.svg.get("preserveAspectRatio", "xMidYMid meet").split()
            if "none" not in par:
                sx = sy = max(sx, sy) if "slice" in par else min(sx, sy)
            return viewbox, sx, sy
        except (ValueError, TypeError, ZeroDivisionError) as error:
            raise inkex.AbortExtension("Cannot read document dimensions. Check the page width and height.") from error

    def read_pages(self, viewbox):
        namedview = self.svg.find(inkex.addNS("namedview", "sodipodi"))
        elements = namedview.findall(inkex.addNS("page", "inkscape")) if namedview is not None else []
        if len(elements) > MAX_PAGES:
            raise inkex.AbortExtension("This version supports up to 2000 pages.")
        if not elements:
            x, y, width, height = viewbox
            return [PageInfo("document", x, y, width, height)]
        pages = []
        used = set()
        for element in elements:
            try:
                x, y, width, height = element.x, element.y, element.width, element.height
                if any(not math.isfinite(v) for v in (x, y, width, height)) or min(width, height) <= 0:
                    raise ValueError("Invalid page")
            except (ValueError, TypeError) as error:
                raise inkex.AbortExtension("A page has invalid dimensions.") from error
            key = element.get("id") or self.unique_id("numbered-page")
            if key in used:
                raise inkex.AbortExtension("Duplicate page IDs. Correct the document before numbering.")
            used.add(key)
            pages.append(PageInfo(key, x, y, width, height, element))
        return pages

    def existing_numbers(self):
        return [element for element in self.svg.iter()
                if isinstance(element, inkex.TextElement) and element.get(MARKER) == "number"]

    def selected_text(self, existing):
        selected = list(self.svg.selection.values())
        candidates = []
        for number in existing:
            if any(element is number or number in element.iterancestors() or
                   element in number.iterancestors() for element in selected):
                candidates.append(number)
        if len(candidates) > 1:
            raise inkex.AbortExtension("Select one number to edit, or choose All pages to update every page.")
        return candidates[0] if candidates else None

    def number_value(self, node):
        """Preserve direct text edits as well as values entered through the extension."""
        content = number_content(node)
        try:
            if not content.isdecimal():
                raise ValueError("Not a plain number")
            value = int(content)
            if value < 0 or value > 999999:
                raise ValueError("Invalid value")
            return value
        except ValueError as error:
            raise inkex.AbortExtension("The selected text is not a valid integer. Enable Change selected value and enter a new number.") from error

    def page_for_number(self, node, pages):
        page = next((p for p in pages if p.key == node.get(PAGE_KEY)), None)
        if page is None and node.get(PAGE_KEY) == "document":
            page = pages[0]
        if page is None:
            raise inkex.AbortExtension("The page for this number was deleted. Choose All pages to rebuild the sequence.")
        return page

    def template_anchor(self, node):
        if any(element.tag == inkex.addNS("textPath", "svg") for element in node.iter()):
            raise inkex.AbortExtension("Choose a plain text number, without a text path.")
        if "shape-inside" in str(node.attrib.get("style", "")) or node.get("inline-size"):
            raise inkex.AbortExtension("Convert the number to plain text without text flow before using it as a template.")
        first = next((element for element, slot in number_slots(node)
                      if slot == "text" and (element.text or "").strip()), node)
        x = y = 0.0
        try:
            # The chain starts at the outer text and ends at the first glyph's tspan.
            chain = [node]
            if first is not node:
                chain = [node] + [a for a in reversed(list(first.iterancestors())) if node in a.iterancestors()] + [first]
            for element in chain:
                for attr in ("x", "y", "dx", "dy"):
                    raw = element.get(attr)
                    if raw is None:
                        continue
                    length = re.split(r"[\s,]+", raw.strip())[0]
                    if "%" in length:
                        raise ValueError("Percentage position")
                    value = inkex.units.convert_unit(length, "px")
                    if value is None or not math.isfinite(value):
                        raise ValueError("Invalid position")
                    if attr == "x":
                        x = value
                    elif attr == "y":
                        y = value
                    elif attr == "dx":
                        x += value
                    else:
                        y += value
            point = root_transform(first).apply_to_point((x, y))
            return point.x, point.y
        except (ValueError, TypeError) as error:
            raise inkex.AbortExtension("Cannot read the template position. Use plain text with valid coordinates.") from error

    def template_page(self, node, pages, anchor):
        if node.get(MARKER) == "number":
            return self.page_for_number(node, pages)
        x, y = anchor
        candidates = [p for p in pages if p.x <= x <= p.x + p.width and p.y <= y <= p.y + p.height]
        if len(candidates) != 1:
            raise inkex.AbortExtension("Place the template number within one page to determine its relative position.")
        return candidates[0]

    def frozen_copy(self, node, value, page, identifier=None):
        """Capture CSS/inherited formatting before moving a text out of its group."""
        if self.style_snapshot is None:
            snapshot = deepcopy(self.svg)
            self.style_snapshot = dict(zip(self.svg.iter(), snapshot.iter()))
        original = self.style_snapshot[node]
        clone = deepcopy(original)
        for source, destination in zip(original.iter(), clone.iter()):
            if not isinstance(source, (inkex.TextElement, inkex.Tspan)):
                continue
            style = source.specified_style()
            # Make default text properties explicit too, so a styled destination
            # layer cannot change the template's font or paint by inheritance.
            defaults = {"font-family": "sans-serif", "font-weight": "normal", "font-style": "normal",
                        "font-stretch": "normal", "font-variant": "normal", "fill": "#000000",
                        "fill-opacity": "1", "stroke": "none", "text-anchor": "start",
                        "direction": "ltr", "writing-mode": "lr-tb", "letter-spacing": "normal",
                        "word-spacing": "normal", "baseline-shift": "0", "visibility": "visible"}
            destination.style = {**defaults, **dict(style), "font-size": svg_number(self.font_size_of(source)) + "px"}
            destination.attrib.pop("class", None)
            if destination is not clone and destination.get("id"):
                destination.set("id", self.unique_id("page-number-span"))
        clone.style["opacity"] = svg_number(effective_opacity(original))
        clone.tail = None
        replace_number_content(clone, value, number_content(node), self.options.minimum_digits)
        self.mark_number(clone, page, value, identifier)
        set_transform(clone, root_transform(node))
        return clone

    def font_size_of(self, node):
        parent = node.getparent()
        raw = node.cascaded_style().get("font-size")
        if raw is None or raw == "inherit":
            return self.font_size_of(parent) if isinstance(parent, inkex.BaseElement) else DEFAULT_FONT_SIZE
        match = re.fullmatch(r"([+\-]?(?:\d*\.)?\d+)(%|em|rem|ex)?", raw)
        if match:
            value, unit = float(match[1]), match[2]
            if unit in ("%", "em", "ex"):
                base = self.font_size_of(parent) if isinstance(parent, inkex.BaseElement) else DEFAULT_FONT_SIZE
                return value * base * (0.01 if unit == "%" else 0.5 if unit == "ex" else 1)
            if unit == "rem":
                return value * (DEFAULT_FONT_SIZE if node is node.root else self.font_size_of(node.root))
            return value
        # SPIFontSize::font_size_table in Inkscape's style-internal.cpp.
        keywords = {"xx-small": 6, "x-small": 8, "small": 10, "medium": DEFAULT_FONT_SIZE,
                    "large": 14, "x-large": 18, "xx-large": 24}
        value = keywords.get(raw)
        if value is None:
            value = inkex.units.convert_unit(raw, "px")
        if value is None or not math.isfinite(value) or value <= 0:
            raise inkex.AbortExtension("Invalid template font size. Use a numeric font size.")
        return value

    def mark_number(self, text, page, value, identifier=None):
        text.set("id", identifier or self.unique_id("page-number"))
        text.set(MARKER, "number")
        text.set(PAGE_KEY, page.key)
        text.set("data-page-numbering-value", str(value))
        text.set("inkscape:label", f"Page number {value}")

    def make_template_number(self, source, source_page, anchor, page, value, identifier=None):
        new = self.frozen_copy(source, value, page, identifier)
        x, y = anchor
        destination = (page.x + (x - source_page.x) / source_page.width * page.width,
                       page.y + (y - source_page.y) / source_page.height * page.height)
        translation = inkex.Transform(translate=(destination[0] - x, destination[1] - y))
        set_transform(new, translation @ inkex.Transform(new.attrib.get("transform")))
        return new

    def make_number(self, page, value, sx, sy, identifier=None):
        o = self.options
        if o.vertical_position != "middle" and o.bottom_margin >= page.height * sy:
            raise inkex.AbortExtension("The vertical margin exceeds a page height. Enter a smaller margin.")
        if o.alignment != "center" and o.side_margin >= page.width * sx:
            raise inkex.AbortExtension("The side margin exceeds a page width. Enter a smaller margin.")
        if o.alignment == "center":
            x = (page.x + page.width / 2) * sx
            anchor = "middle"
        elif o.alignment == "left":
            x = page.x * sx + o.side_margin
            anchor = "start"
        else:
            x = (page.x + page.width) * sx - o.side_margin
            anchor = "end"
        if o.vertical_position == "top":
            y = page.y * sy + o.bottom_margin
        elif o.vertical_position == "middle":
            y = (page.y + page.height / 2) * sy
        else:
            y = (page.y + page.height) * sy - o.bottom_margin
        text = inkex.TextElement()
        self.mark_number(text, page, value, identifier)
        text.set("x", svg_number(x))
        text.set("y", svg_number(y))
        # Font size and margins are literal px in this space; root scaling is cancelled.
        if sx != 1 or sy != 1:
            text.attrib["transform"] = f"scale({svg_number(1 / sx)},{svg_number(1 / sy)})"
        text.text = formatted_value(value, "١" if o.digits == "indic" else "1", o.minimum_digits)
        text.style = {"font-family": self.font, "font-size": str(o.font_size) + "px",
                      "font-weight": "bold" if "bold" in o.font_style else "normal",
                      "font-style": "italic" if "italic" in o.font_style else "normal",
                      "font-stretch": "normal", "font-variant": "normal", "text-anchor": anchor,
                      "direction": "ltr", "writing-mode": "lr-tb", "stroke": "none",
                      "opacity": "1", "display": "inline", "visibility": "visible",
                      "letter-spacing": "normal", "word-spacing": "normal", "baseline-shift": "0",
                      **self.fill}
        return text

    def effect(self):
        self.reserved_ids = set()
        self.style_snapshot = None
        self.validate_options()
        o = self.options
        viewbox, sx, sy = self.document_geometry()
        pages = self.read_pages(viewbox)
        existing = self.existing_numbers()
        by_page = {}
        for number in existing:
            by_page.setdefault(number.get(PAGE_KEY), []).append(number)

        def existing_for_page(page, index):
            candidates = by_page.get(page.key, [])
            if index == 0 and not candidates and page.key != "document":
                candidates = by_page.get("document", [])
            if page.key == "document" and not candidates and existing:
                candidates = [existing[0]]
            return candidates[0] if candidates else None

        target = None if o.scope == "all" else self.selected_text(existing)
        if (o.scope == "selected" or (o.renumber_following and o.scope != "all")) and target is None:
            raise inkex.AbortExtension("Select a number created by Page Numbering Pro first.")
        selected_mode = o.scope == "selected" or (o.scope == "auto" and target is not None and
                        (o.placement_mode == "manual" or o.renumber_following))
        source = source_page = anchor = None
        if o.placement_mode == "template":
            if o.template_source == "selected":
                texts = [node for node in self.svg.iter() if isinstance(node, inkex.TextElement)]
                source = self.selected_text(texts)
                if source is None:
                    raise inkex.AbortExtension("Select a text number as a template, or choose First existing number.")
            else:
                source = next((existing_for_page(page, index) for index, page in enumerate(pages)
                               if existing_for_page(page, index) is not None), None)
                if source is None:
                    raise inkex.AbortExtension("No managed number exists yet. Select a text number as a template or create page numbers first.")
            self.number_value(source)
            anchor = self.template_anchor(source)
            source_page = self.template_page(source, pages, anchor)

        def make(page, value, old):
            identifier = old.get("id") if old is not None else None
            if source is not None:
                return self.make_template_number(source, source_page, anchor, page, value, identifier)
            return self.make_number(page, value, sx, sy, identifier)

        planned = []
        preserved = []
        if selected_mode:
            page = self.page_for_number(target, pages)
            value = o.selected_number if o.change_selected_value else self.number_value(target)
            index = pages.index(page)
            if o.renumber_following and value + len(pages) - index - 1 > 999999:
                raise inkex.AbortExtension("Following numbers exceed 999999. Enter a smaller number.")
            planned.append((target, make(page, value, target)))
            if o.renumber_following:
                for next_index in range(index + 1, len(pages)):
                    next_page = pages[next_index]
                    old = existing_for_page(next_page, next_index)
                    next_value = value + next_index - index
                    if old is None:
                        planned.append((None, make(next_page, next_value, None)))
                    else:
                        new = deepcopy(old)
                        replace_number_content(new, next_value, number_content(old), o.minimum_digits)
                        self.mark_number(new, next_page, next_value, old.get("id"))
                        preserved.append((old, new))
            removals = []
        else:
            start = o.start_number if source is None else self.number_value(source) - pages.index(source_page)
            if not 0 <= start <= 999999 - len(pages) + 1:
                raise inkex.AbortExtension("The sequence must stay between 0 and 999999. Adjust the start number or template value.")
            chosen = []
            for index, page in enumerate(pages):
                old = source if source is not None and page is source_page else existing_for_page(page, index)
                if old is not None:
                    chosen.append(old)
                planned.append((old, make(page, start + index, old)))
            removals = [node for node in existing if node not in chosen]
        # No document mutations before all options/pages/new numbers have been validated.
        layer = next((element for element in reversed(self.svg)
                      if isinstance(element, inkex.Group) and element.get(MARKER) == "layer"), None)
        if source is not None:
            # Moving between groups must not multiply opacity on each rerun.
            layer_opacity = effective_opacity(self.style_snapshot[layer if layer is not None else self.svg])
            if layer_opacity == 0 or any(float(new.style["opacity"]) > layer_opacity + 1e-12
                                         for _, new in planned):
                # An SVG child cannot undo a darker parent. Use a fresh neutral
                # numbering layer; any unrelated artwork in the old layer stays.
                layer = None
                layer_opacity = effective_opacity(self.style_snapshot[self.svg])
            for _, new in planned:
                new.style["opacity"] = svg_number(float(new.style["opacity"]) / layer_opacity if layer_opacity else 1)
        try:
            parent_transform = inkex.Transform()
            if layer is not None:
                parent_transform = root_transform(layer)
            if any(not math.isfinite(value) for value in parent_transform.to_hexad()):
                raise ValueError("Invalid layer transform")
            parent_inverse = -parent_transform
        except (ValueError, ZeroDivisionError) as error:
            raise inkex.AbortExtension("Invalid numbering layer transform. Remove the zero scale and try again.") from error
        if layer is None:
            layer = inkex.Layer()
            layer.set("id", self.unique_id("page-numbering"))
            layer.set(MARKER, "layer")
            layer.set("inkscape:label", "Page Numbering")
            self.svg.append(layer)
        elif layer.get("inkscape:label") == "ترقيم الصفحات":
            # Upgrade the generated label while keeping user-renamed layers.
            layer.set("inkscape:label", "Page Numbering")
        for page in pages:
            if page.element is not None and page.element.get("id") is None:
                page.element.set("id", page.key)
        # Keep a layer users have transformed themselves usable: compensate for its transform.
        for old, new in planned:
            combined = parent_inverse @ inkex.Transform(new.attrib.get("transform"))
            set_transform(new, combined)
            if old is not None:
                old.getparent().remove(old)
            layer.append(new)
        for old, new in preserved:
            # Following numbers keep their original parent, position and formatting.
            parent = old.getparent()
            parent.replace(old, new)
        for node in removals:
            node.getparent().remove(node)
        layer.set("data-page-numbering-version", VERSION)


if __name__ == "__main__":
    PageNumberingPro().run()
