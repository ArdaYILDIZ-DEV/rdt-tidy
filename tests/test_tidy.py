#!/usr/bin/env python3
"""rdt-tidy end-to-end tests via a fake rdt shim on PATH."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIDY = os.path.join(ROOT, "rdt-tidy")
SHIMDIR = os.path.join(ROOT, "tests", "shim")
FIX = os.path.join(ROOT, "tests", "fixtures")


def run(env, *args):
    e = dict(os.environ)
    e.update(env)
    e["PATH"] = SHIMDIR + os.pathsep + e.get("PATH", "")
    return subprocess.run(
        [sys.executable, TIDY, *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=e,
    )


def fixture(name):
    return os.path.join(FIX, name)


def read_fixture(name):
    return Path(fixture(name)).read_text(encoding="utf-8")


def last_argv(log):
    return json.loads(Path(log).read_text(encoding="utf-8").strip().splitlines()[-1])


class CompactE2ETest(unittest.TestCase):
    """One isolated tmpdir per test; methods mirror the old section numbers."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.log = os.path.join(self.tmp, "argv.log")

    def write_tmp(self, name, text):
        path = os.path.join(self.tmp, name)
        Path(path).write_text(text, encoding="utf-8")
        return path

    def clear_log(self):
        Path(self.log).write_text("")

    def test_01_compact_listing_shape_and_ratio(self):
        p = run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "sub",
            "python",
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.strip().splitlines()
        self.assertEqual(len(lines), 4, repr(p.stdout))
        self.assertEqual(lines[0], "no | score | title | author | id", lines[0])
        self.assertNotIn("r/python", lines[1], lines[1])
        self.assertTrue(lines[1].endswith("| 1abc11"), lines[1])
        self.assertEqual(lines[3], "next t3_1abc22", lines[3])
        raw = read_fixture("listing.json")
        # Header adds a fixed ~35 bytes; 1/4 is the small-fixture bound
        # (live data observes ~1/20, 54KB -> 2.7KB).
        self.assertLessEqual(
            len(p.stdout) * 4, len(raw), f"{len(p.stdout)} vs {len(raw)}"
        )

    def test_02_limit_caps_and_defaults(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "search",
            "x",
            "-n",
            "50",
        )
        argv = last_argv(self.log)
        self.assertIn("10", argv, repr(argv))
        self.assertNotIn("50", argv, repr(argv))
        self.clear_log()
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "search",
            "x",
        )
        argv = last_argv(self.log)
        self.assertIn("-n", argv, repr(argv))
        self.assertIn("5", argv, repr(argv))
        self.assertIn("--json", argv, repr(argv))

    def test_03_feed_subs_only_cap(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "feed",
            "--subs-only",
            "--max-subs",
            "20",
            "-n",
            "25",
        )
        argv = last_argv(self.log)
        self.assertIn("5", argv, repr(argv))
        self.assertNotIn("20", argv, repr(argv))
        self.assertNotIn("25", argv, repr(argv))

    def test_04_read_raw_listing_shape(self):
        p = run(
            {"RDT_FIXTURE": fixture("comments_raw.json")}, "--compact", "read", "1abc11"
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout
        self.assertTrue(
            out.splitlines()[0].startswith("# 1abc11 r/python"), out.splitlines()[0]
        )
        self.assertIn("uzun govde " * 5, out, out[:200])
        self.assertNotIn("[...]", out, out[:200])
        self.assertIn("\n  u/zeynep", out, out)
        self.assertIn("\nu/dave", out, out)
        self.assertIn("\nu/erin", out, out)
        self.assertIn("+2 more", out, out)
        self.assertNotIn("awardings", out, "")
        self.assertNotIn("selftext_html", out, "")
        raw = read_fixture("comments_raw.json")
        self.assertLessEqual(len(out) * 2, len(raw), f"{len(out)} vs {len(raw)}")

    def test_05_read_typed_detail_shape(self):
        p = run(
            {"RDT_FIXTURE": fixture("detail_typed.json")}, "--compact", "read", "9zz"
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.splitlines()[0].startswith("# 9zz r/go"), p.stdout)
        self.assertIn("\n  u/deli", p.stdout, p.stdout)
        self.assertIn("\nu/veli", p.stdout, p.stdout)
        self.assertIn("+4 more", p.stdout, p.stdout)

    def test_06_error_passthrough(self):
        p = run({"RDT_FIXTURE": fixture("error.json")}, "--compact", "search", "x")
        self.assertEqual(p.returncode, 1, str(p.returncode))
        self.assertEqual(
            p.stdout.strip(),
            "ERR forbidden: Access forbidden: Resource",
            repr(p.stdout),
        )

    def test_07_passthrough_is_byte_identical(self):
        p = run({"RDT_FIXTURE": fixture("listing.json")}, "sub", "python", "-n", "2")
        self.assertEqual(p.stdout, read_fixture("listing.json"), repr(p.stdout[:100]))
        self.assertEqual(p.returncode, 0, repr(p.stdout[:100]))

    def test_08_subinfo_user_whoami(self):
        p = run(
            {"RDT_FIXTURE": fixture("subinfo.json")}, "--compact", "sub-info", "python"
        )
        self.assertEqual(len(p.stdout.strip().splitlines()), 3, repr(p.stdout))
        self.assertNotIn("banner_img", p.stdout, "")
        self.assertNotIn("<p>", p.stdout, "")
        p = run({"RDT_FIXTURE": fixture("user.json")}, "--compact", "user", "spez")
        self.assertEqual(
            p.stdout.strip(),
            "u/spez post:100 comment:200 age:2005-09-12",
            repr(p.stdout),
        )
        p = run({"RDT_FIXTURE": fixture("whoami.json")}, "--compact", "whoami")
        self.assertEqual(
            p.stdout.strip().splitlines(),
            ["u/spez post:100 comment:200 age:2005-09-12", "sess read,vote modhash:1"],
            repr(p.stdout),
        )

    def test_09_user_comments_keep_full_body(self):
        p = run(
            {"RDT_FIXTURE": fixture("ucomments.json")},
            "--compact",
            "user-comments",
            "u1",
        )
        self.assertNotIn("[...]", p.stdout, repr(p.stdout))
        self.assertEqual(
            p.stdout.splitlines()[0],
            "no | author | score | sub | body | id",
            repr(p.stdout),
        )
        self.assertTrue(
            p.stdout.splitlines()[1].startswith("1 | u/u1 | +9 | r/python | yor"),
            repr(p.stdout),
        )
        self.assertTrue(p.stdout.splitlines()[1].endswith("| k1"), repr(p.stdout))

    def test_10_saved_mixes_post_comment_kinds(self):
        p = run({"RDT_FIXTURE": fixture("mixed.json")}, "--compact", "saved")
        ls = p.stdout.strip().splitlines()
        self.assertEqual(
            ls[0], "kind | no | score | sub | title/body | author | id", repr(p.stdout)
        )
        self.assertTrue(
            ls[1].startswith("P | 1 ") and ls[2].startswith("C | 2 "), repr(p.stdout)
        )

    def test_11_compact_export_requires_o(self):
        p = run({}, "--compact", "export", "x")
        self.assertEqual(p.returncode, 2, str(p.returncode))
        out_csv = os.path.join(self.tmp, "out.txt")
        csv_text = (
            "title,subreddit,author,score,num_comments,url,permalink\n"
            "Hello world,python,ali,10,3,https://ex.com/a,/r/python/a/\n"
        )
        p = run({"RDT_EXPORT_CSV": csv_text}, "--compact", "export", "x", "-o", out_csv)
        self.assertEqual(p.returncode, 0, p.stderr)
        content = Path(out_csv).read_text(encoding="utf-8")
        self.assertEqual(
            content.strip(),
            "score | sub | title | author | url\n"
            "+10c3 | r/python | Hello world | u/ali | https://ex.com/a",
            repr(content),
        )
        self.assertEqual(p.stdout.strip(), f"saved {out_csv} (1 rows)", repr(p.stdout))

    def test_12_trailing_c_stays_with_rdt(self):
        p = run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "comment",
            "3",
            "-c",
        )
        argv = last_argv(self.log)
        self.assertEqual(argv, ["comment", "3", "-c"], repr(argv))
        self.assertEqual(p.stdout, read_fixture("listing.json"), "")

    def test_13_trailing_compact_does_not_enable_tidy_mode(self):
        p = run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "sub",
            "python",
            "--compact",
        )
        argv = last_argv(self.log)
        self.assertIn("--compact", argv, repr(argv))
        self.assertEqual(p.stdout, read_fixture("listing.json"), repr(argv))

    def test_14_tidy_strips_rdt_compact_for_backend(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "search",
            "x",
            "--compact",
        )
        argv = last_argv(self.log)
        self.assertNotIn("--compact", argv, repr(argv))
        self.assertIn("--json", argv, repr(argv))

    def test_15_compact_forces_json_over_yaml(self):
        p = run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "sub",
            "python",
            "--yaml",
        )
        argv = last_argv(self.log)
        self.assertNotIn("--yaml", argv, repr(argv))
        self.assertIn("--json", argv, repr(argv))
        self.assertTrue(
            p.stdout.splitlines()[1].startswith("1 | "), repr(p.stdout[:80])
        )

    def test_16_empty_stdout_becomes_err(self):
        empty = self.write_tmp("empty.json", "")
        p = run({"RDT_FIXTURE": empty}, "--compact", "sub", "python")
        self.assertEqual(p.returncode, 1, repr((p.returncode, p.stdout)))
        self.assertTrue(
            p.stdout.startswith("ERR backend:"), repr((p.returncode, p.stdout))
        )

    def test_17_packed_n50_clamped(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "search",
            "x",
            "-n50",
        )
        argv = last_argv(self.log)
        self.assertIn("-n10", argv, repr(argv))
        self.assertNotIn("-n50", argv, repr(argv))

    def test_18_dash_led_query_keeps_default_limit(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "search",
            "-nonsense",
        )
        argv = last_argv(self.log)
        self.assertGreaterEqual(argv.count("-n"), 1, repr(argv))
        self.assertIn("5", argv, repr(argv))
        self.assertIn("-nonsense", argv, repr(argv))

    def test_19_unknown_command_passes_through(self):
        p = run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "frobnicate",
            "--x",
        )
        argv = last_argv(self.log)
        self.assertEqual(argv, ["frobnicate", "--x"], repr(argv))
        self.assertEqual(p.stdout, read_fixture("listing.json"), repr(argv))

    def test_20_negative_score_prints_minus(self):
        p = run({"RDT_FIXTURE": fixture("neg.json")}, "--compact", "sub", "s")
        self.assertTrue(
            p.stdout.splitlines()[1].startswith("1 | -5c0 | "), repr(p.stdout)
        )

    def test_21_flag_position_and_dashdash(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "-c",
            "search",
            "-c",
        )
        argv = last_argv(self.log)
        self.assertEqual(argv, ["search", "-n", "5", "--json"], repr(argv))
        self.clear_log()
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "-c",
            "search",
            "--",
            "-c",
        )
        argv = last_argv(self.log)
        self.assertEqual(argv, ["search", "-n", "5", "--json", "--", "-c"], repr(argv))

    def test_22_file_output_preserves_raw_limit(self):
        out1 = os.path.join(self.tmp, "list-out.txt")
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "sub",
            "python",
            "-n",
            "50",
            "-o",
            out1,
        )
        argv = last_argv(self.log)
        self.assertIn("50", argv, repr(argv))
        self.assertNotIn("10", argv, repr(argv))
        self.assertNotIn("--json", argv, repr(argv))
        out2 = os.path.join(self.tmp, "list-out2.txt")
        self.clear_log()
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "sub",
            "python",
            "-n",
            "50",
            f"--output={out2}",
        )
        argv = last_argv(self.log)
        self.assertIn("50", argv, repr(argv))
        self.assertNotIn("10", argv, repr(argv))

    def test_23_subs_only_equals_form_triggers_cap(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "feed",
            "--subs-only=true",
            "--max-subs",
            "20",
            "-n",
            "25",
        )
        argv = last_argv(self.log)
        self.assertIn("5", argv, repr(argv))
        self.assertNotIn("20", argv, repr(argv))
        self.assertNotIn("25", argv, repr(argv))

    def test_24_export_missing_file_is_backend_discrepancy(self):
        missing = os.path.join(self.tmp, "never-written.csv")
        p = run({"RDT_EXPORT_SKIP": "1"}, "--compact", "export", "x", "-o", missing)
        self.assertEqual(p.returncode, 1, str(p.returncode))
        self.assertEqual(
            p.stderr.strip(),
            f"ERR backend: export did not write {missing}",
            repr((p.stdout, p.stderr)),
        )
        self.assertNotIn("ERR io", p.stderr, repr(p.stderr))

    def test_25_dashdash_escapes_help_flags(self):
        p = run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "search",
            "--",
            "-h",
        )
        argv = last_argv(self.log)
        self.assertEqual(argv, ["search", "-n", "5", "--json", "--", "-h"], repr(argv))
        self.assertEqual(
            p.stdout.splitlines()[0],
            "no | score | sub | title | author | id",
            repr(p.stdout[:80]),
        )

    def test_26_empty_envelope_renders_header_only(self):
        empty_env = self.write_tmp("empty_env.json", '{"ok": true}')
        p = run({"RDT_FIXTURE": empty_env}, "--compact", "search", "x")
        self.assertEqual(p.returncode, 0, repr((p.returncode, p.stderr)))
        self.assertEqual(
            p.stdout.strip(), "no | score | sub | title | author | id", repr(p.stdout)
        )

    def test_27_null_data_node(self):
        null_env = self.write_tmp("null_data.json", '{"ok": true, "data": null}')
        p = run({"RDT_FIXTURE": null_env}, "--compact", "search", "x")
        self.assertEqual(p.returncode, 0, repr((p.returncode, p.stderr)))
        self.assertIn("no | score", p.stdout, repr(p.stdout))

    def test_28_non_dict_envelope_is_controlled_err(self):
        arr_env = self.write_tmp("arr.json", "[]")
        p = run({"RDT_FIXTURE": arr_env}, "--compact", "search", "x")
        self.assertEqual(p.returncode, 1, str(p.returncode))
        self.assertIn(
            "ERR backend: invalid envelope", p.stdout, repr((p.stdout, p.stderr))
        )
        scalar_env = self.write_tmp("scalar.json", '"oops"')
        p = run({"RDT_FIXTURE": scalar_env}, "--compact", "search", "x")
        self.assertEqual(p.returncode, 1, str(p.returncode))
        self.assertIn(
            "ERR backend: invalid envelope", p.stdout, repr((p.stdout, p.stderr))
        )

    def test_29_doubledash_synthesized_opts_precede_separator(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "-c",
            "search",
            "--",
            "-c",
        )
        argv = last_argv(self.log)
        self.assertEqual(argv, ["search", "-n", "5", "--json", "--", "-c"], repr(argv))

    def test_30_packed_numeric_flag_keeps_subs_only(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "feed",
            "--subs-only",
            "-n=25",
        )
        argv = last_argv(self.log)
        self.assertIn("--subs-only", argv, repr(argv))
        self.assertNotIn("25", argv, repr(argv))

    def test_31_missing_subreddit_keeps_column_count(self):
        missing_sub = self.write_tmp(
            "missing_sub.json",
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "data": {
                            "children": [
                                {
                                    "kind": "t3",
                                    "data": {
                                        "id": "a1",
                                        "title": "t",
                                        "author": "a",
                                        "score": 1,
                                        "num_comments": 0,
                                    },
                                },
                            ],
                            "after": None,
                        }
                    },
                }
            ),
        )
        p = run({"RDT_FIXTURE": missing_sub}, "--compact", "search", "x")
        self.assertIn("r/?", p.stdout, repr(p.stdout))
        self.assertEqual(
            len(p.stdout.splitlines()[1].split(" | ")),
            len(["no", "score", "sub", "title", "author", "id"]),
            repr(p.stdout),
        )

    def test_32_export_default_cap_injects_n50(self):
        out3 = os.path.join(self.tmp, "exp3.csv")
        csv_text2 = (
            "title,subreddit,author,score,num_comments,url\n" "t,s,a,1,0,http://e.com\n"
        )
        run(
            {"RDT_EXPORT_CSV": csv_text2, "RDT_ARGV_LOG": self.log},
            "--compact",
            "export",
            "x",
            "-o",
            out3,
        )
        argv = last_argv(self.log)
        self.assertIn("-n", argv, repr(argv))
        self.assertIn("50", argv, repr(argv))

    def test_33_invalid_json_forwards_stderr(self):
        bad_json = self.write_tmp("bad.json", "not-json\n")
        p = run(
            {"RDT_FIXTURE": bad_json, "RDT_EXIT": "1", "RDT_STDERR": "boom-stderr\n"},
            "--compact",
            "search",
            "x",
        )
        self.assertEqual(p.returncode, 1, str(p.returncode))
        self.assertEqual(p.stdout, "not-json\n", repr(p.stdout))
        self.assertIn("boom-stderr", p.stderr, repr(p.stderr))

    def test_34_export_strips_compact_and_yaml_flags(self):
        out4 = os.path.join(self.tmp, "exp4.csv")
        csv_text2 = (
            "title,subreddit,author,score,num_comments,url\n" "t,s,a,1,0,http://e.com\n"
        )
        run(
            {"RDT_EXPORT_CSV": csv_text2, "RDT_ARGV_LOG": self.log},
            "--compact",
            "export",
            "-c",
            "x",
            "-o",
            out4,
            "--yaml",
            "--compact",
        )
        argv = last_argv(self.log)
        self.assertNotIn("-c", argv, repr(argv))
        self.assertNotIn("--compact", argv, repr(argv))
        self.assertNotIn("--yaml", argv, repr(argv))
        self.assertIn("--format", argv, repr(argv))
        self.assertIn("csv", argv, repr(argv))

    def test_35_count_flag_clamped(self):
        run(
            {"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": self.log},
            "--compact",
            "search",
            "x",
            "--count",
            "50",
        )
        argv = last_argv(self.log)
        self.assertIn("--count", argv, repr(argv))
        self.assertIn("10", argv, repr(argv))
        self.assertNotIn("-n", argv, repr(argv))

    def test_36_self_post_query_params_emit_no_link(self):
        self_post_query = self.write_tmp(
            "self_query.json",
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "post": {
                            "id": "sq1",
                            "title": "Self Query",
                            "subreddit": "test",
                            "author": "tester",
                            "score": 5,
                            "num_comments": 0,
                            "url": "https://www.reddit.com/r/test/comments/sq1/self_query/?utm_source=share",
                            "permalink": "/r/test/comments/sq1/self_query/",
                            "is_self": None,
                        },
                        "comments": [],
                        "more_count": 0,
                    },
                }
            ),
        )
        p = run({"RDT_FIXTURE": self_post_query}, "--compact", "read", "sq1")
        self.assertNotIn("LINK", p.stdout, repr(p.stdout))

    def test_37_null_author_emits_unknown_user(self):
        null_author_comment = self.write_tmp(
            "null_author.json",
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "post": {
                            "id": "na1",
                            "title": "Null Author",
                            "subreddit": "test",
                            "author": "tester",
                            "score": 5,
                            "num_comments": 1,
                        },
                        "comments": [
                            {
                                "author": None,
                                "body": "null author body",
                                "score": 2,
                                "depth": 0,
                            }
                        ],
                        "more_count": 0,
                    },
                }
            ),
        )
        p = run({"RDT_FIXTURE": null_author_comment}, "--compact", "read", "na1")
        self.assertIn("u/? +2: null author body", p.stdout, repr(p.stdout))


if __name__ == "__main__":
    unittest.main(verbosity=1)
