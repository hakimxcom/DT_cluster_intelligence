"""Evidence-based findings generated from calculated results.

Each finding comes from a named decision rule with explicit thresholds, so a
reader can trace every sentence to the numbers behind it. Nothing here is
pre-written about which region performs better: the text is assembled from
whatever the data show, including "no industry met this rule"."""
from __future__ import annotations

from .acs import significantly_different

RULES = {
    "min_employment": 1000,       # end-year jobs in the metro for an industry to be discussed
    "distinctive_lq": 1.25,       # Detroit LQ at or above this...
    "others_below": 1.0,          # ...while both comparison metros are below this
    "shared_lq": 1.10,            # all three metros at or above this
    "top_n": 5,
}


def _fmt_pct(x):
    return f"{x * 100:+.1f}%"


def _names(items, title):
    return "; ".join(f"{title(c)} (LQ {lq:.2f})" for c, lq in items)


def generate(end_lq: dict, pair: dict, metros: list, title, context: dict) -> list[dict]:
    """``end_lq``: {metro: {code: (lq, emp)}} for the end year.
    ``pair``: {metro: {code: record with pct, rc, status}} plus "_totals".
    ``title``: callable code -> industry title."""
    ids = [m.id for m in metros]
    label = {m.id: m.label for m in metros}
    t = RULES
    out = []

    def eligible(mid, code):
        lq, emp = end_lq.get(mid, {}).get(code, (None, None))
        return lq is not None and emp is not None and emp >= t["min_employment"]

    codes = sorted(set().union(*[set(end_lq.get(m, {})) for m in ids]))

    # 1. Distinctive to Detroit
    if "detroit" in ids:
        others = [m for m in ids if m != "detroit"]
        dist = []
        for c in codes:
            if not eligible("detroit", c):
                continue
            lq_d = end_lq["detroit"][c][0]
            other_lqs = [end_lq.get(o, {}).get(c, (None, None))[0] for o in others]
            if lq_d >= t["distinctive_lq"] and all(x is not None and x < t["others_below"] for x in other_lqs):
                dist.append((c, lq_d))
        dist.sort(key=lambda x: -x[1])
        out.append({
            "id": "distinctive", "kind": "descriptive",
            "question": "What appears distinctive about Detroit's industrial structure?",
            "rule": f"Detroit LQ ≥ {t['distinctive_lq']} with at least {t['min_employment']:,} jobs, while Chicago and Cleveland both have LQ < {t['others_below']}.",
            "text": (f"{len(dist)} industries meet the rule. Highest: {_names(dist[:t['top_n']], title)}."
                     if dist else "No industry meets the rule in the selected end year."),
            "evidence": [{"industry": c, "lq": round(v, 3)} for c, v in dist[:t["top_n"]]],
        })

    # 2. Shared strengths
    shared = []
    for c in codes:
        if all(eligible(m, c) and end_lq[m][c][0] >= t["shared_lq"] for m in ids):
            shared.append((c, min(end_lq[m][c][0] for m in ids)))
    shared.sort(key=lambda x: -x[1])
    out.append({
        "id": "shared", "kind": "descriptive",
        "question": "Which strengths are shared across the three metros?",
        "rule": f"LQ ≥ {t['shared_lq']} in all three metros, each with at least {t['min_employment']:,} jobs.",
        "text": (f"{len(shared)} industries meet the rule: " + "; ".join(f"{title(c)} (lowest LQ {v:.2f})" for c, v in shared[:t['top_n']]) + "."
                 if shared else "No industry is specialized (by this rule) in all three metros."),
        "evidence": [{"industry": c, "min_lq": round(v, 3)} for c, v in shared[:t["top_n"]]],
    })

    # 3. Specialized and growing / 4. Specialized and declining
    for rid, question, cond, word in [
        ("specialized_growing", "Which industries combine specialization with positive growth?", lambda p: p > 0, "grew"),
        ("specialized_declining", "Where do employment trends suggest vulnerability?", lambda p: p < 0, "declined"),
    ]:
        parts, evidence = [], []
        for m in ids:
            hits = []
            for c in codes:
                rec = pair.get(m, {}).get(c)
                if not eligible(m, c) or end_lq[m][c][0] < 1 or not rec or rec.get("pct") is None:
                    continue
                if cond(rec["pct"]):
                    hits.append((c, rec["pct"], rec.get("rc")))
            hits.sort(key=lambda x: -abs(x[1]) if rid == "specialized_declining" else -x[1])
            parts.append(f"{label[m]}: {len(hits)}" + (" — " + "; ".join(f"{title(c)} {_fmt_pct(p)}" for c, p, _ in hits[:3]) if hits else ""))
            evidence += [{"metro": m, "industry": c, "pct": round(p, 4), "regional_effect": None if r is None else round(r)} for c, p, r in hits[:t["top_n"]]]
        out.append({
            "id": rid, "kind": "descriptive", "question": question,
            "rule": f"End-year LQ ≥ 1, at least {t['min_employment']:,} jobs, and employment {word} over the selected period.",
            "text": "Count of qualifying industries by metro. " + ". ".join(parts) + ".",
            "evidence": evidence,
        })

    # 5. Industry mix vs regional effect at the metro level
    totals = pair.get("_totals", {})
    lines, evidence = [], []
    for m in ids:
        tot = totals.get(m)
        if not tot or tot.get("im") is None:
            lines.append(f"{label[m]}: not computable")
            continue
        im, rc = tot["im"], tot["rc"]
        lines.append(f"{label[m]}: industry mix {im:+,.0f} jobs, regional effect {rc:+,.0f} jobs "
                     f"(sectors covering {tot['coverage'] * 100:.0f}% of base-year employment)")
        evidence.append({"metro": m, "industry_mix": round(im), "regional": round(rc), "coverage": round(tot["coverage"], 4)})
    out.append({
        "id": "mix_vs_regional", "kind": "descriptive",
        "question": "Does each metro's industry mix appear to favor or constrain its employment growth?",
        "rule": "Sum of sector-level shift-share components over sectors with complete data. A positive industry-mix sum means the metro's base-year mix was weighted toward nationally faster-growing sectors.",
        "text": ". ".join(lines) + ". The regional effect describes relative employment growth only; it does not identify causes.",
        "evidence": evidence,
    })

    # 6. Differences that merit investigation (hypotheses, not conclusions)
    hyp = []
    if "detroit" in ids:
        for c in codes:
            recs = {m: pair.get(m, {}).get(c) for m in ids}
            if not all(r and r.get("rc") is not None and eligible(m, c) for m, r in recs.items()):
                continue
            d = recs["detroit"]["rc"]
            others = [recs[m]["rc"] for m in ids if m != "detroit"]
            if d != 0 and all((o > 0) != (d > 0) for o in others):
                hyp.append((c, d))
        hyp.sort(key=lambda x: -abs(x[1]))
    out.append({
        "id": "investigate", "kind": "hypothesis",
        "question": "Which differences merit further investigation?",
        "rule": "Industries where Detroit's regional effect has the opposite sign from both Chicago's and Cleveland's.",
        "text": ("Candidates for further study (not explanations): " + "; ".join(f"{title(c)} (Detroit regional effect {v:+,.0f} jobs)" for c, v in hyp[:t['top_n']]) + "."
                 if hyp else "No industry has a Detroit regional effect opposite in sign to both comparison metros."),
        "evidence": [{"industry": c, "detroit_regional": round(v)} for c, v in hyp[:t["top_n"]]],
    })

    # 7. What context measures add
    notes = []
    gdp = context.get("gdp_growth", {})
    if gdp:
        notes.append("Real GDP growth over " + gdp["period"] + ": " + "; ".join(
            f"{label[m]} {_fmt_pct(v)}" if v is not None else f"{label[m]} not available" for m, v in gdp["values"].items()))
    est = context.get("estabs_per_1000", {})
    if est:
        notes.append(f"Private establishments per 1,000 private jobs (CBP {est['year']}): " + "; ".join(
            f"{label[m]} {v:.1f}" if v is not None else f"{label[m]} n/a" for m, v in est["values"].items()))
    acs = context.get("bachelors", {})
    if acs and all(v for v in acs["values"].values()):
        vals = acs["values"]
        pairs = []
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                sig = significantly_different(vals[a]["estimate"], vals[a]["moe"], vals[b]["estimate"], vals[b]["moe"])
                pairs.append(f"{label[a]} vs {label[b]}: {'statistically different' if sig else 'not statistically different'} at 90%")
        notes.append(f"Residents 25+ with a bachelor's degree or higher (ACS {acs['year']}): " + "; ".join(
            f"{label[m]} {v['estimate']:.1f}% ±{v['moe']:.1f}" for m, v in vals.items()) + ". " + "; ".join(pairs))
    out.append({
        "id": "context", "kind": "descriptive",
        "question": "What do establishment, GDP and workforce measures add?",
        "rule": "Reported side by side with their own reference periods; not combined with QCEW employment into a single index.",
        "text": (". ".join(notes) + ".") if notes else "No context source was available in this build.",
        "evidence": [],
    })
    return out
