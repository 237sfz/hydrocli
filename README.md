# hydro-cli

Terminal client for Hydro OJ.

This repository is currently in the first implementation pass. The initial target is a practical single-site workflow:

- configure a Hydro base URL
- log in and persist the session cookie
- inspect the current login state
- fetch problem metadata and original Markdown statements
- pull problem bundles into a local workspace
- submit code and inspect records

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

## Basic Usage

```bash
hydro config set-url http://localhost:8888
hydro login 237sfz
hydro whoami
hydro problem show 18
hydro problem pull 18
hydro submit P1000 main.cpp --lang cc.cc20o2 --watch
hydro record list
hydro record show <rid>
hydro contest list
hydro contest use <cid>
hydro contest show
hydro contest problems
hydro contest problem A
hydro contest submit A main.cpp --lang cc.cc20o2 --watch
```

Problem pulling writes:

```text
problems/
  <pid>/
    statement.md
    problem.json
    files/
```

## Notes

Hydro exposes data through a mix of generic API endpoints and embedded page context. This client follows the proven acquisition order used by the local `hydro-problem-fetcher` workflow:

- use `/api/problem` for raw statement Markdown when available
- use `/p/<pid>` and `window.UiContextNew.pdoc` for limits, tags, stats, and attachments
- use `/p/<pid>/file/<name>?type=additional_file` for attachment bytes

Contest support follows the Hydro v5 routes observed on the local instance:

- contest list and details: `/contest`, `/contest/<cid>`
- contest problem list: `/contest/<cid>/problems`
- contest problem detail and submit links: `/p/<pid>?tid=<cid>`, `/p/<pid>/submit?tid=<cid>`
- contest join: `POST /contest/<cid>` with `operation=attend`, plus `code` when an invitation code is required
- contest standings: `/contest/<cid>/scoreboard` when the contest rule makes it visible

Run `hydro contest use <cid>` to save a current contest in the local config. Contest commands still accept an explicit `<cid>`, but `show`, `problems`, `standings`, and the short submit form `hydro contest submit A main.cpp` use the saved contest when it is omitted.
