"""Tests for tagging existing audio files with lyrics, ReplayGain, and metadata enrichment."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kikusan.tagging import (
    SUPPORTED_EXTENSIONS,
    NegativeResultCache,
    FileMetadata,
    PartialMetadata,
    TagStats,
    _extract_partial_metadata,
    _has_cover_art,
    _has_replaygain_tags,
    _make_enrichment_cache,
    _make_lyrics_cache_key,
    _parse_metadata_from_path,
    _search_metadata,
    _write_metadata_tags,
    collect_audio_files,
    extract_metadata,
    tag_directory,
    tag_file,
)


class TestExtractMetadata:
    """Tests for metadata extraction via mutagen."""

    def test_extracts_all_fields(self):
        mock_audio = {
            "title": ["Test Song"],
            "artist": ["Test Artist"],
            "album": ["Test Album"],
        }
        mock_info = MagicMock()
        mock_info.length = 210.5

        mock_file = MagicMock()
        mock_file.__getitem__ = mock_audio.__getitem__
        mock_file.get = mock_audio.get
        mock_file.info = mock_info

        with patch("mutagen.File", return_value=mock_file):
            result = extract_metadata(Path("/fake/song.opus"))

        assert result is not None
        assert result.title == "Test Song"
        assert result.artist == "Test Artist"
        assert result.album == "Test Album"
        assert result.duration_seconds == 210

    def test_returns_none_when_mutagen_cant_open(self):
        with patch("mutagen.File", return_value=None):
            result = extract_metadata(Path("/fake/bad.opus"))

        assert result is None

    def test_returns_none_when_title_missing(self):
        mock_file = MagicMock()
        mock_file.get = lambda key, *args: {"artist": ["Artist"]}.get(key)

        with patch("mutagen.File", return_value=mock_file):
            result = extract_metadata(Path("/fake/notitle.opus"))

        assert result is None

    def test_returns_none_when_artist_missing(self):
        mock_file = MagicMock()
        mock_file.get = lambda key, *args: {"title": ["Song"]}.get(key)

        with patch("mutagen.File", return_value=mock_file):
            result = extract_metadata(Path("/fake/noartist.opus"))

        assert result is None

    def test_album_is_optional(self):
        mock_audio = {
            "title": ["Song"],
            "artist": ["Artist"],
        }
        mock_info = MagicMock()
        mock_info.length = 180.0

        mock_file = MagicMock()
        mock_file.get = lambda key, *args: mock_audio.get(key)
        mock_file.info = mock_info

        with patch("mutagen.File", return_value=mock_file):
            result = extract_metadata(Path("/fake/single.mp3"))

        assert result is not None
        assert result.album is None

    def test_prefers_artists_multi_value_tag(self):
        mock_audio = {
            "ARTISTS": ["Primary Artist"],
            "artist": ["All Artists feat. Someone"],
            "title": ["Song"],
        }
        mock_info = MagicMock()
        mock_info.length = 120.0

        mock_file = MagicMock()
        mock_file.get = lambda key, *args: mock_audio.get(key)
        mock_file.info = mock_info

        with patch("mutagen.File", return_value=mock_file):
            result = extract_metadata(Path("/fake/multi.opus"))

        assert result.artist == "Primary Artist"

    def test_handles_string_metadata(self):
        """Some formats return strings instead of lists."""
        mock_info = MagicMock()
        mock_info.length = 200.0

        mock_file = MagicMock()
        mock_file.get = lambda key, *args: {
            "title": "String Title",
            "artist": "String Artist",
            "album": "String Album",
        }.get(key)
        mock_file.info = mock_info

        with patch("mutagen.File", return_value=mock_file):
            result = extract_metadata(Path("/fake/strings.flac"))

        assert result.title == "String Title"
        assert result.artist == "String Artist"
        assert result.album == "String Album"

    def test_handles_mutagen_exception(self):
        with patch("mutagen.File", side_effect=Exception("corrupt file")):
            result = extract_metadata(Path("/fake/corrupt.opus"))

        assert result is None

    def test_duration_zero_when_no_info(self):
        mock_file = MagicMock()
        mock_file.get = lambda key, *args: {
            "title": ["Song"],
            "artist": ["Artist"],
        }.get(key)
        mock_file.info = None

        with patch("mutagen.File", return_value=mock_file):
            result = extract_metadata(Path("/fake/noinfo.opus"))

        assert result is not None
        assert result.duration_seconds == 0


class TestCollectAudioFiles:
    """Tests for recursive audio file collection."""

    def test_finds_all_supported_formats(self, tmp_path):
        (tmp_path / "song.opus").touch()
        (tmp_path / "song.mp3").touch()
        (tmp_path / "song.flac").touch()

        files = collect_audio_files(tmp_path)

        assert len(files) == 3
        extensions = {f.suffix for f in files}
        assert extensions == SUPPORTED_EXTENSIONS

    def test_ignores_unsupported_formats(self, tmp_path):
        (tmp_path / "song.opus").touch()
        (tmp_path / "song.wav").touch()
        (tmp_path / "song.m4a").touch()
        (tmp_path / "cover.jpg").touch()

        files = collect_audio_files(tmp_path)

        assert len(files) == 1
        assert files[0].suffix == ".opus"

    def test_finds_files_recursively(self, tmp_path):
        subdir = tmp_path / "Artist" / "Album"
        subdir.mkdir(parents=True)
        (subdir / "track.opus").touch()
        (tmp_path / "flat.mp3").touch()

        files = collect_audio_files(tmp_path)

        assert len(files) == 2

    def test_returns_sorted(self, tmp_path):
        (tmp_path / "z_song.opus").touch()
        (tmp_path / "a_song.opus").touch()

        files = collect_audio_files(tmp_path)

        assert files[0].name == "a_song.opus"
        assert files[1].name == "z_song.opus"

    def test_empty_directory(self, tmp_path):
        files = collect_audio_files(tmp_path)
        assert files == []


class TestHasReplaygainTags:
    """Tests for ReplayGain tag detection."""

    def test_opus_r128_track_gain(self):
        mock_file = MagicMock()
        mock_file.__contains__ = lambda self, key: key == "R128_TRACK_GAIN"

        with patch("mutagen.File", return_value=mock_file):
            assert _has_replaygain_tags(Path("/fake/song.opus"), "opus") is True

    def test_opus_replaygain_track_gain(self):
        mock_file = MagicMock()
        mock_file.__contains__ = lambda self, key: key == "REPLAYGAIN_TRACK_GAIN"

        with patch("mutagen.File", return_value=mock_file):
            assert _has_replaygain_tags(Path("/fake/song.opus"), "opus") is True

    def test_mp3_replaygain_track_gain(self):
        mock_file = MagicMock()
        mock_file.__contains__ = lambda self, key: key == "REPLAYGAIN_TRACK_GAIN"

        with patch("mutagen.File", return_value=mock_file):
            assert _has_replaygain_tags(Path("/fake/song.mp3"), "mp3") is True

    def test_flac_replaygain_track_gain(self):
        mock_file = MagicMock()
        mock_file.__contains__ = lambda self, key: key == "REPLAYGAIN_TRACK_GAIN"

        with patch("mutagen.File", return_value=mock_file):
            assert _has_replaygain_tags(Path("/fake/song.flac"), "flac") is True

    def test_no_tags(self):
        mock_file = MagicMock()
        mock_file.__contains__ = lambda self, key: False

        with patch("mutagen.File", return_value=mock_file):
            assert _has_replaygain_tags(Path("/fake/song.opus"), "opus") is False

    def test_mutagen_cant_open(self):
        with patch("mutagen.File", return_value=None):
            assert _has_replaygain_tags(Path("/fake/bad.opus"), "opus") is False

    def test_exception_returns_false(self):
        with patch("mutagen.File", side_effect=Exception("corrupt")):
            assert _has_replaygain_tags(Path("/fake/bad.opus"), "opus") is False


class TestTagFile:
    """Tests for per-file tagging logic."""

    def _make_metadata(self, **overrides):
        defaults = {
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
            "duration_seconds": 200,
        }
        defaults.update(overrides)
        return FileMetadata(**defaults)

    def test_skips_file_when_metadata_extraction_fails(self):
        stats = TagStats()

        with patch("kikusan.tagging.extract_metadata", return_value=None):
            tag_file(Path("/fake/bad.opus"), stats=stats)

        assert stats.errors == 1

    def test_falls_back_to_path_metadata_for_corrupted_files(self, tmp_path):
        """When mutagen can't read a corrupted file, use filename for lyrics lookup."""
        audio = tmp_path / "Cool Artist - Great Song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=None),
            patch("kikusan.lyrics.get_lyrics", return_value="[00:00.00] Lyrics") as mock_get,
            patch("kikusan.lyrics.save_lyrics") as mock_save,
        ):
            tag_file(audio, do_replaygain=False, root_dir=tmp_path, stats=stats)

        assert stats.lyrics_added == 1
        mock_get.assert_called_once_with("Great Song", "Cool Artist", 0)
        mock_save.assert_called_once()

    def test_path_fallback_skipped_when_no_artist_in_filename(self):
        """Files without 'Artist - Title' pattern still get skipped."""
        stats = TagStats()

        with patch("kikusan.tagging.extract_metadata", return_value=None):
            tag_file(Path("/fake/just-a-title.opus"), stats=stats)

        assert stats.errors == 1

    def test_lyrics_skipped_when_lrc_exists(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()
        lrc = tmp_path / "song.lrc"
        lrc.write_text("[00:00.00] Hello")

        stats = TagStats()

        with patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()):
            tag_file(audio, do_replaygain=False, stats=stats)

        assert stats.lyrics_skipped == 1
        assert stats.lyrics_added == 0

    def test_lyrics_added_on_success(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", return_value="[00:00.00] Lyrics here"),
            patch("kikusan.lyrics.save_lyrics") as mock_save,
        ):
            tag_file(audio, do_replaygain=False, stats=stats)

        assert stats.lyrics_added == 1
        mock_save.assert_called_once()

    def test_lyrics_search_fallback(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", return_value=None),
            patch("kikusan.lyrics._search_lyrics", return_value="[00:00.00] Found via search"),
            patch("kikusan.lyrics.save_lyrics") as mock_save,
        ):
            tag_file(audio, do_replaygain=False, stats=stats)

        assert stats.lyrics_added == 1
        mock_save.assert_called_once()

    def test_lyrics_not_found(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", return_value=None),
            patch("kikusan.lyrics._search_lyrics", return_value=None),
            patch("kikusan.lyrics._try_cleaned_lookup", return_value=None),
        ):
            tag_file(audio, do_replaygain=False, stats=stats)

        assert stats.lyrics_not_found == 1

    def test_lyrics_exception_counted_as_failed(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", side_effect=Exception("network error")),
        ):
            tag_file(audio, do_replaygain=False, stats=stats)

        assert stats.lyrics_failed == 1

    def test_replaygain_applied(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.tagging._has_replaygain_tags", return_value=False),
            patch("kikusan.replaygain.apply_replaygain", return_value=True),
        ):
            tag_file(audio, do_lyrics=False, stats=stats)

        assert stats.replaygain_applied == 1

    def test_replaygain_skipped_when_tags_exist(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.tagging._has_replaygain_tags", return_value=True),
            patch("kikusan.replaygain.apply_replaygain") as mock_rg,
        ):
            tag_file(audio, do_lyrics=False, stats=stats)

        assert stats.replaygain_skipped == 1
        mock_rg.assert_not_called()

    def test_replaygain_failure_counted(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.tagging._has_replaygain_tags", return_value=False),
            patch("kikusan.replaygain.apply_replaygain", return_value=False),
        ):
            tag_file(audio, do_lyrics=False, stats=stats)

        assert stats.replaygain_failed == 1

    def test_dry_run_lyrics_no_save(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics") as mock_get,
            patch("kikusan.lyrics.save_lyrics") as mock_save,
        ):
            tag_file(audio, do_replaygain=False, dry_run=True, stats=stats)

        mock_get.assert_not_called()
        mock_save.assert_not_called()

    def test_dry_run_replaygain_no_apply(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.replaygain.apply_replaygain") as mock_rg,
        ):
            tag_file(audio, do_lyrics=False, dry_run=True, stats=stats)

        mock_rg.assert_not_called()

    def test_both_lyrics_and_replaygain(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", return_value="[00:00.00] lyrics"),
            patch("kikusan.lyrics.save_lyrics"),
            patch("kikusan.tagging._has_replaygain_tags", return_value=False),
            patch("kikusan.replaygain.apply_replaygain", return_value=True),
        ):
            tag_file(audio, stats=stats)

        assert stats.lyrics_added == 1
        assert stats.replaygain_applied == 1


class TestTagDirectory:
    """Tests for directory-level tagging."""

    def test_processes_all_files(self, tmp_path):
        (tmp_path / "a.opus").touch()
        (tmp_path / "b.mp3").touch()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=None),
        ):
            stats = tag_directory(tmp_path)

        assert stats.files_found == 2
        assert stats.errors == 2  # both fail metadata extraction

    def test_returns_correct_stats(self, tmp_path):
        (tmp_path / "song.opus").touch()

        metadata = FileMetadata(
            title="Song", artist="Artist", album="Album", duration_seconds=200
        )

        with (
            patch(
                "kikusan.config.get_config",
                return_value=MagicMock(data_dir=tmp_path, lyrics_cache_hours=168),
            ),
            patch("kikusan.tagging.extract_metadata", return_value=metadata),
            patch("kikusan.lyrics.get_lyrics", return_value="[00:00.00] lyrics"),
            patch("kikusan.lyrics.save_lyrics"),
            patch("kikusan.tagging._has_replaygain_tags", return_value=False),
            patch("kikusan.replaygain.apply_replaygain", return_value=True),
        ):
            stats = tag_directory(tmp_path)

        assert stats.files_found == 1
        assert stats.lyrics_added == 1
        assert stats.replaygain_applied == 1

    def test_continues_on_per_file_error(self, tmp_path):
        (tmp_path / "bad.opus").touch()
        (tmp_path / "good.opus").touch()

        metadata = FileMetadata(
            title="Song", artist="Artist", album=None, duration_seconds=200
        )

        call_count = 0

        def extract_side_effect(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("unexpected error")
            return metadata

        with (
            patch("kikusan.tagging.extract_metadata", side_effect=extract_side_effect),
            patch("kikusan.lyrics.get_lyrics", return_value=None),
            patch("kikusan.lyrics._search_lyrics", return_value=None),
            patch("kikusan.lyrics._try_cleaned_lookup", return_value=None),
            patch("kikusan.tagging._has_replaygain_tags", return_value=False),
            patch("kikusan.replaygain.apply_replaygain", return_value=True),
        ):
            stats = tag_directory(tmp_path)

        assert stats.files_found == 2
        assert stats.errors == 1  # first file errored
        assert stats.replaygain_applied == 1  # second file succeeded

    def test_empty_directory(self, tmp_path):
        stats = tag_directory(tmp_path)

        assert stats.files_found == 0
        assert stats.errors == 0

    def test_dry_run_flag_passed_through(self, tmp_path):
        (tmp_path / "song.opus").touch()

        metadata = FileMetadata(
            title="Song", artist="Artist", album=None, duration_seconds=200
        )

        with (
            patch("kikusan.tagging.extract_metadata", return_value=metadata),
            patch("kikusan.lyrics.get_lyrics") as mock_lyrics,
            patch("kikusan.replaygain.apply_replaygain") as mock_rg,
        ):
            stats = tag_directory(tmp_path, dry_run=True)

        mock_lyrics.assert_not_called()
        mock_rg.assert_not_called()
        assert stats.files_found == 1

    def test_lyrics_only_mode(self, tmp_path):
        (tmp_path / "song.opus").touch()

        metadata = FileMetadata(
            title="Song", artist="Artist", album=None, duration_seconds=200
        )

        with (
            patch(
                "kikusan.config.get_config",
                return_value=MagicMock(data_dir=tmp_path, lyrics_cache_hours=168),
            ),
            patch("kikusan.tagging.extract_metadata", return_value=metadata),
            patch("kikusan.lyrics.get_lyrics", return_value="[00:00.00] lyrics"),
            patch("kikusan.lyrics.save_lyrics"),
            patch("kikusan.replaygain.apply_replaygain") as mock_rg,
        ):
            stats = tag_directory(tmp_path, do_replaygain=False)

        mock_rg.assert_not_called()
        assert stats.lyrics_added == 1
        assert stats.replaygain_applied == 0

    def test_replaygain_only_mode(self, tmp_path):
        (tmp_path / "song.opus").touch()

        metadata = FileMetadata(
            title="Song", artist="Artist", album=None, duration_seconds=200
        )

        with (
            patch("kikusan.tagging.extract_metadata", return_value=metadata),
            patch("kikusan.lyrics.get_lyrics") as mock_lyrics,
            patch("kikusan.tagging._has_replaygain_tags", return_value=False),
            patch("kikusan.replaygain.apply_replaygain", return_value=True),
        ):
            stats = tag_directory(tmp_path, do_lyrics=False)

        mock_lyrics.assert_not_called()
        assert stats.replaygain_applied == 1


# --- Metadata enrichment tests ---


class TestParseMetadataFromPath:
    """Tests for filename-based metadata parsing."""

    def test_flat_mode_artist_title(self):
        root = Path("/music")
        fp = Path("/music/Radiohead - Creep.opus")

        title, artist, album = _parse_metadata_from_path(fp, root)

        assert title == "Creep"
        assert artist == "Radiohead"
        assert album is None

    def test_album_mode(self):
        root = Path("/music")
        fp = Path("/music/Radiohead/OK Computer/03 - Subterranean Homesick Alien.opus")

        title, artist, album = _parse_metadata_from_path(fp, root)

        assert title == "Subterranean Homesick Alien"
        assert artist == "Radiohead"
        assert album == "OK Computer"

    def test_no_separator_fallback(self):
        root = Path("/music")
        fp = Path("/music/mystery_track.opus")

        title, artist, album = _parse_metadata_from_path(fp, root)

        assert title == "mystery_track"
        assert artist == ""
        assert album is None

    def test_album_mode_no_track_number(self):
        root = Path("/music")
        fp = Path("/music/Artist/Album/Song Title.flac")

        title, artist, album = _parse_metadata_from_path(fp, root)

        assert title == "Song Title"
        assert artist == "Artist"
        assert album == "Album"

    def test_flat_mode_multiple_separators(self):
        root = Path("/music")
        fp = Path("/music/Artist - Song - Remix.opus")

        title, artist, album = _parse_metadata_from_path(fp, root)

        assert title == "Song - Remix"
        assert artist == "Artist"
        assert album is None


class TestSearchMetadata:
    """Tests for YouTube Music search integration."""

    def test_successful_search(self):
        mock_track = MagicMock()
        mock_track.title = "Found Song"

        with patch("kikusan.search.search", return_value=[mock_track]):
            result = _search_metadata("Song", "Artist")

        assert result is mock_track

    def test_no_results(self):
        with patch("kikusan.search.search", return_value=[]):
            result = _search_metadata("Unknown", "Nobody")

        assert result is None

    def test_exception_returns_none(self):
        with patch("kikusan.search.search", side_effect=Exception("API error")):
            result = _search_metadata("Song", "Artist")

        assert result is None

    def test_empty_artist_uses_title_only(self):
        with patch("kikusan.search.search", return_value=[]) as mock_search:
            _search_metadata("Song Title", "")

        mock_search.assert_called_once_with("Song Title", limit=1)


class TestHasCoverArt:
    """Tests for cover art detection."""

    def test_flac_with_pictures(self):
        mock_flac = MagicMock()
        mock_flac.pictures = [MagicMock()]

        with (
            patch("mutagen.File", return_value=MagicMock()),
            patch("mutagen.flac.FLAC", return_value=mock_flac),
        ):
            assert _has_cover_art(Path("/fake/song.flac")) is True

    def test_flac_without_pictures(self):
        mock_flac = MagicMock()
        mock_flac.pictures = []

        with (
            patch("mutagen.File", return_value=MagicMock()),
            patch("mutagen.flac.FLAC", return_value=mock_flac),
        ):
            assert _has_cover_art(Path("/fake/song.flac")) is False

    def test_opus_with_picture(self):
        mock_audio = MagicMock()
        mock_audio.__contains__ = lambda self, key: key == "metadata_block_picture"

        with patch("mutagen.File", return_value=mock_audio):
            assert _has_cover_art(Path("/fake/song.opus")) is True

    def test_opus_without_picture(self):
        mock_audio = MagicMock()
        mock_audio.__contains__ = lambda self, key: False

        with patch("mutagen.File", return_value=mock_audio):
            assert _has_cover_art(Path("/fake/song.opus")) is False

    def test_mp3_with_apic(self):
        mock_tags = MagicMock()
        mock_tags.getall.return_value = [MagicMock()]

        with (
            patch("mutagen.File", return_value=MagicMock()),
            patch("mutagen.id3.ID3", return_value=mock_tags),
        ):
            assert _has_cover_art(Path("/fake/song.mp3")) is True

    def test_mp3_without_apic(self):
        mock_tags = MagicMock()
        mock_tags.getall.return_value = []

        with (
            patch("mutagen.File", return_value=MagicMock()),
            patch("mutagen.id3.ID3", return_value=mock_tags),
        ):
            assert _has_cover_art(Path("/fake/song.mp3")) is False

    def test_mutagen_cant_open(self):
        with patch("mutagen.File", return_value=None):
            assert _has_cover_art(Path("/fake/bad.opus")) is False


class TestExtractPartialMetadata:
    """Tests for partial metadata extraction."""

    def test_extracts_all_fields(self):
        mock_audio = {
            "title": ["Song"],
            "artist": ["Artist"],
            "album": ["Album"],
        }
        mock_info = MagicMock()
        mock_info.length = 200.0

        mock_file = MagicMock()
        mock_file.get = lambda key, *args: mock_audio.get(key)
        mock_file.info = mock_info

        with (
            patch("mutagen.File", return_value=mock_file),
            patch("kikusan.tagging._has_cover_art", return_value=True),
        ):
            result = _extract_partial_metadata(Path("/fake/song.opus"))

        assert result is not None
        assert result.title == "Song"
        assert result.artist == "Artist"
        assert result.album == "Album"
        assert result.duration_seconds == 200
        assert result.has_cover is True

    def test_returns_partial_when_title_missing(self):
        mock_file = MagicMock()
        mock_file.get = lambda key, *args: {"artist": ["Artist"]}.get(key)
        mock_file.info = MagicMock(length=100.0)

        with (
            patch("mutagen.File", return_value=mock_file),
            patch("kikusan.tagging._has_cover_art", return_value=False),
        ):
            result = _extract_partial_metadata(Path("/fake/song.opus"))

        assert result is not None
        assert result.title is None
        assert result.artist == "Artist"
        assert result.has_cover is False

    def test_returns_none_when_mutagen_fails(self):
        with patch("mutagen.File", return_value=None):
            result = _extract_partial_metadata(Path("/fake/bad.opus"))

        assert result is None


class TestWriteMetadataTags:
    """Tests for metadata tag writing."""

    def _make_partial(self, **overrides):
        defaults = {
            "title": None,
            "artist": None,
            "album": None,
            "duration_seconds": 0,
            "has_cover": False,
        }
        defaults.update(overrides)
        return PartialMetadata(**defaults)

    def _make_track(self, **overrides):
        defaults = {
            "title": "Found Title",
            "artist": "Found Artist",
            "artists": ["Found Artist"],
            "album": "Found Album",
            "thumbnail_url": None,
        }
        defaults.update(overrides)
        return MagicMock(**defaults)

    def test_writes_missing_vorbis_tags(self):
        mock_audio = MagicMock()
        partial = self._make_partial()
        track = self._make_track()

        with patch("mutagen.File", return_value=mock_audio):
            result = _write_metadata_tags(
                Path("/fake/song.opus"), track, partial
            )

        assert result is True
        mock_audio.__setitem__.assert_any_call("title", ["Found Title"])
        mock_audio.__setitem__.assert_any_call("artist", ["Found Artist"])
        mock_audio.__setitem__.assert_any_call("album", ["Found Album"])
        mock_audio.save.assert_called_once()

    def test_skips_existing_tags(self):
        mock_audio = MagicMock()
        partial = self._make_partial(title="Existing", artist="Existing", album="Existing", has_cover=True)
        track = self._make_track()

        with patch("mutagen.File", return_value=mock_audio):
            result = _write_metadata_tags(
                Path("/fake/song.opus"), track, partial
            )

        # Nothing written since all tags exist
        mock_audio.save.assert_not_called()

    def test_writes_multi_artist_tags(self):
        mock_audio = MagicMock()
        partial = self._make_partial(title="Title", artist="Artist", album="Album", has_cover=True)
        track = self._make_track(artists=["Artist1", "Artist2"])

        with (
            patch("mutagen.File", return_value=mock_audio),
            patch("kikusan.tags.write_multi_artist_tags") as mock_multi,
        ):
            _write_metadata_tags(Path("/fake/song.opus"), track, partial)

        mock_multi.assert_called_once_with(Path("/fake/song.opus"), ["Artist1", "Artist2"])

    def test_embeds_cover_when_missing(self):
        mock_audio = MagicMock()
        partial = self._make_partial(title="T", artist="A", album="Al")
        track = self._make_track(thumbnail_url="https://example.com/thumb.jpg", artists=["A"])

        with (
            patch("mutagen.File", return_value=mock_audio),
            patch("kikusan.tagging._embed_cover_art", return_value=True) as mock_embed,
        ):
            _write_metadata_tags(Path("/fake/song.opus"), track, partial)

        mock_embed.assert_called_once_with(Path("/fake/song.opus"), "https://example.com/thumb.jpg")

    def test_skips_cover_when_present(self):
        mock_audio = MagicMock()
        partial = self._make_partial(title="T", artist="A", album="Al", has_cover=True)
        track = self._make_track(thumbnail_url="https://example.com/thumb.jpg", artists=["A"])

        with (
            patch("mutagen.File", return_value=mock_audio),
            patch("kikusan.tagging._embed_cover_art") as mock_embed,
        ):
            _write_metadata_tags(Path("/fake/song.opus"), track, partial)

        mock_embed.assert_not_called()


class TestNegativeResultCache:
    """Tests for the generic negative result cache."""

    def test_records_and_checks_failure(self, tmp_path):
        cache = NegativeResultCache(tmp_path / "cache.json", ttl_hours=168)
        key = NegativeResultCache.make_key("Artist", "Song")

        assert cache.is_cached(key) is False

        cache.record_failure(key)

        assert cache.is_cached(key) is True

    def test_expired_entry_not_cached(self, tmp_path):
        cache = NegativeResultCache(tmp_path / "cache.json", ttl_hours=1)
        key = NegativeResultCache.make_key("Artist", "Song")

        # Write an expired entry directly
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cache._data[key] = {"failed_at": old_time}
        cache._save()

        assert cache.is_cached(key) is False

    def test_ttl_zero_disables_cache(self, tmp_path):
        cache = NegativeResultCache(tmp_path / "cache.json", ttl_hours=0)
        key = NegativeResultCache.make_key("Artist", "Song")
        cache.record_failure(key)

        assert cache.is_cached(key) is False

    def test_persists_to_disk(self, tmp_path):
        path = tmp_path / "cache.json"
        key = NegativeResultCache.make_key("Artist", "Song")

        cache1 = NegativeResultCache(path, ttl_hours=168)
        cache1.record_failure(key)

        # Load fresh
        cache2 = NegativeResultCache(path, ttl_hours=168)
        assert cache2.is_cached(key) is True

    def test_corrupted_cache_resets(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cache_path.write_text("not valid json!!!")

        cache = NegativeResultCache(cache_path, ttl_hours=168)

        assert cache._data == {}
        assert (tmp_path / "cache.json.bak").exists()

    def test_case_insensitive_key(self, tmp_path):
        cache = NegativeResultCache(tmp_path / "cache.json", ttl_hours=168)
        key_upper = NegativeResultCache.make_key("ARTIST", "SONG")
        key_lower = NegativeResultCache.make_key("artist", "song")
        cache.record_failure(key_upper)

        # make_key lowercases, so these should be the same
        assert key_upper == key_lower
        assert cache.is_cached(key_lower) is True

    def test_enrichment_cache_factory(self, tmp_path):
        cache = _make_enrichment_cache(tmp_path, 168)
        assert cache._path == tmp_path / "enrichment_cache.json"


class TestTagFileMetadataEnrichment:
    """Tests for the metadata enrichment flow in tag_file."""

    def _make_partial(self, **overrides):
        defaults = {
            "title": None,
            "artist": None,
            "album": None,
            "duration_seconds": 0,
            "has_cover": False,
        }
        defaults.update(overrides)
        return PartialMetadata(**defaults)

    def _make_track_mock(self):
        track = MagicMock()
        track.title = "Found Song"
        track.artist = "Found Artist"
        track.artists = ["Found Artist"]
        track.album = "Found Album"
        track.thumbnail_url = "https://example.com/thumb.jpg"
        return track

    def test_enriches_missing_metadata(self, tmp_path):
        audio = tmp_path / "Unknown Artist - Cool Song.opus"
        audio.touch()

        stats = TagStats()
        partial = self._make_partial()
        track = self._make_track_mock()

        metadata_after = FileMetadata(
            title="Found Song", artist="Found Artist", album="Found Album", duration_seconds=200
        )

        with (
            patch("kikusan.tagging._extract_partial_metadata", return_value=partial),
            patch("kikusan.tagging._search_metadata", return_value=track),
            patch("kikusan.tagging._write_metadata_tags", return_value=True),
            patch("kikusan.tagging.extract_metadata", return_value=metadata_after),
            patch("kikusan.lyrics.get_lyrics", return_value=None),
            patch("kikusan.lyrics._search_lyrics", return_value=None),
            patch("kikusan.lyrics._try_cleaned_lookup", return_value=None),
            patch("kikusan.tagging._has_replaygain_tags", return_value=True),
        ):
            tag_file(
                audio,
                do_metadata=True,
                root_dir=tmp_path,
                stats=stats,
            )

        assert stats.metadata_enriched == 1

    def test_skips_complete_metadata(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()

        stats = TagStats()
        partial = self._make_partial(
            title="Song", artist="Artist", album="Album", has_cover=True
        )

        metadata = FileMetadata(
            title="Song", artist="Artist", album="Album", duration_seconds=200
        )

        with (
            patch("kikusan.tagging._extract_partial_metadata", return_value=partial),
            patch("kikusan.tagging._search_metadata") as mock_search,
            patch("kikusan.tagging.extract_metadata", return_value=metadata),
            patch("kikusan.lyrics.get_lyrics", return_value=None),
            patch("kikusan.lyrics._search_lyrics", return_value=None),
            patch("kikusan.lyrics._try_cleaned_lookup", return_value=None),
            patch("kikusan.tagging._has_replaygain_tags", return_value=True),
        ):
            tag_file(
                audio,
                do_metadata=True,
                root_dir=tmp_path,
                stats=stats,
            )

        assert stats.metadata_skipped == 1
        mock_search.assert_not_called()

    def test_enrichment_enables_lyrics_on_previously_skipped(self, tmp_path):
        """Files that had no metadata can now get lyrics after enrichment."""
        audio = tmp_path / "Artist - Song.opus"
        audio.touch()

        stats = TagStats()
        partial = self._make_partial()
        track = self._make_track_mock()

        metadata_after = FileMetadata(
            title="Found Song", artist="Found Artist", album="Found Album", duration_seconds=200
        )

        with (
            patch("kikusan.tagging._extract_partial_metadata", return_value=partial),
            patch("kikusan.tagging._search_metadata", return_value=track),
            patch("kikusan.tagging._write_metadata_tags", return_value=True),
            patch("kikusan.tagging.extract_metadata", return_value=metadata_after),
            patch("kikusan.lyrics.get_lyrics", return_value="[00:00.00] lyrics"),
            patch("kikusan.lyrics.save_lyrics") as mock_save,
            patch("kikusan.tagging._has_replaygain_tags", return_value=True),
        ):
            tag_file(
                audio,
                do_metadata=True,
                root_dir=tmp_path,
                stats=stats,
            )

        assert stats.metadata_enriched == 1
        assert stats.lyrics_added == 1
        mock_save.assert_called_once()

    def test_cache_hit_skips_search(self, tmp_path):
        audio = tmp_path / "Artist - Song.opus"
        audio.touch()

        stats = TagStats()
        partial = self._make_partial()

        cache = _make_enrichment_cache(tmp_path, ttl_hours=168)
        key = NegativeResultCache.make_key("Artist", "Song")
        cache.record_failure(key)

        with (
            patch("kikusan.tagging._extract_partial_metadata", return_value=partial),
            patch("kikusan.tagging._search_metadata") as mock_search,
            patch("kikusan.tagging.extract_metadata", return_value=None),
        ):
            tag_file(
                audio,
                do_metadata=True,
                do_lyrics=False,
                do_replaygain=False,
                root_dir=tmp_path,
                enrichment_cache=cache,
                stats=stats,
            )

        mock_search.assert_not_called()
        assert stats.metadata_skipped == 1

    def test_dry_run_no_search(self, tmp_path):
        audio = tmp_path / "Artist - Song.opus"
        audio.touch()

        stats = TagStats()
        partial = self._make_partial()

        metadata = FileMetadata(
            title="Song", artist="Artist", album=None, duration_seconds=200
        )

        with (
            patch("kikusan.tagging._extract_partial_metadata", return_value=partial),
            patch("kikusan.tagging._search_metadata") as mock_search,
            patch("kikusan.tagging.extract_metadata", return_value=metadata),
            patch("kikusan.lyrics.get_lyrics") as mock_lyrics,
            patch("kikusan.replaygain.apply_replaygain") as mock_rg,
        ):
            tag_file(
                audio,
                do_metadata=True,
                root_dir=tmp_path,
                dry_run=True,
                stats=stats,
            )

        mock_search.assert_not_called()

    def test_search_failure_records_in_cache(self, tmp_path):
        audio = tmp_path / "Artist - Song.opus"
        audio.touch()

        stats = TagStats()
        partial = self._make_partial()
        cache = _make_enrichment_cache(tmp_path, ttl_hours=168)

        with (
            patch("kikusan.tagging._extract_partial_metadata", return_value=partial),
            patch("kikusan.tagging._search_metadata", return_value=None),
            patch("kikusan.tagging.extract_metadata", return_value=None),
        ):
            tag_file(
                audio,
                do_metadata=True,
                do_lyrics=False,
                do_replaygain=False,
                root_dir=tmp_path,
                enrichment_cache=cache,
                stats=stats,
            )

        assert stats.metadata_failed == 1
        key = NegativeResultCache.make_key("Artist", "Song")
        assert cache.is_cached(key) is True


class TestLyricsCache:
    """Tests for lyrics caching via MetadataCache (same as cron/download path)."""

    def _make_metadata(self, **overrides):
        defaults = {
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
            "duration_seconds": 200,
        }
        defaults.update(overrides)
        return FileMetadata(**defaults)

    def test_lyrics_not_found_records_in_cache(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()
        cache_dir = tmp_path / ".kikusan"

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", return_value=None),
            patch("kikusan.lyrics._search_lyrics", return_value=None),
            patch("kikusan.lyrics._try_cleaned_lookup", return_value=None),
        ):
            tag_file(
                audio,
                do_lyrics=True,
                do_replaygain=False,
                lyrics_cache_dir=cache_dir,
                stats=stats,
            )

        assert stats.lyrics_not_found == 1

        # Verify it was stored in MetadataCache
        from kikusan.metadata_cache import MetadataCache
        cache_key = _make_lyrics_cache_key("Test Artist", "Test Song")
        with MetadataCache(cache_dir) as cache:
            cached = cache.get_lyrics(cache_key, 168)
        assert cached is not None
        assert cached.lyrics is None  # negative cache

    def test_lyrics_cache_hit_skips_lookup(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()
        cache_dir = tmp_path / ".kikusan"

        # Pre-populate the cache with a negative result
        import time
        from kikusan.metadata_cache import CachedLyrics, MetadataCache
        cache_key = _make_lyrics_cache_key("Test Artist", "Test Song")
        with MetadataCache(cache_dir) as cache:
            cache.add_lyrics(CachedLyrics(
                video_id=cache_key,
                lyrics=None,
                cached_at=time.time(),
            ))

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics") as mock_get,
        ):
            tag_file(
                audio,
                do_lyrics=True,
                do_replaygain=False,
                lyrics_cache_dir=cache_dir,
                lyrics_cache_ttl=168,
                stats=stats,
            )

        mock_get.assert_not_called()
        assert stats.lyrics_skipped == 1

    def test_lyrics_found_caches_positive(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()
        cache_dir = tmp_path / ".kikusan"

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", return_value="[00:00.00] lyrics"),
            patch("kikusan.lyrics.save_lyrics"),
        ):
            tag_file(
                audio,
                do_lyrics=True,
                do_replaygain=False,
                lyrics_cache_dir=cache_dir,
                stats=stats,
            )

        assert stats.lyrics_added == 1

        # Positive result should be cached
        from kikusan.metadata_cache import MetadataCache
        cache_key = _make_lyrics_cache_key("Test Artist", "Test Song")
        with MetadataCache(cache_dir) as cache:
            cached = cache.get_lyrics(cache_key, 168)
        assert cached is not None
        assert cached.lyrics == "[00:00.00] lyrics"

    def test_lyrics_exception_does_not_cache(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()
        cache_dir = tmp_path / ".kikusan"

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics", side_effect=Exception("network error")),
        ):
            tag_file(
                audio,
                do_lyrics=True,
                do_replaygain=False,
                lyrics_cache_dir=cache_dir,
                stats=stats,
            )

        assert stats.lyrics_failed == 1

        # Should NOT be cached on exception
        from kikusan.metadata_cache import MetadataCache
        cache_key = _make_lyrics_cache_key("Test Artist", "Test Song")
        with MetadataCache(cache_dir) as cache:
            cached = cache.get_lyrics(cache_key, 168)
        assert cached is None

    def test_lrc_exists_skips_cache_check(self, tmp_path):
        audio = tmp_path / "song.opus"
        audio.touch()
        lrc = tmp_path / "song.lrc"
        lrc.write_text("[00:00.00] Hello")
        cache_dir = tmp_path / ".kikusan"

        stats = TagStats()

        with patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()):
            tag_file(
                audio,
                do_lyrics=True,
                do_replaygain=False,
                lyrics_cache_dir=cache_dir,
                stats=stats,
            )

        assert stats.lyrics_skipped == 1

    def test_positive_cache_hit_skips_lookup(self, tmp_path):
        """A previously found lyrics result should also skip the lookup."""
        audio = tmp_path / "song.opus"
        audio.touch()
        cache_dir = tmp_path / ".kikusan"

        import time
        from kikusan.metadata_cache import CachedLyrics, MetadataCache
        cache_key = _make_lyrics_cache_key("Test Artist", "Test Song")
        with MetadataCache(cache_dir) as cache:
            cache.add_lyrics(CachedLyrics(
                video_id=cache_key,
                lyrics="[00:00.00] cached lyrics",
                cached_at=time.time(),
            ))

        stats = TagStats()

        with (
            patch("kikusan.tagging.extract_metadata", return_value=self._make_metadata()),
            patch("kikusan.lyrics.get_lyrics") as mock_get,
        ):
            tag_file(
                audio,
                do_lyrics=True,
                do_replaygain=False,
                lyrics_cache_dir=cache_dir,
                lyrics_cache_ttl=168,
                stats=stats,
            )

        # Positive cache hit — skip lookup but count as skipped (lrc file doesn't exist,
        # but we already found lyrics before and the .lrc was presumably saved then)
        mock_get.assert_not_called()
        assert stats.lyrics_skipped == 1
