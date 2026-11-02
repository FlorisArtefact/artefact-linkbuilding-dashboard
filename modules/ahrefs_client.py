from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


AHREFS_BASE = "https://api.ahrefs.com/v3"


class AhrefsClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.today = datetime.now().strftime("%Y-%m-%d")

    def _get(self, endpoint: str, params: dict, strict: bool = False) -> Optional[dict]:
        """GET with retries on rate limits (429) and server errors. strict=True raises when it still fails, so callers
        wrapped in st.cache_data do not cache a failure as if it were 'no data'."""
        import time
        # Only set today as default if no date is explicitly provided
        params.setdefault("date", self.today)
        last = None
        for attempt in range(6):
            try:
                resp = requests.get(
                    f"{AHREFS_BASE}/{endpoint}",
                    headers=self.headers,
                    params=params,
                    timeout=25,
                )
                if resp.status_code == 200:
                    return resp.json()
                last = f"HTTP {resp.status_code}"
                if resp.status_code not in (429, 500, 502, 503, 504):
                    break                                   # e.g. 4xx: retrying will not help
                time.sleep(float(resp.headers.get("Retry-After", 0)) or 4 * (attempt + 1))
            except Exception as e:                          # network hiccup
                last = type(e).__name__
                time.sleep(2 * (attempt + 1))
        if strict:
            raise RuntimeError(f"Ahrefs request failed ({last})")
        return None

    def _clean_url(self, url: str) -> str:
        return url.replace("https://", "").replace("http://", "").rstrip("/")

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_domain_metrics(_self, domain: str) -> dict:
        data = _self._get("site-explorer/metrics", {"target": domain, "mode": "domain"})
        return data.get("metrics", {}) if data else {}

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_domain_rating(_self, domain: str) -> Optional[float]:
        data = _self._get("site-explorer/domain-rating", {"target": domain})
        if data and "domain_rating" in data:
            return data["domain_rating"].get("domain_rating")
        return None

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_url_keywords(_self, url: str, limit: int = 50) -> list:
        data = _self._get(
            "site-explorer/organic-keywords",
            {
                "target": _self._clean_url(url),
                "mode": "exact",
                "select": "keyword,best_position,volume,sum_traffic",
                "limit": limit,
                "order_by": "sum_traffic:desc",
            },
        )
        return data.get("keywords", []) if data else []

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_url_keywords_at_date(_self, url: str, date: str, limit: int = 200) -> list:
        """Fetch organic keyword rankings for a URL at a specific historical date."""
        data = _self._get(
            "site-explorer/organic-keywords",
            {
                "target": _self._clean_url(url),
                "mode": "exact",
                "date": date,
                "select": "keyword,best_position,sum_traffic",
                "limit": limit,
            },
            strict=True,
        )
        return data.get("keywords", []) if data else []

    def get_position_history(self, url: str, months: int = 6) -> pd.DataFrame:
        """
        Build a monthly position history by querying Ahrefs at N monthly snapshots.
        Returns a DataFrame with columns: date, avg_position, top_position,
        keywords, est_traffic.
        """
        records = []
        # The monthly snapshots are independent -> fetch them in parallel (was sequential: ~6x slower)
        dates = [(datetime.now() - timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(months)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            kw_lists = list(pool.map(lambda d: self.get_url_keywords_at_date(url, d), dates))
        for snapshot_date, keywords in zip(dates, kw_lists):
            if keywords:
                positions = [kw["best_position"] for kw in keywords if kw.get("best_position")]
                traffic = sum(kw.get("sum_traffic", 0) for kw in keywords)
                records.append({
                    "date": pd.to_datetime(snapshot_date),
                    "avg_position": round(sum(positions) / len(positions), 1) if positions else None,
                    "top_position": min(positions) if positions else None,
                    "keywords": len(positions),
                    "est_traffic": traffic,
                })
            else:
                records.append({
                    "date": pd.to_datetime(snapshot_date),
                    "avg_position": None,
                    "top_position": None,
                    "keywords": 0,
                    "est_traffic": 0,
                })

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
        return df

    def get_snapshot_history(self, url: str, months: int = 6) -> pd.DataFrame:
        """Monthly snapshots (months+1 points, oldest first): avg position, keyword count, top-10 count, est. traffic.
        Reuses the cached keyword snapshots of get_position_history."""
        rows = []
        snaps = [(datetime.now() - timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(months + 1)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            kw_lists = list(pool.map(lambda d: self.get_url_keywords_at_date(url, d), snaps))
        for snap, kws in zip(snaps, kw_lists):
            pos = [k["best_position"] for k in kws if k.get("best_position")]
            rows.append({
                "date": pd.to_datetime(snap),
                "avg_position": round(sum(pos) / len(pos), 1) if pos else None,
                "keywords": len(pos), "top10": sum(1 for p in pos if p <= 10),
                "est_traffic": sum(k.get("sum_traffic", 0) or 0 for k in kws),
            })
        return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    def get_landing_page_metrics(self, url: str) -> dict:
        keywords = self.get_url_keywords(url)
        if not keywords:
            return {"avg_position": None, "top_position": None, "est_traffic": 0, "keywords": 0}
        positions = [kw["best_position"] for kw in keywords if kw.get("best_position")]
        traffic = sum(kw.get("sum_traffic", 0) for kw in keywords)
        return {
            "avg_position": round(sum(positions) / len(positions), 1) if positions else None,
            "top_position": min(positions) if positions else None,
            "est_traffic": traffic,
            "keywords": len(keywords),
        }

    def enrich_landing_pages(self, urls: list) -> dict:
        with ThreadPoolExecutor(max_workers=6) as pool:
            return dict(zip(urls, pool.map(self.get_landing_page_metrics, urls)))


@st.cache_data(ttl=21600, show_spinner=False)
def get_domain_history(api_key: str, domain: str, months: int = 24) -> pd.DataFrame:
    """Monthly Domain Rating, referring domains and Ahrefs organic-traffic estimate for the whole domain.
    Columns: month, DR, Refdomains, OrgTraffic. Works without GA4/GSC, for every market."""
    from concurrent.futures import ThreadPoolExecutor
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    start = (pd.Timestamp.today().replace(day=1) - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    base = {"target": domain, "date_from": start, "date_to": pd.Timestamp.today().strftime("%Y-%m-%d"), "history_grouping": "monthly"}

    def call(ep_key):
        ep, extra = ep_key
        try:
            r = requests.get(f"{AHREFS_BASE}/site-explorer/{ep}", headers=headers, params={**base, **extra}, timeout=30)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=3) as ex:
        dr, rd, mt = ex.map(call, [("domain-rating-history", {}), ("refdomains-history", {}),
                                   ("metrics-history", {"select": "date,org_traffic"})])
    frames = []
    for key, col, js in (("domain_ratings", "DR", dr), ("refdomains", "Refdomains", rd), ("metrics", "OrgTraffic", mt)):
        rows = js.get(key, [])
        if rows:
            f = pd.DataFrame(rows)
            f["month"] = pd.to_datetime(f["date"]).dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
            src = {"DR": "domain_rating", "Refdomains": "refdomains", "OrgTraffic": "org_traffic"}[col]
            frames.append(f.set_index("month")[[src]].rename(columns={src: col}))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).reset_index().sort_values("month")
