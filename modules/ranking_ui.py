"""Streamlit UI: ranking trend of all pages that received links, per market (Ahrefs now, GSC later)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules import demo_data
from modules.ranking_model import aggregate, per_url_table, trend_status

NAVY, PINK, TEAL, MID, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#8B9BB4", "#FFFFFF"
LANG_COLORS = [PINK, NAVY, TEAL, "#FF7043", "#7B1FA2"]
STATUS_TXT = {"improving": ("🟢", "Improving"), "stable": ("⚪", "Stable"),
              "declining": ("🟠", "Declining"), "unknown": ("⚪", "No data yet")}


@st.cache_data(ttl=21600, show_spinner=False)   # 6 h — each URL x snapshot costs Ahrefs API units
def _fetch_history(api_key: str, urls: tuple, months: int) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    from modules.ahrefs_client import AhrefsClient
    client = AhrefsClient(api_key)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda u: client.get_snapshot_history(u, months), urls))
    return dict(zip(urls, results))


def render_ranking_section(per_lang: dict, api_key: str, demo_mode: bool, flags: dict) -> dict:
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
        if st.button(f"📥 Load ranking trend (~{n_calls} Ahrefs requests, cached 6 h)", key="rk_load"):
            st.session_state["rk_loaded"] = True
        if not st.session_state.get("rk_loaded"):
            st.caption("Not loaded yet — this uses Ahrefs API units, so it only runs when you ask for it.")
            return result
        with st.spinner("Fetching ranking history from Ahrefs…"):
            for l in langs:
                history_by_lang[l] = _fetch_history(api_key, tuple(sorted(per_lang[l]["urls"])), months)

    # ── per market headline ──
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
            if s["status"] == "unknown":
                st.caption("Not enough ranking data.")
            else:
                st.metric("Avg. position", f"{s['pos_now']:.1f}", delta=f"{s['pos_change']:+.1f} places",
                          help="Average position of the keywords these pages rank for. A positive delta = better.")
                st.metric("Keywords in top 10", s["top10_now"], delta=s["top10_now"] - s["top10_start"])
                if s["traffic_change"] is not None:
                    st.metric("Est. organic traffic", f"{s['traffic_now']:,.0f}", delta=f"{s['traffic_change']:+.0%}")

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
