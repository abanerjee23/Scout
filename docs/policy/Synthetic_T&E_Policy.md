# Unloop — Synthetic Travel & Expense Policy

**Policy source for the proof of concept**

- Version: 0.3
- Updated: 8 October 2026
- Owner: Abhinav
- Status: Owner reviewed and approved for local activation
- Effective date: 1 October 2026
- Current coverage: Air, Meals and Ground Transport

[Product vision](../../Unloop_Vision.md) and [architecture](../../Architecture.md) define the current demo. Revision 0.3 adds reviewed Ground Transport rules, the effective date and GBP rounding convention. Existing Air and Meal limits and clause identifiers are unchanged. Abhinav completed policy review on 8 October 2026 and authorized local activation.

## 1. Purpose and applicability

This synthetic policy exists to test Unloop's expense assessment and in-product policy guidance. It is not the policy of a real employer and must not be used for real reimbursement decisions.

This version applies to Air, Meals and Ground Transport in the UK-company proof of concept for receipts dated on or after 1 October 2026. The employee's report currency is GBP. Earlier receipts remain outside this active version and cannot be submitted under it.

Clause IDs are stable citation labels for Unloop. A later policy version may amend a clause, but must not reuse its ID for a different rule. Unloop must show the policy version and applicable clause when explaining a finding.

## 2. General evidence rules

### GEN-01 — A receipt is required

Every expense line must have a receipt or invoice attached before it can be submitted. A booking confirmation may provide supporting journey or cabin details, but does not replace the receipt or invoice.

### GEN-02 — Expense facts must be supported

The merchant, receipt date, original amount and transaction currency must be supported by the attached receipt or invoice. Category-specific facts required by this policy must be supported by the receipt or a permitted supporting document.

The employee may correct an extraction error. A correction does not become policy-compliant merely because it was entered by the employee; required evidence must still support it.

### GEN-03 — Missing and ambiguous evidence

If required evidence is missing, unreadable, contradictory or ambiguous, the expense is **Needs information**. Unloop must ask for the specific missing fact or clearer evidence. It must not guess, deny the expense as noncompliant, or treat an evidence problem as policy ambiguity.

### GEN-04 — VAT

VAT may be recorded when it is explicitly stated on the receipt or invoice. If it cannot be extracted reliably, the VAT field remains blank and does not by itself block the expense.

### GEN-05 — Authority to approve

The employee remains responsible for reviewing the prepared expense and explicitly submitting eligible lines. The manager remains responsible for approving the exact submitted version and may release eligible selected lines while holding or returning others. Partial approval does not waive any applicable rule or imply approval of pending lines. Approved amounts are immutable processing-ready records, not proof of reimbursement.

The demo uses an Employee/Manager toggle within a server-owned session and predefined manager routing, without employee/manager login or manager details at report creation. This does not establish a production identity/role system.

## 3. Air expenses

### AIR-01 — Supported journey types

An Air expense may describe a **One-way** or **Return** journey.

The following facts are required:

- origin;
- destination;
- departure date;
- return date for a Return journey; and
- cabin class.

The return date must not be earlier than the departure date. Flight number, departure time, ticket number and booking reference are not required by this policy version.

### AIR-02 — Trusted employee grade

Cabin entitlement is determined using the employee grade stored in the server-seeded employee profile for the owning demo session. The employee cannot enter or edit their own grade. A connected Gmail address, typed email or persona toggle is not evidence of grade. A production release requires a controlled profile linked to a persistent verified owner; the current demo does not use Supabase employee/manager Auth.

If the profile does not contain a valid grade, the expense is **Employee profile incomplete** and the cabin check cannot finish. This is a profile-data problem, not a policy exception, and it must not default to the highest cabin allowance.

### AIR-03 — Maximum permitted cabin

The maximum permitted cabin is:

| Employee grade | Maximum permitted cabin |
|---|---|
| A–C | Economy |
| D–F | Premium Economy |
| G | Business |

An employee may travel in any lower cabin. For example, a Grade G employee may use Economy, Premium Economy or Business; a Grade A–C employee may use Economy only.

For this version, the cabin order is **Economy → Premium Economy → Business**. Airline-specific fare names must be mapped to one of these three cabins before the rule can be applied. If the mapping is not established, the expense is **Needs information** rather than automatically compliant or noncompliant.

### AIR-04 — Cabin evidence

Cabin class must be supported by the receipt or a permitted booking confirmation attached to the expense. The employee may correct an incorrectly extracted cabin, but an unsupported self-declaration is not sufficient evidence for the cabin check.

If the available documents do not establish the cabin class, the expense is **Needs information**.

### AIR-05 — Cabin compliance outcome

An Air expense is **Compliant** with the cabin rule when its evidence-supported cabin is at or below the maximum allowed for the trusted employee grade.

An Air expense is **Noncompliant** when its evidence-supported cabin is above that maximum. Unloop must identify the booked cabin, the permitted maximum and this policy clause. The employee may correct an evidence or profile error through the appropriate controlled process, or exclude a genuinely noncompliant line before submitting the report. The manager cannot approve it as an exception.

## 4. Meal expenses

### MEAL-01 — Meal type

Every Meal expense must be classified as **Breakfast**, **Lunch** or **Dinner**. Unloop may use explicit receipt wording, purchased items and time context to suggest the meal type, but must never infer it from the amount alone. If the evidence does not establish the type reliably, the expense is **Needs information** and the employee must confirm or correct it before the allowance is applied.

### MEAL-02 — Preserve the receipt amount

The total shown on the receipt remains the original expense amount and must never be overwritten by a policy allowance. For a foreign-currency receipt, Unloop first converts the full receipt amount to GBP using the rules in CUR-02 and CUR-03.

The expense record must distinguish:

- the original receipt amount and transaction currency;
- the full receipt amount converted to GBP, where conversion is required;
- the applicable GBP meal allowance;
- the GBP amount included in the claim; and
- any GBP amount above the allowance that is not included in the claim.

### MEAL-03 — Automatic adjustment to the policy limit

If the full GBP receipt amount is within the allowance for the confirmed meal type, the full amount is included in the claim.

If it exceeds the allowance, Unloop automatically sets the claim amount to the policy limit. The difference is shown as **Amount above policy limit** and is not included in the report total or downstream approved amount. The employee must not be required to calculate or re-enter the maximum claim manually.

The expense receives the user-facing outcome **Adjusted to policy limit** and remains eligible for review and submission at the adjusted amount. Unloop must state the receipt amount, applicable allowance, claim amount, excluded difference and governing clause. The employee may reduce the claim further or exclude the expense, but cannot increase it above the policy limit. The manager cannot override the limit.

The amount comparison and adjustment are deterministic calculations. AI may explain the adjustment in plain language, but must not perform or control the arithmetic.

### MEAL-04 — Meal allowances

The maximum claim amounts are:

| Meal type | Maximum claim amount |
|---|---:|
| Breakfast | £15 |
| Lunch | £25 |
| Dinner | £50 |

These are separate GBP limits for each meal, not a combined daily allowance or a budget that can be filled using several receipts. Unloop applies the limit only after the meal type is supported or confirmed. The receipt amount must never be used to infer whether the expense is Breakfast, Lunch or Dinner.

### MEAL-05 — Tips and service charges

The complete receipt total, including any tip or service charge shown on the receipt, is treated as the Meal amount and is subject to the same Breakfast, Lunch or Dinner limit. There is no separate additional allowance and no tip or service-charge itemisation in the POC.

### MEAL-06 — One meal, one restaurant, one receipt

For each employee, receipt date and meal type, exactly one Meal expense may be claimed. That expense must represent one meal purchased from one restaurant and must be supported by exactly one final receipt from that restaurant.

Unloop must not combine multiple receipts into one Meal expense, add several smaller receipts up to the policy limit, or allow one meal to be split across multiple expense lines. For example, ten £5 Dinner receipts cannot be combined into a £50 Dinner claim. If more than one receipt or Meal expense exists for the same employee, receipt date and meal type, the affected expenses are **Needs information** while the employee selects the single receipt to claim and excludes the others. If the submitted claim still depends on multiple receipts or restaurants, it is **Noncompliant** and cannot proceed.

Two uploads that are verified as copies of the same receipt are a duplicate-upload problem, not two policy receipts. Unloop should retain one evidence record and must not create or pay a second claim.

## 5. Ground Transport

### GROUND-01 — Business journeys

Taxi and Public Transport are eligible for documented business journeys. Route fields are optional. No mode preference applies. Business purpose must be established; missing or ambiguous information pauses the claim for clarification.

### GROUND-02 — Receipt amount and excluded penalties

Eligible business transport uses the full receipt amount, including listed tips and service charges. Separately identified cancellation and penalty charges are excluded before the GBP claim is approved. The business purpose and penalty amount, including confirmation of zero penalties, must be established before the line can proceed.

For foreign-currency expenses, convert and round the full receipt amount and separately identified penalty amount to GBP using the same receipt-date rate, then deduct the rounded penalty amount from the rounded full amount. Preserve the original receipt total and show the excluded amount.

### GROUND-03 — Ground Transport limits

No additional amount cap applies to eligible Taxi or Public Transport in this synthetic demo. The owner approved this rule as part of the policy review.

## 6. Currency and conversion

### CUR-01 — Submission currency

The report submission currency is GBP. A GBP expense is recorded in GBP and does not require foreign-exchange conversion.

### CUR-02 — Foreign-currency expenses

For an expense incurred in another currency, Unloop must retain and display:

- the original amount and transaction currency;
- the converted GBP amount;
- the exchange rate source; and
- the conversion date.

Conversion changes neither the original amount nor its currency.

### CUR-03 — Conversion date

The FX conversion date must equal the receipt date. It must not be replaced by the upload, processing, travel or report-submission date.

Unloop first uses a saved acceptable rate for that source, currency pair and date. Otherwise it requests the receipt-date rate from Frankfurter pinned to ECB data, with Open Exchange Rates as the approved fallback. If neither source supplies an acceptable matching-date rate, the expense is **Conversion pending** and cannot be submitted until the conversion is resolved. An earlier rate must not be relabelled as a receipt-date rate.

The fallback rate may have a different published basis from the ECB rate; Unloop must preserve the provider and actual rate record used rather than present the sources as identical.

### GBP rounding convention

Calculate money using Decimal arithmetic. Round GBP line amounts to two decimal places using ROUND_HALF_UP: round to the nearest penny, with exact halfway values rounded up. For example, £17.0746 becomes £17.07 and £17.075 becomes £17.08. Apply the reviewed allowance or penalty deduction to these rounded amounts. Report and approved-release totals sum the rounded line claim amounts so the displayed lines agree with their total. AI does not control the arithmetic.

## 7. Interpretation and user-facing outcomes

Unloop may produce the following user-facing outcomes for rules covered by this policy:

| Outcome | Meaning | Required next step |
|---|---|---|
| **Compliant** | Required facts are available and the expense meets all applicable rules in this version | Employee reviews the expense before submission |
| **Adjusted to policy limit** | A Meal receipt exceeds its allowance and Unloop has capped the claim deterministically | Show the original, limit, claim amount and excluded difference; employee reviews before submission |
| **Noncompliant** | Supported facts clearly breach an applicable rule | Explain the rule; employee corrects an error or excludes the line |
| **Needs information** | A required fact or evidence is missing, unreadable, contradictory or ambiguous | Ask a targeted question or request evidence |
| **Employee profile incomplete** | Trusted grade is unavailable or invalid | Correct the controlled employee profile; do not ask the employee to self-declare grade |
| **Conversion pending** | No acceptable receipt-date FX rate is available | Preserve the draft and retry or resolve the rate; do not guess |
| **Sent to T&E specialist for review** | Available evidence exposes a genuine policy interpretation conflict that this source set cannot resolve | Show a clearly labelled simulated handoff in the POC; no real specialist is notified |

**Sent to T&E specialist for review** is not used for missing evidence, incomplete profiles, unsupported categories, retrieval outages or other technical failures. Those conditions keep their own explicit status. The specialist handoff is simulated in V1 and does not grant approval.

When this policy contains no applicable rule, Unloop must say that the current policy does not answer the question. Absence of a rule is not permission and must not be converted into an invented restriction.

## 8. Source precedence and version use

The approved governing clauses take precedence over supporting FAQ or guidance material. Supporting material may explain a rule but cannot change an allowance, create an exception or override a clause.

Unloop must assess an expense and answer related policy questions using the same applicable policy version. It must record the version used. A newer draft must not silently replace the version attached to an existing assessment or approved report.

Only this approved version is active in the POC. Receipts dated before its effective date remain unassessed under this version. Before activating a later version, define historic-version selection explicitly; existing assessments and approved records retain their recorded version.

## 9. Explicitly outside this policy version

This version does not define or assess:

- airfare price caps, market-price comparisons or price intelligence;
- permitted or preferred carriers;
- advance-booking windows;
- trip-duration thresholds for cabin entitlement;
- corporate discounts or negotiated fares;
- checked baggage, seat selection, upgrades, change fees or other ancillary charges;
- other Meal rules not expressly defined in section 4;
- Accommodation.

Unloop must not infer a rule for these topics from common practice or open-web content.

## 10. Decisions required for a later policy revision

Before introducing multiple policy versions, agree the historic-version selection rule. Accommodation and additional airfare restrictions require separately reviewed clauses before implementation. The current version retains the exact receipt-date FX rule, including weekends and holidays; an unavailable acceptable same-date rate keeps the expense Conversion pending.
