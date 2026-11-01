# Artboard Maker Pro 1.0

Creates **native Inkscape pages**, with uniform or mixed sizes arranged in rows and columns. The English interface is under **Extensions → Binsalmarts Extensions > → Artboard Maker Pro**. Requires Inkscape 1.4 and its bundled Python/Inkex; no additional packages.

## Use

1. Open the extension. In **Layout**, set **Rows**, **Columns**, **Horizontal gap** and **Vertical gap**. The count is Rows × Columns. Gaps always use pixels.
2. In **Sizes**, select **One size for every artboard** or **Different sizes from a list**.
3. For one size, select a preset or enter custom width and height, with px, mm, cm or inches. Presets include A3/A4/A5, Letter, Tabloid, Square, Story, Full HD, Web and Business card.
4. For mixed sizes, enter a semicolon-separated list, such as `1080x1080; 1080x1920; 1920x1080`, or `A4; A5; 210x297mm`. The list repeats in the chosen fill order until the grid is full. Each entry needs one grid cell; extra entries produce a validation error.
5. Choose the page action and starting position in **Document**, then click **Apply**.

**Swap width and height** rotates the dimensions of every requested size. Presets keep their physical sizes, independently of the custom/list unit. Entries can specify their own units; a trailing unit applies to both dimensions, so `210x297mm` means 210 mm × 297 mm. Entries without units use **Custom / list unit**.

## Grid and spacing

**Across rows** creates pages left to right, then moves to the next row. **Down columns** creates pages top to bottom, then moves to the next column. Native page order follows this setting, so Page Numbering Pro uses the same order.

Each column uses its widest page; each row uses its tallest page. Gaps separate these tracks, keeping every page clear of its neighbors. With a uniform size, the visible page gaps exactly equal the settings. Mixed smaller pages can have additional space inside their tracks. **Within each cell** aligns them at Top left, Center or Bottom right.

## Existing pages and repeat runs

- **Create / update the last generated grid** is the default. It updates that grid on reruns and retains page IDs where possible. This keeps surviving pages connected to Page Numbering Pro. On a document without explicit page metadata, the existing document page becomes the first requested artboard, giving exactly Rows × Columns pages. Other existing native pages are retained; a new grid is placed to their right.
- **Add a new grid; keep existing pages** adds another batch. A document's implicit page is explicitly retained as well. A later Update affects the most recently generated batch.
- **Replace all page definitions; keep artwork** replaces the existing page boundaries with the requested grid. Artwork, layers and guides remain in place.

**Automatic** retains the position of a grid being updated. A newly added grid starts beside existing pages, separated by Horizontal gap. **Custom starting position** uses Start X/Y in pixels relative to the document origin. Negative coordinates are supported.

The page names use **Artboard name prefix**, followed by a number. The prefix can include Arabic or other Unicode text.

Changing page boundaries does not move or resize artwork. On a new canvas, the root viewport is resized to the first generated page while preserving the existing SVG scale and viewBox origin. Imported SVGs with unequal X/Y scales require `preserveAspectRatio="none"` to resize without changing their artwork; validation rejects incompatible resize operations before changing the document. SVGs using a nonuniform canvas with letterboxing can still receive appended pages.

Rerun Modern Grid or Page Numbering Pro after changing page count or dimensions to update their generated content.

## Installation

Extract `dist/Artboard-Maker-Pro-1.0.0.zip`. Copy its extension folder into **Edit → Preferences → System → User extensions**. Keep `artboard_maker_pro.py` and `artboard_maker_pro.inx` together, and install only one copy. Restart Inkscape.

The updated combined package is `dist/Binsalmarts-Extensions-with-Artboard-Maker-2026-10-07.zip`.

## Validation and examples

The maximum is 1,000 total pages, with at most 100 rows and 100 columns. Invalid sizes, lists or dimensions are rejected before modifying the SVG.

Tests cover uniform/mixed tracks, cell alignment, page order, unit conversion, presets, update/append/replacement, stable page IDs, preserved artwork and guides, INX schema, interoperability with the existing grid and numbering extensions, and actual Inkscape PNG exports of different page sizes. Tested with Inkex 1.4.0 and Inkscape 1.4.4 on macOS.

Editable examples are in `examples/artboard_maker/`.

```bash
python3 tests/run_tests.py --inkex-dir /usr/share/inkscape/extensions --pattern test_artboard_maker_pro.py --inkscape /usr/bin/inkscape
python3 tools/package_artboard_maker.py
```

Native page implementation follows the [Inkex page API](https://inkscape.gitlab.io/extensions/documentation/source/inkex.elements._meta.html) and [Inkscape 1.4.4 page source](https://gitlab.com/inkscape/inkscape/-/blob/INKSCAPE_1_4_4/src/object/sp-page.cpp).

MIT license, as in `LICENSE`.
