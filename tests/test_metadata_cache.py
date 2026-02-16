"""Tests for the SQLite metadata cache module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from kikusan.metadata_cache import CachedSongMetadata, CachedTrack, MetadataCache


class TestMetadataCacheSongMetadata:
    """Tests for song_metadata table operations."""

    def test_miss_returns_none(self, tmp_path: Path):
        with MetadataCache(tmp_path) as cache:
            assert cache.get_song_metadata("nonexistent") is None

    def test_round_trip(self, tmp_path: Path):
        entry = CachedSongMetadata(
            video_id="abc123",
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            duration_seconds=210,
        )
        with MetadataCache(tmp_path) as cache:
            cache.add_song_metadata(entry)
            result = cache.get_song_metadata("abc123")

        assert result is not None
        assert result.video_id == "abc123"
        assert result.title == "Test Song"
        assert result.artist == "Test Artist"
        assert result.album == "Test Album"
        assert result.duration_seconds == 210

    def test_album_none_round_trip(self, tmp_path: Path):
        entry = CachedSongMetadata(
            video_id="abc123",
            title="Song",
            artist="Artist",
            album=None,
            duration_seconds=100,
        )
        with MetadataCache(tmp_path) as cache:
            cache.add_song_metadata(entry)
            result = cache.get_song_metadata("abc123")

        assert result is not None
        assert result.album is None

    def test_overwrite_existing(self, tmp_path: Path):
        original = CachedSongMetadata(
            video_id="abc123", title="Old", artist="A", album=None, duration_seconds=100,
        )
        updated = CachedSongMetadata(
            video_id="abc123", title="New", artist="B", album="Album", duration_seconds=200,
        )
        with MetadataCache(tmp_path) as cache:
            cache.add_song_metadata(original)
            cache.add_song_metadata(updated)
            result = cache.get_song_metadata("abc123")

        assert result is not None
        assert result.title == "New"
        assert result.artist == "B"

    def test_corrupt_json_returns_none(self, tmp_path: Path):
        """Corrupt JSON in DB row should return None, not crash."""
        with MetadataCache(tmp_path) as cache:
            # Write corrupt data directly
            cache._conn.execute(
                "INSERT INTO song_metadata (video_id, data) VALUES (?, ?)",
                ("bad", "{not valid json!!!"),
            )
            cache._conn.commit()
            result = cache.get_song_metadata("bad")

        assert result is None


class TestMetadataCacheTrack:
    """Tests for track table operations."""

    def test_miss_returns_none(self, tmp_path: Path):
        with MetadataCache(tmp_path) as cache:
            assert cache.get_track("nonexistent") is None

    def test_round_trip(self, tmp_path: Path):
        entry = CachedTrack(
            video_id="xyz789",
            title="Track Title",
            artist="Main Artist",
            artists=["Main Artist", "Featured Artist"],
            album="Some Album",
            duration_seconds=300,
            thumbnail_url="https://example.com/thumb.jpg",
            view_count="1.5M",
            video_type="MUSIC_VIDEO_TYPE_ATV",
        )
        with MetadataCache(tmp_path) as cache:
            cache.add_track(entry)
            result = cache.get_track("xyz789")

        assert result is not None
        assert result.video_id == "xyz789"
        assert result.title == "Track Title"
        assert result.artists == ["Main Artist", "Featured Artist"]
        assert result.album == "Some Album"
        assert result.thumbnail_url == "https://example.com/thumb.jpg"
        assert result.view_count == "1.5M"
        assert result.video_type == "MUSIC_VIDEO_TYPE_ATV"

    def test_nullable_fields(self, tmp_path: Path):
        entry = CachedTrack(
            video_id="xyz789",
            title="Track",
            artist="Artist",
            artists=["Artist"],
            album=None,
            duration_seconds=100,
            thumbnail_url=None,
            view_count=None,
            video_type=None,
        )
        with MetadataCache(tmp_path) as cache:
            cache.add_track(entry)
            result = cache.get_track("xyz789")

        assert result is not None
        assert result.album is None
        assert result.thumbnail_url is None
        assert result.view_count is None
        assert result.video_type is None

    def test_corrupt_json_returns_none(self, tmp_path: Path):
        with MetadataCache(tmp_path) as cache:
            cache._conn.execute(
                "INSERT INTO track (video_id, data) VALUES (?, ?)",
                ("bad", "corrupted"),
            )
            cache._conn.commit()
            result = cache.get_track("bad")

        assert result is None


class TestMetadataCacheDirectoryCreation:
    """Tests for auto-creation of cache directory."""

    def test_creates_missing_directory(self, tmp_path: Path):
        cache_dir = tmp_path / "nested" / "dir"
        assert not cache_dir.exists()

        with MetadataCache(cache_dir) as cache:
            cache.add_song_metadata(
                CachedSongMetadata(
                    video_id="v1", title="T", artist="A", album=None, duration_seconds=1,
                )
            )

        assert cache_dir.exists()
        assert (cache_dir / "metadata_cache.db").exists()


class TestMetadataCacheConnectionFailure:
    """Tests for graceful handling when DB is unavailable."""

    def test_operations_return_none_when_load_fails(self, tmp_path: Path):
        """If DB open fails, reads return None and writes are no-ops."""
        cache = MetadataCache(tmp_path)
        # Don't call load() — simulate connection being None
        assert cache.get_song_metadata("v1") is None
        assert cache.get_track("v1") is None
        # Writes should not raise
        cache.add_song_metadata(
            CachedSongMetadata(video_id="v1", title="T", artist="A", album=None, duration_seconds=1)
        )
        cache.add_track(
            CachedTrack(
                video_id="v1", title="T", artist="A", artists=["A"],
                album=None, duration_seconds=1, thumbnail_url=None, view_count=None,
            )
        )


class TestGetSongMetadataCacheIntegration:
    """Integration test: get_song_metadata uses cache on second call."""

    @patch("kikusan.search.get_config")
    @patch("kikusan.search.YTMusic")
    def test_second_call_uses_cache(self, mock_ytmusic_class, mock_get_config, tmp_path: Path):
        from kikusan.search import get_song_metadata

        mock_config = MagicMock()
        mock_config.download_dir = tmp_path
        mock_get_config.return_value = mock_config

        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt
        mock_yt.get_song.return_value = {
            "videoDetails": {
                "title": "Bohemian Rhapsody",
                "author": "Queen",
                "lengthSeconds": "354",
            }
        }
        mock_yt.get_watch_playlist.return_value = {
            "tracks": [{
                "album": {"name": "A Night at the Opera"},
            }]
        }

        # First call — hits API
        result1 = get_song_metadata("fJ9rUzIMcZQ")
        assert result1 is not None
        assert mock_yt.get_song.call_count == 1

        # Second call — should use cache, no additional API calls
        result2 = get_song_metadata("fJ9rUzIMcZQ")
        assert result2 is not None
        assert result2.title == "Bohemian Rhapsody"
        assert result2.artist == "Queen"
        assert result2.album == "A Night at the Opera"
        assert result2.duration_seconds == 354
        # get_song should NOT be called again
        assert mock_yt.get_song.call_count == 1


class TestGetTrackFromVideoIdCacheIntegration:
    """Integration test: get_track_from_video_id uses cache on second call."""

    @patch("kikusan.search.get_config")
    @patch("kikusan.search.YTMusic")
    def test_second_call_uses_cache(self, mock_ytmusic_class, mock_get_config, tmp_path: Path):
        from kikusan.search import get_track_from_video_id

        mock_config = MagicMock()
        mock_config.download_dir = tmp_path
        mock_get_config.return_value = mock_config

        mock_yt = MagicMock()
        mock_ytmusic_class.return_value = mock_yt
        mock_yt.get_song.return_value = {
            "videoDetails": {
                "videoId": "abc123abcde",
                "title": "Test Song",
                "author": "Test Artist",
                "lengthSeconds": "200",
                "thumbnail": {"thumbnails": [{"url": "https://img.example.com/1.jpg"}]},
                "viewCount": "1000",
                "musicVideoType": "MUSIC_VIDEO_TYPE_ATV",
            }
        }

        # First call — hits API
        track1 = get_track_from_video_id("abc123abcde")
        assert track1.title == "Test Song"
        assert mock_yt.get_song.call_count == 1

        # Second call — should use cache
        track2 = get_track_from_video_id("abc123abcde")
        assert track2.title == "Test Song"
        assert track2.artist == "Test Artist"
        assert track2.video_type == "MUSIC_VIDEO_TYPE_ATV"
        assert mock_yt.get_song.call_count == 1
