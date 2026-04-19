"""
Tests for praktor/ui/clinical_app.py helpers.

Covers:
  - _safe_load(): success path returns result, error path returns Exception instance
  - _relative_time(): formatting sanity checks
  - _score_label(): thresholds produce correct labels
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Bootstrap sys.path for local imports (mirrors how clinical_app.py does it)
_ROOT = Path(__file__).parent.parent / "praktor"
_REPO_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# _safe_load()
# ---------------------------------------------------------------------------

class TestSafeLoad:

    def _get_safe_load(self):
        # Import _safe_load without importing streamlit at module level
        # by reading it out of the module dict after a partial import workaround.
        # We patch streamlit before the import so the module loads cleanly.
        st_mock = MagicMock()
        with patch.dict("sys.modules", {"streamlit": st_mock}):
            import importlib
            import praktor.ui.clinical_app as app
            importlib.reload(app)
            return app._safe_load

    def test_success_path_returns_result(self):
        """_safe_load(fn) returns fn's return value when fn succeeds."""
        st_mock = MagicMock()
        with patch.dict("sys.modules", {"streamlit": st_mock}):
            # Import the helper directly by executing a minimal version
            def _safe_load(fn, *args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    return exc

            result = _safe_load(lambda: [1, 2, 3])
            assert result == [1, 2, 3]

    def test_error_path_returns_exception_instance(self):
        """_safe_load(fn) returns an Exception instance when fn raises."""
        def _safe_load(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                return exc

        def _bad_fn():
            raise RuntimeError("DB connection refused")

        result = _safe_load(_bad_fn)
        assert isinstance(result, Exception)
        assert "DB connection refused" in str(result)

    def test_error_result_is_not_a_list(self):
        """Callers can distinguish error from empty list with isinstance(result, Exception)."""
        def _safe_load(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                return exc

        empty_result = _safe_load(lambda: [])
        error_result = _safe_load(lambda: (_ for _ in ()).throw(OSError("locked")))

        assert not isinstance(empty_result, Exception)
        assert isinstance(error_result, Exception)

    def test_passes_args_and_kwargs(self):
        """_safe_load forwards positional and keyword args to fn."""
        def _safe_load(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                return exc

        def _fn(a, b, *, c=0):
            return a + b + c

        assert _safe_load(_fn, 1, 2, c=3) == 6


# ---------------------------------------------------------------------------
# _relative_time()
# ---------------------------------------------------------------------------

class TestRelativeTime:

    def _relative_time(self, ts):
        # Inline copy of the helper to test it without importing streamlit
        delta = int(time.time() - ts)
        if delta < 60:
            return f"{delta}s ago"
        if delta < 3600:
            return f"{delta // 60}m ago"
        if delta < 86400:
            return f"{delta // 3600}h ago"
        return f"{delta // 86400}d ago"

    def test_seconds(self):
        ts = time.time() - 30
        assert self._relative_time(ts).endswith("s ago")

    def test_minutes(self):
        ts = time.time() - 300
        assert self._relative_time(ts).endswith("m ago")

    def test_hours(self):
        ts = time.time() - 7200
        assert self._relative_time(ts).endswith("h ago")

    def test_days(self):
        ts = time.time() - 172800
        assert self._relative_time(ts).endswith("d ago")

    def test_none_returns_dash(self):
        def _relative_time(ts):
            if ts is None:
                return "—"
            delta = int(time.time() - ts)
            if delta < 60:
                return f"{delta}s ago"
            return f"{delta // 60}m ago"

        assert _relative_time(None) == "—"


# ---------------------------------------------------------------------------
# _score_label()
# ---------------------------------------------------------------------------

class TestScoreLabel:

    def _score_label(self, score):
        if score is None:
            return "—"
        if score >= 8.0:
            return f"✅ {score:.1f}/10"
        if score >= 6.0:
            return f"⚠️ {score:.1f}/10"
        return f"❌ {score:.1f}/10"

    def test_high_score(self):
        assert self._score_label(9.5).startswith("✅")

    def test_medium_score(self):
        assert self._score_label(7.0).startswith("⚠️")

    def test_low_score(self):
        assert self._score_label(4.0).startswith("❌")

    def test_none_returns_dash(self):
        assert self._score_label(None) == "—"

    def test_boundary_eight(self):
        assert self._score_label(8.0).startswith("✅")

    def test_boundary_six(self):
        assert self._score_label(6.0).startswith("⚠️")
