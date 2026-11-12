"""
ROI & budget-advice model — pure pandas/stdlib, NO Streamlit imports, so it can be
unit-tested (tests/test_roi_model.py) and reused for any client.

Idea in one paragraph
---------------------
We cannot prove which part of organic performance is caused by link building
(Google is a black box). So instead of one "ROI", we show THREE scenarios
(low / base / high). Each scenario differs in the share of the organic value on the
linked landing pages that we attribute to link building. The value base is:

  mode "revenue":  GA4 organic revenue on the linked pages (annualised)
  mode "traffic":  organic visits on the linked pages x conversion rate x value per
                   conversion (used when GA4 revenue is not available / zero)
  mode None:       nothing measurable -> advice is "insufficient data"

ROI(scenario) = attributable value over the horizon / investment.

All assumptions live in config.json under "roi" (see DEFAULT_ASSUMPTIONS) and can be
tweaked live in the sidebar. They are PLACEHOLDERS until validated with BWJ,
colleagues and the pillar leads (see HANDOVER.md -> open questions).
"""
from __future__ import annotations

import copy
from urllib.parse import urlparse

import pandas as pd

SCENARIOS = ("low", "base", "high")
SCENARIO_LABELS = {"low": "Low", "base": "Realistic", "high": "High"}

DEFAULT_ASSUMPTIONS: dict = {
    # Months of value counted after placement. Links keep working longer, so 12 is conservative.
    "horizon_months": 12,
    # Share of organic value on the linked pages attributed to link building (rest = content,
    # on-page SEO, brand, seasonality, ...). PLACEHOLDER — to be agreed with pillar leads.
    "attribution_share": {"low": 0.10, "base": 0.20, "high": 0.35},
    # Only used in "traffic" mode (no GA4 revenue). Organic visit -> conversion.
    "conversion_rate": {"low": 0.010, "base": 0.018, "high": 0.025},
    # Average order value (webshop) or lead value (B2B), in the client's currency.
    "value_per_conversion": 45.0,
    # Decision thresholds for the budget advice.
    "thresholds": {
        "increase_base_roi": 2.0,   # base ROI at/above this AND low ROI above increase_low_roi -> increase
        "increase_low_roi": 1.0,
        "decrease_base_roi": 1.0,   # base ROI below this -> decrease
    },
    "min_investment": 250.0,        # below this there is too little spend to judge
    "currency_symbol": "€",
}


def merged_assumptions(config_roi: dict | None) -> dict:
    """Defaults overlaid with whatever is in config.json['roi'] (nested dicts merged)."""
    out = copy.deepcopy(DEFAULT_ASSUMPTIONS)
    for key, val in (config_roi or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key].update(val)
        else:
            out[key] = val
    return out


# ── Matching GA4 / GSC rows to linked landing pages ─────────────────────────────
def _norm_path(url: str) -> str:
    path = urlparse(str(url)).path.rstrip("/")
    return path or "/"


def _norm_url(url: str) -> str:
    p = urlparse(str(url))
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/') or '/'}"


def linked_page_metrics(
    links_df: pd.DataFrame,
    ga4_df: pd.DataFrame | None = None,
    gsc_df: pd.DataFrame | None = None,
) -> dict:
    """Organic revenue / sessions / clicks on the landing pages that received links.

    GA4 reports paths only -> match on path. GSC reports full URLs -> match on host+path.
    Returns zeros (never raises) when a source is missing.
    """
    out = {"pages": 0, "revenue": 0.0, "conversions": 0.0, "sessions": 0.0, "clicks": 0.0,
           "ga4_matched_pages": 0, "gsc_matched_pages": 0}
    if links_df is None or links_df.empty or "Link to" not in links_df.columns:
        return out
    targets = [t for t in links_df["Link to"].dropna().astype(str).unique() if t.strip()]
    out["pages"] = len(targets)

    if ga4_df is not None and not ga4_df.empty and "path" in ga4_df.columns:
        wanted = {_norm_path(u) for u in targets}
        g = ga4_df.copy()
        g["_p"] = g["path"].apply(lambda p: str(p).rstrip("/") or "/")
        hit = g[g["_p"].isin(wanted)]
        out["revenue"] = float(hit.get("Revenue", pd.Series(dtype=float)).sum())
        out["conversions"] = float(hit.get("Conversions", pd.Series(dtype=float)).sum())
        out["sessions"] = float(hit.get("Sessions", pd.Series(dtype=float)).sum())
        out["ga4_matched_pages"] = int(hit["_p"].nunique())

    if gsc_df is not None and not gsc_df.empty and {"Page", "Clicks"} <= set(gsc_df.columns):
        wanted = {_norm_url(u) for u in targets}
        s = gsc_df.copy()
        s["_u"] = s["Page"].apply(_norm_url)
        hit = s[s["_u"].isin(wanted)]
        out["clicks"] = float(pd.to_numeric(hit["Clicks"], errors="coerce").sum())
        out["gsc_matched_pages"] = int(hit["_u"].nunique())
    return out


# ── Core calculation ────────────────────────────────────────────────────────────
def compute_roi(
    investment: float,
    revenue_window: float = 0.0,
    traffic_window: float = 0.0,
    window_days: int = 90,
    assumptions: dict | None = None,
) -> dict:
    """Return scenarios, mode, advice and sensitivity inputs for one scope (total or per language).

    revenue_window / traffic_window: organic revenue / visits measured over `window_days`.
    """
    a = assumptions or merged_assumptions(None)
    horizon = float(a["horizon_months"])
    scale = (365.0 / max(window_days, 1)) * (horizon / 12.0)   # window -> horizon

    if revenue_window and revenue_window > 0:
        mode = "revenue"
    elif traffic_window and traffic_window > 0 and float(a.get("value_per_conversion") or 0) > 0:
        mode = "traffic"       # only with a conversion value; a client without one (e.g. showroom visits) gets no made-up euros
    else:
        mode = None

    scenarios: dict = {}
    for s in SCENARIOS:
        share = float(a["attribution_share"][s])
        if mode == "revenue":
            value = revenue_window * scale * share
        elif mode == "traffic":
            value = traffic_window * scale * share * float(a["conversion_rate"][s]) * float(a["value_per_conversion"])
        else:
            value = 0.0
        roi = (value / investment) if investment and investment > 0 else None
        scenarios[s] = {
            "share": share, "value": value, "roi": roi,
            "net": value - (investment or 0.0),
            "payback_months": (investment / (value / horizon)) if value > 0 and investment else None,
        }

    return {
        "mode": mode, "investment": float(investment or 0.0), "horizon_months": horizon,
        "scale": scale, "scenarios": scenarios,
        "revenue_window": float(revenue_window or 0.0), "traffic_window": float(traffic_window or 0.0),
        "window_days": window_days, "advice": budget_advice(investment, scenarios, mode, a),
    }


def budget_advice(investment: float, scenarios: dict, mode, a: dict) -> dict:
    """Rule-based advice. Deliberately simple and transparent — thresholds are configurable."""
    t = a["thresholds"]
    # Wording is deliberately a SIGNAL, not a verdict: link building acts with a delay, page-level
    # revenue also depends on content, technique, competition, and links lift the whole domain.
    if mode is None or not investment or investment < a["min_investment"]:
        return {"verdict": "NOT ENOUGH DATA", "key": "unknown", "color": "#8B9BB4",
                "reason": "There is not enough measurable spend or organic value in the selected period "
                          "to give a responsible budget signal. Connect GA4 / Search Console or widen the period."}
    low, base = scenarios["low"]["roi"], scenarios["base"]["roi"]
    if base >= t["increase_base_roi"] and low >= t["increase_low_roi"]:
        return {"verdict": "SIGNAL: ROOM TO INCREASE", "key": "increase", "color": "#1E9E5A",
                "reason": f"Even the cautious scenario covers the investment ({low:.1f}x) and the realistic scenario "
                          f"is at {base:.1f}x. This points towards room to increase budget — to be weighed against "
                          f"the pages that lag (see below)."}
    if base < t["decrease_base_roi"]:
        return {"verdict": "SIGNAL: REVIEW BUDGET", "key": "decrease", "color": "#D93636",
                "reason": f"The realistic scenario is at {base:.1f}x (< {t['decrease_base_roi']:.1f}x) on the linked "
                          f"pages. That does not mean the money was wasted — links also lift the whole domain and "
                          f"work with a delay — but it is a reason to review where the budget goes."}
    return {"verdict": "SIGNAL: KEEP BUDGET STEADY", "key": "maintain", "color": "#E08A00",
            "reason": f"The realistic scenario is at {base:.1f}x, but the cautious scenario ({low:.1f}x) does not "
                      f"clearly clear the bar for extra spend. Keep the budget and re-evaluate next quarter."}


def sensitivity_grid(
    investment: float, revenue_window: float, traffic_window: float, window_days: int,
    assumptions: dict, shares=None, value_mults=None,
) -> tuple[list, list, list]:
    """ROI grid: attribution share (x) vs. size of the value base (y: 50%..150% of measured).
    Uses the base conversion rate in traffic mode."""
    shares = shares or [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]
    value_mults = value_mults or [0.5, 0.75, 1.0, 1.25, 1.5]
    a = assumptions
    scale = (365.0 / max(window_days, 1)) * (float(a["horizon_months"]) / 12.0)
    z = []
    for m in value_mults:
        row = []
        for sh in shares:
            if revenue_window > 0:
                v = revenue_window * m * scale * sh
            else:
                v = traffic_window * m * scale * sh * a["conversion_rate"]["base"] * a["value_per_conversion"]
            row.append(round(v / investment, 2) if investment > 0 else None)
        z.append(row)
    return shares, value_mults, z


def management_summary_text(client: str, period: str, total: dict, a: dict, data_notes: list[str]) -> str:
    """Plain-text/markdown management summary (also offered as download)."""
    cur = a.get("currency_symbol", "€")
    adv = total["advice"]
    lines = [
        f"# Link building — management summary: {client}",
        f"Period: {period}", "",
        f"## Advice: {adv['verdict']}", adv["reason"], "",
        f"Investment in period: {cur}{total['investment']:,.0f}",
    ]
    if total["mode"]:
        lines.append("")
        lines.append(f"| Scenario | Attribution | Value ({int(total['horizon_months'])} mo) | ROI | Net result |")
        lines.append("|---|---|---|---|---|")
        for s in SCENARIOS:
            r = total["scenarios"][s]
            roi = f"{r['roi']:.1f}x" if r["roi"] is not None else "—"
            lines.append(f"| {SCENARIO_LABELS[s]} | {r['share']:.0%} | {cur}{r['value']:,.0f} | {roi} | {cur}{r['net']:,.0f} |")
        basis = ("GA4 organic revenue on the linked landing pages"
                 if total["mode"] == "revenue" else
                 "organic visits x assumed conversion rate x assumed value per conversion (no GA4 revenue available)")
        lines += ["", f"Value basis: {basis}."]
    lines += ["", "## Data & assumptions"] + [f"- {n}" for n in data_notes]
    lines += ["", "## Disclaimer",
              "These figures are projections based on stated assumptions, not guarantees. Google's ranking "
              "algorithm is a black box and organic results are influenced by many factors besides link building. "
              "Attribution shares are estimates and must be validated with the client."]
    return "\n".join(lines)
