# Page Numbering Pro 1.2

An Inkscape 1.4 extension with an English interface and editable SVG page numbers. Supports Western and Arabic-Indic digits, nine positions, a designed number as a template, optional sequential updates, and leading zeros. Uses Python and Inkex supplied with Inkscape.

## Installation

Extract `dist/Page-Numbering-Pro-1.2.0.zip` and copy `page_numbering_pro.py` and `page_numbering_pro.inx` together into **Edit → Preferences → System → User extensions**, replacing both existing files. Restart Inkscape.

Open **Extensions → Binsalmarts Extensions > → Page Numbering Pro**. The combined `Binsalmarts-Extensions-2026-10-07.zip` contains all three extensions in separate folders; install each folder once to avoid duplicate copies.

## Numbering with settings

1. In **Numbering**, choose **All pages**, the **Start number (all pages)** and **Digit style**.
2. Set **Minimum digits**: `1` gives `1`, `2` gives `01`, and `3` gives `001`. Values from 1 to 12 are supported. Larger numbers are never truncated: width 2 still displays `100`. Arabic-Indic uses matching zeros, such as `٠٠١`.
3. In **Placement & Template**, choose **Use settings**, then the vertical and horizontal positions and margins in pixels.
4. In **Appearance**, choose the font, size, style and color, then click **Apply**.

| Vertical position | Left | Center | Right |
| --- | --- | --- | --- |
| Top | Top left | Top center | Top right |
| Middle | Middle left | Page center | Middle right |
| Bottom | Bottom left | Bottom center | Bottom right |

Numbers follow document page order in the **Page Numbering** layer. Rerunning updates existing numbers, creates numbers for added pages and removes numbering for deleted pages. Other design text is preserved. Updates happen when running the extension; there is no continuous watcher.

**All pages** with **Use settings** rebuilds the sequence from the start value and uses the chosen minimum digits. Set it back to 1 to remove padding in this mode. Formatting zeros never change the numeric value.

## Copy a designed number as a template

1. Create a plain text number inside a page, such as `1`, `001` or `١`. Set its font, size, color and position.
2. Select it and open the extension.
3. Choose **Copy a number as a template**, with **Selected text number, including manually created text** as the source.
4. Leave the scope at **Auto** or choose **All pages**, then click **Apply**.

The source becomes that page's number without adding a duplicate. Copies retain font, size, style, color, opacity, alignment, digit script, styled text runs and transforms, including rotation and scaling inherited from groups.

Position follows the first text anchor as a proportion of each page. A number at 50% of page width and 90% of height appears at those proportions on other pages. Font size remains unchanged even when page sizes differ. Equal page sizes retain the same offsets.

The template value anchors the sequence: `17` on page 2 gives `16`, `17`, `18`. Manual start value, digit style, font and placement settings are ignored in template mode. **Minimum digits** still applies: existing leading zeros in a template are preserved, or extended if the minimum is wider. A template `007` gives `007`, `008`, `009`; use a template `7` to remove its inherited padding. Western, Arabic-Indic and Persian template digits remain supported.

To copy later edits from the first managed number, edit it with the text tool and choose **First existing number in page order**. Selection is unnecessary for this source.

A template must contain an integer from 0 to 999999 in ordinary SVG text. Text on a path, flowed text, mixed words and numbers, and text converted to paths are unsupported. Selecting a number's tspan also works. A manually created template's anchor must lie within one page.

## Edit one number and optionally update following pages

Select a managed number. In **Use settings**, **Auto** updates the selection only. In template mode, choose **Selected number only** for an individual update; Auto normally uses the template for all pages.

- Leave **Change selected value** off to preserve its current value, including manual text edits, while changing appearance or padding.
- Enable it and enter **New selected number** to replace the value.
- Enable **Renumber following pages** to update the selected page and later pages. This is off by default.

For example, `1, 2, 3, 4` becomes `1, 3, 4, 5` when page 2 changes to 3 with this option enabled. Earlier pages stay unchanged. Following numbers retain their style, location and parent group; their values change. Their existing padding is retained and expanded if **Minimum digits** is wider. Missing following page numbers are created.

This works with **Selected number only**, or **Auto** with a selected number, in both styling modes. **All pages** updates the complete sequence according to the styling mode.

## Margins and fonts

**Top / bottom margin (px)** measures from the chosen edge to the text baseline. At **Middle**, the baseline is at half the page height and the vertical margin is ignored. Glyph ink bounds vary by font.

**Side margin (px)** measures to the start of the number at Left, or its end at Right. It is ignored at Center. Manual margins and font sizes use SVG pixels at 96 px per inch, including mm/cm documents, independently of zoom.

Choose an installed font. Inkscape uses a fallback if it is missing. Numbers remain editable text; converting them to paths prevents later text updates.

## Examples and validation

Editable SVG examples are in `examples/page_numbering/`, including basic numbering, Arabic digits, templates, sequential updates, `leading_zeros.svg` and `arabic_leading_zeros.svg`.

Tests cover nine positions, inherited formatting, page sizes and order, reruns, templates, cascading updates, leading zeros in all supported digit scripts, px/mm units and INX schema validation. Renderer integration uses Inkscape 1.4.4 and Inkex 1.4.0 on macOS. Linux compatibility is targeted but has not been tested on a Linux host.

```bash
python3 tests/run_tests.py --inkex-dir /usr/share/inkscape/extensions --pattern test_page_numbering_pro.py --inkscape /usr/bin/inkscape
python3 tools/package_page_numbering.py
```

Managed numbers are identified by extension markers and page IDs. A manual text number is adopted only when explicitly chosen as a template. Duplicated managed numbers are reduced to one per page during an all-page update.

## References and license

- [Inkex pages](https://inkscape.gitlab.io/extensions/documentation/source/inkex.elements._meta.html)
- [Inherited styles in Inkex](https://inkscape.gitlab.io/extensions/documentation/source/inkex.elements._base.html)
- [INX interface](https://inkscape.gitlab.io/extensions/documentation/authors/inx-widgets.html)

MIT license, as in `LICENSE`.
