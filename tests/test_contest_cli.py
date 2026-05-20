from __future__ import annotations

from pathlib import Path

import pytest

from hydro_cli.cli import _current_contest_id, _resolve_contest_submit_args
from hydro_cli.config import Config
from hydro_cli.errors import HydroCliError


def test_current_contest_prefers_explicit_id() -> None:
    config = Config(current_contest_id="saved")

    assert _current_contest_id(config, "explicit") == "explicit"


def test_current_contest_uses_saved_id() -> None:
    config = Config(current_contest_id="saved")

    assert _current_contest_id(config, None) == "saved"


def test_current_contest_requires_id_when_missing() -> None:
    with pytest.raises(HydroCliError, match="contest id is required"):
        _current_contest_id(Config(), None)


def test_resolve_contest_submit_args_uses_current_contest() -> None:
    config = Config(current_contest_id="abc123")

    cid, problem, source = _resolve_contest_submit_args(config, "A", "main.cpp", None)

    assert cid == "abc123"
    assert problem == "A"
    assert source == Path("main.cpp")


def test_resolve_contest_submit_args_keeps_legacy_form() -> None:
    config = Config(current_contest_id="saved")

    cid, problem, source = _resolve_contest_submit_args(config, "abc123", "A", Path("main.cpp"))

    assert cid == "abc123"
    assert problem == "A"
    assert source == Path("main.cpp")
