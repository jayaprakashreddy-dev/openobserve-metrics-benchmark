#!/usr/bin/env python3
"""PromQL result-parity check across local Prometheus-compatible backends.

Prometheus is the reference. Every other system is diffed against it, query by query.
This checks CORRECTNESS (same series, same values), not speed; latencies are informational only.

  python3 parity.py                      # all systems that answer, full catalog
  python3 parity.py --only selectors     # a group or id substring
  python3 parity.py --systems prometheus,mimir,vm,o2
"""
import argparse
import base64
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from queries import CATALOG, RANGE_WINDOWS

REFERENCE = "prometheus"
SYSTEMS = {  # name: (base_url, basic_auth or None)
    "prometheus": ("http://localhost:9090", None),
    "mimir": ("http://localhost:9009/prometheus", None),
    "vm": ("http://localhost:8428", None),
    "o2": ("http://localhost:5080/api/default/prometheus", ("root@example.com", "Complexpass#123")),
}
REL_TOL, ABS_TOL = 1e-6, 1e-9
TIMEOUT = 600


def http_json(base, auth, path, params):
    url = f"{base}{path}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            code = resp.status
    except urllib.error.HTTPError as err:
        body, code = err.read(), err.code
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        return {"http": 0, "error": f"connection: {err}", "elapsed": time.time() - started}
    elapsed = time.time() - started
    try:
        return {"http": code, "json": json.loads(body), "elapsed": elapsed}
    except json.JSONDecodeError:
        return {"http": code, "error": f"non-JSON body: {body[:120]!r}", "elapsed": elapsed}


def to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return text  # strings (e.g. string-literal results) compare as text


def normalize(resp):
    """Reduce an HTTP response to {'status','type','series'|'items','error','elapsed'}."""
    out = {"elapsed": resp.get("elapsed", 0.0)}
    body = resp.get("json")
    if body is None or body.get("status") != "success":
        message = resp.get("error") or (body or {}).get("error") or f"http {resp.get('http')}"
        return {**out, "status": "error", "error": str(message)[:200]}
    data = body["data"]
    if isinstance(data, list):  # labels / label_values / series endpoints
        items = {json.dumps(x, sort_keys=True) if isinstance(x, dict) else x for x in data}
        return {**out, "status": "ok", "type": "list", "items": items}
    kind, result = data["resultType"], data["result"]
    series = {}
    if kind == "vector":
        for item in result:
            series[tuple(sorted(item["metric"].items()))] = {None: to_float(item["value"][1])}
    elif kind == "matrix":
        for item in result:
            points = {round(float(ts), 3): to_float(val) for ts, val in item["values"]}
            series[tuple(sorted(item["metric"].items()))] = points
    else:  # scalar | string
        series[()] = {None: to_float(result[1])}
    return {**out, "status": "ok", "type": kind, "series": series}


def same_value(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    if math.isnan(a) and math.isnan(b):
        return True
    return a == b or math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)


def rel_diff(a, b):
    if isinstance(a, str) or isinstance(b, str) or math.isnan(a) or math.isnan(b) or math.isinf(a) or math.isinf(b):
        return 0.0 if same_value(a, b) else float("inf")
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def compare(ref, got):
    """Return (verdict, detail dict). verdict: PASS | DIFF | ERR | SAME-ERR."""
    if ref["status"] == "error" and got["status"] == "error":
        return "SAME-ERR", {"ref": ref["error"], "got": got["error"]}
    if got["status"] == "error":
        return "ERR", {"error": got["error"]}
    if ref["status"] == "error":
        return "DIFF", {"note": "reference errored but system answered", "ref": ref["error"]}
    if ref["type"] != got["type"]:
        return "DIFF", {"note": f"result type {ref['type']} vs {got['type']}"}
    if ref["type"] == "list":
        missing, extra = sorted(ref["items"] - got["items"]), sorted(got["items"] - ref["items"])
        verdict = "PASS" if not missing and not extra else "DIFF"
        return verdict, {"missing": len(missing), "extra": len(extra),
                         "examples": {"missing": missing[:3], "extra": extra[:3]}}
    r, g = ref["series"], got["series"]
    missing, extra = sorted(set(r) - set(g)), sorted(set(g) - set(r))
    detail = {"ref_series": len(r), "got_series": len(g), "missing": len(missing), "extra": len(extra),
              "value_diffs": 0, "point_mismatch": 0, "max_rel": 0.0, "examples": []}
    for key in set(r) & set(g):
        if set(r[key]) != set(g[key]):
            detail["point_mismatch"] += 1
        for ts in set(r[key]) & set(g[key]):
            if not same_value(r[key][ts], g[key][ts]):
                detail["value_diffs"] += 1
                detail["max_rel"] = max(detail["max_rel"], rel_diff(r[key][ts], g[key][ts]))
                if len(detail["examples"]) < 3:
                    detail["examples"].append({"labels": dict(key), "ts": ts, "ref": r[key][ts], "got": g[key][ts]})
    for label, keys in (("missing_examples", missing), ("extra_examples", extra)):
        detail[label] = [dict(k) for k in keys[:2]]
    clean = not (missing or extra or detail["value_diffs"] or detail["point_mismatch"])
    return ("PASS" if clean else "DIFF"), detail


def run_one(system, entry, end_ts, window):
    base, auth = SYSTEMS[system]
    kind, at = entry["kind"], end_ts + entry["end_offset"]
    if kind == "instant":
        resp = http_json(base, auth, "/api/v1/query", {"query": entry["promql"], "time": at})
    elif kind == "range":
        step = entry.get("step", 15)
        resp = http_json(base, auth, "/api/v1/query_range",
                         {"query": entry["promql"], "start": end_ts - window, "end": end_ts, "step": step})
    elif kind == "labels":
        resp = http_json(base, auth, "/api/v1/labels", {"start": end_ts - 600, "end": end_ts})
    elif kind == "label_values":
        resp = http_json(base, auth, f"/api/v1/label/{entry['promql']}/values", {"start": end_ts - 600, "end": end_ts})
    else:
        resp = http_json(base, auth, "/api/v1/series",
                         {"match[]": entry["promql"], "start": end_ts - 600, "end": end_ts})
    return normalize(resp)


def expand(catalog, only):
    """Range entries without an explicit window fan out to every benchmark window."""
    pattern = re.compile(only) if only else None
    for entry in catalog:
        if pattern and not (pattern.search(entry["id"]) or pattern.search(entry["group"])):
            continue
        if entry["kind"] == "range" and "window" not in entry:
            for label, seconds in RANGE_WINDOWS.items():
                yield dict(entry, id=f"{entry['id']}-{label}"), seconds
        else:
            yield entry, entry.get("window", 0)


def wait_until_ready(systems, end_ts, minutes):
    """Mimir ships and syncs blocks in the background; wait until all systems agree on the series count."""
    probe = "count(" + "codelab_api_request_duration_seconds_count" + ")"
    deadline = time.time() + minutes * 60
    while True:
        counts = {}
        for name in systems:
            base, auth = SYSTEMS[name]
            norm = normalize(http_json(base, auth, "/api/v1/query", {"query": probe, "time": end_ts - 15}))
            counts[name] = (list(norm["series"].values())[0][None] if norm["status"] == "ok" and norm["series"] else None)
        print(f"  readiness: {counts}")
        ref = counts.get(REFERENCE)
        if ref and all(v == ref for v in counts.values()):
            return True
        if time.time() > deadline:
            print("  readiness timed out; continuing (results for lagging systems may be incomplete)")
            return False
        time.sleep(30)


def summarize(detail):
    if "note" in detail:
        return detail["note"]
    if "error" in detail:
        return f"error: {detail['error'][:70]}"
    if "ref" in detail and "got" in detail:
        return "both errored"
    if "ref_series" not in detail:
        return f"missing={detail['missing']} extra={detail['extra']}"
    parts = [f"series {detail['got_series']}/{detail['ref_series']}"]
    for key in ("missing", "extra", "value_diffs", "point_mismatch"):
        if detail[key]:
            parts.append(f"{key}={detail[key]}")
    if detail["value_diffs"]:
        parts.append(f"max_rel={detail['max_rel']:.3g}")
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--systems", default="prometheus,mimir,vm,o2")
    ap.add_argument("--only", default="")
    ap.add_argument("--start", default="2026-11-15T03:00:00Z")
    ap.add_argument("--hours", type=float, default=3)
    ap.add_argument("--wait-ready", type=float, default=0, help="minutes to wait for all systems to agree first")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    end_ts = datetime.fromisoformat(args.start.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp() \
        + args.hours * 3600
    wanted = [s for s in args.systems.split(",") if s in SYSTEMS]
    live = [s for s in wanted if http_json(*SYSTEMS[s], "/api/v1/query", {"query": "1"}).get("http") == 200]
    skipped = sorted(set(wanted) - set(live))
    if REFERENCE not in live:
        sys.exit("reference system (prometheus) is not answering; start it with ./stack.sh start")
    print(f"systems: {live}" + (f"  (not answering, skipped: {skipped})" if skipped else ""))
    if args.wait_ready:
        wait_until_ready(live, end_ts, args.wait_ready)

    rows, report = [], []
    with ThreadPoolExecutor(max_workers=len(live)) as pool:
        for entry, window in expand(CATALOG, args.only):
            futures = {s: pool.submit(run_one, s, entry, end_ts, window) for s in live}
            results = {s: f.result() for s, f in futures.items()}
            row = {"id": entry["id"], "group": entry["group"], "why": entry["why"], "systems": {}}
            for system in live:
                if system == REFERENCE:
                    row["systems"][system] = {"verdict": "REF", "elapsed": round(results[system]["elapsed"], 2),
                                              "status": results[system]["status"]}
                    continue
                verdict, detail = compare(results[REFERENCE], results[system])
                row["systems"][system] = {"verdict": verdict, "summary": summarize(detail), "detail": detail,
                                          "elapsed": round(results[system]["elapsed"], 2)}
            rows.append(row)
            marks = "  ".join(f"{s}={row['systems'][s]['verdict']}" for s in live if s != REFERENCE)
            print(f"{entry['id']:<34} {marks}")

    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / f"parity-{stamp}.json").write_text(json.dumps(
        {"end_ts": end_ts, "systems": live, "rows": rows}, indent=1, default=str))
    others = [s for s in live if s != REFERENCE]
    lines = [f"# PromQL parity vs {REFERENCE}  ({stamp})", "",
             f"Systems: {', '.join(live)}. Tolerance: rel {REL_TOL}, abs {ABS_TOL}.", "",
             "| id | group | " + " | ".join(others) + " |", "|---|---|" + "---|" * len(others)]
    for row in rows:
        cells = [f"{row['systems'][s]['verdict']}" + (f" ({row['systems'][s]['summary']})"
                 if row["systems"][s]["verdict"] != "PASS" else "") for s in others]
        lines.append(f"| {row['id']} | {row['group']} | " + " | ".join(cells) + " |")
    lines += ["", "## Totals", ""]
    for system in others:
        tally = {}
        for row in rows:
            tally[row["systems"][system]["verdict"]] = tally.get(row["systems"][system]["verdict"], 0) + 1
        lines.append(f"- {system}: {tally}")
    (out_dir / f"parity-{stamp}.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out_dir}/parity-{stamp}.md and .json")


if __name__ == "__main__":
    main()
