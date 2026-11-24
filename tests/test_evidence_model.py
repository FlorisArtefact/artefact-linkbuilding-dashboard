import pandas as pd

from modules import evidence_model as ev
from modules.growth_model import monthly_pivot

TODAY = "2026-11-10"


def _monthly(linked_boost: float):
    rows = []
    for m in pd.date_range("2024-11-01", "2026-10-01", freq="MS"):
        flat = 1000.0
        # linked page: flat for a year, then (after Apr-2026) boosted
        boost = linked_boost if m >= pd.Timestamp("2026-04-01") else 1.0
        rows.append({"month": m, "path": "/a", "Revenue": flat * boost, "Sessions": 10})
        rows.append({"month": m, "path": "/b", "Revenue": flat, "Sessions": 10})
    return pd.DataFrame(rows)


def _links():
    return pd.DataFrame({"Link to": ["https://x.nl/a"], "LL Date": [pd.Timestamp("2026-04-15")]})


def test_accelerating_when_linked_page_outgrows_control():
    pv = monthly_pivot(_monthly(1.5), TODAY)
    s = ev.summary(pv, _links(), TODAY)
    g = s["groups"]
    assert s["verdict"] == "accelerating"
    assert g["Pages with links"]["acceleration"] > 0.3
    assert abs(g["Pages without links"]["acceleration"]) < 0.01
    assert s["above_control_value"] > 0


def test_stable_when_nothing_changes():
    s = ev.summary(monthly_pivot(_monthly(1.0), TODAY), _links(), TODAY)
    assert s["verdict"] == "stable"


def test_too_early_is_not_a_failure():
    pv = monthly_pivot(_monthly(1.0), TODAY)
    late = pd.DataFrame({"Link to": ["https://x.nl/a"], "LL Date": [pd.Timestamp("2026-10-05")]})
    assert ev.summary(pv, late, TODAY)["verdict"] == "too_early"
    assert ev.page_table(pv, late).iloc[0]["Status"] == "Too early"


def test_page_types_and_cohorts():
    assert ev.page_type("https://x.nl/") == "Homepage"
    assert ev.page_type("/blogs/blog/foo") == "Content / blog"
    assert ev.page_type("/collections/apple") == "Commercial page"
    pt = ev.page_table(monthly_pivot(_monthly(1.5), TODAY), _links())
    c = ev.cohort_table(pt)
    assert c.iloc[0]["Accelerating"] == 1


def test_yoy_curve_has_no_values_without_history():
    s = pd.Series([1.0] * 10, index=pd.date_range("2026-01-01", periods=10, freq="MS"))
    assert ev.yoy_curve(s).empty



def test_group_profile_counts_pages_and_types():
    import pandas as pd
    from modules import evidence_model as ev
    pages = pd.DataFrame({"key": ["/NL", "/NL/laminaat", "/NL/blog/tips", "/NL/pvc", "/NL/old"],
                          "type": ["Homepage", "Commercial page", "Content / blog", "Commercial page", "Commercial page"],
                          "Revenue": [100.0, 50.0, 5.0, 20.0, 0.0]})
    links = pd.DataFrame({"Link to": ["https://x/NL/laminaat/"], "LL Date": ["2025-06-01"]})
    pr = ev.group_profile(pages, links)
    assert pr["Pages with links"]["pages"] == 1
    assert pr["Pages without links"]["pages"] == 3          # /old has no revenue and is left out
    assert pr["Pages without links"]["types"]["Content / blog"] == 1
