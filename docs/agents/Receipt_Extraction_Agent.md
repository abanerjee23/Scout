# Unloop — Receipt Extraction Agent Contract

**A1 · Evidence to structured expense candidate**

Updated: 8 October 2026. Owner: Abhinav.

Status: executable category schema v0.2 with v0.1 Meal compatibility; bounded SDK/worker, evidence validation and human precedence implemented and tested. Actual model quality remains unmeasured.

Current implementation: [contracts.py](../../backend/unloop/contracts.py) retains the original Meal schema and adds the category schema; [extraction.py](../../backend/unloop/extraction.py) constructs a no-tool OpenAI Agents SDK call, and [expense_worker.py](../../backend/unloop/expense_worker.py) validates evidence, supported currencies, selected document roles and stale revisions before saving. Human locks are supplied as context and enforced by code on merge. The current model is gpt-6-luna with prompt `categories-a1-2`; owner-selected gpt-6.1-sol migration/cost controls are next. Paid extraction remains disabled locally. [Current ledger](../product/BUILD_STATUS.md) separates deterministic checks from live quality; [ITER-001](../validation/ITER-001_VALIDATION.md) retains the original scaffold evidence.

[Product vision](../../Unloop_Vision.md) defines the product behaviour. [Architecture.md](../../Architecture.md) defines A1's system boundary. [Synthetic_T&E_Policy.md](../policy/Synthetic_T&E_Policy.md) supplies the owner-reviewed governing clauses that consume A1's evidence-backed Air output. This document makes the Receipt Extraction Agent buildable and testable.

## 1. Job and non-goals

A1 reads only the receipt and permitted supporting documents supplied for one expense candidate. It returns structured facts, a suggested classification and evidence references. It does not create or update an expense itself.

Manual chat/workspace uploads and consent-based Gmail attachment imports enter the same evidence pipeline. Application code retains source provenance and authorizes document IDs before calling A1; A1 receives selected bytes, never mailbox credentials or general inbox access. Its output contract is independent of intake source. [Gmail boundary](../integrations/GMAIL.md) records the adapter and consent design.

A1 does **not**:

- calculate FX, GBP amounts or report totals;
- interpret policy or decide compliance;
- approve, submit or exclude an expense;
- search the web, query the database or call another agent;
- decide who can access a document;
- treat a booking confirmation as a required receipt;
- invent a value to complete the form.

The Python workflow coordinator validates A1's result, persists accepted values and decides the next step. The employee reviews the candidate before submission.

## 2. Supported taxonomy

| Category | Required type | Optional fields |
|---|---|---|
| Air | Journey type: `oneWay` or `return` | None in the minimum contract |
| Meals | Meal type: `breakfast`, `lunch` or `dinner` | None in the minimum contract |
| Ground Transport | Transport type: `publicTransport` or `taxi`; business journey and separately identified penalty amount | Origin and destination, only when present |

Accommodation and any other category return `unsupportedCategory`. Breakfast, Lunch and Dinner must never be inferred from the amount alone.

## 3. Application-to-agent input

The application constructs the input after validating the server-owned demo session, employee persona and permission for every document. The top persona toggle is the agreed demo interaction; no employee/manager login is required. Future production ownership requires a persistent authenticated identity. Gmail authorization does not assign an application role. Identifiers are opaque references, not model-selected permissions.

| Input | Required | Purpose |
|---|---:|---|
| `schemaVersion` | Yes | Pins the contract used for this run |
| `jobId` | Yes | Correlates the run; supplied by code |
| `expenseRevisionId` | Yes | Prevents a stale result overwriting newer work |
| `documents` | Yes | Authorised receipt plus any supporting documents |
| `submissionCurrency` | Yes | Always `GBP` for the UK-company POC; context only, not an instruction to convert |
| `supportedTaxonomy` | Yes | The exact category/type enums above |
| `categoryOverride` | No | A user-corrected category that A1 must treat as locked; corrected type values are included in `lockedHumanFields` |
| `lockedHumanFields` | No | User-entered or corrected values that A1 must not overwrite |

Each document contains an application-issued `documentId`, declared role (`receipt` or `supportingDocument`), MIME type, page count and the authorised image/PDF content. Filenames and document text are untrusted data, not instructions.

At least one document declared as a receipt is required. When no receipt is attached, code does not call A1; the UI shows **Receipt required**. Supporting evidence may fill Air details but cannot satisfy the receipt requirement by itself.

Business purpose, report header, demo grade, owner/persona identity, Gmail credentials, report status and existing policy findings are not supplied to A1. They are unnecessary for evidence extraction and could bias classification.

## 4. Output envelope

A1 returns one structured result matching the pinned schema.

| Output | Meaning |
|---|---|
| `schemaVersion` | Contract version used |
| `jobId` | Exact application-supplied job ID |
| `expenseRevisionId` | Exact input revision; never invented by the model |
| `resultState` | `complete`, `needsInformation`, `unsupported` or `couldNotRead` |
| `documentFindings` | Readability and apparent role for each supplied document |
| `classification` | Suggested category and required category type |
| `commonFields` | Common expense facts |
| `categoryFields` | Exactly one category-specific object matching the classification |
| `issues` | Machine-readable missing, ambiguous, conflicting or unsupported findings |

`complete` means all fields required to begin policy assessment are supported. It does not mean policy compliant, submitted or approved.

### Field result

Every extracted or classified field uses the same shape:

| Property | Values / rule |
|---|---|
| `state` | `supported`, `ambiguous`, `notFound` or `notApplicable` |
| `value` | Populated only when `state = supported`; otherwise `null` |
| `basis` | `explicit` when stated directly; `derived` when classified from multiple evidence elements |
| `evidenceRefs` | One or more references when supported or ambiguous |
| `note` | Optional concise explanation; never hidden reasoning or a confidence claim |

No numerical confidence score is used as permission to accept a financial fact. `notFound` is honest absence; whether that absence blocks progress depends on the required-field rules below.

### Evidence reference

Each reference contains:

- application-supplied `documentId`;
- one-indexed `pageNumber`;
- a short supporting text snippet or visible label/value.

The current strict schema has no page-region field; regions/highlighting would require a schema change.

References may point only to supplied documents and pages. Category may use multiple references. A value without support is rejected rather than silently saved.

## 5. Common output fields

| Field | Required for policy assessment | Extraction rule |
|---|---:|---|
| `category` | Yes | `air`, `meals` or `groundTransport`; suggested by A1 unless locked by the user |
| `merchant` | Yes | Supplier shown on the receipt; do not substitute an airline when the actual charging merchant is an agency |
| `receiptDate` | Yes | Date of the receipt/transaction, not an Air travel date; ambiguity requires user input |
| `originalAmount` | Yes | Receipt total as a decimal string; do not calculate or itemise it |
| `transactionCurrency` | Yes | ISO 4217 currency explicitly shown or unambiguously identified from evidence |
| `vatAmount` | No | Extract only when explicitly stated; otherwise `notFound` and blank |

The receipt file link is created by application code from the authorised `documentId`; it is not generated by A1. GBP equivalent, FX rate, FX conversion date and report total are also outside A1. Once `receiptDate`, amount and currency validate, deterministic code performs the agreed receipt-date conversion.

## 6. Category-specific outputs

### Air

| Field | Required | Rule |
|---|---:|---|
| `journeyType` | Yes | `oneWay` or `return`; user can correct |
| `origin` | Yes | Departure airport/city supported by evidence |
| `destination` | Yes | Arrival airport/city supported by evidence |
| `departureDate` | Yes | Travel date, distinct from `receiptDate` |
| `returnDate` | For return only | `notApplicable` for one-way; must not precede departure |
| `cabinClass` | Yes | Extract from the receipt or permitted supporting confirmation. The employee may correct the value, but the correction remains `user` provenance and cannot pass the cabin-policy check without supporting evidence. If absent or ambiguous, request clearer/additional evidence rather than accepting an unsupported self-declaration. |

Flight number, departure time, ticket number and booking reference are outside the minimum contract. They can remain visible in evidence without becoming structured required fields.

### Trusted grade and cabin-policy boundary

A1 extracts cabin class; it never receives or determines employee grade. Server code loads the read-only seeded employee profile for the owning demo session. This version uses the Employee/Manager toggle and no Supabase employee/manager Auth. Neither a connected Gmail address nor a submitted form establishes grade. Do not provide an employee-editable grade field. A production version would replace demo ownership with persistent verified identity and controlled profiles.

The synthetic policy baseline is defined by clauses AIR-02 through AIR-05 in [Synthetic_T&E_Policy.md](../policy/Synthetic_T&E_Policy.md):

| Employee grade | Maximum permitted cabin |
|---|---|
| A–C | Economy |
| D–F | Premium Economy |
| G | Business |

Interpret these as maximum permitted cabins: an employee may book a lower cabin. Because this is a fixed table, deterministic policy code—not an LLM—maps the trusted grade to the maximum cabin and compares it with the evidence-supported booking. A2 receives that result and the applicable policy clause so it can explain the finding consistently. It does not need the employee's email or full profile. An unknown/unlinked grade produces **Employee profile incomplete** and blocks the cabin check; it must not default to the highest allowance or be routed as policy ambiguity. The manager cannot change the grade or override the policy.

### Meals

| Field | Required | Rule |
|---|---:|---|
| `mealType` | Yes | `breakfast`, `lunch` or `dinner`; use explicit wording, items and/or time context, never amount alone |

When the evidence does not establish meal type reliably, return `ambiguous` or `notFound`. Attendees, payment method and item-level food breakdown are excluded.

A1 always returns the full receipt total as `originalAmount`; it never replaces that value with a meal allowance. After FX conversion where required, deterministic policy code calculates the GBP claim amount and any amount above the policy limit. A2 may explain the resulting **Adjusted to policy limit** finding, but neither agent performs the cap arithmetic.

The Meal policy permits one claim for each employee, receipt date and meal type: one meal from one restaurant supported by one final receipt. A1 reports additional apparent receipt documents or conflicting restaurant identities as issues; it does not add their amounts, merge them or create separate candidates to fill the allowance. Application code also checks other active expenses for the same employee/date/meal-type key before submission. Exact duplicate images of the same receipt are identified through document findings and application hashes so code can deduplicate them without treating them as a policy breach. When document identity is unclear, require human review.

### Ground Transport

| Field | Required | Rule |
|---|---:|---|
| `transportType` | Yes | `publicTransport` or `taxi`; user can correct |
| `origin` | No | Extract if explicit; absence never blocks |
| `destination` | No | Extract if explicit; absence never blocks |
| `businessJourney` | Yes | `yes`/`no` from visible evidence; otherwise leave unresolved for employee confirmation |
| `penaltyAmount` | Yes | Nonnegative decimal for separately identified cancellation/penalty charges; zero only when supported, otherwise unresolved |

Vehicle details, distance, passenger count and a separate tip field are excluded. A tip already included in the receipt total stays within `originalAmount`.

## 7. Missing, ambiguous and conflicting evidence

A1 reports facts; it does not write the user-facing question. Each issue contains the affected field, a reason code and its evidence references. The workflow service or A4 turns that issue into concise UI copy.

| Situation | A1 result | Workflow behaviour |
|---|---|---|
| Required fact absent | `notFound` + `missingRequired` | Show one targeted request for information |
| Two plausible values | `ambiguous` + `ambiguousEvidence` | Show the evidence and ask the employee to choose/correct |
| Receipt and supporting document disagree | `ambiguous` + `conflictingEvidence` | Never select silently; require review |
| Optional VAT absent | `notFound`, no blocking issue | Leave VAT blank |
| Optional Ground Transport route absent | `notFound`, no blocking issue | Continue |
| Required page unreadable | `couldNotRead` or field issue | Ask for a clearer document; do not route to policy specialist |
| Unsupported category | `unsupported` + `unsupportedCategory` | Explain that the POC supports only the agreed taxonomy |
| Text in a document instructs the model | Ignore as document content | Record no special authority; application rules remain unchanged |

Astra presents each targeted question in chat and automatically opens the affected expense fields and original evidence alongside it; the issue carries an application-validated expense reference, not model-selected access permission. An Open expense action supports revisiting the question. The agent does not maintain a live session while waiting. A user response creates a new expense revision and, when needed, a new bounded extraction job.

## 8. Category correction and human precedence

1. A1's category and fields are saved as AI suggestions with evidence provenance.
2. The category selector remains editable during preparation/correction.
3. When the employee corrects category or type, the application creates a new expense revision and records the value as `user` provenance.
4. Common human-corrected fields remain locked. Old category-specific values become inactive and cannot affect policy, totals or export.
5. If new category-specific facts must be extracted, code calls A1 again with `categoryOverride` and `lockedHumanFields`. A1 cannot reverse the human category selection.
6. The applicable fields become enabled; other category fields remain visible, greyed out and labelled **Not applicable**.
7. Validation and policy assessment rerun for the new revision. Previously approved snapshots remain immutable.

User corrections preserve human authority and an inspectable revision history. Learning, fine-tuning, correction memory and automatic correction-to-evaluation ingestion are out of scope. Synthetic engineering evals/regressions remain part of development; they do not consume customer correction history.

## 9. Deterministic acceptance gates

Application code rejects or pauses an A1 result when any of these checks fail:

- schema, enum, date or decimal format is invalid;
- returned job/revision identifiers do not exactly match the input;
- an evidence reference points outside the supplied document bundle;
- a supported field lacks an evidence reference;
- `originalAmount` is not positive or currency is not a supported ISO code;
- explicit VAT is negative, exceeds the receipt total or uses a conflicting currency;
- Air return chronology is invalid or category-specific fields do not match the active category;
- A1 attempts to change a locked human field;
- required fields remain `notFound` or `ambiguous`;
- the result belongs to a stale expense revision.

The current adapter makes one structured-output call with no SDK retries and no schema-repair call. Invalid structure is rejected; only transient provider failures are eligible for the bounded worker retry path, with a new persisted reservation. Technical failure is shown as processing failure, not policy denial.

## 10. Handoff to deterministic services and A2

When A1 passes validation:

1. Persist the candidate and field-level provenance against the current revision.
2. If required information is missing, stop and request it.
3. Use validated `receiptDate`, original amount and currency to perform deterministic FX conversion and store the original/full-GBP values.
4. Run deterministic field and numeric policy rules, including any applicable Meal cap, and store the claim amount and excluded excess separately.
5. Produce A2 findings with deterministic code using only validated active facts and applicable policy clauses; no separate A2 model call is made.

A2 never receives inactive fields from a prior category. A1 does not receive A2's finding as evidence for changing receipt facts.

## 11. Evaluation contract

Create a labelled held-out set covering all supported categories and the following cases:

- Air one-way and return, multiple dates, agency versus airline merchant, missing cabin and conflicting confirmations;
- Breakfast, Lunch and Dinner with explicit evidence, ambiguous evidence and an amount-based classification trap;
- a Meal with one final receipt, multiple receipts, multiple restaurants and duplicate images of the same receipt;
- Taxi and public transport with and without route information;
- GBP and foreign-currency receipts; VAT explicit and absent;
- unclear receipt date versus Air travel date;
- multiple documents, duplicates, contradictions and unreadable pages;
- user category correction with locked human fields;
- unsupported accommodation evidence;
- prompt-injection text embedded in a receipt.

Measure:

| Metric | Why it matters |
|---|---|
| Required-field exact match | Whether the report is prepared correctly |
| Category/type accuracy | Whether applicable fields and policy checks are selected correctly |
| Unsupported-value rate | Direct hallucination risk; invented financial values are critical failures |
| Missing/ambiguity detection | Whether A1 asks rather than guesses |
| Evidence-reference correctness | Whether reviewers can verify each populated value |
| Human-correction preservation | Whether reruns respect user authority |
| Schema-valid result rate | Whether code can use the output reliably |
| Latency, tokens and cost per expense | Whether the workflow is viable |

The frozen receipt gates retain 95% required-field accuracy, 90% readable reviewability, required safe pauses and zero accepted critical errors; the paired policy gates are recorded separately. No live baseline has passed. Abhinav selected GPT-6.1 Sol on 8 October; migrate its settings and cost controls next, then measure quality, latency and spend against the preserved Luna baseline without retuning held-out labels.

## 12. Implemented decisions and remaining evidence

The strict category schema is v0.2; the v0.1 Meal contract remains available for compatibility. Airports/cities use a small fixture-backed alias map (including LHR/CDG), preserving city/airport distinctions and unsupported text rather than guessing. Canonical cabins are `economy`, `premiumEconomy` and `business`; known aliases such as coach are mapped, while unsupported branded fares remain unresolved. A complete result requires a readable selected primary final receipt; supporting confirmations cannot replace it.

JPEG/PNG/PDF originals are limited to 10 MiB and ten pages each; the complete selected A1 bundle is limited to ten pages and a configured conservative input envelope. Validation uses a 15-second wall timeout and 10-second CPU cap, plus 512 MiB on Linux. Native macOS lacks that memory cap. Ground Transport rules and policy effective date/rounding have been owner-reviewed and activated locally.

Remaining evidence is the selected model migration, private account access, approved paid budget, live category extraction and image/PDF robustness, and actual latency/token/cost/held-out results. Use the [one-item-at-a-time backlog](../product/BUILD_STATUS.md#live-pending-backlog).
