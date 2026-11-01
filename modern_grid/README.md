# Modern Grid 4.4.0

A compact English interface for the existing Modern Grid extension, plus a target selector.

## Use

Open **Extensions → Binsalmarts Extensions > → Modern Grid**.

Choose **Apply to**:

- **All artboards**: generate the chosen grid on every Inkscape page, using each page's position and dimensions. Ordinary single-page documents still work.
- **Selected objects**: select one or more shapes, paths, text objects, images, clones or groups first. Each selection gets a grid fitted to its surrounding rectangular bounds. A circle gets a rectangular grid around it, without clipping the grid to the circle. A selected group is treated as one target.

Choose a tab: **Column Grid**, **Row Grid**, **Grid**, or **Bento Grid**, then click **Apply**.

## Compact interface

Layout and margins now appear side by side. Top/bottom and left/right margins share rows. Color is a compact button that opens the color picker, and opacity remains directly accessible.

All existing parameters, ranges, defaults and option values are retained: Stretch/Fixed/Auto, counts, fixed sizes, gutters, alignment, offsets, linked or individual margins, color, opacity, Fill/Outline, outer border, Bento seed, layout synchronization and rounded corners.

The existing extension ID and menu location are retained, so saved settings continue to use the same parameter names. Rerunning replaces only the chosen grid type; the other grid types can still coexist. Source artwork stays editable and unchanged.

## Install or restore

Copy `modern_grid.py` and `modern_grid.inx` together into the existing Modern Grid extension directory, replacing the previous two files. Restart Inkscape to reload the interface.

For this update, the original 4.3.1 files are preserved in `original/` in the workspace and in `Modern-Grid-4.3.1-backup.zip`. Restore both original files together if needed.

## Validation

18 tests passed with Inkex 1.4.0 and Inkscape 1.4.4 on macOS, including 16 comparison cases against the original single-page implementation, descriptor validation, every existing parameter, multi-page placement, shape/group selection, real text and clone bounds, mm/viewBox conversion, repeated updates and Bento layout behavior.

No extra Python packages are required beyond the environment shipped with Inkscape. Real text and clone bounds are measured using the installed Inkscape renderer.
