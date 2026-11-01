"""Named, geometry-preserving logo templates and offline identity galleries."""
import base64
from copy import deepcopy
from dataclasses import dataclass
import html
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

import inkex
from inkex.command import inkscape, CommandNotFound, ProgramRunError
from lxml import etree
from PIL import Image

ROLE = "data-logo-kit-role"
LABEL = inkex.addNS("label", "inkscape")
ROLES = ("icon", "text", "bg", "frame", "keep")
FORMATS = ("svg", "png", "pdf", "jpg", "eps", "webp")
DEFAULT_PALETTE = "Navy=#0f1b34; Blue=#397ce0; Paper=#f0f4f7; Mint=#cbe6e2"


def add_arguments(parser):
    for name, default in (("template_prefix", "-ex-"), ("template_scope", "selection"),
                          ("template_name", "horizontal-bg"), ("identity_palette", DEFAULT_PALETTE),
                          ("identity_backgrounds", ""), ("neutral_text", "best")):
        parser.add_argument("--" + name, default=default)
    parser.add_argument("--minimum_contrast", type=float, default=3.0)
    for name, default in (("identity_bw", True), ("identity_uniform", True), ("identity_mixed", True),
                          ("template_original", True), ("format_webp", False)):
        parser.add_argument("--" + name, type=inkex.Boolean, default=default)


@dataclass(frozen=True)
class Swatch:
    name: str
    color: str


def palette(text, black_white=False):
    result, used_names = [], set()
    for entry in re.split(r"[;,\n]+", text.strip()):
        if not entry.strip():
            continue
        parts = entry.strip().split("=", 1)
        color = parts[-1].strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}|#[0-9a-f]{3}", color):
            raise inkex.AbortExtension("Use HEX colors: Navy=#0f1b34; Blue=#397ce0. Alpha is not supported in the identity palette.")
        if len(color) == 4:
            color = "#" + "".join(c * 2 for c in color[1:])
        name = parts[0].strip() if len(parts) == 2 else color[1:]
        if not name:
            raise inkex.AbortExtension("Give each identity color a name, or enter only its HEX value.")
        if color in [s.color for s in result]:
            continue
        if name.casefold() in used_names:
            raise inkex.AbortExtension("Identity color names must be unique.")
        used_names.add(name.casefold())
        result.append(Swatch(name, color))
    if black_white:
        for name, color in (("White", "#ffffff"), ("Black", "#000000")):
            if color not in [s.color for s in result]:
                result.append(Swatch(name if name.casefold() not in used_names else name + " neutral", color))
    if not 1 <= len(result) <= 16:
        raise inkex.AbortExtension("Enter 1–16 unique identity colors.")
    return result


def luminance(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    rgb = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * w for v, w in zip(rgb, (.2126, .7152, .0722)))


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + .05) / (dark + .05)


def label(node):
    return node.get(LABEL) or node.get("id", "")


def local_role(node):
    value = node.get(ROLE)
    if value in ROLES:
        return value
    match = re.match(r"^-(icon|text|bg|frame|keep)-(?:.*)?$", label(node), re.I)
    return match[1].lower() if match else None


def role_of(node, root):
    found = None
    current = node
    while current is not None:
        role = local_role(current)
        if role in ("frame", "keep"):
            return role
        if found is None and role:
            found = role
        if current is root:
            break
        current = current.getparent()
    return found or "icon"


def template_info(name, prefix):
    from logo_export_pro import safe_stem
    value = name[len(prefix):].strip() if name.startswith(prefix) else name
    if not value:
        raise inkex.AbortExtension("Add a template name after the export prefix, for example -ex-horizontal-bg.")
    match = re.match(r"^(.*?)[-_](bg|background|safe|tight|transparent)$", value, re.I)
    family, canvas = (match[1], match[2].lower()) if match else (value, "transparent")
    canvas = {"bg": "background", "tight": "transparent"}.get(canvas, canvas)
    aliases = {"h": "horizontal", "hz": "horizontal", "v": "vertical", "ve": "vertical", "i": "icon"}
    family = aliases.get(family.lower(), family)
    return safe_stem(family), canvas


def discover(root, selected, prefix, scope):
    if not prefix.strip() or any(c in prefix for c in "\r\n"):
        raise inkex.AbortExtension("Enter an export prefix, for example -ex-.")
    if scope not in ("selection", "document"):
        raise inkex.AbortExtension("Choose Selected groups or All named groups.")
    containers = [root] if scope == "document" else list(selected)
    candidates, seen = [], set()
    for container in containers:
        for node in container.iter():
            if not isinstance(node, inkex.ShapeElement) or not label(node).startswith(prefix) or node in seen:
                continue
            if any(isinstance(a, inkex.Defs) for a in node.iterancestors()):
                continue
            if any(label(a).startswith(prefix) for a in node.iterancestors()):
                raise inkex.AbortExtension("Export templates cannot be nested. Move each -ex- group outside other export templates.")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", node.get("id", "")):
                raise inkex.AbortExtension("Each template needs a normal object ID. Rename its label, rather than using spaces in the ID.")
            seen.add(node)
            candidates.append(node)
    if not candidates:
        raise inkex.AbortExtension("No named templates found. Name your groups -ex-horizontal-bg, -ex-icon-tight, etc. Select those groups, or choose All named groups in Templates.")
    if len(candidates) > 32:
        raise inkex.AbortExtension("Export up to 32 templates in one kit. Select fewer groups.")
    names = [label(n).casefold() for n in candidates]
    if len(names) != len(set(names)):
        raise inkex.AbortExtension("Give every export template a unique label.")
    return sorted(candidates, key=lambda n: list(root.iter()).index(n))


def combinations(colors, backgrounds, has_text, has_bg, options, has_icon=True):
    """Only qualifying combinations; deduplicate equal icon/text paints."""
    result, seen = [], set()
    black, white = Swatch("Black", "#000000"), Swatch("White", "#ffffff")
    for bg in backgrounds if has_bg else [None]:
        for ink in colors:
            if has_icon and bg and contrast(ink.color, bg.color) < options.minimum_contrast:
                continue
            names = [ink] if options.identity_uniform or not has_text else []
            if has_text and options.identity_mixed:
                neutrals = [black, white]
                if bg:
                    neutrals = [s for s in neutrals if contrast(s.color, bg.color) >= options.minimum_contrast]
                    if options.neutral_text == "best" and neutrals:
                        neutrals = [max(neutrals, key=lambda s: contrast(s.color, bg.color))]
                names.extend(neutrals)
            for text in names:
                if has_text and bg and contrast(text.color, bg.color) < options.minimum_contrast:
                    continue
                key = (ink.color if has_icon else None, text.color if has_text else None, bg.color if bg else None)
                if key in seen:
                    continue
                seen.add(key)
                result.append({"ink": ink, "text": text if has_text else None, "bg": bg})
    return result


def recolor(source, paints):
    from logo_export_pro import force_style, image_rgba
    root = deepcopy(source)
    drawable = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "text", "tspan", "image", "use"}
    for node in root.iter():
        if not isinstance(node.tag, str) or etree.QName(node).localname not in drawable:
            continue
        if any(etree.QName(a).localname in ("defs", "clipPath", "mask", "pattern", "marker") for a in node.iterancestors()):
            continue
        role = role_of(node, root)
        if role in ("keep", "frame"):
            continue
        color = paints.get(role)
        if color is None:
            continue
        if isinstance(node, inkex.Image):
            image = image_rgba(node)
            if image is None:
                raise inkex.AbortExtension("Embed template images before recoloring.")
            tinted = Image.new("RGBA", image.size, color)
            tinted.putalpha(image.getchannel("A"))
            stream = io.BytesIO()
            tinted.save(stream, "PNG")
            node.set("href", "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode())
            node.attrib.pop(inkex.addNS("href", "xlink"), None)
            continue
        style = node.specified_style()
        values = {}
        if str(style.get("fill", "#000000")).lower() != "none":
            values["fill"] = color
        if str(style.get("stroke", "none")).lower() != "none":
            values["stroke"] = color
        if values:
            force_style(node, values)
    return root


def parse_bounds(output):
    boxes = {}
    for line in output.splitlines():
        parts = line.rsplit(",", 4)
        if len(parts) != 5:
            continue
        try:
            box = tuple(map(float, parts[1:]))
        except ValueError:
            continue
        if all(math.isfinite(v) for v in box) and min(box[2:]) > 0:
            boxes[parts[0]] = box
    return boxes


def write_svg(svg, path):
    etree.ElementTree(svg).write(str(path), encoding="UTF-8", xml_declaration=True)


def opaque_copy(master, color):
    root = deepcopy(master)
    box = root.get_viewbox()
    if not box:
        box = [0, 0, root.viewport_width, root.viewport_height]
    rect = inkex.Rectangle.new(box[0], box[1], box[2], box[3])
    rect.style = {"fill": color, "stroke": "none"}
    root.insert(0, rect)
    return root


def original_neutral(master):
    """Choose an opaque canvas for original light or dark transparent artwork."""
    from logo_export_pro import image_rgba
    lightness = []
    for node in master.iter():
        if not isinstance(node, inkex.ShapeElement) or isinstance(node, (inkex.Group, inkex.Defs)):
            continue
        if any(isinstance(a, inkex.Defs) for a in node.iterancestors()):
            continue
        if isinstance(node, inkex.Image):
            image = image_rgba(node)
            if image:
                lightness.extend(sum(p[:3]) / 765 for p in image.resize((24, 24)).getdata() if p[3] > 128)
        else:
            for paint in ("fill", "stroke"):
                value = node.specified_style().get(paint, "#000000" if paint == "fill" else "none")
                if str(value).lower() == "none" or str(value).startswith("url("):
                    continue
                try:
                    rgb = inkex.Color(value).to_rgb()
                    lightness.append(sum(rgb[:3]) / 765)
                except (ValueError, TypeError):
                    pass
    return "#0f1b34" if lightness and sum(lightness) / len(lightness) > .65 else "#ffffff"


class TemplateKit:
    def __init__(self, extension):
        self.ext = extension
        self.o = extension.options

    def assign(self):
        action = self.o.source_action.removeprefix("kit_")
        selected = self.ext.selection_nodes()
        if not selected or action == "template" and len(selected) != 1:
            raise inkex.AbortExtension("Select one group to mark as a template, or the objects to mark with an artwork role.")
        if action == "template":
            name = self.o.template_name.strip()
            if not name:
                raise inkex.AbortExtension("Enter a template name in the Templates tab.")
            selected[0].set(LABEL, self.o.template_prefix + name)
        elif action in ROLES:
            for node in selected:
                node.set(ROLE, action)
                node.set(LABEL, "-" + action + "-")
        elif action == "clear":
            for node in selected:
                node.attrib.pop(ROLE, None)
                if local_role(node):
                    node.set(LABEL, node.get("id", "Object"))
        else:
            raise inkex.AbortExtension("Choose a valid template action.")

    def validate(self):
        from logo_export_pro import safe_stem, parse_raster_sizes, bounded
        o = self.o
        self.stem = safe_stem(o.brand_name)
        self.colors = palette(o.identity_palette, o.identity_bw)
        self.backgrounds = palette(o.identity_backgrounds) if o.identity_backgrounds.strip() else self.colors
        bounded(o.minimum_contrast, 1, 21, "Minimum contrast")
        bounded(o.jpeg_quality, 1, 100, "JPEG quality")
        if o.neutral_text not in ("best", "both"):
            raise inkex.AbortExtension("Choose Best contrast or Both qualifying neutrals.")
        if not (o.template_original or o.identity_uniform or o.identity_mixed):
            raise inkex.AbortExtension("Choose Original, Same color or Colored icon + neutral name.")
        self.formats = [f for f in FORMATS if getattr(o, "format_" + f)]
        if not self.formats:
            raise inkex.AbortExtension("Select at least one export format.")
        self.sizes = parse_raster_sizes(o.raster_sizes)
        self.output_dir = Path(o.output_dir).expanduser().absolute()
        if any(c in str(self.output_dir) for c in ";\r\n"):
            raise inkex.AbortExtension("Choose an output folder without semicolons or line breaks.")
        if not o.output_dir.strip() or not self.output_dir.is_dir():
            raise inkex.AbortExtension("Choose an existing output folder in Export.")

    def masters(self, nodes, tmp):
        from logo_export_pro import force_style
        source = self.ext.svg
        for node in nodes:
            source = self.ext.prepare_source(source, node.get("id"))
        targets, ids = [], {n.get("id"): n for n in source.iter() if n.get("id")}
        for original in nodes:
            node = ids[original.get("id")]
            family, canvas = template_info(label(original), self.o.template_prefix)
            frames, backgrounds, has_text, has_icon = [], [], False, False
            for child in node.iter():
                role = local_role(child)
                if role:
                    child.set(ROLE, role)  # plain SVG retains custom data, but removes editor labels
                if role == "frame":
                    if not isinstance(child, inkex.Rectangle):
                        raise inkex.AbortExtension("Use one rectangle named -frame- to define a nonprinting canvas.")
                    frames.append(child)
                    child.get_id()
                elif role == "bg":
                    backgrounds.append(child)
                    child.get_id()
                if role == "text":
                    has_text = True
                if (isinstance(child, inkex.ShapeElement) and not isinstance(child, (inkex.Group, inkex.Defs))
                        and not any(isinstance(a, inkex.Defs) for a in child.iterancestors()) and role_of(child, node) == "icon"):
                    has_icon = True
            if len(frames) > 1:
                raise inkex.AbortExtension(f"{label(original)}: use only one -frame- rectangle per template.")
            if canvas == "background" and not backgrounds:
                raise inkex.AbortExtension(f"{label(original)}: mark the background shape or group -bg-. This keeps it separate from the logo artwork.")
            if backgrounds and canvas != "background":
                canvas = "background"
            targets.append({"id": node.get("id"), "label": label(original), "family": family,
                            "canvas": canvas, "frame": frames[0].get("id") if frames else None,
                            "background_ids": [n.get("id") for n in backgrounds], "has_bg": bool(backgrounds),
                            "has_text": has_text, "has_icon": has_icon})
        measured = deepcopy(source)
        for n in measured.iter():
            if local_role(n) == "frame":
                force_style(n, {"fill": "#000000", "fill-opacity": "1", "opacity": "1", "stroke": "none", "display": "inline", "visibility": "visible"})
        measure_path = tmp / "measure.svg"
        write_svg(measured, measure_path)
        boxes = parse_bounds(inkscape(str(measure_path), batch_process=True, query_all=True))
        source_path = tmp / "source.svg"
        write_svg(source, source_path)
        for index, info in enumerate(targets):
            bounds_id = info["frame"] or (info["background_ids"][0] if len(info["background_ids"]) == 1 else info["id"])
            if bounds_id not in boxes:
                raise inkex.AbortExtension(f'{info["label"]}: no visible canvas. Check the group or its background/frame.')
            x, y, w, h = boxes[bounds_id]
            if w > 100000 or h > 100000:
                raise inkex.AbortExtension("A template canvas exceeds 100,000 px. Check its frame dimensions.")
            crop = tmp / f"template-{index}.svg"
            actions = ["select-clear", "select-by-id:" + info["id"], "clone-unlink-recursively", "select-clear"]
            if self.o.text_to_paths:
                actions += ["select-by-element:text", "object-to-path", "select-clear"]
            inkscape(str(source_path), batch_process=True, actions=";".join(actions),
                     export_id=info["id"], export_id_only=True, export_plain_svg=True,
                     export_area=":".join(str(v) for v in (x, y, x + w, y + h)),
                     export_type="svg", export_filename=str(crop))
            master = inkex.load_svg(str(crop)).getroot()
            # Native plain-SVG export sometimes adopts the viewBox of an embedded
            # SVG and enlarges the outer canvas. Keep the measured document crop
            # in the original document coordinate system instead.
            source_box = source.get_viewbox() or [0, 0, source.viewport_width, source.viewport_height]
            crop_box = master.get_viewbox() or [0, 0, master.viewport_width, master.viewport_height]
            scale_x, scale_y = source.viewport_width / source_box[2], source.viewport_height / source_box[3]
            master.set("width", str(w))
            master.set("height", str(h))
            master.set("viewBox", " ".join(str(v) for v in (crop_box[0], crop_box[1], w / scale_x, h / scale_y)))
            for n in list(master.iter()):
                if local_role(n) == "frame" and n.getparent() is not None:
                    n.getparent().remove(n)
            if self.o.text_to_paths and master.xpath(".//svg:text"):
                raise inkex.AbortExtension("Text could not be outlined. Check your font or disable Convert exported text to paths.")
            # An empty template must fail instead of silently producing a blank kit.
            visible = [n for n in master.iter() if isinstance(n, inkex.ShapeElement)
                       and not isinstance(n, (inkex.Group, inkex.Defs))
                       and not any(isinstance(a, inkex.Defs) for a in n.iterancestors())]
            if not visible:
                raise inkex.AbortExtension(f'{info["label"]}: the template contains no artwork.')
            info["source_bounds_px"] = [x, y, w, h]
            info["width_px"], info["height_px"] = master.viewport_width, master.viewport_height
            if min(info["width_px"], info["height_px"]) <= 0:
                raise inkex.AbortExtension("Inkscape produced an empty template canvas.")
            info["master"] = master
        return targets

    def plan(self, templates, tmp, stage):
        from logo_export_pro import safe_stem
        items, jobs = [], []
        (stage / "preview").mkdir()
        for info in templates:
            combinations_ = combinations(self.colors, self.backgrounds, info["has_text"], info["has_bg"], self.o, info["has_icon"])
            if self.o.template_original:
                combinations_.insert(0, None)
            if not combinations_:
                raise inkex.AbortExtension(f'{info["label"]}: no color pair meets the chosen contrast. Lower Minimum contrast or choose Original.')
            if len(items) + len(combinations_) > 512:
                raise inkex.AbortExtension("This kit exceeds 512 variants. Use fewer templates/colors, or disable some color recipes.")
            for combo in combinations_:
                index = len(items)
                if combo is None:
                    master = deepcopy(info["master"])
                    recipe, ink, text, bg = "original", None, None, None
                else:
                    ink, text, bg = combo["ink"], combo["text"], combo["bg"]
                    recipe = (("ink-" + safe_stem(ink.name)) if info["has_icon"] else "name-only") + ("_name-" + safe_stem(text.name) if text else "") + ("_bg-" + safe_stem(bg.name) if bg else "")
                    master = recolor(info["master"], {"icon": ink.color, "text": text.color if text else ink.color, "bg": bg.color if bg else None})
                # Template label distinguishes arbitrary extra designs sharing the same family.
                stem = self.stem + "_" + safe_stem(info["label"][len(self.o.template_prefix):]) + "_" + recipe + f"_{index + 1:03d}"
                folder = stage / info["family"] / info["canvas"]
                files = []
                master_path = tmp / f"v{index}.svg"
                write_svg(master, master_path)
                def destination(format_, size=None):
                    target = folder / format_.upper() / (stem + (f"_{size}px" if size else "") + "." + format_)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    files.append(target.relative_to(stage).as_posix())
                    return target
                if "svg" in self.formats:
                    shutil.copyfile(master_path, destination("svg"))
                width, height = info["width_px"], info["height_px"]
                actions, rasters = ["export-area-page", "export-background-opacity:0"], []
                needed_sizes = sorted(set([384] + (self.sizes if any(f in self.formats for f in ("png", "jpg", "webp")) else [])))
                for size in needed_sizes:
                    if round(size * min(width, height) / max(width, height)) * size > 32_000_000:
                        raise inkex.AbortExtension("A raster export exceeds 32 million pixels. Reduce Raster sizes.")
                    output = tmp / f"v{index}-{size}.png"
                    actions += ["export-type:png", f"export-width:{size if width >= height else 0}",
                                f"export-height:{0 if width >= height else size}", "export-filename:" + str(output), "export-do"]
                    rasters.append((size, output))
                if "pdf" in self.formats:
                    actions += ["export-width:0", "export-height:0", "export-text-to-path:true", "export-type:pdf",
                                "export-filename:" + str(destination("pdf")), "export-do"]
                if needed_sizes or "pdf" in self.formats:
                    jobs.append((master_path, actions))
                # Opaque formats use a visible neutral canvas only when the designed template has no background.
                neutral = "#ffffff"
                if ink and not bg:
                    colors = [ink.color] + ([text.color] if text else [])
                    neutral = max(("#ffffff", "#0f1b34"), key=lambda b: min(contrast(c, b) for c in colors))
                elif combo is None and not info["has_bg"]:
                    neutral = original_neutral(master)
                if "eps" in self.formats:
                    eps_source = master_path
                    if not info["has_bg"]:
                        eps_source = tmp / f"v{index}-opaque.svg"
                        # Original neutral is determined in finish before EPS jobs are executed.
                        write_svg(opaque_copy(master, neutral or "#ffffff"), eps_source)
                    jobs.append((eps_source, ["export-area-page", "export-background-opacity:1", "export-width:0", "export-height:0",
                                "export-text-to-path:true", "export-type:eps", "export-filename:" + str(destination("eps")), "export-do"]))
                item = {"template": info["label"], "family": info["family"], "canvas": info["canvas"],
                        "recipe": recipe, "icon": ink.color if ink and info["has_icon"] else None, "name": text.color if text else None,
                        "background": bg.color if bg else ("original" if info["has_bg"] else None),
                        "background_name": bg.name if bg else ("Original" if info["has_bg"] else "Transparent"),
                        "width_px": width, "height_px": height, "files": files,
                        "preview": f"preview/v{index}.png", "_rasters": rasters, "_neutral": neutral,
                        "_folder": folder, "_stem": stem, "_master": master}
                items.append(item)
        return items, jobs

    def render(self, jobs):
        """Keep a bounded number of documents in each native process; no GUI file-close action."""
        batch, length = [], 0
        def flush():
            if not batch:
                return
            actions = []
            for index, (path, exports) in enumerate(batch):
                if index:
                    actions.append("file-open:" + str(path))
                actions.extend(exports)
            inkscape(str(batch[0][0]), batch_process=True, actions=";".join(actions))
            batch.clear()
        for path, actions in jobs:
            if any(c in str(path) for c in ";\r\n") or any(c in "".join(actions) for c in "\r\n"):
                raise inkex.AbortExtension("Use an output folder without semicolons or line breaks.")
            size = len(str(path)) + sum(len(a) + 1 for a in actions)
            if batch and (length + size > 6000 or len(batch) >= 12):
                flush()
                length = 0
            batch.append((path, actions))
            length += size
        flush()

    def finish(self, items, stage):
        for item in items:
            for size, path in item.pop("_rasters"):
                if not path.is_file():
                    raise inkex.AbortExtension("Inkscape did not produce a requested raster export.")
                with Image.open(path) as source:
                    image = source.convert("RGBA")
                    if not image.getchannel("A").getbbox():
                        raise inkex.AbortExtension(f'{item["template"]}: exported artwork is empty. Check visibility and its frame.')
                    if size == 384 and self.o.include_preview:
                        image.save(stage / item["preview"], "PNG")
                    if size not in self.sizes:
                        continue
                    for format_ in ("png", "jpg", "webp"):
                        if format_ not in self.formats:
                            continue
                        target = item["_folder"] / format_.upper() / (item["_stem"] + f"_{size}px." + format_)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if format_ == "png":
                            shutil.copyfile(path, target)
                        elif format_ == "webp":
                            image.save(target, "WEBP", lossless=True, method=4)
                        else:
                            neutral = item["_neutral"]
                            if neutral is None:
                                pixels = list(image.resize((32, 32)).getdata())
                                visible = [p for p in pixels if p[3] > 128]
                                light = sum(sum(p[:3]) / 765 for p in visible) / max(1, len(visible))
                                neutral = "#0f1b34" if light > .65 else "#ffffff"
                            flattened = Image.new("RGB", image.size, neutral)
                            flattened.paste(image, mask=image.getchannel("A"))
                            flattened.save(target, "JPEG", quality=self.o.jpeg_quality, subsampling=0, dpi=(96, 96))
                        item["files"].append(target.relative_to(stage).as_posix())
            for path in item["files"]:
                if not (stage / path).is_file() or not (stage / path).stat().st_size:
                    raise inkex.AbortExtension("Inkscape did not create " + path)
            for key in [k for k in item if k.startswith("_")]:
                del item[key]

    def gallery(self, stage, items, templates):
        title = html.escape(self.o.brand_name.strip())
        cards = []
        for item in items:
            links = " ".join('<a download href="' + quote(file, safe="/") + '">' + html.escape(Path(file).suffix[1:].upper() + (" · " + re.search(r"_(\d+)px\.", file)[1] + " px" if re.search(r"_(\d+)px\.", file) else "")) + '</a>' for file in item["files"])
            caption = "Original" if item["recipe"] == "original" else (("Icon " + item["icon"]) if item["icon"] else "") + ((" · " if item["icon"] else "") + "Name " + item["name"] if item["name"] else "")
            ratio = item["width_px"] / item["height_px"]
            cards.append('<article data-family="' + html.escape(item["family"], quote=True) + '" data-canvas="' + item["canvas"] + '" data-bg="' + html.escape(item["background_name"], quote=True) + '" data-template="' + html.escape(item["template"], quote=True) + '"><div class="image" style="aspect-ratio:' + str(ratio) + '"><img loading="lazy" src="' + item["preview"] + '" alt="' + html.escape(caption, quote=True) + '"></div><div class="details"><b>' + html.escape(caption) + '</b><small>' + html.escape(item["template"]) + f' · {item["width_px"]:.1f} × {item["height_px"]:.1f} px</small><div class="links">' + links + '</div></div></article>')
        swatches = "".join('<div class="swatch"><i style="background:' + s.color + '"></i><span>' + html.escape(s.name) + '<small>' + s.color + '</small></span></div>' for s in self.colors)
        families = list(dict.fromkeys(i["family"] for i in templates))
        options = "".join('<option>' + html.escape(f) + '</option>' for f in families)
        page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__ — Identity kit</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f4f1;color:#162033;font-family:system-ui,-apple-system,sans-serif}header{padding:40px 5vw 24px;border-bottom:1px solid #d9ddd9}header p{color:#606978;margin:8px 0}h1{margin:0;font-size:clamp(26px,4vw,46px);letter-spacing:-.04em}.palette{display:flex;flex-wrap:wrap;gap:22px;margin-top:25px}.swatch{display:flex;gap:9px;align-items:center;font-size:13px}.swatch i{width:38px;height:38px;border-radius:7px;border:1px solid #0002}.swatch small{display:block;color:#677080;font-size:11px}nav{position:sticky;top:0;z-index:3;padding:16px 5vw;display:flex;flex-wrap:wrap;gap:10px;background:#f4f4f1ed;backdrop-filter:blur(14px);border-bottom:1px solid #d9ddd9}select,input,button{font:inherit;font-size:13px;border:1px solid #cbd0d2;border-radius:7px;background:white;padding:9px 12px}input{min-width:170px}button{cursor:pointer}nav span{margin:auto 0 auto auto;font-size:12px;color:#606978}main{padding:32px 5vw 60px}h2{font-size:22px;margin:0 0 7px}h3{font-size:14px;margin:25px 0 12px;color:#657081;display:flex;align-items:center;gap:8px}h3 i{width:16px;height:16px;border-radius:4px;border:1px solid #0002}.family-grid{display:grid;grid-template-columns:repeat(__COLS__,minmax(0,1fr));gap:34px}.family{min-width:0}.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));gap:10px}.image{height:auto;aspect-ratio:1;padding:0;display:flex;align-items:center;justify-content:center;border:1px solid #b6bdc3;background-color:var(--canvas,#e9ecee);background-image:linear-gradient(45deg,#00000008 25%,transparent 25%),linear-gradient(-45deg,#00000008 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#00000008 75%),linear-gradient(-45deg,transparent 75%,#00000008 75%);background-size:16px 16px;background-position:0 0,0 8px,8px -8px,-8px 0}.image img{width:100%;height:100%;object-fit:contain;display:block}.details{padding:8px 0}.details b{font-size:10px;display:block;font-weight:500;overflow-wrap:anywhere}.details small{display:block;font-size:9px;line-height:1.6;color:#78818c}.links{display:flex;flex-wrap:wrap;gap:3px;margin-top:6px}.links a{font-size:9px;text-decoration:none;color:#21589f;background:#e3ebf5;padding:3px 5px;border-radius:3px}section.canvas{margin-bottom:44px}section.canvas>h2{font-size:14px;text-transform:uppercase;letter-spacing:.14em;border-bottom:1px solid #d0d5d7;padding-bottom:16px;margin-bottom:26px}footer{padding:20px 5vw;font-size:12px;color:#677080;border-top:1px solid #d9ddd9}body.dark{--canvas:#172033}body.light{--canvas:#ffffff}article[hidden]{display:none}@media(max-width:1000px){.family-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.family-grid{grid-template-columns:1fr}.image{height:auto}}[hidden]{display:none!important}
</style></head><body><header><h1>__TITLE__</h1><p>Identity assets · __COUNT__ variants · __FILES__ files</p><p>Your layouts, preserved. Choose a version and download its format below.</p><div class="palette">__SWATCHES__</div></header><nav><select id="family"><option value="">All designs</option>__OPTIONS__</select><select id="canvas"><option value="">All canvases</option><option value="background">With backgrounds</option><option value="safe">Safe area</option><option value="transparent">Transparent / tight</option></select><input id="search" placeholder="Search colors or template"><button id="surface">Preview surface: checker</button><a href="manifest.json">Manifest</a><span id="count"></span></nav><main id="gallery">__CARDS__</main><footer>Logo Export Pro 2.0 · PNG / JPG / WEBP labels give the longest edge. JPG and EPS are opaque; SVG, PNG, PDF and WEBP retain the designed transparency. Colors are filtered by your chosen contrast; inspect the artwork before publication.</footer><script>
const cards=Array.from(document.querySelectorAll('article')),gallery=document.querySelector('#gallery');const canvases=['background','safe','transparent'];const families=[...new Set(cards.map(c=>c.dataset.family))];
for(const canvas of canvases){const section=document.createElement('section');section.className='canvas';section.dataset.canvas=canvas;const title=document.createElement('h2');title.textContent=({background:'With backgrounds',safe:'Safe area',transparent:'Transparent / tight'})[canvas];section.append(title);const grid=document.createElement('div');grid.className='family-grid';section.append(grid);for(const family of families){const chosen=cards.filter(c=>c.dataset.family===family&&c.dataset.canvas===canvas);if(!chosen.length)continue;const column=document.createElement('div');column.className='family';column.dataset.family=family;const heading=document.createElement('h2');heading.textContent=family;column.append(heading);for(const bg of [...new Set(chosen.map(c=>c.dataset.bg))]){const label=document.createElement('h3');label.textContent=bg;column.append(label);const row=document.createElement('div');row.className='row';chosen.filter(c=>c.dataset.bg===bg).forEach(c=>row.append(c));column.append(row)}grid.append(column)}if(grid.children.length)gallery.append(section)}
function filter(){const family=document.querySelector('#family').value,canvas=document.querySelector('#canvas').value,search=document.querySelector('#search').value.toLowerCase();let count=0;cards.forEach(c=>{c.hidden=Boolean(family&&c.dataset.family!==family||canvas&&c.dataset.canvas!==canvas||search&&!(c.textContent+' '+c.dataset.bg).toLowerCase().includes(search));if(!c.hidden)count++});document.querySelectorAll('.row').forEach(r=>{r.hidden=!Array.from(r.children).some(c=>!c.hidden);r.previousElementSibling.hidden=r.hidden});document.querySelectorAll('.family').forEach(f=>f.hidden=!Array.from(f.querySelectorAll('article')).some(c=>!c.hidden));document.querySelectorAll('section.canvas').forEach(s=>s.hidden=!Array.from(s.querySelectorAll('article')).some(c=>!c.hidden));document.querySelector('#count').textContent=count+' variants'}
['family','canvas','search'].forEach(id=>document.getElementById(id).addEventListener('input',filter));let surface=0;document.querySelector('#surface').onclick=()=>{surface=(surface+1)%3;document.body.classList.toggle('light',surface===1);document.body.classList.toggle('dark',surface===2);document.querySelector('#surface').textContent='Preview surface: '+['checker','light','dark'][surface]};filter();
</script></body></html>'''
        replacements = {"__TITLE__": title, "__COUNT__": str(len(items)), "__FILES__": str(sum(len(v["files"]) for v in items)),
                        "__SWATCHES__": swatches, "__OPTIONS__": options, "__CARDS__": "".join(cards), "__COLS__": str(min(3, len(families)))}
        for key, value in replacements.items():
            page = page.replace(key, value)
        (stage / "preview.html").write_text(page, encoding="UTF-8")
        (stage / "index.html").write_text(page, encoding="UTF-8")

    def run(self):
        if self.o.source_action != "export":
            self.assign()
            return
        self.validate()
        nodes = discover(self.ext.svg, self.ext.svg.selection.values(), self.o.template_prefix, self.o.template_scope)
        stage = None
        try:
            with tempfile.TemporaryDirectory(prefix="logo-kit-") as temp:
                tmp = Path(temp)
                stage = Path(tempfile.mkdtemp(prefix=".logo-kit-", dir=self.output_dir))
                templates = self.masters(nodes, tmp)
                items, jobs = self.plan(templates, tmp, stage)
                self.render(jobs)
                self.finish(items, stage)
                if self.o.include_preview:
                    self.gallery(stage, items, templates)
                manifest = {"extension": "Logo Export Pro", "version": "2.0.0", "brand": self.o.brand_name.strip(), "source_mode": "templates",
                            "palette": [s.__dict__ for s in self.colors], "minimum_contrast": self.o.minimum_contrast,
                            "raster_sizes_longest_edge_px": self.sizes, "templates": [{k: v for k, v in t.items() if k != "master"} for t in templates],
                            "variants": items, "exported_file_count": sum(len(i["files"]) for i in items)}
                (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="UTF-8")
                (stage / "README.txt").write_text("Open index.html for the offline identity gallery.\n\nFolders: design / background, safe or transparent / format.\n"
                    "Template geometry and relative positions are preserved. The -frame- guide defines a nonprinting canvas.\n"
                    "JPG and EPS are opaque. Transparent templates receive a neutral background in these formats only.\n"
                    "Palette recipes follow the chosen minimum contrast. Unmarked artwork uses the icon color; -keep- artwork is preserved.\n"
                    "The source document was not modified.\n", encoding="UTF-8")
                counter = 1
                destination = self.output_dir / (self.stem + "-logo-kit")
                while destination.exists():
                    counter += 1
                    destination = self.output_dir / (self.stem + f"-logo-kit-{counter}")
                stage.rename(destination)
                stage = None
                self.ext.output_path, self.ext.manifest = destination, manifest
        except (CommandNotFound, ProgramRunError, OSError, ValueError, etree.XMLSyntaxError) as error:
            raise inkex.AbortExtension(f"Logo kit export failed: {error}") from error
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
        if self.o.open_folder:
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(destination)])
                elif sys.platform == "win32":
                    import os
                    os.startfile(destination)
                else:
                    subprocess.Popen(["xdg-open", str(destination)])
            except OSError:
                pass
