# Build, test, ship, repeat

Updated: 9 October 2026
Repository: [abanerjee23/UnLoop](https://github.com/abanerjee23/UnLoop)

Abhinav authorized phased development and GitHub publication on 7 October. This is the full-version repository; the separate hackathon app uses abanerjee23/Un-Loop and remains independent. The root [build plan](../../BUILD_PLAN.md) preserves the original scope and acceptance gates; the [current ledger/backlog](BUILD_STATUS.md) records subsequent decisions. Development runs locally, with one active chat and one pending item at a time.

## One delivery cycle

1. Choose one demonstrable increment within the current phase. Record the hypothesis and acceptance criteria in the [iteration log](PRODUCT_ITERATION_LOG.md) before implementation.
2. Build the complete increment, with actual failure/recovery behaviour and honest synthetic/live labels. Preserve existing working paths and phase scope.
3. Run relevant deterministic, integration, model-quality and browser checks. The first repository publication runs all scaffold checks. A phase needing a provider cannot be marked complete from mocks or configuration presence. Record missing integrations separately.
4. Fix failures and review the change, documentation, migrations and staged files. Exclude secrets, installed dependencies, caches, generated screenshots/build output and held-out answer leakage into model/UI inputs.
5. Commit a coherent, tested increment with a clear message and push directly to `main` using ordinary fast-forward Git operations. The owner confirmed this single-contributor workflow on 9 October. Preserve remote history, reconcile new remote changes before pushing and exclude unrelated local work.
6. Check the GitHub Actions run for the published commit. If it fails, diagnose, fix, validate and publish a follow-up. Start the next increment only when required checks pass or a documented external blocker requires independent work. Report the commit and actual CI status.
7. Verify the published commit on `main`. Branches and pull requests are optional and should be used when the owner requests them, rather than as a routine publication step. Publishing source does not complete unverified provider or hosted gates.
8. Record measured results, limitations and the keep/revise decision. Continue with the next item in the live backlog, keeping external gates explicit.

GitHub publication is what “ship” means for this requested loop. Railway deployment is separately tracked in the plan and can occur early for a useful hosted slice; a successful push does not prove hosted integration or reimbursement.

## First deliveries

| Delivery | Contents | Required proof |
|---|---|---|
| Baseline | Existing Phase 0 scaffold, organized current docs and CI | Ruff, backend/fixture/worker checks, frontend build and browser checks; successful GitHub publication/CI |
| Phase 1A | Server-owned persona sessions and confirmed report creation | Ownership/role actions, ambiguous input, reload and actual PostgreSQL persistence |
| Phase 1B | Chat/workspace uploads, durable evidence and recoverable worker jobs | Signature/size/page validation, private evidence access, deduplication and interrupted-job recovery |
| Phase 1C | Consent-bound Gmail intake through the same evidence pipeline | Actual attachment bytes, callback/token lifecycle, denied/revoked/empty/partial scan and idempotent retry |

These are small increments of Phase 1, not new product phases. Database configuration must be available for the live persistence gate. The existing GCP setup for aban.hackathon@gmail.com is reused, with callbacks verified for this application.

## Checks and evidence

[Local development](LOCAL_DEVELOPMENT.md) contains setup and validation commands. GitHub Actions runs backend checks and frontend build/browser checks on pushes and pull requests. Later increments extend CI with meaningful tests for their contracts. Provider checks require secure test configuration; never print credentials or call an unavailable service a pass.

Keep source, tests, migrations and relevant docs together in commits. A documentation-only follow-up needs documentation validation rather than a new model experiment; automatic CI may still rerun the scaffold suite. Engineering iterations/evals do not introduce excluded correction learning.

At each phase boundary report: visible behaviour delivered, commit link, tests/CI, actual integration evidence, unresolved limits, and the next increment. No automatic claim of quality, savings or production readiness follows from committing code.
