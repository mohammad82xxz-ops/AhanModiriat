# فاز ۱ سیستم طراحی آهن‌مدیریت

این شاخه یک PR موضوعی برای پایه‌ی UI/UX است و روی شاخه‌ی feature/accounting-foundation قرار دارد.

## تغییرهای این فاز
- افزودن static/tokens.css برای پالت برند/خنثی، رنگ‌های معنایی، فاصله، تایپوگرافی، شعاع و تم تیره.
- افزودن پوسته‌ی راست‌به‌چپ و سبک‌دهی محلی در static/app.css.
- افزودن static/app.js برای سوییچ تم، Ctrl+K، میان‌برهای پایه، مرتب‌سازی جدول و قالب‌بندی عددهای فارسی.
- افزودن کتابخانه‌ی آیکون محلی static/icons.svg و فایل پایه‌ی رشته‌های فارسی static/fa.json.
- افزودن صفحه /design برای مرور اجزای اولیه.
- افزودن مسیر امن سرو دارایی‌های static از خود برنامه.
- افزودن تست design-system و بررسی syntax فایل جاوااسکریپت در CI.
- بسته‌بندی static/ در ساخت Windows OneDir.

## تست
در پوشه AhanModiriatBuildKit اجرا کنید:
    python -m py_compile app.py test_smoke.py test_design_system.py
    python test_smoke.py
    python test_design_system.py
    node --check static/app.js

## محدودیت
این فاز به معنی تکمیل کل سند UI/UX نیست. جدول‌بندی SQL سمت سرور، تقویم گرافیکی کامل، گردش Undo جامع، onboarding/PIN/POS، فهرست رشته‌های کامل، Lighthouse و screenshot مرورگر هنوز معیارهای باز هستند. فایل فونت Vazirmatn WOFF2 در مخزن اضافه نشده؛ CSS از نسخه‌ی نصب‌شده روی سیستم استفاده می‌کند و از CDN استفاده نمی‌کند. شرح دقیق وضعیت در UI-IMPLEMENTATION-MATRIX.md است.
