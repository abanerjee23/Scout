# Gmail evidence integration

Updated: 8 October 2026
Status: Phase 1C implemented and locally tested; actual full-version Gmail consent/bytes and hosted deployment remain unverified. See [validation](../validation/PHASE_1C_VALIDATION.md) and [deployment handoff](PHASE_1C_DEPLOYMENT.md).

[Vision](../../Unloop_Vision.md), [architecture](../../Architecture.md) and [build plan](../../BUILD_PLAN.md) govern the product. This document specifies optional Gmail intake alongside independent JPEG/PNG/PDF uploads.

## Existing assets and current boundary

Use the existing Google Cloud setup associated with **aban.hackathon@gmail.com**. The separate hackathon app contains configured OAuth/encrypted-token/attachment code for that mailbox; it is a reference for the Python implementation, not proof of the new application's callback, scan or deployment. Do not modify or migrate the other repository as part of this docs update.

Keep the demo mailbox restriction visible. Report creation needs no manager details and persona switching needs no application login. Connecting Gmail is still a Google account authorization step; it does not assign the app's manager role.

## User and server flow

1. Employee chooses Connect Gmail or Upload receipts; uploads require no Gmail connection.
2. Redirect to Google for account choice/read permission. Bind random, expiring, single-use OAuth state to the initiating demo session. Exchange the authorization code server-side at the exact configured callback; request offline access where needed and handle absence/expiry/revocation of refresh credentials. Store encrypted tokens and connected mailbox per owner. [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
3. Display the connected account. Separately ask permission for a specific report scan with an explicit search window. A connection is not consent to continuous scanning. Bind scan authorization to the session/report revision, window and one operation with bounded expiry/retries.
4. Server retrieves candidate message metadata and supported attachment bytes. Retain mailbox, message/attachment IDs, received timestamp, import time and document hash for provenance/deduplication. Limit model input to selected evidence, not the whole inbox.
5. Shared intake validates files, stores original bytes in PostgreSQL and queues the same extraction flow used by uploads. Imported evidence retains Gmail provenance; intake source does not change submission eligibility. Do not label every import as an upload or require a special AI source flag to submit.
6. Return scanned/imported/skipped counts and visible partial results. Questions about uncertain expense dates or attachment association open the relevant expense automatically beside chat. Technical failure does not turn uncertain evidence into a ready claim.

Read-only Gmail scope can read broadly within the mailbox; Google does not enforce a receipt-only or date-only permission. Explain this at connection, while Unloop enforces the disclosed bounded search. Do not request send/modify access for this feature. [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)

## Search and operating limits

Use receipt/invoice/booking/ticket terms and supported attachments as candidate discovery, not proof of a claim. Email arrival is not the receipt/service date. A booking lookback can include earlier confirmations; disclose it and validate the user's requested report dates separately. Ambiguous matches require review rather than silent inclusion/exclusion.

Candidate initial scan bounds, inherited from the hackathon for validation: report duration at most 31 days, search from 90 days before report start through seven days after its end, at most 15 candidate messages, at most ten imported files and 40 MiB aggregate bytes. Common file bounds are 10 MiB/file and ten pages. These bounds are implemented and deterministically tested; they do not guarantee completeness. Actual consent/retrieval and truncated/partial-result behavior still need live validation. Body-only receipts, old bookings and unsupported formats may require manual upload. Never bypass scan bounds after ambiguous date parsing.

Use timeouts/bounded backoff, durable import/scan IDs and revision checks. Repeating a scan reuses already imported attachment identities and document hashes. Partial failures retain prior files and refresh their UI state; a retry must not duplicate expense candidates. Capture failure categories without exposing tokens/email content in logs.

Handle denied consent, wrong demo account, revoked/expired access, empty results, unsupported/oversized files, quota/outage, worker interruption and partial import as separate recoverable outcomes. Require fresh authorization for a new scan after permission expires.

## Disconnect and data lifecycle

Disconnect removes encrypted connection credentials and stops access, with a separate provider revocation outcome. The worker sweeps expired-session credentials. Deterministic PostgreSQL/provider tests cover refresh, key rotation, disconnect races and expiry cleanup; actual Google consent/revocation/refresh still require live proof. Managers inspect submitted evidence only, never the mailbox or tokens. Imported evidence remains retained after disconnect or session expiry. No user-facing evidence deletion or automated retention service is implemented; immutable submission/release history also prevents deleting associated review records. A supported retention/deletion policy and verified backup/restore remain necessary before real-data use.

## Future users connecting their own Gmail

One application integration can serve individual consenting users; each connection and credential set belongs to a persistent owner. Multi-user production needs authenticated owner identity, isolation and genuine manager authorization. Removing the demo allow-list is insufficient. Google sign-in is a possible identity route with no separate password, but identity and Gmail access must be implemented as distinct explicit contracts. Corporate accounts may be subject to administrator restrictions.

The read-only scope is restricted. Public deployment generally needs verification; server-side storage/transmission of restricted data can require a security assessment unless an exception applies. Verify the actual audience and requirements before public onboarding. Current GCP setup does not prove these gates passed. [Restricted-scope requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)

No continuous monitoring, arbitrary inbox providers, mail sending, learning/training from corrections or reuse of Gmail content for training is introduced. This version connects the dedicated demo Gmail mailbox; broader onboarding is a later readiness step.

## Proof required

Phase 1 needs actual authorized attachment bytes retrieved and stored through the shared pipeline, plus denied/revoked/empty/partial/retry cases. Phase 6 repeats the flow on Railway with exact HTTPS callback, token refresh and owner isolation. Synthetic imports and configured variables are useful checks but cannot count as live Gmail integration.
