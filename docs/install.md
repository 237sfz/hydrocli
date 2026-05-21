# Installation

This project can be installed as a normal Python CLI package, run as a PEX
single-file app, or unpacked as a portable bundle.

## From This Source Tree

For development or personal long-term use, install the checked-out source tree
with `pipx`:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install -e /path/to/hydrocli
hydro --help
```

The editable install keeps the command available across new shells while using
the source code in this repository.

If you prefer `uv`:

```bash
uv tool install --editable /path/to/hydrocli
hydro --help
```

## From A Wheel

Build the wheel and source distribution:

```bash
./scripts/build-dist.sh
```

Install the wheel with `pipx`:

```bash
pipx install dist/hydro_cli-0.1.0-py3-none-any.whl
hydro --help
```

Or with `uv`:

```bash
uv tool install dist/hydro_cli-0.1.0-py3-none-any.whl
hydro --help
```

This is the preferred install path for users who already have Python 3.11 or
newer.

## PEX Single File

Build a PEX file:

```bash
./scripts/build-pex.sh
```

Run it on any machine with Python 3.11 or newer:

```bash
./dist/hydro.pex --help
```

The PEX contains the Python package and its dependencies, so the target machine
does not need a virtual environment or a copy of this repository.

## Standalone Executable

Build a platform-specific executable:

```bash
./scripts/build-pyinstaller.sh
```

On Linux, this script defaults to a `uv`-managed Python 3.11 instead of the
system Python. That avoids bundling the current system's `libpython` when the
build machine is newer than the target machine.

Run the generated file:

```bash
./dist/hydro-linux-x86_64 --help
```

PyInstaller output is platform-specific. Build Linux, macOS, and Windows
executables on their matching target platforms.

Linux PyInstaller output is also glibc-sensitive. A binary built with a newer
glibc can fail on older distributions with an error such as `GLIBC_2.38 not
found`. For best compatibility, use the default `uv`-managed Python path in
`build-pyinstaller.sh`, or build directly on the oldest Linux distribution you
need to support.

## Portable Bundle

Build a portable directory tarball:

```bash
./scripts/build-portable.sh
```

Unpack it and run:

```bash
tar -xzf dist/hydro-cli-portable-linux-x86_64.tar.gz
cd hydro-cli-portable-linux-x86_64
./bin/hydro --help
```

The portable launcher stores config under the bundle's `config/` directory by
setting `HYDRO_CLI_CONFIG_DIR`. This makes the bundle easy to move between
directories or machines.

The config file can contain login cookies. Treat the portable bundle as private
after logging in.
