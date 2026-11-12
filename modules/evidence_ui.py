"""Tab 'Effect on organic': is the development better since link building started? Pages with links vs. without,
the whole domain, and domain authority — all year-over-year so seasonality is out of the picture."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules import evidence_model as ev

NAVY, PINK, TEAL, MID, WHITE = "#1B2D5B", "#E5007D", "#00B4C8", "#8B9BB4", "#FFFFFF"
GROUP_COLORS = {"Pages with links": PINK, "Pages without links": MID, "Whole domain": NAVY}


def combine(per_lang: dict, langs: list):
    """Pool several markets into one monthly table + one links table (paths prefixed so markets never collide)."""
    ms, ls = [], []
    for lang in langs:
        d = per_lang.get(lang, {})
        m, lk = d.get("monthly"), d.get("links")
        if m is not None and not m.empty:
            ms.append(m.assign(path=f"/{lang}" + m["path"].astype(str)))
        if lk is not None and not lk.empty and "Link to" in lk.columns:
            ls.append(lk.assign(**{"Link to": f"https://x/{lang}" + lk["Link to"].astype(str).str.replace(r"^https?://[^/]+", "", regex=True)}))
    return (pd.concat(ms, ignore_index=True) if ms else pd.DataFrame(),
            pd.concat(ls, ignore_index=True) if ls else pd.DataFrame())


def _pct(v, digits=0):
    return "n/a" if v is None or pd.isna(v) else f"{v:+.{digits}%}"


def _pp(v):
    return "n/a" if v is None or pd.isna(v) else f"{v * 100:+.0f} pp"


def _verdict_box(s: dict, metric: str) -> None:
    v = s.get("verdict")
    g = s["groups"]["Pages with links"]
    d = s["groups"]["Whole domain"]
    since = f"{s['campaign_start']:%b %Y}"
    msgs = {
        "accelerating": ("#1E9E5A", "Pages with links are growing faster than before the campaign",
                         f"Year-over-year, linked pages went from {_pct(g['yoy_before'])} (before {since}) to {_pct(g['yoy_now'])} "
                         f"(last 3 months): {_pp(g['acceleration'])}. The whole domain: {_pct(d['yoy_before'])} → {_pct(d['yoy_now'])}."),
        "stable": ("#8B9BB4", "No clear change yet on the linked pages",
                   f"Linked pages: {_pct(g['yoy_before'])} → {_pct(g['yoy_now'])} year-over-year. The whole domain: "
                   f"{_pct(d['yoy_before'])} → {_pct(d['yoy_now'])}."),
        "slowing": ("#E08A00", "Linked pages are not outgrowing their own past yet",
                    f"Linked pages: {_pct(g['yoy_before'])} → {_pct(g['yoy_now'])} year-over-year ({_pp(g['acceleration'])}). Check the "
                    "other causes listed below before drawing conclusions."),
        "too_early": ("#8B9BB4", "Too early to judge",
                      f"The first links date from {since}; only {s['months_since']} complete month(s) have passed. Links need "
                      f"about {ev.MIN_MONTHS}+ months, commercial terms often 6–12."),
        "no_baseline": ("#8B9BB4", "Not enough history on the linked pages",
                        "These pages had little or no organic traffic a year ago, so a year-over-year comparison is not possible. "
                        "See the page table: new pages are shown by their current level."),
    }
    color, title, body = msgs.get(v, ("#8B9BB4", "No data", ""))
    ga, da = g.get("acceleration"), d.get("acceleration")
    if v in ("accelerating", "stable", "slowing") and ga is not None and da is not None and da > ga + 0.05:
        body += (f" <b>Note:</b> the whole domain improved even more ({_pp(da)}) than the linked pages ({_pp(ga)}). That fits with links "
                 "lifting the entire site (homepage and category links), but it can also be other causes such as promotions or "
                 "seasonality-independent events, so read it as a direction.")
    elif v in ("accelerating", "stable", "slowing") and ga is not None and da is not None and ga > da + 0.05:
        body += f" The whole domain changed {_pp(da)}, so the linked pages stand out from the rest of the site."
    st.markdown(f"""<div style="background:#fff;border:1px solid #E8ECF2;border-left:6px solid {color};border-radius:12px;
        padding:.9rem 1.2rem;box-shadow:0 2px 10px rgba(27,45,91,.06);margin:.3rem 0 .8rem">
        <div style="font-size:.72rem;text-transform:uppercase;letter-spacing:.8px;color:{MID}">Verdict · {metric.lower()} · campaign since {since}</div>
        <div style="font-size:1.2rem;font-weight:700;color:{NAVY};margin:.2rem 0">{title}</div>
        <div style="font-size:.88rem;color:#4A5875">{body}</div></div>""", unsafe_allow_html=True)


def _yoy_chart(pv: pd.DataFrame, links_df: pd.DataFrame, start, title: str) -> go.Figure:
    fig = go.Figure()
    groups = ev.group_series(pv, ev.linked_paths(links_df))
    for name, s in groups.items():
        c = ev.yoy_curve(s)
        if c.empty:
            continue
        fig.add_trace(go.Scatter(x=c.index, y=c.values, name=name, mode="lines",
                                 line=dict(color=GROUP_COLORS[name], width=3 if name != "Whole domain" else 2,
                                           dash="dot" if name == "Whole domain" else "solid")))
    if start is not None:
        fig.add_vrect(x0=start, x1=start + pd.DateOffset(months=ev.MIN_MONTHS), fillcolor="#FFF3CD", opacity=0.55, line_width=0,
                      layer="below")
        fig.add_shape(type="line", x0=start, x1=start, y0=0, y1=1, yref="paper", line=dict(color=NAVY, width=1.5, dash="dash"))
        fig.add_annotation(x=start, y=1.02, yref="paper", text="first links", showarrow=False, font=dict(size=11, color=NAVY))
    fig.add_hline(y=0, line_color="#C9D2E0", line_width=1)
    fig.update_layout(title=dict(text=title, font=dict(size=13, color=NAVY)), height=360, paper_bgcolor=WHITE, plot_bgcolor=WHITE,
                      font=dict(family="Roboto", color=NAVY, size=11), margin=dict(t=50, b=30, l=50, r=20),
                      legend=dict(orientation="h", y=-0.15), yaxis=dict(tickformat="+.0%", gridcolor="#E8ECF2", zeroline=False),
                      xaxis=dict(showgrid=False), hovermode="x unified")
    return fig


def _authority_chart(h: pd.DataFrame, start) -> go.Figure:
    fig = go.Figure()
    if "Refdomains" in h and h["Refdomains"].notna().any():
        fig.add_trace(go.Bar(x=h["month"], y=h["Refdomains"], name="Referring domains", marker_color="#C9D2E0", yaxis="y2"))
    if "DR" in h and h["DR"].notna().any():
        fig.add_trace(go.Scatter(x=h["month"], y=h["DR"], name="Domain Rating", mode="lines+markers", line=dict(color=PINK, width=3)))
    if start is not None:
        fig.add_shape(type="line", x0=start, x1=start, y0=0, y1=1, yref="paper", line=dict(color=NAVY, width=1.5, dash="dash"))
    fig.update_layout(title=dict(text="Domain authority: Domain Rating and referring domains", font=dict(size=13, color=NAVY)),
                      height=320, paper_bgcolor=WHITE, plot_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
                      margin=dict(t=50, b=30, l=50, r=50), legend=dict(orientation="h", y=-0.15),
                      yaxis=dict(title="DR", gridcolor="#E8ECF2", zeroline=False),
                      yaxis2=dict(title="Ref. domains", overlaying="y", side="right", showgrid=False), xaxis=dict(showgrid=False),
                      hovermode="x unified")
    return fig


def render_evidence_section(per_lang: dict, langs: list, domains: dict, history: dict, gsc_monthly: dict, currency: str,
                            categories: dict | None, content_keywords: list | None, demo_mode: bool, flags: dict):
    """per_lang: {lang: {"monthly": df|None, "links": df}}; history: {lang: Ahrefs domain history df};
    gsc_monthly: {lang: df}. Returns a small headline dict for the scorecard."""
    st.markdown('<div class="section-title">🏆 Is the organic development better since link building started?</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-hint">Every number compares a period with the <b>same months one year earlier</b>, so seasonality '
                'is out. We look at the pages that received links, at pages that did not, and at the whole domain.</div>',
                unsafe_allow_html=True)
    have = [l for l in langs if per_lang.get(l, {}).get("monthly") is not None and not per_lang[l]["monthly"].empty]
    c1, c2 = st.columns([2, 2])
    options = (["All markets"] if len(have) > 1 else []) + have
    market = c1.selectbox("Market", options or ["—"], key=f"ev_market_{'-'.join(have)}")
    metric = c2.radio("Measure", ["Organic revenue", "Organic sessions"], horizontal=True, key="ev_metric",
                      help="Sessions are steadier month to month; revenue is what the business cares about.")
    headline = None
    if not have:
        st.info("💡 Waiting for GA4 (monthly organic revenue per page). The authority view below already works with Ahrefs.")
    else:
        sel = have if market == "All markets" else [market]
        monthly, links = combine(per_lang, sel)
        value = "Revenue" if metric == "Organic revenue" else "Sessions"
        from modules.growth_model import monthly_pivot
        pv = monthly_pivot(monthly, value=value)
        s = ev.summary(pv, links) if not pv.empty else {}
        if not s:
            st.info("Not enough data to compare (needs link dates and at least a year of monthly history).")
        else:
            _verdict_box(s, metric)
            cur = currency if value == "Revenue" else ""
            k = st.columns(4)
            for col, name in zip(k[:3], ["Pages with links", "Pages without links", "Whole domain"]):
                g = s["groups"][name]
                col.metric(name, _pct(g["yoy_now"]), delta=f"before campaign: {_pct(g['yoy_before'])}" if g["yoy_before"] is not None
                           else "no baseline before", delta_color="off",
                           help="Last 3 complete months versus the same 3 months a year earlier.")
            if s.get("above_control_value") is not None:
                v = s["above_control_value"]
                k[3].metric("Linked pages vs. trend of unlinked pages", (f"{'+' if v >= 0 else '-'}{cur}{abs(v):,.0f}"),
                            help="Last 3 months: what the linked pages did minus what they would have done if they had followed the "
                                 "growth of the pages WITHOUT links. An estimate: homepage and category links also lift the unlinked "
                                 "pages, so the real effect is probably larger than this number.")
            st.plotly_chart(_yoy_chart(pv, links, s["campaign_start"],
                                       f"Year-over-year growth of {metric.lower()} (rolling 3 months) · {market}"), width="stretch")
            st.caption("Yellow band = first 3 months after the first link: too early to expect an effect. If the pink line rises above the "
                       "grey one after the dashed line, linked pages are doing better than the rest.")

            # Share of the domain: works for NEW pages too (no year-ago baseline needed) and cancels seasonality.
            grp = ev.group_series(pv, ev.linked_paths(links))
            tot = grp["Whole domain"].rolling(3).sum()
            share = (grp["Pages with links"].rolling(3).sum() / tot.where(tot > 0)).dropna()
            share = share[share.index >= s["campaign_start"] - pd.DateOffset(months=15)]
            if len(share) > 3:
                pre = share[share.index < s["campaign_start"]]
                a_, b_ = (pre.iloc[-1] if len(pre) else None), share.iloc[-1]
                f2 = go.Figure(go.Scatter(x=share.index, y=share.values, mode="lines", line=dict(color=PINK, width=3), name="Share"))
                f2.add_vrect(x0=s["campaign_start"], x1=s["campaign_start"] + pd.DateOffset(months=ev.MIN_MONTHS), fillcolor="#FFF3CD",
                             opacity=0.55, line_width=0, layer="below")
                f2.add_shape(type="line", x0=s["campaign_start"], x1=s["campaign_start"], y0=0, y1=1, yref="paper",
                             line=dict(color=NAVY, width=1.5, dash="dash"))
                f2.update_layout(title=dict(text=f"Share of {metric.lower()} that comes from the pages that received links (rolling 3 months)",
                                            font=dict(size=13, color=NAVY)), height=280, paper_bgcolor=WHITE, plot_bgcolor=WHITE,
                                 font=dict(family="Roboto", color=NAVY, size=11), margin=dict(t=50, b=30, l=50, r=20),
                                 yaxis=dict(tickformat=".0%", gridcolor="#E8ECF2", zeroline=False, rangemode="tozero"),
                                 xaxis=dict(showgrid=False))
                st.plotly_chart(f2, width="stretch")
                st.caption(("Share before the campaign: " + (f"{a_:.1%}" if a_ is not None else "n/a") + f" → now {b_:.1%}. ") +
                           "Works for new pages too: if the linked pages take a growing share of the site's organic results, they are "
                           "doing better than the rest, whatever the season.")
            headline = {"verdict": s["verdict"], "metric": metric, "market": market, "acceleration": s["groups"]["Pages with links"]["acceleration"],
                        "yoy_now_linked": s["groups"]["Pages with links"]["yoy_now"], "yoy_now_domain": s["groups"]["Whole domain"]["yoy_now"],
                        "yoy_before_domain": s["groups"]["Whole domain"]["yoy_before"]}

            pt = ev.page_table(pv, links, content_keywords, categories)
            if not pt.empty:
                st.markdown('<div class="section-title">By type of page</div>', unsafe_allow_html=True)
                st.markdown('<div class="section-hint">Homepage and category links also lift the whole domain; commercial pages show '
                            'their own development. Pages younger than 3 months are not counted.</div>', unsafe_allow_html=True)
                ct = ev.cohort_table(pt, "Type")
                if not ct.empty:
                    st.dataframe(ct.drop(columns=["Last 3 months", "Same months last year"]), width="stretch", hide_index=True,
                                 column_config={"YoY now (pooled)": st.column_config.NumberColumn("YoY now (pooled)", format="percent")})
                new = pt[(pt["Status"] == "No baseline (new page)") & (pt["Months since"] >= ev.MIN_MONTHS)]
                if len(new):
                    st.info(f"**{len(new)} linked pages had little or no organic {'revenue' if value == 'Revenue' else 'traffic'} a year ago** "
                            f"(new or rebuilt pages). A year-over-year comparison is not possible for them; together they delivered "
                            f"{cur}{new['Last 3 months'].sum():,.0f} in the last 3 months.")
                with st.expander(f"📋 All linked pages ({len(pt)})"):
                    show = pt[["Landing Page", "Type", "Category", "First link", "Months since", "YoY before", "YoY now", "Acceleration",
                               "Last 3 months", "Status"]].copy()
                    for c in ("YoY before", "YoY now", "Acceleration"):
                        show[c] = show[c] * 100
                    show["First link"] = show["First link"].dt.strftime("%b %Y")
                    st.dataframe(show, width="stretch", hide_index=True, column_config={
                        "YoY before": st.column_config.NumberColumn(format="%+.0f%%"), "YoY now": st.column_config.NumberColumn(format="%+.0f%%"),
                        "Acceleration": st.column_config.NumberColumn("Change (pp)", format="%+.0f"),
                        "Last 3 months": st.column_config.NumberColumn(format="%,.0f")})

    # ── Whole-domain authority & search visibility (works without GA4) ─────────────
    st.markdown('<div class="section-title">The whole domain: authority and search visibility</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-hint">Links also lift the entire site. Authority and total visibility show that part of the story, '
                'including links to the homepage.</div>', unsafe_allow_html=True)
    dom_market = market if market in langs else (langs[0] if langs else None)
    if len(langs) > 1:
        dom_market = st.selectbox("Domain", langs, index=langs.index(dom_market) if dom_market in langs else 0,
                                  key="ev_dom_market", format_func=lambda l: f"{flags.get(l, '')} {l} · {domains.get(l, '')}")
    h = history.get(dom_market)
    start = ev.campaign_start(per_lang.get(dom_market, {}).get("links"))
    if h is not None and not h.empty:
        first, last = h.iloc[0], h.iloc[-1]
        at_start = h[h["month"] <= (start or h["month"].min())]
        ref = at_start.iloc[-1] if len(at_start) else first
        a, b, c = st.columns(3)
        if "DR" in h:
            a.metric("Domain Rating", f"{last['DR']:.0f}", delta=f"{last['DR'] - ref['DR']:+.0f} since campaign start", delta_color="normal")
        if "Refdomains" in h:
            b.metric("Referring domains", f"{last['Refdomains']:,.0f}", delta=f"{last['Refdomains'] - ref['Refdomains']:+,.0f} since campaign start")
        if "OrgTraffic" in h:
            c.metric("Organic traffic (Ahrefs estimate)", f"{last['OrgTraffic']:,.0f}",
                     delta=f"{last['OrgTraffic'] / ref['OrgTraffic'] - 1:+.0%} since campaign start" if ref["OrgTraffic"] else None)
        st.plotly_chart(_authority_chart(h, start), width="stretch")
        st.caption("Domain Rating moves slowly and on a logarithmic scale, so a small campaign rarely moves it by itself; referring "
                   "domains and traffic are the more sensitive signals. Referring domains also grow from links outside this "
                   "campaign. Ahrefs numbers are estimates." + (" **DEMO DATA.**" if demo_mode else ""))
    else:
        from modules.ahrefs_ui import client_view
        st.info("Domain authority history is not part of this report yet." if client_view() else
                "Ahrefs history is not loaded for this domain (use the load button above, once Ahrefs is switched on).")
    g = gsc_monthly.get(dom_market)
    if g is not None and not g.empty:
        fig = go.Figure(go.Scatter(x=g["month"], y=g["Clicks"], mode="lines+markers", line=dict(color=TEAL, width=3), name="Clicks"))
        if start is not None:
            fig.add_shape(type="line", x0=start, x1=start, y0=0, y1=1, yref="paper", line=dict(color=NAVY, width=1.5, dash="dash"))
        fig.update_layout(title=dict(text="Google organic clicks per month (Search Console)", font=dict(size=13, color=NAVY)), height=280,
                          paper_bgcolor=WHITE, plot_bgcolor=WHITE, font=dict(family="Roboto", color=NAVY, size=11),
                          margin=dict(t=50, b=30, l=50, r=20), yaxis=dict(gridcolor="#E8ECF2", zeroline=False, rangemode="tozero"),
                          xaxis=dict(showgrid=False))
        st.plotly_chart(fig, width="stretch")
    elif dom_market and not demo_mode:
        st.caption(f"Search Console history for {dom_market} is not available (no access yet).")

    with st.expander("🧭 How to read this: what else moves organic results"):
        st.markdown(
            "- **Delay:** links take weeks to months to work; for commercial terms often 6–12 months. Young pages are never counted as a miss.\n"
            "- **Homepage and category links** raise the authority of the whole domain, so the pages *without* links also benefit. That is why "
            "the domain and authority views matter next to the page view.\n"
            "- **Other causes:** competition, technical issues, content, cannibalisation, internal links, page speed, indexability, "
            "Google updates, seasonality and promotions. Use the health check in *Links & health* to rule out the technical ones.\n"
            "- **Not proof:** a better development is a reason to keep investing, a weaker one is a reason to look closer, not to stop.")
    return headline
