# Unloop — Phased Build Plan

Updated: 7 October 2026  
Owner: Abhinav  
Status: Phase 0 complete; revised Phase 1 next. This repository has a scaffold, not the implemented end-to-end product.

## 1. Milestone and agreed changes

First meaningful milestone:

**Employee mode → describe and confirm a report → upload or authorize Gmail intake → extract one Meal → clarify beside the expense → review/correct → convert to GBP if required → apply policy → save and reopen.**

Phases 1–2 deliver this. Air, Ground Transport, policy Q&A, explicit submission, manager partial approval, optional Teams context and the approved-data API remain in the fuller scope. The Employee/Manager toggle replaces app login/logout. Report creation no longer requests manager details. Correction learning is excluded. The manager directly controls partial release after submission; an employee-led linked-report split is not required for that action.

Sources of truth: [vision](Unloop_Vision.md), [architecture](Architecture.md), [synthetic policy](docs/policy/Synthetic_T&E_Policy.md), [A1 contract](docs/agents/Receipt_Extraction_Agent.md), [Gmail design](docs/integrations/GMAIL.md) and [iteration log](docs/product/PRODUCT_ITERATION_LOG.md). Previous documents/diagrams are historical snapshots in [archive](archive/README.md). The separate hackathon source plan remains reference-only and unchanged.

Use **Build → Test → Commit → Push → Check CI → Repeat** for delivery to [abanerjee23/UnLoop](https://github.com/abanerjee23/UnLoop). GitHub publication is the requested shipping step; Railway deployment is tracked separately. The [delivery workflow](docs/product/DELIVERY_WORKFLOW.md) defines smaller Phase 1 increments and the publication gates.

Within each increment use **Build → Validate → Improve → Repeat**. Record the hypothesis before each deliberate increment, its results and the decision afterwards. Do not claim provider integration from mocked calls or quality from fixture validation. Estimate later phases from actual early-phase effort rather than inventing calendar dates.

## 2. Phase overview

| Phase | Visible result | Completion evidence |
|---|---|---|
| 0 — Foundation | Runnable scaffold, synthetic Meal preview and labelled cases | Previously recorded local checks; no live receipt processing |
| 1 — Workspace and evidence | Persona toggle, chat-created reports, manual/Gmail intake and durable evidence | Session isolation, reload, consent, duplicate handling and recoverable jobs |
| 2 — First Meal flow | Evidence becomes a saved policy-capped claim with contextual clarification | Real extraction/FX, corrected-value preservation and quality/cost/latency baseline |
| 3 — Category coverage | Air, Meals and Ground Transport with supported assessments | Category corrections, grade/cabin rules and mixed-report cases |
| 4 — Policy assistance | Questions beside the report with inspectable sources | Held-out answer/citation results versus full-policy baseline |
| 5 — Submission and manager review | Both inboxes, line questions and full/partial approval; optional Teams context | Ten-line/one-dispute journey, resubmission and no stale or duplicate approvals |
| 6 — Hosted completion | Railway journey, approved-data API and portfolio demonstration | Hosted end-to-end checks, immutable approved releases, regression and measured limitations |

Deploy an early useful slice on Railway when it helps feedback; Phase 6 is the completion gate, not the first permissible deployment.

## 3. Phase 0 — Completed foundation

The React/TypeScript/Vite frontend and Flask scaffold, health endpoint, worker entry point, A1 Meal output schema and 24 labelled synthetic Meal cases are present. The historical validation recorded 17 backend tests and two browser tests. Twelve cases are development and twelve held-out; no model ran.

[ITER-001 evidence](docs/validation/ITER-001_VALIDATION.md) describes actual checks and limitations. Static preview amounts are expected outcomes, not extracted records. Reuse this foundation. Preserve held-out separation and add realistic image/PDF diversity before measuring extraction.

The earlier Phase 0 service checklist referenced Supabase Auth. That is historical; the revised build uses server-owned demo sessions and Supabase PostgreSQL. Existing GCP setup belongs to the separate hackathon project context; its Python/Railway integration remains to be demonstrated here.

## 4. Phase 1 — Workspace, report context and evidence

**Deliverable:** an isolated demo session can switch personas, confirm a report and retain evidence sourced through uploads or Gmail.

1. Implement a server-owned demo session with an opaque httpOnly cookie, expiry and predefined employee/manager identities. Validate ownership and role actions on the server; protect state-changing endpoints against cross-site requests. Seed a fixed employee grade, never an editable trusted-grade input. Do not build Supabase employee/manager sign-in.
2. Build Astra chat as the entry point, top persona toggle, report list/workspace and inbox entry. Intake proposes report name, explicit date range/year and business purpose. Validate and confirm the header before creation; omit manager-email inputs. Scope any natural-language parsing to those fields and do not give a model free-form write authority.
3. Add migrations for demo sessions/profiles, reports, expense revisions, documents/evidence provenance and background jobs. Introduce later entities when their phase needs them. Use Pydantic and SQLAlchemy/Alembic as implementation defaults unless a concrete issue appears.
4. Build JPEG/PNG/PDF uploads in both chat and workspace using one endpoint/pipeline. Start with documented candidate limits of 10 MiB/document, ten pages and ten files/batch; validate signatures, MIME, size/pages and hashing server-side. Store original bytes in PostgreSQL separately from listing rows. Deduplicate in the owning session without revealing another session's evidence.
5. Reuse the existing GCP project associated with **aban.hackathon@gmail.com**. Implement the Python OAuth adapter and the exact local/Railway callbacks; keep client secrets and token encryption keys on the server. Bind single-use OAuth state and encrypted connections to the owning session. Gmail consent is not an app login or manager credential.
6. Show the connected account, request explicit authorization for each bounded report scan, retrieve supported attachment bytes and preserve mailbox/message/attachment provenance. Describe the search window, including any booking lookback. Route imports through the upload pipeline; ambiguous report-date matches require review. Denied consent, revoked access, empty results and partially completed scans must leave a recoverable state. No background mailbox monitoring.
7. Add the PostgreSQL queue/worker with bounded attempts, leases, timeouts, revision checks and idempotent result writes. UI polls job status; partial scan/import results are visible. Worker recovery must not duplicate documents, expense candidates or inbox events.

**Done when:** both intake routes produce retained evidence; reload preserves report and connection state within session lifetime; another session cannot fetch it; manager mode cannot see unsubmitted drafts or Gmail credentials; retries do not create duplicate claims; denied/revoked/empty/partial Gmail results have accurate copy. Demonstrate a real authorized Gmail attachment retrieval, not only synthetic import or environment-variable presence.

**PM evidence:** sourcing actions, connection friction, recovery behaviour and a recorded working evidence journey. Public onboarding of arbitrary Gmail users is not a Phase 1 completion claim.

## 5. Phase 2 — First complete Meal workflow

**Deliverable:** a real Meal receipt becomes a corrected, stored and inspectable GBP claim.

1. Implement A1 with the OpenAI Agents SDK and a pinned available model. Retain Luna as the named design baseline until an actual API identifier is verified; do not assume product nicknames are model IDs. Pass only authorized evidence/context, validate structured output and references, and reject stale or unsupported values.
2. Persist AI suggestions/provenance against the expense revision. Preserve human-corrected fields and category/type overrides on reruns. Missing VAT stays blank/non-blocking. Unreadable evidence and unsupported categories have honest states.
3. Surface targeted questions in Astra chat and automatically open the affected expense, fields and receipt alongside the question. Keep a revisitable Open expense action and narrow-screen equivalent. A4 may improve wording later; deterministic question templates suffice here. Corrections invalidate dependent calculations/checks and are not collected for training or eval ingestion.
4. Instrument the first real model run with model/prompt/schema versions, outcome, latency, tokens and cost where available. The project-specific observability/eval baseline remains Galileo; pytest handles deterministic behaviour. Keep traces minimized/redacted and independent of authoritative records. No new observability stack migration is part of this documentation update.
5. Implement GBP-native arithmetic and Meal caps in code: £15 Breakfast, £25 Lunch, £50 Dinner. Retain full receipt totals including listed tips/service charges; calculate full GBP receipt value, claim and excess separately. Show Adjusted to policy limit with its governing clause.
6. Enforce one Meal per demo employee/date/type across session reports, including submitted and approved history when Phase 5 arrives. Exact duplicate uploads do not consume new claim slots. Let the employee choose which conflicting candidate to retain; never pool smaller receipts to fill an allowance.
7. Add historical FX: reuse acceptable observations, then Frankfurter pinned to ECB, then Open Exchange Rates under the agreed fallback rules. Validate requested/returned date and preserve provider/rate metadata. GBP-to-GBP needs no provider. Wrong-date, weekend/holiday or unpublished same-day observations stay Conversion pending unless a different convention is explicitly agreed.
8. Store current facts, locked human fields, FX observation, applicable policy version, claim/excess and calculation revision. Reload reads saved results; relevant edits trigger only necessary rechecks. Run the held-out Meal cases after baseline measurement and record failures by category.

**Decisions due here:** synthetic policy effective date, GBP rounding and actual runtime budgets. Candidate file limits from Phase 1 must be confirmed against examples. Rounding uses decimal arithmetic; no binary floating-point money.

**Done when:** £62 Dinner persists as receipt £62/claim £50/excess £12; within-limit claims remain unchanged; ambiguous meal type opens its expense with a question; foreign currency retains both original and full GBP values; real primary and fallback conversions are demonstrated; correction/reload and uncertainty handling pass release gates.

## 6. Phases 3–4 — Categories and policy help

### Phase 3 — Category coverage and assessment

Define Ground Transport eligibility/caps/charge treatment in reviewed clauses before enabling its assessment; no-cap behaviour has not been agreed. Extend extraction/UI to Air One-way/Return and Ground Transport Public transport/Taxi. Ground Transport route absence does not block.

Map cabin labels and normalize airport/city representations against fixtures. Load server-seeded grade and enforce the maximum cabin table in code; missing grade pauses, unsupported cabin declarations cannot pass. Category correction deactivates old fields, creates a revision and reruns applicable checks.

Implement the approved source registry, immutable policy versions and required-rule checklist. A2 receives validated facts, trusted attributes and deterministic findings; it explains supported outcomes but cannot change amounts, waive rules or approve. Keep missing facts, clear violations, missing coverage, technical failure and genuine policy ambiguity separate. The last may create a visibly simulated T&E inbox item.

**Done when:** mixed reports work; grade/cabin, category-change, multi-document evidence and Meal uniqueness cases pass; every supported finding has valid clauses; unresolved checks cannot become permission.

### Phase 4 — In-context policy Q&A

Prepare reviewed policy/FAQ snapshots with source identity, version and precedence. Build clause-aware ingestion/pgvector retrieval, with pinned embedding configuration and source/access/version filters. Use the agreed small embedding baseline; compare alternatives only on measured gains.

Implement A3 for general or expense-linked questions, sharing policy access with A2. Show answer, supporting passages and policy version beside the report. Clicking a referenced line opens that expense; Astra clarifications continue to open it automatically. A2 retains its required-rule checklist/core policy text so top-k retrieval cannot omit a restriction silently.

Evaluate RAG against full-policy context on held-out direct, paraphrased, multi-source, outdated/conflicting, unsupported and malicious-source questions. A policy answer never changes facts or approval status.

**Done when:** supported answers/citations meet gates, critical false permission is blocked, and retrieval outages produce recoverable guidance-unavailable states.

## 7. Phases 5–6 — Decisions and hosted completion

### Phase 5 — Submission, inboxes and manager partial approval

1. Add explicit employee submission with a server eligibility gate and versioned submitted line set. Preview eligible subset versus wait when draft lines are unresolved. Only submitted snapshots enter manager visibility; retained draft lines stay private to employee mode.
2. Write submission and inbox events transactionally. Employee confirmation and manager review item identify the same submission version, lines and claim total. Add line-specific manager questions, employee responses, corrections, rechecks and explicit resubmission of material changes.
3. Implement manager approve-all or selective release with an explicit line/amount preview. Holding/returning a line does not block another eligible selected line. This is manager discretion after submission; do not require an employee-created `-1` report. Held and returned have distinct next actions.
4. Store immutable approval-release snapshots and idempotency keys, preserving stable expense IDs and claimed portions. A partially approved report remains open for unresolved lines and shows separate approved/pending totals. Protect against stale versions, double approval and modification of approved facts. Create processing-ready records once per approved release; do not simulate payment as completed.
5. Implement A4 focused question/context drafting without sending authority. Optional Teams launch uses explicitly configured demo participant identities; no manager field is added to report creation. A person reviews/sends context and records resolution. Missing Teams configuration provides in-app/copyable context; a fallback alone is not proof of a tested launch.

**Done when:** a ten-line submission can approve nine while one stays held/returned; inboxes state exact outcomes; the tenth can be corrected, resubmitted and separately approved; repeated clicks/concurrent requests cannot approve stale data or duplicate processing. Manager mode cannot inspect unsubmitted corrections, other sessions or Gmail tokens. A real Teams launch is demonstrated if included in the hosted feature claim.

### Phase 6 — Approved-data API, Railway and portfolio proof

Finalize a read-only API for approved release snapshots, with stable report/expense/release IDs and approved revisions. A partially approved report exposes only approved lines and their claim totals; later release adds a separate stable snapshot. Exclude pending amounts, receipts, Gmail credentials, policy explanations and internal conversations/history. Use server-side downstream access credentials independent of the persona toggle. Demonstrate repeat reads and deduplication; no ERP receiver is required.

Deploy Flask serving built React and a worker from the same codebase on Railway against Supabase PostgreSQL. Configure HTTPS OAuth callbacks, server secrets, migrations, health/worker diagnostics and recovery. Verify real Gmail, uploads, extraction, both FX adapters, contextual policy help, submission, manager partial approval and API access in the hosted environment. Recheck session isolation, consent, token refresh/revocation, stale jobs and source versions.

Run final held-out regression, record cost/latency and compare active user time on matched manual/Unloop tasks. Demonstrate a measurable iteration with baseline/change/result and disclose synthetic inputs, simulated specialist handling and remaining limitations. Provide run instructions and a portfolio case study focused on judgment and evidence.

**Done when:** a reviewer can open/run the hosted app, complete the core journey and inspect evidence; approved releases are stable and recoverable; remaining unmet critical gates are recorded as blockers rather than hidden by synthetic success.

## 8. Evaluation and release gates

| Measure | Proposed initial target |
|---|---|
| Money, caps, totals, access, versions and duplicate-claim prevention | All labelled deterministic acceptance cases pass |
| Critical financial facts | No silently accepted wrong/invented amount, currency or receipt date in the held-out release set |
| Required-field accuracy | At least 95% exact/normalized match on supported readable held-out examples; report numerator/denominator |
| Appropriate pauses/useful output | All labelled missing/unreadable/ambiguous cases pause; at least 90% of readable complete cases are reviewable without re-entering supported required facts |
| Policy answers and citations | At least 90% fully correct supported answers; zero false permission in designated critical cases |
| Active preparation time | Target at least 30% reduction on matched tasks; include sample size and failed attempts |
| Latency | Provisional p95 under 30 seconds per upload-to-reviewable receipt and under 15 seconds per policy answer; separate hosted/local results |
| Cost | Measure per receipt, question and completed report; fix budget after baseline and before bulk experiments |

Freeze gates before tuning. Include missing VAT, tips, caps, duplicate/contradictory documents, category corrections, locked human fields, foreign currency, wrong-date FX, unreadable pages and receipt/policy prompt injection. Add Gmail consent/scan failures, cross-session access, partial imports, manager partial release, returned-line resubmission and concurrent approval cases. The small starting set is not evidence of population-level reliability.

Development and held-out fixtures remain separate. If a held-out failure is used for tuning, record exposure and replenish unseen cases. Engineering may add synthetic regression cases; automatic collection/learning from users' corrections remains excluded. Compare stronger models only after diagnosed errors justify an experiment; record quality, latency and cost, with no automatic model upgrade to force success.

## 9. Progress, remaining choices and boundaries

| Phase | Status | Evidence/next action |
|---|---|---|
| 0 | Complete | [Historical validation](docs/validation/ITER-001_VALIDATION.md): scaffold, schema and labelled cases only |
| 1 | Not started | Build sessions, confirmed report creation and shared evidence intake |
| 2–6 | Not started | Deliver and validate in sequence above |

[ITER-002](docs/product/PRODUCT_ITERATION_LOG.md#iter-002--workflow-reconciliation-and-document-organization) records this documentation reconciliation. It does not count as Phase 1 completion. User-confirmed GCP setup and hackathon code are references; no live service has been newly tested in this full-version repository by updating docs.

Resolve exact model IDs, limits, schema details and budgets during Phases 1–2; policy effective date/rounding before authoritative assessment; Ground Transport rules/cabin mappings in Phase 3; source applicability in Phases 3–4; precise held/returned labels and release DTO in Phases 5–6. These do not reopen agreed persona, Gmail/upload, clarification or manager-control decisions.

Out of scope: correction learning/training, accommodation, continuous mailbox monitoring, universal supplier/card intake, price intelligence, external notifications, Teams reading/automatic sending, actual specialist adjudication, manager policy overrides, real payment/ERP posting and production multi-user authorization. Future public Gmail access needs ownership and Google readiness work described in [Gmail design](docs/integrations/GMAIL.md).


## 10. Authorized delivery cadence

Publish a tested baseline first, then implement Phase 1 in demonstrable increments: 1A persona sessions/confirmed reports with PostgreSQL persistence; 1B shared uploads/evidence/jobs; 1C consent-based Gmail. Build and validate each, commit/push to the full-version GitHub repository, check CI and repeat. Complete a phase only when its live acceptance gates pass. Keep the separate hackathon repository and external reference plan unchanged.
