"""
Revenue-growth analysis: did organic revenue grow on the pages that received links?

Pure pandas, no Streamlit (unit-tested in tests/test_growth_model.py).

For every linked landing page we compare average monthly organic revenue in the N months
BEFORE its first link with the N months AFTER (the month of the link itself is skipped), and
compare that with what the whole domain did over the same months. "Outperformance" =
page growth minus domain growth, a first, honest control for seasonality and site-wide trends.
It is still not proof of causality (see the disclaimer in the UI).
"""
from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd

DEFAULT_CATEGORIES = {
    "Apple Watch": ["apple"], "Garmin": ["garmin"], "Samsung": ["samsung", "galaxy"],
    "Fitbit": ["fitbit"], "Huawei": ["huawei"], "Polar": ["polar"], "Google Pixel": ["pixel"],
}


def norm_path(url: str) -> str:
    return urlparse(str(url)).path.rstrip("/") or "/"


def category_of(url: str, categories: dict | None = None) -> str:
    path = norm_path(url).lower()
    if path == "/":
        return "Home"
    for label, keywords in (categories or DEFAULT_CATEGORIES).items():
        if any(k.lower() in path for k in keywords):
            return label
    return "Other"


def last_full_month(today=None) -> pd.Timestamp:
    t = pd.Timestamp(today or pd.Timestamp.today()).normalize().replace(day=1)
    return t - pd.DateOffset(months=1)


def monthly_pivot(monthly_df: pd.DataFrame, today=None) -> pd.DataFrame:
    """Rows = months (complete months only, gaps filled with 0), columns = landing page path."""
    if monthly_df is None or monthly_df.empty:
        return pd.DataFrame()
    df = monthly_df.copy()
    df["path"] = df["path"].apply(norm_path)
    df["month"] = pd.to_datetime(df["month"]).dt.to_period("M").dt.to_timestamp()
    last = last_full_month(today)
    df = df[df["month"] <= last]
    if df.empty:
        return pd.DataFrame()
    pv = df.pivot_table(index="month", columns="path", values="Revenue", aggfunc="sum").fillna(0.0)
    full = pd.date_range(pv.index.min(), last, freq="MS")
    return pv.reindex(full, fill_value=0.0)


def _mean(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp):
    part = series[(series.index >= start) & (series.index <= end)]
    return (float(part.mean()), len(part)) if len(part) else (None, 0)


def _growth(before, after):
    if before is None or after is None or before <= 0:
        return None
    return after / before - 1.0


MIN_MONTHS_AFTER = 2      # fewer months after the first link = too early to say anything
SIGNAL_BAND = 0.10        # +-10 percentage points vs. the domain counts as "in line"

SIGNALS = ["Ahead of domain", "In line with domain", "Behind domain", "Too early / no baseline"]


def signal_for(growth, domain_growth, months_after: int) -> str:
    """Deliberately coarse: a direction, not a verdict. Links work with a delay, and page revenue also
    depends on content, technique, competition and internal linking."""
    if growth is None or domain_growth is None or pd.isna(growth) or pd.isna(domain_growth) or months_after < MIN_MONTHS_AFTER:
        return "Too early / no baseline"
    diff = growth - domain_growth
    if diff >= SIGNAL_BAND:
        return "Ahead of domain"
    if diff <= -SIGNAL_BAND:
        return "Behind domain"
    return "In line with domain"


def growth_table(monthly_df: pd.DataFrame, links_df: pd.DataFrame, window: int = 3, today=None) -> pd.DataFrame:
    """One row per linked landing page. Empty DataFrame when there is nothing to compare."""
    pv = monthly_pivot(monthly_df, today)
    if pv.empty or links_df is None or links_df.empty or "Link to" not in links_df.columns or "LL Date" not in links_df.columns:
        return pd.DataFrame()
    dom = pv.sum(axis=1)
    links = links_df.dropna(subset=["Link to", "LL Date"]).copy()
    links = links[links["Link to"].astype(str).str.strip() != ""]
    links["_path"] = links["Link to"].apply(norm_path)
    rows = []
    for path, grp in links.groupby("_path"):
        first = pd.Timestamp(grp["LL Date"].min()).to_period("M").to_timestamp()
        b0, b1 = first - pd.DateOffset(months=window), first - pd.DateOffset(months=1)
        a0, a1 = first + pd.DateOffset(months=1), first + pd.DateOffset(months=window)
        series = pv[path] if path in pv.columns else pd.Series(0.0, index=pv.index)
        rb, nb = _mean(series, b0, b1)
        ra, na = _mean(series, a0, a1)
        db, _ = _mean(dom, b0, b1)
        da, _ = _mean(dom, a0, a1)
        g, dg = _growth(rb, ra), _growth(db, da)
        not_live = int((grp["Status code"] != 200).sum()) if "Status code" in grp.columns else 0
        avg_da = float(grp["DA"].mean()) if "DA" in grp.columns and grp["DA"].notna().any() else None
        rows.append({
            "Landing Page": grp["Link to"].iloc[0], "path": path, "First link": first,
            "# Links": len(grp), "Months before": nb, "Months after": na,
            "Rev/mo before": rb, "Rev/mo after": ra, "Growth": g, "Domain growth": dg,
            "Outperformance": (g - dg) if (g is not None and dg is not None) else None,
            "Signal": signal_for(g, dg, na), "Links not live": not_live, "Avg DA": avg_da,
        })
    return pd.DataFrame(rows).sort_values("First link").reset_index(drop=True)


def summarize(table: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
    """Aggregate growth_table rows (optionally by a column such as Category). Only rows that have a
    usable before/after pair are counted."""
    if table.empty:
        return pd.DataFrame()
    t = table.dropna(subset=["Rev/mo before", "Rev/mo after"])
    t = t[t["Rev/mo before"] > 0]
    if "Months after" in t.columns:          # links younger than MIN_MONTHS_AFTER months are too early to judge
        t = t[t["Months after"] >= MIN_MONTHS_AFTER]
    if t.empty:
        return pd.DataFrame()
    key = t[group_col] if group_col else pd.Series("All linked pages", index=t.index)
    out = []
    for name, g in t.groupby(key):
        b, a = g["Rev/mo before"].sum(), g["Rev/mo after"].sum()
        dg = g["Domain growth"].dropna().mean() if g["Domain growth"].notna().any() else None
        out.append({"Group": name, "Pages": len(g), "Rev/mo before": b, "Rev/mo after": a,
                    "Growth": a / b - 1.0, "Domain growth": dg,
                    "Outperformance": (a / b - 1.0 - dg) if dg is not None else None})
    return pd.DataFrame(out)
