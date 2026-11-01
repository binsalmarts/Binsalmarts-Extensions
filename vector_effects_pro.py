#!/usr/bin/env python3
"""Editable distortions, warps and SVG appearance effects for Inkscape 1.4+."""
from bisect import bisect_left
from dataclasses import dataclass
import hashlib
import io
import json
import math
import random
import re
import uuid

import inkex
from inkex.paths import Move, Line, Curve, ZoneClose
from lxml import etree

VERSION = '1.2.0'
MARKER = 'data-vector-effects-pro'
ROLE = 'data-vep-role'
SETTINGS = 'data-vep-settings'
SOURCE = 'data-vep-source'
MAX_SHAPES = 500
MAX_NODES = 40000
SHAPES = {'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'}
CHOICES = {
    'geometry': ('roughen', 'zigzag', 'pucker_bloat', 'arc', 'bulge', 'wave', 'none'),
    'size_mode': ('px', 'percent'), 'points': ('corner', 'smooth'),
    'axis': ('horizontal', 'vertical'), 'shadow_mode': ('outer', 'inner'),
    'glow_mode': ('outer', 'inner'), 'outline_position': ('outer', 'inner', 'center'),
    'grain_type': ('regular', 'soft', 'sprinkles', 'clumped', 'contrasty', 'enlarged',
                   'stippled', 'horizontal', 'vertical', 'speckle'),
    'grain_blend': ('soft-light', 'normal', 'multiply', 'screen', 'overlay'),
    'noise_type': ('additive', 'speckle', 'salt_pepper'),
}
BOOLS = {'preserve_endpoints': True, 'shadow': False, 'glow': False, 'outline': False,
         'grain': False, 'grain_monochrome': True, 'noise': False, 'noise_monochrome': True}
FLOATS = {'size': 6, 'detail': 12, 'amount': 30, 'wave_phase': 0, 'tolerance': .2,
          'shadow_dx': 8, 'shadow_dy': 8, 'shadow_blur': 4, 'shadow_spread': 0,
          'shadow_opacity': .35, 'glow_blur': 6, 'glow_spread': 2, 'glow_opacity': .65,
          'outline_width': 2, 'outline_opacity': 1, 'grain_intensity': 45,
          'grain_contrast': 50, 'grain_size': 1.5,
          'noise_amount': 35, 'noise_size': 1, 'noise_density': 35}
INTS = {'seed': 1, 'zigzag_cycles': 12, 'wave_cycles': 1, 'grain_seed': 1, 'noise_seed': 1}
STRINGS = {'shadow_color': '#000000', 'glow_color': '#4f7dff', 'outline_color': '#24354b',
           'group_name': 'Vector Effects Pro · مؤثرات متجهية'}
SETTING_NAMES = [*CHOICES, *BOOLS, *FLOATS, *INTS, *STRINGS]
GRAIN_PRESETS = {
    # X frequency, Y frequency, octaves, contrast multiplier, sparse-dot threshold.
    'regular': (.8, .8, 1, 1, None), 'soft': (.45, .45, 3, .8, None),
    'sprinkles': (.75, .75, 1, 1, .38), 'clumped': (.18, .18, 2, 1.3, None),
    'contrasty': (.75, .75, 2, 1.8, None), 'enlarged': (.22, .22, 1, 1.2, None),
    'stippled': (.8, .8, 1, 1, .43), 'horizontal': (.035, .8, 1, 1.2, None),
    'vertical': (.8, .035, 1, 1.2, None), 'speckle': (1.2, 1.2, 1, 1, .47),
}


def number(value):
    return format(float(value), '.12g')


def fail(message):
    raise inkex.AbortExtension(message)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def bounded(value, low, high, label):
    if not math.isfinite(value) or not low <= value <= high:
        fail(f'{label}: {low} … {high}.')


def color(value):
    try:
        raw = str(value).strip()
        if raw.startswith('0x') or raw.lstrip('-').isdigit():
            packed = int(raw, 0) if raw.startswith('0x') else int(raw)
            if not 0 <= packed <= 0xFFFFFFFF:
                raise ValueError()
            rgb = tuple((packed >> shift) & 255 for shift in (24, 16, 8))
            alpha = (packed & 255) / 255
        else:
            rgba = inkex.Color(raw).to_rgba()
            if len(rgba) != 4:
                raise ValueError()
            rgb, alpha = rgba[:3], rgba[3]
        return '#{:02x}{:02x}{:02x}'.format(*rgb), float(alpha)
    except (ValueError, TypeError, KeyError) as error:
        raise inkex.AbortExtension(f'لون غير صالح / Invalid color: {value}') from error


def composed(element, root):
    result = inkex.Transform()
    chain = []
    while element is not root:
        chain.append(element)
        element = element.getparent()
    for item in reversed(chain):
        result = result @ inkex.Transform(item.attrib.get('transform'))
    return result


def cubic(points, t):
    a, b, c, d = points
    u = 1 - t
    return tuple(u*u*u*a[i] + 3*u*u*t*b[i] + 3*u*t*t*c[i] + t*t*t*d[i] for i in (0, 1))


def split_cubic(points):
    a, b, c, d = points
    ab, bc, cd = lerp(a, b, .5), lerp(b, c, .5), lerp(c, d, .5)
    abc, bcd = lerp(ab, bc, .5), lerp(bc, cd, .5)
    middle = lerp(abc, bcd, .5)
    return (a, ab, abc, middle), (middle, bcd, cd, d)


class Contour:
    """A bounded arc-length table used by noise and zigzag only."""
    def __init__(self, path, tolerance):
        self.closed = path[-1].letter.lower() == 'z'
        csp = path.to_superpath()[0]
        self.points = [tuple(csp[0][1])]

        def flatten(points, depth=0):
            a, b, c, d = points
            excess = distance(a, b) + distance(b, c) + distance(c, d) - distance(a, d)
            if excess <= tolerance or depth >= 18:
                if distance(self.points[-1], d) > 1e-10:
                    self.points.append(tuple(d))
                if len(self.points) > MAX_NODES:
                    fail('المسار كثيف جدًا؛ بسّطه أولًا / Simplify the source path first.')
                return
            left, right = split_cubic(points)
            flatten(left, depth + 1)
            flatten(right, depth + 1)

        for left, right in zip(csp, csp[1:]):
            flatten((left[1], left[2], right[0], right[1]))
        self.lengths = [0]
        for a, b in zip(self.points, self.points[1:]):
            self.lengths.append(self.lengths[-1] + distance(a, b))
        self.length = self.lengths[-1]

    def at(self, fraction):
        value = min(1, max(0, fraction)) * self.length
        index = max(1, min(len(self.points) - 1, bisect_left(self.lengths, value)))
        a, b = self.points[index - 1:index + 1]
        t = (value - self.lengths[index - 1]) / (self.lengths[index] - self.lengths[index - 1])
        return lerp(a, b, t), ((b[0] - a[0]) / distance(a, b), (b[1] - a[1]) / distance(a, b))


def points_path(points, closed, smooth):
    path = inkex.Path([Move(*points[0])])
    if smooth and len(points) > 2:
        count = len(points)
        for index in range(count if closed else count - 1):
            p = points[index]
            q = points[(index + 1) % count]
            previous = points[(index - 1) % count] if closed or index else p
            following = points[(index + 2) % count] if closed or index + 2 < count else q
            c1 = (p[0] + (q[0] - previous[0]) / 6, p[1] + (q[1] - previous[1]) / 6)
            c2 = (q[0] - (following[0] - p[0]) / 6, q[1] - (following[1] - p[1]) / 6)
            path.append(Curve(*c1, *c2, *q))
    else:
        path.extend(Line(*point) for point in points[1:])
    if closed:
        path.append(ZoneClose())
    return path


def displaced(path, options, amplitude, px, source_key):
    if amplitude == 0:
        return inkex.Path(path)
    result = inkex.Path()
    for index, part in enumerate(path.break_apart()):
        contour = Contour(part, options.tolerance * px)
        if contour.length <= 1e-10:
            result += part
            continue
        count = options.zigzag_cycles * 2 if options.geometry == 'zigzag' else max(4, math.ceil(contour.length / (100 * px) * options.detail))
        if count > MAX_NODES:
            fail('تفاصيل كثيرة جدًا؛ قلل Detail أو Cycles / Reduce detail or cycle count.')
        seed = int.from_bytes(hashlib.sha256(f'{options.seed}:{source_key}:{index}'.encode()).digest()[:8], 'big')
        rng = random.Random(seed)
        points = []
        for i in range(count if contour.closed else count + 1):
            position, tangent = contour.at(i / count)
            magnitude = (1 if i % 2 == 0 else -1) if options.geometry == 'zigzag' else rng.uniform(-1, 1)
            if not contour.closed and options.preserve_endpoints and i in (0, count):
                magnitude = 0
            points.append((position[0] - tangent[1] * amplitude * magnitude,
                           position[1] + tangent[0] * amplitude * magnitude))
        result += points_path(points, contour.closed, options.points == 'smooth')
    return result


def puckered(path, box, amount):
    if amount == 0:
        return inkex.Path(path)
    center = (box.center_x, box.center_y)
    result = inkex.Path()
    for part in path.break_apart():
        csp = part.to_superpath()
        for contour in csp:
            for node in contour:
                for index, point in enumerate(node):
                    factor = 1 - amount if index == 1 else 1 + amount
                    point[:] = [center[i] + (point[i] - center[i]) * factor for i in (0, 1)]
        generated = csp.to_path()
        if part[-1].letter.lower() == 'z':
            generated.close()
        result += generated
    return result


def warp_function(box, options, amplitude):
    vertical = options.axis == 'vertical'
    center = (box.center_y, box.center_x) if vertical else (box.center_x, box.center_y)
    width = box.height if vertical else box.width
    if width <= 1e-12:
        fail('بُعد الانحناء صفري؛ اختر المحور الآخر أو مجموعة / Warp axis has zero extent. Choose the other axis or a group.')
    amount = options.amount / 100

    def apply(point):
        x, y = (point[1], point[0]) if vertical else point
        u, v = x - center[0], y - center[1]
        if options.geometry == 'arc' and amount != 0:
            radius = width / (amount * math.pi)
            angle = u / radius
            x = center[0] + (radius - v) * math.sin(angle)
            y = center[1] + radius - (radius - v) * math.cos(angle)
        elif options.geometry == 'bulge':
            y = center[1] + v * (1 + amount * (1 - (2 * u / width) ** 2))
        elif options.geometry == 'wave':
            phase = math.radians(options.wave_phase)
            y += amplitude * math.sin(2 * math.pi * options.wave_cycles * (u / width + .5) + phase)
        return (y, x) if vertical else (x, y)

    return apply


def warped(path, function, tolerance):
    """Fit transformed cubics with checked interior error and transformed tangents."""
    result = inkex.Path()
    count = 0

    def tangent(point, handle):
        vector = (handle[0] - point[0], handle[1] - point[1])
        epsilon = 1e-4
        left = function((point[0] - epsilon * vector[0], point[1] - epsilon * vector[1]))
        right = function((point[0] + epsilon * vector[0], point[1] + epsilon * vector[1]))
        value = function(point)
        return (value[0] + (right[0] - left[0]) / (2 * epsilon),
                value[1] + (right[1] - left[1]) / (2 * epsilon))

    def fit(points, depth=0):
        nonlocal count
        a, b, c, d = points
        mapped = (function(a), tangent(a, b), tangent(d, c), function(d))
        error = max(distance(function(cubic(points, t)), cubic(mapped, t)) for t in (.25, .5, .75))
        if error > tolerance:
            if depth >= 14:
                fail('الانحناء شديد أو معقد؛ قلل القوة / Warp too complex. Reduce strength or simplify the artwork.')
            left, right = split_cubic(points)
            fit(left, depth + 1)
            fit(right, depth + 1)
            return
        count += 1
        if count > MAX_NODES:
            fail('Warp exceeds the curve-node limit. Reduce detail or increase tolerance.')
        result.append(Curve(*mapped[1], *mapped[2], *mapped[3]))

    for part in path.break_apart():
        csp = part.to_superpath()[0]
        result.append(Move(*function(csp[0][1])))
        for a, b in zip(csp, csp[1:]):
            fit((a[1], a[2], b[0], b[1]))
        if part[-1].letter.lower() == 'z':
            result.append(ZoneClose())
    return result


class Appearance:
    """One standard SVG filter graph; all definitions belong to their wrapper."""
    def __init__(self, options, px, box):
        self.o, self.px = options, px
        self.filter = inkex.Filter()
        self.filter.attrib.update({'id': 'vep-filter-' + uuid.uuid4().hex,
                                   'filterUnits': 'userSpaceOnUse', 'primitiveUnits': 'userSpaceOnUse',
                                   'color-interpolation-filters': 'sRGB'})
        o = options
        pad = max(px, (o.glow_spread + 4 * o.glow_blur) * px if o.glow else 0,
                  o.outline_width * px if o.outline else 0)
        shadow_pad = (o.shadow_spread + 4 * o.shadow_blur) * px if o.shadow else 0
        dx, dy = (o.shadow_dx * px, o.shadow_dy * px) if o.shadow else (0, 0)
        left, right = max(pad, shadow_pad - dx), max(pad, shadow_pad + dx)
        top, bottom = max(pad, shadow_pad - dy), max(pad, shadow_pad + dy)
        self.filter.attrib.update({'x': number(box.left - left), 'y': number(box.top - top),
                                   'width': number(max(px, box.width + left + right)),
                                   'height': number(max(px, box.height + top + bottom))})
        self.serial = 0

    def primitive(self, tag, **attrs):
        self.serial += 1
        node = etree.SubElement(self.filter, inkex.addNS(tag, 'svg'))
        for key, value in attrs.items():
            node.set(key.rstrip('_').replace('_', '-'), number(value) if isinstance(value, (int, float)) else str(value))
        result = 'vep' + str(self.serial)
        node.set('result', result)
        return result

    def morph(self, source, radius, operator):
        return self.primitive('feMorphology', in_=source, radius=radius, operator=operator) if radius > 0 else source

    def blur(self, source, radius):
        return self.primitive('feGaussianBlur', in_=source, stdDeviation=radius) if radius > 0 else source

    def invert(self):
        result = self.primitive('feComponentTransfer', in_='SourceAlpha')
        etree.SubElement(self.filter[-1], inkex.addNS('feFuncA', 'svg'), type='table', tableValues='1 0')
        return result

    def tint(self, source, paint, opacity):
        rgb, alpha = color(paint)
        flood = self.primitive('feFlood', flood_color=rgb, flood_opacity=alpha * opacity)
        return self.primitive('feComposite', in_=flood, in2=source, operator='in')

    def grain_surface(self):
        o = self.o
        if not o.grain or o.grain_intensity == 0:
            return 'SourceGraphic'
        fx, fy, octaves, gain, threshold = GRAIN_PRESETS[o.grain_type]
        scale = o.grain_size * self.px
        noise = self.primitive('feTurbulence', type='fractalNoise', seed=o.grain_seed,
                               baseFrequency=f'{number(fx / scale)} {number(fy / scale)}',
                               numOctaves=octaves, stitchTiles='stitch')
        if o.grain_type == 'soft':
            noise = self.blur(noise, scale * .12)
        if o.grain_monochrome:
            noise = self.primitive('feColorMatrix', in_=noise, type='saturate', values='0')
        noise = self.primitive('feComponentTransfer', in_=noise)
        transfer = self.filter[-1]
        slope = (1 + o.grain_contrast * .09) * gain
        intercept = .5 - slope * (threshold if threshold is not None else .5)
        for channel in 'RGB':
            etree.SubElement(transfer, inkex.addNS('feFunc' + channel, 'svg'),
                             type='linear', slope=number(slope), intercept=number(intercept))
        etree.SubElement(transfer, inkex.addNS('feFuncA', 'svg'), type='table', tableValues='1 1')
        if threshold is not None:
            noise = self.primitive('feComponentTransfer', in_=noise)
            for channel in 'RGB':
                etree.SubElement(self.filter[-1], inkex.addNS('feFunc' + channel, 'svg'),
                                 type='discrete', tableValues='0 1')
        # Work on opaque, unpremultiplied source colors. Restore SourceAlpha
        # once at the end, so translucent edges and holes retain their alpha.
        opaque = self.primitive('feComponentTransfer', in_='SourceGraphic')
        etree.SubElement(self.filter[-1], inkex.addNS('feFuncA', 'svg'), type='table', tableValues='1 1')
        textured = self.primitive('feBlend', in_=noise, in2=opaque, mode=o.grain_blend)
        strength = o.grain_intensity / 100
        mixed = self.primitive('feComposite', in_=opaque, in2=textured, operator='arithmetic',
                               k1=0, k2=1-strength, k3=strength, k4=0)
        return self.primitive('feComposite', in_=mixed, in2='SourceAlpha', operator='in')

    def noise_surface(self, source):
        """Apply signed RGB noise or sparse impulses; keep the source alpha.

        These are coherent procedural textures from SVG fractalNoise, not
        independent random bitmap pixels or an exact Gaussian distribution.
        """
        o = self.o
        if not o.noise or o.noise_amount == 0 or o.noise_type == 'salt_pepper' and o.noise_density == 0:
            return source
        scale = o.noise_size * self.px
        noise = self.primitive('feTurbulence', type='fractalNoise', seed=o.noise_seed,
                               baseFrequency=number(.65 / scale), numOctaves=1, stitchTiles='stitch')
        if o.noise_monochrome:
            noise = self.primitive('feColorMatrix', in_=noise, type='saturate', values='0')
        # Expand the narrow fractalNoise range around its neutral 0.5 level.
        noise = self.primitive('feComponentTransfer', in_=noise)
        for channel in 'RGB':
            etree.SubElement(self.filter[-1], inkex.addNS('feFunc' + channel, 'svg'),
                             type='linear', slope='4', intercept='-1.5')
        etree.SubElement(self.filter[-1], inkex.addNS('feFuncA', 'svg'), type='table', tableValues='1 1')
        opaque = self.primitive('feComponentTransfer', in_=source)
        etree.SubElement(self.filter[-1], inkex.addNS('feFuncA', 'svg'), type='table', tableValues='1 1')
        amount = o.noise_amount / 100
        if o.noise_type == 'salt_pepper':
            # The extreme tails select sparse dots. Density is a threshold
            # control, not a claim that fractal noise has a uniform histogram.
            tail = o.noise_density / 200
            mask = self.primitive('feColorMatrix', in_=noise, type='matrix',
                                  values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  1 0 0 0 0')
            mask = self.primitive('feComponentTransfer', in_=mask)
            table = ' '.join('1' if (i + .5) / 256 < tail or (i + .5) / 256 >= 1-tail else '0'
                             for i in range(256))
            etree.SubElement(self.filter[-1], inkex.addNS('feFuncA', 'svg'), type='discrete', tableValues=table)
            spots = self.primitive('feComponentTransfer', in_=noise)
            for channel in 'RGB':
                etree.SubElement(self.filter[-1], inkex.addNS('feFunc' + channel, 'svg'),
                                 type='discrete', tableValues='0 1')
            spots = self.primitive('feComposite', in_=spots, in2=mask, operator='in')
            textured = self.primitive('feComposite', in_=spots, in2=opaque, operator='over')
            mixed = self.primitive('feComposite', in_=opaque, in2=textured, operator='arithmetic',
                                   k1=0, k2=1-amount, k3=amount, k4=0)
        elif o.noise_type == 'speckle':
            mixed = self.primitive('feComposite', in_=opaque, in2=noise, operator='arithmetic',
                                   k1=2*amount, k2=1-amount, k3=0, k4=0)
        else:
            mixed = self.primitive('feComposite', in_=opaque, in2=noise, operator='arithmetic',
                                   k1=0, k2=1, k3=amount, k4=-.5*amount)
        return self.primitive('feComposite', in_=mixed, in2='SourceAlpha', operator='in')

    def build(self):
        o, px = self.o, self.px
        behind, above = [], []
        if o.shadow:
            alpha = self.invert() if o.shadow_mode == 'inner' else 'SourceAlpha'
            alpha = self.morph(alpha, o.shadow_spread * px, 'dilate')
            alpha = self.blur(alpha, o.shadow_blur * px)
            alpha = self.primitive('feOffset', in_=alpha, dx=o.shadow_dx * px, dy=o.shadow_dy * px)
            if o.shadow_mode == 'inner':
                alpha = self.primitive('feComposite', in_=alpha, in2='SourceAlpha', operator='in')
            result = self.tint(alpha, o.shadow_color, o.shadow_opacity)
            (above if o.shadow_mode == 'inner' else behind).append(result)
        if o.glow:
            alpha = self.invert() if o.glow_mode == 'inner' else 'SourceAlpha'
            alpha = self.morph(alpha, o.glow_spread * px, 'dilate')
            alpha = self.blur(alpha, o.glow_blur * px)
            if o.glow_mode == 'inner':
                alpha = self.primitive('feComposite', in_=alpha, in2='SourceAlpha', operator='in')
            result = self.tint(alpha, o.glow_color, o.glow_opacity)
            (above if o.glow_mode == 'inner' else behind).append(result)
        if o.outline and o.outline_width > 0:
            radius = o.outline_width * px
            if o.outline_position == 'inner':
                eroded = self.morph('SourceAlpha', radius, 'erode')
                ring = self.primitive('feComposite', in_='SourceAlpha', in2=eroded, operator='out')
            else:
                if o.outline_position == 'center':
                    radius /= 2
                dilated = self.morph('SourceAlpha', radius, 'dilate')
                inside = self.morph('SourceAlpha', radius, 'erode') if o.outline_position == 'center' else 'SourceAlpha'
                ring = self.primitive('feComposite', in_=dilated, in2=inside, operator='out')
            result = self.tint(ring, o.outline_color, o.outline_opacity)
            (behind if o.outline_position == 'outer' else above).append(result)
        surface = self.noise_surface(self.grain_surface())
        self.primitive('feMerge')
        for source in [*behind, surface, *above]:
            etree.SubElement(self.filter[-1], inkex.addNS('feMergeNode', 'svg'), **{'in': source})
        return self.filter


@dataclass
class Leaf:
    path: object
    style: dict
    key: str
    native_paint: bool = False
    stroke_bound: float = 0


class VectorEffectsPro(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument('--tab', default='geometry')
        pars.add_argument('--action', choices=('apply', 'refresh', 'edit', 'release'), default='apply')
        for name, choices in CHOICES.items():
            pars.add_argument('--' + name, choices=choices, default=choices[0])
        for name, default in BOOLS.items():
            pars.add_argument('--' + name, type=inkex.Boolean, default=default)
        for name, default in FLOATS.items():
            pars.add_argument('--' + name, type=float, default=default)
        for name, default in INTS.items():
            pars.add_argument('--' + name, type=int, default=default)
        for name, default in STRINGS.items():
            pars.add_argument('--' + name, default=default)

    def validate_options(self):
        o = self.options
        if o.geometry == 'none' and not any((o.shadow, o.glow, o.outline, o.grain, o.noise)):
            fail('اختر تأثيرًا واحدًا على الأقل / Enable at least one effect.')
        bounded(o.size, 0, 1000, 'size')
        bounded(o.detail, .1, 1000, 'detail')
        bounded(o.amount, -100, 100, 'amount')
        bounded(o.wave_phase, -360, 360, 'wave_phase')
        bounded(o.tolerance, .05, 5, 'tolerance')
        bounded(o.seed, 0, 2147483647, 'seed')
        bounded(o.zigzag_cycles, 1, 2000, 'zigzag_cycles')
        bounded(o.wave_cycles, 1, 100, 'wave_cycles')
        bounded(o.grain_seed, 0, 2147483647, 'grain_seed')
        bounded(o.grain_intensity, 0, 100, 'grain_intensity')
        bounded(o.grain_contrast, 0, 100, 'grain_contrast')
        bounded(o.grain_size, .2, 100, 'grain_size')
        bounded(o.noise_amount, 0, 100, 'noise_amount')
        bounded(o.noise_size, .2, 100, 'noise_size')
        bounded(o.noise_density, 0, 100, 'noise_density')
        bounded(o.noise_seed, 0, 2147483647, 'noise_seed')
        for key in ('shadow_dx', 'shadow_dy'):
            bounded(getattr(o, key), -10000, 10000, key)
        for key in ('shadow_blur', 'shadow_spread', 'glow_blur', 'glow_spread', 'outline_width'):
            bounded(getattr(o, key), 0, 500, key)
        for key in ('shadow_opacity', 'glow_opacity', 'outline_opacity'):
            bounded(getattr(o, key), 0, 1, key)
        for key in ('shadow_color', 'glow_color', 'outline_color'):
            color(getattr(o, key))
        if not o.group_name.strip():
            fail('Enter a group name.')

    def check_context(self, element):
        for el in [element, *element.iterancestors()]:
            style = el.specified_style()
            if any(str(style.get(key, el.get(key, 'none'))) not in ('none', '', 'None')
                   for key in ('clip-path', 'mask', 'filter', 'marker-start', 'marker-mid', 'marker-end')):
                fail('حوّل القص والأقنعة والمرشحات والعلامات إلى مسارات أولًا / Prepare plain paths without clips, masks, filters or markers.')
            if style.get('transform', 'none') != 'none' or el is not self.svg and el.tag_name == 'svg':
                fail('CSS transforms and nested SVG viewports are unsupported. Use ordinary SVG groups.')

    def collect(self, source, output_parent, opacity_stop=None):
        leaves, box = [], None
        opacity_stop = output_parent if opacity_stop is None else opacity_stop

        def visit(el):
            nonlocal box
            tag = getattr(el, 'tag_name', '')
            if tag in ('title', 'desc', 'metadata', 'defs') or not isinstance(el, inkex.BaseElement):
                return
            if not isinstance(el, inkex.ShapeElement):
                fail(f'Unsupported object: {tag}. Convert to paths first.')
            if el.get(MARKER):
                fail('لا تضع مجموعة تأثير داخل مصدر آخر / Nested generated effects are unsupported. Release them first.')
            if any(p.cascaded_style().get('display', 'inline') == 'none'
                   for p in [el, *el.iterancestors()] if p.get(ROLE) not in ('original', 'render')):
                return
            self.check_context(el)
            if tag in ('g', 'a'):
                for child in el:
                    visit(child)
                return
            if str(el.specified_style()('visibility')) in ('hidden', 'collapse'):
                return
            if tag not in SHAPES:
                fail('حوّل النص إلى مسار وافصل النسخ المرتبطة وأزل الصور / Convert text to paths, unlink clones and remove raster images.')
            if any('%' in el.attrib.get(key, '') for key in ('x','y','width','height','cx','cy','r','rx','ry','x1','x2','y1','y2')):
                fail('Convert percentage geometry to absolute units first.')
            transform = composed(el, self.svg)
            path = el.path.to_absolute().transform(transform)
            bounds = path.bounding_box()
            if bounds is None:
                return
            coordinates = [v for sub in path.to_superpath() for node in sub for point in node for v in point]
            if len(coordinates) > MAX_NODES * 6 or not all(math.isfinite(v) for v in coordinates):
                fail('Source coordinates are invalid or too complex.')
            specified = el.specified_style()
            style = {key: str(specified(key)) for key in ('fill-rule','stroke-linecap','stroke-linejoin','stroke-miterlimit','paint-order')}
            native_paint = False
            for key in ('fill', 'stroke'):
                try:
                    paint = specified(key)
                    if paint is None:
                        style[key], style[key + '-opacity'] = 'none', '0'
                    elif isinstance(paint, (inkex.LinearGradient, inkex.RadialGradient)):
                        if self.options.geometry != 'none':
                            fail('للتدرجات اختر Shape=None؛ استخدم ألوانًا مسطحة مع التشويه / Gradients require Shape=None for appearance effects.')
                        native_paint = True
                        style[key] = 'url(#' + paint.get_id() + ')'
                        style[key + '-opacity'] = number(float(specified(key + '-opacity')))
                    else:
                        rgba = inkex.Color(paint).to_rgba()
                        style[key] = '#{:02x}{:02x}{:02x}'.format(*rgba[:3])
                        style[key + '-opacity'] = number(rgba[3] * float(specified(key + '-opacity')))
                except (TypeError, ValueError, KeyError) as error:
                    raise inkex.AbortExtension('استخدم لونًا مسطحًا أو تدرجًا مع Shape=None / Use solid colors, or gradients with Shape=None. Patterns are unsupported.') from error
            opacity = 1
            for parent in [el, *el.iterancestors()]:
                if parent is opacity_stop:
                    break
                opacity *= float(parent.cascaded_style()('opacity'))
            a, b, c, d, _, _ = transform.to_hexad()
            scale = self.px if str(specified('vector-effect')) == 'non-scaling-stroke' else math.sqrt(abs(a*d-b*c))
            width = el.to_dimensionless(specified('stroke-width')) * scale if style['stroke'] != 'none' else 0
            style['stroke-width'], style['opacity'] = number(width), number(opacity)
            dash = specified('stroke-dasharray')
            style['stroke-dasharray'] = ','.join(number(value * scale) for value in dash) if dash else 'none'
            style['stroke-dashoffset'] = number(el.to_dimensionless(specified('stroke-dashoffset')) * scale)
            bound = width
            if str(specified('vector-effect')) != 'non-scaling-stroke' and style['stroke'] != 'none':
                bound = el.to_dimensionless(specified('stroke-width')) * math.sqrt(a*a+b*b+c*c+d*d)
            leaves.append(Leaf(path, style, el.get('id') or str(len(leaves)), native_paint, bound))
            box += bounds
            if len(leaves) > MAX_SHAPES:
                fail(f'Maximum {MAX_SHAPES} shapes per object.')

        visit(source)
        if not leaves:
            fail('لا توجد مسارات ظاهرة / No visible vector paths in the selection.')
        return leaves, box

    def geometry_path(self, leaf, box, source_id):
        o = self.options
        amplitude = o.size * self.px if o.size_mode == 'px' else o.size / 100 * max(box.width, box.height)
        if o.geometry in ('roughen', 'zigzag'):
            return displaced(leaf.path, o, amplitude, self.px, source_id + ':' + leaf.key)
        if o.geometry == 'pucker_bloat':
            return puckered(leaf.path, box, o.amount / 100)
        if o.geometry in ('arc', 'bulge', 'wave'):
            if o.geometry != 'wave' and o.amount == 0 or o.geometry == 'wave' and amplitude == 0:
                return inkex.Path(leaf.path)
            return warped(leaf.path, warp_function(box, o, amplitude), o.tolerance * self.px)
        return inkex.Path(leaf.path)

    def source_for(self, target):
        if not target.get(MARKER):
            return target
        backup = next((child for child in target if child.get(ROLE) == 'original'), None)
        if backup is None or len(backup) != 1:
            fail('Saved original is missing. Undo the last manual structural edit first.')
        return backup[0]

    def native_copy(self, source):
        """Keep gradient coordinate systems by preserving the source hierarchy.

        IDs are remapped locally, references to shared document definitions stay
        valid, and computed styles keep ID-based CSS after the copy is renamed.
        """
        copied = source.copy()
        original_nodes, copied_nodes = list(source.iter()), list(copied.iter())
        prefix = 'vep-native-' + uuid.uuid4().hex + '-'
        mapping = {node.get('id'): prefix + str(i) for i, node in enumerate(original_nodes) if node.get('id')}
        for original, clone in zip(original_nodes, copied_nodes):
            if isinstance(original, (inkex.ShapeElement, inkex.Stop)):
                clone.style = original.specified_style()
            if original.get('id'):
                clone.attrib['id'] = mapping[original.get('id')]
            for key, value in list(clone.attrib.items()):
                value = re.sub(r'url\(\s*[\"\x27]?#([^\s)\"\x27]+)[\"\x27]?\s*\)',
                               lambda m: 'url(#' + mapping.get(m.group(1), m.group(1)) + ')', value)
                if key in ('href', inkex.addNS('href', 'xlink')) and value.startswith('#'):
                    value = '#' + mapping.get(value[1:], value[1:])
                clone.attrib[key] = value
        matrix = composed(source, self.svg)
        copied.attrib['transform'] = 'matrix(' + ','.join(map(number, matrix.to_hexad())) + ')'
        return copied

    def build_wrapper(self, target):
        o = self.options
        source = self.source_for(target)
        if o.action == 'refresh':
            try:
                saved = json.loads(target.get(SETTINGS))
                if not isinstance(saved, dict):
                    raise ValueError('Expected settings object')
                defaults = self.arg_parser.parse_args([])
                for name in SETTING_NAMES:
                    value = saved.get(name, getattr(defaults, name))
                    argument = '--' + name + '=' + (str(value).lower() if isinstance(value, bool) else str(value))
                    parsed = self.arg_parser.parse_args([argument])
                    setattr(o, name, getattr(parsed, name))
            except (ValueError, TypeError, KeyError, SystemExit) as error:
                raise inkex.AbortExtension('Invalid saved settings. Use the main effects dialog instead.') from error
        self.validate_options()
        parent = target.getparent()
        managed = bool(target.get(MARKER))
        leaves, box = self.collect(source, parent, target if managed else parent)
        wrapper = inkex.Group()
        if managed:
            for key in ('transform', 'style', 'class'):
                if key in target.attrib:
                    wrapper.attrib[key] = target.attrib[key]
        wrapper.set('inkscape:label', o.group_name.strip() + ' · ' + (source.label or source.get('id')))
        wrapper.attrib.update({MARKER: VERSION, SOURCE: source.get('id'),
                               SETTINGS: json.dumps({name: getattr(o, name) for name in SETTING_NAMES})})
        backup = inkex.Group()
        backup.set(ROLE, 'original')
        backup.set('inkscape:label', 'Original · الأصل المحفوظ')
        backup.style = {'display': 'none'}
        wrapper.append(backup)
        render = inkex.Group()
        render.set(ROLE, 'render')
        render.set('inkscape:label', 'Effect · الناتج القابل للتحرير')
        frame = target if managed else parent
        matrix = composed(frame, self.svg) if frame is not self.svg else inkex.Transform()
        a, b, c, d, _, _ = matrix.to_hexad()
        if abs(a*d-b*c) <= 1e-12:
            fail('The parent transform has zero scale.')
        render.attrib['transform'] = 'matrix(' + ','.join(map(number, (-matrix).to_hexad())) + ')'
        wrapper.append(render)
        artwork = inkex.Group()
        artwork.set(ROLE, 'artwork')
        native = any(leaf.native_paint for leaf in leaves)
        count, visual_box = 0, None
        for leaf in leaves:
            path = self.geometry_path(leaf, box, source.get('id'))
            nodes = sum(len(sub) for sub in path.to_superpath())
            count += nodes
            if count > MAX_NODES:
                fail(f'Maximum {MAX_NODES} output curve nodes. Reduce detail or strength.')
            bounds = path.bounding_box()
            if bounds is None:
                continue
            width = max(float(leaf.style['stroke-width']), leaf.stroke_bound)
            visual_box += inkex.BoundingBox((bounds.left-width/2, bounds.right+width/2), (bounds.top-width/2, bounds.bottom+width/2))
            if not native:
                element = inkex.PathElement()
                element.path = path
                element.style = leaf.style
                element.set('data-vep-leaf', leaf.key)
                artwork.append(element)
        if visual_box is None:
            fail('No drawable output.')
        if native:
            artwork.append(self.native_copy(source))
            artwork.set('data-vep-native-paint', 'true')
        if o.shadow or o.glow or o.outline or o.grain or o.noise:
            defs = inkex.Defs()
            effect = Appearance(o, self.px, visual_box).build()
            defs.append(effect)
            render.append(defs)
            artwork.style = {'filter': 'url(#' + effect.get('id') + ')'}
        render.append(artwork)
        wrapper.set('data-vep-node-count', str(count))
        return target.get('id'), wrapper

    def effect(self):
        original = self.svg
        ids = [el.get('id') for el in original.selection.values()]
        self.svg = inkex.load_svg(io.BytesIO(etree.tostring(original))).getroot()
        self.svg.selection.set(*ids)
        try:
            self.px = self.svg.viewport_to_unit('1px')
            if inkex.Transform(self.svg.attrib.get('transform')):
                fail('Move the root SVG transform to an ordinary group first.')
            if self.svg.get('preserveAspectRatio', '').strip() == 'none':
                viewbox = self.svg.get_viewbox()
                if viewbox and not math.isclose(self.svg.viewport_width / viewbox[2], self.svg.viewport_height / viewbox[3], rel_tol=1e-9):
                    fail('Use a uniform root viewport scale.')
            selected = list(self.svg.selection.values())
            selected_set = set(selected)
            targets = [el for el in selected if not any(p in selected_set for p in el.iterancestors())]
            if not targets:
                fail('حدد عنصرًا أو مجموعة أولًا / Select artwork first.')
            if len(targets) > 100:
                fail('Maximum 100 selected objects per run.')
            for target in targets:
                if any(p.get(MARKER) for p in target.iterancestors()):
                    fail('اختر مجموعة التأثير كاملة / Select the entire Vector Effects Pro group.')
                if self.options.action != 'apply' and not target.get(MARKER):
                    fail('حدد مجموعة تأثير مولّدة / Select a generated Vector Effects Pro group.')
            if self.options.action in ('release', 'edit'):
                for target in targets:
                    self.source_for(target)
                results = [(target.get('id'), None) for target in targets]
            else:
                results = [self.build_wrapper(target) for target in targets]
        finally:
            self.svg = original
        for identifier, replacement in results:
            target = self.svg.getElementById(identifier)
            parent, index = target.getparent(), target.getparent().index(target)
            if self.options.action == 'edit':
                for child in target:
                    if child.get(ROLE) == 'original':
                        child.style = {}
                    elif child.get(ROLE) == 'render':
                        child.style = {'display': 'none'}
                target.set('data-vep-editing', 'true')
                continue
            source = self.source_for(target)
            if self.options.action == 'release':
                transform = inkex.Transform(target.attrib.get('transform'))
                if transform:
                    combined = transform @ inkex.Transform(source.attrib.get('transform'))
                    source.attrib['transform'] = 'matrix(' + ','.join(map(number, combined.to_hexad())) + ')'
                wrapper_style = inkex.Style(target.attrib.get('style'))
                if wrapper_style:
                    source_style = inkex.Style(source.attrib.get('style'))
                    for key, value in wrapper_style.items():
                        if key == 'opacity':
                            source_style[key] = number(float(source.cascaded_style()('opacity')) * float(wrapper_style('opacity')))
                        elif key not in source_style and source.get(key) is None:
                            source_style[key] = value
                    source.style = source_style
            source.getparent().remove(source)
            if target is not source:
                parent.remove(target)
            if self.options.action == 'release':
                parent.insert(index, source)
                continue
            backup = next(child for child in replacement if child.get(ROLE) == 'original')
            backup.append(source)
            parent.insert(index, replacement)
            replacement.get_id()
            backup.get_id()
            for child in replacement:
                if child is not backup:
                    for el in child.iter():
                        el.get_id()


if __name__ == '__main__':
    VectorEffectsPro().run()
