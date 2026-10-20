import pytest
from agent import (screen_text, match_financing, analyze_cashflow, halal_audit, load_transactions,
                   verify_log, audit_report_md, BASE)
import agent

DATA = BASE / "data" / "sme_transactions.csv"
BAD = {"products": "Catering with wine pairing", "financing": "Bank loan at 8% APR", "income": "Raffle ticket sales",
       "contracts": "Supply contract with price to be determined", "insurance": "Conventional insurance",
       "savings": "Savings account earning interest"}
GOOD = {"products": "Halal catering", "financing": "Murabaha for a van, fixed mark-up", "income": "Catering orders",
        "contracts": "Fixed-price supply contract with delivery date", "insurance": "Takaful cover",
        "savings": "Profit-sharing Mudarabah account"}


# --- screening
def test_riba_fail(): assert screen_text("Loan at 8% APR with interest")["verdict"] == "FAIL"
def test_interest_free_ok(): assert screen_text("interest-free loan")["verdict"] == "NO RED FLAGS"
def test_no_interest_ok(): assert screen_text("no interest charged")["verdict"] == "NO RED FLAGS"
def test_maysir_fail(): assert screen_text("sell lottery tickets")["verdict"] == "FAIL"
def test_gharar_review(): assert screen_text("futures contract")["verdict"] == "REVIEW"
def test_sector_fail(): assert screen_text("open a wine shop")["verdict"] == "FAIL"
def test_disputed_sector_review(): assert screen_text("sell tobacco")["verdict"] == "REVIEW"

def test_bahasa_indonesia_screening():
    assert screen_text("Pinjaman dengan bunga bank 10%")["verdict"] == "FAIL"
    assert screen_text("Jual tiket judi online")["verdict"] == "FAIL"
    assert screen_text("Pembiayaan tanpa bunga bank")["verdict"] == "NO RED FLAGS"

def test_huge_input_is_capped():
    assert screen_text("halal catering " * 100_000)["verdict"] == "NO RED FLAGS"

def test_remedies_for_riba():
    r = screen_text("Bank loan at 8% APR")
    assert any("Murabaha" in a for a in r["remedies"][0]["alternatives"])


# --- financing
def test_equipment_murabaha_first(): assert "Murabaha" in match_financing("equipment", 20000)["recommended"][0]["structure"]
def test_qard_hasan_cap(): assert all("Qard" not in r["structure"] for r in match_financing("working_capital", 50000)["recommended"])


# --- audit
def test_audit_bad_has_plan():
    r = halal_audit(BAD, need="equipment", amount=20000)
    assert r["verdict"] == "FAIL" and r["score"] == 17 and r["action_plan"][0]["urgency"] == "Fix now"
    assert r["halal_financing_options"]

def test_audit_good_scores_100():
    r = halal_audit(GOOD)
    assert r["score"] == 100 and r["verdict"] == "NO RED FLAGS"

def test_audit_savings_gets_profit_sharing_alternative():
    r = halal_audit({"savings": "Savings account earning interest"})
    assert any("Mudarabah" in a for a in r["pillars"][0]["remedies"][0]["alternatives"])

def test_audit_report_downloads_as_markdown():
    md = audit_report_md(halal_audit(BAD, need="equipment", amount=20000))
    assert "17 / 100" in md and "Action plan" in md


# --- cash flow and analysis
def test_cashflow_purification():
    assert round(analyze_cashflow(DATA, 6000)["purification_due"], 2) == 312.4

def test_cashflow_flags_have_alternatives():
    assert all(x["alternatives"] for x in analyze_cashflow(DATA, 6000)["flagged_transactions"])

def test_cashflow_accepts_uploaded_bytes():
    r = analyze_cashflow(DATA.read_bytes(), 6000)
    assert r["closing_balance"] == 6027.4 and r["runway_months"] == 21.1

def test_financial_analysis_totals():
    fa = analyze_cashflow(DATA, 6000)["analysis"]
    assert fa["total_income"] == 13612.4 and fa["total_expenses"] == 13585.0 and fa["net_profit"] == 27.4
    assert fa["expense_breakdown"][0]["category"] == "Wages" and fa["trend"] == "improving"

def test_analysis_alerts():
    r = analyze_cashflow(DATA, 6000)
    assert any("Wages" in a for a in r["alerts"]) and any("Net loss" in a for a in r["alerts"])

def test_low_cash_links_to_financing():
    r = analyze_cashflow(DATA, 0)
    assert any("Low cash runway" in a for a in r["alerts"]) and r["financing_suggestion"]


# --- upload validation
@pytest.mark.parametrize("bad,msg", [
    (b"date,description\n2026-01-01,x\n", "columns"),
    (b"date,description,amount\n2026-13-01,x,5\n", "YYYY-MM-DD"),
    (b"date,description,amount\n2026-01-01,x,abc\n", "not a number"),
    (b"date,description,amount\n2026-01-01,x,nan\n", "not a number"),
    (b"date,description,amount\n", "no transactions"),
    (b"\xff\xfe\x00bad", "UTF-8"),
])
def test_upload_validation_rejects_bad_files(bad, msg):
    with pytest.raises(ValueError, match=msg):
        load_transactions(bad)

def test_upload_size_limit():
    with pytest.raises(ValueError, match="too large"):
        load_transactions(b"x" * (agent.MAX_BYTES + 1))


# --- tamper-evident audit log
def test_audit_log_chain_is_valid_then_detects_tampering():
    screen_text("interest"); screen_text("halal catering"); match_financing("equipment", 1000)
    assert verify_log() == {"ok": True, "entries": 3, "broken_at": None}
    lines = agent.LOG.read_text().splitlines()
    lines[1] = lines[1].replace("NO RED FLAGS", "FAIL")
    agent.LOG.write_text("\n".join(lines) + "\n")
    assert verify_log()["ok"] is False and verify_log()["broken_at"] == 2

def test_audit_log_never_stores_raw_input():
    screen_text("my secret supplier Acme Ltd interest")
    assert "Acme" not in agent.LOG.read_text()
