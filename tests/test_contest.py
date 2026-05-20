from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from hydro_cli.contest import (
    ContestProblem,
    ContestService,
    parse_contest_detail,
    parse_contest_list,
    parse_contest_problems,
    parse_contest_standings,
    parse_join_form,
    resolve_contest_problem,
)


class FakeClient:
    base_url = "http://localhost:8888"

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.paths: list[str] = []

    def get_text(self, path: str, **_kwargs: object) -> str:
        self.paths.append(path)
        return self.pages[path]


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def iter_bytes(self, chunk_size: int) -> Iterator[bytes]:
        del chunk_size
        yield self.data


class FakeStream:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def __enter__(self) -> FakeResponse:
        return self.response

    def __exit__(self, *_exc: object) -> None:
        return None


class FakePullClient(FakeClient):
    def __init__(self, pages: dict[str, str], files: dict[str, bytes]) -> None:
        super().__init__(pages)
        self.files = files
        self.stream_paths: list[str] = []

    def stream(self, path: str) -> FakeStream:
        self.stream_paths.append(path)
        return FakeStream(FakeResponse(self.files[path]))


def encode_context(data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    escaped = payload.encode("unicode_escape").decode("ascii").replace("'", "\\'")
    return f"<script>window.UiContextNew = '{escaped}';</script>"


def test_parse_contest_list_item_and_live_card() -> None:
    html = """
    <div class="section immersive--content section--contest live">
      <h2 class="status_title">Live...</h2>
      <h1>IOI Test</h1>
      <ul class="info">
        <li><span class="icon icon-calendar"></span> Start at: 2026-5-20 18:30</li>
        <li><span class="icon icon-schedule--fill"></span> Duration: 200 hour(s)</li>
      </ul>
      <a href="/contest/abc123" class="detail-button">View Details</a>
    </div>
    <ol class="contest__list">
      <li class="contest__item contest-type--strictioi">
        <h1 class="contest__title"><a href="/contest/abc123">IOI Test</a></h1>
        <ul class="supplementary list">
          <li><a href="?rule=strictioi" class="contest-type-tag">IOI(Strict)</a></li>
          <li class="contest-tag-rated">Rated</li>
          <li><span class="icon icon-user--multiple"></span> 2</li>
        </ul>
      </li>
    </ol>
    """

    contests = parse_contest_list(html, "http://localhost:8888")

    assert len(contests) == 1
    assert contests[0].contest_id == "abc123"
    assert contests[0].title == "IOI Test"
    assert contests[0].rule == "IOI(Strict)"
    assert contests[0].status == "Live..."
    assert contests[0].duration == "200 hour(s)"
    assert contests[0].rated


def test_parse_contest_detail_from_context_and_sidebar() -> None:
    html = (
        """
        <h1 class="section__title">IOI Test</h1>
        <span class="problem__tag-item icon icon-check">Attended</span>
        <dl class="large horizontal">
          <dt>Status</dt><dd>Live...</dd>
          <dt>Rule</dt><dd>IOI(Strict)</dd>
          <dt>Problem</dt><dd>2</dd>
          <dt>Start at</dt><dd>2026-5-20 18:30</dd>
        </dl>
        """
        + encode_context(
            {
                "tdoc": {
                    "_id": "abc123",
                    "title": "IOI Test",
                    "rule": "strictioi",
                    "beginAt": "2026-05-20T10:30:00.000Z",
                    "endAt": "2026-05-28T18:30:00.000Z",
                    "pids": [16, 17],
                    "rated": True,
                },
                "tsdoc": {"attend": 1},
            }
        )
    )

    detail = parse_contest_detail(html, "http://localhost:8888", "abc123")

    assert detail.contest_id == "abc123"
    assert detail.title == "IOI Test"
    assert detail.rule == "IOI(Strict)"
    assert detail.status == "Live..."
    assert detail.attended
    assert [item.alias for item in detail.problems] == ["A", "B"]
    assert [item.problem_id for item in detail.problems] == ["16", "17"]


def test_parse_contest_problem_table_with_aliases() -> None:
    html = """
    <table class="data-table">
      <thead>
        <tr><th>Status</th><th>Last Submit At</th><th>Problem</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>No Submissions</td>
          <td>-</td>
          <td>
            <a href="/p/16?tid=abc123"><b>A</b>&nbsp;&nbsp;Matrix</a>
            <a href="/p/16/submit?tid=abc123">Submit</a>
          </td>
        </tr>
      </tbody>
    </table>
    """

    problems = parse_contest_problems(html, "http://localhost:8888", "abc123")

    assert len(problems) == 1
    assert problems[0].alias == "A"
    assert problems[0].problem_id == "16"
    assert problems[0].title == "Matrix"
    assert problems[0].status == "No Submissions"
    assert problems[0].last_submit_at == "-"
    assert problems[0].submit_url == "http://localhost:8888/p/16/submit?tid=abc123"
    assert resolve_contest_problem(problems, "A").problem_id == "16"
    assert resolve_contest_problem(problems, "16").alias == "A"


def test_parse_contest_standings_table() -> None:
    html = """
    <table class="data-table">
      <thead><tr><th>Rank</th><th>User</th><th>Score</th><th>A</th></tr></thead>
      <tbody>
        <tr><td>1</td><td>alice</td><td>100</td><td>100</td></tr>
        <tr><td>2</td><td>bob</td><td>40</td><td>40</td></tr>
      </tbody>
    </table>
    """

    standings = parse_contest_standings(html, "http://localhost:8888", "abc123", "/contest/abc123/scoreboard")

    assert standings.headers == ["Rank", "User", "Score", "A"]
    assert standings.rows == [["1", "alice", "100", "100"], ["2", "bob", "40", "40"]]
    assert standings.url == "http://localhost:8888/contest/abc123/scoreboard"


def test_parse_join_form_detects_attend_code_field() -> None:
    html = """
    <form action="/contest/abc123" method="POST">
      <input type="hidden" name="operation" value="attend">
      <input type="password" name="code" value="">
      <button type="submit">Attend Contest</button>
    </form>
    """

    form = parse_join_form(html, "http://localhost:8888", "/contest/abc123")

    assert form is not None
    assert form.action == "/contest/abc123"
    assert form.method == "POST"
    assert form.fields == {"operation": "attend", "code": ""}
    assert form.password_field == "code"


def test_resolve_contest_problem_is_case_insensitive_for_alias() -> None:
    problems = [
        ContestProblem(
            alias="A",
            problem_id="16",
            title="Matrix",
            status="",
            score="",
            last_submit_at="",
            url="/p/16?tid=abc123",
            submit_url="/p/16/submit?tid=abc123",
        )
    ]

    assert resolve_contest_problem(problems, "A").problem_id == "16"
    assert resolve_contest_problem(problems, "a").problem_id == "16"
    assert resolve_contest_problem(problems, "16").alias == "A"


def test_contest_service_fetches_problem_inside_contest_context() -> None:
    problems_html = """
    <table><tbody>
      <tr><td>No Submissions</td><td>-</td><td>
        <a href="/p/16?tid=abc123"><b>A</b>&nbsp;&nbsp;Matrix</a>
        <a href="/p/16/submit?tid=abc123">Submit</a>
      </td></tr>
    </tbody></table>
    """
    problem_html = encode_context(
        {
            "pdoc": {
                "docId": 16,
                "title": "Matrix",
                "content": {"en": "Contest statement"},
                "config": {"timeMin": 1000, "timeMax": 1000, "memoryMin": 256, "memoryMax": 256},
            }
        }
    )
    client = FakeClient(
        {
            "/contest/abc123/problems": problems_html,
            "/p/16?tid=abc123": problem_html,
        }
    )

    problem = ContestService(client).problem("abc123", "A")  # type: ignore[arg-type]

    assert client.paths == ["/contest/abc123/problems", "/p/16?tid=abc123"]
    assert problem.problem_id == "16"
    assert problem.title == "Matrix"
    assert problem.statement == "Contest statement\n"
    assert problem.url == "http://localhost:8888/p/16?tid=abc123"


def test_contest_service_pull_downloads_attachments_with_tid(tmp_path: Path) -> None:
    problems_html = """
    <table><tbody>
      <tr><td>No Submissions</td><td>-</td><td>
        <a href="/p/16?tid=abc123"><b>A</b>&nbsp;&nbsp;Matrix</a>
        <a href="/p/16/submit?tid=abc123">Submit</a>
      </td></tr>
    </tbody></table>
    """
    problem_html = encode_context(
        {
            "pdoc": {
                "docId": 16,
                "title": "Matrix",
                "content": {"en": "[data](file://data.zip)"},
                "additional_file": [{"name": "data.zip", "size": 4}],
                "config": {"timeMin": 1000, "timeMax": 1000, "memoryMin": 256, "memoryMax": 256},
            }
        }
    )
    file_path = "/p/16/file/data.zip?type=additional_file&tid=abc123"
    client = FakePullClient(
        {
            "/contest/abc123/problems": problems_html,
            "/p/16?tid=abc123": problem_html,
        },
        {file_path: b"data"},
    )

    problem = ContestService(client).pull("abc123", "A", tmp_path)  # type: ignore[arg-type]

    assert client.stream_paths == [file_path]
    assert problem.problem_id == "A"
    target = tmp_path / "abc123" / "A"
    assert (target / "files" / "data.zip").read_bytes() == b"data"
    assert "(files/data.zip)" in (target / "statement.md").read_text(encoding="utf-8")
