# Meal fixtures v0.1

24 labelled synthetic scenarios: 12 development and 12 held-out. Each label has a source transcript and line-level evidence. Expected claims use the agreed policy; any FX observation is explicitly synthetic. Labels are not extraction results.

Run `uv run python -m unloop.fixture_check` to check source existence, evidence, split separation, and financial-label reconciliation. This checks fixture integrity, not AI quality. Expected pending outcomes are labels, not proof of implemented workflow gates.

Use `uv run python scripts/render_receipts.py` to render development transcripts to PNG in ignored `artifacts/local/receipts`. Use `--split all` when preparing a held-out run. These uniform images are bootstrap inputs only. Unreadable/missing-text cases are semantic placeholders; actual blur, varied layouts, scans, currencies and receipt imagery remain necessary before claiming vision robustness. PDF/multiple-page structural validation exists, but live extraction quality on those inputs remains unmeasured.

The held-out set has been authored/validated but not used for prompt tuning. Do not expose it through the frontend or send expected labels to a model. Future runners must pass only documents as model input and score the result separately. No prompt or model existed in Phase 0; a bounded SDK adapter is now implemented, with actual model-quality runs still pending. If tuning follows a held-out failure, move that case into regressions and replenish unseen coverage.

Policy review/local activation is complete: £15/£25/£50 limits, effective 1 October 2026 and Decimal ROUND_HALF_UP per line. Frozen labels retain their original exact-penny FX examples. Real PostgreSQL/browser tests now cover cross-report Meal uniqueness, locked human fields, category corrections, shared intake, partial approvals, resubmission and approved-history claim slots; document-level fixtures alone do not prove those workflows. Live extraction and Gmail acceptance remain pending. [Current evidence and backlog](../../docs/product/BUILD_STATUS.md). These fixtures are engineering eval inputs, not learned user corrections. See the [current build plan](../../BUILD_PLAN.md).
