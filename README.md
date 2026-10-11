<p align="center">
  <strong>Single-file wrapper that shrinks rdt-cli output into model-friendly lines.</strong><br>
  <a href="https://pypi.org/project/rdt-cli/"><img src="https://img.shields.io/pypi/v/rdt-cli.svg?style=flat-square" alt="rdt-cli on PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-stdlib%20only-green?style=flat-square" alt="stdlib only">
</p>

rdt-tidy runs the `rdt` binary as a subprocess. Without flags it passes output through unchanged. In `--compact` mode it converts the raw JSON response into short, positional lines, dropping redundant metadata while preserving full titles, bodies and comments. It has no dependencies, uses only the standard library, and never touches credentials or caches.

## Quick start

```sh
rdt-tidy --compact sub python
rdt-tidy -c search "rust vs go" -n 8
```

## Use as an AI agent skill

Agents get the full contract from [SKILL.md](./SKILL.md): compact tables, thread format, paging, and error recovery. Copy it into your harness's skill folder, run from the repo root:

```sh
mkdir -p {skill-dir}/rdt-tidy
cp SKILL.md {skill-dir}/rdt-tidy/SKILL.md
```

Replace `{skill-dir}` with your harness's skill folder location, for example `.agents/skills` (Skills CLI layout) or `~/.pi/agent/skills` (Pi agent).

## Features

- Passthrough output is buffered via pipes (`subprocess.run(capture_output=True)`), preserving bytes but not strictly byte-identical (TTY color, signal bubbling, and interleaving differ); exit code is preserved.
- Compact-mode tables are headed; text fields are never truncated, and line breaks in bodies and comments are kept.
- Reply traversal is iterative; typed replies and hidden-comment counts share one walk. Replies retain their existing display order and flatten to one indented level. Malformed containers are treated as empty, and JSON nesting rejected by the decoder produces a controlled error.
- External links are detected defensively: `LINK {url}` is emitted whenever a non-empty URL differs from the permalink, even if `is_self` is omitted or null in the payload.
- Compact export fetches raw JSON into a private staging file, so publication timestamps are retained. It writes short tables by default; `--format csv` writes actual CSV with a UTC `created_utc` column.
- Listing size limit: default 5, cap 10; `feed --subs-only` is capped at 5x5.
- Write paths (`open`, `upvote`, `save`, `subscribe`, `comment`, `login`, `logout`) stay passthrough by design: single-line backend outputs with no compact envelope to strip.
- Compact stdout is checked against 10 MiB of UTF-8 bytes after capture, before JSON parsing/rendering. This is not a hard subprocess memory limit. Export JSON is read with a 10 MiB bound.
- Position-independent option parsing: query and text fields (including `-c`, `-nonsense`) are never confused with flags.
- Empty compact backend output returns `ERR backend` with the backend's nonzero exit code, or 1 if it exited successfully. Valid structured output never hides a backend failure; backend stderr is preserved.
- Token savings come from dropping redundant fields, not from truncating text.

## Requirements

- Python 3.10 or later (tested on 3.12 and 3.13).
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
rdt-tidy -c export "python tips" --format csv -o tips.csv  # CSV with UTC dates
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
| `sub-info` | Subscriber info, date, and public description when nonempty |
| `user` | Single line: karma and account age |
| `whoami` | User line + session line |
| `status` | Single line: auth, user, caps |
| `export` | Short lines by default, CSV with `--format csv`; UTC dates included, only a summary on stdout |
| `open`, `upvote`, `save`, `subscribe`, `comment`, `login`, `logout` | Passed through |

Compact listings default to `-n 5` and cap at 10; `feed --subs-only` caps at 5 posts per subreddit, and export defaults/caps at 50. Info and action commands receive no synthesized limit. Listings accept `-n/--limit`; export accepts `-n/--count` in `rdt 0.4.1`. Tidy tracks both spellings for limit bookkeeping but does not translate unsupported backend options. For `read` and `show`, `-n` goes to the backend as-is with no cap: prefer a small `-n` and paginate, since `-n 100 --expand-more` on a large thread can return megabytes. In `export --compact`, tidy-specific flags (`-c`, `--compact`, `--yaml`) are stripped. The backend is always invoked with `--format json` into a private staging directory; only after validating that data is the destination replaced atomically.

## Comment expansion

A default `read` makes a single request; unopened comments collapse into a `+<count> more` line. To expand additional nodes:

```sh
rdt-tidy -c read 1abc123 -n 100 --expand-more
```

`--expand-more` makes the backend send extra requests to open closed comment stubs. `rdt-tidy` traverses all reply subtrees iteratively across arbitrary nesting depths (depth >= 2), flattening comments to a single reply level (`depth=1`, two-space indented). Any unexpanded `more` stubs encountered anywhere in the subtree are accumulated into the trailing `+<count> more` remainder line, ensuring zero silent comment loss.

## Troubleshooting

### `ERR backend: empty output`

The backend exited without usable stdout. For `show`, check the index-cache caveat below. Prefer `rdt-tidy -c read <post-id>` when reading an item from a compact browse table.

### `ERR forbidden: ...`

Reddit rejected anonymous access. Run `rdt status` for diagnosis. When it shows `authenticated: false` (compact: `auth:no`), fetch browser cookies with `rdt login`, then retry the command.

### `ERR usage: export --compact requires a file (-o FILE)`

Compact export never writes to stdout. Add `-o FILE` to the command:

```sh
rdt-tidy --compact export "python tips" -o tips.txt
```

### `ERR not-found: rdt binary not found`

`rdt` was found neither on PATH nor under `~/.local/bin/`. Run `which rdt` for diagnosis. When it returns nothing, install rdt-cli and add it to PATH.

### `ERR timeout: rdt did not respond within 30s`

The backend did not return within 30 seconds (default; override with `RDT_TIDY_TIMEOUT=1..300`). Check the network connection and retry with a smaller limit (`-n 5`).

### `ERR backend: invalid envelope`

The backend returned JSON that is not a listing envelope (a bare array or string, for example). Exit code 1; no traceback. Inspect the backend output directly to diagnose.

### `ERR io: cannot read ...` / `cannot parse ...` / `cannot write ...`

Local file failure around the export path: an unreadable staged JSON file, an unwritable target directory, or text that cannot be encoded as UTF-8. Exit code 1. Invalid, oversized (over 10 MiB), or structurally incorrect backend JSON is reported as `ERR backend: invalid export JSON: ...`. Neither failure overwrites an existing destination.

### `ERR backend: cannot execute rdt: ...`

The `rdt` binary exists but the OS refused to run it (permissions or binary format). Check `ls -l $(which rdt)` and reinstall rdt-cli if needed.

## How it works

1. The mode flag is looked up before the command; when absent, the command and options go to `rdt` unchanged.
2. In compact mode the backend call uses raw `--json` (or `--format json` for `export`); rdt's own `-c`/`--compact` and `--yaml` flags are dropped.
3. Limit options (`-n`, `--limit`, `--count`, `--max-subs`) are clamped to the caps; missing ones get defaults. Positional fields stay untouched.
4. The returned envelope is parsed; on `ok: false`, `ERR <code>: <message>` prints and the exit code becomes 1.
5. Records are rendered into the matching format for the command type and written to stdout. For threads, subtrees are traversed iteratively, replies flatten to depth 1, and all nested `more` counts are summed into the remainder line. External links print with `LINK {url}` whenever the URL differs from the permalink.

Empty backend output never loses data: `ERR backend: ...` prints and the process exits 1. When stdout is not JSON, it passes through as-is.

## Compact mode format

Listings (`feed`, `popular`, `all`, `sub`, `user-posts`, `search`):

```text
no | score | sub | title | author | id | created_utc
1 | +2450c312 | r/python | Title (full) | u/alice | 1abc11 | 2024-09-05T15:26:40Z
2 | +187c96 | r/programming | Title | u/bob | 1abc22 | 2024-09-05T15:43:20Z
next t3_1abc22
```

For the `sub` command the `sub` column drops along with its header. `user-comments` is a headed table: `no | author | score | sub | body | id | created_utc`. In `saved` and `upvoted` output the first column is kind: `P` (post) or `C` (comment). When a paging cursor exists, the last line is `next <cursor>`. On error a single line prints: `ERR <code>: <message>`. Table cells are single-line; a literal `|` inside a title or body is escaped as `\|`.

The final `created_utc` column uses each post or comment's own Unix timestamp (seconds), rendered as `YYYY-MM-DDTHH:MM:SSZ`. `Z` means UTC; the machine's timezone does not affect the result. Fractional seconds are omitted. Missing, zero, negative, boolean, malformed or out-of-range values render as `-`; no date is inferred from a parent post, `created` or `edited`. Existing columns keep their order, but consumers expecting an exact column count must accept the new final column.

The same UTC formatter is used by all compact post listings, `user-comments`, mixed `saved`/`upvoted` tables, `read`/`show`, and compact export. Passthrough and listing file-output forwarding remain unchanged: raw backend output, including numeric timestamps and the backend's CSV limitations, is preserved.

Read (`read`, `show`):

```text
# 1abc11 r/python | Title | u/alice +2450 (312c) | created_utc 2024-09-05T15:26:40Z
LINK https://... (external links only)
body (full, line breaks kept)
---
u/dave +150 [2024-09-05T15:28:20Z]: comment (full)
  u/erin +20 [2024-09-05T15:28:30Z]: reply (two-space indented)
+2 more
```

The post header ends with `created_utc <UTC date>`; each comment includes its own `[<UTC date>]` before the colon (`[-]` when unavailable). Raw and typed detail payloads retain dates at every reply depth; a reply never inherits its parent's timestamp. Existing body/link placement and line counts are preserved, but consumers parsing comment headers must accept this added metadata.

All comments print; nested replies of arbitrary depth flatten to a single reply level with a two-space indent, and reply continuation lines keep the same indent. Line breaks survive in bodies and comments (inline whitespace collapses, runs of blank lines shrink to one). `LINK {url}` prints for external link posts whenever `url` is present and differs from `permalink` (or `is_self` is false). `more_children` ids never print; all unexpanded stubs across the entire subtree are summed into the trailing `+<count> more` line.

Export (`--compact export`):

```text
score | sub | title | author | url | created_utc
+10c3 | r/python | Hello world | u/ali | https://example.org | 2024-03-01T00:00:00Z
```

The default remains the compact table, with `created_utc` appended. Unlike the old intermediate-only format flag, explicit `--format csv` now selects actual CSV; omit it to keep short table output. CSV columns are `title,subreddit,author,score,num_comments,url,permalink,created_utc`, preserving full text (including line breaks, commas and quotes) with standard CSV quoting. Dates use the same UTC format and `-` fallback; relative Reddit permalinks become absolute. No additional Reddit request or timestamp lookup is needed: backend JSON already contains the original dates, whereas backend CSV omits them.

The 50-row cap, `saved <file> (<n> rows)` summary and owner-only file permissions remain. An empty JSON list produces an empty default compact file, or a header-only CSV. Backend failures, missing output, malformed JSON and write failures leave the existing destination intact and clean up staging files. `--format json` retains the existing compact-table behavior; use plain (non-compact) mode for untouched backend JSON output. Missing values for the output/format options, or formats other than `csv`/`json`, are rejected before invoking the backend or touching the destination.

Info commands:

```text
sub-info →  r/python 1200000 subs 5000 online / created 2008-01-27 / description
user     →  u/spez post:100 comment:200 age:2005-09-12
whoami   →  user line + second line: sess read,vote modhash:1
status   →  auth:yes u/spez caps:read,write modhash:1 (auth:no when logged out)
```

## Backend compatibility and existing capabilities

The installed backend audited here is `rdt 0.4.1`. All of its commands are accessible in plain passthrough mode; compact mode only adds projection, limits and the timestamp-preserving export adapter. Fetching, pagination, authentication, sorting, expansion and index-cache ownership remain with `rdt`.

**Index-cache caveat:** in this backend version, browse commands (`sub`, `feed`, `popular`, etc.) return JSON before saving their index cache. Search saves its cache before structured output. Consequently, a compact table's `no` is not proof that `show <n>`, `open <n>` or an index-based action will target that row: the backend may use stale search results. Use the displayed post ID with `read <id>` or ID-based actions instead. Tidy does not mirror or rewrite backend caches; fixing JSON browse cache updates belongs in `rdt`.

These backend capabilities already work without a new wrapper feature:

```sh
rdt-tidy -c sub python --sort top --time week
rdt-tidy -c search "asyncio" -r python --sort new --time month
rdt-tidy -c read <post-id> --sort new -n 10 --expand-more
rdt-tidy -c feed --subs-only --max-subs 3 -n 5
```

`--after` remains backend pagination; no second paging implementation is needed. Global backend options work in plain mode (`rdt-tidy --version`, `rdt-tidy --verbose search "asyncio"`), but not as compact-mode prefixes. Proposed compact global-option support and optional comment-context links are not implemented. Existing vote/save/subscribe reversal flags also pass through unchanged; their account effects still require an explicit user request.

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
| Comment depth | Iterative traversal (no recursion limit); replies flatten to one level, marked by indent |
| `export --compact` | At most 50 records, `-o FILE` required, tidy flags stripped, staged JSON; compact table or explicit CSV with UTC dates |
| Backend timeout | 30 seconds default (`RDT_TIDY_TIMEOUT`, 1-300) |
| Backend response | Rejected with `ERR backend: response too large` over 10 MiB |

## Data files

rdt-tidy creates no config file of its own and stores no credentials. It reuses rdt-cli's files under `~/.config/rdt-cli/` as-is (`credential.json` for cookies, `index_cache.json` for short-index navigation). Export uses the destination given via `-o` and temporary staging within its directory. An existing destination is silently overwritten only after successful backend fetch, JSON validation and output formatting. Backend JSON is stored in a unique private directory (`0700` on POSIX) that is removed after reading. Final output is written through a uniquely named temp file (`0600`) and moved into place atomically.

## Project structure

```text
.
├── rdt-tidy               # wrapper (single file, executable)
├── README.md              # this file
└── tests
    ├── test_tidy.py                # end-to-end tests, isolated TestCase methods (with fake rdt)
    ├── test_tokens.py              # unit tests: TokenView, detail parsing, export, backend errors
    ├── test_detail_robustness.py   # regression tests: malformed envelopes, deep nesting
    ├── test_audit.py              # wrapper boundaries, cell safety and cleanup regressions
    ├── test_dates.py              # UTC formatting and listing dates
    ├── test_thread_export_dates.py # thread dates and safe JSON-backed export
    ├── shim
    │   └── rdt            # fake rdt binary for tests
    └── fixtures            # 12 synthetic JSON responses
```

## Development and testing

```sh
python3 -m py_compile rdt-tidy
python3 tests/test_tidy.py
python3 tests/test_tokens.py
```

The suite holds 185 tests (45 end-to-end in `test_tidy.py`, 84 unit in `test_tokens.py`, 17 robustness in `test_detail_robustness.py`, 10 timestamp/table tests in `test_dates.py`, 15 thread/export tests in `test_thread_export_dates.py`, and 14 audit regressions in `test_audit.py`) and needs no network access. Timestamp checks cover per-record mapping, invalid data, UTC day boundaries, raw/typed nested comments and identical CLI output across three process timezones. Export checks cover CSV quoting, JSON validation, bounded reads, row caps, target preservation, atomic writes and cleanup. Full run:

```sh
python3 -m unittest discover tests
```

Direct runners work too:

```sh
python3 tests/test_tidy.py
python3 tests/test_tokens.py
```

Live smoke test, no login required:

```sh
diff <(rdt status) <(./rdt-tidy status)   # passthrough only; --compact status differs by design
./rdt-tidy --compact status              # auth:yes u/... caps:... / auth:no
./rdt-tidy --compact search "x" -n 2; echo $?
```

## Contributing

Scope is behavior-preserving changes only. Every change needs tests; when the suite is red, fix the code, never loosen the test. New compact-format proposals start as a contract discussion.

## License

Apache-2.0, see [LICENSE](./LICENSE).
