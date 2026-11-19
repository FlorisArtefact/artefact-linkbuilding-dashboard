"""
'Budget advice' tab. Main question: WHERE should the next link budget go? Answered per page, substantiated with
Google demand, current position, value per visit (GA4) and how pages respond to earlier links.
Whether a market's total budget could go up or down is secondary and sits at the bottom.
Maths in modules/budget_advice.py; this file only renders.
"""
import pandas as pd
import streamlit as st

from modules import budget_advice as ba

_CSS = """
<style>
.ba-hero{border-radius:14px;padding:1.3rem 1.6rem 1.4rem;background:linear-gradient(120deg,#1B2D5B 0%,#2A4080 60%,#8B1060 100%);
  color:#fff;margin-bottom:.6rem;box-shadow:0 6px 24px rgba(27,45,91,.18)}
.ba-hero .top{font-size:.78rem;opacity:.75;letter-spacing:.6px;text-transform:uppercase}
.ba-hero .h{font-size:1.55rem;font-weight:700;margin:.3rem 0 .9rem;line-height:1.25}
.ba-tiles{display:flex;gap:.8rem;flex-wrap:wrap}
.ba-tile{flex:1;min-width:170px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);border-radius:10px;padding:.75rem 1rem}
.ba-tile.main{flex:1.6;background:rgba(255,255,255,.22);border-color:rgba(255,255,255,.6)}
.ba-tile .lab{font-size:.7rem;text-transform:uppercase;letter-spacing:.8px;opacity:.78}
.ba-tile .big{font-size:1.7rem;font-weight:700;line-height:1.15;margin-top:.15rem;word-break:break-word}
.ba-tile .sub{font-size:.8rem;opacity:.85;margin-top:.15rem}
.ba-basis{font-size:.85rem;color:#4A5875;margin:.2rem 0 1rem}
.ba-chips{display:flex;gap:.5rem;flex-wrap:wrap;margin:.2rem 0 .6rem}
.ba-chip{border-radius:999px;padding:.2rem .75rem;font-size:.82rem;font-weight:600;background:#EEF1F6;color:#1B2D5B}
</style>
"""


def _money(v, cur="€") -> str:
    return "" if v is None or pd.isna(v) else f"{cur}{v:,.0f}"


def _short(u) -> str:
    k = ba.norm_key(u)
    path = k.split("/", 1)[1] if "/" in k else ""
    if not path:
        return "Homepage"
    parts = path.rstrip("/").split("/")
    last = parts[-1]
    if len(last) <= 6 and len(parts) > 1 and any(ch.isdigit() for ch in last):   # ids like S37231: use the segment before
        last = parts[-2]
    return last.replace("-", " ").capitalize()


def render_budget_advice(client: str, period_label: str, overall_key: str, market_rows: list, pages: pd.DataFrame,
                         targets: pd.DataFrame, pipeline: pd.DataFrame, pipeline_total: float, has_links: bool,
                         has_revenue: bool, currency: str = "€", market_names: dict | None = None,
                         allocation: pd.DataFrame | None = None, focus_set: bool = False) -> dict:
    st.markdown(_CSS, unsafe_allow_html=True)
    acts = pages["_action"].value_counts().to_dict() if pages is not None and not pages.empty else {}
    al = allocation if allocation is not None else pd.DataFrame()
    valued = "Extra revenue (90d, rough)" in al.columns

    # ── Management summary: a few tiles, one line ─────────────────────────────
    tiles = ""
    if not al.empty:
        top = al.iloc[0]
        tiles += (f'<div class="ba-tile main"><div class="lab">Best place for the next link</div>'
                  f'<div class="big">{_short(top["Page"])}</div>'
                  f'<div class="sub">{top["Share of next budget"]:.0%} of the next budget (proposal)'
                  + (f' · {top["Market"]}' if "Market" in al.columns else "") + '</div></div>')
        top3 = al.head(3)
        tiles += (f'<div class="ba-tile"><div class="lab">Top 3 pages together</div><div class="big">{top3["Share of next budget"].sum():.0%}</div>'
                  f'<div class="sub">{", ".join(_short(u) for u in top3["Page"])}</div></div>')
        n_linked = int((al["Links so far"] > 0).sum())
        tiles += (f'<div class="ba-tile"><div class="lab">In the plan</div><div class="big">{len(al)} pages</div>'
                  f'<div class="sub">{n_linked} with links already, {len(al) - n_linked} new</div></div>')
    if acts.get("pause"):
        tiles += (f'<div class="ba-tile"><div class="lab">Pause links</div><div class="big">{acts["pause"]} page(s)</div>'
                  f'<div class="sub">{", ".join(_short(u) for u in pages[pages["_action"] == "pause"]["Page"].head(2))}</div></div>')
    elif acts.get("wait"):
        tiles += (f'<div class="ba-tile"><div class="lab">Too early to judge</div><div class="big">{acts["wait"]} page(s)</div>'
                  f'<div class="sub">first link under {ba.WAIT_MONTHS} months old</div></div>')
    if not tiles:
        tiles = ('<div class="ba-tile main"><div class="lab">Not enough data</div><div class="big">No advice yet</div>'
                 '<div class="sub">Needs Search Console data and placed links</div></div>')
    st.markdown(f'<div class="ba-hero"><div class="top">Budget advice · {client} · {period_label}</div>'
                f'<div class="h">Where the next link budget works best</div>'
                f'<div class="ba-tiles">{tiles}</div></div>', unsafe_allow_html=True)
    basis = ["search demand and current position in Google (Search Console)"]
    if valued:
        basis.append("value per visit (GA4 organic revenue per page)")
    basis.append("how pages responded to earlier links")
    if focus_set:
        basis.append("your priority pages")
    st.markdown(f'<div class="ba-basis">Based on {", ".join(basis[:-1])} and {basis[-1]}. '
                'Shares and amounts are a proposal to discuss.</div>', unsafe_allow_html=True)

    # ── 1. Allocation ─────────────────────────────────────────────────────────
    if not al.empty:
        st.markdown('<div class="section-title">1 · Where to spend the next budget</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-hint">Pages ranked by what a better position is worth: how often they are '
                    'seen in Google, how far they are from the top 3' + (', what a visit earns' if valued else '')
                    + ', and whether earlier links already moved them. Pages already in the top 3 or far from page 1 are left out.'
                    '</div>', unsafe_allow_html=True)
        show = al.copy()
        cfg = {
            "Page": st.column_config.LinkColumn("Page"),
            "Share of next budget": st.column_config.ProgressColumn("Share of next budget (proposal)", format="percent",
                                                                    min_value=0, max_value=1),
            "Links so far": st.column_config.NumberColumn("Links so far", format="%d"),
            "Position": st.column_config.NumberColumn("Avg. position", format="%.1f"),
            "Impressions (90d)": st.column_config.NumberColumn("Seen in Google (90d)", format="%,.0f"),
            "Extra clicks (90d, rough)": st.column_config.NumberColumn("Extra clicks at top 3 (90d, rough)", format="%,.0f",
                help="Impressions × the difference in typical click rate between the current position and position 3."),
            "Value per visit": st.column_config.NumberColumn("Value per visit", format="€%.2f",
                help="GA4 organic revenue ÷ organic sessions of this page; site average when the page has too few visits."),
            "Extra revenue (90d, rough)": st.column_config.NumberColumn("Extra revenue at top 3 (90d, rough)", format="€%,.0f"),
            "Client focus": st.column_config.TextColumn("Your priority"),
            "Why here": st.column_config.TextColumn("Why here", width="large"),
        }
        order = [c for c in ["Market", "Page", "Share of next budget", "Links so far", "Position", "Impressions (90d)",
                             "Extra clicks (90d, rough)", "Value per visit", "Extra revenue (90d, rough)", "Client focus",
                             "Why here"] if c in show.columns]
        st.dataframe(show[order], width="stretch", hide_index=True, column_config=cfg)
        if not focus_set:
            st.caption("Your own priorities (for example a brand or product range you want to grow) can be added; "
                       "those pages then weigh 1.5× in the ranking.")

    # ── 2. Linked pages ───────────────────────────────────────────────────────
    if pages is not None and not pages.empty:
        st.markdown('<div class="section-title">2 · Pages with links: more, wait or pause?</div>', unsafe_allow_html=True)
        st.markdown('<div class="ba-chips">' + "".join(
            f'<span class="ba-chip">{ba.ACTIONS[a]}: {acts[a]}</span>' for a in
            ["more", "one_more", "pause", "wait", "keep", "watch"] if acts.get(a)) + '</div>', unsafe_allow_html=True)
        show = pages.drop(columns=[c for c in ["_action", "Impressions (90d)"] if c in pages.columns]).copy()
        if not has_revenue or not show["Development"].astype(bool).any():
            show = show.drop(columns=["Development"])
        st.dataframe(show, width="stretch", hide_index=True, column_config={
            "Page": st.column_config.LinkColumn("Page"),
            "Spent": st.column_config.NumberColumn("Spent (all time)", format="€%,.0f"),
            "First link": st.column_config.DateColumn("First link", format="DD-MM-YYYY"),
            "Latest link": st.column_config.DateColumn("Latest link", format="DD-MM-YYYY"),
            "Clicks (90d)": st.column_config.NumberColumn("Google clicks (90d)", format="%,.0f"),
            "Position": st.column_config.NumberColumn("Avg. Google position", format="%.1f"),
            "Development": st.column_config.TextColumn("Revenue development",
                                                       help="Year-over-year growth now vs. before the first link."),
        })

    # ── 3. Pipeline value ─────────────────────────────────────────────────────
    if pipeline is not None and not pipeline.empty:
        st.markdown('<div class="section-title">3 · Proposed domains with the most reach per euro</div>', unsafe_allow_html=True)
        st.dataframe(pipeline, width="stretch", hide_index=True, column_config={
            "Price": st.column_config.NumberColumn("Price", format="€%,.0f"),
            "DR": st.column_config.NumberColumn("DR", format="%d"),
            "Monthly organic visitors (Ahrefs est.)": st.column_config.NumberColumn(
                "Monthly organic visitors (est.)", format="%,.0f"),
            "Visitors per €": st.column_config.NumberColumn("Visitors per €", format="%,.0f"),
        })

    # ── Secondary: market totals ──────────────────────────────────────────────
    mt = ba.market_table(market_rows, currency) if (has_links and has_revenue) else pd.DataFrame()
    if not mt.empty:
        with st.expander("Per market: is there room for more budget? (secondary)"):
            for c in [c for c in ba.market_conclusion(mt, currency) if not c.startswith("Proposal")]:
                st.markdown(f"- {c}")
            show = mt.copy()
            show["Market"] = show["Market"].map(lambda m: (market_names or {}).get(m, m))
            show["Revenue vs. budget"] = show["Revenue vs. budget"].map(lambda v: "" if v is None or pd.isna(v) else f"{v:.1f}x")
            show["Spent"] = show["Spent"].map(lambda v: _money(v, currency))
            st.dataframe(show[["Market", "Spent", "Revenue vs. budget", "Signal"]], width="stretch", hide_index=True,
                         column_config={"Spent": st.column_config.TextColumn("Spent (selected period)"),
                                        "Signal": st.column_config.TextColumn("Room for more budget?")})

    with st.expander("📐 How this advice is made"):
        st.markdown("- Ranking of pages: extra clicks a move to position 3 would roughly bring (impressions × typical "
                    "click-rate gain)" + (" × value per visit (GA4)" if valued else "") + ", × 1.2 for pages that already "
                    "respond to links" + (", × 1.5 for your priority pages" if focus_set else "") +
                    ". The share of the next budget follows that score.")
        for r in ba.RULES:
            st.markdown(f"- {r}")
        st.markdown("- Links also lift the whole domain and work with a delay, so a page-level signal is a direction, not proof.")
    return {}
