# Unloop — Phased Implementation Plan

Updated: 29 September 2026  
Owner: Abhinav  
Status: Phase 0 complete; Phase 1 next. Scaffold and synthetic preview implemented; live services remain unconfigured.

## 1. First milestone and working approach

The first milestone is a working Meal expense flow:

**Sign in → create a report → upload one receipt → extract facts → review/correct → convert to GBP where needed → apply the meal allowance → save and reopen the expense.**

Complete this milestone through Phases 0–2. Air, Ground Transport, policy Q&A, manager approval, Teams and the approved-data API remain in the full POC and follow in later phases. Starting with Meals is a build sequence, not a reduction of the agreed product scope.

Build one demonstrable increment at a time. Each phase ends with a working demonstration, relevant checks and a short record of what we learned. Resolve a product decision when its implementation phase needs it; routine schema, library and layout choices can be made during implementation and recorded. Do not reopen the architecture without evidence that an agreed choice prevents progress.

Within every phase, use **Build → Validate → Improve → Repeat** and record each deliberate cycle in [PRODUCT_ITERATION_LOG.md](PRODUCT_ITERATION_LOG.md). Capture the hypothesis before the change, the validation evidence and the decision afterwards. A phase may contain several cycles; proceed when its acceptance criteria are met, retaining unsuccessful experiments and known limitations.

Sources of truth:

- [Product vision](Unloop_Vision.md): users, problems and intended behaviour.
- [Architecture](Architecture.md): components, responsibilities and integration boundaries.
- [Synthetic policy](Synthetic_T&E_Policy.md): rule values, evidence requirements and policy clauses.
- [A1 contract](Receipt_Extraction_Agent.md): receipt extraction inputs, outputs and failure handling.
- [Product iteration log](PRODUCT_ITERATION_LOG.md): cycle-by-cycle hypotheses, changes, results, tradeoffs and next experiments.
- This plan: implementation order, phase deliverables and completion evidence.

## 2. Phase overview

| Phase | Visible result | Completion evidence |
|---|---|---|
| 0 — Prepare to build | A scaffold, labelled Meal examples and a runnable test harness | Local app starts; first test cases and acceptance targets are recorded |
| 1 — Identity, reports and receipts | Employee signs in, creates a named report and attaches evidence | Data survives reload; unauthorised access is rejected |
| 2 — First Meal workflow | A real receipt becomes a saved, policy-capped claim | Extraction, FX, correction and cap tests pass; baseline quality/cost/latency recorded |
| 3 — Air, Ground Transport and assessment | One report can contain all three supported categories | Category and policy cases pass; A2 explains supported findings |
| 4 — Policy help inside the report | Employee can ask policy questions with inspectable sources | Held-out answers and citations evaluated against a full-policy baseline |
| 5 — Manager review and clarification | Two people submit, question, discuss, split and approve | Ten-line/one-dispute journey works without duplicate claims or implicit approvals |
| 6 — Approved-data API and portfolio demo | Hosted POC exposes approved claims and demonstrates all three user benefits | API, hosted integration checks, regression results and a recorded demo |

No calendar estimates are claimed yet. Record actual time during Phases 0–2 and use that evidence to estimate later work.

## 3. Phase 0 — Prepare to build

**Deliverable:** a small application scaffold and a testable definition of the first Meal workflow.

1. Scaffold a single repository with `frontend/` for React and `backend/` for Flask plus a worker, alongside migrations, tests and synthetic fixtures. Use TypeScript/Vite, Pydantic, SQLAlchemy/Alembic and pytest as implementation defaults unless a concrete incompatibility appears.
2. Add dependency lockfiles, environment-variable examples without secrets, local run instructions and a basic CI check for tests and the frontend build. Inspect existing Git state before initialising version control.
3. Check access to the selected services. Supabase is needed for Phase 1; an exact available Luna API model and Galileo are needed for Phase 2; FX provider credentials are needed for the fallback integration. Record the actual model identifier rather than assuming a product nickname is an API identifier. Verify current SDK/provider interfaces when implementing each adapter.
4. Create 24 synthetic Meal cases: 12 development examples and 12 held-out examples. Label expected facts, missing information, evidence references and claim outcomes before tuning. Cover the cases in section 11; keep held-out examples out of prompt-development material.
5. Turn A1's existing field contract into an executable schema for the first slice. Keep the wider category enum, but clearly mark Air and Ground Transport processing as coming in Phase 3. Choose and document bounded file/page limits as implementation settings.
6. Sketch only the first screen: report header, upload, expense fields, receipt viewer and the original/GBP/claim amounts. Implement the layout during Phase 1; a complete wireframe programme is not a prerequisite.

**Done when:** the local frontend and Flask health endpoint run, the test harness reads the labelled cases, and external setup dependencies are recorded precisely. Missing credentials can delay their integration test while local schema and calculation work continues; simulated calls must be labelled and cannot count as a completed integration.

**PM evidence:** first-slice hypothesis, example inputs, expected outcomes and baseline measurement method.

## 4. Phase 1 — Identity, reports and receipt storage

**Deliverable:** a signed-in employee can create a report, upload a receipt and return to both later.

1. Connect Supabase Auth and verify authentication server-side. Seed employee and manager test identities plus server-controlled employee grades. A user's editable email or form input must not grant a role or grade.
2. Add migrations for profiles, reports, expenses/revisions, documents/evidence links and background jobs. Add other entities only in the phase that uses them. Preserve the money-field distinctions in section 10.
3. Build report creation with required name, business purpose and manager email. Capture the recipient now; the manager workflow arrives in Phase 5.
4. Store original receipt bytes in PostgreSQL, separate from report-list rows. Validate file type, size and page limits, identify exact duplicate uploads and serve evidence through authorised endpoints.
5. Build the report list, draft report, upload control and receipt viewer. Show clear upload/processing/failure states; a failed extraction must leave the uploaded evidence recoverable.
6. Add the PostgreSQL job queue and worker with bounded attempts, leases, revision checks and idempotent completion. The UI polls job status. Test worker recovery with a lightweight test job before adding model calls.

**Done when:** a report and receipt survive sign-out/reload; another employee cannot read them; the manager cannot view the unsubmitted draft; retrying an upload does not create a second expense; an interrupted job can recover without duplicate output.

**PM evidence:** a short demonstration of the actual report/evidence experience and its failure states.

## 5. Phase 2 — Complete the first Meal workflow

**Deliverable:** a real model reads a Meal receipt and the employee saves a correct, reviewable claim.

1. Implement A1 through the OpenAI Agents SDK using the verified Luna baseline. Validate structured output and evidence references. Preserve unsupported or ambiguous facts as missing; absent VAT remains blank and non-blocking.
2. Persist suggestions with their document references and expense revision. Allow category and meal-type correction, ask targeted factual questions and preserve human corrections on reruns. A correction to Air or Ground Transport is saved but clearly waits for Phase 3 support.
3. Add Galileo instrumentation from the first model run: model/prompt/schema version, run outcome, latency, tokens and cost where available. Redact sensitive payloads; trace failure must not corrupt a saved expense. Use synthetic receipts during development.
4. Implement and test GBP-native amounts and Meal caps first. Use policy configuration for Breakfast £15, Lunch £25 and Dinner £50; include receipt-listed tips/service charges within those limits. A1 preserves the full receipt total. Code calculates the claim and excess, then shows **Adjusted to policy limit** with a clause-linked explanation. A deterministic explanation template is sufficient in this first slice.
5. Enforce one restaurant receipt per employee, receipt date and meal type across claimable expenses. Do not pool several smaller receipts. Let the employee select which expense to retain when there is a conflict. Duplicate images of one receipt do not become additional claims. Excluded expenses release the claim slot; later approval must preserve it across reports.
6. Add historical FX: reuse valid saved observations, then Frankfurter/ECB, then the agreed Open Exchange Rates fallback. Validate the actual returned date against the receipt date. Preserve both the full original amount and full GBP equivalent, and apply the GBP cap only after conversion. A missing or wrong-date rate produces **Conversion pending**.
7. Save the current receipt facts, FX observation, applicable policy version, claim and excluded amount. Reopening the expense reads stored results without rerunning extraction or fetching a new rate. Relevant edits invalidate stale calculations and trigger the required rechecks.
8. Run the held-out Meal set and fix failures by category. Record the initial baseline before prompt changes. Demonstrate at least one real primary-provider conversion and one real fallback-provider conversion; use controlled failures separately to test retry and pending states.

**Decisions needed only for this phase:** approve a synthetic policy effective date and a GBP rounding convention before calling assessments authoritative. Until another date convention is agreed, weekends, holidays and unpublished same-day rates remain pending under the current exact-date rule. These cases do not require a new provider or a daily FX agent.

**Done when:** a £62 Dinner receipt saves with receipt amount £62, claim £50 and excess £12; a within-limit receipt remains unchanged; ambiguous meal type prompts a question; a USD example retains USD and full GBP values before capping; correction and reload work; no required fact is fabricated to finish the demo. The phase acceptance targets in section 11 are met or any unmet target is explicitly recorded as a release blocker.

**PM evidence:** first real product demonstration, extraction error analysis, quality/latency/cost baseline and measured review effort. This is the first milestone worth recording for the portfolio.

## 6. Phase 3 — Complete category coverage and policy assessment

**Deliverable:** employees can prepare Air, Meals and Ground Transport in one report with supported policy findings.

1. Finalise only the Ground Transport rules needed here. Taxi/Public Transport business eligibility, caps and charge treatment remain product decisions; the earlier suggestion of no cap has not been approved. Add reviewed clauses before assessing those expenses.
2. Extend A1 and the UI for Air One-way/Return, the agreed route/date/cabin fields, and Ground Transport Public transport/Taxi. Ground Transport origin/destination remain optional. Inapplicable fields are greyed out and excluded from active checks/export.
3. Resolve Air normalisation and cabin-label mapping through representative fixtures. Run the grade-to-maximum-cabin comparison in code: A–C Economy, D–F Premium Economy, G Business. Missing trusted grade pauses assessment; unsupported cabin self-declaration cannot satisfy the check.
4. Implement the policy source registry, versioned rule configuration and required-rule checklist. This short core policy can be supplied directly before retrieval is introduced in Phase 4.
5. Define and implement A2's schema: supported finding, governing clauses, missing facts and concise explanation. Supply validated facts, trusted attributes and deterministic results. A2 cannot change the arithmetic, waive a rule or approve an expense.
6. Add distinct handling for missing facts, clear violations, missing policy coverage, technical failure and genuine policy ambiguity. The last may produce the explicitly simulated T&E handoff; no real specialist workflow is created.
7. Expand labelled development and held-out cases for Air, Ground Transport and mixed reports. Include category correction, multi-document Air evidence, profile gaps and the Meal uniqueness rule across reports. Preserve previously approved claim slots when approval is introduced in Phase 5.

**Done when:** a mixed-category report is prepared correctly; Air grade/cabin cases pass; Ground Transport route absence does not block; category changes cannot leak stale fields; A2 cites valid clauses and cannot turn an unresolved issue into permission.

**PM evidence:** category-level quality results and a written example of why a fixed rule belongs in code while interpretation/explanation may use AI.

## 7. Phase 4 — Policy Q&A in context

**Deliverable:** the employee can understand policy beside the report with visible source evidence.

1. Prepare a small reviewed policy/FAQ source set and expected answers. Preserve clause IDs, source versions, precedence and applicability metadata in PostgreSQL.
2. Build clause-aware ingestion and pgvector retrieval using the agreed embedding baseline. Pin the embedding configuration, validate retrieved source permissions and version filters, and activate a complete index together with its source set.
3. Define and implement A3 for general and expense-linked questions. Return a concise answer, supporting passages and source identifiers, or a targeted clarification/explicit inability to answer.
4. Build the policy side panel and **Open expense** action beside expense-linked questions. A policy answer must not edit facts, change a compliance result or approve a claim.
5. Share source access and retrieval with A2 while retaining its required-rule checklist and core text. A search result alone is insufficient evidence that every applicable restriction has been checked.
6. Compare RAG with a full-policy-context baseline on the same held-out questions. Cover direct rules, paraphrases, conflicting/outdated sources, missing information, absent rules and malicious instructions in source text.

**Done when:** answers and citations meet the frozen evaluation targets; unsupported permission is blocked in the release cases; the user can inspect the supporting clause without leaving the report; retrieval failure produces a recoverable state. After Phase 5, confirm the manager has the same panel only for reports they may view.

**PM evidence:** measured retrieval/answer quality and a reasoned decision about whether retrieval improves this corpus enough to justify its use. Do not claim success merely because vector search runs.

## 8. Phase 5 — Manager review, clarification and report splitting

**Deliverable:** the employee and manager can resolve a line-specific question and progress undisputed expenses.

1. Define the remaining workflow contract immediately before implementation: short UI labels, repeated split suffixes and the manager's access to previously submitted follow-up evidence versus unsubmitted corrections. Keep the report's manager fixed.
2. Implement explicit employee submission and a server-enforced eligibility gate. Only submission puts a report in the authenticated manager's inbox and starts approval tracking on the employee dashboard.
3. Add line-linked questions, the employee inbox, **Open expense**, response recording and explicit manager resolution. Asking a question does not reject the whole report. Both personas can consult the Phase 4 policy panel.
4. Implement A4 to draft clarification and Teams opening context using Unloop records. Launch a user-reviewed Teams deep link to the other report participant. Test with two actual test identities; a copyable-context fallback is useful but is not proof that Teams integration works. Unloop never reads chat or infers that a launch means a message was sent.
5. Implement **Wait for resolution** and **Submit undisputed lines** with a preview. Move pending expenses atomically to the linked `-1` report, retaining their identities and evidence. Recalculate claim totals and require manager approval of the exact revised original report.
6. Add immutable approval snapshots, revision checks and idempotent submit/split/approve commands. Preserve Meal uniqueness across drafts, submitted reports and approved history so a closed report cannot be used to reclaim the same meal.
7. Include the pre-submission split path for unresolved lines and the simulated specialist inbox item. A pending follow-up stays open until separately resolved, submitted and approved.

**Done when:** the ten-line report/one-question scenario works in two sessions; the original closes with nine lines only after explicit approval; the linked follow-up retains the tenth; retries and concurrent split/approval cannot duplicate expenses or approve stale data. Teams remains private and a human explicitly records the outcome.

**PM evidence:** time/actions needed to ask and resolve a question, progress of undisputed claims and proof of the two-persona access boundary.

## 9. Phase 6 — Approved-data API, hosting and portfolio demonstration

**Deliverable:** a hosted, reproducible POC and evidence of what it achieves.

1. Finalise the approved-data schema and implement authenticated read endpoints. Export stable report/expense IDs, approved financial fields and approved claim totals. Pending follow-ups, receipts, policy explanations and internal workflow history remain outside that response.
2. Demonstrate the API with a saved example request/response. Verify that repeated reads return the same approved identity/version and that receipt value cannot be mistaken for the reimbursable claim. No ERP receiver is required.
3. Deploy the Flask/React web service and worker on Railway against Supabase. Configure server-side secrets, migrations, health checks and basic worker diagnostics. Deployment may happen earlier for feedback; this phase is the hosted-demo completion gate.
4. Exercise the complete journey in the hosted environment, including real extraction, both FX adapters, policy retrieval, Teams launch, split/approval and API access. Recheck relevant authentication, job recovery, source-version and stale-result cases.
5. Run the final held-out regression set, measure representative latency/cost and record remaining failures. Capture active user time separately from system waiting time and receipt sourcing, using matched manual and Unloop tasks.
6. Prepare a concise portfolio case study and demo: user/problem, why AI, scope/tradeoffs, architecture, baseline results, one measured improvement, unresolved limitations and next iteration. Mark synthetic inputs and the simulated specialist handoff visibly. Include run instructions and a known-limitations list.

**Done when:** a new reviewer can run or open the demo, complete the core journey, inspect an approved-data API response and see measured results. A working synthetic POC is the release claim; production readiness remains a separate future assessment.

## 10. Financial and workflow invariants

These apply throughout implementation and are tested in the phase that introduces them.

| Value or rule | Required behaviour |
|---|---|
| Receipt amount and currency | Preserve source values; a policy cap never overwrites them. Correct extraction mistakes through a new recorded revision |
| Full GBP receipt value | Persist the full converted value, FX observation and receipt-aligned conversion date |
| Claim amount in GBP | Apply the allowed cap in code; employee review and manager approval remain separate actions |
| Amount above policy limit | Calculate the excess over the cap. If a user voluntarily claims less, track that reduction separately; it is not additional policy excess |
| Report total | Sum eligible stored GBP claim amounts; never mix currencies or include excluded excess |
| FX date | Validate actual provider date against receipt date; missing acceptable rates remain pending |
| Meal allowance | Breakfast £15, Lunch £25, Dinner £50, including receipt-listed tips/service charges |
| Meal receipt rule | One claim per employee/date/meal type; a spending limit cannot be filled with multiple restaurant receipts |
| Approval | Explicit, authorised and bound to a particular report version; models cannot grant it |
| Split | Move the expense once; preserve identity; an open follow-up is not approved/exportable |
| Policy answer | Explain approved sources without silently changing expense or workflow state |

Use decimal arithmetic and a recorded rounding convention. Validate these calculations with programmatic tests rather than an LLM judge.

## 11. Evaluation and phase gates

Evaluation begins with Phase 0 fixtures and the first Phase 2 model run. Galileo remains the project-specific observability/evaluation choice in the agreed architecture; pytest covers deterministic behaviour. A separate evaluation service is not required to start.

Initial cases must include: within-limit, exactly-at-limit and over-limit meals; explicit/missing VAT; tips/service charge within the total; ambiguous meal type and date; GBP and foreign currency; unavailable/wrong-date FX; unreadable receipts; invented-value traps; duplicate uploads; multiple restaurants for one meal; category correction; and instruction-like text embedded in receipts. Reuse variants where appropriate and add cases as actual failures reveal gaps.

**Proposed starting targets, to freeze before prompt tuning:**

| Measure | Initial target and interpretation |
|---|---|
| Money, caps, totals, permissions and duplicate-claim gates | All labelled deterministic acceptance cases pass |
| Critical financial facts | No silently accepted wrong/invented amount, currency or receipt date in the held-out release set; missing/ambiguous facts may pause |
| Required-field accuracy | At least 95% exact/normalised field match on supported, readable held-out examples; report numerator and denominator |
| Correct pauses and usable output | All labelled unreadable, missing-required and ambiguity cases pause appropriately; at least 90% of readable complete cases produce a reviewable candidate without manual re-entry of supported required facts |
| Policy answers and citations, from Phase 4 | At least 90% fully correct answers with supporting citations; zero false permission in designated critical cases |
| User effort | Target at least 30% less active preparation time on matched tasks; report measured results and sample size, including failed attempts |
| Latency | Provisional p95 target: upload-to-reviewable single receipt under 30 seconds; policy answer under 15 seconds. Report sample size and separate local/hosted results |
| Cost | Log measured cost per receipt, policy answer and completed report. Set a run budget after the first baseline and before bulk experiments |

These are proposed engineering/demo targets, not achieved results or evidence of population-level reliability. The small first set identifies failures; expand it before wider claims. Save prompt/model/schema/policy versions with each run and keep development and held-out cases separate.

After a failure, record the error category and change one relevant component: prompt, schema, source coverage, UI clarification or deterministic code. Capture the baseline, change, validation result and resulting decision in the [product iteration log](PRODUCT_ITERATION_LOG.md). Compare Sol only when diagnosed Luna failures justify a model experiment; do not change models without recording the quality, latency and cost tradeoff.

## 12. Deferred decisions and scope boundaries

| Item | Resolve when |
|---|---|
| Exact available API models, upload limits and schema details | Phases 0–2, as implementation settings |
| Policy effective date and GBP rounding | Phase 2 before authoritative assessment/conversion |
| Weekend/holiday FX alternative | Only if changing the agreed pending behaviour; not a blocker for receipts with matching-date rates |
| Ground Transport business/cap/charge rules | Phase 3 before enabling its assessment |
| Cabin and airport/city normalisation | Phase 3 against actual synthetic examples |
| Policy source precedence and historic applicability | Phase 3 registry/Phase 4 retrieval; use one explicitly applicable approved demo version initially |
| Repeat splits, visibility and final workflow labels | Phase 5 before implementing those paths |
| Exact export schema | Phase 6 before API demonstration |

Accommodation, automatic supplier receipt sourcing, mailbox monitoring, price intelligence, chat transcript access, out-of-app notifications, actual T&E specialist adjudication, real payments and ERP posting remain outside this POC. They do not delay its completion.

## 13. Progress and decision record

Maintain phase progress here and cycle-level learning in [PRODUCT_ITERATION_LOG.md](PRODUCT_ITERATION_LOG.md). The assistant opens and updates an iteration entry for each deliberate Build → Validate → Improve cycle as the work happens. After each phase, link its cycle entries, demonstration, results, unresolved issues and next action in the table below. Tradeoff decisions live in the iteration entries with their reasons, evidence and revisit triggers; update the governing product or architecture document when a decision changes agreed behaviour.

| Phase | Status | Evidence |
|---|---|---|
| 0 | Complete | [ITER-001 validation](artifacts/ITER-001_VALIDATION.md): scaffold, 24 fixtures, 17 backend and 2 browser tests |
| 1 | Not started | — |
| 2 | Not started | — |
| 3 | Not started | — |
| 4 | Not started | — |
| 5 | Not started | — |
| 6 | Not started | — |

**Next implementation action:** begin Phase 1 with Supabase authentication, report creation and receipt persistence. Service configuration is listed in [README.md](README.md). Phase 0 provides the scaffold and labelled Meal cases; the synthetic preview is not a working receipt-processing flow yet.
