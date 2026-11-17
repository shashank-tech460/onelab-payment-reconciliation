# Business Assumptions and Classification Rules

## Period and timing
1. **Reporting period:** 1–30 November 2026. **Cutoff:** 30 November 2026, end of day. Both can be changed in the sidebar.
2. A platform record belongs to the period if its `transaction_date` falls inside it. A bank record belongs to the period if its `settlement_date` does.
3. The bank settles **T+1 to T+2** (`settlement_lag_days = 2`). If an unmatched platform transaction is dated fewer than 2 days before the cutoff (29 or 30 Nov), it is **PENDING_AT_CUTOFF**. That is a timing difference, not an error.
4. If it is older than that and no settlement exists, it is **MISSING_SETTLEMENT**.
5. Any bank row settled after the cutoff is **subsequent evidence**, whether it comes from the main bank file or the optional December file. If it matches an unmatched November transaction, that transaction becomes **LATE_SETTLEMENT** ("subsequently settled"). It is never counted in November's bank total.
6. If December evidence is loaded and a 29/30-Nov transaction is still not found, it stays **PENDING**, because the evidence may be partial.

## Money
7. All amounts are parsed with `Decimal` and stored as **integer paise**. Floats appear only when plotting chart coordinates, never in any calculation, comparison, total or export.
8. Amounts must be > 0 and have at most 2 decimal places. Direction comes from `transaction_type`: refunds reduce net, payments increase it. Zero, negative, malformed or over-precise amounts are rejected as **INVALID_RECORD**. They are never rounded or dropped silently.
9. **Individual tolerance:** ₹0.02. A paired variance with |variance| ≤ ₹0.02 is **MATCHED_ROUNDING**, and anything larger is **AMOUNT_MISMATCH**.
10. **Aggregate tolerance:** ₹0.05 per currency. If the **signed** sum of all within-tolerance variances goes beyond ±₹0.05, the engine raises one **AGGREGATE_ROUNDING** exception. Signed means offsetting +/− differences cancel. Many small differences all in the same direction point to a systematic rule mismatch, such as bank truncation vs platform half-up rounding. At 1 million transactions a month, ₹0.01 each is ₹10,000.

## Matching
11. The matching key is `transaction_id`, which the bank carries in the settlement narrative. `reference_id` is informational.
12. Matching is **one-to-one**. After de-duplication each ID appears once per side, and a bank record is marked used after its first match.
13. **Currency must agree.** Same ID with a different currency gives **CURRENCY_MISMATCH**, reported as one row per side so each currency's totals stay correct. Records in different currencies are never matched.
14. **Type must agree.** A PAYMENT never matches a REFUND, which gives **TYPE_MISMATCH**.

## Duplicates
15. A duplicate is a second row with the same `transaction_id` in the **same** dataset and period. The first occurrence in file order is the original and stays in matching. Later rows become **DUPLICATE_BANK** or **DUPLICATE_PLATFORM**, are excluded from totals (bridge effect 0) and are listed as exceptions.
16. If the duplicate's amount, currency or type differs from the original, it is labelled a "conflicting duplicate" for manual review.
17. Duplicates inside the December evidence file are not November exceptions. The first row is used as evidence.

## Refunds
18. Refunds are matched like payments on their own `transaction_id` (e.g. `RFD-0001`).
19. An unmatched bank refund whose `original_transaction_id` is **not present anywhere in the platform dataset** is an **ORPHAN_REFUND**. An unmatched bank refund whose original payment *does* exist is **UNMATCHED_BANK** (the platform missed recording the refund).

## Categories

| Category | Severity | Counts as | Exception? |
|---|---|---|---|
| MATCHED | None | matched | no |
| MATCHED_ROUNDING | Low | matched | no, but feeds the aggregate test |
| AMOUNT_MISMATCH | High | unmatched | yes |
| PENDING_AT_CUTOFF | Info | unmatched (timing) | yes |
| LATE_SETTLEMENT | Low | unmatched (timing) | yes |
| MISSING_SETTLEMENT | High | unmatched | yes |
| UNMATCHED_BANK | High | unmatched | yes |
| ORPHAN_REFUND | High | unmatched | yes |
| CURRENCY_MISMATCH / TYPE_MISMATCH | High | unmatched | yes |
| DUPLICATE_BANK / DUPLICATE_PLATFORM | High | excluded from totals | yes |
| OUT_OF_PERIOD | Info | excluded | yes |
| INVALID_RECORD | High | excluded | yes |
| AGGREGATE_ROUNDING | Medium | summary row | yes |

## Overall status
- **RECONCILED:** no exceptions apart from out-of-period rows, and no aggregate breach.
- **RECONCILED WITH TIMING DIFFERENCES:** only pending or late items.
- **UNRECONCILED - EXCEPTIONS REQUIRE REVIEW:** any high-severity exception or an aggregate rounding breach.

## Bridge invariant
`platform net + Σ(bridge effects) = bank net`, per currency, exactly in paise. If it does not hold, the engine raises an error instead of producing a report.
