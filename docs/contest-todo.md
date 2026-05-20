# Contest Feature TODO

This file is the handoff note for continuing `hydro-cli` with Hydro contest support.

## Copy-Paste Prompt For A New Session

```text
Continue developing the Hydro CLI in /home/zfs732/hydrocli.

Current state:
- Git repo is initialized and clean.
- Latest known commit: 3cc6264 Reduce live record redraw flicker.
- Implemented commands: config, login, logout, whoami, problem list/show/pull/langs, submit, record list/show/watch.
- Submit uses POST /p/<pid>/submit with multipart fields lang and code.
- Record watch polls GET /record/<rid>, parses #status and record_detail__table, defaults to watch, and shows live grouped details.
- Local Hydro is at http://localhost:8888.
- Test account: username 237sfz. Ask me for the password if needed, or use the existing one if it is already in context.
- Existing verification commands: . .venv/bin/activate && pytest && ruff check .

Goal:
Add contest support to hydro-cli.

Implement conservative first-pass contest commands:
- hydro contest list
- hydro contest show <cid>
- hydro contest join <cid> [--password ...]
- hydro contest problems <cid>
- hydro contest submit <cid> <problem> <file> [--lang ...] [--watch/--no-watch]
- hydro contest standings <cid>

Use existing project patterns:
- Add src/hydro_cli/contest.py for service/parsing logic.
- Register a contest Typer app in src/hydro_cli/cli.py.
- Keep HTTP behavior in HydroClient.
- Use BeautifulSoup for HTML parsing and existing extract_ui_context/extract_user_context helpers when page context is useful.
- Add focused tests with HTML fixtures/snippets under tests/.
- Run pytest and ruff check before finishing.

Important constraints:
- Do not rewrite unrelated submit/record/problem code unless needed.
- Do not store passwords in files.
- Keep commands useful with the local Hydro v5.0.1 instance first.
- If Hydro contest routes require different endpoint details, inspect live pages with curl or Playwright and document the route assumptions in this file or README.
```

## Current CLI Surface

Already implemented:

```bash
hydro config set-url http://localhost:8888
hydro login 237sfz
hydro whoami

hydro problem list
hydro problem show P1000 --raw
hydro problem pull P1000
hydro problem langs P1000

hydro submit P1000 main.cpp --lang cc.cc20o2
hydro submit P1000 main.cpp --lang cc.cc20o2 --no-watch

hydro record list
hydro record show <rid>
hydro record watch <rid>
```

Behavior to preserve:

- `hydro submit` defaults to watching the record.
- `hydro record watch` uses polling, not websocket yet.
- Final record details are grouped as `Subtask > ID`.
- Accepted subtasks are collapsed in final output.
- Cancelled child cases are hidden in final output.

## Target Contest Commands

### `hydro contest list`

Purpose:

- Show available contests from `/contest`.

Suggested columns:

- ID
- Title
- Rule
- Status
- Start
- Duration
- Rated
- URL

Implementation notes:

- Parse `/contest` cards/list items.
- Extract contest id from `/contest/<cid>`.
- Include active, upcoming, and ended contests if visible.
- Add `--page` if Hydro paginates contest list.

### `hydro contest show <cid>`

Purpose:

- Show contest metadata and current user participation state.

Suggested fields:

- Title
- Rule
- Start/end time
- Duration
- Status: upcoming/running/ended
- Registered/attended state
- Problem count
- Standings URL

Implementation notes:

- Fetch `/contest/<cid>`.
- Parse `window.UiContextNew` if it exposes `tdoc`, `pdict`, `problems`, `attend`, or similar fields.
- Otherwise parse visible HTML sections first.

### `hydro contest join <cid> [--password ...]`

Purpose:

- Enter/register/attend a contest.

Implementation notes:

- Inspect the contest page for form action/method and field names.
- Common possibilities:
  - simple POST to `/contest/<cid>` or `/contest/<cid>/attend`
  - password field for protected contests
  - button text such as `Attend`, `Register`, `Join`
- Use `follow_redirects=False` first so success/failure can be detected by Location/status.
- After joining, re-fetch `contest show` and verify the page says attended/registered.

Edge cases:

- Contest has not started.
- Contest has ended.
- Already joined.
- Password required/missing/incorrect.
- User not logged in.

### `hydro contest problems <cid>`

Purpose:

- List contest problems and their contest aliases.

Suggested columns:

- Alias: A/B/C or Hydro-specific id
- PID
- Title
- Status/Score if visible
- URL

Implementation notes:

- Fetch `/contest/<cid>`.
- Parse problem links. Hydro may show contest problem links as:
  - `/contest/<cid>/p/<pid>`
  - `/p/<pid>?contest=<cid>`
  - plain `/p/<pid>` inside contest page
- Preserve both contest alias and real pid where possible.

### `hydro contest submit <cid> <problem> <file> [--lang ...]`

Purpose:

- Submit inside a contest, then watch the returned record.

Implementation notes:

- First inspect the contest problem submit page.
- Candidate routes to verify:
  - `/contest/<cid>/p/<pid>/submit`
  - `/p/<pid>/submit?contest=<cid>`
  - `/p/<pid>/submit` with hidden contest fields
- Parse the contest problem page/form rather than guessing.
- Reuse existing `SubmitService` where possible by allowing a custom submit path.
- Preserve normal `submit` behavior:
  - default watch
  - `--no-watch`
  - record details table

Problem argument behavior:

- Accept both contest alias and pid if feasible.
- If user passes alias `A`, resolve through `hydro contest problems <cid>`.
- If user passes a real pid, submit directly once route is known.

### `hydro contest standings <cid>`

Purpose:

- Show contest ranking.

Suggested columns:

- Rank
- User
- Score/Total
- Penalty/time if visible
- Per-problem scores if visible

Implementation notes:

- Inspect routes:
  - `/contest/<cid>/rank`
  - `/contest/<cid>/ranking`
  - standings embedded in `/contest/<cid>`
- Start with visible HTML table parsing.
- Do not overfit to one table layout; keep parser tolerant.

## Suggested Code Structure

Add:

```text
src/hydro_cli/contest.py
tests/test_contest.py
```

Possible data classes:

```python
@dataclass(slots=True)
class ContestSummary:
    contest_id: str
    title: str
    rule: str
    status: str
    start: str
    duration: str
    url: str

@dataclass(slots=True)
class ContestDetail:
    contest_id: str
    title: str
    rule: str
    status: str
    info: dict[str, str]
    problems: list[ContestProblem]
    url: str

@dataclass(slots=True)
class ContestProblem:
    alias: str
    problem_id: str
    title: str
    status: str
    score: str
    url: str
```

Likely service methods:

```python
class ContestService:
    def list(self, page: int = 1) -> list[ContestSummary]: ...
    def show(self, cid: str) -> ContestDetail: ...
    def join(self, cid: str, password: str = "") -> ContestDetail: ...
    def problems(self, cid: str) -> list[ContestProblem]: ...
    def standings(self, cid: str) -> ContestStanding: ...
```

For contest submit, either:

- Add `SubmitService.submit_to_path(submit_path, source_path, lang)`, or
- Add `SubmitService.submit(pid, source_path, lang="", submit_path=None)`.

Keep normal problem submit unchanged for users.

## Live Route Discovery Checklist

Use a temporary cookie jar or isolated CLI config. Do not commit credentials.

Useful shell pattern:

```bash
jar="$(mktemp)"
curl -sS -c "$jar" -X POST http://localhost:8888/login \
  --data-urlencode uname=237sfz \
  --data-urlencode 'password=ASK_OR_USE_CONTEXT_PASSWORD' \
  --data-urlencode rememberme=on \
  --data-urlencode tfa= \
  --data-urlencode authnChallenge= \
  --data-urlencode login_submit=submit \
  -o /dev/null

curl -sS -b "$jar" http://localhost:8888/contest | sed -n '1,260p'
curl -sS -b "$jar" http://localhost:8888/contest/<cid> | sed -n '1,320p'
```

Useful grep patterns:

```bash
rg -n "UiContextNew|UserContext|contest|attend|join|register|stand|rank|problem|submit|form|input|select|textarea|data-" /tmp/page.html
```

Use Playwright if button-driven UI behavior is unclear:

```bash
bash ~/.codex/skills/playwright/scripts/playwright_cli.sh open http://localhost:8888/contest
bash ~/.codex/skills/playwright/scripts/playwright_cli.sh snapshot
```

## Tests To Add

Add parser unit tests before or alongside implementation:

- Parse contest list item/card with id, title, rule, duration.
- Parse contest detail metadata.
- Parse contest problem table/list with aliases.
- Parse standings table.
- Resolve alias to pid.
- Join form parser detects password field.

Keep tests based on small HTML snippets unless real saved fixtures become necessary.

## End-To-End Validation

Minimum local validation:

```bash
. .venv/bin/activate
pytest
ruff check .

export HYDRO_CLI_CONFIG_DIR="$(mktemp -d)"
hydro config set-url http://localhost:8888
hydro login 237sfz
hydro contest list
hydro contest show <cid>
hydro contest problems <cid>
hydro contest standings <cid>
```

If a contest is currently joinable and has a safe test problem:

```bash
hydro contest join <cid>
hydro contest submit <cid> <alias-or-pid> /tmp/foo.cpp --lang cc.cc20o2
```

Do not use a real high-stakes contest for destructive testing unless explicitly requested.

## Open Questions

- Decided: `hydro contest use <cid>` sets a current contest in the local config. Commands still accept explicit `<cid>` for scripts, and `hydro contest submit <problem> <file>` uses the saved contest.
- Should standings support export formats such as `--json` or `--csv`?
- Should contest problem aliases be cached locally after `hydro contest problems <cid>`?
- Should websocket support be added for record watch before contest submit, or is polling enough for now?
