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


def _fetch_history(api_key: str, urls: tuple, months: int) -> dict:
    """Sequential on purpose: stops at the first refusal. Every result is also stored on disk (ahrefs_guard)."""
    from modules.ahrefs_client import AhrefsClient
    client = AhrefsClient(api_key)
    return {u: client.get_snapshot_history(u, months) for u in urls}


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
            "- **Keywords ranked / in top 3 (Ahrefs):** how many keywords these pages rank for, and how many of them in positions 1–3.\n"
            "- **Avg. position and queries in top 10 come from Search Console** (measured; lower number = higher up).\n"
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
    history_by_lang = {l: {} for l in langs}
    ahrefs_missing = False
    if demo_mode:
        for l in langs:
            history_by_lang[l] = demo_data.demo_ranking_history(per_lang[l]["urls"], months)
    elif not api_key:
        ahrefs_missing = True
        from modules.ahrefs_ui import client_view as _cv
        if not _cv():
            st.info("No Ahrefs key: only the Search Console side is shown.")
    else:
        from modules.ahrefs_client import AhrefsClient
        from modules.ahrefs_ui import gated
        all_urls = tuple(sorted({u for l in langs for u in per_lang[l]["urls"]}))
        pending = AhrefsClient(api_key).pending_snapshots(all_urls, months)
        loaded = gated("rk_load", "Ahrefs keyword and traffic summary of the linked pages", pending,
                       lambda: {l: _fetch_history(api_key, tuple(sorted(per_lang[l]["urls"])), months) for l in langs})
        if loaded is not None:
            history_by_lang = loaded
        ahrefs_missing = loaded is None

    # Search Console windows: the same look-back, as whole calendar months (start month vs. last complete month)
    now_m = pd.Timestamp.today().normalize().replace(day=1) - pd.DateOffset(months=1)
    start_m = now_m - pd.DateOffset(months=months)
    win = {"start": (start_m.date().isoformat(), (start_m + pd.offsets.MonthEnd(0)).date().isoformat()),
           "now": (now_m.date().isoformat(), (now_m + pd.offsets.MonthEnd(0)).date().isoformat())}

    # Search Console first: it supplies the position and top-10 signals (free, measured by Google)
    gsc_by_lang = {}
    _pre = {}
    if not demo_mode and gsc_creds:      # all markets and both windows at once
        from modules.parallel import run_parallel
        _keys = [(l, w) for l in langs if (gsc_sites or {}).get(l) for w in ("start", "now")]
        _res = run_parallel([(get_gsc_linked_summary, (gsc_creds, gsc_sites[l], tuple(sorted(per_lang[l]["urls"])), *win[w]), {})
                             for l, w in _keys])
        _pre = dict(zip(_keys, _res))
    for l in langs:
        site = (gsc_sites or {}).get(l, "")
        g0 = g1 = None
        if demo_mode:
            g0, g1 = demo_data.demo_gsc_summary(l, 0), demo_data.demo_gsc_summary(l, 1)
        elif site and gsc_creds:
            g0 = _pre.get((l, "start"))
            g1 = _pre.get((l, "now"))
            g0 = g0 if isinstance(g0, dict) else None
            g1 = g1 if isinstance(g1, dict) else None
        ok = bool(g0 and g1 and g0.get("position") is not None and g1.get("position") is not None)
        gsc_by_lang[l] = {"site": bool(site and gsc_creds) or demo_mode, "g0": g0, "g1": g1, "ok": ok}

    def _gsc_pair(items):
        """Signals for trend_status; several markets are combined (impression-weighted position, summed top-10)."""
        items = [x for x in items if x["ok"]]
        if not items:
            return None

        def wavg(key):
            w = sum(x[key]["impressions"] for x in items)
            return sum(x[key]["position"] * x[key]["impressions"] for x in items) / w if w else None
        return {"pos_start": wavg("g0"), "pos_now": wavg("g1"), "top10_start": sum(x["g0"]["top10"] for x in items),
                "top10_now": sum(x["g1"]["top10"] for x in items)}

    # ── per market headline: Ahrefs (modelled) next to Search Console (measured by Google) ──
    from modules.ahrefs_ui import client_view as _cvh
    hide_ahrefs = ahrefs_missing and _cvh()     # client view without Ahrefs data: show Search Console only, no empty column
    cols = st.columns(len(langs))
    for i, l in enumerate(langs):
        agg = aggregate(history_by_lang[l])
        gs = gsc_by_lang[l]
        s = trend_status(agg, _gsc_pair([gs]))
        result[l] = s
        icon, label = STATUS_TXT[s["status"]]
        with cols[i]:
            st.markdown(f"**{(flags.get(l, '') + ' ' + l).strip()}** &nbsp; {icon} {label}")
            ca, cg = (None, st.container()) if hide_ahrefs else st.columns(2)
            with (ca if ca is not None else st.empty()):
                if ca is None:
                    pass
                elif ahrefs_missing:
                    st.caption("**Ahrefs** · modelled")
                    from modules.ahrefs_ui import client_view as _cv2
                    st.caption("Not part of this report yet." if _cv2() else
                               ("Not loaded (see the button above)." if api_key else "No Ahrefs key."))
                elif agg.empty or s["traffic_start"] is None:
                    st.caption("**Ahrefs** · modelled")
                    st.caption("Not enough Ahrefs data.")
                else:
                    st.caption("**Ahrefs** · modelled")
                    first, last = agg.iloc[0], agg.iloc[-1]
                    st.metric("Keywords ranked", f"{int(last['keywords']):,}", delta=int(last["keywords"] - first["keywords"]),
                              help="Keywords these pages rank for in Google's top 100, per Ahrefs.")
                    if s["top3_now"] is not None:
                        st.metric("Keywords in top 3", s["top3_now"], delta=s["top3_now"] - s["top3_start"])
                    if s["traffic_change"] is not None:
                        st.metric("Est. organic traffic", f"{s['traffic_now']:,.0f}", delta=f"{s['traffic_change']:+.0%}",
                                  help="Ahrefs model (position x volume x click rate), not measured visits.")
                    st.caption(f"{first['date']:%d %b %Y} → {last['date']:%d %b %Y}")
            with cg:
                st.caption("**Search Console** · measured by Google")
                g0, g1 = gs["g0"], gs["g1"]
                if not gs["ok"]:
                    st.caption("No Search Console access for this market yet." if not gs["site"] or (g0 is None or g1 is None)
                               else "No impressions recorded for these pages in the compared months.")
                else:
                    st.metric("Avg. position", f"{g1['position']:.1f}", delta=f"{g0['position'] - g1['position']:+.1f} places",
                              help="Impression-weighted average position of these pages over all queries, last complete month "
                                   "versus the first month of the look-back.")
                    st.metric("Queries in top 10", f"{g1['top10']:,}", delta=f"{g1['top10'] - g0['top10']:+,}",
                              help="Page + search query pairs on positions 1-10. Google hides rare queries, so this is "
                                   "lower than a keyword tool shows.")
                    st.metric("Impressions", f"{g1['impressions']:,.0f}",
                              delta=(f"{g1['impressions'] / g0['impressions'] - 1:+.0%}" if g0["impressions"] else None),
                              help="Times these pages were shown in Google results (a measured number).")
                    st.caption(f"{start_m:%b %Y} → {now_m:%b %Y}")
                result[f"{l}_gsc"] = {"start": g0, "now": g1}

    all_hist = {f"{l}|{u}": df for l in langs for u, df in history_by_lang[l].items()}
    result["_total"] = trend_status(aggregate(all_hist), _gsc_pair(list(gsc_by_lang.values())))

    # ── all URLs together ── (left out of the client view when there is no Ahrefs data)
    if not hide_ahrefs:
      with st.expander("📋 All pages we build links to: Ahrefs, first vs. latest snapshot"):
          frames = []
          for l in langs:
              t = per_url_table(history_by_lang[l])
              if not t.empty:
                  t.insert(0, "Market", l)
                  frames.append(t)
          if frames:
              st.dataframe(pd.concat(frames, ignore_index=True), width="stretch", hide_index=True, column_config={
                  "Landing Page": st.column_config.LinkColumn("Landing Page", max_chars=50),
                  "Traffic start": st.column_config.NumberColumn(format="%d"),
                  "Traffic now": st.column_config.NumberColumn(format="%d"),
                  "Change": st.column_config.NumberColumn("Traffic change (est.)", format="%+d"),
              })
          else:
              st.caption("Not part of this report yet.")

    st.caption("⚠️ A direction, not proof. Rankings also move because of content, technique and competition. Ahrefs figures are "
               "model estimates; Search Console figures are measured by Google but hide rare queries."
               + (" **DEMO DATA.**" if demo_mode else ""))
    return result
