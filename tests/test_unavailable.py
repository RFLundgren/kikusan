"""Tests for the unavailable video cooldown system."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kikusan.unavailable import (
    DEFAULT_COOLDOWN_HOURS,
    clear_expired,
    get_cooldown_remaining,
    get_unavailable_file,
    is_on_cooldown,
    is_unavailable_error,
    load_unavailable,
    record_unavailable,
    save_unavailable,
)


class TestIsUnavailableError:
    """Tests for detecting unavailable video errors."""

    def test_detects_video_unavailable(self):
        msg = "ERROR: [youtube] 4kvgkNHs3jM: Video unavailable. This video is not available"
        assert is_unavailable_error(msg) is True

    def test_detects_video_not_available(self):
        msg = "This video is not available in your country"
        assert is_unavailable_error(msg) is True

    def test_detects_video_removed(self):
        msg = "This video has been removed by the uploader"
        assert is_unavailable_error(msg) is True

    def test_detects_video_no_longer_available(self):
        msg = "This video is no longer available because the YouTube account was terminated"
        assert is_unavailable_error(msg) is True

    def test_detects_video_does_not_exist(self):
        msg = "This video does not exist"
        assert is_unavailable_error(msg) is True

    def test_detects_uploader_not_made_available(self):
        msg = "The uploader has not made this video available in your country"
        assert is_unavailable_error(msg) is True

    def test_case_insensitive(self):
        msg = "VIDEO UNAVAILABLE"
        assert is_unavailable_error(msg) is True

    def test_ignores_network_errors(self):
        msg = "Network timeout while downloading"
        assert is_unavailable_error(msg) is False

    def test_ignores_auth_errors(self):
        msg = "Sign in to confirm your age"
        assert is_unavailable_error(msg) is False

    def test_ignores_format_errors(self):
        msg = "No suitable format found"
        assert is_unavailable_error(msg) is False

    def test_ignores_generic_errors(self):
        msg = "Download failed: HTTP Error 503"
        assert is_unavailable_error(msg) is False

    def test_empty_string(self):
        assert is_unavailable_error("") is False


class TestGetUnavailableFile:
    """Tests for getting the unavailable file path."""

    def test_returns_correct_path(self, tmp_path):
        result = get_unavailable_file(tmp_path)
        assert result == tmp_path / ".kikusan" / "unavailable.json"

    def test_creates_parent_directory(self, tmp_path):
        get_unavailable_file(tmp_path)
        assert (tmp_path / ".kikusan").exists()


class TestLoadSaveUnavailable:
    """Tests for loading and saving the unavailable registry."""

    def test_load_empty_returns_empty_dict(self, tmp_path):
        result = load_unavailable(tmp_path)
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        data = {
            "abc123": {
                "failed_at": "2025-01-15T10:00:00+00:00",
                "error": "Video unavailable",
                "title": "Test Song",
                "artist": "Test Artist",
            }
        }
        save_unavailable(tmp_path, data)
        loaded = load_unavailable(tmp_path)
        assert loaded == data

    def test_save_atomic_write(self, tmp_path):
        """Verify temp file does not remain after save."""
        data = {"abc123": {"failed_at": "2025-01-15T10:00:00+00:00", "error": "test"}}
        save_unavailable(tmp_path, data)

        tmp_file = get_unavailable_file(tmp_path).with_suffix(".json.tmp")
        assert not tmp_file.exists()

    def test_load_corrupted_file_returns_empty(self, tmp_path):
        """Test that corrupted JSON is handled gracefully."""
        unavailable_file = get_unavailable_file(tmp_path)
        unavailable_file.write_text("not valid json {{{", encoding="utf-8")

        result = load_unavailable(tmp_path)
        assert result == {}
        # Verify backup was created
        backups = list((tmp_path / ".kikusan").glob("unavailable.json.corrupt.*"))
        assert len(backups) == 1

    def test_load_unexpected_format_returns_empty(self, tmp_path):
        """Test that non-dict JSON is handled."""
        unavailable_file = get_unavailable_file(tmp_path)
        unavailable_file.write_text('["not", "a", "dict"]', encoding="utf-8")

        result = load_unavailable(tmp_path)
        assert result == {}

    def test_save_multiple_entries(self, tmp_path):
        data = {
            "vid1": {"failed_at": "2025-01-15T10:00:00+00:00", "error": "err1"},
            "vid2": {"failed_at": "2025-01-16T10:00:00+00:00", "error": "err2"},
            "vid3": {"failed_at": "2025-01-17T10:00:00+00:00", "error": "err3"},
        }
        save_unavailable(tmp_path, data)
        loaded = load_unavailable(tmp_path)
        assert len(loaded) == 3
        assert "vid1" in loaded
        assert "vid2" in loaded
        assert "vid3" in loaded


class TestRecordUnavailable:
    """Tests for recording unavailable videos."""

    def test_records_video(self, tmp_path):
        record_unavailable(tmp_path, "abc123", "Video unavailable", title="Test", artist="Artist")

        data = load_unavailable(tmp_path)
        assert "abc123" in data
        assert data["abc123"]["error"] == "Video unavailable"
        assert data["abc123"]["title"] == "Test"
        assert data["abc123"]["artist"] == "Artist"
        assert "failed_at" in data["abc123"]

    def test_records_without_title_artist(self, tmp_path):
        record_unavailable(tmp_path, "abc123", "Video unavailable")

        data = load_unavailable(tmp_path)
        assert "abc123" in data
        assert data["abc123"]["title"] is None
        assert data["abc123"]["artist"] is None

    def test_overwrites_existing_entry(self, tmp_path):
        record_unavailable(tmp_path, "abc123", "First error")
        record_unavailable(tmp_path, "abc123", "Second error")

        data = load_unavailable(tmp_path)
        assert data["abc123"]["error"] == "Second error"

    def test_preserves_other_entries(self, tmp_path):
        record_unavailable(tmp_path, "vid1", "Error 1")
        record_unavailable(tmp_path, "vid2", "Error 2")

        data = load_unavailable(tmp_path)
        assert "vid1" in data
        assert "vid2" in data

    def test_timestamp_is_utc(self, tmp_path):
        record_unavailable(tmp_path, "abc123", "Video unavailable")

        data = load_unavailable(tmp_path)
        timestamp = datetime.fromisoformat(data["abc123"]["failed_at"])
        assert timestamp.tzinfo is not None


class TestIsOnCooldown:
    """Tests for cooldown checking."""

    def test_not_on_cooldown_when_no_record(self, tmp_path):
        assert is_on_cooldown(tmp_path, "unknown_video") is False

    def test_on_cooldown_when_recently_failed(self, tmp_path):
        # Record a failure just now
        record_unavailable(tmp_path, "abc123", "Video unavailable")
        assert is_on_cooldown(tmp_path, "abc123") is True

    def test_not_on_cooldown_when_expired(self, tmp_path):
        # Create a record from 8 days ago (default cooldown is 7 days)
        data = {
            "abc123": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
                "error": "Video unavailable",
            }
        }
        save_unavailable(tmp_path, data)

        assert is_on_cooldown(tmp_path, "abc123") is False

    def test_still_on_cooldown_within_period(self, tmp_path):
        # Create a record from 3 days ago (within 7-day default cooldown)
        data = {
            "abc123": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                "error": "Video unavailable",
            }
        }
        save_unavailable(tmp_path, data)

        assert is_on_cooldown(tmp_path, "abc123") is True

    def test_custom_cooldown_hours(self, tmp_path):
        # Record a failure 2 hours ago
        data = {
            "abc123": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                "error": "Video unavailable",
            }
        }
        save_unavailable(tmp_path, data)

        # 1-hour cooldown should have expired
        assert is_on_cooldown(tmp_path, "abc123", cooldown_hours=1) is False
        # 3-hour cooldown should still be active
        assert is_on_cooldown(tmp_path, "abc123", cooldown_hours=3) is True

    def test_cooldown_disabled_when_zero(self, tmp_path):
        record_unavailable(tmp_path, "abc123", "Video unavailable")
        assert is_on_cooldown(tmp_path, "abc123", cooldown_hours=0) is False

    def test_handles_naive_timestamps(self, tmp_path):
        """Test that naive timestamps (without timezone) are handled."""
        data = {
            "abc123": {
                "failed_at": datetime.now().isoformat(),  # naive datetime
                "error": "Video unavailable",
            }
        }
        save_unavailable(tmp_path, data)

        # Should not crash - should treat as UTC
        result = is_on_cooldown(tmp_path, "abc123")
        assert isinstance(result, bool)

    def test_handles_invalid_timestamp(self, tmp_path):
        """Test that invalid timestamps are handled gracefully."""
        data = {
            "abc123": {
                "failed_at": "not-a-date",
                "error": "Video unavailable",
            }
        }
        save_unavailable(tmp_path, data)

        assert is_on_cooldown(tmp_path, "abc123") is False

    def test_handles_missing_failed_at(self, tmp_path):
        """Test that missing failed_at is handled."""
        data = {
            "abc123": {
                "error": "Video unavailable",
            }
        }
        save_unavailable(tmp_path, data)

        assert is_on_cooldown(tmp_path, "abc123") is False


class TestGetCooldownRemaining:
    """Tests for getting remaining cooldown time."""

    def test_returns_none_when_no_record(self, tmp_path):
        assert get_cooldown_remaining(tmp_path, "unknown") is None

    def test_returns_none_when_expired(self, tmp_path):
        data = {
            "abc123": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
                "error": "Video unavailable",
            }
        }
        save_unavailable(tmp_path, data)

        assert get_cooldown_remaining(tmp_path, "abc123") is None

    def test_returns_timedelta_when_active(self, tmp_path):
        record_unavailable(tmp_path, "abc123", "Video unavailable")
        remaining = get_cooldown_remaining(tmp_path, "abc123")

        assert remaining is not None
        assert isinstance(remaining, timedelta)
        # Should be close to the full cooldown (just recorded)
        assert remaining.total_seconds() > 0

    def test_returns_none_when_disabled(self, tmp_path):
        record_unavailable(tmp_path, "abc123", "Video unavailable")
        assert get_cooldown_remaining(tmp_path, "abc123", cooldown_hours=0) is None


class TestClearExpired:
    """Tests for clearing expired entries."""

    def test_clears_expired_entries(self, tmp_path):
        data = {
            "expired1": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                "error": "Video unavailable",
            },
            "expired2": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
                "error": "Video unavailable",
            },
            "active": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "error": "Video unavailable",
            },
        }
        save_unavailable(tmp_path, data)

        removed = clear_expired(tmp_path)
        assert removed == 2

        remaining = load_unavailable(tmp_path)
        assert "active" in remaining
        assert "expired1" not in remaining
        assert "expired2" not in remaining

    def test_no_entries_returns_zero(self, tmp_path):
        assert clear_expired(tmp_path) == 0

    def test_all_active_returns_zero(self, tmp_path):
        data = {
            "active1": {
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error": "Video unavailable",
            },
        }
        save_unavailable(tmp_path, data)

        assert clear_expired(tmp_path) == 0

    def test_clears_invalid_timestamps(self, tmp_path):
        data = {
            "invalid": {
                "failed_at": "not-a-date",
                "error": "Video unavailable",
            },
            "missing_timestamp": {
                "error": "Video unavailable",
            },
            "active": {
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error": "Video unavailable",
            },
        }
        save_unavailable(tmp_path, data)

        removed = clear_expired(tmp_path)
        assert removed == 2

        remaining = load_unavailable(tmp_path)
        assert "active" in remaining
        assert len(remaining) == 1

    def test_custom_cooldown(self, tmp_path):
        # Entry from 2 hours ago
        data = {
            "recent": {
                "failed_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                "error": "Video unavailable",
            },
        }
        save_unavailable(tmp_path, data)

        # With 1-hour cooldown, it should be expired
        removed = clear_expired(tmp_path, cooldown_hours=1)
        assert removed == 1

        # With 3-hour cooldown, it should still be active
        save_unavailable(tmp_path, data)
        removed = clear_expired(tmp_path, cooldown_hours=3)
        assert removed == 0
