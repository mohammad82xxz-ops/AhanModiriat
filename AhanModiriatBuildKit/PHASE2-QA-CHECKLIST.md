> **توضیح مهم درباره دامنه:** این چک‌لیست فقط شواهد QA فنی، رابط کاربری، امنیت فرم‌ها و CI شاخه قبلی را ثبت می‌کند؛ تیک‌خوردن موارد آن به معنی تأیید منطق حسابداری آهن‌فروشی یا تکمیل نیازمندی‌های T01 تا T28 نیست. مرجع ممیزی و فازبندی حسابداری از این پس [نقشه بازطراحی منطق حسابداری](ACCOUNTING-REBUILD-ROADMAP-FA.md) است. هیچ فاز حسابداری بدون معیار پذیرش و تست‌های مستقل آن تأیید نمی‌شود.

# Phase 2 QA checklist — AhanModiriat

> وضعیت دامنه در PR #41: صفحه‌های `/loans`، `/cash` و `/buy-advice` بازنشسته شده‌اند؛ ماتریس فعلی رابط ۱۴ مسیر فعال دارد. شواهد ۱۷مسیرهٔ زیر مربوط به baseline تاریخی پیش از حذف این سه صفحه است و نباید به‌عنوان اجرای مجدد روی head فعلی تلقی شود.

This checklist is deliberately separate from automated CI. An unchecked item is not considered passed.

## Automated acceptance gates

- [x] axe-core baseline تاریخی: zero violations of every impact level on all 17 routes؛ سه مسیر از آن زمان بازنشسته شده‌اند و ماتریس جاری ۱۴ مسیر فعال دارد.
- [x] Lighthouse: all 10 reports generated; accessibility and best-practice findings reviewed. Scores are diagnostic unless a threshold is explicitly adopted.
- [x] Browser route matrix baseline تاریخی: 17 routes at both viewport sizes and both themes; ماتریس جاری پس از بازنشستگی سه صفحه ۱۴ مسیر فعال را می‌سنجد.
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
- [x] Malformed/non-finite numeric validation regression suite: product create/edit, purchase/sale/expense edits, service, daily price, settlement, purchase/sales returns, inventory count, and opening capital. Legacy loan/payment and manual cash movement POSTs are now retired and rejected with HTTP 410; no source rows or ledger movements are changed. Executed in the isolated CI suite; passed historically in [Run #835](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42262349580).
- [x] Optional numeric form defaults: omitted `purchase_factor` and `sale_factor` retain their documented defaults without raising an exception. Loan `interval_value` is no longer an active form field because loan entry is retired. Historical test passed in [Run #835](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42262349580).
- [x] Invalid calendar-date regression: impossible Gregorian dates and invalid Jalali leap-day dates are rejected atomically across active purchase, service, expense, price history, settlement, both return types, inventory count, and opening capital. Loan, installment and manual cash movement endpoints are retired in PR #41. Historical test passed in [Run #838](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42358566485).
- [x] Required-reference/description regression: missing product references for purchase, sale, daily price, and inventory count; missing party for settlement; missing source-document references/reason for returns; and blank service title are rejected atomically. Regression asserts no financial, inventory, cash, or audit mutation. Passed historically in [Run #843](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42386789868).
- [ ] Other invalid/missing-value paths beyond the explicitly listed cases are not fully covered yet; continue expanding the matrix as new endpoints or fields are introduced.

Negative-path findings and resolutions:
- [Run #274](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40904421556) caught an empty sale price being converted to zero and accepted. The server guard was tightened from `price < 0` to `price <= 0`; [Run #278](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40904822903) passed.
- Missing sale quantity was added as a regression and passed in [Run #284](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40906632668).
- Blank/zero expense amounts were added as server-side validation and browser regressions; [Run #295](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40909914914) passed.
- Missing expense description was added as a browser regression; [Run #297](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40910500434) passed both jobs.
- Negative purchase extra cost and negative sale received amount passed in [Run #304](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40913032609).
- Negative purchase paid amount and negative sale extra cost passed in [Run #310](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915182879) and PR-triggered [Run #311](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/40915192983).

## Latest complete CI evidence — Run #885

- [x] Run #885 validates code head `692c43be6367582d0aca876c02fa6070c3e09b6e` and completed successfully on 2026-11-09.
- [x] Both jobs passed: `smoke-test` and `windows-onedir`. The smoke job completed compile, isolated regression tests, browser UI matrix, finance/inventory workflows, keyboard/zoom accessibility proxies, Lighthouse, and axe-core audit.
- [x] The Windows job completed cross-process token characterization, PyInstaller OneDir build, and artifact upload.
- [x] All three artifacts were uploaded: Lighthouse + accessibility reports, browser UI screenshots, and Windows OneDir package. See artifact links below.
- [x] Run #885 supersedes Run #874 as the latest complete CI evidence for the code changes. Run #886 separately validates documentation commit `d49258bc6a6047db95e5894874b49199e0a53557`; at last inspection it was still in progress and is not counted as passed: [Run #886](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42628561387).

## Latest automated CI evidence

- [x] Latest complete PR CI: [Run #885](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42627740597) passed both `smoke-test` and `windows-onedir` on tested code head `692c43be6367582d0aca876c02fa6070c3e09b6e`. The smoke job passed Compile, isolated regression tests, browser UI matrix, finance/inventory workflows, keyboard/zoom proxies, Lighthouse, and axe-core; the Windows job passed cross-process token characterization and Windows OneDir packaging. All three artifacts were uploaded. This is the latest complete CI evidence for the code changes; Run #874 and earlier runs remain historical evidence only.
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

## Latest automated evidence for current PR head — Run #889

- [x] Run #889 passed both `smoke-test` and `windows-onedir` on the latest code-bearing commit `8d0ca1df9e4992c127e4934a81e6f1995614c2e4`; the later commits `0ff03aabb4559a51e3c9ecedcc9224c03729b42e` and `424b8ea63bd2546f278069b75355eb10cb4c5bad` update documentation only and do not change application code.
- [x] Compile, isolated regression tests, 14-route browser matrix, finance/inventory workflows, keyboard/zoom proxies, Lighthouse + axe-core audit, Windows cross-process token characterization, and Windows OneDir packaging all completed successfully.
- [x] All three artifacts were uploaded for this exact code-bearing commit: Windows OneDir, Lighthouse/axe reports, and UI screenshots.
- [ ] Owner acceptance of this exact build on a real Windows environment remains outstanding; automated CI does not replace manual acceptance.

Run: [#889](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42628848902).

### Latest run artifacts

- [Lighthouse + axe-core reports — Run #889](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42628848902/artifacts/13679673145)
- [UI screenshots — Run #889](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42628848902/artifacts/13679983842)
- [Windows OneDir build — Run #889](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42628848902/artifacts/13680317286)
- [Lighthouse + axe-core reports — Run #843](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42386789868/artifacts/13579698525)
- [UI screenshots — Run #843](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42386789868/artifacts/13580072340)
- [Windows OneDir build — Run #843](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42386789868/artifacts/13579973114)
- [Lighthouse + axe-core reports — Run #841](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42360312180/artifacts/13570140074)
- [UI screenshots — Run #841](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42360312180/artifacts/13570045190)
- [Windows OneDir build — Run #841](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42360312180/artifacts/13569472972)
- [Lighthouse + axe-core reports — Run #839](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42358970793/artifacts/13569246367)
- [UI screenshots — Run #839](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42358970793/artifacts/13569510046)
- [Windows OneDir build — Run #839](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42358970793/artifacts/13569032570)
- [Lighthouse + axe-core reports — Run #838](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42358566485/artifacts/13568956803)
- [UI screenshots — Run #838](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42358566485/artifacts/13568991721)
- [Windows OneDir build — Run #838](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42358566485/artifacts/13568732468)
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

## Historical automated evidence for PR #41 — Run #872

- [x] Run #872 passed both `smoke-test` and `windows-onedir` on head commit `5f0a094f85319bef9889a0fbc87549f4de02cd38`.
- [x] Isolated regression suite passed, including retired-route guards, preservation of historical loan/cash records, historical loan interest in profit reports, single default cashbox, backup/restore, and retained low-stock warnings.
- [x] Browser acceptance passed on all 14 active routes, two viewport sizes and two themes; 56 screenshots generated.
- [x] Browser transaction workflows and keyboard/200% zoom proxies passed.
- [x] axe-core audited 14/14 active routes with zero violations; Lighthouse generated 10 reports. Performance and accessibility were 100 on all reports; best-practices 96 and SEO 90.
- [x] Windows OneDir packaging completed and artifact uploaded.

Artifacts: [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42479670860/artifacts/13617215817) · [Lighthouse + axe reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42479670860/artifacts/13616918346) · [56 UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42479670860/artifacts/13616858656).

## Latest automated evidence — Run #893 (2026-11-09)

- [x] GitHub Actions [Run #893](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42631536391) completed with conclusion `success` on code SHA `be107dfbf7e4a950115349e4e367c7d3a70fee04`.
- [x] Both jobs passed: `smoke-test` and `windows-onedir`.
- [x] The smoke-test job completed compile, isolated smoke tests, browser UI matrix, browser finance/inventory workflows, keyboard/zoom accessibility proxies, Lighthouse/axe-core audit, and report/screenshot uploads.
- [x] The Windows job passed cross-process token characterization, PyInstaller installation, OneDir build, and artifact upload.
- [x] Artifacts for this exact run:
  - [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42631536391/artifacts/13682345601)
  - [Lighthouse and axe-core reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42631536391/artifacts/13682045562)
  - [Browser UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42631536391/artifacts/13682075557)
- [ ] The automated run does not establish owner acceptance of the packaged Windows app, nor does it approve accounting policy decisions or database migration.

## Historical owner acceptance checklist — Run #893 (superseded by Run #897)

The automated Windows OneDir build is not a substitute for launching and exercising the packaged application on the owner's own Windows machine. Complete these checks against the Run #893 artifact before accepting the candidate:

- [ ] Download and extract the [Run #893 Windows OneDir build](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42631536391/artifacts/13682345601).
- [ ] Launch the packaged application from a clean Windows environment without Python or developer tools installed; confirm the browser opens and the app remains usable.
- [ ] Create and edit a product, purchase, sale, and expense; verify stock, balances, profit, and cash movements against the entered values.
- [ ] Confirm data persistence after closing/reopening the app and test backup creation plus restore using a disposable database.
- [ ] Complete keyboard-only navigation, screen-reader checks, and 200% zoom on the packaged build.
- [ ] Check a narrow application window/small display for clipped forms, inaccessible actions, and unusable tables.
- [ ] Record any defects and retest fixes before owner acceptance. Do not merge this PR until the owner explicitly approves.

## Latest complete CI evidence — Run #897 (2026-11-09)

- [x] GitHub Actions [Run #897](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42633631270) completed with conclusion `success` on the exact PR head `836a67f64b0e5fdb62fd57568b19e97eebc4ac04`.
- [x] Both jobs passed: `smoke-test` and `windows-onedir`.
- [x] The smoke-test job passed compile, isolated smoke tests, browser UI matrix, browser finance/inventory workflows, keyboard/zoom accessibility proxies, Lighthouse + axe-core audit, and both report/screenshot uploads.
- [x] The Windows job passed cross-process token characterization, PyInstaller installation, Windows OneDir build, and artifact upload.
- [x] All three artifacts were uploaded for this exact head:
  - [Windows OneDir package](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42633631270/artifacts/13680779444)
  - [Lighthouse + axe-core reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42633631270/artifacts/13681988069)
  - [Browser UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42633631270/artifacts/13681368623)
- [ ] This automated success does not establish owner acceptance of the packaged Windows app, settle ACC-48/DEC-01, approve accounting-policy behavior, or authorize a database migration.

## Final owner acceptance — current candidate (Run #897)

The automated Windows OneDir build is not a substitute for launching and exercising the packaged application on the owner's own Windows machine. Complete these checks against the Run #897 artifact before accepting the candidate:

- [ ] Download and extract the [Run #897 Windows OneDir build](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42633631270/artifacts/13680779444).
- [ ] Launch the packaged application from a clean Windows environment without Python or developer tools installed; confirm the browser opens and the app remains usable.
- [ ] Create and edit a product, purchase, sale, and expense; verify stock, balances, profit, and cash movements against the entered values.
- [ ] Confirm data persistence after closing/reopening the app and test backup creation plus restore using a disposable database.
- [ ] Complete keyboard-only navigation, screen-reader checks, and 200% zoom on the packaged build.
- [ ] Check a narrow application window/small display for clipped forms, inaccessible actions, and unusable tables.
- [ ] Record any defects and retest fixes before owner acceptance. Do not merge this PR until the owner explicitly approves.

## Guardrails

- All test data must use isolated temporary storage; never point tests at a user's real business database.
- Do not merge this QA work into `main` without explicit authorization.
- Keep PR #41 on `fix/phase2-optional-form-defaults`, stacked on `test/phase2-service-loan-cash-postings` (PR #40); preserve the earlier phase branch and its Draft PR.
- Report automated and manual results separately. Do not mark manual items complete based only on CI.

## Latest complete CI evidence — Run #898 (2026-11-10)

- [x] GitHub Actions [Run #898](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42770410654) completed with conclusion `success` on the exact PR head `68a108108a9cbcf8397a050f2d5ab2561d728d6b`.
- [x] Both jobs passed: `smoke-test` and `windows-onedir`.
- [x] The smoke-test job passed compile, isolated smoke tests, browser UI matrix/screenshots, finance and inventory workflows, keyboard/zoom accessibility proxies, Lighthouse + axe-core audit, and report/screenshot uploads.
- [x] The Windows job passed cross-process token characterization, PyInstaller installation, Windows OneDir build, and artifact upload.
- [x] All three artifacts were uploaded for this exact head:
  - [Windows OneDir package](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42770410654/artifacts/13741283445)
  - [Lighthouse + axe-core reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42770410654/artifacts/13742090958)
  - [Browser UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42770410654/artifacts/13741791454)
- [ ] This automated success does not establish owner acceptance of the packaged Windows app, settle ACC-48/DEC-01, approve accounting-policy behavior, or authorize a database migration.

## Final owner acceptance — previous candidate (Run #898)

The automated Windows OneDir build is not a substitute for launching and exercising the packaged application on the owner's own Windows machine. Complete these checks against the Run #898 artifact before accepting the candidate:

- [ ] Download and extract the [Run #898 Windows OneDir build](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42770410654/artifacts/13741283445).
- [ ] Launch the packaged application from a clean Windows environment without Python or developer tools installed; confirm the browser opens and the app remains usable.
- [ ] Create and edit a product, purchase, sale, and expense; verify stock, balances, profit, and cash movements against the entered values.
- [ ] Confirm data persistence after closing/reopening the app and test backup creation plus restore using a disposable database.
- [ ] Complete keyboard-only navigation, screen-reader checks, and 200% zoom on the packaged build.
- [ ] Check a narrow application window/small display for clipped forms, inaccessible actions, and unusable tables.
- [ ] Record any defects and retest fixes before owner acceptance. Do not merge this PR until the owner explicitly approves.



## Latest complete CI evidence — Runs #899 and #901 (2026-11-10)

- [x] Push [Run #899](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42771282583) completed with conclusion `success` on exact head `59fe32844a7a77965d5468390d4a71dcb22a6ff9`.
- [x] Pull Request [Run #901](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42772179526) completed with conclusion `success` on the same exact head.
- [x] Both runs passed `smoke-test` and `windows-onedir`. The smoke-test job passed compile, isolated smoke tests, browser UI matrix, finance/inventory workflows, keyboard/zoom accessibility proxies, Lighthouse + axe-core audit, and report/screenshot uploads.
- [x] Both Windows jobs passed cross-process token characterization, PyInstaller installation, Windows OneDir build, and artifact upload.
- [x] Push Run #899 artifacts:
  - [Windows OneDir package](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42771282583/artifacts/13742221762)
  - [Lighthouse + axe-core reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42771282583/artifacts/13742147399)
  - [Browser UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42771282583/artifacts/13741499056)
- [x] Pull Request Run #901 artifacts:
  - [Windows OneDir package](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42772179526/artifacts/13742164135)
  - [Lighthouse + axe-core reports](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42772179526/artifacts/13742840372)
  - [Browser UI screenshots](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42772179526/artifacts/13741944411)
- [ ] These automated successes do not establish owner acceptance of the packaged Windows app, settle ACC-48/DEC-01, approve accounting-policy behavior, or authorize a database migration.

## Final owner acceptance — current candidate (Run #901)

The automated Windows OneDir build is not a substitute for launching and exercising the packaged application on the owner's own Windows machine. Complete these checks against the Run #901 artifact before accepting the candidate:

- [ ] Download and extract the [Run #901 Windows OneDir build](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42772179526/artifacts/13742164135).
- [ ] Launch the packaged application from a clean Windows environment without Python or developer tools installed; confirm the browser opens and the app remains usable.
- [ ] Create and edit a product, purchase, sale, and expense; verify stock, balances, profit, and cash movements against the entered values.
- [ ] Confirm data persistence after closing/reopening the app and test backup creation plus restore using a disposable database.
- [ ] Complete keyboard-only navigation, screen-reader checks, and 200% zoom on the packaged build.
- [ ] Check a narrow application window/small display for clipped forms, inaccessible actions, and unusable tables.
- [ ] Record any defects and retest fixes before owner acceptance. Do not merge this PR until the owner explicitly approves.


## DEC-01 — آزمون پذیرش سیاست مرجوعی خرید (شاخهٔ مستقل)

- [x] CI روی شاخهٔ `fix/dec01-purchase-return-valuation-ci` با هر دو Job موفق شد؛ Run #921 روی SHA دقیق زیر سبز است.
- [x] مرجوعی جزئی با ضریب تبدیل خرید، هزینهٔ جانبی و بهای تاریخی آزمون شد.
- [x] چند مرجوعی از یک خرید آزمون شد؛ تخصیص تجمعی، مجموع ارزش را دقیقاً با سهم برگشتی خرید برابر نگه داشت.
- [x] موجودی و میانگین بهای باقی‌مانده در هر مرحله با محاسبهٔ مستقل دستی تطبیق داده شد.
- [x] مرجوعی با ارزش بیش از ارزش دفتری، بدون درج سند یا گردش نقدی رد شد.
- [x] صفرشدن موجودی همراه با ارزش دفتری باقیمانده رد شد.
- [x] وجه نقد واقعی مستقل از ارزش مرجوعی کنترل شد.
- [x] ماندهٔ پرداختنی فروشنده پس از احتساب همهٔ خریدهای fixture، ارزش مرجوعی و وجه نقد دریافتی کنترل شد.
- [x] SQLite integrity و foreign_key_check موفق شدند.

**شواهد دقیق CI:** [Run #921](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42780798386) — head: `598cf95769454693ecd83adea3b2444c442cbf59`.

- [x] Job `smoke-test`: تست DEC-01، گردش مالی/انبار، ۱۴ مسیر axe بدون تخلف و ۱۰ گزارش Lighthouse موفق؛ امتیاز Performance و Accessibility در همهٔ گزارش‌ها ۱۰۰.
- [x] Job `windows-onedir`: تست cross-process و ساخت OneDir ویندوز موفق.
- [x] Artifactها بارگذاری شدند: [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42780798386/artifacts/13745593423)، [Lighthouse و axe](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42780798386/artifacts/13745788526)، [اسکرین‌شات UI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42780798386/artifacts/13745992758).

**مرز پذیرش:** CI و بازبینی عددی DEC-01 تکمیل شده‌اند؛ اجرای دستی بستهٔ Windows روی رایانهٔ مالک، صفحه‌خوان واقعی، بزرگ‌نمایی ۲۰۰٪، نمایشگر کوچک و backup/restore انسانی همچنان باز است. این موارد فقط با اجرای واقعی قابل علامت‌گذاری‌اند و مانع ادعای «پذیرش نهایی کل محصول» هستند.

### اجرای CI روی commit کد/تست PR #43 — Run #933 (2026-11-11)

- [x] اجرای Actions [#933](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42972259971) روی SHA دقیق `db491ae44689eafb07ceb6e7da5ab9a7abbec6a8` با conclusion برابر `success` تکمیل شد. Runهای #925 و #930 روی SHAهای قدیمی‌تر صرفاً سابقه‌اند.
- [x] هر دو Job موفق شدند: `smoke-test` و `windows-onedir`.
- [x] تست‌های Compile و isolated smoke، تست DEC-01، گردش‌های مالی/انبار، ۱۴ مسیر UI در دو viewport و دو theme (۵۶ تصویر)، و keyboard/zoom proxies روی ۷ مسیر موفق شدند.
- [x] axe-core هر ۱۴ مسیر را بدون violation ممیزی کرد؛ ۱۰ گزارش Lighthouse تولید شد. در هر ۱۰ گزارش Performance، Accessibility و Best Practices برابر ۱۰۰ و SEO برابر ۹۰ بود.
- [x] آزمون cross-process token روی Windows و ساخت PyInstaller OneDir موفق شدند.
- [x] Artifactهای همین اجرا: [Windows OneDir](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42972259971/artifacts/13834375833)، [Lighthouse و axe](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42972259971/artifacts/13834231424)، [۵۶ اسکرین‌شات UI](https://github.com/mohammad82xxz-ops/AhanModiriat/actions/runs/42972259971/artifacts/13834181543).

**یادداشت اصلاح تست:** اجرای #932 به‌علت انتظار نادرست تست برای ماندهٔ فروشنده fail شد؛ مقدار مورد انتظار، سه خرید fixture دیگر با همان نام فروشنده را لحاظ نمی‌کرد. انتظار تست به ۳۴٬۲۰۱ ریال اصلاح شد و اجرای #933 روی commit اصلاح‌شده با هر دو Job موفق شد.

**مرز پذیرش دستی:** این اجرا پذیرش روی رایانهٔ واقعی مالک را اثبات نمی‌کند. اجرای بستهٔ OneDir، صفحه‌خوان واقعی، zoom ۲۰۰٪، نمایشگر کوچک و backup/restore روی دیتابیس آزمایشی همچنان باز است؛ دیتابیس واقعی نباید در این آزمون استفاده شود.
