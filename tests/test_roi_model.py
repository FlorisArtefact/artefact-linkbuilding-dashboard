"""Run with:  pip install pytest  &&  python -m pytest tests -q
(roi_model has no Streamlit dependency, so these run anywhere.)"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.roi_model import (  # noqa: E402
    budget_advice, compute_roi, linked_page_metrics, merged_assumptions, sensitivity_grid,
)

A = merged_assumptions(None)


def test_revenue_mode_math():
    # 90-day revenue 10k -> x(365/90) = 40.56k a year; base 20% = 8.11k; invest 4k -> ROI 2.03x
    r = compute_roi(4000, revenue_window=10000, window_days=90, assumptions=A)
    assert r["mode"] == "revenue"
    assert abs(r["scenarios"]["base"]["value"] - 10000 * 365 / 90 * 0.20) < 1e-6
    assert abs(r["scenarios"]["base"]["roi"] - 2.028) < 0.01
    assert r["scenarios"]["low"]["roi"] < r["scenarios"]["base"]["roi"] < r["scenarios"]["high"]["roi"]


def test_traffic_mode_used_when_no_revenue():
    r = compute_roi(1000, revenue_window=0, traffic_window=3000, window_days=90, assumptions=A)
    assert r["mode"] == "traffic"
    expected = 3000 * 365 / 90 * 0.20 * 0.018 * 45
    assert abs(r["scenarios"]["base"]["value"] - expected) < 1e-6


def test_no_data_gives_insufficient():
    r = compute_roi(5000, assumptions=A)
    assert r["mode"] is None and r["advice"]["key"] == "unknown"


def test_no_investment_no_division_by_zero():
    r = compute_roi(0, revenue_window=5000, assumptions=A)
    assert r["scenarios"]["base"]["roi"] is None
    assert r["advice"]["key"] == "unknown"


def test_advice_thresholds():
    def adv(inv, rev):
        return compute_roi(inv, revenue_window=rev, window_days=90, assumptions=A)["advice"]["key"]
    assert adv(1000, 20000) == "increase"      # base ~16x, low ~8x
    assert adv(10000, 5000) == "decrease"      # base ~0.4x
    assert adv(8000, 14000) == "maintain"      # base ~1.4x, low ~0.7x
    assert adv(4000, 14000) == "increase"      # base ~2.8x, low ~1.4x


def test_linked_page_metrics_matching():
    links = pd.DataFrame({"Link to": ["https://www.shop.nl/c/a/", "https://shop.nl/c/b"]})
    ga4 = pd.DataFrame({"path": ["/c/a", "/c/b/", "/c/other"], "Revenue": [100, 50, 999],
                        "Conversions": [2, 1, 9], "Sessions": [10, 5, 99]})
    gsc = pd.DataFrame({"Page": ["https://shop.nl/c/a", "https://shop.nl/c/zzz"], "Clicks": [30, 70]})
    m = linked_page_metrics(links, ga4, gsc)
    assert m["pages"] == 2 and m["revenue"] == 150 and m["sessions"] == 15 and m["clicks"] == 30


def test_sensitivity_grid_shape():
    shares, mults, z = sensitivity_grid(1000, 5000, 0, 90, A)
    assert len(z) == len(mults) and all(len(row) == len(shares) for row in z)
