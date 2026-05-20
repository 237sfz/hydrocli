from __future__ import annotations

import getpass
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .client import HydroClient, dump_cookies
from .config import Config, ConfigStore
from .contest import ContestDetail, ContestProblem, ContestService, ContestStanding
from .errors import HydroCliError
from .problem import ProblemService, render_statement
from .record import RecordDetail, RecordService
from .submit import SubmitService
from .utils import normalize_base_url


app = typer.Typer(no_args_is_help=True, help="Terminal client for Hydro OJ.")
config_app = typer.Typer(help="Manage local hydro-cli configuration.")
problem_app = typer.Typer(help="Read and pull Hydro problems.")
record_app = typer.Typer(help="Inspect Hydro submission records.")
contest_app = typer.Typer(help="Work with Hydro contests.")
app.add_typer(config_app, name="config")
app.add_typer(problem_app, name="problem")
app.add_typer(record_app, name="record")
app.add_typer(contest_app, name="contest")

console = Console()


def _store() -> ConfigStore:
    return ConfigStore()


def _load_client() -> tuple[ConfigStore, HydroClient]:
    store = _store()
    config = store.load()
    return store, HydroClient(config)


@config_app.command("set-url")
def config_set_url(base_url: Annotated[str, typer.Argument(help="Hydro base URL")]) -> None:
    store = _store()
    config = store.load()
    new_base_url = normalize_base_url(base_url)
    if new_base_url != config.base_url:
        config.current_contest_id = ""
    config.base_url = new_base_url
    store.save(config)
    console.print(f"Base URL set to [bold]{config.base_url}[/bold]")


@config_app.command("show")
def config_show() -> None:
    config = _store().load()
    table = Table(show_header=False)
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("base_url", config.base_url)
    table.add_row("default_language", config.default_language or "-")
    table.add_row("current_contest_id", config.current_contest_id or "-")
    table.add_row("username", config.username or "-")
    table.add_row("uid", config.uid or "-")
    table.add_row("session", "present" if config.is_logged_in else "-")
    console.print(table)


@app.command()
def login(
    username: Annotated[str, typer.Argument(help="Hydro username")],
    password: Annotated[
        str | None,
        typer.Option("--password", "-p", help="Hydro password. Prompted when omitted."),
    ] = None,
) -> None:
    store = _store()
    config = store.load()
    secret = password if password is not None else getpass.getpass("Password: ")
    with HydroClient(config) as client:
        user = client.login(username, secret)
        config.cookies = dump_cookies(client.client)
        config.username = user.get("username") or username
        config.uid = user.get("uid") or ""
        store.save(config)
    uid_text = f" (uid {config.uid})" if config.uid else ""
    console.print(f"Logged in as [bold]{config.username}[/bold]{uid_text}")


@app.command()
def logout() -> None:
    store = _store()
    config = store.load()
    with HydroClient(config) as client:
        try:
            client.logout()
        except HydroCliError:
            pass
    store.clear_session()
    console.print("Logged out")


@app.command()
def whoami() -> None:
    store, client = _load_client()
    config = store.load()
    with client:
        user = client.whoami()
        if user.get("username"):
            config.username = user["username"]
            config.uid = user.get("uid") or ""
            config.cookies = dump_cookies(client.client)
            store.save(config)
            uid_text = f" (uid {config.uid})" if config.uid else ""
            console.print(f"[bold]{config.username}[/bold]{uid_text}")
        else:
            console.print("[red]error:[/red] not logged in")
            raise typer.Exit(1)


@problem_app.command("list")
def problem_list(
    page: Annotated[int, typer.Option("--page", "-p", min=1, help="Problem list page.")] = 1,
) -> None:
    _store, client = _load_client()
    with client:
        problems = ProblemService(client).list(page=page)
    table = Table("PID", "Title", "URL")
    for item in problems:
        table.add_row(item["problem_id"], item["title"], item["url"])
    console.print(table)


@problem_app.command("show")
def problem_show(
    pid: Annotated[str, typer.Argument(help="Problem id")],
    raw: Annotated[bool, typer.Option("--raw", help="Print raw Markdown.")] = False,
) -> None:
    _store, client = _load_client()
    with client:
        problem = ProblemService(client).fetch(pid)
    markdown = render_statement(problem)
    if raw:
        console.print(markdown, markup=False)
    else:
        console.print(Markdown(markdown))


@problem_app.command("pull")
def problem_pull(
    pid: Annotated[str, typer.Argument(help="Problem id")],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory for pulled problems."),
    ] = Path("problems"),
) -> None:
    _store, client = _load_client()
    with client:
        problem = ProblemService(client).pull(pid, output_dir)
    target = output_dir / str(pid)
    console.print(
        f"Pulled [bold]{problem.problem_id}[/bold] {problem.title} -> [bold]{target}[/bold] "
        f"({len(problem.attachments)} attachment(s))"
    )


@app.command()
def submit(
    pid: Annotated[str, typer.Argument(help="Problem id")],
    source: Annotated[Path, typer.Argument(help="Source file to submit")],
    lang: Annotated[
        str,
        typer.Option("--lang", "-l", help="Hydro language id. Inferred from extension when omitted."),
    ] = "",
    watch: Annotated[bool, typer.Option("--watch/--no-watch", help="Wait for final result.")] = True,
) -> None:
    if not source.exists():
        raise HydroCliError(f"source file not found: {source}")
    _store, client = _load_client()
    with client:
        rid = SubmitService(client).submit(pid, source, lang)
        console.print(f"Submitted [bold]{pid}[/bold] -> [bold]{rid}[/bold]")
        if watch:
            detail = _watch_record(client, rid)
            _print_record_detail(detail)
        else:
            console.print(f"Use [bold]hydro record watch {rid}[/bold] to wait for the result.")


@problem_app.command("langs")
def problem_langs(pid: Annotated[str, typer.Argument(help="Problem id")]) -> None:
    _store, client = _load_client()
    with client:
        langs = SubmitService(client).languages(pid)
    for item in langs:
        console.print(item)


@contest_app.command("list")
def contest_list(
    page: Annotated[int, typer.Option("--page", "-p", min=1, help="Contest list page.")] = 1,
) -> None:
    _store, client = _load_client()
    with client:
        contests = ContestService(client).list(page=page)
    table = Table("ID", "Title", "Rule", "Status", "Start", "Duration", "Rated", "Partic.", "URL")
    for item in contests:
        table.add_row(
            item.contest_id,
            item.title,
            item.rule or "-",
            item.status or "-",
            item.start or "-",
            item.duration or "-",
            "yes" if item.rated else "-",
            item.participants or "-",
            item.url,
        )
    console.print(table)


@contest_app.command("use")
def contest_use(cid: Annotated[str, typer.Argument(help="Contest id")]) -> None:
    store, client = _load_client()
    config = store.load()
    with client:
        detail = ContestService(client).show(cid)
    _save_current_contest(store, config, detail.contest_id)
    console.print(f"Current contest set to [bold]{detail.contest_id}[/bold] {detail.title}")


@contest_app.command("current")
def contest_current() -> None:
    store, client = _load_client()
    config = store.load()
    cid = _current_contest_id(config, None)
    with client:
        detail = ContestService(client).show(cid)
    _print_contest_detail(detail)


@contest_app.command("clear")
def contest_clear() -> None:
    store = _store()
    config = store.load()
    old = config.current_contest_id
    config.current_contest_id = ""
    store.save(config)
    if old:
        console.print(f"Cleared current contest [bold]{old}[/bold]")
    else:
        console.print("No current contest was set")


@contest_app.command("show")
def contest_show(
    cid: Annotated[str | None, typer.Argument(help="Contest id. Uses current contest when omitted.")] = None,
) -> None:
    store, client = _load_client()
    config = store.load()
    cid = _current_contest_id(config, cid)
    with client:
        detail = ContestService(client).show(cid)
    _print_contest_detail(detail)


@contest_app.command("join")
def contest_join(
    cid: Annotated[str | None, typer.Argument(help="Contest id. Uses current contest when omitted.")] = None,
    password: Annotated[
        str,
        typer.Option("--password", "-p", help="Contest invitation code/password."),
    ] = "",
) -> None:
    store, client = _load_client()
    config = store.load()
    cid = _current_contest_id(config, cid)
    with client:
        detail = ContestService(client).join(cid, password=password)
        config.cookies = dump_cookies(client.client)
        config.current_contest_id = detail.contest_id
        store.save(config)
    console.print(f"Joined [bold]{detail.title}[/bold] ({detail.contest_id})")
    _print_contest_detail(detail)


@contest_app.command("problems")
def contest_problems(
    cid: Annotated[str | None, typer.Argument(help="Contest id. Uses current contest when omitted.")] = None,
) -> None:
    store, client = _load_client()
    config = store.load()
    cid = _current_contest_id(config, cid)
    with client:
        problems = ContestService(client).problems(cid)
    console.print(_contest_problems_table(problems))


@contest_app.command("problem")
def contest_problem(
    problem: Annotated[str, typer.Argument(help="Contest alias or problem id")],
    cid: Annotated[str | None, typer.Argument(help="Contest id. Uses current contest when omitted.")] = None,
    raw: Annotated[bool, typer.Option("--raw", help="Print raw Markdown.")] = False,
) -> None:
    store, client = _load_client()
    config = store.load()
    cid = _current_contest_id(config, cid)
    with client:
        fetched = ContestService(client).problem(cid, problem)
    markdown = render_statement(fetched)
    if raw:
        console.print(markdown, markup=False)
    else:
        console.print(Markdown(markdown))


@contest_app.command("pull")
def contest_pull(
    problem: Annotated[str, typer.Argument(help="Contest alias or problem id")],
    cid: Annotated[str | None, typer.Argument(help="Contest id. Uses current contest when omitted.")] = None,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory for pulled contest problems."),
    ] = Path("contests"),
) -> None:
    store, client = _load_client()
    config = store.load()
    cid = _current_contest_id(config, cid)
    with client:
        pulled = ContestService(client).pull(cid, problem, output_dir)
    target = output_dir / cid / pulled.problem_id
    console.print(
        f"Pulled contest [bold]{cid}[/bold] problem [bold]{pulled.problem_id}[/bold] "
        f"{pulled.title} -> [bold]{target}[/bold] ({len(pulled.attachments)} attachment(s))"
    )


@contest_app.command("submit")
def contest_submit(
    first: Annotated[str, typer.Argument(help="Problem alias, or contest id in legacy form.")],
    second: Annotated[str, typer.Argument(help="Source file, or problem alias in legacy form.")],
    third: Annotated[
        Path | None,
        typer.Argument(help="Source file in legacy form: <cid> <problem> <file>."),
    ] = None,
    lang: Annotated[
        str,
        typer.Option("--lang", "-l", help="Hydro language id. Inferred from extension when omitted."),
    ] = "",
    watch: Annotated[bool, typer.Option("--watch/--no-watch", help="Wait for final result.")] = True,
) -> None:
    store, client = _load_client()
    config = store.load()
    cid, problem, source = _resolve_contest_submit_args(config, first, second, third)
    if not source.exists():
        raise HydroCliError(f"source file not found: {source}")
    with client:
        submission = ContestService(client).submit(cid, problem, source, lang)
        target = submission.target
        label = target.problem.alias or target.problem.problem_id
        console.print(
            f"Submitted [bold]{cid}[/bold] [bold]{label}[/bold] "
            f"({target.problem.problem_id}) -> [bold]{submission.record_id}[/bold]"
        )
        if watch:
            detail = _watch_record(client, submission.record_id)
            _print_record_detail(detail)
        else:
            console.print(
                f"Use [bold]hydro record watch {submission.record_id}[/bold] "
                "to wait for the result."
            )


@contest_app.command("standings")
def contest_standings(
    cid: Annotated[str | None, typer.Argument(help="Contest id. Uses current contest when omitted.")] = None,
) -> None:
    store, client = _load_client()
    config = store.load()
    cid = _current_contest_id(config, cid)
    with client:
        standings = ContestService(client).standings(cid)
    _print_contest_standings(standings)


@record_app.command("list")
def record_list(
    page: Annotated[int, typer.Option("--page", "-p", min=1, help="Record list page.")] = 1,
    uid_or_name: Annotated[str, typer.Option("--user", "-u", help="Filter by user id/name.")] = "",
) -> None:
    store, client = _load_client()
    config = store.load()
    if not uid_or_name and config.uid:
        uid_or_name = config.uid
    with client:
        records = RecordService(client).list(page=page, uid_or_name=uid_or_name)
    table = Table("RID", "Status", "Score", "Problem", "Time", "Memory", "Language", "Submit At")
    for item in records:
        table.add_row(
            item.record_id,
            item.status,
            item.score or "-",
            f"{item.problem_id} {item.problem_title}".strip(),
            item.time,
            item.memory,
            item.language,
            item.submitted_at,
        )
    console.print(table)


@record_app.command("show")
def record_show(rid: Annotated[str, typer.Argument(help="Record id")]) -> None:
    _store, client = _load_client()
    with client:
        detail = RecordService(client).show(rid)
    _print_record_detail(detail)


@record_app.command("watch")
def record_watch(
    rid: Annotated[str, typer.Argument(help="Record id")],
    interval: Annotated[float, typer.Option("--interval", min=0.5, help="Polling interval.")] = 1.5,
    max_wait: Annotated[float, typer.Option("--max-wait", help="Maximum wait seconds.")] = 120.0,
) -> None:
    _store, client = _load_client()
    with client:
        detail = _watch_record(client, rid, interval=interval, max_wait=max_wait)
    _print_record_detail(detail)


def _watch_record(
    client: HydroClient,
    rid: str,
    interval: float = 1.5,
    max_wait: float = 120.0,
) -> RecordDetail:
    service = RecordService(client)
    with Live(console=console, auto_refresh=False, refresh_per_second=1, transient=True) as live:
        deadline = time.monotonic() + max_wait
        detail = service.show(rid)
        last_signature = ""
        while True:
            signature = _record_live_signature(detail)
            if signature != last_signature:
                live.update(_record_live_view(detail), refresh=True)
                last_signature = signature
            if detail.is_done or time.monotonic() >= deadline:
                return detail
            time.sleep(interval)
            detail = service.show(rid)


def _record_panel(detail: RecordDetail) -> Panel:
    score = f" score={detail.score}" if detail.score else ""
    return Panel(
        f"[bold]{detail.record_id}[/bold]\n{detail.status}{score}",
        title="Record",
    )


def _record_live_view(detail: RecordDetail) -> Group:
    parts = [_record_panel(detail)]
    info_table = _record_info_table(detail)
    if info_table:
        parts.append(info_table)
    if detail.cases:
        parts.append(_record_cases_table(detail, limit=18, final=False))
    if detail.compiler_text and detail.status == "Compile Error":
        parts.append(Panel(_truncate(detail.compiler_text, 1200), title="Compiler"))
    return Group(*parts)


def _record_live_signature(detail: RecordDetail) -> str:
    return repr(
        (
            detail.status,
            detail.score,
            tuple(detail.info.items()),
            tuple(tuple(item.items()) for item in detail.cases),
            detail.compiler_text if detail.status == "Compile Error" else "",
        )
    )


def _current_contest_id(config: Config, explicit_cid: str | None) -> str:
    if explicit_cid:
        return explicit_cid
    if config.current_contest_id:
        return config.current_contest_id
    raise HydroCliError("contest id is required; run hydro contest use <cid> first")


def _save_current_contest(store: ConfigStore, config: Config, cid: str) -> None:
    config.current_contest_id = cid
    store.save(config)


def _resolve_contest_submit_args(
    config: Config,
    first: str,
    second: str,
    third: Path | None,
) -> tuple[str, str, Path]:
    if third is None:
        return _current_contest_id(config, None), first, Path(second)
    return first, second, third


def _print_contest_detail(detail: ContestDetail) -> None:
    table = Table(show_header=False, title="Contest")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("ID", detail.contest_id)
    table.add_row("Title", detail.title)
    table.add_row("Rule", detail.rule or "-")
    table.add_row("Status", detail.status or "-")
    table.add_row("Attended", "yes" if detail.attended else "no")
    table.add_row("Problems", str(len(detail.problems)) if detail.problems else detail.info.get("Problem", "-"))
    table.add_row("Standings", detail.standings_url)
    for key, value in detail.info.items():
        if key in {"Rule", "Status", "Problem"}:
            continue
        table.add_row(key, value)
    console.print(table)


def _contest_problems_table(problems: list[ContestProblem]) -> Table:
    table = Table("Alias", "PID", "Title", "Status", "Score", "Last Submit", "URL")
    for item in problems:
        table.add_row(
            item.alias or "-",
            item.problem_id,
            item.title,
            item.status or "-",
            item.score or "-",
            item.last_submit_at or "-",
            item.url,
        )
    return table


def _print_contest_standings(standing: ContestStanding) -> None:
    max_cols = max([len(standing.headers), *(len(row) for row in standing.rows)])
    headers = standing.headers + [f"C{i + 1}" for i in range(len(standing.headers), max_cols)]
    table = Table(*headers, title="Standings")
    for row in standing.rows:
        table.add_row(*(row + [""] * (max_cols - len(row))))
    console.print(table)


def _print_record_detail(detail: RecordDetail) -> None:
    console.print(_record_panel(detail))
    info_table = _record_info_table(detail)
    if info_table:
        console.print(info_table)
    if detail.cases:
        console.print(_record_cases_table(detail, limit=0, final=True))
    if detail.compiler_text:
        console.print(Panel(detail.compiler_text, title="Compiler"))


def _record_info_table(detail: RecordDetail) -> Table | None:
    if not detail.info:
        return None
    wanted = [
        "Submit By",
        "Problem",
        "Language",
        "Code Length",
        "Submit At",
        "Judged At",
        "Score",
        "Total Time",
        "Peak Time",
        "Peak Memory",
    ]
    table = Table(show_header=False)
    table.add_column("Key")
    table.add_column("Value")
    added = False
    for key in wanted:
        value = detail.info.get(key)
        if value:
            table.add_row(key, value)
            added = True
    for key, value in detail.info.items():
        if key not in wanted:
            table.add_row(key, value)
            added = True
    return table if added else None


def _record_cases_table(detail: RecordDetail, limit: int, final: bool) -> Table:
    rows = _build_case_rows(detail.cases, final=final)
    if limit > 0 and len(rows) > limit:
        head = max(1, limit // 2)
        tail = max(1, limit - head - 1)
        rows = (
            rows[:head]
            + [{"subtask": "...", "case": "...", "status": "...", "score": "", "time": "", "memory": "", "message": ""}]
            + rows[-tail:]
        )
    table = Table("Subtask", "ID", "Status", "Score", "Time", "Memory", "Message", title="Details")
    for item in rows:
        table.add_row(
            item.get("subtask", ""),
            item.get("case", ""),
            item.get("status", ""),
            item.get("score", ""),
            item.get("time", ""),
            item.get("memory", ""),
            _truncate(item.get("message", ""), 80),
        )
    return table


def _build_case_rows(cases: list[dict[str, str]], final: bool) -> list[dict[str, str]]:
    groups: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for item in cases:
        case_id = item.get("case", "")
        if _is_subtask_case(case_id):
            current = {"summary": item, "children": []}
            groups.append(current)
            continue
        parent = _parent_subtask(case_id)
        if current is None or _case_key(current["summary"]) != parent:
            summary = {
                "case": parent or case_id,
                "status": "",
                "score": "",
                "time": "",
                "memory": "",
                "message": "",
            }
            current = {"summary": summary, "children": []}
            groups.append(current)
        children = current["children"]
        assert isinstance(children, list)
        children.append(item)

    rows: list[dict[str, str]] = []
    for group in groups:
        summary = group["summary"]
        children = group["children"]
        assert isinstance(summary, dict)
        assert isinstance(children, list)
        rows.append(_format_case_row(summary, subtask=_case_key(summary), is_child=False))
        if final and _case_passed(summary):
            continue
        for child in children:
            if final and _case_cancelled(child):
                continue
            rows.append(_format_case_row(child, subtask="", is_child=True))
    return rows


def _format_case_row(item: dict[str, str], subtask: str, is_child: bool) -> dict[str, str]:
    case_id = item.get("case", "")
    if is_child:
        case_id = f"  {case_id}"
    return {
        "subtask": subtask,
        "case": case_id,
        "status": item.get("status", ""),
        "score": item.get("score", ""),
        "time": item.get("time", ""),
        "memory": item.get("memory", ""),
        "message": item.get("message", ""),
    }


def _is_subtask_case(case_id: str) -> bool:
    return bool(case_id.startswith("#") and "-" not in case_id)


def _parent_subtask(case_id: str) -> str:
    return case_id.split("-", 1)[0] if case_id.startswith("#") else ""


def _case_key(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    case_id = str(item.get("case") or "")
    return _parent_subtask(case_id) or case_id


def _case_passed(item: dict[str, str]) -> bool:
    return item.get("status") == "Accepted"


def _case_cancelled(item: dict[str, str]) -> bool:
    return item.get("status") in {"Canceled", "Cancelled"}


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def main() -> None:
    try:
        app()
    except HydroCliError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
