#!/usr/bin/env python3
"""
Modern Grid - Inkscape Extension
Column Grid  |  Row Grid  |  Grid  |  Bento Grid
Version: 4.4.0 (Compact UI and Target Selection)
"""

import inkex
from inkex import Rectangle, Line
from copy import deepcopy
import math
import re
import random
from tempfile import TemporaryDirectory
from inkex.command import inkscape, write_svg


class ModernGrid(inkex.EffectExtension):

    def add_arguments(self, pars):
        pars.add_argument("--tab", type=str, default="column")
        pars.add_argument("--target", type=str, default="artboards")

        # ── Column ──────────────────────────────────────────────────────
        pars.add_argument("--col_count",         type=int,           default=12)
        pars.add_argument("--col_type",          type=str,           default="stretch")
        pars.add_argument("--col_width",         type=float,         default=60.0)
        pars.add_argument("--col_margin_lock",   type=inkex.Boolean, default=False)
        pars.add_argument("--col_margin_all",    type=float,         default=20.0)
        pars.add_argument("--col_margin_top",    type=float,         default=20.0)
        pars.add_argument("--col_margin_bottom", type=float,         default=20.0)
        pars.add_argument("--col_margin_left",   type=float,         default=20.0)
        pars.add_argument("--col_margin_right",  type=float,         default=20.0)
        pars.add_argument("--col_gutter",        type=float,         default=16.0)
        pars.add_argument("--col_align",         type=str,           default="center")
        pars.add_argument("--col_offset",        type=float,         default=0.0)
        pars.add_argument("--col_color",         type=str,           default="#FF0000")
        pars.add_argument("--col_opacity",       type=float,         default=0.1)

        # ── Row ─────────────────────────────────────────────────────────
        pars.add_argument("--row_count",         type=int,           default=8)
        pars.add_argument("--row_type",          type=str,           default="stretch")
        pars.add_argument("--row_height",        type=float,         default=60.0)
        pars.add_argument("--row_margin_lock",   type=inkex.Boolean, default=False)
        pars.add_argument("--row_margin_all",    type=float,         default=20.0)
        pars.add_argument("--row_margin_top",    type=float,         default=20.0)
        pars.add_argument("--row_margin_bottom", type=float,         default=20.0)
        pars.add_argument("--row_margin_left",   type=float,         default=20.0)
        pars.add_argument("--row_margin_right",  type=float,         default=20.0)
        pars.add_argument("--row_gutter",        type=float,         default=16.0)
        pars.add_argument("--row_align",         type=str,           default="center")
        pars.add_argument("--row_offset",        type=float,         default=0.0)
        pars.add_argument("--row_color",         type=str,           default="#0066FF")
        pars.add_argument("--row_opacity",       type=float,         default=0.1)

        # ── Grid (squares) ──────────────────────────────────────────────
        pars.add_argument("--grd_columns",        type=int,           default=9)
        pars.add_argument("--grd_rows",           type=int,           default=10)
        pars.add_argument("--grd_gutter",         type=float,         default=8.0)
        pars.add_argument("--grd_style",          type=str,           default="fill")
        pars.add_argument("--grd_margin_lock",   type=inkex.Boolean, default=False)
        pars.add_argument("--grd_margin_all",    type=float,         default=20.0)
        pars.add_argument("--grd_margin_top",     type=float,         default=20.0)
        pars.add_argument("--grd_margin_bottom",  type=float,         default=20.0)
        pars.add_argument("--grd_margin_left",    type=float,         default=20.0)
        pars.add_argument("--grd_margin_right",   type=float,         default=20.0)
        pars.add_argument("--grd_color",          type=str,           default="#0000FF")
        pars.add_argument("--grd_opacity",        type=float,         default=0.08)
        pars.add_argument("--grd_border",         type=inkex.Boolean, default=True)

        # ── Bento Grid ──────────────────────────────────────────────────
        pars.add_argument("--bto_count",         type=int,           default=6)
        pars.add_argument("--bto_seed",          type=int,           default=1)
        pars.add_argument("--bto_sync",          type=inkex.Boolean, default=True)
        pars.add_argument("--bto_gutter",        type=float,         default=12.0)
        pars.add_argument("--bto_rounded",       type=float,         default=8.0)
        pars.add_argument("--bto_margin_lock",   type=inkex.Boolean, default=False)
        pars.add_argument("--bto_margin_all",    type=float,         default=20.0)
        pars.add_argument("--bto_margin_top",    type=float,         default=20.0)
        pars.add_argument("--bto_margin_bottom", type=float,         default=20.0)
        pars.add_argument("--bto_margin_left",   type=float,         default=20.0)
        pars.add_argument("--bto_margin_right",  type=float,         default=20.0)
        pars.add_argument("--bto_color",         type=str,           default="#AA00FF")
        pars.add_argument("--bto_opacity",       type=float,         default=0.15)

    # ────────────────────────────────────────────────────────────────────
    # Margin resolvers
    # ────────────────────────────────────────────────────────────────────

    def _col_margins(self):
        o = self.options
        if o.col_margin_lock:
            return o.col_margin_all, o.col_margin_all, o.col_margin_all, o.col_margin_all
        return o.col_margin_top, o.col_margin_bottom, o.col_margin_left, o.col_margin_right

    def _row_margins(self):
        o = self.options
        if o.row_margin_lock:
            return o.row_margin_all, o.row_margin_all, o.row_margin_all, o.row_margin_all
        return o.row_margin_top, o.row_margin_bottom, o.row_margin_left, o.row_margin_right

    def _grd_margins(self):
        o = self.options
        if o.grd_margin_lock:
            return o.grd_margin_all, o.grd_margin_all, o.grd_margin_all, o.grd_margin_all
        return o.grd_margin_top, o.grd_margin_bottom, o.grd_margin_left, o.grd_margin_right

    def _bto_margins(self):
        o = self.options
        if o.bto_margin_lock:
            return o.bto_margin_all, o.bto_margin_all, o.bto_margin_all, o.bto_margin_all
        return o.bto_margin_top, o.bto_margin_bottom, o.bto_margin_left, o.bto_margin_right

    # ────────────────────────────────────────────────────────────────────
    # Core helpers
    # ────────────────────────────────────────────────────────────────────

    def _parse_color(self, raw):
        s = str(raw).strip()
        if s.lstrip("-").isdigit():
            v = int(s) & 0xFFFFFFFF
            return (v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF
        h = s.lstrip("#")
        if len(h) == 3:  h = "".join(c * 2 for c in h)
        if len(h) == 8:  h = h[:6]
        if len(h) != 6:  return 0, 0, 255
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def _fill_style(self, color, opacity):
        r, g, b = self._parse_color(color)
        return f"fill:rgb({r},{g},{b});fill-opacity:{opacity:.4f};stroke:none;"

    def _stroke_style(self, color, opacity, width=0.5):
        r, g, b = self._parse_color(color)
        return (f"fill:none;stroke:rgb({r},{g},{b});"
                f"stroke-opacity:{opacity:.4f};stroke-width:{width};")

    def _add_clip(self, x0, y0, w, h, cid):
        defs = self.svg.defs
        old  = defs.find(f'.//*[@id="{cid}"]')
        if old is not None:
            old.getparent().remove(old)
        cp = inkex.ClipPath()
        cp.set("id", cid)
        r = Rectangle()
        r.set("x", str(x0));  r.set("y", str(y0))
        r.set("width", str(w)); r.set("height", str(h))
        cp.append(r)
        defs.append(cp)
        return f"url(#{cid})"

    def _get_layer(self):
        existing = self.svg.find(".//*[@id='modern-grid-layer']")
        if existing is not None:
            # تنظيف مصفوفة التحويل (transform) التي يفرضها إنكسكيب عند تعديل الصفحات لضمان دقة الإحداثيات المطلقة
            existing.attrib.pop("transform", None)
            return existing
        lyr = self.svg.add(inkex.Layer())
        lyr.label = "Modern Grid"
        lyr.set("{http://www.inkscape.org/namespaces/inkscape}groupmode", "layer")
        lyr.set("{http://www.inkscape.org/namespaces/inkscape}label", "Modern Grid")
        lyr.set("{http://www.sodipodi.com/DTD/sodipodi-0.0}insensitive", "true")
        lyr.set("id", "modern-grid-layer")
        return lyr

    def _remove_child(self, lyr, elem_id):
        old = lyr.find(f".//*[@id='{elem_id}']")
        if old is not None:
            old.getparent().remove(old)

    # ────────────────────────────────────────────────────────────────────
    # Get precise artboard dimensions - IMPROVED v2
    # ────────────────────────────────────────────────────────────────────
    
    def _get_artboard_rects(self):
        """
        Use native page coordinates for all artboards; retain the previous
        viewBox/viewport fallback for ordinary single-page documents.
        """
        namedview = self.svg.find(inkex.addNS("namedview", "sodipodi"))
        pages = namedview.findall(inkex.addNS("page", "inkscape")) if namedview is not None else []
        if pages:
            rects = [(page.x, page.y, page.width, page.height) for page in pages]
            for rect in rects:
                if any(not math.isfinite(value) for value in rect) or min(rect[2:]) <= 0:
                    raise inkex.AbortExtension("An artboard has invalid dimensions.")
            return rects
        rects = []
        
        # ✅ الطريقة الأساسية: استخدام viewBox (الأفضل - لا يتأثر بـ Scale)
        try:
            vb = self.svg.get_viewBox()
            if vb and len(vb) >= 4:
                x, y, w, h = float(vb[0]), float(vb[1]), float(vb[2]), float(vb[3])
                if w > 0 and h > 0:
                    rects.append((x, y, w, h))
        except:
            pass
        
        # إذا فشل viewBox، جرب viewport
        if not rects:
            try:
                w = float(self.svg.viewport_width or self.svg.width or 800)
                h = float(self.svg.viewport_height or self.svg.height or 600)
                if w > 0 and h > 0:
                    rects.append((0.0, 0.0, w, h))
            except:
                pass
        
        # الخيار الأخير الآمن
        if not rects:
            rects.append((0.0, 0.0, 800.0, 600.0))
        
        return rects

    @staticmethod
    def _parent_transform(node):
        """Read attributes directly so querying bounds does not alter artwork."""
        transform = inkex.Transform()
        for parent in node.iterancestors():
            transform = inkex.Transform(parent.attrib.get("transform")) @ transform
        return transform

    def _rendered_bounds(self, selected):
        """Use Inkscape for text/clone bounds that Inkex cannot measure accurately."""
        try:
            with TemporaryDirectory(prefix="modern-grid-bounds-") as directory:
                filename = write_svg(self.svg, directory, "input.svg")
                output = inkscape(filename, query_all=True)
            boxes = {}
            for line in output.splitlines():
                parts = line.rsplit(",", 4)
                if len(parts) == 5:
                    try:
                        boxes[parts[0]] = tuple(map(float, parts[1:]))
                    except ValueError:
                        continue
            viewbox = self.svg.get_viewbox()
            if viewbox == [0, 0, 0, 0]:
                viewbox = [0, 0, self.svg.viewport_width, self.svg.viewport_height]
            vx, vy, vw, vh = viewbox
            width, height = self.svg.viewport_width, self.svg.viewport_height
            sx, sy = width / vw, height / vh
            par = self.svg.get("preserveAspectRatio", "xMidYMid meet").split()
            ox = oy = 0.0
            if "none" not in par:
                sx = sy = max(sx, sy) if "slice" in par else min(sx, sy)
                align = next((part for part in par if part.startswith("x")), "xMidYMid")
                ox = (width - vw * sx) * (1 if "xMax" in align else 0 if "xMin" in align else 0.5)
                oy = (height - vh * sy) * (1 if "YMax" in align else 0 if "YMin" in align else 0.5)
            result = {}
            for node in selected:
                box = boxes.get(node.get("id"))
                if box is None:
                    raise ValueError("Missing object bounds")
                x, y, w, h = box
                result[node.get("id")] = ((x - ox) / sx + vx, (y - oy) / sy + vy, w / sx, h / sy)
            return result
        except (ValueError, ZeroDivisionError, OSError, inkex.command.ProgramRunError,
                inkex.command.CommandNotFound) as error:
            raise inkex.AbortExtension("Could not measure the selected objects. Make sure they are visible and Inkscape is available.") from error

    def _get_selection_rects(self):
        selected = list(self.svg.selection.values())
        # A selected group already includes its children; avoid duplicate grids.
        selected = [node for node in selected if not any(parent in selected for parent in node.iterancestors())]
        if not selected:
            raise inkex.AbortExtension("Select one or more objects, then choose Selected objects.")
        if any(not isinstance(node, inkex.ShapeElement) for node in selected):
            raise inkex.AbortExtension("Select drawable objects such as shapes, paths, text, images or groups.")
        if any(node.get("id") == "modern-grid-layer" or
               any(parent.get("id") == "modern-grid-layer" for parent in node.iterancestors()) for node in selected):
            raise inkex.AbortExtension("Select your artwork, rather than the generated Modern Grid layer.")
        # Inkex's wrapped attributes can normalize source XML while measuring.
        # Read geometry on a detached copy of the complete document instead.
        snapshot = deepcopy(self.svg)
        nodes = dict(zip(self.svg.iter(), snapshot.iter()))
        result = {}
        rendered = []
        for node in selected:
            copy = nodes[node]
            if any(isinstance(child, (inkex.TextElement, inkex.Use)) for child in copy.iter()):
                rendered.append(node)
                continue
            if isinstance(copy, (inkex.Circle, inkex.Ellipse)) and copy.clip is None:
                # Exact ellipse bounds avoid the small Bezier approximation error
                # in the generic path bounding box, including rotated/scaled shapes.
                transform = self._parent_transform(copy) @ inkex.Transform(copy.attrib.get("transform"))
                center = transform.apply_to_point(copy.center)
                rx, ry = copy.rxry()
                half_width = math.hypot(transform.a * rx, transform.c * ry)
                half_height = math.hypot(transform.b * rx, transform.d * ry)
                result[node.get("id")] = (center.x - half_width, center.y - half_height,
                                          2 * half_width, 2 * half_height)
                continue
            try:
                box = copy.bounding_box(transform=self._parent_transform(copy))
            except (ValueError, TypeError, NotImplementedError):
                box = None
            if box is None or box.width <= 0 or box.height <= 0:
                rendered.append(node)
            else:
                result[node.get("id")] = (box.left, box.top, box.width, box.height)
        if rendered:
            result.update(self._rendered_bounds(rendered))
        rects = [result[node.get("id")] for node in selected]
        if any(any(not math.isfinite(value) for value in rect) or min(rect[2:]) <= 0 for rect in rects):
            raise inkex.AbortExtension("Each selected object must have a nonzero width and height.")
        return rects

    def _clean_active_clips(self, tab):
        # Remove only this grid type's generated clips before rebuilding it.
        # Otherwise changing from several targets to one leaves unused defs.
        prefix = {"column": "mg-col-clip-", "row": "mg-row-clip-"}.get(tab)
        if prefix:
            for element in list(self.svg.defs):
                if isinstance(element, inkex.ClipPath) and element.get("id", "").startswith(prefix):
                    element.getparent().remove(element)

    # ────────────────────────────────────────────────────────────────────
    # Layout math
    # ────────────────────────────────────────────────────────────────────

    def _col_layout(self, x0, total_w, count, col_type, fixed_w,
                    margin_top, margin_bottom, margin_left, margin_right, gutter,
                    alignment):
        if margin_left < 0: margin_left = 0
        if margin_right < 0: margin_right = 0
        if margin_top < 0: margin_top = 0
        if margin_bottom < 0: margin_bottom = 0

        area_w = total_w - margin_left - margin_right
        area_x = x0 + margin_left

        if col_type == "fixed":
            cols = []
            total_col_w = count * fixed_w + (count - 1) * gutter
            offset = 0 if alignment == "left" else (
                (area_w - total_col_w) / 2 if alignment == "center" else
                area_w - total_col_w)
            for i in range(count):
                cols.append((x0 + margin_left + offset + i * (fixed_w + gutter), fixed_w))
        else:
            w_col = (area_w - (count - 1) * gutter) / count if count > 0 else 0
            cols = [(area_x + i * (w_col + gutter), w_col) for i in range(count)]
        return cols

    def _row_layout(self, y0, total_h, count, row_type, fixed_h,
                    margin_top, margin_bottom, margin_left, margin_right, gutter,
                    alignment):
        if margin_left < 0: margin_left = 0
        if margin_right < 0: margin_right = 0
        if margin_top < 0: margin_top = 0
        if margin_bottom < 0: margin_bottom = 0

        area_h = total_h - margin_top - margin_bottom
        area_y = y0 + margin_top

        if row_type == "fixed":
            rows = []
            total_row_h = count * fixed_h + (count - 1) * gutter
            offset = 0 if alignment == "top" else (
                (area_h - total_row_h) / 2 if alignment == "center" else
                area_h - total_row_h)
            for i in range(count):
                rows.append((y0 + margin_top + offset + i * (fixed_h + gutter), fixed_h))
        else:
            h_row = (area_h - (count - 1) * gutter) / count if count > 0 else 0
            rows = [(area_y + i * (h_row + gutter), h_row) for i in range(count)]
        return rows

    # ────────────────────────────────────────────────────────────────────
    # Draw Column Grid
    # ────────────────────────────────────────────────────────────────────

    def _draw_columns(self, lyr, rects):
        self._remove_child(lyr, "mg-columns")
        o = self.options
        mt, mb, ml, mr = self._col_margins()
        cols_count = max(1, o.col_count)

        grp = lyr.add(inkex.Group())
        grp.set("id", "mg-columns")

        style = self._fill_style(o.col_color, o.col_opacity)

        for idx, (x0, y0, w, h) in enumerate(rects):
            cols = self._col_layout(x0, w, cols_count, o.col_type, o.col_width,
                                   mt, mb, ml, mr, o.col_gutter, o.col_align)
            cols = [(c[0] + o.col_offset, c[1]) for c in cols]
            sub_grp = grp.add(inkex.Group())

            for cx, cw in cols:
                clip_id = f"mg-col-clip-{idx}-{len(sub_grp)}"
                clip = self._add_clip(cx, y0 + mt, cw, h - mt - mb, clip_id)

                col = sub_grp.add(Rectangle())
                col.set("x",      str(cx))
                col.set("y",      str(y0 + mt))
                col.set("width",  str(cw))
                col.set("height", str(h - mt - mb))
                col.set("style",  style)
                col.set("clip-path", clip)
                col.set("id",     f"mg-col-{idx}-{len(sub_grp)}")

    # ────────────────────────────────────────────────────────────────────
    # Draw Row Grid
    # ────────────────────────────────────────────────────────────────────

    def _draw_rows(self, lyr, rects):
        self._remove_child(lyr, "mg-rows")
        o = self.options
        mt, mb, ml, mr = self._row_margins()
        rows_count = max(1, o.row_count)

        grp = lyr.add(inkex.Group())
        grp.set("id", "mg-rows")

        style = self._fill_style(o.row_color, o.row_opacity)

        for idx, (x0, y0, w, h) in enumerate(rects):
            rows = self._row_layout(y0, h, rows_count, o.row_type, o.row_height,
                                   mt, mb, ml, mr, o.row_gutter, o.row_align)
            rows = [(r[0] + o.row_offset, r[1]) for r in rows]
            sub_grp = grp.add(inkex.Group())

            for ry, rh in rows:
                clip_id = f"mg-row-clip-{idx}-{len(sub_grp)}"
                clip = self._add_clip(x0 + ml, ry, w - ml - mr, rh, clip_id)

                row = sub_grp.add(Rectangle())
                row.set("x",      str(x0 + ml))
                row.set("y",      str(ry))
                row.set("width",  str(w - ml - mr))
                row.set("height", str(rh))
                row.set("style",  style)
                row.set("clip-path", clip)
                row.set("id",     f"mg-row-{idx}-{len(sub_grp)}")

    # ────────────────────────────────────────────────────────────────────
    # Draw Grid (squares)
    # ────────────────────────────────────────────────────────────────────

    def _draw_grid(self, lyr, rects):
        self._remove_child(lyr, "mg-grid")
        o = self.options
        mt, mb, ml, mr = self._grd_margins()
        cols = max(1, o.grd_columns)
        rows = max(1, o.grd_rows)
        gutter = max(0.0, o.grd_gutter)
        opacity = max(0.0, min(1.0, o.grd_opacity))

        grp = lyr.add(inkex.Group())
        grp.set("id", "mg-grid")

        for idx, (x0, y0, w, h) in enumerate(rects):
            area_x = x0 + ml
            area_y = y0 + mt
            area_w = w - ml - mr
            area_h = h - mt - mb
            cell_w = (area_w - (cols - 1) * gutter) / cols if cols > 0 else 0
            cell_h = (area_h - (rows - 1) * gutter) / rows if rows > 0 else 0

            sub_grp = grp.add(inkex.Group())

            if o.grd_style == "fill":
                cell_style = self._fill_style(o.grd_color, opacity)
                for col in range(cols):
                    for row in range(rows):
                        cx = area_x + col * (cell_w + gutter)
                        cy = area_y + row * (cell_h + gutter)
                        rect = sub_grp.add(Rectangle())
                        rect.set("x",      f"{cx:.4f}")
                        rect.set("y",      f"{cy:.4f}")
                        rect.set("width",  f"{cell_w:.4f}")
                        rect.set("height", f"{cell_h:.4f}")
                        rect.set("style",  cell_style)
                        rect.set("id",     f"mg-cell-{idx}-{row}-{col}")
            else:
                line_style = self._stroke_style(o.grd_color, opacity, width=0.5)
                for col in range(cols + 1):
                    if col == 0:       lx = area_x
                    elif col == cols:  lx = area_x + area_w
                    else:              lx = area_x + col * (cell_w + gutter) - gutter / 2
                    ln = sub_grp.add(Line())
                    ln.set("x1", f"{lx:.4f}"); ln.set("y1", f"{area_y:.4f}")
                    ln.set("x2", f"{lx:.4f}"); ln.set("y2", f"{area_y + area_h:.4f}")
                    ln.set("style", line_style)
                for row in range(rows + 1):
                    if row == 0:       ly = area_y
                    elif row == rows:  ly = area_y + area_h
                    else:              ly = area_y + row * (cell_h + gutter) - gutter / 2
                    ln = sub_grp.add(Line())
                    ln.set("x1", f"{area_x:.4f}");          ln.set("y1", f"{ly:.4f}")
                    ln.set("x2", f"{area_x + area_w:.4f}"); ln.set("y2", f"{ly:.4f}")
                    ln.set("style", line_style)

            if o.grd_border:
                bstyle = self._stroke_style(o.grd_color, opacity, width=1.0)
                brect  = sub_grp.add(Rectangle())
                brect.set("x",      f"{area_x:.4f}")
                brect.set("y",      f"{area_y:.4f}")
                brect.set("width",  f"{area_w:.4f}")
                brect.set("height", f"{area_h:.4f}")
                brect.set("style",  bstyle)
                brect.set("id",     f"mg-grid-border-{idx}")

    # ────────────────────────────────────────────────────────────────────
    # Draw Bento Grid (Binary Space Partitioning Layout)
    # ────────────────────────────────────────────────────────────────────

    def _draw_bento(self, lyr, rects):
        self._remove_child(lyr, "mg-bento")
        o = self.options
        mt, mb, ml, mr = self._bto_margins()
        count = max(2, o.bto_count)
        gutter = max(0.0, o.bto_gutter)
        opacity = max(0.0, min(1.0, o.bto_opacity))

        grp = lyr.add(inkex.Group())
        grp.set("id", "mg-bento")

        style = self._fill_style(o.bto_color, opacity)

        for idx, (x0, y0, w, h) in enumerate(rects):
            if o.bto_sync:
                random.seed(o.bto_seed)
            else:
                random.seed(o.bto_seed + idx)

            bx = x0 + ml - gutter / 2
            by = y0 + mt - gutter / 2
            bw = w - ml - mr + gutter
            bh = h - mt - mb + gutter

            if bw <= 0 or bh <= 0:
                continue

            blocks = [[bx, by, bw, bh]]

            while len(blocks) < count:
                blocks.sort(key=lambda b: b[2] * b[3], reverse=True)
                target = blocks.pop(0)
                tx, ty, tw, th = target

                if tw > 1.8 * th:
                    split_vertical = True
                elif th > 1.8 * tw:
                    split_vertical = False
                else:
                    split_vertical = random.choice([True, False])

                ratios = [0.5, 0.333, 0.666, 0.4, 0.6]
                ratio = random.choice(ratios)

                if split_vertical:
                    tw1 = tw * ratio
                    tw2 = tw - tw1
                    blocks.append([tx, ty, tw1, th])
                    blocks.append([tx + tw1, ty, tw2, th])
                else:
                    th1 = th * ratio
                    th2 = th - th1
                    blocks.append([tx, ty, tw, th1])
                    blocks.append([tx, ty + th1, tw, th2])

            sub_grp = grp.add(inkex.Group())
            
            for b_idx, b in enumerate(blocks):
                final_x = b[0] + gutter / 2
                final_y = b[1] + gutter / 2
                final_w = b[2] - gutter
                final_h = b[3] - gutter

                if final_w <= 1 or final_h <= 1:
                    continue

                rect = sub_grp.add(Rectangle())
                rect.set("x", f"{final_x:.4f}")
                rect.set("y", f"{final_y:.4f}")
                rect.set("width", f"{final_w:.4f}")
                rect.set("height", f"{final_h:.4f}")
                
                if o.bto_rounded > 0:
                    rect.set("rx", f"{o.bto_rounded:.4f}")
                    rect.set("ry", f"{o.bto_rounded:.4f}")
                    
                rect.set("style", style)
                rect.set("id", f"mg-bto-item-{idx}-{b_idx+1}")

    # ────────────────────────────────────────────────────────────────────
    # Entry
    # ────────────────────────────────────────────────────────────────────

    def effect(self):
        tab = self.options.tab
        if tab not in ("column", "row", "grid", "bento"):
            raise inkex.AbortExtension("Unknown grid type.")
        if self.options.target == "selection":
            rects = self._get_selection_rects()
        elif self.options.target == "artboards":
            rects = self._get_artboard_rects()
        else:
            raise inkex.AbortExtension("Choose All artboards or Selected objects.")
        lyr = self._get_layer()
        self._clean_active_clips(tab)
        
        # Layout/drawing options and algorithms are unchanged.
        
        # التحقق من أن جميع الآرتبوردات لها نفس الحجم (اختياري)
        if len(rects) > 1:
            w0, h0 = rects[0][2], rects[0][3]
            for r in rects:
                if abs(r[2] - w0) > 0.05 or abs(r[3] - h0) > 0.05:
                    # تحذير لكن لا نوقف البرنامج
                    pass

        if tab == "column":
            self._draw_columns(lyr, rects)
        elif tab == "row":
            self._draw_rows(lyr, rects)
        elif tab == "grid":
            self._draw_grid(lyr, rects)
        elif tab == "bento":
            self._draw_bento(lyr, rects)


if __name__ == "__main__":
    ModernGrid().run()
