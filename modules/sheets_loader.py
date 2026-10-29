"""
Google Sheets loader using a service account.
Reads the same sheet structure as the Excel database.
"""
import streamlit as st
import pandas as pd
from modules.google_auth import get_credentials, credentials_configured

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _get_service(creds_file: str):
    from googleapiclient.discovery import build

    creds = get_credentials(creds_file, SHEETS_SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _unique_headers(headers: list) -> list:
    """Duplicate column names (e.g. two 'LL Date' columns) become 'LL Date', 'LL Date.1' so nothing is lost."""
    seen, out = {}, []
    for h in headers:
        h = str(h).strip()
        n = seen.get(h, 0)
        seen[h] = n + 1
        out.append(h if n == 0 else f"{h}.{n}")
    return out


def _coalesce_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Merge 'X.1', 'X.2' into 'X' taking the first non-empty value (blank strings count as empty)."""
    for col in [c for c in df.columns if "." in c and c.rsplit(".", 1)[-1].isdigit()]:
        base = col.rsplit(".", 1)[0]
        if base in df.columns:
            a = df[base].replace("", pd.NA)
            df[base] = a.fillna(df[col].replace("", pd.NA)).fillna("")
            df = df.drop(columns=[col])
    return df


def _tab_names(config_tpl: str, default_tpl: str, lang: str) -> list:
    """Tab name candidates: configured template first, then the usual variants (underscore / space)."""
    out = []
    for t in (config_tpl, default_tpl, default_tpl.replace("_", " ")):
        if t:
            n = t.format(lang=lang)
            if n not in out:
                out.append(n)
    return out


def _sheet_to_df(service, spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    """Read a single sheet tab into a DataFrame. Silently returns empty if the
    tab doesn't exist yet (e.g. a language not yet added) — only real errors warn."""
    from googleapiclient.errors import HttpError

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
        headers = _unique_headers(rows[0])
        data    = rows[1:]
        data = [row + [""] * (len(headers) - len(row)) for row in data]
        return pd.DataFrame(data, columns=headers)
    except HttpError as e:
        if e.resp.status == 400 and "Unable to parse range" in str(e):
            # Tab doesn't exist yet (e.g. FR/ES not added to the sheet yet) — expected, stay silent
            return pd.DataFrame()
        st.warning(f"Could not load sheet '{sheet_name}': {e}")
        return pd.DataFrame()
    except Exception as e:
        st.warning(f"Could not load sheet '{sheet_name}': {e}")
        return pd.DataFrame()


def _normalise_live(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    """Apply same normalisation as the Excel data_loader."""
    if df.empty:
        return df
    df.columns = df.columns.str.strip()
    df = _coalesce_duplicates(df)
    price_cols = [c for c in df.columns if "price" in c.lower() or "prijs" in c.lower()]
    if price_cols:
        df = df.rename(columns={price_cols[0]: "Price"})
    if "LL Date" in df.columns:
        df["LL Date"] = pd.to_datetime(df["LL Date"], errors="coerce")
    for col in ["DA", "Price", "Q", "Year", "Status code"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Link Type" in df.columns:      # 'Follow' / 'dofollow' / 'Nofollow' -> the two labels the dashboard uses
        lt = df["Link Type"].astype(str).str.strip().str.lower()
        df["Link Type"] = lt.map(lambda v: "Nofollow" if v.startswith(("no", "sponsored", "ugc")) else
                                 ("Dofollow" if "follow" in v else df.get("Link Type", v)))
        df.loc[lt.isin(["", "n/a", "nan"]), "Link Type"] = lt[lt.isin(["", "n/a", "nan"])].replace("", "n/a")
    if "Domain" in df.columns:
        df["Domain"] = df["Domain"].astype(str).replace({"nan": ""})
    df["Language"] = lang
    return df


def _normalise_opp(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    if df.empty:
        return df
    df.columns = df.columns.str.strip()
    df = _coalesce_duplicates(df)
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
def load_live_links_sheets(creds_file: str, spreadsheet_id: str, lang: str, tab_template: str = "") -> pd.DataFrame:
    service = _get_service(creds_file)
    for name in _tab_names(tab_template, "Live_links_{lang}", lang):
        df = _sheet_to_df(service, spreadsheet_id, name)
        if not df.empty:
            return _normalise_live(df, lang)
    return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_opportunities_sheets(creds_file: str, spreadsheet_id: str, lang: str, tab_template: str = "") -> pd.DataFrame:
    service = _get_service(creds_file)
    for name in _tab_names(tab_template, "Opportunities_{lang}", lang):
        df = _sheet_to_df(service, spreadsheet_id, name)
        if not df.empty:
            return _normalise_opp(df, lang)
    return pd.DataFrame()


def sheets_available(config: dict) -> bool:
    """Return True if Google Sheets is configured — either via local JSON or Streamlit Cloud secrets."""
    sid = config.get("google_sheets", {}).get("spreadsheet_id", "")
    if not sid:
        return False
    creds = config.get("google_sheets", {}).get("credentials_file", "")
    return credentials_configured(creds)
