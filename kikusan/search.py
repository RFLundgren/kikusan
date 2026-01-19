"""YouTube Music search functionality using ytmusicapi."""

import logging
from dataclasses import dataclass

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)


@dataclass
class Track:
    """Represents a music track from YouTube Music."""

    video_id: str
    title: str
    artist: str
    album: str | None
    duration_seconds: int
    thumbnail_url: str | None
    view_count: str | None

    @property
    def duration_display(self) -> str:
        """Format duration as MM:SS."""
        minutes = self.duration_seconds // 60
        seconds = self.duration_seconds % 60
        return f"{minutes}:{seconds:02d}"


def search(query: str, limit: int = 20) -> list[Track]:
    """
    Search YouTube Music for tracks.

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        List of Track objects matching the query
    """
    yt = YTMusic()
    results = yt.search(query, filter="songs", limit=limit)

    tracks = []
    for item in results:
        if item.get("resultType") != "song":
            continue

        # Extract artist name(s)
        artists = item.get("artists", [])
        artist_name = artists[0]["name"] if artists else "Unknown Artist"

        # Extract album name
        album = item.get("album")
        album_name = album["name"] if album else None

        # Extract duration in seconds
        duration_text = item.get("duration", "0:00")
        duration_seconds = _parse_duration(duration_text)

        # Extract thumbnail URL (prefer larger size)
        thumbnails = item.get("thumbnails", [])
        thumbnail_url = thumbnails[-1]["url"] if thumbnails else None

        # Extract view count (formatted string like "1.9B", "47M", etc.)
        view_count = item.get("views")

        tracks.append(
            Track(
                video_id=item["videoId"],
                title=item.get("title", "Unknown Title"),
                artist=artist_name,
                album=album_name,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                view_count=view_count,
            )
        )

    logger.info("Found %d tracks for query: %s", len(tracks), query)
    return tracks


def _parse_duration(duration_text: str) -> int:
    """Parse duration string (e.g., '3:45') to seconds."""
    parts = duration_text.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0
