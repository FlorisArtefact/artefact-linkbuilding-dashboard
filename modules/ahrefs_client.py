from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from modules import ahrefs_guard as guard
from modules.ahrefs_guard import AhrefsBlocked  # noqa: F401  (re-exported for the UI)


AHREFS_BASE = "https://api.ahrefs.com/v3"
KW_LIMIT = 100          # rows per snapshot request; Ahrefs charges per row returned, so keep it small


def _week_start() -> str:
    """Monday of this week: 'now' snapshots keep the same cache key for a whole week."""
    t = datetime.now()
    return (t - timedelta(days=t.weekday())).strftime("%Y-%m-%d")


def _month_start(months_ago: int) -> str:
    d = pd.Timestamp.today().normalize().replace(day=1) - pd.DateOffset(months=months_ago)
    return d.strftime("%Y-%m-%d")


def snapshot_dates(months: int) -> list:
    """Two points only: the start of the look-back and now. Every extra point is a full request per page."""
    return [_month_start(months), _week_start()]


def guarded_get(api_key: str, endpoint: str, params: dict, timeout: int = 25) -> dict:
    """One Ahrefs GET: disk cache first, then at most 2 real attempts. Never retries a rate limit/credit error;
    it trips the circuit breaker instead. Raises RuntimeError (AhrefsBlocked) when it cannot deliver."""
    cached = guard.cache_get(endpoint, params)
    if cached is not None:
        return cached
    last = None
    for _attempt in range(2):
        guard.check_allowed()
        guard.register_call()
        try:
            resp = requests.get(f"{AHREFS_BASE}/{endpoint}", headers={"Authorization": f"Bearer {api_key}"},
                                params=params, timeout=timeout)
        except Exception as e:                      # network hiccup
            last = type(e).__name__
            continue
        if resp.status_code == 200:
            data = resp.json()
            guard.cache_put(endpoint, params, data)
            return data
        last = f"HTTP {resp.status_code}"
        if resp.status_code in (401, 402, 403, 429):
            guard.trip(last)
            raise AhrefsBlocked(f"Ahrefs refused the request ({last}: rate limit or out of credits). "
                                f"All Ahrefs calls are paused for {guard.BREAKER_MINUTES} minutes.")
        if resp.status_code not in (500, 502, 503, 504):
            break
    raise RuntimeError(f"Ahrefs request failed ({last})")


class AhrefsClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.today = _week_start()

    def _get(self, endpoint: str, params: dict, strict: bool = True) -> dict:
        params.setdefault("date", self.today)
        return guarded_get(self.api_key, endpoint, params)

    def _clean_url(self, url: str) -> str:
        return url.replace("https://", "").replace("http://", "").rstrip("/")

    # ── request definitions (shared by the fetchers and the 'how many requests?' counters) ──
    def _kw_at_date(self, url: str, date: str) -> tuple:
        return "site-explorer/organic-keywords", {
            "target": self._clean_url(url), "mode": "exact", "date": date,
            "select": "keyword,best_position,sum_traffic", "limit": KW_LIMIT, "order_by": "sum_traffic:desc"}

    def _kw_now(self, url: str, limit: int = 50) -> tuple:
        return "site-explorer/organic-keywords", {
            "target": self._clean_url(url), "mode": "exact", "date": self.today,
            "select": "keyword,best_position,volume,sum_traffic", "limit": limit, "order_by": "sum_traffic:desc"}

    # ── counters: real requests still needed (stored results are free) ──
    def pending_snapshots(self, urls, months: int) -> int:
        return sum(1 for u in set(urls) for d in snapshot_dates(months) if not guard.cache_has(*self._kw_at_date(u, d)))

    def pending_position_history(self, url: str, months: int) -> int:
        return sum(1 for d in self._monthly_dates(months) if not guard.cache_has(*self._kw_at_date(url, d)))

    def pending_landing(self, urls) -> int:
        return sum(1 for u in set(urls) if not guard.cache_has(*self._kw_now(u)))

    # ── single calls ──
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
        ep, params = _self._kw_now(url, limit)
        return _self._get(ep, params).get("keywords", [])

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_url_keywords_at_date(_self, url: str, date: str, limit: int = KW_LIMIT) -> list:
        """Organic keyword rankings for a URL at a specific historical date."""
        ep, params = _self._kw_at_date(url, date)
        return _self._get(ep, params).get("keywords", [])

    @staticmethod
    def _monthly_dates(months: int) -> list:
        return [_month_start(i) for i in range(months)]

    def get_position_history(self, url: str, months: int = 6) -> pd.DataFrame:
        """Monthly position history for one page (page deep-dive): one request per month, stored afterwards.
        Columns: date, avg_position, top_position, keywords, est_traffic."""
        dates = self._monthly_dates(months)
        records = []
        for snapshot_date in dates:                  # sequential: stops at the first refusal
            keywords = self.get_url_keywords_at_date(url, snapshot_date)
            positions = [kw["best_position"] for kw in keywords if kw.get("best_position")]
            records.append({
                "date": pd.to_datetime(snapshot_date),
                "avg_position": round(sum(positions) / len(positions), 1) if positions else None,
                "top_position": min(positions) if positions else None,
                "keywords": len(positions),
                "est_traffic": sum(kw.get("sum_traffic", 0) or 0 for kw in keywords),
            })
        return pd.DataFrame(records).sort_values("date").reset_index(drop=True) if records else pd.DataFrame()

    def get_snapshot_history(self, url: str, months: int = 6) -> pd.DataFrame:
        """Two snapshots (start of look-back, now): avg position, keyword count, top-10 count, est. traffic."""
        rows = []
        for snap in snapshot_dates(months):
            kws = self.get_url_keywords_at_date(url, snap)
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
        return {u: self.get_landing_page_metrics(u) for u in urls}      # sequential: stops at the first refusal


# ── domain history (Effect tab) ──
def _domain_history_calls(domain: str, months: int):
    start = (pd.Timestamp.today().replace(day=1) - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    base = {"target": domain, "date_from": start, "date_to": _week_start(), "history_grouping": "monthly"}
    return [("domain-rating-history", {}), ("refdomains-history", {}), ("metrics-history", {"select": "date,org_traffic"})], base


def pending_domain_history(domains, months: int = 24) -> int:
    n = 0
    for d in set(domains):
        eps, base = _domain_history_calls(d, months)
        n += sum(1 for ep, extra in eps if not guard.cache_has(f"site-explorer/{ep}", {**base, **extra}))
    return n


def get_domain_history(api_key: str, domain: str, months: int = 24) -> pd.DataFrame:
    """Monthly Domain Rating, referring domains and Ahrefs organic-traffic estimate for the whole domain.
    Columns: month, DR, Refdomains, OrgTraffic. 3 requests, stored afterwards. Raises when Ahrefs refuses."""
    eps, base = _domain_history_calls(domain, months)
    dr, rd, mt = [guarded_get(api_key, f"site-explorer/{ep}", {**base, **extra}, timeout=30) for ep, extra in eps]
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
