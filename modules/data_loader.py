import pandas as pd
import streamlit as st


@st.cache_data(show_spinner=False)
def load_live_links(source, lang: str) -> pd.DataFrame:
    sheet = f"Live_links_{lang}"
    try:
        df = pd.read_excel(source, sheet_name=sheet)
        df.columns = df.columns.str.strip()
        # Normalize Price column (encoding may vary)
        price_cols = [c for c in df.columns if "price" in c.lower() or "prijs" in c.lower()]
        if price_cols:
            df = df.rename(columns={price_cols[0]: "Price"})
        # Parse dates
        if "LL Date" in df.columns:
            df["LL Date"] = pd.to_datetime(df["LL Date"], errors="coerce")
        # Numeric coercion
        for col in ["DA", "Price", "Q", "Year", "Status code"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Language"] = lang
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_opportunities(source, lang: str) -> pd.DataFrame:
    sheet = f"Opportunities_{lang}"
    try:
        df = pd.read_excel(source, sheet_name=sheet)
        df.columns = df.columns.str.strip()
        price_cols = [c for c in df.columns if "price" in c.lower()]
        if price_cols:
            df = df.rename(columns={price_cols[0]: "Price"})
        for col in ["DR", "Price", "Q", "Referring Domains", "Organic Traffic ahrefs"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Language"] = lang
        return df
    except Exception:
        return pd.DataFrame()


def apply_filters(df: pd.DataFrame, year=None, quarter=None, campaign=None) -> pd.DataFrame:
    if df.empty:
        return df
    if year and "Year" in df.columns:
        df = df[df["Year"] == year]
    if quarter and "Q" in df.columns:
        df = df[df["Q"] == int(quarter[1])]
    if campaign and "Target campaign" in df.columns:
        df = df[df["Target campaign"].str.contains(campaign, case=False, na=False)]
    return df


def get_landing_page_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Link to" not in df.columns:
        return pd.DataFrame()
    grp = df.groupby("Link to").agg(
        Links=("Live Link", "count"),
        Total_Cost=("Price", "sum"),
        Avg_DA=("DA", "mean"),
        Dofollow=("Link Type", lambda x: (x == "Dofollow").sum()),
        Live_200=("Status code", lambda x: (x == 200).sum()),
    ).reset_index()
    grp.columns = ["Landing Page", "# Links", "Total Cost (€)", "Avg DA", "Dofollow", "Live (200)"]
    grp["Avg DA"] = grp["Avg DA"].round(1)
    grp["Total Cost (€)"] = grp["Total Cost (€)"].round(0)
    return grp.sort_values("# Links", ascending=False)
