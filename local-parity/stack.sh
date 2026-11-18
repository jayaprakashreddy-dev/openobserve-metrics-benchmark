#!/usr/bin/env bash
# Start / stop / inspect the local benchmark stack (native binaries, no containers).
#   ./stack.sh start|start-o2|stop|status|wipe
# Ports: prometheus 9090 | mimir 9009 | victoriametrics 8428 | openobserve 5080 (optional)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="${HERE}/bin"
DATA_DIR="${HERE}/data"
LOGS="${HERE}/logs"
CONF="${HERE}/conf"
PIDS="${DATA_DIR}/pids"
mkdir -p "${DATA_DIR}" "${LOGS}" "${PIDS}"

# Mimir and Prometheus open a lot of files.
ulimit -n 65536 2>/dev/null || true

start_one() { # name, command...
  local name="$1"; shift
  if [[ -f "${PIDS}/${name}.pid" ]] && kill -0 "$(cat "${PIDS}/${name}.pid")" 2>/dev/null; then
    echo "${name}: already running (pid $(cat "${PIDS}/${name}.pid"))"
    return
  fi
  nohup "$@" >"${LOGS}/${name}.log" 2>&1 &
  echo $! >"${PIDS}/${name}.pid"
  echo "${name}: started (pid $!)"
}

start() {
  mkdir -p "${DATA_DIR}/prometheus" "${DATA_DIR}/vm" "${DATA_DIR}/mimir"
  sed "s#\${DATA_DIR}#${DATA_DIR}#g" "${CONF}/mimir.yaml" >"${DATA_DIR}/mimir.rendered.yaml"

  start_one prometheus "${BIN}/prometheus" \
    --config.file="${CONF}/prometheus.yml" \
    --storage.tsdb.path="${DATA_DIR}/prometheus" \
    --web.listen-address=:9090 \
    --web.enable-lifecycle --web.enable-remote-write-receiver \
    --query.max-samples=1000000000 --query.timeout=600s

  start_one mimir "${BIN}/mimir" --config.file="${DATA_DIR}/mimir.rendered.yaml"

  start_one vm "${BIN}/victoria-metrics-prod" \
    -httpListenAddr=:8428 -storageDataPath="${DATA_DIR}/vm" \
    -search.disableCache -search.logSlowQueryDuration=2s \
    -search.maxSamplesPerQuery=2147000000 -search.maxQueryDuration=600s \
    -search.maxUniqueTimeseries=5000000
}

# Optional: only works once oo-build.sh has produced bin/openobserve.
# Settings mirror openobserve-metrics-benchmark/deploy/openobserve-parquet/values.yaml.
start_o2() {
  [[ -x "${BIN}/openobserve" ]] || { echo "bin/openobserve missing; run ./oo-build.sh build first" >&2; exit 1; }
  mkdir -p "${DATA_DIR}/o2"
  start_one o2 env \
    ZO_ROOT_USER_EMAIL=root@example.com ZO_ROOT_USER_PASSWORD='Complexpass#123' \
    ZO_HTTP_PORT=5080 ZO_DATA_DIR="${DATA_DIR}/o2/" \
    ZO_PROMETHEUS_ENABLED=true ZO_PROMETHEUS_HA_CLUSTER=prometheus ZO_PROMETHEUS_HA_REPLICA=prometheus_replica \
    ZO_METRICS_MAX_SERIES_RESPONSE=40000 ZO_METRICS_MAX_POINTS_PER_SERIES=10000000 \
    ZO_RESULT_CACHE_ENABLED=false ZO_METRICS_BLOCKS_CACHE_MAX_SIZE=2048 \
    ZO_COMPACT_DELETE_FILES_DELAY_MINUTES=10 ZO_MAX_FILE_RETENTION_TIME=60 \
    ZO_COMPACT_ENABLED="${ZO_COMPACT_ENABLED:-true}" \
    RUST_LOG='info,config::axum=warn,tantivy=warn' \
    "${BIN}/openobserve"
}

stop() {
  for f in "${PIDS}"/*.pid; do
    [[ -e "${f}" ]] || continue
    local name pid
    name="$(basename "${f}" .pid)"; pid="$(cat "${f}")"
    if kill -0 "${pid}" 2>/dev/null; then kill "${pid}" && echo "${name}: stopped (pid ${pid})"; fi
    rm -f "${f}"
  done
}

status() {
  check() { # name url
    if curl -q --noproxy '*' -sS -o /dev/null --max-time 3 "$2" 2>/dev/null; then echo "${1}: up   ($2)"; else echo "${1}: DOWN ($2)"; fi
  }
  check prometheus http://localhost:9090/-/ready
  check mimir      http://localhost:9009/ready
  check vm         http://localhost:8428/health
  [[ -f "${PIDS}/o2.pid" ]] && check o2 http://localhost:5080/healthz || true
}

wipe() { # explicit and narrow: only our own data subdirectories
  stop
  for d in prometheus vm mimir o2; do rm -r "${DATA_DIR:?}/${d}" 2>/dev/null || true; done
  echo "wiped prometheus/vm/mimir data"
}

case "${1:-}" in
  start) start; sleep 8; status ;;
  start-o2) start_o2; sleep 10; status ;;
  stop) stop ;;
  status) status ;;
  wipe) wipe ;;
  *) echo "usage: $0 start|start-o2|stop|status|wipe" >&2; exit 1 ;;
esac
