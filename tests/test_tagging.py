"""Tests for tagging existing audio files with lyrics and ReplayGain."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kikusan.tagging import (
    SUPPORTED_EXTENSIONS,
    FileMetadata,
    TagStats,
    _has_replaygain_tags,
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
