"""TAWAKKUL: Halal SME Finance Copilot. Read-only advisor: it never moves money.
Verdicts come from auditable rules (rules.json). The LLM only explains them."""
import json, re, csv, io, os, math, hashlib, pathlib, collections
import datetime as dt

BASE = pathlib.Path(__file__).parent
RULES = json.loads((BASE / "rules.json").read_text(encoding="utf-8"))
LOG = BASE / "evidence" / "audit_log.jsonl"
GENESIS = "0" * 64
NEG = re.compile(r"\b(no|without|free of|zero|non|tanpa|bebas)[\s-]*$")
MAX_TEXT = 20_000          # characters screened per input
MAX_BYTES = 1_000_000      # uploaded CSV size limit
MAX_ROWS = 20_000          # uploaded CSV row limit


# ---------------------------------------------------------------- audit log
def _digest(rec):
    return hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()


def _last_hash():
    try:
        lines = LOG.read_text(encoding="utf-8").splitlines()
        return json.loads(lines[-1])["hash"] if lines else GENESIS
    except (OSError, ValueError, KeyError):
        return GENESIS


def _log(tool, inp, out):
    """One hash-chained line per tool call. Raw input is never stored."""
    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "tool": tool,
           "input_sha256": hashlib.sha256(json.dumps(inp, sort_keys=True, default=str).encode()).hexdigest()[:16],
           "verdict": out.get("verdict"), "prev": _last_hash()}
    rec["hash"] = _digest(rec)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass  # logging must never break the advisor


def verify_log(path=None):
    """Check the hash chain. Editing, deleting or reordering any entry breaks it."""
    prev, n = GENESIS, 0
    try:
        lines = pathlib.Path(path or LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"ok": True, "entries": 0, "broken_at": None}
    for i, line in enumerate(lines, 1):
        try:
            rec = json.loads(line)
            h = rec.pop("hash")
            if rec.get("prev") != prev or _digest(rec) != h:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return {"ok": False, "entries": n, "broken_at": i}
        prev, n = h, n + 1
    return {"ok": True, "entries": n, "broken_at": None}


# ---------------------------------------------------------------- screening
def screen_text(text, log=True):
    """Check a business activity, contract or offer for riba, maysir, gharar, prohibited sectors."""
    t, findings = str(text or "")[:MAX_TEXT].lower(), []
    for key, cat in RULES["prohibitions"].items():
        for term in cat["terms"]:
            for m in re.finditer(r"\b" + re.escape(term) + r"s?\b", t):
                before, after = t[max(0, m.start() - 12):m.start()], t[m.end():m.end() + 6]
                if NEG.search(before) or after.startswith(("-free", " free", " bebas")):
                    continue  # e.g. "no interest", "interest-free", "tanpa bunga bank"
                findings.append({"category": key, "name": cat["name"], "term": term,
                                 "severity": cat["severity"], "why": cat["why"], "ref": cat["ref"]})
                break
            if findings and findings[-1]["category"] == key:
                break  # one finding per category
    sev = {f["severity"] for f in findings}
    verdict = "FAIL" if "fail" in sev else "REVIEW" if "warn" in sev else "NO RED FLAGS"
    out = {"verdict": verdict, "findings": findings, "remedies": [_remedy(f) for f in findings],
           "disclaimer": RULES["disclaimer"]}
    if log:
        _log("screen_text", text, out)
    return out


def _remedy(f):
    """Halal alternatives and corrective steps for one finding."""
    cat = RULES["remedies"]["by_category"][f["category"]]
    alt = RULES["remedies"]["by_term"].get(f["term"], {}).get("alternatives", cat["alternatives"])
    return {"issue": f["name"], "category": f["category"], "term": f["term"],
            "alternatives": alt, "steps": cat["steps"]}


# ---------------------------------------------------------------- financing
def match_financing(need, amount, partner_ok=False):
    """need: equipment | inventory | working_capital | expansion | custom_build | agri"""
    ranked = []
    for s in RULES["financing"]:
        score = s["fits"].get(need)
        if not score or amount > s.get("max_amount", float("inf")):
            continue
        note = ""
        if s["requires_partner"] and not partner_ok:
            score, note = score - 1, "Needs a partner who shares profit and loss."
        ranked.append({"structure": s["name"], "score": score, "conditions": s["conditions"],
                       "ref": s["ref"], "note": note})
    ranked.sort(key=lambda r: -r["score"])
    out = {"verdict": "OK", "recommended": ranked[:3],
           "rejected": "Conventional interest-based loan: fails the riba screen.",
           "disclaimer": RULES["disclaimer"]}
    _log("match_financing", {"need": need, "amount": amount, "partner_ok": partner_ok}, out)
    return out


# ---------------------------------------------------------------- cash flow
def load_transactions(source):
    """Validate and parse a transactions CSV (path or raw bytes). Raises ValueError with a clear message."""
    raw = bytes(source) if isinstance(source, (bytes, bytearray)) else pathlib.Path(source).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"File is too large (limit {MAX_BYTES // 1000} KB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("File must be UTF-8 text (CSV).")
    reader = csv.DictReader(io.StringIO(text))
    heads = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if not {"date", "description", "amount"} <= heads:
        raise ValueError("CSV needs the columns: date, description, amount.")
    rows = []
    for n, r in enumerate(reader, 2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items() if k}
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"Too many rows (limit {MAX_ROWS}).")
        try:
            dt.date.fromisoformat(r["date"])
        except ValueError:
            raise ValueError(f"Row {n}: date '{r['date']}' must look like YYYY-MM-DD.")
        try:
            amt = float(r["amount"])
            if not math.isfinite(amt):
                raise ValueError
        except ValueError:
            raise ValueError(f"Row {n}: amount '{r['amount']}' is not a number.")
        rows.append({"date": r["date"], "description": r["description"][:300], "amount": amt,
                     "category": r.get("category", "")})
    if not rows:
        raise ValueError("The file has no transactions.")
    return rows


def analyze_cashflow(csv_source, opening_balance):
    """CSV columns: date (YYYY-MM-DD), description, amount (+income, -expense). Accepts a path or bytes."""
    rows = load_transactions(csv_source)
    months, flags, impure = collections.defaultdict(float), [], 0.0
    for r in rows:
        amt = r["amount"]
        months[r["date"][:7]] += amt
        res = screen_text(r["description"], log=False)
        if res["verdict"] != "NO RED FLAGS":
            flags.append({"date": r["date"], "description": r["description"], "amount": amt,
                          "issues": [x["name"] for x in res["findings"]],
                          "alternatives": res["remedies"][0]["alternatives"][:2]})
            if amt > 0 and res["verdict"] == "FAIL":
                impure += amt
    balance = opening_balance + sum(months.values())
    losing = [-v for v in months.values() if v < 0]
    burn = sum(losing) / len(losing) if losing else 0
    runway = balance / burn if burn else None
    alerts = []
    if runway is not None and runway < 3:
        alerts.append(f"Low cash runway: {runway:.1f} months")
    if impure:
        alerts.append(f"Give {impure:.2f} of non-compliant income to charity, not for own benefit (purification).")
    for x in flags:
        if x["amount"] < 0:
            alerts.append(f"Non-compliant charge on {x['date']}: {x['description']}. Restructure to a halal contract.")
    fa = financial_analysis(rows)
    alerts += fa.pop("alerts")
    fin = []
    if runway is not None and runway < 6:  # link analysis to matching: cover about 3 months of losses
        fin = match_financing("working_capital", round(burn * 3))["recommended"]
    ident = str(csv_source) if not isinstance(csv_source, (bytes, bytearray)) else "upload"
    out = {"verdict": "REVIEW" if flags else "NO RED FLAGS", "monthly_net": dict(months),
           "closing_balance": round(balance, 2), "runway_months": None if runway is None else round(runway, 1),
           "flagged_transactions": flags, "purification_due": round(impure, 2), "alerts": alerts,
           "analysis": fa, "financing_suggestion": fin, "disclaimer": RULES["disclaimer"]}
    _log("analyze_cashflow", {"file": ident, "rows": len(rows), "opening": opening_balance}, out)
    return out


# ---------------------------------------------------------------- explanation
def explain(result, lang="en"):
    """Plain-language explanation. Uses Claude if ANTHROPIC_API_KEY is set, else rule text.
    Only structured findings are sent; the raw user text is not."""
    base = "\n".join(f"- {f['name']}: {f['why']} ({f['ref']})" for f in result.get("findings", [])) \
        or "No red flags found."
    base += "\n" + RULES["disclaimer"]
    if not os.getenv("ANTHROPIC_API_KEY"):
        return base
    try:
        import anthropic
        language = " Write the answer in Bahasa Indonesia." if lang == "id" else ""
        payload = {k: result.get(k) for k in ("verdict", "findings", "remedies", "disclaimer")}
        msg = anthropic.Anthropic().messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=400,
            system="Explain Shariah-screening results simply. Use ONLY the findings given. Never issue a fatwa. "
                   "End by advising confirmation with a qualified scholar." + language,
            messages=[{"role": "user", "content": json.dumps(payload)}])
        return msg.content[0].text
    except Exception:
        return base


# ---------------------------------------------------------------- audit
PILLARS = {"products": "Products and services", "financing": "Financing and loans",
           "income": "Income sources", "contracts": "Contracts with customers and suppliers",
           "insurance": "Insurance and risk cover", "savings": "Savings and investments"}


def halal_audit(profile, need=None, amount=0, partner_ok=False):
    """Whole-business check. profile maps pillar -> description text. Blank pillars are skipped.
    Returns a screening score (not a Shariah rating), per-pillar verdicts and a prioritised action plan."""
    pts = {"FAIL": 0, "REVIEW": 0.5, "NO RED FLAGS": 1}
    pillars = []
    for key, label in PILLARS.items():
        text = (profile.get(key) or "").strip()
        if text:
            r = screen_text(text, log=False)
            override = RULES["remedies"].get("by_pillar", {}).get(key, {})
            rem = [dict(x, alternatives=override.get(x["category"], x["alternatives"])) for x in r["remedies"]]
            pillars.append({"pillar": label, "verdict": r["verdict"], "findings": r["findings"], "remedies": rem})
    score = round(100 * sum(pts[p["verdict"]] for p in pillars) / len(pillars)) if pillars else None
    rank = {"FAIL": 0, "REVIEW": 1, "NO RED FLAGS": 2}
    pillars.sort(key=lambda p: rank[p["verdict"]])
    plan = []
    for p in (x for x in pillars if x["verdict"] != "NO RED FLAGS"):
        rem = p["remedies"][0]
        plan.append({"priority": len(plan) + 1, "pillar": p["pillar"],
                     "urgency": "Fix now" if p["verdict"] == "FAIL" else "Get a scholar's view",
                     "first_step": rem["steps"][0], "halal_alternatives": rem["alternatives"][:3]})
    fin = next((p for p in pillars if p["pillar"] == PILLARS["financing"]), None)
    options = match_financing(need, amount, partner_ok)["recommended"] if need and fin and fin["verdict"] != "NO RED FLAGS" else []
    plan.append({"priority": len(plan) + 1, "pillar": "All", "urgency": "Before acting",
                 "first_step": "Have a qualified Shariah scholar review this plan and your contracts", "halal_alternatives": []})
    worst = pillars[0]["verdict"] if pillars else "NO RED FLAGS"
    out = {"verdict": worst, "score": score, "score_note": "Screening score from keyword rules, not a Shariah rating.",
           "pillars": pillars, "action_plan": plan, "halal_financing_options": options,
           "disclaimer": RULES["disclaimer"]}
    _log("halal_audit", profile, out)
    return out


def audit_report_md(audit, title="TAWAKKUL halal audit"):
    """Markdown report of an audit result, for download."""
    L = [f"# {title}", "", f"**Screening score:** {audit['score']} / 100 ({audit['verdict']})", "",
         f"_{audit['score_note']}_", "", "## Areas"]
    for p in audit["pillars"]:
        L.append(f"- **{p['pillar']}:** {p['verdict']}")
        for r in p["remedies"]:
            L.append(f"  - {r['issue']} ({r['term']}). Halal alternatives: " + "; ".join(r["alternatives"]))
    L += ["", "## Action plan"]
    for s in audit["action_plan"]:
        L.append(f"{s['priority']}. **{s['pillar']}** ({s['urgency']}): {s['first_step']}")
    if audit["halal_financing_options"]:
        L += ["", "## Halal financing options"] + [f"- **{o['structure']}**: {o['conditions']}" for o in audit["halal_financing_options"]]
    L += ["", f"_{audit['disclaimer']}_"]
    return "\n".join(L)


# ---------------------------------------------------------------- financial analysis
CATS = [("interest", "Interest"), ("rent", "Rent"), ("wage", "Wages"), ("salary", "Wages"), ("staff", "Wages"),
        ("suppl", "Supplies"), ("ingredient", "Supplies"), ("stock", "Supplies"), ("inventory", "Supplies"),
        ("utilit", "Utilities"), ("electric", "Utilities"), ("marketing", "Marketing"), ("advert", "Marketing"),
        ("order", "Sales"), ("sales", "Sales"), ("revenue", "Sales")]


def _category(row):
    """Use the CSV category column if present, else group by keywords in the description."""
    c = (row.get("category") or "").strip()
    if c:
        return c
    d = row["description"].lower()
    return next((name for k, name in CATS if k in d), "Other")


def financial_analysis(rows):
    """Profit and loss, margin, expense breakdown, income concentration, monthly series and trend."""
    inc = exp = biggest = 0.0
    months = collections.defaultdict(lambda: {"income": 0.0, "expenses": 0.0})
    exp_cat, inc_cat = collections.defaultdict(float), collections.defaultdict(float)
    for r in rows:
        amt, cat, m = float(r["amount"]), _category(r), months[r["date"][:7]]
        if amt >= 0:
            inc += amt; m["income"] += amt; inc_cat[cat] += amt; biggest = max(biggest, amt)
        else:
            exp -= amt; m["expenses"] -= amt; exp_cat[cat] -= amt
    pct = lambda x, t: round(100 * x / t, 1) if t else 0.0
    monthly = [{"month": k, "income": round(v["income"], 2), "expenses": round(v["expenses"], 2),
                "net": round(v["income"] - v["expenses"], 2)} for k, v in sorted(months.items())]
    breakdown = [{"category": k, "amount": round(v, 2), "share_of_income_pct": pct(v, inc)}
                 for k, v in sorted(exp_cat.items(), key=lambda kv: -kv[1])]
    alerts = [f"{b['category']} costs are {b['share_of_income_pct']}% of income (guide: under 35%)."
              for b in breakdown if b["share_of_income_pct"] > 35 and b["category"] != "Interest"]
    losses = [m["month"] for m in monthly if m["net"] < 0]
    if losses:
        alerts.append("Net loss in: " + ", ".join(losses))
    conc = pct(biggest, inc)
    if conc > 50:
        alerts.append(f"Income concentration: one transaction is {conc}% of income.")
    trend = None
    if len(monthly) >= 2:
        d = monthly[-1]["net"] - monthly[-2]["net"]
        trend = "improving" if d > 0 else "declining" if d < 0 else "flat"
    return {"total_income": round(inc, 2), "total_expenses": round(exp, 2), "net_profit": round(inc - exp, 2),
            "profit_margin_pct": pct(inc - exp, inc), "monthly": monthly, "expense_breakdown": breakdown,
            "income_by_category": {k: round(v, 2) for k, v in inc_cat.items()},
            "largest_income_share_pct": conc, "trend": trend, "alerts": alerts}
