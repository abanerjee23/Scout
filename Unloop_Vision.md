# Unloop — Product Vision

**Prepare expenses. Understand policy. Resolve blockers.**

Updated: 7 October 2026  
Owner: Abhinav  
Status: agreed product direction; Phase 1A confirmed-report workspace verified locally on FastAPI/PostgreSQL; Supabase smoke pending. Evidence/AI/review workflows remain unimplemented.

This is the product source of truth. [Architecture](Architecture.md) defines system responsibilities and [build plan](BUILD_PLAN.md) defines delivery order. The 7 October decisions below supersede the previous login, manual-only intake and employee-led post-submission split design. Previous versions are preserved in [archive](archive/README.md). The hackathon plan in the separate UnLoop folder is reference material, not this repository's governing plan.

## 1. User, problem and value

Employees preparing business travel expenses spend time locating receipts, re-entering their contents, interpreting policy and explaining disputed expenses. Managers need sufficient evidence to approve eligible claims without making an unrelated issue block everything.

Unloop connects three jobs: prepare a report from evidence, understand policy within the report, and resolve line-specific questions while eligible claims progress. Astra is the assistant throughout the interface. The employee is accountable for review and submission; the manager decides approval.

Abhinav's recalled Concur experience—an 18-line report taking approximately 60–90 minutes including receipt sourcing—is directional problem evidence, not a controlled benchmark. It included accommodation, which is outside this POC. Measure savings using matched tasks for supported categories, separately reporting active work and system waiting time. Commercial demand remains a hypothesis requiring user research and adoption evidence.

## 2. Agreed decisions

| Area | Current direction |
|---|---|
| Start a report | Describe the trip in chat; Astra proposes a name, date range and business purpose; employee confirms |
| Manager details | Omitted from creation; a predefined demo manager receives submitted lines |
| Personas | Employee/Manager toggle at the top; no app login/logout |
| Receipt sourcing | Optional Gmail connection and manual uploads; the employee chooses either or both |
| Upload locations | Chat and report workspace, using one evidence pipeline; JPEG, PNG and PDF |
| Clarification | Astra asks in chat and automatically opens the relevant expense and evidence beside it |
| Progression | Employee controls what is submitted before review; manager controls partial approval after submission |
| Inboxes | In-app employee and manager inboxes record submission, questions, responses and approval outcomes |
| Human control | Astra prepares; employee explicitly submits; manager explicitly approves |
| Corrections | Preserve corrected values and revisions; learning, training, memory and automatic correction-to-eval ingestion are out of scope |
| Hosting | Railway web service and worker, with Supabase PostgreSQL |

The toggle is a demo interaction. It is not a production role model. An isolated server-owned session contains predefined personas and a fixed employee grade; every endpoint still checks session ownership and permitted actions. A future multi-user release needs persistent owner identity and genuine manager permissions. Gmail authorization does not grant manager authority.

## 3. Employee journey

### Start and confirm

The landing experience is Astra chat, with the persona toggle and inbox entry visible. For example: “Prepare my London expense report for 1–4 October 2026.” Astra proposes the report header and asks only for missing or ambiguous details. Nothing is submitted by this conversation. Manager email is not a required field.

The report remains visible beside chat, with expense lines and totals. Selecting a line opens its editable facts and original evidence. On narrow screens use a focused expense view with an obvious return to the same question and chat context; avoid clipped side-by-side panels.

### Choose evidence

The employee can connect Gmail, upload files or combine both. Gmail connection permission and an explicit report scan authorization are separate. A connection does not enable background monitoring. Manual uploads work without Gmail.

Use the existing GCP setup associated with **aban.hackathon@gmail.com** for the demo. Its existing configuration and hackathon implementation are starting assets, not proof that this Python application's callback or Railway scan works. Show the connected account so the user knows which mailbox will be searched.

Astra confirms the search window and imports relevant supported receipt attachments. Email arrival dates can differ from transaction or travel dates; describe any booking lookback and validate the expense dates independently. Retain source provenance and let users inspect candidates rather than silently exclude ambiguous matches. Body-only receipts and documents outside scan limits need clear manual-upload guidance. We do not claim to find every receipt.

Chat and workspace uploads reach the same validation, storage, deduplication and processing pipeline as Gmail documents. Retain original evidence and association with each expense. A confirmation may support an Air expense but does not replace a required receipt/invoice.

### Prepare and clarify

Astra extracts evidence-supported facts and suggests the category. Required absent, unreadable or conflicting facts remain unresolved. VAT stays blank when not explicitly stated and does not itself block progress. The employee can correct facts, categories and subcategories; corrected values survive later runs.

When Astra asks “Was this Breakfast, Lunch or Dinner?”, it opens that expense's fields and receipt beside the chat question automatically. An **Open expense** action remains available for revisiting older questions or inbox items. Opening a question never edits financial data. Answering creates a new revision and reruns only the necessary checks.

### Review and submit

Show the original amount/currency, full GBP receipt amount, claim amount, excluded excess, applicable policy and outstanding issues. The employee explicitly reviews and submits a confirmed version. If some lines are not ready, offer a preview to submit eligible lines now or wait. Unsubmitted lines stay in the draft and remain invisible to the manager.

The employee inbox receives submission confirmation identifying the submitted lines and amount; the manager inbox receives that submitted snapshot. Astra must not infer submission from a conversational acknowledgement.

## 4. Supported expenses and financial behaviour

| Category | Types and required category facts |
|---|---|
| Meals | Breakfast/Lunch/Dinner; meal type must be supported or explicitly clarified, never inferred from amount alone |
| Air | One-way/Return; origin, destination, departure date, return date when applicable, evidence-supported cabin |
| Ground Transport | Public transport/Taxi; origin/destination optional |

Common fields are merchant, receipt date, original total, transaction currency and explicit VAT when present. Category-specific fields that do not apply are disabled and labelled **Not applicable**; stale values cannot affect checks or export. Accommodation and other categories are unsupported. Meals is the first implementation slice, not the complete product scope.

The UK-company POC uses GBP submission currency. Preserve original foreign-currency values and the full GBP conversion separately from the claim. Historical FX uses saved valid observations first, Frankfurter pinned to ECB next, and Open Exchange Rates as the agreed fallback. The conversion date must match the receipt date; wrong-date or unavailable observations leave **Conversion pending**. Weekend/holiday previous-rate exceptions remain unapproved. Reopening an expense never recalculates it automatically.

The draft [synthetic policy](docs/policy/Synthetic_T&E_Policy.md) sets Meal limits of £15 Breakfast, £25 Lunch and £50 Dinner. Tips/service charges already in the receipt total are included in the limit. A £62 Dinner retains receipt value £62, claim £50 and excess £12, with **Adjusted to policy limit** and its clause. Report totals sum eligible GBP claims, not full receipt amounts.

Only one Meal claim per demo employee, receipt date and meal type is permitted across that session's reports: one restaurant, one final receipt. Several smaller receipts cannot fill one allowance. Duplicate evidence cannot become another claim. Excluded lines release the claim slot; approved history preserves it.

For Air, a server-seeded employee grade determines the maximum cabin: A–C Economy, D–F Premium Economy, G Business. Lower cabins are allowed. Grade is not user-editable or inferred from a Gmail address. Missing grade pauses assessment; unsupported cabin self-declaration cannot establish compliance. Managers cannot override policy. Ground Transport eligibility/caps/charge rules remain to be agreed before assessment is enabled. The synthetic policy also needs an effective date before activation.

## 5. Policy assistance and uncertainty

Both personas can ask policy questions beside context they may view. Show a concise answer, supporting passage, clause/source identifier and policy version. General questions need no selected expense. Approved source copies and supporting FAQs are the only corpus; no open-web policy search or live intranet connector is included.

Assessments and related answers use the same applicable policy version. Missing coverage is not permission to claim and is not an invented prohibition. An answer cannot edit facts, change compliance, submit or approve. Fixed arithmetic and rules belong in application code; AI assists with reading evidence and grounded explanations.

Distinguish missing facts, clear violations, technical failures, unavailable conversion and genuine policy ambiguity. For the last, retain the labelled simulated T&E referral and in-app inbox item. No actual specialist is notified and no automatic resolution occurs. Pending lines remain visible and can be separated from the eligible progression path.

## 6. Manager review and partial approval

The toggle opens a manager inbox containing submitted snapshots from the same demo session. It does not expose the employee's unsubmitted drafts or Gmail connection. Managers review expense facts and evidence, ask questions against individual lines, and approve an exact submitted version.

The manager can approve all eligible lines or select eligible lines to release while holding/returning others. Show an explicit preview with selected identities, amounts, totals and next actions before confirmation. Partial approval is discretionary; absence of a question never implies approval.

For a ten-line report with one dispute, nine can become approved for processing while the tenth remains held or returned. The report shows **Partially approved** with separate approved and pending totals. Held means awaiting resolution; returned means employee correction is required. A material correction is rechecked and explicitly resubmitted before another approval.

Keep the report and stable expense identities; an employee-created `-1` follow-up is not a prerequisite to manager partial approval. Each release has an immutable snapshot and stable identifier. An unresolved line cannot be exported, approved twice or silently change an earlier release. Complete the report only when every line has a terminal recorded outcome and no active question remains. The employee inbox communicates precisely which lines progressed, the approved amount and remaining work.

Optional **Discuss in Teams** remains a later feature within manager review. Use explicitly configured demo participants, without restoring manager details to report creation. A human reviews and sends the opening context. Unloop does not read Teams or infer that a launch proves delivery/resolution; a human records the outcome in the app. Missing Teams configuration leaves the in-app conversation usable.

## 7. Integration and product boundaries

Original receipt bytes, reports, policy snapshots, FX observations, jobs and workflow history remain in one PostgreSQL database hosted by Supabase, with pgvector for retrieval. There is no separate object-storage service in this POC. Railway runs the web service and worker. Separate Supabase employee/manager Auth is removed from this version.

An access-controlled read API exposes only immutable approved release data: stable report/expense/release IDs, approved versions and financial fields. A partially approved report contributes only approved lines. Pending lines, Gmail credentials, receipt files, conversations and internal policy/history stay outside the response. Repeated reads preserve identities for downstream deduplication. Approval is readiness for processing, not proof of payment.

Future users can consent to connect their own Gmail through the same application integration. Production readiness requires persistent ownership, role permissions, Google verification as applicable and organizational access-policy handling. It is not achieved by removing the demo mailbox restriction. See the [Gmail integration design](docs/integrations/GMAIL.md).

Out of scope: correction learning/training, accommodation, automatic continuous mailbox monitoring, universal supplier intake, card feeds, price intelligence, airline-discount systems, Teams transcript access or automatic sending, external notifications, real T&E adjudication, actual booking/payment, ERP posting, manager policy overrides, multiple countries, admin/auditor personas and an additional vector database.

## 8. Success criteria and delivery evidence

Measure evidence-sourcing actions, active preparation time, clarification effort, external navigation, factual accuracy, policy-answer/citation quality, appropriate pauses, partial progression, latency, retries and cost. Inbox discovery delay is measured separately because there are no out-of-app alerts.

Proposed first targets are 95% required-field accuracy on supported readable held-out cases, no silently accepted wrong critical financial facts in release cases, 90% correct policy answers with supporting citations, and 30% less active preparation time on matched tasks. These are targets, not achieved results. All labelled deterministic money, eligibility, version and duplicate-claim cases must pass. See [build gates](BUILD_PLAN.md#8-evaluation-and-release-gates).

Retain separate development/held-out datasets and evaluate RAG against a full-policy-context baseline. Trace model/prompt/schema/policy versions, latency and cost from the first live run. Record measured product iterations in the [iteration log](docs/product/PRODUCT_ITERATION_LOG.md); this engineering process does not introduce learning from customer corrections.

Phase 0 retains its synthetic preview, schema and fixtures. Phase 1A now adds persona sessions, deterministic chat-led header review/confirmation and PostgreSQL-backed report reopen, verified locally. The Supabase persistence gate remains unverified. Durable manual/Gmail evidence intake and all later workflows remain to be built; no complete Phase 1 or real receipt-processing claim is made. See [Phase 1A evidence](docs/validation/PHASE_1A_VALIDATION.md).
