"""UI for the free health checks: other reasons a page may not be moving (technical) and whether links still stand."""
import pandas as pd
import streamlit as st

from modules import health_check as hc


@st.cache_data(ttl=3600, show_spinner=False)
def _landing(urls: tuple) -> list:
    return hc.run_landing_checks(list(urls))


@st.cache_data(ttl=3600, show_spinner=False)
def _links(pairs: tuple) -> list:
    return hc.run_link_checks(list(pairs))


def render_health_section(raw_links: dict, flags: dict, demo_mode: bool) -> None:
    st.markdown('<div class="section-title">🩺 Health check: are the links and pages doing their job?</div>',
                unsafe_allow_html=True)
    st.caption("Free checks that rule out technical reasons when a page does not move: is the landing page reachable and "
               "indexable, and is each placed link still live and followed? Runs only when you press the button.")
    frames = [d for d in raw_links.values() if d is not None and not d.empty and "Live Link" in d.columns]
    if not frames:
        st.info("No placements to check.")
        return
    links = pd.concat(frames, ignore_index=True).dropna(subset=["Live Link"])
    pl = links[links.get("Link to", pd.Series(dtype=str)).astype(str).str.startswith("http")]
    pairs = tuple(sorted({(str(a), str(b)) for a, b in zip(pl["Live Link"], pl["Link to"])}))
    pages = tuple(sorted({b for _, b in pairs}))
    if not pairs:
        st.info("No placements with a target URL yet.")
        return
    if not st.button(f"▶ Run health check ({len(pages)} landing pages + {len(pairs)} links)", key="run_health"):
        st.session_state.setdefault("health_done", False)
        if not st.session_state.get("health_done"):
            return
    st.session_state["health_done"] = True
    with st.spinner("Checking pages and links…"):
        lp = pd.DataFrame(hc.demo_landing(list(pages)) if demo_mode else _landing(pages))
        lk = pd.DataFrame(hc.demo_links(list(pairs)) if demo_mode else _links(pairs))

    lp_bad, lk_bad = lp[lp["Issues"] != "OK"], lk[lk["Result"] != "OK"]
    lost = lk[(~lk["Link present"])]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Landing pages OK", f"{len(lp) - len(lp_bad)} / {len(lp)}")
    c2.metric("Landing pages with an issue", len(lp_bad))
    c3.metric("Links OK", f"{len(lk) - len(lk_bad)} / {len(lk)}")
    c4.metric("Links missing / dead", len(lost), help="Article is gone (HTTP error) or our link is no longer in it.")

    if len(lp_bad):
        with st.expander(f"⚠️ Landing pages with issues ({len(lp_bad)})", expanded=True):
            st.dataframe(lp_bad[["Landing Page", "Status", "Issues", "Seconds"]], width="stretch", hide_index=True)
    if len(lk_bad):
        with st.expander(f"⚠️ Links to follow up ({len(lk_bad)})", expanded=True):
            st.dataframe(lk_bad[["Live Link", "Link to", "Result"]], width="stretch", hide_index=True,
                         column_config={"Live Link": st.column_config.LinkColumn("Live Link", max_chars=60)})
    if not len(lp_bad) and not len(lk_bad):
        st.success("Everything checked looks fine technically.")
    st.caption("Indicative: some sites block automated requests (shown as errors), and a canonical or redirect is not always "
               "a problem. Use this as a to-do list for follow-up with the publisher or the site team."
               + (" **DEMO DATA.**" if demo_mode else ""))
