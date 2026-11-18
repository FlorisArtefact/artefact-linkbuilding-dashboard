"""
Streamlit UI for the generic ROI & budget-advice module.
All maths lives in modules/roi_model.py; this file only renders.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.roi_model import (
    SCENARIOS, SCENARIO_LABELS, compute_roi, linked_page_metrics, merged_assumptions,
    sensitivity_grid, management_summary_text,
)

NAVY, PINK, TEAL, MID, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#8B9BB4", "#FFFFFF"
SCEN_COLORS = {"low": "#8B9BB4", "base": NAVY, "high": TEAL}

_CSS = """
<style>
.roi-hero{border-radius:14px;padding:1.4rem 1.6rem;background:linear-gradient(120deg,#1B2D5B 0%,#2A4080 60%,#8B1060 100%);
  color:#fff;margin-bottom:1rem;box-shadow:0 6px 24px rgba(27,45,91,.18)}
.roi-verdict{display:inline-block;padding:.35rem 1rem;border-radius:999px;font-weight:700;letter-spacing:.6px;font-size:.9rem;color:#fff}
.roi-reason{margin-top:.8rem;font-size:1.02rem;line-height:1.5;opacity:.95}
.roi-tiles{display:flex;gap:.8rem;margin-top:1.1rem;flex-wrap:wrap}
.roi-tile{flex:1;min-width:150px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);border-radius:10px;padding:.8rem 1rem}
.roi-tile.base{background:rgba(255,255,255,.22);border-color:rgba(255,255,255,.6)}
.roi-tile .lab{font-size:.72rem;text-transform:uppercase;letter-spacing:.8px;opacity:.75}
.roi-tile .big{font-size:1.9rem;font-weight:700;line-height:1.15}
.roi-tile .sub{font-size:.78rem;opacity:.8}
.roi-disc{background:#FFF8E1;border:1px solid #FFD54F;border-radius:8px;padding:.7rem 1rem;color:#6D4C00;font-size:.82rem;margin:.6rem 0 1rem}
.roi-badge{display:inline-block;padding:.1rem .55rem;border-radius:6px;font-size:.72rem;font-weight:600;margin-left:.4rem}
</style>
"""


def sidebar_assumptions(config: dict) -> dict:
    """Sidebar expander with the ROI assumptions (defaults from config.json 'roi'). Returns the assumptions to use."""
    a = merged_assumptions(config.get("roi"))
    with st.expander("🎛️ ROI assumptions", expanded=False):
        st.caption("Placeholders until validated with the client and pillar leads. Change them live to see the effect.")
        a["horizon_months"] = st.slider("Value horizon (months)", 6, 24, int(a["horizon_months"]), key="roi_horizon",
                                        help="How many months of value after placement are counted. 12 is conservative.")
        st.markdown("**Share of organic revenue credited to link building**")
        st.caption("Of the organic revenue on the linked pages, what share do we assume is due to the links "
                   "(rest = content, technique, brand, seasonality)?")
        c1, c2, c3 = st.columns(3)
        shares = sorted([
            c1.number_input("Low %", 1, 100,int(round(a["attribution_share"]["low"] * 100)), key="roi_sh_low"),
            c2.number_input("Real. %", 1, 100,int(round(a["attribution_share"]["base"] * 100)), key="roi_sh_base"),
            c3.number_input("High %", 1, 100,int(round(a["attribution_share"]["high"] * 100)), key="roi_sh_high"),
        ])
        a["attribution_share"] = {"low": shares[0] / 100, "base": shares[1] / 100, "high": shares[2] / 100}
        st.markdown("**Only if there is no GA4 revenue** (traffic mode)")
        d1, d2, d3 = st.columns(3)
        crs = sorted([
            d1.number_input("CR low %", 0.1, 20.0, round(a["conversion_rate"]["low"] * 100, 2), 0.1, key="roi_cr_low"),
            d2.number_input("CR real. %", 0.1, 20.0, round(a["conversion_rate"]["base"] * 100, 2), 0.1, key="roi_cr_base"),
            d3.number_input("CR high %", 0.1, 20.0, round(a["conversion_rate"]["high"] * 100, 2), 0.1, key="roi_cr_high"),
        ])
        a["conversion_rate"] = {"low": crs[0] / 100, "base": crs[1] / 100, "high": crs[2] / 100}
        a["value_per_conversion"] = st.number_input(
            f"Value per conversion ({a['currency_symbol']})", 0.0, 100000.0, float(a["value_per_conversion"]), 5.0,
            key="roi_vpc", help="Average order value (webshop) or average lead value (B2B). 0 = no value known: "
                                "no indicative return is then calculated from traffic.")
    return a


def _money(a: dict, v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}{a['currency_symbol']}{abs(v):,.0f}"


def _roi_txt(r) -> str:
    return f"{r:.1f}x" if r is not None else "—"


def render_roi_section(client: str, period_label: str, per_lang: dict, a: dict,
                       ga4_connected: bool, gsc_connected: bool, demo_mode: bool, flags: dict,
                       window_days: int = 90, window_txt: str = "last 90 days") -> None:
    """per_lang: {lang: {"links": df_of_live_links, "ga4": df, "gsc": df}} (already filtered to the period).
    window_days / window_txt: the period the GA4 revenue/traffic was measured over (scaled up to the horizon)."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div class="section-title">💼 Business value & budget signal</div>', unsafe_allow_html=True)

    # Aggregate per language
    rows, tot_inv, tot_rev, tot_traffic, tot_days = [], 0.0, 0.0, 0.0, window_days
    for lang, d in per_lang.items():
        links = d["links"]
        inv = float(links["Price"].sum()) if (not links.empty and "Price" in links.columns) else 0.0
        m = linked_page_metrics(links, d.get("ga4"), d.get("gsc"))
        # Traffic fallback order: GA4 organic sessions -> GSC clicks (90d) -> Ahrefs monthly estimate x3
        traffic = m["sessions"] or m["clicks"] or float(d.get("ahrefs_monthly") or 0) * 3
        res = compute_roi(inv, m["revenue"], traffic, tot_days, a)
        rows.append((lang, inv, m, res))
        tot_inv += inv
        tot_rev += m["revenue"]
        tot_traffic += traffic
    total = compute_roi(tot_inv, tot_rev, tot_traffic, tot_days, a)
    adv = total["advice"]

    tiles = ""
    # With revenue as basis and the same credited share in every scenario the three tiles would be identical
    same = total["mode"] == "revenue" and len({round(total["scenarios"][s]["share"], 4) for s in SCENARIOS}) == 1
    if total["mode"] is not None:
        for s in (("base",) if same else SCENARIOS):
            r = total["scenarios"][s]
            cls = "roi-tile base" if s == "base" else "roi-tile"
            lab = (f'Revenue vs. budget · {r["share"]:.0%} of page revenue counted' if same
                   else f'{SCENARIO_LABELS[s]} · {r["share"]:.0%} credited to links')
            tiles += (f'<div class="{cls}"><div class="lab">{lab}</div>'
                      f'<div class="big">{_roi_txt(r["roi"])}</div>'
                      f'<div class="sub">value {_money(a, r["value"])} · net {_money(a, r["net"])}</div></div>')
        pay = total["scenarios"]["base"]["payback_months"]
        pay_txt = f"{pay:.1f} months" if pay else "—"
        tiles += (f'<div class="roi-tile"><div class="lab">Investment</div><div class="big">{_money(a, total["investment"])}</div>'
                  f'<div class="sub">payback (realistic): {pay_txt}</div></div>')

    st.markdown(
        f'<div class="roi-hero">'
        f'<div style="font-size:.8rem;opacity:.75;letter-spacing:.6px;text-transform:uppercase">'
        f'Management summary · {client} · {period_label}</div>'
        f'<div style="margin-top:.5rem"><span class="roi-verdict" style="background:{adv["color"]}">{adv["verdict"]}</span>'
        + ('<span class="roi-verdict" style="background:rgba(255,255,255,.2);margin-left:.5rem">INDICATIVE · based on traffic estimate</span>'
           if total["mode"] == "traffic" else "") + '</div>'
        f'<div class="roi-reason">{adv["reason"]}</div>'
        f'<div class="roi-tiles">{tiles}</div></div>', unsafe_allow_html=True)

    if total["mode"] is None:
        st.info("💡 Connect **GA4** (revenue) or **Search Console** (organic clicks) to show revenue against budget. "
                "Until then the investment is shown but no value can be estimated.")
    else:
        mode_txt = ("measured **GA4 organic revenue** on the linked landing pages"
                    if total["mode"] == "revenue" else
                    "**estimated** from organic visits × assumed conversion rate × assumed value per conversion "
                    "(no GA4 revenue available — treat as indicative)")
        scale = (365.0 / max(tot_days, 1)) * (float(a["horizon_months"]) / 12.0)
        st.caption(f"Value basis: {mode_txt}. **How the bar is built:** revenue on the linked pages in {window_txt} "
                   f"({_money(a, tot_rev)}) × {scale:.1f} = projected over {int(a['horizon_months'])} months, "
                   f"set against the investment of the selected links ({_money(a, total['investment'])}).")

        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=["Investment"], y=[total["investment"]], marker_color=PINK, name="Investment",
                                 text=[_money(a, total["investment"])], textposition="outside"))
            for s in (("base",) if same else SCENARIOS):
                v = total["scenarios"][s]["value"]
                fig.add_trace(go.Bar(x=[f"Projected revenue, {int(a['horizon_months'])} months" if same else SCENARIO_LABELS[s] + " scenario"], y=[v], marker_color=SCEN_COLORS[s],
                                     name=SCENARIO_LABELS[s], text=[_money(a, v)], textposition="outside"))
            fig.add_hline(y=total["investment"], line=dict(color=PINK, width=1.5, dash="dash"),
                          annotation_text="break-even", annotation_position="top left",
                          annotation_font=dict(size=10, color=PINK))
            fig.update_layout(title=dict(text="Investment vs. projected value (revenue on linked pages)", font=dict(size=13, color=NAVY)),
                              showlegend=False, height=340, paper_bgcolor=WHITE, plot_bgcolor=WHITE,
                              font=dict(family="Roboto", color=NAVY, size=11), margin=dict(t=45, b=30, l=40, r=20),
                              yaxis=dict(gridcolor="#E8ECF2", zeroline=False), xaxis=dict(showgrid=False), bargap=0.35)
            st.plotly_chart(fig, width="stretch")
        with c2:
            shares, mults, z = sensitivity_grid(total["investment"], tot_rev, tot_traffic, tot_days, a)
            hm = go.Figure(go.Heatmap(
                x=[f"{s:.0%}" for s in shares], y=[f"{m:.0%}" for m in mults], z=z, zmin=0, zmax=4,
                colorscale=[[0, "#F8D7DA"], [0.25, "#FFE9B0"], [0.5, "#D9F0D3"], [1, "#2E9E5B"]],
                texttemplate="%{z:.1f}x", showscale=False, hoverongaps=False,
                hovertemplate="Attribution %{x}<br>Value base %{y}<br>Revenue vs. budget %{z:.2f}x<extra></extra>"))
            hm.update_layout(title=dict(text="Sensitivity: revenue vs. budget by attribution & value base (break-even = 1.0x)",
                                        font=dict(size=13, color=NAVY)),
                             height=340, paper_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
                             margin=dict(t=45, b=40, l=60, r=20),
                             xaxis=dict(title="Share attributed to link building"), yaxis=dict(title="Measured value ×"))
            st.plotly_chart(hm, width="stretch")

    # Per-language table
    # Values pre-formatted as text so the live dashboard and the static snapshot show the same thing.
    def _x(v):
        try:
            return "—" if v is None or pd.isna(v) else f"{float(v):.1f}x"
        except (TypeError, ValueError):
            return "—"
    table = []
    for lang, inv, m, res in rows:
        sc = res["scenarios"]
        table.append({
            "Market": f"{flags.get(lang, '')} {lang}".strip(), "Budget": _money(a, inv or 0),
            "Basis": {"revenue": "GA4 revenue", "traffic": "Traffic estimate", None: "—"}[res["mode"]],
            "Revenue vs. budget (cautious)": _x(sc["low"]["roi"]),
            "Revenue vs. budget (realistic)": _x(sc["base"]["roi"]),
            "Revenue vs. budget (optimistic)": _x(sc["high"]["roi"]),
            "Signal": res["advice"]["verdict"].capitalize(),
        })
    if table:
        st.markdown("**Per market**")
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)

    # Data notes + assumptions
    notes = []
    if demo_mode:
        notes.append("DEMO MODE — all numbers are synthetic.")
    notes.append(f"GA4: {'connected' if ga4_connected else 'not connected'}; Search Console: "
                 f"{'connected' if gsc_connected else 'not connected'}.")
    notes.append(f"Value basis: {total['mode'] or 'none available'}. Revenue/traffic window: {window_txt} ({tot_days} days), "
                 f"extrapolated to {int(a['horizon_months'])} months.")
    from modules.ahrefs_ui import client_view
    _client = client_view()
    if _client:
        notes.append("Share of page revenue counted for link building per scenario (cautious / realistic / optimistic): "
                     + " / ".join(f"{a['attribution_share'][s]:.0%}" for s in SCENARIOS) + ". These are working assumptions.")
    else:
        notes.append("Attribution shares (" + " / ".join(f"{a['attribution_share'][s]:.0%}" for s in SCENARIOS) +
                     ") are PLACEHOLDERS — not yet validated with BWJ, colleagues or pillar leads.")
    notes.append("Revenue is organic-search only and matched to linked landing pages by URL path; "
                 "cross-page halo effects and brand-search lift are not counted (conservative).")

    with st.expander("📐 Assumptions & data quality"):
        for n in notes:
            st.markdown(f"- {n}")
        if not _client:
            st.markdown(f"- Advice rule: increase if realistic ROI ≥ {a['thresholds']['increase_base_roi']}x **and** low ROI ≥ "
                        f"{a['thresholds']['increase_low_roi']}x; decrease if realistic ROI < {a['thresholds']['decrease_base_roi']}x; "
                        f"otherwise maintain. Thresholds are configurable in `config.json → roi.thresholds`.")

    with st.expander("🧭 How to read this — steering, not proof"):
        st.markdown(
            "- **This is decision support.** The signal points a direction; it does not prove that links caused revenue.\n"
            "- **Effects come with a delay.** Links often need weeks to months before rankings and revenue move. A recent "
            "link may simply not have had time to show.\n"
            "- **Pages can fall for reasons unrelated to links:** competition, technical issues (indexability, "
            "PageSpeed), weak content, internal cannibalisation, too few internal links.\n"
            "- **Links also lift the whole domain.** An expensive link to a deep page may not pay back on that page, "
            "yet strengthens the domain — the page-level figure therefore *understates* the total effect. Look at the "
            "domain trend below as well.\n"
            "- **Budget does not need to return 100 %.** Treat revenue vs. budget as a compass: is the direction good, and where "
            "does the money work best?\n"
            "- **“Credited to links” (" + " / ".join(f"{a['attribution_share'][s]:.0%}" for s in SCENARIOS) + ")** is the share of organic revenue on the linked pages that we "
            "assume is due to link building. " + ("It is a working assumption." if _client else
                                                  "It is an assumption to agree with the client and pillar leads.")
        )

    st.markdown('<div class="roi-disc">⚠️ <strong>Disclaimer.</strong> These are projections based on stated assumptions, '
                'not guarantees. Google\'s algorithm is a black box and organic results depend on many factors besides link '
                'building. Use the scenarios as decision support, not as a promise.</div>', unsafe_allow_html=True)

    if not _client:   # analyst export; the client reads the summary on the page
        st.download_button("⬇️ Download management summary (.md)",
                           management_summary_text(client, period_label, total, a, notes),
                           file_name=f"management-summary-{client.split(' ')[0].lower()}.md", mime="text/markdown")
    return total
