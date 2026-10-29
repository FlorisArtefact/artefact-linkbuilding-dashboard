from modules.health_check import evaluate_landing, evaluate_link, parse_page

HTML = '<html><head><meta name="robots" content="noindex,follow"><link rel="canonical" href="https://a.nl/x"></head>' \
       '<body><a href="https://www.client.nl/cat/a/" rel="sponsored nofollow">x</a></body></html>'


def test_parse_page():
    p = parse_page(HTML, "https://b.nl/")
    assert "noindex" in p["robots"] and p["canonical"] == "https://a.nl/x"


def test_landing_flags_issues():
    r = evaluate_landing(200, "https://b.nl/p", "https://b.nl/p", HTML)
    assert r["Noindex"] and r["Canonical elsewhere"] and "noindex" in r["Issues"]
    assert evaluate_landing(200, "https://b.nl/p", "https://b.nl/p", "<html></html>")["Issues"] == "OK"
    assert "HTTP 404" in evaluate_landing(404, "", "https://b.nl/p", "")["Issues"]


def test_link_present_and_rel():
    r = evaluate_link(200, HTML, "https://pub.nl/a", "https://client.nl/cat/a")
    assert r["Link present"] and r["Rel"] == "nofollow,sponsored"
    assert evaluate_link(200, HTML, "https://pub.nl/a", "https://client.nl/other")["Result"] == "link NOT found"
    assert evaluate_link(404, "", "https://pub.nl/a", "https://client.nl/x")["Result"].startswith("article HTTP")
