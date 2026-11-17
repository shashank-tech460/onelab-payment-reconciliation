"""Payment reconciliation engine.

Pipeline
--------
1. Validate both datasets (invalid rows -> INVALID_RECORD, never dropped).
2. Period filter: platform by transaction_date, bank by settlement_date.
   Bank rows settled after the cutoff become *subsequent evidence*.
3. Duplicate detection within each dataset (first occurrence is kept as the
   original; later ones become DUPLICATE_* and are excluded from totals).
4. One-to-one matching on transaction_id. Currency and transaction_type
   must agree before amounts are compared.
5. Amount comparison in integer paise against an individual tolerance.
6. Unmatched platform rows -> LATE_SETTLEMENT (found in subsequent evidence),
   PENDING_AT_CUTOFF (inside the settlement-lag window) or MISSING_SETTLEMENT.
7. Unmatched bank rows -> ORPHAN_REFUND (refund whose original payment is not
   in the platform dataset) or UNMATCHED_BANK.
8. Aggregate rounding test per currency on within-tolerance variances.
9. A bridge (platform net -> bank net) that must tie out exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from .validators import ValidationResult, format_inr, validate_dataframe

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReconciliationConfig:
    period_start: date = date(2026, 11, 1)
    cutoff_date: date = date(2026, 11, 30)
    #: |bank - platform| at or below this (per record) is a rounding difference.
    individual_tolerance_paise: int = 2  # Rs 0.02
    #: |sum of rounding differences| above this is an aggregate breach.
    aggregate_tolerance_paise: int = 5  # Rs 0.05
    #: Bank settles T+1..T+2; transactions newer than this at cutoff are pending.
    settlement_lag_days: int = 2
    reporting_currency: str = "INR"

    def __post_init__(self):
        if self.cutoff_date < self.period_start:
            raise ValueError("cutoff_date must be on or after period_start")
        if self.individual_tolerance_paise < 0 or self.aggregate_tolerance_paise < 0:
            raise ValueError("tolerances must be non-negative")
        if self.settlement_lag_days < 0:
            raise ValueError("settlement_lag_days must be non-negative")


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
MATCHED = "MATCHED"
MATCHED_ROUNDING = "MATCHED_ROUNDING"
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
PENDING_AT_CUTOFF = "PENDING_AT_CUTOFF"
LATE_SETTLEMENT = "LATE_SETTLEMENT"
MISSING_SETTLEMENT = "MISSING_SETTLEMENT"
UNMATCHED_BANK = "UNMATCHED_BANK"
ORPHAN_REFUND = "ORPHAN_REFUND"
DUPLICATE_PLATFORM = "DUPLICATE_PLATFORM"
DUPLICATE_BANK = "DUPLICATE_BANK"
CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
TYPE_MISMATCH = "TYPE_MISMATCH"
OUT_OF_PERIOD = "OUT_OF_PERIOD"
INVALID_RECORD = "INVALID_RECORD"
AGGREGATE_ROUNDING = "AGGREGATE_ROUNDING"

#: label, severity, is_exception, group
CATEGORY_META: dict[str, dict[str, Any]] = {
    MATCHED: {"label": "Matched", "severity": "None", "exception": False, "group": "Matched"},
    MATCHED_ROUNDING: {"label": "Matched (rounding)", "severity": "Low", "exception": False, "group": "Matched"},
    AMOUNT_MISMATCH: {"label": "Amount mismatch", "severity": "High", "exception": True, "group": "Unmatched"},
    PENDING_AT_CUTOFF: {"label": "Pending at cutoff", "severity": "Info", "exception": True, "group": "Timing"},
    LATE_SETTLEMENT: {"label": "Late settlement", "severity": "Low", "exception": True, "group": "Timing"},
    MISSING_SETTLEMENT: {"label": "Missing settlement", "severity": "High", "exception": True, "group": "Unmatched"},
    UNMATCHED_BANK: {"label": "Unmatched bank record", "severity": "High", "exception": True, "group": "Unmatched"},
    ORPHAN_REFUND: {"label": "Orphan refund", "severity": "High", "exception": True, "group": "Unmatched"},
    DUPLICATE_PLATFORM: {"label": "Duplicate (platform)", "severity": "High", "exception": True, "group": "Data quality"},
    DUPLICATE_BANK: {"label": "Duplicate (bank)", "severity": "High", "exception": True, "group": "Data quality"},
    CURRENCY_MISMATCH: {"label": "Currency mismatch", "severity": "High", "exception": True, "group": "Unmatched"},
    TYPE_MISMATCH: {"label": "Type mismatch", "severity": "High", "exception": True, "group": "Unmatched"},
    OUT_OF_PERIOD: {"label": "Out of period", "severity": "Info", "exception": True, "group": "Data quality"},
    INVALID_RECORD: {"label": "Invalid record", "severity": "High", "exception": True, "group": "Data quality"},
    AGGREGATE_ROUNDING: {"label": "Aggregate rounding breach", "severity": "Medium", "exception": True, "group": "Aggregate"},
}

#: Categories where the record has no in-period counterpart.
UNMATCHED_CATEGORIES = {
    AMOUNT_MISMATCH, PENDING_AT_CUTOFF, LATE_SETTLEMENT, MISSING_SETTLEMENT,
    UNMATCHED_BANK, ORPHAN_REFUND, CURRENCY_MISMATCH, TYPE_MISMATCH,
}
MATCHED_CATEGORIES = {MATCHED, MATCHED_ROUNDING}
TIMING_CATEGORIES = {PENDING_AT_CUTOFF, LATE_SETTLEMENT}

REPORT_COLUMNS = [
    "category", "category_label", "severity", "is_exception", "side",
    "transaction_id", "original_transaction_id", "reference_id", "transaction_type", "currency",
    "platform_amount_paise", "bank_amount_paise", "variance_paise", "bridge_effect_paise",
    "transaction_date", "settlement_date", "bank_record_id",
    "platform_status", "bank_status", "platform_source_row", "bank_source_row", "explanation",
]
_PAISE_COLS = ["platform_amount_paise", "bank_amount_paise", "variance_paise", "bridge_effect_paise",
               "platform_source_row", "bank_source_row"]


def _sign(ttype: str) -> int:
    """Payments increase net cash, refunds decrease it."""
    return -1 if ttype == "REFUND" else 1


# --------------------------------------------------------------------------- #
# Result object
# --------------------------------------------------------------------------- #
@dataclass
class ReconciliationResult:
    config: ReconciliationConfig
    report: pd.DataFrame
    summary: dict[str, Any]
    bridge: pd.DataFrame
    rounding: pd.DataFrame
    platform_validation: ValidationResult
    bank_validation: ValidationResult
    subsequent_validation: ValidationResult | None = None
    notes: list[str] = field(default_factory=list)

    def by_category(self, *categories: str) -> pd.DataFrame:
        return self.report[self.report["category"].isin(categories)].reset_index(drop=True)

    @property
    def matched(self) -> pd.DataFrame:
        return self.by_category(*MATCHED_CATEGORIES)

    @property
    def unmatched(self) -> pd.DataFrame:
        return self.by_category(*UNMATCHED_CATEGORIES)

    @property
    def exceptions(self) -> pd.DataFrame:
        return self.report[self.report["is_exception"]].reset_index(drop=True)

    def count(self, category: str) -> int:
        return int((self.report["category"] == category).sum())


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def _records(df: pd.DataFrame) -> list[dict]:
    return df.to_dict("records") if not df.empty else []


def _row(category: str, *, p: dict | None = None, b: dict | None = None, explanation: str,
         variance: int | None = None, p_counted: bool = False, b_counted: bool = False,
         side: str | None = None, currency: str | None = None) -> dict:
    """Build a report row. `*_counted` says whether that side's amount is part
    of the in-period net total; bridge_effect is the row's contribution to
    (bank_net - platform_net)."""
    src = p or b or {}
    effect = 0
    if p_counted and p is not None:
        effect -= _sign(p["transaction_type"]) * int(p["amount_paise"])
    if b_counted and b is not None:
        effect += _sign(b["transaction_type"]) * int(b["amount_paise"])
    meta = CATEGORY_META[category]
    return {
        "category": category,
        "category_label": meta["label"],
        "severity": meta["severity"],
        "is_exception": meta["exception"],
        "side": side or ("BOTH" if p is not None and b is not None else "PLATFORM" if p is not None else "BANK"),
        "transaction_id": src.get("transaction_id", ""),
        "original_transaction_id": (p or {}).get("original_transaction_id") or (b or {}).get("original_transaction_id", ""),
        "reference_id": (p or {}).get("reference_id") or (b or {}).get("reference_id", ""),
        "transaction_type": src.get("transaction_type", ""),
        "currency": currency or src.get("currency", ""),
        "platform_amount_paise": p.get("amount_paise") if p else None,
        "bank_amount_paise": b.get("amount_paise") if b else None,
        "variance_paise": variance,
        "bridge_effect_paise": effect,
        "transaction_date": (p or b or {}).get("transaction_date", ""),
        "settlement_date": (b or {}).get("settlement_date", ""),
        "bank_record_id": (b or {}).get("bank_record_id", ""),
        "platform_status": (p or {}).get("status", ""),
        "bank_status": (b or {}).get("status", ""),
        "platform_source_row": p.get("source_row") if p else None,
        "bank_source_row": b.get("source_row") if b else None,
        "explanation": explanation,
    }


def _dedupe(records: list[dict], label: str, dup_category: str, rows: list[dict],
            key=lambda r: r["transaction_id"]) -> list[dict]:
    """Keep the first occurrence per key; report later ones as duplicates.

    The duplicate is excluded from totals (bridge_effect 0) so nothing is
    double counted, but it stays visible in the exceptions report.
    """
    first: dict[Any, dict] = {}
    kept: list[dict] = []
    for rec in records:
        k = key(rec)
        if k not in first:
            first[k] = rec
            kept.append(rec)
            continue
        orig = first[k]
        exact = (orig["amount_paise"] == rec["amount_paise"] and orig["currency"] == rec["currency"]
                 and orig["transaction_type"] == rec["transaction_type"])
        kind = "exact duplicate" if exact else "conflicting duplicate (same ID, different amount/currency/type)"
        ref = f"bank record {orig['bank_record_id']}" if label == "bank" else f"source row {orig['source_row']}"
        expl = (f"{kind.capitalize()} of transaction {rec['transaction_id']} in the {label} file; original kept "
                f"at {ref} (row {orig['source_row']}). Excluded from totals to prevent double counting"
                f" ({format_inr(rec['amount_paise'])} not counted).")
        if label == "bank":
            rows.append(_row(dup_category, b=rec, explanation=expl))
        else:
            rows.append(_row(dup_category, p=rec, explanation=expl))
    return kept


def reconcile(platform_df: pd.DataFrame, bank_df: pd.DataFrame,
              config: ReconciliationConfig | None = None,
              subsequent_bank_df: pd.DataFrame | None = None) -> ReconciliationResult:
    """Reconcile platform transactions against bank settlements.

    platform_df / bank_df / subsequent_bank_df are raw (string) dataframes as
    read from CSV. Raises DatasetValidationError for unusable inputs.
    """
    cfg = config or ReconciliationConfig()
    pv = validate_dataframe(platform_df, "platform")
    bv = validate_dataframe(bank_df, "bank")
    sv = validate_dataframe(subsequent_bank_df, "bank") if subsequent_bank_df is not None else None
    notes: list[str] = list(pv.warnings) + list(bv.warnings) + (list(sv.warnings) if sv else [])

    rows: list[dict] = []

    # 1. Invalid rows -------------------------------------------------------
    for rec in _records(pv.rejected):
        rows.append(_row(INVALID_RECORD, side="PLATFORM", p={**rec, "amount_paise": None},
                         explanation=f"Platform row {rec['source_row']} rejected: {rec['rejection_reason']}"))
    for rec in _records(bv.rejected):
        rows.append(_row(INVALID_RECORD, side="BANK", b={**rec, "amount_paise": None},
                         explanation=f"Bank row {rec['source_row']} rejected: {rec['rejection_reason']}"))

    # 2. Period filter ------------------------------------------------------
    platform_in: list[dict] = []
    for rec in _records(pv.valid):
        if cfg.period_start <= rec["txn_date"] <= cfg.cutoff_date:
            platform_in.append(rec)
        else:
            rows.append(_row(OUT_OF_PERIOD, p=rec, explanation=(
                f"Transaction dated {rec['transaction_date']} is outside the reporting period "
                f"{cfg.period_start} to {cfg.cutoff_date}; excluded from this reconciliation.")))

    bank_in: list[dict] = []
    subsequent: list[dict] = []
    for rec in _records(bv.valid):
        if rec["settle_date"] > cfg.cutoff_date:
            subsequent.append(rec)  # evidence for after-cutoff settlement
        elif rec["settle_date"] < cfg.period_start:
            rows.append(_row(OUT_OF_PERIOD, b=rec, explanation=(
                f"Settled {rec['settlement_date']}, before the reporting period; excluded.")))
        else:
            bank_in.append(rec)
    if sv is not None:
        subsequent.extend(r for r in _records(sv.valid) if r["settle_date"] > cfg.cutoff_date)

    # 3. Duplicates -----------------------------------------------------------
    platform_kept = _dedupe(platform_in, "platform", DUPLICATE_PLATFORM, rows)
    bank_kept = _dedupe(bank_in, "bank", DUPLICATE_BANK, rows)
    subsequent_by_id: dict[str, dict] = {}
    for rec in subsequent:  # first evidence wins; Dec duplicates are Dec's problem
        subsequent_by_id.setdefault(rec["transaction_id"], rec)

    # 4/5. One-to-one matching ---------------------------------------------
    bank_by_id = {r["transaction_id"]: r for r in bank_kept}  # unique after dedupe
    used_bank: set[str] = set()
    unmatched_platform: list[dict] = []
    tol = cfg.individual_tolerance_paise

    for p in platform_kept:
        b = bank_by_id.get(p["transaction_id"])
        if b is None or b["transaction_id"] in used_bank:
            unmatched_platform.append(p)
            continue
        used_bank.add(b["transaction_id"])

        if b["currency"] != p["currency"]:
            msg = (f"Same transaction_id but platform currency {p['currency']} vs bank currency "
                   f"{b['currency']}. Records in different currencies are never matched.")
            rows.append(_row(CURRENCY_MISMATCH, p=p, explanation=msg, p_counted=True, side="PLATFORM"))
            rows.append(_row(CURRENCY_MISMATCH, b=b, explanation=msg, b_counted=True, side="BANK"))
            continue
        if b["transaction_type"] != p["transaction_type"]:
            rows.append(_row(TYPE_MISMATCH, p=p, b=b, p_counted=True, b_counted=True, explanation=(
                f"Platform records a {p['transaction_type']} but the bank records a {b['transaction_type']} "
                f"for {p['transaction_id']}. Refunds and payments are never matched to each other.")))
            continue

        diff = int(b["amount_paise"]) - int(p["amount_paise"])
        if diff == 0:
            cat, msg = MATCHED, "Matched on transaction_id; currency, type and amount agree exactly."
        elif abs(diff) <= tol:
            cat = MATCHED_ROUNDING
            msg = (f"Matched on transaction_id. Variance {format_inr(diff)} is within the individual "
                   f"tolerance of {format_inr(tol)}; included in the aggregate rounding test.")
        else:
            cat = AMOUNT_MISMATCH
            msg = (f"Matched on transaction_id but bank amount differs by {format_inr(diff)}, exceeding the "
                   f"individual tolerance of {format_inr(tol)}. Investigate fees, partial settlement or keying error.")
        rows.append(_row(cat, p=p, b=b, variance=diff, explanation=msg, p_counted=True, b_counted=True))

    # 6. Unmatched platform: late / pending / missing ----------------------
    for p in unmatched_platform:
        s = subsequent_by_id.get(p["transaction_id"])
        days_before_cutoff = (cfg.cutoff_date - p["txn_date"]).days
        if s is not None and s["currency"] == p["currency"] and s["transaction_type"] == p["transaction_type"]:
            diff = int(s["amount_paise"]) - int(p["amount_paise"])
            extra = "" if diff == 0 else f" Note: settled amount differs by {format_inr(diff)}."
            rows.append(_row(LATE_SETTLEMENT, p=p, b=s, p_counted=True, b_counted=False, explanation=(
                f"Recorded {p['transaction_date']} but settled {s['settlement_date']} (after the "
                f"{cfg.cutoff_date} cutoff) by bank record {s['bank_record_id']}. Timing difference only: "
                f"subsequently settled, not missing.{extra}")))
        elif days_before_cutoff < cfg.settlement_lag_days:
            rows.append(_row(PENDING_AT_CUTOFF, p=p, p_counted=True, explanation=(
                f"Recorded {p['transaction_date']}, {days_before_cutoff} day(s) before cutoff, inside the "
                f"T+{cfg.settlement_lag_days} settlement window. Expected to settle after cutoff; "
                f"load next-period bank evidence to confirm.")))
        else:
            rows.append(_row(MISSING_SETTLEMENT, p=p, p_counted=True, explanation=(
                f"Recorded {p['transaction_date']}, {days_before_cutoff} day(s) before cutoff, beyond the "
                f"T+{cfg.settlement_lag_days} settlement window, and no bank settlement was found"
                f"{' in current or subsequent evidence' if subsequent_by_id else ''}.")))

    # 7. Unmatched bank: orphan refund / unmatched --------------------------
    all_platform_ids = set(pv.valid["transaction_id"]) if not pv.valid.empty else set()
    for b in bank_kept:
        if b["transaction_id"] in used_bank:
            continue
        if b["transaction_type"] == "REFUND" and b["original_transaction_id"] not in all_platform_ids:
            rows.append(_row(ORPHAN_REFUND, b=b, b_counted=True, explanation=(
                f"Bank refund {b['transaction_id']} of {format_inr(b['amount_paise'])} references original "
                f"transaction {b['original_transaction_id']}, which does not exist in the platform dataset. "
                f"Money left the account with no corresponding sale.")))
        elif b["transaction_type"] == "REFUND":
            rows.append(_row(UNMATCHED_BANK, b=b, b_counted=True, explanation=(
                f"Bank refund {b['transaction_id']} for known payment {b['original_transaction_id']} has no "
                f"matching refund record on the platform.")))
        else:
            rows.append(_row(UNMATCHED_BANK, b=b, b_counted=True, explanation=(
                f"Bank settlement {b['bank_record_id']} for {b['transaction_id']} has no matching platform "
                f"transaction.")))

    # 8. Aggregate rounding per currency -----------------------------------
    rounding_rows = []
    currencies = sorted({r["currency"] for r in rows if r["currency"]} | {cfg.reporting_currency})
    for cur in currencies:
        sub = [r for r in rows if r["category"] == MATCHED_ROUNDING and r["currency"] == cur]
        total = sum(int(r["variance_paise"]) for r in sub)
        breach = abs(total) > cfg.aggregate_tolerance_paise
        rounding_rows.append({
            "currency": cur, "records": len(sub), "aggregate_variance_paise": total,
            "max_abs_individual_paise": max((abs(int(r["variance_paise"])) for r in sub), default=0),
            "individual_tolerance_paise": tol, "aggregate_tolerance_paise": cfg.aggregate_tolerance_paise,
            "breach": breach,
        })
        if breach:
            agg = _row(AGGREGATE_ROUNDING, side="AGGREGATE", currency=cur, variance=total, explanation=(
                f"{len(sub)} records each within the {format_inr(tol)} individual tolerance sum to "
                f"{format_inr(total)}, exceeding the {format_inr(cfg.aggregate_tolerance_paise)} aggregate "
                f"tolerance. Small per-record differences that all point the same way indicate a systematic "
                f"rounding/truncation rule mismatch; at production volume this becomes a material loss. "
                f"(Already included in the bridge via the individual rows; not counted twice.)"))
            agg["transaction_id"] = ", ".join(r["transaction_id"] for r in sub)
            rows.append(agg)
    rounding = pd.DataFrame(rounding_rows)
    report = pd.DataFrame(rows, columns=REPORT_COLUMNS)

    for col in _PAISE_COLS:
        report[col] = pd.array(report[col].tolist(), dtype="Int64")
    report["is_exception"] = report["is_exception"].astype(bool)

    # 9. Totals and bridge --------------------------------------------------
    bridge, totals = _build_bridge(report, platform_kept, bank_kept, bank_in, currencies)
    summary = _build_summary(cfg, report, totals, rounding, pv, bv, sv, platform_in, bank_in)
    return ReconciliationResult(cfg, report, summary, bridge, rounding, pv, bv, sv, notes)


def _net(records: list[dict], currency: str) -> int:
    return sum(_sign(r["transaction_type"]) * int(r["amount_paise"]) for r in records if r["currency"] == currency)


_BRIDGE_ORDER = [
    (MATCHED_ROUNDING, "Rounding differences (within tolerance)"),
    (AMOUNT_MISMATCH, "Amount mismatches"),
    (PENDING_AT_CUTOFF, "Pending at cutoff (timing)"),
    (LATE_SETTLEMENT, "Settled after cutoff (timing)"),
    (MISSING_SETTLEMENT, "Missing settlements"),
    (UNMATCHED_BANK, "Unmatched bank records"),
    (ORPHAN_REFUND, "Orphan refunds"),
    (CURRENCY_MISMATCH, "Currency mismatches"),
    (TYPE_MISMATCH, "Type mismatches"),
]


def _build_bridge(report, platform_kept, bank_kept, bank_in, currencies):
    lines, totals = [], {}
    for cur in currencies:
        p_net, b_net = _net(platform_kept, cur), _net(bank_kept, cur)
        b_raw = _net(bank_in, cur)
        sub = report[report["currency"] == cur]
        lines.append({"currency": cur, "step": "Platform net (deduplicated)", "category": "START", "amount_paise": p_net})
        explained = 0
        for cat, label in _BRIDGE_ORDER:
            amt = int(sub.loc[sub["category"] == cat, "bridge_effect_paise"].fillna(0).sum())
            if amt:
                lines.append({"currency": cur, "step": label, "category": cat, "amount_paise": amt})
                explained += amt
        lines.append({"currency": cur, "step": "Bank net (deduplicated)", "category": "END", "amount_paise": b_net})
        unexplained = b_net - p_net - explained
        if unexplained != 0:  # invariant: every rupee of difference must be explained
            raise AssertionError(f"Bridge does not tie out for {cur}: unexplained {unexplained} paise")
        totals[cur] = {"platform_net": p_net, "bank_net": b_net, "bank_net_incl_duplicates": b_raw,
                       "duplicates_excluded": b_raw - b_net, "difference": b_net - p_net}
    return pd.DataFrame(lines, columns=["currency", "step", "category", "amount_paise"]), totals


def _build_summary(cfg, report, totals, rounding, pv, bv, sv, platform_in, bank_in):
    cur = cfg.reporting_currency
    t = totals.get(cur, {"platform_net": 0, "bank_net": 0, "difference": 0,
                         "bank_net_incl_duplicates": 0, "duplicates_excluded": 0})
    cats = report["category"].value_counts().to_dict()
    n = lambda *c: int(sum(cats.get(x, 0) for x in c))  # noqa: E731
    high = report[(report["severity"] == "High")]
    rr = rounding[rounding["currency"] == cur]
    breach = bool(rr["breach"].any()) if not rr.empty else False

    if len(high) == 0 and not breach and n(*TIMING_CATEGORIES) == 0:
        status = "RECONCILED"
    elif len(high) == 0 and not breach:
        status = "RECONCILED WITH TIMING DIFFERENCES"
    else:
        status = "UNRECONCILED - EXCEPTIONS REQUIRE REVIEW"

    return {
        "period_start": cfg.period_start, "cutoff_date": cfg.cutoff_date, "currency": cur,
        "platform_records_raw": len(pv.valid) + len(pv.rejected),
        "platform_records_in_period": len(platform_in),
        "bank_records_raw": len(bv.valid) + len(bv.rejected),
        "bank_records_in_period": len(bank_in),
        "subsequent_evidence_records": len(sv.valid) if sv is not None else 0,
        "subsequent_evidence_loaded": sv is not None,
        "matched": n(*MATCHED_CATEGORIES), "matched_exact": n(MATCHED), "matched_rounding": n(MATCHED_ROUNDING),
        "unmatched": n(*UNMATCHED_CATEGORIES),
        "exceptions": int(report["is_exception"].sum()),
        "high_severity_exceptions": len(high),
        "category_counts": {k: int(v) for k, v in cats.items()},
        "platform_net_paise": t["platform_net"], "bank_net_paise": t["bank_net"],
        "bank_net_incl_duplicates_paise": t["bank_net_incl_duplicates"],
        "duplicates_excluded_paise": t["duplicates_excluded"],
        "total_variance_paise": t["difference"],
        "rounding_aggregate_paise": int(rr["aggregate_variance_paise"].sum()) if not rr.empty else 0,
        "rounding_breach": breach,
        "status": status,
    }
