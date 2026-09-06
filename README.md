<p align="center">
  <strong>Single-file wrapper that shrinks rdt-cli output into model-friendly lines.</strong><br>
  <a href="https://pypi.org/project/rdt-cli/"><img src="https://img.shields.io/pypi/v/rdt-cli.svg?style=flat-square" alt="rdt-cli on PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.8%2B-blue?style=flat-square" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/deps-stdlib%20only-green?style=flat-square" alt="stdlib only">
</p>

rdt-tidy runs the `rdt` binary as a subprocess. Without flags it passes output through unchanged. In `--compact` mode it converts the raw JSON response into short, positional lines, cutting token cost 27-38x on live data. It has no dependencies, uses only the standard library, and never touches credentials or caches.

## Quick start

```sh
rdt-tidy --compact sub python
rdt-tidy -c search "rust vs go" -n 8
```

## Features

- Passthrough output is byte-identical in normal mode; exit code is preserved.
- Compact-mode tables are headed; text fields are never truncated, and line breaks in bodies and comments are kept.
- Listing size limit: default 5, cap 10; `feed --subs-only` is capped at 5x5.
- Position-independent option parsing: query and text fields (including `-c`, `-nonsense`) are never confused with flags.
- Empty backend output is never silently passed through; it returns `ERR backend` with exit code 1.
- Token savings come from dropping redundant fields, not from truncating text.

## Requirements

- Python 3.8 or later (verified on 3.13.5).
- A working `rdt` install on PATH or under `~/.local/bin/` (see below).
- `uv` or `pipx` to install rdt-cli.

## Installation

### 1. Install rdt-cli

Recommended: uv tool (fast, isolated):

```sh
uv tool install rdt-cli
```

Or pipx:

```sh
pipx install rdt-cli
```

Upgrade to the latest version:

```sh
uv tool upgrade rdt-cli
# or: pipx upgrade rdt-cli
```

From source (upstream: `github.com/jackwener/rdt-cli`, requires Python 3.10+):

```sh
git clone git@github.com:jackwener/rdt-cli.git
cd rdt-cli
uv sync
uv run rdt status   # run from the clone without installing
```

Verify:

```sh
rdt status
```

Anonymous browsing works without login. Commands that need an account (`feed`, `saved`, voting) require `rdt login` first, which extracts browser cookies.

### 2. Install rdt-tidy

No build step. The file only needs to be executable:

```sh
chmod +x rdt-tidy
ln -s "$PWD/rdt-tidy" ~/.local/bin/rdt-tidy
rdt-tidy --compact sub python
```

## Usage

```sh
rdt-tidy sub python -n 5                        # normal mode, same output as rdt
rdt-tidy --compact sub python                   # 5 records, short lines
rdt-tidy -c search "rust vs go" -n 8            # 8 results
rdt-tidy -c read 1abc123                        # record + all comments
rdt-tidy -c read 1abc123 -n 100 --expand-more   # also opens closed comments
rdt-tidy -c show 3                              # 3rd record of the last listing
rdt-tidy -c export "python tips" -o tips.txt    # short lines written to a file
```

The mode flag comes before the command. A `-c`/`--compact` after the command belongs to rdt itself and is forwarded as-is. A query or text starting with a dash goes after `--`:

```sh
rdt-tidy -c search -- -c                        # "-c" is query text, not a flag
```

## CLI options

| Flag | Description |
| --- | --- |
| `--compact`, `-c` | Enables compact mode (written before the command) |
| `-h`, `--help` | Shows this help text |
| `<command> --help` | Passes through the help of that rdt command |

Every option except the mode flag is forwarded to the matching rdt command as-is. For the full rdt option list run `rdt <command> --help`.

### Command reference

| Command | Compact-mode output |
| --- | --- |
| `feed`, `popular`, `all`, `sub`, `user-posts`, `search` | Record lines + `next <cursor>` if any |
| `user-comments` | Comment lines (full body) |
| `saved`, `upvoted` | `P`-prefixed record lines, `C`-prefixed comment lines |
| `read`, `show` | Header block + all comments, single-level replies |
| `sub-info` | 3 lines: subscriber info, date, description |
| `user` | Single line: karma and account age |
| `whoami` | User line + session line |
| `status` | Passed through |
| `export` | Short lines written to a file, only a summary on stdout |
| `open`, `upvote`, `save`, `subscribe`, `comment`, `login`, `logout` | Passed through |

In compact mode, `-n` defaults to 5 and caps at 10 for every command except `read` and `show`. For `read` and `show`, `-n` goes to the backend as-is with no cap.

## Comment expansion

A default `read` makes a single request; unopened comments collapse into a `+<count> more` line. To open everything:

```sh
rdt-tidy -c read 1abc123 -n 100 --expand-more
```

`--expand-more` makes the backend send extra requests and opens closed top-level comments. If nested nodes still cannot be opened, the `+<count> more` line is kept; that line is a remainder count, not data loss.

## Troubleshooting

### `ERR backend: empty output`

The backend exited without stdout. For `show`, the cache is usually empty. Run a listing command first (`rdt sub python`), then retry `show`.

### `ERR forbidden: ...`

Reddit rejected anonymous access. Run `rdt status` for diagnosis. When it shows `authenticated: false`, fetch browser cookies with `rdt login`, then retry the command.

### `ERR usage: export --compact requires a file (-o FILE)`

Compact export never writes to stdout. Add `-o FILE` to the command:

```sh
rdt-tidy --compact export "python tips" -o tips.txt
```

### `ERR not-found: rdt binary not found`

`rdt` was found neither on PATH nor under `~/.local/bin/`. Run `which rdt` for diagnosis. When it returns nothing, install rdt-cli and add it to PATH.

### `ERR timeout: rdt did not respond within 30s`

The backend did not return within 30 seconds. Check the network connection and retry with a smaller limit (`-n 5`).

## How it works

1. The mode flag is looked up before the command; when absent, the command and options go to `rdt` unchanged.
2. In compact mode the backend call uses raw `--json`; rdt's own `-c`/`--compact` and `--yaml` flags are dropped.
3. Limit options (`-n`, `--limit`, `--max-subs`) are clamped to the caps; missing ones get defaults. Positional fields stay untouched.
4. The returned envelope is parsed; on `ok: false`, `ERR <code>: <message>` prints and the exit code becomes 1.
5. Records are rendered into the matching format for the command type and written to stdout.

Empty backend output never loses data: `ERR backend: ...` prints and the process exits 1. When stdout is not JSON, it passes through as-is.

## Compact mode format

Listings (`feed`, `popular`, `all`, `sub`, `user-posts`, `search`):

```text
no | score | sub | title | author | id
1 | +2450c312 | r/python | Title (full) | u/alice | 1abc11
2 | +187c96 | r/programming | Title | u/bob | 1abc22
next t3_1abc22
```

For the `sub` command the `sub` column drops along with its header. `user-comments` is a headed table: `no | author | score | sub | body | id`. In `saved` and `upvoted` output the first column is kind: `P` (post) or `C` (comment). When a paging cursor exists, the last line is `next <cursor>`. On error a single line prints: `ERR <code>: <message>`. Table cells are single-line; a literal `|` inside a title or body stays unescaped.

Read (`read`, `show`):

```text
# 1abc11 r/python | Title | u/alice +2450 (312c)
LINK https://... (external links only)
body (full, line breaks kept)
---
u/dave +150: comment (full)
  u/erin +20: reply (two-space indented)
+2 more
```

All comments print, replies flatten to one level and carry a two-space indent, and reply continuation lines keep the same indent. Line breaks survive in bodies and comments (inline whitespace collapses, runs of blank lines shrink to one). `more_children` ids never print; only the `+<count> more` line stays.

Info commands:

```text
sub-info →  r/python 1200000 subs 5000 online / created 2008-01-27 / description
user     →  u/spez post:100 comment:200 age:2005-09-12
whoami   →  user line + second line: sess read,vote modhash:1
status   →  passed through
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Backend error (`ERR ...` printed on stdout) |
| 2 | Usage error (unknown command, `export` without `-o`) |
| 127 | `rdt` binary not found |
| other | Backend exit code passed through |

## Limits

| Area | Limit |
| --- | --- |
| Listing record count | Default 5, cap 10 |
| `feed --subs-only` | At most 5 subscriptions, 5 records per subscription |
| Title, body, comment, description | Never truncated, printed in full |
| Comment depth | Replies flatten to one level, marked by indent |
| `export --compact` | At most 50 lines, `-o FILE` required |
| Backend timeout | 30 seconds |

## Data files

rdt-tidy creates no config file of its own and stores no credentials. It reuses rdt-cli's files under `~/.config/rdt-cli/` as-is (`credential.json` for cookies, `index_cache.json` for short-index navigation). The only write path is the export file given via `-o`; an existing file is silently overwritten.

## Use as an AI agent skill

Agents get the full contract from [SKILL.md](./SKILL.md): compact tables, thread format, paging, and error recovery. Copy it into your harness's skill folder, run from the repo root:

```sh
mkdir -p {skill-dir}/rdt-tidy
cp SKILL.md {skill-dir}/rdt-tidy/SKILL.md
```

Replace `{skill-dir}` with your harness's skill folder location, for example `.agents/skills` (Skills CLI layout) or `~/.pi/agent/skills` (Pi agent).

## Project structure

```text
.
├── rdt-tidy               # wrapper (single file, executable)
├── README.md              # this file
└── tests
    ├── test_tidy.py       # end-to-end tests (with fake rdt)
    ├── test_tokens.py     # TokenView unit tests
    ├── shim
    │   └── rdt            # fake rdt binary for tests
    └── fixtures            # 10 synthetic JSON responses
```

## Development and testing

```sh
python3 -m py_compile rdt-tidy
python3 tests/test_tidy.py
python3 tests/test_tokens.py
```

The suite holds 52 end-to-end tests and 15 unit tests, and needs no network access. Live smoke test, no login required:

```sh
diff <(rdt status) <(./rdt-tidy status)
./rdt-tidy --compact search "x" -n 2; echo $?
```

## Contributing

Scope is behavior-preserving changes only. Every change needs tests; when the suite is red, fix the code, never loosen the test. New compact-format proposals start as a contract discussion.

## License

Apache-2.0, see [LICENSE](./LICENSE).
