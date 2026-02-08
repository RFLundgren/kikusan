"""Tests for M3U playlist management (rebuild_m3u)."""

from pathlib import Path

from kikusan.playlist import rebuild_m3u


def _create_audio_file(directory: Path, name: str) -> Path:
    """Create a dummy audio file and return its path."""
    file_path = directory / name
    file_path.write_text("fake audio data")
    return file_path


def _read_m3u_entries(m3u_path: Path) -> list[str]:
    """Read non-empty lines from an M3U file."""
    content = m3u_path.read_text().strip()
    if not content:
        return []
    return [line for line in content.split("\n") if line]


class TestRebuildM3uCreatesPlaylist:
    """Tests that rebuild_m3u creates a new M3U with the given entries."""

    def test_creates_m3u_with_single_track(self, tmp_path):
        track = _create_audio_file(tmp_path, "song.opus")

        result = rebuild_m3u([track], "myplaylist", tmp_path)

        assert result == tmp_path / "myplaylist.m3u"
        assert result.exists()
        entries = _read_m3u_entries(result)
        assert entries == ["song.opus"]

    def test_creates_m3u_with_multiple_tracks(self, tmp_path):
        tracks = [
            _create_audio_file(tmp_path, "track1.opus"),
            _create_audio_file(tmp_path, "track2.opus"),
            _create_audio_file(tmp_path, "track3.opus"),
        ]

        result = rebuild_m3u(tracks, "playlist", tmp_path)

        entries = _read_m3u_entries(result)
        assert entries == ["track1.opus", "track2.opus", "track3.opus"]

    def test_preserves_order_of_file_paths(self, tmp_path):
        tracks = [
            _create_audio_file(tmp_path, "zebra.opus"),
            _create_audio_file(tmp_path, "alpha.opus"),
            _create_audio_file(tmp_path, "middle.opus"),
        ]

        result = rebuild_m3u(tracks, "ordered", tmp_path)

        entries = _read_m3u_entries(result)
        assert entries == ["zebra.opus", "alpha.opus", "middle.opus"]

    def test_returns_m3u_path(self, tmp_path):
        track = _create_audio_file(tmp_path, "song.opus")

        result = rebuild_m3u([track], "test", tmp_path)

        assert result == tmp_path / "test.m3u"

    def test_strips_m3u_extension_from_name(self, tmp_path):
        track = _create_audio_file(tmp_path, "song.opus")

        result = rebuild_m3u([track], "test.m3u", tmp_path)

        assert result == tmp_path / "test.m3u"
        assert result.exists()

    def test_uses_relative_paths_in_m3u(self, tmp_path):
        subdir = tmp_path / "Artist" / "Album"
        subdir.mkdir(parents=True)
        track = _create_audio_file(subdir, "song.opus")

        result = rebuild_m3u([track], "playlist", tmp_path)

        entries = _read_m3u_entries(result)
        assert entries == ["Artist/Album/song.opus"]


class TestRebuildM3uRemovesStaleEntries:
    """Tests that rebuild_m3u removes entries not in the file_paths list (the core bug fix)."""

    def test_replaces_old_entries_with_new_ones(self, tmp_path):
        old_track = _create_audio_file(tmp_path, "old.opus")
        new_track = _create_audio_file(tmp_path, "new.opus")

        # Build initial playlist with old track
        rebuild_m3u([old_track], "playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert "old.opus" in entries

        # Rebuild with only new track -- old track should be gone
        rebuild_m3u([new_track], "playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert entries == ["new.opus"]
        assert "old.opus" not in entries

    def test_removes_all_previous_entries_when_none_provided(self, tmp_path):
        tracks = [
            _create_audio_file(tmp_path, "a.opus"),
            _create_audio_file(tmp_path, "b.opus"),
        ]
        rebuild_m3u(tracks, "playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert len(entries) == 2

        # Rebuild with empty list
        rebuild_m3u([], "playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert entries == []

    def test_subset_of_tracks_removes_the_rest(self, tmp_path):
        tracks = [
            _create_audio_file(tmp_path, "keep1.opus"),
            _create_audio_file(tmp_path, "keep2.opus"),
            _create_audio_file(tmp_path, "remove.opus"),
        ]
        rebuild_m3u(tracks, "playlist", tmp_path)

        # Rebuild with only two of the three
        rebuild_m3u([tracks[0], tracks[1]], "playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert entries == ["keep1.opus", "keep2.opus"]
        assert "remove.opus" not in entries


class TestRebuildM3uSkipsNonexistentFiles:
    """Tests that rebuild_m3u skips files that don't exist on disk."""

    def test_skips_missing_file(self, tmp_path):
        existing = _create_audio_file(tmp_path, "exists.opus")
        missing = tmp_path / "missing.opus"  # never created

        result = rebuild_m3u([existing, missing], "playlist", tmp_path)

        entries = _read_m3u_entries(result)
        assert entries == ["exists.opus"]

    def test_all_files_missing_produces_empty_playlist(self, tmp_path):
        missing1 = tmp_path / "gone1.opus"
        missing2 = tmp_path / "gone2.opus"

        result = rebuild_m3u([missing1, missing2], "playlist", tmp_path)

        assert result.exists()
        entries = _read_m3u_entries(result)
        assert entries == []

    def test_skips_deleted_file(self, tmp_path):
        track = _create_audio_file(tmp_path, "temp.opus")
        track.unlink()  # delete it before rebuild

        result = rebuild_m3u([track], "playlist", tmp_path)

        entries = _read_m3u_entries(result)
        assert entries == []


class TestRebuildM3uEmptyFilePathsList:
    """Tests that rebuild_m3u handles empty file_paths list (writes empty file)."""

    def test_empty_list_creates_empty_m3u(self, tmp_path):
        result = rebuild_m3u([], "empty", tmp_path)

        assert result.exists()
        content = result.read_text()
        assert content == ""

    def test_empty_list_overwrites_existing_playlist(self, tmp_path):
        track = _create_audio_file(tmp_path, "song.opus")
        rebuild_m3u([track], "playlist", tmp_path)

        # Verify it had content
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert len(entries) == 1

        # Rebuild with empty list
        rebuild_m3u([], "playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert entries == []

    def test_empty_list_returns_correct_path(self, tmp_path):
        result = rebuild_m3u([], "mylist", tmp_path)
        assert result == tmp_path / "mylist.m3u"


class TestRebuildM3uSyncIntegration:
    """Integration-style tests simulating the sync flow."""

    def test_sync_removes_deleted_track(self, tmp_path):
        """Simulate: 3 tracks synced, 1 deleted, rebuild with remaining 2."""
        track_a = _create_audio_file(tmp_path, "artist - songA.opus")
        track_b = _create_audio_file(tmp_path, "artist - songB.opus")
        track_c = _create_audio_file(tmp_path, "artist - songC.opus")

        # Initial sync: all 3 tracks
        rebuild_m3u([track_a, track_b, track_c], "sync_playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "sync_playlist.m3u")
        assert len(entries) == 3

        # Sync detects songB should be removed -- delete from disk
        track_b.unlink()

        # Rebuild with only the remaining tracks
        rebuild_m3u([track_a, track_c], "sync_playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "sync_playlist.m3u")
        assert len(entries) == 2
        assert "artist - songA.opus" in entries
        assert "artist - songC.opus" in entries
        assert "artist - songB.opus" not in entries

    def test_sync_adds_new_and_removes_old(self, tmp_path):
        """Simulate: initial sync with 2 tracks, next sync adds 1 and removes 1."""
        track_old = _create_audio_file(tmp_path, "old_hit.opus")
        track_keep = _create_audio_file(tmp_path, "classic.opus")

        # First sync
        rebuild_m3u([track_old, track_keep], "charts", tmp_path)
        entries = _read_m3u_entries(tmp_path / "charts.m3u")
        assert len(entries) == 2

        # Next sync: old_hit dropped from chart, new_hit added
        track_old.unlink()
        track_new = _create_audio_file(tmp_path, "new_hit.opus")

        rebuild_m3u([track_keep, track_new], "charts", tmp_path)
        entries = _read_m3u_entries(tmp_path / "charts.m3u")
        assert len(entries) == 2
        assert "classic.opus" in entries
        assert "new_hit.opus" in entries
        assert "old_hit.opus" not in entries

    def test_sync_all_tracks_removed(self, tmp_path):
        """Simulate: all tracks removed during sync, playlist should be empty."""
        tracks = [
            _create_audio_file(tmp_path, f"song{i}.opus")
            for i in range(3)
        ]
        rebuild_m3u(tracks, "playlist", tmp_path)

        # All tracks removed
        for t in tracks:
            t.unlink()

        rebuild_m3u([], "playlist", tmp_path)
        entries = _read_m3u_entries(tmp_path / "playlist.m3u")
        assert entries == []
        assert (tmp_path / "playlist.m3u").exists()

    def test_sync_with_album_subdirectories(self, tmp_path):
        """Simulate sync with album-mode organization (subdirectories)."""
        album_dir = tmp_path / "Artist" / "Album"
        album_dir.mkdir(parents=True)
        track_a = _create_audio_file(album_dir, "01 - First.opus")
        track_b = _create_audio_file(album_dir, "02 - Second.opus")
        track_c = _create_audio_file(album_dir, "03 - Third.opus")

        # Initial sync
        rebuild_m3u([track_a, track_b, track_c], "album_sync", tmp_path)
        entries = _read_m3u_entries(tmp_path / "album_sync.m3u")
        assert len(entries) == 3
        assert "Artist/Album/01 - First.opus" in entries

        # Remove middle track
        track_b.unlink()
        rebuild_m3u([track_a, track_c], "album_sync", tmp_path)
        entries = _read_m3u_entries(tmp_path / "album_sync.m3u")
        assert len(entries) == 2
        assert "Artist/Album/01 - First.opus" in entries
        assert "Artist/Album/03 - Third.opus" in entries
        assert "Artist/Album/02 - Second.opus" not in entries

    def test_no_temp_file_left_after_rebuild(self, tmp_path):
        """Verify atomic write doesn't leave temp files."""
        track = _create_audio_file(tmp_path, "song.opus")
        rebuild_m3u([track], "playlist", tmp_path)

        temp_file = tmp_path / "playlist.m3u.tmp"
        assert not temp_file.exists()
