# Queries used in the parity check

Every query in `queries.py`, plus the ad-hoc diagnostics run while investigating. Reference system: Prometheus 3.6.0.

Instant queries are evaluated at the end of data = 2026-11-15T06:00:00Z (backfill start 03:00:00Z + 3 h). Metric names come from the vendor's `fake-webserver` generator.

| Origin | Catalog entries | Rows in the results table |
|---|---:|---:|
| Vendor (`bench/queries.sh`) | 8 | 4 instant + 4 x 3 windows = 16 |
| Added by this harness | 44 | 44 |
| Total | 52 | 60 |

The vendor's four queries are copied from `bench/queries.sh` (path filter `/api/bar` is the repo's default); the range forms reuse them over the repo's 30m/1h/3h windows. The added queries are a generic catalog aimed at known PromQL differences (see openobserve issues #14924 and #15761) and common rule/dashboard functions. They are not taken from real production rules.

## Group: benchmark

### A1-irate
- Origin: vendor
- Evaluated: instant at end of data
- Tests: Vendor query 1

```promql
sum by (path) (irate(codelab_api_request_duration_seconds_count[1m]))
```

### A2-hist-all
- Origin: vendor
- Evaluated: instant at end of data
- Tests: Vendor query 2 (all buckets)

```promql
histogram_quantile(0.9, sum by(le, path) (rate(codelab_api_request_duration_seconds_bucket{}[5m])))
```

### A3-hist-regex
- Origin: vendor
- Evaluated: instant at end of data
- Tests: Vendor query 3

```promql
histogram_quantile(0.9, sum by(le, path) (rate(codelab_api_request_duration_seconds_bucket{path=~"/api/bar"}[5m])))
```

### A4-hist-eq
- Origin: vendor
- Evaluated: instant at end of data
- Tests: Vendor query 4

```promql
histogram_quantile(0.9, sum by(le, path) (rate(codelab_api_request_duration_seconds_bucket{path="/api/bar"}[5m])))
```

## Group: benchmark-range

### R1-irate
- Origin: vendor
- Evaluated: range over the last 30m/1h/3h (three runs), step 15s
- Tests: Vendor query 1
- PromQL: same as A1-irate

### R2-hist-all
- Origin: vendor
- Evaluated: range over the last 30m/1h/3h (three runs), step 15s
- Tests: Vendor query 2 (all buckets)
- PromQL: same as A2-hist-all

### R3-hist-regex
- Origin: vendor
- Evaluated: range over the last 30m/1h/3h (three runs), step 15s
- Tests: Vendor query 3
- PromQL: same as A3-hist-regex

### R4-hist-eq
- Origin: vendor
- Evaluated: range over the last 30m/1h/3h (three runs), step 15s
- Tests: Vendor query 4
- PromQL: same as A4-hist-eq

## Group: selectors

### B1-missing-eq
- Origin: added
- Evaluated: instant at end of data
- Tests: Prometheus: empty. Bug class: matcher on missing label ignored (#15761)

```promql
count(codelab_api_requests_total{nonexistent_label="foo"})
```

### B2-missing-neq
- Origin: added
- Evaluated: instant at end of data
- Tests: Prometheus: all series

```promql
count(codelab_api_requests_total{nonexistent_label!="x"})
```

### B3-missing-empty
- Origin: added
- Evaluated: instant at end of data
- Tests: Prometheus: all series

```promql
count(codelab_api_requests_total{nonexistent_label=""})
```

### B4-missing-regex-all
- Origin: added
- Evaluated: instant at end of data
- Tests: Prometheus: all series

```promql
count(codelab_api_requests_total{nonexistent_label=~".*"})
```

### B5-status-neq
- Origin: added
- Evaluated: instant at end of data
- Tests: Negative matcher (#15892)

```promql
count(codelab_api_request_errors_total{status!="500"})
```

### B6-status-empty
- Origin: added
- Evaluated: instant at end of data
- Tests: Empty-string matcher (#15892)

```promql
count(codelab_api_request_errors_total{status=""})
```

## Group: functions

### C1-hist-by-le
- Origin: added
- Evaluated: instant at end of data
- Tests: histogram_quantile grouping

```promql
histogram_quantile(0.9, sum by (le) (rate(codelab_api_request_duration_seconds_bucket{path="/api/bar"}[5m])))
```

### C2-hist-unaggregated
- Origin: added
- Evaluated: instant at end of data
- Tests: histogram_quantile without aggregation (label/__name__ handling)

```promql
histogram_quantile(0.9, rate(codelab_api_request_duration_seconds_bucket{path="/api/bar",method="GET"}[5m]))
```

### C3-label_replace
- Origin: added
- Evaluated: instant at end of data
- Tests: label_replace

```promql
label_replace(sum by (path) (rate(codelab_api_request_duration_seconds_count[5m])), "svc", "$1", "path", "/api/(.*)")
```

### C4-label_join
- Origin: added
- Evaluated: instant at end of data
- Tests: label_join

```promql
label_join(sum by (path, method) (rate(codelab_api_request_duration_seconds_count[5m])), "pm", "-", "path", "method")
```

### C5-count_values
- Origin: added
- Evaluated: instant at end of data
- Tests: count_values grouping

```promql
count_values("v", codelab_api_http_requests_in_progress)
```

### C6-topk-0
- Origin: added
- Evaluated: instant at end of data
- Tests: Invalid k: Prometheus returns empty

```promql
topk(0, sum by (path) (rate(codelab_api_request_duration_seconds_count[5m])))
```

### C7-topk-3
- Origin: added
- Evaluated: instant at end of data
- Tests: topk

```promql
topk(3, sum by (path) (rate(codelab_api_request_duration_seconds_count[5m])))
```

### C8-bottomk-3
- Origin: added
- Evaluated: instant at end of data
- Tests: bottomk

```promql
bottomk(3, sum by (path) (rate(codelab_api_request_duration_seconds_count[5m])))
```

### C9-quantile-by
- Origin: added
- Evaluated: instant at end of data
- Tests: quantile aggregation

```promql
quantile by (path) (0.5, rate(codelab_api_request_duration_seconds_count[5m]))
```

### C10-stddev-over-time
- Origin: added
- Evaluated: instant at end of data
- Tests: Variance implementation

```promql
stddev_over_time(codelab_api_http_requests_in_progress[10m])
```

### C11-stdvar-over-time
- Origin: added
- Evaluated: instant at end of data
- Tests: Variance implementation

```promql
stdvar_over_time(codelab_api_http_requests_in_progress[10m])
```

### C12-predict_linear
- Origin: added
- Evaluated: instant at end of data
- Tests: Regression

```promql
predict_linear(codelab_api_requests_total{path="/api/bar"}[30m], 3600)
```

### C13-predict_linear-offset
- Origin: added
- Evaluated: instant at end of data
- Tests: Regression with offset

```promql
predict_linear(codelab_api_requests_total{path="/api/bar"}[30m] offset 10m, 3600)
```

### C14-deriv
- Origin: added
- Evaluated: instant at end of data
- Tests: Regression

```promql
deriv(codelab_api_http_requests_in_progress[10m])
```

### C15-absent
- Origin: added
- Evaluated: instant at end of data
- Tests: absent() labels + value

```promql
absent(codelab_nonexistent{a="b"})
```

### C16-absent_over_time
- Origin: added
- Evaluated: instant at end of data
- Tests: absent_over_time

```promql
absent_over_time(codelab_nonexistent[5m])
```

### C17-timestamp
- Origin: added
- Evaluated: instant at end of data
- Tests: timestamp()

```promql
timestamp(codelab_api_http_requests_in_progress)
```

### C18-sgn
- Origin: added
- Evaluated: instant at end of data
- Tests: sgn()

```promql
sgn(deriv(codelab_api_http_requests_in_progress[10m]))
```

### C19-and-on
- Origin: added
- Evaluated: instant at end of data
- Tests: Set operation with on()

```promql
sum by (path) (rate(codelab_api_request_duration_seconds_count[5m])) and on (path) sum by (path) (rate(codelab_api_request_duration_seconds_sum[5m]))
```

### C20-unless-ignoring
- Origin: added
- Evaluated: instant at end of data
- Tests: Set operation with ignoring()

```promql
sum by (path, method) (rate(codelab_api_requests_total[5m])) unless ignoring (method) sum by (path) (rate(codelab_api_request_duration_seconds_count[5m]))
```

### C21-group_left
- Origin: added
- Evaluated: instant at end of data
- Tests: group_left matching

```promql
sum by (path, method) (rate(codelab_api_requests_total[5m])) / on (path) group_left sum by (path) (rate(codelab_api_requests_total[5m]))
```

### C22-avg
- Origin: added
- Evaluated: instant at end of data
- Tests: avg

```promql
avg(rate(codelab_api_requests_total[5m]))
```

### C23-rate-plain
- Origin: added
- Evaluated: instant at end of data
- Tests: rate() extrapolation

```promql
rate(codelab_api_requests_total{path="/api/bar",method="GET"}[5m])
```

### C24-increase
- Origin: added
- Evaluated: instant at end of data
- Tests: increase() extrapolation

```promql
increase(codelab_api_requests_total{path="/api/bar",method="GET"}[10m])
```

### C25-histogram_quantile-0.99
- Origin: added
- Evaluated: instant at end of data
- Tests: Quantile over all series

```promql
histogram_quantile(0.99, sum by (le) (rate(codelab_api_request_duration_seconds_bucket[5m])))
```

## Group: modifiers

### D1-subquery
- Origin: added
- Evaluated: instant at end of data
- Tests: Subquery

```promql
max_over_time(sum(rate(codelab_api_request_duration_seconds_count[1m]))[10m:1m])
```

### D2-at-end
- Origin: added
- Evaluated: instant at end of data
- Tests: @ modifier

```promql
sum(rate(codelab_api_request_duration_seconds_count[5m] @ end()))
```

### D3-subquery-at
- Origin: added
- Evaluated: instant at end of data
- Tests: Subquery with @ (rejected by OpenObserve per #14924)

```promql
max_over_time(sum(rate(codelab_api_request_duration_seconds_count[1m]))[10m:1m] @ end())
```

### D4-offset
- Origin: added
- Evaluated: instant at end of data
- Tests: offset

```promql
sum(rate(codelab_api_request_duration_seconds_count[5m] offset 1h))
```

## Group: lookback

### E1-lookback-3m
- Origin: added
- Evaluated: instant at end of data + 180s
- Tests: Within 5m after last sample: Prometheus returns a value

```promql
count(codelab_api_requests_total)
```

### E2-lookback-7m
- Origin: added
- Evaluated: instant at end of data + 420s
- Tests: Beyond 5m: Prometheus returns empty

```promql
count(codelab_api_requests_total)
```

## Group: api

### F1-string-literal
- Origin: added
- Evaluated: instant at end of data
- Tests: Instant string result type

```promql
"hello"
```

### F2-scalar
- Origin: added
- Evaluated: instant at end of data
- Tests: Scalar result type

```promql
1 + 1
```

### F3-range-start-eq-end
- Origin: added
- Evaluated: range with start == end, step 15s
- Tests: start==end: Prometheus returns a matrix

```promql
sum by (path) (rate(codelab_api_request_duration_seconds_count[5m]))
```

### F4-range-zero-step
- Origin: added
- Evaluated: range, last 30 min, step=0
- Tests: step=0 must be rejected

```promql
sum by (path) (rate(codelab_api_request_duration_seconds_count[5m]))
```

### F5-labels
- Origin: added
- Evaluated: GET /api/v1/labels (last 10 min)
- Tests: /api/v1/labels

### F6-label-values
- Origin: added
- Evaluated: GET /api/v1/label/path/values (last 10 min)
- Tests: /api/v1/label/path/values

```promql
path
```

### F7-series
- Origin: added
- Evaluated: GET /api/v1/series (last 10 min)
- Tests: /api/v1/series

```promql
codelab_api_requests_total{path="/api/bar"}
```

## Ad-hoc diagnostics (not in the catalog)

Run by hand with small scripts against the same data. Numbers are from the 2026-11-17 run.

### Metric and label discovery

```text
/api/v1/label/__name__/values and /api/v1/labels (Prometheus)
```

Found: 6 metric names (codelab_api_* series, buckets, count, sum, errors, in-progress gauge); labels app, instance, job, le, method, namespace, node, path, pod, region, status, version, vnode.

### Readiness probe (parity.py wait_until_ready)

```promql
count(codelab_api_request_duration_seconds_count)  at end - 15s
```

Found: Polled until every system equals Prometheus (6,480). Mimir returned nothing until its blocks were shipped and synced.

### Data-identity check before trusting any comparison

```promql
count(codelab_api_request_duration_seconds_count)
count(codelab_api_request_duration_seconds_bucket)
sum(codelab_api_requests_total)
```

Found: Prometheus and OpenObserve agreed exactly: 6,480 / 168,480 / 22,231,129. Confirms the seeded generator is deterministic and ingestion was complete.

### Mimir ingestion state (not PromQL: GET /metrics)

```text
cortex_ingester_ingested_samples_total, cortex_ingester_memory_series, cortex_ingester_tsdb_compactions_total, cortex_ingester_shipper_uploads_total
```

Found: 137,239,532 samples and 191,190 series ingested; 0 compactions/uploads until the 5-minute idle timeout passed, then 2 and 2.

### Which series does VictoriaMetrics drop? (C2 follow-up)

```promql
histogram_quantile(0.9, rate(codelab_api_request_duration_seconds_bucket{path="/api/bar",method="GET"}[5m]))
```

Found: Prometheus 60 series, VictoriaMetrics 48. All 12 missing series are NaN in Prometheus.

### Find the worst histogram_quantile gap (A2 follow-up)

```promql
histogram_quantile(0.9, sum by(le, path) (rate(codelab_api_request_duration_seconds_bucket{}[5m])))  compared per path
```

Found: Worst: /api/service-18, 29.0 ms (Prometheus) vs 44.5 ms (VictoriaMetrics), 35% apart. Next: /api/service-49 (9%), /api/service-5 (7%).

### Root cause of that gap: same inputs, own quantile code

```promql
sum by (le) (rate(codelab_api_request_duration_seconds_bucket{path="/api/service-18"}[5m]))
histogram_quantile(0.9, <the same expression>)
```

Found: A hand-written quantile over each system's own bucket rates reproduced both answers (0.0290, 0.0445), so histogram_quantile agrees and rate() is the input that differs. Share below le=0.029: 91.1% vs 89.7%.

### Raw-sample check of rate() (first attempt, flawed)

```promql
codelab_api_requests_total{path="/api/bar",method="GET",status="200",region="eu-central-1"}[5m]
rate(<same selector>[5m])
```

Found: The selector matched 6 series, so [0] of each result was not guaranteed to be the same series. Discarded and redone below.

### Raw-sample check of rate() (exact label set)

```promql
codelab_api_requests_total{<all labels of one series>}[6m]
rate(codelab_api_requests_total{<all labels of one series>}[5m])
```

Found: Prometheus 0.674074 = (v[-15s]-v[-285s])/270. VictoriaMetrics 0.659649 = (v[-15s]-v[-300s])/285. Both matched by hand to 1e-9.

### Missing-label matcher on OpenObserve (B1 follow-ups)

```promql
count(codelab_api_requests_total{nonexistent_label="foo"})
count(codelab_api_requests_total)
count(codelab_api_requests_total{status_code="500"})   # typo: real label is "status"
codelab_api_requests_total{nonexistent_label="foo"}   # bare selector
```

Found: Prometheus: 0, 6,480, 0, no series. OpenObserve: 6,480, 6,480, 6,480, 6,480 series. The matcher on a missing label is ignored.

### Where do the 3h-window differences sit? (R4 follow-up)

```promql
histogram_quantile(0.9, sum by(le, path) (rate(codelab_api_request_duration_seconds_bucket{path="/api/bar"}[5m])))  range, end-3h .. end, step 15s
```

Found: OpenObserve differs on 18 of 720 points; all between +15 s and +270 s after the first sample, none missing or extra.
