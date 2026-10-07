# Unloop — Architecture

**Prepare expenses. Understand policy. Resolve blockers.**

Updated: 29 September 2026  
Owner: Abhinav  
Status: high-level architecture baseline v1.0 agreed and closed; Phase 0 local scaffold implemented. Authentication, persistence, agents and hosted infrastructure are not yet implemented.

[Product vision](Unloop_Vision.md) defines what Unloop does. [Synthetic_T&E_Policy.md](Synthetic_T&E_Policy.md) is the draft governing source for policy retrieval and assessment; Air and Meals are defined, while Ground Transport rules remain pending. This document records the agreed high-level architecture for delivering them. [BUILD_PLAN.md](BUILD_PLAN.md) defines the phased implementation sequence. **Agreed** means selected in our discussion; **proposed** identifies remaining implementation defaults or detailed behaviour to validate. Closing the architecture baseline does not mean implementation, integration testing or production readiness is complete. Section 15 separates that remaining work from architecture decisions.

## 1. The architecture in one minute

Build **one Python application with a React interface, a background worker, four specialised agents and one PostgreSQL database with pgvector**. The API and worker share the same codebase and business rules; they are separate processes, not independently engineered microservices.

Each agent has one narrowly defined responsibility. Ordinary Python code decides which specialist runs, validates its result and controls what happens next. There is no general-purpose supervisor agent with authority to approve expenses or rewrite workflow state.

| User problem | Responsible components |
|---|---|
| Building the report manually | Receipt Extraction Agent + deterministic validation, FX and report assembly |
| Leaving the report to understand policy | Policy Answer Agent + shared policy retrieval using pgvector |
| Reconstructing context and blocking an entire report | Clarification Drafting Agent + line-linked questions, Teams launch and transactional report splitting |

The Policy Assessment Agent checks expense facts against the same approved policy sources used by policy Q&A. It supplies a supported assessment, not manager approval.

**Scope correction:** the starting categories are Air (one-way/return), Meals (Breakfast, Lunch, Dinner) and Ground Transport (Public transport, Taxi). Earlier flights-only wording was incorrect and is superseded. This changes category-specific contracts, policy rules and test coverage, not the agreed component topology or four-agent structure. Accommodation remains outside the starting scope.

## 2. Visual system map

![Unloop architecture: a React interface connects to the Flask application, which controls four specialist agents through a background worker. PostgreSQL stores records, receipt files, jobs and the pgvector policy index. External services provide authentication, models, FX, private Teams chat and diagnostic evaluation.](assets/unloop-architecture.png)

[Open the scalable diagram](assets/unloop-architecture.svg)

### Colour and line legend

| Code | Meaning | Responsibility |
|---|---|---|
| Blue `#2563EB` | Human experience | Employee and manager screens; explicit review and action |
| Teal `#0F766E` | Deterministic application | Permissions, routing, calculations, validation, state changes |
| Violet `#7C3AED` | Specialist AI | Interpret evidence or draft language; no direct workflow writes |
| Amber `#B45309` | Durable data | One PostgreSQL database; pgvector is an extension inside it |
| Slate `#475569` | External dependency | Identity, model/embedding API, FX and Teams |
| Rose `#BE185D` | Measurement | Galileo diagnostics and evaluation, not the financial audit record |

Solid arrows show application requests or controlled data flow. Dashed arrows show diagnostic traces or user-initiated departure to Teams. Labels supplement colour; the diagram shows the agreed high-level responsibilities, not a sequence in which every component runs on every action. Detailed contracts and operational settings remain to be specified and tested.

## 3. Stack: agreed choices versus proposed defaults

| Layer | Choice | Status and rationale |
|---|---|---|
| Interface | React | **Agreed.** Propose TypeScript and Vite for implementation. |
| Backend and API | Python + Flask | **Agreed.** Flask owns both the UI-facing API and the separate approved-data API. |
| Agent framework | OpenAI Agents SDK | **Agreed.** Four isolated agent definitions; code-controlled execution. |
| Generation model | OpenAI Luna | **Agreed baseline.** Sol is an evaluation candidate only if meaningful gains justify cost/latency. No automatic Sol fallback. Pin an exact available API model version before building. |
| Database and files | PostgreSQL | **Agreed.** Includes original receipt bytes and policy snapshots, with upload limits. No separate object-storage service. |
| Policy retrieval | pgvector in PostgreSQL | **Agreed.** No Qdrant or second vector database. |
| Observability and AI evals | Galileo | **Agreed.** Application tests remain separate from model-quality evaluation. |
| Database hosting and identity | Supabase Postgres + Supabase Auth | **Agreed.** Supabase hosts the single PostgreSQL database and supplies login. Records, original file bytes and pgvector remain in PostgreSQL; this does not add the separate Supabase Storage bucket service. |
| Background jobs | PostgreSQL job table + Python worker | **Agreed direction.** Avoids adding Redis/Celery to the POC; requires explicit leasing, retry and recovery behaviour. |
| Embeddings | OpenAI `text-embedding-3-small` | **Agreed baseline.** Separate embedding model, not a specialist agent or Luna task. Freeze its version/configuration with the index and evaluate retrieval quality; compare large only on measured gains. |
| Historical FX | Frankfurter, pinned to ECB; Open Exchange Rates free tier fallback | **Agreed.** Reuse valid saved rates first; retain provider/date and fallback reason; leave conversion pending if no acceptable rate exists. Accounts and adapters are not yet configured. See section 9. |
| Application hosting | Railway | **Agreed.** Web service serving Flask and built React assets, plus a worker from the same codebase. Supabase is agreed for database hosting and Auth. No separate Vercel deployment is required initially. |
| Implementation support | Pydantic, SQLAlchemy/Alembic, pytest | **Proposed.** Typed validation, database access/migrations and deterministic tests. These are libraries, not extra hosted services. |

The SDK runs inside our application, so application-owned storage and approval rules remain outside the model loop. This follows the [OpenAI Agents SDK deployment boundary](https://developers.openai.com/api/docs/guides/agents/sdk). Model/account availability and provider data-handling settings still require verification before implementation; none of these services has been provisioned.

## 4. Four agents, four contracts

An agent is a specialised prompt, output schema and restricted tool set, not a separate server. All four initially use Luna. They do not call one another directly or share an unbounded conversation history.

The detailed A1 baseline is maintained in [Receipt_Extraction_Agent.md](Receipt_Extraction_Agent.md). Its Air policy handoff is grounded in the stable clause IDs in [Synthetic_T&E_Policy.md](Synthetic_T&E_Policy.md).

| Agent | One responsibility | Inputs and permitted access | Output | Explicitly forbidden |
|---|---|---|---|---|
| **A1 · Receipt Extraction** | Turn supplied evidence into a structured expense candidate | Only the authorised receipt/confirmation bundle and document/page identifiers; no web search | Merchant, transaction date, amount, original currency, explicit VAT, suggested category/subcategory, applicable Air/Meals/Ground Transport details, evidence references and missing/ambiguous fields | Guessing missing values or meal type from amount alone, policy decisions, FX arithmetic, approval or database writes |
| **A2 · Policy Assessment** | Assess one expense against applicable policy | Validated expense facts, trusted policy-relevant profile attributes supplied by code, deterministic check results, and the shared read-only policy retrieval tool scoped to an approved policy version | Candidate finding: compliant, noncompliant, needs facts or ambiguous; concise rationale, clause references and missing facts | Manager approval, exception grants, changing extracted facts/profile attributes or mutating an expense |
| **A3 · Policy Answer** | Answer the user's policy question | Question, relevant authorised expense context if selected, bounded question history, and the same scoped policy retrieval tool | Supported explanation, conditions, citations and any clarification question or inability to answer | Changing compliance status, editing/submitting a report, following arbitrary URLs or approving an expense |
| **A4 · Clarification Drafting** | Turn an existing issue into concise communication | Known missing-field issue, manager's recorded question, relevant expense facts and approved source references; no private chat access | A focused question or a proposed Teams opening message, for a person to review | Sending messages, reading Teams, inventing agreement, resolving disputes or writing workflow state |

Outputs carry the input revision and source identifiers supplied by the application. The application validates them before saving; model-generated identifiers are never trusted as permission to access records. Source-linked explanations are exposed, not hidden chain-of-thought or unsupported numerical confidence scores.

**Why A2 and A3 are separate:** assessment produces a constrained result for an expense check; Q&A explains policy to a person and may ask follow-up questions. They share source material and retrieval code, not authority or conversational state.

**What does not need an agent:** authentication, document hashing, permitted-file checks, arithmetic, rate lookup, rule comparisons, receipt linking by explicit identifiers, eligibility gates, report splitting, approval and export. A1 suggests the category as part of interpreting the receipt; there is no additional classification agent. Unsupported or unclear document types require clarification. Embedding generation is an API operation, not an autonomous worker.

Code-controlled routing is agreed, using the SDK's specialist definitions and runner rather than a free-form handoff network. See [OpenAI orchestration guidance](https://developers.openai.com/api/docs/guides/agents/orchestration).

**Is there an orchestrator agent?** No fifth LLM agent is proposed. A Python workflow coordinator manages the four specialists: receipt upload triggers A1, validated facts trigger A2, a policy question triggers A3, and a request for communication context triggers A4. It also manages dependencies, retries and pauses for human input. The agent count does not imply that every action invokes all four. A model-based manager could dynamically select specialists, but would add latency, tokens and routing failure modes without a demonstrated need in these known workflows. Revisit only if a genuinely open-ended user journey justifies it; financial and approval gates remain code-controlled either way.

## 5. Application components and authority

| Component | What it owns |
|---|---|
| React interface | Report header, upload, review, policy side panel, inbox, dispute/split preview and receipt viewer. Shows stored results; does not rerun AI when a report opens. |
| Flask API | Validates identity, checks ownership/manager access, accepts commands and returns authorised views. The client cannot supply its own trusted role or tenant. |
| Workflow service | Report/expense versions, submission eligibility, question resolution, report split, manager approval and immutable approved snapshots. All mutations pass through this service. |
| Validation and calculation service | Required fields, explicit VAT-or-blank, decimal amounts, currencies, historical FX, policy caps, claim amounts, excluded excess, totals and policy rules that can be encoded deterministically. No binary floating-point money arithmetic. |
| Policy service | Source registry, approved source versions, retrieval filters, citation validation and deterministic policy-rule configuration. Both policy agents use it. |
| Job runner and worker | Durable execution, specialist selection, deadlines, retries, stale-result rejection and validated result persistence. No open model session while waiting for a person. |
| Adapters | Model/embedding calls, FX, Galileo and identity verification. Teams launch is a browser action, not a chat-reading integration. |

An agent never receives database credentials, arbitrary SQL, a shell, a general browser or workflow-mutation tools. Code outside the agent performs all writes. The whole application still needs ordinary access control; an SDK guardrail does not replace it.

**Category-aware form rule:** code defines applicable fields and allowed subcategories for Air, Meals and Ground Transport. AI proposes a classification; the employee can correct it through an editable category selector during preparation/correction. Inapplicable fields are greyed out and labelled “Not applicable”, not treated as missing required values. Category changes create a new expense revision, invalidate stale category-specific assessments and trigger the relevant checks. The server enforces the same field-applicability rules; hidden/disabled browser controls alone are not validation. Old category-specific values must not leak into active policy checks or approved-data exports. Approved snapshots cannot be edited through this control.

**Meal uniqueness rule:** the policy permits one claimed Meal expense for each employee, receipt date and meal type. The server checks that key across active and submitted expenses; A1 separately reports multiple receipt documents within a candidate. Several smaller receipts are never summed toward the allowance. Suspected conflicts pause the affected expenses for employee selection, while exact duplicate uploads are deduplicated rather than paid twice.

## 6. How the main journeys run

### A. Receipt to reviewable expense

1. Employee creates the named report with manager email and business purpose. Authentication establishes employee identity.
2. API checks permission and file limits, stores the original receipt bytes and creates the processing job in one database transaction. Return a job ID without waiting for an AI call.
3. Worker claims the job and passes only the authorised document bundle to A1. Preserve the original; document text is untrusted input, not executable instructions.
4. Code validates the extraction schema and source links. Missing required facts remain missing. VAT stays blank when not explicit. Supporting confirmations do not automatically satisfy the receipt requirement. Ambiguous receipt-to-expense matching requires a person; repeated uploads must not create another claim.
5. Once date/currency are known, code fetches or reuses the historical FX rate and calculates the full GBP receipt value. It then applies any explicit policy cap to produce the claim amount and excluded excess without overwriting the receipt value. Load the applicable reviewed policy source set, run other explicit rules and invoke A2 for interpretation. Independent FX and source lookup work can overlap; dependent stages cannot.
6. Validate A2's evidence and required-rule coverage. A plausible answer alone does not unlock submission. Save the assessment and issues against the expense revision. If wording needs help, call A4; a deterministic missing-field template is the fallback.
7. React polls authorised job status, then shows the prepared expense, receipt and issues. Technical failures display retry/recovery, not a policy denial. The employee explicitly reviews, corrects and submits.

User-visible processing labels should be short and readable, such as **Reading receipt**, **Checking policy**, **Needs information**, **Ready for review** and **Could not process**. These do not imply submission or manager approval. Final UI wording remains design work.

### B. Ask about policy in the report

1. User opens the policy panel. API checks the selected report/expense and source access; a general question needs no expense selection.
2. Capture the applicable policy version, expense revision and the bounded context needed for the question. Queue a policy-answer job; prioritise interactive questions over bulk receipt processing.
3. The policy service embeds the query and searches source-linked chunks in PostgreSQL/pgvector, filtered by authorised source set, version and applicability before results reach the model. Combine exact term/section lookup with similarity search where useful.
4. A3 receives relevant passages plus their stable citation identifiers. It explains what is supported, asks for missing facts or states that it cannot establish the answer.
5. Code verifies cited IDs belong to the supplied sources and validates quotations. Display the answer and source passages in the same panel. A valid citation does not prove the interpretation is correct; that needs evaluation.
6. No expense or workflow status changes because the user asked a question. If an expense remains genuinely ambiguous after factual clarification, the existing workflow may record **Sent to T&E specialist for review**, explicitly labelled as simulated. No real specialist is notified.

RAG is not used as an exhaustive checklist: a top-k search can omit an important restriction. A2 also receives the curated required-rule checklist and, while the POC policy is short, its applicable core policy text. Missing required coverage stays unresolved. Evaluate A3's retrieval approach against a full-policy-context baseline using the same questions.

### C. Manager question, Teams and partial progression

1. Only explicit employee submission puts a report into the manager's approval inbox. A typed manager email is a routing value, not proof of identity or authority.
2. Manager records a question against an expense. The workflow service saves it and an employee inbox item atomically. It does not reject the whole report merely to ask a question.
3. If either person selects **Discuss in Teams**, A4 drafts context from Unloop records. The user reviews it; code creates the Teams launch link with the other participant's validated Teams identity. The user sends the message.
4. Unloop never reads the conversation or assumes a message was sent. A human records the outcome in Unloop, and the manager explicitly resolves the question. Recheck material corrections and require employee reconfirmation.
5. If the employee chooses **Submit undisputed lines**, show a split preview. In one transaction, move the disputed expense(s) to `UNL-1042-1`, retain their identities/evidence/questions, recalculate totals and submit the eligible original for explicit manager approval. Waiting creates no follow-up.
6. The nine-line original closes only after the manager approves that exact version. The open follow-up stays outside the approved-data API until separately resolved, rechecked, submitted and approved. Closed originals never change because a follow-up changes.

For a post-submission follow-up, propose preserving manager access to the previously submitted question/evidence, without exposing unsubmitted corrections as an approved or newly submitted version. Keep it out of the approval inbox until the employee submits it. This visibility detail needs confirmation before UI implementation. Before-initial-submission pending lines remain employee-only until submitted.

Teams deep links create/open a chat and can prefill draft context; they are not message-delivery APIs. Entra user principal names may differ from an email alias. Validate recipient resolution, existing-chat behaviour and supported clients with two test accounts. Provide copyable context if launch fails, without claiming that fallback demonstrates a working integration. [Microsoft Teams guidance](https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-teams)

## 7. One database: conceptual data model

These are proposed entities, not a final field contract or a migration to run.

| Entity group | Stored information and invariants |
|---|---|
| Users, employee profiles and report participants | Auth identity reference, role, trusted employee grade and authorised employee/manager relationships. Grade is server-controlled and linked to the authenticated user ID; it is not inferred from email text or editable by the employee. Two product personas only. |
| Reports and report versions | Required name, owner, fixed manager, purpose, submission currency fixed to GBP for the UK-company POC, GBP claim total, state, revision, original/follow-up links and approved snapshot. |
| Expenses and expense versions | Stable expense identity, current report, original amount/currency/receipt date, full converted receipt amount in GBP, receipt-aligned FX conversion date, applied FX observation reference and internal processing timestamp, applicable policy cap, GBP claim amount, excluded GBP excess, evidence links, field origin and eligibility findings. Receipt and converted values remain immutable evidence; a cap changes the claim amount, not those source values. One expense cannot be claimed in two active reports. |
| Documents and evidence links | Original PDF/image bytes (`bytea`), type, filename, owner, hash and linking metadata. Keep bytes separate from ordinary list-query rows. Multiple permitted references do not require duplicate files. |
| Policy sources and versions | Approved original snapshots, effective/applicability metadata, precedence, source locations and reviewed rule configuration. |
| Policy chunks and embeddings | Source/version/page/section references, text, embedding configuration and vectors using pgvector. Derived and rebuildable; not independent policy truth. |
| FX observations | Pair, requested transaction date, effective rate date and provider timestamp where supplied, rate, source, retrieval time and conversion/rounding version. The linked expense's conversion timestamp is distinct from the rate date and retrieval time. |
| Issues, answers and inbox items | Line-linked questions, explicit human responses/resolution, policy-answer citations and simulated specialist referral markers. Never Teams transcripts. |
| Jobs and AI runs | Task type, input revision, policy snapshot, lease, attempts, deadline, result status, model/prompt version and trace correlation ID. |
| Approval events, split events and request keys | Authoritative business history, actor, approved version and idempotency keys. Model traces are not this audit record. |

PostgreSQL's binary field type supports original file contents; pgvector adds similarity search within the same database. [Binary data](https://www.postgresql.org/docs/current/datatype-binary.html) · [pgvector](https://github.com/pgvector/pgvector)

### Consistency before convenience

- **Atomic split:** lock the current report/version and moved expenses; enforce unique follow-up numbering and request keys. Either the full move/totals/link update commits or nothing does. Concurrent approval and split attempts cannot both succeed against the same revision.
- **Idempotency:** repeated upload/submit/split commands return the original outcome for that request. Exact duplicate document hashes help detect repeated uploads; different scans of the same receipt remain a separate duplicate-detection risk to test.
- **Revision checks:** reject stale approval requests and worker results. A result produced for an older expense or policy snapshot cannot overwrite current facts. Human edits retain priority and trigger the necessary rechecks.
- **Approved snapshots:** store the approved financial view and supporting internal evidence references. Exports read that immutable approved version, not a mutable draft or agent conversation.
- **File privacy:** receipt retrieval goes through authorised Flask endpoints. Do not expose binary data, unrestricted database APIs or privileged keys to the browser.

## 8. Retrieval ingestion and freshness

Demo setup imports the reviewed synthetic policy and a few approved FAQ/guidance snapshots. No live intranet connector, crawler or third persona is needed.

1. Register a new source version and retain the original in PostgreSQL.
2. Extract text and split by meaningful clauses, preserving headings, limits, exceptions and page/section references. Inspect tables and negations; do not blindly treat every fixed-size chunk as self-contained.
3. Create embeddings through the agreed OpenAI embedding baseline and store them with the chunk/source version. Embeddings are numerical search representations, not replacements for original text.
4. Run ingestion checks and labelled retrieval tests before activating a source set. Activate only a complete, reviewed index; retain the prior source set for historic assessments.
5. Use matching document/query embedding configurations. Re-embed and evaluate when changing the embedding model; do not mix incompatible vectors.

Start with exact vector search for the small corpus. Add an approximate index only if measured retrieval latency warrants it. Source authorisation/version filters are enforced in application/database code, never chosen freely by a model. Semantic similarity is not a calibrated confidence score or permission to claim.

**Embedding recommendation — robustness at reasonable cost:** retain `text-embedding-3-small` as the initial candidate, and compare it with `text-embedding-3-large` on held-out policy questions. Official listed standard input prices checked on 27 September 2026 are $0.02 and $0.13 per million tokens respectively; this excludes answer generation, database hosting and other services. For a small policy corpus, the absolute cost difference is modest, so do not sacrifice required-clause retrieval just to select the cheaper model. Measure whether the relevant clauses and exceptions appear in retrieved results, alongside downstream answer correctness and latency. Check chunking, source coverage and filters before attributing a failure to the model. Keep small if it meets the release bar; choose large if it delivers meaningful measured gains. Cache document embeddings until source content/configuration changes. This is an evaluation-backed recommendation, not a claim that robustness has already been demonstrated. [Small model](https://developers.openai.com/api/docs/models/text-embedding-3-small) · [Large model](https://developers.openai.com/api/docs/models/text-embedding-3-large)

The draft synthetic policy permits only one approved active version until the temporal rule for historic expenses and later policy changes is agreed. Every run records the selected source set; no silent switch to whichever version happens to rank highest.

## 9. Historical FX and money handling

Use Frankfurter with an explicit ECB source as the agreed primary, rather than its default blended-provider feed. Open Exchange Rates' free tier is the agreed fallback. Request the expense transaction date and original-currency-to-GBP pair, not the flight departure date or today's rate. Retain original amounts. GBP-to-GBP is 1 and needs no external call. [Frankfurter documentation](https://frankfurter.dev/)

**Agreed date rule:** the FX conversion date equals the receipt date, never the upload, processing or submission date. Ask for clarification if the receipt contains ambiguous dates. Request that exact date and validate the returned observation date; a successful API response does not establish a date match. The previous-publication exception proposed for weekends/holidays remains unapproved. If no acceptable matching-date rate exists, leave conversion pending unless a different-date exception is explicitly agreed. Never relabel an earlier rate as a receipt-date observation. Same-day rates not yet published also remain pending.

Fetch rates on demand and cache by source/pair/effective date. Compute conversion and rounding in Python with decimal arithmetic. Preserve the rate and converted amount used by the approved snapshot. No daily FX-maintenance agent is needed.

**Agreed dual-currency contract:** submission currency is GBP for the assumed UK company. Persist the original amount/currency, converted GBP amount/currency, receipt date and matching FX conversion date. Retain the provider's actual rate date through its immutable observation and keep the calculation timestamp as internal processing metadata, not the business conversion date. The UI shows both amounts and the receipt-aligned FX conversion date; the previously proposed user-facing “Converted on” processing-time label is removed. Persist results rather than recomputing them on read. Sum stored GBP line amounts using the agreed rounding convention. No mixed-currency sum or submission with missing required GBP conversions is allowed. GBP-native lines use the same original/submission amount and indicate that no FX conversion was needed, without inventing a provider rate date.

### Agreed fallback: Open Exchange Rates

**Decision log, 27 September 2026:** Open Exchange Rates' free tier is selected as the fallback to Frankfurter/ECB. XE is excluded because its subscription cost is disproportionate to this POC. Direct ECB downloads and Currencyapi were considered but are not selected integrations. Code orchestration of the four specialists and the small embedding baseline are also agreed. This completes high-level architecture selection; detailed contracts, operating settings and evaluation thresholds remain design work. No account, subscription or integration was created by this decision.

Options checked on 27 September 2026; retained below as the decision record, not a list of integrations to build:

| Candidate | Cost and historical access | Main trade-off |
|---|---|---|
| Open Exchange Rates — selected | Free plan: daily historical data, 1,000 API requests/month, USD base; account/App ID required | Derive GBP cross-rates in Python from the same dated response. Its completed-day historical snapshot is end-of-day UTC, not the ECB fixing. This alternative basis is accepted for the POC fallback and must be encoded in the synthetic policy, with source/date visible. [Free plan](https://openexchangerates.org/signup/free) · [Base restriction](https://openexchangerates.org/signup) · [Historical convention](https://docs.openexchangerates.org/reference/historical-json) |
| Direct ECB historical downloads | Public CSV/XML time series; no paid API subscription | A second access route to the same ECB source, not an independent source or wider currency coverage. More parsing/cross-rate work. Useful for a Frankfurter outage, not missing ECB observations. [ECB downloads](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) |
| Currencyapi | Free plan: 300 requests/month and historical rates | Free tier is labelled private use; confirm whether the intended portfolio demo qualifies before adopting. [Plan details](https://currencyapi.com/pricing/) |

Agreed sequence: reuse a saved rate matching the configured source/date convention; otherwise request Frankfurter/ECB with bounded retries; on service failure or unsupported currency, try Open Exchange Rates under the permitted date/source rules; if no acceptable rate is available, keep the expense saved with **Conversion pending**. A non-publication day follows the date convention, not automatic provider switching. Do not stack multiple new providers for this POC. For the current UTC date, do not mistake an interim fallback observation for a completed-day historical rate; keep conversion pending unless a separately agreed same-day policy permits it.

For each conversion, record access provider, underlying source/rate type, currency pair, requested date, actual rate timestamp/date, retrieval time and fallback reason. Derive cross-rates from one provider's same-date snapshot, never mixed sources or dates. Never substitute today's rate for a past transaction or silently overwrite an approved conversion when the primary recovers. Confirm terms permit required retention and demo display; enforce quota limits locally and keep the App ID on the server. Account setup and adapter tests remain implementation tasks; no signup, purchase or integration was performed during architecture design.

These are POC reporting reference rates, not necessarily card-settlement or real reimbursement rates. ECB describes its rates as informational and discourages transactional use; a commercial product would require the customer's explicit FX policy. [ECB reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)

## 10. Execution, latency and recovery

Use a durable jobs table and a worker process, not fire-and-forget tasks inside a Flask request. Flask recommends a queue for background work. [Flask background-task guidance](https://flask.palletsprojects.com/en/stable/async-await/)

**Proposed minimal queue design:** claim due jobs in a short transaction using row locking and `SKIP LOCKED`; record a lease and attempt count, commit, then make external calls outside the transaction. Renew leases for active work, recover expired leases, cap attempts and schedule backoff after transient failures. PostgreSQL documents `SKIP LOCKED` as useful for queue-like consumers. [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html)

Execution is **at least once**, not exactly once. Jobs and result writes therefore need idempotency keys and revision checks. A worker crash may cause another model call and extra cost, but must not create another expense, duplicate an inbox item or approve anything twice. No database lock remains held while waiting for a model, FX provider or human.

Proposed starting limits, to calibrate with tests: 10 MiB per receipt, 20 pages per document, 10 files per batch, two concurrent AI jobs per demo account, and at most two transient retries. Agent turn/tool limits, deadlines and a per-report spend ceiling must be fixed before running paid experiments. Do not expand budgets automatically to force a successful answer.

| Failure | User-visible behaviour and recovery |
|---|---|
| Missing receipt or unreadable evidence | Request the required document or a clearer copy; preserve the existing draft. |
| Invalid model schema or unknown citation | Reject the output, allow one bounded repair attempt, then display a processing failure. |
| Missing factual detail | Ask a targeted question; pause the job and resume with a new validated revision after the user responds. |
| Genuine policy conflict/ambiguity | Keep the expense pending and use the labelled simulated specialist referral when applicable. |
| Retrieval or embedding service unavailable | Say policy guidance is unavailable and offer retry; never interpret service failure as policy permission. |
| Model/FX timeout or rate limit | Bounded retry/backoff; keep processing state visible and reuse valid saved results. No automatic stronger-model fallback. |
| Galileo unavailable | Continue the business operation; retain minimal local operational metadata and surface a monitoring failure. Do not lose the authoritative business event. |
| Teams unavailable | Preserve the question, offer copyable opening context and require explicit resolution in Unloop. |

Load report fields without receipt bytes; fetch the selected file only when needed. Do not rerun extraction, FX or Q&A merely because a report is reopened. Measure report-opening, receipt-opening, upload-to-draft and policy-answer latency separately; one database does not itself guarantee fast UX.

## 11. Security and external-data boundaries

- **Authentication, profile and authorisation:** agreed Supabase Auth establishes identity. Flask verifies the token, loads the server-controlled employee profile by authenticated user ID and enforces report/source permissions on every endpoint, including file downloads, jobs and conversation history. A verified email can support controlled profile provisioning, but email does not prove grade; employee grade is seeded for the POC and cannot be self-edited. Manager email must resolve to the fixed authenticated participant; it is not an access token. No public demo-role or grade toggle substitutes for authorisation. [Supabase Auth](https://supabase.com/docs/guides/auth)
- **Minimum data:** send only required receipt pages/facts and authorised policy passages to OpenAI. A single local database does not mean data never leaves Unloop: model/embedding processing and selected Galileo diagnostics are external transfers. Start with synthetic evidence and verify retention/region settings before real employee data.
- **Untrusted input:** uploaded files, policy text and user questions cannot grant permissions, change the recipient, override checks or request arbitrary network access. Validate file signatures, size/pages and rendered text; do not execute attachments. Escape model output in the UI and allow only registered source links.
- **Secrets:** keep OpenAI, Galileo, database and identity-service secrets on the server. Use least-privilege database access, TLS and separate development/demo credentials. Never ship privileged Supabase keys to React.
- **Privacy:** neither agents nor adapters have Teams-read or corporate-email permissions. Do not put receipt contents or credentials into Teams-link query strings; keep the user-reviewed opening context minimal and link back to an authenticated expense view.
- **Retention and recovery:** restrict and test backups containing receipt bytes; specify retention/deletion before real data. Do not call the POC production-ready without restore tests, access testing and operational monitoring.

## 12. API boundary

Propose two clearly separated API surfaces within the same Flask application:

| Surface | Purpose | Example routes, subject to final contract |
|---|---|---|
| Internal application API | Authenticated employee/manager operations and private evidence views | `/api/v1/reports`, `/api/v1/receipts`, `/api/v1/jobs`, `/api/v1/policy/questions`, explicit submit/split/approve commands |
| Approved-data API | Demonstrate reliable core data is available to a permitted downstream reader | Read-only `/api/v1/approved-reports/{reportId}` and paginated listing |

The approved-data response contains stable report/expense identifiers and approved financial fields: merchant, transaction date, category, original receipt amount/currency, full converted GBP receipt amount, approved GBP claim amount and report claim total. A policy-capped expense therefore does not misrepresent the receipt or send the disallowed excess downstream. The exact DTO and any project code remain to be finalised. Internal workflow status, policy explanations, receipt files, chat context, split history and audit evidence are not included. A pending follow-up contributes no amount until separately approved. Access checks apply to this API too; knowing an ID is not sufficient.

There is no ERP receiver, payment execution or automatic downstream push. Repeated reads return the same approved expense identity/version, allowing a future consumer to deduplicate. The POC does not claim to control a nonexistent consumer's payment behaviour.

## 13. Galileo, evaluations and the PM evidence

Use Galileo's Agents SDK integration to trace each specialist and its tool calls, and experiments to run labelled datasets through the real workflow. Keep trace context isolated per concurrent job. Confirm processor configuration so diagnostics are not unintentionally duplicated to multiple tracing providers. [Galileo integration](https://docs.galileo.ai/sdk-api/third-party-integrations/openai-agents/openai-agents) · [Experiments](https://docs.galileo.ai/sdk-api/experiments/running-experiments)

Record model/prompt/source versions, stage latency, attempts, validation errors, tokens, estimated cost, retrieval IDs and user corrections. Minimise/redact exported content; avoid logging complete receipt files, access tokens, unnecessary personal information or signed links. PostgreSQL retains the authoritative business evidence and decisions. Galileo is a diagnostic copy, not the expense ledger.

| Test layer | What success must demonstrate |
|---|---|
| A1 extraction | Correct required fields and source attribution; no invented amounts; missing VAT stays blank; unreadable or unsupported evidence handled honestly |
| A2 assessment | Correct application of supported rules; no false permission to claim; missing facts and true ambiguity separated from outages |
| A3 policy Q&A | Relevant retrieval, supported answers/citations, correct source version, appropriate abstention, reduced external navigation |
| A4 drafting | Correct recipient context and facts, concise useful question, no invented approval or private-chat claims |
| Deterministic integration tests | Exact totals/FX, authorisation, malicious file/input handling, concurrent split/approval, duplicate retries, stale-run rejection and approved-only exports |
| End-to-end product test | Upload → review → submit → manager question → split/wait → explicit approval → inspectable API result; two genuine test identities |

Use exact/programmatic checks for money, identifiers and state; human-reviewed labels for policy; an LLM judge only where appropriate, never as the sole arbiter of financial correctness. Freeze a held-out set and acceptance thresholds before tuning. Include injection attempts, conflicting sources, duplicates, missing receipts and failures. Compare Luna with Sol only after diagnosing failures in prompts, source coverage and tooling; record quality gain alongside additional cost and latency.

## 14. Agreed deployment shape and deliberate trade-offs

Railway is agreed for application hosting; Supabase is agreed for PostgreSQL hosting and Auth. The high-level topology is one Railway web service for Flask plus the built React assets, a second Railway process/service for the worker using the same application image, and one managed Supabase Postgres database with pgvector. Original receipts remain database bytes, not objects in separate Supabase Storage buckets. Service sizing, budget and regions still need confirmation before deployment. Railway supports separately deployed services; this topology is our selected design, not a requirement of the framework. [Railway services](https://docs.railway.com/services)

| Trade-off | Why selected | Cost or limitation accepted |
|---|---|---|
| One database, including receipts and jobs | Fewer infrastructure components and cohesive backups | File/job growth consumes database resources; size limits and monitoring matter |
| Four specialists, one code-controlled workflow | Clear ownership, task-specific evals and restricted tools | Additional model calls only when the task requires them; not all four run on every request |
| PostgreSQL job queue | Avoid a separate queue service for the small POC | We must implement/test leases, retries, priorities and idempotency; not a free reliability guarantee |
| pgvector rather than a dedicated vector service | Reuse source permissions/version metadata in one database | Retrieval quality and index tuning remain our responsibility |
| Managed Auth | Avoid inventing password security | External dependency; token verification and application permissions still need implementation |
| Luna first | Evidence-led quality/cost trade-off | Do not assume it meets the quality bar; evaluate and limit unsupported behaviour |
| One web origin and polling | Simple deployment/session model | Less elaborate streaming; keep loading states responsive and measure wait times |

## 15. Architecture closure and next-phase work

**The high-level architecture is closed as baseline v1.0.** Components, hosting providers, storage approach, specialist responsibilities, orchestration, model/embedding baselines, measurement platform and FX primary/fallback are selected. No further provider or top-level orchestration choice blocks moving into detailed design. Reopen a baseline decision only when implementation evidence or an explicit product-scope change justifies it, and record the reason here.

Closure is not a claim that the system has been built or validated. These are the remaining detailed-design and readiness tasks:

| Pending item | Recommended next action |
|---|---|
| Agent contracts | A1's detailed baseline is documented in [Receipt_Extraction_Agent.md](Receipt_Extraction_Agent.md); finish its implementation schema and then define A2–A4 to the same standard |
| Synthetic policy and source applicability | Air rules, source precedence and Meals rules are drafted in [Synthetic_T&E_Policy.md](Synthetic_T&E_Policy.md). Complete Ground Transport, approve an effective date, define historic-version selection and add labelled expected answers/guidance pages |
| FX and service configuration | The Frankfurter/ECB → Open Exchange Rates fallback and matching-receipt-date rule are in the draft policy. Finalise weekend/holiday/same-day availability and rounding. Before integration runs, confirm access/terms/budgets and pin versions; before deployment, choose regions and service sizing |
| Job and file limits | Validate proposed limits against a realistic synthetic receipt batch; set deadlines and spend caps |
| Repeat splits and follow-up visibility | Define suffixes beyond `-1`, empty-report prevention and precisely which submitted snapshot each role can see |
| API/field contract and state labels | Common expense fields and persisted original/full-GBP/claim/excess amounts with rate/conversion dates are agreed in the vision. Define category-specific fields and applicability rules, exact schemas, approved-data field mapping, user-facing labels and rounding rules |
| Evals and release gate | Define held-out cases and acceptable quality/latency/cost before implementation claims |

**Integration proof before demo sign-off:** demonstrate both FX adapters (including quota/outage handling), authorised receipt access, and a Teams launch between two genuine test identities. Verify model/provider access and Galileo trace redaction. Before any real employee data or production claim, also complete retention, restore, access-control and operational readiness checks. These tests may uncover reasons to revise the architecture; they are not silently assumed to have passed.

**Next implementation step:** begin Phases 0–2 of [BUILD_PLAN.md](BUILD_PLAN.md): scaffold the application, prepare labelled Meal cases and complete the authenticated Meal receipt-to-claim workflow. Resolve A1 schema and calculation details while building that slice. Ground Transport policy is deferred to Phase 3, before its assessment is implemented; it does not block the first Meal milestone.

Then build in thin slices: (1) authenticated report/receipt storage with one real extraction run; (2) validated FX and policy assessment; (3) in-context policy retrieval/Q&A; (4) clarification, split and explicit manager approval; (5) approved-data API and end-to-end failure tests. Instrument and evaluate from the first AI slice rather than adding observability at the end.

No price intelligence, mailbox monitoring, automated Teams sending/reading, real specialist adjudication, payment processing or ERP posting is introduced by this architecture. The two-persona product boundary and starting categories—Air, Meals and Ground Transport—are defined by [Unloop_Vision.md](Unloop_Vision.md).
