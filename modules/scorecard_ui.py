"""Campaign scorecard: the three questions the client actually asks, on one line each."""
import streamlit as st

_CSS = """
<style>
.sc-wrap{display:flex;gap:.9rem;flex-wrap:wrap;margin:.2rem 0 .6rem}
.sc-card{flex:1;min-width:200px;background:#fff;border:1px solid #E8ECF2;border-top:4px solid var(--c);
  border-radius:12px;padding:.9rem 1.1rem;box-shadow:0 2px 10px rgba(27,45,91,.06)}
.sc-q{font-size:.72rem;text-transform:uppercase;letter-spacing:.8px;color:#8B9BB4}
.sc-a{font-size:1.25rem;font-weight:700;color:#1B2D5B;margin:.25rem 0}
.sc-d{font-size:.82rem;color:#4A5875;line-height:1.4}
.sc-sum{background:#F0F4F8;border-radius:8px;padding:.6rem 1rem;color:#1B2D5B;font-size:.9rem}
</style>
"""
GREEN, AMBER, GREY = "#1E9E5A", "#E08A00", "#8B9BB4"


def _card(question: str, answer: str, detail: str, color: str) -> str:
    return (f'<div class="sc-card" style="--c:{color}"><div class="sc-q">{question}</div>'
            f'<div class="sc-a">{answer}</div><div class="sc-d">{detail}</div></div>')


def render_scorecard(roi_total: dict, growth: dict | None, ranking: dict | None, demo_mode: bool, evidence: dict | None = None, gsc: dict | None = None) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    cards, positive, known = [], 0, 0

    # 1) Payback
    adv = (roi_total or {}).get("advice", {}).get("key", "unknown")
    base = ((roi_total or {}).get("scenarios", {}).get("base", {}) or {}).get("roi")
    ind = " (indicative — traffic estimate)" if (roi_total or {}).get("mode") == "traffic" else ""
    if adv == "increase":
        cards.append(_card("Does it pay back?", "Covers its cost", f"Return on linked pages ≈ {base:.1f}x{ind}.", GREEN)); positive += 1; known += 1
    elif adv == "maintain":
        cards.append(_card("Does it pay back?", "Around break-even", f"Return ≈ {base:.1f}x{ind}. Direction unclear yet.", AMBER)); known += 1
    elif adv == "decrease":
        cards.append(_card("Does it pay back?", "Not yet visible", f"Return ≈ {base:.1f}x{ind} on the linked pages. "
                           "Links also lift the whole domain and act with a delay.", AMBER)); known += 1
    else:
        cards.append(_card("Does it pay back?", "Not enough data", "Needs GA4 revenue (or a traffic estimate) and spend.", GREY))

    # 2) Organic growth — year-over-year evidence first (seasonality-free), before/after growth as fallback
    ev_ = evidence or {}
    vd = ev_.get("verdict")
    if vd in ("accelerating", "stable", "slowing"):
        g_, d_, b_ = ev_["yoy_now_linked"], ev_["yoy_now_domain"], ev_.get("yoy_before_domain")
        txt = (f"Linked pages {g_:+.0%} year-over-year (change vs. before the campaign: {ev_['acceleration'] * 100:+.0f} pp); "
               f"whole domain {d_:+.0%}" + (f" (before: {b_:+.0%})." if b_ is not None else "."))
        label, col = {"accelerating": ("Growing faster than before", GREEN), "stable": ("No clear change yet", GREY),
                      "slowing": ("Not outgrowing the past yet", AMBER)}[vd]
        cards.append(_card("Do we see organic growth?", label, txt, col)); known += 1; positive += 1 if vd == "accelerating" else 0
    elif vd in ("too_early", "no_baseline"):
        cards.append(_card("Do we see organic growth?", "Too early to judge" if vd == "too_early" else "Not enough history",
                           "Links need months to work; most linked pages are young or had no traffic a year ago.", GREY))
    elif growth:
        out, g, dg = growth.get("Outperformance"), growth.get("Growth"), growth.get("Domain growth")
        txt = f"Linked pages {g:+.0%} vs. domain {dg:+.0%} (same months, around first link)." if dg is not None else f"Linked pages {g:+.0%}."
        if out is not None and out >= 0.10:
            cards.append(_card("Do we see organic growth?", "Ahead of the domain", txt, GREEN)); positive += 1
        elif out is not None and out <= -0.10:
            cards.append(_card("Do we see organic growth?", "Behind the domain", txt + " Check other causes.", AMBER))
        else:
            cards.append(_card("Do we see organic growth?", "In line with the domain", txt, GREY))
        known += 1
    else:
        cards.append(_card("Do we see organic growth?", "Waiting for GA4", "Needs monthly organic revenue per page (GA4).", GREY))

    # 3) Rankings
    st_ = (ranking or {}).get("status", "unknown")
    if st_ in ("improving", "stable", "declining"):
        r = ranking
        det = (f"Avg. position {r['pos_start']:.1f} → {r['pos_now']:.1f}; top-10 keywords {r['top10_start']} → {r['top10_now']}.")
        label = {"improving": "Improving", "stable": "Stable", "declining": "Declining"}[st_]
        cards.append(_card("Are rankings getting better?", label, det, {"improving": GREEN, "stable": GREY, "declining": AMBER}[st_]))
        known += 1
        positive += 1 if st_ == "improving" else 0
    else:
        cards.append(_card("Are rankings getting better?", "No data", "Needs the Ahrefs key and linked pages in the selected market.", GREY))

    # 4) Search Console: Google clicks of the whole site, year-over-year (same months a year earlier)
    g_ = gsc or {}
    if g_.get("yoy") is not None:
        y = g_["yoy"]
        label, col = (("Growing", GREEN) if y >= 0.05 else ("Declining", AMBER) if y <= -0.05 else ("Stable", GREY))
        pos = (f" Avg. position {g_['pos_prev']:.1f} → {g_['pos_now']:.1f}." if g_.get("pos_now") and g_.get("pos_prev") else "")
        cards.append(_card("Is Google sending more clicks?", label,
                           f"Clicks last 3 months {y:+.0%} vs. same months last year (whole site).{pos}", col))
        known += 1
        positive += 1 if y >= 0.05 else 0
    else:
        cards.append(_card("Is Google sending more clicks?", "No data", "Needs Search Console access for this market.", GREY))

    st.markdown('<div class="section-title">🎯 Campaign scorecard — is link building paying off?</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sc-wrap">{"".join(cards)}</div>', unsafe_allow_html=True)
    caveat = ""
    out_ = (growth or {}).get("Outperformance")
    if adv == "increase" and (vd == "slowing" or (not vd and out_ is not None and out_ <= -0.10)):
        caveat = (' <br><b>Note:</b> the payback figure credits 100% of the linked pages revenue to link building, while those '
                  'pages are growing slower than the domain. Treat the return as an <b>upper bound</b>, not as proof.')
    if known:
        st.markdown(f'<div class="sc-sum">Read together: <b>{positive} of {known}</b> available signals point the right way. '
                    f'This is direction, not proof — links work with a delay and rankings and revenue also depend on content, '
                    f'technique and competition.{caveat}{" <b>DEMO DATA.</b>" if demo_mode else ""}</div>', unsafe_allow_html=True)
