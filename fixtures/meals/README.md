# Meal fixtures v0.1

24 labelled synthetic scenarios: 12 development and 12 held-out. Each label has a source transcript and line-level evidence. Expected claims use the agreed policy; any FX observation is explicitly synthetic. Labels are not extraction results.

Run `uv run python -m unloop.fixture_check` to check source existence, evidence, split separation, and financial-label reconciliation. This checks fixture integrity, not AI quality. Expected pending outcomes are labels, not proof of implemented workflow gates.

Use `uv run python scripts/render_receipts.py` to render development transcripts to PNG in ignored `artifacts/local/receipts`. Use `--split all` when preparing a held-out run. These uniform images are bootstrap inputs only. Unreadable/missing-text cases are semantic placeholders; Phase 2 must add actual blur, varied layouts, scans, currencies and receipt imagery before claiming vision robustness. PDF and multiple-page coverage also arrive then.

The held-out set has been authored/validated but not used for prompt tuning. Do not expose it through the frontend or send expected labels to a model. Future runners must pass only documents as model input and score the result separately. No prompt or model exists in Phase 0. If tuning follows a held-out failure, move that case into regressions and replenish unseen coverage.

Limits and policy dates remain draft. FX examples have exact-penny results to avoid silently deciding rounding. Cross-report Meal uniqueness for the server-seeded demo employee, locked human fields, category corrections and shared manual/Gmail evidence intake need integration tests in Phases 1–3; document-level fixtures alone cannot prove them. Manager partial approval, returned-line resubmission and approved-history claim-slot preservation require Phase 5 tests. These fixtures are engineering eval inputs, not learned user corrections. See the [current build plan](../../BUILD_PLAN.md).
