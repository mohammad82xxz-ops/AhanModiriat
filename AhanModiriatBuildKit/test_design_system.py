# -*- coding: utf-8 -*-
"""Smoke checks for the locally-served phase-one design system."""
import os, sys, tempfile
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
    tokens = (root / "tokens.css").read_text(encoding="utf-8")
    css = (root / "app.css").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "--brand-50:" in tokens and "--brand-950:" in tokens
    assert "--neutral-50:" in tokens and "--neutral-950:" in tokens
    assert '[data-theme="dark"]' in tokens
    assert ".app-shell" in css and "prefers-reduced-motion" in css
    assert "https://" not in css + js and "http://" not in css + js
    assert "localStorage" in js and "Ctrl" not in js  # JS shortcuts are registered as key events.
    with app.conn() as c:
        rendered = app.design_page(c)
        assert "سیستم طراحی" in rendered
        assert "static/tokens.css" in rendered and "static/app.js" in rendered
        assert "<style>" not in rendered and "style=" not in rendered
        assert "command-palette" in rendered and "app-sidebar" in rendered
    assert "DIGIT_TRANSLATION" in (Path(app.__file__).read_text(encoding="utf-8"))
    print("Design system smoke tests passed.")
    _TMP.cleanup()

if __name__ == "__main__":
    main()
