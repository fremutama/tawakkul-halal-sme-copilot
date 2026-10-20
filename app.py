import os
import streamlit as st
from agent import (screen_text, match_financing, analyze_cashflow, halal_audit, explain, verify_log,
                   audit_report_md, BASE, PILLARS)
from test_agent import BAD, GOOD

st.set_page_config(page_title="TAWAKKUL", page_icon="🌿", layout="wide")

# Optional login: set APP_PASSWORD in the environment (or Streamlit secrets) to require a password.
_pw = os.getenv("APP_PASSWORD")
if _pw and not st.session_state.get("authed"):
    st.title("TAWAKKUL")
    entered = st.text_input("Password", type="password")
    if entered and entered == _pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.error("Wrong password.")
    st.stop()

ICON = {"FAIL": "❌", "REVIEW": "⚠️", "NO RED FLAGS": "✅"}

with st.sidebar:
    st.header("TAWAKKUL")
    st.write("Trust in Allah, and a copilot you can trust: it **never moves money**. "
             "Rules decide every verdict. AI only explains.")
    lang_label = st.radio("Explanation language", ["English", "Bahasa Indonesia"])
    lang = "id" if lang_label.startswith("Bahasa") else "en"
    st.caption("Screening understands English and Bahasa Indonesia terms (for example bunga bank, judi, tanpa bunga bank).")
    st.divider()
    if st.button("Check audit-log integrity"):
        v = verify_log()
        st.success(f"Log intact: {v['entries']} entries, hash chain valid.") if v["ok"] else \
            st.error(f"Log tampered: chain breaks at entry {v['broken_at']}.")
    st.caption("Screening guidance only. Not a fatwa. Confirm with a qualified Shariah scholar.")

st.title("TAWAKKUL")
st.caption("Halal SME Finance Copilot: audit, screen, finance and cash-flow advice for small businesses.")
t0, t1, t2, t3 = st.tabs(["🌿 Halal audit", "🔍 Screen a contract", "🏦 Find halal financing", "📊 Cash flow"])


def show_remedies(remedies):
    for r in remedies:
        st.markdown(f"**{r['issue']}** ({r['term']}). Halal alternatives:")
        for a in r["alternatives"]:
            st.markdown(f"- {a}")
        st.markdown("Steps: " + "; ".join(r["steps"]))


def load_profile(profile, need="equipment"):
    for k in PILLARS:
        st.session_state["p_" + k] = profile.get(k, "")
    st.session_state["aud_need"] = need


# ------------------------------------------------------------------ audit
with t0:
    st.write("Describe each part of the business, or load an example. Leave blank what does not apply.")
    b1, b2, _ = st.columns([1, 1, 3])
    b1.button("Load a messy business", on_click=load_profile, args=(BAD,))
    b2.button("Load the fixed version", on_click=load_profile, args=(GOOD, ""))
    profile = {k: st.text_area(label, key="p_" + k, height=70) for k, label in PILLARS.items()}
    need = st.selectbox("Funding need (optional)", ["", "equipment", "inventory", "working_capital", "expansion",
                                                    "custom_build", "agri"], key="aud_need")
    amount = st.number_input("Amount", 0, 10_000_000, 20000, key="aud_amt")
    if st.button("Run audit", type="primary"):
        r = halal_audit(profile, need or None, amount)
        if r["score"] is None:
            st.info("Fill in at least one area.")
        else:
            prev = st.session_state.get("last_score")
            st.session_state["last_score"] = r["score"]
            c1, c2 = st.columns([1, 3])
            c1.metric("Screening score", f"{r['score']} / 100", None if prev is None else r["score"] - prev)
            c2.progress(r["score"] / 100)
            c2.caption(r["score_note"])
            for p in r["pillars"]:
                with st.expander(f"{ICON[p['verdict']]} {p['pillar']}: {p['verdict']}"):
                    if p["remedies"]:
                        show_remedies(p["remedies"])
                    else:
                        st.write("No red flags found in what you described.")
            st.subheader("Action plan")
            for s in r["action_plan"]:
                st.markdown(f"**{s['priority']}. {s['pillar']}** ({s['urgency']}): {s['first_step']}")
            for o in r["halal_financing_options"]:
                st.markdown(f"Financing option: **{o['structure']}**. {o['conditions']}")
            st.download_button("Download report (Markdown)", audit_report_md(r), "tawakkul_audit.md")
            st.caption(r["disclaimer"])

# ------------------------------------------------------------------ screener
with t1:
    EXAMPLES = ["Bank loan at 9% APR with compound interest", "Futures contract, price to be determined later",
                "Pinjaman dengan bunga bank 10% per tahun", "Interest-free Murabaha for a delivery van"]
    cols = st.columns(len(EXAMPLES))
    for c, ex in zip(cols, EXAMPLES):
        c.button(ex, on_click=lambda e=ex: st.session_state.update(screen_in=e), key="ex_" + ex)
    text = st.text_area("Paste a business activity, contract term or loan offer (English or Bahasa Indonesia)", key="screen_in")
    if st.button("Screen", type="primary") and text:
        r = screen_text(text)
        st.subheader(f"{ICON[r['verdict']]} {r['verdict']}")
        st.write(explain(r, lang))
        show_remedies(r["remedies"])
        if r["verdict"] == "NO RED FLAGS":
            st.caption("No red flags means no known keyword was found. It does not confirm the item is halal.")

# ------------------------------------------------------------------ financing
with t2:
    need2 = st.selectbox("What do you need funding for?", ["equipment", "inventory", "working_capital", "expansion",
                                                           "custom_build", "agri"])
    amount2 = st.number_input("Amount", 0, 10_000_000, 20000)
    partner = st.checkbox("Open to a profit-sharing partner")
    if st.button("Match", type="primary"):
        r = match_financing(need2, amount2, partner)
        for s in r["recommended"]:
            st.markdown(f"**{s['structure']}** ({s['ref']})  \n{s['conditions']} {s['note']}")
        st.warning(r["rejected"])
        st.caption(r["disclaimer"])

# ------------------------------------------------------------------ cash flow
with t3:
    opening = st.number_input("Opening balance", 0.0, 10_000_000.0, 6000.0)
    f = st.file_uploader("Transactions CSV (date, description, amount)", type="csv")
    sample = BASE / "data" / "sme_transactions.csv"
    st.download_button("Download the sample CSV", sample.read_bytes(), "sme_transactions.csv")
    if not f:
        st.caption("No file uploaded: the built-in sample (a catering business, synthetic data) will be used.")
    if st.button("Analyse", type="primary"):
        try:
            r = analyze_cashflow(f.getvalue() if f else sample, opening)
        except ValueError as e:
            st.error(str(e))
            st.stop()
        fa = r["analysis"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Income", f"{fa['total_income']:,.2f}"); c2.metric("Expenses", f"{fa['total_expenses']:,.2f}")
        c3.metric("Net profit", f"{fa['net_profit']:,.2f}"); c4.metric("Margin %", fa["profit_margin_pct"])
        d1, d2, d3 = st.columns(3)
        d1.metric("Closing balance", f"{r['closing_balance']:,.2f}")
        d2.metric("Runway (months)", "n/a" if r["runway_months"] is None else r["runway_months"])
        d3.metric("To purify (give to charity)", f"{r['purification_due']:,.2f}")
        st.write(f"Trend: **{fa['trend']}**.")
        for al in r["alerts"]:
            st.warning(al)
        st.subheader("Net cash flow by month")
        st.bar_chart({m["month"]: m["net"] for m in fa["monthly"]})
        st.subheader("Expenses by category")
        st.bar_chart({b["category"]: b["amount"] for b in fa["expense_breakdown"]})
        st.subheader("Flagged transactions and halal alternatives")
        st.dataframe(r["flagged_transactions"])
        if r["financing_suggestion"]:
            st.subheader("Halal financing to cover a cash gap")
            for s in r["financing_suggestion"]:
                st.markdown(f"**{s['structure']}** ({s['ref']}). {s['conditions']} {s['note']}")
        st.caption(r["disclaimer"])
