from __future__ import annotations

from hydro_cli.record import RecordService, parse_record_detail, parse_record_list


def test_parse_record_list() -> None:
    html = """
    <table class="data-table record_main__table"><tbody>
      <tr data-rid="abc">
        <td><a href="/record/abc"><span>100</span> Accepted</a></td>
        <td><a href="/p/P1000"><b>P1000</b>&nbsp;&nbsp;A+B Problem</a></td>
        <td><a class="user-profile-name">alice</a></td>
        <td>1ms</td><td>256KB</td><td>C++20(O2)</td>
        <td><span class="time">2026-5-20</span></td>
      </tr>
    </tbody></table>
    """

    records = parse_record_list(html, "http://localhost:8888")

    assert len(records) == 1
    assert records[0].record_id == "abc"
    assert records[0].status == "Accepted"
    assert records[0].score == "100"
    assert records[0].problem_id == "P1000"


def test_parse_record_list_keeps_plain_contest_record_href() -> None:
    html = """
    <table class="data-table record_main__table"><tbody>
      <tr data-rid="abc">
        <td><a href="/record/abc"><span>100</span> Accepted</a></td>
        <td><a href="/p/P1000?tid=t1"><b>P1000</b>&nbsp;&nbsp;A+B Problem</a></td>
        <td><a class="user-profile-name">alice</a></td>
        <td>1ms</td><td>256KB</td><td>C++20(O2)</td>
        <td><span class="time">2026-5-20</span></td>
      </tr>
    </tbody></table>
    """

    records = parse_record_list(html, "http://localhost:8888")

    assert records[0].url == "http://localhost:8888/record/abc"


class FakeRecordClient:
    base_url = "http://localhost:8888"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_text(self, path: str, **kwargs: object) -> str:
        self.calls.append((path, kwargs))
        return """
        <div id="status" data-status="2">
          <h1 class="section__title"><span>100</span><span>Accepted</span></h1>
        </div>
        """


def test_record_service_list_can_filter_by_contest() -> None:
    client = FakeRecordClient()

    RecordService(client).list(page=2, uid_or_name="7", contest_id="abc123")  # type: ignore[arg-type]

    assert client.calls == [("/record", {"params": {"page": 2, "uidOrName": "7", "tid": "abc123"}})]


def test_record_service_list_contest_self_uses_contest_problemlist() -> None:
    client = FakeRecordClient()

    RecordService(client).list_contest_self("abc 123")  # type: ignore[arg-type]

    assert client.calls == [("/contest/abc%20123/problems", {})]


def test_record_service_show_uses_plain_record_detail_path() -> None:
    client = FakeRecordClient()

    detail = RecordService(client).show("r/1")  # type: ignore[arg-type]

    assert client.calls == [("/record/r%2F1", {})]
    assert detail.url == "http://localhost:8888/record/r%2F1"


def test_parse_record_detail() -> None:
    html = """
    <div id="status" data-status="2">
      <h1 class="section__title"><span>100</span><span>Accepted</span></h1>
      <pre class="compiler-text">ok</pre>
    </div>
    <dl class="large horizontal">
      <dt>Problem</dt><dd><a href="/p/P1000"><b>P1000</b> A+B Problem</a></dd>
      <dt>Language</dt><dd>C++20(O2)</dd>
    </dl>
    <dl class="large horizontal" id="summary"><dt>Score</dt><dd>100</dd></dl>
    <pre class="line-numbers"><code class="language-cpp">int main(){}</code></pre>
    """

    detail = parse_record_detail(html, "http://localhost:8888", "abc")

    assert detail.status == "Accepted"
    assert detail.score == "100"
    assert detail.info["Problem"] == "P1000 A+B Problem"
    assert detail.code == "int main(){}"


def test_parse_record_cases() -> None:
    html = """
    <div id="status" data-status="1">
      <h1 class="section__title"><span>100</span><span>Accepted</span></h1>
    </div>
    <table class="data-table record_detail__table">
      <tbody>
        <tr class="subtask-case">
          <td class="col--case">#1</td>
          <td class="col--status">
            <span class="record-status--text pass">Accepted</span>
            <span class="float-right record-status--text pass">50</span>
            <span class="message">ok</span>
          </td>
          <td class="col--time">1ms</td>
          <td class="col--memory">512 KiB</td>
        </tr>
      </tbody>
    </table>
    """

    detail = parse_record_detail(html, "http://localhost:8888", "abc")

    assert detail.cases == [
        {
            "case": "#1",
            "status": "Accepted",
            "score": "50",
            "time": "1ms",
            "memory": "512 KiB",
            "message": "ok",
        }
    ]


def test_compiling_record_is_not_done() -> None:
    html = """
    <div id="status" data-status="2">
      <h1 class="section__title"><span>0</span><span>Compiling</span></h1>
    </div>
    <dl class="large horizontal" id="summary"><dt>Score</dt><dd>0</dd></dl>
    """

    detail = parse_record_detail(html, "http://localhost:8888", "abc")

    assert detail.status == "Compiling"
    assert not detail.is_done


def test_running_record_is_not_done() -> None:
    html = """
    <div id="status" data-status="20">
      <h1 class="section__title"><span>0</span><span>Running</span><span>1%</span></h1>
    </div>
    <dl class="large horizontal" id="summary"><dt>Score</dt><dd>0</dd></dl>
    """

    detail = parse_record_detail(html, "http://localhost:8888", "abc")

    assert detail.status == "Running 1%"
    assert not detail.is_done


def test_time_exceeded_record_is_done() -> None:
    html = """
    <div id="status" data-status="3">
      <h1 class="section__title"><span>80</span><span>Time Exceeded</span></h1>
    </div>
    <dl class="large horizontal" id="summary"><dt>Score</dt><dd>80</dd></dl>
    """

    detail = parse_record_detail(html, "http://localhost:8888", "abc")

    assert detail.status == "Time Exceeded"
    assert detail.score == "80"
    assert detail.is_done
