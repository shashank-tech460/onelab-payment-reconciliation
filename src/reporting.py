"""Export helpers: turn engine output (integer paise) into human/CSV tables.

Exports carry amounts as exact two-decimal strings derived from paise via
Decimal, so a CSV round-trip never introduces float error.
"""
from __future__ import annotations

import io

import pandas as pd

from .reconciliation import ReconciliationResult
from .validators import format_inr, paise_to_str

_AMOUNT_COLS = {
    "platform_amount_paise": "platform_amount",
    "bank_amount_paise": "bank_amount",
    "variance_paise": "variance",
    "bridge_effect_paise": "bridge_effect",
}

EXPORT_COLUMNS = [
    "category", "category_label", "severity", "side", "transaction_id", "original_transaction_id",
    "reference_id", "bank_record_id", "transaction_type", "currency", "platform_amount", "bank_amount",
    "variance", "bridge_effect", "transaction_date", "settlement_date", "platform_status", "bank_status",
    "platform_source_row", "bank_source_row", "explanation",
]


def to_export_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Report rows -> CSV-ready frame with decimal-string amounts."""
    out = df.copy()
    for src, dst in _AMOUNT_COLS.items():
        out[dst] = [paise_to_str(None if pd.isna(v) else int(v)) for v in out[src]]
    for col in ("platform_source_row", "bank_source_row"):
        out[col] = [("" if pd.isna(v) else str(int(v))) for v in out[col]]
    return out[EXPORT_COLUMNS]


def to_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Report rows -> on-screen frame with ₹-formatted amounts."""
    out = df.copy()
    labels = {"platform_amount_paise": "Platform ₹", "bank_amount_paise": "Bank ₹", "variance_paise": "Variance ₹"}
    for src, dst in labels.items():
        out[dst] = [format_inr(None if pd.isna(v) else int(v), symbol=False) if not pd.isna(v) else "" for v in out[src]]
    cols = ["category_label", "severity", "transaction_id", "original_transaction_id", "bank_record_id",
            "transaction_type", "currency", "Platform ₹", "Bank ₹", "Variance ₹", "transaction_date",
            "settlement_date", "explanation"]
    return out[cols].rename(columns={
        "category_label": "Category", "severity": "Severity", "transaction_id": "Transaction ID",
        "original_transaction_id": "Original Txn", "bank_record_id": "Bank Record", "transaction_type": "Type",
        "currency": "Ccy", "transaction_date": "Txn Date", "settlement_date": "Settled", "explanation": "Explanation",
    })


def summary_frame(result: ReconciliationResult) -> pd.DataFrame:
    s = result.summary
    rows = [
        ("Reporting period", f"{s['period_start']} to {s['cutoff_date']}"),
        ("Reporting currency", s["currency"]),
        ("Overall status", s["status"]),
        ("Subsequent (post-cutoff) evidence loaded", "Yes" if s["subsequent_evidence_loaded"] else "No"),
        ("Platform records (raw)", s["platform_records_raw"]),
        ("Platform records in period", s["platform_records_in_period"]),
        ("Bank records (raw)", s["bank_records_raw"]),
        ("Bank records settled in period", s["bank_records_in_period"]),
        ("Matched", s["matched"]),
        ("  of which exact", s["matched_exact"]),
        ("  of which within rounding tolerance", s["matched_rounding"]),
        ("Unmatched / breaks", s["unmatched"]),
        ("Exceptions (all)", s["exceptions"]),
        ("High-severity exceptions", s["high_severity_exceptions"]),
        ("Platform net", paise_to_str(s["platform_net_paise"])),
        ("Bank net (deduplicated)", paise_to_str(s["bank_net_paise"])),
        ("Bank net incl. duplicates (NOT used)", paise_to_str(s["bank_net_incl_duplicates_paise"])),
        ("Duplicate amount excluded", paise_to_str(s["duplicates_excluded_paise"])),
        ("Total variance (bank - platform)", paise_to_str(s["total_variance_paise"])),
        ("Aggregate rounding variance", paise_to_str(s["rounding_aggregate_paise"])),
        ("Aggregate rounding breach", "Yes" if s["rounding_breach"] else "No"),
        ("Individual tolerance", paise_to_str(result.config.individual_tolerance_paise)),
        ("Aggregate tolerance", paise_to_str(result.config.aggregate_tolerance_paise)),
        ("Settlement lag (days)", result.config.settlement_lag_days),
    ]
    for cat, cnt in sorted(s["category_counts"].items()):
        rows.append((f"Count: {cat}", cnt))
    return pd.DataFrame(rows, columns=["metric", "value"]).astype(str)


def bridge_export(result: ReconciliationResult) -> pd.DataFrame:
    out = result.bridge.copy()
    out["amount"] = [paise_to_str(int(v)) for v in out["amount_paise"]]
    return out[["currency", "step", "category", "amount"]]


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


def full_report_csv(result: ReconciliationResult) -> bytes:
    """Single CSV: summary block, bridge block, then every report row."""
    buf = io.StringIO()
    buf.write("# SECTION: SUMMARY\n")
    summary_frame(result).to_csv(buf, index=False, lineterminator="\n")
    buf.write("\n# SECTION: BRIDGE (platform net -> bank net)\n")
    bridge_export(result).to_csv(buf, index=False, lineterminator="\n")
    buf.write("\n# SECTION: RECORDS\n")
    to_export_frame(result.report).to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue().encode("utf-8")
