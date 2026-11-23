"""
Campaign evaluation (clients without GA4, e.g. Hornbach Vloeren): what the link campaign did for the whole domain and
for the pages that received links, measured with Google Search Console. Pure pandas; rendering in campaign_eval_ui.py.

Inputs
- monthly: get_gsc_monthly -> month, Clicks, Impressions, Position (whole property)
- queries: get_gsc_monthly_by(..., "query") -> month, Key, Clicks, Impressions, Position
- page_queries: get_gsc_page_queries_monthly -> month, Page, Query, Clicks, Impressions, Position (linked pages only)
- links: live-links sheet -> 'LL Date', 'Link to', 'Price', 'Domain', 'DA'
"""
import pandas as pd

from modules.budget_advice import norm_key

ROW_CAP = 25000   # Search Console returns at most this many rows per request


def _brand_mask(s: pd.Series, brand_terms: list) -> pd.Series:
    pat = "|".join(t.lower() for t in (brand_terms or []) if t)
    return s.astype(str).str.lower().str.contains(pat, regex=True) if pat else pd.Series(False, index=s.index)


def _links(links: pd.DataFrame) -> pd.DataFrame:
    if links is None or links.empty or "LL Date" not in links.columns:
        return pd.DataFrame(columns=["date", "month", "page", "price"])
    raw = links["LL Date"]
    iso = pd.to_datetime(raw, errors="coerce", format="ISO8601")
    d = pd.DataFrame({"date": iso.fillna(pd.to_datetime(raw, errors="coerce", dayfirst=True)),
                      "page": links.get("Link to", pd.Series(dtype=str)).astype(str).map(norm_key),
                      "price": pd.to_numeric(links.get("Price"), errors="coerce").fillna(0)})
    d = d.dropna(subset=["date"])
    d["month"] = d["date"].dt.to_period("M").dt.to_timestamp()
    return d


def domain_timeline(monthly: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    """Per month: Clicks, Impressions, Position, Links placed, Links total, Spend total."""
    if monthly is None or monthly.empty:
        return pd.DataFrame()
    m = monthly.sort_values("month").reset_index(drop=True).copy()
    lk = _links(links)
    per = lk.groupby("month").agg(n=("page", "size"), spend=("price", "sum"))
    m["Links placed"] = m["month"].map(per["n"]).fillna(0).astype(int)
    m["Links total"] = m["month"].map(lambda x: int((lk["month"] <= x).sum()))
    m["Spend total"] = m["month"].map(lambda x: float(lk.loc[lk["month"] <= x, "price"].sum()))
    return m


def query_timeline(queries: pd.DataFrame, brand_terms: list) -> pd.DataFrame:
    """Per month: search terms with impressions, terms on page 1 (top 10), non-brand terms on page 1, non-brand clicks
    and impressions, brand clicks. 'Capped' = Google returned the maximum number of rows, so counts are a lower bound."""
    if queries is None or queries.empty:
        return pd.DataFrame()
    q = queries.copy()
    q["brand"] = _brand_mask(q["Key"], brand_terms)
    rows = []
    for mo, g in q.groupby("month"):
        nb = g[~g["brand"]]
        rows.append({"month": mo, "Search terms": len(g), "Terms top 10": int((g["Position"] <= 10).sum()),
                     "Non-brand terms top 10": int((nb["Position"] <= 10).sum()),
                     "Non-brand clicks": float(nb["Clicks"].sum()), "Non-brand impressions": float(nb["Impressions"].sum()),
                     "Brand clicks": float(g.loc[g["brand"], "Clicks"].sum()), "Capped": len(g) >= ROW_CAP})
    return pd.DataFrame(rows).sort_values("month").reset_index(drop=True)


def _main_term(g: pd.DataFrame, brand_terms: list) -> str | None:
    """The non-brand search term this page is seen for most in its latest month."""
    last = g[g["month"] == g["month"].max()]
    nb = last[~_brand_mask(last["Query"], brand_terms)]
    if nb.empty:
        return None
    return str(nb.sort_values("Impressions", ascending=False).iloc[0]["Query"])


def _pos_by_month(g: pd.DataFrame) -> pd.Series:
    """Impression-weighted position per month (one page can appear under several URL spellings)."""
    if g.empty:
        return pd.Series(dtype=float)
    w = g.assign(pw=g["Position"] * g["Impressions"]).groupby("month")[["pw", "Impressions"]].sum()
    return w["pw"] / w["Impressions"].where(w["Impressions"] > 0)


def focus_pages(page_queries: pd.DataFrame, links: pd.DataFrame, brand_terms: list) -> pd.DataFrame:
    """One row per page that received links: links, spend, first link, main search term and its position in the first
    and the latest month, clicks/impressions/top-10 terms first vs. latest month and a plain verdict."""
    lk = _links(links)
    if lk.empty or page_queries is None or page_queries.empty:
        return pd.DataFrame()
    pq = page_queries.copy()
    pq["k"] = pq["Page"].map(norm_key)
    rows = []
    for k, lg in lk.groupby("page"):
        g = pq[(pq["k"] == k) & (pq["month"] >= lg["month"].min())]   # compare from the month of this page's first link
        row = {"Page": str(links.loc[links["Link to"].astype(str).map(norm_key) == k, "Link to"].iloc[0]),
               "Links": len(lg), "Spent": float(lg["price"].sum()), "First link": lg["date"].min().date()}
        if g.empty:
            rows.append(row)
            continue
        m0, m1 = g["month"].min(), g["month"].max()
        a, b = g[g["month"] == m0], g[g["month"] == m1]
        term = _main_term(g, brand_terms)
        tp = _pos_by_month(g[g["Query"] == term]) if term else pd.Series(dtype=float)
        p0, p1 = (float(tp.get(m0)) if m0 in tp.index else None), (float(tp.get(m1)) if m1 in tp.index else None)
        row.update({"Main search term": term, "From": m0, "To": m1, "Position then": p0, "Position now": p1,
                    "Clicks then": float(a["Clicks"].sum()), "Clicks now": float(b["Clicks"].sum()),
                    "Impressions then": float(a["Impressions"].sum()), "Impressions now": float(b["Impressions"].sum()),
                    "Top-10 terms then": int((a["Position"] <= 10).sum()), "Top-10 terms now": int((b["Position"] <= 10).sum())})
        if p0 is not None and p1 is not None:
            row["Verdict"] = "Rising" if p1 <= p0 - 3 else ("Falling" if p1 >= p0 + 3 else "Stable")
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values(["Links", "Spent"], ascending=False).reset_index(drop=True)


def term_history(page_queries: pd.DataFrame, focus: pd.DataFrame) -> pd.DataFrame:
    """Position per month of each focus page's main search term (long format: month, Page, Term, Position)."""
    if page_queries is None or page_queries.empty or focus is None or focus.empty or "Main search term" not in focus:
        return pd.DataFrame()
    pq = page_queries.assign(k=page_queries["Page"].map(norm_key))
    out = []
    for _, r in focus.dropna(subset=["Main search term"]).iterrows():
        g = pq[(pq["k"] == norm_key(r["Page"])) & (pq["Query"] == r["Main search term"])]
        if pd.notna(r.get("From")):
            g = g[g["month"] >= r["From"]]
        out += [{"month": mo, "Page": r["Page"], "Term": r["Main search term"], "Position": v}
                for mo, v in _pos_by_month(g).items()]
    return pd.DataFrame(out)


def headline(dt: pd.DataFrame, qt: pd.DataFrame, launch_month=None, links: pd.DataFrame | None = None) -> dict:
    """Numbers for the hero: clicks and impressions in the last full month vs. the last month before the links (or the
    first month), non-brand top-10 terms then vs. now."""
    if dt is None or dt.empty:
        return {}
    d = dt.sort_values("month")
    first_link = d.loc[d["Links placed"] > 0, "month"].min() if (d["Links placed"] > 0).any() else None
    base = d[d["month"] < (launch_month or first_link)] if (launch_month or first_link) is not None else d.head(1)
    b = base.iloc[-1] if not base.empty else d.iloc[0]
    n = d.iloc[-1]
    out = {"base_month": b["month"], "now_month": n["month"], "clicks_then": float(b["Clicks"]),
           "clicks_now": float(n["Clicks"]), "impr_then": float(b["Impressions"]), "impr_now": float(n["Impressions"]),
           "links": int(n["Links total"]), "spend": float(n["Spend total"]), "first_link": first_link}
    lk = _links(links) if links is not None else pd.DataFrame()
    if not lk.empty:   # all links placed so far, also those after the last complete month
        out.update(links=int(len(lk)), spend=float(lk["price"].sum()))
    if qt is not None and not qt.empty:
        qb = qt[qt["month"] == b["month"]]
        qn = qt[qt["month"] == n["month"]]
        if not qb.empty and not qn.empty:
            out.update({"nb_top10_then": int(qb.iloc[0]["Non-brand terms top 10"]),
                        "nb_top10_now": int(qn.iloc[0]["Non-brand terms top 10"]), "capped": bool(qn.iloc[0]["Capped"]),
                        "nb_clicks_then": float(qb.iloc[0]["Non-brand clicks"]), "nb_clicks_now": float(qn.iloc[0]["Non-brand clicks"])})
    return out
