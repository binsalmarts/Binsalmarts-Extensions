#!/usr/bin/env python3
"""Vector shape/color blends, fitted spines and reversible refresh for Inkscape."""
from bisect import bisect_left
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import io
import json
import math
import uuid

import inkex
from inkex.bezier import csplength
from inkex.paths import Move, Line
from inkex.tween import EqualSubsegmentsInterpolator
from lxml import etree

VERSION = "1.1.0"
MARKER = "data-blend-tool-pro"
SOURCES = "data-blend-sources"
SETTINGS = "data-blend-settings"
SPINE = "data-blend-spine-reference"
KEY = "data-blend-key"
MAX_STEPS = 1000
MAX_OUTPUT_PATHS = 10000
MAX_CURVE_NODES = 300000
MAX_SOURCE_NODES = 2000
SHAPES = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}
BOOL_DEFAULTS = {"blend_fill": True, "blend_stroke": True, "blend_opacity": True,
                 "auto_match": True, "reverse_target": False, "reverse_objects": False,
                 "reverse_stack": False, "follow_spine": False, "reverse_spine": False,
                 "show_spine": False, "shade_stroke": True,
                 "shade_endpoints": True, "cast_shadow": False}
FLOAT_DEFAULTS = {"distance": 20, "smooth_spacing": 2, "position_bias": 1,
                  "shape_bias": 1, "color_bias": 1, "spine_start": 0, "spine_end": 100,
                  "shading_strength": .9, "light_angle": 225, "light_elevation": 50,
                  "ambient": .22, "gloss": .5, "shininess": 24,
                  "shadow_distance": 12, "shadow_opacity": .18}
CHOICES = {"spacing": ("steps", "distance", "smooth"),
           "order": ("stack", "left_right", "top_bottom"),
           "shape_mode": ("morph", "scale", "copy"),
           "orientation": ("page", "path"), "color_space": ("srgb", "linear_rgb"),
           "on_apply": ("replace", "append"), "shading_mode": ("off", "tube", "sphere")}
SETTING_NAMES = [*BOOL_DEFAULTS, *FLOAT_DEFAULTS, *CHOICES,
                "steps", "target_shift", "extra_turns", "source_ids", "spine_id", "group_name"]


def num(value):
    return format(float(value), ".12g")


def fail(message):
    raise inkex.AbortExtension(message)


def bounded(value, low, high, name):
    if not math.isfinite(value) or not low <= value <= high:
        fail(f"{name}: {low} … {high}.")


def transform_to_root(element, root):
    chain = []
    while element is not root:
        chain.append(element)
        element = element.getparent()
    result = inkex.Transform()
    for item in reversed(chain):
        result = result @ inkex.Transform(item.attrib.get("transform"))
    return result


def translate(x, y):
    return inkex.Transform((1, 0, 0, 1, x, y))


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def paint_value(style, key):
    try:
        paint = style(key)
        if paint is None or str(paint) == "none":
            return None
        rgba = inkex.Color(paint).to_rgba()
        return tuple(float(c) for c in rgba[:3]) + (float(rgba[3]),)
    except (TypeError, ValueError, KeyError) as error:
        raise inkex.AbortExtension("استخدم تعبئات وحدودًا بألوان مسطحة / "
                                   "Use solid colors; gradients and patterns are not supported.") from error


def mix(a, b, t):
    return a + (b - a) * t


def mix_paint(a, b, t, linear=False):
    if a is None and b is None:
        return "none", 0
    if a is None:
        a = (*b[:3], 0)
    if b is None:
        b = (*a[:3], 0)
    channels = []
    for left, right in zip(a[:3], b[:3]):
        if linear:
            def decode(v):
                v /= 255
                return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
            value = mix(decode(left), decode(right), t)
            value = 12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055
            channels.append(round(value * 255))
        else:
            channels.append(round(mix(left, right, t)))
    return "#{:02x}{:02x}{:02x}".format(*channels), mix(a[3], b[3], t)


@dataclass
class Leaf:
    path: object
    style: dict
    fill: object
    stroke: object
    fill_opacity: float
    stroke_opacity: float
    opacity: float
    stroke_width: float


@dataclass
class Source:
    element: object
    leaves: list
    box: object

    @property
    def center(self):
        return (self.box.center_x, self.box.center_y)


class ArcTable:
    """Adaptive cubic flattening; positions are interpolated by arc length."""
    def __init__(self, path, tolerance):
        csp = path.to_superpath()
        if len(csp) != 1 or len(csp[0]) < 2:
            fail("مسار التوزيع يجب أن يكون منحنى واحدًا مفتوحًا / Spine must be one open subpath.")
        self.points = [tuple(csp[0][0][1])]
        self.tangents = []

        def flatten(p0, p1, p2, p3, depth=0):
            chord = distance(p0, p3)
            polygon = distance(p0, p1) + distance(p1, p2) + distance(p2, p3)
            if depth >= 18 or polygon - chord <= tolerance:
                if distance(self.points[-1], p3) > 1e-12:
                    self.points.append(tuple(p3))
                    def direction(pairs):
                        for first, second in pairs:
                            if distance(first, second) > 1e-12:
                                return math.atan2(second[1] - first[1], second[0] - first[0])
                        return 0
                    self.tangents.append((direction(((p0, p1), (p0, p2), (p0, p3))),
                                          direction(((p2, p3), (p1, p3), (p0, p3)))))
                if len(self.points) > 20000:
                    fail("Spine too complex; simplify it first.")
                return
            midpoint = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            a, b, c = midpoint(p0, p1), midpoint(p1, p2), midpoint(p2, p3)
            d, e = midpoint(a, b), midpoint(b, c)
            f = midpoint(d, e)
            flatten(p0, a, d, f, depth + 1)
            flatten(f, e, c, p3, depth + 1)

        for first, second in zip(csp[0], csp[0][1:]):
            flatten(first[1], first[2], second[0], second[1])
        self.lengths = [0]
        for a, b in zip(self.points, self.points[1:]):
            self.lengths.append(self.lengths[-1] + distance(a, b))
        self.length = self.lengths[-1]
        if self.length <= 1e-10:
            fail("مسار توزيع صفري / Spine has zero length.")

    def at(self, fraction, smooth_tangent=False):
        target = min(1, max(0, fraction)) * self.length
        index = max(1, min(len(self.points) - 1, bisect_left(self.lengths, target)))
        a, b = self.points[index - 1:index + 1]
        t = (target - self.lengths[index - 1]) / (self.lengths[index] - self.lengths[index - 1])
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        if smooth_tangent:
            start, end = self.tangents[index - 1]
            delta = (end - start + math.pi) % (2 * math.pi) - math.pi
            angle = start + delta * t
        return (mix(a[0], b[0], t), mix(a[1], b[1], t)), angle


def closed(path):
    return bool(path and path[-1].letter.lower() == "z")


def rotate_closed(path, shift):
    nodes = deepcopy(path.to_superpath()[0])
    if distance(nodes[0][1], nodes[-1][1]) < 1e-8:
        nodes[0][0] = nodes[-1][0][:]
        nodes.pop()
    shift %= len(nodes)
    nodes = nodes[shift:] + nodes[:shift]
    nodes.append(deepcopy(nodes[0]))
    return inkex.CubicSuperPath([nodes]).to_path()


def signed_area(path):
    points = [p[1] for p in path.to_superpath()[0]]
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))


def aligned_target(start, end, automatic, reverse, shift):
    if automatic and closed(start):
        if signed_area(start) * signed_area(end) < 0:
            end = end.reverse()
        a, b = start.bounding_box(), end.bounding_box()
        point = next(start.end_points)
        target = ((point.x - a.center_x) / max(a.width, 1e-12),
                  (point.y - a.center_y) / max(a.height, 1e-12))
        nodes = end.to_superpath()[0][:-1]
        match = min(range(len(nodes)), key=lambda i: distance(
            target, ((nodes[i][1][0] - b.center_x) / max(b.width, 1e-12),
                     (nodes[i][1][1] - b.center_y) / max(b.height, 1e-12))))
        end = rotate_closed(end, match)
    if reverse:
        end = end.reverse()
    if shift and closed(end):
        end = rotate_closed(end, shift)
    return end


class Morph:
    def __init__(self, start, end, options):
        left, right = start.break_apart(), end.break_apart()
        if len(left) != len(right):
            fail("يجب تطابق عدد المسارات الفرعية / Match the number of subpaths (including holes) in each shape pair.")
        self.parts = []
        self.node_count = 0
        for a, b in zip(left, right):
            if closed(a) != closed(b):
                fail("لا يمكن مزج منحنى مفتوح بمسار مغلق / Each path pair must both be open or both closed.")
            if min(csplength(a.to_superpath())[1], csplength(b.to_superpath())[1]) <= 1e-10:
                fail("مسار صفري؛ احذف الأجزاء الفارغة / Remove zero-length subpaths first.")
            b = aligned_target(a, b, options.auto_match, options.reverse_target, options.target_shift)
            try:
                interp = EqualSubsegmentsInterpolator(a, b)
            except (ValueError, IndexError, ZeroDivisionError) as error:
                raise inkex.AbortExtension("تعذر مطابقة العقد؛ بسّط المسارين / Cannot map path nodes. Simplify both shapes.") from error
            self.parts.append((interp, closed(a)))
            self.node_count += sum(len(part) for part in interp.processed_start_path)

    def at(self, t):
        result = inkex.Path()
        for interpolator, is_closed in self.parts:
            path = interpolator.interpolate(t).to_path()
            if is_closed:
                path.close()
            result += path
        return result


class VectorLighting:
    """SVG gradient lighting only: no filters, masks, images or rasterization.

    Tube mode samples a circular cross-section normal to the travel tangent.
    Sphere mode uses a focal radial gradient for isolated rounded beads.
    Gradients live inside the blend so release/replace never leak definitions.
    """
    def __init__(self, options, px, group):
        self.o, self.px = options, px
        self.defs = inkex.Defs()
        self.defs.set('data-blend-role', 'lighting-defs')
        group.append(self.defs)
        self.prefix = 'blend3d-' + uuid.uuid4().hex
        self.count = 0
        azimuth = math.radians(options.light_angle)
        elevation = math.radians(options.light_elevation)
        self.light = (math.cos(azimuth) * math.cos(elevation),
                      math.sin(azimuth) * math.cos(elevation), math.sin(elevation))

    def shade_color(self, base, diffuse, specular):
        o = self.o
        brightness = o.ambient + (1 - o.ambient) * max(0, diffuse)
        result = []
        for channel in base:
            lit = channel * brightness
            lit += (255 - lit) * o.gloss * max(0, specular)
            result.append(round(min(255, max(0, mix(channel, lit, o.shading_strength)))))
        return '#{:02x}{:02x}{:02x}'.format(*result)

    def stops(self, gradient, entries):
        for offset, value in sorted(entries):
            stop = inkex.Stop()
            stop.attrib.update({'offset': num(offset), 'stop-color': value, 'stop-opacity': '1'})
            gradient.append(stop)

    def gradient(self, path, base, tangent, stroke_width=0):
        o = self.o
        box = path.bounding_box()
        if box is None:
            return None
        cx, cy = box.center_x, box.center_y
        if o.shading_mode == 'tube':
            nx, ny = -math.sin(tangent), math.cos(tangent)
            projected = path.transform(inkex.Transform((nx, -ny, ny, nx, 0, 0))).bounding_box()
            low, high = projected.left - stroke_width / 2, projected.right + stroke_width / 2
            if high - low < self.px * 1e-5:
                return None
            center_projection = cx * nx + cy * ny
            gradient = inkex.LinearGradient()
            gradient.attrib.update({'gradientUnits': 'userSpaceOnUse',
                                    'x1': num(cx + (low - center_projection) * nx),
                                    'y1': num(cy + (low - center_projection) * ny),
                                    'x2': num(cx + (high - center_projection) * nx),
                                    'y2': num(cy + (high - center_projection) * ny)})
            lx, ly, lz = self.light
            across = lx * nx + ly * ny
            half_length = math.sqrt(lx * lx + ly * ly + (lz + 1) ** 2)
            half_across, half_z = across / half_length, (lz + 1) / half_length
            offsets = {i / 32 for i in range(33)}
            for x, z in ((across, lz), (half_across, half_z)):
                norm = math.hypot(x, z)
                if norm > 1e-12:
                    offsets.add((x / norm + 1) / 2)
            entries = []
            for offset in offsets:
                u = offset * 2 - 1
                z = math.sqrt(max(0, 1 - u * u))
                diffuse = max(0, u * across + z * lz)
                specular = max(0, u * half_across + z * half_z) ** o.shininess
                entries.append((offset, self.shade_color(base, diffuse, specular)))
            self.stops(gradient, entries)
        else:
            rx = max((box.width + stroke_width) / 2, self.px * .01)
            ry = max((box.height + stroke_width) / 2, self.px * .01)
            lx, ly, lz = self.light
            focal = .65
            gradient = inkex.RadialGradient()
            gradient.attrib.update({'gradientUnits': 'userSpaceOnUse', 'cx': '0', 'cy': '0', 'r': '1',
                                    'fx': num(lx * focal), 'fy': num(ly * focal),
                                    'gradientTransform': f'matrix({num(rx)},0,0,{num(ry)},{num(cx)},{num(cy)})'})
            # A smooth focal dome with an independently controlled specular peak.
            entries = []
            for i in range(33):
                offset = i / 32
                diffuse = max(0, 1 - offset ** 1.7) * (.8 + .2 * lz)
                specular = math.exp(-offset * offset * o.shininess * 2)
                entries.append((offset, self.shade_color(base, diffuse, specular)))
            self.stops(gradient, entries)
        self.count += 1
        gradient_id = self.prefix + '-' + str(self.count)
        gradient.attrib['id'] = gradient_id
        self.defs.append(gradient)
        return 'url(#' + gradient_id + ')'

    def apply(self, element, tangent):
        style = dict(element.style)
        for paint in ('fill', 'stroke'):
            if paint == 'stroke' and not self.o.shade_stroke:
                continue
            value = style.get(paint, 'none')
            if value == 'none' or float(style.get(paint + '-opacity', 1)) <= 0:
                continue
            base = inkex.Color(value).to_rgb()
            width = float(style.get('stroke-width', 0)) if paint == 'stroke' else 0
            shaded = self.gradient(element.path, base, tangent, width)
            if shaded:
                style[paint] = shaded
        element.style = style
        element.set('data-blend-shading', self.o.shading_mode)

    def shadow(self, generated):
        if not self.o.cast_shadow or self.o.shadow_opacity <= 0 or self.o.shadow_distance <= 0:
            return None
        angle = math.radians(self.o.light_angle)
        length = self.o.shadow_distance * self.px
        offset = translate(-math.cos(angle) * length, -math.sin(angle) * length)
        group = inkex.Group()
        group.set('data-blend-role', 'shadow')
        group.set('inkscape:label', '3D · Vector shadow')
        group.style = {'opacity': num(self.o.shadow_opacity)}
        for step in generated:
            for element in step:
                style = dict(element.style)
                shadow = inkex.PathElement()
                shadow.path = element.path.transform(offset)
                style['fill'] = '#000000' if style.get('fill', 'none') != 'none' else 'none'
                style['stroke'] = '#000000' if style.get('stroke', 'none') != 'none' else 'none'
                shadow.style = style
                group.append(shadow)
        return group


class BlendToolPro(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument('--tab', default='blend')
        pars.add_argument('--action', choices=('blend', 'refresh', 'release', 'expand', 'set_spine'), default='blend')
        for name, choices in CHOICES.items():
            pars.add_argument('--' + name, choices=choices, default=choices[0])
        for name, default in BOOL_DEFAULTS.items():
            pars.add_argument('--' + name, type=inkex.Boolean, default=default)
        for name, default in FLOAT_DEFAULTS.items():
            pars.add_argument('--' + name, type=float, default=default)
        pars.add_argument('--steps', type=int, default=12)
        pars.add_argument('--target_shift', type=int, default=0)
        pars.add_argument('--extra_turns', type=int, default=0)
        pars.add_argument('--source_ids', default='')
        pars.add_argument('--spine_id', default='')
        pars.add_argument('--group_name', default='Blend Tool Pro · مزج الأشكال')

    def selected(self):
        selected = list(self.svg.selection.values())
        selected_set = set(selected)
        return [el for el in selected if not any(a in selected_set for a in el.iterancestors())]

    def validate_context(self, el):
        for item in [el, *el.iterancestors()]:
            style = item.specified_style()
            if any(str(style.get(prop, item.get(prop, 'none'))) not in ('none', '', 'None')
                   for prop in ('clip-path', 'mask', 'filter', 'marker-start', 'marker-mid', 'marker-end')):
                fail("القص والأقنعة والمرشحات والعلامات غير مدعومة / Convert clips, masks, filters and markers to plain paths first.")
            if item is not self.svg and item.tag_name == 'svg':
                fail("Move nested SVG artwork into an ordinary group first.")
            if style.get('transform', 'none') != 'none':
                fail("Convert CSS transforms to SVG transform attributes first.")

    def collect(self, element):
        leaves, box = [], None

        def visit(el):
            nonlocal box
            tag = getattr(el, 'tag_name', '')
            if tag in ('title', 'desc', 'metadata', 'defs') or not isinstance(el, inkex.BaseElement):
                return
            if not isinstance(el, inkex.ShapeElement):
                fail(f"Unsupported object: {tag}. Use vector shapes or paths.")
            if any(str(p.cascaded_style().get('display', 'inline')) == 'none'
                   for p in [el, *el.iterancestors()]):
                return
            self.validate_context(el)
            if tag in ('g', 'a'):
                for child in el:
                    visit(child)
                return
            if str(el.specified_style()('visibility')) in ('hidden', 'collapse'):
                return
            if tag not in SHAPES:
                fail("حوّل النص إلى مسار وافصل النسخ المرتبطة / Convert text to paths, unlink clones, and remove raster images.")
            if any('%' in el.attrib.get(k, '') for k in ('x', 'y', 'width', 'height', 'cx', 'cy', 'r', 'rx', 'ry', 'x1', 'x2', 'y1', 'y2')):
                fail("Convert percentage geometry to absolute SVG units first.")
            transform = transform_to_root(el, self.svg)
            path = el.path.to_absolute().transform(transform)
            bounds = path.bounding_box()
            if bounds is None:
                return
            coords = [v for sub in path.to_superpath() for node in sub for point in node for v in point]
            if not all(math.isfinite(v) for v in coords):
                fail("Invalid path coordinates.")
            if len(coords) > MAX_SOURCE_NODES * 6:
                fail(f"Simplify each source shape to at most {MAX_SOURCE_NODES} curve nodes.")
            style = el.specified_style()
            fill, stroke = paint_value(style, 'fill'), paint_value(style, 'stroke')
            base = {key: str(style(key)) for key in ('fill-rule', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit')}
            # Only bake opacity below the output parent. Its own opacity will
            # still apply to the generated group, and must not be counted twice.
            opacity = 1
            for ancestor in [el, *el.iterancestors()]:
                if ancestor is getattr(self, 'output_parent', self.svg):
                    break
                opacity *= float(ancestor.cascaded_style()('opacity'))
            a, b, c, d, _, _ = transform.to_hexad()
            scale = math.sqrt(abs(a * d - b * c))
            if str(style.get('vector-effect', el.get('vector-effect', ''))) == 'non-scaling-stroke':
                scale = self.px
            dash = style('stroke-dasharray')
            base['stroke-dasharray'] = ','.join(num(v * scale) for v in dash) if dash else 'none'
            base['stroke-dashoffset'] = num(el.to_dimensionless(style('stroke-dashoffset')) * scale)
            base['paint-order'] = str(style('paint-order'))
            width = el.to_dimensionless(style('stroke-width')) * scale if stroke is not None else 0
            leaf = Leaf(path, base, fill, stroke, float(style('fill-opacity')), float(style('stroke-opacity')), opacity, width)
            leaves.append(leaf)
            box += bounds

        visit(element)
        if not leaves or box is None:
            fail("عنصر فارغ أو مخفي / A source is empty or hidden.")
        if len(leaves) > 100:
            fail("Maximum 100 shapes per source group. Simplify or split the group.")
        center = (box.center_x, box.center_y)
        for leaf in leaves:
            leaf.path = leaf.path.transform(translate(-center[0], -center[1]))
        return Source(element, leaves, box)

    def spine_path(self, el):
        if el is None or el.tag_name not in SHAPES:
            fail("حدد مسار توزيع صالحًا / Choose a valid spine path or its Object ID.")
        self.validate_context(el)
        path = el.path.to_absolute().transform(transform_to_root(el, self.svg))
        parts = path.break_apart()
        if len(parts) != 1 or closed(parts[0]):
            fail("مسار التوزيع يجب أن يكون واحدًا ومفتوحًا / Spine must be one open subpath.")
        ArcTable(path, self.px * .05)
        return path

    def style_at(self, a, b, t):
        o = self.options
        style = dict(a.style)
        for key, enabled in (('fill', o.blend_fill), ('stroke', o.blend_stroke)):
            ta = t if enabled else 0
            pa, pb = getattr(a, key), getattr(b, key)
            if pa is not None:
                pa = (*pa[:3], pa[3] * getattr(a, key + '_opacity'))
            if pb is not None:
                pb = (*pb[:3], pb[3] * getattr(b, key + '_opacity'))
            value, alpha = mix_paint(pa, pb, ta, o.color_space == 'linear_rgb')
            style[key] = value
            style[key + '-opacity'] = num(alpha)
        style['stroke-width'] = num(mix(a.stroke_width, b.stroke_width, t if o.blend_stroke else 0))
        style['opacity'] = num(mix(a.opacity, b.opacity, t if o.blend_opacity else 0))
        return style

    def endpoint(self, source, tangent, lighting):
        if lighting is None or not self.options.shade_endpoints:
            return None
        group = inkex.Group()
        group.set('data-blend-role', 'endpoint')
        group.set('data-blend-source', source.element.get('id'))
        group.set('inkscape:label', '3D · Endpoint ' + source.element.get('id'))
        for leaf in source.leaves:
            alpha = [paint[3] * opacity for paint, opacity in
                     ((leaf.fill, leaf.fill_opacity), (leaf.stroke, leaf.stroke_opacity)) if paint is not None]
            # Cover only fully opaque originals. Duplicating translucent paint
            # would alter its alpha; those originals deliberately stay untouched.
            if not alpha or leaf.opacity < .999999 or any(value < .999999 for value in alpha):
                continue
            result = inkex.PathElement()
            result.path = leaf.path.transform(translate(*source.center))
            result.style = self.style_at(leaf, leaf, 0)
            lighting.apply(result, tangent)
            group.append(result)
        return group if len(group) else None

    def count_steps(self, a, b, length):
        o = self.options
        if o.spacing == 'steps':
            return o.steps
        if o.spacing == 'distance':
            return max(0, math.ceil(length / (o.distance * self.px)) - 1)
        color_change = 0
        for first, second in zip(a.leaves, b.leaves):
            for key, enabled in (('fill', o.blend_fill), ('stroke', o.blend_stroke)):
                if enabled:
                    l, r = getattr(first, key), getattr(second, key)
                    if l is not None and r is not None:
                        color_change = max(color_change, max(abs(x - y) for x, y in zip(l[:3], r[:3])))
        geometry_motion = max(length, abs(a.box.width - b.box.width), abs(a.box.height - b.box.height))
        if o.shape_mode == 'morph' and any(str(l.path) != str(r.path) for l, r in zip(a.leaves, b.leaves)):
            geometry_motion = max(geometry_motion, max(a.box.width, a.box.height, b.box.width, b.box.height) / 2)
        return min(MAX_STEPS, max(1, math.ceil(max(geometry_motion / (o.smooth_spacing * self.px), color_change)) - 1))

    def fitted_spine(self, source_path, a, b):
        o = self.options
        path = source_path.reverse() if o.reverse_spine else source_path
        table = ArcTable(path, self.px * .05)
        lo, hi = o.spine_start / 100, o.spine_end / 100
        start, _ = table.at(lo)
        end, _ = table.at(hi)
        delta = complex(*end) - complex(*start)
        target = complex(*b.center) - complex(*a.center)
        if abs(delta) < 1e-9 or abs(target) < 1e-9:
            fail("Separate the source centers and choose a non-zero spine range.")
        factor = target / delta
        offset = complex(*a.center) - factor * complex(*start)
        affine = inkex.Transform((factor.real, factor.imag, -factor.imag, factor.real, offset.real, offset.imag))
        angle = math.atan2(factor.imag, factor.real)

        def at(t):
            point, tangent = table.at(mix(lo, hi, t), o.shading_mode != 'off' and o.shading_strength > 0)
            value = factor * complex(*point) + offset
            return (value.real, value.imag), tangent + angle

        preview = inkex.Path([Move(*at(0)[0])])
        for point, traveled in zip(table.points, table.lengths):
            if lo < traveled / table.length < hi:
                preview.append(Line(*affine.apply_to_point(point)))
        preview.append(Line(*at(1)[0]))
        return at, table.length * (hi - lo) * abs(factor), preview

    def validate_options(self):
        o = self.options
        bounded(o.steps, 1, MAX_STEPS, 'steps')
        for name in ('distance', 'smooth_spacing'):
            bounded(getattr(o, name), .1, 100000, name)
        for name in ('position_bias', 'shape_bias', 'color_bias'):
            bounded(getattr(o, name), .1, 10, name)
        for name in ('spine_start', 'spine_end'):
            bounded(getattr(o, name), 0, 100, name)
        if o.spine_start >= o.spine_end:
            fail("Spine start must be smaller than spine end.")
        bounded(o.extra_turns, -10, 10, 'extra_turns')
        bounded(o.target_shift, -2000, 2000, 'target_shift')
        for name in ('shading_strength', 'ambient', 'gloss', 'shadow_opacity'):
            bounded(getattr(o, name), 0, 1, name)
        bounded(o.light_angle, -360, 360, 'light_angle')
        bounded(o.light_elevation, 0, 90, 'light_elevation')
        bounded(o.shininess, 1, 128, 'shininess')
        bounded(o.shadow_distance, 0, 10000, 'shadow_distance')
        if not o.group_name.strip():
            fail("Enter a blend group name.")
        if inkex.Transform(self.svg.attrib.get('transform')):
            fail("Move the root SVG transform to an ordinary group first.")
        if self.svg.get('preserveAspectRatio', '').strip() == 'none':
            v = self.svg.get_viewbox()
            if v and not math.isclose(self.svg.viewport_width / v[2], self.svg.viewport_height / v[3], rel_tol=1e-9):
                fail("Use a uniform root viewport scale first.")

    def build(self):
        o = self.options
        self.px = self.svg.viewport_to_unit('1px')
        selected = self.selected()
        managed = selected[0] if len(selected) == 1 and selected[0].get(MARKER) else None
        if o.action in ('release', 'expand', 'refresh') and managed is None:
            fail("حدد مجموعة المزج كاملة / Select one generated Blend Tool Pro group.")
        if o.action in ('release', 'expand'):
            return o.action, managed.get('id')
        if o.action == 'set_spine':
            if len(selected) != 1:
                fail("حدد مسار توزيع واحدًا / Select exactly one open spine path.")
            self.spine_path(selected[0])
            return 'set_spine', selected[0].get('id')
        if o.action == 'refresh':
            try:
                saved = json.loads(managed.get(SETTINGS))
                defaults = self.arg_parser.parse_args([])
                for name in SETTING_NAMES:
                    value = saved.get(name, getattr(defaults, name))
                    # Reuse argparse's type/choice validation for stored metadata.
                    parsed = self.arg_parser.parse_args(['--' + name + '=' + str(value).lower() if isinstance(value, bool)
                                                         else '--' + name + '=' + str(value)])
                    setattr(o, name, getattr(parsed, name))
            except (ValueError, TypeError, KeyError, SystemExit) as error:
                raise inkex.AbortExtension("Invalid saved blend settings. Use the main Blend dialog instead.") from error
        self.validate_options()
        spine_id = (o.spine_id.strip().lstrip('#') or self.svg.get(SPINE, '')) if o.follow_spine else ''
        if o.follow_spine and not spine_id:
            fail("عيّن مسار التوزيع أو أدخل ID / Use Set Blend Spine or enter its Object ID.")
        if managed is not None:
            try:
                source_ids = json.loads(managed.get(SOURCES, '[]'))
                if not isinstance(source_ids, list) or not all(isinstance(i, str) for i in source_ids):
                    raise ValueError()
            except (ValueError, TypeError) as error:
                raise inkex.AbortExtension("Invalid saved source IDs. Select the original objects instead.") from error
        elif o.source_ids.strip():
            source_ids = [value.strip().lstrip('#') for value in o.source_ids.split(',') if value.strip()]
        else:
            selected = [el for el in selected if el.get('id') != spine_id]
            if o.order == 'stack':
                order = {el: i for i, el in enumerate(self.svg.iter())}
                selected.sort(key=lambda el: order[el])
            source_ids = [el.get('id') for el in selected]
        if o.source_ids.strip():
            source_ids = [value.strip().lstrip('#') for value in o.source_ids.split(',') if value.strip()]
        if len(source_ids) < 2 or len(source_ids) != len(set(source_ids)):
            fail("حدد عنصرين مختلفين على الأقل / Select at least two different vector objects.")
        if len(source_ids) > 20:
            fail("Maximum 20 source objects per blend.")
        elements = [self.svg.getElementById(value) for value in source_ids]
        if any(el is None for el in elements):
            fail("أحد عناصر المزج محذوف / A blend source was deleted. Select new source objects.")
        for el in elements:
            if any(p.get(MARKER) for p in [el, *el.iterancestors()]):
                fail("Select original objects, or select the entire generated blend group to update it.")
            if any(other is not el and other in el.iterancestors() for other in elements):
                fail("Do not specify a source together with its ancestor group.")
        source_parents = [el.getparent() for el in elements]
        self.output_parent = source_parents[0] if all(p is source_parents[0] for p in source_parents) else self.svg
        sources = [self.collect(el) for el in elements]
        if managed is None and not o.source_ids.strip():
            if o.order == 'left_right':
                sources.sort(key=lambda source: source.center[0])
            elif o.order == 'top_bottom':
                sources.sort(key=lambda source: source.center[1])
        # Store source order before the reversible direction switch.
        stored_ids = [source.element.get('id') for source in sources]
        if o.reverse_objects:
            sources.reverse()
        if o.follow_spine and len(sources) != 2:
            fail("المسار المنحني يدعم عنصرين؛ استخدم المزج المستقيم لعدة مراحل / Custom spine requires exactly two sources.")
        source_spine = self.spine_path(self.svg.getElementById(spine_id)) if o.follow_spine else None
        group = inkex.Group()
        group.set('inkscape:label', o.group_name.strip())
        settings = {name: getattr(o, name) for name in SETTING_NAMES}
        settings['spine_id'] = spine_id
        key = hashlib.sha256(json.dumps(sorted(stored_ids)).encode()).hexdigest()[:20]
        group.attrib.update({MARKER: VERSION, SOURCES: json.dumps(stored_ids), SETTINGS: json.dumps(settings), KEY: key})
        lighting = VectorLighting(o, self.px, group) if o.shading_mode != 'off' and o.shading_strength > 0 else None
        generated, total_nodes, visible_spine, step_total = [], 0, None, 0
        for stage, (a, b) in enumerate(zip(sources, sources[1:])):
            if len(a.leaves) != len(b.leaves):
                fail("المجموعتان تحتاجان عدد أشكال متطابقًا / Source groups must have the same number of visible shapes.")
            base_angle = math.atan2(b.center[1] - a.center[1], b.center[0] - a.center[0])
            if source_spine is not None:
                position_at, length, visible_spine = self.fitted_spine(source_spine, a, b)
            else:
                position_at = lambda t, a=a, b=b, angle=base_angle: ((mix(a.center[0], b.center[0], t), mix(a.center[1], b.center[1], t)), angle)
                length = distance(a.center, b.center)
            count = self.count_steps(a, b, length)
            if count > MAX_STEPS or step_total + count > MAX_STEPS:
                fail(f"Maximum {MAX_STEPS} intermediate objects. Increase the spacing or reduce steps.")
            morphs = [Morph(l.path, r.path, o) for l, r in zip(a.leaves, b.leaves)] if o.shape_mode == 'morph' else []
            nodes_per_step = sum(m.node_count for m in morphs) if morphs else sum(sum(len(s) for s in l.path.to_superpath()) for l in a.leaves)
            total_nodes += count * nodes_per_step
            if total_nodes > MAX_CURVE_NODES or (step_total + count) * len(a.leaves) > MAX_OUTPUT_PATHS:
                fail("Blend too complex. Reduce steps or simplify the source shapes.")
            if stage == 0:
                cap = self.endpoint(a, position_at(0)[1], lighting)
                if cap is not None:
                    generated.append(cap)
            for index in range(1, count + 1):
                t = index / (count + 1)
                position, angle = position_at(t ** o.position_bias)
                shape_t, color_t = t ** o.shape_bias, t ** o.color_bias
                rotation = (angle - base_angle if o.orientation == 'path' else 0) + o.extra_turns * 2 * math.pi * t
                c, s = math.cos(rotation), math.sin(rotation)
                placement = inkex.Transform((c, s, -s, c, position[0], position[1]))
                step = inkex.Group()
                step.set('inkscape:label', f'Blend {stage + 1}.{index}')
                step.attrib.update({'data-blend-role': 'step', 'data-blend-t': num(t),
                                    'data-blend-stage': str(stage), 'data-blend-center': ','.join(map(num, position))})
                for leaf_index, (l, r) in enumerate(zip(a.leaves, b.leaves)):
                    if o.shape_mode == 'morph':
                        path = morphs[leaf_index].at(shape_t)
                    elif o.shape_mode == 'scale':
                        if a.box.width <= 1e-12 or a.box.height <= 1e-12:
                            fail("Scale mode needs a non-zero source width and height. Use Morph or Copy for lines.")
                        sx, sy = mix(1, b.box.width / a.box.width, shape_t), mix(1, b.box.height / a.box.height, shape_t)
                        path = l.path.transform(inkex.Transform((sx, 0, 0, sy, 0, 0)))
                    else:
                        path = l.path
                    result = inkex.PathElement()
                    result.path = path.transform(placement)
                    result.style = self.style_at(l, r, color_t)
                    if lighting is not None:
                        lighting.apply(result, angle)
                    step.append(result)
                generated.append(step)
            step_total += count
            cap = self.endpoint(b, position_at(1)[1], lighting)
            if cap is not None:
                generated.append(cap)
        cap_nodes = sum(sum(len(sub) for sub in path.path.to_superpath())
                        for item in generated if item.get('data-blend-role') == 'endpoint' for path in item)
        multiplier = 2 if lighting is not None and o.cast_shadow and o.shadow_opacity > 0 and o.shadow_distance > 0 else 1
        if (total_nodes + cap_nodes) * multiplier > MAX_CURVE_NODES or sum(len(item) for item in generated) * multiplier > MAX_OUTPUT_PATHS:
            fail("3D output too complex. Reduce steps, disable shadows, or simplify the sources.")
        if o.reverse_stack:
            generated.reverse()
        if lighting is not None:
            shadow = lighting.shadow(generated)
            if shadow is not None:
                group.append(shadow)
        if o.show_spine and visible_spine is not None:
            line = inkex.PathElement()
            line.path = visible_spine
            line.style = {'fill': 'none', 'stroke': '#94a3b8', 'stroke-width': num(self.px),
                          'stroke-dasharray': f'{num(self.px*4)},{num(self.px*4)}'}
            line.set('data-blend-role', 'spine-preview')
            group.append(line)
        group.extend(generated)
        group.set('data-blend-step-count', str(step_total))
        group.set('data-blend-cap-count', str(sum(item.get('data-blend-role') == 'endpoint' for item in generated)))
        if not step_total:
            fail("المسافة كبيرة ولا تنتج أشكالًا وسيطة / Spacing produces no intermediate objects. Reduce it.")
        parents = [el.getparent() for el in elements]
        parent = parents[0] if all(p is parents[0] for p in parents) else self.svg
        if parent is self.svg:
            insertion = len(parent)
        else:
            insertion = (max if lighting is not None and o.shade_endpoints else min)(parent.index(el) for el in elements) + 1
            matrix = transform_to_root(parent, self.svg)
            a, b, c, d, _, _ = matrix.to_hexad()
            if abs(a*d - b*c) < 1e-12:
                fail("Source parent has a zero-scale transform.")
            group.attrib['transform'] = 'matrix(' + ','.join(map(num, (-matrix).to_hexad())) + ')'
        old_ids = [managed.get('id')] if managed is not None else [el.get('id') for el in self.svg.iter() if el.get(MARKER) and el.get(KEY) == key]
        parent_indices = []
        while parent is not self.svg:
            parent_indices.append(parent.getparent().index(parent))
            parent = parent.getparent()
        return 'blend', group, list(reversed(parent_indices)), insertion, old_ids

    def effect(self):
        original = self.svg
        selected_ids = [el.get('id') for el in original.selection.values()]
        self.svg = inkex.load_svg(io.BytesIO(etree.tostring(original))).getroot()
        self.svg.selection.set(*selected_ids)
        try:
            result = self.build()
        finally:
            self.svg = original
        action = result[0]
        if action == 'set_spine':
            self.svg.set(SPINE, result[1])
            return
        if action == 'release':
            element = self.svg.getElementById(result[1])
            element.getparent().remove(element)
            return
        if action == 'expand':
            element = self.svg.getElementById(result[1])
            for el in [element, *element.iterdescendants()]:
                for key in list(el.attrib):
                    if key.startswith('data-blend-'):
                        del el.attrib[key]
            return
        _, group, parent_indices, insertion, old_ids = result
        parent = self.svg
        for index in parent_indices:
            parent = parent[index]
        if self.options.on_apply == 'replace' or self.options.action == 'refresh':
            for old_id in old_ids:
                old = self.svg.getElementById(old_id)
                if old is not None:
                    if old.getparent() is parent and parent.index(old) < insertion:
                        insertion -= 1
                    old.getparent().remove(old)
        parent.insert(insertion, group)
        for el in [group, *group.iterdescendants()]:
            el.get_id()


if __name__ == '__main__':
    BlendToolPro().run()
