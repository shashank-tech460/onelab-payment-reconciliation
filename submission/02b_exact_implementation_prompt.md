# Exact prompt used for this implementation (Claude Code)

This is the verbatim prompt pasted into Claude Code (Opus 5.5) on 17 Nov 2026 to start the build.

---

# ONELAB AI FITNESS ASSESSMENT — PAYMENT RECONCILIATION SYSTEM

Act as a Senior FinTech Software Engineer, AI-Native Engineer, Python Developer, Software Architect, UI/UX Engineer and QA Engineer.

You are responsible for building a complete, functional and professionally presented Payment Reconciliation System for the Onelab AI Native Engineer Intern assessment (November 2026).

IMPORTANT: We have a strict two-hour assessment deadline. Start implementation immediately. Do not waste time producing lengthy plans or asking unnecessary questions. Make sensible engineering decisions, document assumptions and build the actual application.

## 1. BUSINESS PROBLEM

A payments company records every transaction immediately when a customer makes a payment.

The bank processes these transactions in batches and settles funds after approximately 1–2 days.

At month-end, the company's transaction records should reconcile with the bank's settlement records.

However, there are differences between the two datasets.

Build a system that compares both datasets, identifies discrepancies, calculates financial differences and explains why the books do not balance.

## 2. MANDATORY ANOMALIES

You MUST generate synthetic datasets that contain all four scenarios:

A. LATE SETTLEMENT
- A platform transaction is recorded on 30 November 2026.
- Its corresponding bank settlement occurs on 1 December 2026.
- When November is reconciled as of 30 November, identify it as pending at cutoff.
- When December settlement evidence is available, identify it as subsequently settled.
- Do not incorrectly classify it as permanently missing.

B. CUMULATIVE ROUNDING DIFFERENCE
- Create multiple transactions with small individual differences, such as ₹0.01.
- Individual differences should be within the configured tolerance.
- Their aggregate difference must exceed the aggregate tolerance.
- Report individual and cumulative variances separately.
- Explain why the aggregate difference matters.

C. DUPLICATE ENTRY
- Duplicate a record in exactly one dataset.
- Detect the duplicate using transaction identifiers and appropriate duplicate rules.
- Preserve the original record.
- Prevent double-counting in financial totals.
- Show the duplicate record in the exceptions report.

D. ORPHAN REFUND
- Add a bank refund referencing an original transaction that does not exist in the platform dataset.
- Identify it as an orphan refund.
- Show the refund reference, amount and reason for the exception.

Also include normal matched transactions and ordinary unmatched transactions.

## 3. TECHNOLOGY STACK

Use:

- Python
- Pandas
- Streamlit
- Plotly
- Pytest

Use Decimal or integer paise for all monetary calculations. Never use floating-point arithmetic for financial reconciliation.

Keep the project modular and maintainable.

## 4. DATA GENERATION

Generate deterministic synthetic datasets with at least 30 platform transaction records and 30 bank records.

Include:
- Platform transaction CSV.
- Bank settlement CSV.
- December settlement evidence for the late-settlement scenario.

Include appropriate columns such as:
- transaction_id
- original_transaction_id
- reference_id
- transaction_date
- settlement_date
- transaction_type
- amount
- currency
- status

You may add additional columns when necessary.

Requirements:
- Use INR as the default currency.
- Use November 2026 as the reporting month.
- Use December 2026 for subsequent settlement evidence.
- Include a fixed random seed.
- Include a data dictionary.
- Document exactly which records contain planted anomalies.
- Make sample datasets downloadable.

## 5. RECONCILIATION ENGINE

Create a reliable reconciliation engine.

Implement:

1. Transaction matching using stable transaction references.
2. Duplicate detection.
3. Late settlement identification.
4. Missing settlement detection.
5. Orphan refund detection.
6. Individual amount variance calculation.
7. Aggregate rounding variance calculation.
8. Matched transaction classification.
9. Unmatched transaction classification.
10. Exception categorisation.
11. Financial reconciliation summary.

Important financial rules:

- Use Decimal or integer paise.
- Preserve source amounts.
- Do not silently discard records.
- Never match records from different currencies.
- Prevent one bank record from matching multiple platform transactions.
- Do not count duplicates twice.
- Distinguish pending settlements from permanently missing settlements.
- Distinguish refunds from original payments.
- Document matching tolerances and aggregate tolerances.
- Explain all classification decisions.

## 6. PROFESSIONAL STREAMLIT DASHBOARD

Build a professional fintech dashboard.

The interface should include:

### Dashboard overview
- Application title.
- Reporting period.
- Total platform transactions.
- Total bank settlements.
- Matched transactions.
- Unmatched transactions.
- Total exceptions.
- Total variance.
- Overall reconciliation status.

### Data upload
- Upload platform transactions CSV.
- Upload bank settlements CSV.
- Load built-in sample datasets.
- Validate uploaded files.
- Display useful validation errors.

### Reconciliation results
- Matched transactions.
- Unmatched transactions.
- Pending settlements.
- Late settlements.
- Duplicate records.
- Orphan refunds.
- Rounding differences.

### Analytics
- Reconciliation status chart.
- Exception category chart.
- Platform versus bank amount comparison.
- Aggregate variance analysis.

### Investigation
- Detailed transaction-level records.
- Search and filters.
- Exception descriptions.
- Original transaction references.
- Settlement information.

### Reports
- Download matched transactions.
- Download unmatched transactions.
- Download exceptions.
- Download complete reconciliation report as CSV.

Design should be clean, modern, professional and suitable for a fintech company.

Use a consistent colour palette, good spacing, readable tables and useful financial summary cards.

Do not prioritise decorative UI over correct calculations.

## 7. PROJECT STRUCTURE

Create a professional structure similar to:

onelab-payment-reconciliation/
    app.py
    requirements.txt
    README.md
    src/
        __init__.py
        reconciliation.py
        data_generator.py
        validators.py
        reporting.py
    data/
        platform_transactions.csv
        bank_settlements.csv
    tests/
        test_reconciliation.py
    docs/
        assumptions.md
        data_dictionary.md
        test_cases.md
        production_limitations.md

You may modify the structure if necessary.

## 8. AUTOMATED TESTING

Use Pytest.

Write tests for:

- Correctly matched payments.
- Late settlements.
- Individual rounding differences.
- Cumulative rounding differences.
- Duplicate bank entries.
- Orphan refunds.
- Missing settlements.
- Invalid CSV files.
- Missing required columns.
- Currency mismatch.
- Empty datasets.
- Zero and negative amounts where appropriate.
- Duplicate counting prevention.

Execute all tests.

Fix failures and rerun the tests.

Never report a test as passed unless it was actually executed successfully.

## 9. DOCUMENTATION

Create a complete README containing:

- Business problem.
- Solution overview.
- Features.
- Technology stack.
- Installation instructions.
- How to run the application.
- Dataset explanation.
- Reconciliation methodology.
- Assumptions.
- Testing instructions.
- Deployment instructions.

Create documentation for:
- Business assumptions.
- Data dictionary.
- Test cases and expected results.
- Exactly three things the system could get wrong in production.

Production limitations must be realistic and honest.

## 10. DEPLOYMENT PREPARATION

Prepare the application for deployment using Streamlit Community Cloud.

Include:
- requirements.txt
- Correct application entry point.
- README deployment instructions.
- GitHub-ready project structure.

If GitHub authentication or deployment credentials are required, tell me exactly what action I need to perform.

Do not claim successful deployment unless the deployed URL has actually been opened and verified.

## 11. EXECUTION PRIORITIES

Follow this exact order:

PRIORITY 1: Create the project structure.

PRIORITY 2: Generate synthetic datasets containing all four mandatory anomalies.

PRIORITY 3: Implement the financial reconciliation engine.

PRIORITY 4: Build the Streamlit dashboard.

PRIORITY 5: Implement automated tests and run them.

PRIORITY 6: Fix critical bugs.

PRIORITY 7: Prepare deployment.

PRIORITY 8: Prepare all submission documents.

Do not stop after giving me a plan. Actually create the files and implement the application.

Keep working until you have a functional application or encounter a genuine blocker.

Use your available tools to inspect files, execute commands, run tests and debug errors.

If you encounter a problem, investigate and fix it rather than repeatedly asking me what to do.

## 12. FINAL ASSESSMENT DELIVERABLES

Onelab requires five deliverables:

1. BRAINSTORMING THREAD
   Preserve the complete LLM brainstorming conversation, including the original discussion.

2. DISTILLED PROMPT AND RAW PROMPT
   Save the refined engineering specification and the exact prompt used for this implementation.

3. CLAUDE CODE EXECUTION THREAD
   Preserve the complete execution conversation, including mistakes, debugging and corrections.

4. TEST CASES
   Provide test cases with expected results, actual results and execution status.

5. WORKING OUTPUT
   Prepare:
   - Deployed application URL.
   - Complete source code ZIP.
   - Demo video recording checklist.
   - Exactly three production limitations.

Create a submission folder with appropriate documentation and files.

Do not fabricate conversation histories, test results, deployment URLs or demo videos.

## 13. FINAL INSTRUCTIONS

Start building immediately.

The most important success criteria are:

- All four mandatory anomalies are correctly detected.
- Financial calculations are accurate.
- The dashboard actually works.
- Automated tests execute successfully.
- The project is documented.
- Submission requirements are addressed.

Work efficiently. Avoid unnecessary features. Prioritise a reliable, working engineering solution over an overcomplicated application.

Begin by inspecting the current directory and creating the project files. Then implement the application.
