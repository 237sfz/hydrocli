#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_build-env.sh
source "$SCRIPT_DIR/_build-env.sh"

cd "$ROOT"
install_build_tools build

mkdir -p "$ROOT/dist"
rm -rf "$ROOT/build"
rm -f "$ROOT"/dist/hydro_cli-*.whl "$ROOT"/dist/hydro_cli-*.tar.gz

"$BUILD_PYTHON" -m build "$ROOT" --outdir "$ROOT/dist"

echo
echo "Built Python package artifacts:"
ls -1 "$ROOT"/dist/hydro_cli-*.whl "$ROOT"/dist/hydro_cli-*.tar.gz
