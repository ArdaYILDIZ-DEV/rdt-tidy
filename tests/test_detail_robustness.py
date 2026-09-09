#!/usr/bin/env python3
"""Regression tests: malformed detail envelopes must not crash the parser.

Covers two reported bugs (branch bugfix/detail-robustness):

  Bug 1 -- `_absorb_raw_child` more-stub branch evaluates
  ``child.get("data")`` twice inside one ternary, which mypy 2.3.1
  rejects (``union-attr``: ``Any | dict | None`` has no ``.get``).
  Runtime behavior for missing/null ``data`` (counted as one hidden
  item) is locked in here so the cleanup cannot change it.

  Bug 2 -- `_parse_raw_detail` calls ``.get("children", [])`` on
  ``(first/second.get("data") or {})``. Any *truthy non-dict* ``data``
  node (list, int, str, ...) raises ``AttributeError`` and kills the
  `read`/`show` path on a malformed backend envelope. These tests are
  red until the fix lands.
"""

import importlib.machinery
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader(
    "rdt_tidy", os.path.join(ROOT, "rdt-tidy")
)
_spec = importlib.util.spec_from_loader("rdt_tidy", _loader)
_mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(_mod)

parse_detail = _mod.parse_detail
render_detail = _mod.render_detail
_absorb_raw_child = _mod._absorb_raw_child


def _post_child():
    return {"data": {"children": [{"data": {"id": "p1", "title": "t"}}]}}


class RawDetailMalformedDataTest(unittest.TestCase):
    """Bug 2: truthy non-dict `data` nodes must parse as empty (red pre-fix)."""

    def test_second_data_truthy_list(self):
        post, comments, more = parse_detail(
            [_post_child(), {"data": ["not", "a", "dict"]}]
        )
        self.assertEqual(post.get("id"), "p1")
        self.assertEqual((comments, more), ([], 0))

    def test_second_data_truthy_int(self):
        post, comments, more = parse_detail([_post_child(), {"data": 5}])
        self.assertEqual(post.get("id"), "p1")
        self.assertEqual((comments, more), ([], 0))

    def test_second_data_truthy_string(self):
        post, comments, more = parse_detail([_post_child(), {"data": "oops"}])
        self.assertEqual(post.get("id"), "p1")
        self.assertEqual((comments, more), ([], 0))

    def test_first_data_truthy_list(self):
        post, comments, more = parse_detail(
            [{"data": ["nope"]}, {"data": {"children": []}}]
        )
        self.assertEqual((post, comments, more), ({}, [], 0))

    def test_first_data_truthy_int(self):
        post, comments, more = parse_detail([{"data": 7}, {"data": {"children": []}}])
        self.assertEqual((post, comments, more), ({}, [], 0))

    def test_render_detail_survives_malformed_raw_envelope(self):
        env = {"ok": True, "data": [_post_child(), {"data": ["nope"]}]}
        self.assertIsInstance(render_detail(env), str)


class RawDetailNullDataTest(unittest.TestCase):
    """Falsy non-dict `data` already degrades gracefully; lock that in."""

    def test_second_data_none(self):
        post, comments, more = parse_detail([_post_child(), {"data": None}])
        self.assertEqual(post.get("id"), "p1")
        self.assertEqual((comments, more), ([], 0))

    def test_first_data_none(self):
        post, comments, more = parse_detail(
            [{"data": None}, {"data": {"children": []}}]
        )
        self.assertEqual((post, comments, more), ({}, [], 0))


class MoreStubDataTest(unittest.TestCase):
    """Bug 1: more-stub counting must stay at one hidden item for
    missing/null `data`, and nested `replies.data = None` must not crash."""

    def test_more_stub_data_none_counts_one(self):
        self.assertEqual(_absorb_raw_child({"kind": "more", "data": None}, []), 1)

    def test_more_stub_data_missing_counts_one(self):
        self.assertEqual(_absorb_raw_child({"kind": "more"}, []), 1)

    def test_more_stub_data_dict_uses_count(self):
        comments: list = []
        more = _absorb_raw_child(
            {"kind": "more", "data": {"count": 4, "children": ["a", "b"]}}, comments
        )
        self.assertEqual(more, 4)
        self.assertEqual(comments, [])

    def test_more_stub_children_non_list_no_crash(self):
        comments: list = []
        more = _absorb_raw_child(
            {"kind": "more", "data": {"count": 0, "children": 5}}, comments
        )
        self.assertEqual(more, 1)
        self.assertEqual(comments, [])

    def test_comment_replies_data_none_no_crash(self):
        comments: list = []
        child = {
            "kind": "t1",
            "data": {"id": "c1", "author": "a", "body": "b", "replies": {"data": None}},
        }
        self.assertEqual(_absorb_raw_child(child, comments), 0)
        self.assertEqual(len(comments), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
