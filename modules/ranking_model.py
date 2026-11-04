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
    """Per snapshot date over all URLs: sums of keywords/top3/top10/traffic, mean position (URLs with rankings only).
    Columns that a source does not deliver (Ahrefs summary has no position and no top-10) stay out / NaN."""
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
    spec = {"keywords": ("keywords", "sum"), "est_traffic": ("est_traffic", "sum")}
    for c in ("top3", "top10"):
        if c in allv.columns and allv[c].notna().any():
            spec[c] = (c, "sum")
    out = allv.groupby("date").agg(**spec).reset_index()
    if "avg_position" in ranked.columns and ranked["avg_position"].notna().any():
        pos = ranked.groupby("date")["avg_position"].mean().rename("avg_position")
        out = out.merge(pos, on="date", how="left")
    else:
        out["avg_position"] = float("nan")
    cnt = ranked.groupby("date")["url"].nunique().rename("urls_ranking")
    out = out.merge(cnt, on="date", how="left")
    out["urls_ranking"] = out["urls_ranking"].fillna(0).astype(int)
    return out.sort_values("date").reset_index(drop=True)


def _dir(change, step):
    return 1 if change >= step else -1 if change <= -step else 0


def trend_status(agg: pd.DataFrame, gsc: dict | None = None) -> dict:
    """Compare first and last snapshot. Coarse on purpose.
    agg: Ahrefs aggregate (traffic estimate, top-3 keywords; position/top-10 only in old/demo data).
    gsc: optional measured Search Console numbers {pos_start, pos_now, top10_start, top10_now}; they supply the position
    and top-10 signals when Ahrefs does not carry them."""
    out = {"status": "unknown", "pos_start": None, "pos_now": None, "pos_change": None,
           "traffic_start": None, "traffic_now": None, "traffic_change": None,
           "top10_start": None, "top10_now": None, "top3_start": None, "top3_now": None}
    dirs = []
    a = b = None
    if agg is not None and not agg.empty:
        valid = agg[agg["urls_ranking"] > 0]
        if len(valid) >= 2:
            a, b = valid.iloc[0], valid.iloc[-1]
    if a is not None:
        t0, t1 = float(a["est_traffic"]), float(b["est_traffic"])
        out.update(traffic_start=t0, traffic_now=t1, date_start=a["date"], date_now=b["date"])
        if t0 > 0:
            out["traffic_change"] = t1 / t0 - 1.0
            dirs.append(_dir(out["traffic_change"], TRAFFIC_STEP))
        for c in ("top3", "top10"):
            if c in agg.columns and pd.notna(a[c]) and pd.notna(b[c]):
                out[f"{c}_start"], out[f"{c}_now"] = int(a[c]), int(b[c])
                if a[c] > 0:
                    dirs.append(_dir(b[c] / a[c] - 1.0, TRAFFIC_STEP))
        if pd.notna(a["avg_position"]) and pd.notna(b["avg_position"]):
            out.update(pos_start=float(a["avg_position"]), pos_now=float(b["avg_position"]))
    if gsc:
        if out["pos_start"] is None and gsc.get("pos_start") is not None and gsc.get("pos_now") is not None:
            out.update(pos_start=float(gsc["pos_start"]), pos_now=float(gsc["pos_now"]))
        if out["top10_start"] is None and gsc.get("top10_start") is not None:
            out.update(top10_start=int(gsc["top10_start"]), top10_now=int(gsc["top10_now"]))
            if gsc["top10_start"] > 0:
                dirs.append(_dir(gsc["top10_now"] / gsc["top10_start"] - 1.0, TRAFFIC_STEP))
    if out["pos_start"] is not None:
        out["pos_change"] = out["pos_start"] - out["pos_now"]           # positive = better (lower number)
        dirs.append(_dir(out["pos_change"], POSITION_STEP))
    if not dirs:
        return out
    # Careful wording: conflicting signals are "mixed", never a plain "declining".
    if any(d > 0 for d in dirs) and any(d < 0 for d in dirs):
        out["status"] = "mixed"
    elif any(d > 0 for d in dirs):
        out["status"] = "improving"
    elif any(d < 0 for d in dirs):
        out["status"] = "declining"
    else:
        out["status"] = "stable"
    return out


def per_url_table(history: dict) -> pd.DataFrame:
    """One row per page: first vs last snapshot of keywords, top-3 keywords and the Ahrefs traffic estimate."""
    rows = []
    for url, df in (history or {}).items():
        if df is None or df.empty:
            continue
        d = df.sort_values("date")
        a, b = d.iloc[0], d.iloc[-1]
        has3 = "top3" in d.columns and d["top3"].notna().any()
        t0, t1 = float(a["est_traffic"]), float(b["est_traffic"])
        rows.append({"Landing Page": url,
                     "Keywords start": int(a["keywords"]), "Keywords now": int(b["keywords"]),
                     "Top-3 start": int(a["top3"]) if has3 else None, "Top-3 now": int(b["top3"]) if has3 else None,
                     "Traffic start": t0, "Traffic now": t1, "Change": t1 - t0})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Change", ascending=False, na_position="last").reset_index(drop=True)
