# Phase 2 QA checklist — AhanModiriat

This checklist is deliberately separate from automated CI. An unchecked item is not considered passed.

## Automated acceptance gates

- [x] axe-core: zero violations of every impact level on all 17 audited routes.
- [x] Lighthouse: all 10 reports generated; accessibility and best-practice findings reviewed. Scores are diagnostic unless a threshold is explicitly adopted.
- [x] Browser route matrix: all 17 routes at both viewport sizes and both themes; no console/page errors, unexpected external requests, or horizontal overflow.
- [x] Browser workflows: create a purchase, verify stock/average cost/cash movement; create a sale, verify stock/profit/cash movement; create an expense, verify expense/cash/profit impact; perform a physical inventory count and verify adjustment ledger.
- [x] Automated keyboard tab-reachability and simulated 200% zoom proxies on seven core routes (proxies only; do not substitute for manual review).
- [x] Negative path: browser regression test confirms that a sale exceeding available stock is rejected, stock remains unchanged, no sale record is created, and the rejection message is returned in the redirect query string. Verified in CI run #252.
- [x] Negative path: browser regression submits a zero-quantity purchase while bypassing browser constraint validation; server rejection, unchanged stock/average cost, and no purchase record confirmed in CI run #262.
- [x] Negative path: browser regression submits a zero-quantity sale while bypassing browser constraint validation; server rejection message, unchanged stock, and no sale record confirmed in CI run #266.
- [x] Negative path: browser validation bypassed and sale submitted with missing unit price; server rejects the request, stock remains unchanged, no sale record is created, and the rejection message is returned. Verified after server fix in CI run #278.
- [x] Negative path: sale submitted with a missing quantity while browser validation is bypassed; server rejection, unchanged stock, and no sale record confirmed in CI run #284.
- [x] Negative path: expense submitted with blank or zero amount; server rejects it and the regression asserts no expense row and no cash movement. Verified in CI run #295.
- [x] Negative path: expense submitted with a missing description; server rejects it. Browser regression passed in CI run #297.
- [x] Negative path: purchase submitted with negative extra cost; server rejects it and the regression confirms no purchase row, stock/average-cost change, or purchase cash movement. Verified in CI run #304.
- [x] Negative path: sale submitted with negative received amount; server rejects it and the regression confirms no sale row, stock change, or sale cash movement. Verified in CI run #304.
- [x] Negative path: purchase submitted with negative paid amount; server rejects it and the regression confirms no purchase row, stock/average-cost change, or purchase cash movement. Verified in CI run #310.
- [x] Negative path: sale submitted with negative extra cost; server rejects it and the regression confirms no sale row, stock change, or sale cash movement. Verified in CI run #310.
- [x] Regression: isolated test suite, browser workflow suite, Lighthouse + axe audit, UI screenshot matrix, and Windows OneDir build passed in CI runs #310 and #311.
- [x] Regression: product creation rejects duplicate names after case-folding and collapsing repeated whitespace, without changing existing stock or average cost. Passed in [Run #331](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40920526408).
- [x] Regression: editing a second product to a duplicate normalized name is rejected and leaves both records unchanged. Passed in [Run #331](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40920526408).
- [x] Duplicate-submission regression: replaying the exact successful POST for purchase, sale, or expense is rejected by a one-use server-side token; regression verifies no duplicate transaction, stock change, or duplicate cash movement. Passed in [Run #347](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40931305232).
- [x] Product creation rejects whitespace-only names and negative initial stock; browser regressions assert no product is created. Added in the current QA work; final CI result pending.
- [x] Product editing now rejects negative stock, average cost, market price, minimum stock, roll weight, and sheet area. Automated CI result pending.
- [ ] Other invalid/missing-value paths beyond the cases listed above are not fully covered yet.

Negative-path findings and resolutions:
- [Run #274](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40904421556) caught an empty sale price being converted to zero and accepted. The server guard was tightened from `price < 0` to `price <= 0`; [Run #278](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40904822903) passed.
- Missing sale quantity was added as a regression and passed in [Run #284](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40906632668).
- Blank/zero expense amounts were added as server-side validation and browser regressions; [Run #295](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40909914914) passed.
- Missing expense description was added as a browser regression; [Run #297](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40910500434) passed both jobs.
- Negative purchase extra cost and negative sale received amount passed in [Run #304](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40913032609).
- Negative purchase paid amount and negative sale extra cost passed in [Run #310](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915182879) and PR-triggered [Run #311](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915192983).

## Latest automated CI evidence

- [Run #349 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473) passed both `smoke-test` and `windows-onedir` on commit `90ee40701fd8843bf08d53707893770e4eae5dfa`. This includes the 17-route browser UI matrix, finance/inventory workflows, Lighthouse + axe audit, UI screenshots, and Windows OneDir packaging.
- [Run #348 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932129198) also passed both jobs on the same commit.
- Latest code changes add server-side nonnegative validation for product creation and editing, plus browser regressions for whitespace-only product names and negative initial stock. The CI run for these changes is pending.
- [Run #347 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40931305232) passed both `smoke-test` and `windows-onedir` on commit `976dcc324ce47cc6918652ef6f28bfa9d392a789`; retained as historical evidence.
- [Run #331 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40920526408) passed on an earlier commit and is retained as historical evidence only.
- [Run #310 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915182879) and [Run #311 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915192983) passed on the older commit `ac12541c99b389e2b187757a3a0aa60746a57185`; they remain historical evidence only.

### Latest run artifacts

- [Lighthouse + axe-core reports — Run #349](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473/artifacts/12924155523)
- [UI screenshots — Run #349](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473/artifacts/12923611890)
- [Windows OneDir build — Run #349](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473/artifacts/12923920707)

## Manual checks — required before calling the entire phase complete

- [ ] **Defer to final real-environment pass (user will perform):** keyboard-only navigation through sidebar, forms, dialogs, command palette, and tables; visible focus and logical order.
- [ ] **Defer to final real-environment pass (user will perform):** screen reader pass on key workflows (at minimum NVDA + Firefox/Chrome on Windows, or a documented equivalent): page title, heading structure, field labels/errors, dialog name/description, status feedback, and table headers.
- [ ] **Defer to final real-environment pass (user will perform):** narrow viewport / real-device review: sidebar behavior, forms, data tables, dialogs, horizontal scrolling, and touch targets.
- [ ] **Defer to final real-environment pass (user will perform):** zoom to 200% and verify no loss of core content or operation.
- [x] Reviewed 68 screenshots via contact sheet and selected full-resolution screens (dashboard, purchases, settings) from Run #347; no systematic clipping/overlap was observed. This does not replace real-device/200%-zoom/screen-reader checks.
- [ ] **Defer to final real-environment pass (user will perform):** verify build artifact starts in a clean Windows environment and can open the app without developer tools installed.

## Guardrails

- All test data must use isolated temporary storage; never point tests at a user's real business database.
- Do not merge this QA work into `main` without explicit authorization.
- Keep phase 2 on `qa/phase2-workflow-accessibility-hardening`; preserve phase 1 branch and its draft PR.
- Report automated and manual results separately. Do not mark manual items complete based only on CI.
