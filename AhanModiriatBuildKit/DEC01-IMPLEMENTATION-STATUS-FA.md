# وضعیت اجرایی DEC-01 و پذیرش ACC-48

**تاریخ بازبینی:** ۱۴۰۵/۰۸/۲۰ (2026-11-11)  
**مخزن:** mohammad82xxz-ops/AhanModiriat  
**شاخه:** fix/dec01-purchase-return-valuation-ci  
**PR:** [#43 — fix(accounting): implement approved DEC-01 purchase return valuation](https://github.com/mohammad82xxz-ops/AhanModiriat/pull/43)

## ۱. تصمیم مصوب

مالک کسب‌وکار در 2026-11-10، DEC-01 را با گزینه A و تکمیل تخصیص هزینه‌های جانبی تصویب کرده است:

- مرجوعی خرید بر مبنای بهای همان ردیف خرید اولیه به‌علاوه سهم متناسب هزینه‌های جانبی ارزش‌گذاری می‌شود.
- تخصیص در مرجوعی‌های چندمرحله‌ای تجمعی است؛ مبلغ هر مرحله اختلاف تخصیص تجمعی جدید و مبلغ تخصیص‌یافتهٔ قبلی است.
- پس از خروج مقدار و ارزش مرجوعی، میانگین موجودی باقی‌مانده از ارزش دفتری و مقدار باقی‌مانده مشتق می‌شود.
- وجه نقد دریافتی از فروشنده از ارزش مرجوعی مستقل است؛ فقط وجه واقعاً دریافت‌شده گردش نقدی ایجاد می‌کند.
- اگر ارزش برگشت از ارزش دفتری موجودی بیشتر شود، یا پس از صفرشدن مقدار ارزش باقی بماند، عملیات باید اتمیک رد شود.

مرجع رسمی وضعیت و متن تصمیم: [دفتر تصمیم‌های سیاست حسابداری](ACCOUNTING-POLICY-DECISION-REGISTER-FA.md).

## ۲. دامنهٔ پیاده‌سازی و آزمون

PR #43 پیاده‌سازی محدود DEC-01 و تست پذیرش آن را در بر می‌گیرد:

- تبدیل واحد خرید و تخصیص هزینهٔ جانبی؛
- مرجوعی‌های جزئی چندمرحله‌ای از یک ردیف خرید؛
- تطبیق جمع مبالغ مرجوعی با ارزش قابل برگشت کل؛
- کنترل باقیمانده‌های یک‌ریالی و جلوگیری از drift گردکردن؛
- بازمیانگین‌گیری پس از هر مرجوعی؛
- رد ارزش منفی و ارزش یتیم پس از صفرشدن موجودی؛
- تفکیک ارزش مرجوعی از وجه نقد واقعی؛
- کنترل ماندهٔ پرداختنی فروشنده، سلامت SQLite و foreign-key check.

سناریوی طلایی مرجع DEC-01، شناسهٔ INV-03 در ACCOUNTING-P0-GOLDEN-SCENARIOS-FA.md است. INV-04 یک مثال تشخیصی با فرض متفاوتِ برگشت از ارزش دفتری جاری است و نباید به‌عنوان expected policy برای DEC-01 یا تست پذیرش آن استفاده شود.

## ۳. شواهد CI

- اجرای [#933](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42972259971) روی commit کد/تست db491ae44689eafb07ceb6e7da5ab9a7abbec6a8 موفق شد؛ هر دو Job یعنی smoke-test و windows-onedir سبز بودند.
- اجرای [#939](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42973746661) روی SHA b1ecd09407935a7c621866e4e3329d085841e9a2 موفق شد؛ هر دو Job سبز بودند.
- اجرای [#940](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42974519044) روی head مستنداتی fdc4590fe4906527a958fca9dcc5c8a6c8489562 موفق شد؛ هر دو Job سبز بودند. Job اصلی Compile، تست‌های ایزوله، ماتریس UI، گردش‌های مالی/انبار، proxyهای صفحه‌کلید و zoom، Lighthouse/axe و بارگذاری گزارش‌ها را تکمیل کرد. Job ویندوز آزمون توکن بین‌پردازه‌ای، ساخت OneDir و بارگذاری Artifact را تکمیل کرد.
- Artifactهای اجرای #940:
  - [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42974519044/artifacts/13834309043)
  - [گزارش Lighthouse و axe](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42974519044/artifacts/13834613548)
  - [تصاویر UI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42974519044/artifacts/13834922925)

## ۴. مرز نتیجه

**ACC-48 فقط در محدودهٔ تصمیم DEC-01 و پیاده‌سازی/تست PR #43 بسته است.** این نتیجه به معنی تکمیل موتور عمومی ارزش‌گذاری، دفتر مستقل ارزش موجودی یا replay نیست.

موارد خارج از دامنه و باز:
- DEC-02 تا DEC-11؛
- ثبت اسناد تاریخ‌گذشته و replay طبق DEC-04؛
- اختلاف credit note با ارزش تاریخی خرید؛
- دفتر مستقل رویداد/ارزش‌گذاری و تطبیق کامل همهٔ گردش‌های موجودی؛
- سایر P0ها و پذیرش نهایی حسابداری.

## ۵. پذیرش دستی و ایمنی

- [ ] اجرای بستهٔ OneDir روی Windows واقعی و محیط تمیز؛
- [ ] بررسی صفحه‌خوان واقعی، صفحه‌کلید و بزرگ‌نمایی ۲۰۰٪؛
- [ ] بررسی نمایشگر کوچک؛
- [ ] اجرای سناریوهای خرید/مرجوعی و backup/restore فقط روی دیتابیس آزمایشی یا کپی؛
- [ ] ثبت نتیجه و بازبینی انسانی مالک.

موفقیت CI جایگزین این پذیرش دستی نیست. PR #43 باید Draft بماند تا پذیرش انسانی و بازبینی حسابداری تکمیل شود. هیچ merge به main یا شاخهٔ پایه و هیچ migration روی دیتابیس واقعی مجاز/انجام‌شده نیست.

## به‌روزرسانی اعتبارسنجی روی HEAD نهایی — 2026-11-11

- HEAD فعلی PR #43 برابر `42110775a855236f49999d4634b7a9ea0313192a` است.
- اجرای CI شمارهٔ **#941** با شناسهٔ `42975500965` دقیقاً روی همین SHA اجرا و با نتیجهٔ کلی `success` تکمیل شد: [مشاهده Run #941](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42975500965).
- هر دو Job روی همین HEAD موفق‌اند: `smoke-test` و `windows-onedir`.
- مقایسه با base فعلی PR یعنی `db8d78aff6cce0d6c323d4d13d41bf9ec310386e` نشان می‌دهد شاخهٔ PR تعداد ۴۹ commit جلوتر و صفر commit عقب‌تر است؛ تغییرات در همان PR stacked باقی مانده‌اند.
- PR #43 همچنان باز و Draft است؛ هیچ review submission یا review thread ثبت‌شده‌ای در زمان این بررسی مشاهده نشد.
- این CI، اعتبارسنجی خودکار آخرین HEAD را پوشش می‌دهد؛ پذیرش دستی Windows واقعی، صفحه‌خوان، بزرگ‌نمایی ۲۰۰٪، نمایشگر کوچک و backup/restore همچنان باز است.

## یادداشت نهایی دربارهٔ head مستنداتی — 2026-11-11

پس از اجرای موفق #941 روی commit کد/تست `42110775a855236f49999d4634b7a9ea0313192a`، فقط همین سند وضعیت به‌روزرسانی شد و commit مستنداتی جدید `1e4457c5c50f216911f6164f913e58f39fe79e7b` ایجاد گردید. این commit فقط Markdown را تغییر می‌دهد؛ هیچ فایل اجرایی یا تستی تغییر نکرده است. در زمان بررسی پس از این commit، برای SHA مستنداتی جدید اجرای CI مستقلی در فهرست اجراهای متصل به commit مشاهده نشد. بنابراین:
- آخرین CI موفق روی کد و تست‌های PR: Run #941 روی SHA `42110775a855236f49999d4634b7a9ea0313192a`.
- پس از ثبت SHA مستنداتی `1e4457c5c50f216911f6164f913e58f39fe79e7b`، همین یادداشت نیز در commit مستنداتی دیگری تکمیل شده است؛ هر دو تغییر صرفاً Markdown هستند و کد/تست را تغییر نداده‌اند.
- نباید Run #941 را به‌عنوان اجرای روی SHA مستنداتی جدید معرفی کرد؛ تغییرات کد/تست از آن زمان تغییری نکرده‌اند.

## نتیجهٔ نهایی CI شمارهٔ 944 — 2026-11-11

- SHA بررسی‌شده: `dd4b19ad6d100565a562fb736ed9f8dcfdae19b5`.
- اجرای [CI #944](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42979484557) با نتیجهٔ نهایی `success` تکمیل شد.
- Job لینوکس `smoke-test`: موفق؛ شامل Compile، مجموعهٔ تست‌های ایزوله، Browser UI، گردش‌های مالی/انبار، keyboard/zoom proxy و ممیزی Lighthouse/axe.
- Job ویندوز `windows-onedir`: موفق؛ تست توکن بین‌پردازه‌ای Windows، نصب PyInstaller، ساخت OneDir و بارگذاری Artifact.
- Artifactها:
  - [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42979484557/artifacts/13836882741)
  - [Lighthouse و axe-core](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42979484557/artifacts/13837246251)
  - [اسکرین‌شات‌های UI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42979484557/artifacts/13837430712)
- نتیجهٔ CI فقط به SHA فوق تعلق دارد. هر commit بعدی باید جداگانه بررسی شود؛ در صورت commit مستنداتی بعدی، شواهد #944 همچنان برای کد/تست این SHA معتبر است، نه SHA جدید.
- PR #43 همچنان Draft و باز است. موفقیت CI به معنی پذیرش انسانی یا مجوز Merge نیست.
- پذیرش دستی مالک روی Windows واقعی، صفحه‌خوان واقعی، zoom ۲۰۰٪، نمایشگر کوچک و backup/restore هنوز باز است.
- هیچ merge به `main` و هیچ migration روی دیتابیس واقعی انجام نشده است.

## اعتبارسنجی نهایی روی HEAD فعلی PR #43 — 2026-11-11

- SHA دقیق HEAD بررسی‌شده: `98820e6e485fd350fc4424b1c54657a33efd7d5a`.
- اجرای GitHub Actions شمارهٔ **#945** با شناسهٔ `42980113437` دقیقاً روی همین SHA با نتیجهٔ کلی `success` تکمیل شد: [مشاهدهٔ Run #945](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42980113437).
- هر دو Job موفق‌اند: `smoke-test` و `windows-onedir`.
- Job اصلی شامل Compile، تست‌های ایزوله، Browser UI، گردش‌های مالی/انبار، proxyهای keyboard/zoom، ممیزی Lighthouse/axe-core و بارگذاری گزارش‌ها و تصاویر بود.
- Job ویندوز شامل characterization توکن بین‌پردازه‌ای، نصب PyInstaller، ساخت Windows OneDir و بارگذاری Artifact بود.
- Artifactهای Run #945:
  - [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42980113437/artifacts/13837516752)
  - [گزارش Lighthouse و axe-core](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42980113437/artifacts/13836709130)
  - [اسکرین‌شات‌های UI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42980113437/artifacts/13836749119)
- Run #945 شواهد CI برای SHA بالا است؛ این اجرا به commit مستنداتی بعدی (در صورت ایجاد) منتسب نیست، هرچند محتوای کد و تست‌ها در آن commit تغییر نکرده باشد.
- در زمان این بازبینی، PR #43 باز، Draft و ادغام‌نشده است؛ PR #41 نیز باز و Draft است و شاخهٔ پایهٔ PR #43 محسوب می‌شود. هیچ review submission یا inline review thread برای PR #43 ثبت نشده بود.
- پذیرش انسانی Windows واقعی، صفحه‌خوان واقعی، keyboard-only، zoom ۲۰۰٪، نمایشگر کوچک و backup/restore روی دیتابیس آزمایشی همچنان باز است. موفقیت CI جایگزین این مراحل نیست.
- هیچ merge به `main` یا شاخهٔ پایه و هیچ migration روی دیتابیس واقعی انجام نشده است.

## اعتبارسنجی CI روی HEAD بعدی PR #43 — 2026-11-11

- SHA دقیق کد/تست: `b818a427b44e004f988b47720f9f8080ed49c890`.
- اجرای GitHub Actions [Run #946](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42989789168) روی همین SHA با نتیجهٔ نهایی `success` تکمیل شد.
- هر دو Job موفق‌اند: `smoke-test` و `windows-onedir`.
- Job اصلی Compile، تست‌های ایزوله، ماتریس UI مرورگر، گردش‌های مالی/انبار، proxyهای keyboard/zoom، ممیزی Lighthouse/axe-core و بارگذاری گزارش‌ها و تصاویر را با موفقیت تکمیل کرد.
- Job ویندوز آزمون cross-process token، ساخت Windows OneDir و بارگذاری Artifact را با موفقیت تکمیل کرد.
- Artifactهای همین اجرا:
  - [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42989789168/artifacts/13840604549)
  - [Lighthouse و axe-core](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42989789168/artifacts/13841442932)
  - [اسکرین‌شات‌های UI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42989789168/artifacts/13841866014)
- هر سه Artifact هنگام ثبت این یادداشت موجود و منقضی‌نشده‌اند.
- این نتیجه فقط به SHA بالا تعلق دارد. هر commit بعدی، حتی اگر مستنداتی باشد، SHA جداگانه دارد و نباید Run #946 به‌عنوان اجرای همان SHA جدید معرفی شود.
- PR #43 همچنان Draft و stacked روی PR #41 است. پذیرش دستی Windows واقعی، صفحه‌خوان واقعی، keyboard-only، zoom ۲۰۰٪، نمایشگر کوچک و backup/restore روی دیتابیس آزمایشی باز است.
- هیچ merge به `main` یا شاخهٔ پایه و هیچ migration روی دیتابیس واقعی انجام نشده است.

## محدودیت دقت ارزش کل در مرجوعی‌های چندمرحله‌ای — کشف و characterization در 2026-11-11

**وضعیت: یافتهٔ باز؛ DEC-01 به‌تنهایی این شکاف معماری را نمی‌بندد.**

در مسیر فعلی `add_purchase_return`، ارزش قبلی موجودی از `stock × avg_cost` بازسازی می‌شود. چون `avg_cost` به ریال صحیح گرد می‌شود، باقیماندهٔ ارزش کل پس از تقسیم بر مقدار در cache میانگین از دست می‌رود. مرجوعی بعدی این مقدار گرد‌شده را دوباره در تعداد ضرب می‌کند و می‌تواند ارزش دفتری را منحرف کند.

### سناریوی بازتولید مستقل

- موجودی افتتاحی fixture: ۳ واحد با بهای میانگین ۲ ریال؛ ارزش کل مستقل مورد انتظار ۶ ریال.
- خرید مرجع برای مرجوعی: ۲ واحد × ۱ ریال؛ یک واحد قدیمی دیگر در موجودی باقی است.
- مرجوعی اول: ۱ واحد با ارزش تاریخی ۱ ریال؛ ارزش دقیق باقی‌مانده ۵ ریال روی ۲ واحد است، اما `avg_cost` به ۳ ریال گرد می‌شود.
- مرجوعی دوم: ۱ واحد با ارزش تاریخی ۱ ریال؛ کد فعلی ارزش قبلی را از `2 × 3 = 6` بازسازی می‌کند و ارزش باقی‌مانده را ۵ ریال می‌سازد.
- expected مستقل از رویدادها: `6 - 1 - 1 = 4` ریال؛ مقدار بازسازی‌شده از cache فعلی: `1 × 5 = 5` ریال. اختلاف: ۱ ریال.

### اقدام ثبت‌شده

- تست characterization به `test_phase2_purchase_return_cost_characterization.py` اضافه شد. تست به‌صراحت رفتار فعلی و اختلاف یک‌ریالی را ثبت می‌کند؛ این تست، ادعای صحت دفتر ارزش‌گذاری نیست و نباید به‌عنوان پذیرش این invariant تفسیر شود.
- اصلاح production انجام نشد؛ زیرا راه‌حل صحیح به نگهداری ارزش کل integer-rial مستقل یا ledger قابل بازسازی وابسته است و طبق نقشهٔ P0، بخشی از Gate B/T09 است. نباید با تغییر محلی `avg_cost` یا گردکردن متفاوت، خطای انباشته را پنهان کرد.
- DEC-01 در محدودهٔ روش ارزش‌گذاری مرجوعی (بهای خرید اولیه + هزینهٔ جانبی تخصیص‌یافته) همچنان مصوب و پیاده‌سازی‌شده است؛ اما ادعای حفظ دقیق ارزش کل موجودی پس از هر تعداد مرجوعی، خارج از پذیرش محدود ACC-48 و همچنان باز می‌ماند.
- پیش‌نیاز رفع: تصمیم/قرارداد مدل ارزش‌گذاری P0-A و اجرای موتور ارزش‌گذاری P0-B/T09؛ تعریف مقدار پایه و `total_value_rial` به‌عنوان منبع حقیقت، `avg_cost` صرفاً projection مشتق‌شده، سپس تست golden و integration. هر migration فقط روی fixture و کپی دیتابیس؛ بدون migration واقعی.
- تا زمان تکمیل Gate B، PR #43 باید Draft بماند و هیچ merge یا ادعای پذیرش کامل ارزش‌گذاری مجاز نیست.
