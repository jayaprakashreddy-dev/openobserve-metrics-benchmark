# Local PromQL parity + benchmark harness

Local-only (nothing touches stage/prod). Native macOS arm64 binaries, no containers.
Goal: check whether candidate TSDBs return the **same PromQL results as Prometheus**, before caring about latency.

## Layout

| Path | What |
|---|---|
| `stack.sh` | `start` / `start-o2` / `stop` / `status` / `wipe` for Prometheus :9090, Mimir :9009, VictoriaMetrics :8428, OpenObserve :5080 |
| `conf/` | Prometheus + Mimir configs, copied from the vendor benchmark's `deploy/` manifests |
| `queries.py` | Query catalog: vendor's 4 queries + selector/function/modifier/lookback/API edge cases |
| `parity.py` | Runs the catalog on every system, diffs against Prometheus (series set, labels, values, result type) |
| `oo-build.sh` | Builds OpenObserve v1.1.1 from source (no macOS binary is published) |
| `results/` | `parity-<ts>.md` (table) and `.json` (with diff examples) |
| `report.py`, `observations.py` | `python3 report.py` builds `results/report.html`, a self-contained page (content lives in `observations.py`) |
| `QUERIES.md`, `queries_doc.py` | Every query the harness runs plus the ad-hoc diagnostics; regenerate with `python3 queries_doc.py` |
| `bin/ data/ logs/ rust/ openobserve-src/` | git-ignored |

## Prerequisites (macOS arm64; swap the asset names for other platforms)

Run everything from this directory. Binaries go in `bin/` (git-ignored):

```bash
mkdir -p bin && cd bin
curl -sSL https://github.com/prometheus/prometheus/releases/download/v3.6.0/prometheus-3.6.0.darwin-arm64.tar.gz | tar xz --strip-components=1 prometheus-3.6.0.darwin-arm64/prometheus
curl -sSL https://github.com/VictoriaMetrics/VictoriaMetrics/releases/download/v1.154.0/victoria-metrics-darwin-arm64-v1.154.0.tar.gz | tar xz
curl -sSL -o mimir https://github.com/grafana/mimir/releases/download/mimir-3.2.2/mimir-darwin-arm64 && chmod +x mimir
git clone https://github.com/openobserve/fake-webserver ../fake-webserver && (cd ../fake-webserver && go build -o ../bin/fake-webserver .)
cd ..
./oo-build.sh toolchain && ./oo-build.sh source && ./oo-build.sh build   # OpenObserve has no macOS binary; ~10+ min
```

`oo-build.sh` installs Rust into `./rust` (not `~/.cargo`). Behind a corporate mirror, set `RUST_DIST` and `CARGO_INDEX` (see the script header).

## Run it

```bash
./stack.sh start
# identical data into all targets (deterministic, seed=1). Start must be < 31 days old (VictoriaMetrics retention)
# and > 13h old (so Mimir answers from store-gateway like the vendor setup).
./bin/fake-webserver -num-nodes=2 -node-name=fake-webserver \
  -backfill-start=2026-11-15T03:00:00Z -backfill-step=15s -backfill-hours=3 -backfill-seed=1 \
  -backfill-labels=job=fake-webserver,instance=localhost:8080,app=fake-webserver,namespace=local,pod=fake-1,node=laptop \
  -remote-write=http://localhost:9090/api/v1/write \
  -remote-write=http://localhost:9009/api/v1/push \
  -remote-write=http://localhost:8428/api/v1/write
python3 -u parity.py --wait-ready 25 --systems prometheus,mimir,vm   # add ,o2 once OpenObserve is up
```

`--wait-ready` matters: Mimir only ships blocks ~5 min after the last write (`head_compaction_idle_timeout`) and
answers nothing for old data until the store-gateway syncs them.

## Setup actually used (differs from the vendor's)

| | Vendor | This run |
|---|---|---|
| Hardware | dedicated k8s nodes, 12 CPU / 24 GB per system | one Mac (18 cores, 48 GB), all systems at once |
| Data | ~1.34M series, ~7h | 191,190 series (2 nodes), 3h, 15s step, **137.2M samples per target, 0 retries** |
| Versions | Prometheus 3.6.0, VM 1.154.0, Mimir 3.2.2, OpenObserve v1.1.1 | same (OpenObserve built from source) |

Latencies in the JSON are informational only: all systems share one laptop. This is a correctness run.

## Results: 60 queries, Prometheus = reference (run 2026-11-17, 4 systems)

| System | PASS | DIFF | ERR | Same error as reference |
|---|---:|---:|---:|---:|
| Mimir 3.2.2 | 59 | 0 | 0 | 1 |
| OpenObserve v1.1.1 (built from source) | 50 | 7 | 3 | 0 |
| VictoriaMetrics 1.154.0 | 25 | 34 | 0 | 1 |

OpenObserve data check before the run: series counts (6,480 `_count`, 168,480 buckets) and `sum(requests_total)` (22,231,129)
match Prometheus exactly, so the same deterministic dataset was ingested in full (visible ~2.5 min after the write finished).

Mimir embeds the Prometheus engine, so 59/59 is the expected outcome and confirms the harness has no false positives.

### OpenObserve: what differs (and what does not)

Passes all four vendor queries (instant and 30m/1h range), `rate`/`irate`/`increase`, `histogram_quantile`, `label_replace`, `topk`,
`group_left`, subqueries, `offset`, `@ end()`, and the 5m lookback at +3m/+7m. Its `rate()` matches Prometheus' extrapolation
(unlike VictoriaMetrics), so its quantiles agree too.

1. **Matcher on a missing label is ignored (B1) - verified.** `count(requests_total{nonexistent_label="foo"})`: Prometheus 0, OpenObserve 6,480.
   A typo'd label (`{status_code="500"}`) also returns every series. A rule with a mistyped label would evaluate over everything instead
   of nothing. This is the bug class in openobserve#15761, reproduced on v1.1.1. The `!=`/`=""`/`=~".*"` variants (B2-B4) pass.
2. **3h range queries on `histogram_quantile` (R2-R4 at 3h) - verified for R4.** All 18 differing points are in the first 270s of data,
   where the 5m `rate` window is not full yet (up to 35% apart there). Interior points match. The 30m/1h windows pass because they start
   after the data begins. R2's 1,004 diffs over 54 series is consistent with the same edge effect (~18.6/series) but was not checked per point.
3. **`predict_linear(... offset 10m ...)` (C13):** 119/120 series differ by up to 5.9%; without `offset` (C12) it passes. Cause not isolated.
4. **Not implemented / different API behaviour:** subquery with `@` errors (D3, "Subquery: @ modifier is not supported"); a string literal
   errors (F1, "invalid result type: string"); `start == end` range returns a vector instead of a matrix (F3); `step=0` is accepted where
   Prometheus rejects it (F4); `/label/<name>/values` without `match[]` is rejected (F6).

Caveats: 191k series, 3h, one node, all systems on one laptop. This says nothing about behaviour at production scale, and latency was not measured.

## Results: VictoriaMetrics vs Prometheus

### Why VictoriaMetrics differs (each cause verified, not assumed)

1. **`rate()`/`increase()` use a different baseline.** On one exact series, with 15s samples and `[5m]`:
   Prometheus = `(v[-15s] - v[-285s]) / 270s` = 0.674074; VictoriaMetrics = `(v[-15s] - v[-300s]) / 285s` = 0.659649.
   Both match to 1e-9. VictoriaMetrics takes the sample at the window start as baseline; Prometheus only uses samples inside the window.
   That is a ~1-2% shift on every `rate()`, which is why `avg`, `label_replace`, `group_left`, `topk`, `D1`-`D4` all differ slightly.
2. **Small `rate()` differences get amplified by `histogram_quantile`.** Worst vendor query (A2, all paths, p90): `/api/service-18`
   = 29.0 ms (Prometheus) vs 44.5 ms (VictoriaMetrics), **35% apart**. A hand-written quantile over each system's *own* bucket rates
   reproduces both engine answers (0.0290 / 0.0445), so `histogram_quantile` itself agrees. The cumulative share of requests under
   `le=0.029` is 91.1% in Prometheus but 89.7% in VictoriaMetrics, straddling the 90% rank, and the next bucket (`le=0.044`) is nearly
   empty (0.015 req/s), so the answer jumps from 29 ms to 44 ms.
   Same effect in range form: up to 55% on `R2`-`R4`. Near a latency SLO threshold this can flip an alert.
3. **NaN results are dropped.** `C2`: Prometheus returns 60 series, VictoriaMetrics 48; all 12 missing are `NaN` in Prometheus
   (quantile of an idle histogram).
4. **`__name__` is kept by some functions.** `predict_linear` (C12/C13): every series differs because VictoriaMetrics keeps `__name__`.
   Matters for rule output labels and alert grouping.
5. **Literals return a vector.** `"hello"` and `1 + 1` come back as `vector`, not `string`/`scalar` (F1/F2); a `start == end` range query
   returns a different shape (F3).

What passed on VictoriaMetrics: `irate`, all six missing/empty-label matcher cases (B1-B6), `count_values`, `topk(0)`, `stddev/stdvar_over_time`,
`deriv`, `absent`, `absent_over_time`, `timestamp`, `sgn`, `unless ignoring`, lookback at +3m and +7m, labels/label-values/series endpoints.

### Not yet tested
- Native histograms, late/out-of-order samples, `@` with fresh data, rule-evaluation-style queries at production scale, any latency/resource comparison.
- Whether `predict_linear ... offset` (C13) is an OpenObserve bug or a legitimate semantic choice.
- VictoriaMetrics ran with the vendor's query limits and otherwise default settings; whether any setting narrows the gaps above is untested.
