"""
Deterministic SYNTHETIC data so the dashboard can be shown / developed without any
credentials (Google, Ahrefs) — and so a colleague can try the template in 10 seconds.

Everything here is fake. The app labels demo mode clearly; never show demo numbers to a
client as real results.
"""
from __future__ import annotations

import random
from datetime import date, datetime

import pandas as pd

_DEMO = {
    "NL": {"host": "https://demo-shop.nl", "pages": ["/collections/apple-watch-bandjes", "/collections/siliconen-bandjes",
           "/collections/leren-bandjes", "/collections/sport-bandjes", "/collections/milanese-bandjes"],
           "domains": ["tech-nieuws.nl", "gadgetgids.nl", "lifestyle-blog.nl", "sportmagazine.nl", "wearables.nl", "dagelijksetips.nl"],
           "anchors": ["apple watch bandje", "siliconen bandjes", "horlogebandje kopen", "sport bandje", "demo-shop"]},
    "EN": {"host": "https://demo-straps.co.uk", "pages": ["/collections/apple-watch-straps", "/collections/silicone-straps",
           "/collections/leather-straps", "/collections/sport-straps"],
           "domains": ["gadget-review.co.uk", "wearable-world.com", "the-tech-daily.co.uk", "fitness-hub.co.uk"],
           "anchors": ["apple watch strap", "silicone watch bands", "best watch straps", "demo-straps"]},
    "DE": {"host": "https://demo-armbaender.de", "pages": ["/collections/apple-watch-armbaender", "/collections/silikon-armbaender",
           "/collections/leder-armbaender"],
           "domains": ["technikblog.de", "smartwatch-ratgeber.de", "fitness-welt.de"],
           "anchors": ["apple watch armband", "silikon armband", "smartwatch armbänder", "demo-armbaender"]},
}
_GENERIC = {"host": "https://demo-client.com", "pages": ["/category/a", "/category/b", "/category/c"],
            "domains": ["blog-one.com", "magazine-two.com", "news-three.com"], "anchors": ["brand", "product", "buy now"]}
_COUNT = {"NL": 22, "EN": 14, "DE": 9}


def _cfg(lang: str) -> dict:
    return _DEMO.get(lang, _GENERIC)


def demo_live_links(lang: str, year: int) -> pd.DataFrame:
    rng = random.Random(f"links-{lang}-{year}")
    c = _cfg(lang)
    today = date.today()
    last_month = today.month if year == today.year else 12
    rows = []
    for i in range(_COUNT.get(lang, 8)):
        month = rng.randint(1, max(last_month, 1))
        day = rng.randint(1, 27)
        d = datetime(year, month, day)
        da = int(min(80, max(18, rng.gauss(44, 14))))
        rows.append({
            "Q": (month - 1) // 3 + 1, "Invoiced Month": d.strftime("%B"), "Year": year, "LL Date": d,
            "Live Link": f"https://{rng.choice(c['domains'])}/artikel-{i + 1}",
            "Status code": 200 if rng.random() > 0.07 else rng.choice([403, 404]),
            "DA": da, "Backlink/Brand Mention": "Backlink",
            "Link Type": "Dofollow" if rng.random() > 0.05 else "Nofollow",
            "Domain": rng.choice(c["domains"]), "Link to": c["host"] + rng.choice(c["pages"]),
            "_mention": rng.random() < 0.15,
            "Anchor text": rng.choice(c["anchors"]),
            "Price": float(round(120 + da * 4.2 + rng.randint(-40, 60), -1)),
            "Target campaign": "Paid linkbuilding" if rng.random() > 0.2 else "Digital PR",
            "Language": lang,
        })
    for r in rows:                      # some placements are brand mentions (citation without link)
        if r.pop("_mention"):
            r["Backlink/Brand Mention"] = "Brand Mention"
            r["Link to"], r["Link Type"], r["Anchor text"] = "", "n/a", ""
    return pd.DataFrame(rows)


def demo_opportunities(lang: str) -> pd.DataFrame:
    rng = random.Random(f"opp-{lang}")
    c = _cfg(lang)
    rows = []
    for i in range(8):
        rows.append({
            "Domain": f"kans-{i + 1}-{rng.choice(c['domains'])}", "DR": rng.randint(25, 72),
            "Topic": rng.choice(["Tech", "Lifestyle", "Sport", "Gadgets"]), "Price": float(rng.randrange(150, 520, 10)),
            "Proposed month": rng.choice(["Nov", "Dec", "Jan"]), "Approved?": "Yes" if rng.random() > 0.55 else None,
            "Link to": c["host"] + rng.choice(c["pages"]), "Anchor": rng.choice(c["anchors"]), "Language": lang,
        })
    return pd.DataFrame(rows)


def demo_ga4(lang: str) -> pd.DataFrame:
    """Organic revenue per landing page path, 90 days (same schema as ga4_client.get_revenue_by_page)."""
    rng = random.Random(f"ga4-{lang}")
    scale = {"NL": 1.0, "EN": 0.8, "DE": 0.6}.get(lang, 0.7)
    rows = []
    for p in _cfg(lang)["pages"]:
        sessions = rng.randint(900, 3200) * scale
        conv = sessions * rng.uniform(0.012, 0.03)
        rows.append({"path": p, "Revenue": round(conv * rng.uniform(42, 58), 2),
                     "Conversions": round(conv, 1), "Sessions": round(sessions)})
    return pd.DataFrame(rows)


def demo_monthly(lang: str, links: pd.DataFrame, months: int = 14) -> pd.DataFrame:
    """Synthetic monthly organic revenue per page: seasonal domain trend + a ramp-up after each page's
    first link (so the growth view has something to show). Same schema as get_monthly_revenue_by_page."""
    rng = random.Random(f"monthly-{lang}")
    c = _cfg(lang)
    now = pd.Timestamp.today().normalize().replace(day=1)
    first_link = {}
    if links is not None and not links.empty:
        for url, d in links.dropna(subset=["LL Date"]).groupby("Link to")["LL Date"].min().items():
            first_link[url.replace(c["host"], "")] = pd.Timestamp(d).to_period("M").to_timestamp()
    rows = []
    for p in c["pages"]:
        base = rng.uniform(500, 1800) * {"NL": 1.0, "EN": 0.8, "DE": 0.6}.get(lang, 0.7)
        fl = first_link.get(p)
        for k in range(months):
            m = now - pd.DateOffset(months=months - k)
            season = 1 + 0.25 * (1 if m.month in (11, 12) else 0) + 0.02 * k
            ramp = 1.0
            if fl is not None and m > fl:
                ramp = 1 + min(0.45, 0.15 * ((m.year - fl.year) * 12 + m.month - fl.month))
            rev = base * season * ramp * rng.uniform(0.9, 1.1)
            rows.append({"month": m, "path": p, "Revenue": round(rev, 2), "Sessions": round(rev / 1.6)})
    return pd.DataFrame(rows)


def demo_ranking_history(urls: list, months: int = 6) -> dict:
    """Synthetic snapshot history per URL (positions improve on most pages, a few lag)."""
    out = {}
    now = pd.Timestamp.today().normalize()
    for u in urls:
        rng = random.Random(f"rk-{u}")
        start = rng.uniform(16, 34)
        gain = rng.uniform(-3, 12)           # a minority drift the wrong way
        rows = []
        for i in range(months, -1, -1):
            prog = (months - i) / max(months, 1)
            pos = max(1.5, start - gain * prog + rng.uniform(-1, 1))
            kw = int(40 + 25 * prog + rng.uniform(-5, 5))
            rows.append({"date": now - pd.Timedelta(days=30 * i), "avg_position": round(pos, 1), "keywords": kw,
                         "top10": int(kw * max(0.02, (24 - pos) / 80)), "est_traffic": int(kw * rng.uniform(2, 5) * (1 + prog))})
        out[u] = pd.DataFrame(rows)
    return out


def demo_referral(lang: str, links: pd.DataFrame) -> pd.DataFrame:
    """Synthetic referral sessions from some of the placed links' articles (same schema as get_referral_traffic)."""
    rng = random.Random(f"ref-{lang}")
    rows = []
    if links is not None and not links.empty:
        for _, r in links.iterrows():
            if rng.random() < 0.7 and str(r.get("Link to", "")).strip():
                s = rng.randint(3, 140)
                rows.append({"referrer": r["Live Link"], "source": str(r["Domain"]), "Sessions": float(s),
                             "Revenue": round(s * rng.uniform(0, 1.6), 2), "Conversions": float(round(s * rng.uniform(0, 0.03), 1))})
    for src in ("google-news.example", "reddit.example"):      # unrelated referrers, to show the filtering
        rows.append({"referrer": f"https://{src}/x", "source": src, "Sessions": 55.0, "Revenue": 40.0, "Conversions": 1.0})
    return pd.DataFrame(rows)


def demo_gsc(lang: str) -> pd.DataFrame:
    rng = random.Random(f"gsc-{lang}")
    c = _cfg(lang)
    rows = [{"Page": c["host"] + p, "Clicks": rng.randint(400, 2600), "Impressions": rng.randint(15000, 90000),
             "CTR": round(rng.uniform(0.015, 0.05), 4), "Avg Position": round(rng.uniform(4.5, 22), 1)}
            for p in c["pages"]]
    return pd.DataFrame(rows)


def demo_ahrefs_for_page(url: str) -> dict:
    rng = random.Random(f"ah-{url}")
    return {"avg_position": round(rng.uniform(4, 25), 1), "est_traffic": rng.randint(120, 2600), "keywords": rng.randint(15, 220)}


def demo_position_history(url: str, months: int, events: pd.DataFrame | None = None) -> pd.DataFrame:
    """Monthly avg-position series that improves over time, so the impact chart looks meaningful."""
    rng = random.Random(f"hist-{url}")
    now = pd.Timestamp.today().normalize().replace(day=1)
    start_pos = rng.uniform(22, 34)
    rows = []
    for k in range(months):
        d = now - pd.DateOffset(months=months - 1 - k)
        progress = k / max(months - 1, 1)
        rows.append({"date": d, "avg_position": round(start_pos - progress * rng.uniform(8, 16) + rng.uniform(-1.5, 1.5), 1)})
    return pd.DataFrame(rows)
