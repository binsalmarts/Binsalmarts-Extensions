# Binsalmarts Extensions 1.2.0

٩ إضافات لإنكسكيب. يضيف هذا الإصدار خيار **Without artboard names** في **Artboard Maker Pro → Document** لإنشاء صفحات بدون أسماء مخصصة أو إزالة أسماء آخر شبكة مولّدة عند تحديثها، مع الاحتفاظ بمعرّفات الصفحات وأسماء الصفحات الأخرى. تبقى التسمية المعتادة مفعّلة افتراضيًا، ويمكن إعادتها بإلغاء الخيار. قد يعرض Inkscape أرقام الصفحات الافتراضية للصفحات بدون أسماء.

## التنزيل والتثبيت

- **Binsalmarts-Extensions-1.2.0.zip**: الإضافات التسع مع أمثلتها. انسخ مجلدات الإضافات إلى مسار **Preferences → System → User extensions** ثم أعد تشغيل Inkscape.
- **Artboard-Maker-Pro-1.1.0.zip**: إضافة الآرت بورد المحدّثة فقط. بقية الإضافات متاحة أيضًا كحزم منفردة.
- **Binsalmarts-Examples-1.2.0.zip**: أمثلة SVG للتجربة.
- **Studio-Dark-Compact-2.3.zip**: ثيم مستقل بمثبّت macOS؛ أغلق Inkscape قبل تشغيله.
- **SHA256SUMS**: بصمات جميع حزم التنزيل.

## Included components

| Extension | Version |
| --- | --- |
| ASCII Art Pro | 1.2.0 |
| Page Numbering Pro | 1.2.0 |
| Modern Grid | 4.4.0 |
| Artboard Maker Pro | 1.1.0 |
| Logo Export Pro | 2.0.0 |
| Logo Construction | 1.0.0 |
| Blend Tool Pro | 1.1.0 |
| Vector Effects Pro | 1.2.0 |
| Color Guide Pro | 1.0.1 |
| Studio Dark Compact (separate theme) | 2.3 |

Requires Inkscape 1.4+ with its bundled Python/Inkex. ASCII Art and Logo Export also use Pillow. Editable text uses fonts installed on your system. Development validation was performed on macOS with Inkscape 1.4.4; Linux renderer checks also run in GitHub Actions. Windows has not been verified.

All extension source is MIT licensed. The theme includes its upstream MIT license and third-party notices.

Color Guide Pro includes cover, palette, tones, text contrast, combinations and gradient sections; documented offline names; saved source refresh; custom vector symbols; and SVG/PDF/PNG/GPL/JSON/CSV exports. Each section can be enabled independently. CMYK is an unprofiled approximation; automatic nearest names are labeled.

Color Guide Pro 1.0.1 keeps all original source references when refreshing with a source element selected.

Artboard Maker Pro 1.1.0 adds **Without artboard names** in **Document**. The prefix is ignored when enabled. Updating removes names only from the generated grid being updated and keeps page IDs stable; disabling the option names the grid again. Validation covers all page actions, empty prefixes, name removal/restoration and real Inkscape exports.
