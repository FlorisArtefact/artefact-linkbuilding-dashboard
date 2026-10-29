import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.growth_model import category_of, growth_table, summarize  # noqa: E402

TODAY = "2026-10-15"   # last full month = 2026-09


def _monthly(page_rev, dom_rev):
    rows = []
    for m in pd.date_range("2026-01-01", "2026-09-01", freq="MS"):
        rows.append({"month": m, "path": "/c/a", "Revenue": page_rev(m)})
        rows.append({"month": m, "path": "/c/other", "Revenue": dom_rev(m)})
    return pd.DataFrame(rows)


def test_growth_and_outperformance():
    # page: 100/mo before the link (May), 200/mo after; other page flat 100 -> domain 200 -> 300 (+50%)
    m = _monthly(lambda d: 100 if d.month <= 5 else 200, lambda d: 100)
    links = pd.DataFrame({"Link to": ["https://x.nl/c/a/"], "LL Date": [pd.Timestamp("2026-05-10")]})
    t = growth_table(m, links, window=3, today=TODAY)
    r = t.iloc[0]
    assert r["Rev/mo before"] == 100 and r["Rev/mo after"] == 200
    assert abs(r["Growth"] - 1.0) < 1e-9
    assert abs(r["Domain growth"] - 0.5) < 1e-9          # (300/200 - 1)
    assert abs(r["Outperformance"] - 0.5) < 1e-9


def test_incomplete_current_month_excluded_and_partial_after_window():
    m = _monthly(lambda d: 100 if d.month <= 7 else 150, lambda d: 100)
    links = pd.DataFrame({"Link to": ["https://x.nl/c/a"], "LL Date": [pd.Timestamp("2026-07-02")]})
    t = growth_table(m, links, window=3, today=TODAY)
    assert t.iloc[0]["Months after"] == 2            # Aug, Sep only (Oct not complete)


def test_no_history_before_gives_none_growth():
    m = _monthly(lambda d: 100, lambda d: 100)
    links = pd.DataFrame({"Link to": ["https://x.nl/c/a"], "LL Date": [pd.Timestamp("2026-01-05")]})
    t = growth_table(m, links, window=3, today=TODAY)
    assert t.iloc[0]["Growth"] is None or pd.isna(t.iloc[0]["Growth"])
    assert summarize(t).empty


def test_signals_are_coarse_and_cautious():
    from modules.growth_model import signal_for
    assert signal_for(0.40, 0.10, 3) == "Ahead of domain"
    assert signal_for(0.12, 0.10, 3) == "In line with domain"
    assert signal_for(-0.20, 0.05, 3) == "Behind domain"
    assert signal_for(0.9, 0.1, 1) == "Too early / no baseline"     # only 1 month after the link
    assert signal_for(None, 0.1, 5) == "Too early / no baseline"


def test_category_of():
    assert category_of("https://x.nl/collections/apple-watch-se-bandjes") == "Apple Watch"
    assert category_of("https://x.nl/") == "Home"
    assert category_of("https://x.nl/collections/iets-anders") == "Other"
