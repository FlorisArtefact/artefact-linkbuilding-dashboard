import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.ranking_model import aggregate, per_url_table, trend_status  # noqa: E402


def _hist(pos0, pos1, t0, t1):
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-04-01", "2026-10-01"]), "avg_position": [pos0, pos1],
        "keywords": [10, 12], "top10": [1, 3], "est_traffic": [t0, t1]})


def test_improving_when_position_and_traffic_up():
    agg = aggregate({"/a": _hist(25, 15, 100, 200), "/b": _hist(30, 22, 50, 80)})
    s = trend_status(agg)
    assert s["status"] == "improving" and s["pos_change"] > 5 and s["traffic_change"] > 0.5
    assert s["top10_start"] == 2 and s["top10_now"] == 6


def test_conflicting_signals_are_mixed_not_declining():
    # position and traffic worse, but top-10 keywords up in the fixture -> mixed
    assert trend_status(aggregate({"/a": _hist(10, 20, 200, 100)}))["status"] == "mixed"
    # position better but traffic estimate down -> mixed
    assert trend_status(aggregate({"/a": _hist(20, 10, 200, 100)}))["status"] == "mixed"


def test_declining_and_stable():
    worse = _hist(10, 20, 200, 100)
    worse["top10"] = [3, 1]
    assert trend_status(aggregate({"/a": worse}))["status"] == "declining"
    flat = _hist(10, 10.3, 100, 101)
    flat["top10"] = [3, 3]
    assert trend_status(aggregate({"/a": flat}))["status"] == "stable"


def test_no_data_is_unknown():
    assert trend_status(aggregate({}))["status"] == "unknown"
    assert trend_status(aggregate({"/a": pd.DataFrame()}))["status"] == "unknown"


def _summary(k0, k1, t3a, t3b, t0, t1):
    return pd.DataFrame({"date": pd.to_datetime(["2026-05-01", "2026-11-02"]), "avg_position": [float("nan")] * 2,
                         "keywords": [k0, k1], "top3": [t3a, t3b], "est_traffic": [t0, t1]})


def test_ahrefs_summary_without_position_uses_gsc_for_position():
    agg = aggregate({"/a": _summary(100, 120, 10, 14, 500, 800)})
    assert "top10" not in agg.columns and agg["avg_position"].isna().all()
    s = trend_status(agg)                                   # Ahrefs alone: traffic and top-3 up -> improving, no position
    assert s["status"] == "improving" and s["pos_change"] is None and s["top3_now"] == 14
    s = trend_status(agg, {"pos_start": 20.0, "pos_now": 7.5, "top10_start": 100, "top10_now": 300})
    assert s["status"] == "improving" and abs(s["pos_change"] - 12.5) < 1e-9 and s["top10_now"] == 300


def test_gsc_only_status_when_ahrefs_not_loaded():
    s = trend_status(pd.DataFrame(), {"pos_start": 9.0, "pos_now": 12.0, "top10_start": 50, "top10_now": 40})
    assert s["status"] == "declining" and s["traffic_start"] is None
    assert trend_status(pd.DataFrame(), None)["status"] == "unknown"


def test_gsc_position_better_but_ahrefs_traffic_down_is_mixed():
    agg = aggregate({"/a": _summary(100, 90, 10, 6, 900, 500)})
    s = trend_status(agg, {"pos_start": 20.0, "pos_now": 10.0, "top10_start": 100, "top10_now": 100})
    assert s["status"] == "mixed"


def test_per_url_table_sorted_by_traffic_change():
    t = per_url_table({"/a": _summary(10, 12, 1, 2, 100, 300), "/b": _summary(10, 9, 3, 2, 50, 40)})
    assert list(t["Landing Page"]) == ["/a", "/b"] and t.iloc[0]["Change"] == 200 and t.iloc[0]["Top-3 now"] == 2
