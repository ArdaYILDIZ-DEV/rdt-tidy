"""Publication timestamps in compact tables, without network access."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("rdt_tidy_dates", str(ROOT / "rdt-tidy"))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
tidy = importlib.util.module_from_spec(_spec)
_loader.exec_module(tidy)


class TimestampTest(unittest.TestCase):
    def test_numeric_seconds_and_strings(self):
        for value in (
            1725550000,
            1725550000.0,
            "1725550000",
            "1725550000.75",
            1725550000.9999998,
        ):
            with self.subTest(value=value):
                self.assertEqual(tidy.fmt_created_utc(value), "2024-09-05T15:26:40Z")

    def test_missing_invalid_and_out_of_range(self):
        for value in (
            None,
            "",
            "bad",
            0,
            "0",
            -1,
            True,
            False,
            [],
            {},
            float("nan"),
            float("inf"),
            float("-inf"),
            "NaN",
            "Infinity",
            10**1000,
            "1e1000",
            253402300800,
        ):
            with self.subTest(value=value):
                self.assertEqual(tidy.fmt_created_utc(value), "-")

    def test_utc_midnight_and_leap_day(self):
        for value, expected in (
            (1709251199, "2024-02-29T23:59:59Z"),
            (1709251200, "2024-03-01T00:00:00Z"),
        ):
            with self.subTest(value=value):
                self.assertEqual(tidy.fmt_created_utc(value), expected)

    def test_existing_date_only_metadata_is_unchanged(self):
        self.assertEqual(tidy.fmt_date(1725550000), "2024-09-05")
        self.assertEqual(tidy.fmt_date(None), "-")


class TableDateTest(unittest.TestCase):
    @staticmethod
    def envelope(nested=True):
        data = {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "p1",
                        "title": "post",
                        "created_utc": 1709251199,
                        "created": 1,
                        "edited": 1709251200,
                    },
                },
                {
                    "kind": "t1",
                    "data": {
                        "id": "c1",
                        "body": "comment",
                        "created_utc": "1709251200",
                        "link_id": "t3_p1",
                        "created": 1,
                        "edited": 1709251300,
                    },
                },
            ],
            "after": "t1_c1",
        }
        return {"ok": True, "data": {"data": data} if nested else data}

    def assert_dates(self, output, expected):
        lines = output.splitlines()
        header = lines[0].split(" | ")
        self.assertEqual(header[-1], "created_utc")
        rows = [line.split(" | ") for line in lines[1:] if not line.startswith("next ")]
        self.assertTrue(all(len(row) == len(header) for row in rows))
        self.assertEqual([(row[header.index("id")], row[-1]) for row in rows], expected)

    def test_mixed_rows_use_own_timestamp_not_parent_or_edited(self):
        for nested in (True, False):
            with self.subTest(nested=nested):
                env = self.envelope(nested)
                self.assert_dates(
                    tidy.render_mixed(env),
                    [
                        ("p1", "2024-02-29T23:59:59Z"),
                        ("c1", "2024-03-01T00:00:00Z"),
                    ],
                )
                self.assertTrue(tidy.render_mixed(env).endswith("next t1_c1"))

    def test_homogeneous_headers_fall_back_to_mixed_without_losing_dates(self):
        env = self.envelope()
        for output in (tidy.render_listing(env, True), tidy.render_comment_list(env)):
            self.assert_dates(
                output,
                [
                    ("p1", "2024-02-29T23:59:59Z"),
                    ("c1", "2024-03-01T00:00:00Z"),
                ],
            )
            self.assertTrue(output.startswith("kind | no |"))

    def test_post_tables_with_and_without_sub(self):
        env = self.envelope()
        env["data"]["data"]["children"].pop()
        for show_sub in (True, False):
            output = tidy.render_listing(env, show_sub)
            self.assert_dates(output, [("p1", "2024-02-29T23:59:59Z")])
            self.assertEqual("sub" in output.splitlines()[0].split(" | "), show_sub)

    def test_comment_missing_date_does_not_borrow_post_date(self):
        env = self.envelope()
        comment = env["data"]["data"]["children"][1]["data"]
        del comment["created_utc"]
        comment["link_created_utc"] = 1709251199
        self.assert_dates(
            tidy.render_mixed(env),
            [
                ("p1", "2024-02-29T23:59:59Z"),
                ("c1", "-"),
            ],
        )
        env["data"]["data"]["children"].pop(0)
        self.assert_dates(tidy.render_comment_list(env), [("c1", "-")])

    def test_dates_keep_empty_table_headers(self):
        for renderer in (
            lambda env: tidy.render_listing(env, True),
            lambda env: tidy.render_listing(env, False),
            tidy.render_comment_list,
            tidy.render_mixed,
        ):
            output = renderer({"ok": True, "data": None})
            self.assertEqual(len(output.splitlines()), 1)
            self.assertTrue(output.endswith(" | created_utc"))

    def test_cli_all_listing_commands_and_timezone_independence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "listing.json"
            for cmd, args, kind in (
                ("feed", [], "t3"),
                ("popular", [], "t3"),
                ("all", [], "t3"),
                ("sub", ["python"], "t3"),
                ("user-posts", ["alice"], "t3"),
                ("search", ["query"], "t3"),
                ("user-comments", ["alice"], "t1"),
                ("saved", [], "mixed"),
                ("upvoted", [], "mixed"),
            ):
                env_data = self.envelope()
                children = env_data["data"]["data"]["children"]
                if kind != "mixed":
                    children[:] = [child for child in children if child["kind"] == kind]
                path.write_text(json.dumps(env_data), encoding="utf-8")
                expected = [
                    (
                        child["data"]["id"],
                        "2024-02-29T23:59:59Z"
                        if child["kind"] == "t3"
                        else "2024-03-01T00:00:00Z",
                    )
                    for child in children
                ]
                outputs = []
                for tz in ("UTC0", "EST5EDT", "JST-9"):
                    with self.subTest(command=cmd, tz=tz):
                        env = dict(os.environ, TZ=tz, RDT_FIXTURE=str(path))
                        env["PATH"] = (
                            str(ROOT / "tests" / "shim")
                            + os.pathsep
                            + env.get("PATH", "")
                        )
                        proc = subprocess.run(
                            [
                                sys.executable,
                                str(ROOT / "rdt-tidy"),
                                "--compact",
                                cmd,
                                *args,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            check=False,
                            env=env,
                        )
                        self.assertEqual(proc.returncode, 0, proc.stderr)
                        self.assert_dates(proc.stdout, expected)
                        outputs.append(proc.stdout)
                self.assertEqual(len(set(outputs)), 1)


if __name__ == "__main__":
    unittest.main()
