"""Reference checking for safe file deletion across playlists and plugins."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from kikusan.cron.state import load_state as load_playlist_state
from kikusan.plugins.state import load_plugin_state

logger = logging.getLogger(__name__)


@dataclass
class NavidromeProtectionCache:
    """Cache of Navidrome protection data for batch operations."""

    starred_songs: list
    keep_playlist_songs: list
    enabled: bool


def is_safe_to_delete(
    file_path: Path,
    download_dir: Path,
    current_playlist_name: str | None = None,
    current_plugin_name: str | None = None,
    navidrome_cache: NavidromeProtectionCache | None = None,
) -> bool:
    """
    Check if a file can be safely deleted without breaking other playlists/plugins.

    This function scans all playlist and plugin state files to determine if
    the given file is referenced by any other source besides the current one.
    Also checks Navidrome protection (starred songs and keep playlist).

    Args:
        file_path: Path to the file to check
        download_dir: Download directory (used to locate state files)
        current_playlist_name: Name of the playlist requesting deletion (to exclude from check)
        current_plugin_name: Name of the plugin requesting deletion (to exclude from check)
        navidrome_cache: Optional Navidrome protection cache for batch operations

    Returns:
        True if safe to delete (no other references), False otherwise
    """
    file_path_str = str(file_path)

    # Check playlist states
    playlist_state_dir = download_dir / ".kikusan" / "state"
    if playlist_state_dir.exists():
        for state_file in playlist_state_dir.glob("*.json"):
            # Skip temp files and current playlist
            if state_file.suffix == ".tmp":
                continue

            playlist_name = state_file.stem
            if playlist_name == current_playlist_name:
                continue

            # Load state and check for file reference
            try:
                state = load_playlist_state(playlist_state_dir, playlist_name)
                if state:
                    for track in state.tracks:
                        if track.file_path == file_path_str:
                            logger.info(
                                "File %s is still referenced by playlist '%s', not deleting",
                                file_path.name,
                                playlist_name,
                            )
                            return False
            except Exception as e:
                logger.warning(
                    "Failed to load playlist state %s: %s",
                    state_file,
                    e,
                )
                # Continue checking other states

    # Check plugin states
    plugin_state_dir = download_dir / ".kikusan" / "plugin_state"
    if plugin_state_dir.exists():
        for state_file in plugin_state_dir.glob("*.json"):
            # Skip temp files and current plugin
            if state_file.suffix == ".tmp":
                continue

            plugin_name = state_file.stem
            if plugin_name == current_plugin_name:
                continue

            # Load state and check for file reference
            try:
                state = load_plugin_state(plugin_state_dir, plugin_name)
                if state:
                    for track in state.tracks:
                        if track.file_path == file_path_str:
                            logger.info(
                                "File %s is still referenced by plugin '%s', not deleting",
                                file_path.name,
                                plugin_name,
                            )
                            return False
            except Exception as e:
                logger.warning(
                    "Failed to load plugin state %s: %s",
                    state_file,
                    e,
                )
                # Continue checking other states

    # Check Navidrome protection
    if not _check_navidrome_protection(file_path, navidrome_cache):
        return False

    # No other references found, safe to delete
    return True


def _extract_metadata(file_path: Path) -> tuple[str, str]:
    """
    Extract artist and title from audio file metadata.

    Prefers ARTISTS multi-value tag if available, falls back to ARTIST.

    Args:
        file_path: Path to audio file

    Returns:
        Tuple of (artist, title) - defaults to ("Unknown", "Unknown") on error
    """
    try:
        from mutagen import File

        audio = File(file_path)
        if not audio:
            return "Unknown", "Unknown"

        # Try ARTISTS first (multi-value tag), then fall back to artist
        artist = audio.get("ARTISTS") or audio.get("artists") or audio.get("artist", ["Unknown"])
        title = audio.get("title", ["Unknown"])

        # Handle both list and string formats
        if isinstance(artist, list):
            artist = artist[0] if artist else "Unknown"
        if isinstance(title, list):
            title = title[0] if title else "Unknown"

        return str(artist), str(title)

    except Exception as e:
        logger.debug("Failed to extract metadata from %s: %s", file_path, e)
        return "Unknown", "Unknown"


def _check_navidrome_protection(
    file_path: Path,
    navidrome_cache: NavidromeProtectionCache | None = None,
) -> bool:
    """
    Check if file is protected by Navidrome (starred or in keep playlist).

    Args:
        file_path: Path to file to check
        navidrome_cache: Optional pre-fetched Navidrome protection cache

    Returns:
        True if safe to delete (not protected)
        False if protected or error occurred
    """
    from kikusan.navidrome import (
        get_navidrome_client,
        is_navidrome_enabled,
        is_song_in_navidrome_list,
    )

    # Skip if not configured
    if not is_navidrome_enabled():
        return True

    # Use cached data if provided
    if navidrome_cache is not None:
        if not navidrome_cache.enabled:
            return True

        # Extract metadata from file
        artist, title = _extract_metadata(file_path)

        # Check starred songs
        matched, reason = is_song_in_navidrome_list(
            file_path,
            artist,
            title,
            navidrome_cache.starred_songs,
            "starred in Navidrome",
        )
        if matched:
            logger.info(
                "File %s is protected (%s), not deleting",
                file_path.name,
                reason,
            )
            return False

        # Check keep playlist
        matched, reason = is_song_in_navidrome_list(
            file_path,
            artist,
            title,
            navidrome_cache.keep_playlist_songs,
            f"in Navidrome playlist '{os.getenv('NAVIDROME_KEEP_PLAYLIST', 'keep')}'",
        )
        if matched:
            logger.info(
                "File %s is protected (%s), not deleting",
                file_path.name,
                reason,
            )
            return False

        return True

    # Fallback: fetch data on-demand (shouldn't happen in batch operations)
    try:
        client = get_navidrome_client()
        if not client:
            return True

        # Extract metadata from file
        artist, title = _extract_metadata(file_path)

        # Check starred songs
        starred_songs = client.get_starred_songs()
        matched, reason = is_song_in_navidrome_list(
            file_path, artist, title, starred_songs, "starred in Navidrome"
        )
        if matched:
            logger.info(
                "File %s is protected (%s), not deleting",
                file_path.name,
                reason,
            )
            return False

        # Check keep playlist
        keep_playlist_name = os.getenv("NAVIDROME_KEEP_PLAYLIST", "keep")
        playlist_id = client.find_playlist_by_name(keep_playlist_name)

        if playlist_id:
            playlist_songs = client.get_playlist_songs(playlist_id)
            matched, reason = is_song_in_navidrome_list(
                file_path,
                artist,
                title,
                playlist_songs,
                f"in Navidrome playlist '{keep_playlist_name}'",
            )
            if matched:
                logger.info(
                    "File %s is protected (%s), not deleting",
                    file_path.name,
                    reason,
                )
                return False

        # Not protected
        return True

    except Exception as e:
        logger.warning(
            "Navidrome check failed for %s: %s - keeping file to be safe",
            file_path.name,
            e,
        )
        # Fail-safe: don't delete on error
        return False


def get_navidrome_protection_cache() -> NavidromeProtectionCache:
    """
    Fetch Navidrome protection data once for batch operations.

    Returns cache object that can be passed to is_safe_to_delete().

    Returns:
        NavidromeProtectionCache with starred songs and keep playlist songs
    """
    from kikusan.navidrome import get_navidrome_client, is_navidrome_enabled

    if not is_navidrome_enabled():
        return NavidromeProtectionCache(
            starred_songs=[],
            keep_playlist_songs=[],
            enabled=False,
        )

    try:
        client = get_navidrome_client()
        if not client:
            return NavidromeProtectionCache([], [], False)

        # Fetch starred songs
        starred = client.get_starred_songs()

        # Fetch keep playlist songs
        keep_playlist_name = os.getenv("NAVIDROME_KEEP_PLAYLIST", "keep")
        playlist_id = client.find_playlist_by_name(keep_playlist_name)
        playlist_songs = []
        if playlist_id:
            playlist_songs = client.get_playlist_songs(playlist_id)
        else:
            logger.info(
                "Navidrome playlist '%s' not found, skipping playlist protection",
                keep_playlist_name,
            )

        logger.info(
            "Navidrome protection loaded: %d starred, %d in '%s' playlist",
            len(starred),
            len(playlist_songs),
            keep_playlist_name,
        )

        return NavidromeProtectionCache(
            starred_songs=starred,
            keep_playlist_songs=playlist_songs,
            enabled=True,
        )

    except Exception as e:
        logger.warning("Failed to load Navidrome protection: %s", e)
        # Fail-safe: return empty cache but mark as enabled (will block deletions)
        return NavidromeProtectionCache([], [], True)
