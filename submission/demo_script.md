# Demo Script (about 2.5 minutes)

**Before recording:** open the live app (or `streamlit run app.py`) at ≥ 1280 px width with the sidebar visible and the post-cutoff toggle **off**. Have a terminal open in the project folder.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:20 | Overview tab, header | "A payments platform records every transaction instantly, but the bank settles in batches one to two days later. At month-end the two sets of books should agree, and they don't. This app finds every difference, classifies it, and explains the gap to the paisa." |
| 0:20–0:35 | Sidebar → *Built-in sample* selected; point at the KPI cards | "I've loaded the November sample: 35 platform transactions and 36 bank settlements. You can also upload your own CSVs here. 32 records match, 22 exactly and 10 within a two-paise tolerance." |
| 0:35–0:50 | Results → **Matched** sub-tab | "Matching is one-to-one on transaction ID. Currency and payment-versus-refund type must agree before amounts are compared, and all money is in integer paise, never floats." |
| 0:50–1:10 | Results → **Pending settlements** (`TXN-0032`), then toggle **Include post-cutoff settlement evidence**, then **Late settlements** | "**Anomaly A:** this ₹12,750 payment was made on 30 November. As of cutoff it is *pending*, not missing. When I load December's bank file, it shows as settled late on 1 December." |
| 1:10–1:30 | Results → **Rounding differences**; then Analytics → aggregate rounding chart | "**Anomaly B:** ten records are each one paisa short, inside the per-record tolerance. Together they come to minus ten paise, beyond the five-paise aggregate tolerance. A same-direction drift like this is a systematic rounding bug, and at a million transactions it's ₹10,000." |
| 1:30–1:45 | Results → **Duplicates** (`BNK-0031-D`); point at the *Duplicates excluded* card | "**Anomaly C:** the bank posted `TXN-0031` twice. The original is kept, the copy is flagged, and its ₹4,321.50 is excluded so nothing is double counted." |
| 1:45–1:58 | Results → **Orphan refunds** (`RFD-0099`) | "**Anomaly D:** the bank refunded ₹750 against `TXN-9999`, a transaction that doesn't exist on our platform. Money left with no sale behind it." |
| 1:58–2:20 | Overview → bridge chart and "Why the books don't balance" | "The books are out by minus ₹16,575.10, and the bridge explains all of it: rounding, a ₹25 short settlement, the timing item, one missing settlement, an unknown bank credit, and the orphan refund. The engine refuses to produce a report if this doesn't tie out exactly." |
| 2:20–2:35 | Reports → click **Complete reconciliation report**, open the CSV | "Matched, unmatched, exceptions, and the full report with its summary, bridge and every record are all downloadable as CSV." |
| 2:35–2:45 | Terminal: `pytest -q` → *55 passed* | "55 automated tests cover each scenario and the edge cases. Thanks for watching." |

**Fallback:** if a sub-tab count looks different, check that the post-cutoff toggle is in the state the script expects. Pending and Late swap when it changes.
