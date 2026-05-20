from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .client import HydroClient
from .parsing import choose_markdown, extract_ui_context, format_limit, rewrite_attachment_links
from .utils import absolute_url, quote_path_part


@dataclass(slots=True)
class Attachment:
    name: str
    size: int | None = None
    last_modified: int | None = None
    etag: str = ""
    download_url: str = ""
    local_path: str = ""


@dataclass(slots=True)
class Problem:
    problem_id: str
    title: str
    url: str
    statement: str
    tags: list[str]
    stats: dict[str, Any]
    reference: str | None
    config: dict[str, Any]
    limits: dict[str, Any]
    attachments: list[Attachment]


class ProblemService:
    def __init__(self, client: HydroClient) -> None:
        self.client = client

    def fetch(self, pid: str, *, page_path: str = "", use_api: bool = True) -> Problem:
        page_problem = self._fetch_from_page(pid, page_path=page_path)
        api_statement = self._fetch_api_statement(pid) if use_api else ""
        if api_statement.strip():
            statement = api_statement
        else:
            statement = page_problem.statement
        attachment_names = {item.name for item in page_problem.attachments}
        statement = rewrite_attachment_links(
            statement,
            self.client.base_url,
            pid,
            attachment_names,
        ).strip()
        page_problem.statement = statement + "\n"
        return page_problem

    def list(self, page: int = 1) -> list[dict[str, str]]:
        html = self.client.get_text("/p", params={"page": page} if page > 1 else None)
        soup = BeautifulSoup(html, "html.parser")
        problems: list[dict[str, str]] = []
        seen: set[str] = set()
        for link in soup.select('a[href^="/p/"]'):
            href = link.get("href") or ""
            match = re.fullmatch(r"/p/([^/?#]+)", href)
            if not match:
                continue
            pid = match.group(1)
            title = link.get_text(" ", strip=True)
            if not title or pid in seen:
                continue
            seen.add(pid)
            problems.append({"problem_id": pid, "title": title, "url": absolute_url(self.client.base_url, href)})
        return problems

    def pull(self, pid: str, output_dir: Path) -> Problem:
        problem = self.fetch(pid)
        problem_dir = output_dir / str(pid)
        files_dir = problem_dir / "files"
        problem_dir.mkdir(parents=True, exist_ok=True)
        files_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[Attachment] = []
        for attachment in problem.attachments:
            target = files_dir / attachment.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with self.client.stream(
                f"/p/{quote_path_part(pid)}/file/{quote_path_part(attachment.name)}?type=additional_file"
            ) as response:
                with target.open("wb") as fh:
                    for chunk in response.iter_bytes(chunk_size=1 << 16):
                        if chunk:
                            fh.write(chunk)
            attachment.local_path = str(target.relative_to(problem_dir))
            downloaded.append(attachment)

        problem.attachments = downloaded
        (problem_dir / "statement.md").write_text(render_statement(problem), encoding="utf-8")
        (problem_dir / "problem.json").write_text(
            json.dumps(problem_to_dict(problem), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return problem

    def _fetch_from_page(self, pid: str, *, page_path: str = "") -> Problem:
        quoted_pid = quote_path_part(pid)
        path = page_path or f"/p/{quoted_pid}"
        html = self.client.get_text(path)
        ui = extract_ui_context(html)
        pdoc = ui.get("pdoc") or {}
        if not isinstance(pdoc, dict):
            pdoc = {}
        config = pdoc.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        attachments: list[Attachment] = []
        for item in pdoc.get("additional_file") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("_id")
            if not name:
                continue
            attachments.append(
                Attachment(
                    name=str(name),
                    size=item.get("size") if isinstance(item.get("size"), int) else None,
                    last_modified=item.get("lastModified")
                    if isinstance(item.get("lastModified"), int)
                    else None,
                    etag=str(item.get("etag") or ""),
                    download_url=absolute_url(
                        self.client.base_url,
                        f"/p/{quoted_pid}/file/{quote_path_part(name)}?type=additional_file",
                    ),
                )
            )

        tags = pdoc.get("tag") or []
        if not isinstance(tags, list):
            tags = []
        stats = pdoc.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        return Problem(
            problem_id=str(pid),
            title=str(pdoc.get("title") or f"Problem {pid}"),
            url=absolute_url(self.client.base_url, path),
            statement=choose_markdown(pdoc.get("content")).strip() + "\n",
            tags=[str(tag) for tag in tags],
            stats=stats,
            reference=pdoc.get("reference") if isinstance(pdoc.get("reference"), str) else None,
            config=config,
            limits={
                "time_ms": {
                    "min": config.get("timeMin"),
                    "max": config.get("timeMax"),
                    "display": format_limit(config.get("timeMin"), config.get("timeMax"), "ms"),
                },
                "memory_mb": {
                    "min": config.get("memoryMin"),
                    "max": config.get("memoryMax"),
                    "display": format_limit(config.get("memoryMin"), config.get("memoryMax"), "MB"),
                },
            },
            attachments=attachments,
        )

    def _fetch_api_statement(self, pid: str) -> str:
        args = json.dumps({"id": pid}, ensure_ascii=False, separators=(",", ":"))
        try:
            data = self.client.get_json(
                "/api/problem",
                params={"args": args, "projection": "content"},
            )
        except Exception:
            return ""
        content = data.get("content") if isinstance(data, dict) else None
        return choose_markdown(content).strip() + "\n" if content is not None else ""


def problem_to_dict(problem: Problem) -> dict[str, Any]:
    data = asdict(problem)
    return data


def render_statement(problem: Problem) -> str:
    tags = ", ".join(problem.tags) if problem.tags else "-"
    time_limit = problem.limits.get("time_ms", {}).get("display") or "-"
    memory_limit = problem.limits.get("memory_mb", {}).get("display") or "-"
    header = [
        f"# {problem.problem_id}. {problem.title}",
        "",
        f"- Source: {problem.url}",
        f"- Time limit: {time_limit}",
        f"- Memory limit: {memory_limit}",
        f"- Tags: {tags}",
        "",
    ]
    return "\n".join(header) + problem.statement.lstrip("\n")
