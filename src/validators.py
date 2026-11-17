"""Input loading, schema validation and money parsing.

All monetary values are converted to integer paise (1 INR = 100 paise) at the
boundary. Nothing downstream of this module ever touches a float amount.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

PLATFORM_REQUIRED_COLUMNS = [
    "transaction_id",
    "original_transaction_id",
    "reference_id",
    "transaction_date",
    "transaction_type",
    "amount",
    "currency",
    "status",
]

BANK_REQUIRED_COLUMNS = [
    "bank_record_id",
    "transaction_id",
    "original_transaction_id",
    "reference_id",
    "transaction_date",
    "settlement_date",
    "transaction_type",
    "amount",
    "currency",
    "status",
]

VALID_TRANSACTION_TYPES = {"PAYMENT", "REFUND"}
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_TWO_DP = Decimal("0.01")


class DatasetValidationError(Exception):
    """Raised when a file cannot be used at all (unreadable, missing columns)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class ValidationResult:
    """Outcome of validating one dataset.

    valid    -- rows that passed, with typed helper columns added
                (amount_paise, txn_date, settle_date, source_row)
    rejected -- rows that failed, original values + rejection_reason.
                Rejected rows are NEVER silently dropped: the engine reports
                them as INVALID_RECORD exceptions.
    warnings -- non-fatal, dataset-level messages (e.g. empty file)
    """

    kind: str
    valid: pd.DataFrame
    rejected: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Money helpers
# --------------------------------------------------------------------------- #
def parse_amount_to_paise(value: Any) -> int:
    """Parse a source amount string into integer paise using Decimal.

    Rejects blanks, non-numbers, NaN/Infinity and more than two decimal places
    (we never round source data silently).
    """
    if value is None:
        raise ValueError("amount is blank")
    text = str(value).strip().replace(",", "")
    if text == "" or text.lower() in {"nan", "none", "null"}:
        raise ValueError("amount is blank")
    try:
        dec = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"amount '{value}' is not a valid number") from None
    if not dec.is_finite():
        raise ValueError(f"amount '{value}' is not a finite number")
    if dec != dec.quantize(_TWO_DP):
        raise ValueError(f"amount '{value}' has more than 2 decimal places")
    return int(dec * 100)


def paise_to_decimal(paise: int | None) -> Decimal | None:
    if paise is None or (isinstance(paise, float) and pd.isna(paise)) or paise is pd.NA:
        return None
    return (Decimal(int(paise)) / 100).quantize(_TWO_DP)


def paise_to_str(paise: int | None) -> str:
    """Plain decimal string, e.g. -1234.50 -- used in CSV exports."""
    dec = paise_to_decimal(paise)
    return "" if dec is None else f"{dec:.2f}"


def format_inr(paise: int | None, symbol: bool = True) -> str:
    """Indian digit grouping: 1234567.8 -> ₹12,34,567.80."""
    dec = paise_to_decimal(paise)
    if dec is None:
        return "—"
    sign = "-" if dec < 0 else ""
    whole, frac = f"{abs(dec):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}{'₹' if symbol else ''}{whole}.{frac}"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def read_csv(source: Any) -> pd.DataFrame:
    """Read a CSV as all-string columns (no float coercion of amounts).

    `source` may be a path, a file-like object (Streamlit UploadedFile) or bytes.
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    if hasattr(source, "seek"):
        source.seek(0)
    try:
        df = pd.read_csv(source, dtype=str, keep_default_na=False, skipinitialspace=True)
    except pd.errors.EmptyDataError:
        raise DatasetValidationError(["The file is empty (no header row found)."]) from None
    except pd.errors.ParserError as exc:
        raise DatasetValidationError([f"The file is not a valid CSV: {exc}"]) from None
    except UnicodeDecodeError:
        raise DatasetValidationError(["The file is not UTF-8 text. Please upload a CSV file."]) from None
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _parse_date(value: Any) -> date:
    text = str(value).strip()
    if not text:
        raise ValueError("is blank")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{text}' is not a valid date (expected YYYY-MM-DD)")


def validate_dataframe(df: pd.DataFrame, kind: str) -> ValidationResult:
    """Validate a platform or bank dataframe.

    Fatal problems (missing columns, duplicate column names) raise
    DatasetValidationError. Row-level problems move the row to `rejected`.
    """
    if kind not in {"platform", "bank"}:
        raise ValueError("kind must be 'platform' or 'bank'")
    if df is None:
        raise DatasetValidationError([f"No {kind} dataset was provided."])

    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = PLATFORM_REQUIRED_COLUMNS if kind == "platform" else BANK_REQUIRED_COLUMNS

    errors: list[str] = []
    dupes = sorted({c for c in df.columns if list(df.columns).count(c) > 1})
    if dupes:
        errors.append(f"Duplicate column names in {kind} file: {', '.join(dupes)}")
    missing = [c for c in required if c not in df.columns]
    if missing:
        errors.append(f"{kind.capitalize()} file is missing required column(s): {', '.join(missing)}")
    if errors:
        raise DatasetValidationError(errors)

    df = df.fillna("").astype(str)
    warnings: list[str] = []
    if df.empty:
        warnings.append(f"The {kind} dataset has a valid header but contains no records.")

    valid_rows, rejected_rows = [], []
    for idx, rec in enumerate(df.to_dict("records")):
        rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in rec.items()}
        source_row = idx + 2  # +1 for header, +1 for 1-based line numbers
        reasons: list[str] = []

        if not rec["transaction_id"]:
            reasons.append("transaction_id is blank")
        if kind == "bank" and not rec["bank_record_id"]:
            reasons.append("bank_record_id is blank")

        ttype = rec["transaction_type"].upper()
        rec["transaction_type"] = ttype
        if ttype not in VALID_TRANSACTION_TYPES:
            reasons.append(f"transaction_type '{rec['transaction_type']}' must be PAYMENT or REFUND")
        if ttype == "REFUND" and not rec["original_transaction_id"]:
            reasons.append("REFUND must reference an original_transaction_id")

        currency = rec["currency"].upper()
        rec["currency"] = currency
        if not _CURRENCY_RE.match(currency):
            reasons.append(f"currency '{currency}' is not a 3-letter ISO code")

        amount_paise = None
        try:
            amount_paise = parse_amount_to_paise(rec["amount"])
            if amount_paise <= 0:
                reasons.append(
                    f"amount {rec['amount']} must be greater than zero "
                    "(direction is expressed by transaction_type, not by sign)"
                )
        except ValueError as exc:
            reasons.append(str(exc))

        txn_date = settle_date = None
        try:
            txn_date = _parse_date(rec["transaction_date"])
        except ValueError as exc:
            reasons.append(f"transaction_date {exc}")
        if kind == "bank":
            try:
                settle_date = _parse_date(rec["settlement_date"])
            except ValueError as exc:
                reasons.append(f"settlement_date {exc}")
            if txn_date and settle_date and settle_date < txn_date:
                reasons.append("settlement_date is before transaction_date")

        rec["source_row"] = source_row
        if reasons:
            rec["rejection_reason"] = "; ".join(reasons)
            rejected_rows.append(rec)
        else:
            rec["amount_paise"] = amount_paise
            rec["txn_date"] = txn_date
            rec["settle_date"] = settle_date
            valid_rows.append(rec)

    base_cols = list(df.columns) + ["source_row"]
    valid = pd.DataFrame(valid_rows, columns=base_cols + ["amount_paise", "txn_date", "settle_date"])
    rejected = pd.DataFrame(rejected_rows, columns=base_cols + ["rejection_reason"])
    if not rejected.empty:
        warnings.append(f"{len(rejected)} {kind} row(s) failed validation and are reported as INVALID_RECORD.")
    return ValidationResult(kind=kind, valid=valid, rejected=rejected, warnings=warnings)
