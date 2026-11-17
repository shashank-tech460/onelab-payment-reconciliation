"""Tests for the reconciliation engine, validators and sample data."""
from __future__ import annotations

import io
from decimal import Decimal

import pandas as pd
import pytest

from src.data_generator import generate
from src.reconciliation import (
    AGGREGATE_ROUNDING, AMOUNT_MISMATCH, CURRENCY_MISMATCH, DUPLICATE_BANK, DUPLICATE_PLATFORM,
    INVALID_RECORD, LATE_SETTLEMENT, MATCHED, MATCHED_ROUNDING, MISSING_SETTLEMENT, ORPHAN_REFUND,
    OUT_OF_PERIOD, PENDING_AT_CUTOFF, TYPE_MISMATCH, UNMATCHED_BANK, ReconciliationConfig, reconcile,
)
from src.reporting import full_report_csv, to_export_frame
from src.validators import (
    DatasetValidationError, format_inr, parse_amount_to_paise, read_csv, validate_dataframe,
)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def P(tid, amount, date="2026-11-10", ttype="PAYMENT", original="", currency="INR"):
    return {"transaction_id": tid, "original_transaction_id": original, "reference_id": f"REF-{tid}",
            "transaction_date": date, "transaction_type": ttype, "amount": amount, "currency": currency,
            "status": "SUCCESS"}


def B(tid, amount, settle="2026-11-11", date="2026-11-10", ttype="PAYMENT", original="", currency="INR", bid=None):
    return {"bank_record_id": bid or f"BNK-{tid}", "transaction_id": tid, "original_transaction_id": original,
            "reference_id": f"REF-{tid}", "transaction_date": date, "settlement_date": settle,
            "transaction_type": ttype, "amount": amount, "currency": currency, "status": "SETTLED"}


PCOLS = list(P("x", "1").keys())
BCOLS = list(B("x", "1").keys())


def pdf(*rows):
    return pd.DataFrame(list(rows), columns=PCOLS)


def bdf(*rows):
    return pd.DataFrame(list(rows), columns=BCOLS)


def cats(result, tid):
    return sorted(result.report.loc[result.report["transaction_id"] == tid, "category"])


def assert_bridge_ties(result, currency="INR"):
    b = result.bridge[result.bridge["currency"] == currency]
    start = int(b.loc[b["category"] == "START", "amount_paise"].iloc[0])
    end = int(b.loc[b["category"] == "END", "amount_paise"].iloc[0])
    middle = int(b.loc[~b["category"].isin(["START", "END"]), "amount_paise"].sum())
    assert start + middle == end


# --------------------------------------------------------------------------- #
# Money handling
# --------------------------------------------------------------------------- #
class TestMoney:
    @pytest.mark.parametrize("text,paise", [("100", 10000), ("100.5", 10050), ("0.01", 1), ("1,234.56", 123456),
                                            ("  42.10 ", 4210), ("-5.00", -500)])
    def test_parse_amount_to_paise(self, text, paise):
        assert parse_amount_to_paise(text) == paise

    @pytest.mark.parametrize("bad", ["", "abc", "1.234", "NaN", "inf", None])
    def test_parse_amount_rejects_bad_values(self, bad):
        with pytest.raises(ValueError):
            parse_amount_to_paise(bad)

    def test_no_float_drift(self):
        # 0.1 + 0.2 != 0.3 in float; in paise it is exact
        total = sum(parse_amount_to_paise(x) for x in ["0.10", "0.20"])
        assert total == parse_amount_to_paise("0.30")
        assert sum(parse_amount_to_paise("0.01") for _ in range(10_000)) == 10_000

    def test_format_inr_indian_grouping(self):
        assert format_inr(123456789) == "₹12,34,567.89"
        assert format_inr(-150) == "-₹1.50"
        assert format_inr(None) == "—"


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
class TestMatching:
    def test_exact_match(self):
        r = reconcile(pdf(P("T1", "100.00"), P("T2", "250.50")), bdf(B("T1", "100.00"), B("T2", "250.50")))
        assert cats(r, "T1") == [MATCHED] and cats(r, "T2") == [MATCHED]
        assert r.summary["matched"] == 2 and r.summary["exceptions"] == 0
        assert r.summary["total_variance_paise"] == 0
        assert r.summary["status"] == "RECONCILED"

    def test_refund_matched_and_netted(self):
        r = reconcile(pdf(P("T1", "500.00"), P("R1", "200.00", ttype="REFUND", original="T1")),
                      bdf(B("T1", "500.00"), B("R1", "200.00", ttype="REFUND", original="T1")))
        assert cats(r, "R1") == [MATCHED]
        assert r.summary["platform_net_paise"] == 30000  # refunds reduce net

    def test_refund_never_matches_payment(self):
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "100.00", ttype="REFUND", original="T0")))
        assert cats(r, "T1") == [TYPE_MISMATCH]
        assert r.summary["matched"] == 0

    def test_amount_mismatch_beyond_tolerance(self):
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "99.90")))
        row = r.by_category(AMOUNT_MISMATCH).iloc[0]
        assert row["variance_paise"] == -10
        assert r.summary["total_variance_paise"] == -10

    def test_one_bank_record_cannot_match_two_platform_records(self):
        # Two platform rows share an ID -> second is a duplicate, bank row used once only
        r = reconcile(pdf(P("T1", "100.00"), P("T1", "100.00")), bdf(B("T1", "100.00")))
        assert sorted(r.report["category"]) == [DUPLICATE_PLATFORM, MATCHED]
        assert r.summary["matched"] == 1
        assert r.summary["platform_net_paise"] == 10000

    def test_source_amounts_preserved(self):
        r = reconcile(pdf(P("T1", "1234.56")), bdf(B("T1", "1234.55")))
        exp = to_export_frame(r.report)
        assert exp.loc[0, "platform_amount"] == "1234.56"
        assert exp.loc[0, "bank_amount"] == "1234.55"
        assert exp.loc[0, "variance"] == "-0.01"


# --------------------------------------------------------------------------- #
# Late settlement / pending / missing
# --------------------------------------------------------------------------- #
class TestTiming:
    platform = pdf(P("T1", "100.00"), P("LATE", "500.00", date="2026-11-30"))
    bank = bdf(B("T1", "100.00"))
    december = bdf(B("LATE", "500.00", date="2026-11-30", settle="2026-12-01"))

    def test_late_settlement_is_pending_at_cutoff(self):
        r = reconcile(self.platform, self.bank)
        assert cats(r, "LATE") == [PENDING_AT_CUTOFF]
        assert r.count(MISSING_SETTLEMENT) == 0
        assert r.summary["status"] == "RECONCILED WITH TIMING DIFFERENCES"

    def test_late_settlement_with_december_evidence(self):
        r = reconcile(self.platform, self.bank, subsequent_bank_df=self.december)
        assert cats(r, "LATE") == [LATE_SETTLEMENT]
        row = r.by_category(LATE_SETTLEMENT).iloc[0]
        assert row["settlement_date"] == "2026-12-01" and row["bank_record_id"] == "BNK-LATE"
        assert r.count(MISSING_SETTLEMENT) == 0

    def test_post_cutoff_row_in_main_bank_file_is_treated_as_evidence(self):
        bank = pd.concat([self.bank, self.december], ignore_index=True)
        r = reconcile(self.platform, bank)
        assert cats(r, "LATE") == [LATE_SETTLEMENT]
        assert r.summary["bank_net_paise"] == 10000  # December money not in November bank total

    def test_missing_settlement_outside_lag_window(self):
        r = reconcile(pdf(P("OLD", "300.00", date="2026-11-12")), bdf())
        assert cats(r, "OLD") == [MISSING_SETTLEMENT]

    def test_missing_even_with_evidence_when_not_found(self):
        r = reconcile(pdf(P("OLD", "300.00", date="2026-11-12")), bdf(), subsequent_bank_df=self.december)
        assert cats(r, "OLD") == [MISSING_SETTLEMENT]

    def test_lag_boundary(self):
        # T+2 lag: 29-Nov pending, 28-Nov should have settled -> missing
        r = reconcile(pdf(P("D29", "1.00", date="2026-11-29"), P("D28", "1.00", date="2026-11-28")), bdf())
        assert cats(r, "D29") == [PENDING_AT_CUTOFF]
        assert cats(r, "D28") == [MISSING_SETTLEMENT]

    def test_unrelated_december_records_ignored(self):
        dec = bdf(B("DEC1", "999.00", date="2026-12-01", settle="2026-12-02"))
        r = reconcile(self.platform, self.bank, subsequent_bank_df=dec)
        assert "DEC1" not in set(r.report["transaction_id"])


# --------------------------------------------------------------------------- #
# Rounding
# --------------------------------------------------------------------------- #
class TestRounding:
    def test_individual_rounding_within_tolerance(self):
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "99.99")))
        assert cats(r, "T1") == [MATCHED_ROUNDING]
        assert r.count(AGGREGATE_ROUNDING) == 0
        assert not r.summary["rounding_breach"]

    def test_cumulative_rounding_breaches_aggregate_tolerance(self):
        n = 8
        r = reconcile(pdf(*[P(f"T{i}", "100.00") for i in range(n)]),
                      bdf(*[B(f"T{i}", "99.99") for i in range(n)]))
        assert r.count(MATCHED_ROUNDING) == n           # each individually fine
        assert r.count(AMOUNT_MISMATCH) == 0
        assert r.summary["rounding_aggregate_paise"] == -8
        assert r.summary["rounding_breach"] is True     # aggregate is not
        agg = r.by_category(AGGREGATE_ROUNDING).iloc[0]
        assert agg["variance_paise"] == -8 and agg["bridge_effect_paise"] == 0  # not counted twice
        assert r.summary["status"].startswith("UNRECONCILED")
        assert r.summary["total_variance_paise"] == -8

    def test_offsetting_rounding_does_not_breach(self):
        r = reconcile(pdf(*[P(f"T{i}", "100.00") for i in range(6)]),
                      bdf(*[B(f"T{i}", "100.01" if i % 2 else "99.99") for i in range(6)]))
        assert r.summary["rounding_aggregate_paise"] == 0 and not r.summary["rounding_breach"]

    def test_tolerance_is_configurable(self):
        cfg = ReconciliationConfig(individual_tolerance_paise=0)
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "99.99")), cfg)
        assert cats(r, "T1") == [AMOUNT_MISMATCH]


# --------------------------------------------------------------------------- #
# Duplicates
# --------------------------------------------------------------------------- #
class TestDuplicates:
    def test_duplicate_bank_entry_detected_original_preserved(self):
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "100.00", bid="B1"), B("T1", "100.00", bid="B1-DUP")))
        dup = r.by_category(DUPLICATE_BANK)
        assert len(dup) == 1 and dup.iloc[0]["bank_record_id"] == "B1-DUP"
        matched = r.by_category(MATCHED)
        assert len(matched) == 1 and matched.iloc[0]["bank_record_id"] == "B1"

    def test_duplicate_not_double_counted(self):
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "100.00", bid="B1"), B("T1", "100.00", bid="B1-DUP")))
        assert r.summary["bank_net_paise"] == 10000
        assert r.summary["bank_net_incl_duplicates_paise"] == 20000
        assert r.summary["duplicates_excluded_paise"] == 10000
        assert r.summary["total_variance_paise"] == 0
        assert r.by_category(DUPLICATE_BANK).iloc[0]["bridge_effect_paise"] == 0

    def test_conflicting_duplicate_flagged(self):
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "100.00", bid="B1"), B("T1", "150.00", bid="B2")))
        assert "conflicting" in r.by_category(DUPLICATE_BANK).iloc[0]["explanation"].lower()


# --------------------------------------------------------------------------- #
# Orphan refunds / unmatched bank
# --------------------------------------------------------------------------- #
class TestOrphans:
    def test_orphan_refund(self):
        r = reconcile(pdf(P("T1", "100.00")),
                      bdf(B("T1", "100.00"), B("R9", "75.00", ttype="REFUND", original="TXN-9999")))
        row = r.by_category(ORPHAN_REFUND).iloc[0]
        assert row["transaction_id"] == "R9" and row["original_transaction_id"] == "TXN-9999"
        assert row["bank_amount_paise"] == 7500
        assert "does not exist" in row["explanation"]
        assert r.summary["total_variance_paise"] == -7500

    def test_bank_refund_for_known_payment_is_unmatched_not_orphan(self):
        r = reconcile(pdf(P("T1", "100.00")),
                      bdf(B("T1", "100.00"), B("R1", "40.00", ttype="REFUND", original="T1")))
        assert cats(r, "R1") == [UNMATCHED_BANK]

    def test_unmatched_bank_payment(self):
        r = reconcile(pdf(P("T1", "100.00")), bdf(B("T1", "100.00"), B("X9", "50.00")))
        assert cats(r, "X9") == [UNMATCHED_BANK]


# --------------------------------------------------------------------------- #
# Currency
# --------------------------------------------------------------------------- #
class TestCurrency:
    def test_currency_mismatch_never_matched(self):
        r = reconcile(pdf(P("T1", "100.00", currency="INR")), bdf(B("T1", "100.00", currency="USD")))
        assert r.summary["matched"] == 0
        assert r.count(CURRENCY_MISMATCH) == 2  # one row per side, each in its own currency
        assert_bridge_ties(r, "INR")
        assert_bridge_ties(r, "USD")


# --------------------------------------------------------------------------- #
# Validation / invalid input
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_invalid_csv_bytes(self):
        with pytest.raises(DatasetValidationError):
            read_csv(b"")
        with pytest.raises(DatasetValidationError):
            read_csv(b'a,b\n"unterminated,1\n')

    def test_non_utf8_file(self):
        with pytest.raises(DatasetValidationError):
            read_csv(b"\xff\xfe\x00\x81\x8d\x90")

    def test_missing_required_columns(self):
        df = pd.DataFrame([{"transaction_id": "T1", "amount": "1.00"}])
        with pytest.raises(DatasetValidationError) as exc:
            validate_dataframe(df, "platform")
        assert "currency" in str(exc.value) and "transaction_date" in str(exc.value)
        with pytest.raises(DatasetValidationError):
            reconcile(df, bdf())

    def test_empty_datasets(self):
        r = reconcile(pdf(), bdf())
        assert r.report.empty or r.summary["exceptions"] == 0
        assert r.summary["total_variance_paise"] == 0
        assert any("no records" in n for n in r.notes)

    def test_empty_platform_all_bank_unmatched(self):
        r = reconcile(pdf(), bdf(B("T1", "10.00")))
        assert cats(r, "T1") == [UNMATCHED_BANK]

    @pytest.mark.parametrize("amount", ["0", "0.00", "-100.00"])
    def test_zero_and_negative_amounts_rejected_not_dropped(self, amount):
        r = reconcile(pdf(P("T1", amount), P("T2", "10.00")), bdf(B("T2", "10.00")))
        inv = r.by_category(INVALID_RECORD)
        assert len(inv) == 1 and inv.iloc[0]["transaction_id"] == "T1"
        assert "greater than zero" in inv.iloc[0]["explanation"]
        assert r.summary["platform_records_raw"] == 2  # nothing silently discarded

    def test_row_level_errors(self):
        rows = [P("", "1.00"), P("T2", "abc"), P("T3", "1.005"), P("T4", "1.00", date="31-31-2026"),
                P("T5", "1.00", ttype="CHARGEBACK"), P("T6", "1.00", currency="RUPEES"),
                P("T7", "1.00", ttype="REFUND", original="")]
        v = validate_dataframe(pdf(*rows), "platform")
        assert len(v.valid) == 0 and len(v.rejected) == 7

    def test_out_of_period_record(self):
        r = reconcile(pdf(P("OCT", "10.00", date="2026-10-31")), bdf())
        assert cats(r, "OCT") == [OUT_OF_PERIOD]

    def test_uploaded_csv_roundtrip(self):
        buf = io.BytesIO(pdf(P("T1", "10.00")).to_csv(index=False).encode())
        df = read_csv(buf)
        assert validate_dataframe(df, "platform").valid.iloc[0]["amount_paise"] == 1000


# --------------------------------------------------------------------------- #
# Sample dataset: all four mandatory anomalies
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def data():
    return {k: v.astype(str) for k, v in generate().items()}


class TestSampleData:
    def test_deterministic(self):
        a, b = generate(), generate()
        for k in a:
            pd.testing.assert_frame_equal(a[k], b[k])

    def test_minimum_sizes(self, data):
        assert len(data["platform"]) >= 30 and len(data["bank"]) >= 30

    def test_all_anomalies_as_of_cutoff(self, data):
        r = reconcile(data["platform"], data["bank"])
        assert cats(r, "TXN-0032") == [PENDING_AT_CUTOFF]                    # A
        assert r.count(MATCHED_ROUNDING) == 10 and r.summary["rounding_breach"]  # B
        assert r.summary["rounding_aggregate_paise"] == -10
        assert cats(r, "TXN-0031") == [DUPLICATE_BANK, MATCHED]              # C
        assert cats(r, "RFD-0099") == [ORPHAN_REFUND]                        # D
        assert cats(r, "TXN-0033") == [MISSING_SETTLEMENT]
        assert cats(r, "TXN-0099") == [UNMATCHED_BANK]
        assert cats(r, "TXN-0034") == [AMOUNT_MISMATCH]
        assert r.count(MATCHED) == 22
        assert_bridge_ties(r)

    def test_late_settlement_with_december(self, data):
        r = reconcile(data["platform"], data["bank"], subsequent_bank_df=data["december"])
        assert cats(r, "TXN-0032") == [LATE_SETTLEMENT]
        assert r.count(PENDING_AT_CUTOFF) == 0 and r.count(MISSING_SETTLEMENT) == 1
        assert_bridge_ties(r)

    def test_financial_totals_exact(self, data):
        r = reconcile(data["platform"], data["bank"])
        p = sum((Decimal(a) * (-1 if t == "REFUND" else 1))
                for a, t in zip(data["platform"]["amount"], data["platform"]["transaction_type"]))
        assert r.summary["platform_net_paise"] == int(p * 100)
        s = r.summary
        assert s["bank_net_paise"] - s["platform_net_paise"] == s["total_variance_paise"]
        expected = -1 - 1 * 9 - 2500 - 1275000 - 620000 + 315000 - 75000  # see bridge
        assert s["total_variance_paise"] == expected

    def test_full_report_csv(self, data):
        r = reconcile(data["platform"], data["bank"])
        text = full_report_csv(r).decode("utf-8")
        assert "# SECTION: SUMMARY" in text and "# SECTION: BRIDGE" in text and "ORPHAN_REFUND" in text
