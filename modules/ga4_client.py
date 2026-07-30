"""
Google Analytics 4 (GA4) Data API — revenue and conversions per landing page.
Uses the same service account as Sheets and Search Console: add it as a
Viewer in GA4 Admin → Property Access Management, then set the property ID
in config.json under "ga4".
"""
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
from modules.google_auth import get_credentials, credentials_configured

GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def get_ga4_property_id(config: dict, lang: str) -> str:
    """Supports either one property for the whole account, or one per language."""
    ga4_cfg = config.get("ga4", {})
    per_lang = ga4_cfg.get("property_ids", {})
    if per_lang.get(lang):
        return per_lang[lang]
    return ga4_cfg.get("property_id", "")


def ga4_available(config: dict, creds_file: str, lang: str = None) -> bool:
    if lang is not None:
        has_id = bool(get_ga4_property_id(config, lang))
    else:
        ga4_cfg = config.get("ga4", {})
        has_id = bool(ga4_cfg.get("property_id")) or any(ga4_cfg.get("property_ids", {}).values())
    return has_id and credentials_configured(creds_file)


@st.cache_data(ttl=21600, show_spinner=False)  # 6 hours
def get_revenue_by_page(creds_file: str, property_id: str, days: int = 90) -> pd.DataFrame:
    """Fetch revenue, conversions and sessions per landing page path from GA4."""
    if not property_id:
        return pd.DataFrame()
    try:
        from googleapiclient.discovery import build

        creds   = get_credentials(creds_file, GA4_SCOPES)
        service = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)

        body = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "dimensions": [{"name": "landingPagePlusQueryString"}],
            "metrics": [
                {"name": "totalRevenue"},
                {"name": "conversions"},
                {"name": "sessions"},
            ],
            "limit": 10000,
        }
        resp = service.properties().runReport(
            property=f"properties/{property_id}", body=body
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return pd.DataFrame()

        data = []
        for r in rows:
            path = r["dimensionValues"][0]["value"].split("?")[0]
            revenue, conversions, sessions = (float(m["value"]) for m in r["metricValues"])
            data.append({"path": path, "Revenue": revenue, "Conversions": conversions, "Sessions": sessions})
        return pd.DataFrame(data)
    except Exception:
        # Fail silently — e.g. the service account may not have been granted
        # access to this GA4 property yet. Degrade gracefully rather than
        # surface a raw API error to the client.
        return pd.DataFrame()


def merge_ga4_into_table(lp_table: pd.DataFrame, ga4_df: pd.DataFrame) -> pd.DataFrame:
    """Join GA4 revenue/conversions into the landing page table by matching URL path
    (GA4 only reports the path, not the full domain, so we compare on path)."""
    if ga4_df.empty or "Landing Page" not in lp_table.columns:
        return lp_table

    merged = lp_table.copy()
    merged["_path"] = merged["Landing Page"].apply(lambda u: urlparse(u).path.rstrip("/") or "/")

    ga4_slim = ga4_df.copy()
    ga4_slim["_path"] = ga4_slim["path"].apply(lambda p: p.rstrip("/") or "/")
    ga4_slim = ga4_slim.groupby("_path", as_index=False).agg(
        Revenue=("Revenue", "sum"), Conversions=("Conversions", "sum"), Sessions=("Sessions", "sum")
    )

    merged = merged.merge(ga4_slim[["_path", "Revenue", "Conversions", "Sessions"]], on="_path", how="left")
    merged = merged.drop(columns=["_path"])

    if "Total Cost (€)" in merged.columns and "Revenue" in merged.columns:
        merged["ROI"] = merged.apply(
            lambda r: (r["Revenue"] / r["Total Cost (€)"])
            if r["Total Cost (€)"] > 0 and pd.notna(r["Revenue"]) else None,
            axis=1,
        )
    return merged
