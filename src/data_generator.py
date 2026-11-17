"""Deterministic synthetic data for the November 2026 reconciliation.

Run `python -m src.data_generator` to (re)write the CSVs in ./data.

Planted scenarios (see ANOMALY_MANIFEST and docs/data_dictionary.md):
  TXN-0001..0020  normal payments, exact match
  RFD-0001        normal refund of TXN-0005, exact match
  TXN-0021..0030  CUMULATIVE ROUNDING: bank amount is Rs 0.01 lower on each
  TXN-0031        DUPLICATE: posted twice in the bank file (BNK-0031, BNK-0031-D)
  TXN-0032        LATE SETTLEMENT: platform 30-Nov, bank settles 01-Dec
  TXN-0033        ordinary unmatched: no settlement anywhere (missing)
  TXN-0034        amount mismatch: bank is Rs 25.00 short
  TXN-0099        ordinary unmatched bank credit with no platform record
  RFD-0099        ORPHAN REFUND: bank refund of TXN-9999, which does not exist
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 42
CURRENCY = "INR"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PLATFORM_FILE = "platform_transactions.csv"
BANK_FILE = "bank_settlements.csv"
DECEMBER_FILE = "bank_settlements_december.csv"
MANIFEST_FILE = "anomaly_manifest.csv"

PAYMENT_METHODS = ["UPI", "CARD", "NETBANKING", "WALLET"]


def _fmt(paise: int) -> str:
    return f"{paise // 100}.{paise % 100:02d}"


def _gateway_ref(rng: random.Random) -> str:
    return f"PGW{rng.randint(10**8, 10**9 - 1)}"


def generate(seed: int = SEED) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)
    platform: list[dict] = []
    bank: list[dict] = []
    december: list[dict] = []
    manifest: list[dict] = []

    def add_platform(tid, tdate, paise, ttype="PAYMENT", original="", ref=None):
        ref = ref or _gateway_ref(rng)
        platform.append(
            {
                "transaction_id": tid,
                "original_transaction_id": original,
                "reference_id": ref,
                "transaction_date": tdate.isoformat(),
                "transaction_type": ttype,
                "amount": _fmt(paise),
                "currency": CURRENCY,
                "status": "SUCCESS",
                "customer_id": f"CUST{rng.randint(1000, 9999)}",
                "payment_method": rng.choice(PAYMENT_METHODS),
            }
        )
        return ref

    def bank_row(bid, tid, tdate, sdate, paise, ttype="PAYMENT", original="", ref=""):
        return {
            "bank_record_id": bid,
            "transaction_id": tid,
            "original_transaction_id": original,
            "reference_id": ref,
            "transaction_date": tdate.isoformat(),
            "settlement_date": sdate.isoformat(),
            "transaction_type": ttype,
            "amount": _fmt(paise),
            "currency": CURRENCY,
            "status": "SETTLED",
            "batch_id": f"BATCH-{sdate:%Y%m%d}",
        }

    def nov(day: int) -> date:
        return date(2026, 11, day)

    # 1) Normal payments TXN-0001..0020 and rounding payments TXN-0021..0030
    for n in range(1, 31):
        tid = f"TXN-{n:04d}"
        tdate = nov(rng.randint(1, 27))
        sdate = tdate + timedelta(days=rng.choice([1, 2]))
        paise = rng.randint(1500_00, 25000_00)
        ref = add_platform(tid, tdate, paise)
        bank_paise = paise
        if n >= 21:
            bank_paise = paise - 1  # Rs 0.01 lower: bank truncation vs platform rounding
            manifest.append(
                {
                    "scenario": "B. Cumulative rounding",
                    "record_ids": tid,
                    "dataset": "platform + bank",
                    "detail": f"platform {_fmt(paise)} vs bank {_fmt(bank_paise)} (diff -0.01)",
                    "expected_category": "MATCHED_ROUNDING (+ AGGREGATE_ROUNDING breach)",
                }
            )
        bank.append(bank_row(f"BNK-{n:04d}", tid, tdate, sdate, bank_paise, ref=ref))

    # 2) Normal refund of TXN-0005 (partial), matched exactly
    ref = add_platform("RFD-0001", nov(15), 1000_00, "REFUND", original="TXN-0005")
    bank.append(bank_row("BNK-R001", "RFD-0001", nov(15), nov(16), 1000_00, "REFUND", "TXN-0005", ref))

    # 3) DUPLICATE: TXN-0031 posted twice by the bank
    paise = 4321_50
    ref = add_platform("TXN-0031", nov(18), paise)
    bank.append(bank_row("BNK-0031", "TXN-0031", nov(18), nov(19), paise, ref=ref))
    bank.append(bank_row("BNK-0031-D", "TXN-0031", nov(18), nov(19), paise, ref=ref))
    manifest.append(
        {
            "scenario": "C. Duplicate entry",
            "record_ids": "TXN-0031 (bank rows BNK-0031, BNK-0031-D)",
            "dataset": "bank only",
            "detail": "Same transaction_id/amount/currency posted twice in the bank file",
            "expected_category": "MATCHED (BNK-0031) + DUPLICATE_BANK (BNK-0031-D)",
        }
    )

    # 4) LATE SETTLEMENT: TXN-0032 on 30-Nov, settled 01-Dec (December file)
    paise = 12750_00
    ref = add_platform("TXN-0032", nov(30), paise)
    december.append(bank_row("BNK-D0032", "TXN-0032", nov(30), date(2026, 12, 1), paise, ref=ref))
    manifest.append(
        {
            "scenario": "A. Late settlement",
            "record_ids": "TXN-0032 (bank BNK-D0032)",
            "dataset": "platform (Nov) + December bank file",
            "detail": "Recorded 2026-11-30, settled 2026-12-01",
            "expected_category": "PENDING_AT_CUTOFF without Dec evidence; LATE_SETTLEMENT with it",
        }
    )

    # 5) Ordinary unmatched platform record: never settled
    paise = 6200_00
    add_platform("TXN-0033", nov(12), paise)
    manifest.append(
        {
            "scenario": "Ordinary unmatched (platform)",
            "record_ids": "TXN-0033",
            "dataset": "platform only",
            "detail": "Recorded 2026-11-12, no bank settlement in Nov or Dec",
            "expected_category": "MISSING_SETTLEMENT",
        }
    )

    # 6) Amount mismatch beyond tolerance
    paise = 8900_00
    ref = add_platform("TXN-0034", nov(20), paise)
    bank.append(bank_row("BNK-0034", "TXN-0034", nov(20), nov(21), paise - 25_00, ref=ref))
    manifest.append(
        {
            "scenario": "Amount mismatch",
            "record_ids": "TXN-0034 (bank BNK-0034)",
            "dataset": "platform + bank",
            "detail": "Bank settled Rs 25.00 less than recorded",
            "expected_category": "AMOUNT_MISMATCH",
        }
    )

    # 7) Ordinary unmatched bank credit
    bank.append(bank_row("BNK-0099", "TXN-0099", nov(22), nov(23), 3150_00, ref="PGW000000099"))
    manifest.append(
        {
            "scenario": "Ordinary unmatched (bank)",
            "record_ids": "TXN-0099 (bank BNK-0099)",
            "dataset": "bank only",
            "detail": "Bank credit with no platform record",
            "expected_category": "UNMATCHED_BANK",
        }
    )

    # 8) ORPHAN REFUND
    bank.append(
        bank_row("BNK-R099", "RFD-0099", nov(24), nov(25), 750_00, "REFUND", "TXN-9999", "PGW000009999")
    )
    manifest.append(
        {
            "scenario": "D. Orphan refund",
            "record_ids": "RFD-0099 (bank BNK-R099), original TXN-9999",
            "dataset": "bank only",
            "detail": "Refund of Rs 750.00 referencing TXN-9999, which is not in the platform dataset",
            "expected_category": "ORPHAN_REFUND",
        }
    )

    # 9) December file also carries genuine December activity (must be ignored)
    for n in range(1, 4):
        tdate = date(2026, 12, n)
        december.append(
            bank_row(
                f"BNK-D12{n:02d}", f"TXN-12{n:02d}", tdate, tdate + timedelta(days=1),
                rng.randint(1500_00, 25000_00), ref=_gateway_ref(rng),
            )
        )

    return {
        "platform": pd.DataFrame(platform),
        "bank": pd.DataFrame(bank),
        "december": pd.DataFrame(december),
        "manifest": pd.DataFrame(manifest),
    }


def write_sample_data(out_dir: Path = DATA_DIR, seed: int = SEED) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = generate(seed)
    paths = {
        "platform": out_dir / PLATFORM_FILE,
        "bank": out_dir / BANK_FILE,
        "december": out_dir / DECEMBER_FILE,
        "manifest": out_dir / MANIFEST_FILE,
    }
    for key, path in paths.items():
        frames[key].to_csv(path, index=False, lineterminator="\n")
    return paths


def load_sample_data(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    """Load the committed CSVs as strings; regenerate in memory if absent."""
    files = {"platform": PLATFORM_FILE, "bank": BANK_FILE, "december": DECEMBER_FILE, "manifest": MANIFEST_FILE}
    if all((data_dir / f).exists() for f in files.values()):
        return {k: pd.read_csv(data_dir / f, dtype=str, keep_default_na=False) for k, f in files.items()}
    return {k: v.astype(str) for k, v in generate().items()}


if __name__ == "__main__":
    for name, p in write_sample_data().items():
        print(f"wrote {name:9s} -> {p}")
