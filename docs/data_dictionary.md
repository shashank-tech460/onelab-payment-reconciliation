# Data Dictionary

All files are UTF-8 CSV with a header row. Amounts are **positive decimal strings with at most two decimal places** (e.g. `1234.50`). Direction comes from `transaction_type`, never from the sign. Dates are ISO `YYYY-MM-DD` (`DD-MM-YYYY` and `DD/MM/YYYY` are also accepted on upload).

## `platform_transactions.csv`: the company's ledger (November 2026)

| Column | Required | Type | Description |
|---|---|---|---|
| `transaction_id` | ✔ | string | Stable, unique platform ID (`TXN-0001`, refunds `RFD-0001`). **Primary matching key.** |
| `original_transaction_id` | ✔ (may be blank) | string | For refunds: the payment being refunded. Blank for payments. Required for `REFUND`. |
| `reference_id` | ✔ | string | Payment-gateway reference (`PGW…`). Informational, used in search. |
| `transaction_date` | ✔ | date | Date the customer paid / the refund was issued. Determines the reporting period. |
| `transaction_type` | ✔ | enum | `PAYMENT` or `REFUND`. |
| `amount` | ✔ | decimal | Positive amount in major units (INR). Parsed to integer paise. |
| `currency` | ✔ | ISO-4217 | 3-letter code; `INR` in the sample. |
| `status` | ✔ | string | Platform status (`SUCCESS`). |
| `customer_id` | (optional) | string | Synthetic customer reference. |
| `payment_method` | (optional) | string | `UPI`, `CARD`, `NETBANKING` or `WALLET`. |

## `bank_settlements.csv`: bank settlement file (settled in November 2026)

| Column | Required | Type | Description |
|---|---|---|---|
| `bank_record_id` | ✔ | string | Bank's own line ID (`BNK-0001`). Unique per bank line, including duplicates (`BNK-0031-D`). |
| `transaction_id` | ✔ | string | Platform transaction ID carried in the settlement narrative. **Matching key.** |
| `original_transaction_id` | ✔ (may be blank) | string | For refunds: the original payment. Used for orphan-refund detection. |
| `reference_id` | ✔ | string | Gateway reference. |
| `transaction_date` | ✔ | date | Original transaction date as reported by the bank. |
| `settlement_date` | ✔ | date | Date funds settled. **Determines the bank's period.** Must be ≥ `transaction_date`. |
| `transaction_type` | ✔ | enum | `PAYMENT` or `REFUND`. |
| `amount` | ✔ | decimal | Positive settled amount (INR). |
| `currency` | ✔ | ISO-4217 | 3-letter code. |
| `status` | ✔ | string | `SETTLED`. |
| `batch_id` | (optional) | string | Settlement batch (`BATCH-YYYYMMDD`). |

## `bank_settlements_december.csv`: post-cutoff evidence

Same schema as `bank_settlements.csv`. Contains settlements dated **1–4 December 2026**. Only rows that match an unmatched November platform transaction are used. The rest is genuine December activity and is ignored.

## `anomaly_manifest.csv`

Lists exactly which records carry planted scenarios and the category the engine is expected to assign.

## Planted records (seed = 42)

| Scenario | Records | Dataset | Detail | Expected category |
|---|---|---|---|---|
| Normal matches | `TXN-0001` … `TXN-0020`, `RFD-0001` (refund of `TXN-0005`) | both | Identical | `MATCHED` (21) |
| **A. Late settlement** | `TXN-0032` / `BNK-D0032` | platform + December file | ₹12,750.00 recorded 30-Nov, settled 01-Dec | `PENDING_AT_CUTOFF`; `LATE_SETTLEMENT` once December evidence is loaded |
| **B. Cumulative rounding** | `TXN-0021` … `TXN-0030` | both | Bank is ₹0.01 lower on each of 10 records → −₹0.10 | `MATCHED_ROUNDING` ×10 + one `AGGREGATE_ROUNDING` breach |
| **C. Duplicate** | `TXN-0031` → `BNK-0031`, `BNK-0031-D` | bank only | ₹4,321.50 posted twice | `MATCHED` (`BNK-0031`) + `DUPLICATE_BANK` (`BNK-0031-D`) |
| **D. Orphan refund** | `RFD-0099` / `BNK-R099`, original `TXN-9999` | bank only | ₹750.00 refund of a non-existent payment | `ORPHAN_REFUND` |
| Ordinary unmatched (platform) | `TXN-0033` | platform only | ₹6,200.00 on 12-Nov, never settled | `MISSING_SETTLEMENT` |
| Ordinary unmatched (bank) | `TXN-0099` / `BNK-0099` | bank only | ₹3,150.00 credit, no platform record | `UNMATCHED_BANK` |
| Amount mismatch | `TXN-0034` / `BNK-0034` | both | Bank ₹25.00 short | `AMOUNT_MISMATCH` |

Record counts: platform 35, bank (November) 36, December evidence 4.

## Reconciliation report columns (exports)

| Column | Description |
|---|---|
| `category` / `category_label` | Classification code and readable label (see `assumptions.md`) |
| `severity` | `High`, `Medium`, `Low`, `Info` or `None` |
| `side` | `BOTH`, `PLATFORM`, `BANK` or `AGGREGATE` |
| `platform_amount`, `bank_amount` | Source amounts, preserved exactly |
| `variance` | `bank − platform` for paired records |
| `bridge_effect` | This row's contribution to `bank net − platform net` (0 for duplicates, invalid and out-of-period rows) |
| `platform_source_row`, `bank_source_row` | Line number in the source CSV, for traceability |
| `explanation` | Plain-English reason for the classification |
