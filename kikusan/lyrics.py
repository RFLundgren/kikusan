"""Lyrics fetching from lrclib.net."""

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

LRCLIB_BASE_URL = "https://lrclib.net/api"


def get_lyrics(track_name: str, artist_name: str, duration_seconds: int) -> str | None:
    """
    Fetch synced lyrics from lrclib.net.

    Args:
        track_name: Song title
        artist_name: Artist name
        duration_seconds: Track duration in seconds

    Returns:
        LRC formatted lyrics string, or None if not found
    """
    try:
        response = httpx.get(
            f"{LRCLIB_BASE_URL}/get",
            params={
                "track_name": track_name,
                "artist_name": artist_name,
                "duration": duration_seconds,
            },
            timeout=10.0,
        )

        if response.status_code == 404:
            logger.info("No lyrics found for: %s - %s", artist_name, track_name)
            return None

        response.raise_for_status()
        data = response.json()

        # Prefer synced lyrics, fall back to plain
        synced = data.get("syncedLyrics")
        if synced:
            logger.info("Found synced lyrics for: %s - %s", artist_name, track_name)
            return synced

        plain = data.get("plainLyrics")
        if plain:
            logger.info("Found plain lyrics for: %s - %s", artist_name, track_name)
            return plain

        return None

    except httpx.HTTPError as e:
        logger.warning("Failed to fetch lyrics: %s", e)
        return None


def save_lyrics(lyrics: str, audio_path: Path) -> Path:
    """
    Save lyrics as an LRC file alongside the audio file.

    Args:
        lyrics: LRC formatted lyrics string
        audio_path: Path to the audio file

    Returns:
        Path to the saved LRC file
    """
    lrc_path = audio_path.with_suffix(".lrc")
    lrc_path.write_text(lyrics, encoding="utf-8")
    logger.info("Saved lyrics to: %s", lrc_path)
    return lrc_path
