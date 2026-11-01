# Binsalmarts Extensions 1.1.0

٩ إضافات لإنكسكيب، مع Color Guide Pro الجديدة لإنشاء أدلة ألوان هوية عربية وإنجليزية بأقسام اختيارية. Color Info Card الحالية تبقى مستقلة دون تغيير.

## التنزيل والتثبيت

- **Binsalmarts-Extensions-1.1.0.zip**: الإضافات التسع مع أمثلتها. انسخ مجلدات الإضافات إلى مسار **Preferences → System → User extensions** ثم أعد تشغيل Inkscape.
- **حزم الإضافات المنفردة**: لتثبيت إضافة واحدة فقط.
- **Binsalmarts-Examples-1.1.0.zip**: أمثلة SVG للتجربة.
- **Studio-Dark-Compact-2.3.zip**: ثيم مستقل بمثبّت macOS؛ أغلق Inkscape قبل تشغيله.
- **SHA256SUMS**: بصمات جميع حزم التنزيل.

## Included components

| Extension | Version |
| --- | --- |
| ASCII Art Pro | 1.2.0 |
| Page Numbering Pro | 1.2.0 |
| Modern Grid | 4.4.0 |
| Artboard Maker Pro | 1.0.0 |
| Logo Export Pro | 2.0.0 |
| Logo Construction | 1.0.0 |
| Blend Tool Pro | 1.1.0 |
| Vector Effects Pro | 1.2.0 |
| Color Guide Pro | 1.0.0 |
| Studio Dark Compact (separate theme) | 2.3 |

Requires Inkscape 1.4+ with its bundled Python/Inkex. ASCII Art and Logo Export also use Pillow. Editable text uses fonts installed on your system. Development validation was performed on macOS with Inkscape 1.4.4; Linux renderer checks also run in GitHub Actions. Windows has not been verified.

All extension source is MIT licensed. The theme includes its upstream MIT license and third-party notices.

Color Guide Pro includes cover, palette, tones, text contrast, combinations and gradient sections; documented offline names; saved source refresh; custom vector symbols; and SVG/PDF/PNG/GPL/JSON/CSV exports. Each section can be enabled independently. CMYK is an unprofiled approximation; automatic nearest names are labeled.
