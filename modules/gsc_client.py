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
        # The client may have a URL-prefix property OR a Domain property (sc-domain:...). Try the
        # configured URL first, then the common variants, so nobody has to ask which one it is.
        from urllib.parse import urlparse
        host = urlparse(site_url).netloc.lower() if "://" in site_url else site_url.replace("sc-domain:", "")
        bare = host.removeprefix("www.")
        candidates = [site_url, f"sc-domain:{bare}", f"https://{bare}/", f"https://www.{bare}/"]
        resp = None
        for cand in dict.fromkeys(candidates):
            try:
                resp = service.searchanalytics().query(siteUrl=cand, body=body).execute()
                break
            except Exception:
                continue
        if resp is None:
            return pd.DataFrame()
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
        import io
        import zipfile
        if str(getattr(uploaded_file, "name", "")).lower().endswith(".zip"):
            # GSC's "Export → Download CSV" delivers a ZIP; take the pages table (Pages/Pagina's)
            with zipfile.ZipFile(uploaded_file) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                pick = next((n for n in names if "page" in n.lower() or "pagina" in n.lower()), None)
                if pick is None:
                    return pd.DataFrame()
                df = pd.read_csv(io.BytesIO(zf.read(pick)))
        else:
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


@st.cache_data(ttl=21600, show_spinner=False)
def get_gsc_monthly(creds_file: str, site_url: str, months: int = 16) -> pd.DataFrame:
    """Clicks / impressions / average position per month for the whole property (complete months only).
    Columns: month, Clicks, Impressions, Position."""
    if not site_url:
        return pd.DataFrame()
    try:
        from googleapiclient.discovery import build
        from urllib.parse import urlparse

        creds = get_credentials(creds_file, GSC_SCOPES)
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        end = datetime.now().date()
        start = (pd.Timestamp(end).replace(day=1) - pd.DateOffset(months=months)).date()
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": ["date"], "rowLimit": 25000}
        host = urlparse(site_url).netloc.lower() if "://" in site_url else site_url.replace("sc-domain:", "")
        bare = host.removeprefix("www.")
        resp = None
        for cand in dict.fromkeys([site_url, f"sc-domain:{bare}", f"https://{bare}/", f"https://www.{bare}/"]):
            try:
                resp = service.searchanalytics().query(siteUrl=cand, body=body).execute()
                break
            except Exception:
                continue
        rows = (resp or {}).get("rows", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([{"date": pd.Timestamp(r["keys"][0]), "Clicks": r["clicks"], "Impressions": r["impressions"],
                            "pos_w": r["position"] * r["impressions"]} for r in rows])
        df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
        g = df.groupby("month").agg(Clicks=("Clicks", "sum"), Impressions=("Impressions", "sum"), pos_w=("pos_w", "sum")).reset_index()
        g["Position"] = g["pos_w"] / g["Impressions"].where(g["Impressions"] > 0)
        g = g[g["month"] < pd.Timestamp(end).replace(day=1)]
        return g.drop(columns="pos_w")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=21600, show_spinner=False)  # 6 hours
def get_gsc_linked_summary(creds_file: str, site_url: str, urls: tuple, start: str, end: str) -> dict | None:
    """Measured Google performance of the pages that received links, for one period (ISO dates).
    Looks at every page + search query pair of those pages. Returns None without access / data.
    Keys: clicks, impressions, position (impression-weighted average), top10 (page+query pairs on positions 1-10), pairs.
    Note: Google hides rare (anonymised) queries, so counts are lower than a third-party keyword tool shows."""
    if not site_url or not urls:
        return None
    try:
        import re
        from urllib.parse import urlparse
        from googleapiclient.discovery import build

        creds = get_credentials(creds_file, GSC_SCOPES)
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        paths = sorted({(urlparse(str(u).strip()).path or "/").rstrip("/") or "/" for u in urls})
        chunks, cur, size = [], [], 0
        for p in paths:                                   # keep every regex well below the API's size limit
            esc = re.escape(p if p != "/" else "")
            if size + len(esc) > 2500 and cur:
                chunks.append(cur); cur, size = [], 0
            cur.append(esc); size += len(esc) + 1
        if cur:
            chunks.append(cur)
        host = urlparse(site_url).netloc.lower() if "://" in site_url else site_url.replace("sc-domain:", "")
        bare = host.removeprefix("www.")
        site = None
        rows = []
        for cand in dict.fromkeys([site_url, f"sc-domain:{bare}", f"https://{bare}/", f"https://www.{bare}/"]):
            try:
                rows = []
                for ch in chunks:
                    pattern = r"^https?://[^/]+(" + "|".join(ch) + r")/?$"
                    start_row = 0
                    while True:
                        body = {"startDate": start, "endDate": end, "dimensions": ["page", "query"], "rowLimit": 25000,
                                "startRow": start_row,
                                "dimensionFilterGroups": [{"filters": [{"dimension": "page", "operator": "includingRegex",
                                                                         "expression": pattern}]}]}
                        resp = service.searchanalytics().query(siteUrl=cand, body=body).execute()
                        got = resp.get("rows", [])
                        rows += got
                        if len(got) < 25000 or start_row > 100000:
                            break
                        start_row += 25000
                site = cand
                break
            except Exception:
                continue
        if site is None:
            return None
        if not rows:
            return {"clicks": 0.0, "impressions": 0.0, "position": None, "top10": 0, "pairs": 0}
        d = pd.DataFrame([{"clicks": r["clicks"], "impr": r["impressions"], "pos": r["position"]} for r in rows])
        impr = float(d["impr"].sum())
        return {"clicks": float(d["clicks"].sum()), "impressions": impr,
                "position": float((d["pos"] * d["impr"]).sum() / impr) if impr > 0 else None,
                "top10": int((d["pos"] <= 10).sum()), "pairs": int(len(d))}
    except Exception:
        return None
