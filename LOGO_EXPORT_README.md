# Logo Export Pro · 2.0.0

Export existing horizontal/vertical designs together, a finished logo, a single
icon/name, or a separately assigned icon and name. Names may be **paths, groups,
raster images or text**. Ready variants matches rendered artwork; it does not
require live text or named layers. The English interface has Source, Templates, Identity, Layouts, Sizing, Colors
and Export tabs. Arabic artwork and text are supported. Tested with Inkscape 1.4.4.

The previous 1.2.1 Ready variants fix remains: live text with Inkscape line/word spans is matched whole.
The complete text object is matched, so Arabic shaping stays intact. Invisible
optional child paths no longer stop recognition; an empty selected or assigned
object still reports its ID for correction.


## Named templates: identity kits from your own finished designs (new default)

Design every variant yourself: icon, horizontal, vertical, a custom footer,
lockup, stamp, background application, safe-area version or tight crop. The
extension reads the current artwork on every export. It does not rebuild or
center named templates and does not extract duplicate icon/name copies.

1. Group each finished design separately. In Object Properties, set its **Label**
   to `-ex-horizontal-bg`, `-ex-vertical-safe`, `-ex-icon-tight`, etc. The prefix
   is configurable; any extra name is supported, e.g. `-ex-footer-bg`.
2. Inside each export group, label the icon group `-icon-`, the name artwork
   `-text-`, and its background shape/group `-bg-`. Names can be paths, groups,
   live Arabic text or embedded raster images. Unmarked artwork uses the icon
   color. Mark decorations `-keep-` to preserve their colors.
3. For a blank safe area or an exact canvas, add one rectangle labeled `-frame-`
   inside the group. Its bounds define the output canvas; the rectangle is
   removed from exported copies. Keep this guide visible in the editor; `fill:none`
   is fine. Hidden ancestor groups are not exportable. The artwork may be
   intentionally off-center. Without a frame, a single background defines the
   canvas; otherwise the finished group bounds do.
4. Choose **Named templates** in Source. Select the named groups, or choose
   **All named groups in the document** in Templates. Labels describe the export
   groups, not just the containing document layer. Export groups cannot nest.
5. In Identity enter, for example:
   `Navy=#0f1b34; Blue=#397ce0; Paper=#f0f4f7; Mint=#cbe6e2`.
   Names are optional: `#0f1b34; #397ce0` also works. Include black and white is
   optional. Background palette may be blank (all identity colors), or separate.
6. Enable **Icon and name in the same identity color** and/or **Colored icon +
   black / white name**. Background templates receive qualifying foreground /
   background combinations. A ratio below Minimum contrast is skipped; 3 is a
   design filter, not a blanket text accessibility guarantee. Choose the neutral
   name with best contrast, or both black and white when they qualify.
   Transparent templates generate both neutral names because their eventual
   background is unknown. Original designs can also be exported unchanged.
7. Choose Output folder, formats and Raster sizes in Export, then Apply.

You can mark objects through **Source → Action** instead of typing labels.
Select one group and choose **Mark selection as export template**; set its name
in Templates. Select the icon, name, background or guide separately and use the
corresponding Mark action. These explicit actions update labels/role metadata;
normal exports do not change the document.

Group suffixes organize the kit:

| Example label | Output organization |
| --- | --- |
| `-ex-horizontal-bg` | horizontal / background / format |
| `-ex-horizontal-safe` | horizontal / safe / format |
| `-ex-horizontal-tight` | horizontal / transparent / format |
| `-ex-custom-name-bg` | custom-name / background / format |

A `-bg-` role makes a template a background application regardless of suffix.
Suffixes do not create padding or backgrounds: you design the frame and background
inside the group. This keeps the exact margins, scaling, position and arrangement
from your artwork. Nonrectangular backgrounds are supported; the export canvas
is rectangular. SVG/PDF/PNG/WEBP preserve designed transparency. JPG and EPS use
a neutral opaque canvas for transparent artwork; a designed background is kept.

The **offline index.html / preview.html** gallery includes palette swatches,
background rows, separate background / safe / transparent sections, design and
canvas filters, search, checker/light/dark preview surfaces and real download
links for every selected size/format. Outputs are organized by design, canvas
and format. WEBP is lossless. Original files are kept on subsequent exports;
a new kit folder is created each time. The manifest records all templates,
source bounds, palette and generated files.

Templates mode uses Templates, Identity and Export. Legacy Layouts, Sizing,
Colors and icon/name assignments remain available for the older source modes.
All interface text stays English; Arabic artwork is supported. Text is outlined
only in exported copies. Brand colors replace foreground paints while retaining
geometry, opacity, compound path holes and marked keep-color artwork. Embedded
images are tinted with their alpha retained; multicolor shading is not retained
in recolored recipes. Clip paths and masks are preserved as designed. For white
shapes intended as holes, use real compound-path holes or `-keep-` artwork; the
legacy white-cutout option applies only to legacy modes.

Limits: 32 templates, 16 colors, 512 generated variants, 8 raster sizes,
16–8192 px per longest edge, 32 million raster pixels. Background+logo contrasts
are checked by palette colors; effects, opacity and keep-color elements still
require visual review.

Install `logo_export_pro.py`, `logo_export_kit.py`, and `logo_export_pro.inx`
together in the existing Logo-Export-Pro folder. Restart Inkscape after saving
open documents. The generic `examples/named-templates.svg` demonstrates the
naming scheme. The separate workspace SABR example is made from read-only copies
of the reference client artwork and is not included in the general release ZIP.

---

## Legacy: export several finished variants together

1. Group each finished design separately: horizontal, vertical and standalone
   icon. Keep the sizes and spacing you have designed.
2. Select those groups together, then open Logo Export Pro.
3. Choose **Ready variants**, enter Brand / folder name and Output folder,
   then Apply.

The extension compares the icon artwork with components inside the other groups.
It identifies horizontal/vertical from the relative positions of the matched
icon and the remaining name, including right-to-left horizontal designs. It can
match outlined components without subgroups by splitting at empty gaps between
paths. When there is no standalone icon, it also searches for a shared grouped
or spatial component in the two finished designs.

Each finished horizontal/vertical design retains its own current sizes, spacing,
positions and stacking. The existing layouts are not rebuilt. Icon and Name
are exported once, and repeated matching standalone icons are collapsed to one
output. No extra As designed copy is created. Different designs assigned to the
same type require you to select one, rather than silently discarding a design.

This is visual matching, not a guarantee that every arbitrary logo can be
understood. If the icon/name are visually ambiguous, the layouts overlap, or
artwork differs between variants, use an explicit assignment:

- Select a group alone, choose **Action → Assign selected group as Horizontal**
  or **Vertical**, then Apply. For components, use **Assign selected object as
  icon** or **name**. Assign all the roles that need clarification.
- Select the finished groups together, switch Action back to **Export logo kit**,
  and export with **Ready variants**. Name artwork may be paths or a group.
- The assignments are stored on the objects. You do not need to rename layers.
  Only the role is remembered; geometry is read again at each export. You can
  also assign the icon and name inside one finished group (Ctrl+click). Leave
  them in that group and select the finished groups for export; the assigned
  components are used without a separate icon/name selection.

Optional layer/group labels are also recognized: **Horizontal**, **Vertical**,
**Icon**, **Name** or **Wordmark**, and their `logo-…` forms. Arabic labels such
as أفقي، عمودي، أيقونة، الاسم are accepted. An explicit Action assignment has
priority. Select the groups themselves, or a layer containing them. An outer
container can also be selected if its direct children have assigned roles or
recognized labels.

Ready variants uses the Horizontal / Vertical / Icon / Name checkboxes in Layouts
and exports only the types that exist or can be extracted. As designed and the
rebuild size/gap controls are ignored in this mode. Outer padding and Square
icon-only canvas still apply. Choose **Complete logo** for a single unclassified
finished group or several parts intended to form one logo.

## Export your own arrangement

1. Arrange the artwork exactly as you want it in Inkscape. Group a finished logo
   to preserve effects applied to the whole group.
2. Select that group or object. You can also select several separate logo parts.
3. Open **Extensions → Binsalmarts Extensions > → Logo Export Pro**.
4. Leave Action on **Export logo kit** and Logo source on **Complete logo**.
5. Enter a filename brand name, choose Output folder, and click Apply.

Complete logo mode exports **As designed**. It uses the current dimensions,
relative positions, stacking and spacing each time you export. It does not save
or reuse an old arrangement. Rebuild size/gap controls do not change As designed.
Outer padding adds space around the artwork without changing the artwork size.
For an exact cropped canvas without a margin, set Outer padding to 0.

A text-only logo needs no icon. A symbol-only logo needs no name. Both can use
Complete logo mode. The dedicated **Icon only** and **Name only** modes accept
one selected object or group and export just that component, using the applicable
Sizing controls. These modes do not require a second object. Their layout output
is selected by the source mode; the paired-layout checkboxes are not required.

The brand/folder name field only names files. It does not alter your name artwork.

## Choose icon and name yourself

For **Icon + name** mode, there are three explicit ways to choose the objects:

- **Assign from selection:** select the icon alone, choose Action → Assign
  selected object as icon, and Apply. Select the name alone, choose Action →
  Assign selected object as name, and Apply. Finally choose Action → **Export
  logo kit**, Logo source → **Icon + name**, and Choose object roles → **Use my
  assigned objects / Object IDs**. Export can use those objects without selecting
  both again. Assigning records their IDs in document metadata; it does not move,
  scale, recolor or rename either object. Clear assignments removes that metadata.
  Only object identity is recorded; layout geometry is always read afresh.
- **Object IDs:** enter Icon ID and Name ID from Inkscape Object Properties.
  These optional fields override the assigned object for the corresponding role.
- **Explicit stacking convention:** select two separate objects/groups and
  choose **First (back) object is icon** or **Last (front) object is icon**.
  First/last means stacking order from back to front, not click order.

The name may be outlined or grouped; it never has to contain a text element.
The icon and name must be distinct objects/groups, with neither containing the
other. Group the parts of each component before assigning it.

## Layout and sizing choices

Paired mode provides **As designed**, **Horizontal**, **Vertical**, **Icon only**
and **Name only** checkboxes. As designed retains your manually built lockup.
The other layouts are rebuilt from the explicitly chosen components. Horizontal
layouts place the icon on the chosen side; vertical layouts place it above the
name. Aspect ratios are always preserved.

| Sizing choice | Rebuilt layouts |
| --- | --- |
| Keep actual object sizes (default) | Retains each component's current visible width and height |
| Auto balance icon to name | Retains name size; sizes the icon from the ratios below |
| Use manual heights | Uses your icon/name heights in literal pixels |

Auto balance has two adjustable ratios. Horizontal is **icon height / name
height**, initially 1.5. Vertical is **icon width / name width**, initially 0.5.
These are starting values you can adjust, not a universal rule for logo design.
The icon-only file in paired auto mode uses the horizontal balance ratio.
Auto balance needs an icon and a name; single-component modes retain their
actual size unless you select manual heights.

Spacing when rebuilding defaults to the current shortest distance between the
two visible bounding rectangles. Diagonal gaps use the Euclidean distance;
overlapping/touching bounds give 0. Alternatively choose a manual pixel gap.
This is the gap applied to new horizontal/vertical layouts. **As designed keeps
all current offsets and spacing regardless of these controls.**

Square icon-only canvas adds empty space if needed; it does not distort the icon.
Disable it to use a tightly cropped rectangular icon canvas.

## Formats and color versions

| Option | Versions |
| --- | --- |
| Colors | Original colors, black, white |
| Vector formats | SVG, PDF, EPS |
| Raster formats | PNG, JPG |
| Default raster sizes | 512, 1024, 2048 pixels on the longest edge |

All formats/colors are enabled initially. Ready variants with four detected types produces **108 artwork files**.
Complete logo or single-component mode produces **27 artwork files** with default raster sizes. Paired mode with
all five layouts produces **135 files**. Disabling As designed in paired mode
retains the four-layout, 108-file kit from version 1.0. Uncheck unwanted formats,
colors or paired layouts.

Each layout/color combination has its own folder. The optional `preview.html`
is an offline gallery with links and SVG previews. `manifest.json` records source
IDs, measured source bounds, recognition decisions, sizing/spacing modes, outputs
and dimensions. Generated IDs for extracted parts belong only to the export copy.

- Convert exported text to paths is initially enabled. This preserves fonts and
  Arabic shaping on other devices. Disable it for editable SVG text; recipients
  need the same font. PDF/EPS text is outlined. Source text stays editable.
- Black/white exports preserve transparency through SVG masks. With **White
  details become cutouts**, pure white paint in a mixed-color component becomes
  a transparent detail. Entirely white components stay visible. Disable it if
  white should be foreground, such as white lettering in a mixed-color group.
- SVG/PNG/PDF can retain a transparent background. JPG/EPS always use a solid
  light background for Original/Black and the configured dark background for White.
- EPS may flatten masks, transparency and filters to raster content. PDF can
  rasterize filters. Embedded source images remain raster images; SVG export
  does not trace them.
- Groups, gradients, paths, text, local clones and raster images are supported.
  Local clones expand only in the exported copy. Local linked images are embedded.
  Embed missing images and unlink external-file clones before exporting.

Raster sizes accept 1–8 values from 16 to 8192. Each export is limited to 32
million pixels; source images to 20 million pixels / 64 MiB. Completed exports
are kept: repeat exports create Brand-logo-kit-2, -3, etc. An unfinished export
is removed on failure. Exporting does not edit the source document. Assignment
and Clear assignment actions only update role metadata. Clear all logo role
assignments removes object tags and icon/name references throughout the document;
optional layer/group names are retained.

## Installation and examples

Replace the existing Logo-Export-Pro files in the User extensions folder shown
in **Inkscape → Preferences → System**. Keep logo_export_pro.py and .inx together,
install only one copy, then restart Inkscape. Uses bundled Inkex, Pillow and the
native exporter; no web service or artwork upload.

The sample-logo.svg and sample-arabic-logo.svg examples have logo-icon and
logo-name IDs. Select both and use Complete logo, or assign those IDs in paired
mode. Their instructional captions are excluded when not selected.
ready-variants.svg demonstrates three finished designs selected together (IDs
ready-horizontal, ready-vertical and ready-icon). No role tags or layer names are
required for its automatic matching.
manual-lockup.svg demonstrates a grouped, deliberately arranged logo containing
an outlined name. Its group ID is finished-logo; its component IDs are
custom-icon and custom-name. They work without any text object.

## Verification

Run tests/run_tests.py with your Inkex path and --pattern test_logo_export_pro.py.
Supply --inkscape to enable actual SVG/PNG/PDF/JPG/EPS checks. The test environment
needs Inkex, Pillow, tinycss2, lxml and pypdf. Checks cover all formats, Arabic,
explicit roles, single components, current arrangements, transformed/scaled SVGs,
auto/manual sizing, visual matching of grouped and flat path artwork, RTL finished
layouts, duplicate removal, explicit type overrides, CSS/clone colors, cutouts,
linked images and failure cleanup.

References: [Inkscape command line](https://wiki.inkscape.org/wiki/Using_the_Command_Line),
[Inkex command API](https://inkscape.gitlab.io/extensions/documentation/source/inkex.command.html).

## الاستخدام السريع

لنسخ جاهزة مثل الأفقي والعمودي والأيقونة: اجعل كل نسخة مجموعة مستقلة، حدّدها
معاً واختر Ready variants. يتعرّف على الأيقونة المتكررة، ويأخذ النسخ كما رتّبتها،
ويصدّر الأيقونة والاسم كل واحد مرة واحدة. لا يلزم أن يكون الاسم Text.
إذا احتاج تصحيحاً: حدّد المجموعة وحدها، عيّن نوعها من Action، واضغط Apply.
بعدها حدّد النسخ معاً، وأعد Action إلى Export logo kit. لا تحتاج لتسمية الطبقات.
لشعار جاهز: رتّبه يدوياً، حدّد المجموعة، واختر Complete logo ثم Export logo kit.
يأخذ المقاسات والتباعد والمواقع الحالية عند كل تصدير؛ لا يسترجع نسقاً قديماً.
لشعار أيقونة واسم: حدّد الأيقونة وحدها واختر Assign selected object as icon واضغط
Apply، ثم عيّن الاسم بالطريقة نفسها. بعدها اختر Icon + name وExport logo kit.
الاسم يقبل المسارات والمجموعات والصور، ولا يلزم أن يكون Text.
Keep actual object sizes يحافظ على مقاسات العنصرين؛ Auto balance يحسب حجم الأيقونة
بنسبة قابلة للتعديل؛ Manual heights يتيح ضبط الأحجام بنفسك. As designed يحتفظ
بنسختك المرتبة يدوياً. الواجهة إنجليزية، ودعم العربي باقٍ.
