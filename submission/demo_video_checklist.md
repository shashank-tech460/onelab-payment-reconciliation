# Demo Video Recording Checklist (target 3–5 minutes)

**Setup:** run `streamlit run app.py` (or open the deployed URL). Use a browser at ≥ 1280 px wide with zoom at 100%. Close unrelated tabs.

- [ ] **0:00 Intro (20 s).** State the problem: the platform records instantly, the bank settles T+1/T+2, and the books don't match at month-end.
- [ ] **Overview.** Point out the reporting period, KPI cards and status badge ("UNRECONCILED - EXCEPTIONS REQUIRE REVIEW").
- [ ] **Bridge waterfall.** Walk from platform net ₹3,71,260.37 to bank net ₹3,54,685.27, then show the "Why the books don't balance" list.
- [ ] **A. Late settlement.** In Results → *Pending settlements*, show `TXN-0032`. Toggle **Include post-cutoff settlement evidence** in the sidebar. It moves to *Late settlements* with settlement date 2026-12-01 and bank record `BNK-D0032`, and it is not counted as missing.
- [ ] **B. Rounding.** In Results → *Rounding differences*, show 10 records at −₹0.01, each within ±₹0.02, with a cumulative −₹0.10 breaching ±₹0.05. Then show Analytics → the aggregate rounding chart crossing the dashed tolerance line.
- [ ] **C. Duplicate.** In Results → *Duplicates*, show `BNK-0031-D`. Point at the KPI card "Duplicates excluded ₹4,321.50".
- [ ] **D. Orphan refund.** In Results → *Orphan refunds*, show `RFD-0099`, original `TXN-9999`, ₹750.00 and the reason.
- [ ] **Investigation.** Search `TXN-0034`, open the record detail and show the variance of −₹25.00 with its explanation. Filter by severity = High.
- [ ] **Upload and validation.** Switch to *Upload CSV files* and upload a CSV with a column removed to show the error message. Then upload the sample files to show the app working on uploaded data.
- [ ] **Reports.** Download *Complete reconciliation report* and open it to show the summary, bridge and records sections.
- [ ] **Tests (20 s).** In a terminal, run `pytest -v` and show 55 passed.
- [ ] **Close (20 s).** Name the three production limitations (`docs/production_limitations.md`).

Upload as an unlisted YouTube or Loom video, and paste the link into `05_working_output.md`.
