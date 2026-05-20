from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, Tag

from .client import HydroClient
from .parsing import clean_text
from .utils import absolute_url


TERMINAL_STATUS_HINTS = {
    "Accepted",
    "Wrong Answer",
    "Time Exceeded",
    "Time Limit Exceeded",
    "Memory Limit Exceeded",
    "Runtime Error",
    "Compile Error",
    "System Error",
    "Canceled",
    "Ignored",
    "Format Error",
    "Hack Successful",
    "Hack Unsuccessful",
}

RUNNING_STATUS_HINTS = {
    "Waiting",
    "Compiling",
    "Judging",
    "Fetching",
    "Running",
}


@dataclass(slots=True)
class RecordSummary:
    record_id: str
    status: str
    score: str
    problem_id: str
    problem_title: str
    submitter: str
    time: str
    memory: str
    language: str
    submitted_at: str
    url: str


@dataclass(slots=True)
class RecordDetail:
    record_id: str
    status: str
    status_code: str
    score: str
    info: dict[str, str]
    compiler_text: str
    code: str
    url: str

    @property
    def is_done(self) -> bool:
        if self.status in RUNNING_STATUS_HINTS:
            return False
        if re.search(r"\b\d+(?:\.\d+)?%\b", self.status):
            return False
        if self.status in TERMINAL_STATUS_HINTS:
            return True
        return False


class RecordService:
    def __init__(self, client: HydroClient) -> None:
        self.client = client

    def list(self, page: int = 1, uid_or_name: str = "") -> list[RecordSummary]:
        params: dict[str, Any] = {"page": page} if page > 1 else {}
        if uid_or_name:
            params["uidOrName"] = uid_or_name
        html = self.client.get_text("/record", params=params or None)
        return parse_record_list(html, self.client.base_url)

    def show(self, rid: str) -> RecordDetail:
        html = self.client.get_text(f"/record/{rid}")
        return parse_record_detail(html, self.client.base_url, rid)

    def watch(self, rid: str, interval: float = 1.5, max_wait: float = 120.0) -> RecordDetail:
        deadline = time.monotonic() + max_wait
        last = self.show(rid)
        while not last.is_done and time.monotonic() < deadline:
            time.sleep(interval)
            last = self.show(rid)
        return last


def parse_record_list(html: str, base_url: str) -> list[RecordSummary]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.record_main__table tbody tr[data-rid]")
    records: list[RecordSummary] = []
    for row in rows:
        rid = str(row.get("data-rid") or "")
        cells = row.find_all("td")
        if len(cells) < 7 or not rid:
            continue

        status_text, score = _parse_status_cell(cells[0])
        problem_id, problem_title = _parse_problem_cell(cells[1])
        submitted_at = ""
        time_node = cells[6].select_one(".time")
        if time_node:
            submitted_at = clean_text(time_node.get_text(" ", strip=True))
        else:
            submitted_at = clean_text(cells[6].get_text(" ", strip=True))

        records.append(
            RecordSummary(
                record_id=rid,
                status=status_text,
                score=score,
                problem_id=problem_id,
                problem_title=problem_title,
                submitter=clean_text(cells[2].get_text(" ", strip=True)),
                time=clean_text(cells[3].get_text(" ", strip=True)),
                memory=clean_text(cells[4].get_text(" ", strip=True)),
                language=clean_text(cells[5].get_text(" ", strip=True)),
                submitted_at=submitted_at,
                url=absolute_url(base_url, f"/record/{rid}"),
            )
        )
    return records


def parse_record_detail(html: str, base_url: str, rid: str) -> RecordDetail:
    soup = BeautifulSoup(html, "html.parser")
    status_section = soup.select_one("#status")
    status_code = str(status_section.get("data-status") or "") if status_section else ""
    title = status_section.select_one(".section__title") if status_section else None
    status_text = clean_text(title.get_text(" ", strip=True)) if title else ""
    score = _extract_score(status_text)
    status = _strip_score(status_text, score)

    info = _parse_info_dl(soup)
    if not score:
        score = info.get("Score", "")

    compiler = soup.select_one("pre.compiler-text")
    compiler_text = clean_text(compiler.get_text("\n", strip=False)) if compiler else ""
    mask_marker = "Expand"
    if compiler_text.endswith(mask_marker):
        compiler_text = compiler_text[: -len(mask_marker)].rstrip()

    code_node = soup.select_one("pre.line-numbers code")
    code = code_node.get_text("", strip=False) if code_node else ""

    return RecordDetail(
        record_id=rid,
        status=status,
        status_code=status_code,
        score=score,
        info=info,
        compiler_text=compiler_text,
        code=code,
        url=absolute_url(base_url, f"/record/{rid}"),
    )


def _parse_status_cell(cell: Tag) -> tuple[str, str]:
    text = clean_text(cell.get_text(" ", strip=True))
    score = _extract_score(text)
    return _strip_score(text, score), score


def _parse_problem_cell(cell: Tag) -> tuple[str, str]:
    link = cell.find("a")
    text = clean_text((link or cell).get_text(" ", strip=True))
    match = re.match(r"(\S+)\s+(.*)", text)
    if not match:
        return text, ""
    return match.group(1), match.group(2)


def _parse_info_dl(soup: BeautifulSoup) -> dict[str, str]:
    info: dict[str, str] = {}
    for dl in soup.select("dl.large.horizontal"):
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


def _extract_score(text: str) -> str:
    match = re.match(r"(-?\d+(?:\.\d+)?)\s+", text)
    return match.group(1) if match else ""


def _strip_score(text: str, score: str) -> str:
    if score and text.startswith(score):
        return text[len(score) :].strip()
    return text.strip()
