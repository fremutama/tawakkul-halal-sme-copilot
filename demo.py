"""Sandbox run: exercises every tool on synthetic data and writes evidence/sandbox_run.json.
No real accounts, customers or on-chain transactions are used."""
import json
import agent
from agent import screen_text, match_financing, analyze_cashflow, halal_audit, verify_log, BASE
from test_agent import BAD, GOOD

agent.LOG.unlink(missing_ok=True)  # start a fresh, verifiable audit log for this run
SAMPLES = ["Bank loan at 9% APR with compound interest", "Interest-free Murabaha for a delivery van",
           "Sell lottery tickets at our shop", "Futures contract with price to be determined later",
           "Halal catering for weddings"]
ID_SAMPLES = ["Pinjaman dengan bunga bank 10% per tahun", "Pembiayaan tanpa bunga bank untuk mesin"]

out = {
    "screening": {t: screen_text(t)["verdict"] for t in SAMPLES},
    "screening_bahasa_indonesia": {t: screen_text(t)["verdict"] for t in ID_SAMPLES},
    "financing_equipment_20k": match_financing("equipment", 20000)["recommended"][0]["structure"],
    "audit_before": halal_audit(BAD, need="equipment", amount=20000),
    "audit_after": halal_audit(GOOD),
    "cashflow": analyze_cashflow(BASE / "data" / "sme_transactions.csv", 6000),
}
out["audit_log_check"] = verify_log()
(BASE / "evidence").mkdir(exist_ok=True)
(BASE / "evidence" / "sandbox_run.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("screening:", out["screening"])
print("bahasa:", out["screening_bahasa_indonesia"])
print("audit score before/after:", out["audit_before"]["score"], "->", out["audit_after"]["score"])
print("cashflow: closing", out["cashflow"]["closing_balance"], "runway", out["cashflow"]["runway_months"],
      "purify", out["cashflow"]["purification_due"], "flagged", len(out["cashflow"]["flagged_transactions"]))
print("audit log:", out["audit_log_check"])
