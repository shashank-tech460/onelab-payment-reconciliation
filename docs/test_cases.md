# Test Cases: Expected vs Actual

**Execution:** `pytest -v` on 17 Nov 2026, Python 3.13.5, pytest 9.1.1.
**Result: 55 passed, 0 failed.** The raw output is in [`submission/test_results.txt`](../submission/test_results.txt).

"Actual" is what the assertion verified in that run. Every row below corresponds to a test that executed and passed. Rerun with `pytest -v` to reproduce.

## Mandatory anomalies (sample dataset)

| ID | Test | Input | Expected | Actual | Status |
|---|---|---|---|---|---|
| A1 | `TestSampleData::test_all_anomalies_as_of_cutoff` | Sample, no Dec evidence | `TXN-0032` → PENDING_AT_CUTOFF | PENDING_AT_CUTOFF | ✅ PASS |
| A2 | `TestSampleData::test_late_settlement_with_december` | Sample + Dec evidence | `TXN-0032` → LATE_SETTLEMENT; 0 pending; still 1 missing (`TXN-0033`) | As expected | ✅ PASS |
| B1 | `TestSampleData::test_all_anomalies_as_of_cutoff` | Sample | 10 × MATCHED_ROUNDING, aggregate −₹0.10, breach = True | As expected | ✅ PASS |
| C1 | `TestSampleData::test_all_anomalies_as_of_cutoff` | Sample | `TXN-0031` → MATCHED + DUPLICATE_BANK | As expected | ✅ PASS |
| D1 | `TestSampleData::test_all_anomalies_as_of_cutoff` | Sample | `RFD-0099` → ORPHAN_REFUND | ORPHAN_REFUND | ✅ PASS |
| S1 | `TestSampleData::test_financial_totals_exact` | Sample | Platform net equals Decimal sum of CSV; variance = −₹16,575.10 | As expected | ✅ PASS |
| S2 | `TestSampleData::test_deterministic` / `test_minimum_sizes` | seed 42 | Identical output on every run; ≥ 30 rows per file | As expected | ✅ PASS |
| S3 | `TestSampleData::test_full_report_csv` | Sample | CSV has summary, bridge and records sections | As expected | ✅ PASS |

## Engine behaviour (focused fixtures)

| ID | Test | Input | Expected | Status |
|---|---|---|---|---|
| M1 | `test_exact_match` | 2 identical pairs | 2 MATCHED, 0 exceptions, status RECONCILED | ✅ PASS |
| M2 | `test_refund_matched_and_netted` | ₹500 payment, ₹200 refund on both sides | Refund MATCHED; platform net ₹300.00 | ✅ PASS |
| M3 | `test_refund_never_matches_payment` | Platform PAYMENT vs bank REFUND, same ID | TYPE_MISMATCH, 0 matched | ✅ PASS |
| M4 | `test_amount_mismatch_beyond_tolerance` | ₹100.00 vs ₹99.90 | AMOUNT_MISMATCH, variance −10 paise | ✅ PASS |
| M5 | `test_one_bank_record_cannot_match_two_platform_records` | 2 platform rows with the same ID, 1 bank row | 1 MATCHED + 1 DUPLICATE_PLATFORM; net counted once | ✅ PASS |
| M6 | `test_source_amounts_preserved` | 1234.56 vs 1234.55 | Export shows `1234.56`, `1234.55`, `-0.01` exactly | ✅ PASS |
| T1 | `test_late_settlement_is_pending_at_cutoff` | 30-Nov txn, no evidence | PENDING_AT_CUTOFF; status "WITH TIMING DIFFERENCES" | ✅ PASS |
| T2 | `test_late_settlement_with_december_evidence` | + Dec settlement 01-Dec | LATE_SETTLEMENT with settlement date and bank record | ✅ PASS |
| T3 | `test_post_cutoff_row_in_main_bank_file_is_treated_as_evidence` | 01-Dec row inside the Nov bank file | LATE_SETTLEMENT; not counted in Nov bank net | ✅ PASS |
| T4 | `test_missing_settlement_outside_lag_window` | 12-Nov txn, no bank | MISSING_SETTLEMENT | ✅ PASS |
| T5 | `test_missing_even_with_evidence_when_not_found` | 12-Nov txn, unrelated Dec evidence | MISSING_SETTLEMENT | ✅ PASS |
| T6 | `test_lag_boundary` | 29-Nov and 28-Nov txns | 29-Nov PENDING, 28-Nov MISSING | ✅ PASS |
| T7 | `test_unrelated_december_records_ignored` | Dec-only record | Not in the report | ✅ PASS |
| R1 | `test_individual_rounding_within_tolerance` | ₹100.00 vs ₹99.99 | MATCHED_ROUNDING, no aggregate breach | ✅ PASS |
| R2 | `test_cumulative_rounding_breaches_aggregate_tolerance` | 8 × (−₹0.01) | 8 MATCHED_ROUNDING; aggregate −₹0.08 breach; aggregate row bridge effect 0 | ✅ PASS |
| R3 | `test_offsetting_rounding_does_not_breach` | +₹0.01 / −₹0.01 alternating | Aggregate ₹0.00, no breach | ✅ PASS |
| R4 | `test_tolerance_is_configurable` | Tolerance 0, −₹0.01 | AMOUNT_MISMATCH | ✅ PASS |
| D1 | `test_duplicate_bank_entry_detected_original_preserved` | Bank B1 + B1-DUP | B1 matched, B1-DUP is DUPLICATE_BANK | ✅ PASS |
| D2 | `test_duplicate_not_double_counted` | Same | Bank net ₹100 (raw ₹200); variance 0 | ✅ PASS |
| D3 | `test_conflicting_duplicate_flagged` | Same ID, ₹100 vs ₹150 | Explanation says "conflicting" | ✅ PASS |
| O1 | `test_orphan_refund` | Bank refund of TXN-9999 | ORPHAN_REFUND with reference, amount, reason | ✅ PASS |
| O2 | `test_bank_refund_for_known_payment_is_unmatched_not_orphan` | Bank refund of an existing payment | UNMATCHED_BANK | ✅ PASS |
| O3 | `test_unmatched_bank_payment` | Bank-only payment | UNMATCHED_BANK | ✅ PASS |
| C1 | `test_currency_mismatch_never_matched` | INR vs USD, same ID | 0 matched; 2 CURRENCY_MISMATCH rows; INR and USD bridges both tie | ✅ PASS |

## Validation and edge cases

| ID | Test | Input | Expected | Status |
|---|---|---|---|---|
| V1 | `test_invalid_csv_bytes` | Empty bytes; malformed quoting | DatasetValidationError | ✅ PASS |
| V2 | `test_non_utf8_file` | Binary bytes | DatasetValidationError | ✅ PASS |
| V3 | `test_missing_required_columns` | Only 2 columns | Error lists the missing columns; reconcile refuses | ✅ PASS |
| V4 | `test_empty_datasets` | Header-only files | No crash, variance 0, "no records" warning | ✅ PASS |
| V5 | `test_empty_platform_all_bank_unmatched` | Empty platform | Bank row UNMATCHED_BANK | ✅ PASS |
| V6 | `test_zero_and_negative_amounts_rejected_not_dropped` ×3 | `0`, `0.00`, `-100.00` | INVALID_RECORD (reported, not dropped) | ✅ PASS |
| V7 | `test_row_level_errors` | Blank ID, `abc`, `1.005`, bad date, bad type, bad currency, refund without original | All 7 rejected | ✅ PASS |
| V8 | `test_out_of_period_record` | 31-Oct txn | OUT_OF_PERIOD | ✅ PASS |
| V9 | `test_uploaded_csv_roundtrip` | CSV bytes | Parsed to 1000 paise | ✅ PASS |
| $1 | `TestMoney::test_parse_amount_to_paise` ×6 | `100`, `100.5`, `0.01`, `1,234.56`, padded, `-5.00` | Exact paise | ✅ PASS |
| $2 | `TestMoney::test_parse_amount_rejects_bad_values` ×6 | blank, `abc`, `1.234`, NaN, inf, None | ValueError | ✅ PASS |
| $3 | `TestMoney::test_no_float_drift` | 0.10 + 0.20; 10,000 × 0.01 | Exactly 0.30; exactly ₹100.00 | ✅ PASS |
| $4 | `TestMoney::test_format_inr_indian_grouping` | 123456789 paise | `₹12,34,567.89` | ✅ PASS |

## Manual UI checks (Streamlit `AppTest`, headless)
The app was executed headlessly with `streamlit.testing.v1.AppTest`: default sample load, then toggling post-cutoff evidence on. Both runs completed with **0 exceptions and 0 error elements**. Browser-level visual checks are part of the demo checklist (`submission/demo_video_checklist.md`).
