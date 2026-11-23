"""
'Search performance' tab for clients without GA4 revenue : what Google Search Console shows
for the whole site. Monthly trend, page groups, brand vs. non-brand search terms, top pages.
"""
from urllib.parse import urlparse

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

NAVY, PINK, TEAL, MID, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#8B9BB4", "#FFFFFF"
DEFAULT_GROUPS = {"": "Homepage", "c": "Category pages", "p": "Product pages", "inspiratie": "Inspiration & advice",
                  "blog": "Blog", "services": "Services", "vestigingsinfo": "Store pages", "actueel": "News"}


def page_group(url: str, groups: dict | None = None) -> str:
    g = {**DEFAULT_GROUPS, **(groups or {})}
    path = urlparse(str(url)).path.strip("/")
    seg = path.split("/")[0] if path else ""
    return g.get(seg, seg.replace("-", " ").capitalize() or "Homepage")


def group_table(pages: pd.DataFrame, groups: dict | None = None) -> pd.DataFrame:
    if pages is None or pages.empty:
        return pd.DataFrame()
    p = pages.copy()
    p["Group"] = p["Page"].map(lambda u: page_group(u, groups))
    p["_pw"] = pd.to_numeric(p["Avg Position"], errors="coerce") * p["Impressions"]
    g = p.groupby("Group").agg(Pages=("Page", "nunique"), Clicks=("Clicks", "sum"), Impressions=("Impressions", "sum"),
                               _pw=("_pw", "sum")).reset_index()
    g["Avg. position"] = g["_pw"] / g["Impressions"].where(g["Impressions"] > 0)
    tot = g["Clicks"].sum()
    g["Share of clicks"] = g["Clicks"] / tot if tot else 0.0
    return g.drop(columns="_pw").sort_values("Clicks", ascending=False).reset_index(drop=True)


def brand_split(queries: pd.DataFrame, brand_terms: list) -> dict:
    if queries is None or queries.empty:
        return {}
    pat = "|".join(t.lower() for t in brand_terms if t)
    is_b = queries["Query"].astype(str).str.lower().str.contains(pat, regex=True) if pat else pd.Series(False, index=queries.index)
    nb = queries[~is_b]
    return {"brand_clicks": float(queries.loc[is_b, "Clicks"].sum()), "nonbrand_clicks": float(nb["Clicks"].sum()),
            "nonbrand": nb.sort_values("Clicks", ascending=False)}


def render_search_section(per_lang: dict, market_names: dict, brand_terms: list, groups: dict | None = None) -> None:
    """per_lang: {lang: {"monthly": df(month, Clicks, Impressions, Position), "pages": df(Page...), "queries": df}}"""
    st.markdown('<div class="section-title">🔎 How the site performs in Google</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-hint">Measured by Google Search Console for the whole site. This is the baseline the '
                'links have to move: more search terms on page 1, more clicks without the brand name.</div>',
                unsafe_allow_html=True)
    have = [l for l, d in per_lang.items() if d.get("monthly") is not None and not d["monthly"].empty]
    if not have:
        st.info("Search Console data is not available yet.")
        return
    lang = have[0] if len(have) == 1 else st.selectbox("Market", have, format_func=lambda l: market_names.get(l, l),
                                                       key="sp_market")
    d = per_lang[lang]
    m = d["monthly"].sort_values("month")
    last, prev = m.iloc[-1], (m.iloc[-2] if len(m) > 1 else None)
    bs = brand_split(d.get("queries"), brand_terms)

    k1, k2, k3, k4 = st.columns(4)
    mname = f"{last['month']:%b %Y}"
    k1.metric(f"Clicks · {mname}", f"{last['Clicks']:,.0f}",
              delta=f"{last['Clicks'] / prev['Clicks'] - 1:+.0%} vs. month before" if prev is not None and prev["Clicks"] else None)
    k2.metric(f"Impressions · {mname}", f"{last['Impressions']:,.0f}",
              delta=f"{last['Impressions'] / prev['Impressions'] - 1:+.0%} vs. month before" if prev is not None and prev["Impressions"] else None)
    k3.metric(f"Avg. position · {mname}", f"{last['Position']:.1f}" if pd.notna(last["Position"]) else "—",
              help="Average over all search terms. It goes UP (worse) when the site starts to show for many new terms "
                   "on lower positions, so read it together with impressions.")
    if bs:
        tot = bs["brand_clicks"] + bs["nonbrand_clicks"]
        k4.metric("Clicks without brand name (90d)", f"{bs['nonbrand_clicks'] / tot:.0%}" if tot else "—",
                  help=f"Share of clicks from search terms that do not contain {', '.join(brand_terms)}. "
                       "This is where link building helps most; brand searches come anyway.")

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=m["month"], y=m["Clicks"], name="Clicks", marker_color=PINK))
        fig.add_trace(go.Scatter(x=m["month"], y=m["Impressions"], name="Impressions", yaxis="y2", mode="lines+markers",
                                 line=dict(color=NAVY, width=2)))
        fig.update_layout(title=dict(text="Clicks and impressions per month", font=dict(size=13, color=NAVY)), height=320,
                          paper_bgcolor=WHITE, plot_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
                          margin=dict(t=45, b=30, l=50, r=50), legend=dict(orientation="h", y=-0.15),
                          yaxis=dict(title="Clicks", gridcolor="#E8ECF2"), xaxis=dict(showgrid=False, tickformat="%b %Y"),
                          yaxis2=dict(title="Impressions", overlaying="y", side="right", showgrid=False))
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = go.Figure(go.Scatter(x=m["month"], y=m["Position"], mode="lines+markers", line=dict(color=TEAL, width=2),
                                   name="Avg. position"))
        fig.update_layout(title=dict(text="Average position per month (lower is better)", font=dict(size=13, color=NAVY)),
                          height=320, paper_bgcolor=WHITE, plot_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
                          margin=dict(t=45, b=30, l=50, r=20), yaxis=dict(autorange="reversed", gridcolor="#E8ECF2"),
                          xaxis=dict(showgrid=False, tickformat="%b %Y"), showlegend=False)
        st.plotly_chart(fig, width="stretch")
    st.caption("Complete months only. The current month is added once it is over.")

    pages = d.get("pages")
    gt = group_table(pages, groups)
    if not gt.empty:
        st.markdown("**Which parts of the site get the clicks** (last 90 days)")
        st.dataframe(gt, width="stretch", hide_index=True, column_config={
            "Clicks": st.column_config.NumberColumn("Clicks", format="%,.0f"),
            "Impressions": st.column_config.NumberColumn("Impressions", format="%,.0f"),
            "Avg. position": st.column_config.NumberColumn("Avg. position", format="%.1f"),
            "Share of clicks": st.column_config.ProgressColumn("Share of clicks", format="percent", min_value=0, max_value=1)})

    c3, c4 = st.columns(2)
    with c3:
        if bs and not bs["nonbrand"].empty:
            st.markdown("**Top search terms without the brand name** (last 90 days)")
            st.dataframe(bs["nonbrand"].head(15), width="stretch", hide_index=True, column_config={
                "Clicks": st.column_config.NumberColumn("Clicks", format="%,.0f"),
                "Impressions": st.column_config.NumberColumn("Impressions", format="%,.0f"),
                "Position": st.column_config.NumberColumn("Avg. position", format="%.1f")})
    with c4:
        if pages is not None and not pages.empty:
            st.markdown("**Top pages** (last 90 days)")
            tp = pages.sort_values("Clicks", ascending=False).head(15)[["Page", "Clicks", "Impressions", "Avg Position"]]
            st.dataframe(tp, width="stretch", hide_index=True, column_config={
                "Page": st.column_config.LinkColumn("Page"),
                "Clicks": st.column_config.NumberColumn("Clicks", format="%,.0f"),
                "Impressions": st.column_config.NumberColumn("Impressions", format="%,.0f"),
                "Avg Position": st.column_config.NumberColumn("Avg. position", format="%.1f")})
