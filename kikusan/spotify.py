"""Spotify playlist support."""

import logging
import re
from dataclasses import dataclass

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from kikusan.config import get_config

logger = logging.getLogger(__name__)

SPOTIFY_PLAYLIST_PATTERN = re.compile(
    r"(?:https?://)?(?:open\.)?spotify\.com/playlist/([a-zA-Z0-9]+)"
)
SPOTIFY_ALBUM_PATTERN = re.compile(
    r"(?:https?://)?(?:open\.)?spotify\.com/album/([a-zA-Z0-9]+)"
)


@dataclass
class SpotifyTrack:
    """Represents a track from Spotify."""

    name: str
    artist: str
    artists: list[str]
    album: str | None
    duration_ms: int

    @property
    def search_query(self) -> str:
        """Generate a search query for YouTube Music."""
        return f"{self.name} {self.artist}"


def is_spotify_url(url: str) -> bool:
    """Check if a URL is a Spotify playlist or album URL."""
    return bool(SPOTIFY_PLAYLIST_PATTERN.match(url) or SPOTIFY_ALBUM_PATTERN.match(url))


def get_spotify_client() -> spotipy.Spotify:
    """Get an authenticated Spotify client."""
    config = get_config()

    if not config.spotify_configured:
        raise ValueError(
            "Spotify credentials not configured. "
            "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables."
        )

    auth_manager = SpotifyClientCredentials(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def get_playlist_tracks(url: str) -> list[SpotifyTrack]:
    """
    Fetch tracks from a Spotify playlist URL.

    Args:
        url: Spotify playlist URL

    Returns:
        List of SpotifyTrack objects
    """
    match = SPOTIFY_PLAYLIST_PATTERN.match(url)
    if not match:
        raise ValueError(f"Invalid Spotify playlist URL: {url}")

    playlist_id = match.group(1)
    sp = get_spotify_client()

    tracks = []
    offset = 0
    limit = 100

    # Fetch playlist info
    playlist_info = sp.playlist(playlist_id, fields="name")
    playlist_name = playlist_info.get("name", "Unknown Playlist")
    logger.info("Fetching Spotify playlist: %s", playlist_name)

    # Paginate through all tracks
    while True:
        results = sp.playlist_tracks(
            playlist_id,
            offset=offset,
            limit=limit,
            fields="items(track(name,artists,album,duration_ms)),total",
        )

        for item in results.get("items", []):
            track = item.get("track")
            if not track:
                continue

            artist_objects = track.get("artists", [])
            artist_names = [a["name"] for a in artist_objects] if artist_objects else ["Unknown Artist"]
            artist_name = artist_names[0]  # Primary artist for display/compatibility

            album = track.get("album")
            album_name = album.get("name") if album else None

            tracks.append(
                SpotifyTrack(
                    name=track.get("name", "Unknown"),
                    artist=artist_name,
                    artists=artist_names,
                    album=album_name,
                    duration_ms=track.get("duration_ms", 0),
                )
            )

        total = results.get("total", 0)
        offset += limit

        if offset >= total:
            break

    logger.info("Found %d tracks in Spotify playlist", len(tracks))
    return tracks


def get_album_tracks(url: str) -> list[SpotifyTrack]:
    """
    Fetch tracks from a Spotify album URL.

    Args:
        url: Spotify album URL

    Returns:
        List of SpotifyTrack objects
    """
    match = SPOTIFY_ALBUM_PATTERN.match(url)
    if not match:
        raise ValueError(f"Invalid Spotify album URL: {url}")

    album_id = match.group(1)
    sp = get_spotify_client()

    # Fetch album info
    album_info = sp.album(album_id)
    album_name = album_info.get("name", "Unknown Album")
    album_artists = album_info.get("artists", [])
    album_artist = album_artists[0]["name"] if album_artists else "Unknown Artist"

    logger.info("Fetching Spotify album: %s - %s", album_artist, album_name)

    tracks = []
    offset = 0
    limit = 50

    # Paginate through all tracks
    while True:
        results = sp.album_tracks(album_id, offset=offset, limit=limit)

        for track in results.get("items", []):
            artist_objects = track.get("artists", [])
            artist_names = [a["name"] for a in artist_objects] if artist_objects else [album_artist]
            artist_name = artist_names[0]  # Primary artist for display/compatibility

            tracks.append(
                SpotifyTrack(
                    name=track.get("name", "Unknown"),
                    artist=artist_name,
                    artists=artist_names,
                    album=album_name,
                    duration_ms=track.get("duration_ms", 0),
                )
            )

        total = results.get("total", 0)
        offset += limit

        if offset >= total:
            break

    logger.info("Found %d tracks in Spotify album", len(tracks))
    return tracks


def get_tracks_from_url(url: str) -> list[SpotifyTrack]:
    """
    Fetch tracks from a Spotify URL (playlist or album).

    Args:
        url: Spotify playlist or album URL

    Returns:
        List of SpotifyTrack objects
    """
    if SPOTIFY_PLAYLIST_PATTERN.match(url):
        return get_playlist_tracks(url)
    elif SPOTIFY_ALBUM_PATTERN.match(url):
        return get_album_tracks(url)
    else:
        raise ValueError(f"Unsupported Spotify URL: {url}")
