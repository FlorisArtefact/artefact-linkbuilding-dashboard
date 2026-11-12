"""Referral traffic that arrives through the placed links (GA4 medium = referral), matched to our placements."""
from urllib.parse import urlparse

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

NAVY, PINK, TEAL, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#FFFFFF"


def _host(s: str) -> str:
    s = str(s).strip().lower()
    h = urlparse(s).netloc if "://" in s else s.split("/")[0]
    return h.removeprefix("www.")


def _url_key(u: str) -> str:
    p = urlparse(str(u).strip().lower())
    return f"{p.netloc.removeprefix('www.')}{p.path.rstrip('/')}"


def referral_by_domain(referral: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    """Only referrals from domains where we placed a link/mention. Adds how many placements per domain and how
    many sessions can be tied to the exact placed article (pageReferrer match)."""
    if referral is None or referral.empty or links is None or links.empty or "Live Link" not in links.columns:
        return pd.DataFrame()
    pl = links.dropna(subset=["Live Link"]).copy()
    pl["_host"] = pl["Domain"].apply(_host) if "Domain" in pl.columns else pl["Live Link"].apply(_host)
    pl["_key"] = pl["Live Link"].apply(_url_key)
    ref = referral.copy()
    ref["_host"] = ref["source"].apply(_host)
    ref["_key"] = ref["referrer"].apply(_url_key)
    ref = ref[ref["_host"].isin(set(pl["_host"]))]
    if ref.empty:
        return pd.DataFrame()
    ref["_exact"] = ref["_key"].isin(set(pl["_key"]))
    g = ref.groupby("_host").agg(Sessions=("Sessions", "sum"), Revenue=("Revenue", "sum"), Conversions=("Conversions", "sum"))
    g["Sessions from placed article"] = ref[ref["_exact"]].groupby("_host")["Sessions"].sum()
    g["Sessions from placed article"] = g["Sessions from placed article"].fillna(0)
    g["Placements"] = pl.groupby("_host")["Live Link"].count()
    return g.reset_index().rename(columns={"_host": "Domain"}).sort_values("Sessions", ascending=False).reset_index(drop=True)


def render_referral_section(per_lang: dict, flags: dict, demo_mode: bool, period_txt: str = "last 180 days") -> None:
    """per_lang: {lang: {"referral": df|None, "links": live links df (all periods)}}.
    The referral sessions were fetched for `period_txt` (the Year/Quarter/Month filters)."""
    st.markdown('<div class="section-title">🔗 Visitors coming through the placed links (referral traffic)</div>',
                unsafe_allow_html=True)
    st.caption(f"Period: **{period_txt}** (follows the Year / Quarter / Month filters). Counts visitors from sites where a link "
               "was placed at any time, so a link placed later in the year still shows its visitors for the whole period.")
    frames = []
    for lang, d in per_lang.items():
        t = referral_by_domain(d.get("referral"), d.get("links"))
        if not t.empty:
            t.insert(0, "Market", lang)
            frames.append(t)
    have_data = any(d.get("referral") is not None and not d["referral"].empty for d in per_lang.values())
    if not have_data:
        st.info("💡 Visitor and revenue data is not connected yet. Once it is, this shows how many visitors, and how much revenue, arrive via "
                "the articles where we placed links — per site and per market.")
        return
    if not frames:
        st.info("GA4 has referral traffic, but none from the domains where we placed links (yet).")
        return
    allt = pd.concat(frames, ignore_index=True)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Visitors via placed links", f"{allt['Sessions'].sum():,.0f}", help="GA4 sessions with medium 'referral' from "
              f"domains where we placed a link ({period_txt}).")
    k2.metric("Revenue from them", f"€{allt['Revenue'].sum():,.0f}")
    k3.metric("Conversions", f"{allt['Conversions'].sum():,.0f}")
    k4.metric("Sites sending visitors", f"{len(allt)}")

    top = allt.sort_values("Sessions", ascending=True).tail(12)
    fig = go.Figure(go.Bar(x=top["Sessions"], y=top["Domain"], orientation="h", marker_color=TEAL,
                           text=top["Sessions"].round(0).astype(int), textposition="outside"))
    fig.update_layout(title=dict(text="Top sites sending visitors (referral sessions)", font=dict(size=13, color=NAVY)),
                      height=360, paper_bgcolor=WHITE, plot_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
                      margin=dict(t=45, b=30, l=10, r=40), xaxis=dict(gridcolor="#E8ECF2", zeroline=False),
                      yaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")

    with st.expander("📋 Per site"):
        st.dataframe(allt, width="stretch", hide_index=True, column_config={
            "Sessions": st.column_config.NumberColumn(format="%d"),
            "Revenue": st.column_config.NumberColumn(format="€%,.0f"),
            "Conversions": st.column_config.NumberColumn(format="%.0f"),
            "Sessions from placed article": st.column_config.NumberColumn(format="%d"),
        })
    st.caption("Referral visitors are a bonus effect of a link, separate from the SEO effect. GA4 sometimes hides the exact "
               "referring page, so matching is by site; 'from placed article' counts only exact matches."
               + (" **DEMO DATA.**" if demo_mode else ""))
