# Distilled Engineering Specification (as built)

> Claude Code condensed this from the implementation prompt (`02b_exact_implementation_prompt.md`) and the decisions made during the build. If your brainstorming session produced its own distilled prompt, add it here as well. The **raw prompt** from the start of the brainstorming thread lives in that thread (`01_brainstorming_thread.md`).

## Goal
Reconcile a payments platform's November 2026 ledger with bank settlement files. Classify every difference, and explain the total gap with a bridge that ties out exactly.

## Inputs
- `platform_transactions.csv`: transaction_id, original_transaction_id, reference_id, transaction_date, transaction_type (PAYMENT/REFUND), amount, currency, status.
- `bank_settlements.csv`: the same fields plus bank_record_id and settlement_date.
- Optional post-cutoff evidence (December) in the bank schema.

## Non-negotiable financial rules
- Parse amounts with Decimal into **integer paise**. No float arithmetic. Preserve source amounts.
- Never drop a record silently. Invalid rows become exceptions.
- One-to-one matching. Never match across currencies, or a refund to a payment.
- Duplicates are detected, the original is kept, and the duplicate is excluded from totals but reported.
- Pending (within the T+2 window at cutoff) ≠ late (settled after cutoff, proven by evidence) ≠ missing.
- Individual tolerance ₹0.02 and aggregate tolerance ₹0.05 are both configurable and documented.
- `platform net + Σ category effects = bank net` per currency, or the engine fails loudly.

## Mandatory synthetic scenarios (seed 42, ≥ 30 rows per file)
A. Late settlement (30-Nov → 01-Dec) · B. 10 × ₹0.01 rounding (aggregate ₹0.10 > ₹0.05) · C. bank-side duplicate · D. bank refund of a non-existent transaction · plus normal matches, a missing settlement, an unknown bank credit and an amount mismatch.

## Deliverables
Streamlit dashboard (KPIs, upload and validation, results by category, analytics, investigation, CSV reports) · pytest suite (executed) · README and docs (assumptions, data dictionary, test cases, three production limitations) · Streamlit Cloud-ready repo · submission folder.

## Stack
Python, pandas, Streamlit, Plotly, pytest.
