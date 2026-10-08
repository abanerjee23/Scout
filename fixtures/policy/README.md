# Frozen policy comparison

Version policy-1, frozen 8 October 2026 before live model tuning. Twelve development and twelve held-out synthetic questions cover direct, paraphrased, combined rules, unsupported coverage, stale/conflicting source claims and prompt injection. The malicious/stale text is question data, never an ingested approved source. No supplementary FAQ document has been approved or indexed.

Run each question with the same pinned model/prompt/source version in `rag` and `fullContext` modes. `scripts/policy_eval.py --inputs --split development` emits only model inputs, never rubric labels. Held-out emission/scoring requires `--release-heldout`. Keep provider results and a human review of semantic correctness separate from input files. No user corrections or private receipts are collected.

The scorer checks exact registered citations and a human verdict against the rubric; exact quotes alone cannot establish semantic correctness. A missing, failed or unreviewed answer counts against coverage and quality. Critical false permission must be zero, supported-answer quality at least 90%, and every critical case must be reviewed. Report measured answer latency, token/cost coverage and denominators separately for each mode. Missing timing/cost stays unmeasured, not zero. A paired comparison must include every case in both modes. The small synthetic set does not establish population reliability.

No live baseline has been measured. If a held-out failure informs tuning, record the exposure in the iteration log and replace it with unseen cases before another release claim. A provider runner must use the application queue and persistent reservation budget; this scorer makes no network calls and cannot approve or activate a policy.
