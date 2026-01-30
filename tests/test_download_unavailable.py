"""Tests for unavailable video recording in download functions.

Verifies that the download() function properly records unavailable videos
and checks the cooldown before attempting downloads.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from yt_dlp.utils import DownloadError

from kikusan.download import UnavailableCooldownError, download, _extract_video_id_from_url
from kikusan.unavailable import load_unavailable, record_unavailable, save_unavailable


class TestDownloadRecordsUnavailable:
    """Tests that download() records unavailable videos to unavailable.json."""

    @patch("kikusan.download.extract_info_with_retry")
    @patch("kikusan.download.get_config")
    def test_records_unavailable_on_info_extraction_failure(self, mock_config, mock_extract, tmp_path):
        """When extract_info_with_retry fails with 'Video unavailable' during
        info extraction, the video ID should be recorded in unavailable.json."""
        mock_config.return_value = MagicMock(
            unavailable_cooldown_hours=168,
            cookie_file_path=None,
        )
        mock_extract.side_effect = DownloadError(
            "ERROR: [youtube] djiKWmUtCFU: Video unavailable. This video is not available"
        )

        with pytest.raises(DownloadError):
            download(
                video_id="djiKWmUtCFU",
                output_dir=tmp_path,
                audio_format="opus",
            )

        # Verify the video was recorded in unavailable.json
        data = load_unavailable(tmp_path)
        assert "djiKWmUtCFU" in data
        assert "Video unavailable" in data["djiKWmUtCFU"]["error"]
        assert data["djiKWmUtCFU"]["failed_at"] is not None

    @patch("kikusan.download.extract_info_with_retry")
    @patch("kikusan.download.get_config")
    def test_records_unavailable_on_download_failure(self, mock_config, mock_extract, tmp_path):
        """When extract_info_with_retry succeeds for info but fails during download
        with 'Video unavailable', the video should be recorded."""
        mock_config.return_value = MagicMock(
            unavailable_cooldown_hours=168,
            cookie_file_path=None,
        )

        # First call (info extraction) succeeds, second call (download) fails
        mock_extract.side_effect = [
            {"title": "Test Song", "artist": "Test Artist", "duration": 180, "id": "abc123"},
            DownloadError("ERROR: [youtube] abc123: Video unavailable"),
        ]

        with pytest.raises(DownloadError):
            download(
                video_id="abc123",
                output_dir=tmp_path,
                audio_format="opus",
            )

        data = load_unavailable(tmp_path)
        assert "abc123" in data
        assert data["abc123"]["title"] == "Test Song"
        assert data["abc123"]["artist"] == "Test Artist"

    @patch("kikusan.download.extract_info_with_retry")
    @patch("kikusan.download.get_config")
    def test_does_not_record_non_unavailable_errors(self, mock_config, mock_extract, tmp_path):
        """Network errors or other non-unavailable errors should NOT be recorded."""
        mock_config.return_value = MagicMock(
            unavailable_cooldown_hours=168,
            cookie_file_path=None,
        )
        mock_extract.side_effect = DownloadError("Network timeout while downloading")

        with pytest.raises(DownloadError):
            download(
                video_id="xyz789",
                output_dir=tmp_path,
                audio_format="opus",
            )

        # Should NOT be recorded
        data = load_unavailable(tmp_path)
        assert "xyz789" not in data


class TestDownloadChecksCooldown:
    """Tests that download() checks unavailable cooldown before hitting YouTube."""

    @patch("kikusan.download.get_config")
    def test_raises_cooldown_error_when_on_cooldown(self, mock_config, tmp_path):
        """If a video is on cooldown, download() should raise UnavailableCooldownError
        without making any network requests."""
        mock_config.return_value = MagicMock(
            unavailable_cooldown_hours=168,
            cookie_file_path=None,
        )

        # Pre-record the video as unavailable
        record_unavailable(tmp_path, "djiKWmUtCFU", "Video unavailable")

        with pytest.raises(UnavailableCooldownError) as exc_info:
            download(
                video_id="djiKWmUtCFU",
                output_dir=tmp_path,
                audio_format="opus",
            )

        assert "cooldown" in str(exc_info.value).lower()
        assert "djiKWmUtCFU" in str(exc_info.value)

    @patch("kikusan.download.extract_info_with_retry")
    @patch("kikusan.download.get_config")
    def test_no_cooldown_when_disabled(self, mock_config, mock_extract, tmp_path):
        """When cooldown_hours is 0, the cooldown should be disabled."""
        mock_config.return_value = MagicMock(
            unavailable_cooldown_hours=0,
            cookie_file_path=None,
        )

        # Pre-record the video as unavailable
        record_unavailable(tmp_path, "djiKWmUtCFU", "Video unavailable")

        # Should NOT raise UnavailableCooldownError; proceeds to extract info
        mock_extract.side_effect = DownloadError("Video unavailable")

        with pytest.raises(DownloadError):
            download(
                video_id="djiKWmUtCFU",
                output_dir=tmp_path,
                audio_format="opus",
            )

    @patch("kikusan.download.extract_info_with_retry")
    @patch("kikusan.download.get_config")
    def test_no_cooldown_when_not_recorded(self, mock_config, mock_extract, tmp_path):
        """A video that hasn't been recorded should proceed normally."""
        mock_config.return_value = MagicMock(
            unavailable_cooldown_hours=168,
            cookie_file_path=None,
        )

        # Should proceed to extract info (no cooldown record exists)
        mock_extract.return_value = {
            "title": "Good Song",
            "artist": "Good Artist",
            "duration": 200,
            "id": "goodvid",
        }

        # Will fail at _find_downloaded_file but that's fine - we just need
        # to verify it didn't raise UnavailableCooldownError
        result = download(
            video_id="goodvid",
            output_dir=tmp_path,
            audio_format="opus",
            fetch_lyrics=False,
        )
        # It should have called extract_info_with_retry (at least for info extraction)
        assert mock_extract.call_count >= 1


class TestExtractVideoIdFromUrl:
    """Tests for _extract_video_id_from_url helper."""

    def test_extracts_from_youtube_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert _extract_video_id_from_url(url) == "dQw4w9WgXcQ"

    def test_extracts_from_youtube_music_url(self):
        url = "https://music.youtube.com/watch?v=djiKWmUtCFU"
        assert _extract_video_id_from_url(url) == "djiKWmUtCFU"

    def test_extracts_with_additional_params(self):
        url = "https://music.youtube.com/watch?v=abc12345678&list=PLxyz"
        assert _extract_video_id_from_url(url) == "abc12345678"

    def test_returns_none_for_playlist_url(self):
        url = "https://music.youtube.com/playlist?list=PLxyz"
        assert _extract_video_id_from_url(url) is None

    def test_returns_none_for_non_youtube_url(self):
        url = "https://example.com/page"
        assert _extract_video_id_from_url(url) is None

    def test_handles_hyphen_and_underscore_in_id(self):
        url = "https://www.youtube.com/watch?v=a-b_c1234_5"
        assert _extract_video_id_from_url(url) == "a-b_c1234_5"


class TestUnavailableCooldownError:
    """Tests for the UnavailableCooldownError exception class."""

    def test_is_exception(self):
        err = UnavailableCooldownError("test message")
        assert isinstance(err, Exception)

    def test_message_preserved(self):
        msg = "Video xyz is on cooldown"
        err = UnavailableCooldownError(msg)
        assert str(err) == msg
