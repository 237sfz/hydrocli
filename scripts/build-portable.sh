#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_build-env.sh
source "$SCRIPT_DIR/_build-env.sh"

cd "$ROOT"

if [ ! -x "$ROOT/dist/hydro.pex" ]; then
  "$ROOT/scripts/build-pex.sh"
fi

platform="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
bundle_name="hydro-cli-portable-$platform"
staging_root="$ROOT/.build/portable"
bundle_dir="$staging_root/$bundle_name"

rm -rf "$bundle_dir"
mkdir -p "$bundle_dir/bin" "$bundle_dir/lib" "$bundle_dir/config" "$bundle_dir/workspace" "$ROOT/dist"

cp "$ROOT/dist/hydro.pex" "$bundle_dir/lib/hydro.pex"

cat > "$bundle_dir/bin/hydro" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HYDRO_CLI_CONFIG_DIR="${HYDRO_CLI_CONFIG_DIR:-$ROOT/config}"
exec python3 "$ROOT/lib/hydro.pex" "$@"
SH
chmod +x "$bundle_dir/bin/hydro"

cat > "$bundle_dir/README.txt" <<'TXT'
hydro-cli portable bundle

Run:
  ./bin/hydro --help

Requirements:
  Python 3.11 or newer available as python3.

Config:
  This launcher stores config and login cookies in ./config by setting
  HYDRO_CLI_CONFIG_DIR when that variable is not already set.

Workspace:
  The ./workspace directory is provided for pulled problems and local solutions.
  The launcher does not change your current working directory.
TXT

tarball="$ROOT/dist/$bundle_name.tar.gz"
rm -f "$tarball"
tar -C "$staging_root" -czf "$tarball" "$bundle_name"

echo
echo "Built portable bundle:"
ls -lh "$tarball"
