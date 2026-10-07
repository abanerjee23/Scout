# Unloop — Product Iteration Log

**Build → Validate → Improve → Repeat**

Created: 28 September 2026  
Owner: Abhinav  
Status: ITER-001 closed; Phase 0 validated and Phase 1 next

## Purpose

Capture how Unloop improves through evidence: what we expected, what we built, what happened, what we learned and what we changed. This is the ongoing record of product judgment for the project and its portfolio story.

[BUILD_PLAN.md](BUILD_PLAN.md) defines delivery phases and acceptance targets. This log records the iterations within them. A phase may need several cycles, and an iteration may revisit an earlier phase when new evidence exposes a problem.

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
| [ITER-001](#iter-001--runnable-foundation-and-meal-fixtures) | Phase 0 / make the first slice buildable and testable | Closed | Keep scaffold; proceed to Phase 1 | [Validation record](artifacts/ITER-001_VALIDATION.md) |

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

## Initial cycle scope

Phase 0 should establish the runnable scaffold and labelled Meal cases. Validate that the app starts and the fixture harness can represent receipt facts, policy-capped claims and missing-information outcomes. Record that result as the first cycle; extraction quality, user time savings and model cost remain unmeasured until the relevant implementation exists.

### ITER-001 — Runnable foundation and Meal fixtures

**Date / phase:** 29 September 2026 / Phase 0  
**Status:** Closed  
**Previous cycle:** First cycle

**Frame:** The project has design documents but no executable application or examples against which to check it. Hypothesis: a runnable React/Flask scaffold, explicit extraction schema and 24 labelled Meal fixtures will make the first expense flow implementable without more broad design work.

**Success criteria:** frontend typecheck/build pass; Flask health endpoint responds; all 24 cases validate with 12 development/12 held-out separation; malformed extraction states are rejected; local preview clearly distinguishes synthetic expected outcomes from actual AI output. No model accuracy or user-time target can be measured yet.

**Build:** React/Flask scaffold, health endpoint, checkable worker entry point, strict A1 Meal output schema, 24 labelled cases, source receipt transcripts and a renderer, synthetic receipt/claim preview, dependency locks and CI configuration. Preview labels and disabled upload/save distinguish expected outcomes from implemented workflows. The receipt-first layout follows the frontend-design skill: evidence next to the financial result, readable amounts and mobile layout.

**Validate:** 17 backend tests, 2 browser tests, all fixture integrity checks, Ruff and the frontend build passed. Live Flask health endpoint responded. Desktop/mobile screenshots inspected. Full results and commands are linked in [ITER-001 validation](artifacts/ITER-001_VALIDATION.md). The first run found an incorrect fixture root; later checks/review found unsupported currency and misplaced VAT labels. All were corrected, including a VAT evidence regression check. No model runs occurred.

**Improve — Keep:** the scaffold meets Phase 0 criteria. Fixture preparation itself can contain unsupported labels; validating sources before evaluating a model prevents false quality conclusions. Store only relevant source facts and review evidence locations, not just numeric equality. No claim of improved AI quality is supported yet.

**Tradeoff:** the preview uses static expected examples and uniform generated receipts to allow early interaction review. This speeds feedback but provides no evidence of real extraction or photo robustness. Expand visual fixture diversity before Phase 2 model evaluation.

**Next action:** configure Supabase and build authentication/report/receipt persistence in Phase 1. All required external environment variables are absent in the inherited environment. Provider access and the exact Luna API identifier are unverified; credentials must be configured through secure setup, not pasted into chat.

**Revisit trigger:** failures in real receipt layouts, user confusion between original/claim values, or service integration constraints. Relevant targets for AI accuracy, cost and time saved remain unmeasured.

**Docs updated:** [Build plan](BUILD_PLAN.md), [README](README.md), [architecture status](Architecture.md), [A1 implementation note](Receipt_Extraction_Agent.md). Next cycle has not started.
