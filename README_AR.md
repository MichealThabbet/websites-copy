# أداة تنزيل الموارد العامة

المستودع: https://github.com/MichealThabbet/websites-copy

## التشغيل

يتطلب Python 3.12. من مجلد المستودع:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python downloader.py 'https://www.stmark-kw.net/category.aspx?catid=18' --mode page
```

الأوضاع: `page` لروابط الملفات والصور والصوت والفيديو والصفحات المرتبطة، `file` لملف مباشر، و`iiif` لأجسام صور IIIF ذات الروابط المباشرة. لا ينفذ JavaScript ولا يعيد بناء الموقع للعمل دون اتصال.

## GitHub Actions

بعد رفع التغييرات ودمج ملف workflow في الفرع الافتراضي، افتح:
https://github.com/MichealThabbet/websites-copy/actions

اختر **Heritage Downloader → Run workflow**. الرابط المذكور هو القيمة الافتراضية؛ اختر `page`. بعد انتهاء التشغيل نزّل **heritage-downloads** من Artifacts. تُحفظ النتائج 7 أيام، ولا تُضاف إلى Git. قد يحتوي artifact لتشغيل فاشل على نتائج جزئية وسجل الأخطاء.

## الحدود والحقوق

افتراضيًا: 40 محاولة تنزيل، 20 صفحة، 50 MiB لكل ملف، 8 MiB لبيانات الصفحة/IIIF، عمق واحد، طلب واحد في كل مرة وفاصل ثانيتين على الأقل مع احترام Crawl-delay. حد تشغيل Actions هو 30 دقيقة. الخيارات المحلية: `--max-files` و`--max-pages` و`--max-mb` و`--depth`.

يُفحص robots.txt عبر جلسة HTTP نفسها مع التحقق من TLS ومهلة وحجم محدودين. غياب robots برمز 404 يسمح بالمتابعة؛ المنع أو تعذر التحقق أو تحويل robots يوقف الطلبات لهذا الأصل. لا توجد إعادة محاولات تلقائية للحظر أو تحديد المعدل. لا تستخدم روابط تحمل بيانات دخول أو أسرارًا؛ الروابط تُسجل في manifest.json. راجع حقوق الموارد وشروط الموقع؛ سماح robots لا يمنح حقوق إعادة النشر.

manifest.json يسجل المصدر والحجم وSHA-256 أو الخطأ. أي خطأ، أو عدم العثور على ملفات، يجعل أمر CLI يفشل بدل إعلان نجاح وهمي.

## التحقق الفعلي

نجحت 9 اختبارات محلية تشمل HTTP فعليًا على خادم اختبار: تنزيل الصفحة والملفات، البصمات، صور IIIF النسبية، المنع بعد تحويل، خطأ 404، حد الحجم وتنظيف الملفات الجزئية، حد العدد والتكرار، رفض بيانات الدخول في الرابط، وفشل CLI. نجح pip check.

تمت مراجعة بيانات requests وbeautifulsoup4 من PyPI وتثبيت الإصدارات المختبرة والاعتماديات الانتقالية في requirements.lock. مراجع Actions مثبتة ببصمات commit من وسوم المستودعات الرسمية.

بعد تحديث الشبكة وصل طلب robots.txt إلى الموقع وأعاد HTTP 302 إلى ~/Error.aspx. توقفت الأداة برسالة robots unavailable or denied: 302؛ لم تُنزّل موارد الموقع لأن السماح لم يُتحقق منه. لم يُشغَّل GitHub Actions بعد. روابط sources.json بذور بحث غير متحقق منها.
