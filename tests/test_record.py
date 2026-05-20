from __future__ import annotations

from hydro_cli.record import parse_record_detail, parse_record_list


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
