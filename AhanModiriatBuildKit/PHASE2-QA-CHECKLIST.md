# Phase 2 QA checklist — AhanModiriat

This checklist is deliberately separate from automated CI. An unchecked item is not considered passed.

## Automated acceptance gates

- [x] axe-core: zero violations of every impact level on all 17 audited routes.
- [x] Lighthouse: all 10 reports generated; accessibility and best-practice findings reviewed. Scores are diagnostic unless a threshold is explicitly adopted.
- [x] Browser route matrix: all 17 routes at both viewport sizes and both themes; no console/page errors, unexpected external requests, or horizontal overflow.
- [x] Browser workflows: create a purchase, verify stock/average cost/cash movement; create a sale, verify stock/profit/cash movement; create an expense, verify expense/cash/profit impact; perform a physical inventory count and verify adjustment ledger.
- [x] Automated keyboard tab-reachability and simulated 200% zoom proxies on seven core routes (proxies only; do not substitute for manual review).
- [ ] Negative paths: reject invalid or missing required values; reject sale quantities exceeding available stock if that is the intended business rule; prevent duplicate submission where applicable.
- [x] Regression: run the full existing isolated test suite and Windows OneDir build.

## Manual checks — required before calling the entire phase complete

- [ ] Keyboard-only navigation through sidebar, forms, dialogs, command palette, and tables; visible focus and logical order.
- [ ] Screen reader pass on key workflows (at minimum NVDA + Firefox/Chrome on Windows, or a documented equivalent): page title, heading structure, field labels/errors, dialog name/description, status feedback, and table headers.
- [ ] Narrow viewport / real-device review: sidebar behavior, forms, data tables, dialogs, horizontal scrolling, and touch targets.
- [ ] Zoom to 200% and verify no loss of core content or operation.
- [ ] Review each screenshot contact sheet for clipping, overlap, unreadable Persian text, and theme-specific contrast.
- [ ] Verify build artifact starts in a clean Windows environment and can open the app without developer tools installed.

## Guardrails

- All test data must use isolated temporary storage; never point tests at a user's real business database.
- Do not merge this QA work into `main` without explicit authorization.
- Keep phase 2 on `qa/phase2-workflow-accessibility-hardening`; preserve phase 1 branch and its draft PR.
- Report automated and manual results separately. Do not mark manual items complete based only on CI.
