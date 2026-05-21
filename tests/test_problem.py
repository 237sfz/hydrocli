from __future__ import annotations

from hydro_cli.problem import parse_problem_list_page


def test_parse_problem_list_page_reads_pager_total() -> None:
    html = """
    <table>
      <tr><td><a href="/p/1001">A + B</a></td></tr>
      <tr><td><a href="/p/1002">Matrix</a></td></tr>
    </table>
    <nav class="pager">
      <a href="/p?page=2">2</a>
      <a href="/p?page=145">Last &raquo;</a>
    </nav>
    """

    page = parse_problem_list_page(html, "http://localhost:8888")

    assert page.total_pages == 145
    assert page.problems == [
        {"problem_id": "1001", "title": "A + B", "url": "http://localhost:8888/p/1001"},
        {"problem_id": "1002", "title": "Matrix", "url": "http://localhost:8888/p/1002"},
    ]


def test_parse_problem_list_page_has_unknown_total_without_pager() -> None:
    html = '<a href="/p/1001">A + B</a>'

    page = parse_problem_list_page(html, "http://localhost:8888")

    assert page.total_pages is None
    assert [item["problem_id"] for item in page.problems] == ["1001"]


def test_parse_problem_list_page_deduplicates_same_page_pid() -> None:
    html = """
    <a href="/p/1001">A + B</a>
    <a href="/p/1001">A + B Duplicate</a>
    <a href="/p/1001/submit">Submit</a>
    """

    page = parse_problem_list_page(html, "http://localhost:8888")

    assert [item["problem_id"] for item in page.problems] == ["1001"]
    assert page.problems[0]["title"] == "A + B"
