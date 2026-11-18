#!/usr/bin/env python3
"""Generate QUERIES.md: every query the parity harness runs (from queries.py) plus the ad-hoc diagnostics.

  python3 queries_doc.py
"""
from pathlib import Path

from queries import CATALOG, RANGE_WINDOWS

HERE = Path(__file__).parent
VENDOR_GROUPS = {"benchmark", "benchmark-range"}
END_NOTE = "end of data = 2026-11-15T06:00:00Z (backfill start 03:00:00Z + 3 h)"

# Diagnostics run by hand while investigating differences. They are not part of the catalog.
# Each item: (title, query, finding[, fence language]); the language defaults to promql.
ADHOC = [
    ("Metric and label discovery", "/api/v1/label/__name__/values and /api/v1/labels (Prometheus)",
     "6 metric names (codelab_api_* series, buckets, count, sum, errors, in-progress gauge); labels app, instance, job, le, method, namespace, node, path, pod, region, status, version, vnode.", "text"),
    ("Readiness probe (parity.py wait_until_ready)", "count(codelab_api_request_duration_seconds_count)  at end - 15s",
     "Polled until every system equals Prometheus (6,480). Mimir returned nothing until its blocks were shipped and synced."),
    ("Data-identity check before trusting any comparison",
     "count(codelab_api_request_duration_seconds_count)\ncount(codelab_api_request_duration_seconds_bucket)\nsum(codelab_api_requests_total)",
     "Prometheus and OpenObserve agreed exactly: 6,480 / 168,480 / 22,231,129. Confirms the seeded generator is deterministic and ingestion was complete."),
    ("Mimir ingestion state (not PromQL: GET /metrics)",
     "cortex_ingester_ingested_samples_total, cortex_ingester_memory_series, cortex_ingester_tsdb_compactions_total, cortex_ingester_shipper_uploads_total",
     "137,239,532 samples and 191,190 series ingested; 0 compactions/uploads until the 5-minute idle timeout passed, then 2 and 2.", "text"),
    ("Which series does VictoriaMetrics drop? (C2 follow-up)",
     'histogram_quantile(0.9, rate(codelab_api_request_duration_seconds_bucket{path="/api/bar",method="GET"}[5m]))',
     "Prometheus 60 series, VictoriaMetrics 48. All 12 missing series are NaN in Prometheus."),
    ("Find the worst histogram_quantile gap (A2 follow-up)",
     "histogram_quantile(0.9, sum by(le, path) (rate(codelab_api_request_duration_seconds_bucket{}[5m])))  compared per path",
     "Worst: /api/service-18, 29.0 ms (Prometheus) vs 44.5 ms (VictoriaMetrics), 35% apart. Next: /api/service-49 (9%), /api/service-5 (7%)."),
    ("Root cause of that gap: same inputs, own quantile code",
     'sum by (le) (rate(codelab_api_request_duration_seconds_bucket{path="/api/service-18"}[5m]))\nhistogram_quantile(0.9, <the same expression>)',
     "A hand-written quantile over each system's own bucket rates reproduced both answers (0.0290, 0.0445), so histogram_quantile agrees and rate() is the input that differs. Share below le=0.029: 91.1% vs 89.7%."),
    ("Raw-sample check of rate() (first attempt, flawed)",
     'codelab_api_requests_total{path="/api/bar",method="GET",status="200",region="eu-central-1"}[5m]\nrate(<same selector>[5m])',
     "The selector matched 6 series, so [0] of each result was not guaranteed to be the same series. Discarded and redone below."),
    ("Raw-sample check of rate() (exact label set)",
     "codelab_api_requests_total{<all labels of one series>}[6m]\nrate(codelab_api_requests_total{<all labels of one series>}[5m])",
     "Prometheus 0.674074 = (v[-15s]-v[-285s])/270. VictoriaMetrics 0.659649 = (v[-15s]-v[-300s])/285. Both matched by hand to 1e-9."),
    ("Missing-label matcher on OpenObserve (B1 follow-ups)",
     'count(codelab_api_requests_total{nonexistent_label="foo"})\ncount(codelab_api_requests_total)\ncount(codelab_api_requests_total{status_code="500"})   # typo: real label is "status"\ncodelab_api_requests_total{nonexistent_label="foo"}   # bare selector',
     "Prometheus: 0, 6,480, 0, no series. OpenObserve: 6,480, 6,480, 6,480, 6,480 series. The matcher on a missing label is ignored."),
    ("Where do the 3h-window differences sit? (R4 follow-up)",
     'histogram_quantile(0.9, sum by(le, path) (rate(codelab_api_request_duration_seconds_bucket{path="/api/bar"}[5m])))  range, end-3h .. end, step 15s',
     "OpenObserve differs on 18 of 720 points; all between +15 s and +270 s after the first sample, none missing or extra."),
]


def evaluation(entry):
    kind = entry["kind"]
    if kind == "instant":
        offset = entry["end_offset"]
        return f"instant at {'end of data' if not offset else f'end of data + {offset}s'}"
    if kind == "range":
        if "window" in entry and entry["window"] == 0:
            return "range with start == end, step 15s"
        step = entry.get("step", 15)
        if "window" in entry:
            return f"range, last {entry['window'] // 60} min, step={step}"
        windows = "/".join(RANGE_WINDOWS)
        return f"range over the last {windows} (three runs), step 15s"
    return {"labels": "GET /api/v1/labels (last 10 min)", "label_values": "GET /api/v1/label/path/values (last 10 min)",
            "series": "GET /api/v1/series (last 10 min)"}[kind]


def entry_block(entry):
    origin = "vendor" if entry["group"] in VENDOR_GROUPS else "added"
    lines = [f"### {entry['id']}", f"- Origin: {origin}", f"- Evaluated: {evaluation(entry)}", f"- Tests: {entry['why']}"]
    if entry["group"] == "benchmark-range":
        lines.append(f"- PromQL: same as {entry['id'].replace('R', 'A', 1)}")
    elif entry["promql"]:
        lines += ["", "```promql", entry["promql"], "```"]
    return "\n".join(lines) + "\n"


def main():
    vendor = [e for e in CATALOG if e["group"] in VENDOR_GROUPS]
    added = [e for e in CATALOG if e["group"] not in VENDOR_GROUPS]
    out = ["# Queries used in the parity check", "",
           "Every query in `queries.py`, plus the ad-hoc diagnostics run while investigating. Reference system: Prometheus 3.6.0.", "",
           f"Instant queries are evaluated at the {END_NOTE}. Metric names come from the vendor's `fake-webserver` generator.", "",
           "| Origin | Catalog entries | Rows in the results table |", "|---|---:|---:|",
           f"| Vendor (`bench/queries.sh`) | {len(vendor)} | 4 instant + 4 x {len(RANGE_WINDOWS)} windows = {4 + 4 * len(RANGE_WINDOWS)} |",
           f"| Added by this harness | {len(added)} | {len(added)} |",
           f"| Total | {len(CATALOG)} | {4 + 4 * len(RANGE_WINDOWS) + len(added)} |", "",
           "The vendor's four queries are copied from `bench/queries.sh` (path filter `/api/bar` is the repo's default); the range forms reuse them "
           "over the repo's 30m/1h/3h windows. The added queries are a generic catalog aimed at known PromQL differences "
           "(see openobserve issues #14924 and #15761) and common rule/dashboard functions. They are not taken from real production rules.", ""]
    current = None
    for entry in CATALOG:
        if entry["group"] != current:
            current = entry["group"]
            out += [f"## Group: {current}", ""]
        out.append(entry_block(entry))
    out += ["## Ad-hoc diagnostics (not in the catalog)", "",
            "Run by hand with small scripts against the same data. Numbers are from the 2026-11-17 run.", ""]
    for title, query, found, *lang in ADHOC:
        out += [f"### {title}", "", f"```{lang[0] if lang else 'promql'}", query, "```", "", f"Found: {found}", ""]
    (HERE / "QUERIES.md").write_text("\n".join(out))
    print(f"wrote QUERIES.md ({len(CATALOG)} catalog entries, {len(ADHOC)} diagnostics)")


if __name__ == "__main__":
    main()
