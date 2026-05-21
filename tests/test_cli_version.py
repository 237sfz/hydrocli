from __future__ import annotations

from typer.testing import CliRunner

from hydro_cli import __version__
from hydro_cli.cli import app


def test_version_option() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
