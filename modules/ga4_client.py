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
def get_revenue_by_page(creds_file: str, property_id: str, days: int = 90, organic_only: bool = True,
                        hostname: str = "", start_date: str = "", end_date: str = "") -> pd.DataFrame:
    """Fetch revenue, conversions and sessions per landing page path from GA4.

    start_date / end_date (ISO) select an exact period; without them the last `days` days are used.
    organic_only=True restricts to the 'Organic Search' channel group — required for a fair
    link-building ROI (paid/direct/email revenue on the same page is not caused by links)."""
    if not property_id:
        return pd.DataFrame()
    try:
        from googleapiclient.discovery import build

        creds   = get_credentials(creds_file, GA4_SCOPES)
        service = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)

        body = {
            "dateRanges": [{"startDate": start_date or f"{days}daysAgo", "endDate": end_date or "today"}],
            "dimensions": [{"name": "landingPage"}],
            "metrics": [
                {"name": "totalRevenue"},
                {"name": "conversions"},
                {"name": "sessions"},
            ],
            "limit": 100000,
        }
        filters = []
        if organic_only:
            filters.append({"filter": {
                "fieldName": "sessionDefaultChannelGroup",
                "stringFilter": {"matchType": "EXACT", "value": "Organic Search"},
            }})
        if hostname:   # one GA4 property shared by several domains -> only this market's domain
            filters.append({"filter": {
                "fieldName": "hostName",
                "stringFilter": {"matchType": "CONTAINS", "value": hostname.removeprefix("www.")},
            }})
        if len(filters) == 1:
            body["dimensionFilter"] = filters[0]
        elif filters:
            body["dimensionFilter"] = {"andGroup": {"expressions": filters}}
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


@st.cache_data(ttl=21600, show_spinner=False)  # 6 hours
def get_monthly_revenue_by_page(creds_file: str, property_id: str, months: int = 36, organic_only: bool = True,
                                hostname: str = "", paths: tuple = ()) -> pd.DataFrame:
    """Monthly organic revenue/sessions per landing page (for growth analysis).
    Columns: month (first day), path, Revenue, Sessions.

    Fast path: when `paths` (the pages that received links) is given, only those pages are fetched per month, plus the
    domain total; everything else is returned as one row '(other pages)' = total - linked pages. So the table still sums to the
    domain total, but needs a few hundred rows instead of >100,000. Without `paths` all pages are fetched (paged)."""
    if not property_id:
        return pd.DataFrame()
    try:
        from datetime import date
        from googleapiclient.discovery import build

        creds   = get_credentials(creds_file, GA4_SCOPES)
        service = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)
        start = (pd.Timestamp(date.today()).replace(day=1) - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
        base_filters = []
        if organic_only:
            base_filters.append({"filter": {"fieldName": "sessionDefaultChannelGroup",
                                            "stringFilter": {"matchType": "EXACT", "value": "Organic Search"}}})
        if hostname:
            base_filters.append({"filter": {"fieldName": "hostName",
                                            "stringFilter": {"matchType": "CONTAINS", "value": hostname.removeprefix("www.")}}})

        def run(dims, extra_filters, page=100000):
            out, offset = [], 0
            while offset < 1_000_000:
                flt = base_filters + extra_filters
                body = {"dateRanges": [{"startDate": start, "endDate": "today"}],
                        "dimensions": [{"name": d} for d in dims],
                        "metrics": [{"name": "totalRevenue"}, {"name": "sessions"}], "limit": page, "offset": offset}
                if len(flt) == 1:
                    body["dimensionFilter"] = flt[0]
                elif flt:
                    body["dimensionFilter"] = {"andGroup": {"expressions": flt}}
                rows = service.properties().runReport(property=f"properties/{property_id}", body=body).execute().get("rows", [])
                out += rows
                if len(rows) < page:
                    break
                offset += page
            return out

        def to_df(rows, with_path=True):
            return pd.DataFrame([{"month": pd.to_datetime(r["dimensionValues"][0]["value"] + "01", format="%Y%m%d"),
                                  "path": (r["dimensionValues"][1]["value"].split("?")[0] if with_path else "(all)"),
                                  "Revenue": float(r["metricValues"][0]["value"]), "Sessions": float(r["metricValues"][1]["value"])}
                                 for r in rows])

        if not paths:
            return to_df(run(["yearMonth", "landingPage"], []))
        variants = sorted({v for p in paths for v in (p, p.rstrip("/") or "/", (p.rstrip("/") + "/"))})
        linked = to_df(run(["yearMonth", "landingPage"], [{"filter": {"fieldName": "landingPage",
                                                                       "inListFilter": {"values": variants}}}]))
        total = to_df(run(["yearMonth"], []), with_path=False)
        if total.empty:
            return linked
        sums = linked.groupby("month")[["Revenue", "Sessions"]].sum() if not linked.empty else pd.DataFrame(columns=["Revenue", "Sessions"])
        rest = total.set_index("month")[["Revenue", "Sessions"]].sub(sums, fill_value=0).clip(lower=0).reset_index()
        rest["path"] = "(other pages)"
        return pd.concat([linked, rest], ignore_index=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=21600, show_spinner=False)  # 6 hours
def get_referral_traffic(creds_file: str, property_id: str, days: int = 180, hostname: str = "",
                         start_date: str = "", end_date: str = "") -> pd.DataFrame:
    """Sessions/revenue/conversions arriving via referral (other sites linking to us).
    Columns: referrer (full referring page URL when GA4 has it), source (domain), Sessions, Revenue, Conversions."""
    if not property_id:
        return pd.DataFrame()
    try:
        from googleapiclient.discovery import build

        creds   = get_credentials(creds_file, GA4_SCOPES)
        service = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)
        filters = [{"filter": {"fieldName": "sessionMedium", "stringFilter": {"matchType": "EXACT", "value": "referral"}}}]
        if hostname:
            filters.append({"filter": {"fieldName": "hostName",
                                       "stringFilter": {"matchType": "CONTAINS", "value": hostname.removeprefix("www.")}}})
        body = {
            "dateRanges": [{"startDate": start_date or f"{days}daysAgo", "endDate": end_date or "today"}],
            "dimensions": [{"name": "pageReferrer"}, {"name": "sessionSource"}],
            "metrics": [{"name": "sessions"}, {"name": "totalRevenue"}, {"name": "conversions"}],
            "dimensionFilter": {"andGroup": {"expressions": filters}} if len(filters) > 1 else filters[0],
            "limit": 25000,
        }
        resp = service.properties().runReport(property=f"properties/{property_id}", body=body).execute()
        data = [{"referrer": r["dimensionValues"][0]["value"], "source": r["dimensionValues"][1]["value"],
                 "Sessions": float(r["metricValues"][0]["value"]), "Revenue": float(r["metricValues"][1]["value"]),
                 "Conversions": float(r["metricValues"][2]["value"])} for r in resp.get("rows", [])]
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def load_ga4_csv(uploaded_file) -> pd.DataFrame:
    """Fallback while the service account has no GA4 access: parse a GA4 report export (CSV).

    Expected columns (names may vary slightly per GA4 UI language/version):
      landing page (+ query string), [session default channel group], sessions,
      key events / conversions, total revenue. Rows are filtered to 'Organic Search' when the
      channel column is present. Same schema as get_revenue_by_page(); assumes a 90-day export."""
    try:
        import io
        text = uploaded_file.getvalue().decode("utf-8-sig", errors="replace")
        body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
        df = pd.read_csv(io.StringIO(body))
        df.columns = [str(c).strip() for c in df.columns]
        low = {c: c.lower() for c in df.columns}
        page = next((c for c, l in low.items() if "landing" in l or "page" in l), None)
        chan = next((c for c, l in low.items() if "channel" in l), None)
        rev = next((c for c, l in low.items() if "revenue" in l), None)
        conv = next((c for c, l in low.items() if "key event" in l or "conversion" in l), None)
        sess = next((c for c, l in low.items() if "session" in l and "channel" not in l and "conversion" not in l), None)
        if page is None:
            return pd.DataFrame()
        if chan is not None:
            df = df[df[chan].astype(str).str.strip().str.lower() == "organic search"]

        def num(col):
            if col is None:
                return pd.Series(0.0, index=df.index)
            # GA4 CSV exports use en-US numbers (1,234.56); drop thousand separators and symbols
            s = df[col].astype(str).str.replace(r"[^\d.\-]", "", regex=True)
            return pd.to_numeric(s, errors="coerce").fillna(0.0)

        out = pd.DataFrame({
            "path": df[page].astype(str).str.split("?").str[0],
            "Revenue": num(rev), "Conversions": num(conv), "Sessions": num(sess),
        })
        return out.groupby("path", as_index=False).sum(numeric_only=True)
    except Exception:
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
