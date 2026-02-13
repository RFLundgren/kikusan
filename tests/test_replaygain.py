"""Tests for ReplayGain/R128 loudness normalization tagging."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kikusan.replaygain import apply_replaygain, is_rsgain_available


class TestIsRsgainAvailable:
    """Tests for rsgain availability check."""

    def setup_method(self):
        """Clear the lru_cache before each test."""
        is_rsgain_available.cache_clear()

    def test_available_when_found(self):
        with patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"):
            assert is_rsgain_available() is True

    def test_unavailable_when_not_found(self):
        with patch("kikusan.replaygain.shutil.which", return_value=None):
            assert is_rsgain_available() is False

    def test_result_is_cached(self):
        with patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain") as mock_which:
            assert is_rsgain_available() is True
            assert is_rsgain_available() is True
            # shutil.which should only be called once due to caching
            mock_which.assert_called_once()


class TestApplyReplaygain:
    """Tests for applying ReplayGain tags."""

    def setup_method(self):
        """Clear the lru_cache before each test."""
        is_rsgain_available.cache_clear()

    def test_skips_when_rsgain_unavailable(self, tmp_path):
        audio_file = tmp_path / "test.opus"
        audio_file.touch()

        with patch("kikusan.replaygain.shutil.which", return_value=None):
            result = apply_replaygain(audio_file, "opus")

        assert result is False

    def test_skips_when_file_missing(self, tmp_path):
        audio_file = tmp_path / "nonexistent.opus"

        with patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"):
            result = apply_replaygain(audio_file, "opus")

        assert result is False

    def test_opus_uses_r128_tags(self, tmp_path):
        audio_file = tmp_path / "test.opus"
        audio_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"),
            patch("kikusan.replaygain.subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = apply_replaygain(audio_file, "opus")

        assert result is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["rsgain", "custom", "-q", "-s", "i", "-o", "r", str(audio_file)]

    def test_mp3_no_r128_flag(self, tmp_path):
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"),
            patch("kikusan.replaygain.subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = apply_replaygain(audio_file, "mp3")

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd == ["rsgain", "custom", "-q", "-s", "i", str(audio_file)]
        assert "-o" not in cmd

    def test_flac_no_r128_flag(self, tmp_path):
        audio_file = tmp_path / "test.flac"
        audio_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"),
            patch("kikusan.replaygain.subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = apply_replaygain(audio_file, "flac")

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "-o" not in cmd

    def test_failure_nonzero_exit_code(self, tmp_path):
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"

        with (
            patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"),
            patch("kikusan.replaygain.subprocess.run", return_value=mock_result),
        ):
            result = apply_replaygain(audio_file, "mp3")

        assert result is False

    def test_failure_timeout(self, tmp_path):
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with (
            patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"),
            patch(
                "kikusan.replaygain.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="rsgain", timeout=300),
            ),
        ):
            result = apply_replaygain(audio_file, "mp3")

        assert result is False

    def test_failure_binary_disappeared(self, tmp_path):
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with (
            patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"),
            patch(
                "kikusan.replaygain.subprocess.run",
                side_effect=FileNotFoundError("rsgain not found"),
            ),
        ):
            result = apply_replaygain(audio_file, "mp3")

        assert result is False

    def test_timeout_value(self, tmp_path):
        audio_file = tmp_path / "test.opus"
        audio_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("kikusan.replaygain.shutil.which", return_value="/usr/bin/rsgain"),
            patch("kikusan.replaygain.subprocess.run", return_value=mock_result) as mock_run,
        ):
            apply_replaygain(audio_file, "opus")

        assert mock_run.call_args[1]["timeout"] == 300
