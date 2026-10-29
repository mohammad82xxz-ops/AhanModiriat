# -*- coding: utf-8 -*-
"""Browser acceptance matrix for all main pages, viewport sizes, themes, and local-only assets."""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit
from http.server import ThreadingHTTPServer

TMP = tempfile.TemporaryDirectory(prefix="ahan_browser_ui_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


ROUTES = (
    ("/", "dashboard"),
    ("/products", "products"),
    ("/purchases", "purchases"),
    ("/sales", "sales"),
    ("/services", "services"),
    ("/expenses", "expenses"),
    ("/loans", "loans"),
    ("/prices", "prices"),
    ("/reports", "reports"),
    ("/settings", "settings"),
    ("/design", "design"),
    ("/cash", "cash"),
    ("/parties", "parties"),
    ("/inventory", "inventory"),
    ("/buy-advice", "buy-advice"),
    ("/returns", "returns"),
    ("/audit", "audit"),
)
VIEWPORTS = ((1366, 768), (1920, 1080))
THEMES = ("light", "dark")
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def main() -> None:
    errors: list[str] = []
    external_requests: set[str] = set()
    javascript_errors: list[str] = []
    screenshot_dir = Path(__file__).resolve().parent / "artifacts" / "ui-screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    source = Path(app.__file__).read_text(encoding="utf-8")
    if re.search(r"\bstyle\s*=", source):
        errors.append("app.py contains a literal inline style attribute; use a class or SVG geometry instead.")

    app.init()
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                # Confirm that every required UI asset is served by the local application.
                asset_context = browser.new_context()
                try:
                    for asset in (
                        "tokens.css",
                        "app.css",
                        "app.js",
                        "icons.svg",
                        "fonts/Vazirmatn-Variable.woff2",
                    ):
                        response = asset_context.request.get(f"{base_url}/static/{asset}")
                        if response.status != 200:
                            errors.append(f"Local asset /static/{asset} returned HTTP {response.status}.")
                        if asset.endswith(".woff2"):
                            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                            if content_type != "font/woff2":
                                errors.append(f"WOFF2 MIME type is {content_type!r}, expected 'font/woff2'.")
                            if not response.body().startswith(b"wOF2"):
                                errors.append("Vazirmatn font response does not have the WOFF2 signature.")
                finally:
                    asset_context.close()

                for width, height in VIEWPORTS:
                    for theme in THEMES:
                        context = browser.new_context(
                            viewport={"width": width, "height": height},
                            color_scheme=theme,
                            locale="fa-IR",
                            reduced_motion="reduce",
                        )

                        def guard_request(route) -> None:
                            parsed = urlsplit(route.request.url)
                            if parsed.scheme in ("http", "https") and parsed.hostname not in ALLOWED_HOSTS:
                                external_requests.add(route.request.url)
                                route.abort()
                            else:
                                route.continue_()

                        context.route("**/*", guard_request)
                        context.add_init_script(
                            "if (location.protocol === 'http:' && location.hostname === '127.0.0.1') "
                            f"localStorage.setItem('ahan-theme', {json.dumps(theme)});"
                        )
                        page = context.new_page()
                        page.set_default_timeout(15000)
                        page.on("pageerror", lambda exc: javascript_errors.append(f"{page.url}: {exc}"))

                        for route_path, slug in ROUTES:
                            target_url = f"{base_url}{route_path}"
                            try:
                                response = page.goto(target_url, wait_until="networkidle")
                                if response is None:
                                    errors.append(f"{route_path} {width}x{height} {theme}: navigation returned no response.")
                                    continue
                                if response.status != 200:
                                    errors.append(f"{route_path} {width}x{height} {theme}: HTTP {response.status}.")
                                    continue

                                metadata = page.evaluate("""() => ({
                                    lang: document.documentElement.lang,
                                    dir: document.documentElement.dir,
                                    theme: document.documentElement.dataset.theme,
                                    hasMain: Boolean(document.querySelector('main')),
                                    hasShell: Boolean(document.querySelector('.app-shell')),
                                    viewport: window.innerWidth,
                                    pageWidth: document.documentElement.scrollWidth,
                                    bodyWidth: document.body.scrollWidth,
                                    inlineStyleCount: document.querySelectorAll('[style]').length,
                                    unnamedIconButtons: [...document.querySelectorAll('button')]
                                      .filter(b => b.querySelector('svg') && !b.textContent.trim() && !b.getAttribute('aria-label'))
                                      .map(b => b.outerHTML.slice(0, 120))
                                })""")
                                prefix = f"{route_path} {width}x{height} {theme}"
                                if metadata["lang"] != "fa" or metadata["dir"] != "rtl":
                                    errors.append(f"{prefix}: expected lang=fa and dir=rtl.")
                                if metadata["theme"] != theme:
                                    errors.append(f"{prefix}: expected theme {theme!r}, got {metadata['theme']!r}.")
                                if not metadata["hasMain"] or not metadata["hasShell"]:
                                    errors.append(f"{prefix}: app shell or main content is missing.")
                                if metadata["pageWidth"] > metadata["viewport"] + 2 or metadata["bodyWidth"] > metadata["viewport"] + 2:
                                    errors.append(f"{prefix}: page overflows horizontally ({metadata['pageWidth']}px document / {metadata['bodyWidth']}px body).")
                                if metadata["inlineStyleCount"]:
                                    errors.append(f"{prefix}: found {metadata['inlineStyleCount']} inline style attribute(s).")
                                if metadata["unnamedIconButtons"]:
                                    errors.append(f"{prefix}: icon-only button lacks aria-label: {metadata['unnamedIconButtons'][0]}")

                                page.evaluate("() => document.fonts.ready.then(() => true)")
                                shot_path = screenshot_dir / f"{slug}-{width}x{height}-{theme}.png"
                                page.screenshot(path=str(shot_path), full_page=False, animations="disabled")
                                if not shot_path.is_file() or shot_path.stat().st_size < 1000:
                                    errors.append(f"{prefix}: screenshot was not created or is suspiciously small.")
                                else:
                                    with shot_path.open("rb") as shot:
                                        header = shot.read(24)
                                    if header[:8] != b"\x89PNG\r\n\x1a\n":
                                        errors.append(f"{prefix}: screenshot is not a PNG file.")
                                    elif struct.unpack(">II", header[16:24]) != (width, height):
                                        errors.append(f"{prefix}: screenshot dimensions do not match requested viewport.")

                            except Exception as exc:  # keep collecting evidence for other pages
                                errors.append(f"{route_path} {width}x{height} {theme}: {type(exc).__name__}: {exc}")

                        # Verify the theme switch and the principal keyboard interactions.
                        try:
                            page.goto(f"{base_url}/design", wait_until="networkidle")
                            expected_theme = theme
                            page.locator("#theme-toggle").click()
                            actual_theme = page.locator("html").get_attribute("data-theme")
                            if actual_theme != ("dark" if expected_theme == "light" else "light"):
                                errors.append(f"{width}x{height} {theme}: theme toggle did not switch themes.")
                            page.locator("#theme-toggle").click()
                            page.keyboard.press("Control+k")
                            palette = page.locator("#command-palette")
                            if "open" not in (palette.get_attribute("class") or "") or palette.get_attribute("aria-hidden") != "false":
                                errors.append(f"{width}x{height} {theme}: Ctrl+K did not open the command palette.")
                            page.keyboard.press("Escape")
                            if "open" in (palette.get_attribute("class") or "") or palette.get_attribute("aria-hidden") != "true":
                                errors.append(f"{width}x{height} {theme}: Escape did not close the command palette.")
                        except Exception as exc:
                            errors.append(f"{width}x{height} {theme}: interaction check failed: {type(exc).__name__}: {exc}")
                        finally:
                            context.close()
                browser.close()
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        if external_requests:
            errors.append("External network requests were attempted: " + ", ".join(sorted(external_requests)))
        if javascript_errors:
            errors.extend("Uncaught browser JavaScript error: " + item for item in javascript_errors)

        expected_count = len(ROUTES) * len(VIEWPORTS) * len(THEMES)
        actual_count = len(list(screenshot_dir.glob("*.png")))
        if actual_count < expected_count:
            errors.append(f"Expected {expected_count} screenshots, found {actual_count} in {screenshot_dir}.")

        if errors:
            print("BROWSER UI ACCEPTANCE FAILED:")
            for item in errors:
                print(f" - {item}")
            raise SystemExit(1)

        print(
            f"BROWSER UI ACCEPTANCE PASSED: {len(ROUTES)} routes, "
            f"{len(VIEWPORTS)} viewport sizes, {len(THEMES)} themes, "
            f"{expected_count} screenshots; local-only assets, RTL, no inline styles, "
            "no unnamed icon-only buttons, theme toggle, and Ctrl+K/Escape verified."
        )
        print(f"Screenshot artifact directory: {screenshot_dir}")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        TMP.cleanup()


if __name__ == "__main__":
    main()
