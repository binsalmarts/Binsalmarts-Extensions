#!/usr/bin/env python3
"""Create native Inkscape pages with uniform or mixed sizes in a grid."""
from dataclasses import dataclass
import math
import re
import uuid

import inkex

VERSION = "1.0.0"
MARKER = "data-artboard-maker-pro"
BATCH = "data-artboard-maker-batch"
ACTIVE_BATCH = "data-artboard-maker-active-batch"
MAX_PAGES = 1000
UNITS = {"px": 1.0, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0}
# Presets are defined in physical pixels independently of the custom unit.
PRESETS = {
    "a3": (297 * UNITS["mm"], 420 * UNITS["mm"]),
    "a4": (210 * UNITS["mm"], 297 * UNITS["mm"]),
    "a5": (148 * UNITS["mm"], 210 * UNITS["mm"]),
    "letter": (8.5 * 96, 11 * 96),
    "tabloid": (11 * 96, 17 * 96),
    "square": (1080, 1080),
    "story": (1080, 1920),
    "full_hd": (1920, 1080),
    "web": (1440, 900),
    "business_card": (85 * UNITS["mm"], 55 * UNITS["mm"]),
}
DIMENSION = r"(\d+(?:\.\d*)?|\.\d+)\s*(px|mm|cm|in)?"
SIZE_PATTERN = re.compile(r"\s*" + DIMENSION + r"\s*[x×]\s*" + DIMENSION + r"\s*", re.I)


def svg_number(value):
    return format(float(value), ".12g")


def bounded(value, low, high, label):
    if not math.isfinite(value) or not low <= value <= high:
        raise inkex.AbortExtension(f"{label} must be between {low} and {high}.")


def parse_sizes(text, default_unit):
    """Read a semicolon/newline list of dimensions or preset keys."""
    entries = [entry.strip() for entry in re.split(r"[;\n]+", text) if entry.strip()]
    if not entries:
        raise inkex.AbortExtension("Enter at least one mixed size, such as 1080x1080; 1080x1920.")
    if len(entries) > MAX_PAGES:
        raise inkex.AbortExtension(f"The mixed size list is limited to {MAX_PAGES} entries.")
    sizes = []
    for entry in entries:
        key = entry.lower().replace(" ", "_")
        if key in PRESETS:
            sizes.append(PRESETS[key])
            continue
        match = SIZE_PATTERN.fullmatch(entry)
        if not match:
            raise inkex.AbortExtension(f"Invalid size '{entry}'. Use WIDTHxHEIGHT, optional units, or a preset such as A4.")
        width, width_unit, height, height_unit = match.groups()
        # A trailing unit applies to both dimensions: 210x297mm.
        width_unit = (width_unit or height_unit or default_unit).lower()
        height_unit = (height_unit or width_unit).lower()
        size = (float(width) * UNITS[width_unit], float(height) * UNITS[height_unit])
        for value in size:
            bounded(value, 0.01, 1_000_000, "Artboard dimension (px)")
        sizes.append(size)
    return sizes


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float


def grid_rectangles(sizes, rows, columns, gap_x, gap_y, order="rows", alignment="start"):
    """Aligned tracks: gaps separate the widest column and tallest row."""
    cells = []
    for index in range(rows * columns):
        row, column = divmod(index, columns) if order == "rows" else (index % rows, index // rows)
        width, height = sizes[index % len(sizes)]
        cells.append((row, column, width, height))
    widths = [max(w for r, c, w, h in cells if c == column) for column in range(columns)]
    heights = [max(h for r, c, w, h in cells if r == row) for row in range(rows)]
    xs, ys = [0.0], [0.0]
    for width in widths[:-1]:
        xs.append(xs[-1] + width + gap_x)
    for height in heights[:-1]:
        ys.append(ys[-1] + height + gap_y)
    factor = {"start": 0, "center": 0.5, "end": 1}[alignment]
    return [Rect(xs[c] + (widths[c] - w) * factor, ys[r] + (heights[r] - h) * factor, w, h)
            for r, c, w, h in cells]


class ArtboardMakerPro(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="layout")
        pars.add_argument("--rows", type=int, default=2)
        pars.add_argument("--columns", type=int, default=3)
        pars.add_argument("--gap_x", type=float, default=40)
        pars.add_argument("--gap_y", type=float, default=40)
        pars.add_argument("--order", default="rows")
        pars.add_argument("--cell_alignment", default="start")
        pars.add_argument("--size_mode", default="uniform")
        pars.add_argument("--preset", default="custom")
        pars.add_argument("--width", type=float, default=1080)
        pars.add_argument("--height", type=float, default=1080)
        pars.add_argument("--unit", default="px")
        pars.add_argument("--swap_dimensions", type=inkex.Boolean, default=False)
        pars.add_argument("--mixed_sizes", default="1080x1080; 1080x1920; 1920x1080")
        pars.add_argument("--action", default="update")
        pars.add_argument("--position", default="auto")
        pars.add_argument("--origin_x", type=float, default=0)
        pars.add_argument("--origin_y", type=float, default=0)
        pars.add_argument("--label_prefix", default="Artboard")

    def validate_options(self):
        o = self.options
        for value, low, high, label in (
            (o.rows, 1, 100, "Rows"), (o.columns, 1, 100, "Columns"),
            (o.gap_x, 0, 100000, "Horizontal gap (px)"), (o.gap_y, 0, 100000, "Vertical gap (px)"),
            (o.width, 0.01, 100000, "Width"), (o.height, 0.01, 100000, "Height"),
            (o.origin_x, -1000000, 1000000, "Origin X (px)"),
            (o.origin_y, -1000000, 1000000, "Origin Y (px)"),
        ):
            bounded(value, low, high, label)
        if o.rows * o.columns > MAX_PAGES:
            raise inkex.AbortExtension(f"Rows × Columns must not exceed {MAX_PAGES} artboards.")
        for value, allowed, label in (
            (o.order, ("rows", "columns"), "fill order"),
            (o.cell_alignment, ("start", "center", "end"), "cell alignment"),
            (o.size_mode, ("uniform", "mixed"), "size mode"),
            (o.preset, ("custom", *PRESETS), "size preset"),
            (o.unit, UNITS, "unit"), (o.action, ("update", "append", "replace_all"), "page action"),
            (o.position, ("auto", "custom"), "position"),
        ):
            if value not in allowed:
                raise inkex.AbortExtension(f"Unknown {label}.")
        if not o.label_prefix.strip() or any(ord(c) < 32 for c in o.label_prefix):
            raise inkex.AbortExtension("Enter a nonempty artboard name prefix without control characters.")
        if o.size_mode == "mixed":
            sizes = parse_sizes(o.mixed_sizes, o.unit)
            if len(sizes) > o.rows * o.columns:
                raise inkex.AbortExtension("The size list has more entries than Rows × Columns. Increase the grid or shorten the list.")
        else:
            sizes = [PRESETS[o.preset] if o.preset != "custom" else
                     (o.width * UNITS[o.unit], o.height * UNITS[o.unit])]
        if o.swap_dimensions:
            sizes = [(h, w) for w, h in sizes]
        return sizes

    def document_geometry(self):
        try:
            width, height = self.svg.viewport_width, self.svg.viewport_height
            viewbox = self.svg.get_viewbox()
            if viewbox == [0, 0, 0, 0]:
                viewbox = [0, 0, width, height]
            vx, vy, vw, vh = viewbox
            if any(not math.isfinite(v) for v in (*viewbox, width, height)) or min(vw, vh, width, height) <= 0:
                raise ValueError("Invalid dimensions")
            return viewbox, width / vw, height / vh
        except (ValueError, TypeError, ZeroDivisionError) as error:
            raise inkex.AbortExtension("Cannot read document dimensions. Check the page width, height and viewBox.") from error

    def native_pages(self, namedview):
        pages = namedview.findall(inkex.addNS("page", "inkscape")) if namedview is not None else []
        for page in pages:
            try:
                values = (page.x, page.y, page.width, page.height)
                if any(not math.isfinite(v) for v in values) or min(page.width, page.height) <= 0:
                    raise ValueError("Invalid page")
            except (ValueError, TypeError) as error:
                raise inkex.AbortExtension("An existing page has invalid dimensions. Correct it before creating artboards.") from error
        return pages

    def root_size_attributes(self, first, viewbox, sx, sy):
        # Maintain the SVG scale and viewBox origin: resizing the page must not
        # scale or translate existing artwork. Nonuniform scales use PAR=none.
        par = self.svg.get("preserveAspectRatio", "xMidYMid meet")
        if "none" not in par.split() and not math.isclose(sx, sy, rel_tol=1e-9):
            raise inkex.AbortExtension("To resize this document, match its page and viewBox proportions or use preserveAspectRatio='none'.")
        attributes = {"viewBox": " ".join(map(svg_number, (viewbox[0], viewbox[1], first.width, first.height)))}
        for name, value in (("width", first.width * sx), ("height", first.height * sy)):
            _, unit = inkex.units.parse_unit(self.svg.get(name, ""), default_unit="px")
            if unit not in UNITS and unit not in ("pt", "pc", "q"):
                unit = "px"
            attributes[name] = svg_number(inkex.units.convert_unit(str(value) + "px", unit)) + unit
        return attributes

    def effect(self):
        o = self.options
        sizes = self.validate_options()
        viewbox, sx, sy = self.document_geometry()
        namedview = self.svg.find(inkex.addNS("namedview", "sodipodi"))
        pages = self.native_pages(namedview)
        managed = [p for p in pages if p.get(MARKER) == "page" and p.get(BATCH)]
        active = namedview.get(ACTIVE_BATCH) if namedview is not None else None
        if active not in {p.get(BATCH) for p in managed}:
            active = managed[-1].get(BATCH) if managed else None
        previous = [p for p in managed if p.get(BATCH) == active] if o.action == "update" else []
        removals = pages if o.action == "replace_all" else previous
        retained = [p for p in pages if p not in removals]
        preserve_implicit = not pages and o.action == "append"
        if len(retained) + int(preserve_implicit) + o.rows * o.columns > MAX_PAGES:
            raise inkex.AbortExtension(f"The resulting document would exceed {MAX_PAGES} pages.")
        if o.position == "custom":
            origin = (o.origin_x / sx, o.origin_y / sy)
        elif previous:
            origin = (previous[0].x, previous[0].y)
        elif retained:
            origin = (max(p.x + p.width for p in retained) + o.gap_x / sx, min(p.y for p in retained))
        elif preserve_implicit:
            origin = (viewbox[2] + o.gap_x / sx, 0)
        else:
            origin = (0, 0)
        rectangles = grid_rectangles(sizes, o.rows, o.columns, o.gap_x, o.gap_y, o.order, o.cell_alignment)
        rectangles = [Rect(origin[0] + r.x / sx, origin[1] + r.y / sy, r.width / sx, r.height / sy)
                      for r in rectangles]
        resize_root = not retained and not preserve_implicit
        if previous and pages[0] in previous and abs(previous[0].x) < 1e-9 and abs(previous[0].y) < 1e-9:
            resize_root = abs(rectangles[0].x) < 1e-9 and abs(rectangles[0].y) < 1e-9
        root_attributes = self.root_size_attributes(rectangles[0], viewbox, sx, sy) if resize_root else {}
        batch = active if previous else "artboard-grid-" + uuid.uuid4().hex
        reserved_ids = set(self.svg.get_ids())
        planned = []
        for index, rect in enumerate(rectangles):
            page = previous[index] if index < len(previous) else inkex.Page()
            attributes = {key: svg_number(getattr(rect, key)) for key in ("x", "y", "width", "height")}
            if not page.get("id"):
                identifier = self.svg.get_unique_id("artboard", blacklist=reserved_ids)
                reserved_ids.add(identifier)
                attributes["id"] = identifier
            attributes.update({MARKER: "page", BATCH: batch, "data-artboard-maker-version": VERSION,
                               inkex.addNS("label", "inkscape"): f"{o.label_prefix.strip()} {index + 1}"})
            planned.append((page, attributes))
        # Commit only after validating every option, page, dimension and root size.
        if namedview is None:
            namedview = inkex.NamedView()
            self.svg.insert(0, namedview)
        if preserve_implicit:
            original = inkex.Page(x="0", y="0", width=svg_number(viewbox[2]), height=svg_number(viewbox[3]))
            original.set("id", self.svg.get_unique_id("original-page", blacklist=reserved_ids))
            namedview.append(original)
        for key, value in root_attributes.items():
            self.svg.set(key, value)
        for page in removals:
            if page not in previous[:len(rectangles)]:
                namedview.remove(page)
        for page, attributes in planned:
            for key, value in attributes.items():
                page.set(key, value)
            if page.getparent() is None:
                namedview.append(page)
        namedview.set(ACTIVE_BATCH, batch)


if __name__ == "__main__":
    ArtboardMakerPro().run()
