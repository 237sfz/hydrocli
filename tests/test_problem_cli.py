from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hydro_cli import cli as cli_module
from hydro_cli.cli import (
    _collect_problem_ids,
    _pull_problem_ids,
    _pull_problem_with_retries,
    app,
)
from hydro_cli.config import Config, ConfigStore
from hydro_cli.errors import HydroRequestError
from hydro_cli.problem import Attachment, Problem, ProblemListPage


class FakeListClient:
    base_url = "http://localhost:8888"

    def __init__(self) -> None:
        self.calls: list[int] = []


class RecordingProblemService:
    pages: dict[int, ProblemListPage] = {}
    list_calls: list[int] = []
    pull_behaviors: dict[str, list[object]] = {}
    pull_calls: list[str] = []
    instances = 0

    def __init__(self, _client: object) -> None:
        type(self).instances += 1

    def list_page(self, page: int = 1) -> ProblemListPage:
        type(self).list_calls.append(page)
        return type(self).pages[page]

    def pull(self, pid: str, output_dir: Path) -> Problem:
        del output_dir
        type(self).pull_calls.append(pid)
        behaviors = type(self).pull_behaviors.setdefault(pid, [])
        result = behaviors.pop(0) if behaviors else _fake_problem(pid)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, Problem):
            return result
        return _fake_problem(pid, attachments=int(result))

    @classmethod
    def reset(cls) -> None:
        cls.pages = {}
        cls.list_calls = []
        cls.pull_behaviors = {}
        cls.pull_calls = []
        cls.instances = 0


class FakeClient:
    def __init__(self, _config: Config) -> None:
        pass

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _fake_problem(pid: str, attachments: int = 0) -> Problem:
    return Problem(
        problem_id=pid,
        title=f"Problem {pid}",
        url=f"http://localhost:8888/p/{pid}",
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
        attachments=[Attachment(name=f"{index}.txt") for index in range(attachments)],
    )


@pytest.fixture(autouse=True)
def reset_recording_service(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingProblemService.reset()
    monkeypatch.setattr(cli_module, "ProblemService", RecordingProblemService)


@pytest.fixture
def no_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "Progress", FakeProgress)


class FakeProgress:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def __enter__(self) -> "FakeProgress":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def add_task(self, *_args: object, **_kwargs: object) -> int:
        return 1

    def update(self, *_args: object, **_kwargs: object) -> None:
        return None


def _page(*pids: str, total_pages: int | None = None) -> ProblemListPage:
    return ProblemListPage(
        problems=[
            {"problem_id": pid, "title": f"Problem {pid}", "url": f"http://localhost:8888/p/{pid}"}
            for pid in pids
        ],
        total_pages=total_pages,
    )


def test_collect_problem_ids_respects_start_and_end_page(no_progress: None) -> None:
    RecordingProblemService.pages = {
        2: _page("1002", total_pages=5),
        3: _page("1003", total_pages=5),
    }

    pids = _collect_problem_ids(FakeListClient(), start_page=2, end_page=3)  # type: ignore[arg-type]

    assert pids == ["1002", "1003"]
    assert RecordingProblemService.list_calls == [2, 3]


def test_collect_problem_ids_stops_at_empty_page_when_total_unknown(no_progress: None) -> None:
    RecordingProblemService.pages = {
        1: _page("1001"),
        2: _page("1002", "1001"),
        3: _page(),
    }

    pids = _collect_problem_ids(FakeListClient(), start_page=1, end_page=None)  # type: ignore[arg-type]

    assert pids == ["1001", "1002"]
    assert RecordingProblemService.list_calls == [1, 2, 3]


def test_pull_problem_with_retries_skips_existing(tmp_path: Path) -> None:
    problem_dir = tmp_path / "1001"
    problem_dir.mkdir()
    (problem_dir / "statement.md").write_text("statement\n", encoding="utf-8")
    (problem_dir / "problem.json").write_text("{}\n", encoding="utf-8")
    service = RecordingProblemService(FakeListClient())

    item = _pull_problem_with_retries(
        service,  # type: ignore[arg-type]
        "1001",
        output_dir=tmp_path,
        skip_existing=True,
    )

    assert item.status == "skipped"
    assert RecordingProblemService.pull_calls == []


def test_pull_problem_with_retries_continues_after_retryable_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module.time, "sleep", lambda _seconds: None)
    RecordingProblemService.pull_behaviors = {
        "1001": [HydroRequestError("busy", status_code=429), _fake_problem("1001", attachments=2)]
    }
    service = RecordingProblemService(FakeListClient())

    item = _pull_problem_with_retries(
        service,  # type: ignore[arg-type]
        "1001",
        output_dir=tmp_path,
        skip_existing=False,
    )

    assert item.status == "pulled"
    assert item.attachments == 2
    assert RecordingProblemService.pull_calls == ["1001", "1001"]


def test_pull_problem_with_retries_does_not_retry_forbidden(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module.time, "sleep", lambda _seconds: None)
    RecordingProblemService.pull_behaviors = {
        "1001": [HydroRequestError("forbidden", status_code=403), _fake_problem("1001")]
    }
    service = RecordingProblemService(FakeListClient())

    item = _pull_problem_with_retries(
        service,  # type: ignore[arg-type]
        "1001",
        output_dir=tmp_path,
        skip_existing=False,
    )

    assert item.status == "failed"
    assert item.error == "forbidden"
    assert RecordingProblemService.pull_calls == ["1001"]


def test_pull_problem_with_retries_handles_hydro_403_rate_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module.time, "sleep", lambda _seconds: None)
    RecordingProblemService.pull_behaviors = {
        "1001": [
            HydroRequestError(
                "forbidden",
                status_code=403,
                response_text="Too frequent operations of global (limit: 100 operations in 5 seconds).",
            ),
            _fake_problem("1001"),
        ]
    }
    service = RecordingProblemService(FakeListClient())

    item = _pull_problem_with_retries(
        service,  # type: ignore[arg-type]
        "1001",
        output_dir=tmp_path,
        skip_existing=False,
    )

    assert item.status == "pulled"
    assert RecordingProblemService.pull_calls == ["1001", "1001"]


def test_pull_problem_ids_continues_after_failure(no_progress: None, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "HydroClient", FakeClient)
    RecordingProblemService.pull_behaviors = {
        "1001": [_fake_problem("1001")],
        "1002": [HydroRequestError("missing", status_code=404)],
        "1003": [_fake_problem("1003")],
    }

    summary = _pull_problem_ids(
        Config(),
        ["1001", "1002", "1003"],
        output_dir=tmp_path,
        skip_existing=False,
        jobs=1,
    )

    assert summary.pulled == 2
    assert [item.pid for item in summary.failures] == ["1002"]
    assert RecordingProblemService.pull_calls == ["1001", "1002", "1003"]


def test_pull_problem_ids_uses_worker_client_per_problem(no_progress: None, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "HydroClient", FakeClient)
    RecordingProblemService.pull_behaviors = {
        "1001": [_fake_problem("1001")],
        "1002": [_fake_problem("1002")],
    }

    summary = _pull_problem_ids(
        Config(),
        ["1001", "1002"],
        output_dir=tmp_path,
        skip_existing=False,
        jobs=2,
    )

    assert summary.pulled == 2
    assert summary.failed == 0
    assert sorted(RecordingProblemService.pull_calls) == ["1001", "1002"]
    assert RecordingProblemService.instances == 2


def test_cli_problem_pull_all_exits_one_when_any_problem_fails(
    no_progress: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module, "HydroClient", FakeClient)
    monkeypatch.setenv("HYDRO_CLI_CONFIG_DIR", str(tmp_path / "config"))
    store = ConfigStore()
    store.save(Config(base_url="http://localhost:8888"))
    RecordingProblemService.pages = {1: _page("1001", "1002", total_pages=1)}
    RecordingProblemService.pull_behaviors = {
        "1001": [_fake_problem("1001")],
        "1002": [HydroRequestError("forbidden", status_code=403)],
    }

    result = CliRunner().invoke(app, ["problem", "pull-all", "--output-dir", str(tmp_path / "problems")])

    assert result.exit_code == 1
    assert "1 pulled, 0 skipped, 1 failed" in " ".join(result.stdout.split())
    assert "1002" in result.stdout


def test_cli_problem_pull_all_exits_zero_when_only_skipped(
    no_progress: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module, "HydroClient", FakeClient)
    monkeypatch.setenv("HYDRO_CLI_CONFIG_DIR", str(tmp_path / "config"))
    store = ConfigStore()
    store.save(Config(base_url="http://localhost:8888"))
    output_dir = tmp_path / "problems"
    problem_dir = output_dir / "1001"
    problem_dir.mkdir(parents=True)
    (problem_dir / "statement.md").write_text("statement\n", encoding="utf-8")
    (problem_dir / "problem.json").write_text(json.dumps({"problem_id": "1001"}), encoding="utf-8")
    RecordingProblemService.pages = {1: _page("1001", total_pages=1)}

    result = CliRunner().invoke(
        app,
        ["problem", "pull-all", "--output-dir", str(output_dir), "--skip-existing"],
    )

    assert result.exit_code == 0
    assert "0 pulled, 1 skipped, 0 failed" in " ".join(result.stdout.split())
    assert RecordingProblemService.pull_calls == []
