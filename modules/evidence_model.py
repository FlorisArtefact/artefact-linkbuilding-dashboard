"""
Evidence model: is the organic development better since link building started?

Design (kept simple on purpose, no Streamlit):
 * Seasonality is removed by comparing every window with the SAME months one year earlier (year-over-year, YoY).
 * "Acceleration" = YoY growth now minus YoY growth in the months just BEFORE the first link. If link building
   works, linked pages should accelerate. This is a before/after comparison of growth rates, not a level comparison.
 * Three groups run side by side: pages that received links, pages that did not (control), and the whole domain.
   Links to the homepage / categories also lift the domain, so the domain is reported separately instead of
   being used as a clean control.
 * Pages whose first link is younger than MIN_MONTHS are "too early" and never count as a failure.
This is evidence for steering a budget decision, not proof of causality.
"""
from __future__ import annotations

import pandas as pd

from modules.growth_model import category_of, monthly_pivot, norm_path

W = 3                    # months per comparison window
MIN_MONTHS = 3           # complete months after the first link before a page is judged
BAND = 0.05              # +-5 percentage points acceleration counts as "stable"

DEFAULT_CONTENT_KEYWORDS = ["blog", "nieuws", "news", "magazine", "gids", "guide", "ratgeber"]


def page_type(path: str, content_keywords: list | None = None) -> str:
    p = norm_path(path).lower()
    if p == "/":
        return "Homepage"
    if any(k in p for k in (content_keywords or DEFAULT_CONTENT_KEYWORDS)):
        return "Content / blog"
    return "Commercial page"


def _win(series: pd.Series, end: pd.Timestamp, w: int = W) -> float:
    start = end - pd.DateOffset(months=w - 1)
    return float(series[(series.index >= start) & (series.index <= end)].sum())


def _yoy(series: pd.Series, end: pd.Timestamp, w: int = W):
    """Growth of the w months ending at `end` versus the same months a year earlier; None without a baseline."""
    cur = _win(series, end, w)
    prev = _win(series, end - pd.DateOffset(years=1), w)
    has_hist = (end - pd.DateOffset(years=1) - pd.DateOffset(months=w - 1)) >= series.index.min()
    if not has_hist or prev <= 0:
        return None, cur, prev
    return cur / prev - 1.0, cur, prev


def campaign_start(links_df: pd.DataFrame):
    if links_df is None or links_df.empty or "LL Date" not in links_df.columns:
        return None
    d = pd.to_datetime(links_df["LL Date"], errors="coerce").dropna()
    return d.min().to_period("M").to_timestamp() if len(d) else None


def linked_paths(links_df: pd.DataFrame) -> set:
    if links_df is None or links_df.empty or "Link to" not in links_df.columns:
        return set()
    return {norm_path(u) for u in links_df["Link to"].dropna() if str(u).strip()}


def group_series(pv: pd.DataFrame, links: set) -> dict:
    cols = list(pv.columns)
    lk = [c for c in cols if c in links]
    rest = [c for c in cols if c not in links]
    return {"Pages with links": pv[lk].sum(axis=1) if lk else pd.Series(0.0, index=pv.index),
            "Pages without links": pv[rest].sum(axis=1) if rest else pd.Series(0.0, index=pv.index),
            "Whole domain": pv.sum(axis=1)}


def yoy_curve(series: pd.Series, w: int = W) -> pd.Series:
    """Rolling w-month YoY growth per month (NaN where there is no baseline)."""
    roll = series.rolling(w).sum()
    prev = roll.shift(12)
    out = roll / prev.where(prev > 0) - 1.0
    return out.iloc[12 + w - 1:]


def summary(pv: pd.DataFrame, links_df: pd.DataFrame, today=None) -> dict:
    """Headline numbers per group. Returns {} when there is not enough data."""
    if pv is None or pv.empty or links_df is None or links_df.empty:
        return {}
    start = campaign_start(links_df)
    if start is None:
        return {}
    end = pv.index.max()
    months_since = (end.year - start.year) * 12 + end.month - start.month
    pre_end = start - pd.DateOffset(months=1)
    groups = group_series(pv, linked_paths(links_df))
    out = {"campaign_start": start, "months_since": months_since, "window_end": end, "groups": {}}
    for name, s in groups.items():
        now, cur, prev = _yoy(s, end)
        before, _, _ = _yoy(s, pre_end)
        acc = (now - before) if (now is not None and before is not None) else None
        out["groups"][name] = {"yoy_now": now, "yoy_before": before, "acceleration": acc, "now_value": cur, "year_ago_value": prev}
    # Above / below what the 'no links' trend would predict, in value terms (an estimate, see caveats).
    g, c = out["groups"]["Pages with links"], out["groups"]["Pages without links"]
    if c["yoy_now"] is not None and g["year_ago_value"] > 0:
        out["above_control_value"] = g["now_value"] - g["year_ago_value"] * (1 + c["yoy_now"])
    else:
        out["above_control_value"] = None
    out["verdict"] = verdict(out)
    return out


def verdict(s: dict) -> str:
    if not s:
        return "no_data"
    if s["months_since"] < MIN_MONTHS:
        return "too_early"
    g = s["groups"]["Pages with links"]["acceleration"]
    if g is None:
        return "no_baseline"
    if g >= BAND:
        return "accelerating"
    if g <= -BAND:
        return "slowing"
    return "stable"


def page_table(pv: pd.DataFrame, links_df: pd.DataFrame, content_keywords: list | None = None,
               categories: dict | None = None) -> pd.DataFrame:
    """One row per linked page: YoY before its first link vs YoY now, and whether it is old enough to judge."""
    if pv is None or pv.empty or links_df is None or links_df.empty:
        return pd.DataFrame()
    end = pv.index.max()
    links = links_df.dropna(subset=["Link to", "LL Date"]).copy()
    links = links[links["Link to"].astype(str).str.strip() != ""]
    links["_path"] = links["Link to"].apply(norm_path)
    rows = []
    for path, grp in links.groupby("_path"):
        first = pd.Timestamp(grp["LL Date"].min()).to_period("M").to_timestamp()
        months_since = (end.year - first.year) * 12 + end.month - first.month
        s = pv[path] if path in pv.columns else pd.Series(0.0, index=pv.index)
        now, cur, prev = _yoy(s, end)
        before, _, _ = _yoy(s, first - pd.DateOffset(months=1))
        acc = (now - before) if (now is not None and before is not None) else None
        if months_since < MIN_MONTHS:
            status = "Too early"
        elif acc is None:
            status = "No baseline (new page)"
        elif acc >= BAND:
            status = "Accelerating"
        elif acc <= -BAND:
            status = "Slowing"
        else:
            status = "Stable"
        rows.append({"Landing Page": grp["Link to"].iloc[0], "path": path, "Type": page_type(path, content_keywords),
                     "Category": category_of(path, categories), "First link": first, "# Links": len(grp),
                     "Months since": months_since, "YoY before": before, "YoY now": now, "Acceleration": acc,
                     "Last 3 months": cur, "Same months last year": prev, "Status": status})
    return pd.DataFrame(rows).sort_values("First link").reset_index(drop=True)


def cohort_table(pt: pd.DataFrame, by: str = "Type") -> pd.DataFrame:
    """Pooled (revenue-weighted, so tiny pages do not dominate) YoY now vs before, per group of pages."""
    if pt is None or pt.empty:
        return pd.DataFrame()
    t = pt[pt["Months since"] >= MIN_MONTHS]
    rows = []
    for name, g in t.groupby(by):
        g2 = g.dropna(subset=["YoY before", "YoY now"])
        rows.append({by: name, "Pages (old enough)": len(g), "Pages with baseline": len(g2),
                     "Accelerating": int((g["Status"] == "Accelerating").sum()),
                     "Stable": int((g["Status"] == "Stable").sum()), "Slowing": int((g["Status"] == "Slowing").sum()),
                     "Last 3 months": g["Last 3 months"].sum(), "Same months last year": g["Same months last year"].sum()})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["YoY now (pooled)"] = out["Last 3 months"] / out["Same months last year"].where(out["Same months last year"] > 0) - 1
    return out
