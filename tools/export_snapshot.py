"""Freeze the dashboard into a static site (one HTML file + plotly.js) for sharing behind an access wall.

The dashboard runs headless (Streamlit AppTest) in client view, once per market, and every element it renders
(tiles, text, tables, charts, tabs, expanders) is written to HTML. No server, no API calls, no Ahrefs credits:
only results already stored are used. Works for any client config.

    python tools/export_snapshot.py --config clients/<client>.json --out site/<client>
    python tools/export_snapshot.py --config config.example.json --out site/demo      # demo data

The result is a snapshot: filters other than the market switch are fixed at their defaults.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _md(text: str) -> str:
    import markdown
    return markdown.markdown(text or "", extensions=["tables", "sane_lists", "md_in_html"])


class Renderer:
    def __init__(self):
        self.n = 0                  # unique ids for tabs and plots
        self.skipped: dict[str, int] = {}

    def uid(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n}"

    # ---- leaf elements -------------------------------------------------------------------------------------
    def metric(self, el) -> str:
        label = getattr(el, "label", "") or getattr(el.proto, "label", "")
        delta = getattr(el.proto, "delta", "") or ""
        d = f'<div class="m-delta">{html.escape(delta)}</div>' if delta else ""
        return (f'<div class="metric"><div class="m-label">{html.escape(str(label))}</div>'
                f'<div class="m-value">{html.escape(str(el.value))}</div>{d}</div>')

    def dataframe(self, el) -> str:
        df = el.value
        try:
            df = df.head(300).copy()
            for c in df.columns:                      # None in text columns would print as "None"
                if df[c].dtype == object:
                    df[c] = df[c].where(df[c].notna(), "")
            return '<div class="tbl">' + df.to_html(index=False, border=0, na_rep="", float_format=lambda v: f"{v:,.2f}".rstrip("0").rstrip("."),
                                                   classes="df", escape=True) + "</div>"
        except Exception:
            return ""

    def plot(self, el) -> str:
        spec = getattr(el.proto, "spec", "") or ""
        if not spec:
            return ""
        pid = self.uid("p")
        safe = spec.replace("</", "<\\/")
        return (f'<div class="plot" id="{pid}" data-spec="{pid}s"></div>'
                f'<script type="application/json" id="{pid}s">{safe}</script>')

    # ---- containers ----------------------------------------------------------------------------------------
    def children(self, node) -> str:
        return "".join(self.element(ch) for ch in getattr(node, "children", {}).values())

    def element(self, el) -> str:
        t = getattr(el, "type", "")
        if t == "markdown":
            return f'<div class="md">{_md(el.value)}</div>'
        if t == "caption":
            return f'<div class="cap">{_md(el.value)}</div>'
        if t in ("info", "warning", "error", "success"):
            return f'<div class="box {t}">{_md(el.value)}</div>'
        if t == "metric":
            return self.metric(el)
        if t == "dataframe":
            return self.dataframe(el)
        if t == "plotly_chart":
            return self.plot(el)
        if t == "divider":
            return "<hr>"
        if t == "expander":
            return f'<details><summary>{html.escape(el.label)}</summary>{self.children(el)}</details>'
        if t == "column":
            return f'<div class="col">{self.children(el)}</div>'
        if t == "tab_container":
            tabs = [c for c in el.children.values() if getattr(c, "type", "") == "tab"]
            gid = self.uid("g")
            bar = "".join(f'<button class="tabbtn{" on" if i == 0 else ""}" data-g="{gid}" data-i="{i}">{html.escape(tb.label)}</button>'
                          for i, tb in enumerate(tabs))
            body = "".join(f'<div class="tabpane{" on" if i == 0 else ""}" data-g="{gid}" data-i="{i}">{self.children(tb)}</div>'
                           for i, tb in enumerate(tabs))
            return f'<div class="tabs"><div class="tabbar">{bar}</div>{body}</div>'
        if t in ("flex_container", "container", "tab", "block", "vertical_block", "horizontal_block"):
            kids = list(getattr(el, "children", {}).values())
            row = bool(kids) and all(getattr(k, "type", "") == "column" for k in kids)
            return f'<div class="{"row" if row else "stack"}">{self.children(el)}</div>'
        if t in ("empty", "button", "download_button", "selectbox", "radio", "slider", "text_input", "toggle", "file_uploader",
                 "number_input", "multiselect", "checkbox", "form_submit_button"):
            return ""
        self.skipped[t] = self.skipped.get(t, 0) + 1
        return ""


CSS = """
:root{--navy:#1B2D5B;--mid:#4A5875;--line:#E8ECF2;--bg:#F7F8FC}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#1B2D5B;font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:18px 20px 60px}
.snap{background:#fff;border:1px solid var(--line);border-radius:8px;padding:.5rem .9rem;font-size:.82rem;color:var(--mid);margin-bottom:12px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.mk{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.mk button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:.35rem .9rem;cursor:pointer;font:inherit;color:var(--navy)}
.mk button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
section.market{display:none}section.market.on{display:block}
.row{display:flex;gap:14px;flex-wrap:wrap;margin:8px 0}.col{flex:1;min-width:220px}.stack>*{margin-bottom:10px}
.metric{background:#fff;border:1px solid var(--line);border-radius:12px;padding:.7rem 1rem;box-shadow:0 2px 8px rgba(27,45,91,.05)}
.m-label{font-size:.75rem;text-transform:uppercase;letter-spacing:.6px;color:#8B9BB4}.m-value{font-size:1.7rem;font-weight:700}.m-delta{font-size:.8rem;color:var(--mid)}
.cap{font-size:.82rem;color:var(--mid)}.md p{margin:.4rem 0}.md table,.df{border-collapse:collapse;width:100%;font-size:.86rem}
.md th,.md td,.df th,.df td{border-bottom:1px solid var(--line);padding:.35rem .55rem;text-align:left;vertical-align:top}.df th,.md th{background:#F0F4F8}
.tbl{overflow-x:auto;background:#fff;border:1px solid var(--line);border-radius:8px}
.box{border-radius:8px;padding:.6rem .9rem;font-size:.9rem;background:#E8EEF8}.box.warning{background:#FFF8E1}.box.error{background:#FDECEC}.box.success{background:#E7F6EE}
details{background:#fff;border:1px solid var(--line);border-radius:8px;padding:.4rem .8rem;margin:8px 0}summary{cursor:pointer;font-weight:600}
.tabbar{display:flex;gap:4px;flex-wrap:wrap;border-bottom:2px solid var(--line);margin:14px 0 10px}
.tabbtn{border:0;background:none;padding:.5rem .8rem;cursor:pointer;font:inherit;color:var(--mid);border-bottom:3px solid transparent;margin-bottom:-2px}
.tabbtn.on{color:#C21E6B;border-bottom-color:#C21E6B;font-weight:600}.tabpane{display:none}.tabpane.on{display:block}
.plot{width:100%;min-height:340px;background:#fff;border:1px solid var(--line);border-radius:8px}
hr{border:0;border-top:1px solid var(--line);margin:14px 0}
@media(max-width:640px){.wrap{padding:12px}.m-value{font-size:1.3rem}}
"""

JS = """
function renderPlots(){
  document.querySelectorAll('.plot:not(.done)').forEach(function(d){
    if(d.offsetParent===null) return;
    try{var s=JSON.parse(document.getElementById(d.dataset.spec).textContent);
      Plotly.newPlot(d,s.data,s.layout,{responsive:true,displaylogo:false});d.classList.add('done');}catch(e){d.textContent='';}
  });
  window.dispatchEvent(new Event('resize'));
}
document.addEventListener('click',function(e){
  var b=e.target.closest('.tabbtn');
  if(b){document.querySelectorAll('[data-g="'+b.dataset.g+'"]').forEach(function(x){x.classList.toggle('on',x.dataset.i===b.dataset.i);});renderPlots();}
  var m=e.target.closest('.mk button');
  if(m){document.querySelectorAll('.mk button').forEach(function(x){x.classList.toggle('on',x===m);});
    document.querySelectorAll('section.market').forEach(function(s){s.classList.toggle('on',s.dataset.m===m.dataset.m);});renderPlots();}
});
document.addEventListener('toggle',function(){setTimeout(renderPlots,30);},true);
window.addEventListener('load',renderPlots);
"""


def export(config: str, out: Path, title: str | None = None, single_file: Path | None = None) -> dict:
    os.environ["CONFIG_FILE"] = config
    os.environ["VIEW_MODE"] = "client"
    os.environ["AHREFS_ENABLED"] = "0"          # a snapshot never spends credits
    sys.path.insert(0, str(ROOT))
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=2400)
    at.run()
    if at.exception:
        raise RuntimeError("dashboard raised: " + "; ".join(str(e.value)[:200] for e in at.exception))

    cfg_path = Path(config) if Path(config).is_absolute() else ROOT / config
    client = json.loads(cfg_path.read_text(encoding="utf-8")).get("client_name", "Client")
    r = Renderer()
    radios = [x for x in at.radio if x.key == "market_filter"]
    sections, markets = [], []
    if radios:
        opts = list(radios[0].options)
        for i, o in enumerate(opts):
            if i:
                at.radio(key="market_filter").set_value(o).run()
                if at.exception:
                    raise RuntimeError(f"dashboard raised for {o}")
            markets.append(o)
            sections.append(r.children(at.main))
    else:
        markets.append("All markets")
        sections.append(r.children(at.main))

    stamp = datetime.now().strftime("%d-%m-%Y")
    switch = ""
    if len(markets) > 1:
        switch = '<div class="mk">' + "".join(
            f'<button data-m="{html.escape(m)}" class="{"on" if i == 0 else ""}">{html.escape(m)}</button>'
            for i, m in enumerate(markets)) + "</div>"
    body = "".join(f'<section class="market{" on" if i == 0 else ""}" data-m="{html.escape(m)}">{s}</section>'
                   for i, (m, s) in enumerate(zip(markets, sections)))
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{html.escape(title or client)} | Linkbuilding dashboard</title>'
            f'<style>{CSS}</style></head><body><div class="wrap">'
            f'<div class="snap"><span>Snapshot of {stamp}. Filters other than the market are fixed.</span><span>{html.escape(client)}</span></div>'
            f'{switch}{body}</div><script src="plotly.min.js"></script><script>{JS}</script></body></html>')

    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    import plotly
    plotly_js = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    shutil.copy(plotly_js, out / "plotly.min.js")
    res = {"client": client, "markets": markets, "bytes": len(page), "plots": r.n, "skipped": r.skipped, "out": str(out)}
    if single_file:
        # One self-contained file (plotly inlined): can be shared via Google Drive per e-mail address and opened offline.
        lib = plotly_js.read_text(encoding="utf-8").replace("</script", "<\\/script")
        one = page.replace('<script src="plotly.min.js"></script>', f"<script>{lib}</script>")
        single_file.parent.mkdir(parents=True, exist_ok=True)
        single_file.write_text(one, encoding="utf-8")
        res["single_file"] = str(single_file)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--single-file", help="also write one self-contained HTML file (plotly inlined) to this path")
    a = ap.parse_args()
    res = export(a.config, Path(a.out), a.title, Path(a.single_file) if a.single_file else None)
    print(json.dumps(res, ensure_ascii=True))
