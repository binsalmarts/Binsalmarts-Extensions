# التثبيت · Installation

تتطلب الإضافات **Inkscape 1.4 أو أحدث** وبيئة Python/Inkex المرفقة به. تستخدم ASCII Art وLogo Export مكتبة Pillow؛ تكون موجودة في حزم Inkscape المعتادة، ويمكن تثبيت `python3-pil` في توزيعات Linux التي تستخدم Python النظام.

## تثبيت جميع الإضافات

1. نزّل `Binsalmarts-Extensions-1.1.0.zip` من [آخر إصدار](https://github.com/binsalmarts/Binsalmarts-Extensions/releases/latest).
2. فك الضغط. افتح **Preferences → System → User extensions** في Inkscape، وانسخ المسار الذي يعرضه البرنامج.
3. انسخ المجلدات التسعة، من `ASCII-Art-Pro` إلى `Color-Guide-Pro`، إلى ذلك المسار. أبقِ ملفات `.py` و`.inx` معًا داخل كل مجلد. لا تنسخ المجلد الخارجي للحزمة إلى مسار الإضافات.
4. عند التحديث، استبدل الملفات في مجلد الإضافة المثبتة نفسه، وتجنب وجود نسختين بمعرّف الإضافة نفسه.
5. أعد تشغيل Inkscape. افتح **Extensions → Binsalmarts Extensions >**.

يمكن أيضًا تنزيل ZIP منفصل لأي إضافة وتثبيت مجلدها بالطريقة نفسها. مجلدات الأمثلة اختيارية، ولا تحتاج إلى تثبيت أدوات التطوير أو الاختبارات.

## Studio Dark Compact

الثيم حزمة مستقلة، ومثبّته مخصص لـmacOS. نزّل `Studio-Dark-Compact-2.3.zip`، وفك الضغط، وأغلق Inkscape، ثم شغّل `install-macos.command`. راجع [التعليمات الكاملة وطريقة الاستعادة](../studio_dark/README_AR.md). لا تنسخ الثيم إلى مجلد User extensions.

## تجربة الأمثلة

افتح ملف SVG من [دليل الأمثلة](../examples/README.md). ملفات المصدر مهيأة للتجربة، وملفات النتائج قابلة للتحرير. بعض الأمثلة متعددة الصفحات؛ استخدم أداة الصفحات لرؤية الصفحات الأخرى. تعتمد النصوص القابلة للتحرير على الخطوط المثبتة في جهازك.

## إذا لم تظهر الإضافة

- تحقق من المسار في **System → User extensions**؛ قد يختلف بين التثبيت العادي وFlatpak وAppImage.
- تأكد من بقاء ملفات `.inx` والبرنامج المشار إليه معًا، ومن عدم وجود نسخة قديمة أخرى.
- أعد تشغيل Inkscape بالكامل.
- عند ظهور خطأ Python، أرفق نصه وإصدار Inkscape ونظامك في [بلاغ مشكلة](https://github.com/binsalmarts/Binsalmarts-Extensions/issues/new/choose).

## English quick start

Download the complete extension ZIP from Releases, extract it, and copy the **nine individual extension folders** into the User extensions directory displayed in Inkscape Preferences → System. Restart Inkscape and open Extensions → Binsalmarts Extensions >. Each `.inx` must stay beside its Python script. Install one copy of each extension. The Studio Dark theme has a separate macOS installer.
