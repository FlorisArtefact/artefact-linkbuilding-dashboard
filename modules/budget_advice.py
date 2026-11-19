"""
Budget advice: turns the signals the dashboard already has into concrete steering advice.
Pure pandas, no Streamlit, so it is unit-tested (tests/test_budget_advice.py) and works for every client.

Three questions, each answered with the data that is available for the client:
  1. Per market: raise, keep or lower the link budget?          (revenue vs. budget; needs GA4 revenue)
  2. Per linked page: put more links here, wait, or pause?       (YoY development per page and/or Search Console position)
  3. Where should the next links go?                             (pages close to the top of Google without links yet,
                                                                  plus the best-value domains in the pipeline)

Every suggested amount is a PROPOSAL derived from simple, visible rules (see RULES below); the account team decides.
"""
from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd

# Proposed budget change per signal, for the next period of the same length. Deliberately modest steps.
STEP = {"increase": 0.25, "maintain": 0.0, "decrease": -0.25, "unknown": 0.0}
WAIT_MONTHS = 3            # links younger than this are too young to judge
PUSH_POS = (4.0, 20.0)     # Google positions where an extra link has the most leverage (just below / around page 1)
TOP_POS = 3.0              # already in the top 3: more links add little
MANY_LINKS = 3             # pages with this many links and no progress: stop adding links, check content first

ACTIONS = {
    "more": "Put next links here",
    "keep": "Working, keep as is",
    "wait": "Wait, too early to judge",
    "pause": "Pause links, check page first",
    "one_more": "One more link, then evaluate",
    "watch": "Watch",
}
RULES = [
    f"Market: raise the budget by {STEP['increase']:.0%} when revenue on linked pages is at least 2x the budget in the "
    f"realistic case and above 1x in the cautious case; lower it by {-STEP['decrease']:.0%} below 1x; otherwise keep it.",
    f"Page: pages whose first link is younger than {WAIT_MONTHS} months are not judged yet. A page that grows faster than before and is not in "
    f"the top {TOP_POS:.0f} gets the next links. A page with {MANY_LINKS}+ links and no progress is paused until content "
    "and technique are checked.",
    f"Next targets: pages without links that rank between position {PUSH_POS[0]:.0f} and {PUSH_POS[1]:.0f} and get many "
    "impressions. One position up there is worth the most extra clicks.",
]


def norm_key(url) -> str:
    """host+path without www, trailing slash or query: matches Sheet URLs to Search Console URLs."""
    s = str(url or "").strip()
    if not s or s.lower() == "nan":
        return ""
    if "://" not in s:
        s = "https://" + s
    p = urlparse(s)
    return p.netloc.lower().removeprefix("www.") + (p.path.rstrip("/") or "/")


# ── 1. Markets ─────────────────────────────────────────────────────────────────
def market_table(per_market: list[dict], currency: str = "€") -> pd.DataFrame:
    """per_market: [{"market", "investment", "roi_base", "roi_low", "key"}] (key from roi_model.budget_advice).
    Returns one row per market with the signal, a proposed change and a proposed budget for the next period."""
    rows = []
    for m in per_market:
        inv = float(m.get("investment") or 0)
        key = m.get("key", "unknown")
        step = STEP.get(key, 0.0)
        rows.append({
            "Market": m["market"], "Spent": inv, "Revenue vs. budget": m.get("roi_base"),
            "Signal": {"increase": "Raise", "maintain": "Keep", "decrease": "Lower", "unknown": "Not enough data"}[key],
            "Proposed change": step, "Proposed budget": inv * (1 + step), "key": key,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["Revenue vs. budget", "Spent"], ascending=[False, False], na_position="last").reset_index(drop=True)


def market_conclusion(mt: pd.DataFrame, currency: str = "€") -> list[str]:
    """Plain sentences for the top of the advice page."""
    if mt is None or mt.empty:
        return []
    out = []
    judged = mt[mt["key"] != "unknown"]
    spent, proposed = mt["Spent"].sum(), mt["Proposed budget"].sum()
    if not judged.empty and spent > 0:
        delta = proposed / spent - 1
        word = "raise" if delta > 0.02 else ("lower" if delta < -0.02 else "keep")
        out.append(f"Proposal: {word} the total link budget for the next period from {currency}{spent:,.0f} to "
                   f"{currency}{proposed:,.0f} ({delta:+.0%}), split per market as in the table.")
    up = judged[judged["key"] == "increase"]["Market"].tolist()
    down = judged[judged["key"] == "decrease"]["Market"].tolist()
    if up:
        out.append(f"The money works best in {', '.join(up)}: revenue on the linked pages is well above the link budget there.")
    if down:
        tgt = f" and move it to {up[0]}" if up else ""
        out.append(f"In {', '.join(down)} the linked pages do not yet earn back their links: spend less there{tgt}, "
                   "and check the pages themselves before adding links.")
    unknown = mt[mt["key"] == "unknown"]["Market"].tolist()
    if unknown:
        out.append(f"Not enough spend or revenue data to judge {', '.join(unknown)} yet.")
    return out


# ── 2. Linked pages ────────────────────────────────────────────────────────────
def page_table(links: pd.DataFrame, gsc: pd.DataFrame | None = None, status: pd.DataFrame | None = None,
               today=None) -> pd.DataFrame:
    """One row per page that received links (all time), with an action.
    links: live links with 'Link to', 'LL Date', 'Price'. gsc: Search Console per page (Page, Clicks, Impressions,
    Avg Position), last 90 days. status: evidence_model.page_table output (path-level 'Status'), optional."""
    if links is None or links.empty or "Link to" not in links.columns:
        return pd.DataFrame()
    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    lk = links.copy()
    lk["_k"] = lk["Link to"].apply(norm_key)
    lk = lk[lk["_k"] != ""]
    if lk.empty:
        return pd.DataFrame()
    lk["_d"] = pd.to_datetime(lk.get("LL Date"), errors="coerce")
    lk["_p"] = pd.to_numeric(lk.get("Price"), errors="coerce")
    g = {}
    if gsc is not None and not gsc.empty and "Page" in gsc.columns:
        s = gsc.copy()
        s["_k"] = s["Page"].apply(norm_key)
        s["_pw"] = pd.to_numeric(s["Avg Position"], errors="coerce") * pd.to_numeric(s["Impressions"], errors="coerce")
        agg = s.groupby("_k").agg(Clicks=("Clicks", "sum"), Impressions=("Impressions", "sum"), _pw=("_pw", "sum"))
        agg["Position"] = agg["_pw"] / agg["Impressions"].where(agg["Impressions"] > 0)
        g = agg[["Clicks", "Impressions", "Position"]].to_dict("index")
    st_map = {}
    if status is not None and not status.empty and {"Landing Page", "Status"} <= set(status.columns):
        st_map = {norm_key(u): s for u, s in zip(status["Landing Page"], status["Status"])}
    rows = []
    for k, grp in lk.groupby("_k"):
        first = grp["_d"].min()
        last = grp["_d"].max()
        months_last = ((today - first).days / 30.4) if pd.notna(first) else None   # age of the FIRST link: a page
        # that keeps getting links would otherwise never be judged
        m = g.get(k, {})
        pos = m.get("Position")
        stt = st_map.get(k)
        n = len(grp)
        action, why = _page_action(n, months_last, pos, m.get("Impressions") or 0, stt)
        if k.split("/", 1)[-1] == "" and n >= MANY_LINKS and action != "wait":
            action, why = "pause", (f"The homepage already has {n} links and is found through the brand name anyway; "
                                     "the next links do more on category pages.")
        rows.append({"Page": grp["Link to"].iloc[0], "Links": n, "Spent": float(grp["_p"].sum()),
                     "First link": first, "Latest link": last,
                     "Clicks (90d)": m.get("Clicks"), "Impressions (90d)": m.get("Impressions"), "Position": pos, "Development": stt or "",
                     "Action": ACTIONS[action], "Why": why, "_action": action})
    df = pd.DataFrame(rows)
    order = {a: i for i, a in enumerate(["more", "one_more", "pause", "wait", "keep", "watch"])}
    df["_o"] = df["_action"].map(order)
    return df.sort_values(["_o", "Spent"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)


def _page_action(n_links: int, months_since_last, pos, impressions: float, status) -> tuple[str, str]:
    if months_since_last is not None and months_since_last < WAIT_MONTHS and status not in ("Accelerating",):
        return "wait", f"First link is less than {WAIT_MONTHS} months old; links need about that long to show."
    has_pos = pos is not None and not pd.isna(pos)
    if status == "Accelerating":
        if has_pos and pos <= TOP_POS:
            return "keep", f"Grows faster than before and already ranks around position {pos:.0f}."
        return "more", "Grows faster than before the links" + (f" and ranks around position {pos:.0f}, so more can be won." if has_pos else ".")
    if status in ("Slowing", "Stable") and n_links >= MANY_LINKS:
        return "pause", f"{n_links} links, but no faster growth than before. Check content, technique and internal links first."
    if status in ("Slowing", "Stable"):
        return "one_more", f"No clear effect yet with {n_links} link(s)."
    # No revenue development (new page, no GA4): fall back on Google position.
    if has_pos and PUSH_POS[0] <= pos <= PUSH_POS[1] and impressions > 0:
        if n_links >= MANY_LINKS:
            return "one_more", f"Ranks around position {pos:.0f} with {n_links} links; one more, then evaluate."
        return "more", f"Ranks around position {pos:.0f}: close to the top, where an extra link counts most."
    if has_pos and pos < PUSH_POS[0]:
        return "keep", f"Already ranks around position {pos:.0f}."
    if has_pos:
        return "watch", f"Ranks around position {pos:.0f}: far from page 1, links alone will not lift it."
    return "watch", "No Google data for this page in the last 90 days."


# ── 3. Next targets ────────────────────────────────────────────────────────────
# Rough CTR by position (organic, desktop+mobile). Used only to rank pages by how much one step up is worth.
_CTR = {1: .28, 2: .15, 3: .10, 4: .07, 5: .05, 6: .04, 7: .03, 8: .025, 9: .02, 10: .018}


def _ctr(pos: float) -> float:
    p = max(1, int(round(pos)))
    return _CTR.get(p, 0.015 if p <= 20 else 0.005)


def next_targets(gsc: pd.DataFrame | None, linked_urls, host: str = "", n: int = 10,
                 exclude_paths: tuple = ()) -> pd.DataFrame:
    """Pages WITHOUT links that rank between PUSH_POS and get impressions, ranked by the extra clicks a move
    to position 3 would roughly bring (impressions x CTR difference). A ranking aid, not a forecast."""
    if gsc is None or gsc.empty or "Page" not in gsc.columns:
        return pd.DataFrame()
    linked = {norm_key(u) for u in (linked_urls or [])}
    s = gsc.copy()
    s["_k"] = s["Page"].apply(norm_key)
    if host:
        s = s[s["_k"].str.startswith(host.lower().removeprefix("www."))]
    s = s[~s["_k"].isin(linked)]
    s = s[s["_k"].str.split("/", n=1).str[1].fillna("") != ""]  # homepage gets links anyway; target deeper pages
    s = s[s["_k"].str.split("/", n=1).str[1].fillna("").str.len() > 1]   # section roots like /c/ are not link targets
    s = s[~s["_k"].str.contains("=", regex=False)]   # filtered views (/f/Material=Jute) are not link targets
    if exclude_paths:
        s = s[~s["_k"].apply(lambda k: any(x in k for x in exclude_paths))]
    s = s[s["Page"].astype(str).str.contains("#") == False]  # noqa: E712  (jump links duplicate their page)
    pos = pd.to_numeric(s["Avg Position"], errors="coerce")
    imp = pd.to_numeric(s["Impressions"], errors="coerce").fillna(0)
    s = s[(pos >= PUSH_POS[0]) & (pos <= PUSH_POS[1]) & (imp > 0)].copy()
    if s.empty:
        return pd.DataFrame()
    s["Position"] = pd.to_numeric(s["Avg Position"], errors="coerce")
    s["Potential"] = s.apply(lambda r: r["Impressions"] * max(0.0, _ctr(3) - _ctr(r["Position"])), axis=1)
    s = s.sort_values("Potential", ascending=False).head(n)
    return s[["Page", "Clicks", "Impressions", "Position", "Potential"]].rename(
        columns={"Clicks": "Clicks (90d)", "Impressions": "Impressions (90d)",
                 "Potential": "Extra clicks per 90d at position 3 (rough)"}).reset_index(drop=True)


def approved_only(opps: pd.DataFrame) -> pd.DataFrame:
    """Long candidate lists (hundreds of domains) are not a plan; when some rows are approved, only those count."""
    if opps is None or opps.empty or "Approved?" not in opps.columns:
        return opps.copy() if opps is not None else pd.DataFrame()
    from modules.data_loader import is_approved
    m = is_approved(opps["Approved?"])
    return opps[m].copy() if m.any() else opps.copy()


# ── Pipeline: which proposed domains give most for the money ───────────────────
def pipeline_value(opps: pd.DataFrame | None, n: int = 10) -> pd.DataFrame:
    """Proposed domains ranked by organic reach per euro (Ahrefs traffic estimate / price), DR as tie-breaker.
    Domains without price or traffic are left out of the ranking."""
    if opps is None or opps.empty or "Price" not in opps.columns:
        return pd.DataFrame()
    o = approved_only(opps)
    o["Price"] = pd.to_numeric(o["Price"], errors="coerce")
    tcol = next((c for c in o.columns if "organic traffic" in c.lower()), None)
    if tcol is None:
        return pd.DataFrame()
    o["_t"] = pd.to_numeric(o[tcol], errors="coerce")
    o = o[(o["Price"] > 0) & (o["_t"] > 0)]
    if o.empty:
        return pd.DataFrame()
    o["Visitors per €"] = o["_t"] / o["Price"]
    if "Domain" in o.columns:   # a domain proposed for several months is one publisher: rank it once
        cnt = o["Domain"].value_counts()
        o = o.sort_values("Price").drop_duplicates("Domain")
        o["Planned links"] = o["Domain"].map(cnt)
    o = o.sort_values(["Visitors per €", "DR"] if "DR" in o.columns else ["Visitors per €"], ascending=False).head(n)
    cols = [c for c in ["Domain", "DR", "Topic", "Price"] if c in o.columns]
    extra = ["Planned links"] if "Planned links" in o.columns else []
    out = o[cols + extra + ["_t", "Visitors per €"]].rename(columns={"_t": "Monthly organic visitors (Ahrefs est.)"})
    return out.reset_index(drop=True)


# ── Per-market revenue vs. budget (same maths as the 'Revenue vs. budget' tab) ──
def per_market_roi(per_lang: dict, a: dict, window_days: int) -> list[dict]:
    """per_lang: {lang: {"links": df (selected period), "ga4": df|None, "gsc": df|None}}."""
    from modules.roi_model import compute_roi, linked_page_metrics
    out = []
    for lang, d in per_lang.items():
        links = d.get("links")
        inv = float(pd.to_numeric(links["Price"], errors="coerce").sum()) if (links is not None and not links.empty
                                                                             and "Price" in links.columns) else 0.0
        m = linked_page_metrics(links, d.get("ga4"), d.get("gsc"))
        res = compute_roi(inv, m["revenue"], m["sessions"] or m["clicks"], window_days, a)
        out.append({"market": lang, "investment": inv, "roi_base": res["scenarios"]["base"]["roi"] if res["mode"] else None,
                    "roi_low": res["scenarios"]["low"]["roi"] if res["mode"] else None, "key": res["advice"]["key"]})
    return out


# ── Where should the next budget go? (the main question) ───────────────────────
RESPONSE_WEIGHT = {"more": 1.2, "one_more": 1.0, "new": 1.0}   # pages that already respond to links get a small bonus
FOCUS_WEIGHT = 1.5                                                # pages matching the client's own priorities (config)


def allocation(pages: pd.DataFrame | None, targets: pd.DataFrame | None, value_per_visit: dict | None = None,
               focus: list | None = None, n: int = 10) -> pd.DataFrame:
    """Rank candidate pages for the next links and propose a share of the next budget per page.

    Candidates: linked pages whose action is 'more' / 'one_more' and pages without links that rank 4-20.
    Score = extra clicks a move to position 3 would roughly bring (Search Console impressions x CTR gain)
            x value per visit (GA4 revenue / sessions of that page; site average when the page has none; 1 without GA4)
            x response bonus (page already responds to links) x client focus (config 'focus_pages').
    Share = score / sum of the top-n scores. A proposal to discuss, not a forecast."""
    rows = []
    vpv = value_per_visit or {}
    avg = vpv.get("_avg")
    focus = [f.lower() for f in (focus or []) if f]
    if pages is not None and not pages.empty:
        for _, r in pages[pages["_action"].isin(["more", "one_more"])].iterrows():
            rows.append({"Market": r.get("Market", ""), "Page": r["Page"], "Links so far": int(r["Links"]),
                         "Position": r["Position"], "Impressions (90d)": r.get("Impressions (90d)"),
                         "Why here": r["Why"], "_kind": r["_action"]})
    if targets is not None and not targets.empty:
        for _, r in targets.iterrows():
            rows.append({"Market": r.get("Market", ""), "Page": r["Page"], "Links so far": 0, "Position": r["Position"],
                         "Impressions (90d)": r["Impressions (90d)"],
                         "Why here": f"No links yet; ranks around position {r['Position']:.0f} with "
                                     f"{r['Impressions (90d)']:,.0f} impressions.", "_kind": "new"})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["Position"] = pd.to_numeric(df["Position"], errors="coerce")
    df["Impressions (90d)"] = pd.to_numeric(df["Impressions (90d)"], errors="coerce").fillna(0)
    df["Extra clicks (90d, rough)"] = [imp * max(0.0, _ctr(3) - _ctr(p)) if pd.notna(p) else 0.0
                                       for imp, p in zip(df["Impressions (90d)"], df["Position"])]
    if vpv:
        df["Value per visit"] = [vpv.get(norm_key(u), vpv.get("_avg:" + norm_key(u).split("/")[0], avg)) for u in df["Page"]]
        df["Extra revenue (90d, rough)"] = df["Extra clicks (90d, rough)"] * df["Value per visit"].fillna(0)
        base = df["Extra revenue (90d, rough)"]
    else:
        base = df["Extra clicks (90d, rough)"]
    df["Client focus"] = ["yes" if any(f in norm_key(u) for f in focus) else "" for u in df["Page"]] if focus else ""
    df["_score"] = base * df["_kind"].map(RESPONSE_WEIGHT).fillna(1.0) * df["Client focus"].map(
        lambda v: FOCUS_WEIGHT if v == "yes" else 1.0)
    df = df[df["_score"] > 0].sort_values("_score", ascending=False).head(n)
    if df.empty:
        return df
    df["Share of next budget"] = df["_score"] / df["_score"].sum()
    if not focus:
        df = df.drop(columns="Client focus")
    if not (df["Market"].astype(str) != "").any():
        df = df.drop(columns="Market")
    return df.drop(columns="_score").reset_index(drop=True)


def value_per_visit(ga4: pd.DataFrame | None, host: str) -> dict:
    """{host+path: revenue per organic session} from GA4 per-page data, plus '_avg' for the whole site."""
    if ga4 is None or ga4.empty or not {"path", "Revenue", "Sessions"} <= set(ga4.columns):
        return {}
    g = ga4.groupby(ga4["path"].astype(str).str.rstrip("/").replace("", "/")).agg(R=("Revenue", "sum"), S=("Sessions", "sum"))
    out = {f"{host}{p if p.startswith('/') else '/' + p}": r / s for p, (r, s) in g.iterrows() if s >= 20}
    tot_s = g["S"].sum()
    out["_avg"] = float(g["R"].sum() / tot_s) if tot_s else None
    out[f"_avg:{host}"] = out["_avg"]
    return out
