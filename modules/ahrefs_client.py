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

    def _get(self, endpoint: str, params: dict) -> Optional[dict]:
        # Only set today as default if no date is explicitly provided
        params.setdefault("date", self.today)
        try:
            resp = requests.get(
                f"{AHREFS_BASE}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=25,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
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
        )
        return data.get("keywords", []) if data else []

    def get_position_history(self, url: str, months: int = 6) -> pd.DataFrame:
        """
        Build a monthly position history by querying Ahrefs at N monthly snapshots.
        Returns a DataFrame with columns: date, avg_position, top_position,
        keywords, est_traffic.
        """
        records = []
        for i in range(months):
            snapshot_dt = datetime.now() - timedelta(days=30 * i)
            snapshot_date = snapshot_dt.strftime("%Y-%m-%d")
            keywords = self.get_url_keywords_at_date(url, snapshot_date)
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
        return {url: self.get_landing_page_metrics(url) for url in urls}
