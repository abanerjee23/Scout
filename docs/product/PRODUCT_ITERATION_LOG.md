# Unloop — Product Iteration Log

**Build → Validate → Improve → Repeat**

Created: 28 September 2026  
Owner: Abhinav  
Updated: 7 October 2026  
Status: ITER-004 Phase 1A local implementation validated; Supabase/provider and Git publication gates pending

## Purpose

Capture how Unloop improves through evidence: what we expected, what we built, what happened, what we learned and what we changed. This is the ongoing record of product judgment for the project and its portfolio story.

[BUILD_PLAN.md](../../BUILD_PLAN.md) defines delivery phases and acceptance targets. This log records the iterations within them. A phase may need several cycles, and an iteration may revisit an earlier phase when new evidence exposes a problem.

## How we use the loop

1. **Frame:** identify one user problem or observed failure, state the hypothesis and choose a success measure before making the change.
2. **Build:** implement a bounded change and record the relevant version and reasoning. For the first cycle, establish a baseline rather than claim an improvement.
3. **Validate:** test the change against the chosen measure and relevant regressions. Record actual outcomes, failures and limitations with links to evidence.
4. **Improve:** decide to keep, revise, revert or defer the change. Explain the tradeoff and state the next experiment, if needed.
5. **Repeat:** link the next entry to this one. Stop iterating on this problem when the agreed acceptance criteria are met and material regressions are resolved; record any accepted limitations and what would cause us to revisit it.

“Get it right” means meeting explicit user-value and reliability criteria for the current scope. It does not mean indefinite optimisation or perfect performance on every possible input.

## Recording rules

- Create an entry at the start of every deliberate Build → Validate → Improve cycle, using sequential IDs such as `ITER-001`. Update it as the work proceeds; do not wait until the end of a phase.
- The assistant maintains the entries during implementation and includes the cycle result in the handoff. Abhinav supplies product judgment and feedback when needed. Routine logging requires no separate approval.
- Keep entries proportionate: a small correction may need a few sentences; a model or workflow experiment needs its comparison and evidence. Do not create an entry for every tool call or incidental edit.
- Preserve unsuccessful attempts, baseline results and superseded decisions. Append a follow-up rather than rewriting history to make an experiment look successful.
- Distinguish **observed**, **suspected** and **not yet tested**. Separate a synthetic test, Abhinav's own usability session and research with other users. None should be described as the others.
- Record before/after results on comparable inputs and conditions. If several things change together, say so and avoid attributing the gain to one change without evidence.
- Link to test reports, evaluation runs, trace IDs, screenshots or demos when available. Include relevant code, model, prompt, schema, dataset and policy versions; mark irrelevant fields as not applicable.
- Keep raw receipts, secrets and personal information out of this log. Reference authorised evidence rather than copying it here.
- Use development cases for tuning. A held-out failure may become a regression case, but record that exposure and replenish the unseen evaluation set before making a fresh generalisation claim.
- When a decision changes product behaviour, update the policy, vision, architecture or agent contract as appropriate and link the change here. This log explains the decision; the governing document defines the current behaviour.
- At a phase boundary, link its completed cycles and remaining issues in the build plan. Do not mark a phase complete merely because an iteration ended.

## Cycle index

The first cycle establishes the runnable foundation and labelled cases before live extraction.

| Cycle | Phase / user problem | Status | Decision | Evidence / next cycle |
|---|---|---|---|---|
| [ITER-001](#iter-001--runnable-foundation-and-meal-fixtures) | Phase 0 / make the first slice buildable and testable | Closed | Keep scaffold; its original auth next-action is superseded by ITER-002 | [Validation record](../validation/ITER-001_VALIDATION.md) |
| [ITER-002](#iter-002--workflow-reconciliation-and-document-organization) | Reconcile agreed workflow and organize docs | Closed | Revised persona/Gmail/partial-approval plan; no app feature implementation | [Docs validation](../validation/DOCS_UPDATE_VALIDATION.md) |
| [ITER-003](#iter-003--tested-baseline-and-phased-github-delivery) | Publish tested baseline and establish delivery cadence | Validating | Local baseline `5fa19ba`; publication/CI pending | [Delivery workflow](DELIVERY_WORKFLOW.md) |
| [ITER-004](#iter-004--confirmed-reports-in-isolated-demo-sessions) | Phase 1A / confirmed private reports | Closed (local); Supabase gate pending | Keep deterministic FastAPI/PostgreSQL slice | [Phase 1A validation](../validation/PHASE_1A_VALIDATION.md) |

Suggested statuses: Planned, Building, Validating, Closed, Blocked. A closed cycle records a decision; it does not necessarily mean the attempted change succeeded.

## Entry template

Copy this section below the template for each new cycle. Replace placeholders with facts; use “Not measured” or “Pending” where evidence is unavailable.

### ITER-NNN — Short description of the problem or experiment

**Date / phase:** [date and build phase]  
**Status:** [status]  
**Previous cycle:** [link or First cycle]

#### Frame — why this cycle matters

- **User problem or observed failure:** [specific behaviour and its consequence]
- **Hypothesis:** [what change should improve which outcome, and why]
- **Success criteria:** [metric, target and any regression constraints, chosen before validation]
- **Baseline:** [existing measurement or plan to establish one]

#### Build — what changed

- **Change:** [bounded implementation, prompt, policy or UX change]
- **Reason and tradeoff:** [why this option; cost, speed, reliability or user-control implications]
- **Version references:** [relevant code/model/prompt/schema/policy versions and evidence links]

#### Validate — what happened

**Method and sample:** [test type, dataset/version, case count, conditions and who reviewed it]

| Measure | Before | After | Target / interpretation |
|---|---|---|---|
| [Primary outcome] | [value or Not measured] | [value] | [met / not met and why] |
| [Relevant regression or tradeoff] | [value] | [value] | [interpretation] |

- **Failures and surprises:** [include adverse results, not just averages]
- **Evidence:** [links to results, traces or demonstration]
- **Limitations:** [sample size, synthetic data, exposed test cases, missing measurements or confounding changes]

#### Improve — what we decided

- **Decision:** [Keep / Revise / Revert / Defer]
- **Learning:** [what the evidence supports; label an unverified explanation as a hypothesis]
- **Next action:** [specific improvement or proceed to the next build task]
- **Revisit trigger:** [new evidence or condition that would change this decision]
- **Docs updated:** [links or Not applicable]
- **Next cycle:** [link when created, or None required for this problem]

## Current scope boundary

The log records engineering hypotheses, evaluations and decisions; it is not an AI correction-learning system. Automatic correction-to-eval ingestion, fine-tuning, memory and learning from user corrections are excluded. ITER-001 below remains a historical record of 29 September; its original Supabase-auth action and missing-service observations are not current design requirements or fresh connectivity checks. See ITER-002 for the 7 October decisions.

## Initial cycle scope

Phase 0 should establish the runnable scaffold and labelled Meal cases. Validate that the app starts and the fixture harness can represent receipt facts, policy-capped claims and missing-information outcomes. Record that result as the first cycle; extraction quality, user time savings and model cost remain unmeasured until the relevant implementation exists.

### ITER-001 — Runnable foundation and Meal fixtures

**Date / phase:** 29 September 2026 / Phase 0  
**Status:** Closed  
**Previous cycle:** First cycle

**Frame:** The project has design documents but no executable application or examples against which to check it. Hypothesis: a runnable React/Flask scaffold, explicit extraction schema and 24 labelled Meal fixtures will make the first expense flow implementable without more broad design work.

**Success criteria:** frontend typecheck/build pass; Flask health endpoint responds; all 24 cases validate with 12 development/12 held-out separation; malformed extraction states are rejected; local preview clearly distinguishes synthetic expected outcomes from actual AI output. No model accuracy or user-time target can be measured yet.

**Build:** React/Flask scaffold, health endpoint, checkable worker entry point, strict A1 Meal output schema, 24 labelled cases, source receipt transcripts and a renderer, synthetic receipt/claim preview, dependency locks and CI configuration. Preview labels and disabled upload/save distinguish expected outcomes from implemented workflows. The receipt-first layout follows the frontend-design skill: evidence next to the financial result, readable amounts and mobile layout.

**Validate:** 17 backend tests, 2 browser tests, all fixture integrity checks, Ruff and the frontend build passed. Live Flask health endpoint responded. Desktop/mobile screenshots inspected. Full results and commands are linked in [ITER-001 validation](../validation/ITER-001_VALIDATION.md). The first run found an incorrect fixture root; later checks/review found unsupported currency and misplaced VAT labels. All were corrected, including a VAT evidence regression check. No model runs occurred.

**Improve — Keep:** the scaffold meets Phase 0 criteria. Fixture preparation itself can contain unsupported labels; validating sources before evaluating a model prevents false quality conclusions. Store only relevant source facts and review evidence locations, not just numeric equality. No claim of improved AI quality is supported yet.

**Tradeoff:** the preview uses static expected examples and uniform generated receipts to allow early interaction review. This speeds feedback but provides no evidence of real extraction or photo robustness. Expand visual fixture diversity before Phase 2 model evaluation.

**Next action:** configure Supabase and build authentication/report/receipt persistence in Phase 1. All required external environment variables are absent in the inherited environment. Provider access and the exact Luna API identifier are unverified; credentials must be configured through secure setup, not pasted into chat.

**Revisit trigger:** failures in real receipt layouts, user confusion between original/claim values, or service integration constraints. Relevant targets for AI accuracy, cost and time saved remain unmeasured.

**Docs updated:** [Build plan](../../BUILD_PLAN.md), [README](../../README.md), [architecture status](../../Architecture.md), [A1 implementation note](../agents/Receipt_Extraction_Agent.md). Next cycle has not started.


### ITER-002 — Workflow reconciliation and document organization

**Date / phase:** 7 October 2026 / design maintenance before revised Phase 1  
**Status:** Closed  
**Previous cycle:** ITER-001

**Frame:** The full-version docs still required separate logins, excluded Gmail and required employee-led post-submission splits, conflicting with Abhinav's current decisions. Root supporting docs and stale diagrams made the current source of truth harder to find. Hypothesis: one reconciled set of root docs and grouped supporting contracts will make implementation follow the agreed workflow without losing history.

**Success criteria:** only BUILD_PLAN.md, Unloop_Vision.md, Architecture.md and README.md remain as root documentation; active links resolve; current docs agree on no app login/manager details, optional Gmail plus uploads, automatic expense opening, manager partial approval and excluded learning; prior originals remain recoverable; separate reference plan and application code remain unchanged.

**Build:** revised the vision/architecture/build plan/README; moved and reconciled A1, policy, iteration log and validation documents under docs; added Gmail integration design; archived exact prior documents and outdated PNG/SVG architecture diagrams with SHA256 manifest; replaced the active architecture map with Mermaid. Kept prior stack and detailed policy controls, real-integration gates and explicit human actions.

**Validate:** documentation structure/link/consistency checks and hash comparisons are recorded in [docs validation](../validation/DOCS_UPDATE_VALIDATION.md). This cycle performs no live Gmail, model, FX, database or Railway run and cannot validate those integrations.

**Improve — Keep:** active docs now agree on the current workflow and use the requested root/folder structure. Active relative links/anchors and archived checksums passed; application/fixture files and the external reference plan are unchanged. The cycle is complete as documentation maintenance, not as application implementation.

**Tradeoff:** active docs are consolidated around current behaviour; exact previous content remains in archive for historical detail and prior options. Manager release uses immutable approved subsets on the original report, removing a mandatory employee-created -1 report while preserving identities, totals and no-double-claim gates.

**Next action:** implement Phase 1 demo sessions, confirmed chat-created reports and shared manual/Gmail evidence intake. Reuse user-confirmed GCP setup for aban.hackathon@gmail.com, verifying callbacks and actual bytes in this application's environment.

**Docs updated:** [vision](../../Unloop_Vision.md), [architecture](../../Architecture.md), [build plan](../../BUILD_PLAN.md), [README](../../README.md), [A1](../agents/Receipt_Extraction_Agent.md), [policy](../policy/Synthetic_T&E_Policy.md), [Gmail](../integrations/GMAIL.md).

**Revisit trigger:** actual implementation evidence conflicts with session isolation, partial-release correctness, provider limits or usability. No calendar estimate, live integration success or achieved quality/savings is claimed by this docs update.


### ITER-003 — Tested baseline and phased GitHub delivery

**Date / phase:** 7 October 2026 / baseline publication before Phase 1  
**Status:** Validating  
**Previous cycle:** ITER-002

**Frame:** Abhinav requested build, test, commit/push to GitHub and repeat in phases. The full-version working directory was not a Git checkout, and the requested abanerjee23/UnLoop repository was empty. The hackathon's abanerjee23/Un-Loop repository is distinct and must not be overwritten.

**Hypothesis:** publishing the tested existing scaffold/current docs before feature implementation gives each subsequent increment a reproducible baseline and automatic CI feedback.

**Success criteria:** all scaffold checks pass locally; initialize the full-version checkout without touching the hackathon; exclude secrets/dependencies/generated artifacts; push the baseline to the requested repository; verify the published commit's GitHub Actions. Record provider gaps honestly.

**Build:** added the delivery workflow and linked the root plan/README; subdivided Phase 1 into session/report, evidence/jobs and Gmail increments without changing product scope. No runtime feature changes are included in the baseline.

**Validate:** pending baseline checks and publication. Current full-version inherited environment has no configured database/model/Galileo/FX credentials; this is not a live-integration check. GCP setup remains user-confirmed in the existing hackathon context.

**Decision:** pending local validation and CI.

**Next increment:** Phase 1A persona sessions and confirmed reports, with live PostgreSQL configuration needed before its persistence gate can pass.

### ITER-004 — Confirmed reports in isolated demo sessions

**Date / phase:** 7 October 2026 / Phase 1A
**Status:** Closed (local implementation); Supabase gate pending
**Previous cycle:** ITER-003

**Frame:** The employee cannot create or reopen a report. The synthetic workspace has no authoritative ownership or persona boundary.

**Hypothesis:** deterministic Astra intake, explicit header confirmation and server-owned persona sessions backed by PostgreSQL deliver a useful first report workflow without model cost or later-phase dependencies.

**Success criteria:** valid confirmed reports survive re-fetch and app restart; unconfirmed proposals create no report; dates include an explicit year; a second session and manager persona cannot access drafts; mutations require origin and session-bound CSRF protection; employee identity/grade remain server-seeded; baseline and new PostgreSQL/API/browser checks pass.

**Implementation decisions:** user explicitly requested FastAPI/Python instead of Flask. Preserve health/fixture/schema/preview capabilities while migrating the API/test harness. One implementation agent on `codex/phase-1a`, no worktree. Scope excludes uploads, Gmail, extraction, policy, FX, submission, approval, Teams and RAG.

**Baseline:** local scaffold checks passed (17 backend, 2 browser tests, Ruff, fixture integrity, worker check, build). Baseline commit `5fa19ba` establishes the previously uncommitted source. No Supabase connection is configured; disposable PostgreSQL validation is distinct from a Supabase integration claim.

**Validation:** 69 backend tests and seven browser tests passed against real local PostgreSQL, including isolation, spoofing/CSRF, explicit confirmation, concurrent retry, reload and actual Uvicorn-process restart. Ruff/build/24-case fixture/worker checks passed; desktop/mobile screenshots inspected. [Validation record](../validation/PHASE_1A_VALIDATION.md) distinguishes local checks from external gates.

**Improve — Keep:** bounded deterministic intake delivers the first real persisted workflow without model dependencies. The user-requested FastAPI migration preserves Phase 0 checks; synthetic Meal examples remain separate. No Phase 1B/1C functionality was implemented.

**Limitations / next gate:** Supabase connectivity is unverified because no connection was configured. Hosted CI/publication has not run. Configure/verify these gates before treating 1A as fully signed off or starting 1B. The local implementation cycle closes with these explicit delivery/provider limitations, not a complete Phase 1 claim.

### ITER-005 — Phase 1A date and database invariant hardening

**Date / phase:** 7 October 2026 / Phase 1A

**Status:** Closed (Cloud validation); hosted CI verification and Supabase gate pending

**Previous cycle:** ITER-004

**Frame:** Cloud review of PR #1 at `a020dbf` found mixed/incomplete dates silently discarded, SQL CHECK accepting employee null grade, and owner-only profile FK accepting a manager as report employee. Hypothesis: conservative date-signal validation and narrow database constraints close these gaps without changing the session/report workflow.

**Success criteria:** reviewed date probes ask for clarification; supported explicit-year inputs remain valid; actual PostgreSQL rejects null/non-C employee grade, manager report profile and foreign-owner profile; existing databases upgrade safely; fresh/upgrade/downgrade/re-upgrade metadata and all regression gates pass. Keep deterministic intake, FastAPI, no model write authority, no new phase features.

**Build:** one agent on existing tracking branch `codex/phase-1a`, no worktree. Added parser regression coverage, explicit non-null grade CHECK, fixed report employee-persona FK alongside existing owner FK, reversible `0002_phase1a_hardening`, readiness revision and actual PostgreSQL negative/backfill/rollback tests. Demo backfill repairs null grade to C and same-owner manager references to existing seeded employees; absent employee aborts atomically. Downgrade retains repaired values.

**Validate:** frozen sync, Ruff, **88 backend tests / zero skips**, 24-case fixture integrity / zero model runs, worker check, npm ci/build and **7 Chromium browser tests / zero skips** passed in restored Cloud using disposable native PostgreSQL. Existing cookie/report survives migration. Missing employee upgrade fails with version/schema/report intact. [Cloud hardening evidence](../validation/PHASE_1A_VALIDATION.md#cloud-phase-1a-hardening--7-october-2026) records commands, runtime and limits.

**Improve — Keep:** SQL null semantics and owner-versus-persona constraints need explicit negative database tests; passing API seeds alone did not prove those invariants. Deterministic intake conservatively asks for correction instead of discarding unsupported date signals. No extraction quality, model cost or provider integration is inferred.

**Remaining gate:** verify this increment's hosted CI (Cloud GitHub API returned Forbidden), and separately verify a securely configured non-production Supabase connection. Do not merge or start 1B/1C in this task. Protected build plan/fixtures/held-out separation remain unchanged; no prompt tuning or correction learning.

### ITER-006 — Prepare isolated opt-in Supabase persistence validation

**Date / phase:** 7 October 2026 / Phase 1A validation

**Status:** Closed — live Supabase gate VERIFIED at `8a88ac5eb3c1c41954f7a93654576df18a163e05`

**Previous cycle:** ITER-005

**Frame:** Cloud cannot directly reach the project's public PostgreSQL target through a supported exact TCP grant. Hypothesis: a branch-restricted, opt-in GitHub Actions job can validate live persistence using a privately supplied repository secret without moving the Cloud vault value or changing network infrastructure.

**Success criteria:** real FastAPI HTTP confirmation/list/re-fetch/restart/owner/manager/grade checks in a unique migrated schema; target and TLS fail closed; public cannot be the migration fallback; logs never expose credentials/exception strings; normal failure cleans only the new schema; local test mode cannot substitute for live-provider success.

**Build:** `scripts/supabase_smoke.py`, schema/TLS/timeout safety in existing helper, targeted guard/real-native-PostgreSQL tests and a restricted opt-in live job in existing `Checks` workflow. Only branch pushes after ordinary checks pass can use the secret; PR/fork/ordinary jobs cannot. [Concrete private setup/trigger instructions](../validation/SUPABASE_PHASE_1A_SMOKE.md) preserve the pending provider boundary.

**Validate:** standalone local smoke passes with explicitly non-provider output. Full **113 backend tests and 7 browser tests / zero skips**, frozen sync, Ruff, 24-case fixture integrity / zero model runs, worker check and npm ci/build pass. Tests cover real subprocess restart, normal failure cleanup, non-TLS rejection, wrong-schema migration refusal and suppressed child failure logs. Mocked target/failure guards are not provider evidence.

**Historical preparation decision (superseded by completion below):** live validation awaits user review, private repository secret and opt-in variable, then a harmless normal feature-branch push. No live schemas/data touched; no vault extraction/transfer, VPN/relay, merge, BUILD_PLAN/fixture changes or Phase 1B/1C work. The live Supabase gate remains UNVERIFIED until a recorded actual successful run.

## Verified live provider evidence — 7 October 2026

**VERIFIED** at exact commit `8a88ac5eb3c1c41954f7a93654576df18a163e05` on `codex/phase-1a`: [hosted push run 37652912234](https://github.com/abanerjee23/UnLoop/actions/runs/37652912234), [live job 112901079685](https://github.com/abanerjee23/UnLoop/actions/runs/37652912234/job/112901079685). At `2026-10-07T16:34:43.9015201Z` (17:34 Europe/London), the job emitted:

```json
{"status":"passed","mode":"live_supabase","project":"lchwjzunjqtakjdnzrze","tls":true,"migration":"0002_phase1a_hardening","http_restart_ownership_grade":true,"schema_cleanup":true}
```

Hosted backend **152 passed, zero skips** and Chromium **7 passed, zero skips**; Ruff, build, fixture integrity and worker checks passed. This proves synthetic isolated-schema persistence over client TLS, migration, explicit confirmation, list/re-fetch, process restart, ownership/persona/fixed-grade boundaries and cleanup against the live provider. It does not prove a deployed UI, production operation or public-schema migrations. Astra header intake remains deterministic; no live model was called. Phase 1B/1C are not implemented.

After success the owner set `RUN_SUPABASE_SMOKE=false`; the repository secret remains private. Subsequent documentation pushes intentionally skip the live job while ordinary CI runs. Earlier failures and local-only results below are historical evidence, not outstanding provider blockers. Deployment and its production configuration remain separate work; PR #1 stays draft and unmerged.

**Decision — Close ITER-006:** retain the bounded smoke and isolation checks; provider persistence gate is satisfied by the actual hosted run. No prompt tuning, correction learning, held-out changes or later-phase work occurred.

### ITER-007 — Shared retained evidence and recoverable validation jobs

**Date / phase:** 7 October 2026 / Phase 1B
**Status:** Verified and review approved; [PR #2](https://github.com/abanerjee23/UnLoop/pull/2) ready for parent merge. Verified 7 October 2026 at `599a391c009674d44dca9ad8275f4901ddb13031`: [hosted run 37673483432](https://github.com/abanerjee23/UnLoop/actions/runs/37673483432) passed **186 backend / 9 Chromium tests, zero skips**, and live Supabase job `112972061482` passed, including `evidence_bytes_dedup_restart_worker_recovery:true` and `schema_cleanup:true`. This proves synthetic isolated-schema provider persistence/restart/worker recovery; it does not prove Gmail, deployed UI/worker or production public migrations. Parent disabled `RUN_SUPABASE_SMOKE=false` after success.

**Hypothesis:** a shared chat/workspace pipeline with private retained originals, session-scoped deduplication and leased PostgreSQL validation jobs makes evidence reusable and recoverable before Gmail or AI integration.

**Acceptance criteria:** JPEG/PNG/PDF signature/MIME/validity/hash checks; limits 10 MiB/document, ten pages and ten files/batch; original-byte reopen; report/source provenance; no cross-session/manager access or existence leaks; employee origin/CSRF mutations; concurrent dedup; bounded attempts/leases/timeouts, stale-result refusal and interrupted-worker recovery; desktop/mobile honest queued/validated/failed/retry states; complete real PostgreSQL/backend/browser baseline passes. No extraction/claim is fabricated. Preserve BUILD_PLAN, fixtures, archive and held-out separation.


**Build:** one shared multipart pipeline; structural JPEG/PNG/PDF validation in bounded subprocesses; separate PostgreSQL bytes, owner/hash uniqueness and report/source provenance; revision-keyed jobs with three attempts, 30s leases and idempotent/stale-safe finishes; shared upload component and honest polling/retry/download states. No AI or expense amounts.

**Validate:** **182 backend / 9 Chromium passed, zero skips** with required native PostgreSQL and CI flags. Frozen sync/Ruff/24-case fixture integrity (zero model runs)/worker check/npm ci/build passed. Real worker OS-process exit after committed claim recovers in a new process; full provider script runs locally with real HTTP/worker/bytes/restart/cleanup assertions. Fresh/0002 upgrade/downgrade/re-upgrade/Alembic alignment pass. Desktop/mobile screenshots inspected. Earlier migration-table and multipart exception-boundary failures were corrected; final suites pass.

**Decision — Keep:** ordinary CI and the reviewed Phase 1B Supabase gate passed at the exact commit/run above; parent merge remains pending. Phase 1A live success is already verified and PR #1 merged. No Cloud provider secret/TCP, BUILD_PLAN/fixture/archive changes, correction learning, policy activation or paid work. Phase 1C and later remain unimplemented. Current handoff authority/evidence lives in [BUILD_STATUS](BUILD_STATUS.md).


### Lead-review follow-up — 7 October 2026

Upload authentication now uses a short unlocked read transaction before multipart intake, releases it before body receipt/validation, and acquires a fresh locking transaction only after the whole batch validates. Cookie/token, expiry, CSRF, employee persona and report ownership are checked again before dedup/bytes/links/jobs writes. Other Phase 1A routes retain their existing locking behavior. Multipart content-type errors now describe multipart intake correctly.

Delayed-validation regressions prove same-session reads and persona switching complete promptly; a persona switch or expiry during validation produces zero document/byte/link/job rows. Existing concurrent dedup tests remain. Targeted checks: four passed; full mandatory PostgreSQL suite with CI=true/GITHUB_ACTIONS=true: **186 passed, zero skips**; Chromium real API/PostgreSQL/worker suite: **9 passed, zero skips**; Ruff and diff whitespace checks passed. An initial test setup used the wrong persona route and violated the expiry ordering constraint; those test setup errors were corrected before the successful full run. Hosted/live follow-up passed at the exact commit/run above; earlier failures are historical.

### ITER-008 — Consent-bound Gmail evidence and early deployment packaging

**Date / phase:** 7 October 2026 / Phase 1C; branch `codex/phase-1c` from merged main `bb971287919639e0d1c3cba2876f841a9cdfba85`.

**Hypothesis:** a separately authorized, bounded report scan can retain Gmail attachments through the shared evidence pipeline without continuous mailbox access or weakening owner authority.

**Acceptance:** single-use session-bound OAuth; dedicated mailbox allowlist; encrypted versioned tokens and refresh/disconnect/expiry races; explicit revision/window/expiry-bound scans; bounded durable partial/retry/dedup/provenance; no DB locks during external work; employee/CSRF/origin ownership; honest disabled/denied/empty/partial UI; real PostgreSQL/browser regression and reversible aligned migration. Package same-origin FastAPI/React and separate worker for early Railway validation. Actual private credential/callback/consent/attachment and deployment proof remain parent-owned gates, not mock successes. No AI/policy/approval or Phase 2 features.


**ITER-008 validation/decision:** 226 backend / 10 Chromium passed, zero skips with mandatory native PostgreSQL; frozen sync/Ruff/24-case fixture integrity (zero models)/worker check/React build passed. Fresh/populated migration and downgrade/re-upgrade/metadata checks passed. Real OS-process scan crash/reclaim and original bytes/checkpoints proved locally with an explicit fake Google adapter. Lead-review truncation/stale-consent/token-format checks resolved. Keep the increment pending hosted CI and actual Railway/Gmail gates; no live provider claim or next phase. Exact runtime fields and dashboard settings are in [deployment handoff](../integrations/PHASE_1C_DEPLOYMENT.md). Phase 1B is merged in PR #2 at main `bb971287`.

Final packaging proof: non-root image served built React/assets; real FastAPI/native PostgreSQL upload plus a separate image worker validated bytes; originals survived web-container restart and unique schema cleanup completed. Callback privacy response assertions: eight targeted checks passed, 32 deselected (no skipped DB tests); final image smoke includes `no-referrer`. Worker CLI failure output is fixed/sanitized. Railway services remain offline setup only.

Lead-review follow-up: published `69f582abb4364f8f98cece00b9b2ab53c4476f76` passed hosted [run 37679353634](https://github.com/abanerjee23/UnLoop/actions/runs/37679353634), 226 backend/10 browser, zero skips; draft [PR #3](https://github.com/abanerjee23/UnLoop/pull/3). Live Supabase deliberately skipped. Narrow follow-up adds named inline MIME evidence via shared validation, actual client TLS flag enforcement, unlocked authority recheck between OAuth exchange/profile, and exact-origin guards. Fourteen focused regressions passed (40 deselected, zero skips); fake HTTP and native PostgreSQL remain offline proof. Private Railway credential fields are pending owner entry; services are offline, no live Gmail or deployment claim.

Follow-up complete mandatory PostgreSQL suite: **240 passed, zero skips**, one existing Starlette/httpx warning (82.59s); Ruff/diff checks passed. The inline persistence test was then strengthened and passed across two actual API OS processes (one passed, 53 deselected), without further application changes. No UI/image/migration changes or manual browser/image reruns; the initial hosted 10-browser/image evidence remains scoped to its tested commit. Follow-up hosted CI remains pending publication.

### ITER-009 — Saved Meal facts, bounded extraction and code-owned calculations

**Date / phase:** 7 October 2026 / Phase 2; stacked `codex/phase-2` from reviewed `2808bc06ad09e9bc00933295ea7b40e8448351bc`. Phase 1C remains unmerged/live-gated; its follow-up hosted [run 37681580232](https://github.com/abanerjee23/UnLoop/actions/runs/37681580232) passed backend/frontend, live Supabase deliberately skipped.

**Hypothesis:** authorized evidence can become a durable, correctable Meal candidate with locked human facts and contextual questions, while all model output remains untrusted and financial arithmetic/version/duplicate authority remains code-owned.

**Acceptance before building:** real PostgreSQL revisions, selected private bytes only, bounded Agents SDK `gpt-6-luna` output/reference validation, immutable suggestions and recoverable revision-safe jobs; correction/reload/duplicate/conflict behavior; Decimal full GBP/claim/excess and exact-date FX precedence; contextual receipt/field workspace and honest inactive/provider failures. Draft policy effective date/rounding and paid budget remain owner gates. Test candidate rounding only in explicit synthetic test configuration. No live credentials/calls, automatic model upgrade, held-out tuning, correction learning, A2/Phase 3+, submission or approval.
