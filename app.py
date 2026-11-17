"""Onelab Payment Reconciliation — Streamlit dashboard.

Run:  streamlit run app.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_generator import BANK_FILE, DECEMBER_FILE, PLATFORM_FILE, load_sample_data
from src.reconciliation import (
    AGGREGATE_ROUNDING, AMOUNT_MISMATCH, CATEGORY_META, CURRENCY_MISMATCH, DUPLICATE_BANK,
    DUPLICATE_PLATFORM, INVALID_RECORD, LATE_SETTLEMENT, MATCHED, MATCHED_ROUNDING, MISSING_SETTLEMENT,
    ORPHAN_REFUND, OUT_OF_PERIOD, PENDING_AT_CUTOFF, TYPE_MISMATCH, UNMATCHED_BANK,
    ReconciliationConfig, reconcile,
)
from src.reporting import (
    bridge_export, full_report_csv, summary_frame, to_csv_bytes, to_display_frame, to_export_frame,
)
from src.validators import DatasetValidationError, format_inr, read_csv, validate_dataframe

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"

# --------------------------------------------------------------------------- #
# Theme tokens (validated reference palette; status colours always with labels)
# --------------------------------------------------------------------------- #
C = {
    "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#8a8984",
    "grid": "#e1e0d9", "axis": "#c3c2b7", "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
    "s4": "#eda100", "pos": "#2a78d6", "neg": "#e34948", "total": "#52514e",
    "good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b",
    "brand": "#0F766E",
}
GROUP_COLORS = {"Matched": C["s1"], "Timing": C["s2"], "Unmatched": C["s3"], "Data quality": C["s4"]}
SEVERITY_ICON = {"High": "🔴 High", "Medium": "🟠 Medium", "Low": "🟡 Low", "Info": "🔵 Info", "None": "🟢 None"}

st.set_page_config(page_title="Payment Reconciliation · Onelab", page_icon="💳", layout="wide")

st.markdown(
    f"""
<style>
  .block-container {{ padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1400px; }}
  .app-header {{ display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap;
                gap: 12px; border-bottom: 1px solid {C['grid']}; padding-bottom: 14px; margin-bottom: 18px; }}
  .app-title {{ font-size: 1.65rem; font-weight: 700; color:{C['ink']}; margin:0; letter-spacing:-0.01em; }}
  .app-sub {{ color:{C['ink2']}; font-size: 0.92rem; margin-top: 2px; }}
  .badge {{ display:inline-block; padding: 6px 12px; border-radius: 999px; font-weight:600; font-size:0.82rem;
            border: 1px solid rgba(11,11,11,0.10); }}
  .badge-ok {{ background:#e8f6e8; color:#006300; }}
  .badge-warn {{ background:#fff4dc; color:#7a5200; }}
  .badge-bad {{ background:#fdeaea; color:#9b1c1c; }}
  .kpi {{ background:#ffffff; border:1px solid rgba(11,11,11,0.08); border-radius: 12px; padding: 14px 16px;
          height: 100%; box-shadow: 0 1px 2px rgba(15,23,42,0.04); }}
  .kpi-label {{ color:{C['ink2']}; font-size:0.76rem; text-transform:uppercase; letter-spacing:0.05em; font-weight:600; }}
  .kpi-value {{ color:{C['ink']}; font-size:1.55rem; font-weight:700; margin-top:4px; font-variant-numeric: tabular-nums; }}
  .kpi-foot {{ color:{C['muted']}; font-size:0.78rem; margin-top:2px; }}
  .note {{ background:#f3f7fb; border-left: 3px solid {C['s1']}; padding: 10px 14px; border-radius: 6px;
           color:{C['ink2']}; font-size: 0.88rem; }}
  div[data-testid="stTabs"] button p {{ font-weight: 600; }}
</style>
""",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _sample():
    return load_sample_data()


@st.cache_data(show_spinner=False)
def _run(platform: pd.DataFrame, bank: pd.DataFrame, subsequent: pd.DataFrame | None, cfg_tuple: tuple):
    cfg = ReconciliationConfig(*cfg_tuple)
    return reconcile(platform, bank, cfg, subsequent)


def _load_upload(upload, kind: str):
    """Return (df or None, list_of_errors)."""
    if upload is None:
        return None, []
    try:
        df = read_csv(upload)
        validate_dataframe(df, kind)  # fatal checks only; row checks reported by engine
        return df, []
    except DatasetValidationError as exc:
        return None, exc.errors


sample = _sample()

with st.sidebar:
    st.markdown("### Data source")
    source = st.radio("Choose input", ["Built-in sample (Nov 2026)", "Upload CSV files"], label_visibility="collapsed")
    errors: list[str] = []
    if source.startswith("Built-in"):
        platform_df, bank_df, december_df = sample["platform"], sample["bank"], sample["december"]
        source_label = "Built-in synthetic sample (seed 42)"
    else:
        up_p = st.file_uploader("Platform transactions CSV", type=["csv"])
        up_b = st.file_uploader("Bank settlements CSV", type=["csv"])
        up_s = st.file_uploader("Subsequent bank evidence CSV (optional, e.g. December)", type=["csv"])
        platform_df, e1 = _load_upload(up_p, "platform")
        bank_df, e2 = _load_upload(up_b, "bank")
        december_df, e3 = _load_upload(up_s, "bank")
        errors = [f"Platform file: {e}" for e in e1] + [f"Bank file: {e}" for e in e2] + [f"Subsequent file: {e}" for e in e3]
        source_label = "Uploaded files"

    st.markdown("### Reconciliation settings")
    use_subsequent = st.toggle(
        "Include post-cutoff settlement evidence", value=False,
        help="Off: reconcile as of the cutoff (late items show as PENDING). On: use December evidence to "
             "confirm items that settled after cutoff (LATE_SETTLEMENT).",
    )
    with st.expander("Period & tolerances", expanded=False):
        period_start = st.date_input("Period start", date(2026, 11, 1))
        cutoff = st.date_input("Cutoff date", date(2026, 11, 30))
        ind_tol = st.number_input("Individual tolerance (₹)", min_value=0.00, max_value=100.0, value=0.02,
                                  step=0.01, format="%.2f")
        agg_tol = st.number_input("Aggregate tolerance (₹)", min_value=0.00, max_value=10000.0, value=0.05,
                                  step=0.01, format="%.2f")
        lag = st.number_input("Settlement lag (days, T+n)", min_value=0, max_value=10, value=2, step=1)

    st.markdown("### Sample datasets")
    st.download_button("⬇ Platform transactions", to_csv_bytes(sample["platform"]), PLATFORM_FILE, "text/csv",
                       use_container_width=True)
    st.download_button("⬇ Bank settlements (Nov)", to_csv_bytes(sample["bank"]), BANK_FILE, "text/csv",
                       use_container_width=True)
    st.download_button("⬇ Bank settlements (Dec evidence)", to_csv_bytes(sample["december"]), DECEMBER_FILE,
                       "text/csv", use_container_width=True)

# number_input returns float; convert via round() to integer paise once, at the UI edge.
cfg_tuple = (period_start, cutoff, int(round(ind_tol * 100)), int(round(agg_tol * 100)), int(lag), "INR")

# --------------------------------------------------------------------------- #
# Guard rails
# --------------------------------------------------------------------------- #
if errors:
    st.error("**The uploaded file(s) could not be used:**\n\n" + "\n".join(f"- {e}" for e in errors))
    st.stop()
if platform_df is None or bank_df is None:
    st.markdown('<div class="app-title">💳 Payment Reconciliation</div>', unsafe_allow_html=True)
    st.info("Upload both a **platform transactions** CSV and a **bank settlements** CSV in the sidebar, "
            "or switch to the built-in sample. Download the sample files to see the expected format.")
    st.stop()
if cutoff < period_start:
    st.error("Cutoff date must be on or after the period start.")
    st.stop()

try:
    result = _run(platform_df, bank_df, december_df if use_subsequent else None, cfg_tuple)
except DatasetValidationError as exc:
    st.error("**Validation failed:**\n\n" + "\n".join(f"- {e}" for e in exc.errors))
    st.stop()

S = result.summary
R = result.report

# --------------------------------------------------------------------------- #
# Header + KPIs
# --------------------------------------------------------------------------- #
status = S["status"]
badge_cls = "badge-ok" if status == "RECONCILED" else "badge-warn" if "TIMING" in status else "badge-bad"
badge_icon = "✔" if badge_cls == "badge-ok" else "◷" if badge_cls == "badge-warn" else "⚠"
st.markdown(
    f"""
<div class="app-header">
  <div>
    <div class="app-title">💳 Payment Reconciliation</div>
    <div class="app-sub">Reporting period <b>{S['period_start']:%d %b %Y} – {S['cutoff_date']:%d %b %Y}</b>
      · Currency {S['currency']} · {source_label}
      · Post-cutoff evidence: <b>{'included' if S['subsequent_evidence_loaded'] else 'not included'}</b></div>
  </div>
  <span class="badge {badge_cls}">{badge_icon} {status}</span>
</div>
""",
    unsafe_allow_html=True,
)


def kpi(col, label, value, foot=""):
    col.markdown(f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>'
                 f'<div class="kpi-foot">{foot}</div></div>', unsafe_allow_html=True)


k = st.columns(4)
kpi(k[0], "Platform transactions", S["platform_records_raw"], f"Net {format_inr(S['platform_net_paise'])}")
kpi(k[1], "Bank settlements", S["bank_records_raw"], f"Net {format_inr(S['bank_net_paise'])} (deduplicated)")
kpi(k[2], "Matched", S["matched"], f"{S['matched_exact']} exact · {S['matched_rounding']} within tolerance")
kpi(k[3], "Unmatched / breaks", S["unmatched"], "No in-period counterpart or amount break")
st.write("")
k = st.columns(4)
kpi(k[0], "Total exceptions", S["exceptions"], f"{S['high_severity_exceptions']} high severity")
kpi(k[1], "Total variance (bank − platform)", format_inr(S["total_variance_paise"]), "Fully explained in the bridge below")
kpi(k[2], "Aggregate rounding", format_inr(S["rounding_aggregate_paise"]),
    f"{'⚠ breach' if S['rounding_breach'] else '✔ within'} ±{format_inr(result.config.aggregate_tolerance_paise)} tolerance")
kpi(k[3], "Duplicates excluded", format_inr(S["duplicates_excluded_paise"]), "Not double counted in bank net")

for n in result.notes:
    st.warning(n)
st.write("")

# --------------------------------------------------------------------------- #
# Chart helpers
# --------------------------------------------------------------------------- #
def _layout(fig: go.Figure, height=360, **kw):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=78, b=8), plot_bgcolor=C["surface"], paper_bgcolor=C["surface"],
        font=dict(color=C["ink2"], size=12), hoverlabel=dict(bgcolor="white", font_color=C["ink"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"), **kw,
    )
    fig.update_layout(title_x=0, title_xref="paper", title_y=0.985, title_yanchor="top")
    fig.update_xaxes(gridcolor=C["grid"], linecolor=C["axis"], zeroline=False)
    fig.update_yaxes(gridcolor=C["grid"], linecolor=C["axis"], zerolinecolor=C["axis"])
    return fig


def rupees(p):  # charts only: float rupees for plotting; all maths stays in paise
    return int(p) / 100.0


def bridge_chart(currency="INR"):
    b = result.bridge[result.bridge["currency"] == currency]
    measures = ["absolute" if c == "START" else "total" if c == "END" else "relative" for c in b["category"]]
    vals = [rupees(v) for v in b["amount_paise"]]
    vals[-1] = 0 if measures[-1] == "total" else vals[-1]
    # Zoom the axis to the range the bridge actually moves through, otherwise
    # ₹-thousands of differences are invisible next to a ₹-lakhs total.
    running, levels = 0, []
    for m, v in zip(measures, b["amount_paise"].astype(int)):
        running = int(v) if m != "relative" else running + int(v)
        levels.append(running)
    lo, hi = min(levels), max(levels)
    span = max(hi - lo, 100)
    yrange = [rupees(lo - span * 0.9), rupees(hi + span * 0.35)]
    def _wrap(text):  # two-line tick labels so neighbours never collide
        head = text.split(" (")[0]
        words = head.split(" ")
        cut = max(1, len(words) // 2)
        return " ".join(words[:cut]) + "<br>" + " ".join(words[cut:]) if len(words) > 1 else head
    labels = [_wrap(s) for s in b["step"]]
    fig = go.Figure(go.Waterfall(
        x=labels, y=vals, measure=measures, cliponaxis=False,
        text=[format_inr(v) for v in b["amount_paise"]], textposition="outside",
        increasing=dict(marker=dict(color=C["pos"])), decreasing=dict(marker=dict(color=C["neg"])),
        totals=dict(marker=dict(color=C["total"])), connector=dict(line=dict(color=C["axis"], width=1)),
        hovertemplate="%{x}<br>%{text}<extra></extra>",
    ))
    _layout(fig, height=440, title=dict(text="Bridge: platform net → bank net  ·  axis zoomed, does not start at ₹0",
                                         font=dict(size=14, color=C["ink"])), showlegend=False)
    fig.update_yaxes(tickprefix="₹", separatethousands=True, range=yrange)
    fig.update_xaxes(tickangle=0)
    return fig


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_over, tab_res, tab_an, tab_inv, tab_rep, tab_data = st.tabs(
    ["Overview", "Reconciliation results", "Analytics", "Investigation", "Reports", "Data & validation"]
)

with tab_over:
    st.plotly_chart(bridge_chart(), use_container_width=True)
    st.markdown(
        '<div class="note">Every rupee of difference between the platform ledger and the bank is attributed to a '
        "category. The engine refuses to produce a report if the bridge does not tie out exactly (in paise).</div>",
        unsafe_allow_html=True,
    )
    st.write("")
    left, right = st.columns(2)
    with left:
        st.markdown("##### Why the books don't balance")
        reasons = []
        bridge = result.bridge[(result.bridge["currency"] == "INR") & ~result.bridge["category"].isin(["START", "END"])]
        for _, row in bridge.iterrows():
            cat = row["category"]
            cnt = int(((R["category"] == cat) & (R["currency"] == "INR")).sum())
            reasons.append(f"- **{row['step']}** — {format_inr(row['amount_paise'])} across {cnt} record(s)")
        st.markdown("\n".join(reasons) if reasons else "No differences — the books balance.")
        if S["duplicates_excluded_paise"]:
            st.markdown(f"- **Duplicates** — {format_inr(S['duplicates_excluded_paise'])} posted twice by the bank was "
                        "excluded so it is not double counted.")
    with right:
        st.markdown("##### Exception summary")
        exc = result.exceptions
        if exc.empty:
            st.success("No exceptions.")
        else:
            g = exc.groupby(["category_label", "severity"]).size().reset_index(name="records")
            g["severity"] = g["severity"].map(SEVERITY_ICON)
            g.columns = ["Category", "Severity", "Records"]
            st.dataframe(g, hide_index=True, use_container_width=True)

with tab_res:
    sections = [
        ("Matched", [MATCHED, MATCHED_ROUNDING]),
        ("Unmatched", [AMOUNT_MISMATCH, MISSING_SETTLEMENT, UNMATCHED_BANK, CURRENCY_MISMATCH, TYPE_MISMATCH]),
        ("Pending settlements", [PENDING_AT_CUTOFF]),
        ("Late settlements", [LATE_SETTLEMENT]),
        ("Duplicates", [DUPLICATE_BANK, DUPLICATE_PLATFORM]),
        ("Orphan refunds", [ORPHAN_REFUND]),
        ("Rounding differences", [MATCHED_ROUNDING, AGGREGATE_ROUNDING]),
        ("Other (invalid / out of period)", [INVALID_RECORD, OUT_OF_PERIOD]),
    ]
    sub = st.tabs([f"{name} ({len(result.by_category(*cats))})" for name, cats in sections])
    for t, (name, cats) in zip(sub, sections):
        with t:
            df = result.by_category(*cats)
            if name == "Pending settlements" and not S["subsequent_evidence_loaded"]:
                st.info("Reconciled as of cutoff. Turn on **Include post-cutoff settlement evidence** in the sidebar "
                        "to check whether these settled in December.")
            if name == "Late settlements" and not S["subsequent_evidence_loaded"]:
                st.info("Post-cutoff evidence is not loaded, so late settlements currently appear as **Pending**.")
            if name == "Rounding differences":
                rr = result.rounding[result.rounding["currency"] == "INR"].iloc[0]
                c1, c2, c3 = st.columns(3)
                c1.metric("Records within tolerance", int(rr["records"]))
                c2.metric("Largest individual difference", format_inr(int(rr["max_abs_individual_paise"])),
                          help=f"Individual tolerance ±{format_inr(int(rr['individual_tolerance_paise']))}")
                c3.metric("Cumulative difference", format_inr(int(rr["aggregate_variance_paise"])),
                          delta="Breach" if rr["breach"] else "Within tolerance",
                          delta_color="inverse" if rr["breach"] else "normal",
                          help=f"Aggregate tolerance ±{format_inr(int(rr['aggregate_tolerance_paise']))}")
            if df.empty:
                st.caption("No records in this category.")
            else:
                st.dataframe(to_display_frame(df), hide_index=True, use_container_width=True,
                             column_config={"Explanation": st.column_config.TextColumn(width="large")})

with tab_an:
    c1, c2 = st.columns(2)
    with c1:
        counts = R.groupby("category").size().reset_index(name="n")
        counts["label"] = counts["category"].map(lambda c: CATEGORY_META[c]["label"])
        counts["group"] = counts["category"].map(lambda c: CATEGORY_META[c]["group"])
        counts = counts[counts["group"] != "Aggregate"].sort_values("n")
        fig = go.Figure()
        for grp, color in GROUP_COLORS.items():
            d = counts[counts["group"] == grp]
            if not d.empty:
                fig.add_bar(y=d["label"], x=d["n"], orientation="h", name=grp, marker_color=color,
                            text=d["n"], textposition="outside",
                            hovertemplate="%{y}: %{x} record(s)<extra>" + grp + "</extra>")
        _layout(fig, title=dict(text="Reconciliation status (records)", font=dict(size=14, color=C["ink"])),
                bargap=0.45)
        fig.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        exc = result.exceptions
        ec = exc.groupby("category_label").size().reset_index(name="n").sort_values("n")
        fig = go.Figure(go.Bar(y=ec["category_label"], x=ec["n"], orientation="h", marker_color=C["s1"],
                               text=ec["n"], textposition="outside",
                               hovertemplate="%{y}: %{x}<extra></extra>"))
        _layout(fig, title=dict(text="Exceptions by category", font=dict(size=14, color=C["ink"])),
                showlegend=False, bargap=0.55)
        fig.update_xaxes(dtick=1)
        st.plotly_chart(fig, use_container_width=True)

    # Platform vs bank by day (signed, deduplicated, in-period)
    pv = result.platform_validation.valid
    bv = result.bank_validation.valid
    dup_ids = set(R.loc[R["category"] == DUPLICATE_BANK, "bank_record_id"])
    if not pv.empty and not bv.empty:
        p = pv[(pv["txn_date"] >= result.config.period_start) & (pv["txn_date"] <= result.config.cutoff_date)].copy()
        b = bv[(bv["settle_date"] >= result.config.period_start) & (bv["settle_date"] <= result.config.cutoff_date)
               & ~bv["bank_record_id"].isin(dup_ids)].copy()
        p["signed"] = p.apply(lambda r: -r["amount_paise"] if r["transaction_type"] == "REFUND" else r["amount_paise"], axis=1)
        b["signed"] = b.apply(lambda r: -r["amount_paise"] if r["transaction_type"] == "REFUND" else r["amount_paise"], axis=1)
        pd_ = p.groupby("txn_date")["signed"].sum()
        bd_ = b.groupby("settle_date")["signed"].sum()
        idx = pd.date_range(result.config.period_start, result.config.cutoff_date).date
        pd_ = pd_.reindex(idx, fill_value=0).cumsum()
        bd_ = bd_.reindex(idx, fill_value=0).cumsum()
        fig = go.Figure()
        fig.add_scatter(x=list(idx), y=[rupees(v) for v in pd_], name="Platform (by transaction date)",
                        mode="lines", line=dict(color=C["s1"], width=2),
                        hovertemplate="%{x|%d %b}<br>Platform cumulative ₹%{y:,.2f}<extra></extra>")
        fig.add_scatter(x=list(idx), y=[rupees(v) for v in bd_], name="Bank (by settlement date)",
                        mode="lines", line=dict(color=C["s2"], width=2),
                        hovertemplate="%{x|%d %b}<br>Bank cumulative ₹%{y:,.2f}<extra></extra>")
        _layout(fig, height=380, hovermode="x unified",
                title=dict(text="Platform vs bank — cumulative net amount", font=dict(size=14, color=C["ink"])))
        fig.update_yaxes(tickprefix="₹", separatethousands=True)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("The bank line lags the platform line by the T+1/T+2 settlement window; the gap at month-end "
                   "is the total variance explained in the bridge.")

    # Aggregate rounding analysis
    rnd = result.by_category(MATCHED_ROUNDING).sort_values("transaction_id")
    if not rnd.empty:
        cum = rnd["variance_paise"].astype(int).cumsum().tolist()
        tol = result.config.aggregate_tolerance_paise
        fig = go.Figure()
        fig.add_bar(x=rnd["transaction_id"], y=[rupees(v) for v in rnd["variance_paise"]], name="Individual difference",
                    marker_color=C["s1"], width=0.45, hovertemplate="%{x}: ₹%{y:.2f}<extra>individual</extra>")
        fig.add_scatter(x=rnd["transaction_id"], y=[rupees(v) for v in cum], name="Cumulative difference",
                        mode="lines+markers", line=dict(color=C["s2"], width=2), marker=dict(size=8),
                        hovertemplate="%{x}: cumulative ₹%{y:.2f}<extra></extra>")
        for sgn in (1, -1):
            fig.add_hline(y=sgn * rupees(tol), line=dict(color=C["critical"], width=1, dash="dash"),
                          annotation_text=f"Aggregate tolerance {'+' if sgn > 0 else '−'}₹{rupees(tol):.2f}",
                          annotation_font_color=C["ink2"], annotation_position="top left" if sgn > 0 else "bottom left")
        _layout(fig, height=380, title=dict(text="Aggregate rounding variance", font=dict(size=14, color=C["ink"])))
        fig.update_yaxes(tickprefix="₹", tickformat=".2f")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Each record is within the individual tolerance, but they all fall the same way. The cumulative "
                   "line crosses the aggregate tolerance — a systematic rounding/truncation mismatch, which at "
                   "production volume becomes material.")

with tab_inv:
    f1, f2, f3, f4 = st.columns([2, 2, 1.3, 1.3])
    q = f1.text_input("Search", placeholder="Transaction ID, bank record, reference, original txn…")
    cats = f2.multiselect("Category", sorted(R["category_label"].unique()))
    sev = f3.multiselect("Severity", ["High", "Medium", "Low", "Info", "None"])
    only_exc = f4.toggle("Exceptions only", value=False)
    df = R.copy()
    if q:
        ql = q.strip().lower()
        mask = pd.Series(False, index=df.index)
        for col in ["transaction_id", "bank_record_id", "reference_id", "original_transaction_id", "explanation"]:
            mask |= df[col].astype(str).str.lower().str.contains(ql, regex=False)
        df = df[mask]
    if cats:
        df = df[df["category_label"].isin(cats)]
    if sev:
        df = df[df["severity"].isin(sev)]
    if only_exc:
        df = df[df["is_exception"]]
    st.caption(f"{len(df)} of {len(R)} records")
    disp = to_display_frame(df)
    disp["Severity"] = disp["Severity"].map(SEVERITY_ICON)
    st.dataframe(disp, hide_index=True, use_container_width=True, height=420,
                 column_config={"Explanation": st.column_config.TextColumn(width="large")})

    st.markdown("##### Record detail")
    ids = [f"{r.transaction_id} · {r.category_label}" + (f" · {r.bank_record_id}" if r.bank_record_id else "")
           for r in df.itertuples()]
    if ids:
        pick = st.selectbox("Select a record", range(len(ids)), format_func=lambda i: ids[i])
        rec = df.iloc[pick]
        d1, d2, d3 = st.columns(3)
        d1.markdown(f"**Category:** {rec['category_label']}  \n**Severity:** {SEVERITY_ICON[rec['severity']]}  \n"
                    f"**Type:** {rec['transaction_type'] or '—'} · **Currency:** {rec['currency'] or '—'}")
        d2.markdown(f"**Transaction:** `{rec['transaction_id'] or '—'}`  \n**Original txn:** `{rec['original_transaction_id'] or '—'}`  \n"
                    f"**Reference:** `{rec['reference_id'] or '—'}`")
        d3.markdown(f"**Bank record:** `{rec['bank_record_id'] or '—'}`  \n**Transaction date:** {rec['transaction_date'] or '—'}  \n"
                    f"**Settlement date:** {rec['settlement_date'] or '—'}")
        a1, a2, a3 = st.columns(3)
        na = lambda v: None if pd.isna(v) else int(v)  # noqa: E731
        a1.metric("Platform amount", format_inr(na(rec["platform_amount_paise"])))
        a2.metric("Bank amount", format_inr(na(rec["bank_amount_paise"])))
        a3.metric("Variance", format_inr(na(rec["variance_paise"])))
        st.info(rec["explanation"])

with tab_rep:
    st.markdown("Amounts in exports are exact two-decimal values derived from integer paise.")
    r1, r2 = st.columns(2)
    stamp = f"{S['cutoff_date']:%Y%m}"
    r1.download_button("⬇ Matched transactions", to_csv_bytes(to_export_frame(result.matched)),
                       f"matched_{stamp}.csv", "text/csv", use_container_width=True)
    r2.download_button("⬇ Unmatched transactions", to_csv_bytes(to_export_frame(result.unmatched)),
                       f"unmatched_{stamp}.csv", "text/csv", use_container_width=True)
    r1.download_button("⬇ Exceptions", to_csv_bytes(to_export_frame(result.exceptions)),
                       f"exceptions_{stamp}.csv", "text/csv", use_container_width=True)
    r2.download_button("⬇ Complete reconciliation report", full_report_csv(result),
                       f"reconciliation_report_{stamp}.csv", "text/csv", use_container_width=True, type="primary")
    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Summary")
        st.dataframe(summary_frame(result), hide_index=True, use_container_width=True, height=420)
    with c2:
        st.markdown("##### Bridge")
        st.dataframe(bridge_export(result), hide_index=True, use_container_width=True)

with tab_data:
    d1, d2 = st.columns(2)
    with d1:
        st.markdown(f"##### Platform transactions ({len(platform_df)})")
        st.dataframe(platform_df, hide_index=True, use_container_width=True, height=280)
    with d2:
        st.markdown(f"##### Bank settlements ({len(bank_df)})")
        st.dataframe(bank_df, hide_index=True, use_container_width=True, height=280)
    if december_df is not None:
        st.markdown(f"##### Post-cutoff bank evidence ({len(december_df)})")
        st.dataframe(december_df, hide_index=True, use_container_width=True)
    rej = pd.concat([result.platform_validation.rejected.assign(file="platform"),
                     result.bank_validation.rejected.assign(file="bank")], ignore_index=True)
    st.markdown("##### Validation")
    if rej.empty:
        st.success("All rows passed validation (required columns, positive amounts with ≤2 decimals, "
                   "valid dates, PAYMENT/REFUND types, 3-letter currency).")
    else:
        st.error(f"{len(rej)} row(s) failed validation and are reported as INVALID_RECORD exceptions.")
        st.dataframe(rej[["file", "source_row", "transaction_id", "rejection_reason"]], hide_index=True,
                     use_container_width=True)
    if source.startswith("Built-in"):
        st.markdown("##### Planted anomalies (sample data)")
        st.dataframe(sample["manifest"], hide_index=True, use_container_width=True)
    dd = DOCS / "data_dictionary.md"
    if dd.exists():
        with st.expander("Data dictionary"):
            st.markdown(dd.read_text(encoding="utf-8"))
