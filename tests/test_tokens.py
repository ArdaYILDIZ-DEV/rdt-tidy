#!/usr/bin/env python3
"""Unit tests for TokenView edge cases (no e2e shim)."""
import importlib.machinery
import importlib.util
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
            ["search", "--", "-c", "--json"],
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
