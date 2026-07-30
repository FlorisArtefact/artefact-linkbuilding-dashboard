import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from modules.google_auth import get_credentials, credentials_configured

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def gsc_api_available(config: dict, creds_file: str) -> bool:
    """True if a service account is configured AND at least one GSC property URL is set."""
    site_urls = config.get("gsc_properties", {})
    return credentials_configured(creds_file) and any(v for v in site_urls.values())


@st.cache_data(ttl=21600, show_spinner=False)  # 6 hours — GSC data itself lags ~2-3 days anyway
def get_gsc_data_api(creds_file: str, site_url: str, days: int = 90) -> pd.DataFrame:
    """Fetch per-page clicks/impressions/CTR/position directly from the Search Console API.
    No manual export needed — this replaces the CSV upload entirely once configured."""
    if not site_url:
        return pd.DataFrame()
    try:
        from googleapiclient.discovery import build

        creds   = get_credentials(creds_file, GSC_SCOPES)
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

        end   = datetime.now().date()
        start = end - timedelta(days=days)
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["page"],
            "rowLimit": 25000,
        }
        resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        rows = resp.get("rows", [])
        if not rows:
            return pd.DataFrame()

        data = [{
            "Page": r["keys"][0],
            "Clicks": r.get("clicks", 0),
            "Impressions": r.get("impressions", 0),
            "CTR": r.get("ctr", 0),
            "Avg Position": r.get("position", 0),
        } for r in rows]
        return pd.DataFrame(data)
    except Exception:
        # Fail silently — e.g. the service account may not have been granted
        # access to this property yet. Same pattern as the Ahrefs client:
        # degrade gracefully rather than surface a raw API error to the client.
        return pd.DataFrame()


def load_gsc_csv(uploaded_file) -> pd.DataFrame:
    """Parse a GSC performance export (Pages view) CSV — fallback when the API isn't configured."""
    try:
        df = pd.read_csv(uploaded_file)
        df.columns = df.columns.str.strip()
        rename_map = {}
        for col in df.columns:
            low = col.lower()
            if "page" in low or "query" in low or "url" in low:
                rename_map[col] = "Page"
            elif "click" in low:
                rename_map[col] = "Clicks"
            elif "impression" in low:
                rename_map[col] = "Impressions"
            elif "ctr" in low:
                rename_map[col] = "CTR"
            elif "position" in low:
                rename_map[col] = "Avg Position"
        df = df.rename(columns=rename_map)
        if "Avg Position" in df.columns:
            df["Avg Position"] = pd.to_numeric(df["Avg Position"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def merge_gsc_into_table(lp_table: pd.DataFrame, gsc_df: pd.DataFrame) -> pd.DataFrame:
    """Join GSC position data into landing page summary table. Same schema for
    both the API path and the CSV fallback, so this function needs no changes either way."""
    if gsc_df.empty or "Page" not in gsc_df.columns or "Avg Position" not in gsc_df.columns:
        return lp_table
    gsc_slim = gsc_df[["Page", "Avg Position", "Clicks", "Impressions"]].copy()
    gsc_slim.columns = ["Landing Page", "GSC Position", "GSC Clicks", "GSC Impressions"]
    gsc_slim = gsc_slim.groupby("Landing Page", as_index=False).mean(numeric_only=True)
    merged = lp_table.merge(gsc_slim, on="Landing Page", how="left")
    return merged
