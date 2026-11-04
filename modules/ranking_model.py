"""
Ranking trend of ALL pages that received links ("tagged" pages), per market. Pure pandas, no Streamlit.

Input per URL: a DataFrame with one row per snapshot date and columns
  date, avg_position, keywords, top10, est_traffic
(from Ahrefs snapshots today, from Search Console later).

Output: an aggregated trend, a per-URL table and a coarse status (improving / stable / declining).
It is a direction, not proof: no control group, and Ahrefs positions are estimates from its own tracking.
"""
from __future__ import annotations

import pandas as pd

POSITION_STEP = 1.0      # average position improving by >= 1 place counts as a real move
TRAFFIC_STEP = 0.10      # +-10 % estimated organic traffic


def aggregate(history: dict) -> pd.DataFrame:
    """Per snapshot date over all URLs: mean position (URLs with rankings only), sums of keywords/top10/traffic."""
    frames = []
    for url, df in (history or {}).items():
        if df is None or df.empty:
            continue
        d = df.copy()
        d["url"] = url
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    allv = pd.concat(frames, ignore_index=True)
    allv["date"] = pd.to_datetime(allv["date"])
    ranked = allv[allv["keywords"].fillna(0) > 0]
    out = allv.groupby("date").agg(keywords=("keywords", "sum"), top10=("top10", "sum"),
                                   est_traffic=("est_traffic", "sum")).reset_index()
    pos = ranked.groupby("date")["avg_position"].mean().rename("avg_position")
    cnt = ranked.groupby("date")["url"].nunique().rename("urls_ranking")
    out = out.merge(pos, on="date", how="left").merge(cnt, on="date", how="left")
    out["urls_ranking"] = out["urls_ranking"].fillna(0).astype(int)
    return out.sort_values("date").reset_index(drop=True)


def trend_status(agg: pd.DataFrame) -> dict:
    """Compare the first and last snapshot that has rankings. Coarse on purpose."""
    empty = {"status": "unknown", "pos_start": None, "pos_now": None, "pos_change": None,
             "traffic_start": None, "traffic_now": None, "traffic_change": None,
             "top10_start": None, "top10_now": None}
    if agg is None or agg.empty:
        return empty
    valid = agg[(agg["urls_ranking"] > 0) & agg["avg_position"].notna()]
    if len(valid) < 2:
        return empty
    a, b = valid.iloc[0], valid.iloc[-1]
    pos_change = float(a["avg_position"] - b["avg_position"])          # positive = better (lower number)
    t0, t1 = float(a["est_traffic"]), float(b["est_traffic"])
    tr = (t1 / t0 - 1.0) if t0 > 0 else None
    t10_0, t10_1 = int(a["top10"]), int(b["top10"])
    t10 = (t10_1 / t10_0 - 1.0) if t10_0 > 0 else None
    dirs = [1 if pos_change >= POSITION_STEP else -1 if pos_change <= -POSITION_STEP else 0]
    if tr is not None:
        dirs.append(1 if tr >= TRAFFIC_STEP else -1 if tr <= -TRAFFIC_STEP else 0)
    if t10 is not None:
        dirs.append(1 if t10 >= TRAFFIC_STEP else -1 if t10 <= -TRAFFIC_STEP else 0)
    # Careful wording: conflicting signals are "mixed", never a plain "declining".
    if any(d > 0 for d in dirs) and any(d < 0 for d in dirs):
        status = "mixed"
    elif any(d > 0 for d in dirs):
        status = "improving"
    elif any(d < 0 for d in dirs):
        status = "declining"
    else:
        status = "stable"
    return {"status": status, "pos_start": float(a["avg_position"]), "pos_now": float(b["avg_position"]),
            "pos_change": pos_change, "traffic_start": t0, "traffic_now": t1, "traffic_change": tr,
            "top10_start": int(a["top10"]), "top10_now": int(b["top10"]),
            "date_start": a["date"], "date_now": b["date"]}


def per_url_table(history: dict) -> pd.DataFrame:
    rows = []
    for url, df in (history or {}).items():
        if df is None or df.empty:
            continue
        d = df.sort_values("date")
        ranked = d[(d["keywords"] > 0) & d["avg_position"].notna()]
        if ranked.empty:
            rows.append({"Landing Page": url, "Position start": None, "Position now": None, "Change": None,
                         "Traffic start": float(d.iloc[0]["est_traffic"]), "Traffic now": float(d.iloc[-1]["est_traffic"]),
                         "Top-10 kw now": int(d.iloc[-1]["top10"])})
            continue
        a, b = ranked.iloc[0], ranked.iloc[-1]
        rows.append({"Landing Page": url, "Position start": float(a["avg_position"]),
                     "Position now": float(d.iloc[-1]["avg_position"]) if pd.notna(d.iloc[-1]["avg_position"]) else None,
                     "Change": float(a["avg_position"] - d.iloc[-1]["avg_position"]) if pd.notna(d.iloc[-1]["avg_position"]) else None,
                     "Traffic start": float(d.iloc[0]["est_traffic"]), "Traffic now": float(d.iloc[-1]["est_traffic"]),
                     "Top-10 kw now": int(d.iloc[-1]["top10"])})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Change", ascending=False, na_position="last").reset_index(drop=True)
