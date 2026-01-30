"""Tests for filename length truncation to prevent 'File name too long' errors."""

from pathlib import Path

from kikusan.config import MAX_FILENAME_BYTES
from kikusan.download import (
    _get_output_path,
    _get_ydl_opts,
    _sanitize_path_component,
    _truncate_to_bytes,
)


class TestTruncateToBytes:
    """Test UTF-8-safe byte truncation."""

    def test_short_string_unchanged(self):
        """ASCII string under limit passes through unchanged."""
        assert _truncate_to_bytes("hello", 100) == "hello"

    def test_exact_limit_unchanged(self):
        """String exactly at byte limit passes through unchanged."""
        text = "a" * 50
        assert _truncate_to_bytes(text, 50) == text

    def test_truncates_long_ascii(self):
        """Long ASCII string is truncated to byte limit."""
        text = "a" * 300
        result = _truncate_to_bytes(text, 200)
        assert len(result.encode("utf-8")) <= 200
        assert len(result) == 200

    def test_preserves_multibyte_characters(self):
        """Multi-byte UTF-8 characters are not split mid-character."""
        # Each accented char is 2 bytes in UTF-8
        text = "\u00e9" * 150  # e-acute, 2 bytes each = 300 bytes
        result = _truncate_to_bytes(text, 200)
        assert len(result.encode("utf-8")) <= 200
        # 200 bytes / 2 bytes per char = 100 chars
        assert len(result) == 100

    def test_preserves_emoji_characters(self):
        """4-byte emoji characters are not split."""
        # Each emoji is 4 bytes in UTF-8
        text = "\U0001f600" * 60  # grinning face, 4 bytes each = 240 bytes
        result = _truncate_to_bytes(text, 200)
        assert len(result.encode("utf-8")) <= 200
        # 200 / 4 = 50 full emojis
        assert len(result) == 50

    def test_mixed_ascii_and_multibyte(self):
        """Mixed ASCII and multi-byte chars are handled correctly."""
        # "Jose" (4 bytes) + accent chars
        text = "Jos\u00e9 " * 50  # "Jose " repeated, 6 bytes each
        result = _truncate_to_bytes(text, 30)
        assert len(result.encode("utf-8")) <= 30

    def test_strips_trailing_whitespace(self):
        """Trailing whitespace is stripped after truncation."""
        text = "Artist Name " * 30
        result = _truncate_to_bytes(text, 50)
        assert not result.endswith(" ")

    def test_empty_string(self):
        """Empty string returns empty."""
        assert _truncate_to_bytes("", 200) == ""

    def test_zero_limit(self):
        """Zero byte limit returns empty string."""
        assert _truncate_to_bytes("hello", 0) == ""


class TestSanitizePathComponentTruncation:
    """Test that _sanitize_path_component truncates long names."""

    def test_short_name_unchanged(self):
        """Short names pass through without truncation."""
        assert _sanitize_path_component("Short Artist") == "Short Artist"

    def test_long_name_truncated(self):
        """Names exceeding MAX_FILENAME_BYTES are truncated."""
        long_name = "A" * 300
        result = _sanitize_path_component(long_name)
        assert len(result.encode("utf-8")) <= MAX_FILENAME_BYTES
        assert result == "A" * MAX_FILENAME_BYTES

    def test_bad_bunny_artist_string(self):
        """The exact Bad Bunny artist string from the bug report is truncated."""
        bad_bunny_artists = (
            "Bad Bunny, Benito A. Martinez Ocasio, Roberto Jos\u00e9 Rosado Torres, "
            "Cristobal Ignacio D\u00edaz Lizama, Marcos Efra\u00edn Masis, "
            "\u00c1ngel Rivera Guzm\u00e1n, Francisco Salda\u00f1a, "
            "Christian Colon Rol\u00f3n, Norgie Noriega Montes, Joel Mart\u00ednez, "
            "Ra\u00fal Alexis Ortiz Rol\u00f3n, Llandel Veguilla Malav\u00e9, "
            "Everton Bonner, Hector Luis Delgado, Juan Luis Morera Luna, "
            "Lloyd Oliver Willis, John Christopher Taylor, Sly Filmore Dundar Lowell"
        )
        result = _sanitize_path_component(bad_bunny_artists)
        assert len(result.encode("utf-8")) <= MAX_FILENAME_BYTES

    def test_long_name_with_accented_chars(self):
        """Long names with accented characters truncate at character boundary."""
        # Create a string with 2-byte UTF-8 chars that exceeds limit
        long_name = "Caf\u00e9 " * 50
        result = _sanitize_path_component(long_name)
        # Verify valid UTF-8 (no split chars)
        result.encode("utf-8").decode("utf-8")
        assert len(result.encode("utf-8")) <= MAX_FILENAME_BYTES

    def test_custom_max_bytes(self):
        """Custom max_bytes parameter is respected."""
        long_name = "A" * 100
        result = _sanitize_path_component(long_name, max_bytes=50)
        assert len(result) == 50

    def test_sanitization_happens_before_truncation(self):
        """Invalid chars are removed before length check."""
        # String with invalid chars that would be shorter after sanitization
        name = 'A<>:"|?*' * 30  # 8 chars * 30 = 240 chars, but only 'A' * 30 after sanitization
        result = _sanitize_path_component(name)
        assert result == "A" * 30


class TestGetYdlOptsTrimFileName:
    """Test that yt-dlp options include trim_file_name."""

    def test_trim_file_name_in_opts(self):
        """yt-dlp options include trim_file_name to prevent long filenames."""
        output_dir = Path("/downloads")
        info = {"artist": "Test", "title": "Test Song"}
        opts = _get_ydl_opts(
            output_dir=output_dir,
            audio_format="opus",
            filename_template="%(artist)s - %(title)s",
            organization_mode="flat",
            info=info,
        )
        assert "trim_file_name" in opts
        assert opts["trim_file_name"] == MAX_FILENAME_BYTES

    def test_trim_file_name_in_album_mode(self):
        """trim_file_name is set for album mode too."""
        output_dir = Path("/downloads")
        info = {
            "artist": "Test Artist",
            "album": "Test Album",
            "title": "Test Song",
        }
        opts = _get_ydl_opts(
            output_dir=output_dir,
            audio_format="opus",
            filename_template="%(artist)s - %(title)s",
            organization_mode="album",
            info=info,
        )
        assert opts["trim_file_name"] == MAX_FILENAME_BYTES


class TestGetOutputPathTruncation:
    """Test that album mode output paths have truncated directory names."""

    def test_long_artist_name_truncated_in_album_mode(self):
        """Artist directory name is truncated in album mode."""
        output_dir = Path("/downloads")
        long_artist = "A" * 300
        info = {
            "artist": long_artist,
            "album": "Test Album",
            "release_year": 2024,
            "track_number": 1,
        }
        filename_template = "%(artist)s - %(title)s"
        result = _get_output_path(output_dir, info, filename_template, "album")
        # Extract the artist directory component
        parts = Path(result).parts
        # parts: ('/', 'downloads', '<artist>', '2024 - Test Album', '01 - ...')
        artist_dir = parts[2]
        assert len(artist_dir.encode("utf-8")) <= MAX_FILENAME_BYTES

    def test_long_album_name_truncated_in_album_mode(self):
        """Album directory name is truncated in album mode."""
        output_dir = Path("/downloads")
        long_album = "B" * 300
        info = {
            "artist": "Test Artist",
            "album": long_album,
            "release_year": 2024,
            "track_number": 1,
        }
        filename_template = "%(artist)s - %(title)s"
        result = _get_output_path(output_dir, info, filename_template, "album")
        # Extract the album directory component (includes "2024 - ")
        parts = Path(result).parts
        album_dir = parts[3]
        assert len(album_dir.encode("utf-8")) <= MAX_FILENAME_BYTES + len("2024 - ")
