"""Tests for lyrics fetching with ytmusicapi metadata enhancement.

Verifies that get_lyrics_for_video() properly:
1. Fetches clean metadata from ytmusicapi
2. Tries exact match with ytmusicapi metadata first
3. Falls back to search endpoint if exact match fails
4. Falls back to yt-dlp metadata if ytmusicapi fails entirely
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from kikusan.lyrics import (
    _extract_lyrics_from_response,
    _get_lyrics_exact,
    _search_lyrics,
    get_lyrics,
    get_lyrics_for_video,
)
from kikusan.search import SongMetadata


class TestGetLyricsForVideo:
    """Tests for the primary lyrics lookup function with ytmusicapi metadata."""

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_uses_ytmusicapi_metadata_for_exact_match(self, mock_exact, mock_metadata):
        """When ytmusicapi returns metadata, exact match should use it."""
        mock_metadata.return_value = SongMetadata(
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            duration_seconds=354,
        )
        mock_exact.return_value = "[00:00.00] Is this the real life?"

        result = get_lyrics_for_video(
            video_id="fJ9rUzIMcZQ",
            fallback_title="Queen - Bohemian Rhapsody (Official Video)",
            fallback_artist="QueenVEVO",
            fallback_duration=355,
        )

        assert result == "[00:00.00] Is this the real life?"
        # Verify exact match was called with ytmusicapi metadata, not fallback
        mock_exact.assert_called_once_with("Bohemian Rhapsody", "Queen", 354)

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_falls_back_to_search_when_exact_fails(self, mock_exact, mock_search, mock_metadata):
        """When exact match fails, search endpoint should be tried with ytmusicapi metadata."""
        mock_metadata.return_value = SongMetadata(
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            duration_seconds=354,
        )
        mock_exact.return_value = None
        mock_search.return_value = "[00:00.00] Is this the real life?"

        result = get_lyrics_for_video(
            video_id="fJ9rUzIMcZQ",
            fallback_title="Queen - Bohemian Rhapsody (Official Video)",
            fallback_artist="QueenVEVO",
            fallback_duration=355,
        )

        assert result == "[00:00.00] Is this the real life?"
        mock_search.assert_called_once_with(
            "Bohemian Rhapsody", "Queen", "A Night at the Opera", 354
        )

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_falls_back_to_ytdlp_metadata(self, mock_exact, mock_search, mock_metadata):
        """When ytmusicapi exact and search both fail, fall back to yt-dlp metadata."""
        mock_metadata.return_value = SongMetadata(
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            duration_seconds=354,
        )
        # First call (ytmusicapi metadata) returns None, second call (yt-dlp fallback) returns lyrics
        mock_exact.side_effect = [None, "[00:00.00] Is this the real life?"]
        mock_search.return_value = None

        result = get_lyrics_for_video(
            video_id="fJ9rUzIMcZQ",
            fallback_title="Queen - Bohemian Rhapsody (Official Video)",
            fallback_artist="QueenVEVO",
            fallback_duration=355,
        )

        assert result == "[00:00.00] Is this the real life?"
        # Should have been called twice: once with ytmusicapi data, once with fallback
        assert mock_exact.call_count == 2
        mock_exact.assert_called_with(
            "Queen - Bohemian Rhapsody (Official Video)", "QueenVEVO", 355
        )

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_uses_ytdlp_when_ytmusicapi_fails(self, mock_exact, mock_metadata):
        """When ytmusicapi metadata fetch fails, fall back to yt-dlp metadata directly."""
        mock_metadata.return_value = None
        mock_exact.return_value = "[00:00.00] Is this the real life?"

        result = get_lyrics_for_video(
            video_id="fJ9rUzIMcZQ",
            fallback_title="Queen - Bohemian Rhapsody (Official Video)",
            fallback_artist="QueenVEVO",
            fallback_duration=355,
        )

        assert result == "[00:00.00] Is this the real life?"
        # Should be called once with fallback data
        mock_exact.assert_called_once_with(
            "Queen - Bohemian Rhapsody (Official Video)", "QueenVEVO", 355
        )

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_returns_none_when_all_strategies_fail(self, mock_exact, mock_search, mock_metadata):
        """When all lookup strategies fail, return None."""
        mock_metadata.return_value = SongMetadata(
            title="Some Song",
            artist="Some Artist",
            album=None,
            duration_seconds=200,
        )
        mock_exact.return_value = None
        mock_search.return_value = None

        result = get_lyrics_for_video(
            video_id="test123",
            fallback_title="Some Song",
            fallback_artist="Some Artist",
            fallback_duration=200,
        )

        assert result is None


class TestGetLyricsExact:
    """Tests for the exact match lyrics lookup (_get_lyrics_exact)."""

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_synced_lyrics(self, mock_get):
        """Should return synced lyrics when available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "syncedLyrics": "[00:00.00] Hello",
            "plainLyrics": "Hello",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _get_lyrics_exact("Hello", "Adele", 300)
        assert result == "[00:00.00] Hello"

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_plain_lyrics_when_no_synced(self, mock_get):
        """Should return plain lyrics when synced not available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "syncedLyrics": None,
            "plainLyrics": "Hello from the other side",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _get_lyrics_exact("Hello", "Adele", 300)
        assert result == "Hello from the other side"

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_none_on_404(self, mock_get):
        """Should return None when lrclib returns 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = _get_lyrics_exact("Unknown Song", "Unknown Artist", 100)
        assert result is None

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_none_on_http_error(self, mock_get):
        """Should return None on HTTP error."""
        mock_get.side_effect = httpx.HTTPError("Connection timeout")

        result = _get_lyrics_exact("Hello", "Adele", 300)
        assert result is None

    @patch("kikusan.lyrics.httpx.get")
    def test_passes_correct_params(self, mock_get):
        """Should pass correct parameters to lrclib API."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        _get_lyrics_exact("Sparks", "Coldplay", 267)

        mock_get.assert_called_once_with(
            "https://lrclib.net/api/get",
            params={
                "track_name": "Sparks",
                "artist_name": "Coldplay",
                "duration": 267,
            },
            timeout=10.0,
        )


class TestSearchLyrics:
    """Tests for the search endpoint lyrics lookup (_search_lyrics)."""

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_synced_lyrics_from_search(self, mock_get):
        """Should return synced lyrics from search results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "trackName": "Bohemian Rhapsody",
                "artistName": "Queen",
                "duration": 354,
                "syncedLyrics": "[00:00.00] Is this the real life?",
                "plainLyrics": "Is this the real life?",
            }
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _search_lyrics("Bohemian Rhapsody", "Queen", "A Night at the Opera", 354)
        assert result == "[00:00.00] Is this the real life?"

    @patch("kikusan.lyrics.httpx.get")
    def test_filters_by_duration(self, mock_get):
        """Should prefer results matching duration within tolerance."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "trackName": "Bohemian Rhapsody",
                "artistName": "Queen",
                "duration": 100,  # Wrong duration
                "syncedLyrics": "[00:00.00] Wrong version",
                "plainLyrics": "Wrong version",
            },
            {
                "trackName": "Bohemian Rhapsody",
                "artistName": "Queen",
                "duration": 355,  # Within 3s tolerance of 354
                "syncedLyrics": "[00:00.00] Is this the real life?",
                "plainLyrics": "Is this the real life?",
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _search_lyrics("Bohemian Rhapsody", "Queen", None, 354)
        assert result == "[00:00.00] Is this the real life?"

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_plain_when_no_synced(self, mock_get):
        """Should return plain lyrics when no synced available in search results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "trackName": "Test Song",
                "artistName": "Test Artist",
                "duration": 200,
                "syncedLyrics": None,
                "plainLyrics": "Just plain lyrics",
            }
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _search_lyrics("Test Song", "Test Artist", None, 200)
        assert result == "Just plain lyrics"

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_none_on_empty_results(self, mock_get):
        """Should return None when search returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _search_lyrics("Unknown Song", "Unknown Artist", None, 100)
        assert result is None

    @patch("kikusan.lyrics.httpx.get")
    def test_includes_album_in_params_when_provided(self, mock_get):
        """Should include album_name in search params when available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        _search_lyrics("Song", "Artist", "Album Name", 200)

        mock_get.assert_called_once_with(
            "https://lrclib.net/api/search",
            params={
                "track_name": "Song",
                "artist_name": "Artist",
                "album_name": "Album Name",
            },
            timeout=10.0,
        )

    @patch("kikusan.lyrics.httpx.get")
    def test_omits_album_when_none(self, mock_get):
        """Should not include album_name when it is None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        _search_lyrics("Song", "Artist", None, 200)

        mock_get.assert_called_once_with(
            "https://lrclib.net/api/search",
            params={
                "track_name": "Song",
                "artist_name": "Artist",
            },
            timeout=10.0,
        )

    @patch("kikusan.lyrics.httpx.get")
    def test_falls_back_to_all_results_when_no_duration_match(self, mock_get):
        """When no results match duration, should use full result set."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "trackName": "Song",
                "artistName": "Artist",
                "duration": 500,  # Far from target 200
                "syncedLyrics": "[00:00.00] Still some lyrics",
                "plainLyrics": "Still some lyrics",
            }
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _search_lyrics("Song", "Artist", None, 200)
        assert result == "[00:00.00] Still some lyrics"

    @patch("kikusan.lyrics.httpx.get")
    def test_returns_none_on_http_error(self, mock_get):
        """Should return None on HTTP error."""
        mock_get.side_effect = httpx.HTTPError("Connection timeout")

        result = _search_lyrics("Song", "Artist", None, 200)
        assert result is None


class TestGetLyricsBackwardCompat:
    """Tests that the original get_lyrics() function still works."""

    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_delegates_to_exact_match(self, mock_exact):
        """get_lyrics() should delegate to _get_lyrics_exact()."""
        mock_exact.return_value = "[00:00.00] Hello"

        result = get_lyrics("Hello", "Adele", 300)

        assert result == "[00:00.00] Hello"
        mock_exact.assert_called_once_with("Hello", "Adele", 300)


class TestExtractLyricsFromResponse:
    """Tests for _extract_lyrics_from_response helper."""

    def test_prefers_synced_over_plain(self):
        """Should prefer synced lyrics when both are available."""
        data = {"syncedLyrics": "[00:00.00] Synced", "plainLyrics": "Plain"}
        result = _extract_lyrics_from_response(data, "Artist", "Track")
        assert result == "[00:00.00] Synced"

    def test_returns_plain_when_no_synced(self):
        """Should return plain lyrics when synced is missing."""
        data = {"syncedLyrics": None, "plainLyrics": "Plain lyrics here"}
        result = _extract_lyrics_from_response(data, "Artist", "Track")
        assert result == "Plain lyrics here"

    def test_returns_none_when_no_lyrics(self):
        """Should return None when neither synced nor plain lyrics exist."""
        data = {"syncedLyrics": None, "plainLyrics": None}
        result = _extract_lyrics_from_response(data, "Artist", "Track")
        assert result is None

    def test_returns_none_for_empty_strings(self):
        """Should return None when lyrics are empty strings."""
        data = {"syncedLyrics": "", "plainLyrics": ""}
        result = _extract_lyrics_from_response(data, "Artist", "Track")
        assert result is None
