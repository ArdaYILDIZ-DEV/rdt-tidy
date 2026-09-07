#!/usr/bin/env python3
"""Unit tests for TokenView edge cases (no e2e shim)."""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader("rdt_tidy", os.path.join(ROOT, "rdt-tidy"))
_spec = importlib.util.spec_from_loader("rdt_tidy", _loader)
_mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(_mod)

TokenView = _mod.TokenView
backend_args = _mod.backend_args
TIDY_FLAGS = _mod.TIDY_FLAGS
check_error = _mod.check_error
_looks_like_flag = _mod._looks_like_flag
EX_BACKEND = _mod.EX_BACKEND
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
        self.assertEqual(TokenView(["export", "x", "-o", "f.txt"]).value({"-o", "--output"}), "f.txt")
        self.assertEqual(TokenView(["export", "x", "--output=f.txt"]).value({"-o", "--output"}), "f.txt")
        self.assertIsNone(TokenView(["export", "x"]).value({"-o", "--output"}))

    def test_value_packed_short(self):
        self.assertEqual(TokenView(["search", "x", "-n50"]).value({"-n", "--limit"}), "50")

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
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
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
            {"data": {"children": [
                {"kind": "t1", "data": {"author": "a", "body": "b", "score": 1, "replies": {}}},
            ]}},
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

    def test_empty_inputs(self):
        self.assertEqual(parse_detail({}), ({}, [], 0))
        self.assertEqual(parse_detail([]), ({}, [], 0))
        self.assertEqual(parse_detail(None), ({}, [], 0))


class RenderDetailTest(unittest.TestCase):
    """Multi-line bodies keep line breaks at any depth."""

    def test_multiline_top_level_comment(self):
        # Top-level append(text) must equal extend(splitlines) once joined:
        # no newline may be lost or merged into one line.
        env = {"data": {
            "post": {"id": "x", "subreddit": "s", "title": "t",
                       "author": "a", "score": 1, "num_comments": 1},
            "comments": [{"author": "u1", "body": "line1\nline2\n\nline3",
                            "score": 1, "depth": 0}],
            "more_count": 0,
        }}
        out = render_detail(env)
        self.assertIn("u/u1 +1: line1", out)
        self.assertIn("\nline2\n\nline3", out)
        self.assertEqual(out.splitlines()[2], "u/u1 +1: line1")

    def test_multiline_reply_stays_indented(self):
        # Dict-shape replies come from the nested "replies" list
        # (parse_detail forces top-level nodes to depth 0).
        env = {"data": {
            "post": {"id": "x", "subreddit": "s", "title": "t",
                       "author": "a", "score": 1, "num_comments": 2},
            "comments": [{"author": "u0", "body": "top", "score": 1,
                            "replies": [{"author": "u1", "body": "a1\na2",
                                         "score": 1}]}],
            "more_count": 0,
        }}
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
        env = {"ok": True, "data": {"data": {"children": [
            {"kind": "t3", "data": None},
            {"kind": "t3", "data": {"id": "a1", "title": "t"}},
        ], "after": None}}}
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
        self.assertEqual(TokenView(["cmd", "-rSub"]).value({"-r", "--subreddit"}), "Sub")
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
            args=["rdt", "search"], returncode=1,
            stdout="not-json\n", stderr="boom-stderr\n")
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            with self.assertRaises(SystemExit) as ctx:
                load_envelope(proc)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(out_buf.getvalue(), "not-json\n")
        self.assertEqual(err_buf.getvalue(), "boom-stderr\n")


if __name__ == "__main__":
    unittest.main(verbosity=1)
