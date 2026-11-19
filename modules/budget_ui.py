"""
'Budget advice' tab: what to do with the link budget, in plain words first, the tables behind it below.
Maths in modules/budget_advice.py; this file only renders.
"""
import pandas as pd
import streamlit as st

from modules import budget_advice as ba

NAVY, PINK = "#1B2D5B", "#E5007D"
_HEAD = {
    "increase": ("RAISE THE BUDGET", "#1E9E5A"),
    "maintain": ("KEEP THE BUDGET, SHIFT WITHIN IT", "#E08A00"),
    "decrease": ("LOWER OR SHIFT THE BUDGET", "#D93636"),
    "start": ("START PHASE: WHERE THE FIRST BUDGET GOES", "#00B4C8"),
    "unknown": ("NOT ENOUGH DATA FOR A BUDGET CHANGE YET", "#8B9BB4"),
}
_CSS = """
<style>
.ba-hero{border-radius:14px;padding:1.3rem 1.6rem;background:linear-gradient(120deg,#1B2D5B 0%,#2A4080 60%,#8B1060 100%);
  color:#fff;margin-bottom:1rem;box-shadow:0 6px 24px rgba(27,45,91,.18)}
.ba-hero .top{font-size:.8rem;opacity:.75;letter-spacing:.6px;text-transform:uppercase}
.ba-verdict{display:inline-block;margin-top:.5rem;padding:.35rem 1rem;border-radius:999px;font-weight:700;letter-spacing:.6px;font-size:.9rem}
.ba-hero ol{margin:.9rem 0 0 1.1rem;padding:0;font-size:1rem;line-height:1.55}
.ba-hero li{margin-bottom:.35rem}
.ba-chips{display:flex;gap:.5rem;flex-wrap:wrap;margin:.2rem 0 .6rem}
.ba-chip{border-radius:999px;padding:.2rem .75rem;font-size:.82rem;font-weight:600;background:#EEF1F6;color:#1B2D5B}
</style>
"""


def _money(v, cur="€") -> str:
    return "" if v is None or pd.isna(v) else f"{cur}{v:,.0f}"


def render_budget_advice(client: str, period_label: str, overall_key: str, market_rows: list, pages: pd.DataFrame,
                         targets: pd.DataFrame, pipeline: pd.DataFrame, pipeline_total: float, has_links: bool,
                         has_revenue: bool, currency: str = "€", market_names: dict | None = None) -> dict:
    """Returns {"key", "headline", "conclusions"} for the scorecard."""
    st.markdown(_CSS, unsafe_allow_html=True)
    mt = ba.market_table(market_rows, currency) if (has_links and has_revenue) else pd.DataFrame()
    key = overall_key if has_links else "start"
    if key not in _HEAD:
        key = "unknown"
    conclusions: list[str] = []
    if not mt.empty:
        conclusions += ba.market_conclusion(mt, currency)
    acts = pages["_action"].value_counts().to_dict() if pages is not None and not pages.empty else {}

    def _short(u):
        k = ba.norm_key(u)
        return k.split("/", 1)[1] if "/" in k and k.split("/", 1)[1] else "homepage"
    if acts.get("more"):
        top = pages[pages["_action"] == "more"]["Page"].head(3).map(_short).tolist()
        conclusions.append(f"Put the next links on the {acts['more']} page(s) that already respond, for example "
                           + ", ".join(f"/{t}" if t != "homepage" else t for t in top) + ".")
    if acts.get("pause"):
        conclusions.append(f"Pause links to {acts['pause']} page(s) that have {ba.MANY_LINKS}+ links without progress; "
                           "check their content and technique first. That budget can go to the pages above.")
    if acts.get("wait"):
        conclusions.append(f"{acts['wait']} page(s) received links recently; judge them in about {ba.WAIT_MONTHS} months.")
    if targets is not None and not targets.empty:
        t3 = ", ".join(f"/{_short(u)}" if _short(u) != "homepage" else "homepage" for u in targets["Page"].head(3))
        lead = "Spend the first budget on" if not has_links else "New candidates without links yet:"
        conclusions.append(f"{lead} pages that already rank just below the top of Google, such as {t3}.")
    if pipeline is not None and not pipeline.empty:
        best = pipeline.head(5)
        conclusions.append(f"Of the proposed domains ({_money(pipeline_total, currency)} in total), the 5 domains with the "
                           f"most reach per euro cost {_money(best['Price'].sum(), currency)} together (one link each): "
                           + ", ".join(best["Domain"].astype(str)) + ". Start there.")
    if not conclusions:
        conclusions.append("There is not enough spend, revenue or Google data in the selected period to advise a change yet.")

    label, color = _HEAD[key]
    st.markdown(
        f'<div class="ba-hero"><div class="top">Budget advice · {client} · {period_label}</div>'
        f'<div class="ba-verdict" style="background:{color}">{label}</div>'
        f'<ol>{"".join(f"<li>{c}</li>" for c in conclusions)}</ol></div>', unsafe_allow_html=True)
    st.caption("Amounts and steps are proposals based on the rules under 'How this advice is made'. "
               "We decide together, with your context on margins, stock and seasons.")

    # 1) Markets
    if not mt.empty:
        st.markdown('<div class="section-title">1 · Per market: raise, keep or lower?</div>', unsafe_allow_html=True)
        show = mt.copy()
        show["Market"] = show["Market"].map(lambda m: (market_names or {}).get(m, m))
        show["Revenue vs. budget"] = show["Revenue vs. budget"].map(lambda v: "" if v is None or pd.isna(v) else f"{v:.1f}x")
        show["Proposed change"] = show.apply(lambda r: "" if r["key"] == "unknown" else f"{r['Proposed change']:+.0%}", axis=1)
        show["Spent"] = show["Spent"].map(lambda v: _money(v, currency))
        show["Proposed budget"] = show.apply(lambda r: "" if r["key"] == "unknown" else _money(r["Proposed budget"], currency), axis=1)
        st.dataframe(show[["Market", "Spent", "Revenue vs. budget", "Signal", "Proposed change", "Proposed budget"]],
                     width="stretch", hide_index=True, column_config={
                         "Spent": st.column_config.TextColumn("Spent (selected period)"),
                         "Revenue vs. budget": st.column_config.TextColumn(
                             "Revenue vs. budget", help="Organic revenue on the linked pages, projected over 12 months, "
                                                        "divided by the link budget. See the 'Revenue vs. budget' tab."),
                         "Proposed budget": st.column_config.TextColumn("Proposed budget (next period, proposal)")})

    # 2) Pages that received links
    n = "2" if not mt.empty else "1"
    if pages is not None and not pages.empty:
        st.markdown(f'<div class="section-title">{n} · Pages with links: more, wait or pause?</div>', unsafe_allow_html=True)
        st.markdown('<div class="ba-chips">' + "".join(
            f'<span class="ba-chip">{ba.ACTIONS[a]}: {acts[a]}</span>' for a in
            ["more", "one_more", "pause", "wait", "keep", "watch"] if acts.get(a)) + '</div>', unsafe_allow_html=True)
        show = pages.drop(columns=["_action"]).copy()
        if not has_revenue or not show["Development"].astype(bool).any():
            show = show.drop(columns=["Development"])
        st.dataframe(show, width="stretch", hide_index=True, column_config={
            "Page": st.column_config.LinkColumn("Page"),
            "Spent": st.column_config.NumberColumn("Spent (all time)", format="€%,.0f"),
            "First link": st.column_config.DateColumn("First link", format="DD-MM-YYYY"),
            "Latest link": st.column_config.DateColumn("Latest link", format="DD-MM-YYYY"),
            "Clicks (90d)": st.column_config.NumberColumn("Google clicks (90d)", format="%,.0f"),
            "Position": st.column_config.NumberColumn("Avg. Google position", format="%.1f",
                                                      help="Average over all search terms the page shows up for (Search Console)."),
            "Development": st.column_config.TextColumn("Revenue development",
                                                       help="Year-over-year growth now vs. before the first link."),
        })
        n = str(int(n) + 1)

    # 3) New targets
    if targets is not None and not targets.empty:
        st.markdown(f'<div class="section-title">{n} · Where the next links help most</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-hint">Pages <b>without links</b> that already rank on positions '
                    f'{ba.PUSH_POS[0]:.0f}–{ba.PUSH_POS[1]:.0f} in Google and are seen often. A few positions up there brings '
                    'the most extra visitors per link. Last 90 days, Search Console.</div>', unsafe_allow_html=True)
        st.dataframe(targets, width="stretch", hide_index=True, column_config={
            "Page": st.column_config.LinkColumn("Page"),
            "Clicks (90d)": st.column_config.NumberColumn("Clicks (90d)", format="%,.0f"),
            "Impressions (90d)": st.column_config.NumberColumn("Impressions (90d)", format="%,.0f"),
            "Position": st.column_config.NumberColumn("Avg. position", format="%.1f"),
            "Extra clicks per 90d at position 3 (rough)": st.column_config.NumberColumn(
                "Extra clicks at position 3 (rough, 90d)", format="%,.0f",
                help="Impressions × the difference in typical click rate between the current position and position 3. "
                     "Only to rank the pages; not a forecast."),
        })
        n = str(int(n) + 1)

    # 4) Pipeline value
    if pipeline is not None and not pipeline.empty:
        st.markdown(f'<div class="section-title">{n} · Proposed domains with the most reach per euro</div>', unsafe_allow_html=True)
        st.dataframe(pipeline, width="stretch", hide_index=True, column_config={
            "Price": st.column_config.NumberColumn("Price", format="€%,.0f"),
            "DR": st.column_config.NumberColumn("DR", format="%d"),
            "Monthly organic visitors (Ahrefs est.)": st.column_config.NumberColumn(
                "Monthly organic visitors (est.)", format="%,.0f"),
            "Visitors per €": st.column_config.NumberColumn("Visitors per €", format="%,.0f"),
        })

    with st.expander("📐 How this advice is made"):
        for r in ba.RULES:
            st.markdown(f"- {r}")
        st.markdown("- Links also lift the whole domain and work with a delay, so a page-level signal is a direction, not proof.")
    return {"key": key, "headline": label, "conclusions": conclusions}
