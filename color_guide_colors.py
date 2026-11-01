#!/usr/bin/env python3
"""sRGB/OKLab calculations and attributed, offline color names for Color Guide Pro."""
import colorsys
from dataclasses import dataclass, field
from functools import lru_cache
import json
import math
from pathlib import Path
import re

import inkex


def linear(channel):
    channel /= 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def encode(channel):
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def oklab(rgb):
    r, g, b = map(linear, rgb)
    l = (0.4122214708*r + 0.5363325363*g + 0.0514459929*b) ** (1/3)
    m = (0.2119034982*r + 0.6806995451*g + 0.1073969566*b) ** (1/3)
    s = (0.0883024619*r + 0.2817188376*g + 0.6299787005*b) ** (1/3)
    return (0.2104542553*l + 0.7936177850*m - 0.0040720468*s,
            1.9779984951*l - 2.4285922050*m + 0.4505937099*s,
            0.0259040371*l + 0.7827717662*m - 0.8086757660*s)


def _linear_from_lab(L, a, b):
    l = (L + 0.3963377774*a + 0.2158037573*b) ** 3
    m = (L - 0.1055613458*a - 0.0638541728*b) ** 3
    s = (L - 0.0894841775*a - 1.2914855480*b) ** 3
    return (4.0767416621*l - 3.3077115913*m + 0.2309699292*s,
            -1.2684380046*l + 2.6097574011*m - 0.3413193965*s,
            -0.0041960863*l - 0.7034186147*m + 1.7076147010*s)


def from_oklab(lab):
    L, a, b = lab
    values = _linear_from_lab(L, a, b)
    # Reduce chroma at constant lightness/hue until inside the sRGB gamut.
    if any(c < -1e-7 or c > 1 + 1e-7 for c in values):
        low, high = 0., 1.
        for _ in range(24):
            mid = (low + high) / 2
            trial = _linear_from_lab(L, a * mid, b * mid)
            if all(-1e-7 <= c <= 1 + 1e-7 for c in trial):
                low = mid
            else:
                high = mid
        values = _linear_from_lab(L, a * low, b * low)
    return tuple(round(255 * max(0., min(1., encode(max(0., c))))) for c in values)


def luminance(rgb):
    return sum(c * weight for c, weight in zip(map(linear, rgb), (0.2126, 0.7152, 0.0722)))


def contrast(foreground, background):
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + 0.05) / (a + 0.05)


def contrast_level(ratio):
    # Never round before comparing WCAG thresholds.
    return 'AAA' if ratio >= 7 else 'AA' if ratio >= 4.5 else 'Large AA' if ratio >= 3 else 'Low'


def readable_ink(rgb):
    return '#FFFFFF' if contrast(rgb, (255,255,255)) >= contrast(rgb, (17,22,35)) else '#111623'


def hex_rgb(rgb):
    return '#%02X%02X%02X' % tuple(rgb)


def rgb_cmyk(rgb):
    r, g, b = (v / 255 for v in rgb)
    k = 1 - max(r, g, b)
    if k >= 1:
        return (0, 0, 0, 100)
    return tuple(round(v * 100) for v in ((1-r-k)/(1-k), (1-g-k)/(1-k), (1-b-k)/(1-k), k))


def rgb_hsl(rgb):
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    return round(h * 360) % 360, round(s * 100), round(l * 100)


def rgba(value):
    """Parse Inkex sRGB/CSS colors; unsupported ICC/pattern paints are not guessed."""
    if value is None or str(value).strip().lower() in ('none', 'inherit', 'unset'):
        return None
    if str(value).strip().lower() == 'transparent':
        return (0, 0, 0, 0.)
    color = inkex.Color(int(value) if str(value).isdigit() else str(value)).to_rgba()
    return tuple(int(color[i]) for i in range(3)) + (float(color[3]),)


def composite(value, background):
    return tuple(round(value[i] * value[3] + background[i] * (1-value[3])) for i in range(3))


def tonal_scale(rgb, count=11, base_index=0):
    if count not in (5, 7, 9, 11):
        raise ValueError('Choose 5, 7, 9 or 11 tones.')
    lab = oklab(rgb)
    targets = [0.98 - i * 0.84 / (count - 1) for i in range(count)]
    anchor = min(range(count), key=lambda i: abs(targets[i] - lab[0])) if base_index == 0 else base_index - 1
    if not 0 <= anchor < count:
        raise ValueError('Original tone position must fit the selected number of tones.')
    result = []
    for i in range(count):
        if i == anchor:
            result.append(tuple(rgb))
        elif i < anchor:
            t = (anchor-i) / anchor
            result.append(from_oklab((lab[0]+(0.98-lab[0])*t, lab[1]*(1-t), lab[2]*(1-t))))
        else:
            t = (i-anchor) / (count-1-anchor)
            result.append(from_oklab((lab[0]*(1-t)+0.12*t, lab[1]*(1-t), lab[2]*(1-t))))
    labels = [50,100,200,300,400,500,600,700,800,900,950]
    return [(labels[round(i*10/(count-1))], c, i == anchor) for i, c in enumerate(result)]


@lru_cache(maxsize=1)
def name_database():
    path = Path(__file__).with_name('color_guide_names.json')
    data = json.loads(path.read_text(encoding='utf8'))['colors']
    return [(record, oklab(rgba(record['hex'])[:3])) for record in data]


@lru_cache(maxsize=4096)
def nearest_name(rgb):
    target = oklab(rgb)
    record, _ = min(name_database(), key=lambda item: sum((a-b)**2 for a,b in zip(target, item[1])))
    return {**record, 'exact': record['hex'].upper() == hex_rgb(rgb)}


def name_overrides(text):
    """HEX=English name|Arabic name, separated by newlines or semicolons."""
    result = {}
    for line in re.split('[;\n]+', text):
        if not line.strip():
            continue
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'#[0-9a-fA-F]{6}', key.strip()):
            raise ValueError('Names: use #RRGGBB=English name|Arabic name.')
        en, separator, ar = value.strip().partition('|')
        ar = ar.strip() if separator else en.strip()
        en = en.strip()
        if not en or not ar or max(len(en),len(ar)) > 48 or any(ord(c)<32 for c in en+ar):
            raise ValueError('Each color name must have 1–48 characters, without control characters.')
        result[key.strip().upper()] = {'en':en, 'ar':ar, 'exact':True, 'custom':True, 'hex':key.strip().upper()}
    return result


@dataclass
class Swatch:
    value: tuple
    sources: list = field(default_factory=list)
    name: dict = field(default_factory=dict)

    @property
    def key(self):
        return hex_rgb(self.value[:3]) + '@' + format(self.value[3],'.8f')

    @property
    def hex(self):
        return hex_rgb(self.value[:3])

    def effective(self, background):
        return composite(self.value, background)

    def title(self, language):
        title = self.name.get(language, self.name.get('en', self.hex))
        return title if self.name.get('exact') else '≈ ' + title
