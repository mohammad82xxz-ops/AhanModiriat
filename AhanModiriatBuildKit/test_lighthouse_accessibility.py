# -*- coding: utf-8 -*-
"""Run axe-core against primary pages and Lighthouse against key workflows."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, threading
from http.server import ThreadingHTTPServer
from pathlib import Path
TMP = tempfile.TemporaryDirectory(prefix="ahan_lighthouse_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts" / "accessibility-lighthouse"
AXE_SCRIPT = ROOT / "node_modules" / "axe-core" / "axe.min.js"
LIGHTHOUSE_BIN = ROOT / "node_modules" / ".bin" / ("lighthouse.cmd" if os.name == "nt" else "lighthouse")
AXE_ROUTES = ("/", "/products", "/purchases", "/sales", "/services", "/expenses", "/loans",
              "/prices", "/reports", "/settings", "/design", "/cash", "/parties",
              "/inventory", "/buy-advice", "/returns", "/audit")
LIGHTHOUSE_ROUTES = (("/", "dashboard"), ("/sales", "sales"), ("/purchases", "purchases"),
                     ("/reports", "reports"), ("/settings", "settings"))
def main():
    if not AXE_SCRIPT.is_file(): raise SystemExit(f"axe-core script not found: {AXE_SCRIPT}")
    if not LIGHTHOUSE_BIN.exists(): raise SystemExit(f"Lighthouse CLI not found: {LIGHTHOUSE_BIN}")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    app.init()
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    axe_results, failures, lighthouse_rows = [], [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for route in AXE_ROUTES:
                    page = browser.new_page(viewport={"width": 1366, "height": 768}, color_scheme="light")
                    try:
                        # Serve axe-core as a same-origin external script so the app's
                        # restrictive script-src 'self' CSP remains enabled during the audit.
                        page.route(base + "/axe.min.js", lambda request_route: request_route.fulfill(
                            path=str(AXE_SCRIPT), content_type="application/javascript"))
                        response = page.goto(base + route, wait_until="networkidle")
                        if response is None or response.status != 200:
                            failures.append(f"axe: {route} returned HTTP {getattr(response, 'status', None)}")
                            continue
                        page.add_script_tag(url=base + "/axe.min.js")
                        result = page.evaluate("""async () => {
                          const r = await axe.run(document, {
                            runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}
                          });
                          return {
                            url: location.pathname,
                            violations: r.violations.map(v => ({
                              id: v.id, impact: v.impact, description: v.description,
                              help: v.help, helpUrl: v.helpUrl,
                              nodes: v.nodes.map(n => ({target: n.target, html: n.html.slice(0, 240), summary: n.failureSummary}))
                            })),
                            passes: r.passes.length, incomplete: r.incomplete.length,
                            inapplicable: r.inapplicable.length
                          };
                        }""")
                        axe_results.append(result)
                        # Phase 2 gate: every axe-core violation blocks CI, including moderate/minor.
                        # The previous report had zero violations on every audited route, so this
                        # tightens the acceptance rule without suppressing known current findings.
                        for v in result["violations"]:
                            failures.append(
                                f"axe: {route} {v['impact']} {v['id']} "
                                f"({len(v['nodes'])} affected nodes)"
                            )
                    except Exception as exc:
                        failures.append(f"axe: {route} {type(exc).__name__}: {exc}")
                    finally:
                        page.close()
                browser.close()
            finally:
                try: browser.close()
                except Exception: pass
        (ARTIFACTS / "axe-results.json").write_text(json.dumps(axe_results, ensure_ascii=False, indent=2), encoding="utf-8")
        chrome = playwright.chromium.executable_path
        for route, slug in LIGHTHOUSE_ROUTES:
            for mode in ("mobile", "desktop"):
                report_path = ARTIFACTS / f"lighthouse-{slug}-{mode}.json"
                command = [str(LIGHTHOUSE_BIN), base + route, "--output=json", f"--output-path={report_path}",
                           "--chrome-path=" + chrome, "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage",
                           "--quiet", "--only-categories=performance,accessibility,best-practices,seo",
                           "--max-wait-for-load=15000", "--timeout=60000"]
                if mode == "desktop": command.append("--preset=desktop")
                env = dict(os.environ); env["CHROME_PATH"] = chrome
                completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
                if completed.returncode != 0 or not report_path.is_file():
                    failures.append(f"Lighthouse: {route} {mode} exited {completed.returncode}: {(completed.stderr or completed.stdout)[-1200:]}")
                    continue
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    scores = {name: (None if item.get("score") is None else round(item["score"] * 100))
                              for name, item in report.get("categories", {}).items()}
                    lighthouse_rows.append({"route": route, "mode": mode, "scores": scores,
                                            "finalUrl": report.get("finalDisplayedUrl", base + route)})
                except Exception as exc:
                    failures.append(f"Lighthouse: {route} {mode} invalid JSON report: {exc}")
        (ARTIFACTS / "lighthouse-summary.json").write_text(json.dumps(lighthouse_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# AhanModiriat Lighthouse and axe-core audit", "",
                 "Lighthouse scores are diagnostic and are not treated as a pass/fail threshold.", "",
                 "## Lighthouse scores (0–100)", "",
                 "| Page | Mode | Performance | Accessibility | Best practices | SEO |",
                 "|---|---|---:|---:|---:|---:|"]
        for row in lighthouse_rows:
            s = row["scores"]
            lines.append(f"| {row['route']} | {row['mode']} | {s.get('performance', 'n/a')} | {s.get('accessibility', 'n/a')} | {s.get('best-practices', 'n/a')} | {s.get('seo', 'n/a')} |")
        lines += ["", "## axe-core results", "", "| Page | Passes | Violations | Critical/serious | Moderate/minor |", "|---|---:|---:|---:|---:|"]
        for row in axe_results:
            serious = sum(v["impact"] in ("critical", "serious") for v in row["violations"])
            lower = sum(v["impact"] in ("moderate", "minor") for v in row["violations"])
            lines.append(f"| {row['url']} | {row['passes']} | {len(row['violations'])} | {serious} | {lower} |")
        lines += ["", "## Gate failures", ""] + ([f"- {x}" for x in failures] if failures else ["None."])
        (ARTIFACTS / "audit-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"AXE AUDIT: {len(axe_results)}/{len(AXE_ROUTES)} routes audited.")
        print(f"LIGHTHOUSE: {len(lighthouse_rows)}/{len(LIGHTHOUSE_ROUTES) * 2} reports created.")
        for row in lighthouse_rows: print(f"LIGHTHOUSE {row['route']} {row['mode']}: {row['scores']}")
        print(f"Report directory: {ARTIFACTS}")
        if failures:
            print("ACCESSIBILITY/LIGHTHOUSE AUDIT FAILED:")
            for failure in failures: print(" - " + failure)
            raise SystemExit(1)
        print("ACCESSIBILITY/LIGHTHOUSE AUDIT PASSED: zero axe-core violations at every impact level; reports complete.")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); TMP.cleanup()
if __name__ == "__main__": main()
