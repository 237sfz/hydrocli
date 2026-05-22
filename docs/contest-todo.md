# Contest Support Status And TODO

This file tracks the current Hydro contest support in `hydro-cli` and the remaining work after the first implementation pass.

## Current State

Implemented contest commands:

```bash
hydro contest list
hydro contest use <cid>
hydro contest current
hydro contest clear
hydro contest show [cid]
hydro contest join [cid] [--password ...]
hydro contest problems [cid]
hydro contest problem <alias-or-pid> [cid] [--raw]
hydro contest pull <alias-or-pid> [cid] [--output-dir contests]
hydro contest pull-all [cid] [--output-dir contests]
hydro contest submit <alias-or-pid> <file> [--lang ...] [--watch/--no-watch]
hydro contest submit <cid> <alias-or-pid> <file> [--lang ...] [--watch/--no-watch]
hydro contest record list [cid] [--user ...]
hydro contest record show <rid>
hydro contest record watch <rid> [--interval ...] [--max-wait ...]
hydro contest standings [cid]
```

Implemented behavior to preserve:

- `hydro contest use <cid>` saves the current contest in local config as `current_contest_id`.
- `show`, `join`, `problems`, `problem`, `pull`, `pull-all`, `submit`, `record`, and `standings` use the saved contest when `cid` is omitted.
- `hydro contest join <cid>` saves the joined contest as current after success.
- `hydro config set-url` clears the saved current contest when the base URL changes.
- Contest aliases such as `A`, `B`, `C` resolve through `/contest/<cid>/problems`.
- Contest problem viewing and pulling use the contest context path `/p/<pid>?tid=<cid>`.
- Contest attachment downloads use `/p/<pid>/file/<name>?type=additional_file&tid=<cid>`.
- Contest `pull-all` pulls every visible contest problem under `contests/<cid>/`.
- Contest submission uses the parsed or inferred path `/p/<pid>/submit?tid=<cid>`.
- Contest self records are parsed from the `Submissions` table on `/contest/<cid>/problems`, which matches HydroOJ's in-contest self-record visibility rules.
- Contest record detail and watch use `/record/<rid>`; HydroOJ derives contest permissions from the record itself.
- Normal `hydro submit`, `hydro problem show`, and `hydro problem pull` behavior is unchanged.

Example local verification target:

- Hydro base URL: `https://hydro.example.com`
- Example contest: `<contest-title>`
- Example contest id: `<cid>`
- Example first problem alias/pid: `A` / `<pid>`
- Example first problem solution path used for smoke tests: `/tmp/solution.cpp`

Do not store Hydro passwords in repository files.

## Route Assumptions

Observed on local Hydro v5.0.1:

- Contest list: `GET /contest`
- Contest detail: `GET /contest/<cid>`
- Contest join: `POST /contest/<cid>` with `operation=attend`; invitation code uses `code`.
- Contest problem list: `GET /contest/<cid>/problems`
- Contest problem detail: `GET /p/<pid>?tid=<cid>`
- Contest problem submit page: `GET /p/<pid>/submit?tid=<cid>`
- Contest problem submit action: `POST /p/<pid>/submit?tid=<cid>` with multipart fields `lang` and `code`.
- Contest attachment download: `GET /p/<pid>/file/<name>?type=additional_file&tid=<cid>`
- Contest self record list: `GET /contest/<cid>/problems`, parse the `Submissions` table.
- Contest record list for explicit `--user`: `GET /record?tid=<cid>&uidOrName=...` when Hydro's scoreboard visibility permits it.
- Contest record detail: `GET /record/<rid>`
- Contest scoreboard: `GET /contest/<cid>/scoreboard` when visible under the contest rule.

Known local behavior:

- The sample `IOI(Strict)` contest hides standings while running. `hydro contest standings` should report the Hydro 403 as a user-facing unavailable message.
- `hydro record watch` still uses polling rather than websocket.

## Verification Commands

Run before finishing contest-related changes:

```bash
. .venv/bin/activate
pytest
ruff check .
```

Local smoke test pattern:

```bash
export HYDRO_CLI_CONFIG_DIR="$(mktemp -d)"
hydro config set-url https://hydro.example.com
hydro login <username>
hydro contest list
hydro contest use <cid>
hydro contest current
hydro contest problems
hydro contest problem A --raw
hydro contest pull A --output-dir "$(mktemp -d)"
hydro contest pull-all --output-dir "$(mktemp -d)"
hydro contest submit A /tmp/solution.cpp --lang cc.cc20o2 --no-watch
hydro contest submit <cid> A /tmp/solution.cpp --lang cc.cc20o2 --no-watch
hydro contest record list
hydro contest record show <rid>
hydro contest record watch <rid> --max-wait 5
hydro contest clear
```

For `standings`, use the local sample only to confirm the user-facing 403 path while it is running:

```bash
hydro contest standings <cid>
```

## Next TODO

High priority:

- Add contest-aware `langs` command, for example `hydro contest langs A`, using `/p/<pid>/submit?tid=<cid>`.
- Improve `standings` parsing against real visible scoreboard HTML from an ended or non-strict contest.

Medium priority:

- Add structured output options for standings and problems, probably `--json` first. CSV can come later if there is a concrete workflow.
- Cache contest problem alias mappings only if repeated network calls become a real usability or performance issue. Current behavior deliberately fetches live data.
- Improve contest join feedback by parsing Hydro error text for wrong invitation code, contest ended, or not started.

Low priority:

- Investigate websocket support for record watching. Polling is currently good enough and simpler.
- Consider a safer script mode with `--no-current` or explicit-current checks if users frequently work across multiple contests.
- Add documentation screenshots or terminal transcripts after the command output format stabilizes.

## Recently Completed

- Added `hydro contest record list/show/watch` shortcuts; self record listing uses the contest problem page so in-contest visible submissions work under HydroOJ's `canShowSelfRecord` rules.
- Added first-pass contest service and CLI commands.
- Added persistent current contest support.
- Added contest problem statement viewing.
- Added contest problem pulling with contest-context attachment downloads.
- Added contest `pull-all` for pulling every visible contest problem.
- Added CliRunner coverage for optional current-contest behavior on contest commands.
- Added pulled statement `File IO` metadata from Hydro `subType`.
- Added user guide at `docs/user-guide.md`, including persistent `pipx` installation and update workflow.
