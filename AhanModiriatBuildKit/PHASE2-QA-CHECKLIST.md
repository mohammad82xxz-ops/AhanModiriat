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
- [x] Product creation rejects whitespace-only names and negative initial stock; browser regressions assert no product is created. Passed in [Run #359](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40940718650) and [Run #360](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40940730913).
- [x] Product editing rejects negative stock, average cost, market price, minimum stock, roll weight, and sheet area; product-creation validation is enforced server-side. CI on commit `d369de9c0a30c564c8b482942cf34278a0ec7598` passed in [Run #355](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40934032513) and [Run #356](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40934040035).
- [x] Service creation rejects negative revenue and asserts no service row or cash movement is written; loan creation rejects remaining balance above principal and asserts no loan row; zero market price is rejected without history or current-price changes. Passed in [Run #359](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40940718650) and [Run #360](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40940730913).
- [x] Missing-token regression: direct POSTs to purchase, sale, and expense routes without a one-use submission token are rejected; transaction counts, cash movements, and product stock remain unchanged, and SQLite integrity check passes. Passed in [Run #388 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40951540783) and [Run #387 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40951531647).
- [x] Regression: a purchase-form token cannot authorize a sale or expense POST; purchase/sale/expense counts, cash movements, and stock remain unchanged. Extended sale+expense coverage passed in [Run #394 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40953431465) and [Run #393 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40953422226).
- [x] Missing-token regression: direct POSTs to purchase-return and sales-return routes without a one-use submission token are rejected; return rows, cash movements, stock, and party balances remain unchanged. Passed in [Run #388 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40951540783) and [Run #387 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40951531647).
- [x] Regression: purchase and sale POSTs with a nonexistent product ID or non-numeric quantity are rejected atomically; purchase/sale counts, cash movements, stock, and average cost remain unchanged, with SQLite foreign-key and integrity checks passing. Passed in [Run #398 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40954524465) and [Run #397 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40954512220).
- [ ] New regression suite added; pending CI: malformed/non-finite numeric input across product create/edit, purchase/sale/expense edits, service, expense, loan/payment, daily price, settlement, purchase/sales returns, inventory count, and cash movement; zero-price sale edits must follow the same rule as new sales; negative/malformed/blank opening capital must be rejected. All rejected requests must leave source records, stock, cash movements, balances, and audit data unchanged.
- [ ] Other invalid/missing-value paths beyond the cases listed above are not fully covered yet.

Negative-path findings and resolutions:
- [Run #274](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40904421556) caught an empty sale price being converted to zero and accepted. The server guard was tightened from `price < 0` to `price <= 0`; [Run #278](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40904822903) passed.
- Missing sale quantity was added as a regression and passed in [Run #284](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40906632668).
- Blank/zero expense amounts were added as server-side validation and browser regressions; [Run #295](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40909914914) passed.
- Missing expense description was added as a browser regression; [Run #297](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40910500434) passed both jobs.
- Negative purchase extra cost and negative sale received amount passed in [Run #304](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40913032609).
- Negative purchase paid amount and negative sale extra cost passed in [Run #310](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915182879) and PR-triggered [Run #311](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915192983).

## Latest automated CI evidence

- [Run #398 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40954524465) passed both `smoke-test` and `windows-onedir` on commit `69e3048a9002627a3dba7c1d5a967e75dc8b1daf`; includes invalid product-ID and malformed-quantity atomicity regressions.
- [Run #397 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40954512220) also passed both jobs on the same commit.
- [Run #396 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40954449028) and [Run #395 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40954439459) passed both jobs on checklist-evidence commit `bd812c812f88e5d529c28cbddeaf820060e09b82`.
- [Run #394 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40953431465) passed both `smoke-test` and `windows-onedir` on commit `7647885b3dc55f9bedd5c589639c8566b3b1fd6f`; includes purchase-token route-binding rejection for both sale and expense POSTs.
- [Run #393 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40953422226) also passed both jobs on the same commit.
- [Run #392 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40952592378) passed both `smoke-test` and `windows-onedir` on commit `a90ed0dc856313f6a2df46e33e93758d7acd893c`, including transaction-token route-binding regression.
- [Run #391 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40952583557) also passed both jobs on the same commit.
- [Run #388 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40951540783) passed both `smoke-test` and `windows-onedir` on commit `cbf6b045e2e80732386b6952bce5ae54e1683891`, including tokenless purchase/sale/expense rejection regressions.
- [Run #387 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40951531647) also passed both jobs on the same commit, including the browser acceptance suite, Lighthouse + axe-core audit, screenshots, and Windows OneDir packaging.
- [Run #360 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40940730913) passed both `smoke-test` and `windows-onedir` on the current browser-regression commit `28b9151eca1f40edca3b1b260128fb95f339eaad`.
- [Run #359 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40940718650) also passed both jobs on the same commit. These runs include the browser acceptance suite and Windows OneDir packaging.
- [Run #358 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40936960736) and [Run #357 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40936947971) passed after service, loan, payment, daily-price, and import-related server validation changes.
- [Run #349 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473) passed both `smoke-test` and `windows-onedir` on commit `90ee40701fd8843bf08d53707893770e4eae5dfa`. This includes the 17-route browser UI matrix, finance/inventory workflows, Lighthouse + axe audit, UI screenshots, and Windows OneDir packaging.
- [Run #348 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932129198) also passed both jobs on the same commit.
- Product and finance validation work has now passed automated CI through Runs #359 and #360. Real-environment manual checks below remain open and must not be inferred from CI.
- [Run #347 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40931305232) passed both `smoke-test` and `windows-onedir` on commit `976dcc324ce47cc6918652ef6f28bfa9d392a789`; retained as historical evidence.
- [Run #331 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40920526408) passed on an earlier commit and is retained as historical evidence only.
- [Run #310 — push CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915182879) and [Run #311 — PR CI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915192983) passed on the older commit `ac12541c99b389e2b187757a3a0aa60746a57185`; they remain historical evidence only.

### Latest run artifacts

- [Lighthouse + axe-core reports — Run #349](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473/artifacts/12924155523)
- [UI screenshots — Run #349](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473/artifacts/12923611890)
- [Windows OneDir build — Run #349](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40932140473/artifacts/12923920707)

## Manual checks — user confirmation

- [x] User-confirmed on 2026-10-29: keyboard-only navigation through sidebar, forms, dialogs, command palette, and tables; visible focus and logical order.
- [x] User-confirmed on 2026-10-29: screen-reader pass on key workflows, including page title, heading structure, field labels/errors, dialog name/description, status feedback, and table headers.
- [x] User-confirmed on 2026-10-29: narrow viewport / real-device review covering sidebar behavior, forms, data tables, dialogs, horizontal scrolling, and touch targets.
- [x] User-confirmed on 2026-10-29: zoom to 200% with no loss of core content or operation.
- [x] Reviewed 68 screenshots via contact sheet and selected full-resolution screens (dashboard, purchases, settings) from Run #347; no systematic clipping/overlap was observed. Screenshot review is separate from the user's real-environment confirmation.
- [x] User-confirmed on 2026-10-29: build artifact starts in a clean Windows environment and opens without developer tools installed.

The items above are marked complete based on the user's explicit confirmation; they are not represented as independently observed by CI or the assistant.

## Guardrails

- All test data must use isolated temporary storage; never point tests at a user's real business database.
- Do not merge this QA work into `main` without explicit authorization.
- Keep phase 2 on `qa/phase2-workflow-accessibility-hardening`; preserve phase 1 branch and its draft PR.
- Report automated and manual results separately. Do not mark manual items complete based only on CI.
