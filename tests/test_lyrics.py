"""Tests for lyrics fetching with ytmusicapi metadata enhancement.

Verifies that get_lyrics_for_video() properly:
1. Fetches clean metadata from ytmusicapi
2. Tries exact match with ytmusicapi metadata first
3. Falls back to search endpoint if exact match fails
4. Falls back to yt-dlp metadata if ytmusicapi fails entirely
"""

from unittest.mock import MagicMock, patch

import httpx

from kikusan.lyrics import (
    _clean_artist,
    _clean_title,
    _extract_lyrics_from_response,
    _get_lyrics_exact,
    _lookup_lyrics_for_video,
    _search_lyrics,
    _strip_artist_from_title,
    _try_cleaned_lookup,
    get_lyrics,
    get_lyrics_for_video,
)
from kikusan.search import SongMetadata


class TestLookupLyricsForVideo:
    """Tests for the internal lyrics lookup logic (_lookup_lyrics_for_video)."""

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

        result = _lookup_lyrics_for_video(
            video_id="fJ9rUzIMcZQ",
            fallback_title="Queen - Bohemian Rhapsody (Official Video)",
            fallback_artist="QueenVEVO",
            fallback_duration=355,
        )

        assert result == "[00:00.00] Is this the real life?"
        mock_exact.assert_called_once_with("Bohemian Rhapsody", "Queen", 354)

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_falls_back_to_search_when_exact_fails(
        self, mock_exact, mock_search, mock_metadata
    ):
        """When exact match fails, search endpoint should be tried with ytmusicapi metadata."""
        mock_metadata.return_value = SongMetadata(
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            duration_seconds=354,
        )
        mock_exact.return_value = None
        mock_search.return_value = "[00:00.00] Is this the real life?"

        result = _lookup_lyrics_for_video(
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
        mock_exact.side_effect = [None, "[00:00.00] Is this the real life?"]
        mock_search.return_value = None

        result = _lookup_lyrics_for_video(
            video_id="fJ9rUzIMcZQ",
            fallback_title="Queen - Bohemian Rhapsody (Official Video)",
            fallback_artist="QueenVEVO",
            fallback_duration=355,
        )

        assert result == "[00:00.00] Is this the real life?"
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

        result = _lookup_lyrics_for_video(
            video_id="fJ9rUzIMcZQ",
            fallback_title="Queen - Bohemian Rhapsody (Official Video)",
            fallback_artist="QueenVEVO",
            fallback_duration=355,
        )

        assert result == "[00:00.00] Is this the real life?"
        mock_exact.assert_called_once_with(
            "Queen - Bohemian Rhapsody (Official Video)", "QueenVEVO", 355
        )

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_returns_none_when_all_strategies_fail(
        self, mock_exact, mock_search, mock_metadata
    ):
        """When all lookup strategies fail, return None."""
        mock_metadata.return_value = SongMetadata(
            title="Some Song",
            artist="Some Artist",
            album=None,
            duration_seconds=200,
        )
        mock_exact.return_value = None
        mock_search.return_value = None

        result = _lookup_lyrics_for_video(
            video_id="test123",
            fallback_title="Some Song",
            fallback_artist="Some Artist",
            fallback_duration=200,
        )

        assert result is None

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_tries_cleaned_ytmusicapi_metadata(
        self, mock_exact, mock_search, mock_metadata
    ):
        """When ytmusicapi metadata has parentheticals, cleaned version should be tried."""
        mock_metadata.return_value = SongMetadata(
            title="Force (Radio Edit)",
            artist="8181 Enzo, Michael Ekow",
            album="Force (Radio Edit)",
            duration_seconds=164,
        )
        mock_exact.side_effect = [None, "[00:00.00] Force lyrics"]
        mock_search.return_value = None

        result = _lookup_lyrics_for_video(
            video_id="test123",
            fallback_title="Force (Radio Edit)",
            fallback_artist="8181 Enzo, Michael Ekow",
            fallback_duration=164,
        )

        assert result == "[00:00.00] Force lyrics"
        mock_exact.assert_called_with("Force", "8181 Enzo", 164)

    @patch("kikusan.search.get_song_metadata")
    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_tries_cleaned_ytdlp_fallback(self, mock_exact, mock_search, mock_metadata):
        """When ytmusicapi fails, cleaned yt-dlp metadata should be tried."""
        mock_metadata.return_value = None
        mock_exact.side_effect = [None, "[00:00.00] lyrics"]
        mock_search.return_value = None

        result = _lookup_lyrics_for_video(
            video_id="test123",
            fallback_title="Song (Official Video)",
            fallback_artist="Artist",
            fallback_duration=200,
        )

        assert result == "[00:00.00] lyrics"
        mock_exact.assert_called_with("Song", "Artist", 200)


class TestGetLyricsForVideoCache:
    """Tests for the cache wrapper in get_lyrics_for_video()."""

    @patch("kikusan.lyrics._lookup_lyrics_for_video")
    @patch("kikusan.config.get_config")
    def test_cache_hit_positive_skips_lookup(self, mock_config, mock_lookup, tmp_path):
        """When lyrics are cached (positive), skip API lookup entirely."""
        import time
        from kikusan.metadata_cache import CachedLyrics, MetadataCache

        mock_cfg = MagicMock()
        mock_cfg.data_dir = tmp_path
        mock_cfg.lyrics_cache_hours = 168
        mock_config.return_value = mock_cfg

        # Pre-populate cache with positive result
        cache_dir = tmp_path
        with MetadataCache(cache_dir) as cache:
            cache.add_lyrics(
                CachedLyrics(
                    video_id="abc123",
                    lyrics="[00:00.00] Cached lyrics",
                    cached_at=time.time(),
                )
            )

        result = get_lyrics_for_video("abc123", "Title", "Artist", 200)

        assert result == "[00:00.00] Cached lyrics"
        mock_lookup.assert_not_called()

    @patch("kikusan.lyrics._lookup_lyrics_for_video")
    @patch("kikusan.config.get_config")
    def test_cache_hit_negative_skips_lookup(self, mock_config, mock_lookup, tmp_path):
        """When lyrics are cached (negative), skip API lookup and return None."""
        import time
        from kikusan.metadata_cache import CachedLyrics, MetadataCache

        mock_cfg = MagicMock()
        mock_cfg.data_dir = tmp_path
        mock_cfg.lyrics_cache_hours = 168
        mock_config.return_value = mock_cfg

        cache_dir = tmp_path
        with MetadataCache(cache_dir) as cache:
            cache.add_lyrics(
                CachedLyrics(
                    video_id="abc123",
                    lyrics=None,
                    cached_at=time.time(),
                )
            )

        result = get_lyrics_for_video("abc123", "Title", "Artist", 200)

        assert result is None
        mock_lookup.assert_not_called()

    @patch("kikusan.lyrics._lookup_lyrics_for_video")
    @patch("kikusan.config.get_config")
    def test_cache_miss_does_lookup_and_stores(
        self, mock_config, mock_lookup, tmp_path
    ):
        """On cache miss, perform lookup and store result."""
        from kikusan.metadata_cache import MetadataCache

        mock_cfg = MagicMock()
        mock_cfg.data_dir = tmp_path
        mock_cfg.lyrics_cache_hours = 168
        mock_config.return_value = mock_cfg

        mock_lookup.return_value = "[00:00.00] Fresh lyrics"

        result = get_lyrics_for_video("abc123", "Title", "Artist", 200)

        assert result == "[00:00.00] Fresh lyrics"
        mock_lookup.assert_called_once_with("abc123", "Title", "Artist", 200)

        # Verify it was stored in cache
        cache_dir = tmp_path
        with MetadataCache(cache_dir) as cache:
            cached = cache.get_lyrics("abc123")
        assert cached is not None
        assert cached.lyrics == "[00:00.00] Fresh lyrics"

    @patch("kikusan.lyrics._lookup_lyrics_for_video")
    @patch("kikusan.config.get_config")
    def test_cache_stores_negative_result(self, mock_config, mock_lookup, tmp_path):
        """Negative lookup results should be stored in cache."""
        from kikusan.metadata_cache import MetadataCache

        mock_cfg = MagicMock()
        mock_cfg.data_dir = tmp_path
        mock_cfg.lyrics_cache_hours = 168
        mock_config.return_value = mock_cfg

        mock_lookup.return_value = None

        result = get_lyrics_for_video("abc123", "Title", "Artist", 200)

        assert result is None

        cache_dir = tmp_path
        with MetadataCache(cache_dir) as cache:
            cached = cache.get_lyrics("abc123")
        assert cached is not None
        assert cached.lyrics is None

    @patch("kikusan.lyrics._lookup_lyrics_for_video")
    @patch("kikusan.config.get_config")
    def test_expired_negative_triggers_relookup(
        self, mock_config, mock_lookup, tmp_path
    ):
        """Expired negative cache should trigger a fresh lookup."""
        import time
        from kikusan.metadata_cache import CachedLyrics, MetadataCache

        mock_cfg = MagicMock()
        mock_cfg.data_dir = tmp_path
        mock_cfg.lyrics_cache_hours = 1  # 1 hour TTL
        mock_config.return_value = mock_cfg

        # Pre-populate with expired negative
        cache_dir = tmp_path
        with MetadataCache(cache_dir) as cache:
            cache.add_lyrics(
                CachedLyrics(
                    video_id="abc123",
                    lyrics=None,
                    cached_at=time.time() - 7200,  # 2 hours ago
                )
            )

        mock_lookup.return_value = "[00:00.00] Now available!"

        result = get_lyrics_for_video("abc123", "Title", "Artist", 200)

        assert result == "[00:00.00] Now available!"
        mock_lookup.assert_called_once()


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

    def test_returns_none_when_duration_is_zero(self):
        """Should skip exact lookup when duration is 0 (unknown)."""
        result = _get_lyrics_exact("Foo", "Bar", 0)
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

        result = _search_lyrics(
            "Bohemian Rhapsody", "Queen", "A Night at the Opera", 354
        )
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


class TestCleanTitle:
    """Tests for _clean_title helper."""

    def test_strips_radio_edit(self):
        assert _clean_title("Force (Radio Edit)") == "Force"

    def test_strips_official_video(self):
        assert _clean_title("Song (Official Video)") == "Song"

    def test_strips_brackets(self):
        assert _clean_title("Song [Official Music Video]") == "Song"

    def test_strips_multiple_suffixes(self):
        assert _clean_title("Song (feat. Artist) (Radio Edit)") == "Song"

    def test_preserves_clean_title(self):
        assert _clean_title("Bohemian Rhapsody") == "Bohemian Rhapsody"

    def test_preserves_mid_parens(self):
        assert _clean_title("Song (Part 1) Extra") == "Song (Part 1) Extra"

    def test_returns_original_if_cleaning_empties(self):
        assert _clean_title("(Radio Edit)") == "(Radio Edit)"

    def test_strips_remastered(self):
        assert _clean_title("Song (Remastered 2011)") == "Song"

    def test_strips_live(self):
        assert _clean_title("Song (Live at Wembley)") == "Song"


class TestCleanArtist:
    """Tests for _clean_artist helper."""

    def test_splits_on_comma(self):
        assert _clean_artist("8181 Enzo, Michael Ekow") == "8181 Enzo"

    def test_splits_on_semicolon(self):
        assert _clean_artist("Artist1; Artist2") == "Artist1"

    def test_splits_on_feat(self):
        assert _clean_artist("Main Artist feat. Other") == "Main Artist"

    def test_splits_on_ft(self):
        assert _clean_artist("Main Artist ft. Other") == "Main Artist"

    def test_splits_on_featuring(self):
        assert _clean_artist("Main Artist featuring Other") == "Main Artist"

    def test_preserves_single_artist(self):
        assert _clean_artist("Queen") == "Queen"

    def test_returns_original_if_cleaning_empties(self):
        assert _clean_artist(", Artist") == ", Artist"

    def test_case_insensitive_feat(self):
        assert _clean_artist("Main FEAT. Other") == "Main"


class TestTryCleanedLookup:
    """Tests for _try_cleaned_lookup helper."""

    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_skips_when_nothing_changes(self, mock_exact, mock_search):
        """Should return None without API calls if cleaning doesn't change anything."""
        result = _try_cleaned_lookup("Song", "Artist", None, 200)

        assert result is None
        mock_exact.assert_not_called()
        mock_search.assert_not_called()

    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_tries_exact_with_cleaned(self, mock_exact, mock_search):
        """Should try exact match with cleaned title/artist."""
        mock_exact.return_value = "[00:00.00] lyrics"

        result = _try_cleaned_lookup(
            "Force (Radio Edit)", "8181 Enzo, Michael Ekow", None, 164
        )

        assert result == "[00:00.00] lyrics"
        mock_exact.assert_called_once_with("Force", "8181 Enzo", 164)
        mock_search.assert_not_called()

    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_falls_back_to_search(self, mock_exact, mock_search):
        """Should try search if exact match fails."""
        mock_exact.return_value = None
        mock_search.return_value = "[00:00.00] found via search"

        result = _try_cleaned_lookup("Song (Radio Edit)", "Artist", "Album", 200)

        assert result == "[00:00.00] found via search"
        mock_search.assert_called_once_with("Song", "Artist", "Album", 200)

    @patch("kikusan.lyrics._search_lyrics")
    @patch("kikusan.lyrics._get_lyrics_exact")
    def test_tries_artist_stripped_title(self, mock_exact, mock_search):
        """Should try stripping artist prefix from title as additional step."""
        mock_exact.return_value = None
        mock_search.side_effect = [None, "[00:00.00] found via stripped"]

        result = _try_cleaned_lookup(
            "AK AUSSERKONTROLLE x PASHANIM - BLN [Visualizer]",
            "AK AUSSERKONTROLLE",
            None,
            200,
        )

        assert result == "[00:00.00] found via stripped"
        # First search call: cleaned title "AK AUSSERKONTROLLE x PASHANIM - BLN"
        # Second search call: stripped title "BLN" with combined artists
        assert mock_search.call_count == 2
        mock_search.assert_called_with(
            "BLN", "AK AUSSERKONTROLLE, PASHANIM", None, 200
        )


class TestStripArtistFromTitle:
    """Tests for _strip_artist_from_title helper."""

    def test_strips_single_artist_prefix(self):
        result = _strip_artist_from_title("Coldplay - Yellow", "Coldplay")
        assert result == ("Yellow", "Coldplay")

    def test_strips_collab_prefix_with_x(self):
        result = _strip_artist_from_title(
            "AK AUSSERKONTROLLE x PASHANIM - BLN", "AK AUSSERKONTROLLE"
        )
        assert result == ("BLN", "AK AUSSERKONTROLLE, PASHANIM")

    def test_strips_collab_prefix_with_ampersand(self):
        result = _strip_artist_from_title(
            "Artist1 & Artist2 - Song Name", "Artist1"
        )
        assert result == ("Song Name", "Artist1, Artist2")

    def test_returns_none_when_no_dash(self):
        result = _strip_artist_from_title("Just A Song Title", "Artist")
        assert result is None

    def test_returns_none_when_artist_not_in_prefix(self):
        result = _strip_artist_from_title("Someone Else - Song", "My Artist")
        assert result is None

    def test_case_insensitive_match(self):
        result = _strip_artist_from_title("coldplay - Yellow", "Coldplay")
        assert result == ("Yellow", "coldplay")

    def test_returns_none_for_empty_suffix(self):
        result = _strip_artist_from_title("Artist - ", "Artist")
        assert result is None

    def test_multiple_collaborators_with_comma(self):
        result = _strip_artist_from_title(
            "Artist1, Artist2, Artist3 - Track", "Artist1"
        )
        assert result == ("Track", "Artist1, Artist2, Artist3")
