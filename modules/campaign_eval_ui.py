"""
'Campaign evaluation' tab: impact of the link campaign on the whole domain and on the pages that received links, plus
the pages to build on next. Search Console only (no revenue). Maths in modules/campaign_eval.py.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules import campaign_eval as ce
from modules.budget_ui import _CSS as _BA_CSS, _short

NAVY, PINK, TEAL, MID, LIGHT = "#1B2D5B", "#E5007D", "#00B4C8", "#8B9BB4", "#EEF1F6"
_PAL = [PINK, NAVY, TEAL, "#F28C28", "#7B3FA0", MID]


def _n(v) -> str:
    return "" if v is None or pd.isna(v) else f"{v:,.0f}".replace(",", ".")


def _x(a, b) -> str:
    return f"{b / a:.1f}×".replace(".", ",") if a else ""


def _m(ts) -> str:
    return pd.Timestamp(ts).strftime("%b %Y")


def render_campaign_eval(client: str, monthly: pd.DataFrame, links: pd.DataFrame, queries: pd.DataFrame,
                         page_queries: pd.DataFrame, allocation: pd.DataFrame | None, brand_terms: list,
                         launch_month=None) -> dict:
    st.markdown(_BA_CSS, unsafe_allow_html=True)
    dt = ce.domain_timeline(monthly, links)
    qt = ce.query_timeline(queries, brand_terms)
    fp = ce.focus_pages(page_queries, links, brand_terms)
    h = ce.headline(dt, qt, launch_month, links)
    if not h:
        st.info("Search Console data is not available yet, so the campaign cannot be evaluated.")
        return {}

    # ── Hero ──────────────────────────────────────────────────────────────────
    since = _m(h["base_month"])
    tiles = (f'<div class="ba-tile main"><div class="lab">Clicks from Google per month</div>'
             f'<div class="big">{_n(h["clicks_then"])} → {_n(h["clicks_now"])}</div>'
             f'<div class="sub">{since} → {_m(h["now_month"])} · {_x(h["clicks_then"], h["clicks_now"])}</div></div>'
             f'<div class="ba-tile"><div class="lab">Seen in Google per month</div>'
             f'<div class="big">{_n(h["impr_then"])} → {_n(h["impr_now"])}</div>'
             f'<div class="sub">impressions · {_x(h["impr_then"], h["impr_now"])}</div></div>')
    if "nb_top10_now" in h:
        tiles += (f'<div class="ba-tile"><div class="lab">Non-brand search terms on page 1</div>'
                  f'<div class="big">{_n(h["nb_top10_then"])} → {"≥ " if h.get("capped") else ""}{_n(h["nb_top10_now"])}</div>'
                  f'<div class="sub">terms without "{(brand_terms or [client])[0]}" in the top 10</div></div>')
    tiles += (f'<div class="ba-tile"><div class="lab">Links live</div><div class="big">{h["links"]}</div>'
              f'<div class="sub">€{_n(h["spend"])} invested</div></div>')
    fl = f' · first link {_m(h["first_link"])}' if h.get("first_link") is not None else ""
    st.markdown(f'<div class="ba-hero"><div class="top">Campaign evaluation · {client}{fl}</div>'
                f'<div class="h">What the link campaign did for the domain and the focus pages</div>'
                f'<div class="ba-tiles">{tiles}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="ba-basis">Measured with Google Search Console. Links work together with the launch, content '
                'and seasonality, so this shows direction and size, not proof of cause per link.</div>', unsafe_allow_html=True)

    # ── 1. Whole domain ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">1 · The whole domain</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-hint">Clicks from Google per month (bars) and the number of live links (line).</div>',
                unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_bar(x=dt["month"], y=dt["Clicks"], name="Clicks from Google", marker_color=NAVY,
                text=[_n(v) for v in dt["Clicks"]], textposition="outside")
    fig.add_scatter(x=dt["month"], y=dt["Links total"], name="Links live (total)", yaxis="y2", mode="lines+markers+text",
                    line=dict(color=PINK, width=3), text=[str(v) if v else "" for v in dt["Links total"]],
                    textposition="top center", textfont=dict(color=PINK))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), plot_bgcolor="white", legend=dict(orientation="h", y=-0.15),
                      yaxis=dict(title="Clicks", gridcolor=LIGHT, rangemode="tozero"),
                      yaxis2=dict(title="Links", overlaying="y", side="right", rangemode="tozero", showgrid=False),
                      xaxis=dict(tickformat="%b %Y", dtick="M1"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if not qt.empty:
        c1, c2 = st.columns(2)
        with c1:
            f2 = go.Figure(go.Bar(x=qt["month"], y=qt["Non-brand terms top 10"], marker_color=TEAL,
                                  text=[_n(v) for v in qt["Non-brand terms top 10"]], textposition="outside"))
            f2.update_layout(title=dict(text="Non-brand search terms on page 1", font=dict(size=14)), height=280,
                             margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="white",
                             yaxis=dict(gridcolor=LIGHT), xaxis=dict(tickformat="%b", dtick="M1"))
            st.plotly_chart(f2, width="stretch", config={"displayModeBar": False})
        with c2:
            f3 = go.Figure(go.Bar(x=dt["month"], y=dt["Impressions"], marker_color=MID,
                                  text=[_n(v) for v in dt["Impressions"]], textposition="outside"))
            f3.update_layout(title=dict(text="Seen in Google (impressions)", font=dict(size=14)), height=280,
                             margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="white",
                             yaxis=dict(gridcolor=LIGHT), xaxis=dict(tickformat="%b", dtick="M1"))
            st.plotly_chart(f3, width="stretch", config={"displayModeBar": False})
        if qt["Capped"].any():
            st.caption("From the month marked as capped, Google returned its maximum of 25,000 search terms, so the real "
                       "number of page-1 terms is higher than shown.")

    # ── 2. Focus pages ────────────────────────────────────────────────────────
    if not fp.empty and "Main search term" in fp.columns:
        st.markdown('<div class="section-title">2 · The pages that received links</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="section-hint">Per page the search term it is seen for most (without the brand name) and '
                    f'its average Google position in the month of its first link vs. {_m(fp["To"].max())}. Lower is better.</div>',
                    unsafe_allow_html=True)
        cnt = fp["Verdict"].value_counts().to_dict() if "Verdict" in fp.columns else {}
        st.markdown('<div class="ba-chips">' + "".join(
            f'<span class="ba-chip">{k}: {cnt[k]}</span>' for k in ["Rising", "Stable", "Falling"] if cnt.get(k)) + '</div>',
            unsafe_allow_html=True)
        th = ce.term_history(page_queries, fp)
        if not th.empty:
            f4 = go.Figure()
            for i, (pg, g) in enumerate(th.groupby("Page", sort=False)):
                g = g.sort_values("month")
                f4.add_scatter(x=g["month"], y=g["Position"], mode="lines+markers", name=f'{_short(pg)} · "{g["Term"].iloc[0]}"',
                               line=dict(color=_PAL[i % len(_PAL)], width=3))
            f4.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
                             legend=dict(orientation="h", y=-0.2), xaxis=dict(tickformat="%b %Y", dtick="M1"),
                             yaxis=dict(title="Google position", autorange="reversed", gridcolor=LIGHT))
            f4.add_hrect(y0=0.5, y1=10.5, fillcolor=TEAL, opacity=0.08, line_width=0,
                         annotation_text="page 1", annotation_position="top left")
            st.plotly_chart(f4, width="stretch", config={"displayModeBar": False})
        show = fp.copy()
        show["Page"] = show["Page"]
        cols = [c for c in ["Page", "Links", "Spent", "First link", "Main search term", "Position then", "Position now",
                            "Verdict", "Clicks then", "Clicks now", "Top-10 terms then", "Top-10 terms now"] if c in show.columns]
        st.dataframe(show[cols], width="stretch", hide_index=True, column_config={
            "Page": st.column_config.LinkColumn("Page"),
            "Spent": st.column_config.NumberColumn("Spent", format="€%,.0f"),
            "First link": st.column_config.DateColumn("First link", format="DD-MM-YYYY"),
            "Position then": st.column_config.NumberColumn("Position in month of first link", format="%.1f"),
            "Position now": st.column_config.NumberColumn(f"Position {_m(fp['To'].max())}", format="%.1f"),
            "Clicks then": st.column_config.NumberColumn("Clicks then", format="%,.0f"),
            "Clicks now": st.column_config.NumberColumn("Clicks now", format="%,.0f"),
            "Top-10 terms then": st.column_config.NumberColumn("Page-1 terms then", format="%d"),
            "Top-10 terms now": st.column_config.NumberColumn("Page-1 terms now", format="%d"),
        })

    # ── 3. Next year ──────────────────────────────────────────────────────────
    al = allocation if allocation is not None else pd.DataFrame()
    if not al.empty:
        st.markdown('<div class="section-title">3 · Where to build on next</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-hint">Pages that are seen often in Google but are not in the top 3 yet. The full '
                    'ranking and its reasoning are in the Budget advice tab.</div>', unsafe_allow_html=True)
        top = al.head(6).copy()
        top.insert(0, "Name", top["Page"].map(_short))
        cols = [c for c in ["Name", "Page", "Links so far", "Position", "Impressions (90d)", "Share of next budget"] if c in top.columns]
        st.dataframe(top[cols], width="stretch", hide_index=True, column_config={
            "Page": st.column_config.LinkColumn("Page"),
            "Position": st.column_config.NumberColumn("Avg. position", format="%.1f"),
            "Impressions (90d)": st.column_config.NumberColumn("Seen in Google (90d)", format="%,.0f"),
            "Share of next budget": st.column_config.ProgressColumn("Share (proposal)", format="percent", min_value=0, max_value=1),
        })

    with st.expander("📐 How this is measured"):
        st.markdown("- Clicks and impressions: Google Search Console, whole property, complete months.\n"
                    "- Search terms: Google hides rare (anonymised) terms, so term counts and term clicks are lower than the "
                    "property total. From 25,000 terms per month Google stops returning more rows.\n"
                    "- Average position of the whole site gets 'worse' when the site starts to show up for many more search "
                    "terms. That is growth, not decline; the page-1 term count is the better measure.\n"
                    "- Per page: the main term is the non-brand term the page was seen for most in the latest month.")
    return h
