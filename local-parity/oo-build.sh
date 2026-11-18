#!/usr/bin/env bash
# Build OpenObserve from source (no macOS binary is published).
# Everything is isolated under ./rust and ./openobserve-src; nothing touches ~/.cargo or ~/.rustup.
#   ./oo-build.sh toolchain   # install the pinned nightly via the rust-lang dist server (or a mirror)
#   ./oo-build.sh source      # clone OpenObserve at OO_TAG and stub the UI assets
#   ./oo-build.sh build       # cargo build --release (long; run in the background)
#
# Optional mirrors (leave unset to use static.rust-lang.org and crates.io):
#   RUST_DIST=https://mirror.example/rust-dist  CARGO_INDEX=sparse+https://mirror.example/cargo/index/
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OO_TAG="${OO_TAG:-v1.1.1}"                       # same version the vendor benchmark used
NIGHTLY="nightly-2026-05-20"                     # pinned in OpenObserve's rust-toolchain.toml
RUST_DIST="${RUST_DIST:-https://static.rust-lang.org}"
CARGO_INDEX="${CARGO_INDEX:-}"

export RUSTUP_HOME="${HERE}/rust/rustup"
export CARGO_HOME="${HERE}/rust/cargo"
export RUSTUP_DIST_SERVER="${RUST_DIST}"
export RUSTUP_UPDATE_ROOT="${RUST_DIST}/rustup"
export RUSTUP_TOOLCHAIN="${NIGHTLY}"             # overrides rust-toolchain.toml (skips clippy/rustfmt)
export PATH="${CARGO_HOME}/bin:${HERE}/bin:${PATH}"

toolchain() {
  mkdir -p "${RUSTUP_HOME}" "${CARGO_HOME}"
  curl -q -sSL --fail -o "${HERE}/rust/rustup-init" \
    "${RUST_DIST}/rustup/dist/aarch64-apple-darwin/rustup-init"
  chmod +x "${HERE}/rust/rustup-init"
  RUSTUP_TOOLCHAIN= "${HERE}/rust/rustup-init" -y --no-modify-path --profile minimal --default-toolchain none
  rustup toolchain install "${NIGHTLY}" --profile minimal
  : >"${CARGO_HOME}/config.toml"
  if [[ -n "${CARGO_INDEX}" ]]; then
    cat >>"${CARGO_HOME}/config.toml" <<EOF
[source.crates-io]
replace-with = "mirror"

[source.mirror]
registry = "${CARGO_INDEX}"

EOF
  fi
  cat >>"${CARGO_HOME}/config.toml" <<'EOF'
# Shallow-fetch git dependencies: a full fetch of the tantivy fork is 64 MB and was very slow.
[unstable.gitoxide]
fetch = true

[unstable.git]
shallow_deps = true
EOF
  # protoc is needed by prost-build.
  if [[ ! -x "${HERE}/bin/protoc" ]]; then
    curl -q -sSL --fail -o "${HERE}/rust/protoc.zip" \
      "https://github.com/protocolbuffers/protobuf/releases/download/v25.3/protoc-25.3-osx-aarch_64.zip"
    (cd "${HERE}/rust" && unzip -oq protoc.zip -d protoc-dist && cp protoc-dist/bin/protoc "${HERE}/bin/protoc")
  fi
  rustc --version && cargo --version && protoc --version
}

source_tree() {
  if [[ ! -d "${HERE}/openobserve-src/.git" ]]; then
    git clone --depth 1 --branch "${OO_TAG}" https://github.com/openobserve/openobserve.git "${HERE}/openobserve-src"
  fi
  # The server embeds web/dist at compile time. PromQL needs no UI, so a stub is enough.
  mkdir -p "${HERE}/openobserve-src/web/dist"
  [[ -f "${HERE}/openobserve-src/web/dist/index.html" ]] || echo '<html><body>stub</body></html>' \
    >"${HERE}/openobserve-src/web/dist/index.html"
  echo "source ready at ${OO_TAG}"
}

build() {
  export PROTOC="${HERE}/bin/protoc"
  export PROTOC_INCLUDE="${HERE}/rust/protoc-dist/include"   # google/protobuf/*.proto well-known types
  # Faster than the project's release profile; correctness is unaffected.
  export CARGO_PROFILE_RELEASE_LTO=off CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 \
         CARGO_PROFILE_RELEASE_DEBUG=0 CARGO_PROFILE_RELEASE_OPT_LEVEL=2
  cd "${HERE}/openobserve-src"
  cargo build --release --bin openobserve
  cp target/release/openobserve "${HERE}/bin/openobserve"
  "${HERE}/bin/openobserve" --version || true
}

case "${1:-}" in
  toolchain) toolchain ;;
  source) source_tree ;;
  build) build ;;
  *) echo "usage: $0 toolchain|source|build" >&2; exit 1 ;;
esac
