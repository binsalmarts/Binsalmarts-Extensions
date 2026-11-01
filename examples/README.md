# أمثلة الإضافات · Editable SVG examples

افتح ملف SVG في Inkscape 1.4+. يمكنك تعديل النتائج مباشرة أو تجربة الإضافة على ملف المصدر. استخدم لوحة Layers and Objects لتحديد العناصر، وأداة الصفحات في المستندات متعددة الصفحات. الخطوط المستخدمة في النصوص تعتمد على جهازك.

| الإضافة | ملف البداية | النتيجة أو أمثلة إضافية | طريقة التجربة |
| --- | --- | --- | --- |
| ASCII Art Pro | [input.svg](input.svg) | [ملون](color.svg)، [أحادي اللون](monochrome.svg)، [حواف](edges.svg)، [عربي](arabic.svg)، [تراكب](overlay.svg) | حدد الصورة ثم افتح ASCII Art Pro |
| Page Numbering Pro | [input.svg](page_numbering/input.svg) | [ترقيم](page_numbering/numbered.svg)، [عربي بأصفار](page_numbering/arabic_leading_zeros.svg)، [قالب](page_numbering/template_numbered.svg) | افتح الإضافة واختر موضع الرقم |
| Modern Grid | [شبكة أعمدة](modern_grid/column.svg) | [صفوف](modern_grid/row.svg)، [وحدات](modern_grid/grid.svg)، [Bento](modern_grid/bento.svg) | افتح الإضافة واختر نوع الشبكة؛ إعادة التشغيل تستبدل النوع نفسه |
| Artboard Maker Pro | [صفحات موحدة](artboard_maker/uniform.svg) | [صفحات بمقاسات مختلفة](artboard_maker/mixed.svg) | استخدم أداة الصفحات للتنقل، أو افتح الإضافة لإنشاء تخطيط جديد |
| Logo Export Pro | [named-templates.svg](logo_export/named-templates.svg) | [تصميم يدوي](logo_export/manual-lockup.svg)، [نسخ جاهزة](logo_export/ready-variants.svg) | جرّب وضع Named templates وحدد مجلد تصدير محليًا |
| Logo Construction | [مصدر الشعار](logo_construction/source-logo.svg) | [مخطط البناء](logo_construction/construction-demo.svg) | حدد الشعار ثم افتح Logo Construction |
| Blend Tool Pro | [blend-source.svg](blend_tool/blend-source.svg) | [خط مستقيم](blend_tool/blend-straight.svg)، [منحنى](blend_tool/blend-curved.svg)، [3D](blend_tool/blend-3d-demo.svg) | حدد الشكلين الملونين؛ للمنحنى استخدم Spine ID: `guide` |
| Vector Effects Pro | [effects-source.svg](vector_effects/effects-source.svg) | [معرض](vector_effects/effects-gallery.svg)، [Grain](vector_effects/grain-gallery.svg)، [Noise](vector_effects/noise-gallery.svg)، [تركيب](vector_effects/effects-combined.svg) | حدد شكلًا ثم اختر المؤثر أو Grain أو Noise |
| Color Guide Pro | [مصدر الألوان](color_guide/source.svg) | [الدليل الإنجليزي](color_guide/brand-guide-en-pages.svg)، [تكوينات عربية](color_guide/combinations-ar-pages.svg)، [شكل مخصص](color_guide/custom-symbol-ar-pages.svg)، [بطاقات](color_guide/cards-ar-pages.svg)، [تدرجات](color_guide/gradients-en-pages.svg) | حدد مجموعة brand-colors، وافتح Color Guide Pro واختر الصفحات المطلوبة |

الثيم له [ملف صفحة جاهز](../studio_dark/examples/Studio-Dark.svg) و[صورة واجهة](../studio_dark/qa/preview-controls-v23.png). يتوفر أيضًا [فيديو عربي لـLogo Export](../tutorials/logo-export-pro/README.md).

## إعادة توليد الأمثلة

توجد الأدوات في `tools/make_examples.py` و`make_page_numbering_examples.py` و`make_grid_examples.py` و`make_artboard_examples.py` و`make_named_logo_examples.py` و`make_logo_construction_example.py` و`make_blend_examples.py` و`make_vector_effects_examples.py`. مرّر `--inkex-dir` لمسار Inkex المرفق مع تثبيت Inkscape.

The release contains the same editable SVG examples. Raster thumbnails are previews; SVG files are the editable sources and results.
