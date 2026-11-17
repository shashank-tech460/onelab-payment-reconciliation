# 💳 Payment Reconciliation System

Month-end reconciliation of a payments platform's transaction ledger against bank settlement files. Built for the Onelab AI-Native Engineer Intern assessment (November 2026).

It finds every difference between the two datasets, sorts each one into a category, and produces a **bridge that explains every paisa** of the gap between the platform's books and the bank.

---

## Business problem
The platform records each payment as soon as the customer pays. The bank settles in batches 1–2 days later. At month-end the two should agree, but they don't, because of:

- **Timing:** a 30 Nov payment settles on 1 Dec.
- **Rounding:** tiny per-record differences that add up.
- **Duplicates:** the bank posted the same settlement twice.
- **Orphan refunds:** the bank refunded a transaction that doesn't exist on the platform.
- **Plain breaks:** missing settlements, unknown bank credits and short settlements.

## Solution overview
```
CSV upload / sample ─▶ validators.py ─▶ reconciliation.py ─▶ reporting.py ─▶ app.py (Streamlit)
                       schema, Decimal     dedupe → period → match         CSV exports    dashboard,
                       → integer paise     → classify → aggregate test                    charts, drill-down
                                           → bridge (must tie out)
```

## Features
- Detects all four mandatory anomalies (late settlement, cumulative rounding, duplicate, orphan refund), plus missing settlements, unmatched bank records, amount, currency and type mismatches, out-of-period rows and invalid rows.
- Reconciles **as of the cutoff** (late items are *pending*) or **with December evidence** (late items are *subsequently settled*), switched with a sidebar toggle.
- **Integer-paise money handling.** Decimal parsing, no floats in any calculation, source amounts preserved.
- **One-to-one matching.** Different currencies are never matched, and refunds never match payments.
- **Duplicates excluded from totals** but listed as exceptions. The dashboard shows "bank net incl. duplicates" next to the deduplicated figure.
- **Bridge invariant:** `platform net + Σ explained differences = bank net` per currency. The engine raises an error if it doesn't tie out.
- Dashboard with KPI cards, status badge, waterfall bridge, status and exception charts, a cumulative platform-vs-bank comparison, aggregate rounding analysis, search and filters, record drill-down, validation feedback and CSV downloads.
- 55 automated tests.

## Technology stack
Python 3.11+ (tested on 3.13.5) · pandas · Streamlit · Plotly · pytest · `decimal`

## Project structure
```
app.py                      Streamlit dashboard (entry point)
src/validators.py           CSV loading, schema/row validation, Decimal → paise, ₹ formatting
src/reconciliation.py       Engine: config, categories, matching, bridge, summary
src/reporting.py            Export/display frames and the full CSV report
src/data_generator.py       Deterministic synthetic data (seed 42)
data/                       platform_transactions.csv, bank_settlements.csv,
                            bank_settlements_december.csv, anomaly_manifest.csv
tests/test_reconciliation.py
docs/                       assumptions, data dictionary, test cases, production limitations
submission/                 assessment deliverables
.streamlit/config.toml      theme
```

## Installation
```bash
git clone https://github.com/shashank-tech460/onelab-payment-reconciliation.git
cd onelab-payment-reconciliation
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Run the application
```bash
streamlit run app.py
```
Open http://localhost:8501. The built-in sample loads automatically. To use your own data, choose **Upload CSV files** in the sidebar. Files must follow [`docs/data_dictionary.md`](docs/data_dictionary.md); the sample files can be downloaded from the sidebar as templates.

To regenerate the sample data (the output is identical every time):
```bash
python -m src.data_generator
```

## Dataset
35 platform records, 36 November bank records and 4 December evidence records, all INR. The planted anomalies are listed in [`data/anomaly_manifest.csv`](data/anomaly_manifest.csv) and [`docs/data_dictionary.md`](docs/data_dictionary.md):

| Scenario | Record(s) | Result |
|---|---|---|
| A. Late settlement | `TXN-0032` ₹12,750.00 (30-Nov → 01-Dec) | PENDING_AT_CUTOFF, then LATE_SETTLEMENT with Dec evidence |
| B. Cumulative rounding | `TXN-0021`…`TXN-0030` (−₹0.01 each) | 10 × MATCHED_ROUNDING + AGGREGATE_ROUNDING breach (−₹0.10 vs ±₹0.05) |
| C. Duplicate | `TXN-0031` posted twice by the bank (`BNK-0031-D`) | DUPLICATE_BANK, ₹4,321.50 excluded |
| D. Orphan refund | `RFD-0099` → `TXN-9999` ₹750.00 | ORPHAN_REFUND |
| Unmatched | `TXN-0033` (platform), `TXN-0099` (bank), `TXN-0034` (₹25 short) | MISSING_SETTLEMENT, UNMATCHED_BANK, AMOUNT_MISMATCH |

**Sample result:** platform net ₹3,71,260.37 · bank net ₹3,54,685.27 · variance −₹16,575.10, fully explained:

| Bridge line | ₹ |
|---|---|
| Platform net | 3,71,260.37 |
| Rounding differences | −0.10 |
| Amount mismatch | −25.00 |
| Pending / late settlement | −12,750.00 |
| Missing settlement | −6,200.00 |
| Unmatched bank credit | +3,150.00 |
| Orphan refund | −750.00 |
| **Bank net** | **3,54,685.27** |

## Reconciliation methodology
1. **Validate** each file. A missing column or unreadable CSV is a hard error with a clear message. Bad rows (blank ID, non-positive or over-precise amount, bad date, unknown type or currency, refund without an original) become `INVALID_RECORD` and are kept in the report.
2. **Period filter.** Platform rows by `transaction_date`, bank rows by `settlement_date`. Bank rows settled after the cutoff become *subsequent evidence*.
3. **De-duplicate** within each dataset by `transaction_id`. The first row is the original; later rows become `DUPLICATE_*` and are excluded from totals.
4. **Match one-to-one** on `transaction_id`. Currency and type must agree.
5. **Compare amounts in paise.** A variance of ±₹0.02 or less is `MATCHED_ROUNDING`; anything larger is `AMOUNT_MISMATCH`.
6. **Unmatched platform rows.** Found in subsequent evidence → `LATE_SETTLEMENT`. Otherwise, within T+2 of cutoff → `PENDING_AT_CUTOFF`. Otherwise → `MISSING_SETTLEMENT`.
7. **Unmatched bank rows.** A refund whose original payment is absent from the platform → `ORPHAN_REFUND`. Anything else → `UNMATCHED_BANK`.
8. **Aggregate rounding test.** If the signed sum of within-tolerance variances goes beyond ±₹0.05 per currency → `AGGREGATE_ROUNDING`.
9. **Bridge and summary**, with the tie-out invariant enforced.

Every row has a plain-English `explanation`. The full rules are in [`docs/assumptions.md`](docs/assumptions.md).

## Assumptions (key)
Reporting period 1–30 Nov 2026 · T+2 settlement lag · individual tolerance ₹0.02 · aggregate tolerance ₹0.05 · `transaction_id` is carried by the bank · amounts are positive, with direction given by `transaction_type`. All of these can be changed in the sidebar except the matching key. See [`docs/assumptions.md`](docs/assumptions.md).

## Testing
```bash
pytest -v
```
55 tests cover matching, late and pending settlements, individual and cumulative rounding, duplicates and double-count prevention, orphan refunds, missing settlements, invalid CSVs, missing columns, currency mismatch, empty datasets, zero and negative amounts, and the full sample. Expected vs actual results are in [`docs/test_cases.md`](docs/test_cases.md), and the raw run output is in [`submission/test_results.txt`](submission/test_results.txt).

## Deployment (Streamlit Community Cloud)
1. Push this folder to a **public GitHub repository**:
   ```bash
   git init && git add . && git commit -m "Payment reconciliation system"
   gh repo create onelab-payment-reconciliation --public --source . --push
   ```
2. Go to https://share.streamlit.io, sign in with GitHub, and click **Create app**, then **Deploy a public app from GitHub**.
3. Choose the repository and branch `main`, and set the main file path to `app.py`. Python 3.11+ works.
4. Click **Deploy**. `requirements.txt` is installed automatically, and the sample data ships in `data/`, so there are no secrets or environment variables to set.

## Production limitations
See [`docs/production_limitations.md`](docs/production_limitations.md). In short:
1. Matching depends on the bank echoing our `transaction_id`, with no fee, net or batch settlement handling.
2. The "first occurrence wins" duplicate rule can mislabel legitimate split settlements and partial refunds.
3. The fixed T+2 calendar-day window and timezone-naive dates misclassify settlements around holidays and the cutoff hour.
