from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .client import HydroClient
from .errors import HydroCliError
from .parsing import clean_text, extract_ui_context
from .problem import Problem, ProblemService
from .submit import SubmitService
from .utils import absolute_url, quote_path_part


RULE_NAMES = {
    "acm": "XCPC",
    "oi": "OI",
    "ioi": "IOI",
    "strictioi": "IOI(Strict)",
    "ledo": "Ledo",
    "homework": "Homework",
}


@dataclass(slots=True)
class ContestSummary:
    contest_id: str
    title: str
    rule: str
    status: str
    start: str
    duration: str
    rated: bool
    participants: str
    url: str


@dataclass(slots=True)
class ContestProblem:
    alias: str
    problem_id: str
    title: str
    status: str
    score: str
    last_submit_at: str
    url: str
    submit_url: str


@dataclass(slots=True)
class ContestDetail:
    contest_id: str
    title: str
    rule: str
    status: str
    attended: bool
    info: dict[str, str]
    problems: list[ContestProblem]
    standings_url: str
    url: str


@dataclass(slots=True)
class ContestStanding:
    contest_id: str
    headers: list[str]
    rows: list[list[str]]
    url: str


@dataclass(slots=True)
class JoinForm:
    action: str
    method: str
    fields: dict[str, str]
    password_field: str


@dataclass(slots=True)
class ContestSubmitTarget:
    contest_id: str
    problem: ContestProblem
    submit_path: str
    submit_url: str
    record_detail_path: str
    languages: list[str]


@dataclass(slots=True)
class ContestSubmission:
    record_id: str
    target: ContestSubmitTarget


class ContestService:
    def __init__(self, client: HydroClient) -> None:
        self.client = client

    def list(self, page: int = 1) -> list[ContestSummary]:
        html = self.client.get_text("/contest", params={"page": page} if page > 1 else None)
        return parse_contest_list(html, self.client.base_url)

    def show(self, cid: str) -> ContestDetail:
        html = self.client.get_text(f"/contest/{quote_path_part(cid)}")
        return parse_contest_detail(html, self.client.base_url, cid)

    def join(self, cid: str, password: str = "") -> ContestDetail:
        path = f"/contest/{quote_path_part(cid)}"
        html = self.client.get_text(path)
        detail = parse_contest_detail(html, self.client.base_url, cid)
        if detail.attended:
            return detail

        form = parse_join_form(html, self.client.base_url, path)
        data = form.fields.copy() if form else {"operation": "attend"}
        password_field = form.password_field if form else "code"
        if password:
            data[password_field or "code"] = password
        elif form and password_field and not data.get(password_field):
            raise HydroCliError("contest password is required; pass --password")

        action = form.action if form else path
        method = form.method if form else "POST"
        self.client.raw_request(method, action, data=data, follow_redirects=False)

        updated = self.show(cid)
        if not updated.attended:
            raise HydroCliError("contest join did not confirm attendance")
        return updated

    def problems(self, cid: str) -> list[ContestProblem]:
        path = f"/contest/{quote_path_part(cid)}/problems"
        try:
            html = self.client.get_text(path)
        except HydroCliError:
            detail = self.show(cid)
            if detail.problems:
                return detail.problems
            raise
        return parse_contest_problems(html, self.client.base_url, cid)

    def problem(self, cid: str, problem_arg: str) -> Problem:
        contest_problem = resolve_contest_problem(self.problems(cid), problem_arg)
        path = f"/p/{quote_path_part(contest_problem.problem_id)}?tid={quote_path_part(cid)}"
        return ProblemService(self.client).fetch(
            contest_problem.problem_id,
            page_path=path,
            use_api=False,
        )

    def standings(self, cid: str) -> ContestStanding:
        quoted = quote_path_part(cid)
        paths = [
            f"/contest/{quoted}/scoreboard",
            f"/contest/{quoted}/scoreboard/default",
            f"/contest/{quoted}/ranking",
            f"/contest/{quoted}/rank",
            f"/contest/{quoted}/standings",
        ]
        errors: list[str] = []
        for path in paths:
            try:
                html = self.client.get_text(path)
            except HydroCliError as exc:
                errors.append(str(exc))
                continue
            standing = parse_contest_standings(html, self.client.base_url, cid, path)
            if standing.rows:
                return standing
        reason = f": {errors[0]}" if errors else ""
        raise HydroCliError(f"contest standings are not visible or unavailable{reason}")

    def submit_target(self, cid: str, problem_arg: str) -> ContestSubmitTarget:
        problems = self.problems(cid)
        problem = resolve_contest_problem(problems, problem_arg)
        default_path = (
            _url_path(problem.submit_url)
            if problem.submit_url
            else f"/p/{quote_path_part(problem.problem_id)}/submit?tid={quote_path_part(cid)}"
        )
        html = self.client.get_text(default_path)
        return parse_submit_target(html, self.client.base_url, cid, problem, default_path)

    def submit(
        self,
        cid: str,
        problem_arg: str,
        source_path: Path,
        lang: str = "",
    ) -> ContestSubmission:
        target = self.submit_target(cid, problem_arg)
        record_id = SubmitService(self.client).submit_to_path(target.submit_path, source_path, lang)
        return ContestSubmission(record_id=record_id, target=target)


def parse_contest_list(html: str, base_url: str) -> list[ContestSummary]:
    soup = BeautifulSoup(html, "html.parser")
    summaries: list[ContestSummary] = []
    seen: set[str] = set()

    for item in soup.select("li.contest__item"):
        link = item.select_one('h1.contest__title a[href^="/contest/"], a[href^="/contest/"]')
        if not link:
            continue
        contest_id = _contest_id_from_href(str(link.get("href") or ""))
        if not contest_id or contest_id in seen:
            continue
        seen.add(contest_id)
        summaries.append(
            ContestSummary(
                contest_id=contest_id,
                title=clean_text(link.get_text(" ", strip=True)),
                rule=_first_text(item, ".contest-type-tag"),
                status=_status_from_node(item),
                start=_contest_item_start(item),
                duration=_text_for_icon(item, "schedule"),
                rated=bool(item.select_one(".contest-tag-rated")),
                participants=_text_for_icon(item, "user--multiple"),
                url=absolute_url(base_url, str(link.get("href") or "")),
            )
        )

    for card in soup.select(".section--contest"):
        link = card.select_one('a[href^="/contest/"]')
        contest_id = _contest_id_from_href(str(link.get("href") or "")) if link else ""
        if not contest_id:
            continue
        card_summary = ContestSummary(
            contest_id=contest_id,
            title=_first_text(card, "h1") or clean_text(link.get_text(" ", strip=True)),
            rule=_text_for_icon(card, "award"),
            status=_status_from_node(card),
            start=_text_for_icon(card, "calendar") or _contest_item_start(card),
            duration=_text_for_icon(card, "schedule"),
            rated=bool(card.select_one(".contest-tag-rated")),
            participants=_text_for_icon(card, "user--multiple"),
            url=absolute_url(base_url, str(link.get("href") or "")),
        )
        for index, summary in enumerate(summaries):
            if summary.contest_id != contest_id:
                continue
            summaries[index] = _merge_summary(summary, card_summary)
            break
        else:
            summaries.append(card_summary)
            seen.add(contest_id)

    if summaries:
        return summaries

    for link in soup.select('a[href^="/contest/"]'):
        href = str(link.get("href") or "")
        contest_id = _contest_id_from_href(href)
        title = clean_text(link.get_text(" ", strip=True))
        if not contest_id or not title or contest_id in seen:
            continue
        seen.add(contest_id)
        summaries.append(
            ContestSummary(
                contest_id=contest_id,
                title=title,
                rule="",
                status="",
                start="",
                duration="",
                rated=False,
                participants="",
                url=absolute_url(base_url, href),
            )
        )
    return summaries


def parse_contest_detail(html: str, base_url: str, cid: str) -> ContestDetail:
    soup = BeautifulSoup(html, "html.parser")
    ui = _safe_ui_context(html)
    tdoc = ui.get("tdoc") if isinstance(ui.get("tdoc"), dict) else {}
    tsdoc = ui.get("tsdoc") if isinstance(ui.get("tsdoc"), dict) else {}
    info = _parse_info_dl(soup)

    contest_id = str(tdoc.get("_id") or tdoc.get("docId") or cid)
    title = str(tdoc.get("title") or _first_text(soup, ".section__title") or f"Contest {cid}")
    rule = info.get("Rule") or _rule_name(str(tdoc.get("rule") or ""))
    status = info.get("Status") or _status_from_node(soup) or _status_from_times(tdoc)
    attended = _is_attended(tsdoc, soup)

    pids = tdoc.get("pids") if isinstance(tdoc.get("pids"), list) else []
    problems = parse_contest_problems(html, base_url, cid)
    if not problems and pids:
        problems = [
            ContestProblem(
                alias=alphabetic_id(index),
                problem_id=str(pid),
                title=f"Problem {pid}",
                status="",
                score="",
                last_submit_at="",
                url=absolute_url(base_url, f"/p/{quote_path_part(pid)}?tid={quote_path_part(cid)}"),
                submit_url=absolute_url(
                    base_url,
                    f"/p/{quote_path_part(pid)}/submit?tid={quote_path_part(cid)}",
                ),
            )
            for index, pid in enumerate(pids)
        ]

    if pids and "Problem" not in info:
        info["Problem"] = str(len(pids))
    if tdoc.get("beginAt") and "Start at" not in info:
        info["Start at"] = str(tdoc["beginAt"])
    if tdoc.get("endAt") and "End at" not in info:
        info["End at"] = str(tdoc["endAt"])
    if tdoc.get("rated") is not None and "Rated" not in info:
        info["Rated"] = "yes" if tdoc.get("rated") else "no"

    standings_link = soup.select_one(f'a[href^="/contest/{quote_path_part(cid)}/scoreboard"]')
    standings_href = str(standings_link.get("href") or "") if standings_link else ""
    standings_url = absolute_url(base_url, standings_href or f"/contest/{quote_path_part(cid)}/scoreboard")

    return ContestDetail(
        contest_id=contest_id,
        title=title,
        rule=rule,
        status=status,
        attended=attended,
        info=info,
        problems=problems,
        standings_url=standings_url,
        url=absolute_url(base_url, f"/contest/{quote_path_part(contest_id)}"),
    )


def parse_contest_problems(html: str, base_url: str, cid: str) -> list[ContestProblem]:
    soup = BeautifulSoup(html, "html.parser")
    problems: list[ContestProblem] = []
    seen: set[str] = set()

    for row in soup.select("tbody tr"):
        problem_link = _find_problem_link(row)
        if not problem_link:
            continue
        href = str(problem_link.get("href") or "")
        problem_id = _problem_id_from_href(href)
        if not problem_id or problem_id in seen:
            continue
        seen.add(problem_id)

        alias = _problem_alias(problem_link)
        title = _problem_title(problem_link, alias, problem_id)
        cell_by_header = _row_cells_by_header(row)
        cells = row.find_all("td")
        status = _cell_text(cell_by_header.get("status")) or (_cell_text(cells[0]) if cells else "")
        score = _cell_text(cell_by_header.get("score"))
        last_submit_at = (
            _cell_text(cell_by_header.get("last submit at"))
            or _cell_text(cell_by_header.get("submit at"))
            or _cell_text(cell_by_header.get("last submit"))
        )
        submit_link = row.select_one('a[href*="/submit"]')
        submit_href = str(submit_link.get("href") or "") if submit_link else ""

        problems.append(
            ContestProblem(
                alias=alias,
                problem_id=problem_id,
                title=title,
                status=status,
                score=score,
                last_submit_at=last_submit_at,
                url=absolute_url(base_url, href),
                submit_url=absolute_url(base_url, submit_href) if submit_href else "",
            )
        )

    if problems:
        return problems

    ui = _safe_ui_context(html)
    tdoc = ui.get("tdoc") if isinstance(ui.get("tdoc"), dict) else {}
    pids = tdoc.get("pids") if isinstance(tdoc.get("pids"), list) else []
    return [
        ContestProblem(
            alias=alphabetic_id(index),
            problem_id=str(pid),
            title=f"Problem {pid}",
            status="",
            score="",
            last_submit_at="",
            url=absolute_url(base_url, f"/p/{quote_path_part(pid)}?tid={quote_path_part(cid)}"),
            submit_url=absolute_url(
                base_url,
                f"/p/{quote_path_part(pid)}/submit?tid={quote_path_part(cid)}",
            ),
        )
        for index, pid in enumerate(pids)
    ]


def parse_contest_standings(
    html: str,
    base_url: str,
    cid: str,
    path: str,
) -> ContestStanding:
    soup = BeautifulSoup(html, "html.parser")
    best_headers: list[str] = []
    best_rows: list[list[str]] = []
    for table in soup.select("table"):
        headers = _table_headers(table)
        rows = _table_rows(table)
        if not rows:
            continue
        if _looks_like_standings(headers) or not best_rows:
            best_headers = headers or [f"C{i + 1}" for i in range(max(len(row) for row in rows))]
            best_rows = rows
            if _looks_like_standings(headers):
                break
    return ContestStanding(
        contest_id=cid,
        headers=best_headers,
        rows=best_rows,
        url=absolute_url(base_url, path),
    )


def parse_join_form(html: str, base_url: str, current_path: str) -> JoinForm | None:
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.select("form"):
        action_raw = str(form.get("action") or "")
        if "/login" in action_raw:
            continue
        fields = _form_fields(form)
        operation = fields.get("operation", "").lower()
        text = clean_text(form.get_text(" ", strip=True)).lower()
        names = {str(field.get("name") or "").lower() for field in form.select("[name]")}
        password_field = _password_field(form)
        joinish = (
            operation in {"attend", "join", "register"}
            or any(word in text for word in ("attend", "join", "register", "参加", "报名"))
            or "code" in names
        )
        dangerous = operation in {"early_end", "delete", "remove", "update"}
        if not joinish or dangerous:
            continue
        return JoinForm(
            action=_resolve_action(base_url, current_path, action_raw),
            method=str(form.get("method") or "GET").upper(),
            fields=fields or {"operation": "attend"},
            password_field=password_field,
        )
    return None


def parse_submit_target(
    html: str,
    base_url: str,
    cid: str,
    problem: ContestProblem,
    default_path: str,
) -> ContestSubmitTarget:
    soup = BeautifulSoup(html, "html.parser")
    ui = _safe_ui_context(html)

    submit_path = ""
    post_submit_url = ui.get("postSubmitUrl")
    if isinstance(post_submit_url, str) and post_submit_url:
        submit_path = post_submit_url
    else:
        form = soup.select_one('form[method="post"], form[method="POST"], form')
        action = str(form.get("action") or "") if form else ""
        submit_path = _resolve_action(base_url, default_path, action) if action else default_path

    record_detail_path = ""
    get_record_detail_url = ui.get("getRecordDetailUrl")
    if isinstance(get_record_detail_url, str):
        record_detail_path = get_record_detail_url

    languages = _languages_from_submit_context(ui) or _languages_from_select(soup)

    return ContestSubmitTarget(
        contest_id=cid,
        problem=problem,
        submit_path=submit_path,
        submit_url=absolute_url(base_url, submit_path),
        record_detail_path=record_detail_path,
        languages=languages,
    )


def resolve_contest_problem(problems: list[ContestProblem], problem_arg: str) -> ContestProblem:
    wanted = problem_arg.strip()
    for item in problems:
        if item.alias.lower() == wanted.lower() or item.problem_id == wanted:
            return item
    for item in problems:
        if item.title == wanted:
            return item
    choices = ", ".join(
        f"{item.alias}:{item.problem_id}" if item.alias else item.problem_id for item in problems
    )
    raise HydroCliError(f"contest problem not found: {problem_arg} ({choices})")


def alphabetic_id(index: int) -> str:
    value = index
    result = ""
    while True:
        result = chr(ord("A") + value % 26) + result
        value = value // 26 - 1
        if value < 0:
            return result


def _merge_summary(base: ContestSummary, extra: ContestSummary) -> ContestSummary:
    return ContestSummary(
        contest_id=base.contest_id,
        title=base.title or extra.title,
        rule=base.rule or extra.rule,
        status=extra.status or base.status,
        start=extra.start or base.start,
        duration=extra.duration or base.duration,
        rated=base.rated or extra.rated,
        participants=extra.participants or base.participants,
        url=base.url or extra.url,
    )


def _safe_ui_context(html: str) -> dict[str, Any]:
    try:
        return extract_ui_context(html)
    except Exception:
        return {}


def _contest_id_from_href(href: str) -> str:
    path = urlparse(href).path
    match = re.fullmatch(r"/contest/([^/?#]+)", path)
    return unquote(match.group(1)) if match else ""


def _problem_id_from_href(href: str) -> str:
    path = urlparse(href).path
    for pattern in (r"/p/([^/?#]+)(?:/submit)?", r"/contest/[^/]+/p/([^/?#]+)(?:/submit)?"):
        match = re.fullmatch(pattern, path)
        if match:
            return unquote(match.group(1))
    return ""


def _find_problem_link(row: Tag) -> Tag | None:
    for link in row.select('a[href*="/p/"]'):
        href = str(link.get("href") or "")
        if "/submit" not in urlparse(href).path and _problem_id_from_href(href):
            return link
    return None


def _problem_alias(link: Tag) -> str:
    bold = link.find("b")
    if bold:
        value = clean_text(bold.get_text(" ", strip=True)).rstrip(".")
        if value:
            return value
    text = clean_text(link.get_text(" ", strip=True))
    match = re.match(r"([A-Z]+|\d+)[\s.]+", text)
    return match.group(1) if match else ""


def _problem_title(link: Tag, alias: str, problem_id: str) -> str:
    text = clean_text(link.get_text(" ", strip=True))
    if alias:
        text = re.sub(rf"^{re.escape(alias)}[\s.]+", "", text).strip()
    return text or f"Problem {problem_id}"


def _row_cells_by_header(row: Tag) -> dict[str, Tag]:
    table = row.find_parent("table")
    if not isinstance(table, Tag):
        return {}
    headers = [clean_text(th.get_text(" ", strip=True)).lower() for th in table.select("thead th")]
    cells = row.find_all("td")
    return {header: cell for header, cell in zip(headers, cells, strict=False)}


def _cell_text(node: Tag | None) -> str:
    return clean_text(node.get_text(" ", strip=True)) if node else ""


def _parse_info_dl(soup: BeautifulSoup) -> dict[str, str]:
    info: dict[str, str] = {}
    for dl in soup.select("dl.large.horizontal, dl"):
        pending_key = ""
        for child in dl.children:
            if not isinstance(child, Tag):
                continue
            if child.name == "dt":
                pending_key = clean_text(child.get_text(" ", strip=True))
            elif child.name == "dd" and pending_key:
                info[pending_key] = clean_text(child.get_text(" ", strip=True))
                pending_key = ""
    return info


def _first_text(root: BeautifulSoup | Tag, selector: str) -> str:
    node = root.select_one(selector)
    return clean_text(node.get_text(" ", strip=True)) if node else ""


def _status_from_node(node: BeautifulSoup | Tag) -> str:
    for selector in (".status_title", ".problem__tag-item"):
        for item in node.select(selector):
            text = clean_text(item.get_text(" ", strip=True))
            if text and _looks_like_status(text):
                return text
    classes = " ".join(str(item) for item in (node.get("class") or [])) if isinstance(node, Tag) else ""
    if "live" in classes:
        return "Live"
    if "done" in classes or "ended" in classes:
        return "Ended"
    if "not_started" in classes or "upcoming" in classes:
        return "Upcoming"
    return ""


def _looks_like_status(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ("live", "ended", "upcoming", "not started"))


def _contest_item_start(item: Tag) -> str:
    full = ""
    for text in [clean_text(node.get_text(" ", strip=True)) for node in item.select(".time")]:
        if text and text not in full:
            full = f"{full} {text}".strip()
    return full


def _text_for_icon(item: Tag, icon_part: str) -> str:
    for icon in item.select(f'[class*="{icon_part}"]'):
        parent = icon.find_parent("li")
        if isinstance(parent, Tag):
            text = clean_text(parent.get_text(" ", strip=True))
            return re.sub(r"^(Rule|Start at|Duration|Partic\.?):\s*", "", text).strip()
    return ""


def _rule_name(rule: str) -> str:
    return RULE_NAMES.get(rule, rule)


def _is_attended(tsdoc: object, soup: BeautifulSoup) -> bool:
    if isinstance(tsdoc, dict) and tsdoc.get("attend"):
        return True
    text = clean_text(soup.get_text(" ", strip=True)).lower()
    return "attended" in text and "not attended" not in text


def _status_from_times(tdoc: object) -> str:
    if not isinstance(tdoc, dict):
        return ""
    if tdoc.get("beginAt") and tdoc.get("endAt"):
        return ""
    return ""


def _table_headers(table: Tag) -> list[str]:
    headers = [clean_text(th.get_text(" ", strip=True)) for th in table.select("thead th")]
    if headers:
        return headers
    first_row = table.select_one("tr")
    if not first_row:
        return []
    return [clean_text(cell.get_text(" ", strip=True)) for cell in first_row.find_all("th")]


def _table_rows(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.select("tbody tr"):
        cells = row.find_all(["th", "td"])
        if cells:
            rows.append([clean_text(cell.get_text(" ", strip=True)) for cell in cells])
    if rows:
        return rows
    for row in table.select("tr")[1:]:
        cells = row.find_all(["th", "td"])
        if cells:
            rows.append([clean_text(cell.get_text(" ", strip=True)) for cell in cells])
    return rows


def _looks_like_standings(headers: list[str]) -> bool:
    text = " ".join(headers).lower()
    keywords = ("rank", "user", "team", "score", "total", "penalty", "排名", "用户", "总分", "罚时")
    return any(keyword in text for keyword in keywords)


def _form_fields(form: Tag) -> dict[str, str]:
    fields: dict[str, str] = {}
    for field in form.select("input[name], textarea[name], select[name]"):
        name = str(field.get("name") or "")
        if not name:
            continue
        if field.name == "select":
            selected = field.select_one("option[selected]")
            if not selected:
                selected = field.select_one("option")
            fields[name] = str(selected.get("value") or selected.get_text(" ", strip=True)) if selected else ""
        elif field.name == "textarea":
            fields[name] = field.get_text("", strip=False)
        else:
            field_type = str(field.get("type") or "").lower()
            if field_type in {"submit", "button", "file"}:
                continue
            fields[name] = str(field.get("value") or "")
    return fields


def _password_field(form: Tag) -> str:
    for field in form.select("input[name]"):
        name = str(field.get("name") or "")
        field_type = str(field.get("type") or "").lower()
        if field_type == "password" or name in {"code", "password", "token", "contest_password"}:
            return name
    return ""


def _resolve_action(base_url: str, current_path: str, action: str) -> str:
    if not action:
        return current_path
    current_url = absolute_url(base_url, current_path)
    resolved = urljoin(current_url, action)
    parsed = urlparse(resolved)
    base = urlparse(base_url)
    if parsed.scheme == base.scheme and parsed.netloc == base.netloc:
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return resolved


def _url_path(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme and not parsed.netloc:
        return url
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _languages_from_submit_context(ui: dict[str, Any]) -> list[str]:
    pdoc = ui.get("pdoc") if isinstance(ui.get("pdoc"), dict) else {}
    config = pdoc.get("config") if isinstance(pdoc.get("config"), dict) else {}
    langs = config.get("langs")
    if not isinstance(langs, list):
        return []
    return [str(item) for item in langs]


def _languages_from_select(soup: BeautifulSoup) -> list[str]:
    values: list[str] = []
    for option in soup.select('select[name="lang"] option[value]'):
        value = str(option.get("value") or "")
        if value:
            values.append(value)
    return values
