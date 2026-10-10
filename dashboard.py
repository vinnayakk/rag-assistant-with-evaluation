import html, json, math
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

import metrics

router = APIRouter()
CHART_MAX_BARS = 40                                            # the last 40 answered requests are drawn and listed


@router.get("/stats")
def stats(mode: Optional[str] = None, last: Optional[int] = Query(None, ge=1, le=1_000_000)):
    records, bad = metrics.read_log()
    records = metrics.select(records, mode, last)
    return {"filters": {"mode": mode, "last": last}, "overall": metrics.summarise(records),
            "by_mode": metrics.summarise_by_mode(records), "unreadable_lines": bad}


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(mode: Optional[str] = None, last: Optional[int] = Query(None, ge=1, le=1_000_000)):
    everything, bad = metrics.read_log()
    modes_present = sorted({r.get("mode") for r in everything if r.get("mode")})
    return HTMLResponse(render(metrics.select(everything, mode, last), mode, last, modes_present, bad))


# ----------------------------------------------------------------------------- small helpers
e = html.escape


def usd(v, digits=4):
    return "-" if v is None else f"${v:,.{digits}f}"


def ms(v):
    return "-" if v is None else (f"{v / 1000:.2f} s" if v >= 1000 else f"{v:,.0f} ms")


def tick_label(v):
    return "0" if v == 0 else (f"{v:g} ms" if v < 1000 else f"{v / 1000:g} s")


def nice_step(x):
    """A round number at or above x: 1, 2, 2.5 or 5 times a power of ten (so the axis reads 0, 500, 1,000 ...)."""
    mag = 10 ** math.floor(math.log10(x))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if x <= m * mag)


def link(label, params, current):
    q = "&".join(f"{k}={e(str(v))}" for k, v in params.items() if v)
    href = "/dashboard" + (f"?{q}" if q else "")
    return (f'<a href="{href}"' + (' aria-current="true"' if current else "") + f">{'&#10003; ' if current else ''}{e(label)}</a>")


# ----------------------------------------------------------------------------- the chart
def seg_path(x, y, w, h, round_top):
    """A bar segment: square at the bottom, 4px rounded corners at the top when it is the last segment of the stack."""
    r = min(4, w / 2, h) if round_top else 0
    if r <= 0:
        return f"M{x:.1f},{y + h:.1f}V{y:.1f}H{x + w:.1f}V{y + h:.1f}Z"
    return (f"M{x:.1f},{y + h:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}H{x + w - r:.1f}"
            f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}V{y + h:.1f}Z")


def chart(recs):
    """Stacked bars, one per request, oldest on the left: search (bottom) and the model call (top)."""
    W, H, L, R, T, B = 720, 236, 56, 12, 12, 34
    pw, ph = W - L - R, H - T - B
    n = len(recs)
    parts = [r.get("search_ms") or 0 for r in recs], [r.get("llm_ms") or 0 for r in recs]
    tallest = max(s + m for s, m in zip(*parts)) or 1
    step = nice_step(tallest / 4)
    top = step * math.ceil(tallest / step)
    base = T + ph
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Latency of the last {n} requests, split into search and model call">']
    t = 0
    while t <= top + 1e-9:                                                 # gridlines and tick labels
        y = base - ph * t / top
        out.append(f'<line class="{"axis" if t == 0 else "grid"}" x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="tick" x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{e(tick_label(t))}</text>')
        t += step
    slot = pw / n
    bw = min(24, max(3, slot * 0.7))                                       # thin bars: never fill the slot
    for i, rec in enumerate(recs):
        s_ms, m_ms = parts[0][i], parts[1][i]
        x = L + i * slot + (slot - bw) / 2
        hs, hm = ph * s_ms / top, ph * m_ms / top
        tip = {"q": (rec.get("question") or "")[:90], "mode": rec.get("mode"), "search": ms(s_ms), "llm": ms(m_ms),
               "total": ms(s_ms + m_ms), "cost": usd(rec.get("cost_usd"))}
        label = f"Request {i + 1} of {n}: total {ms(s_ms + m_ms)}, search {ms(s_ms)}, model call {ms(m_ms)}"
        out.append(f'<g class="bar" tabindex="0" aria-label="{e(label)}" data-tip="{e(json.dumps(tip), quote=True)}">')
        if hs > 0:
            out.append(f'<path class="seg s1" d="{seg_path(x, base - hs, bw, hs, round_top=hm <= 0)}"/>')
        if hm > 0:
            gap = 2 if hs > 0 and hm > 3 else 0                           # a 2px surface gap between the two segments
            out.append(f'<path class="seg s2" d="{seg_path(x, base - hs - hm, bw, hm - gap, round_top=True)}"/>')
        out.append(f'<rect class="hit" x="{L + i * slot:.1f}" y="{T}" width="{slot:.1f}" height="{ph + B - 8}"/></g>')
    out.append(f'<text class="tick" x="{L}" y="{H - 6}">oldest</text>'
               f'<text class="tick" x="{W - R}" y="{H - 6}" text-anchor="end">newest</text>')
    out.append("</svg>")
    return "".join(out)


# ----------------------------------------------------------------------------- the page
CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;
--axis:#c3c2b7;--border:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;
--ink:#fff;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--grid:#2c2c2a;
--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:22px;margin:0 0 4px;font-weight:600}h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub{color:var(--ink2);margin:0;font-size:14px}
.filters{display:flex;flex-wrap:wrap;gap:6px 24px;margin:18px 0 16px;font-size:14px}
.filters div{display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center}.filters b{font-weight:500;color:var(--ink2);margin-right:4px}
.filters a{color:var(--ink2);text-decoration:none;padding:3px 10px;border-radius:999px;border:1px solid var(--border)}
.filters a:hover{background:var(--surface)}.filters a[aria-current]{color:var(--ink);font-weight:600;border-color:var(--ink2)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:12px}
.card,.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px}
.card{margin-bottom:12px}
.tile .label{color:var(--ink2);font-size:13px}.tile .value{font-size:30px;font-weight:600;line-height:1.2;margin:2px 0}
.tile .note{color:var(--ink2);font-size:13px}
.legend{display:flex;gap:16px;margin:10px 0 4px;font-size:13px;color:var(--ink2)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}
svg{display:block;width:100%;height:auto}
.grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--axis);stroke-width:1}
.tick{fill:var(--muted);font-size:11px}
.seg.s1,.dot1{fill:var(--s1);background:var(--s1)}.seg.s2,.dot2{fill:var(--s2);background:var(--s2)}
.bar{outline:none}.bar:hover .seg,.bar:focus-visible .seg{filter:brightness(1.15)}
.bar:focus-visible .hit{stroke:var(--ink);stroke-width:1}.hit{fill:transparent}
.scroll{overflow-x:auto;margin-top:8px}
table{border-collapse:collapse;width:100%;font-size:14px}
th{font-weight:500;color:var(--ink2);text-align:left;border-bottom:1px solid var(--axis);padding:6px 10px 6px 0;white-space:nowrap}
td{border-bottom:1px solid var(--grid);padding:6px 10px 6px 0;vertical-align:top}
th.n,td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;padding-right:0;padding-left:12px}
td.q{min-width:220px}
summary{cursor:pointer;font-weight:600}
.foot{color:var(--ink2);font-size:13px;margin-top:16px}
#tip{position:fixed;display:none;z-index:5;pointer-events:none;max-width:280px;background:var(--surface);color:var(--ink);
border:1px solid var(--axis);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.18)}
#tip .q{color:var(--ink2);margin-bottom:4px}#tip .row{display:flex;gap:8px;align-items:center}
#tip .k{width:10px;height:3px;border-radius:2px;display:inline-block}#tip b{font-weight:600}
code{font-size:13px}
"""

JS = """
(function(){var tip=document.getElementById('tip');if(!tip)return;
function row(parent,cls,value,label){var r=document.createElement('div');r.className='row';var k=document.createElement('span');
k.className='k';if(cls)k.style.background=cls;else k.style.background='transparent';r.appendChild(k);
var b=document.createElement('b');b.textContent=value;r.appendChild(b);var l=document.createElement('span');l.textContent=label;
r.appendChild(l);parent.appendChild(r)}
function show(el,x,y){var d=JSON.parse(el.getAttribute('data-tip'));tip.replaceChildren();
var q=document.createElement('div');q.className='q';q.textContent=(d.q||'')+(d.mode?'  ('+d.mode+')':'');tip.appendChild(q);
row(tip,'var(--s1)',d.search,'search');row(tip,'var(--s2)',d.llm,'model call');row(tip,'','= '+d.total,'total');row(tip,'',d.cost,'cost');
tip.style.display='block';var w=tip.offsetWidth,h=tip.offsetHeight;
tip.style.left=Math.max(8,Math.min(innerWidth-w-8,x+14))+'px';tip.style.top=Math.max(8,y-h-10)+'px'}
function hide(){tip.style.display='none'}
document.querySelectorAll('.bar').forEach(function(el){
el.addEventListener('pointermove',function(ev){show(el,ev.clientX,ev.clientY)});el.addEventListener('pointerleave',hide);
el.addEventListener('focus',function(){var r=el.getBoundingClientRect();show(el,r.left+r.width/2,r.top)});
el.addEventListener('blur',hide)})})();
"""


def chart_card(plotted):
    if not plotted:                                                        # every request so far failed: nothing to draw
        return '<section class="card"><h2>Where the time goes</h2><p class="sub">No request has had a model reply yet.</p></section>'
    return ('<section class="card"><h2>Where the time goes</h2>'
            f'<p class="sub">One bar per request, oldest on the left (the last {len(plotted)} that got a reply).</p>'
            '<div class="legend"><span><i class="dot1"></i>Search</span><span><i class="dot2"></i>Model call</span></div>'
            f"{chart(plotted)}</section>")


def tile(label, value, note):
    return f'<div class="tile"><div class="label">{e(label)}</div><div class="value">{e(value)}</div><div class="note">{note}</div></div>'


def table(headers, rows, numeric_from):
    head = "".join(f'<th class="{"n" if i >= numeric_from else ""}">{e(h)}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="{c[0]}">{c[1]}</td>' for c in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render(recs, mode, last, modes_present, unreadable):
    filters = (
        '<nav class="filters" aria-label="Filters">'
        '<div><b>Window</b>' + "".join(link(lbl, {"mode": mode, "last": v}, last == v)
                                      for lbl, v in (("All requests", None), ("Last 100", 100), ("Last 20", 20))) + "</div>"
        '<div><b>Search mode</b>' + link("All modes", {"last": last}, not mode)
        + "".join(link(m, {"mode": m, "last": last}, mode == m) for m in modes_present) + "</div></nav>")
    head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Assistant dashboard</title><style>{CSS}</style></head><body><main class=\"wrap\">"
            f"<h1>Assistant dashboard</h1>")
    if not recs:
        what = f"No requests with search mode {e(mode)} in" if mode else "No requests in"
        return (head + f'<p class="sub">{what} {e(str(metrics.log_path()))} yet.</p>{filters}'
                '<div class="card"><p>Start the server and ask something, and reload this page:</p>'
                "<p><code>curl -s localhost:8000/ask -H 'content-type: application/json' "
                "-d '{\"question\": \"How do I limit memory for Gitaly?\"}'</code></p></div></main></body></html>")

    s = metrics.summarise(recs)
    lat, cost, tok = s["latency_ms"], s["cost_usd"], s["tokens"]
    done = s["requests"] - s["errors"]
    plotted = [r for r in recs if r.get("status") != "error"][-CHART_MAX_BARS:]
    span = f"{(s['first_ts'] or '')[:16].replace('T', ' ')} to {(s['last_ts'] or '')[:16].replace('T', ' ')} UTC"
    replies = " · ".join(f"{n} {e(k)}" for k, n in sorted(s["statuses"].items(), key=lambda kv: -kv[1]))
    tiles = "".join([
        tile("Requests", f"{s['requests']:,}", replies),
        tile("Average latency", ms(lat["mean"]), f"median {ms(lat['median'])} · 95th percentile {ms(lat['p95'])}"),
        tile("Average cost per request", usd(cost["mean"]),
             f"{usd(cost['per_1000'], 2)} per 1,000 requests" + (f" · {cost['unpriced']} without a price" if cost["unpriced"] else "")),
        tile("Total cost", usd(cost["total"], 2 if (cost["total"] or 0) >= 0.1 else 4),
             f"average {tok['input_mean'] or 0:,.0f} tokens in, {tok['output_mean'] or 0:,.0f} out" if done else ""),
    ])

    by_mode_rows = []
    for m, ms_ in metrics.summarise_by_mode(recs).items():
        l, c = ms_["latency_ms"], ms_["cost_usd"]
        by_mode_rows.append([("", e(m)), ("n", f"{ms_['requests']:,}" + (f" ({ms_['errors']} error{'s' if ms_['errors'] != 1 else ''})" if ms_["errors"] else "")),
                             ("n", ms(l["mean"])), ("n", ms(l["median"])), ("n", ms(l["p95"])), ("n", ms(l["search_mean"])),
                             ("n", ms(l["llm_mean"])), ("n", usd(c["mean"]))])
    by_mode = table(["Search mode", "Requests", "Average", "Median", "95th pct", "Avg search", "Avg model call", "Avg cost"],
                    by_mode_rows, 1)

    recent_rows = []
    for r in reversed(plotted):
        recent_rows.append([("", e((r.get("ts") or "")[11:19])), ("", e(r.get("mode") or "-")), ("", e(r.get("status") or "-")),
                            ("q", e((r.get("question") or "")[:120])), ("n", ms(r.get("search_ms"))), ("n", ms(r.get("llm_ms"))),
                            ("n", ms(r.get("total_ms"))), ("n", usd(r.get("cost_usd")))])
    recent = table(["Time (UTC)", "Mode", "Reply", "Question", "Search", "Model call", "Total", "Cost"], recent_rows, 4)

    notes = (f"Averages use the {done:,} requests that got a model reply. "
             + (f"{s['errors']} failed requests are counted above but have no cost or full latency. " if s["errors"] else "")
             + "Latency is the server's own time for <code>/ask</code> (search + model call), not network or queueing. "
               "Cost = tokens × the price table in <code>metrics.py</code>."
             + (f" {unreadable} unreadable line(s) in the log were skipped." if unreadable else ""))
    return (head + f'<p class="sub">{s["requests"]:,} requests logged, {e(span)}</p>{filters}<section class="tiles">{tiles}</section>'
            f"{chart_card(plotted)}"
            f'<section class="card"><h2>By search mode</h2>{by_mode}</section>'
            f'<section class="card"><details><summary>Table view: the {len(plotted)} requests in the chart, newest first</summary>'
            f"{recent}</details></section><p class=\"foot\">{notes}</p></main><div id=\"tip\" role=\"status\"></div>"
            f"<script>{JS}</script></body></html>")
