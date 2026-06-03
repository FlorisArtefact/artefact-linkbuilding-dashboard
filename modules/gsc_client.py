import pandas as pd
import streamlit as st
from typing import Optional


def load_gsc_csv(uploaded_file) -> pd.DataFrame:
    """Parse a GSC performance export (Pages view) CSV."""
    try:
        df = pd.read_csv(uploaded_file)
        df.columns = df.columns.str.strip()
        # GSC exports use 'Top queries' or 'Pages' as first column
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
    """Join GSC position data into landing page summary table."""
    if gsc_df.empty or "Page" not in gsc_df.columns or "Avg Position" not in gsc_df.columns:
        return lp_table
    gsc_slim = gsc_df[["Page", "Avg Position", "Clicks", "Impressions"]].copy()
    gsc_slim.columns = ["Landing Page", "GSC Position", "GSC Clicks", "GSC Impressions"]
    merged = lp_table.merge(gsc_slim, on="Landing Page", how="left")
    return merged


GSC_SETUP_INSTRUCTIONS = """
## Google Search Console API instellen

**Stap 1 — Search Console API inschakelen**
1. Ga naar [console.cloud.google.com](https://console.cloud.google.com)
2. Selecteer jouw project (of maak een nieuw project aan)
3. Ga naar **APIs & Services → Library**
4. Zoek op "Search Console API" → klik **Enable**

**Stap 2 — OAuth credentials aanmaken**
1. Ga naar **APIs & Services → Credentials**
2. Klik **+ Create Credentials → OAuth Client ID**
3. Application type: **Desktop app**
4. Geef het een naam (bijv. "Linkbuilding Dashboard")
5. Download het `credentials.json` bestand

**Stap 3 — credentials.json plaatsen**
Zet het gedownloade `credentials.json` bestand in de map van het dashboard:
```
linkbuilding-dashboard/
└── credentials.json   ← hier
```

**Stap 4 — Eerste keer inloggen**
Start het dashboard. Bij de eerste keer op **"Connect Google Search Console"** klikken,
opent een browser popup om in te loggen. Daarna slaat de app het token lokaal op.

**Kosten:** Gratis — de Search Console API heeft geen kosten.
"""
