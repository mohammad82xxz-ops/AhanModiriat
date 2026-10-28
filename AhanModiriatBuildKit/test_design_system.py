# -*- coding: utf-8 -*-
"""Smoke checks for the locally-served phase-one design system."""
import os, sys, tempfile, threading, urllib.request
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="ahan_design_smoke_")
os.environ["AHAN_DATA_DIR"] = _TMP.name
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app

def main():
    app.init()
    root = Path(app.STATIC_DIR)
    for name in ("tokens.css", "app.css", "app.js", "icons.svg", "fa.json", "print.css"):
        assert (root / name).is_file(), f"missing local asset: {name}"
    font_path = root / "fonts" / "Vazirmatn-Variable.woff2"
    license_path = root / "fonts" / "OFL-Vazirmatn.txt"
    assert font_path.is_file() and font_path.stat().st_size > 50000
    assert font_path.read_bytes()[:4] == b"wOF2"
    assert license_path.is_file() and "SIL OPEN FONT LICENSE" in license_path.read_text(encoding="utf-8")
    tokens = (root / "tokens.css").read_text(encoding="utf-8")
    css = (root / "app.css").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "--brand-50:" in tokens and "--brand-950:" in tokens
    assert "--neutral-50:" in tokens and "--neutral-950:" in tokens
    assert '[data-theme="dark"]' in tokens
    assert ".app-shell" in css and "prefers-reduced-motion" in css
    assert 'url("/static/fonts/Vazirmatn-Variable.woff2") format("woff2")' in css
    assert "font-display:swap" in css
    assert "https://" not in css + js and "http://" not in css + js
    assert "localStorage" in js and "keydown" in js
    assert "requestSubmit" in js and "e.key.toLowerCase()==='n'" in js
    assert "if(!inField" in js and "F2" in js and "F3" in js and "F4" in js
    with app.conn() as c:
        rendered = app.design_page(c)
        assert "سیستم طراحی" in rendered
        assert "static/tokens.css" in rendered and "static/app.js" in rendered
        assert "<style>" not in rendered and "style=" not in rendered
        assert "command-palette" in rendered and "app-sidebar" in rendered
    assert app.num("۲٬۵۰۰٬۰۰۰") == 2500000
    money_field = app.field("مبلغ", "amount", "number", "۲۵۰۰۰۰۰")
    assert 'data-money="true"' in money_field and "amount-words" in money_field
    date_field = app.field("تاریخ", "date", "date", app.TODAY)
    assert 'data-date-input="true"' in date_field and "data-today=" in date_field and "data-yesterday=" in date_field
    assert "jalali-date-picker" in js and "jalali-calendar-days" in js and "ماه قبل" in js
    assert ".jalali-date-picker" in css and ".jalali-calendar-day" in css
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/static/tokens.css", headers={"Host": f"127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 200 and "--brand-50" in response.read().decode("utf-8")
        font_req=urllib.request.Request(f"http://127.0.0.1:{port}/static/fonts/Vazirmatn-Variable.woff2",headers={"Host":f"127.0.0.1:{port}"})
        with urllib.request.urlopen(font_req,timeout=5) as response:
            assert response.status==200 and response.headers.get("Content-Type","").startswith("font/woff2")
            assert response.read(4)==b"wOF2"
    finally:
        server.shutdown()
        server.server_close()
    assert "DIGIT_TRANSLATION" in Path(app.__file__).read_text(encoding="utf-8")
    print("Design system smoke tests passed.")

if __name__ == "__main__":
    main()
