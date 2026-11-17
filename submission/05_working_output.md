# 05: Working Output

| Item | Status | Location |
|---|---|---|
| GitHub repository | ✅ Public, `main` pushed (verified via `gh` / GitHub API) | https://github.com/shashank-tech460/onelab-payment-reconciliation |
| Deployed application URL | ⏳ **Not yet deployed.** Needs the candidate's Streamlit Community Cloud sign-in in a browser (steps below). | _<paste URL after it is opened and verified>_ |
| Source code ZIP | ✅ Built and verified (opens, required files present) | `submission/onelab-payment-reconciliation.zip` (local; not committed) |
| Demo video | ⏳ To be recorded by candidate. No video exists yet. | Script: `demo_script.md` · checklist: `demo_video_checklist.md` · link: _<paste>_ |
| Three production limitations | ✅ | `docs/production_limitations.md` (summary below) |
| Test results | ✅ 55 passed, 0 failed (executed) | `docs/test_cases.md`, `submission/test_results.txt` |

## Deploying on Streamlit Community Cloud (candidate action)
1. Go to https://share.streamlit.io and sign in with GitHub. Authorize Streamlit if asked.
2. Click **Create app**, then **Deploy a public app from GitHub**.
3. Set repository `shashank-tech460/onelab-payment-reconciliation`, branch `main`, main file `app.py`. No secrets are needed.
4. Click **Deploy** and wait for the build, about 2–4 minutes.
5. Open the URL and check:
   - the header shows "UNRECONCILED - EXCEPTIONS REQUIRE REVIEW"
   - Total variance is −₹16,575.10
   - each Results sub-tab lists its anomaly
   - **Complete reconciliation report** downloads
6. Paste the URL in the table above.

## Three things this system could get wrong in production
1. **Reference dependence.** Matching requires the bank to carry our `transaction_id`. Settlements that are net of fees, batched, or carry only the bank's reference would produce false missing and unmatched breaks.
2. **Duplicate rule.** "Same ID ⇒ duplicate, keep first" would wrongly exclude legitimate split settlements or partial refunds, and can keep the wrong row.
3. **Calendar-naive timing.** A fixed T+2 calendar window and timezone-naive dates misclassify holiday and weekend settlements as missing, and put cutoff-hour transactions in the wrong month.
