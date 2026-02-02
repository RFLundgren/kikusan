"""Tests for get_song_metadata() in search module.

Verifies that the function properly extracts clean metadata from
YouTube Music API for lyrics lookup enhancement.
"""

from unittest.mock import MagicMock, patch

from kikusan.search import SongMetadata, get_song_metadata


class TestGetSongMetadata:
    """Tests for get_song_metadata function."""

    @patch("kikusan.search.YTMusic")
    def test_returns_metadata_from_video_details(self, mock_ytmusic_class):
        """Should extract metadata from get_song() videoDetails."""
        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt

        mock_yt.get_song.return_value = {
            "videoDetails": {
                "videoId": "fJ9rUzIMcZQ",
                "title": "Bohemian Rhapsody",
                "author": "Queen",
                "lengthSeconds": "354",
            }
        }
        mock_yt.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "title": "Bohemian Rhapsody",
                    "artists": [{"name": "Queen", "id": "123"}],
                    "album": {"name": "A Night at the Opera", "id": "456"},
                    "length": "5:54",
                }
            ]
        }

        result = get_song_metadata("fJ9rUzIMcZQ")

        assert result is not None
        assert result.title == "Bohemian Rhapsody"
        assert result.artist == "Queen"
        assert result.album == "A Night at the Opera"
        assert result.duration_seconds == 354

    @patch("kikusan.search.YTMusic")
    def test_returns_none_when_get_song_fails(self, mock_ytmusic_class):
        """Should return None when get_song() raises an exception."""
        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt
        mock_yt.get_song.side_effect = Exception("API error")

        result = get_song_metadata("bad_id")
        assert result is None

    @patch("kikusan.search.YTMusic")
    def test_falls_back_to_watch_playlist_on_incomplete_details(self, mock_ytmusic_class):
        """When videoDetails is incomplete, should try watch playlist."""
        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt

        # get_song returns empty/incomplete videoDetails
        mock_yt.get_song.return_value = {
            "videoDetails": {}
        }
        mock_yt.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "title": "Bohemian Rhapsody",
                    "artists": [{"name": "Queen", "id": "123"}],
                    "album": {"name": "A Night at the Opera", "id": "456"},
                    "length": "5:54",
                }
            ]
        }

        result = get_song_metadata("fJ9rUzIMcZQ")

        assert result is not None
        assert result.title == "Bohemian Rhapsody"
        assert result.artist == "Queen"
        assert result.album == "A Night at the Opera"
        assert result.duration_seconds == 354

    @patch("kikusan.search.YTMusic")
    def test_handles_album_not_available(self, mock_ytmusic_class):
        """Should handle case where album info is not available."""
        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt

        mock_yt.get_song.return_value = {
            "videoDetails": {
                "title": "Some Song",
                "author": "Some Artist",
                "lengthSeconds": "200",
            }
        }
        # Watch playlist does not have album info
        mock_yt.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "title": "Some Song",
                    "artists": [{"name": "Some Artist"}],
                    "album": None,
                }
            ]
        }

        result = get_song_metadata("test123")

        assert result is not None
        assert result.title == "Some Song"
        assert result.artist == "Some Artist"
        assert result.album is None
        assert result.duration_seconds == 200

    @patch("kikusan.search.YTMusic")
    def test_handles_watch_playlist_failure_gracefully(self, mock_ytmusic_class):
        """Should still return metadata even if watch playlist fails (no album)."""
        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt

        mock_yt.get_song.return_value = {
            "videoDetails": {
                "title": "Some Song",
                "author": "Some Artist",
                "lengthSeconds": "200",
            }
        }
        mock_yt.get_watch_playlist.side_effect = Exception("Watch API failed")

        result = get_song_metadata("test123")

        assert result is not None
        assert result.title == "Some Song"
        assert result.artist == "Some Artist"
        assert result.album is None
        assert result.duration_seconds == 200

    @patch("kikusan.search.YTMusic")
    def test_returns_none_when_all_fallbacks_fail(self, mock_ytmusic_class):
        """Should return None when both get_song and watch playlist fail."""
        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt

        mock_yt.get_song.return_value = {
            "videoDetails": {}  # No title or author
        }
        mock_yt.get_watch_playlist.return_value = {
            "tracks": []  # Empty tracks
        }

        result = get_song_metadata("test123")
        assert result is None

    @patch("kikusan.search.YTMusic")
    def test_handles_non_numeric_length_seconds(self, mock_ytmusic_class):
        """Should handle non-numeric lengthSeconds gracefully."""
        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt

        mock_yt.get_song.return_value = {
            "videoDetails": {
                "title": "Some Song",
                "author": "Some Artist",
                "lengthSeconds": "not_a_number",
            }
        }
        mock_yt.get_watch_playlist.return_value = {"tracks": []}

        result = get_song_metadata("test123")

        assert result is not None
        assert result.duration_seconds == 0


class TestSongMetadataDataclass:
    """Tests for the SongMetadata dataclass."""

    def test_creates_with_all_fields(self):
        """Should create a SongMetadata with all fields."""
        metadata = SongMetadata(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            duration_seconds=300,
        )
        assert metadata.title == "Test Song"
        assert metadata.artist == "Test Artist"
        assert metadata.album == "Test Album"
        assert metadata.duration_seconds == 300

    def test_album_can_be_none(self):
        """Album field should accept None."""
        metadata = SongMetadata(
            title="Test Song",
            artist="Test Artist",
            album=None,
            duration_seconds=300,
        )
        assert metadata.album is None
