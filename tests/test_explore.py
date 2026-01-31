"""Tests for explore functionality (moods, charts, playlists)."""

from unittest.mock import MagicMock, patch

import pytest

from kikusan.search import (
    Charts,
    ChartArtist,
    ChartTrack,
    MoodCategory,
    MoodPlaylist,
    MoodSection,
    get_charts,
    get_mood_categories,
    get_mood_playlists,
    get_playlist_tracks,
)


class TestGetMoodCategories:
    """Test get_mood_categories()."""

    @patch("kikusan.search.YTMusic")
    def test_returns_sections(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_categories.return_value = {
            "Genres": [
                {"title": "Pop", "params": "ggMPOg1uX1J"},
                {"title": "Rock", "params": "ggMPOg1uX1S"},
            ],
            "Moods & moments": [
                {"title": "Chill", "params": "ggMPOg1uX1A"},
            ],
        }

        sections = get_mood_categories()
        assert len(sections) == 2
        assert isinstance(sections[0], MoodSection)

        genres = next(s for s in sections if s.title == "Genres")
        assert len(genres.categories) == 2
        assert genres.categories[0].title == "Pop"
        assert genres.categories[0].params == "ggMPOg1uX1J"

    @patch("kikusan.search.YTMusic")
    def test_empty_result(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_categories.return_value = {}

        sections = get_mood_categories()
        assert sections == []

    @patch("kikusan.search.YTMusic")
    def test_raises_on_error(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_categories.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            get_mood_categories()


class TestGetMoodPlaylists:
    """Test get_mood_playlists()."""

    @patch("kikusan.search.YTMusic")
    def test_returns_playlists(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_playlists.return_value = [
            {
                "playlistId": "RDCLAK5uy_k123",
                "title": "Pop Hits",
                "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
                "author": "YouTube Music",
            },
            {
                "playlistId": "RDCLAK5uy_k456",
                "title": "Chill Vibes",
                "thumbnails": [],
                "author": None,
            },
        ]

        playlists = get_mood_playlists("ggMPOg1uX1J")
        assert len(playlists) == 2
        assert isinstance(playlists[0], MoodPlaylist)
        assert playlists[0].playlist_id == "RDCLAK5uy_k123"
        assert playlists[0].title == "Pop Hits"
        assert playlists[0].thumbnail_url == "https://example.com/thumb.jpg"
        assert playlists[0].author == "YouTube Music"
        assert playlists[1].thumbnail_url is None

    @patch("kikusan.search.YTMusic")
    def test_empty_result(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_playlists.return_value = []

        playlists = get_mood_playlists("ggMPOg1uX1J")
        assert playlists == []

    @patch("kikusan.search.YTMusic")
    def test_missing_fields(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_playlists.return_value = [
            {"title": "Minimal"},
        ]

        playlists = get_mood_playlists("params")
        assert len(playlists) == 1
        assert playlists[0].playlist_id == ""
        assert playlists[0].title == "Minimal"
        assert playlists[0].thumbnail_url is None
        assert playlists[0].author is None


class TestGetCharts:
    """Test get_charts()."""

    @patch("kikusan.search.YTMusic")
    def test_returns_charts(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {
            "videos": {
                "items": [
                    {
                        "videoId": "abc123",
                        "title": "Hit Song",
                        "artists": [{"name": "Artist A"}],
                        "album": {"name": "Album X"},
                        "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
                        "rank": "1",
                        "trend": "up",
                    },
                ],
            },
            "artists": {
                "items": [
                    {
                        "browseId": "UC123",
                        "title": "Top Artist",
                        "thumbnails": [{"url": "https://example.com/artist.jpg"}],
                        "rank": "1",
                        "trend": "neutral",
                    },
                ],
            },
        }

        charts = get_charts("US")
        assert isinstance(charts, Charts)
        assert charts.country == "US"
        assert len(charts.tracks) == 1
        assert charts.tracks[0].video_id == "abc123"
        assert charts.tracks[0].title == "Hit Song"
        assert charts.tracks[0].artist == "Artist A"
        assert charts.tracks[0].album == "Album X"
        assert charts.tracks[0].rank == "1"
        assert charts.tracks[0].trend == "up"
        assert len(charts.artists) == 1
        assert charts.artists[0].browse_id == "UC123"

    @patch("kikusan.search.YTMusic")
    def test_empty_charts(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {}

        charts = get_charts("ZZ")
        assert charts.tracks == []
        assert charts.artists == []

    @patch("kikusan.search.YTMusic")
    def test_missing_album(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {
            "videos": {
                "items": [
                    {
                        "videoId": "xyz",
                        "title": "No Album",
                        "artists": [{"name": "Solo"}],
                        "thumbnails": [],
                    },
                ],
            },
        }

        charts = get_charts()
        assert len(charts.tracks) == 1
        assert charts.tracks[0].album is None
        assert charts.tracks[0].thumbnail_url is None

    @patch("kikusan.search.YTMusic")
    def test_default_country(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {"videos": {"items": []}, "artists": {"items": []}}

        charts = get_charts()
        assert charts.country == "ZZ"
        mock_yt.get_charts.assert_called_once_with("ZZ")


class TestGetPlaylistTracks:
    """Test get_playlist_tracks()."""

    @patch("kikusan.search.YTMusic")
    def test_returns_tracks(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_playlist.return_value = {
            "title": "Pop Hits",
            "tracks": [
                {
                    "videoId": "vid1",
                    "title": "Song One",
                    "artists": [{"name": "Artist 1"}, {"name": "Artist 2"}],
                    "album": {"name": "Album A"},
                    "duration": "3:45",
                    "duration_seconds": 225,
                    "thumbnails": [{"url": "https://example.com/t1.jpg"}],
                },
                {
                    "videoId": "vid2",
                    "title": "Song Two",
                    "artists": [{"name": "Artist 3"}],
                    "album": None,
                    "duration": "4:10",
                    "thumbnails": [],
                },
            ],
        }

        tracks = get_playlist_tracks("RDCLAK5uy_k123")
        assert len(tracks) == 2
        assert tracks[0].video_id == "vid1"
        assert tracks[0].title == "Song One"
        assert tracks[0].artist == "Artist 1"
        assert tracks[0].artists == ["Artist 1", "Artist 2"]
        assert tracks[0].album == "Album A"
        assert tracks[0].duration_seconds == 225
        assert tracks[1].album is None

    @patch("kikusan.search.YTMusic")
    def test_skips_entries_without_video_id(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_playlist.return_value = {
            "title": "Test",
            "tracks": [
                {"videoId": "vid1", "title": "Good", "artists": [{"name": "A"}], "duration": "3:00"},
                {"title": "Bad Entry", "artists": []},
                {"videoId": None, "title": "Null ID", "artists": []},
            ],
        }

        tracks = get_playlist_tracks("playlist")
        assert len(tracks) == 1
        assert tracks[0].video_id == "vid1"

    @patch("kikusan.search.YTMusic")
    def test_empty_playlist(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_playlist.return_value = {"title": "Empty", "tracks": []}

        tracks = get_playlist_tracks("empty")
        assert tracks == []

    @patch("kikusan.search.YTMusic")
    def test_duration_fallback(self, mock_ytmusic_cls):
        """Test that duration_text is parsed when duration_seconds is missing."""
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_playlist.return_value = {
            "title": "Test",
            "tracks": [
                {"videoId": "v1", "title": "T", "artists": [{"name": "A"}], "duration": "2:30"},
            ],
        }

        tracks = get_playlist_tracks("pl")
        assert tracks[0].duration_seconds == 150
