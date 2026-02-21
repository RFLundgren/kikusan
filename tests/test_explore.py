"""Tests for explore functionality (moods, charts, playlists)."""

from unittest.mock import MagicMock, patch

import pytest

from kikusan.search import (
    Album,
    Charts,
    ChartArtist,
    ChartTrack,
    MoodCategory,
    MoodPlaylist,
    MoodSection,
    _get_mood_playlists_fallback,
    get_charts,
    get_mood_categories,
    get_mood_playlists,
    get_new_releases,
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

    @patch("kikusan.search.YTMusic")
    def test_normalizes_author_list_payload(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_playlists.return_value = [
            {
                "playlistId": "RDCLAK5uy_list",
                "title": "Mixed Author",
                "author": [{"name": "Album", "id": None}],
            }
        ]

        playlists = get_mood_playlists("params")
        assert len(playlists) == 1
        assert playlists[0].author == "Album"

    @patch("kikusan.search._get_mood_playlists_fallback")
    @patch("kikusan.search.YTMusic")
    def test_falls_back_on_key_error(self, mock_ytmusic_cls, mock_fallback):
        """When ytmusicapi raises KeyError (musicTwoRowItemRenderer), fallback is used."""
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_playlists.side_effect = KeyError("musicTwoRowItemRenderer")
        mock_fallback.return_value = [
            {
                "playlistId": "RDCLAK5uy_recovered",
                "title": "Recovered Playlist",
                "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
            }
        ]

        playlists = get_mood_playlists("ggMPOg1uX_test")
        assert len(playlists) == 1
        assert playlists[0].playlist_id == "RDCLAK5uy_recovered"
        assert playlists[0].title == "Recovered Playlist"
        mock_fallback.assert_called_once_with(mock_yt, "ggMPOg1uX_test")

    @patch("kikusan.search.YTMusic")
    def test_non_key_error_still_raises(self, mock_ytmusic_cls):
        """Non-KeyError exceptions from ytmusicapi should still propagate."""
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_mood_playlists.side_effect = ValueError("API error")

        with pytest.raises(ValueError, match="API error"):
            get_mood_playlists("params")


class TestGetMoodPlaylistsFallback:
    """Test _get_mood_playlists_fallback() for manual response parsing."""

    def _make_section(self, renderer_type, items):
        """Helper to create a musicCarouselShelfRenderer section."""
        return {
            "musicCarouselShelfRenderer": {
                "contents": [{renderer_type: item} for item in items]
            }
        }

    def _make_playlist_item(self, title, playlist_id):
        """Helper to create a musicTwoRowItemRenderer playlist item."""
        return {
            "title": {
                "runs": [
                    {
                        "text": title,
                        "navigationEndpoint": {
                            "browseEndpoint": {"browseId": "VL" + playlist_id}
                        },
                    }
                ]
            },
            "subtitle": {"runs": [{"text": "YouTube Music"}]},
            "thumbnailRenderer": {
                "musicThumbnailRenderer": {
                    "thumbnail": {
                        "thumbnails": [{"url": "https://example.com/thumb.jpg"}]
                    }
                }
            },
            "navigationEndpoint": {
                "browseEndpoint": {"browseId": "VL" + playlist_id}
            },
        }

    def _make_response(self, sections):
        """Helper to wrap sections in the standard response structure."""
        return {
            "contents": {
                "singleColumnBrowseResultsRenderer": {
                    "tabs": [
                        {
                            "tabRenderer": {
                                "content": {
                                    "sectionListRenderer": {"contents": sections}
                                }
                            }
                        }
                    ]
                }
            }
        }

    def test_skips_non_playlist_sections(self):
        """Sections with musicResponsiveListItemRenderer (songs) should be skipped."""
        song_section = self._make_section(
            "musicResponsiveListItemRenderer",
            [{"flexColumns": []}],
        )
        playlist_section = self._make_section(
            "musicTwoRowItemRenderer",
            [self._make_playlist_item("My Playlist", "RDCLAK5uy_k123")],
        )
        response = self._make_response([song_section, playlist_section])

        mock_yt = MagicMock()
        mock_yt._send_request.return_value = response

        result = _get_mood_playlists_fallback(mock_yt, "test_params")
        assert len(result) == 1
        assert result[0]["title"] == "My Playlist"
        assert result[0]["playlistId"] == "RDCLAK5uy_k123"

    def test_handles_empty_sections(self):
        """Empty response sections should not crash."""
        empty_section = {"musicCarouselShelfRenderer": {"contents": []}}
        response = self._make_response([empty_section])

        mock_yt = MagicMock()
        mock_yt._send_request.return_value = response

        result = _get_mood_playlists_fallback(mock_yt, "test_params")
        assert result == []

    def test_handles_parse_errors_gracefully(self):
        """Individual item parse failures should not crash the whole function."""
        # Create one good item and one bad item (missing required fields)
        good_item = self._make_playlist_item("Good Playlist", "RDCLAK5uy_good")
        bad_item = {"title": {"runs": [{"text": "Bad Item"}]}}  # Missing navigationEndpoint
        section = {
            "musicCarouselShelfRenderer": {
                "contents": [
                    {"musicTwoRowItemRenderer": good_item},
                    {"musicTwoRowItemRenderer": bad_item},
                ]
            }
        }
        response = self._make_response([section])

        mock_yt = MagicMock()
        mock_yt._send_request.return_value = response

        result = _get_mood_playlists_fallback(mock_yt, "test_params")
        assert len(result) == 1
        assert result[0]["title"] == "Good Playlist"

    def test_handles_failed_response_navigation(self):
        """If the response structure is unexpected, return empty list."""
        mock_yt = MagicMock()
        mock_yt._send_request.return_value = {"unexpected": "structure"}

        result = _get_mood_playlists_fallback(mock_yt, "test_params")
        assert result == []

    def test_handles_multiple_valid_sections(self):
        """Multiple sections with musicTwoRowItemRenderer should all be parsed."""
        section1 = self._make_section(
            "musicTwoRowItemRenderer",
            [self._make_playlist_item("Playlist A", "RDCLAK5uy_a")],
        )
        section2 = self._make_section(
            "musicTwoRowItemRenderer",
            [self._make_playlist_item("Playlist B", "RDCLAK5uy_b")],
        )
        response = self._make_response([section1, section2])

        mock_yt = MagicMock()
        mock_yt._send_request.return_value = response

        result = _get_mood_playlists_fallback(mock_yt, "test_params")
        assert len(result) == 2
        titles = [r["title"] for r in result]
        assert "Playlist A" in titles
        assert "Playlist B" in titles

    def test_handles_grid_renderer_sections(self):
        """Sections using gridRenderer should also be parsed."""
        section = {
            "gridRenderer": {
                "items": [
                    {
                        "musicTwoRowItemRenderer": self._make_playlist_item(
                            "Grid Playlist", "RDCLAK5uy_grid"
                        )
                    }
                ]
            }
        }
        response = self._make_response([section])

        mock_yt = MagicMock()
        mock_yt._send_request.return_value = response

        result = _get_mood_playlists_fallback(mock_yt, "test_params")
        assert len(result) == 1
        assert result[0]["title"] == "Grid Playlist"

    def test_skips_unknown_section_types(self):
        """Sections with unknown renderer types should be skipped."""
        section = {"unknownRenderer": {"contents": []}}
        response = self._make_response([section])

        mock_yt = MagicMock()
        mock_yt._send_request.return_value = response

        result = _get_mood_playlists_fallback(mock_yt, "test_params")
        assert result == []


class TestGetCharts:
    """Test get_charts().

    ytmusicapi get_charts returns:
      - videos: list of playlist references [{title, playlistId, thumbnails}, ...]
      - artists: flat list of artist objects [{title, browseId, rank, trend, ...}, ...]
    The function fetches tracks from the first working video playlist via get_playlist.
    """

    @patch("kikusan.search.YTMusic")
    def test_returns_charts(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {
            "videos": [
                {"title": "Daily Top Music Videos", "playlistId": "PL_test123", "thumbnails": []},
            ],
            "artists": [
                {
                    "browseId": "UC123",
                    "title": "Top Artist",
                    "thumbnails": [{"url": "https://example.com/artist.jpg"}],
                    "rank": "1",
                    "trend": "neutral",
                },
            ],
        }
        mock_yt.get_playlist.return_value = {
            "title": "Daily Top Music Videos",
            "tracks": [
                {
                    "videoId": "abc123",
                    "title": "Hit Song",
                    "artists": [{"name": "Artist A"}],
                    "album": {"name": "Album X"},
                    "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
                },
            ],
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
        assert len(charts.artists) == 1
        assert charts.artists[0].browse_id == "UC123"
        mock_yt.get_playlist.assert_called_once_with("PL_test123", limit=100)

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
            "videos": [
                {"title": "Top Videos", "playlistId": "PL_test456", "thumbnails": []},
            ],
        }
        mock_yt.get_playlist.return_value = {
            "title": "Top Videos",
            "tracks": [
                {
                    "videoId": "xyz",
                    "title": "No Album",
                    "artists": [{"name": "Solo"}],
                    "thumbnails": [],
                },
            ],
        }

        charts = get_charts()
        assert len(charts.tracks) == 1
        assert charts.tracks[0].album is None
        assert charts.tracks[0].thumbnail_url is None

    @patch("kikusan.search.YTMusic")
    def test_default_country(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {"videos": [], "artists": []}

        charts = get_charts()
        assert charts.country == "ZZ"
        mock_yt.get_charts.assert_called_once_with("ZZ")

    @patch("kikusan.search.YTMusic")
    def test_falls_back_to_next_playlist_on_error(self, mock_ytmusic_cls):
        """When the first playlist fails (e.g. album-style ID), the next one is tried."""
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {
            "videos": [
                {"title": "Trending 20", "playlistId": "OLAK5uy_bad", "thumbnails": []},
                {"title": "Daily Top", "playlistId": "PL_good", "thumbnails": []},
            ],
            "artists": [],
        }
        mock_yt.get_playlist.side_effect = [
            Exception("not a playlist"),
            {
                "title": "Daily Top",
                "tracks": [
                    {
                        "videoId": "v1",
                        "title": "Fallback Song",
                        "artists": [{"name": "Artist B"}],
                        "thumbnails": [],
                    },
                ],
            },
        ]

        charts = get_charts("US")
        assert len(charts.tracks) == 1
        assert charts.tracks[0].video_id == "v1"
        assert charts.tracks[0].title == "Fallback Song"
        assert mock_yt.get_playlist.call_count == 2

    @patch("kikusan.search.YTMusic")
    def test_skips_tracks_without_video_id(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {
            "videos": [
                {"title": "Charts", "playlistId": "PL_test", "thumbnails": []},
            ],
            "artists": [],
        }
        mock_yt.get_playlist.return_value = {
            "title": "Charts",
            "tracks": [
                {"videoId": "good_id", "title": "Good", "artists": [{"name": "A"}], "thumbnails": []},
                {"videoId": "", "title": "Empty ID", "artists": [{"name": "B"}], "thumbnails": []},
                {"title": "No ID", "artists": [{"name": "C"}], "thumbnails": []},
            ],
        }

        charts = get_charts()
        assert len(charts.tracks) == 1
        assert charts.tracks[0].video_id == "good_id"

    @patch("kikusan.search.YTMusic")
    def test_chart_tracks_include_view_count_and_duration(self, mock_ytmusic_cls):
        """Chart tracks should include view_count and duration_seconds from playlist data."""
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {
            "videos": [
                {"title": "Charts", "playlistId": "PL_test", "thumbnails": []},
            ],
            "artists": [],
        }
        mock_yt.get_playlist.return_value = {
            "title": "Charts",
            "tracks": [
                {
                    "videoId": "v1",
                    "title": "Hit Song",
                    "artists": [{"name": "Artist A"}],
                    "thumbnails": [],
                    "duration": "3:45",
                    "duration_seconds": 225,
                    "views": "1.5B views",
                },
                {
                    "videoId": "v2",
                    "title": "New Song",
                    "artists": [{"name": "Artist B"}],
                    "thumbnails": [],
                    "duration": "4:10",
                },
            ],
        }

        charts = get_charts()
        assert len(charts.tracks) == 2

        assert charts.tracks[0].view_count == "1.5B views"
        assert charts.tracks[0].duration_seconds == 225
        assert charts.tracks[0].duration_display == "3:45"

        assert charts.tracks[1].view_count is None
        assert charts.tracks[1].duration_seconds == 250
        assert charts.tracks[1].duration_display == "4:10"

    @patch("kikusan.search.YTMusic")
    def test_chart_track_defaults(self, mock_ytmusic_cls):
        """Chart tracks should have sensible defaults for view_count and duration_seconds."""
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_charts.return_value = {
            "videos": [
                {"title": "Charts", "playlistId": "PL_test", "thumbnails": []},
            ],
            "artists": [],
        }
        mock_yt.get_playlist.return_value = {
            "title": "Charts",
            "tracks": [
                {
                    "videoId": "v1",
                    "title": "Minimal Track",
                    "artists": [{"name": "Artist"}],
                    "thumbnails": [],
                },
            ],
        }

        charts = get_charts()
        assert charts.tracks[0].view_count is None
        assert charts.tracks[0].duration_seconds == 0
        assert charts.tracks[0].duration_display == "0:00"


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
    def test_get_playlist_api_error_raises_value_error(self, mock_ytmusic_cls):
        """When ytmusicapi cannot parse the playlist response, a ValueError is raised."""
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_playlist.side_effect = Exception("Unable to find 'contents'")

        with pytest.raises(ValueError, match="unavailable or could not be loaded"):
            get_playlist_tracks("REb_GRi2dMZvne0")

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


class TestGetNewReleases:
    """Test get_new_releases()."""

    @patch("kikusan.search.YTMusic")
    def test_returns_albums(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_explore.return_value = {
            "new_releases": [
                {
                    "browseId": "MPREb_abc123",
                    "title": "New Album",
                    "type": "Album",
                    "artists": [{"name": "Artist A", "id": "UCabc"}],
                    "audioPlaylistId": "OLAK5uy_xyz",
                    "thumbnails": [
                        {"url": "https://lh3.example.com/thumb_small", "width": 60},
                        {"url": "https://lh3.example.com/thumb_large", "width": 226},
                    ],
                    "isExplicit": True,
                    "year": "2026",
                },
                {
                    "browseId": "MPREb_def456",
                    "title": "New Single",
                    "type": "Single",
                    "artists": [{"name": "Artist B"}],
                    "audioPlaylistId": "OLAK5uy_uvw",
                    "thumbnails": [],
                    "isExplicit": False,
                },
            ],
        }

        albums = get_new_releases()
        assert len(albums) == 2

        assert isinstance(albums[0], Album)
        assert albums[0].browse_id == "MPREb_abc123"
        assert albums[0].title == "New Album"
        assert albums[0].artist == "Artist A"
        assert albums[0].year == 2026
        assert albums[0].thumbnail_url == "https://lh3.example.com/thumb_large"
        assert albums[0].audio_playlist_id == "OLAK5uy_xyz"
        assert albums[0].album_type == "Album"
        assert albums[0].is_explicit is True

        assert albums[1].browse_id == "MPREb_def456"
        assert albums[1].album_type == "Single"
        assert albums[1].is_explicit is False
        assert albums[1].thumbnail_url is None

    @patch("kikusan.search.YTMusic")
    def test_empty_new_releases(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_explore.return_value = {}

        albums = get_new_releases()
        assert albums == []

    @patch("kikusan.search.YTMusic")
    def test_raises_on_error(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_explore.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            get_new_releases()

    @patch("kikusan.search.YTMusic")
    def test_missing_artists(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_explore.return_value = {
            "new_releases": [
                {
                    "browseId": "MPREb_noa",
                    "title": "No Artist Album",
                    "artists": [],
                    "thumbnails": [],
                },
            ],
        }

        albums = get_new_releases()
        assert albums[0].artist == "Unknown Artist"

    @patch("kikusan.search.YTMusic")
    def test_non_numeric_year(self, mock_ytmusic_cls):
        mock_yt = MagicMock()
        mock_ytmusic_cls.return_value = mock_yt
        mock_yt.get_explore.return_value = {
            "new_releases": [
                {
                    "browseId": "MPREb_noyear",
                    "title": "No Year",
                    "artists": [{"name": "X"}],
                    "thumbnails": [],
                    "year": "N/A",
                },
            ],
        }

        albums = get_new_releases()
        assert albums[0].year is None
