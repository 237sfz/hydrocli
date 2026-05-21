#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_build-env.sh
source "$SCRIPT_DIR/_build-env.sh"

cd "$ROOT"
install_build_tools pex

mkdir -p "$ROOT/dist"
rm -f "$ROOT/dist/hydro.pex"

"$BUILD_PYTHON" -m pex "$ROOT" \
  --console-script hydro \
  --output-file "$ROOT/dist/hydro.pex" \
  --python-shebang "/usr/bin/env python3"

chmod +x "$ROOT/dist/hydro.pex"

echo
echo "Built portable PEX:"
ls -lh "$ROOT/dist/hydro.pex"
