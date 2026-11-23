import pandas as pd

from modules import campaign_eval as ce

M = lambda s: pd.Timestamp(s)


def _links():
    return pd.DataFrame({"LL Date": ["2026-07-08", "2026-07-20", "2026-08-20"],
                         "Link to": ["https://www.shop.nl/", "https://www.shop.nl/c/lam/", "https://www.shop.nl/c/lam/"],
                         "Price": [500, 600, 700]})


def test_domain_timeline_counts_links_and_spend():
    m = pd.DataFrame({"month": [M("2026-06-01"), M("2026-07-01"), M("2026-08-01")], "Clicks": [100, 200, 400],
                      "Impressions": [1000, 3000, 9000], "Position": [3, 10, 12]})
    dt = ce.domain_timeline(m, _links())
    assert dt["Links placed"].tolist() == [0, 2, 1]
    assert dt["Links total"].tolist() == [0, 2, 3]
    assert dt["Spend total"].tolist() == [0, 1100, 1800]
    h = ce.headline(dt, pd.DataFrame())
    assert h["base_month"] == M("2026-06-01") and h["clicks_then"] == 100 and h["clicks_now"] == 400 and h["links"] == 3


def test_query_timeline_splits_brand():
    q = pd.DataFrame({"month": [M("2026-07-01")] * 3, "Key": ["shop vloer", "laminaat", "pvc"],
                      "Clicks": [10, 5, 1], "Impressions": [100, 200, 300], "Position": [1.0, 8.0, 30.0]})
    qt = ce.query_timeline(q, ["shop"])
    r = qt.iloc[0]
    assert r["Terms top 10"] == 2 and r["Non-brand terms top 10"] == 1 and r["Brand clicks"] == 10 and not r["Capped"]


def test_focus_pages_main_term_and_verdict():
    pq = pd.DataFrame({"month": [M("2026-07-01"), M("2026-07-01"), M("2026-10-01"), M("2026-10-01")],
                       "Page": ["https://www.shop.nl/c/lam/"] * 4, "Query": ["laminaat", "shop laminaat", "laminaat", "shop laminaat"],
                       "Clicks": [1, 5, 9, 6], "Impressions": [500, 50, 900, 60], "Position": [36.0, 8.0, 18.0, 4.0]})
    fp = ce.focus_pages(pq, _links(), ["shop"])
    r = fp[fp["Page"].str.contains("lam")].iloc[0]
    assert r["Links"] == 2 and r["Main search term"] == "laminaat"
    assert r["Position then"] == 36.0 and r["Position now"] == 18.0 and r["Verdict"] == "Rising"
    th = ce.term_history(pq, fp)
    assert len(th) == 2
    early = pd.concat([pq.assign(month=M("2026-05-01"), Position=5.0).head(1), pq])   # before the first link: ignored
    assert ce.focus_pages(early, _links(), ["shop"]).query("Links == 2").iloc[0]["Position then"] == 36.0


def test_two_url_spellings_one_page():
    pq = pd.DataFrame({"month": [M("2026-07-01")] * 2 + [M("2026-10-01")] * 2,
                       "Page": ["https://www.shop.nl/c/lam/", "https://shop.nl/c/lam"] * 2, "Query": ["laminaat"] * 4,
                       "Clicks": [1, 1, 2, 2], "Impressions": [100, 100, 300, 100], "Position": [30.0, 40.0, 10.0, 30.0]})
    r = ce.focus_pages(pq, _links(), ["shop"]).query("Links == 2").iloc[0]
    assert r["Position then"] == 35.0 and r["Position now"] == 15.0
