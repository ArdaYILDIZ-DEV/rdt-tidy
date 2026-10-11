"""UTC publication dates in thread rendering and JSON-backed export."""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader(
    "tidy_thread_dates", str(ROOT / "rdt-tidy")
)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
tidy = importlib.util.module_from_spec(_spec)
_loader.exec_module(tidy)


class ThreadDatesTest(unittest.TestCase):
    def test_typed_reply_dates_survive_normalization(self):
        data = {
            "post": {"id": "p", "created_utc": 1709251199},
            "comments": [
                {
                    "author": "top",
                    "score": 1,
                    "body": "top body",
                    "created_utc": 1709251200,
                    "replies": [
                        {
                            "author": "reply",
                            "score": 2,
                            "body": "line1\nline2",
                            "created_utc": "1709251201",
                            "edited": 1709251300,
                            "replies": [
                                {
                                    "author": "deep",
                                    "body": "deep body",
                                    "created_utc": 1709251202,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        output = tidy.render_detail({"data": data})
        self.assertIn(" | created_utc 2024-02-29T23:59:59Z", output.splitlines()[0])
        self.assertIn("u/top +1 [2024-03-01T00:00:00Z]: top body", output)
        self.assertIn("  u/reply +2 [2024-03-01T00:00:01Z]: line1\n  line2", output)
        self.assertIn("  u/deep +0 [2024-03-01T00:00:02Z]: deep body", output)
        self.assertNotIn("2024-03-01T00:01:40Z", output)

    def test_raw_nested_comments_keep_their_own_dates(self):
        reply = {
            "kind": "t1",
            "data": {
                "author": "reply",
                "body": "reply",
                "created_utc": 1709251201,
            },
        }
        data = [
            {"data": {"children": [{"data": {"id": "p", "created_utc": 1709251199}}]}},
            {
                "data": {
                    "children": [
                        {
                            "kind": "t1",
                            "data": {
                                "author": "top",
                                "body": "top",
                                "created_utc": 1709251200,
                                "replies": {"data": {"children": [reply]}},
                            },
                        }
                    ]
                }
            },
        ]
        post, comments, _ = tidy.parse_detail(data)
        self.assertEqual(post["created_utc"], 1709251199)
        self.assertEqual([c["created_utc"] for c in comments], [1709251200, 1709251201])
        output = tidy.render_detail({"data": data})
        self.assertIn("u/top +0 [2024-03-01T00:00:00Z]: top", output)
        self.assertIn("  u/reply +0 [2024-03-01T00:00:01Z]: reply", output)

    def test_missing_invalid_dates_do_not_inherit_post_date(self):
        output = tidy.render_detail(
            {
                "data": {
                    "post": {"created_utc": 1709251199},
                    "comments": [
                        {
                            "author": "missing",
                            "body": "body",
                            "replies": [
                                {
                                    "author": "invalid",
                                    "body": "reply",
                                    "created_utc": True,
                                },
                            ],
                        }
                    ],
                }
            }
        )
        self.assertIn("u/missing +0 [-]: body", output)
        self.assertIn("  u/invalid +0 [-]: reply", output)


class JsonExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "export.txt"
        self.out.write_text("existing content", encoding="utf-8")
        self.posts = [
            {
                "title": 'a|b,"c"\nline',
                "subreddit": "s",
                "author": "a",
                "score": 1,
                "num_comments": 2,
                "url": "https://example.org",
                "permalink": "/r/s/comments/p/title/",
                "created_utc": 1709251199,
            }
        ]
        self.calls = []

    def run_export(self, payload=None, flags=(), code=0, skip=False):
        def backend(args):
            self.calls.append(args)
            view = tidy.TokenView(args[1:])
            self.assertEqual(view.value({"--format"}), "json")
            stage = Path(view.value({"-o", "--output"}))
            self.assertNotEqual(stage, self.out)
            if os.name == "posix":
                self.assertEqual(os.stat(stage.parent).st_mode & 0o777, 0o700)
            self.assertEqual(self.out.read_text(encoding="utf-8"), "existing content")
            if not skip:
                stage.write_bytes(
                    json.dumps(self.posts).encode() if payload is None else payload
                )
            return mock.Mock(
                returncode=code,
                stdout="backend out\n" if code else "",
                stderr="backend err\n" if code else "",
            )

        with (
            mock.patch.object(tidy, "run_backend", side_effect=backend),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            rc = tidy.cmd_export_compact(["query", "-o", str(self.out), *flags])
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_compact_export_retains_fields_and_adds_utc_date(self):
        rc, stdout, _ = self.run_export()
        self.assertEqual(rc, 0)
        content = self.out.read_text(encoding="utf-8")
        self.assertEqual(
            content.splitlines()[0], "score | sub | title | author | url | created_utc"
        )
        self.assertIn('a\\|b,"c" line', content)
        self.assertTrue(content.splitlines()[1].endswith(" | 2024-02-29T23:59:59Z"))
        self.assertEqual(stdout, f"saved {self.out} (1 rows)\n")
        self.assertEqual(os.stat(self.out).st_mode & 0o777, 0o600)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.out])

    def test_csv_export_quotes_raw_text_and_includes_utc_date(self):
        rc, _, _ = self.run_export(flags=("--format", "csv"))
        self.assertEqual(rc, 0)
        rows = list(
            tidy.csv.DictReader(io.StringIO(self.out.read_text(encoding="utf-8")))
        )
        self.assertEqual(rows[0]["title"], self.posts[0]["title"])
        self.assertEqual(rows[0]["created_utc"], "2024-02-29T23:59:59Z")
        self.assertEqual(
            rows[0]["permalink"], "https://reddit.com/r/s/comments/p/title/"
        )
        self.assertEqual(
            list(rows[0]),
            [
                "title",
                "subreddit",
                "author",
                "score",
                "num_comments",
                "url",
                "permalink",
                "created_utc",
            ],
        )

    def test_missing_and_invalid_export_dates_are_dash(self):
        self.posts = [{}, {"created_utc": "bad"}, {"created_utc": 0}]
        rc, _, _ = self.run_export()
        self.assertEqual(rc, 0)
        self.assertTrue(
            all(line.endswith(" | -") for line in self.out.read_text().splitlines()[1:])
        )

    def test_empty_list_preserves_empty_export_contract(self):
        self.posts = []
        rc, stdout, _ = self.run_export()
        self.assertEqual(rc, 0)
        self.assertEqual(self.out.read_bytes(), b"")
        self.assertIn("(0 rows)", stdout)

    def test_json_errors_leave_existing_target_untouched(self):
        for payload in (
            b"broken",
            b"{}",
            b"[null]",
            b"[1]",
            b"\xff",
            b"[[[]]]",
            b"[" * 2000 + b"]" * 2000,
        ):
            with self.subTest(payload=payload):
                rc, stdout, _ = self.run_export(payload=payload)
                self.assertEqual(rc, tidy.EX_BACKEND)
                self.assertIn("ERR backend", stdout)
                self.assertEqual(self.out.read_text(), "existing content")
                self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.out])

    def test_backend_failure_preserves_streams_and_target(self):
        rc, stdout, stderr = self.run_export(code=7)
        self.assertEqual(rc, 7)
        self.assertEqual(stdout, "backend out\n")
        self.assertEqual(stderr, "backend err\n")
        self.assertEqual(self.out.read_text(), "existing content")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.out])

    def test_no_backend_file_cannot_reuse_existing_target(self):
        rc, stdout, _ = self.run_export(skip=True)
        self.assertEqual(rc, tidy.EX_BACKEND)
        self.assertIn("ERR backend: export did not write", stdout)
        self.assertEqual(self.out.read_text(), "existing content")

    def test_size_limit_and_row_cap(self):
        with mock.patch.object(tidy, "MAX_BACKEND_BYTES", 20):
            rc, stdout, _ = self.run_export()
        self.assertEqual(rc, tidy.EX_BACKEND)
        self.assertIn("too large", stdout)
        self.assertEqual(self.out.read_text(), "existing content")
        self.posts *= 60
        rc, _, _ = self.run_export(flags=("-n", "100"))
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.out.read_text().splitlines()), 51)
        self.assertEqual(tidy.TokenView(self.calls[-1]).value(tidy.LIMIT_FLAGS), "50")

    def test_backend_exception_cleans_staging(self):
        def backend(args):
            stage = Path(tidy.TokenView(args[1:]).value({"-o", "--output"}))
            stage.write_text("unfinished", encoding="utf-8")
            raise SystemExit(tidy.EX_BACKEND)

        with (
            mock.patch.object(tidy, "run_backend", side_effect=backend),
            self.assertRaises(SystemExit),
        ):
            tidy.cmd_export_compact(["query", "-o", str(self.out)])
        self.assertEqual(self.out.read_text(), "existing content")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.out])

    def test_invalid_unicode_text_cannot_damage_target(self):
        self.posts = [{"title": "\ud800"}]
        for flags in ((), ("--format", "csv")):
            with self.subTest(flags=flags):
                rc, stdout, _ = self.run_export(flags=flags)
                self.assertEqual(rc, tidy.EX_BACKEND)
                self.assertIn("ERR io", stdout)
                self.assertEqual(self.out.read_text(), "existing content")
                self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.out])

    def test_empty_csv_has_header(self):
        self.posts = []
        rc, _, _ = self.run_export(flags=("--format", "csv"))
        self.assertEqual(rc, 0)
        content = self.out.read_text()
        self.assertTrue(content.strip().endswith(",created_utc"))
        self.assertEqual(len(content.splitlines()), 1)

    def test_replace_failure_preserves_target_and_cleans_temp(self):
        with mock.patch.object(tidy.os, "replace", side_effect=OSError("blocked")):
            rc, stdout, _ = self.run_export()
        self.assertEqual(rc, tidy.EX_BACKEND)
        self.assertIn("ERR io", stdout)
        self.assertEqual(self.out.read_text(), "existing content")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.out])


if __name__ == "__main__":
    unittest.main()
