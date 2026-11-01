# Color Guide Pro: sources and notices

The bundled `color_guide_names.json` contains 150 curated conventional color names from Randall Munroe's [xkcd color survey](https://xkcd.com/color/rgb/), using the published [RGB data](https://xkcd.com/color/rgb.txt). That data is released under [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/). The source digest and retrieval date are recorded in the JSON. The project supplies the Arabic translations; nearest matches are estimates, not exact standardized names. White is also included as the canonical sRGB endpoint.

Color calculations implement the published sRGB transfer function, WCAG relative luminance/contrast, and OKLab matrices from their definitions:

- [W3C WCAG 2.2: Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
- [W3C WCAG 2.2: Contrast (Enhanced)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced.html)
- [Björn Ottosson: OKLab](https://bottosson.github.io/posts/oklab/)
- [W3C CSS Color 4](https://www.w3.org/TR/css-color-4/)

The Python implementation, page layouts, translations and examples are distributed under the repository's MIT license. No code, logos or assets from the Adobe extension shown in the references are included. Example artwork is generated from native SVG paths.
