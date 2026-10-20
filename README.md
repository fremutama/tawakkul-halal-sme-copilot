# TAWAKKUL: Halal SME Finance Copilot

*FinTechathon 2026, International Track, Topic E: SME Finance Copilot.*

TAWAKKUL (trust in Allah) is an AI-assisted, **read-only** advisor that helps small businesses stay clear of riba (interest), maysir (gambling), gharar (excessive uncertainty) and prohibited sectors. It never moves money. Rules decide every verdict; AI only explains them.

**Team:** Frem Utama Shakti (frem.shakti@studenti.unitus.it), Fyolla Rezka Putri (BSW01085673@student.uniten.edu.my)
**Repository:** [(https://github.com/fremutama/tawakkul-halal-sme-copilot)]

## What it does
| Feature | What you get |
|---|---|
| Halal audit | Six business areas screened, a score out of 100, an action plan (worst first), downloadable report |
| Contract screener | FAIL / REVIEW / NO RED FLAGS for any text, in English or Bahasa Indonesia, with halal alternatives and steps |
| Financing matcher | Seven halal structures ranked by need, amount and partner availability |
| Cash flow and analysis | Runway, purification amount, income and expense analysis, alerts, charts |

Try the built-in examples: *Load a messy business* scores 17 / 100, *Load the fixed version* scores 100 / 100.

## Run it
Requires Python 3.10 or newer.

    pip install -r requirements.txt
    pytest -q                # 31 automated tests
    python demo.py           # sandbox run, writes evidence/sandbox_run.json
    streamlit run app.py     # web interface at http://localhost:8501

Optional environment variables:
- `ANTHROPIC_API_KEY`: Claude-written explanations (without it the app prints the rule text)
- `CLAUDE_MODEL`: model name for explanations (default `claude-sonnet-5-5`)
- `APP_PASSWORD`: require a password before the web app loads

## Deploy
Push the repository to GitHub, then create an app on [Streamlit Community Cloud](https://share.streamlit.io) pointing at `app.py`. Add `ANTHROPIC_API_KEY` and `APP_PASSWORD` as secrets if wanted. The platform provides HTTPS. Audit logs on hosted platforms are not persistent.

## Repository layout
- `agent.py`: tools (audit, screening, matching, cash flow, analysis, log verification)
- `rules.json`: rule set, halal alternatives, corrective steps, financing structures
- `app.py`: Streamlit interface
- `demo.py`: sandbox run that writes the execution evidence
- `test_agent.py`, `conftest.py`: tests (the tests log to a temporary folder)
- `data/sme_transactions.csv`: synthetic transactions
- `evidence/`: `sandbox_run.json` and `audit_log.jsonl` (hash-chained)
- `docs/`: technical documentation, security self-assessment, final presentation

## Security design
- Read-only: no payment library, no bank integration, no credentials.
- Verdicts, scores and alternatives come from `rules.json`; the model cannot change them.
- The model sees only structured findings, never the raw user text.
- Hash-chained audit log with hashed inputs; integrity check in the app sidebar.
- Uploads validated (1 MB, 20,000 rows, schema, dates, amounts) and read from memory.
- Pinned dependencies, optional password, a disclaimer on every output: screening guidance, not a fatwa.

See `docs/` for the full Security Self-Assessment (permission tiers and known-risk list).

## Topic E coverage
- **Financing-option matching:** seven halal structures ranked by need, amount and partner availability. Low cash and a failing financing area also trigger suggestions.
- **Cash-flow management with alerts:** monthly net, runway, purification, interest-charge, heavy-cost, net-loss and income-concentration alerts.
- **Business financial analysis:** income, expenses, net profit, margin, expense breakdown, monthly series and trend, plus the halal audit.

## Limits
Screening is keyword-based (English and Bahasa Indonesia), so it can miss unusual wording. NO RED FLAGS does not confirm that something is halal. Have a qualified Shariah scholar review the rules before real use.
