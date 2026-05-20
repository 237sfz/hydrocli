from __future__ import annotations

import getpass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .client import HydroClient, dump_cookies
from .config import ConfigStore
from .errors import HydroCliError
from .problem import ProblemService, render_statement
from .record import RecordDetail, RecordService
from .submit import SubmitService
from .utils import normalize_base_url


app = typer.Typer(no_args_is_help=True, help="Terminal client for Hydro OJ.")
config_app = typer.Typer(help="Manage local hydro-cli configuration.")
problem_app = typer.Typer(help="Read and pull Hydro problems.")
record_app = typer.Typer(help="Inspect Hydro submission records.")
app.add_typer(config_app, name="config")
app.add_typer(problem_app, name="problem")
app.add_typer(record_app, name="record")

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
    config.base_url = normalize_base_url(base_url)
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
    watch: Annotated[bool, typer.Option("--watch", "-w", help="Wait for final result.")] = False,
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


@problem_app.command("langs")
def problem_langs(pid: Annotated[str, typer.Argument(help="Problem id")]) -> None:
    _store, client = _load_client()
    with client:
        langs = SubmitService(client).languages(pid)
    for item in langs:
        console.print(item)


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
    with Live(console=console, refresh_per_second=4) as live:
        deadline = __import__("time").monotonic() + max_wait
        detail = service.show(rid)
        while True:
            live.update(_record_panel(detail))
            if detail.is_done or __import__("time").monotonic() >= deadline:
                return detail
            __import__("time").sleep(interval)
            detail = service.show(rid)


def _record_panel(detail: RecordDetail) -> Panel:
    score = f" score={detail.score}" if detail.score else ""
    return Panel(
        f"[bold]{detail.record_id}[/bold]\n{detail.status}{score}",
        title="Record",
    )


def _print_record_detail(detail: RecordDetail) -> None:
    console.print(_record_panel(detail))
    table = Table(show_header=False)
    table.add_column("Key")
    table.add_column("Value")
    for key, value in detail.info.items():
        table.add_row(key, value)
    if detail.info:
        console.print(table)
    if detail.compiler_text:
        console.print(Panel(detail.compiler_text, title="Compiler"))


def main() -> None:
    try:
        app()
    except HydroCliError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    main()
