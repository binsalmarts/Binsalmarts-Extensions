#!/usr/bin/env python3
"""Editable, geometric logo construction diagrams for Inkscape 1.4+.

Only this module and its two INX files are needed at runtime. No renderer,
network access, external Python packages or source-object mutation is used.
"""
from dataclasses import dataclass
import hashlib
import io
import json
import math

import inkex
from lxml import etree

VERSION = "1.0.0"
MARKER = "data-logo-construction"
REFERENCE = "data-logo-construction-reference"
KEY = "data-logo-construction-key"
MAX_SHAPES = 2000
MAX_NODES = 30000
MAX_DIMENSIONS = 500
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
CONTAINERS = {"g", "a"}
IGNORED = {"title", "desc", "metadata", "defs", "namedview"}


def number(value):
    return format(float(value), ".12g")


def abort(message):
    raise inkex.AbortExtension(message)


def bounded(value, low, high, label):
    if not math.isfinite(value) or not low <= value <= high:
        abort(f"{label}: {low} … {high}.")


def color(value, property_name):
    """Accept the INX RGBA integer, or a CSS color when invoked via CLI."""
    try:
        raw = str(value).strip()
        if raw.startswith("0x") or raw.lstrip("-").isdigit():
            packed = int(raw, 0) if raw.startswith("0x") else int(raw)
            if not 0 <= packed <= 0xFFFFFFFF:
                raise ValueError()
            rgb = tuple((packed >> shift) & 255 for shift in (24, 16, 8))
            alpha = (packed & 255) / 255
        else:
            rgba = inkex.Color(raw).to_rgba()
            if len(rgba) != 4:
                raise ValueError()
            rgb, alpha = rgba[:3], rgba[3]
        return {property_name: "#{:02x}{:02x}{:02x}".format(*rgb),
                property_name + "-opacity": number(alpha)}
    except (ValueError, KeyError, TypeError) as error:
        raise inkex.AbortExtension(f"لون غير صالح / Invalid color: {value}") from error


def ratio_label(value, unit, precision):
    ratio = value / unit
    text = f"{ratio:.{precision}f}".rstrip("0").rstrip(".") if precision else f"{ratio:.0f}"
    if float(text) == 0 and ratio > 0:
        text = f"{ratio:.{max(1, precision)}g}"
    return text + "X"


def document_transform(element, root):
    """Read matrices without Inkex's attribute-bound transform callbacks.

    Accessing element.transform can normalize the original attribute and round
    matrix values. Detached matrices preserve source XML and full precision.
    """
    chain = []
    while element is not root:
        chain.append(element)
        element = element.getparent()
    result = inkex.Transform()
    for item in reversed(chain):
        result = result @ inkex.Transform(item.attrib.get("transform"))
    return result


@dataclass
class Shape:
    element: object
    path: object
    box: object
    nodes: list


@dataclass
class Dimension:
    axis: str
    start: float
    end: float
    origin: float
    kind: str
    source: str = ""
    lane: int = 0


class LogoConstruction(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="geometry")
        pars.add_argument("--mode", choices=("diagram", "reference"), default="diagram")
        pars.add_argument("--reference_id", default="")
        pars.add_argument("--reference_dimension", choices=("width", "height"), default="width")
        pars.add_argument("--component_scope", choices=("children", "leaves", "selection"), default="children")
        pars.add_argument("--action", choices=("replace", "append"), default="replace")
        bools = {"show_alignment": True, "show_axes": True, "horizontal_axis": True,
                 "vertical_axis": True, "show_nodes": True, "show_dimensions": True,
                 "show_outlines": False, "measure_overall": True, "measure_parts": False,
                 "measure_gaps": True, "measure_reference": True}
        for name, default in bools.items():
            pars.add_argument("--" + name, type=inkex.Boolean, default=default)
        colors = {"alignment_color": "#718096", "axis_color": "#718096",
                  "node_color": "#24354b", "node_fill": "#ffffff",
                  "dimension_color": "#0088ee", "label_color": "#24354b",
                  "outline_color": "#24354b", "background_color": "#f0f3f8"}
        for name, default in colors.items():
            pars.add_argument("--" + name, default=default)
        floats = {"line_width": 0.7, "axis_width": 0.9, "node_width": 0.9,
                  "dimension_width": 1.3, "outline_width": 0.8, "node_size": 4,
                  "font_size": 14, "extension": 0.7, "dimension_offset": 0.4,
                  "lane_spacing": 0.32, "tick_size": 6, "panel_padding": 0.35}
        for name, default in floats.items():
            pars.add_argument("--" + name, type=float, default=default)
        pars.add_argument("--precision", type=int, default=3)
        pars.add_argument("--font_family", default="sans-serif")
        pars.add_argument("--node_shape", choices=("square", "circle"), default="square")
        pars.add_argument("--axis_style", choices=("dotted", "dashed", "solid"), default="dotted")
        pars.add_argument("--dimension_style", choices=("ticks", "arrows", "bar"), default="ticks")
        pars.add_argument("--background", choices=("keep", "panel"), default="keep")
        pars.add_argument("--layer_name", default="Logo Construction · مخطط الشعار")

    def selected_roots(self):
        selected = list(self.svg.selection.values())
        if not selected:
            abort("حدد الشعار أولًا / Select the vector logo first.")
        selected_set = set(selected)
        roots = [el for el in selected if not any(p in selected_set for p in el.iterancestors())]
        for el in roots:
            if any(p.get(MARKER) for p in [el, *el.iterancestors()]):
                abort("حدد الشعار الأصلي، دون طبقة المخطط / Select the original logo, without the diagram layer.")
        return roots

    def validate_context(self, element):
        # Effects on any ancestor also affect the selected element's geometry.
        for el in [element, *element.iterancestors()]:
            if el is self.svg:
                continue
            style = el.specified_style()
            if any(str(style.get(prop, el.get(prop, "none"))) not in ("none", "", "None")
                   for prop in ("clip-path", "mask", "filter")):
                abort("عنصر بقص أو قناع أو مرشح: حضّر نسخة بمسارات فعلية أولًا / "
                      "Clips, masks and filters are unsupported; prepare plain paths first.")
            if el.tag_name == "svg":
                abort("Nested SVG viewports: move the artwork into a normal group first.")
            if style.get("transform", "none") != "none":
                abort("CSS transforms: convert them to SVG transform attributes first.")

    def collect(self, root):
        """Return detached paths in root content coordinates, without editing root."""
        found = []

        def visit(el):
            tag = getattr(el, "tag_name", "")
            if tag in IGNORED or not isinstance(el, inkex.BaseElement):
                return
            if not el.is_visible():
                return
            self.validate_context(el)
            if tag in CONTAINERS:
                for child in el:
                    visit(child)
                return
            if tag not in SHAPES:
                abort(f"عنصر غير مدعوم ({tag}, {el.get('id', '')}). "
                      "حوّل النص إلى مسار، وافصل النسخ المرتبطة، وأزل الصور النقطية. / "
                      "Convert text to paths, unlink clones, and remove raster images.")
            if any("%" in el.attrib.get(attr, "") for attr in
                   ("x", "y", "width", "height", "cx", "cy", "r", "rx", "ry", "x1", "x2", "y1", "y2")):
                abort("Percentage geometry: convert dimensions to absolute SVG units first.")
            try:
                path = el.path.to_absolute().transform(document_transform(el, self.svg))
                box = path.bounding_box()
                nodes = list(path.end_points)
            except (ValueError, TypeError, AttributeError, ZeroDivisionError) as error:
                raise inkex.AbortExtension(f"تعذر قراءة المسار / Invalid path: {el.get('id', '')}") from error
            if box is None:
                return
            values = [box.left, box.top, box.right, box.bottom]
            values += [v for p in nodes for v in p]
            if not all(math.isfinite(v) for v in values):
                abort("المسار يحتوي إحداثيات غير صالحة / Non-finite path coordinates.")
            found.append(Shape(el, path, box, nodes))
            if len(found) > MAX_SHAPES:
                abort(f"Maximum {MAX_SHAPES} paths per selection.")

        visit(root)
        return found

    @staticmethod
    def union(shapes):
        box = None
        for shape in shapes:
            box += shape.box
        return box

    def reference(self, roots):
        ref_id = self.options.reference_id.strip().lstrip("#") or self.svg.get(REFERENCE, "")
        if not ref_id:
            abort("عيّن جزءًا مرجعًا عبر Set X Reference أو أدخل معرّفه. / "
                  "Use Set X Reference on a logo part, or enter its Object ID.")
        ref = self.svg.getElementById(ref_id)
        if ref is None:
            abort(f"مرجع X محذوف أو غير موجود / X reference not found: {ref_id}")
        if not any(ref is root or root in ref.iterancestors() for root in roots):
            abort("يجب أن يكون مرجع X جزءًا من الشعار المحدد / X reference must belong to the selected logo.")
        box = self.union(self.collect(ref))
        if box is None:
            abort("مرجع X خالٍ أو مخفي / X reference is empty or hidden.")
        unit = box.width if self.options.reference_dimension == "width" else box.height
        if not math.isfinite(unit) or unit <= 1e-12:
            abort("بُعد مرجع X يساوي صفرًا؛ اختر العرض/الارتفاع الآخر أو جزءًا آخر. / "
                  "X reference dimension is zero. Choose the other dimension or another part.")
        return ref, box, unit

    def components(self, roots, shapes):
        scope = self.options.component_scope
        if scope == "leaves":
            return [(s.element.get("id", ""), s.box) for s in shapes]
        items = roots
        if scope == "children" and len(roots) == 1 and roots[0].tag_name in CONTAINERS:
            items = list(roots[0])
        result = []
        for el in items:
            box = self.union([s for s in shapes if s.element is el or el in s.element.iterancestors()])
            if box is not None:
                result.append((el.get("id", ""), box))
        return result

    def dimensions(self, box, parts, ref_id, ref_box):
        o = self.options
        result = []
        if o.measure_overall:
            result.extend([Dimension("x", box.left, box.right, box.bottom, "overall"),
                           Dimension("y", box.top, box.bottom, box.right, "overall")])
        if o.measure_reference:
            if o.reference_dimension == "width":
                result.append(Dimension("x", ref_box.left, ref_box.right, ref_box.bottom, "reference", ref_id))
            else:
                result.append(Dimension("y", ref_box.top, ref_box.bottom, ref_box.right, "reference", ref_id))
        if o.measure_parts:
            for source, part in parts:
                result.extend([Dimension("x", part.left, part.right, part.bottom, "part", source),
                               Dimension("y", part.top, part.bottom, part.right, "part", source)])
        if o.measure_gaps:
            for axis in ("x", "y"):
                # A gap is an empty projected interval between neighboring parts
                # that overlap along the perpendicular axis. Never invent gaps
                # between overlapping bounds or unrelated diagonal elements.
                def coords(item):
                    b = item[1]
                    return (b.left, b.right, b.top, b.bottom) if axis == "x" else (b.top, b.bottom, b.left, b.right)
                ordered = sorted(parts, key=lambda item: coords(item)[0])
                for i, (source, part) in enumerate(ordered):
                    _, end, low, high = coords((source, part))
                    candidates = []
                    for other in ordered[i + 1:]:
                        start, _, low2, high2 = coords(other)
                        if start > end + self.unit * 1e-9 and min(high, high2) > max(low, low2):
                            candidates.append((start, other))
                    if candidates:
                        start, (other_id, other) = min(candidates, key=lambda item: item[0])
                        # A third component crossing this interval means it is
                        # not an empty gap, even if its left edge precedes part.
                        blocked = any(a < start - self.unit * 1e-9 and b > end + self.unit * 1e-9
                                      and min(high, d) > max(low, c)
                                      for a, b, c, d in map(coords, ordered)
                                      if b > end + self.unit * 1e-9)
                        if not blocked:
                            result.append(Dimension(axis, end, start, max(high, coords((other_id, other))[3]),
                                                    "gap", source + " " + other_id))
        # Retain reference rulers even when they duplicate a part/overall size.
        unique, seen = [], set()
        for dim in result:
            if dim.end - dim.start <= self.unit * 1e-9:
                continue
            key = (dim.axis, round(dim.start / self.unit, 7), round(dim.end / self.unit, 7), dim.kind)
            if key not in seen:
                unique.append(dim)
                seen.add(key)
        if len(unique) > MAX_DIMENSIONS:
            abort(f"أكثر من {MAX_DIMENSIONS} قياس؛ اختر المجموعات بدل المسارات أو أوقف قياسات الأجزاء. / Too many dimensions.")
        # Allocate non-overlapping label lanes in each axis. Each label gets an
        # estimated text-width envelope; the result remains manually editable.
        for axis in ("x", "y"):
            lanes = []
            for dim in [d for d in unique if d.axis == axis]:
                label = ratio_label(dim.end - dim.start, self.unit, o.precision)
                half = max((dim.end - dim.start) / 2, len(label) * self.font * .34) + self.font * .6
                center = (dim.start + dim.end) / 2
                span = (center - half, center + half)
                lane = next((i for i, spans in enumerate(lanes)
                             if all(span[1] < s[0] or span[0] > s[1] for s in spans)), len(lanes))
                if lane == len(lanes):
                    lanes.append([])
                lanes[lane].append(span)
                dim.lane = lane
        return unique

    def group(self, parent, label, role):
        group = inkex.Group()
        group.set("inkscape:label", label)
        group.set("data-lc-role", role)
        parent.append(group)
        return group

    @staticmethod
    def line(parent, x1, y1, x2, y2, style):
        line = inkex.Line(x1=number(x1), y1=number(y1), x2=number(x2), y2=number(y2))
        line.style = style
        parent.append(line)
        return line

    def text(self, parent, x, y, content, rotation=None):
        text = inkex.TextElement(x=number(x), y=number(y))
        text.text = content
        text.style = {**self.colors["label"], "stroke": "none", "font-size": number(self.font),
                      "font-family": self.options.font_family.strip(), "text-anchor": "middle",
                      "direction": "ltr", "unicode-bidi": "embed"}
        if rotation is not None:
            text.set("transform", f"rotate({rotation},{number(x)},{number(y)})")
        parent.append(text)
        return text

    def stroke(self, kind, width):
        return {**self.colors[kind], "fill": "none", "stroke-width": number(width * self.px),
                "stroke-linecap": "butt", "stroke-linejoin": "round"}

    def draw_dimension(self, parent, dim, box):
        o = self.options
        group = self.group(parent, dim.kind + " · " + dim.source, "dimension")
        value = dim.end - dim.start
        group.attrib.update({"data-lc-axis": dim.axis, "data-lc-kind": dim.kind,
                             "data-lc-value": number(value), "data-lc-ratio": number(value / self.unit),
                             "data-lc-source": dim.source})
        offset = o.dimension_offset * self.unit + dim.lane * self.lane_step
        baseline = (box.bottom if dim.axis == "x" else box.right) + offset
        style = self.stroke("dimension", o.dimension_width)
        extension_style = self.stroke("dimension", max(.15, o.dimension_width * .5))
        a, b, origin = dim.start, dim.end, dim.origin
        tick = o.tick_size * self.px / 2
        if dim.axis == "x":
            project = lambda u, v: (u, v)
        else:
            project = lambda u, v: (v, u)
        for end in (a, b):
            self.line(group, *project(end, origin), *project(end, baseline + tick), extension_style)
        if o.dimension_style == "bar":
            style["stroke-width"] = number(max(o.dimension_width * self.px, 2 * tick))
        self.line(group, *project(a, baseline), *project(b, baseline), style)
        if o.dimension_style == "ticks":
            for end in (a, b):
                self.line(group, *project(end, baseline - tick), *project(end, baseline + tick), style)
        elif o.dimension_style == "arrows":
            size = min(2 * tick, value / 3)
            for end, sign in ((a, 1), (b, -1)):
                path = inkex.PathElement()
                points = [project(end, baseline), project(end + sign * size, baseline - size / 3),
                          project(end + sign * size, baseline + size / 3)]
                path.set("d", "M " + " L ".join(f"{number(x)},{number(y)}" for x, y in points) + " Z")
                path.style = {**color(o.dimension_color, "fill"), "stroke": "none"}
                group.append(path)
        label = ratio_label(value, self.unit, o.precision)
        center = (a + b) / 2
        if dim.axis == "x":
            self.text(group, center, baseline + tick + self.font * 1.15, label)
        else:
            self.text(group, baseline + tick + self.font * 1.15, center, label, -90)

    def configure(self):
        o = self.options
        for name in ("line_width", "axis_width", "node_width", "dimension_width", "outline_width"):
            bounded(getattr(o, name), .05, 100, name)
        for name in ("node_size", "font_size", "tick_size"):
            bounded(getattr(o, name), .1, 500, name)
        for name in ("extension", "panel_padding"):
            bounded(getattr(o, name), 0, 20, name)
        for name in ("dimension_offset", "lane_spacing"):
            bounded(getattr(o, name), .01, 20, name)
        bounded(o.precision, 0, 8, "precision")
        if not o.font_family.strip() or not o.layer_name.strip():
            abort("أدخل اسم الخط والطبقة / Font family and layer name must not be empty.")
        self.px = self.svg.viewport_to_unit("1px")
        self.font = o.font_size * self.px
        self.colors = {name: color(getattr(o, name + "_color"), "fill" if name == "label" else "stroke")
                       for name in ("alignment", "axis", "node", "dimension", "label", "outline")}
        self.colors["node_fill"] = color(o.node_fill, "fill")
        self.colors["background"] = color(o.background_color, "fill")

    def effect(self):
        # Analyze a separate tree: Inkex lazily normalizes styles/transforms
        # even on some reads. The original tree must remain byte-for-byte
        # unchanged apart from newly created layers / stored reference metadata.
        original = self.svg
        selected_ids = [el.get("id") for el in original.selection.values()]
        self.svg = inkex.load_svg(io.BytesIO(etree.tostring(original))).getroot()
        self.svg.selection.set(*selected_ids)
        try:
            result = self.build()
        finally:
            self.svg = original
        if self.options.mode == "reference":
            self.svg.set(REFERENCE, result)
            return
        layer, background, key = result
        if self.options.action == "replace":
            for el in list(self.svg):
                if el.get(MARKER) and el.get(KEY) == key:
                    self.svg.remove(el)
        if background is not None:
            self.svg.insert(0, background)
        self.svg.append(layer)
        for el in [layer, *layer.iterdescendants()] + ([] if background is None else [background, *background.iterdescendants()]):
            el.get_id()

    def build(self):
        roots = self.selected_roots()
        if inkex.Transform(self.svg.attrib.get("transform")):
            abort("Root SVG transform: move it to an artwork group first.")
        if self.svg.get("preserveAspectRatio", "").strip() == "none":
            viewbox = self.svg.get_viewbox()
            if viewbox and not math.isclose(self.svg.viewport_width / viewbox[2],
                                            self.svg.viewport_height / viewbox[3], rel_tol=1e-9):
                abort("Non-uniform root viewport: use a uniform page scale before measuring X.")
        if self.options.mode == "reference":
            if len(roots) != 1:
                abort("حدد جزءًا واحدًا ليكون مرجع X / Select exactly one X reference part.")
            box = self.union(self.collect(roots[0]))
            if box is None or max(box.width, box.height) <= 1e-12:
                abort("مرجع فارغ أو صفري / Empty or zero-size reference.")
            return roots[0].get_id()
        self.configure()
        o = self.options
        if not any((o.show_alignment, o.show_axes and (o.horizontal_axis or o.vertical_axis),
                    o.show_nodes, o.show_dimensions and any((o.measure_overall, o.measure_parts,
                    o.measure_gaps, o.measure_reference)), o.show_outlines)):
            abort("فعّل عنصرًا واحدًا على الأقل / Enable at least one diagram element.")
        shapes = [s for root in roots for s in self.collect(root)]
        if not shapes:
            abort("لا توجد مسارات ظاهرة / No visible vector paths in the selection.")
        if len(shapes) > MAX_SHAPES or sum(len(s.nodes) for s in shapes) > MAX_NODES:
            abort(f"Selection limit: {MAX_SHAPES} paths / {MAX_NODES} nodes. Split the logo into smaller selections.")
        ref, ref_box, self.unit = self.reference(roots)
        box = self.union(shapes)
        parts = self.components(roots, shapes)
        self.lane_step = max(o.lane_spacing * self.unit, self.font * 2.5 + o.tick_size * self.px)
        dimensions = self.dimensions(box, parts, ref.get("id"), ref_box) if o.show_dimensions else []
        source_ids = sorted(root.get_id() for root in roots)
        key = hashlib.sha256(json.dumps(source_ids).encode()).hexdigest()[:20]
        layer = inkex.Layer()
        layer.set("inkscape:label", o.layer_name.strip())
        layer.attrib.update({MARKER: VERSION, KEY: key, "data-lc-role": "diagram",
                             "data-lc-sources": json.dumps(source_ids), "data-lc-reference": ref.get("id"),
                             "data-lc-unit": number(self.unit), "data-lc-unit-dimension": o.reference_dimension})
        title = inkex.Title()
        title.text = "Logo Construction: geometric bounds in SVG document coordinates; editable annotations."
        layer.append(title)
        margin = o.extension * self.unit
        left, right, top, bottom = box.left - margin, box.right + margin, box.top - margin, box.bottom + margin
        if o.show_outlines:
            group = self.group(layer, "Path outlines · حدود المسارات", "outlines")
            for shape in shapes:
                path = inkex.PathElement()
                path.path = shape.path
                path.style = self.stroke("outline", o.outline_width)
                group.append(path)
        if o.show_alignment:
            group = self.group(layer, "Alignment · المحاذاة", "alignment")
            style = self.stroke("alignment", o.line_width)
            xs = {box.left, box.right, *(v for _, b in parts for v in (b.left, b.right))}
            ys = {box.top, box.bottom, *(v for _, b in parts for v in (b.top, b.bottom))}
            for x in sorted(xs):
                self.line(group, x, top, x, bottom, style)
            for y in sorted(ys):
                self.line(group, left, y, right, y, style)
        if o.show_axes and (o.horizontal_axis or o.vertical_axis):
            group = self.group(layer, "Axes · المحاور", "axes")
            style = self.stroke("axis", o.axis_width)
            if o.axis_style != "solid":
                dash = (1, 4) if o.axis_style == "dotted" else (6, 4)
                style["stroke-dasharray"] = ",".join(number(v * self.px) for v in dash)
            if o.horizontal_axis:
                self.line(group, left, box.center_y, right, box.center_y, style)
            if o.vertical_axis:
                self.line(group, box.center_x, top, box.center_x, bottom, style)
        if o.show_nodes:
            group = self.group(layer, "Path nodes · عقد المسارات", "nodes")
            size = o.node_size * self.px
            seen = set()
            for shape in shapes:
                for point in shape.nodes:
                    loc = (round(point.x, 9), round(point.y, 9))
                    if loc in seen:
                        continue
                    seen.add(loc)
                    if o.node_shape == "circle":
                        node = inkex.Circle(cx=number(point.x), cy=number(point.y), r=number(size / 2))
                    else:
                        node = inkex.Rectangle(x=number(point.x - size / 2), y=number(point.y - size / 2),
                                               width=number(size), height=number(size))
                    node.style = {**self.stroke("node", o.node_width), **self.colors["node_fill"]}
                    node.set("data-lc-source", shape.element.get("id", ""))
                    group.append(node)
        if o.show_dimensions:
            group = self.group(layer, "Dimensions · القياسات", "dimensions")
            for dim in dimensions:
                self.draw_dimension(group, dim, box)
        background = None
        if o.background == "panel":
            # Background is a separate bottom layer so it never covers the logo.
            background = inkex.Layer()
            background.set("inkscape:label", o.layer_name.strip() + " · Background")
            background.attrib.update({MARKER: VERSION, KEY: key, "data-lc-role": "background"})
            last_x = max((d.lane for d in dimensions if d.axis == "x"), default=-1)
            last_y = max((d.lane for d in dimensions if d.axis == "y"), default=-1)
            extra = o.dimension_offset * self.unit + self.font * 2 + o.tick_size * self.px
            bottom = max(bottom, box.bottom + extra + max(0, last_x) * self.lane_step) if last_x >= 0 else bottom
            right = max(right, box.right + extra + max(0, last_y) * self.lane_step) if last_y >= 0 else right
            padding = o.panel_padding * self.unit
            panel = inkex.Rectangle(x=number(left - padding), y=number(top - padding),
                                   width=number(right - left + 2 * padding), height=number(bottom - top + 2 * padding))
            panel.style = {**self.colors["background"], "stroke": "none"}
            background.append(panel)
        return layer, background, key


if __name__ == "__main__":
    LogoConstruction().run()
