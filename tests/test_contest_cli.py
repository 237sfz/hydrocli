from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from hydro_cli import cli as cli_module
from hydro_cli.cli import _current_contest_id, _resolve_contest_submit_args
from hydro_cli.cli import app
from hydro_cli.config import Config, ConfigStore
from hydro_cli.contest import ContestProblem, ContestSubmission, ContestSubmitTarget
from hydro_cli.errors import HydroCliError
from hydro_cli.problem import Problem


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


class FakeClient:
    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class RecordingContestService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def problem(self, cid: str, problem_arg: str) -> Problem:
        self.calls.append(("problem", cid, problem_arg))
        return _fake_problem("16")

    def pull(self, cid: str, problem_arg: str, output_dir: Path) -> Problem:
        self.calls.append(("pull", cid, problem_arg, output_dir))
        return _fake_problem("A")

    def pull_all(self, cid: str, output_dir: Path) -> list[Problem]:
        self.calls.append(("pull_all", cid, output_dir))
        return [_fake_problem("A"), _fake_problem("B")]

    def submit(
        self,
        cid: str,
        problem_arg: str,
        source_path: Path,
        lang: str = "",
    ) -> ContestSubmission:
        self.calls.append(("submit", cid, problem_arg, source_path, lang))
        contest_problem = ContestProblem(
            alias=problem_arg,
            problem_id="16",
            title="Matrix",
            status="",
            score="",
            last_submit_at="",
            url="http://localhost:8888/p/16?tid=abc123",
            submit_url="http://localhost:8888/p/16/submit?tid=abc123",
        )
        target = ContestSubmitTarget(
            contest_id=cid,
            problem=contest_problem,
            submit_path="/p/16/submit?tid=abc123",
            submit_url="http://localhost:8888/p/16/submit?tid=abc123",
            record_detail_path="",
            languages=[],
        )
        return ContestSubmission(record_id="r1", target=target)


def _fake_problem(problem_id: str) -> Problem:
    return Problem(
        problem_id=problem_id,
        title="Matrix",
        url="http://localhost:8888/p/16?tid=abc123",
        statement="Statement\n",
        tags=[],
        stats={},
        reference=None,
        subType="",
        config={},
        limits={
            "time_ms": {"display": "1000 ms"},
            "memory_mb": {"display": "256 MB"},
        },
        attachments=[],
    )


def _install_fake_contest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service: RecordingContestService,
) -> None:
    monkeypatch.setenv("HYDRO_CLI_CONFIG_DIR", str(tmp_path / "config"))
    store = ConfigStore()
    store.save(Config(base_url="http://localhost:8888", current_contest_id="abc123"))
    monkeypatch.setattr(cli_module, "_load_client", lambda: (store, FakeClient()))
    monkeypatch.setattr(cli_module, "ContestService", lambda _client: service)


def test_cli_contest_problem_uses_current_contest(monkeypatch, tmp_path) -> None:
    service = RecordingContestService()
    _install_fake_contest(monkeypatch, tmp_path, service)

    result = CliRunner().invoke(app, ["contest", "problem", "A", "--raw"])

    assert result.exit_code == 0
    assert service.calls == [("problem", "abc123", "A")]
    assert "# 16. Matrix" in result.stdout


def test_cli_contest_pull_uses_current_contest(monkeypatch, tmp_path) -> None:
    service = RecordingContestService()
    output_dir = tmp_path / "contests"
    _install_fake_contest(monkeypatch, tmp_path, service)

    result = CliRunner().invoke(app, ["contest", "pull", "A", "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    assert service.calls == [("pull", "abc123", "A", output_dir)]


def test_cli_contest_pull_all_uses_current_contest(monkeypatch, tmp_path) -> None:
    service = RecordingContestService()
    output_dir = tmp_path / "contests"
    _install_fake_contest(monkeypatch, tmp_path, service)

    result = CliRunner().invoke(app, ["contest", "pull-all", "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    assert service.calls == [("pull_all", "abc123", output_dir)]


def test_cli_contest_submit_uses_current_contest(monkeypatch, tmp_path) -> None:
    service = RecordingContestService()
    source = tmp_path / "main.cpp"
    source.write_text("int main() {}\n", encoding="utf-8")
    _install_fake_contest(monkeypatch, tmp_path, service)

    result = CliRunner().invoke(
        app,
        ["contest", "submit", "A", str(source), "--lang", "cc.cc20o2", "--no-watch"],
    )

    assert result.exit_code == 0
    assert service.calls == [("submit", "abc123", "A", source, "cc.cc20o2")]
