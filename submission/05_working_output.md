# 05: Working Output

| Item | Status | Location |
|---|---|---|
| Deployed application URL | ⏳ **Not yet deployed.** It needs the candidate's GitHub and Streamlit Cloud sign-in (steps below). | _<paste URL after verifying it loads>_ |
| Source code ZIP | ✅ Built | `submission/onelab-payment-reconciliation.zip` |
| Demo video | ⏳ To be recorded by candidate | Checklist: `demo_video_checklist.md` · link: _<paste>_ |
| Three production limitations | ✅ | `docs/production_limitations.md` (summary below) |
| Test results | ✅ 55 passed, 0 failed (executed) | `docs/test_cases.md`, `submission/test_results.txt` |

## Deploying (needs your credentials)
1. `gh auth login` (once), then from the project root:
   ```bash
   git init -b main
   git add .
   git commit -m "Payment reconciliation system"
   gh repo create onelab-payment-reconciliation --public --source . --push
   ```
2. Go to https://share.streamlit.io, sign in with GitHub, click **Create app**, choose the repo and branch `main`, and set the main file to `app.py`. Click **Deploy**.
3. Open the URL, confirm the dashboard loads with the sample data, and paste the URL above.

## Three things this system could get wrong in production
1. **Reference dependence.** Matching requires the bank to carry our `transaction_id`. Settlements that are net of fees, batched, or carry only the bank's reference would produce false missing and unmatched breaks.
2. **Duplicate rule.** "Same ID ⇒ duplicate, keep first" would wrongly exclude legitimate split settlements or partial refunds, and can keep the wrong row.
3. **Calendar-naive timing.** A fixed T+2 calendar window and timezone-naive dates misclassify holiday and weekend settlements as missing, and put cutoff-hour transactions in the wrong month.
