# rdt-tidy

A single-file Python wrapper around the `rdt` backend. Plain mode forwards backend arguments and output; compact mode projects JSON into short tables and flattened threads. Keep fetching, authentication, pagination, sorting and cache ownership in `rdt`, not in a second client implementation.

## Where work belongs

- `rdt-tidy`: executable entry point, option parsing (`TokenView`), backend execution, renderers and export adapter. Python 3.10+, standard library only; no build step.
- `tests/test_tidy.py` and `tests/shim/rdt`: isolated CLI tests with a fake backend on PATH. `tests/fixtures/` supplies responses; no Reddit access is needed.
- Other `tests/test_*.py`: parsing, error boundaries, reply robustness, UTC dates and export regressions.
- `README.md`: user-facing contract and installation/testing instructions. `SKILL.md`: agent-facing usage guidance. Update relevant examples and descriptions when changing CLI behavior; neither document replaces the implementation and tests as evidence.

## Behavior contracts

- Only leading `-c/--compact` flags select wrapper mode. Respect `--` and positional values, including dash-led query text. Use `TokenView` for option transformations rather than ad-hoc token replacement; insert synthesized flags before `--`.
- Plain mode and compact action commands (`open`, votes, saves, subscriptions, comments, login/logout) forward arguments without projection or synthesized limits. Output is captured as UTF-8 through pipes, not an interactive terminal; do not promise identical TTY or signal behavior.
- Compact structured commands request backend JSON and remove backend compact/YAML flags. Listings default to 5 and cap at 10; `feed --subs-only` caps at 5 subreddits × 5 posts. `read/show` have no wrapper limit. Listings with `-o/--output` bypass compact conversion and clamping entirely.
- Backend long limit options differ: listings/details use `--limit`, export uses `--count`. Tracking both for clamping does not make them interchangeable backend options.
- Compact mode drops metadata, never length-truncates retained text. Table cells collapse whitespace and escape pipes once; thread bodies retain paragraph breaks while normalizing inline whitespace. All nested replies flatten to two spaces, so immediate-parent relationships are lost. Count encountered unexpanded `more` stubs throughout the subtree; do not imply a complete thread from their absence.
- Publication timestamps belong to each post/comment: UTC `YYYY-MM-DDTHH:MM:SSZ`, fractional seconds discarded, missing/invalid values `-`. Account/community creation summaries remain date-only. Preserve raw passthrough timestamps.
- In the documented `rdt 0.4.1` behavior, JSON browse listings do not refresh the index cache; search does. Table row numbers are not reliable targets for cached navigation or writes after browsing. Prefer post IDs; do not mirror or rewrite backend caches to compensate.
- Preserve backend stderr and do not render nonzero backend results as success. Structured error envelopes become `ERR ...` with exit 1; other backend failures can retain their exit code. Non-JSON stdout passes through. Wrapper usage errors use exit 2; missing `rdt` uses 127. Execution has a default 30s timeout (`RDT_TIDY_TIMEOUT`: 1–300s); compact JSON responses are bounded at 10 MiB after capture.

## Export is a separate adapter

Compact export requires an output path and defaults/caps at 50 rows. Fetch backend JSON into private staging in the destination directory, validate it, then atomically replace the target through a unique temporary file. Failures before replacement must leave existing destination content intact and clean up temporary artifacts. Keep private staging/output permissions.

The default final output is a short table, including when `--format json` is supplied; explicit `--format csv` selects real CSV with standard quoting and each post's UTC timestamp. Plain export retains backend CSV/JSON behavior. Validate rewritten output/format options before invoking the backend; do not accidentally forward the user's destination to the fetch stage.

## Checks

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests
```

For a focused change, run the relevant `tests/test_*.py` directly. Add regressions in the existing suite for changed behavior, especially argument forwarding, output shape and export failure paths. Keep fixtures and the shim isolated from real credentials/caches. Real CLI help can check backend option compatibility, but fake-backend tests do not establish live Reddit access or account behavior.
