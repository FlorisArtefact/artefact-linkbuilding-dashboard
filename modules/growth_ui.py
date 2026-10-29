"""Streamlit UI: organic revenue growth for pages that received links — per URL, per category, whole domain."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.growth_model import (
    category_of, growth_table, monthly_pivot, norm_path, summarize,
)

NAVY, PINK, TEAL, MID, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#8B9BB4", "#FFFFFF"


def _pct(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+.0%}"


def _pp(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:+.0f} pp"


def render_growth_section(per_lang: dict, categories: dict | None, currency: str, flags: dict, demo_mode: bool):
    """Renders the section; returns the headline summary row (dict) or None."""
    """per_lang: {lang: {"monthly": df(month,path,Revenue), "links": df(live links)}}"""
    st.markdown('<div class="section-title">📈 Revenue growth on linked pages</div>', unsafe_allow_html=True)

    available = {l: d for l, d in per_lang.items() if d.get("monthly") is not None and not d["monthly"].empty}
    if not available:
        st.info("💡 Waiting for GA4 history. Once the service account has access, this section shows the monthly "
                "**organic revenue** per landing page, per category and for the whole domain — with the date of every "
                "placed link — and whether linked pages grew faster than the rest of the site.")
        return None

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    market = c1.selectbox("Market", ["All markets"] + list(available), key="gr_market")
    window = c2.slider("Compare ± months around first link", 2, 6, 3, key="gr_window",
                       help="Average monthly revenue in N months before vs. N months after the first link to a page.")
    scope = c3.radio("Level", ["Domain", "Category", "Landing page"], key="gr_scope", horizontal=False)

    markets = list(available) if market == "All markets" else [market]
    tables, series_dom, series_pages = [], None, {}
    for lang in markets:
        d = available[lang]
        t = growth_table(d["monthly"], d["links"], window)
        if not t.empty:
            t["Market"] = lang
            t["Category"] = t["Landing Page"].apply(lambda u: category_of(u, categories))
            tables.append(t)
        pv = monthly_pivot(d["monthly"])
        if not pv.empty:
            series_dom = pv.sum(axis=1) if series_dom is None else series_dom.add(pv.sum(axis=1), fill_value=0)
            for col in pv.columns:
                series_pages[(lang, col)] = pv[col]

    table = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    link_rows = pd.concat([available[l]["links"].assign(_m=l) for l in markets
                           if not available[l]["links"].empty], ignore_index=True) if any(
        not available[l]["links"].empty for l in markets) else pd.DataFrame()

    # ── headline numbers ──
    summ = summarize(table)
    headline = summ.iloc[0].to_dict() if not summ.empty else None
    k1, k2, k3, k4 = st.columns(4)
    if summ.empty:
        k1.metric("Growth linked pages", "—", help="Not enough months of data before/after the first link yet.")
    else:
        r = summ.iloc[0]
        k1.metric("Growth linked pages", _pct(r["Growth"]),
                  help="Average monthly organic revenue on linked pages: N months after vs. N months before the first link.")
        k2.metric("Growth whole domain", _pct(r["Domain growth"]), help="Same months, all landing pages.")
        k3.metric("Outperformance", _pp(r["Outperformance"]),
                  help="Linked-page growth minus domain growth (percentage points). A first control for seasonality — "
                       "not proof of cause.")
        k4.metric("Pages with enough history", int(r["Pages"]),
                  help="Pages whose first link is at least 2 full months ago. Younger links are 'too early' to judge.")

    if not table.empty and "Signal" in table.columns:
        counts = table["Signal"].value_counts()
        st.markdown(
            "**Signal per page:** "
            f"🟢 {counts.get('Ahead of domain', 0)} ahead of domain &nbsp;·&nbsp; "
            f"⚪ {counts.get('In line with domain', 0)} in line &nbsp;·&nbsp; "
            f"🟠 {counts.get('Behind domain', 0)} behind &nbsp;·&nbsp; "
            f"⏳ {counts.get('Too early / no baseline', 0)} too early to say"
        )

    # ── chart ──
    pick_cat = pick_url = None
    if scope == "Category" and not table.empty:
        pick_cat = st.selectbox("Category", sorted(table["Category"].unique()), key="gr_cat")
    if scope == "Landing page" and not table.empty:
        pick_url = st.selectbox("Landing page", table["Landing Page"].tolist(), key="gr_url")

    fig = go.Figure()
    if series_dom is not None:
        if scope == "Domain":
            fig.add_trace(go.Scatter(x=series_dom.index, y=series_dom.values, name="Whole domain", mode="lines+markers",
                                     line=dict(color=NAVY, width=3)))
            sel_links = link_rows
            # link spend per month as bars: the domain-level view (links lift the whole domain, not just their target)
            if not link_rows.empty and {"LL Date", "Price"} <= set(link_rows.columns):
                spend = (link_rows.dropna(subset=["LL Date"]).assign(
                    _m=lambda x: pd.to_datetime(x["LL Date"]).dt.to_period("M").dt.to_timestamp())
                    .groupby("_m")["Price"].sum())
                fig.add_trace(go.Bar(x=spend.index, y=spend.values, name="Link spend", marker_color=PINK,
                                     opacity=0.35, yaxis="y2"))
        else:
            fig.add_trace(go.Scatter(x=series_dom.index, y=series_dom.values, name="Whole domain", mode="lines",
                                     line=dict(color=MID, width=2, dash="dot"), yaxis="y2"))
            if scope == "Category":
                rows = table[table["Category"] == pick_cat]
            else:
                rows = table[table["Landing Page"] == pick_url]
            total = None
            for _, r in rows.iterrows():
                s = series_pages.get((r["Market"], r["path"]))
                if s is not None:
                    total = s if total is None else total.add(s, fill_value=0)
            if total is not None:
                fig.add_trace(go.Scatter(x=total.index, y=total.values, name=pick_cat or pick_url, mode="lines+markers",
                                         line=dict(color=PINK, width=3)))
            paths = set(rows["path"]) if not rows.empty else set()
            sel_links = (link_rows[link_rows["Link to"].apply(norm_path).isin(paths)]
                         if not link_rows.empty else pd.DataFrame())
        if not sel_links.empty and "LL Date" in sel_links.columns:
            # one marker per month with links (a line per link would clutter the domain view)
            for d in sorted({pd.Timestamp(x).to_period("M").to_timestamp() for x in sel_links["LL Date"].dropna()}):
                fig.add_vline(x=d.timestamp() * 1000, line=dict(color=TEAL, width=1.5, dash="dash"), opacity=0.7)
        fig.update_layout(
            title=dict(text=f"Monthly organic revenue ({currency}) — dashed lines = links placed", font=dict(size=13, color=NAVY)),
            height=380, paper_bgcolor=WHITE, plot_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
            margin=dict(t=45, b=30, l=50, r=50), hovermode="x unified",
            legend=dict(orientation="h", y=-0.15),
            yaxis=dict(gridcolor="#E8ECF2", zeroline=False, title="Revenue"),
            yaxis2=dict(overlaying="y", side="right", showgrid=False, zeroline=False,
                        title="Domain revenue" if scope != "Domain" else "Link spend"),
            xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig, width="stretch")

    # ── tables ──
    if table.empty:
        st.caption("No linked pages with enough revenue history around their first link yet.")
    else:
        show = {"Category": "Category", "Landing page": "Landing Page"}
        if scope == "Category":
            tbl = summarize(table, "Category").rename(columns={"Group": "Category"})
        elif scope == "Domain":
            tbl = summarize(table)
        else:
            tbl = table[["Landing Page", "Category", "Signal", "First link", "# Links", "Months after", "Rev/mo before",
                         "Rev/mo after", "Growth", "Domain growth", "Outperformance", "Links not live", "Avg DA"]].copy()
            tbl["First link"] = pd.to_datetime(tbl["First link"]).dt.strftime("%b %Y")
        for col in ("Growth", "Domain growth", "Outperformance"):
            if col in tbl.columns:
                tbl[col] = tbl[col].astype(float) * 100
        cfg = {
            "Rev/mo before": st.column_config.NumberColumn(format=f"{currency}%,.0f"),
            "Rev/mo after": st.column_config.NumberColumn(format=f"{currency}%,.0f"),
            "Growth": st.column_config.NumberColumn(format="%+.0f%%"),
            "Domain growth": st.column_config.NumberColumn(format="%+.0f%%"),
            "Outperformance": st.column_config.NumberColumn("Outperformance (pp)", format="%+.0f"),
            "Landing Page": st.column_config.LinkColumn("Landing Page", max_chars=55),
        }
        st.dataframe(tbl, width="stretch", hide_index=True, column_config=cfg)

    with st.expander("🔎 A page is behind or flat? Check these causes before blaming the links"):
        st.markdown(
            "Link building works with a delay (weeks to months) and is only one of many factors. For a page that lags:\n"
            "1. **Too early?** Links younger than ~3 months often have not shown their effect yet.\n"
            "2. **Links themselves:** are they live (status 200), dofollow, topically relevant, decent DA? "
            "(columns *Links not live* and *Avg DA* above)\n"
            "3. **Indexability & technique:** is the page indexed, canonical correct, not blocked, fast enough (PageSpeed)?\n"
            "4. **Content:** does the page match search intent and compete with what ranks now?\n"
            "5. **Cannibalisation:** does another page of the site compete for the same keyword?\n"
            "6. **Internal links:** does the page receive enough internal links from strong pages?\n"
            "7. **Competition & seasonality:** did competitors improve, or is demand falling?\n\n"
            "Also remember the other direction: links to a deep page can strengthen the **whole domain** even when that "
            "page itself does not grow — compare with the domain view (spend bars vs. total revenue)."
        )
    st.caption(
        "⚠️ A direction, not a proof. Growth after a link does not mean the link caused it, and no growth does not mean "
        "it did nothing. “Ahead / in line / behind” compares a page with the whole domain over the same months "
        "(±10 pp = in line), which only controls for seasonality and site-wide trends. Revenue is organic-search only (GA4)."
        + (" **DEMO DATA.**" if demo_mode else "")
    )
    return headline
