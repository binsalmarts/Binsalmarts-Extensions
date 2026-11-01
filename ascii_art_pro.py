#!/usr/bin/env python3
"""ASCII Art Pro: editable, bounded ASCII rendering for Inkscape 1.4.

Copyright (c) 2026. Released under the MIT license (see LICENSE).
"""

import base64
import binascii
import copy
import io
import math
import os
from pathlib import Path
import tempfile
import unicodedata
from urllib.parse import unquote, urlsplit
import warnings

import inkex
from lxml import etree

try:
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
except ImportError as error:
    raise inkex.AbortExtension(
        "ASCII Art Pro requires Pillow in Inkscape's Python environment. "
        "On Linux, install python3-pil and restart Inkscape."
    ) from error


VERSION = "1.2.0"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_CELLS = 100_000
MAX_ROWS = 1000
CHARACTERS = {
    "standard": "@%#*+=-:. ",
    "blocks": "█▓▒░ ",
    "simple": "#*-. ",
    "binary": "10 ",
    "dense": "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
    "minimal": "█ ",
    "retro": "MWNXK0Okxdolc:,. ",
    "symbols": "@$#%&+=<>!?* ",
    "arabic": "شسضصغعقهومنبترزا. ",
}
LAYER_LABELS = {"ASCII Art": "ASCII Art", "Original Image": "Original Image",
                "Original Overlay": "Original Overlay", "Background": "Background"}
OPTION_LABELS = {"font_size": "Font size", "font_scale": "Font scale",
                 "character_spacing": "Character spacing", "line_height": "Line height",
                 "contrast": "Contrast", "brightness": "Brightness",
                 "overlay_opacity": "Overlay opacity", "blur_strength": "Blur strength"}
QUALITY = {"low": 40, "medium": 80, "high": 120, "ultra": 200}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
RESAMPLE_BOX = getattr(Image, "Resampling", Image).BOX


def number(value):
    """Compact SVG floats, without loss at normal document scales."""
    return format(float(value), ".10g")


def checked_range(value, low, high, label):
    if not math.isfinite(value) or not low <= value <= high:
        raise inkex.AbortExtension(f"{label} must be between {low} and {high}.")
    return value


def rgba_color(value):
    """Accept Inkscape's unsigned RGBA decimal, plus CSS for CLI use."""
    try:
        raw = str(value).strip()
        if raw.startswith("0x") or raw.lstrip("-").isdigit():
            integer = int(raw, 0) if raw.startswith("0x") else int(raw)
            if not 0 <= integer <= 0xFFFFFFFF:
                raise ValueError("RGBA out of range")
            return tuple((integer >> shift) & 255 for shift in (24, 16, 8, 0))
        color = inkex.Color(raw).to_rgba()
        if len(color) != 4:
            raise ValueError("No color")
        return tuple(int(c) for c in color[:3]) + (round(color[3] * 255),)
    except (ValueError, KeyError, TypeError) as error:
        raise inkex.AbortExtension(f"Invalid color: {value}") from error


def fill_style(rgba):
    return {"fill": "#{:02x}{:02x}{:02x}".format(*rgba[:3]),
            "fill-opacity": number(rgba[3] / 255)}


def split_characters(sequence):
    """One base letter plus its marks per cell, including Arabic harakat.

    This deliberately supports letters/marks rather than arbitrary emoji ZWJ
    sequences. Grid cells are independent symbols, not connected words.
    """
    cells = []
    for char in unicodedata.normalize("NFC", sequence):
        category = unicodedata.category(char)
        if category.startswith("C") or (char.isspace() and char != " "):
            raise inkex.AbortExtension("Use visible characters. Newlines, control characters and invisible joiners are unsupported.")
        if category.startswith("M"):
            if not cells or cells[-1].isspace():
                raise inkex.AbortExtension("Place each diacritic after its base letter, never alone or after a space.")
            cells[-1] += char
        else:
            cells.append(char)
    return tuple(cells)


def is_rtl(cell):
    return any(unicodedata.bidirectional(char) in ("R", "AL", "AN") for char in cell)


def character_sequence(name, custom, invert=False):
    if name == "custom":
        sequence = custom
        if not sequence or not sequence.strip():
            raise inkex.AbortExtension("Custom characters must contain at least one visible glyph.")
        if len(sequence) > 1024:
            raise inkex.AbortExtension("Custom characters are too long. The limit is 256 glyphs with their diacritics.")
    else:
        try:
            sequence = CHARACTERS[name]
        except KeyError as error:
            raise inkex.AbortExtension("Unknown character preset.") from error
    cells = split_characters(sequence)
    if len(cells) > 256:
        raise inkex.AbortExtension("Custom characters are limited to 256 glyphs.")
    # Invert symbols, never split a letter from its diacritics.
    return cells[::-1] if invert else cells


def map_characters(gray, alpha, sequence):
    """Dark-to-dense mapping; alpha zero is always an empty cell, even inverted."""
    return [" " if a == 0 else sequence[min(len(sequence) - 1, v * len(sequence) // 256)]
            for v, a in zip(pixels(gray), pixels(alpha))]


def pixels(image):
    # Pillow 12.3 renamed getdata; keep compatibility with Linux distro versions.
    method = getattr(image, "get_flattened_data", None)
    return method() if method else image.getdata()


def viewport_image(image, size, preserve_aspect_ratio):
    """Rasterize the SVG image viewport, including meet/slice and alignment.

    Render four samples per axis before BOX averaging. Cropping before resizing
    avoids allocating a huge intermediate image for extreme slice aspect ratios.
    """
    width, height = size
    tokens = (preserve_aspect_ratio or "xMidYMid meet").split()
    if tokens and tokens[0] == "defer":
        tokens.pop(0)
    align = tokens[0] if tokens else "xMidYMid"
    if align == "none":
        return image.resize(size, RESAMPLE_BOX)
    if align not in {"x" + x + "Y" + y for x in ("Min", "Mid", "Max")
                     for y in ("Min", "Mid", "Max")}:
        raise inkex.AbortExtension("Unsupported preserveAspectRatio alignment.")
    mode = tokens[1] if len(tokens) > 1 else "meet"
    if mode not in ("meet", "slice"):
        raise inkex.AbortExtension("Unsupported preserveAspectRatio mode.")
    fx = {"Min": 0, "Mid": 0.5, "Max": 1}[align[1:4]]
    fy = {"Min": 0, "Mid": 0.5, "Max": 1}[align[5:8]]
    iw, ih = image.size
    scale = (min if mode == "meet" else max)(width / iw, height / ih)
    if mode == "slice":
        cw, ch = min(iw, width / scale), min(ih, height / scale)
        left, top = (iw - cw) * fx, (ih - ch) * fy
        return image.resize(size, RESAMPLE_BOX, box=(left, top, left + cw, top + ch))
    rw, rh = max(1, round(iw * scale)), max(1, round(ih * scale))
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    resized = image.resize((min(width, rw), min(height, rh)), RESAMPLE_BOX)
    canvas.alpha_composite(resized, (round((width - resized.width) * fx),
                                     round((height - resized.height) * fy)))
    return canvas


def analyze(image, columns, rows, viewport_ratio, par, matte, contrast, brightness,
            edge_detection, hybrid, sequence):
    """Average RGB/alpha separately from adjusted luma; keep source colors intact."""
    # Sampling canvas has the viewport's physical aspect ratio, not glyph aspect ratio.
    # It must have enough pixels for the denser axis; bounded by the cell budget.
    sample_width = max(columns * 4, round(rows * 4 * viewport_ratio))
    sample_height = max(rows * 4, round(columns * 4 / viewport_ratio))
    # Extreme viewport proportions can need a very large canvas. A proportional cap
    # keeps aspect handling correct and still oversamples the dense grid axis.
    scale = min(1, math.sqrt(4_000_000 / (sample_width * sample_height)))
    sample_size = (max(1, round(sample_width * scale)), max(1, round(sample_height * scale)))
    viewport = viewport_image(image, sample_size, par)
    colors = viewport.resize((columns, rows), RESAMPLE_BOX)
    # A translucent custom background is analyzed over a white page, like transparency.
    matte_rgb = tuple(round(c * matte[3] / 255 + 255 - matte[3]) for c in matte[:3])
    matte_image = Image.new("RGBA", viewport.size, matte_rgb + (255,))
    gray = Image.alpha_composite(matte_image, viewport).convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(contrast)
    gray = ImageEnhance.Brightness(gray).enhance(brightness)
    if edge_detection or hybrid:
        edges = gray.filter(ImageFilter.FIND_EDGES)
        # FIND_EDGES leaves unfiltered pixels on the border, creating a false frame.
        if edges.width > 2 and edges.height > 2:
            borderless = Image.new("L", edges.size, 0)
            borderless.paste(edges.crop((1, 1, edges.width - 1, edges.height - 1)), (1, 1))
            edges = borderless
        # Normalize after averaging so thin edges survive low-resolution grids.
        edges = edges.resize((columns, rows), RESAMPLE_BOX)
        # Suppress tiny quantization changes in otherwise smooth gradients.
        edges = ImageOps.autocontrast(edges.point(lambda value: max(0, value - 4)))
        edge_darkness = ImageOps.invert(edges)
        gray = gray.resize((columns, rows), RESAMPLE_BOX)
        gray = Image.blend(gray, edge_darkness, 0.5) if hybrid else edge_darkness
    else:
        gray = gray.resize((columns, rows), RESAMPLE_BOX)
    return map_characters(gray, colors.getchannel("A"), sequence), list(pixels(colors))


class AsciiArtPro(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="general")
        pars.add_argument("--sequence", default="standard")
        pars.add_argument("--custom_characters", default="@#%*+=-:. ")
        pars.add_argument("--quality", default="manual")
        pars.add_argument("--columns", type=int, default=80)
        pars.add_argument("--font_size", type=float, default=12)
        pars.add_argument("--font_family", default="monospace")
        pars.add_argument("--custom_font", default="DejaVu Sans Mono")
        pars.add_argument("--font_scale", type=float, default=1)
        pars.add_argument("--character_spacing", type=float, default=0)
        pars.add_argument("--line_height", type=float, default=1.2)
        pars.add_argument("--layout", default="fit")
        pars.add_argument("--contrast", type=float, default=1)
        pars.add_argument("--brightness", type=float, default=1)
        pars.add_argument("--invert", type=inkex.Boolean, default=False)
        pars.add_argument("--edge_detection", type=inkex.Boolean, default=False)
        pars.add_argument("--hybrid", type=inkex.Boolean, default=False)
        pars.add_argument("--original_colors", type=inkex.Boolean, default=False)
        pars.add_argument("--ascii_color", default="255")
        pars.add_argument("--background", default="transparent")
        pars.add_argument("--background_color", default="4294967295")
        pars.add_argument("--overlay_original", type=inkex.Boolean, default=False)
        pars.add_argument("--overlay_opacity", type=float, default=0.25)
        pars.add_argument("--blur_strength", type=float, default=0)
        pars.add_argument("--original_action", default="preserve")
        pars.add_argument("--separate_layers", type=inkex.Boolean, default=True)
        pars.add_argument("--convert_to_paths", type=inkex.Boolean, default=False)

    def validate_options(self):
        o = self.options
        for name, low, high in (("font_size", 1, 200), ("font_scale", 0.1, 5),
                                ("character_spacing", -0.4, 3), ("line_height", 0.5, 3),
                                ("contrast", 0, 5), ("brightness", 0, 5),
                                ("overlay_opacity", 0, 1), ("blur_strength", 0, 100)):
            checked_range(getattr(o, name), low, high, OPTION_LABELS[name])
        checked_range(o.columns, 20, 500, "Columns")
        if o.quality not in {"manual", *QUALITY}:
            raise inkex.AbortExtension("Unknown quality setting.")
        if o.layout not in ("fit", "font") or o.original_action not in ("preserve", "replace"):
            raise inkex.AbortExtension("Unknown text layout or original image action.")
        if o.font_family not in ("monospace", "Courier New", "Consolas", "Liberation Mono",
                                  "DejaVu Sans Mono", "Noto Sans Arabic", "Noto Naskh Arabic",
                                  "Amiri", "DejaVu Sans", "custom"):
            raise inkex.AbortExtension("Unknown font family.")
        font = o.custom_font if o.font_family == "custom" else o.font_family
        if not font.strip() or any(c in font for c in "\n\r\t;{}"):
            raise inkex.AbortExtension("Enter a valid font family name.")
        self.sequence = character_sequence(o.sequence, o.custom_characters, o.invert)
        self.independent_cells = any(is_rtl(cell) or len(cell) > 1 for cell in self.sequence)
        self.ascii_rgba = rgba_color(o.ascii_color)
        backgrounds = {"transparent": (255, 255, 255, 0), "white": (255, 255, 255, 255),
                       "black": (0, 0, 0, 255), "custom": rgba_color(o.background_color)}
        if o.background not in backgrounds:
            raise inkex.AbortExtension("Unknown background type.")
        self.background_rgba = backgrounds[o.background]
        self.font = font if font == "monospace" else f"'{font.replace(chr(39), '')}', monospace"
        if self.independent_cells:
            # Preserve the user's first choice while offering installed Arabic fallbacks.
            self.font = f"'{font.replace(chr(39), '')}', 'Noto Sans Arabic', 'DejaVu Sans', sans-serif"

    def read_source(self, node):
        href = node.get("href") or node.get("{http://www.w3.org/1999/xlink}href")
        if not href:
            raise inkex.AbortExtension("The selected image has no href or xlink:href.")
        if href.startswith("data:"):
            header, separator, encoded = href.partition(",")
            if not separator or ";base64" not in header.lower():
                raise inkex.AbortExtension("Embedded image data must use Base64.")
            if not header.lower().startswith("data:image/"):
                raise inkex.AbortExtension("Embedded data is not an image.")
            encoded = "".join(encoded.split())
            if len(encoded) > (MAX_FILE_BYTES + 2) // 3 * 4:
                raise inkex.AbortExtension("The embedded image exceeds the 64 MiB limit.")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise inkex.AbortExtension("Invalid Base64 image data.") from error
        else:
            parsed = urlsplit(href)
            if parsed.scheme not in ("", "file") or parsed.netloc not in ("", "localhost"):
                raise inkex.AbortExtension("Use an embedded image or a linked local file. Internet links are unsupported.")
            path = Path(unquote(parsed.path)).expanduser()
            candidates = []
            if path.is_absolute():
                candidates.append(path)
            else:
                doc = self.document_path()
                if doc:
                    candidates.append(Path(doc).parent / path)
                else:
                    input_file = self.options.input_file
                    if isinstance(input_file, str):
                        candidates.append(Path(input_file).absolute().parent / path)
            # Inkscape's absolute reference is a fallback only, never preferred to href.
            absref = node.get("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}absref")
            if absref and Path(absref).is_absolute():
                candidates.append(Path(absref))
            actual = next((p for p in candidates if p.is_file()), None)
            if actual is None:
                raise inkex.AbortExtension("Cannot find the linked image. Save the SVG beside the image or embed it first.")
            try:
                with actual.open("rb") as handle:
                    raw = handle.read(MAX_FILE_BYTES + 1)
            except OSError as error:
                raise inkex.AbortExtension("Cannot read the linked image file.") from error
        if len(raw) > MAX_FILE_BYTES:
            raise inkex.AbortExtension("The image exceeds the 64 MiB limit.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise inkex.AbortExtension("The image exceeds 20 million pixels. Resize it before converting.")
                    # Inkscape displays raw pixel orientation; respect the embedded raster.
                    return image.convert("RGBA")
        except (OSError, ValueError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as error:
            raise inkex.AbortExtension("Pillow cannot decode the image. Use PNG or JPEG.") from error

    def geometry(self, node):
        def length(name, default=None):
            value = node.get(name, default)
            if value is None:
                raise inkex.AbortExtension(f"The image needs an explicit {name} value.")
            try:
                if str(value).endswith("%"):
                    # Percentages refer to the nearest SVG viewport (SVG specification).
                    viewport = node.getparent()
                    while viewport is not None and viewport.tag != inkex.addNS("svg", "svg"):
                        viewport = viewport.getparent()
                    if viewport is None:
                        viewport = self.svg
                    vb = viewport.get("viewBox")
                    if vb:
                        parts = [float(v) for v in vb.replace(",", " ").split()]
                        reference = parts[2 if name in ("x", "width") else 3]
                    else:
                        reference = viewport.to_dimensionless(viewport.get(
                            "width" if name in ("x", "width") else "height"))
                    result = float(str(value)[:-1]) * reference / 100
                else:
                    result = node.to_dimensionless(value)
                if not math.isfinite(result):
                    raise ValueError("Nonfinite length")
                return result
            except (ValueError, TypeError, IndexError) as error:
                raise inkex.AbortExtension(f"Cannot read image property {name}: {value}") from error
        x, y, width, height = (length("x", "0"), length("y", "0"), length("width"), length("height"))
        if width <= 0 or height <= 0:
            raise inkex.AbortExtension("Image width and height must be greater than zero.")
        return x, y, width, height

    def make_group(self, label):
        group = inkex.Layer() if self.options.separate_layers else inkex.Group()
        group.set("inkscape:label", LAYER_LABELS.get(label, label))
        group.set("id", self.unique_id("ascii-" + label.lower().replace(" ", "-")))
        return group

    def unique_id(self, prefix):
        # Detached elements are not in svg.ids yet. Reserve IDs until commit.
        identifier = self.svg.get_unique_id(prefix, blacklist=self.generated_ids)
        self.generated_ids.add(identifier)
        return identifier

    def make_text(self, chars, colors, columns, rows, x, y, advance, line_advance, font_size):
        group = self.make_group("ASCII Art")
        common = {"font-family": self.font, "font-size": number(font_size),
                  "font-style": "normal", "font-weight": "normal", "font-stretch": "normal",
                  "font-variant": "normal", "text-anchor": "start", "stroke": "none",
                  "direction": "ltr", "writing-mode": "lr-tb", "white-space": "pre",
                  "font-variant-ligatures": "none", "letter-spacing": "0px",
                  "word-spacing": "0px", "line-height": number(self.options.line_height),
                  **fill_style(self.ascii_rgba)}
        positions = " ".join(number(x + col * advance) for col in range(columns))
        for row in range(rows):
            start = row * columns
            rowchars = chars[start:start + columns]
            if not "".join(rowchars).strip():
                continue
            text = inkex.TextElement()
            text.set("id", self.unique_id("ascii-row"))
            text.set("x", number(x) if self.independent_cells else positions)
            text.set("y", number(y + row * line_advance + font_size * 0.82))
            text.set(XML_SPACE, "preserve")
            text.style = common
            if not self.options.original_colors:
                # Alpha must survive even in monochrome. Runs keep one text per line.
                rowcolors = [self.ascii_rgba[:3] + (round(c[3] * self.ascii_rgba[3] / 255),)
                             for c in colors[start:start + columns]]
            else:
                rowcolors = colors[start:start + columns]
            if self.independent_cells:
                # Each absolute x/y starts a separate SVG text chunk: bidi ordering
                # and ligatures stay within a cell, and Arabic marks stay on the letter.
                # One TextElement per row is retained, bounded by MAX_CELLS.
                text.set("data-ascii-cell-layout", "independent")
                for col, (cell, color) in enumerate(zip(rowchars, rowcolors)):
                    if not cell.strip():
                        continue
                    span = inkex.Tspan()
                    span.set("x", number(x + (col + 0.5) * advance))
                    span.set("y", text.get("y"))
                    span.set("data-ascii-column", str(col))
                    span.text = cell
                    # Inkscape 1.4 can shape across positioned tspan boundaries.
                    # An explicit non-joiner prevents adjacent lam/alef or beh/teh
                    # from merging, without separating a letter from its marks.
                    span.tail = "\u200c"
                    span.style = {**fill_style(color), "text-anchor": "middle",
                                  "direction": "rtl" if is_rtl(cell) else "ltr"}
                    text.append(span)
            elif len(set(rowcolors)) == 1:
                text.text = "".join(rowchars)
                text.style.update(fill_style(rowcolors[0]))
            else:
                # Quantize colors mildly, merging adjacent equal colors into one tspan.
                runs = []
                for char, color in zip(rowchars, rowcolors):
                    rgba = tuple(min(255, round(c / 8) * 8) for c in color[:3]) + (color[3],)
                    if runs and runs[-1][0] == rgba:
                        runs[-1][1] += char
                    else:
                        runs.append([rgba, char])
                for color, content in runs:
                    span = inkex.Tspan()
                    span.text = content
                    span.style = fill_style(color)
                    text.append(span)
            group.append(text)
        return group

    def to_paths(self, text_group, geometry):
        """Convert only generated text in an isolated file using Inkscape's renderer."""
        from inkex.command import inkscape, CommandNotFound, ProgramRunError
        x, y, width, height = geometry
        root = inkex.SvgDocumentElement()
        root.set("width", number(width))
        root.set("height", number(height))
        root.set("viewBox", " ".join(map(number, geometry)))
        root.append(copy.deepcopy(text_group))
        with tempfile.TemporaryDirectory(prefix="ascii-art-pro-") as directory:
            source = os.path.join(directory, "text.svg")
            output = os.path.join(directory, "paths.svg")
            etree.ElementTree(root).write(source, encoding="utf-8", xml_declaration=True)
            try:
                inkscape(source, batch_process=True, export_type="svg", export_filename=output,
                         actions=f"select-by-id:{text_group.get('id')};object-to-path;export-do")
                converted = inkex.load_svg(output).getroot()
            except (CommandNotFound, ProgramRunError, OSError, etree.XMLSyntaxError) as error:
                raise inkex.AbortExtension("Text to path conversion failed. Ensure Inkscape is on PATH or disable Convert text to paths.") from error
        group = converted.getElementById(text_group.get("id"))
        if group is None or group.xpath(".//svg:text"):
            raise inkex.AbortExtension("Inkscape did not convert all text to paths. The original image was kept unchanged.")
        group = copy.deepcopy(group)
        for descendant in group.iterdescendants():
            if descendant.get("id"):
                descendant.set("id", self.unique_id("ascii-path"))
        return group

    def effect(self):
        self.generated_ids = set()
        self.validate_options()
        selected = list(self.svg.selection.values())
        if len(selected) != 1 or not isinstance(selected[0], inkex.Image):
            raise inkex.AbortExtension("Select exactly one raster image before running ASCII Art Pro.")
        node = selected[0]
        image = self.read_source(node)
        x, y, width, height = self.geometry(node)
        o = self.options
        columns = QUALITY.get(o.quality, o.columns)
        nominal = o.font_size * o.font_scale
        advance = nominal * (0.6 + o.character_spacing)
        line_advance = nominal * o.line_height
        fit_scale = width / (columns * advance) if o.layout == "fit" else 1
        font_size = nominal * fit_scale
        advance *= fit_scale
        line_advance *= fit_scale
        row_estimate = height / line_advance
        # Abort rather than silently destroy aspect ratio or create a giant SVG.
        if row_estimate > min(MAX_ROWS, MAX_CELLS // columns) + 0.5:
            raise inkex.AbortExtension("The grid exceeds 100,000 cells or 1,000 rows. Reduce columns or increase line height or font size.")
        rows = max(1, round(row_estimate))
        # Exact fit uses all image height; font-size mode keeps requested line spacing.
        if o.layout == "fit":
            line_advance = height / rows
        chars, colors = analyze(image, columns, rows, width / height,
                                node.get("preserveAspectRatio"), self.background_rgba,
                                o.contrast, o.brightness, o.edge_detection, o.hybrid, self.sequence)
        result = inkex.Group()
        result.set("id", self.unique_id("ascii-art-pro"))
        result.set("inkscape:label", "ASCII Art")
        result.set("data-ascii-art-pro-version", VERSION)
        result.set("data-ascii-columns", str(columns))
        result.set("data-ascii-rows", str(rows))
        if node.get("transform"):
            result.transform = copy.deepcopy(node.transform)
        # Stay in the same parent coordinate system; retain source clipping and opacity.
        specified = node.specified_style()
        result.style = {key: specified[key] for key in
                        ("opacity", "visibility", "display", "mix-blend-mode")
                        if key in specified}
        for key in ("clip-path", "mask"):
            if key in specified:
                result.set(key, str(specified[key]))
        definitions = []
        # Clip glyphs and blur to the source viewport; retain any original clip separately.
        viewport_group = inkex.Group()
        clip = inkex.ClipPath()
        clip_id = self.unique_id("ascii-viewport-clip")
        clip.set("id", clip_id)
        clip.set("clipPathUnits", "userSpaceOnUse")
        clip.append(inkex.Rectangle.new(x, y, width, height))
        definitions.append(clip)
        viewport_group.set("clip-path", f"url(#{clip_id})")
        result.append(viewport_group)
        if self.background_rgba[3]:
            background = self.make_group("Background")
            rect = inkex.Rectangle.new(x, y, width, height)
            rect.style = {**fill_style(self.background_rgba), "stroke": "none"}
            background.append(rect)
            viewport_group.append(background)
        if o.overlay_original:
            overlay = self.make_group("Original Overlay")
            preview = inkex.Image()
            for key, value in zip(("x", "y", "width", "height"), (x, y, width, height)):
                preview.set(key, number(value))
            preview.set("preserveAspectRatio", node.get("preserveAspectRatio", "xMidYMid meet"))
            # Embed even linked sources so the output remains portable after replacement.
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            preview.set("xlink:href", "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"))
            preview.style = {"opacity": number(o.overlay_opacity)}
            if o.blur_strength:
                blur = inkex.Filter()
                blur_id = self.unique_id("ascii-overlay-blur")
                blur.set("id", blur_id)
                blur.set("filterUnits", "userSpaceOnUse")
                margin = o.blur_strength * 3
                for key, value in zip(("x", "y", "width", "height"),
                                      (x - margin, y - margin, width + 2 * margin, height + 2 * margin)):
                    blur.set(key, number(value))
                blur.add_primitive("feGaussianBlur", stdDeviation=number(o.blur_strength))
                definitions.append(blur)
                preview.style["filter"] = f"url(#{blur_id})"
            overlay.append(preview)
            viewport_group.append(overlay)
        text = self.make_text(chars, colors, columns, rows, x, y, advance, line_advance, font_size)
        if o.convert_to_paths and len(text):
            text = self.to_paths(text, (x, y, width, height))
        viewport_group.append(text)
        # Commit document mutations only after decoding, analysis and path conversion succeed.
        parent = node.getparent()
        index = parent.index(node)
        for definition in definitions:
            self.svg.defs.append(definition)
        if o.original_action == "replace":
            parent.replace(node, result)
        elif o.separate_layers:
            original = self.make_group("Original Image")
            original.style = {"display": "none"}
            parent.insert(index, original)
            original.append(node)
            parent.insert(index + 1, result)
        else:
            node.style["display"] = "none"
            parent.insert(index + 1, result)


if __name__ == "__main__":
    AsciiArtPro().run()
