"""Explore (charts/moods/genres) synchronization logic for cron mode.

Fetches tracks from YouTube Music charts or mood/genre playlists and
synchronizes them using the same infrastructure as playlist sync:
state tracking, download with lyrics, M3U playlist updates,
cross-reference protection, and Navidrome protection.
"""

import logging
from datetime import datetime
from pathlib import Path

from kikusan.config import get_config
from kikusan.cron.config import ExploreConfig
from kikusan.cron.state import PlaylistState, TrackState, get_state_dir, load_state, save_state
from kikusan.cron.sync import SyncResult, compare_tracks, download_new_tracks, remove_old_tracks, update_m3u_playlist
from kikusan.search import get_charts, get_mood_playlists, get_playlist_tracks

logger = logging.getLogger(__name__)


def sync_explore(
    explore_config: ExploreConfig,
    download_dir: Path,
    audio_format: str,
    filename_template: str,
    organization_mode: str = "flat",
    use_primary_artist: bool = False,
) -> SyncResult:
    """Synchronize an explore source (charts or mood/genre).

    Fetches the current track list from YouTube Music, compares it with
    the saved state, downloads new tracks, optionally removes old ones,
    and updates the M3U playlist.

    Args:
        explore_config: Explore entry configuration
        download_dir: Download directory
        audio_format: Audio format (opus, mp3, flac)
        filename_template: Filename template for downloads
        organization_mode: File organization mode ("flat" or "album")
        use_primary_artist: Extract primary artist for folder (before feat., &, etc.)

    Returns:
        SyncResult with counts of operations performed
    """
    logger.info(
        "Starting explore sync: %s (type=%s)",
        explore_config.name,
        explore_config.type,
    )

    state_dir = get_state_dir(download_dir)

    try:
        # Fetch current tracks based on explore type
        current_tracks = fetch_explore_tracks(explore_config)
        if not current_tracks:
            logger.warning("No tracks found for explore source: %s", explore_config.name)
            return SyncResult(downloaded=0, skipped=0, deleted=0, failed=0)

        logger.info("Found %d track(s) from explore source", len(current_tracks))

        # Load existing state (reuses the same PlaylistState model)
        state = load_state(state_dir, explore_config.name)
        if not state:
            state = PlaylistState(
                playlist_name=explore_config.name,
                url=_build_explore_url(explore_config),
                last_check=datetime.now().isoformat(),
                tracks=[],
            )
            logger.info("Created fresh state for explore source: %s", explore_config.name)

        # Compare tracks
        new_tracks, removed_tracks = compare_tracks(current_tracks, state)

        logger.info(
            "Changes detected: %d new, %d removed",
            len(new_tracks),
            len(removed_tracks),
        )

        # Download new tracks
        download_result = download_new_tracks(
            new_tracks,
            download_dir,
            audio_format,
            filename_template,
            state,
            organization_mode,
            use_primary_artist,
        )

        # Remove old tracks if sync=true
        deleted_count = 0
        if explore_config.sync and removed_tracks:
            deleted_count = remove_old_tracks(removed_tracks, state, download_dir)

        # Update M3U playlist
        update_m3u_playlist(explore_config.name, state, download_dir)

        # Update and save state
        state.url = _build_explore_url(explore_config)
        state.last_check = datetime.now().isoformat()
        save_state(state_dir, state)

        result = SyncResult(
            downloaded=download_result["downloaded"],
            skipped=download_result["skipped"],
            deleted=deleted_count,
            failed=download_result["failed"],
        )

        logger.info(
            "Explore sync completed for %s: %d downloaded, %d skipped, %d deleted, %d failed",
            explore_config.name,
            result.downloaded,
            result.skipped,
            result.deleted,
            result.failed,
        )

        return result

    except Exception as e:
        logger.error("Explore sync failed for %s: %s", explore_config.name, e)
        return SyncResult(downloaded=0, skipped=0, deleted=0, failed=1)


def fetch_explore_tracks(explore_config: ExploreConfig) -> list[tuple[str, str, str]]:
    """Fetch current tracks from an explore source.

    For charts: fetches chart tracks via get_charts().
    For mood: fetches all playlists for the mood/genre params,
    then fetches tracks from each playlist.

    Args:
        explore_config: Explore entry configuration

    Returns:
        List of tuples: (video_id, title, artist)
    """
    if explore_config.type == "charts":
        return _fetch_chart_tracks(explore_config.country)
    elif explore_config.type == "mood":
        return _fetch_mood_tracks(explore_config.params)
    else:
        logger.error("Unknown explore type: %s", explore_config.type)
        return []


def _fetch_chart_tracks(country: str) -> list[tuple[str, str, str]]:
    """Fetch tracks from YouTube Music charts.

    Args:
        country: ISO 3166-1 Alpha-2 country code

    Returns:
        List of tuples: (video_id, title, artist)
    """
    try:
        charts = get_charts(country)
        tracks = []
        for chart_track in charts.tracks:
            if chart_track.video_id:
                tracks.append((chart_track.video_id, chart_track.title, chart_track.artist))
        logger.info("Fetched %d chart tracks for country %s", len(tracks), country)
        return tracks
    except Exception as e:
        logger.error("Failed to fetch chart tracks for %s: %s", country, e)
        return []


def _fetch_mood_tracks(params: str) -> list[tuple[str, str, str]]:
    """Fetch tracks from all playlists in a mood/genre category.

    First fetches the list of playlists for the category, then fetches
    tracks from each playlist. Deduplicates by video_id to avoid
    downloading the same track twice.

    Args:
        params: Mood/genre category params string

    Returns:
        List of tuples: (video_id, title, artist)
    """
    try:
        playlists = get_mood_playlists(params)
        if not playlists:
            logger.warning("No playlists found for mood params: %s", params)
            return []

        logger.info("Found %d playlists for mood category", len(playlists))

        seen_ids = set()
        tracks = []

        for playlist in playlists:
            try:
                playlist_tracks = get_playlist_tracks(playlist.playlist_id)
                for track in playlist_tracks:
                    if track.video_id and track.video_id not in seen_ids:
                        seen_ids.add(track.video_id)
                        tracks.append((track.video_id, track.title, track.artist))
            except Exception as e:
                logger.warning(
                    "Failed to fetch tracks from playlist '%s' (%s): %s",
                    playlist.title,
                    playlist.playlist_id,
                    e,
                )

        logger.info("Fetched %d unique tracks from %d mood playlists", len(tracks), len(playlists))
        return tracks

    except Exception as e:
        logger.error("Failed to fetch mood playlists for params %s: %s", params, e)
        return []


def _build_explore_url(explore_config: ExploreConfig) -> str:
    """Build a descriptive URL string for the state file.

    This is not a real URL but a human-readable identifier stored in
    the state file to describe the explore source.

    Args:
        explore_config: Explore entry configuration

    Returns:
        Descriptive string identifying the explore source
    """
    if explore_config.type == "charts":
        return f"explore:charts:{explore_config.country}"
    elif explore_config.type == "mood":
        return f"explore:mood:{explore_config.params}"
    return f"explore:{explore_config.type}"
