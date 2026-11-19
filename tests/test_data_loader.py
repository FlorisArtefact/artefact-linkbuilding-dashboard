import pandas as pd

from modules.data_loader import get_landing_page_summary, normalize_link_targets, normalize_url


def test_homepage_spellings_are_one_page():
    variants = ["smartwatchbanden.nl", "https://smartwatchbanden.nl", "https://smartwatchbanden.nl/", " HTTPS://SmartwatchBanden.nl/ "]
    assert {normalize_url(v) for v in variants} == {"https://smartwatchbanden.nl/"}


def test_paths_keep_their_case_and_lose_trailing_slash():
    assert normalize_url("https://smartwatchbanden.nl/collections/Apple-Watch/") == "https://smartwatchbanden.nl/collections/Apple-Watch"


def test_bare_path_gets_market_domain_and_empty_stays_empty():
    assert normalize_url("/collections/x", "smartwatchbanden.nl") == "https://smartwatchbanden.nl/collections/x"
    assert normalize_url("") == "" and normalize_url(None) == "" and normalize_url(float("nan")) == ""


def test_summary_groups_homepage_once():
    df = pd.DataFrame({
        "Link to": ["smartwatchbanden.nl", "https://smartwatchbanden.nl/", "https://smartwatchbanden.nl/collections/a"],
        "Live Link": ["a", "b", "c"], "Price": [100, 200, 300], "DA": [40, 50, 60],
        "Link Type": ["Dofollow"] * 3, "Status code": [200] * 3,
    })
    out = get_landing_page_summary(normalize_link_targets(df))
    assert len(out) == 2
    home = out[out["Landing Page"] == "https://smartwatchbanden.nl/"].iloc[0]
    assert home["# Links"] == 2 and home["Total Cost (€)"] == 300


def test_blank_sheet_cells_are_not_approved():
    from modules.data_loader import is_approved
    col = pd.Series(["Ja", "", None, "  ", "nee", "Yes", float("nan"), "x"])
    assert is_approved(col).tolist() == [True, False, False, False, False, True, False, True]
