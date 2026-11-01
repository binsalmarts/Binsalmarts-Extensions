#!/usr/bin/env python3
"""Export selected icon/wordmark artwork as a complete, offline logo kit."""
import base64
from copy import deepcopy
from dataclasses import dataclass
import html
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

import inkex
from lxml import etree
import tinycss2
try:
    from PIL import Image, ImageChops
except ImportError as error:
    raise inkex.AbortExtension("Logo Export Pro requires Pillow in Inkscape's Python environment.") from error

VERSION = "2.0.0"
LAYOUTS = ("as_designed", "horizontal", "vertical", "icon", "wordmark")
SOURCE_MODES = ("ready", "complete", "paired", "icon", "wordmark")
ROLE_ATTRIBUTES = {"icon": "data-logo-export-icon-id", "wordmark": "data-logo-export-wordmark-id"}
VARIANT_ATTRIBUTE = "data-logo-export-role"
READY_LAYOUTS = ("horizontal", "vertical", "icon", "wordmark")
COLORS = ("original", "black", "white")
FORMATS = ("svg", "png", "pdf", "jpg", "eps")
DRAWABLES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "use"}
URL_REF = re.compile(r"url\(\s*['\"]?#([^\s)'\"]+)['\"]?\s*\)")
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_RASTER_PIXELS = 32_000_000


def svg_number(value):
    return format(float(value), ".12g")


def bounded(value, low, high, label):
    if not math.isfinite(value) or not low <= value <= high:
        raise inkex.AbortExtension(f"{label} must be between {low} and {high}.")


def parse_raster_sizes(text):
    pieces = [p.strip() for p in re.split(r"[,;\s]+", text) if p.strip()]
    if not pieces or len(pieces) > 8 or any(not p.isascii() or not p.isdecimal() for p in pieces):
        raise inkex.AbortExtension("Enter 1–8 raster sizes, such as 512, 1024, 2048.")
    sizes = sorted(set(map(int, pieces)))
    for size in sizes:
        bounded(size, 16, 8192, "Raster size (px)")
    return sizes


def safe_stem(text):
    text = text.strip()
    stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in text)
    stem = re.sub(r"-+", "-", stem).strip("-_")
    if not stem or len(stem) > 80:
        raise inkex.AbortExtension("Enter a brand name containing letters or numbers, up to 80 characters.")
    if stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        stem = "brand-" + stem
    return stem


def css_color(value):
    try:
        raw = str(value).strip()
        if raw.startswith("0x") or raw.isdecimal():
            rgba = int(raw, 0) if raw.startswith("0x") else int(raw)
            if not 0 <= rgba <= 0xFFFFFFFF:
                raise ValueError("Invalid RGBA")
            rgb = [(rgba >> shift) & 255 for shift in (24, 16, 8)]
        else:
            rgb = inkex.Color(raw).to_rgb()
        return "#{:02x}{:02x}{:02x}".format(*rgb)
    except (ValueError, TypeError, KeyError) as error:
        raise inkex.AbortExtension("Choose a valid background color.") from error


@dataclass
class Component:
    svg: object
    width: float
    height: float
    x: float = 0
    y: float = 0


@dataclass
class Placement:
    role: str
    x: float
    y: float
    width: float
    height: float


def layout_geometry(icon, wordmark, layout, icon_height, wordmark_height, gap, padding, side="left", square=True):
    iw, ih = icon.width * icon_height / icon.height, icon_height
    nw, nh = wordmark.width * wordmark_height / wordmark.height, wordmark_height
    if layout == "horizontal":
        width, height = iw + gap + nw, max(ih, nh)
        ix, nx = (0, iw + gap) if side == "left" else (nw + gap, 0)
        placements = [Placement("icon", ix, (height - ih) / 2, iw, ih),
                      Placement("wordmark", nx, (height - nh) / 2, nw, nh)]
    elif layout == "vertical":
        width, height = max(iw, nw), ih + gap + nh
        placements = [Placement("icon", (width - iw) / 2, 0, iw, ih),
                      Placement("wordmark", (width - nw) / 2, ih + gap, nw, nh)]
    elif layout == "icon":
        width, height = (max(iw, ih),) * 2 if square else (iw, ih)
        placements = [Placement("icon", (width - iw) / 2, (height - ih) / 2, iw, ih)]
    elif layout == "wordmark":
        width, height = nw, nh
        placements = [Placement("wordmark", 0, 0, nw, nh)]
    else:
        raise inkex.AbortExtension("Unknown logo layout.")
    for placement in placements:
        placement.x += padding
        placement.y += padding
    return width + 2 * padding, height + 2 * padding, placements


def current_geometry(components, padding):
    left = min(c.x for c in components.values())
    top = min(c.y for c in components.values())
    right = max(c.x + c.width for c in components.values())
    bottom = max(c.y + c.height for c in components.values())
    return right - left + 2 * padding, bottom - top + 2 * padding, [
        Placement(role, c.x - left + padding, c.y - top + padding, c.width, c.height)
        for role, c in components.items()]


def component_gap(icon, wordmark):
    dx = max(0, wordmark.x - icon.x - icon.width, icon.x - wordmark.x - wordmark.width)
    dy = max(0, wordmark.y - icon.y - icon.height, icon.y - wordmark.y - wordmark.height)
    return math.hypot(dx, dy)


def artwork_role(node):
    """Explicit object tags take priority over optional layer/group labels."""
    role = node.get(VARIANT_ATTRIBUTE)
    if role in READY_LAYOUTS:
        return role
    aliases = {
        "horizontal": ("horizontal", "horizontal logo", "logo horizontal", "افقي", "أفقي", "الشعار الأفقي"),
        "vertical": ("vertical", "vertical logo", "logo vertical", "عمودي", "رأسي", "راسي", "الشعار العمودي"),
        "icon": ("icon", "symbol", "logo icon", "logo symbol", "أيقونة", "ايقونة", "ايقونه", "أيقونه", "رمز"),
        "wordmark": ("name", "wordmark", "logo name", "logo wordmark", "اسم", "الاسم", "نص", "الشعار النصي"),
    }
    label = node.get(inkex.addNS("label", "inkscape"), "").strip().casefold()
    label = re.sub(r"[-_\s]+", " ", label)
    return next((key for key, values in aliases.items() if label in values), None)


def visual_signature(path, allow_empty=False):
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        if allow_empty:
            return None
        raise inkex.AbortExtension("A logo component is empty. Check its visibility.")
    rgba = rgba.crop(bbox)
    ratio = rgba.width / rgba.height
    rgba.thumbnail((128, 128), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (128, 128))
    canvas.paste(rgba, ((128 - rgba.width) // 2, (128 - rgba.height) // 2))
    alpha = canvas.getchannel("A")
    # Premultiply to make RGB in fully transparent pixels immaterial.
    channels = [ImageChops.multiply(channel, alpha) for channel in canvas.convert("RGB").split()]
    return ratio, Image.merge("RGBA", (*channels, alpha))


def visual_distance(first, second):
    if abs(math.log(first[0] / second[0])) > 0.08:
        return 1.0
    histogram = ImageChops.difference(first[1], second[1]).histogram()
    return sum((index % 256) * count for index, count in enumerate(histogram)) / (128 * 128 * 4 * 255)


def export_geometry(components, layout, options):
    if layout == "as_designed":
        return current_geometry(components, options.padding)
    icon, name = components.get("icon"), components.get("wordmark")
    mode = getattr(options, "sizing_mode", "original")
    ih = icon.height if icon else 1
    nh = name.height if name else 1
    if mode == "manual":
        ih, nh = options.icon_height, options.wordmark_height
    elif mode == "balanced" and icon and name:
        ih = (name.width * options.vertical_balance * icon.height / icon.width
              if layout == "vertical" else name.height * options.horizontal_balance)
    if layout in ("icon", "wordmark"):
        role, part, height = ("icon", icon, ih) if layout == "icon" else ("wordmark", name, nh)
        width = part.width * height / part.height
        cw, ch = (max(width, height),) * 2 if role == "icon" and options.square_icon else (width, height)
        return cw + 2 * options.padding, ch + 2 * options.padding, [
            Placement(role, options.padding + (cw - width) / 2, options.padding + (ch - height) / 2, width, height)]
    gap = (component_gap(icon, name) if getattr(options, "gap_mode", "current") == "current" else options.gap)
    return layout_geometry(icon, name, layout, ih, nh, gap, options.padding,
                           options.icon_side, options.square_icon)


def prefix_ids(svg, prefix):
    """Keep defs, clones and CSS references local to each nested component."""
    mapping = {node.get("id"): prefix + node.get("id") for node in svg.iter() if node.get("id")}
    def urls(value):
        return URL_REF.sub(lambda m: "url(#" + mapping.get(m[1], m[1]) + ")", value)
    def rewrite_tokens(tokens, selectors=False):
        for token in tokens:
            if selectors and token.type == "hash" and token.is_identifier and token.value in mapping:
                token.value = mapping[token.value]
            if hasattr(token, "content") and token.content:
                rewrite_tokens(token.content, selectors)
            if hasattr(token, "arguments"):
                rewrite_tokens(token.arguments, selectors)
    def rewrite_rules(rules):
        for rule in rules:
            if rule.type == "qualified-rule":
                rewrite_tokens(rule.prelude, True)
            elif rule.type == "at-rule" and rule.content and rule.lower_at_keyword in ("media", "supports", "layer"):
                children = tinycss2.parse_rule_list(rule.content)
                rewrite_rules(children)
                rule.content = tinycss2.parse_component_value_list(tinycss2.serialize(children))
    for node in svg.iter():
        if not isinstance(node.tag, str):
            continue
        for key, value in list(node.attrib.items()):
            if key == "id":
                node.attrib[key] = mapping[value]
            elif etree.QName(key).localname == "href" and value.startswith("#"):
                node.attrib[key] = "#" + mapping.get(value[1:], value[1:])
            elif key in ("aria-labelledby", "aria-describedby"):
                node.attrib[key] = " ".join(mapping.get(part, part) for part in value.split())
            else:
                node.attrib[key] = urls(value)
        if etree.QName(node).localname == "style" and node.text:
            rules = tinycss2.parse_stylesheet(urls(node.text), skip_comments=False, skip_whitespace=False)
            rewrite_rules(rules)
            node.text = tinycss2.serialize(rules)


def build_master(components, layout, options):
    width, height, placements = export_geometry(components, layout, options)
    root = inkex.SvgDocumentElement()
    root.set("width", svg_number(width))
    root.set("height", svg_number(height))
    root.set("viewBox", f"0 0 {svg_number(width)} {svg_number(height)}")
    for placement in placements:
        svg = deepcopy(components[placement.role].svg)
        prefix_ids(svg, placement.role + "-")
        for key in ("x", "y", "width", "height"):
            svg.set(key, svg_number(getattr(placement, key)))
        svg.set("preserveAspectRatio", "xMidYMid meet")
        svg.set("overflow", "visible")
        svg.set("data-logo-export-component", placement.role)
        root.append(svg)
    return root


def image_rgba(node):
    href = node.get("href") or node.get(inkex.addNS("href", "xlink"), "")
    try:
        header, data = href.split(",", 1)
        if not header.startswith("data:image/") or ";base64" not in header.lower():
            raise ValueError("Not embedded")
        payload = base64.b64decode(data, validate=True)
        if len(payload) > MAX_ASSET_BYTES:
            raise ValueError("Too large")
        with Image.open(io.BytesIO(payload)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Too many pixels")
            return image.convert("RGBA")
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise inkex.AbortExtension("A logo image is not a supported embedded raster image. Embed it as PNG or JPEG first.") from error


def pure_white_mask(image):
    rgb = image.convert("RGB")
    channels = [channel.point([0] * 255 + [255]) for channel in rgb.split()]
    return ImageChops.multiply(ImageChops.multiply(channels[0], channels[1]), channels[2])


def paint_rgba(style, key):
    raw = style.get(key, "#000000" if key == "fill" else "none")
    if raw == "currentColor":
        raw = style.get("color", "#000000")
    if raw == "none" or raw.startswith("url("):
        return None
    try:
        return inkex.Color(raw).to_rgba(style.get(key + "-opacity", "1"))
    except (ValueError, TypeError, KeyError):
        return None


def force_style(node, values):
    """Write importance explicitly: Inkex 1.4's serializer drops that flag."""
    style = node.style
    importance = {key for key in style if style.get_importance(key)}
    style.update(values)
    importance.update(values)
    # BaseElement.set("style", ...) also serializes through Inkex. Write the
    # XML attribute directly after every style operation has finished.
    node.attrib["style"] = ";".join(f"{key}:{value}" + (" !important" if key in importance else "")
                                    for key, value in style.items())


def monochrome(master, color, preserve_cutouts=True):
    """A vector luminance mask preserves holes, transparency and paint order."""
    content = deepcopy(master)
    for component in list(content):
        styles = {node: dict(node.specified_style()) for node in component.iter() if isinstance(node, inkex.BaseElement)}
        identifiers = {node.get("id"): node for node in component.iter() if node.get("id")}
        images = {node: image_rgba(node) for node in component.iter() if isinstance(node, inkex.Image)}
        def resource(node):
            return any(etree.QName(parent).localname in ("defs", "clipPath", "mask") for parent in node.iterancestors())
        has_nonwhite = False
        for node, style in styles.items():
            if resource(node):
                continue
            if node in images:
                image = images[node]
                nonwhite = ImageChops.multiply(ImageChops.invert(pure_white_mask(image)), image.getchannel("A"))
                has_nonwhite |= nonwhite.getbbox() is not None
            elif etree.QName(node).localname in DRAWABLES:
                for key in ("fill", "stroke"):
                    rgba = paint_rgba(style, key)
                    if rgba is not None and rgba[3] > 0 and tuple(rgba[:3]) != (255, 255, 255):
                        has_nonwhite = True
                    for ref in URL_REF.findall(style.get(key, "")):
                        gradient = identifiers.get(ref)
                        if gradient is not None:
                            for stop in gradient.iter(inkex.addNS("stop", "svg")):
                                stop_color = inkex.Color(styles[stop].get("stop-color", "#000000")).to_rgb()
                                has_nonwhite |= tuple(stop_color) != (255, 255, 255)
        cutouts = preserve_cutouts and has_nonwhite
        for node, style in styles.items():
            if any(etree.QName(parent).localname in ("mask", "clipPath") for parent in node.iterancestors()):
                continue
            local = etree.QName(node).localname
            if node in images:
                image = images[node]
                channel = ImageChops.invert(pure_white_mask(image)) if cutouts else Image.new("L", image.size, 255)
                mask_image = Image.merge("RGBA", (channel, channel, channel, image.getchannel("A")))
                buffer = io.BytesIO()
                mask_image.save(buffer, "PNG")
                node.set("href", "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode())
                node.attrib.pop(inkex.addNS("href", "xlink"), None)
            elif local == "stop":
                rgba = inkex.Color(style.get("stop-color", "#000000")).to_rgba(style.get("stop-opacity", "1"))
                force_style(node, {"stop-color": "#000000" if cutouts and tuple(rgba[:3]) == (255, 255, 255) else "#ffffff",
                                   "stop-opacity": svg_number(rgba[3])})
            elif local in DRAWABLES:
                values = {}
                for key in ("fill", "stroke"):
                    raw = style.get(key, "#000000" if key == "fill" else "none")
                    if raw.startswith("url(") or raw == "none":
                        continue
                    rgba = paint_rgba(style, key)
                    if rgba is not None:
                        values[key] = "#000000" if cutouts and tuple(rgba[:3]) == (255, 255, 255) else "#ffffff"
                        values[key + "-opacity"] = svg_number(rgba[3])
                if values:
                    force_style(node, values)
    result = inkex.SvgDocumentElement()
    for key in ("width", "height", "viewBox"):
        result.set(key, master.get(key))
    defs = inkex.Defs()
    result.append(defs)
    mask = inkex.Mask(id="logo-export-silhouette", maskUnits="userSpaceOnUse", maskContentUnits="userSpaceOnUse",
                      x="0", y="0", width=master.get("width"), height=master.get("height"))
    force_style(mask, {"mask-type": "luminance"})
    defs.append(mask)
    for component in list(content):
        mask.append(component)
    rect = inkex.Rectangle(x="0", y="0", width=master.get("width"), height=master.get("height"))
    force_style(rect, {"fill": color, "stroke": "none", "mask": "url(#logo-export-silhouette)"})
    result.append(rect)
    return result


def add_background(svg, color):
    rect = inkex.Rectangle(x="0", y="0", width=svg.get("width"), height=svg.get("height"))
    force_style(rect, {"fill": color, "stroke": "none"})
    svg.insert(0, rect)


class LogoExportPro(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="source")
        pars.add_argument("--brand_name", default="My Brand")
        pars.add_argument("--source_action", default="export")
        pars.add_argument("--source_mode", default="templates")
        from logo_export_kit import add_arguments
        add_arguments(pars)
        pars.add_argument("--role_assignment", default="assigned")
        pars.add_argument("--icon_id", default="")
        pars.add_argument("--wordmark_id", default="")
        pars.add_argument("--sizing_mode", default="original")
        pars.add_argument("--gap_mode", default="current")
        pars.add_argument("--horizontal_balance", type=float, default=1.5)
        pars.add_argument("--vertical_balance", type=float, default=0.5)
        pars.add_argument("--icon_height", type=float, default=128)
        pars.add_argument("--wordmark_height", type=float, default=48)
        pars.add_argument("--gap", type=float, default=32)
        pars.add_argument("--padding", type=float, default=32)
        pars.add_argument("--icon_side", default="left")
        pars.add_argument("--square_icon", type=inkex.Boolean, default=True)
        for value in LAYOUTS:
            pars.add_argument("--layout_" + value, type=inkex.Boolean, default=True)
        for value in COLORS:
            pars.add_argument("--color_" + value, type=inkex.Boolean, default=True)
        pars.add_argument("--preserve_white_cutouts", type=inkex.Boolean, default=True)
        pars.add_argument("--text_to_paths", type=inkex.Boolean, default=True)
        pars.add_argument("--output_dir", default="")
        pars.add_argument("--raster_sizes", default="512, 1024, 2048")
        pars.add_argument("--jpeg_quality", type=int, default=95)
        for value in FORMATS:
            pars.add_argument("--format_" + value, type=inkex.Boolean, default=True)
        pars.add_argument("--transparent_background", type=inkex.Boolean, default=True)
        pars.add_argument("--background_color", default="4294967295")
        pars.add_argument("--white_background_color", default="387986431")
        pars.add_argument("--include_preview", type=inkex.Boolean, default=True)
        pars.add_argument("--open_folder", type=inkex.Boolean, default=True)

    def validate_options(self):
        o = self.options
        self.stem = safe_stem(o.brand_name)
        for value, low, high, label in ((o.icon_height, 1, 2000, "Icon height"), (o.wordmark_height, 1, 2000, "Name height"),
            (o.gap, 0, 10000, "Icon / name gap"), (o.padding, 0, 10000, "Outer padding"),
            (o.horizontal_balance, 0.1, 10, "Horizontal balance"), (o.vertical_balance, 0.1, 10, "Vertical balance"),
            (o.jpeg_quality, 1, 100, "JPEG quality")):
            bounded(value, low, high, label)
        if o.role_assignment not in ("assigned", "auto", "icon_first", "icon_last") or o.icon_side not in ("left", "right"):
            raise inkex.AbortExtension("Unknown object role or icon position.")
        if o.source_mode not in SOURCE_MODES or o.sizing_mode not in ("original", "balanced", "manual") or o.gap_mode not in ("current", "manual"):
            raise inkex.AbortExtension("Choose a valid source, sizing and spacing mode.")
        self.layouts = ([key for key in (READY_LAYOUTS if o.source_mode == "ready" else LAYOUTS) if getattr(o, "layout_" + key)] if o.source_mode in ("paired", "ready")
                        else ["as_designed" if o.source_mode == "complete" else o.source_mode])
        self.colors = [key for key in COLORS if getattr(o, "color_" + key)]
        self.formats = [key for key in FORMATS if getattr(o, "format_" + key)]
        if not self.layouts or not self.colors or not self.formats:
            raise inkex.AbortExtension("Select at least one layout, color version and file format.")
        self.raster_sizes = parse_raster_sizes(o.raster_sizes)
        self.background = css_color(o.background_color)
        self.white_background = css_color(o.white_background_color)
        if not o.output_dir.strip():
            raise inkex.AbortExtension("Choose an output folder in the Export tab.")
        self.output_directory = Path(o.output_dir).expanduser().absolute()
        if not self.output_directory.is_dir():
            raise inkex.AbortExtension("The output folder does not exist. Choose an existing folder.")

    def selection_nodes(self):
        selected = list(self.svg.selection.values())
        if not selected or any(not isinstance(node, inkex.ShapeElement) for node in selected):
            raise inkex.AbortExtension("Select the logo artwork: an object, a group, or several separate objects.")
        if any(parent in selected for node in selected for parent in node.iterancestors()):
            raise inkex.AbortExtension("Select separate objects, rather than a group and its child together.")
        selected.sort(key=lambda node: next(i for i, candidate in enumerate(self.svg.iter()) if candidate is node))
        for node in selected:
            if not node.get("id") or not re.fullmatch(r"[\w.:-]+", node.get("id")):
                raise inkex.AbortExtension("Give each selected object a simple ID in Object Properties.")
        return selected

    def assigned_node(self, role):
        identifier = getattr(self.options, role + "_id").strip() or self.svg.get(ROLE_ATTRIBUTES[role], "")
        if not identifier:
            return None
        node = self.svg.getElementById(identifier)
        if not isinstance(node, inkex.ShapeElement) or not re.fullmatch(r"[\w.:-]+", identifier):
            raise inkex.AbortExtension(f"The assigned {role} '{identifier}' is missing or invalid. Select and assign it again.")
        return node

    def selected_components(self):
        mode = self.options.source_mode
        if mode == "paired":
            if self.options.role_assignment == "assigned":
                icon, name = self.assigned_node("icon"), self.assigned_node("wordmark")
                if icon is None or name is None:
                    raise inkex.AbortExtension("Assign the icon and name separately using Source action, or enter their Object IDs. You may also explicitly choose First / Last object is icon.")
            else:
                selected = self.selection_nodes()
                if len(selected) != 2:
                    raise inkex.AbortExtension("For First / Last assignment, select exactly two objects or groups.")
                # Legacy 'auto' now follows the explicit first-object convention;
                # object type and the presence of text never decide a role.
                icon, name = selected if self.options.role_assignment != "icon_last" else reversed(selected)
            if icon is name or icon in name.iterancestors() or name in icon.iterancestors():
                raise inkex.AbortExtension("The icon and name must be two separate objects or groups.")
            order = {node: index for index, node in enumerate(self.svg.iter())}
            return dict(sorted({"icon": icon, "wordmark": name}.items(), key=lambda item: order[item[1]]))
        selected = self.selection_nodes()
        if mode in ("icon", "wordmark") and len(selected) != 1:
            raise inkex.AbortExtension("Group the selected parts into one object for Icon only or Name only mode, or use Complete logo mode.")
        return ({mode: selected[0]} if mode != "complete" else
                {"logo" if len(selected) == 1 else f"logo-{index + 1}": node for index, node in enumerate(selected)})

    def assign_selection(self):
        action = self.options.source_action
        if action == "clear_roles":
            for attribute in ROLE_ATTRIBUTES.values():
                self.svg.attrib.pop(attribute, None)
            for node in self.svg.iter():
                node.attrib.pop(VARIANT_ATTRIBUTE, None)
            return
        role = {"assign_icon": "icon", "assign_wordmark": "wordmark", "assign_horizontal": "horizontal",
                "assign_vertical": "vertical"}.get(action)
        if role is None:
            raise inkex.AbortExtension("Choose a valid Source action.")
        selected = self.selection_nodes()
        if len(selected) != 1:
            raise inkex.AbortExtension("Select just the object or group you want to assign.")
        identifier = selected[0].get("id")
        other = "wordmark" if role == "icon" else "icon"
        if role in ROLE_ATTRIBUTES and self.svg.get(ROLE_ATTRIBUTES[other]) == identifier:
            raise inkex.AbortExtension("The same object cannot be both icon and name. Clear assignments or choose another object.")
        selected[0].set(VARIANT_ATTRIBUTE, role)
        if role in ROLE_ATTRIBUTES:
            self.svg.set(ROLE_ATTRIBUTES[role], identifier)
        else:
            for attribute in ROLE_ATTRIBUTES.values():
                if self.svg.get(attribute) == identifier:
                    self.svg.attrib.pop(attribute, None)

    def ready_nodes(self, source, directory):
        """Recognize finished variants on a disposable document, not the original."""
        from inkex.command import inkscape
        chosen = self.selection_nodes()
        if len(chosen) == 1 and isinstance(chosen[0], inkex.Group):
            children = [node for node in source.getElementById(chosen[0].get("id")) if isinstance(node, inkex.ShapeElement)]
            if (sum(artwork_role(node) is not None for node in children) >= 2 or
                    chosen[0].get(inkex.addNS("groupmode", "inkscape")) == "layer"):
                chosen = children
        if not chosen or len(chosen) > 12:
            raise inkex.AbortExtension("Select up to 12 finished logo groups, or a layer containing them.")
        explicit = {node.get_id(): artwork_role(node) for node in chosen}
        component_ids = {}
        for root in chosen:
            for node in root.iterdescendants():
                role = artwork_role(node)
                if role in ROLE_ATTRIBUTES and node.get("id"):
                    component_ids.setdefault(role, node.get("id"))
        for role, attribute in ROLE_ATTRIBUTES.items():
            identifier = getattr(self.options, role + "_id").strip() or self.svg.get(attribute, "")
            node = self.svg.getElementById(identifier) if identifier else None
            # An old assignment belonging to an unrelated logo in the same
            # document must not influence this selection.
            if node is not None and (identifier in explicit or any(parent.get("id") in explicit for parent in node.iterancestors())):
                component_ids[role] = identifier
        # Each selected variant must have its own group. An outer container is
        # supported when its children have explicit roles, or it is a layer.
        for identifier in explicit:
            source = self.prepare_source(source, identifier)
        for index, node in enumerate(source.iter()):
            if isinstance(node, inkex.ShapeElement) and not node.get("id"):
                node.set("id", source.get_unique_id("lep-part-" + str(index)))
        roots = [source.getElementById(identifier) for identifier in explicit]
        root_map = {node.get("id"): node for node in roots}
        self.measure_components(source, root_map, directory)
        bounds = dict(self.all_bounds)
        candidates = {identifier: [] for identifier in root_map}
        removed = {}
        serial = 0
        stylesheets = [deepcopy(node) for node in source.iter() if isinstance(node.tag, str) and
                       etree.QName(node).localname == "style"]

        def subset(parent, exclude):
            nonlocal serial
            serial += 1
            clone = deepcopy(parent)
            for node in list(clone.iter()):
                if node.get("id") in exclude and node.getparent() is not None:
                    node.getparent().remove(node)
            # Keep synthetic regions outside every original variant. Appending
            # a region to its original parent would duplicate artwork/effects.
            wrapped = clone
            for ancestor in parent.iterancestors():
                if ancestor is source:
                    break
                wrapper = type(ancestor)()
                wrapper.attrib.update(dict(ancestor.attrib))
                wrapper.append(wrapped)
                wrapped = wrapper
            for stylesheet in stylesheets:
                wrapped.append(deepcopy(stylesheet))
            prefix_ids(wrapped, f"lep-{serial}-")
            source.append(wrapped)
            return clone

        def union(boxes):
            x, y = min(b[0] for b in boxes), min(b[1] for b in boxes)
            return x, y, max(b[0] + b[2] for b in boxes) - x, max(b[1] + b[3] for b in boxes) - y

        for root in roots:
            rid = root.get("id")
            for node in list(root.iterdescendants()):
                identifier = node.get("id")
                if isinstance(node, inkex.ShapeElement) and identifier in bounds and not any(
                        isinstance(parent, (inkex.Defs, inkex.TextElement)) for parent in node.iterancestors()):
                    # Inkscape reports bounds for tspans, but export-id-only
                    # cannot paint them independently of their parent text.
                    # Match the complete text object, preserving Arabic shaping.
                    candidates[rid].append(identifier)
                    removed[identifier] = [identifier]
            # Outlined names/icons need not be subgroups: split at the largest
            # empty horizontal/vertical gaps between direct children.
            for group in [root, *list(root.iterdescendants())]:
                if not isinstance(group, inkex.Group) or group.get("id") not in bounds:
                    continue
                children = [node for node in group if isinstance(node, inkex.ShapeElement) and node.get("id") in bounds]
                if not 3 <= len(children) <= 250:
                    continue
                for axis in (0, 1):
                    ordered = sorted(children, key=lambda node: bounds[node.get("id")][axis])
                    end = -math.inf
                    gaps = []
                    for index, node in enumerate(ordered):
                        box = bounds[node.get("id")]
                        if index and box[axis] > end:
                            gaps.append((box[axis] - end, index))
                        end = max(end, box[axis] + box[axis + 2])
                    for gap, index in sorted(gaps, reverse=True)[:2]:
                        if gap < max(0.2, bounds[group.get("id")][axis + 2] * 0.01):
                            continue
                        for keep, discard in ((ordered[:index], ordered[index:]), (ordered[index:], ordered[:index])):
                            if len(keep) == 1:
                                continue
                            clone = subset(group, {node.get("id") for node in discard})
                            cid = clone.get("id")
                            bounds[cid] = union([bounds[node.get("id")] for node in keep])
                            candidates[rid].append(cid)
                            removed[cid] = [node.get("id") for node in keep]
        identifiers = list(dict.fromkeys([*root_map, *(cid for ids in candidates.values() for cid in ids)]))
        if len(identifiers) > 500:
            raise inkex.AbortExtension("These groups contain too many parts for automatic matching. Group each icon/name first, or assign the finished variants with Action.")
        if any(not re.fullmatch(r"[\w.:-]+", identifier) for identifier in identifiers):
            raise inkex.AbortExtension("A component has an unsupported ID. Give it a simple ID in Object Properties.")
        if any(c in str(directory) for c in ";\r\n"):
            raise inkex.AbortExtension("The temporary folder contains unsupported action delimiters.")
        input_path = directory / "recognize.svg"
        etree.ElementTree(source).write(str(input_path), encoding="UTF-8", xml_declaration=True)
        actions = ["export-type:png", "export-id-only:true", "export-background-opacity:0"]
        images = {}
        for index, identifier in enumerate(identifiers):
            image_path = directory / f"recognize-{index}.png"
            images[identifier] = image_path
            wide = bounds[identifier][2] >= bounds[identifier][3]
            actions += ["export-id:" + identifier, f"export-width:{128 if wide else 0}",
                        f"export-height:{0 if wide else 128}", "export-filename:" + str(image_path), "export-do"]
        inkscape(str(input_path), batch_process=True, actions=";".join(actions))
        signatures = {}
        for identifier, path in images.items():
            signature = visual_signature(path, allow_empty=True)
            if signature is None:
                if identifier in root_map or identifier in component_ids.values():
                    raise inkex.AbortExtension(f"The selected or assigned object '{identifier}' renders empty. Check its visibility, or select the whole text object instead of a text span.")
                # Optional paths may have geometric bounds without visible
                # paint, or be clipped out. They do not invalidate their logo.
                continue
            signatures[identifier] = signature
        candidates = {rid: [cid for cid in ids if cid in signatures]
                      for rid, ids in candidates.items()}
        distances = {}

        def distance(first, second):
            key = tuple(sorted((first, second)))
            if key not in distances:
                distances[key] = visual_distance(signatures[first], signatures[second])
            return distances[key]

        def match(reference, parent):
            matches = [(distance(reference, cid), index, cid)
                       for index, cid in enumerate(candidates[parent])]
            if not matches:
                return None
            score, _, identifier = min(matches)
            if score > 0.018:
                return None
            # Prefer the outermost matching group when wrappers have the same
            # appearance, so removing an icon also removes its wrapper effects.
            return next(cid for cid in candidates[parent]
                        if distance(reference, cid) <= score + 0.002)

        def ambiguity(message):
            raise inkex.AbortExtension(message + " Select that group alone and assign Horizontal, Vertical, Icon or Name with Source > Action, then select the finished variants and export again.")

        icon_roots = [rid for rid in root_map if explicit[rid] == "icon"]
        if icon_roots:
            reference = icon_roots[0]
        elif component_ids.get("icon") in signatures:
            reference = component_ids["icon"]
        else:
            ranked = []
            for rid in root_map:
                if explicit[rid] in ("horizontal", "vertical", "wordmark"):
                    continue
                matches = sum(match(rid, other) is not None for other in root_map if other != rid)
                if matches:
                    ranked.append((-matches, abs(math.log(signatures[rid][0])), rid))
            if not ranked:
                # Without a standalone icon, compare grouped/spatial components
                # across the finished horizontal and vertical variants.
                for rid, ids in candidates.items():
                    for cid in ids:
                        if not isinstance(source.getElementById(cid), inkex.Group):
                            continue
                        matches = sum(match(cid, other) is not None for other in root_map if other != rid)
                        if matches:
                            ranked.append((-matches, abs(math.log(signatures[cid][0])), cid))
            ranked.sort(key=lambda item: (item[0], item[1]))
            if ranked:
                reference = ranked[0][2]
                if len(ranked) > 1 and ranked[0][0] == ranked[1][0] and abs(ranked[0][1] - ranked[1][1]) < 0.3 and distance(
                        reference, ranked[1][2]) > 0.018:
                    ambiguity("Both icon and name look equally plausible; the icon needs an explicit assignment.")
            else:
                reference = None

        plan, reasons = {}, {}

        def accept(role, node, reason):
            if role in plan:
                previous = plan[role].get("id")
                current = node.get("id")
                if previous == current or (previous in signatures and current in signatures and
                                          distance(previous, current) <= 0.018):
                    return
                ambiguity(f"There are two different {role} designs. Select one design for each type.")
            plan[role], reasons[role] = node, reason

        for rid, role in explicit.items():
            if role:
                accept(role, root_map[rid], "assigned object or layer label")
        for role, identifier in component_ids.items():
            if role not in plan and identifier in signatures:
                accept(role, source.getElementById(identifier), "assigned component inside a selected variant")
        if reference:
            if "icon" not in plan:
                accept("icon", source.getElementById(reference), "matching artwork shared by the finished variants")
            for rid, root in root_map.items():
                if explicit[rid] in ("icon", "wordmark"):
                    continue
                if distance(reference, rid) <= 0.018:
                    if explicit[rid] is None:
                        accept("icon", root, "matching standalone icon")
                    continue
                found = match(reference, rid)
                if found is None:
                    if explicit[rid] is not None:
                        continue
                    # A separately selected outlined name is also recognized
                    # by its occurrence inside a finished variant.
                    if any(match(rid, other) is not None for other in root_map if other != rid):
                        accept("wordmark", root, "matching standalone name")
                        continue
                    ambiguity(f"Could not identify the selected group '{rid}'.")
                name = subset(root, set(removed[found]))
                name_id = name.get("id")
                measured = self.measure_components(source, {"name": name}, directory)["name"]
                bounds[name_id] = measured
                ix, iy, iw, ih = bounds[found]
                nx, ny, nw, nh = measured
                dx = abs(ix + iw / 2 - nx - nw / 2) / ((iw + nw) / 2)
                dy = abs(iy + ih / 2 - ny - nh / 2) / ((ih + nh) / 2)
                role = explicit[rid]
                if role is None:
                    if max(dx, dy) < 0.6 or min(dx, dy) > max(dx, dy) * 0.8:
                        ambiguity(f"The layout of '{rid}' is ambiguous.")
                    role = "horizontal" if dx > dy else "vertical"
                    accept(role, root, "matched icon and current relative positions")
                if "wordmark" not in plan:
                    accept("wordmark", name, "name extracted by removing the matched icon")
                    reasons["wordmark"] += f" from {rid}"
        unidentified = [rid for rid in root_map if explicit[rid] is None and
                        not any(node is root_map[rid] for node in plan.values())]
        # Duplicate standalone icons or names may be deliberately selected.
        if reference is None and unidentified:
            ambiguity("Automatic detection needs a matching icon, or explicitly assigned finished variants.")
        self.ready_metadata = {role: {"source_id": node.get("id"), "recognition": reasons[role]} for role, node in plan.items()}
        plan = {role: plan[role] for role in self.layouts if role in plan}
        if not plan:
            raise inkex.AbortExtension("None of the recognized layouts are enabled in the Layouts tab.")
        self.layouts = list(plan)
        return source, plan

    def measure_components(self, source, selected, directory):
        from inkex.command import inkscape
        snapshot = source
        for node in selected.values():
            snapshot = self.prepare_source(snapshot, node.get("id"))
        input_path = directory / "measure-source.svg"
        etree.ElementTree(snapshot).write(str(input_path), encoding="UTF-8", xml_declaration=True)
        output = inkscape(str(input_path), batch_process=True, query_all=True)
        boxes = {}
        for row in output.splitlines():
            parts = row.rsplit(",", 4)
            if len(parts) != 5:
                continue
            try:
                box = tuple(map(float, parts[1:]))
            except ValueError:
                continue
            if all(math.isfinite(value) for value in box) and min(box[2:]) > 0:
                boxes[parts[0]] = box
        self.all_bounds = boxes
        if any(node.get("id") not in boxes for node in selected.values()):
            raise inkex.AbortExtension("A chosen object has no measurable visible area. Check its visibility and dimensions.")
        return {role: boxes[node.get("id")] for role, node in selected.items()}

    def prepare_source(self, source, identifier):
        """Work on a snapshot; embed assets belonging to this component."""
        root = deepcopy(source)
        for attribute in ROLE_ATTRIBUTES.values():
            root.attrib.pop(attribute, None)
        for node in root.iter():
            node.attrib.pop(VARIANT_ATTRIBUTE, None)
        original_styles = {node: node.attrib["style"] for node in root.iter() if "style" in node.attrib}
        for node in list(root.iter()):
            if isinstance(node.tag, str) and etree.QName(node).localname in ("namedview", "script"):
                if node.getparent() is not None:
                    node.getparent().remove(node)
        identifiers = {node.get("id"): node for node in root.iter() if node.get("id")}
        selected = identifiers[identifier]
        relevant, pending = set(), [selected, *selected.iterancestors()]
        while pending:
            node = pending.pop()
            if node in relevant:
                continue
            relevant.add(node)
            if node is selected or node not in selected.iterancestors():
                pending.extend(list(node))
            values = list(node.attrib.values()) + list(dict(node.specified_style()).values()) if isinstance(node, inkex.BaseElement) else []
            refs = [ref for value in values for ref in URL_REF.findall(str(value))]
            href = node.get("href") or node.get(inkex.addNS("href", "xlink"), "")
            if href.startswith("#"):
                refs.append(href[1:])
            pending.extend(identifiers[ref] for ref in refs if ref in identifiers)
        for node in relevant:
            if isinstance(node, inkex.Use):
                href = node.get("href") or node.get(inkex.addNS("href", "xlink"), "")
                if href and not href.startswith("#"):
                    raise inkex.AbortExtension("Unlink clones that reference external files before exporting the logo.")
            if not isinstance(node, inkex.Image):
                continue
            href = node.get("href") or node.get(inkex.addNS("href", "xlink"), "")
            if not href.startswith("data:"):
                parsed = urlsplit(href)
                if parsed.scheme not in ("", "file") or parsed.netloc not in ("", "localhost"):
                    raise inkex.AbortExtension("Logo images must be embedded or linked to local files.")
                asset = Path(unquote(parsed.path)).expanduser()
                candidates = [asset] if asset.is_absolute() else []
                document = self.document_path()
                if not asset.is_absolute() and document:
                    candidates.append(Path(document).parent / asset)
                if not asset.is_absolute() and isinstance(self.options.input_file, str):
                    candidates.append(Path(self.options.input_file).absolute().parent / asset)
                absref = node.get(inkex.addNS("absref", "sodipodi"))
                if absref:
                    candidates.append(Path(absref))
                actual = next((p for p in candidates if p.is_file()), None)
                if actual is None:
                    raise inkex.AbortExtension("Cannot find a linked logo image. Embed it before exporting.")
                if actual.stat().st_size > MAX_ASSET_BYTES:
                    raise inkex.AbortExtension("A linked logo image exceeds 64 MiB.")
                raw = actual.read_bytes()
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise inkex.AbortExtension("A logo image exceeds 20 million pixels.")
                    buffer = io.BytesIO()
                    image.convert("RGBA").save(buffer, "PNG")
                node.set("href", "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode())
                node.attrib.pop(inkex.addNS("href", "xlink"), None)
            image_rgba(node)
        # Reading Inkex's computed styles must not normalize away inline
        # !important declarations before the native original-color export.
        for node, style in original_styles.items():
            node.attrib["style"] = style
        return root

    def extract_component(self, source, role, node, directory):
        from inkex.command import inkscape
        input_path, output = directory / (role + "-source.svg"), directory / (role + "-component.svg")
        snapshot = self.prepare_source(source, node.get("id"))
        etree.ElementTree(snapshot).write(str(input_path), encoding="UTF-8", xml_declaration=True)
        kwargs = dict(batch_process=True, export_id=node.get("id"), export_id_only=True, export_plain_svg=True,
                      export_type="svg", export_filename=str(output))
        # Expand local clones on the temporary copy so inherited clone styles
        # can be recolored without losing their visible geometry.
        actions = []
        if any(isinstance(child, inkex.Use) for child in node.iter()):
            actions += ["select-clear", "select-by-id:" + node.get("id"), "clone-unlink-recursively", "select-clear"]
        if self.options.text_to_paths:
            actions += ["select-by-element:text", "object-to-path"]
        if actions:
            kwargs["actions"] = ";".join(actions)
        inkscape(str(input_path), **kwargs)
        svg = inkex.load_svg(str(output)).getroot()
        for child in list(svg):
            if etree.QName(child).localname in ("metadata", "title", "desc", "namedview", "script"):
                svg.remove(child)
        width, height = svg.viewport_width, svg.viewport_height
        if any(not math.isfinite(v) for v in (width, height)) or min(width, height) <= 0:
            raise inkex.AbortExtension(f"The {role} has no visible area. Check its visibility and dimensions.")
        if self.options.text_to_paths and svg.xpath(".//svg:text"):
            raise inkex.AbortExtension("Inkscape did not outline all logo text. Check the font or disable Text to paths.")
        return Component(svg, width, height)

    def export_variant(self, master, layout, color, stage, temporary):
        from inkex.command import inkscape
        o = self.options
        stem = f"{self.stem}-{layout}-{color}"
        folder = stage / layout / color
        folder.mkdir(parents=True)
        background = self.white_background if color == "white" else self.background
        if not o.transparent_background:
            add_background(master, background)
        master_path = temporary / (layout + "-" + color + ".svg")
        etree.ElementTree(master).write(str(master_path), encoding="UTF-8", xml_declaration=True)
        files = []
        if "svg" in self.formats:
            destination = folder / (stem + ".svg")
            shutil.copyfile(master_path, destination)
            files.append(destination)
        if o.include_preview:
            preview = stage / "preview" / (layout + "-" + color + ".svg")
            preview.parent.mkdir(exist_ok=True)
            shutil.copyfile(master_path, preview)
        width, height = master.viewport_width, master.viewport_height
        requests = []
        for size in self.raster_sizes if any(f in self.formats for f in ("png", "jpg")) else []:
            longest_is_width = width >= height
            scaled_width = max(1, round(size if longest_is_width else size * width / height))
            scaled_height = max(1, round(size * height / width if longest_is_width else size))
            if scaled_width * scaled_height > MAX_RASTER_PIXELS:
                raise inkex.AbortExtension("A raster export exceeds 32 million pixels. Reduce the raster sizes.")
            requests.append((size, longest_is_width, temporary / f"{layout}-{color}-{size}.png"))
        actions = ["export-area-page", "export-background-opacity:0", "export-width:0", "export-height:0"]
        for size, longest_is_width, output in requests:
            actions += ["export-type:png", f"export-width:{size if longest_is_width else 0}",
                        f"export-height:{0 if longest_is_width else size}", f"export-filename:{output}", "export-do"]
        for format_ in ("pdf",):
            if format_ in self.formats:
                output = temporary / (layout + "-" + color + "." + format_)
                actions += ["export-width:0", "export-height:0", "export-text-to-path:true", "export-type:" + format_,
                            f"export-filename:{output}", "export-do"]
        if requests or "pdf" in self.formats:
            # Action paths are generated temporary paths, never user-entered folder names.
            if any(c in str(temporary) for c in ";\r\n"):
                raise inkex.AbortExtension("The temporary folder contains unsupported action delimiters.")
            inkscape(str(master_path), batch_process=True, actions=";".join(actions))
        if "eps" in self.formats:
            # PostScript flattens transparency against white. Give EPS a solid
            # canvas so a white silhouette and its cutouts remain visible.
            eps_path = master_path
            if o.transparent_background:
                eps_master = deepcopy(master)
                add_background(eps_master, background)
                eps_path = temporary / (layout + "-" + color + "-eps-source.svg")
                etree.ElementTree(eps_master).write(str(eps_path), encoding="UTF-8", xml_declaration=True)
            inkscape(str(eps_path), batch_process=True, export_area_page=True,
                     export_text_to_path=True, export_type="eps",
                     export_filename=str(temporary / (layout + "-" + color + ".eps")))
        for size, _, output in requests:
            if not output.is_file():
                raise inkex.AbortExtension("Inkscape did not create a requested PNG export.")
            if "png" in self.formats:
                destination = folder / f"{stem}-{size}px.png"
                shutil.copyfile(output, destination)
                files.append(destination)
            if "jpg" in self.formats:
                with Image.open(output) as image:
                    rgba = image.convert("RGBA")
                    flattened = Image.new("RGB", rgba.size, background)
                    flattened.paste(rgba, mask=rgba.getchannel("A"))
                    destination = folder / f"{stem}-{size}px.jpg"
                    flattened.save(destination, "JPEG", quality=o.jpeg_quality, subsampling=0, dpi=(96, 96))
                    files.append(destination)
        for format_ in ("pdf", "eps"):
            if format_ in self.formats:
                output = temporary / (layout + "-" + color + "." + format_)
                if not output.is_file() or output.stat().st_size == 0:
                    raise inkex.AbortExtension(f"Inkscape did not create a requested {format_.upper()} export.")
                destination = folder / (stem + "." + format_)
                shutil.copyfile(output, destination)
                files.append(destination)
        return {"layout": layout, "color": color, "width_px": width, "height_px": height,
                "files": [str(file.relative_to(stage)) for file in files]}

    def gallery(self, stage, variants):
        cards = []
        for variant in variants:
            layout, color = variant["layout"], variant["color"]
            links = []
            for file in variant["files"]:
                label = Path(file).suffix[1:].upper()
                size = re.search(r"-(\d+)px\.(png|jpg)$", file)
                if size:
                    label += " · " + size[1] + " px"
                links.append(f'<a href="{html.escape(file, quote=True)}">{label}</a>')
            links = " ".join(links)
            cards.append(f'<article><div class="image {color}"><img src="preview/{layout}-{color}.svg" alt="{layout} {color}"></div>'
                         f'<h2>{layout.title()} · {color.title()}</h2><p>{links}</p></article>')
        title = html.escape(self.options.brand_name.strip())
        page = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title} — Logo kit</title><style>body{{margin:0;padding:32px;background:#f1f5f9;color:#172033;font-family:system-ui,sans-serif}}'
                'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}article{background:white;padding:16px;border-radius:14px}'
                '.image{height:180px;display:grid;place-items:center;background:#e2e8f0;border-radius:8px}.image.white{background:#172033}'
                'img{max-width:90%;max-height:150px}h2{font-size:16px}a{display:inline-block;margin:4px;color:#2563eb}p{line-height:1.6}</style>'
                f'<h1>{title}</h1><p>Logo Export Pro · Raster labels show the longest edge.</p><main>'
                + "".join(cards) + '</main></html>')
        (stage / "preview.html").write_text(page, encoding="UTF-8")

    def effect(self):
        from inkex.command import CommandNotFound, ProgramRunError
        if self.options.source_action.startswith("kit_") or self.options.source_mode == "templates" and self.options.source_action == "export":
            from logo_export_kit import TemplateKit
            TemplateKit(self).run()
            return
        if self.options.source_action != "export":
            self.assign_selection()
            return
        self.validate_options()
        selected = None if self.options.source_mode == "ready" else self.selected_components()
        source = deepcopy(self.svg)
        stage = None
        try:
            with tempfile.TemporaryDirectory(prefix="logo-export-pro-") as directory:
                temporary = Path(directory)
                if self.options.source_mode == "ready":
                    source, selected = self.ready_nodes(source, temporary)
                measured = self.measure_components(source, selected, temporary)
                components = {role: self.extract_component(source, role, node, temporary) for role, node in selected.items()}
                for role, component in components.items():
                    component.x, component.y = measured[role][:2]
                stage = Path(tempfile.mkdtemp(prefix=".logo-export-pro-", dir=self.output_directory))
                variants = []
                for layout in self.layouts:
                    if self.options.source_mode == "ready":
                        # Ready layouts retain their own current design. Only
                        # component canvases may gain the chosen square margin.
                        ready_options = deepcopy(self.options)
                        ready_options.sizing_mode = "original"
                        original = build_master({layout: components[layout]},
                                                "icon" if layout == "icon" else "as_designed", ready_options)
                    else:
                        original = build_master(components, layout, self.options)
                    for color in self.colors:
                        master = deepcopy(original) if color == "original" else monochrome(original, "#000000" if color == "black" else "#ffffff", self.options.preserve_white_cutouts)
                        variants.append(self.export_variant(master, layout, color, stage, temporary))
                if self.options.include_preview:
                    self.gallery(stage, variants)
                manifest = {"extension": "Logo Export Pro", "version": VERSION, "brand": self.options.brand_name.strip(),
                    "source_mode": self.options.source_mode, "sizing_mode": self.options.sizing_mode,
                    "spacing_mode": self.options.gap_mode,
                    "source_bounds_px": {role: list(bounds) for role, bounds in measured.items()},
                    "source_ids": {role: node.get("id") for role, node in selected.items()}, "text_to_paths": self.options.text_to_paths,
                    "raster_sizes_longest_edge_px": self.raster_sizes, "variants": variants,
                    "exported_file_count": sum(len(v["files"]) for v in variants)}
                if self.options.source_mode == "ready":
                    manifest["recognized_layouts"] = self.ready_metadata
                (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="UTF-8")
                (stage / "README.txt").write_text("Logo Export Pro\n\nOpen preview.html for the gallery, if enabled.\n"
                    "Layouts and color versions follow your chosen export options.\n"
                    "PNG/JPG sizes specify the longest edge. SVG/PDF/EPS use the vector canvas dimensions.\n"
                    "JPG/EPS use the configured light background; White uses the dark background.\n"
                    "EPS cannot retain all SVG transparency/filter effects; Inkscape may flatten them.\n"
                    "The source Inkscape document is unchanged.\n", encoding="UTF-8")
                index = 1
                while True:
                    destination = self.output_directory / (self.stem + "-logo-kit" + ("" if index == 1 else f"-{index}"))
                    try:
                        if destination.exists():
                            index += 1
                            continue
                        stage.rename(destination)
                        break
                    except FileExistsError:
                        index += 1
                stage = None
                self.output_path, self.manifest = destination, manifest
        except (CommandNotFound, ProgramRunError, OSError, ValueError, etree.XMLSyntaxError) as error:
            raise inkex.AbortExtension(f"Logo export failed: {error}. Check the selected artwork, fonts and output folder.") from error
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
        if self.options.open_folder:
            try:
                if sys.platform == "win32":
                    os.startfile(str(self.output_path))
                else:
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.output_path)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                inkex.errormsg(f"Export complete. Folder: {self.output_path}")


if __name__ == "__main__":
    LogoExportPro().run()
