"""Regression checks for wrapper boundaries and behavior-preserving cleanup."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_tokens import _mod as tidy


class TableSafetyTest(unittest.TestCase):
    def test_all_post_cells_are_single_line_and_pipe_escaped(self):
        line = tidy.post_line(
            1,
            {
                "id": "p|1\nnext",
                "title": "a | b",
                "author": "u|name\nnext",
                "subreddit": "sub|name\nnext",
            },
            True,
        )
        self.assertNotIn("\n", line)
        cells = line.split(" | ")
        self.assertEqual(len(cells), len(tidy.POST_COLS_SUB))
        self.assertEqual(cells[2], r"r/sub\|name next")
        self.assertEqual(cells[3], r"a \| b")
        self.assertEqual(cells[4], r"u/u\|name next")
        self.assertEqual(cells[5], r"p\|1 next")

    def test_comment_and_export_cells_escape_once(self):
        comment = tidy.comment_line(
            1,
            {
                "author": "a|b",
                "subreddit": "s|t",
                "id": "c|1",
                "body": "x|y",
            },
        )
        self.assertIn(r"u/a\|b", comment)
        self.assertIn(r"x\|y", comment)
        self.assertNotIn(r"x\\|y", comment)
        export = tidy._export_line(
            {"url": "https://example.org/a|b\nnext", "title": "x|y"}
        )
        self.assertNotIn("\n", export)
        self.assertIn(r"https://example.org/a\|b next", export)
        self.assertIn(r"x\|y", export)

    def test_capability_summary_remains_single_line(self):
        output = tidy.render_status(
            {
                "data": {
                    "authenticated": True,
                    "username": "u",
                    "capabilities": ["read\nwrite"],
                }
            }
        )
        self.assertEqual(output, "auth:yes u/u caps:read write modhash:0")


class DetailBoundaryTest(unittest.TestCase):
    def test_raw_comment_children_are_required_to_be_a_list(self):
        for children in (1, True, None, "oops", {"unexpected": 1}):
            with self.subTest(children=children):
                post, comments, more = tidy.parse_detail(
                    [
                        {"data": {"children": [{"data": {"id": "p"}}]}},
                        {"data": {"children": children}},
                    ]
                )
                self.assertEqual((post, comments, more), ({"id": "p"}, [], 0))

    def test_typed_comments_are_required_to_be_a_list(self):
        for comments in (1, True, None, "oops", {"unexpected": 1}):
            with self.subTest(comments=comments):
                self.assertEqual(
                    tidy.parse_detail(
                        {
                            "post": {"id": "p"},
                            "comments": comments,
                        }
                    ),
                    ({"id": "p"}, [], 0),
                )

    def test_typed_replies_are_required_to_be_a_list(self):
        for replies in (1, True, None, "oops", {"unexpected": 1}):
            with self.subTest(replies=replies):
                _, comments, more = tidy.parse_detail(
                    {
                        "comments": [
                            {
                                "author": "top",
                                "body": "kept",
                                "replies": replies,
                            }
                        ]
                    }
                )
                self.assertEqual([c["body"] for c in comments], ["kept"])
                self.assertEqual(more, 0)

    def test_typed_sibling_order_and_more_counts_are_preserved(self):
        data = {
            "comments": [
                {
                    "author": "top",
                    "more_count": 2,
                    "replies": [
                        {
                            "author": "a",
                            "more_count": 3,
                            "replies": [
                                {"author": "a1", "created_utc": 1709251200},
                                {"author": "[more]", "more_children": ["x", "y"]},
                            ],
                        },
                        {"author": "b", "replies": [{"author": "b1"}]},
                    ],
                },
                {"author": "last"},
            ]
        }
        before = json.dumps(data)
        _, comments, more = tidy.parse_detail(data)
        self.assertEqual(
            [c["author"] for c in comments], ["top", "a", "b", "a1", "b1", "last"]
        )
        self.assertEqual([c["depth"] for c in comments], [0, 1, 1, 1, 1, 0])
        self.assertEqual(comments[3]["created_utc"], 1709251200)
        self.assertEqual(more, 7)
        self.assertEqual(json.dumps(data), before)


class BackendBoundaryTest(unittest.TestCase):
    def run_compact(self, stdout, stderr="", code=0):
        proc = subprocess.CompletedProcess(["rdt"], code, stdout, stderr)
        with (
            mock.patch.object(tidy, "run_backend", return_value=proc),
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            result = tidy._run_compact(
                "status", tidy.TokenView([]), lambda _: "success"
            )
        return result, out.getvalue(), err.getvalue()

    def test_nonzero_exit_cannot_be_reported_as_success(self):
        code, out, err = self.run_compact(
            '{"ok":true,"data":{}}', "backend failure\n", 7
        )
        self.assertEqual(code, 7)
        self.assertIn("ERR backend", out)
        self.assertNotIn("success", out)
        self.assertEqual(err, "backend failure\n")

    def test_success_keeps_backend_warnings(self):
        code, out, err = self.run_compact('{"ok":true,"data":{}}', "warning\n")
        self.assertEqual((code, out, err), (0, "success\n", "warning\n"))

    def test_structured_error_keeps_backend_stderr(self):
        proc = subprocess.CompletedProcess(
            ["rdt"], 1, '{"ok":false,"error":"failed"}', "details\n"
        )
        with (
            mock.patch.object(tidy, "run_backend", return_value=proc),
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as exit_info,
        ):
            tidy._run_compact("status", tidy.TokenView([]), lambda _: "success")
        self.assertEqual(exit_info.exception.code, 1)
        self.assertEqual(out.getvalue(), "ERR backend: failed\n")
        self.assertEqual(err.getvalue(), "details\n")

    def test_json_limit_measures_utf8_bytes_not_characters(self):
        payload = json.dumps({"text": "ğ"}, ensure_ascii=False)
        proc = subprocess.CompletedProcess(["rdt"], 0, payload, "")
        with (
            mock.patch.object(tidy, "MAX_BACKEND_BYTES", len(payload)),
            contextlib.redirect_stdout(io.StringIO()) as out,
            self.assertRaises(SystemExit) as exit_info,
        ):
            tidy.load_envelope(proc)
        self.assertEqual(exit_info.exception.code, 1)
        self.assertIn("response too large", out.getvalue())

    def test_excessive_json_depth_is_a_controlled_error(self):
        payload = '{"data":' + "[" * 10000 + "]" * 10000 + "}"
        proc = subprocess.CompletedProcess(["rdt"], 0, payload, "")
        with (
            contextlib.redirect_stdout(io.StringIO()) as out,
            self.assertRaises(SystemExit) as exit_info,
        ):
            tidy.load_envelope(proc)
        self.assertEqual(exit_info.exception.code, 1)
        self.assertIn("ERR backend", out.getvalue())

    def test_invalid_utf8_backend_output_is_a_controlled_error(self):
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
        with (
            mock.patch.object(tidy.subprocess, "run", side_effect=error),
            contextlib.redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as exit_info,
        ):
            tidy.run_backend(["status"])
        self.assertEqual(exit_info.exception.code, 1)
        self.assertIn("not valid UTF-8", err.getvalue())


class ExportOptionBoundaryTest(unittest.TestCase):
    def test_invalid_consumed_options_never_touch_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "existing.txt"
            out.write_text("existing content")
            for extra in (("--output",), ("--format",), ("--format", "xml")):
                with (
                    self.subTest(extra=extra),
                    mock.patch.object(
                        tidy,
                        "run_backend",
                        return_value=subprocess.CompletedProcess([], 0, "", ""),
                    ) as backend,
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()) as err,
                ):
                    code = tidy.cmd_export_compact(["query", "-o", str(out), *extra])
                    self.assertEqual(code, tidy.EX_USAGE)
                    self.assertIn("ERR usage", err.getvalue())
                    backend.assert_not_called()
                    self.assertEqual(out.read_text(), "existing content")
                    self.assertEqual(list(Path(temp).iterdir()), [out])


if __name__ == "__main__":
    unittest.main()
