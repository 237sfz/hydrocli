from __future__ import annotations

import json

from hydro_cli.contest import (
    parse_contest_detail,
    parse_contest_list,
    parse_contest_problems,
    parse_contest_standings,
    parse_join_form,
    resolve_contest_problem,
)


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
