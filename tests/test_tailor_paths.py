"""Tests for tailor.py path/dirname sanitization."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobpilot.steps.tailor import _safe_dirname  # noqa: E402


def test_safe_dirname_strips_windows_illegal_chars():
    assert _safe_dirname("Marsh & McLennan") == "Marsh & McLennan"
    assert _safe_dirname("X / Twitter") == "X_Twitter"
    assert _safe_dirname("Foo / Bar") == "Foo_Bar"
    assert _safe_dirname("a:b<c>d|e?f*g") == "a_b_c_d_e_f_g"


def test_safe_dirname_strips_backslash():
    assert "\\" not in _safe_dirname("path\\with\\backslashes")


def test_safe_dirname_handles_unicode_emoji():
    out = _safe_dirname("AcmeCo \U0001f4a1")
    assert "/" not in out and "\\" not in out
    assert out


def test_safe_dirname_truncates_to_max_len():
    assert len(_safe_dirname("a" * 200)) <= 80


def test_safe_dirname_empty_returns_underscore():
    assert _safe_dirname("") == "_"
    assert _safe_dirname("   ") == "_"
    assert _safe_dirname("...") == "_"


def test_safe_dirname_strips_trailing_dots_and_spaces():
    assert _safe_dirname("Acme  ").endswith("e")
    assert _safe_dirname("Acme...") == "Acme"
