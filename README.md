# آهن‌مدیریت ۴٫۰ — نسخه نهایی قابل‌آزمایش

این شاخه نسخهٔ کامل‌تری از برنامهٔ محلی مدیریت انبار و حسابداری «آهن‌آلات برادران» را دارد.

## دانلود
- [دانلود مستقیم سورس از همین شاخه (ZIP)](https://github.com/mohammad82xxz-ops/AhanModiriat/archive/refs/heads/release/ahanmodiriat-v4-final.zip)
- [فایل‌های پروژه](https://github.com/mohammad82xxz-ops/AhanModiriat/tree/release/ahanmodiriat-v4-final/AhanModiriatBuildKit)
- [صفحهٔ اجرای تست و ساخت ویندوز](https://github.com/mohammad82xxz-ops/AhanModiriat/actions)

وقتی CI موفق شد، فایل‌های `AhanModiriat-Final-Source` و `AhanModiriat-Windows-OneDir` نیز از بخش Artifacts اجرای workflow قابل دریافت‌اند.

## امکانات برجسته
دفتر اشخاص و صورت‌حساب، صندوق و بانک، مرجوعی خرید/فروش، ویرایش و حذف کنترل‌شدهٔ تراکنش‌ها، پشتیبان‌گیری/بازیابی، واگرد پنج‌دقیقه‌ای، Excel بومی `.xlsx`، صفحه‌بندی SQL برای فهرست‌های اصلی، POS چندقلمی، پیش‌نویس خودکار، راه‌اندازی اولیه، اعلان‌ها، تم روشن/تیره و طراحی RTL محلی.

## اجرا
در پوشهٔ `AhanModiriatBuildKit`، Python 3.10+ نصب و `python -m pip install -r requirements-build.txt` اجرا شود؛ سپس `run.bat` را اجرا کنید. ساخت Windows OneDir از `build.bat` یا GitHub Actions انجام می‌شود.

جزئیات تست‌ها و محدودیت‌ها در `README.txt`, `FEATURE-MATRIX.md` و `UI-IMPLEMENTATION-MATRIX.md` داخل پوشهٔ پروژه است. معیارهایی مانند تست بصری کامل Lighthouse و اسکرین‌شات همهٔ اندازه‌ها/تم‌ها صریحاً در ماتریس باقی‌مانده‌ها ثبت شده‌اند.
