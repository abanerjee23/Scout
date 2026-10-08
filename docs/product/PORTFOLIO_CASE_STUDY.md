# Unloop — evidence-based expense preparation

**Candidate, not a completed live product.** This case study records demonstrated engineering and separates proposed success metrics from unmeasured outcomes. Updated 8 October 2026.

## User problem and product judgment

A travelling employee must find receipts, reconcile currencies and Meal allowances, answer evidence questions, and prepare a claim a manager can inspect. A manager needs to approve correct lines without releasing a disputed line or losing the original submitted version. The working hypothesis is that assisted extraction, contextual questions and selective approval reduce active preparation time while retaining human control.

AI is used for uncertain document interpretation and grounded policy-language assistance. Report intake, ownership, versions, Decimal money, FX date acceptance, caps, duplicate prevention, submission and approval are code-owned. Deterministic question templates and outcome explanations avoid unnecessary model calls. Extraction cannot infer grade, waive policy, submit or approve. No automatic learning from user corrections is implemented.

## System and trust boundaries

React/FastAPI use a server-owned expiring demo session with explicit Employee/Manager personas. This is not production identity/role authorization. PostgreSQL retains original receipt bytes separately from evidence lists and owns revision-bound leased jobs. The OpenAI Agents SDK produces strict document/fact suggestions; validated reference IDs, selected primary/supporting evidence and human locks constrain what can become a saved fact. A3 uses approved immutable source snapshots, exact pgvector retrieval and mandatory rule passages; its answer cannot change authoritative facts or decisions. Exact quotations validate citation structure, not semantic correctness.

```mermaid
flowchart LR
  E[Employee selects evidence] --> V[Bounded validation and retained originals]
  V --> A[Untrusted extraction suggestions]
  A --> C[Code validation and employee correction]
  C --> D[Exact-date FX and Decimal policy rules]
  D --> S[Explicit submitted snapshot]
  S --> M[Manager selects exact eligible lines]
  M --> R[Immutable approval release]
  R --> P[Processing ready and approved API]
  Q[Grounded policy help] --> E
```

Original receipt values remain distinct from full GBP value, claim and excluded amount. A £62 Dinner becomes a £50 claim and £12 excess; the original is retained. A voluntary £40 claim preserves the £62 receipt and shows £22 excluded. Conflicting Meal candidates require a choice; approved employee/date/type slots stay occupied across reports. Missing or contradictory evidence pauses. Unavailable receipt-date FX pauses. Evidence-supported Air cabins above trusted grade cannot be approved as exceptions.

## Demonstrated iteration

Cloud-to-local migration preserved the Git snapshot, ignored private configuration, local DB backups and separate hackathon repository. A macOS resource-limit incompatibility was isolated and fixed while preserving Linux validation limits. Later browser stress identified serialized GET locks, request/thread contention and a lost-cookie replacement race; owner mutation locks were retained, reads made concurrent, request admission bounded, and prior-use tabs require an explicit fresh session after cookie loss. Intermittent loading failures and an intermediate migrated-table CI failure are documented, not excluded from the record.

The ten-line real PostgreSQL acceptance scenario submits £320, releases nine lines for £270 and holds £50, then corrects/resubmits/releases the tenth for £45. The first release remains unchanged; approved total is £315 in two stable release records. Desktop/mobile UI journeys similarly release £50, hold £25, and separately release a corrected £20. Concurrent approval attempts cannot create a second processing record. Returned lines require explicit resubmission; manager discussions cannot replace submitted facts. This establishes deterministic workflow behavior on synthetic inputs, not model extraction quality or user-time savings.

## Evaluation and operations

The receipt release set has twelve development and twelve held-out labelled cases. The paired policy set has twelve development and twelve held-out questions covering paraphrases, combined rules, unsupported coverage, stale/conflicting claims and injection. Labels are excluded from model inputs; human semantic review supplements citation validation. Freeze gates before tuning and replace held-out cases exposed by failure analysis. Missing results/reviews count against coverage. Critical false permission and silently accepted wrong financial facts have zero tolerance in the designated release cases.

Proposed targets: at least 95% supported required-field accuracy, 90% useful readable receipts/correct supported policy answers, 30% less active user preparation time, receipt p95 below 30 seconds and policy-answer p95 below 15 seconds. None of these live metrics has yet been established. Measure paired manual/Unloop tasks including failed attempts, report sample sizes, cost/token coverage and local versus hosted timings. A small synthetic set cannot establish population-level reliability.

A1, embedding and A3 calls share persistent owner/global call and conservative reservation ceilings. Provider retries do not refund uncertain spend. The pinned Luna model and small embedding baseline support cost-aware experiments; do not upgrade automatically to hide failures. Galileo receives minimized diagnostics rather than receipt/Gmail/conversation content; actual trace delivery is still unverified. Original evidence and review history remain retained after access expires, with no automatic deletion workflow. Immutable review history blocks schema downgrade after submission.

## Remaining live release gates

Owner decisions on policy effective date/rounding, Ground Transport rules and paid budget; private API credentials/account availability; real extraction and complete primary/fallback FX journeys; Galileo trace confirmation; paired held-out receipt/policy results; Railway/Supabase app-schema runtime; exact HTTPS OAuth callback and human Gmail consent/attachment retrieval; hosted recovery/privacy checks; measured user-time/cost/latency. Teams is limited to in-app/copyable review context unless a real launch is separately configured and demonstrated. No payment or ERP posting is included.

A direct public ECB adapter check returned exact-date EUR→GBP `0.85373` for 1 October 2026 and left a 3 October weekend request Conversion pending. This is real adapter/date-handling evidence; it is not a live extracted-receipt journey or OXR fallback success.
