# hydro-cli User Guide

This guide describes a practical long-term workflow for using `hydro-cli` as a regular Hydro OJ user.

## First-Time Setup

For long-term use across new shells, install the command with `pipx`:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install -e /path/to/hydrocli
```

Open a new shell after `pipx ensurepath`, then verify:

```bash
hydro --help
```

This gives you a persistent `hydro` command while still using the editable source tree at `/path/to/hydrocli`.

If you only want to run from this repository without a persistent command, use the local virtualenv:

```bash
cd /path/to/hydrocli
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

That activation only affects the current shell. In a new shell, either activate again:

```bash
cd /path/to/hydrocli
. .venv/bin/activate
hydro --help
```

or call the script directly:

```bash
/path/to/hydrocli/.venv/bin/hydro --help
```

Point the CLI at your Hydro site and log in:

```bash
hydro config set-url https://hydro.example.com
hydro login <username>
hydro whoami
```

The login command stores your session cookie in the local config directory. The password is not stored.

Check current configuration at any time:

```bash
hydro config show
```

If you switch to another Hydro site with `hydro config set-url`, the saved current contest is cleared so you do not accidentally submit to a contest from a different site.

## Updating

If you installed with `pipx install -e /path/to/hydrocli`, update the source tree and reinstall dependencies when they change:

```bash
cd /path/to/hydrocli
git pull
pipx reinstall hydro-cli
hydro --help
```

If `pipx reinstall hydro-cli` cannot find the original editable source, do a clean reinstall:

```bash
pipx uninstall hydro-cli
pipx install -e /path/to/hydrocli
```

For the local virtualenv workflow:

```bash
cd /path/to/hydrocli
git pull
. .venv/bin/activate
python -m pip install -e ".[dev]"
hydro --help
```

Your Hydro config, login session, and current contest live outside the repository under your user config directory, so normal code updates do not erase them.

## Daily Problem Workflow

Find and inspect problems:

```bash
hydro problem list
hydro problem show <pid>
hydro problem show <pid> --raw
hydro problem langs <pid>
```

Pull a full local copy of a problem statement and attachments:

```bash
hydro problem pull <pid>
```

Pulled problems are written as:

```text
problems/
  <pid>/
    statement.md
    problem.json
    files/
```

Submit a normal, non-contest problem:

```bash
hydro submit <pid> main.cpp --lang cc.cc20o2
```

Submissions watch the record by default. Use `--no-watch` when you only want the record id:

```bash
hydro submit <pid> main.cpp --lang cc.cc20o2 --no-watch
```

## Contest Workflow

List available contests:

```bash
hydro contest list
```

Select the contest you are working on:

```bash
hydro contest use <cid>
hydro contest current
```

After this, most contest commands can omit the contest id:

```bash
hydro contest show
hydro contest problems
hydro contest problem A
hydro contest pull A
hydro contest standings
```

Join a contest:

```bash
hydro contest join
```

For an invitation-code contest:

```bash
hydro contest join --password <code>
```

You can still pass an explicit contest id in scripts or when switching temporarily:

```bash
hydro contest show <cid>
hydro contest problems <cid>
hydro contest join <cid>
```

Clear the saved current contest:

```bash
hydro contest clear
```

## Contest Submissions

Read a contest problem statement by alias or visible problem id:

```bash
hydro contest problem A
hydro contest problem A --raw
hydro contest problem 16
```

This command loads the problem inside the contest context, so it works for contest-hidden problems after you have attended the contest.

Pull a contest problem, including statement attachments:

```bash
hydro contest pull A
hydro contest pull A --output-dir contests
hydro contest pull-all
```

Contest pulls are written under `contests/<cid>/<alias-or-pid>/`. `pull-all` uses
the same layout and pulls every visible problem in the contest:

```text
contests/
  <cid>/
    A/
      statement.md
      problem.json
      files/
```

After setting a current contest, submit by contest alias:

```bash
hydro contest submit A main.cpp --lang cc.cc20o2
```

The old explicit form also works:

```bash
hydro contest submit <cid> A main.cpp --lang cc.cc20o2
```

The problem argument can be either the contest alias, such as `A`, `B`, `C`, or the real Hydro problem id when it is visible:

```bash
hydro contest submit A main.cpp --lang cc.cc20o2
hydro contest submit 16 main.cpp --lang cc.cc20o2
```

Like normal submissions, contest submissions watch the returned record by default. Use `--no-watch` if you want to submit and continue working immediately:

```bash
hydro contest submit A main.cpp --lang cc.cc20o2 --no-watch
```

## Records and Results

Inspect recent records:

```bash
hydro record list
```

By default, `record list` uses your saved user id after login. You can request another user explicitly if your account has permission:

```bash
hydro record list --user <uid-or-name>
```

Show or watch a record:

```bash
hydro record show <rid>
hydro record watch <rid>
```

Record output groups final test details by subtask and collapses accepted subtasks so the important failures stay visible.

Some contest rules hide standings or record details while the contest is running. In that case the CLI reports the Hydro permission error instead of inventing a local result.

## Long-Term Habits

Use a stable config directory for your normal account. Only set `HYDRO_CLI_CONFIG_DIR` when you want a temporary isolated session for testing:

```bash
export HYDRO_CLI_CONFIG_DIR="$(mktemp -d)"
```

Before a contest, run:

```bash
hydro whoami
hydro contest use <cid>
hydro contest current
hydro contest problems
hydro contest problem A
hydro contest pull A
```

During a contest, prefer the short submit form:

```bash
hydro contest submit A main.cpp --lang cc.cc20o2
```

After a contest or when switching contests, update the saved current contest:

```bash
hydro contest use <new-cid>
```

Log out on shared machines:

```bash
hydro logout
```

## Troubleshooting

If a command says login is required:

```bash
hydro login <username>
hydro whoami
```

If a contest command says the contest id is required:

```bash
hydro contest list
hydro contest use <cid>
```

If a submission says the language is required, pass `--lang` explicitly:

```bash
hydro problem langs <pid>
hydro submit <pid> main.cpp --lang cc.cc20o2
```

If standings are unavailable, the contest rule may hide the scoreboard until the contest ends.

If the CLI seems to be using the wrong site or wrong contest:

```bash
hydro config show
hydro config set-url <correct-url>
hydro contest use <correct-cid>
```
