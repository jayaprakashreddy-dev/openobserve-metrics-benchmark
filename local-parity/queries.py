"""Query catalog for the PromQL parity check.

Each entry: id, group, kind, promql (or endpoint params), why.
kind: instant | range | labels | label_values | series
`end_offset` shifts the evaluation time relative to the end of the loaded data (seconds).
Placeholders: {P} = path used by the benchmark's filtered queries.
"""

P = "/api/bar"
COUNT = "codelab_api_request_duration_seconds_count"
BUCKET = "codelab_api_request_duration_seconds_bucket"
REQS = "codelab_api_requests_total"
ERRS = "codelab_api_request_errors_total"
GAUGE = "codelab_api_http_requests_in_progress"
RATE_BY_PATH = f"sum by (path) (rate({COUNT}[5m]))"


def q(qid, group, promql, why, kind="instant", end_offset=0, **extra):
    return {"id": qid, "group": group, "kind": kind, "promql": promql,
            "why": why, "end_offset": end_offset, **extra}


BENCHMARK = [
    q("A1-irate", "benchmark", f"sum by (path) (irate({COUNT}[1m]))", "Vendor query 1"),
    q("A2-hist-all", "benchmark",
      f"histogram_quantile(0.9, sum by(le, path) (rate({BUCKET}{{}}[5m])))", "Vendor query 2 (all buckets)"),
    q("A3-hist-regex", "benchmark",
      f'histogram_quantile(0.9, sum by(le, path) (rate({BUCKET}{{path=~"{P}"}}[5m])))', "Vendor query 3"),
    q("A4-hist-eq", "benchmark",
      f'histogram_quantile(0.9, sum by(le, path) (rate({BUCKET}{{path="{P}"}}[5m])))', "Vendor query 4"),
]

# Same four, as range queries (the shape the vendor actually timed).
RANGE_WINDOWS = {"30m": 1800, "1h": 3600, "3h": 10800}
RANGE = [dict(x, id=x["id"].replace("A", "R", 1), kind="range", group="benchmark-range")
         for x in BENCHMARK]

SELECTORS = [  # issues #15761 / #15892: matchers on absent or NULL labels
    q("B1-missing-eq", "selectors", f'count({REQS}{{nonexistent_label="foo"}})',
      "Prometheus: empty. Bug class: matcher on missing label ignored (#15761)"),
    q("B2-missing-neq", "selectors", f'count({REQS}{{nonexistent_label!="x"}})', "Prometheus: all series"),
    q("B3-missing-empty", "selectors", f'count({REQS}{{nonexistent_label=""}})', "Prometheus: all series"),
    q("B4-missing-regex-all", "selectors", f'count({REQS}{{nonexistent_label=~".*"}})', "Prometheus: all series"),
    q("B5-status-neq", "selectors", f'count({ERRS}{{status!="500"}})', "Negative matcher (#15892)"),
    q("B6-status-empty", "selectors", f'count({ERRS}{{status=""}})', "Empty-string matcher (#15892)"),
]

FUNCTIONS = [  # classes of difference listed in openobserve#14924
    q("C1-hist-by-le", "functions", f'histogram_quantile(0.9, sum by (le) (rate({BUCKET}{{path="{P}"}}[5m])))',
      "histogram_quantile grouping"),
    q("C2-hist-unaggregated", "functions",
      f'histogram_quantile(0.9, rate({BUCKET}{{path="{P}",method="GET"}}[5m]))',
      "histogram_quantile without aggregation (label/__name__ handling)"),
    q("C3-label_replace", "functions",
      f'label_replace({RATE_BY_PATH}, "svc", "$1", "path", "/api/(.*)")', "label_replace"),
    q("C4-label_join", "functions",
      f'label_join(sum by (path, method) (rate({COUNT}[5m])), "pm", "-", "path", "method")', "label_join"),
    q("C5-count_values", "functions", f'count_values("v", {GAUGE})', "count_values grouping"),
    q("C6-topk-0", "functions", f"topk(0, {RATE_BY_PATH})", "Invalid k: Prometheus returns empty"),
    q("C7-topk-3", "functions", f"topk(3, {RATE_BY_PATH})", "topk"),
    q("C8-bottomk-3", "functions", f"bottomk(3, {RATE_BY_PATH})", "bottomk"),
    q("C9-quantile-by", "functions", f"quantile by (path) (0.5, rate({COUNT}[5m]))", "quantile aggregation"),
    q("C10-stddev-over-time", "functions", f"stddev_over_time({GAUGE}[10m])", "Variance implementation"),
    q("C11-stdvar-over-time", "functions", f"stdvar_over_time({GAUGE}[10m])", "Variance implementation"),
    q("C12-predict_linear", "functions", f'predict_linear({REQS}{{path="{P}"}}[30m], 3600)', "Regression"),
    q("C13-predict_linear-offset", "functions",
      f'predict_linear({REQS}{{path="{P}"}}[30m] offset 10m, 3600)', "Regression with offset"),
    q("C14-deriv", "functions", f"deriv({GAUGE}[10m])", "Regression"),
    q("C15-absent", "functions", 'absent(codelab_nonexistent{a="b"})', "absent() labels + value"),
    q("C16-absent_over_time", "functions", "absent_over_time(codelab_nonexistent[5m])", "absent_over_time"),
    q("C17-timestamp", "functions", f"timestamp({GAUGE})", "timestamp()"),
    q("C18-sgn", "functions", f"sgn(deriv({GAUGE}[10m]))", "sgn()"),
    q("C19-and-on", "functions",
      f"{RATE_BY_PATH} and on (path) sum by (path) (rate(codelab_api_request_duration_seconds_sum[5m]))",
      "Set operation with on()"),
    q("C20-unless-ignoring", "functions",
      f"sum by (path, method) (rate({REQS}[5m])) unless ignoring (method) {RATE_BY_PATH}",
      "Set operation with ignoring()"),
    q("C21-group_left", "functions",
      f"sum by (path, method) (rate({REQS}[5m])) / on (path) group_left sum by (path) (rate({REQS}[5m]))",
      "group_left matching"),
    q("C22-avg", "functions", f"avg(rate({REQS}[5m]))", "avg"),
    q("C23-rate-plain", "functions", f'rate({REQS}{{path="{P}",method="GET"}}[5m])', "rate() extrapolation"),
    q("C24-increase", "functions", f'increase({REQS}{{path="{P}",method="GET"}}[10m])', "increase() extrapolation"),
    q("C25-histogram_quantile-0.99", "functions",
      f'histogram_quantile(0.99, sum by (le) (rate({BUCKET}[5m])))', "Quantile over all series"),
]

MODIFIERS = [
    q("D1-subquery", "modifiers", f"max_over_time(sum(rate({COUNT}[1m]))[10m:1m])", "Subquery"),
    q("D2-at-end", "modifiers", f"sum(rate({COUNT}[5m] @ end()))", "@ modifier"),
    q("D3-subquery-at", "modifiers", f"max_over_time(sum(rate({COUNT}[1m]))[10m:1m] @ end())",
      "Subquery with @ (rejected by OpenObserve per #14924)"),
    q("D4-offset", "modifiers", f"sum(rate({COUNT}[5m] offset 1h))", "offset"),
]

LOOKBACK = [  # Prometheus uses a 5m lookback delta for instant queries
    q("E1-lookback-3m", "lookback", f"count({REQS})", "Within 5m after last sample: Prometheus returns a value",
      end_offset=180),
    q("E2-lookback-7m", "lookback", f"count({REQS})", "Beyond 5m: Prometheus returns empty", end_offset=420),
]

API_SHAPE = [
    q("F1-string-literal", "api", '"hello"', "Instant string result type"),
    q("F2-scalar", "api", "1 + 1", "Scalar result type"),
    q("F3-range-start-eq-end", "api", RATE_BY_PATH, "start==end: Prometheus returns a matrix",
      kind="range", window=0),
    q("F4-range-zero-step", "api", RATE_BY_PATH, "step=0 must be rejected", kind="range", window=1800, step=0),
    {"id": "F5-labels", "group": "api", "kind": "labels", "promql": "", "why": "/api/v1/labels", "end_offset": 0},
    {"id": "F6-label-values", "group": "api", "kind": "label_values", "promql": "path",
     "why": "/api/v1/label/path/values", "end_offset": 0},
    {"id": "F7-series", "group": "api", "kind": "series", "promql": f'{REQS}{{path="{P}"}}',
     "why": "/api/v1/series", "end_offset": 0},
]

CATALOG = BENCHMARK + RANGE + SELECTORS + FUNCTIONS + MODIFIERS + LOOKBACK + API_SHAPE
