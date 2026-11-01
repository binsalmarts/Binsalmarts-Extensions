#!/usr/bin/env python3
"""Check a few normal-text pairs from the supplied MacTahoe dark palette.

Translucent surfaces are composited over #202020. These are declared palette
checks, not measurements of every GTK state or a certification of the theme.
"""


def luminance(color):
    rgb = [int(color[n:n + 2], 16) / 255 for n in (1, 3, 5)]
    linear = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in rgb]
    return sum(x * y for x, y in zip(linear, (.2126, .7152, .0722)))


for label, fg, bg in [
    ('Panel labels', '#dedede', '#202020'),
    ('Numeric/RGBA text', '#dadada', '#2d2d2d'),
    ('Button text', '#afafaf', '#2d2d2d'),
    ('Inactive tab text', '#b2b2b2', '#2d2d2d'),
    ('Active tab text', '#dedede', '#454545'),
]:
    a, b = sorted((luminance(fg), luminance(bg)))
    ratio = (b + .05) / (a + .05)
    assert ratio >= 4.5, (label, ratio)
    print(f'{label}: {ratio:.2f}:1 PASS')
