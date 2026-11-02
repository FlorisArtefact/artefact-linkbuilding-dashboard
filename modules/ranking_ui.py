"""Streamlit UI: ranking trend of all pages that received links, per market (Ahrefs now, GSC later)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules import demo_data
from modules.gsc_client import get_gsc_linked_summary
from modules.ranking_model import aggregate, per_url_table, trend_status

NAVY, PINK, TEAL, MID, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#8B9BB4", "#FFFFFF"
LANG_COLORS = [PINK, NAVY, TEAL, "#FF7043", "#7B1FA2"]
STATUS_TXT = {"improving": ("🟢", "Improving"), "stable": ("⚪", "Stable"), "mixed": ("🟡", "Mixed signals"),
              "declining": ("⚪", "Mixed to weaker"), "unknown": ("⚪", "No data yet")}


@st.cache_data(ttl=21600, show_spinner=False)   # 6 h — cached per URL, so switching market reuses earlier fetches
def _fetch_one(api_key: str, url: str, months: int):
    from modules.ahrefs_client import AhrefsClient
    return AhrefsClient(api_key).get_snapshot_history(url, months)


def _fetch_history(api_key: str, urls: tuple, months: int) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda u: _fetch_one(api_key, u, months), urls))
    return dict(zip(urls, results))


def render_ranking_section(per_lang: dict, api_key: str, demo_mode: bool, flags: dict,
                           gsc_creds: str = "", gsc_sites: dict | None = None) -> dict:
    """per_lang: {lang: {"urls": [landing page urls that received links]}}.
    Returns {lang: status dict, "_total": status dict} (status 'unknown' until data is loaded)."""
    st.markdown('<div class="section-title">🏁 Rankings of all pages we build links to</div>', unsafe_allow_html=True)
    st.caption("All landing pages that received links, per market: are their organic rankings better now than "
               "when we started? Same set of pages at every point in time.")

    langs = [l for l, d in per_lang.items() if d["urls"]]
    result = {"_total": trend_status(pd.DataFrame())}
    if not langs:
        st.info("No landing pages with links in the selected data.")
        return result

    with st.expander("ℹ️ What am I looking at? (source and how to read it)"):
        st.markdown(
            "- **Source: Ahrefs, not GA4 and not Google.** For every landing page that received a link, Ahrefs gives a monthly "
            "snapshot of the keywords it ranks for. We compare the first snapshot in the look-back window with the latest one.\n"
            "- **Avg. position:** average Google position over the keywords each page ranks for (lower number = higher up).\n"
            "- **Keywords in top 10:** how many keywords of these pages Ahrefs sees in positions 1–10.\n"
            "- **Est. organic traffic:** Ahrefs' *model* (position × search volume × expected click rate). It is **not** measured "
            "visits, so it can differ strongly from GA4.\n"
            "- **Why signals can disagree:** the keyword set changes every month (long-tail keywords appear and disappear), "
            "volumes shift and AI answers take clicks. A page can rank higher on its core keywords while the total keyword count and "
            "the traffic *estimate* fall. That is why a mix is shown as 'Mixed signals' and not as a failure.\n"
            "- **Search Console (second column) is Google's own measured data** for the same pages: average position over "
            "all queries, queries on positions 1–10 and impressions, last complete month versus the first month of the "
            "look-back. Google hides rare queries, so its counts are lower than Ahrefs'; Ahrefs models, Google measures. "
            "Where both point the same way the signal is strong; where they differ, the truth is usually in between.\n"
            "- **What to do with it:** use it as an early, indirect signal. The decisive evidence is revenue (tab *Effect on organic*)."
        )

    months = st.slider("Look back (months)", 3, 12, 6, key="rk_months",
                       help="How far back to compare. The campaign has been running for about six months.")
    n_calls = sum(len(per_lang[l]["urls"]) for l in langs) * (months + 1)

    history_by_lang = {}
    if demo_mode:
        for l in langs:
            history_by_lang[l] = demo_data.demo_ranking_history(per_lang[l]["urls"], months)
    elif not api_key:
        st.info("Add the Ahrefs API key to load ranking history (Search Console will replace this once connected).")
        return result
    else:
        try:
            with st.spinner(f"Fetching ranking history from Ahrefs… (first time ~{n_calls} requests, then cached for 6 hours)"):
                for l in langs:
                    history_by_lang[l] = _fetch_history(api_key, tuple(sorted(per_lang[l]["urls"])), months)
        except RuntimeError:
            st.warning("Ahrefs did not answer (most likely its rate limit). Nothing was stored; reload in a minute to try again. "
                       "Search Console numbers do not depend on it.")
            return result

    # Search Console windows: the same look-back, as whole calendar months (start month vs. last complete month)
    now_m = pd.Timestamp.today().normalize().replace(day=1) - pd.DateOffset(months=1)
    start_m = now_m - pd.DateOffset(months=months)
    win = {"start": (start_m.date().isoformat(), (start_m + pd.offsets.MonthEnd(0)).date().isoformat()),
           "now": (now_m.date().isoformat(), (now_m + pd.offsets.MonthEnd(0)).date().isoformat())}

    # ── per market headline: Ahrefs (modelled) next to Search Console (measured by Google) ──
    cols = st.columns(len(langs))
    aggs = {}
    for i, l in enumerate(langs):
        agg = aggregate(history_by_lang[l])
        aggs[l] = agg
        s = trend_status(agg)
        result[l] = s
        icon, label = STATUS_TXT[s["status"]]
        with cols[i]:
            st.markdown(f"**{flags.get(l, '🌐')} {l}** &nbsp; {icon} {label}")
            ca, cg = st.columns(2)
            with ca:
                st.caption("**Ahrefs** · modelled")
                if s["status"] == "unknown":
                    st.caption("Not enough ranking data.")
                else:
                    st.metric("Avg. position", f"{s['pos_now']:.1f}", delta=f"{s['pos_change']:+.1f} places",
                              help="Average position of the keywords these pages rank for. A positive delta = better.")
                    st.metric("Keywords in top 10", s["top10_now"], delta=s["top10_now"] - s["top10_start"])
                    if s["traffic_change"] is not None:
                        st.metric("Est. organic traffic", f"{s['traffic_now']:,.0f}", delta=f"{s['traffic_change']:+.0%}")
            with cg:
                st.caption("**Search Console** · measured by Google")
                site = (gsc_sites or {}).get(l, "")
                g0 = g1 = None
                if demo_mode:
                    g0, g1 = demo_data.demo_gsc_summary(l, 0), demo_data.demo_gsc_summary(l, 1)
                elif site and gsc_creds:
                    urls = tuple(sorted(per_lang[l]["urls"]))
                    g0 = get_gsc_linked_summary(gsc_creds, site, urls, *win["start"])
                    g1 = get_gsc_linked_summary(gsc_creds, site, urls, *win["now"])
                if not g0 or not g1 or g0.get("position") is None or g1.get("position") is None:
                    st.caption("No Search Console access for this market yet." if not (site and gsc_creds) or (g0 is None or g1 is None)
                               else "No impressions recorded for these pages in the compared months.")
                else:
                    st.metric("Avg. position", f"{g1['position']:.1f}", delta=f"{g0['position'] - g1['position']:+.1f} places",
                              help="Impression-weighted average position of these pages over all queries, last complete month "
                                   "versus the first month of the look-back.")
                    st.metric("Queries in top 10", g1["top10"], delta=g1["top10"] - g0["top10"],
                              help="Page + search query pairs on positions 1-10. Google hides rare queries, so this is "
                                   "lower than a keyword tool shows.")
                    st.metric("Impressions", f"{g1['impressions']:,.0f}",
                              delta=(f"{g1['impressions'] / g0['impressions'] - 1:+.0%}" if g0["impressions"] else None),
                              help="Times these pages were shown in Google results (a measured number).")
                    st.caption(f"{start_m:%b %Y} → {now_m:%b %Y}")
                result[f"{l}_gsc"] = {"start": g0, "now": g1}

    all_hist = {f"{l}|{u}": df for l in langs for u, df in history_by_lang[l].items()}
    result["_total"] = trend_status(aggregate(all_hist))

    # ── chart: avg position over time per market ──
    fig = go.Figure()
    for i, l in enumerate(langs):
        a = aggs[l]
        a = a[a["avg_position"].notna()]
        if not a.empty:
            fig.add_trace(go.Scatter(x=a["date"], y=a["avg_position"], mode="lines+markers", name=l,
                                     line=dict(color=LANG_COLORS[i % len(LANG_COLORS)], width=3)))
    fig.update_layout(
        title=dict(text="Average position of linked pages (higher on chart = better)", font=dict(size=13, color=NAVY)),
        height=340, paper_bgcolor=WHITE, plot_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
        margin=dict(t=45, b=30, l=50, r=20), hovermode="x unified", legend=dict(orientation="h", y=-0.15),
        yaxis=dict(autorange="reversed", gridcolor="#E8ECF2", zeroline=False, title="Avg. position"),
        xaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")

    # ── all URLs together ──
    with st.expander("📋 All pages we build links to — position then vs. now"):
        frames = []
        for l in langs:
            t = per_url_table(history_by_lang[l])
            if not t.empty:
                t.insert(0, "Market", l)
                frames.append(t)
        if frames:
            st.dataframe(pd.concat(frames, ignore_index=True), width="stretch", hide_index=True, column_config={
                "Landing Page": st.column_config.LinkColumn("Landing Page", max_chars=50),
                "Position start": st.column_config.NumberColumn(format="%.1f"),
                "Position now": st.column_config.NumberColumn(format="%.1f"),
                "Change": st.column_config.NumberColumn("Change (places, + = better)", format="%+.1f"),
                "Traffic start": st.column_config.NumberColumn(format="%d"),
                "Traffic now": st.column_config.NumberColumn(format="%d"),
            })

    st.caption("⚠️ A direction, not proof. Rankings also move because of content, technique and competition, and "
               "Ahrefs positions are estimates from its own tracking (Google's search-result changes can make "
               "third-party tools less exact). Search Console will be the more reliable source once connected."
               + (" **DEMO DATA.**" if demo_mode else ""))
    return result
