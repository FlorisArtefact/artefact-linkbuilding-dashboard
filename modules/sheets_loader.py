"""
Google Sheets loader using a service account.
Reads the same sheet structure as the Excel database.
"""
import streamlit as st
import pandas as pd
import os
from typing import Optional

# Lazy imports to avoid hard dependency when Sheets is not configured
def _get_service(creds_file: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    import streamlit as st

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    # Streamlit Cloud: credentials stored as secrets (wrapped in try/except
    # because st.secrets raises FileNotFoundError locally when no secrets.toml exists)
    try:
        cloud_creds = "gcp_service_account" in st.secrets
    except Exception:
        cloud_creds = False

    if cloud_creds:
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES
        )
    else:
        # Local: credentials JSON file on disk
        creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=SCOPES
        )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _sheet_to_df(service, spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    """Read a single sheet tab into a DataFrame."""
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=sheet_name,
                valueRenderOption="UNFORMATTED_VALUE",
                dateTimeRenderOption="FORMATTED_STRING",
            )
            .execute()
        )
        rows = result.get("values", [])
        if len(rows) < 2:
            return pd.DataFrame()
        headers = rows[0]
        data    = rows[1:]
        # Pad short rows so all rows have the same number of columns
        data = [row + [""] * (len(headers) - len(row)) for row in data]
        return pd.DataFrame(data, columns=headers)
    except Exception as e:
        st.warning(f"Could not load sheet '{sheet_name}': {e}")
        return pd.DataFrame()


def _normalise_live(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    """Apply same normalisation as the Excel data_loader."""
    if df.empty:
        return df
    df.columns = df.columns.str.strip()
    # Fix Price column encoding
    price_cols = [c for c in df.columns if "price" in c.lower() or "prijs" in c.lower()]
    if price_cols:
        df = df.rename(columns={price_cols[0]: "Price"})
    # Parse types
    if "LL Date" in df.columns:
        df["LL Date"] = pd.to_datetime(df["LL Date"], errors="coerce")
    for col in ["DA", "Price", "Q", "Year", "Status code"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Language"] = lang
    return df


def _normalise_opp(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    if df.empty:
        return df
    df.columns = df.columns.str.strip()
    price_cols = [c for c in df.columns if "price" in c.lower()]
    if price_cols:
        df = df.rename(columns={price_cols[0]: "Price"})
    for col in ["DR", "Price", "Q", "Referring Domains", "Organic Traffic ahrefs"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Language"] = lang
    return df


# Cache for 5 minutes so the dashboard stays up to date without hammering the API
@st.cache_data(ttl=300, show_spinner=False)
def load_live_links_sheets(creds_file: str, spreadsheet_id: str, lang: str) -> pd.DataFrame:
    service = _get_service(creds_file)
    df = _sheet_to_df(service, spreadsheet_id, f"Live_links_{lang}")
    return _normalise_live(df, lang)


@st.cache_data(ttl=300, show_spinner=False)
def load_opportunities_sheets(creds_file: str, spreadsheet_id: str, lang: str) -> pd.DataFrame:
    service = _get_service(creds_file)
    df = _sheet_to_df(service, spreadsheet_id, f"Opportunities_{lang}")
    return _normalise_opp(df, lang)


def sheets_available(config: dict) -> bool:
    """Return True if Google Sheets is configured — either via local JSON or Streamlit Cloud secrets."""
    sid = config.get("google_sheets", {}).get("spreadsheet_id", "")
    if not sid:
        return False

    # Streamlit Cloud: credentials are in st.secrets
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            return True
    except Exception:
        pass

    # Local: credentials JSON file on disk
    creds = config.get("google_sheets", {}).get("credentials_file", "")
    return bool(creds) and os.path.exists(creds)
