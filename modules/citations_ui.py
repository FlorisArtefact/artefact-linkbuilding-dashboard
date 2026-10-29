"""Brand mentions (citations without a link) per market — the 'GEO / brand presence' side of the campaign."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

NAVY, PINK, TEAL, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#FFFFFF"


def _type_col(df: pd.DataFrame):
    return next((c for c in df.columns if "brand" in c.lower() and "mention" in c.lower()), None)


def render_citations_section(raw_links: dict, flags: dict, demo_mode: bool) -> None:
    """raw_links: {lang: live links DataFrame} (all periods). Counts placements typed 'Brand Mention' vs 'Backlink'."""
    st.markdown('<div class="section-title">🗣️ Brand mentions (citations without a link)</div>', unsafe_allow_html=True)
    rows, mentions = [], []
    for lang, df in raw_links.items():
        if df is None or df.empty:
            continue
        col = _type_col(df)
        if col is None:
            continue
        kind = df[col].astype(str).str.lower()
        is_m = kind.str.contains("brand")
        rows.append({"Market": lang, "Backlinks": int((kind.str.contains("backlink")).sum()), "Brand mentions": int(is_m.sum())})
        if is_m.any():
            m = df[is_m].copy()
            m["Market"] = lang
            mentions.append(m)
    if not rows:
        st.info("No link-type column found in the data (expected 'Backlink/ Brand Mention').")
        return
    summ = pd.DataFrame(rows)
    total_m = int(summ["Brand mentions"].sum())

    c1, c2 = st.columns([1, 2])
    c1.metric("Brand mentions placed", total_m,
              help="Placements where the brand is named on another site without a link. They build brand presence "
                   "and are likely to matter for being cited in AI answers (GEO).")
    c1.metric("Backlinks placed", int(summ["Backlinks"].sum()))
    with c2:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=summ["Market"], y=summ["Backlinks"], name="Backlinks", marker_color=NAVY))
        fig.add_trace(go.Bar(x=summ["Market"], y=summ["Brand mentions"], name="Brand mentions", marker_color=PINK))
        fig.update_layout(barmode="group", height=260, paper_bgcolor=WHITE, plot_bgcolor=WHITE,
                          font=dict(family="Roboto", color=NAVY, size=11), margin=dict(t=20, b=30, l=40, r=10),
                          legend=dict(orientation="h", y=-0.2), yaxis=dict(gridcolor="#E8ECF2", zeroline=False),
                          xaxis=dict(showgrid=False), bargap=0.35)
        st.plotly_chart(fig, width="stretch")

    if total_m == 0:
        st.info("No brand mentions registered yet. To show them here, set **Brand Mention** in the column "
                "'Backlink/ Brand Mention' of the Live_links tab when a placement names the brand without a link.")
    else:
        with st.expander(f"📋 All brand mentions ({total_m})"):
            allm = pd.concat(mentions, ignore_index=True)
            show = [c for c in ("Market", "LL Date", "Live Link", "Domain", "DA", "Price", "Target campaign") if c in allm.columns]
            st.dataframe(allm[show], width="stretch", hide_index=True,
                         column_config={"Live Link": st.column_config.LinkColumn("Live Link", max_chars=60)})
    st.caption("Mentions raise brand presence and likely help visibility in AI answers (GEO), but this dashboard counts "
               "placements only — it does not measure AI citations themselves." + (" **DEMO DATA.**" if demo_mode else ""))
