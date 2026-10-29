"""Campaign scorecard: the three questions the client actually asks, on one line each."""
import streamlit as st

_CSS = """
<style>
.sc-wrap{display:flex;gap:.9rem;flex-wrap:wrap;margin:.2rem 0 .6rem}
.sc-card{flex:1;min-width:230px;background:#fff;border:1px solid #E8ECF2;border-top:4px solid var(--c);
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


def render_scorecard(roi_total: dict, growth: dict | None, ranking: dict | None, demo_mode: bool) -> None:
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

    # 2) Organic growth
    if growth:
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
        cards.append(_card("Are rankings getting better?", "Not loaded", "Open the Results tab and load the ranking trend (uses Ahrefs units).", GREY))

    st.markdown('<div class="section-title">🎯 Campaign scorecard — is link building paying off?</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sc-wrap">{"".join(cards)}</div>', unsafe_allow_html=True)
    if known:
        st.markdown(f'<div class="sc-sum">Read together: <b>{positive} of {known}</b> available signals point the right way. '
                    f'This is direction, not proof — links work with a delay and rankings and revenue also depend on content, '
                    f'technique and competition.{" <b>DEMO DATA.</b>" if demo_mode else ""}</div>', unsafe_allow_html=True)
