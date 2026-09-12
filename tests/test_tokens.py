#!/usr/bin/env python3
"""Unit tests for TokenView edge cases (no e2e shim)."""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader(
    "rdt_tidy", os.path.join(ROOT, "rdt-tidy")
)
_spec = importlib.util.spec_from_loader("rdt_tidy", _loader)
_mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(_mod)

TokenView = _mod.TokenView
backend_args = _mod.backend_args
TIDY_FLAGS = _mod.TIDY_FLAGS
check_error = _mod.check_error
_looks_like_flag = _mod._looks_like_flag
EX_BACKEND = _mod.EX_BACKEND
EX_OK = _mod.EX_OK
parse_detail = _mod.parse_detail
render_detail = _mod.render_detail
_envelope_data = _mod._envelope_data
_listing_children = _mod._listing_children
render_listing = _mod.render_listing
render_mixed = _mod.render_mixed
_post_cells = _mod._post_cells
post_line = _mod.post_line
load_envelope = _mod.load_envelope
LISTING_HEADER = _mod.LISTING_HEADER
EXPORT_CAP_N = _mod.EXPORT_CAP_N
_comment_cells = _mod._comment_cells
_raw_comment_of = _mod._raw_comment_of
render_user = _mod.render_user
render_status = _mod.render_status
_compact_list_view = _mod._compact_list_view
LIMIT_FLAGS = _mod.LIMIT_FLAGS


class TokenViewTest(unittest.TestCase):
    def test_cap_separate_value(self):
        v = TokenView(["search", "x", "-n", "50"])
        v.cap({"-n", "--limit"}, 10)
        self.assertEqual(v.tokens, ["search", "x", "-n", "10"])

    def test_cap_equals_form(self):
        v = TokenView(["search", "x", "--limit=50"])
        v.cap({"-n", "--limit"}, 10)
        self.assertEqual(v.tokens, ["search", "x", "--limit=10"])

    def test_cap_packed_short(self):
        v = TokenView(["search", "x", "-n50"])
        v.cap({"-n", "--limit"}, 10)
        self.assertEqual(v.tokens, ["search", "x", "-n10"])

    def test_cap_below_cap_untouched(self):
        v = TokenView(["search", "x", "-n", "3"])
        v.cap({"-n", "--limit"}, 10)
        self.assertEqual(v.tokens, ["search", "x", "-n", "3"])

    def test_cap_ignores_dash_query(self):
        v = TokenView(["search", "-nonsense"])
        v.cap({"-n", "--limit"}, 10)
        v.ensure("-n", "5", {"-n", "--limit"})
        self.assertEqual(v.tokens, ["search", "-nonsense", "-n", "5"])

    def test_ensure_existing_untouched(self):
        v = TokenView(["search", "x", "-n", "3"])
        v.ensure("-n", "5", {"-n", "--limit"})
        self.assertEqual(v.tokens, ["search", "x", "-n", "3"])

    def test_value_forms(self):
        self.assertEqual(
            TokenView(["export", "x", "-o", "f.txt"]).value({"-o", "--output"}), "f.txt"
        )
        self.assertEqual(
            TokenView(["export", "x", "--output=f.txt"]).value({"-o", "--output"}),
            "f.txt",
        )
        self.assertIsNone(TokenView(["export", "x"]).value({"-o", "--output"}))

    def test_value_packed_short(self):
        self.assertEqual(
            TokenView(["search", "x", "-n50"]).value({"-n", "--limit"}), "50"
        )

    def test_drop_bare_flags(self):
        v = TokenView(["search", "x", "--compact", "--yaml"])
        v.drop(TIDY_FLAGS | {"--yaml"})
        self.assertEqual(v.tokens, ["search", "x"])

    def test_drop_keeps_positional_after_dashdash(self):
        v = TokenView(["search", "--", "-c"])
        v.drop({"-c", "--compact"})
        self.assertEqual(v.tokens, ["search", "--", "-c"])

    def test_drop_keeps_option_value(self):
        v = TokenView(["-o", "-c"])
        v.drop({"-c", "--compact"})
        self.assertEqual(v.tokens, ["-o", "-c"])

    def test_negative_number_is_positional(self):
        v = TokenView(["search", "-5"])
        self.assertEqual(v.kinds, ["p", "p"])
        v.cap({"-n", "--limit"}, 10)
        self.assertEqual(v.tokens, ["search", "-5"])

    def test_has_json_equals_form(self):
        self.assertTrue(TokenView(["sub", "x", "--json=true"]).has({"--json"}))

    def test_backend_args_flow(self):
        self.assertEqual(
            backend_args(TokenView(["search", "--", "-c"])),
            ["search", "--json", "--", "-c"],
        )
        self.assertEqual(
            backend_args(TokenView(["search", "x", "--compact"])),
            ["search", "x", "--json"],
        )

    def test_kinds_stay_in_sync(self):
        v = TokenView(["search", "x", "-n", "50", "--compact"])
        v.cap({"-n", "--limit"}, 10).ensure("-n", "5", {"-n", "--limit"})
        v.drop(TIDY_FLAGS | {"--yaml"}).add_bare("--json")
        self.assertEqual(len(v.kinds), len(v.tokens))
        self.assertEqual(v.tokens, ["search", "x", "-n", "10", "--json"])


class CheckErrorTest(unittest.TestCase):
    """check_error falls back to neutral English, never synthetic locale text."""

    def _run(self, env):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as ctx:
            check_error(env)
        return ctx.exception.code, buf.getvalue()

    def test_missing_message_key(self):
        code, out = self._run({"ok": False, "error": {"code": "forbidden"}})
        self.assertEqual(code, EX_BACKEND)
        self.assertEqual(out.strip(), "ERR forbidden: unknown error")

    def test_missing_error_envelope(self):
        code, out = self._run({"ok": False})
        self.assertEqual(code, EX_BACKEND)
        self.assertEqual(out.strip(), "ERR backend: unknown error")

    def test_empty_string_message(self):
        # Key present but empty: squish("") stays empty, no fallback invented.
        code, out = self._run({"ok": False, "error": {"code": "x", "message": ""}})
        self.assertEqual(code, EX_BACKEND)
        self.assertEqual(out.strip(), "ERR x:")

    def test_none_message(self):
        # Key present with None: squish(str(None)) -> "None"; locked as-is.
        code, out = self._run({"ok": False, "error": {"code": "x", "message": None}})
        self.assertEqual(code, EX_BACKEND)
        self.assertEqual(out.strip(), "ERR x: None")

    def test_non_dict_info(self):
        code, out = self._run({"ok": False, "error": "boom"})
        self.assertEqual(code, EX_BACKEND)
        self.assertEqual(out.strip(), "ERR backend: boom")

    def test_ok_true_is_silent(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            check_error({"ok": True, "data": {}})
        self.assertEqual(buf.getvalue(), "")

    def test_error_key_without_ok_triggers_error(self):
        code, out = self._run({"error": {"code": "gone", "message": "deleted"}})
        self.assertEqual(code, EX_BACKEND)
        self.assertEqual(out.strip(), "ERR gone: deleted")

    def test_error_key_with_ok_true_is_silent(self):
        # Explicit ok:true overrides the error key presence heuristic.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            check_error({"ok": True, "error": {"code": "x", "message": "y"}})
        self.assertEqual(buf.getvalue(), "")


class LooksLikeFlagTest(unittest.TestCase):
    """Direct _looks_like_flag edge cases: flags vs numbers vs text."""

    def test_true_cases(self):
        for tok in ["-f", "--flag", "--subs-only=true", "-o", "-nonsense"]:
            with self.subTest(token=tok):
                self.assertTrue(_looks_like_flag(tok), tok)

    def test_false_cases(self):
        for tok in ["-5", "-3.14", "-0.5", "-", "plain_arg", "sub"]:
            with self.subTest(token=tok):
                self.assertFalse(_looks_like_flag(tok), tok)

    def test_double_dash_separator(self):
        # "--" returns True from the helper in isolation, but _classify
        # handles it earlier as the positional separator, so this path is
        # unreachable via TokenView; locked as documented current behavior.
        self.assertTrue(_looks_like_flag("--"))
        v = TokenView(["search", "--", "-c"])
        self.assertEqual(v.kinds, ["p", "f", "p"])


class SubsOnlyTest(unittest.TestCase):
    """--subs-only recognition routes through TokenView.has()."""

    def test_bare_flag(self):
        self.assertTrue(TokenView(["feed", "--subs-only"]).has({"--subs-only"}))

    def test_equals_true(self):
        self.assertTrue(TokenView(["feed", "--subs-only=true"]).has({"--subs-only"}))

    def test_equals_false_still_matches_head(self):
        # Head-split matching: value assignments match the flag head.
        # Locked as documented grammar behavior (cap applies whenever the
        # flag is present, regardless of the assigned value).
        self.assertTrue(TokenView(["feed", "--subs-only=false"]).has({"--subs-only"}))

    def test_after_double_dash_is_positional(self):
        self.assertFalse(TokenView(["feed", "--", "--subs-only"]).has({"--subs-only"}))

    def test_absent(self):
        self.assertFalse(TokenView(["feed", "-n", "5"]).has({"--subs-only"}))


class ParseDetailTest(unittest.TestCase):
    """Dict and list envelopes parse without shared-state leakage."""

    def test_dict_shape(self):
        data = {
            "post": {"id": "p1", "title": "t"},
            "comments": [{"author": "a", "body": "b", "score": 1, "replies": []}],
            "more_count": 2,
        }
        post, comments, more = parse_detail(data)
        self.assertEqual(post, {"id": "p1", "title": "t"})
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["depth"], 0)
        self.assertEqual(more, 2)

    def test_list_shape(self):
        data = [
            {"data": {"children": [{"data": {"id": "p1", "title": "t"}}]}},
            {
                "data": {
                    "children": [
                        {
                            "kind": "t1",
                            "data": {
                                "author": "a",
                                "body": "b",
                                "score": 1,
                                "replies": {},
                            },
                        },
                    ]
                }
            },
        ]
        post, comments, more = parse_detail(data)
        self.assertEqual(post.get("id"), "p1")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["author"], "a")
        self.assertEqual(more, 0)

    def test_no_state_leak_between_calls(self):
        dict_data = {
            "post": {"id": "p1"},
            "comments": [{"author": "a", "body": "b", "score": 1, "replies": []}],
            "more_count": 0,
        }
        parse_detail(dict_data)
        post, comments, more = parse_detail([])
        self.assertEqual((post, comments, more), ({}, [], 0))

    def test_top_level_comment_more_count(self):
        data = {
            "post": {"id": "p1", "title": "t"},
            "comments": [
                {"author": "u1", "body": "c1", "more_count": 5, "replies": []}
            ],
            "more_count": 0,
        }
        post, comments, more = parse_detail(data)
        self.assertEqual(post["title"], "t")
        self.assertEqual(len(comments), 1)
        self.assertEqual(more, 5)

    def test_empty_inputs(self):
        self.assertEqual(parse_detail({}), ({}, [], 0))
        self.assertEqual(parse_detail([]), ({}, [], 0))
        self.assertEqual(parse_detail(None), ({}, [], 0))


class RenderDetailTest(unittest.TestCase):
    """Multi-line bodies keep line breaks at any depth."""

    def test_multiline_top_level_comment(self):
        # Top-level append(text) must equal extend(splitlines) once joined:
        # no newline may be lost or merged into one line.
        env = {
            "data": {
                "post": {
                    "id": "x",
                    "subreddit": "s",
                    "title": "t",
                    "author": "a",
                    "score": 1,
                    "num_comments": 1,
                },
                "comments": [
                    {
                        "author": "u1",
                        "body": "line1\nline2\n\nline3",
                        "score": 1,
                        "depth": 0,
                    }
                ],
                "more_count": 0,
            }
        }
        out = render_detail(env)
        self.assertIn("u/u1 +1: line1", out)
        self.assertIn("\nline2\n\nline3", out)
        self.assertEqual(out.splitlines()[2], "u/u1 +1: line1")

    def test_multiline_reply_stays_indented(self):
        # Dict-shape replies come from the nested "replies" list
        # (parse_detail forces top-level nodes to depth 0).
        env = {
            "data": {
                "post": {
                    "id": "x",
                    "subreddit": "s",
                    "title": "t",
                    "author": "a",
                    "score": 1,
                    "num_comments": 2,
                },
                "comments": [
                    {
                        "author": "u0",
                        "body": "top",
                        "score": 1,
                        "replies": [{"author": "u1", "body": "a1\na2", "score": 1}],
                    }
                ],
                "more_count": 0,
            }
        }
        out = render_detail(env)
        self.assertIn("  u/u1 +1: a1", out)
        self.assertIn("\n  a2", out)


class RegressionTest(unittest.TestCase):
    """Targeted defect remediation tests (task directive Phase 2-3)."""

    def test_empty_envelope_no_keyerror(self):
        # {"ok": true} without data renders header only.
        self.assertEqual(_envelope_data({"ok": True}), {})
        items, after = _listing_children({"ok": True})
        self.assertEqual((items, after), ([], None))
        out = render_listing({"ok": True}, show_sub=True)
        self.assertEqual(out.strip(), LISTING_HEADER)

    def test_null_data_node_no_attribute_error(self):
        # Reddit truncated listings legitimately return data:null.
        self.assertEqual(_envelope_data({"ok": True, "data": None}), {})
        items, after = _listing_children({"ok": True, "data": None})
        self.assertEqual((items, after), ([], None))
        # Raw null children inside a listing must not crash either.
        env = {
            "ok": True,
            "data": {
                "data": {
                    "children": [
                        {"kind": "t3", "data": None},
                        {"kind": "t3", "data": {"id": "a1", "title": "t"}},
                    ],
                    "after": None,
                }
            },
        }
        items, _ = _listing_children(env)
        self.assertEqual(len(items), 1)

    def test_non_dict_envelope_controlled(self):
        self.assertEqual(_envelope_data([]), {})
        self.assertEqual(_envelope_data("oops"), {})
        # _run_compact guards non-dict envelopes; renderers stay total.
        out = render_listing([], show_sub=True)
        self.assertIn(LISTING_HEADER, out)

    def test_double_dash_insertion(self):
        v = TokenView(["search", "--", "-c"])
        v.ensure("-n", "5", {"-n", "--limit"})
        v.add_bare("--json")
        self.assertEqual(v.tokens, ["search", "-n", "5", "--json", "--", "-c"])
        # Value tokens after -- stay positional, never treated as options.
        self.assertFalse(TokenView(["search", "--", "-n", "5"]).has({"-n", "--limit"}))

    def test_packed_numeric_flag_classification(self):
        # -n=5 packs its value; --subs-only stays a flag, not a value.
        v = TokenView(["search", "-n=5", "--subs-only"])
        self.assertEqual(v.kinds, ["p", "f", "f"])
        self.assertEqual(v.value({"-n", "--limit"}), "5")
        self.assertTrue(v.has({"--subs-only"}))

    def test_packed_string_flag(self):
        v = TokenView(["export", "x", "-otips.txt"])
        self.assertIn(v._option_slot(2)[0], {"-o"})
        self.assertEqual(v.value({"-o", "--output"}), "tips.txt")
        self.assertEqual(
            TokenView(["cmd", "-rSub"]).value({"-r", "--subreddit"}), "Sub"
        )
        self.assertEqual(TokenView(["cmd", "-sTop"]).value({"-s", "--sort"}), "Top")

    def test_duplicate_flags_last_wins(self):
        v = TokenView(["export", "x", "-o", "first.txt", "-o", "second.txt"])
        self.assertEqual(v.value({"-o", "--output"}), "second.txt")

    def test_missing_subreddit_invariant(self):
        row = _post_cells(1, {"id": "a1", "title": "t", "author": "a"})
        self.assertEqual(row["sub"], "r/?")
        line = post_line(1, {"id": "a1", "title": "t", "author": "a"}, show_sub=True)
        self.assertIn("r/?", line)
        self.assertEqual(len(line.split(" | ")), len(LISTING_HEADER.split(" | ")))

    def test_remove_valued_options(self):
        v = TokenView(["export", "x", "--format", "csv", "-o", "f.txt"])
        v.remove({"--format"})
        self.assertEqual(v.tokens, ["export", "x", "-o", "f.txt"])
        v2 = TokenView(["export", "x", "--format=csv"])
        v2.remove({"--format"})
        self.assertEqual(v2.tokens, ["export", "x"])

    def test_backend_error_passthrough_forwards_stderr(self):
        import subprocess

        proc = subprocess.CompletedProcess(
            args=["rdt", "search"],
            returncode=1,
            stdout="not-json\n",
            stderr="boom-stderr\n",
        )
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(
            err_buf
        ), self.assertRaises(SystemExit) as ctx:
            load_envelope(proc)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(out_buf.getvalue(), "not-json\n")
        self.assertEqual(err_buf.getvalue(), "boom-stderr\n")

    def test_raw_nested_depth_comments_and_more(self):
        data = [
            {"data": {"children": [{"data": {"id": "p1", "title": "Post Title"}}]}},
            {
                "data": {
                    "children": [
                        {
                            "kind": "t1",
                            "data": {
                                "id": "c1",
                                "author": "u1",
                                "body": "depth-0",
                                "score": 1,
                                "replies": {
                                    "data": {
                                        "children": [
                                            {
                                                "kind": "t1",
                                                "data": {
                                                    "id": "c2",
                                                    "author": "u2",
                                                    "body": "depth-1",
                                                    "score": 1,
                                                    "replies": {
                                                        "data": {
                                                            "children": [
                                                                {
                                                                    "kind": "t1",
                                                                    "data": {
                                                                        "id": "c3",
                                                                        "author": "u3",
                                                                        "body": "depth-2",
                                                                        "score": 1,
                                                                        "replies": {
                                                                            "data": {
                                                                                "children": [
                                                                                    {
                                                                                        "kind": "more",
                                                                                        "data": {
                                                                                            "children": [
                                                                                                "c4",
                                                                                                "c5",
                                                                                            ]
                                                                                        },
                                                                                    }
                                                                                ]
                                                                            }
                                                                        },
                                                                    },
                                                                }
                                                            ]
                                                        }
                                                    },
                                                },
                                            }
                                        ]
                                    }
                                },
                            },
                        },
                        {"kind": "more", "data": {"children": ["c6"]}},
                    ]
                }
            },
        ]
        post, comments, more = parse_detail(data)
        self.assertEqual(post.get("id"), "p1")
        self.assertEqual(len(comments), 3, f"Expected 3 comments, got {len(comments)}")
        self.assertEqual(comments[0]["depth"], 0)
        self.assertEqual(comments[1]["depth"], 1)
        self.assertEqual(comments[2]["depth"], 1)
        self.assertEqual(more, 3)

    def test_typed_nested_depth_comments_and_more(self):
        data = {
            "post": {"id": "p1", "title": "Post Title"},
            "comments": [
                {
                    "author": "u1",
                    "body": "depth-0",
                    "score": 1,
                    "replies": [
                        {
                            "author": "u2",
                            "body": "depth-1",
                            "score": 1,
                            "replies": [
                                {
                                    "author": "u3",
                                    "body": "depth-2",
                                    "score": 1,
                                    "replies": [
                                        {
                                            "author": "[more]",
                                            "more_count": 2,
                                            "more_children": ["x", "y"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "more_count": 1,
        }
        post, comments, more = parse_detail(data)
        self.assertEqual(len(comments), 3, f"Expected 3 comments, got {len(comments)}")
        self.assertEqual(post.get("id"), "p1")
        self.assertEqual(len(comments), 3, f"Expected 3 comments, got {len(comments)}")
        self.assertEqual(comments[0]["depth"], 0)
        self.assertEqual(comments[1]["depth"], 1)
        self.assertEqual(comments[2]["depth"], 1)
        self.assertEqual(more, 3)

    def test_render_detail_is_self_fallback(self):
        # 1. Missing is_self with external URL -> emits LINK
        env1 = {
            "data": {
                "post": {
                    "id": "p1",
                    "title": "t",
                    "url": "https://example.com/art",
                    "permalink": "/r/news/comments/p1/t/",
                },
                "comments": [],
                "more_count": 0,
            }
        }
        out1 = render_detail(env1)
        self.assertIn("LINK https://example.com/art", out1)

        # 2. is_self is None with external URL -> emits LINK
        env2 = {
            "data": {
                "post": {
                    "id": "p1",
                    "title": "t",
                    "url": "https://example.com/art",
                    "permalink": "/r/news/comments/p1/t/",
                    "is_self": None,
                },
                "comments": [],
                "more_count": 0,
            }
        }
        out2 = render_detail(env2)
        self.assertIn("LINK https://example.com/art", out2)

        # 3. is_self is None with url matching permalink -> no LINK
        env3 = {
            "data": {
                "post": {
                    "id": "p1",
                    "title": "t",
                    "url": "https://www.reddit.com/r/news/comments/p1/t/",
                    "permalink": "/r/news/comments/p1/t/",
                    "is_self": None,
                },
                "comments": [],
                "more_count": 0,
            }
        }
        out3 = render_detail(env3)
        self.assertNotIn("LINK", out3)

        # 4. is_self explicitly True -> no LINK even if url is non-empty
        env4 = {
            "data": {
                "post": {
                    "id": "p1",
                    "title": "t",
                    "url": "https://example.com/art",
                    "permalink": "/r/news/comments/p1/t/",
                    "is_self": True,
                },
                "comments": [],
                "more_count": 0,
            }
        }
        out4 = render_detail(env4)
        self.assertNotIn("LINK", out4)

    def test_raw_more_count_and_fallback(self):
        data_count = [
            {"data": {"children": [{"data": {"id": "p1"}}]}},
            {
                "data": {
                    "children": [
                        {"kind": "more", "data": {"count": 15, "children": []}}
                    ]
                }
            },
        ]
        _, _, more = parse_detail(data_count)
        self.assertEqual(more, 15)

        data_children = [
            {"data": {"children": [{"data": {"id": "p1"}}]}},
            {
                "data": {
                    "children": [{"kind": "more", "data": {"children": ["c1", "c2"]}}]
                }
            },
        ]
        _, _, more = parse_detail(data_children)
        self.assertEqual(more, 2)

        data_empty = [
            {"data": {"children": [{"data": {"id": "p1"}}]}},
            {"data": {"children": [{"kind": "more", "data": {}}]}},
        ]
        _, _, more = parse_detail(data_empty)
        self.assertEqual(more, 1)

    def test_more_count_safe_integer_conversion(self):
        data = {
            "post": {"id": "p1"},
            "comments": [
                {
                    "author": "u1",
                    "body": "b1",
                    "more_count": "invalid",
                    "replies": [
                        {
                            "author": "u2",
                            "body": "b2",
                            "more_count": "nope",
                            "replies": [],
                        },
                        {"author": "[more]", "more_count": "bad", "more_children": []},
                    ],
                },
                {"author": "[more]", "more_count": "bad", "more_children": ["c1"]},
            ],
            "more_count": "invalid",
        }
        _, comments, more = parse_detail(data)
        self.assertEqual(len(comments), 2)
        self.assertIsInstance(more, int)

    def test_render_detail_url_normalization_with_query_params(self):
        env = {
            "data": {
                "post": {
                    "id": "p1",
                    "title": "t",
                    "url": "https://www.reddit.com/r/news/comments/p1/t/?sort=top&utm_source=share",
                    "permalink": "/r/news/comments/p1/t/",
                    "is_self": None,
                },
                "comments": [],
                "more_count": 0,
            }
        }
        out = render_detail(env)
        self.assertNotIn("LINK", out)

        env_ext = {
            "data": {
                "post": {
                    "id": "p1",
                    "title": "t",
                    "url": "https://example.com/art?foo=bar#section",
                    "permalink": "/r/news/comments/p1/t/",
                    "is_self": None,
                },
                "comments": [],
                "more_count": 0,
            }
        }
        out_ext = render_detail(env_ext)
        self.assertIn("LINK https://example.com/art?foo=bar#section", out_ext)

    def test_null_author_and_subreddit_safe_fallback(self):
        cells = _comment_cells(1, {"author": None, "subreddit": None})
        self.assertEqual(cells["author"], "u/?")
        self.assertEqual(cells["sub"], "r/?")

        raw = _raw_comment_of({"author": None})
        self.assertEqual(raw["author"], "?")

        user_out = render_user({"data": {"name": None}})
        self.assertTrue(user_out.startswith("u/?"))

    def test_consistent_limit_and_count_flags(self):
        self.assertEqual(LIMIT_FLAGS, {"-n", "--limit", "--count"})

        v_count = _compact_list_view("sub", ["--count", "50"])
        self.assertEqual(v_count.tokens, ["--count", "10"])

        v_limit = _compact_list_view("search", ["--limit", "50"])
        self.assertEqual(v_limit.tokens, ["--limit", "10"])


class RunBackendOSErrorTest(unittest.TestCase):
    """Non-ENOENT OS errors must surface as clean backend errors."""

    @mock.patch.object(_mod.subprocess, "run")
    def test_permission_denied_becomes_backend_error(self, mock_run):
        mock_run.side_effect = OSError(13, "Permission denied")
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(
            io.StringIO()
        ) as err:
            _mod.run_backend(["feed"])
        self.assertEqual(ctx.exception.code, EX_BACKEND)
        self.assertIn("ERR backend", err.getvalue())


class ExportTmpSafetyTest(unittest.TestCase):
    """A planted `{outfile}.tmp` (file or link) must not hijack the export."""

    def _run_export(self, out):
        proc = mock.Mock()
        proc.returncode = 0
        with mock.patch.object(_mod, "run_backend", return_value=proc):
            return _mod.cmd_export_compact(["-o", out])

    def _write_valid_csv(self, out):
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write("score,num_comments,subreddit,title,author,url\n" "1,2,s,t,a,u\n")

    def test_preplanted_tmp_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ex.csv")
            with open(out + ".tmp", "w", encoding="utf-8") as f:
                f.write("stale")
            self._write_valid_csv(out)
            rc = self._run_export(out)
            self.assertEqual(rc, EX_OK)
            with open(out + ".tmp", encoding="utf-8") as f:
                self.assertEqual(f.read(), "stale")
            with open(out, encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(
                content.startswith("score | sub | title | author | url\n"), content
            )
            self.assertIn("u/a", content)

    def test_symlink_tmp_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ex.csv")
            victim = os.path.join(tmp, "victim.txt")
            with open(victim, "w", encoding="utf-8") as f:
                f.write("untouched")
            os.symlink(victim, out + ".tmp")
            self._write_valid_csv(out)
            rc = self._run_export(out)
            self.assertEqual(rc, EX_OK)
            self.assertTrue(os.path.islink(out + ".tmp"))
            with open(victim, encoding="utf-8") as f:
                self.assertEqual(f.read(), "untouched")


class ExportMalformedCsvTest(unittest.TestCase):
    """Oversized backend CSV cells must be a controlled error, not a traceback."""

    @mock.patch.object(_mod, "run_backend")
    def test_oversized_cell_is_controlled_error(self, mock_run):
        mock_run.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "big.csv")
            with open(out, "w", encoding="utf-8", newline="") as f:
                f.write("score,num_comments,subreddit,title,author,url\n")
                f.write("1,2,s," + "t" * 200000 + ",a,u\n")
            with contextlib.redirect_stdout(io.StringIO()) as cap:
                rc = _mod.cmd_export_compact(["-o", out])
            self.assertEqual(rc, EX_BACKEND)
            self.assertIn("ERR io", cap.getvalue())


class PipeEscapeTest(unittest.TestCase):
    """A literal '|' in cell text must escape as '\\|' (single-line tables)."""

    def test_safe_cell_escapes_pipe(self):
        self.assertEqual(_mod._safe_cell("a|b"), r"a\|b")
        self.assertEqual(_mod._safe_cell("a | b"), r"a \| b")

    def test_post_title_pipe_escaped(self):
        d = {
            "id": "x1",
            "title": "a|b",
            "subreddit": "s",
            "author": "u1",
            "score": 1,
            "num_comments": 2,
        }
        line = _mod.post_line(1, d, True)
        self.assertIn(r"a\|b", line)
        self.assertEqual(line.count(" | "), 5)

    def test_comment_body_pipe_escaped(self):
        line = _mod.comment_line(
            1,
            {"id": "k1", "author": "u1", "score": 1, "subreddit": "s", "body": "x|y"},
        )
        self.assertIn(r"x\|y", line)

    def test_export_title_pipe_escaped(self):
        line = _mod._export_line(
            {"score": 1, "num_comments": 2, "subreddit": "s", "title": "p|q", "author": "a", "url": "u"}
        )
        self.assertIn(r"p\|q", line)


class StatusRenderTest(unittest.TestCase):
    """Compact status stays one line and never leaks local paths."""

    def test_authenticated_shape(self):
        env = {
            "ok": True,
            "data": {
                "authenticated": True,
                "username": "spez",
                "capabilities": ["read", "write"],
                "modhash_present": True,
                "credential_file": "/home/user/.config/rdt-cli/credential.json",
                "cookie_count": 10,
            },
        }
        out = render_status(env)
        self.assertEqual(out, "auth:yes u/spez caps:read,write modhash:1")
        self.assertNotIn("credential", out)
        self.assertNotIn("/home/", out)
        self.assertNotIn("cookie", out)
        self.assertEqual(len(out.splitlines()), 1)

    def test_anonymous_shape(self):
        out = render_status({"ok": True, "data": {"authenticated": False}})
        self.assertEqual(out, "auth:no")

    def test_anonymous_error_suffix(self):
        out = render_status(
            {"ok": True, "data": {"authenticated": False, "error": "expired"}}
        )
        self.assertEqual(out, "auth:no expired")

    def test_missing_username_and_caps(self):
        out = render_status({"ok": True, "data": {"authenticated": True}})
        self.assertEqual(out, "auth:yes u/? caps:- modhash:0")


class BackendTimeoutTest(unittest.TestCase):
    """RDT_TIDY_TIMEOUT overrides the default 30 s within 1..300."""

    def test_default_is_30(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_mod.BACKEND_TIMEOUT_ENV, None)
            self.assertEqual(_mod.backend_timeout(), 30)

    def test_custom_value(self):
        with mock.patch.dict(os.environ, {_mod.BACKEND_TIMEOUT_ENV: "5"}):
            self.assertEqual(_mod.backend_timeout(), 5)

    def test_invalid_falls_back(self):
        for bad in ("nonsense", "0", "-3", "9999", ""):
            with mock.patch.dict(os.environ, {_mod.BACKEND_TIMEOUT_ENV: bad}):
                self.assertEqual(_mod.backend_timeout(), 30, bad)

    @mock.patch.object(_mod.subprocess, "run")
    def test_run_backend_uses_configured_timeout(self, mock_run):
        mock_run.return_value = mock.Mock(stdout="{}", stderr="", returncode=0)
        with mock.patch.dict(os.environ, {_mod.BACKEND_TIMEOUT_ENV: "7"}):
            _mod.run_backend(["status"])
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 7)

    @mock.patch.object(_mod.subprocess, "run")
    def test_timeout_message_reports_configured_seconds(self, mock_run):
        mock_run.side_effect = _mod.subprocess.TimeoutExpired(cmd="rdt", timeout=9)
        with mock.patch.dict(os.environ, {_mod.BACKEND_TIMEOUT_ENV: "9"}):
            with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(
                io.StringIO()
            ) as err:
                _mod.run_backend(["status"])
        self.assertEqual(ctx.exception.code, _mod.EX_BACKEND)
        self.assertIn("within 9s", err.getvalue())


class EnvelopeSizeGuardTest(unittest.TestCase):
    """Oversized backend payloads fail closed instead of exhausting memory."""

    def test_normal_payload_parses(self):
        proc = mock.Mock(stdout='{"ok": true}', stderr="", returncode=0)
        self.assertEqual(_mod.load_envelope(proc), {"ok": True})

    def test_oversized_payload_is_controlled_error(self):
        big = "x" * (_mod.MAX_BACKEND_BYTES + 1)
        proc = mock.Mock(stdout=big, stderr="", returncode=0)
        with contextlib.redirect_stdout(io.StringIO()) as cap:
            with self.assertRaises(SystemExit) as ctx:
                _mod.load_envelope(proc)
        self.assertEqual(ctx.exception.code, _mod.EX_BACKEND)
        self.assertIn("response too large", cap.getvalue())


class CapsHelperTest(unittest.TestCase):
    """Shared caps/modhash formatting stays identical for whoami/status."""

    def test_caps_str(self):
        self.assertEqual(_mod._caps_str(["read", "write"]), "read,write")
        self.assertEqual(_mod._caps_str(("a", "", None)), "a")
        self.assertEqual(_mod._caps_str([]), "-")
        self.assertEqual(_mod._caps_str(None), "-")
        self.assertEqual(_mod._caps_str("read"), "read")

    def test_mod_flag(self):
        self.assertEqual(_mod._mod_flag(True), 1)
        self.assertEqual(_mod._mod_flag(False), 0)
        self.assertEqual(_mod._mod_flag(None), 0)

    def test_whoami_uses_helper(self):
        env = {
            "ok": True,
            "data": {
                "name": "spez",
                "link_karma": 1,
                "comment_karma": 2,
                "created_utc": 1126550000,
                "_session": {"capabilities": [], "modhash_present": False},
            },
        }
        self.assertTrue(_mod.render_whoami(env).endswith("sess - modhash:0"))


class WhitespacePolicyTest(unittest.TestCase):
    """squish vs _safe_cell vs flow each keep their documented contract."""

    def test_matrix(self):
        self.assertEqual(_mod.squish("a  b\n c"), "a b c")
        self.assertEqual(_mod._safe_cell("a|b"), r"a\|b")
        self.assertEqual(_mod.flow("a  b\n\n c"), "a b\n\nc")
        self.assertEqual(_mod.flow(""), "")
        self.assertEqual(_mod.flow("   "), "")


class ExportSchemaTest(unittest.TestCase):
    """Lenient CSV parsing: missing columns default, extras are ignored."""

    def test_missing_columns_default(self):
        line = _mod._export_line({})
        self.assertIn("u/?", line)
        self.assertTrue(line.startswith("+0c0 | r/? |  | u/? | "))

    def test_extra_columns_ignored(self):
        line = _mod._export_line(
            {
                "score": 3,
                "num_comments": 4,
                "subreddit": "s",
                "title": "t",
                "author": "a",
                "url": "u",
                "flair": "X",
                "awards": [1, 2],
            }
        )
        self.assertNotIn("X", line.split(" | "))
        self.assertIn("u/a", line)


class FindRdtCacheTest(unittest.TestCase):
    """Process cache works and cache_clear() re-resolves after PATH changes."""

    def setUp(self):
        _mod.find_rdt.cache_clear()
        self.addCleanup(_mod.find_rdt.cache_clear)

    def test_second_call_is_cached(self):
        with mock.patch.object(_mod.shutil, "which", return_value="/x/rdt") as m:
            self.assertEqual(_mod.find_rdt(), "/x/rdt")
            self.assertEqual(_mod.find_rdt(), "/x/rdt")
            self.assertEqual(m.call_count, 1)

    def test_clear_resolves_again(self):
        with mock.patch.object(_mod.shutil, "which", return_value="/a/rdt"):
            self.assertEqual(_mod.find_rdt(), "/a/rdt")
        _mod.find_rdt.cache_clear()
        with mock.patch.object(_mod.shutil, "which", return_value="/b/rdt"):
            self.assertEqual(_mod.find_rdt(), "/b/rdt")


class ExportModeTest(unittest.TestCase):
    """Rewritten export files carry 0600 permissions."""

    @mock.patch.object(_mod, "run_backend")
    def test_output_is_owner_only(self, mock_run):
        mock_run.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "mode.csv")
            with open(out, "w", encoding="utf-8", newline="") as f:
                f.write("score,num_comments,subreddit,title,author,url\n1,2,s,t,a,u\n")
            rc = _mod.cmd_export_compact(["-o", out])
            self.assertEqual(rc, _mod.EX_OK)
            self.assertEqual(0o777 & os.stat(out).st_mode, 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=1)
