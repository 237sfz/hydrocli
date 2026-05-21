#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_build-env.sh
source "$SCRIPT_DIR/_build-env.sh"

cd "$ROOT"

platform="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
target_name="${HYDRO_PYINSTALLER_NAME:-hydro-$platform-$arch}"

ENTRY_DIR="$ROOT/.build/pyinstaller"
ENTRY_FILE="$ENTRY_DIR/hydro_entry.py"
PYINSTALLER_VENV="${PYINSTALLER_VENV:-$ROOT/.build/pyinstaller-venv}"
mkdir -p "$ENTRY_DIR"

cat > "$ENTRY_FILE" <<'PY'
from hydro_cli.cli import main

if __name__ == "__main__":
    main()
PY

select_python() {
  if [ -n "${PYINSTALLER_PYTHON:-}" ]; then
    printf '%s\n' "$PYINSTALLER_PYTHON"
    return
  fi

  if [ "$platform" = "linux" ] && [ "${HYDRO_PYINSTALLER_USE_SYSTEM_PYTHON:-0}" != "1" ]; then
    if ! command -v uv >/dev/null 2>&1; then
      echo "error: uv is required for the default Linux PyInstaller build." >&2
      echo "Install uv, set PYINSTALLER_PYTHON=/path/to/python, or set HYDRO_PYINSTALLER_USE_SYSTEM_PYTHON=1." >&2
      exit 1
    fi

    local python_dir="${HYDRO_STANDALONE_PYTHON_DIR:-$ROOT/.build/uv-python}"
    local python_version="${HYDRO_STANDALONE_PYTHON_VERSION:-3.11}"
    mkdir -p "$python_dir"

    if ! find "$python_dir" -path "*/bin/python3.11" -type f -perm -111 | grep -q .; then
      uv python install "$python_version" --install-dir "$python_dir" --no-bin
    fi

    find "$python_dir" -path "*/bin/python3.11" -type f -perm -111 | sort -V | tail -n 1
    return
  fi

  command -v python3
}

build_python="$(select_python)"
if [ -z "$build_python" ] || [ ! -x "$build_python" ]; then
  echo "error: selected build Python is not executable: $build_python" >&2
  exit 1
fi

rm -rf "$PYINSTALLER_VENV"
"$build_python" -m venv "$PYINSTALLER_VENV"
PYINSTALLER_ENV_PYTHON="$PYINSTALLER_VENV/bin/python"

"$PYINSTALLER_ENV_PYTHON" -m pip install --upgrade pip
"$PYINSTALLER_ENV_PYTHON" -m pip install --upgrade pyinstaller "$ROOT"

"$PYINSTALLER_ENV_PYTHON" -m PyInstaller \
  --clean \
  --onefile \
  --collect-submodules shellingham \
  --name "$target_name" \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/.build/pyinstaller/work" \
  --specpath "$ROOT/.build/pyinstaller" \
  "$ENTRY_FILE"

echo
echo "Built standalone executable:"
ls -lh "$ROOT/dist/$target_name"
echo "Build Python: $build_python"
if [ "$platform" = "linux" ]; then
  echo "Host glibc: $(ldd --version | sed -n '1s/.* //p')"
  libpython="$(find "$(dirname "$(dirname "$build_python")")" -name 'libpython*.so*' -type f | sort -V | tail -n 1 || true)"
  if [ -n "$libpython" ] && command -v strings >/dev/null 2>&1; then
    max_glibc="$(strings "$libpython" | grep -Eo 'GLIBC_[0-9]+\.[0-9]+' | sort -Vu | tail -n 1 || true)"
    if [ -n "$max_glibc" ]; then
      echo "Build Python libpython max glibc symbol: $max_glibc"
    fi
  fi
  echo "For best Linux compatibility, keep using the default uv-managed Python or build on the oldest target system."
fi
