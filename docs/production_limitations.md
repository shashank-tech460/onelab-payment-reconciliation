# Three Things This System Could Get Wrong in Production

## 1. It depends on the bank echoing our `transaction_id`
Matching is an exact join on `transaction_id`. Real bank and acquirer files often carry only their own reference (UTR or RRN), a truncated ID, or a free-text narrative. They also frequently settle **net of fees, or as one batch amount covering many transactions**.

In those cases this engine would report a valid settlement as MISSING_SETTLEMENT on one side and UNMATCHED_BANK on the other, overstating exceptions on both sides. A gateway deducting a fee (e.g. 2%) would turn every record into an AMOUNT_MISMATCH.

**Production fix:** a reference-mapping layer (gateway ref ↔ UTR), fuzzy and amount/date-window matching with confidence scores, explicit fee and GST lines, and one-to-many matching of batch settlements.

## 2. "First occurrence is the original" can be wrong for duplicates
The duplicate rule treats repeated `transaction_id` rows as duplicates and keeps the **first row in file order**. That breaks in two ways:

- **Legitimate repeats are flagged as duplicates.** Split or partial settlements, a reversal followed by a re-presentment, or multiple partial refunds would be marked DUPLICATE. Their money would be excluded from the bank total, understating cash.
- **The wrong row can be kept.** If the "duplicate" is actually the correct posting (e.g. the first was later reversed), the variance lands on the wrong record.

The rule also cannot catch a duplicate that the bank re-posted under a *different* transaction ID.

**Production fix:** composite duplicate keys (ID + amount + settlement batch + bank line), reversal/status awareness, and a maker-checker workflow before money is excluded.

## 3. The timing and period rules are calendar-naive
The pending window is a fixed **T+2 calendar days**, and periods are cut on naive dates.

- **Settlement delays get misclassified.** Bank holidays, weekends and RBI settlement-cycle changes can delay settlement beyond T+2. A transaction on Friday 27 Nov might legitimately settle on Monday 30 Nov or later, but would be classified MISSING_SETTLEMENT instead of pending.
- **Cutoff-hour transactions can land in the wrong period.** Timestamps are treated as dates without time zone. A payment made at 00:10 IST on 1 December, exported by a UTC-based system, appears as 30 November (18:40 UTC). It is then reconciled in November when it belongs to December, and the bank side may disagree.
- **Partial December evidence makes old items look worse.** Older items still not found are reported as missing even if that December file is simply incomplete.

**Production fix:** business-day calendars per bank and settlement rail, timezone-aware timestamps with an explicit cutoff instant, and ageing buckets (T+3, T+7, T+30) instead of a binary pending/missing flag.
