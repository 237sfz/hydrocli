#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/.build}"
BUILD_VENV="${BUILD_VENV:-$BUILD_DIR/venv}"
BUILD_PYTHON="$BUILD_VENV/bin/python"

ensure_build_venv() {
  mkdir -p "$BUILD_DIR"
  if [ ! -x "$BUILD_PYTHON" ]; then
    python3 -m venv "$BUILD_VENV"
  fi
}

install_build_tools() {
  ensure_build_venv
  "$BUILD_PYTHON" -m pip install --upgrade pip
  "$BUILD_PYTHON" -m pip install --upgrade "$@"
}
