# Distribution

This repository does not need to be on GitHub before building local artifacts.
The scripts in `scripts/` create releasable files under `dist/`.

## Artifact Types

| Artifact | Build command | Target user | Runtime requirement |
| --- | --- | --- | --- |
| Wheel and sdist | `./scripts/build-dist.sh` | Python users, `pipx`, `uv tool` | Python 3.11+ |
| PEX | `./scripts/build-pex.sh` | Users who want one file | Python 3.11+ |
| PyInstaller binary | `./scripts/build-pyinstaller.sh` | Users without Python tooling | Matching OS/CPU and compatible glibc |
| Portable tarball | `./scripts/build-portable.sh` | Users who want to carry config with the app | Python 3.11+ |

The build scripts use `.build/venv` for packaging tools. They do not install
`build`, `pex`, or `pyinstaller` into the project development virtualenv.

On Linux, `build-pyinstaller.sh` defaults to a `uv`-managed Python 3.11 for the
PyInstaller build. This avoids bundling the host system's `libpython`, which can
make a binary built on a new distribution fail on an older one.

## Local Release Checklist

1. Verify the code:

   ```bash
   . .venv/bin/activate
   pytest
   ruff check .
   hydro --version
   ```

2. Build the Python package:

   ```bash
   ./scripts/build-dist.sh
   ```

3. Build the single-file Python app:

   ```bash
   ./scripts/build-pex.sh
   ./dist/hydro.pex --version
   ```

4. Build the portable bundle:

   ```bash
   ./scripts/build-portable.sh
   ```

5. Optional: build a standalone executable on each target platform:

   ```bash
   ./scripts/build-pyinstaller.sh
   ./dist/hydro-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m) --version
   ```

   On Linux, inspect the glibc note printed by the script. If the binary must
   support an older distribution, test it there before publishing.

6. Inspect the generated files:

   ```bash
   ls -lh dist/
   ```

## Versioning

The package version is defined once in `src/hydro_cli/__init__.py` and read by
Hatch during packaging. Update `__version__` before creating a new release.

The CLI exposes the same version:

```bash
hydro --version
```

## Linux PyInstaller Compatibility

There is no fully universal PyInstaller binary for all Linux distributions. A
PyInstaller executable is still a native Linux executable, and glibc symbol
versions matter. A binary built with a Python shared library requiring
`GLIBC_2.38` will not run on Ubuntu 20.04, which ships an older glibc.

The project script uses this policy:

```bash
./scripts/build-pyinstaller.sh
```

- On Linux, default to a `uv`-managed Python 3.11 installed under
  `.build/uv-python`.
- Build PyInstaller in `.build/pyinstaller-venv`.
- Print the host glibc version and the highest glibc symbol required by the
  selected `libpython`.

To force a specific Python interpreter:

```bash
PYINSTALLER_PYTHON=/path/to/python3.11 ./scripts/build-pyinstaller.sh
```

To deliberately use the system Python:

```bash
HYDRO_PYINSTALLER_USE_SYSTEM_PYTHON=1 ./scripts/build-pyinstaller.sh
```

For maximum compatibility, build on the oldest Linux distribution you need to
support, or use the default `uv`-managed Python and still test the result on the
oldest target distribution.

## Portable Config

Normal installs store config in the platform user config directory, or in
`HYDRO_CLI_CONFIG_DIR` when that environment variable is set.

Portable bundles use this layout:

```text
hydro-cli-portable-<platform>/
  bin/
    hydro
  lib/
    hydro.pex
  config/
  workspace/
```

`bin/hydro` sets `HYDRO_CLI_CONFIG_DIR` to the bundle's `config/` directory
unless the user already set the variable. After login, that directory can
contain session cookies and should not be shared publicly.

## GitHub Later

When the project is pushed to GitHub, the same commands can be moved into a
release workflow:

1. Run tests and lint.
2. Build wheel and sdist.
3. Build PEX.
4. Build platform binaries on Linux, macOS, and Windows runners.
5. Upload all files from `dist/` to the release.
