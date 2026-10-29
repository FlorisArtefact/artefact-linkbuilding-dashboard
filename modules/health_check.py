"""Free, tool-less health checks that explain *why* a linked page may not move:
 - landing pages: reachable, indexable (noindex?), canonical pointing elsewhere, slow response
 - placed links: article still live, our link still present, rel=nofollow/sponsored/ugc
Pure parsing is separated from the HTTP calls so it can be tested offline."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; LinkHealthCheck/1.0)"}
TIMEOUT = 12


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.robots, self.canonical, self.anchors = "", "", []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta" and a.get("name", "").lower() in ("robots", "googlebot"):
            self.robots += " " + a.get("content", "").lower()
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href", "")
        elif tag == "a" and a.get("href"):
            self.anchors.append((a["href"], a.get("rel", "").lower()))


def _norm(u: str) -> str:
    p = urlparse(str(u).strip().lower())
    return f"{p.netloc.removeprefix('www.')}{p.path.rstrip('/')}"


def parse_page(html: str, base_url: str = "") -> dict:
    p = _Parser()
    try:
        p.feed(html or "")
    except Exception:
        pass
    return {"robots": p.robots.strip(), "canonical": urljoin(base_url, p.canonical) if p.canonical else "",
            "anchors": [(urljoin(base_url, h), r) for h, r in p.anchors]}


def evaluate_landing(status: int, final_url: str, requested_url: str, html: str, x_robots: str = "",
                     seconds: float = 0.0) -> dict:
    info = parse_page(html, final_url or requested_url)
    noindex = "noindex" in info["robots"] or "noindex" in x_robots.lower()
    canon_other = bool(info["canonical"]) and _norm(info["canonical"]) != _norm(final_url or requested_url)
    issues = []
    if status >= 400 or status == 0:
        issues.append(f"HTTP {status or 'error'}")
    if noindex:
        issues.append("noindex")
    if canon_other:
        issues.append("canonical points elsewhere")
    if _norm(final_url or requested_url) != _norm(requested_url) and status < 400:
        issues.append("redirects")
    if seconds > 6:
        issues.append(f"slow ({seconds:.1f}s)")
    return {"Status": status, "Noindex": noindex, "Canonical elsewhere": canon_other,
            "Seconds": round(seconds, 2), "Issues": ", ".join(issues) or "OK"}


def evaluate_link(status: int, html: str, live_url: str, target_url: str) -> dict:
    info = parse_page(html, live_url)
    tgt = _norm(target_url)
    found = [(h, r) for h, r in info["anchors"] if tgt and _norm(h) == tgt]
    present = bool(found)
    rel = ",".join(sorted({x for _, r in found for x in r.split() if x in ("nofollow", "sponsored", "ugc")}))
    if status >= 400 or status == 0:
        result = f"article HTTP {status or 'error'}"
    elif not present:
        result = "link NOT found"
    elif rel:
        result = f"present ({rel})"
    else:
        result = "OK"
    return {"Status": status, "Link present": present, "Rel": rel, "Result": result}


def _get(url: str):
    t = time.time()
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code, r.url, r.text[:400_000], r.headers.get("X-Robots-Tag", ""), time.time() - t
    except Exception:
        return 0, url, "", "", time.time() - t


def check_landing(url: str) -> dict:
    s, final, html, xr, secs = _get(url)
    return {"Landing Page": url, **evaluate_landing(s, final, url, html, xr, secs)}


def check_link(live_url: str, target_url: str) -> dict:
    s, _final, html, _xr, _secs = _get(live_url)
    return {"Live Link": live_url, "Link to": target_url, **evaluate_link(s, html, live_url, target_url)}


def run_landing_checks(urls: list[str], workers: int = 8) -> list[dict]:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(check_landing, urls))


def run_link_checks(pairs: list[tuple[str, str]], workers: int = 8) -> list[dict]:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda p: check_link(*p), pairs))


def demo_landing(urls: list[str]) -> list[dict]:
    out = []
    for i, u in enumerate(urls):
        issues = {3: "canonical points elsewhere", 7: "slow (4.2s)"}.get(i % 9, "OK")
        out.append({"Landing Page": u, "Status": 200, "Noindex": False, "Canonical elsewhere": "canonical" in issues,
                    "Seconds": 4.2 if "slow" in issues else 0.8, "Issues": issues})
    return out


def demo_links(pairs: list[tuple[str, str]]) -> list[dict]:
    res = ["OK", "OK", "OK", "present (nofollow)", "link NOT found", "OK", "article HTTP 404"]
    return [{"Live Link": a, "Link to": b, "Status": 404 if "404" in res[i % 7] else 200,
             "Link present": "NOT" not in res[i % 7] and "404" not in res[i % 7],
             "Rel": "nofollow" if "nofollow" in res[i % 7] else "", "Result": res[i % 7]}
            for i, (a, b) in enumerate(pairs)]
