import pandas as pd
from modules import budget_advice as ba

TODAY = pd.Timestamp("2026-11-19")


def _links(rows):
    return pd.DataFrame(rows, columns=["Link to", "LL Date", "Price"])


def test_market_table_steps_and_conclusion():
    mt = ba.market_table([
        {"market": "NL", "investment": 1000, "roi_base": 3.0, "roi_low": 1.5, "key": "increase"},
        {"market": "FR", "investment": 1000, "roi_base": 0.5, "roi_low": 0.2, "key": "decrease"},
        {"market": "DE", "investment": 0, "roi_base": None, "roi_low": None, "key": "unknown"},
    ])
    assert list(mt["Market"]) == ["NL", "FR", "DE"]
    assert mt.set_index("Market").loc["NL", "Proposed budget"] == 1250
    assert mt.set_index("Market").loc["FR", "Proposed budget"] == 750
    text = " ".join(ba.market_conclusion(mt))
    assert "move it to NL" in text and "DE" in text


def test_page_actions():
    links = _links([
        ["https://shop.nl/a", "2026-10-15", 100],                       # recent -> wait
        ["https://shop.nl/b", "2025-01-01", 100],                       # accelerating, pos 8 -> more
        ["https://shop.nl/c", "2025-01-01", 100], ["https://shop.nl/c/", "2025-02-01", 100],
        ["https://shop.nl/c", "2025-03-01", 100],                       # 3 links, stable -> pause
        ["shop.nl/d", "2025-01-01", 100],                               # no revenue status, pos 6 -> more
    ])
    gsc = pd.DataFrame({"Page": ["https://www.shop.nl/b", "https://shop.nl/d/"], "Clicks": [10, 5],
                        "Impressions": [1000, 500], "Avg Position": [8.0, 6.0]})
    status = pd.DataFrame({"Landing Page": ["https://shop.nl/b", "https://shop.nl/c"], "Status": ["Accelerating", "Stable"]})
    pt = ba.page_table(links, gsc, status, today=TODAY).set_index("Page")
    act = pt["_action"].to_dict()
    assert act["https://shop.nl/a"] == "wait"
    assert act["https://shop.nl/b"] == "more"
    assert act["https://shop.nl/c"] == "pause" and pt.loc["https://shop.nl/c", "Links"] == 3
    assert act["shop.nl/d"] == "more"


def test_next_targets_excludes_linked_and_far_pages():
    gsc = pd.DataFrame({"Page": ["https://shop.nl/xa", "https://shop.nl/ya", "https://shop.nl/za", "https://shop.nl/xa#faq",
                                 "https://other.nl/q"],
                        "Clicks": [5, 1, 0, 1, 9], "Impressions": [5000, 100, 9000, 800, 9999],
                        "Avg Position": [7.0, 9.0, 45.0, 7.0, 6.0]})
    t = ba.next_targets(gsc, ["https://shop.nl/ya"], host="shop.nl")
    assert list(t["Page"]) == ["https://shop.nl/xa"]


def test_pipeline_value_ranks_reach_per_euro():
    opp = pd.DataFrame({"Domain": ["a.nl", "b.nl", "c.nl"], "DR": [30, 50, 40], "Price": [100, 1000, None],
                        "Organic Traffic ahrefs": [10000, 20000, 50000]})
    pv = ba.pipeline_value(opp)
    assert list(pv["Domain"]) == ["a.nl", "b.nl"]


def test_homepage_with_many_links_is_paused():
    links = _links([["https://shop.nl/", "2026-01-01", 100]] * 4)
    gsc = pd.DataFrame({"Page": ["https://shop.nl/"], "Clicks": [10], "Impressions": [1000], "Avg Position": [12.0]})
    pt = ba.page_table(links, gsc, today=TODAY)
    assert pt["_action"].iloc[0] == "pause"


def test_allocation_ranks_by_value_and_sums_to_one():
    pages = pd.DataFrame({"Page": ["https://shop.nl/a", "https://shop.nl/b"], "Links": [2, 1], "Position": [8.0, 5.0],
                          "Impressions (90d)": [10000, 10000], "Why": ["x", "y"], "_action": ["more", "pause"]})
    targets = pd.DataFrame({"Page": ["https://shop.nl/c"], "Position": [12.0], "Impressions (90d)": [20000]})
    vpv = {"shop.nl/a": 1.0, "shop.nl/c": 5.0, "_avg": 2.0}
    al = ba.allocation(pages, targets, vpv)
    assert list(al["Page"]) == ["https://shop.nl/c", "https://shop.nl/a"]        # paused page b is not a candidate
    assert abs(al["Share of next budget"].sum() - 1) < 1e-9
    al2 = ba.allocation(pages, targets, None, focus=["/a"])
    assert "Client focus" in al2.columns and al2.set_index("Page").loc["https://shop.nl/a", "Client focus"] == "yes"


def test_own_ctr_curve_and_realistic_target():
    import pandas as pd
    from modules import budget_advice as ba
    gsc = pd.DataFrame({"Page": ["https://x.nl/a", "https://x.nl/b", "https://x.nl/"],
                        "Clicks": [60, 30, 9000], "Impressions": [3000, 3000, 10000], "Avg Position": [3.2, 8.0, 1.0]})
    c = ba.own_ctr_curve(gsc)
    assert c[(3, 3)]["source"] == "own data" and abs(c[(3, 3)]["ctr"] - 0.02) < 1e-9
    assert c[(1, 1)]["source"] == "benchmark"          # homepage (brand) is left out of the measurement
    assert ba.target_position(9) == 3 and ba.target_position(14) == 7
    t = pd.DataFrame({"Page": ["https://x.nl/b"], "Position": [8.0], "Impressions (90d)": [10000], "Clicks (90d)": [100]})
    al = ba.allocation(None, t, curve=c)
    assert "10,000 impressions" in al.loc[0, "How calculated"] and al.loc[0, "Target position"] == 3
