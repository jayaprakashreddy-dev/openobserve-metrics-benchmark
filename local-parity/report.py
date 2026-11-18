#!/usr/bin/env python3
"""Generate results/report.html: a single flat page summarising the local TSDB parity benchmark.

  python3 report.py [results/parity-<ts>.json]     # default: newest run that includes OpenObserve
"""
import html
import json
import sys
from datetime import datetime
from pathlib import Path

from observations import BOTTOM_LINE, EXEC_SUMMARY, NOT_TESTED, OBSERVATIONS, SETUP_ROWS

HERE = Path(__file__).parent
SYSTEM_LABELS = {"mimir": "Mimir 3.2.2", "o2": "OpenObserve v1.1.1", "vm": "VictoriaMetrics 1.154.0"}
VERDICT_CLASS = {"PASS": "v-pass", "SAME-ERR": "v-same", "DIFF": "v-diff", "ERR": "v-err"}
SEVERITY_CLASS = {"high": "sev-high", "medium": "sev-med", "low": "sev-low", "info": "sev-info"}
STATUS_LABEL = {"verified": "Verified", "observed": "Observed", "open": "Cause not isolated", "note": "Not tested directly"}


def newest_run_with(system):
    for path in sorted((HERE / "results").glob("parity-*.json"), reverse=True):
        if system in json.loads(path.read_text())["systems"]:
            return path
    sys.exit("no parity run that includes OpenObserve; run parity.py --systems prometheus,mimir,vm,o2")


def tally(rows, system):
    counts = {"PASS": 0, "DIFF": 0, "ERR": 0, "SAME-ERR": 0}
    for row in rows:
        counts[row["systems"][system]["verdict"]] += 1
    return counts


def group_pass_rates(rows, systems):
    groups = list(dict.fromkeys(row["group"] for row in rows))
    rates = {s: [] for s in systems}
    for group in groups:
        subset = [r for r in rows if r["group"] == group]
        for system in systems:
            ok = sum(r["systems"][system]["verdict"] in ("PASS", "SAME-ERR") for r in subset)
            rates[system].append(round(100 * ok / len(subset), 1))
    return groups, rates


def esc(text):
    return html.escape(str(text), quote=True)


def render_observations():
    cards = []
    for obs in OBSERVATIONS:
        evidence = "".join(f"<li>{esc(line)}</li>" for line in obs["evidence"])
        cards.append(f"""
<article class="obs {SEVERITY_CLASS[obs['severity']]}" id="{esc(obs['id'])}">
  <header>
    <span class="chip sys">{esc(obs['system'])}</span>
    <span class="chip">{esc(obs['severity'].upper())}</span>
    <span class="chip status">{esc(STATUS_LABEL[obs['status']])}</span>
  </header>
  <h3>{esc(obs['id'])}. {esc(obs['title'])}</h3>
  <p>{esc(obs['detail'])}</p>
  <ul>{evidence}</ul>
  <p class="why"><strong>Why it matters:</strong> {esc(obs['matters'])}</p>
</article>""")
    return "\n".join(cards)


def render_table(rows, systems):
    head = "".join(f'<th scope="col">{esc(SYSTEM_LABELS[s])}</th>' for s in systems)
    body = []
    for row in rows:
        cells = []
        for system in systems:
            cell = row["systems"][system]
            note = "" if cell["verdict"] == "PASS" else f'<span class="note">{esc(cell["summary"])}</span>'
            cells.append(f'<td><span class="verdict {VERDICT_CLASS[cell["verdict"]]}">{esc(cell["verdict"])}</span>{note}</td>')
        flag = "diff" if any(row["systems"][s]["verdict"] not in ("PASS", "SAME-ERR") for s in systems) else "ok"
        body.append(f'<tr data-flag="{flag}" data-text="{esc((row["id"] + " " + row["group"] + " " + row["why"]).lower())}">'
                    f'<th scope="row">{esc(row["id"])}</th><td>{esc(row["group"])}</td><td class="why-cell">{esc(row["why"])}</td>'
                    + "".join(cells) + "</tr>")
    return (f'<table id="results"><thead><tr><th scope="col">Query</th><th scope="col">Group</th><th scope="col">What it tests</th>'
            f"{head}</tr></thead><tbody>{''.join(body)}</tbody></table>")


def render_scorecards(rows, systems):
    cards = []
    for system in systems:
        t = tally(rows, system)
        total = len(rows)
        cards.append(f"""
<div class="score">
  <h3>{esc(SYSTEM_LABELS[system])}</h3>
  <p class="big">{t['PASS'] + t['SAME-ERR']}<span>/{total}</span></p>
  <p class="small">match Prometheus</p>
  <p class="small"><span class="verdict v-diff">DIFF</span> {t['DIFF']} &nbsp; <span class="verdict v-err">ERR</span> {t['ERR']}</p>
</div>""")
    return "".join(cards)


PAGE_CSS = """
:root{--ink:#1b1f23;--muted:#4b5563;--line:#d7dce1;--bg:#f6f7f9;--card:#fff}
*{box-sizing:border-box}body{margin:0;font:16px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
main{max-width:1180px;margin:0 auto;padding:24px 20px 64px}h1{font-size:2rem;margin:.2em 0}h2{font-size:1.4rem;margin:2.2em 0 .6em;border-bottom:2px solid var(--line);padding-bottom:.25em}
h3{margin:.2em 0 .4em;font-size:1.05rem}.sub{color:var(--muted);margin:0}a{color:#0b5cad}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin:12px 0}
.box ul{margin:.4em 0;padding-left:1.2em}.exec{border-left:6px solid #0b5cad}.exec li{margin:.35em 0}
.grid{display:grid;gap:14px}.g3{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}.g2{grid-template-columns:repeat(auto-fit,minmax(420px,1fr))}
.score{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px}.big{font-size:2.6rem;font-weight:700;margin:0;line-height:1}.big span{font-size:1.1rem;color:var(--muted)}.small{margin:.3em 0;color:var(--muted)}
.chart{position:relative;height:300px}
.verdict{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.78rem;font-weight:700;border:1px solid}
.v-pass{background:#e3f6e8;color:#0d5b2a;border-color:#0d5b2a}.v-diff{background:#fff1d6;color:#7a4500;border-color:#7a4500}
.v-err{background:#fde3e3;color:#8a1212;border-color:#8a1212}.v-same{background:#e8eef7;color:#27415f;border-color:#27415f}
.obs{background:var(--card);border:1px solid var(--line);border-left-width:8px;border-radius:10px;padding:14px 18px;margin:12px 0}
.sev-high{border-left-color:#b42318}.sev-med{border-left-color:#b76e00}.sev-low{border-left-color:#4b6b88}.sev-info{border-left-color:#2e7d32}
.obs header{display:flex;gap:6px;flex-wrap:wrap}.chip{font-size:.72rem;font-weight:700;padding:1px 8px;border-radius:6px;background:#eceff3;color:#1b1f23;border:1px solid var(--line)}
.chip.sys{background:#1b1f23;color:#fff}.obs ul{margin:.4em 0 .6em;padding-left:1.2em}.why{margin:.4em 0 0;color:#1f2a37}
.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:8px 0}input[type=search]{padding:7px 10px;border:1px solid #8a94a0;border-radius:6px;min-width:260px;font-size:1rem}
label{cursor:pointer}table{border-collapse:collapse;width:100%;background:var(--card);font-size:.9rem}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}thead th{background:#1b1f23;color:#fff;position:sticky;top:0}
tbody th{font-weight:600;white-space:nowrap}.note{display:block;color:var(--muted);font-size:.78rem;margin-top:2px}.why-cell{color:var(--muted)}
.tablewrap{max-height:720px;overflow:auto;border:1px solid var(--line);border-radius:8px}
table.plain th{background:#eceff3;color:var(--ink);position:static}code{background:#eceff3;padding:1px 5px;border-radius:4px;font-size:.88em}
.skip{position:absolute;left:-999px}.skip:focus{left:8px;top:8px;background:#fff;padding:6px}
"""

PAGE_JS = """
const D = JSON.parse(document.getElementById('data').textContent);
const colors = {mimir:'#0b5cad', o2:'#8a4fff', vm:'#c75a00'};
new Chart(document.getElementById('stack'), {type:'bar',
  data:{labels:D.systems.map(s=>D.labels[s]), datasets:[
    {label:'Match Prometheus', data:D.systems.map(s=>D.tally[s].PASS + D.tally[s]['SAME-ERR']), backgroundColor:'#2e7d32'},
    {label:'Differ', data:D.systems.map(s=>D.tally[s].DIFF), backgroundColor:'#d98a00'},
    {label:'Error', data:D.systems.map(s=>D.tally[s].ERR), backgroundColor:'#b42318'}]},
  options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',scales:{x:{stacked:true,max:D.total,title:{display:true,text:'queries (of '+D.total+')'}},y:{stacked:true}}}});
new Chart(document.getElementById('groups'), {type:'bar',
  data:{labels:D.groups, datasets:D.systems.map(s=>({label:D.labels[s], data:D.rates[s], backgroundColor:colors[s]}))},
  options:{responsive:true,maintainAspectRatio:false,scales:{y:{min:0,max:100,title:{display:true,text:'% matching Prometheus'}}}}});
const rows = [...document.querySelectorAll('#results tbody tr')];
const q = document.getElementById('q'), only = document.getElementById('onlydiff');
function applyFilter(){const t=q.value.toLowerCase();rows.forEach(r=>{r.hidden=(only.checked&&r.dataset.flag==='ok')||(t&&!r.dataset.text.includes(t));});
  document.getElementById('count').textContent=rows.filter(r=>!r.hidden).length+' of '+rows.length+' queries shown';}
q.addEventListener('input',applyFilter);only.addEventListener('change',applyFilter);applyFilter();
"""


def chart_script_tag():
    """Inline Chart.js when vendored (page works offline); otherwise fall back to the CDN."""
    local = HERE / "vendor" / "chart.umd.min.js"
    if local.exists():
        source = local.read_text().replace("</script", "<\\/script")
        return "<script>" + source + "</script>"
    return '<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>'


def build(run_path):
    run = json.loads(run_path.read_text())
    rows, systems = run["rows"], [s for s in ("mimir", "o2", "vm") if s in run["systems"]]
    groups, rates = group_pass_rates(rows, systems)
    data = {"systems": systems, "labels": SYSTEM_LABELS, "total": len(rows), "groups": groups, "rates": rates,
            "tally": {s: tally(rows, s) for s in systems}}
    exec_items = "".join(f"<li>{esc(x)}</li>" for x in EXEC_SUMMARY)
    setup = "".join(f"<tr><th scope='row'>{esc(a)}</th><td>{esc(b)}</td><td>{esc(c)}</td></tr>" for a, b, c in SETUP_ROWS)
    todo = "".join(f"<li>{esc(x)}</li>" for x in NOT_TESTED)
    bottom = "".join(f"<li>{esc(x)}</li>" for x in BOTTOM_LINE)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TSDB PromQL parity benchmark: observations</title>
{chart_script_tag()}
<style>{PAGE_CSS}</style></head><body>
<a class="skip" href="#table">Skip to the full query table</a>
<main>
<h1>TSDB PromQL parity benchmark: all observations</h1>
<p class="sub">Prometheus-compatible time-series databases checked for PromQL result parity, with Prometheus as the reference. Local run, generated {stamp} from <code>{esc(run_path.name)}</code>.</p>

<section class="box exec" aria-labelledby="exec-h"><h2 id="exec-h" style="margin-top:0;border:0">Executive summary</h2><ul>{exec_items}</ul></section>

<h2>Scorecard</h2>
<div class="grid g3">{render_scorecards(rows, systems)}</div>
<div class="grid g2" style="margin-top:14px">
  <div class="box"><h3>Verdicts per system</h3><div class="chart"><canvas id="stack" role="img" aria-label="Stacked bar of pass, differ and error counts per system"></canvas></div></div>
  <div class="box"><h3>% matching Prometheus, by query group</h3><div class="chart"><canvas id="groups" role="img" aria-label="Grouped bar of pass rate per query group and system"></canvas></div></div>
</div>

<h2>Observations</h2>
<p class="sub">Severity is about impact on rule/alert evaluation. <strong>Verified</strong> means I reproduced the cause with a direct measurement, not only the diff.</p>
{render_observations()}

<h2>How the test was set up</h2>
<div class="box"><table class="plain"><thead><tr><th scope="col">Item</th><th scope="col">Vendor benchmark</th><th scope="col">This run</th></tr></thead><tbody>{setup}</tbody></table></div>

<h2 id="table">All {len(rows)} queries</h2>
<div class="controls">
  <label for="q">Filter</label><input id="q" type="search" placeholder="id, group or keyword (e.g. histogram, selectors)">
  <label><input id="onlydiff" type="checkbox"> Only rows where something differs</label>
  <span id="count" role="status" class="sub"></span>
</div>
<div class="tablewrap">{render_table(rows, systems)}</div>

<h2>Not tested yet</h2>
<div class="box"><ul>{todo}</ul></div>

<section class="box exec" aria-labelledby="bottom-h"><h2 id="bottom-h" style="margin-top:0;border:0">Bottom line</h2><ul>{bottom}</ul></section>
</main>
<script id="data" type="application/json">{json.dumps(data)}</script>
<script>{PAGE_JS}</script>
</body></html>"""


def main():
    run_path = Path(sys.argv[1]) if len(sys.argv) > 1 else newest_run_with("o2")
    out = HERE / "results" / "report.html"
    out.write_text(build(run_path))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
