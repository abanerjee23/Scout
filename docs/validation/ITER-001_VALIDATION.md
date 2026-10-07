# ITER-001 — Phase 0 validation record

Date: 29 September 2026
Scope: runnable scaffold, extraction output contract, labelled Meal fixtures and synthetic UI preview.

Historical evidence, moved on 7 October 2026. Results remain observations from 29 September, not fresh checks. Original auth/profile assumptions are superseded by the current [architecture](../../Architecture.md); nothing in this record proves the revised Gmail/persona/partial-approval workflow. Links below use current locations.

## Results

| Check | Result |
|---|---|
| Python dependency lock/install | uv.lock generated; Python 3.12.12 |
| Frontend dependency lock/install | package-lock.json generated; 72 packages audited, no known vulnerabilities reported at installation |
| Ruff | All checks passed |
| Backend tests | 17 passed in 0.15 seconds on final run |
| Fixture integrity | 24 cases validated; 12 development / 12 held-out; zero model runs |
| Worker entry point | --check succeeds; queue processing explicitly not implemented |
| TypeScript / Vite production build | Passed; 29 modules transformed |
| Playwright | 2 tests passed in 7.6 seconds; scenario selection, amounts, evidence toggle, disabled save, API failure and mobile overflow |
| Flask live HTTP smoke | GET /api/health returned 200 with service=unloop, status=ok, phase=scaffold, persistence=false |
| Visual review | Desktop 1280px and mobile 390px full-page screenshots inspected; no clipped controls or horizontal overflow observed |
| Synthetic image rendering | 13 unique development receipt PNGs rendered; duplicate-document scenarios are separate from image count |
| Credential presence | Supabase 0/3, OpenAI 0/2, Galileo 0/2, FX fallback 0/1 expected environment variables present; no secrets printed |

Browser health success/failure is stubbed in UI tests. The separate Flask smoke request verifies the real endpoint. Provider connectivity, auth, database persistence and model output have not been tested. The reported test timings are test-run duration, not product latency.

## Failures found and fixes

1. Initial fixture loader resolved one directory above the project. Fixed the root path. Four fixture tests initially failed; subsequent runs reached label validation.
2. Missing-total fixture incorrectly labelled GBP despite no currency evidence. Removed that unsupported label/reference; the expected result remains Needs information.
3. A VAT label matched the substring 4.00 inside a 24.00 total. Pointed it to the explicit VAT line and added a regression check rejecting VAT references to total lines.
4. Import formatting failed initial lint; applied Ruff formatting and verified again.
5. Sandbox restrictions blocked dependency-cache access, npm network access and local server binding. Approved escalated execution enabled those operations. Browser tests initially lacked the matching Chromium binary; installing it resolved the setup failure.

These are scaffold/data preparation fixes, not evidence of better model behaviour.

## Evidence files and reproducibility

- [Backend tests](../../backend/tests/)
- [Browser tests](../../frontend/tests/preview.spec.ts)
- [Fixture checker](../../backend/unloop/fixture_check.py)
- [Fixture guidance](../../fixtures/meals/README.md)
- [Desktop capture](../../artifacts/local/phase0-desktop.png) and [mobile capture](../../artifacts/local/phase0-mobile.png) are local generated evidence; rerun browser tests to regenerate them.
- [Run instructions](../../README.md)

Version references: project 0.1.0; A1 Meal schema 0.1; Meal dataset 0.1; policy remains draft 0.1. Dependencies are pinned by uv.lock and frontend/package-lock.json. No model or prompt version exists yet. No Git remote or hosted CI execution exists.

## Decision

Keep the scaffold and proceed to Phase 1. It provides a runnable starting point and detects inconsistent fixtures. User effort, extraction accuracy, production latency and model cost are not measured. Broader receipt-image variety, real model evaluation, trusted identity and storage remain future work.
