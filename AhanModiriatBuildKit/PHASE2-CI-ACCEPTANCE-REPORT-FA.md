# گزارش پذیرش CI فاز ۲ — ۳ نوامبر ۲۰۲۶

## دامنه و شناسه اجرا

- مخزن: `mohammad82xxz-ops/AhanModiriat`
- شاخه: `design/phase2-quantity-date-contract`
- PR: [شماره ۱۰](https://github.com/mohammad82xxz-ops/AhanModiriat/pull/10) — باز، Draft و ادغام‌نشده
- اجرای مبنا: [GitHub Actions Run #715](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41705150028)
- SHA آزموده‌شده: `69950025ae6e826ff6518763bee536bb7d44eed1`
- نتیجهٔ Run #715: هر دو Job با conclusion=success.

این گزارش فقط شواهد اجرای CI روی SHA بالا را ثبت می‌کند. اگر این سند در commit بعدی تغییر کند، Run #715 همچنان شواهد commit قبلی است و باید CI مربوط به SHA جدید جداگانه بررسی شود.

## نتایج آزمون

| حوزه | نتیجه |
|---|---|
| Compile | موفق |
| Isolated smoke tests | موفق |
| Browser UI matrix و screenshots | موفق |
| گردش‌کارهای مالی و انبار در مرورگر | موفق |
| Keyboard و zoom proxies | موفق |
| Lighthouse و axe-core | موفق |
| ساخت Windows OneDir | موفق |

سناریوی end-to-end مرورگر شامل ایجاد محصول، خرید، فروش، هزینه، تعدیل/انبارگردانی و تطبیق مبلغ فروش پس از تبدیل واحد بود. خروجی workflow آن را موفق اعلام کرد.

آزمون‌های keyboard/zoom proxy روی ۷ مسیر اجرا شدند. اینها آزمون خودکار شبیه‌سازی‌شده‌اند و معادل بررسی انسانی صفحه‌کلید، screen reader یا نمایشگر واقعی نیستند.

## Lighthouse

۱۰ گزارش برای ۵ مسیر در دو حالت mobile و desktop تولید شد:

- مسیرها: `/`, `/sales`, `/purchases`, `/reports`, `/settings`
- Performance: 100 در هر ۱۰ گزارش
- Accessibility: 100 در هر ۱۰ گزارش
- Best Practices: 100 در هر ۱۰ گزارش
- SEO: 82 در هر ۱۰ گزارش

دو مورد مؤثر بر امتیاز SEO عبارت‌اند از نبود meta description و نامعتبر بودن پاسخ `robots.txt` در محیط آزمون محلی. برای نرم‌افزار حسابداری محلی/داخلی، SEO در حال حاضر معیار پذیرش عملیاتی نیست؛ بنابراین این دو مورد بدون نیاز محصولی به تغییر کد تبدیل نشدند.

## axe-core

- ۱۷ مسیر بررسی شد.
- تعداد violation در تمام مسیرها: صفر.
- در دادهٔ خلاصهٔ خام، برای مسیرهای `/loans`, `/prices`, `/parties`, `/returns` هرکدام ۲ مورد incomplete ثبت شده است.
- خروجی summary فقط تعداد incomplete را ثبت می‌کند؛ جزئیات موردی برای نتیجه‌گیری دربارهٔ علت یا تأیید دستی کافی نیست.
- صفر violation به‌معنای اثبات دسترس‌پذیری کامل نیست و بررسی انسانی همچنان لازم است.

## Artifactهای بارگذاری‌شده

هر سه artifact زیر در Run #715 بارگذاری و از GitHub دریافت شدند. زمان نگهداری اعلام‌شده در تنظیم workflow برابر ۱۴ روز است:

1. [گزارش Lighthouse و axe-core](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41705150028/artifacts/13265418594) — شامل ۱۰ گزارش Lighthouse، خلاصهٔ امتیازها، خروجی axe و audit summary.
2. [تصاویر UI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41705150028/artifacts/13265453507) — شامل ۶۸ فایل screenshot در ابعاد و حالت‌های مختلف.
3. [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41705150028/artifacts/13264889580) — شامل executable و پوشهٔ وابستگی‌های بسته‌بندی‌شده.

ساخت موفق OneDir فقط موفقیت فرایند build را ثابت می‌کند؛ اجرای واقعی روی Windows پاک و صحت رفتار برنامه روی دستگاه مالک را ثابت نمی‌کند.

## هشدارها و موارد خارج از دامنه

- در log سرور چند `BrokenPipeError` هنگام بسته‌شدن اتصال سمت مرورگر دیده شد؛ سناریوهای browser و job نهایی موفق ماندند. علت دقیق این پیام‌ها در این گزارش ریشه‌یابی نشده است.
- هشدارهای deprecation مربوط به Node.js 20 و برخی APIهای Node/npm در log دیده شدند؛ این هشدارها موجب شکست job نشدند.
- هیچ دیتابیس واقعی در CI استفاده نشده است. تست‌های B0/B1 با fixture مصنوعی هستند.
- هیچ migration یا تغییر schema کسب‌وکار اجرا نشده است.
- DEC-01 تا DEC-11 و پیشنهادهای DEC-12 تا DEC-16 تصویب نشده‌اند.

## چک‌لیست باقی‌ماندهٔ مالک محیط

موارد زیر را CI نمی‌تواند جایگزین کند و باید در محیط واقعی Windows بررسی شوند:

- [ ] نصب پاک روی Windows پشتیبانی‌شده
- [ ] اجرای واقعی برنامه و گردش‌کارهای اصلی
- [ ] اجرای بستهٔ OneDir روی سیستم پاک
- [ ] بزرگ‌نمایی واقعی ۲۰۰٪
- [ ] کاربری فقط با صفحه‌کلید
- [ ] بررسی با screen reader
- [ ] نمایشگر کوچک و تغییر اندازهٔ پنجره
- [ ] بررسی backup/restore فقط با کپی آزمایشی و بدون دست‌کاری دادهٔ اصلی

## جمع‌بندی

Run #715 روی SHA ثبت‌شده کاملاً موفق است و artifactهای لازم تولید شده‌اند. این نتیجه، آمادگی شواهد CI برای این snapshot را نشان می‌دهد؛ نه تکمیل کل فاز دوم، نه تصویب سیاست حسابداری، نه تأیید دادهٔ واقعی و نه تأیید نهایی اجرای Windows. PR باید Draft و main دست‌نخورده باقی بماند تا گیت‌های باز و بررسی‌های مالک تکمیل شوند.


## اجرای تکمیلی Run #719 — CSV characterization و رفع باگ

- Run: [#719](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41708106130)
- SHA آزموده‌شده: `5ea31da29c2d9084c3b0b6fd59bbe1e1244a5490`
- نتیجه: هر دو Job یعنی `smoke-test` و `windows-onedir` با موفقیت کامل شدند.
- در اولین اجرای تست تازهٔ CSV، Run [#718](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41707978421) شکست واقعی را آشکار کرد: query خروجی CSV به‌دلیل ستون مبهم `notes` در JOIN جدول‌های فروش و کالا، `sqlite3.OperationalError` می‌داد. در commit `5ea31da` فقط ارجاع ستون‌های هزینه و یادداشت فروش به جدول `sales` مقید شد؛ فرمول مالی یا منطق موجودی تغییر نکرد.
- `test_phase2_csv_export_characterization.py` پس از اصلاح، در Isolated Smoke Tests موفق شد. این تست HTTP واقعی برنامه را با fixture مصنوعی اجرا می‌کند و BOM، header شش‌ستونی، ردیف‌های فروش کالا/خدمت/پرداخت، نبود ردیف خرید و نبود ستون مقدار/واحد را بررسی می‌کند.
- Browser UI matrix، finance/inventory workflows و keyboard/zoom proxies همگی موفق شدند.
- Lighthouse: در ۱۰ گزارش، Accessibility=100 و Best Practices=100 در همهٔ مسیرها؛ Performance=99 فقط برای mobile در `/purchases` و 100 برای ۹ گزارش دیگر؛ SEO=82 در همهٔ ۱۰ گزارش.
- axe-core: ۱۷ مسیر، صفر violation در همهٔ سطوح؛ incomplete=2 برای هر یک از `/loans`، `/prices`، `/parties` و `/returns` و صفر برای ۱۳ مسیر دیگر. این موارد incomplete جایگزین بررسی انسانی نیستند.
- Artifactهای Run #719 دریافت و فهرست فایل‌هایشان بررسی شدند:
  - [UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41708106130/artifacts/13267906093) — ۶۸ تصویر.
  - [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41708106130/artifacts/13266221786) — شامل `AhanModiriat.exe` و پوشهٔ `_internal`.
  - [Lighthouse/axe reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41708106130/artifacts/13266156651) — ۱۰ گزارش Lighthouse، `axe-results.json` و خلاصهٔ audit.
- هر سه artifact تا ۱۷ نوامبر ۲۰۲۶ در دسترس‌اند. Build موفق Windows OneDir معادل اجرای دستی روی Windows پاک نیست.

Run #719 روی SHA کد `5ea31da` تأیید CI را می‌دهد؛ Run #720 نیز commit مستندات `dae5534` را جداگانه تأیید کرده است. شواهد هر اجرا فقط به SHA همان اجرا محدود است.


## اجرای تکمیلی Run #721 — characterization خروجی XLSX

- Run: [#721](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41792827717)
- SHA آزموده‌شده: `ae054aac4ce82eb93ef0944a822ae80d3122a9be`
- نتیجه: هر دو Job یعنی `smoke-test` و `windows-onedir` با موفقیت کامل شدند.
- تست تازهٔ `test_phase2_xlsx_export_characterization.py` در Compile و Isolated Smoke Tests اجرا شد و endpoint واقعی `/export.xlsx` را با fixture مصنوعی بررسی کرد: هر ۱۵ ستون محصول، هر ۴ ستون شخص، تبدیل نمایشی مبالغ ریالی به تومان، نام/ترتیب دو برگهٔ `Products` و `People` و نبود برگه‌های گردش خرید/فروش/مرجوعی/انبار.
- هیچ کد production یا schema کسب‌وکار در این commit تغییر نکرد؛ فقط تست characterization، workflow CI و مستندات ممیزی/برنامهٔ تست به‌روز شدند.
- Lighthouse در ۱۰ گزارش: Accessibility=100 و Best Practices=100 در همهٔ مسیرها؛ Performance=99 در mobile برای `/sales` و `/purchases` و 100 در ۸ گزارش دیگر؛ SEO=82 در هر ۱۰ گزارش.
- axe-core در ۱۷ مسیر صفر violation داشت؛ incomplete=2 در `/loans`، `/prices`، `/parties` و `/returns` و صفر در ۱۳ مسیر دیگر. این موارد incomplete نیازمند بررسی انسانی‌اند و صفر violation به‌تنهایی اثبات دسترس‌پذیری کامل نیست.
- Artifactهای Run #721 دریافت و بررسی شدند:
  - [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41792827717/artifacts/13304442202) — ZIP سالم، ۷۰ فایل شامل `AhanModiriat.exe` و ۶۹ فایل در `_internal`.
  - [UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41792827717/artifacts/13304412303) — ZIP سالم، ۶۸ تصویر.
  - [Lighthouse/axe reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41792827717/artifacts/13304412297) — ZIP سالم، ۱۳ فایل شامل ۱۰ گزارش Lighthouse، `axe-results.json` و `audit-summary.md`.
- Build موفق OneDir و artifact سالم، معادل اجرای دستی روی Windows پاک یا تأیید محیط واقعی مالک نیست.

این گزارش در commit بعدی ثبت می‌شود؛ CI همان commit مستندات باید جداگانه بررسی شود. نتیجهٔ Run #721 به SHA `ae054aac` محدود است.


## تأیید commit مستندات — Run #722

- Run: [#722](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41793603385)
- SHA آزموده‌شده: `b63d6cb6ccf6a6caca57681cb7cb438e2b0c93e1`
- نتیجه: هر دو Job یعنی `smoke-test` و `windows-onedir` موفق شدند.
- Compile، تمام isolated smoke tests، browser UI matrix، finance/inventory workflows، keyboard/zoom proxies و Lighthouse/axe-core موفق شدند.
- Lighthouse در ۱۰ گزارش: Accessibility=100 و Best Practices=100؛ Performance=99 فقط برای mobile در `/purchases` و 100 در ۹ گزارش دیگر؛ SEO=82 در همهٔ گزارش‌ها.
- axe-core در ۱۷ مسیر صفر violation داشت؛ incomplete=2 در `/loans`، `/prices`، `/parties` و `/returns` و صفر در ۱۳ مسیر دیگر.
- Artifactها دریافت و ZIPها بررسی شدند: [Lighthouse/axe](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41793603385/artifacts/13305020866) — ۱۳ فایل؛ [UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41793603385/artifacts/13304845956) — ۶۸ تصویر؛ [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/41793603385/artifacts/13304503220) — ۷۰ فایل شامل `AhanModiriat.exe`.
- این Run تأیید CI برای commit `b63d6cb` است؛ اجرای واقعی بسته روی Windows پاک همچنان آزمون دستی مالک است.
