# -*- coding: utf-8 -*-
"""Automated proxies for keyboard reachability and 200% zoom on core routes.

These checks do not replace human keyboard, screen-reader, or real-device review.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

TMP = tempfile.TemporaryDirectory(prefix="ahan_accessibility_proxies_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROUTES = ("/", "/products", "/purchases", "/sales", "/expenses", "/inventory", "/settings")


def main() -> None:
    app.init()
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    failures: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="fa-IR")
                page.set_default_timeout(10000)
                for route in ROUTES:
                    response = page.goto(base + route, wait_until="networkidle")
                    if response is None or response.status != 200:
                        failures.append(f"{route}: navigation did not return HTTP 200")
                        continue
                    page.keyboard.press("Tab")
                    first = page.evaluate("""() => {
                        const el = document.activeElement;
                        return el && el !== document.body && el !== document.documentElement
                          ? {tag: el.tagName, text: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim()}
                          : null;
                    }""")
                    if first is None:
                        failures.append(f"{route}: first Tab did not move focus to an element")
                    # Walk a bounded sequence and ensure focus remains on reachable controls.
                    focused = 0
                    for _ in range(25):
                        page.keyboard.press("Tab")
                        is_control = page.evaluate("""() => {
                            const e = document.activeElement;
                            return !!e && e !== document.body && e !== document.documentElement &&
                              (e.matches('a,button,input,select,textarea,[tabindex]:not([tabindex="-1"])'));
                        }""")
                        focused += int(bool(is_control))
                    if focused == 0:
                        failures.append(f"{route}: keyboard tab sequence did not reach interactive controls")
                    # Simulate browser zoom at 200%; verify the core page and an interactive control remain rendered.
                    page.evaluate("""() => {
                        document.documentElement.style.zoom = '200%';
                        window.dispatchEvent(new Event('resize'));
                    }""")
                    zoom = page.evaluate("""() => {
                        const main = document.querySelector('main') || document.body;
                        const control = document.querySelector('main a, main button, main input, main select, main textarea, body a, body button, body input, body select, body textarea');
                        const visible = el => {
                          if (!el) return false;
                          const r = el.getBoundingClientRect();
                          const s = getComputedStyle(el);
                          return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                        };
                        return {mainVisible: visible(main), controlVisible: visible(control)};
                    }""")
                    if not zoom["mainVisible"] or not zoom["controlVisible"]:
                        failures.append(f"{route}: page content or an interactive control is not rendered at simulated 200% zoom")
                    page.evaluate("() => { document.documentElement.style.zoom = ''; }")
                if failures:
                    raise AssertionError("\\n".join(failures))
                print(f"ACCESSIBILITY PROXIES PASSED: keyboard tab reachability and simulated 200% zoom on {len(ROUTES)} routes.")
                print("NOTE: automated proxies only; human keyboard, screen-reader, and device checks remain required.")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        TMP.cleanup()


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()
